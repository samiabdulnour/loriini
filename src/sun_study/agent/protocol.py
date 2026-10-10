"""JSON-RPC on stdin and stdout, the way an agent's client speaks to a tool server.

This is the Model Context Protocol's stdio transport, in the subset a tool
server needs: ``initialize``, ``ping``, ``tools/list``, ``tools/call`` and
``logging/setLevel`` in; progress and log notifications out; a cancellation
in. Written here rather than taken from the official ``mcp`` package, which
would put twenty-eight more packages into the one-file executable -- a web
server, an SSE framework, a JWT library with its cryptography -- for two
transports Loriini does not use, on an API that renamed its main class this
year. What is needed is five methods and three notifications, stable across
every published version of the protocol (D120).

What a client does: it starts this program, writes one JSON-RPC message per
line on its stdin, and reads one per line on its stdout. It opens with
``initialize`` and ``notifications/initialized``, asks ``tools/list`` once,
then ``tools/call`` as the agent decides, with ``ping`` in between. Nothing
else may be written to stdout -- a stray print is a protocol error to the
client -- which is one reason the studies run in a child process whose
output comes back through a pipe.

Requests are answered on the reading thread, except a tool call, which runs
on a thread of its own so that a ping during a six-minute study is still
answered: a client that hears nothing for a minute gives the server up for
dead. A ``notifications/cancelled`` for that call stops it the way the
window's Stop button does, and the call then gets no answer, as the
protocol asks.
"""

from __future__ import annotations

import base64
import json
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, BinaryIO

__all__ = [
    "INVALID_PARAMS",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "PROTOCOL_VERSIONS",
    "Call",
    "InvalidArgumentsError",
    "Server",
    "Tool",
    "ToolResult",
]

#: The protocol's published versions, newest first. A client asks for the
#: one it speaks; the server answers with the same when it knows it, and with
#: the newest otherwise, which is what the protocol says to do.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

# JSON-RPC's own error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

#: The protocol's log levels, least to most severe: syslog's.
LOG_LEVELS = ("debug", "info", "notice", "warning", "error", "critical", "alert", "emergency")

#: How long to wait, on the client going away, for a running study to stop.
#: ``app.runner`` asks the run to stop, waits twenty seconds, terminates it,
#: waits twenty more and kills it; this is that, with room over.
LEAVING_SECONDS = 45.0


class InvalidArgumentsError(ValueError):
    """The arguments do not fit the tool. A protocol error, not a tool's
    failure: the client sent a call the tool cannot take."""


@dataclass(frozen=True)
class ToolResult:
    """What a tool answers: text for the agent to read, and the same as data
    where a client can use it. ``is_error`` is the tool's own failure -- a
    study that stopped with an error -- which the protocol keeps apart from
    a call that could not be made at all."""

    text: str
    structured: Mapping[str, Any] | None = None
    is_error: bool = False


class Call:
    """One tool call in flight: where its progress goes, and how it is stopped.

    A tool that runs for minutes says what it is doing through ``say``, one
    line at a time; each line goes to the client as a log message and, when
    the client gave the call a progress token, as a progress notification
    too. A tool that can be stopped registers how with ``when_stopped``, and
    the server calls that if the client cancels.
    """

    def __init__(self, server: Server, request_id: object, token: object) -> None:
        self._server = server
        self._id = request_id
        self._token = token
        self._steps = 0
        self._stopped = False
        self._hook: Callable[[], None] | None = None
        self._lock = threading.Lock()

    def say(self, message: str) -> None:
        """One line of progress, to the client's log and its progress bar."""
        self._steps += 1
        self._server.log("info", message)
        if self._token is not None:
            self._server.notify(
                "notifications/progress",
                {"progressToken": self._token, "progress": self._steps, "message": message},
            )

    def when_stopped(self, hook: Callable[[], None]) -> None:
        """What to do if the client cancels. Called at once if it already has."""
        with self._lock:
            self._hook = hook
            stopped = self._stopped
        if stopped:
            hook()

    @property
    def stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            hook = self._hook
        if hook is not None:
            hook()


