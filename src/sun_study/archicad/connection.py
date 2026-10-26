"""Transport for Archicad's JSON API and the Loriini add-on.

Everything in this package is written against the protocol as it actually is,
read out of the Tapir source and its published command definitions, not from
memory. ``docs/archicad.md`` records what was verified, against which version,
and where each fact came from.

**None of this package is covered by CI**, because there is no Archicad to run
against. That is the whole reason ``core`` is kept pure: the parts that can be
tested are tested exhaustively, and the part that cannot is kept thin, boring
and free of any analysis logic. The tests here exercise the request and
response handling through a fake transport; the real thing needs a human at a
workstation, following the checklist in ``docs/archicad.md``.

The protocol
------------
Archicad 24+ listens on ``http://127.0.0.1:19723`` and takes::

    {"command": "API.<Name>", "parameters": {...}}

Tapir's commands are reached through one official command::

    {"command": "API.ExecuteAddOnCommand",
     "parameters": {"addOnCommandId": {"commandNamespace": "LoriiniTapir",
                                       "commandName": "<Name>"},
                    "addOnCommandParameters": {...}}}

Tapir's command code is built into the Loriini add-on (``archicad-addon/Tapir``),
so one add-on is all a workstation needs. Its commands answer under
``LoriiniTapir``; a standalone Tapir, answering under ``TapirCommand``, is only a
fallback for a Loriini build that predates this.

**Errors arrive at two levels, and both must be checked.** The outer response
carries ``succeeded`` and may carry ``error``; the inner Tapir response, under
``result.addOnCommandResponse``, may carry its own ``error`` while the outer
call reports success. Tapir's own reference client prints both and returns
``None``, so a caller that does not inspect the return value sees a silent
failure. This module raises instead.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from sun_study import ADDON_FILE

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "PORT_RANGE",
    "UNTITLED",
    "ArchicadConnection",
    "ArchicadError",
    "ArchicadNotRunningError",
    "CommandFailedError",
    "HttpTransport",
    "Instance",
    "TapirUnavailableError",
    "Transport",
    "find_instances",
    "project_name",
    "where_archicad_actually_is",
]

DEFAULT_HOST = "http://127.0.0.1"
DEFAULT_PORT = 19723

#: Where Tapir's commands answer inside the Loriini add-on, which carries
#: Tapir's code (``archicad-addon/Tapir``). Its own namespace rather than
#: Tapir's, so a standalone Tapir left installed does not claim the same
#: commands, and so Tapir's ``CreateSlabs`` and ``CreateTexts`` stay apart from
#: Loriini's commands of the same name.
TAPIR_NAMESPACE = "LoriiniTapir"

#: The standalone Tapir add-on's namespace. Only a fallback now: used when the
#: installed Loriini predates the built-in commands and Tapir is still beside
#: it, so the two add-ons can be updated in either order.
STANDALONE_TAPIR_NAMESPACE = "TapirCommand"

#: Archicad's answer for a namespace or command no add-on registered. What
#: separates "this Loriini is too old to carry Tapir" from a real failure.
NOT_REGISTERED_CODE = 4010

#: This project's own add-on, in ``archicad-addon/``: the commands no JSON
#: command exists for at all, beside Tapir's under ``TAPIR_NAMESPACE``.
LORIINI_NAMESPACE = "Loriini"

#: A project never saved, named as Archicad's title bar names it.
#: ``GetProjectInfo`` gives one no name at all, only ``isUntitled``, and a
#: blank name reads as "no project open": the window refused a new file it had
#: read in full -- 135 layers, 55 masters -- as "could not read the project".
UNTITLED = "Untitled"

#: What to do about a missing or too-old add-on, said once so every message
#: gives the same advice.
INSTALL_LORIINI = (
    f"Install the current Loriini add-on ({ADDON_FILE}, the one for your "
    "Archicad version, built by the 'Archicad add-on' workflow), which has "
    "Tapir's commands built in."
)

#: How long to let Archicad think about one command before giving up on it.
#: Sized for the slowest thing anyone asks of it -- the IFC export -- on the
#: biggest project seen so far, with room over. The old five minutes was sized
#: for nothing in particular and a 455 MB export walked straight through it.
DEFAULT_TIMEOUT_SECONDS = 1800.0

#: Every port Archicad can put its JSON API on. Each running instance claims
#: one, in order, so the second Archicad open on a machine is on 19724 and a
#: tool hard-wired to 19723 talks to the wrong project -- or, once the first
#: instance is closed, to nothing at all. Range taken from Tapir's own client
#: (``sandbox/python-package/src/tapir_py/core.py``: ``range(19723, 19743)``).
PORT_RANGE = range(DEFAULT_PORT, 19743)

#: Tapir add-on version this package was written against. 1.5.7 was read out of
#: the repository (``archicad-addon/Sources/AddOnVersion.hpp``); 1.5.8 was
#: re-verified against a live add-on on Archicad 26 -- command registration
#: probed one by one, and the creation schemas read out of the installed
#: ``TapirAddOn_AC26_Win.apx`` itself rather than out of the sources.
VERIFIED_AGAINST_TAPIR_VERSION = "1.5.8"

#: The newest "since" version among the commands this package uses.
#: ``GetElementsByIFCIds`` arrived in 1.5.1 and is the binding constraint.
MINIMUM_TAPIR_VERSION = (1, 5, 1)


class ArchicadError(Exception):
    """Base for every failure talking to Archicad."""


class ArchicadNotRunningError(ArchicadError):
    """Nothing is listening on the JSON API port."""


class TapirUnavailableError(ArchicadError):
    """Archicad answered but Tapir's commands are missing or too old.

    They come from the Loriini add-on now; the name is kept because every
    caller that handles "the add-on is not there" already catches this.
    """


class CommandFailedError(ArchicadError):
    """Archicad accepted the request and reported a failure.

    ``code`` is Archicad's or the add-on's error code where one was given, so
    a caller can tell "not registered" from a real failure without matching
    on the words.
    """

    def __init__(self, message: str, code: Any = None) -> None:
        super().__init__(message)
        self.code = code


class Transport(Protocol):
    """Anything that can carry one JSON request and return the response.

    Exists so the request and response handling can be tested without an
    Archicad, which is the only part of this package a machine can check.
    """

    def send(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HttpTransport:
    """The real transport: an HTTP POST to Archicad's JSON API port."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    """Generous on purpose. An IFC export of a large model is not quick, and a
    timeout mid-export leaves a half-written file that looks like a real one.

    It is a hung-Archicad detector, not a budget for the export. Five minutes
    was neither: a 455 MB export of a real mixed-use project ran past it, and
    the run then died putting the layers back -- leaving the project holding
    the study's layer state, which is the one thing ``export_state`` exists to
    prevent. Raise it with ``--timeout`` rather than trimming a model to fit."""

    @property
    def url(self) -> str:
        return f"{self.host}:{self.port}"

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read()
        except urllib.error.URLError as exc:
            # Deliberately does not scan for other instances here. Building an
            # error message must not do network I/O: this path is hit on every
            # failed call, and a twenty-port scan per failure turns one dead
            # connection into a very slow one. The CLI scans once, when it has
            # decided to tell a human. See `where_archicad_actually_is`.
            raise ArchicadNotRunningError(
                f"Could not reach Archicad's JSON API at {self.url} ({exc.reason}). "
                f"Check that Archicad is running with a project open, and that the "
                f"JSON interface is enabled in Options > Work Environment > "
                f"Model Compare and JSON Interface."
            ) from exc
        except TimeoutError as exc:
            raise ArchicadError(
                f"Archicad did not answer within {self.timeout_seconds:g}s. A large "
                f"IFC export can legitimately take longer, so this is not proof "
                f"that the export failed: give it longer with --timeout, in "
                f"seconds -- or, in the window, 'Archicad wait (min)' under "
                f"Advanced. If it stops at double the wait too, the thing to "
                f"look at is Archicad itself: a dialog waiting to be clicked "
                f"stops it answering at any timeout."
            ) from exc

        try:
            decoded: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ArchicadError(
                f"Archicad returned something that is not JSON: {body[:200]!r}"
            ) from exc
        return decoded


@dataclass(frozen=True)
class Instance:
    """One running Archicad, found by scanning the port range."""

    port: int
    project: str = ""
    """The open project's name, ``UNTITLED`` for one never saved, blank if it
    could not be read."""

    def describe(self) -> str:
        return f"port {self.port}" + (f" -- {self.project}" if self.project else "")


def find_instances(
    host: str = DEFAULT_HOST,
    ports: Iterable[int] = PORT_RANGE,
    *,
    timeout_seconds: float = 0.4,
) -> tuple[Instance, ...]:
    """Every Archicad answering on the JSON API, with the project each has open.

    Archicad gives each running instance its own port in order, so a second
    project opened alongside the first is on 19724 and the default port either
    reaches the wrong project or, once the first is closed, nothing at all.
    That failure reads as "Archicad is not running" and sends people to check
    a setting that was never off, so the answer is to go and look.

    Deliberately impatient. This runs on a path that has already failed, and
    twenty ports at the normal timeout would be a very long wait to be told
    something simple.
    """
    found: list[Instance] = []
    for port in ports:
        probe = HttpTransport(host=host, port=port, timeout_seconds=timeout_seconds)
        try:
            alive = probe.send({"command": "API.IsAlive", "parameters": {}})
        except ArchicadError:
            continue
        if not alive.get("succeeded"):
            continue
        found.append(Instance(port=port, project=_project_name(probe)))
    return tuple(found)


def _project_name(probe: HttpTransport) -> str:
    """The open project's name, or blank.

    Best effort: an instance with no project open still answers ``IsAlive``,
    and knowing a port is live is most of the value even without a name.
    """
    for namespace in (TAPIR_NAMESPACE, STANDALONE_TAPIR_NAMESPACE):
        try:
            response = probe.send(
                {
                    "command": "API.ExecuteAddOnCommand",
                    "parameters": {
                        "addOnCommandId": {
                            "commandNamespace": namespace,
                            "commandName": "GetProjectInfo",
                        },
                        "addOnCommandParameters": {},
                    },
                }
            )
        except ArchicadError:
            return ""
        inner = (response.get("result") or {}).get("addOnCommandResponse") or {}
        if not isinstance(inner, dict) or "error" in inner:
            continue
        return project_name(inner)
    return ""


def project_name(info: dict[str, Any]) -> str:
    """The name in a ``GetProjectInfo`` answer: ``UNTITLED`` for a project
    never saved, blank when there is none to give."""
    name = info.get("projectName") or info.get("projectPath") or ""
    if isinstance(name, str) and name:
        return name
    return UNTITLED if info.get("isUntitled") is True else ""


#: Archicad refuses every API call while a modal dialog is open, and answers
#: with this. It is the single most common way a run fails on a workstation
#: somebody is also *using*: leave Object Settings open, and nothing works
#: until it is closed. Worth its own message, because "Invalid program status"
#: reads like a fault in the tool.
BUSY_STATUS_CODE = 4001

#: The same code with these words is something else: the person is in the
#: middle of doing something by hand -- a double-click still landing, a drag,
#: a field being typed in -- and Archicad refuses the API for exactly that
#: long. It passes in a moment, where a dialog stays open until it is closed.
#: A run that asks the person to double-click a worksheet, sees it in front,
#: and sends its next command while the mouse is still down meets this every
#: time, so the request is retried for a while before it is given up on.
INPUT_BUSY_WORDS = "ongoing user input"
INPUT_WAIT_S = 30.0
INPUT_PAUSE_S = 1.0

#: Replaced by the tests, so that a wait of thirty seconds costs them nothing.
_sleep = time.sleep
_clock = time.monotonic


def _busy_with_input(error: dict[str, Any]) -> bool:
    return error.get("code") == BUSY_STATUS_CODE and INPUT_BUSY_WORDS in str(
        error.get("message", "")
    )


def _not_registered(error: ArchicadError) -> bool:
    """Whether a failure means "nobody registered that", not "that went wrong".

    Both shapes count: Archicad's code 4010, and an envelope that came back
    with no add-on response at all.
    """
    if isinstance(error, TapirUnavailableError):
        return True
    return isinstance(error, CommandFailedError) and error.code == NOT_REGISTERED_CODE


def _explain(command: str, error: dict[str, Any]) -> str:
    """A failed official command, in words that name the fix where there is one."""
    message = str(error.get("message", "no message"))
    code = error.get("code", "none")
    if _busy_with_input(error):
        return (
            f"Archicad is busy and refused the request: {message}\n"
            f"Something is still being done in Archicad by hand -- a drag, a "
            f"double-click, a field being edited -- and Archicad refuses the API "
            f"while it lasts. The request was retried for {INPUT_WAIT_S:.0f} seconds. "
            f"Let go of the mouse, finish or cancel the edit, and run this again "
            f"-- this is not a problem with the project or the tool."
        )
    if code == BUSY_STATUS_CODE:
        return (
            f"Archicad is busy and refused the request: {message}\n"
            f"Close the dialog in Archicad and run this again. Archicad blocks its "
            f"whole API while a modal dialog is open, so nothing will work until "
            f"then -- this is not a problem with the project or the tool."
        )
    return f"{command} failed: {message} (code {code})"


def where_archicad_actually_is(
    tried: int, host: str = DEFAULT_HOST, ports: Iterable[int] = PORT_RANGE
) -> str:
    """Where Archicad *is* listening, if anywhere, or ``""`` if that adds nothing.

    Called once by the CLI after a connection has already failed, never from
    the transport. The default message sends people to the Work Environment
    setting, which is the wrong place whenever the real cause is a second
    Archicad holding the port -- so this goes and looks before letting that
    advice stand.
    """
    others = [instance for instance in find_instances(host, ports) if instance.port != tried]
    if not others:
        return ""
    listed = "; ".join(instance.describe() for instance in others)
    return (
        f"Archicad IS answering, on another port: {listed}. Each running instance "
        f"gets its own port, so a second project opened alongside the first does not "
        f"take {PORT_RANGE.start}. Re-run with --port {others[0].port}, or close the "
        f"other instances and reopen this project."
    )


@dataclass(frozen=True)
class Database:
    """Which database this tool last made current, and of what kind.

    Archicad will not say. ``GetCurrentWindowType`` answers for the *window*
    on screen, which is a different thing: ``ChangeWindow`` moves the current
    database while the visible window stays put, so a run can be looking at a
    floor plan with a layout current underneath it. There is no
    ``GetCurrentDatabase`` -- it is unregistered on Tapir 1.5.7 *and* on 1.5.8,
    along with ``GetCurrentWindow`` and ``GetDatabases``. Re-probed against a
    live 1.5.8 add-on: all three still answer *"Archicad does not have the
    registered Add-On command"*, so this is not a gap an update closes.

    So the tool remembers instead of asking. That is sound because the tool is
    the only thing moving the database during a run, and it is honest about
    its limit: a person who clicks into a layout mid-run makes this stale, and
    ``None`` means nobody has moved it yet and the answer is unknown.
    """

    guid: str
    window_type: str

    @property
    def is_model(self) -> bool:
        """True for a floor plan -- the only database the *building* is in.

        A layout holds drawings, a worksheet holds whatever was drawn into it,
        and neither holds a wall. This is what separates a database a study
        can read from one it cannot.
        """
        return self.window_type == "FloorPlan"


def activate(connection: ArchicadConnection, database_id: str, window_type: str) -> None:
    """Make one database current, so reads and creation land in it.

    Here, rather than beside the callers, because moving the database is what
    the connection remembers and the two belong together -- three call sites
    used to issue the raw command and none of them looked at the answer.

    Checking is not a formality. On AC26 only the ``databaseId`` form works;
    the ``navigatorItemId`` form is rejected as needing Archicad 27. And
    ``GetCurrentWindowType`` is *not* a check on this -- the database moves
    while the visible window does not, so it reports ``FloorPlan`` either way.
    The command's own result is the only confirmation there is, and a refused
    move leaves the previous database current, so a read that follows one
    quietly answers about the wrong sheet.
    """
    result = connection.run_tapir(
        "ChangeWindow", {"databaseId": {"guid": database_id}, "windowType": window_type}
    )
    if isinstance(result, dict) and result.get("success"):
        return
    hint = (
        " A worksheet created through the API has to be opened by a person "
        "once -- double-clicked in the Project Map -- before it can ever be "
        "activated. Reopening the project does not do it (measured, D95)."
        if window_type == "Worksheet"
        else " A layout is only readable once the project has been saved since it was made."
        if window_type == "Layout"
        else ""
    )
    raise ArchicadError(
        f"Could not make {window_type} database {database_id} current: {result!r}.{hint}"
    )


class ArchicadConnection:
    """A connection to Archicad, with Tapir's commands reachable through it."""

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport if transport is not None else HttpTransport()
        self._tapir_version: str | None = None
        self._tapir_namespace: str | None = None
        self._database: Database | None = None

    # -- raw protocol ----------------------------------------------------
    def run_official(self, command: str, parameters: dict[str, Any] | None = None) -> Any:
        """Run one of Archicad's own ``API.*`` commands.

        A refusal for *ongoing user input* is waited out: the request is sent
        again every ``INPUT_PAUSE_S`` for up to ``INPUT_WAIT_S``, since what
        refuses it is a hand on the mouse, not a dialog. Everything else
        fails at once.
        """
        payload = {"command": command, "parameters": parameters or {}}
        give_up_at: float | None = None
        while True:
            response = self._transport.send(payload)
            if response.get("succeeded", False):
                return response.get("result")
            error = response.get("error") or {}
            if _busy_with_input(error):
                now = _clock()
                if give_up_at is None:
                    give_up_at = now + INPUT_WAIT_S
                if now < give_up_at:
                    _sleep(INPUT_PAUSE_S)
                    continue
            raise CommandFailedError(_explain(command, error), error.get("code"))

    def run_tapir(self, command: str, parameters: dict[str, Any] | None = None) -> Any:
        """Run one of Tapir's commands, as built into the Loriini add-on.

        Checks both error levels. The inner one is the dangerous one: the
        official call reports success while the add-on response carries a
        failure, so a client that only looks at ``succeeded`` reads an error
        object as though it were data.

        Until one namespace has answered, a "not registered" from Loriini's is
        retried once under a standalone Tapir's, and whichever answers is kept
        for the rest of the connection. That is what lets the Loriini add-on
        and a leftover Tapir be updated in either order. Once settled there is
        no retry, so a command that really is missing fails once, plainly.
        """
        missing = "Tapir's commands are not answering. " + INSTALL_LORIINI
        if self._tapir_namespace is not None:
            inner = self._run_addon(self._tapir_namespace, command, parameters, missing=missing)
        else:
            try:
                inner = self._run_addon(TAPIR_NAMESPACE, command, parameters, missing=missing)
                self._tapir_namespace = TAPIR_NAMESPACE
            except (TapirUnavailableError, CommandFailedError) as first:
                if not _not_registered(first):
                    raise
                try:
                    inner = self._run_addon(
                        STANDALONE_TAPIR_NAMESPACE, command, parameters, missing=missing
                    )
                except (TapirUnavailableError, CommandFailedError) as second:
                    if _not_registered(second):
                        raise first from None
                    raise
                self._tapir_namespace = STANDALONE_TAPIR_NAMESPACE
        if command == "ChangeWindow":
            self._note_change_window(parameters or {}, inner)
        return inner

    @property
    def tapir_namespace(self) -> str | None:
        """Which namespace Tapir's commands answered under, once one has."""
        return self._tapir_namespace

    def run_loriini(self, command: str, parameters: dict[str, Any] | None = None) -> Any:
        """Run one of this project's own add-on commands.

        A second namespace rather than a fork of Tapir. Three things Archicad
        can do and its JSON API cannot ask for -- reading the 3D projection,
        aiming it, and creating a 3D Document -- live in ``archicad-addon/``
        and answer here. Everything else stays on Tapir, which is why this is
        the same transport with one word changed.

        The two add-ons are installed separately, so a project can have one
        and not the other. That is why the "no add-on response" message names
        this one specifically: told only that an add-on is missing, the
        obvious thing to go and check is the Tapir install that is already
        working fine.
        """
        return self._run_addon(
            LORIINI_NAMESPACE,
            command,
            parameters,
            missing=(
                "The Loriini add-on is not installed. It is built by the "
                f"'Archicad add-on' workflow; copy the {ADDON_FILE} for your "
                "Archicad version into an add-on folder and add that folder in "
                "Options > Add-On Manager."
            ),
        )

    def _run_addon(
        self,
        namespace: str,
        command: str,
        parameters: dict[str, Any] | None,
        *,
        missing: str,
    ) -> Any:
        """One add-on command, with both error levels checked.

        Shared by both namespaces because the mechanism is Archicad's, not
        Tapir's: ``API.ExecuteAddOnCommand`` is the official envelope any
        add-on's commands arrive in, and the trap it carries -- an outer
        success wrapped around an inner error -- is the same either way.
        """
        result = self.run_official(
            "API.ExecuteAddOnCommand",
            {
                "addOnCommandId": {
                    "commandNamespace": namespace,
                    "commandName": command,
                },
                "addOnCommandParameters": parameters or {},
            },
        )

        if not isinstance(result, dict) or "addOnCommandResponse" not in result:
            raise TapirUnavailableError(
                f"Archicad ran API.ExecuteAddOnCommand for {command!r} but returned no "
                f"add-on response. {missing}"
            )

        inner = result["addOnCommandResponse"]
        if isinstance(inner, dict) and "error" in inner:
            error = inner["error"] or {}
            raise CommandFailedError(
                f"{namespace} command {command} failed: "
                f"{error.get('message', 'no message')} "
                f"(code {error.get('code', 'none')})",
                error.get("code"),
            )
        return inner

    # -- where the tool is -----------------------------------------------
    def _note_change_window(self, parameters: dict[str, Any], answer: Any) -> None:
        """Remember what ``ChangeWindow`` just made current.

        Here rather than at the call sites because there are four of them and
        a fifth would forget. Every database move in this package goes through
        ``run_tapir``, so this is the one place that cannot be bypassed.

        A refused move leaves the database where it was, so the note is only
        taken when the command actually reports success.
        """
        if isinstance(answer, dict) and answer.get("success") is False:
            return
        guid = (parameters.get("databaseId") or {}).get("guid")
        window = parameters.get("windowType")
        if guid and window:
            self._database = Database(guid=str(guid), window_type=str(window))

    @property
    def database(self) -> Database | None:
        """What this tool last made current, or ``None`` if it has not."""
        return self._database

    def note_model_database(self, guid: str = "") -> None:
        """Record that a floor plan is current without having moved anything.

        For the caller that has *proved* it -- ``ensure_model_database`` reads
        the walls, and a database with walls in it is a floor plan. Without
        this the common path, where nothing needed moving, would leave the
        connection saying it does not know where it is.
        """
        self._database = Database(guid=guid, window_type="FloorPlan")

    # -- handshake -------------------------------------------------------
    @property
    def tapir_version(self) -> str:
        if self._tapir_version is None:
            response = self.run_tapir("GetAddOnVersion")
            self._tapir_version = str(response.get("version", ""))
        return self._tapir_version

    def require_tapir(self) -> str:
        """Confirm Tapir is present and new enough, or say exactly what is wrong.

        Called before anything else so a version problem surfaces as a version
        problem, rather than as an unexplained failure on whichever command
        happens to be the first one that needs a newer add-on.
        """
        return self.require_tapir_at_least(
            MINIMUM_TAPIR_VERSION,
            "GetElementsByIFCIds, which maps IFC GlobalIds onto Archicad elements,",
        )

    def require_tapir_at_least(self, minimum: tuple[int, ...], because: str) -> str:
        """Confirm the add-on is new enough for one particular feature.

        Separate from ``require_tapir`` so an optional capability can need a
        newer build without locking everyone else out. Drawing needs 1.5.7 for
        ``CreateHatches``; reading and writing numbers need only 1.5.1, and
        someone who wants the numbers should not be blocked by a picture they
        did not ask for.

        ``because`` names the command that sets the floor, so the message says
        what the update actually buys.
        """
        version = self.tapir_version
        parts = self._version_parts(version)

        if parts < minimum:
            needed = ".".join(str(p) for p in minimum)
            raise TapirUnavailableError(
                f"Tapir {version} is installed but this needs at least {needed}. "
                f"{because} arrived in {needed}. {INSTALL_LORIINI}"
            )
        return version

    def has_tapir_at_least(self, minimum: tuple[int, ...]) -> bool:
        """Whether the add-on is new enough, without refusing to go on.

        The counterpart to ``require_tapir_at_least``, for a capability that
        has a working fallback rather than a floor: 1.5.8 lets ``CreateWalls``
        take a ``favoriteName`` per element, and an older build still gets the
        skin built, just by way of the shared tool defaults. Asking with a
        raise would turn an improvement into a version requirement.
        """
        return self._version_parts(self.tapir_version) >= minimum

    @staticmethod
    def _version_parts(version: str) -> tuple[int, ...]:
        try:
            return tuple(int(p) for p in version.split(".")[:3])
        except ValueError as exc:
            raise TapirUnavailableError(
                f"Could not read the Tapir add-on version from {version!r}."
            ) from exc

    def describe(self) -> str:
        """One line for the console banner, so the human can see what it found."""
        version = self.require_tapir()
        note = (
            ""
            if version == VERIFIED_AGAINST_TAPIR_VERSION
            else f" (this tool was written against {VERIFIED_AGAINST_TAPIR_VERSION})"
        )
        if self._tapir_namespace == STANDALONE_TAPIR_NAMESPACE:
            return (
                f"Archicad JSON API reachable, standalone Tapir add-on {version}{note}. "
                f"The installed Loriini add-on predates the built-in Tapir commands; "
                f"update it and Tapir can be removed"
            )
        return f"Archicad JSON API reachable, Loriini add-on with Tapir {version} built in{note}"