@dataclass(frozen=True)
class Tool:
    """One thing an agent can ask for: its name and the schema of what it
    takes, which the client shows the agent, and what runs when it asks."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    run: Callable[[Mapping[str, Any], Call], ToolResult]
    title: str = ""
    read_only: bool = False
    """True for a tool that changes nothing -- a listing -- which a client may
    run without asking its person first."""

    def descriptor(self) -> dict[str, Any]:
        """The tool as ``tools/list`` describes it."""
        described: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "annotations": {"readOnlyHint": self.read_only, "destructiveHint": not self.read_only},
        }
        if self.title:
            described["title"] = self.title
        return described


class Server:
    """The tool server: answers one client for as long as its stream lasts."""

    def __init__(
        self,
        *,
        name: str,
        version: str,
        tools: Sequence[Tool],
        instructions: str = "",
        icon: bytes | None = None,
        icon_type: str = "image/png",
    ) -> None:
        self.name = name
        self.version = version
        self.instructions = instructions
        #: The server's icon, for a client that shows one beside the server's
        #: name (the 2025-11-25 protocol's ``icons`` on ``serverInfo``, sent
        #: whatever version the client asked for, since an older client
        #: ignores a field it does not know). The bytes of a PNG, or nothing.
        self.icon = icon
        self.icon_type = icon_type
        self._tools = {tool.name: tool for tool in tools}
        self._out: BinaryIO | None = None
        self._write_lock = threading.Lock()
        self._calls: dict[Any, Call] = {}
        self._threads: list[threading.Thread] = []
        self._level = "info"
        self._gone = False
        self.protocol_version = PROTOCOL_VERSIONS[0]

    # -- the loop ----------------------------------------------------------

    def serve(self, inp: BinaryIO, out: BinaryIO) -> None:
        """Answer the client until its stream ends, then stop what is running.

        The end of the stream is the client leaving, and a study left running
        past it would hold the project's layers with nobody to stop it. So a
        running call is stopped the way a cancellation stops it, and waited
        for, before this returns and the process ends.
        """
        self._out = out
        for raw in iter(inp.readline, b""):
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self._send({"jsonrpc": "2.0", "id": None, "error": _error(PARSE_ERROR, "not JSON")})
                continue
            for one in message if isinstance(message, list) else [message]:
                self._receive(one)
        self._gone = True
        for call in list(self._calls.values()):
            call.stop()
        for thread in self._threads:
            thread.join(timeout=LEAVING_SECONDS)

    def _receive(self, message: object) -> None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            self._send(
                {"jsonrpc": "2.0", "id": None, "error": _error(INVALID_REQUEST, "not a request")}
            )
            return
        method = message.get("method")
        if method is None:
            # A response to a request of ours. There are none: this server
            # asks its client for nothing.
            return
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        if "id" not in message:
            self._notification(str(method), params)
        else:
            self._request(message["id"], str(method), params)

    def _notification(self, method: str, params: Mapping[str, Any]) -> None:
        if method == "notifications/cancelled":
            call = self._calls.get(params.get("requestId"))
            if call is not None:
                call.stop()
        # ``notifications/initialized`` and anything else: nothing to do.

    def _request(self, request_id: Any, method: str, params: Mapping[str, Any]) -> None:
        if method == "initialize":
            self._respond(request_id, self._initialize(params))
        elif method == "ping":
            self._respond(request_id, {})
        elif method == "tools/list":
            self._respond(
                request_id, {"tools": [tool.descriptor() for tool in self._tools.values()]}
            )
        elif method == "tools/call":
            self._call(request_id, params)
        elif method == "logging/setLevel":
            level = params.get("level")
            if level in LOG_LEVELS:
                self._level = str(level)
                self._respond(request_id, {})
            else:
                self._fail(request_id, INVALID_PARAMS, f"Unknown log level: {level!r}")
        else:
            self._fail(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    def _initialize(self, params: Mapping[str, Any]) -> dict[str, Any]:
        asked = params.get("protocolVersion")
        self.protocol_version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        info: dict[str, Any] = {"name": self.name, "title": self.name, "version": self.version}
        if self.icon is not None:
            encoded = base64.b64encode(self.icon).decode("ascii")
            info["icons"] = [
                {"src": f"data:{self.icon_type};base64,{encoded}", "mimeType": self.icon_type}
            ]
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {"tools": {"listChanged": False}, "logging": {}},
            "serverInfo": info,
            "instructions": self.instructions,
        }

    # -- a tool call, on its own thread ------------------------------------

    def _call(self, request_id: Any, params: Mapping[str, Any]) -> None:
        name = params.get("name")
        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            self._fail(request_id, INVALID_PARAMS, f"Unknown tool: {name!r}")
            return
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            self._fail(request_id, INVALID_PARAMS, "arguments must be an object")
            return
        meta = params.get("_meta")
        token = meta.get("progressToken") if isinstance(meta, dict) else None
        call = Call(self, request_id, token)
        self._calls[request_id] = call
        self._threads = [thread for thread in self._threads if thread.is_alive()]
        thread = threading.Thread(
            target=self._finish, args=(request_id, call, tool, arguments), daemon=True, name=name
        )
        self._threads.append(thread)
        thread.start()

    def _finish(self, request_id: Any, call: Call, tool: Tool, arguments: dict[str, Any]) -> None:
        try:
            result = tool.run(arguments, call)
        except InvalidArgumentsError as wrong:
            self._calls.pop(request_id, None)
            if not call.stopped:
                self._fail(request_id, INVALID_PARAMS, str(wrong))
            return
        except Exception as failed:
            # The protocol's own rule: a tool that fails answers with
            # ``isError``, so the agent reads what went wrong and can try
            # again; an exception on the server would end every tool.
            result = ToolResult(f"{type(failed).__name__}: {failed}", is_error=True)
        self._calls.pop(request_id, None)
        if call.stopped:
            return
        body: dict[str, Any] = {
            "content": [{"type": "text", "text": result.text}],
            "isError": result.is_error,
        }
        if result.structured is not None:
            body["structuredContent"] = dict(result.structured)
        self._respond(request_id, body)

    # -- writing -------------------------------------------------------------

    def log(self, level: str, data: Any) -> None:
        """A log message to the client, if it asked for that level or lower."""
        if LOG_LEVELS.index(level) < LOG_LEVELS.index(self._level):
            return
        self.notify("notifications/message", {"level": level, "logger": self.name, "data": data})

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _respond(self, request_id: Any, result: Mapping[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "id": request_id, "result": dict(result)})

    def _fail(self, request_id: Any, code: int, message: str) -> None:
        self._send({"jsonrpc": "2.0", "id": request_id, "error": _error(code, message)})

    def _send(self, message: Mapping[str, Any]) -> None:
        if self._out is None or self._gone:
            return
        # One line, whatever the text held: json escapes a newline inside a
        # string, so the message is a line and the framing holds.
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            try:
                self._out.write(line.encode("utf-8", "replace") + b"\n")
                self._out.flush()
            except OSError:
                # The client closed its end. The reading loop sees the same
                # and stops what is running; nothing more can be said to it.
                self._gone = True


def _error(code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}
