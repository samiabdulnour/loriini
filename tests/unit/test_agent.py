"""The agent's server, spoken to the way a client speaks to it.

A client here is a pair of pipes and a thread: it writes JSON-RPC lines to
the server's stdin and reads them off its stdout, as Claude Desktop does.
The studies are a fake command line, so a "run" is a script that prints,
waits, and stops when the stop file appears -- the same file the window's
Stop button writes -- and what is tested is the protocol around it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from sun_study.agent import protocol, tools
from sun_study.app import probe, runner
from sun_study.app.probe import ProjectOptions, ZoneKind
from sun_study.archicad.connection import Instance

#: A command line that behaves: it says its arguments, and in ``slow`` mode
#: prints two lines a second apart, and in ``wait`` mode waits for the stop
#: file and says where it noticed it.
FAKE = """
import os, sys, time
mode = sys.argv[1] if len(sys.argv) > 1 else ""
print("args: " + " ".join(sys.argv[1:]), flush=True)
if mode == "slow":
    print("one", flush=True)
    time.sleep(1.0)
    print("two", flush=True)
elif mode == "wait":
    stop = os.environ.get("SUN_STUDY_STOP_FILE", "")
    for _ in range(600):
        if stop and os.path.exists(stop):
            Path = __import__("pathlib").Path
            Path(os.environ["FAKE_MARKER"]).write_text("stopped", encoding="utf-8")
            sys.exit(130)
        time.sleep(0.05)
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


@pytest.fixture
def fake_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The runner's command line is the fake, and the marker it writes is here."""
    monkeypatch.setattr(runner, "command_prefix", lambda: [sys.executable, "-c", FAKE])
    marker = tmp_path / "marker"
    monkeypatch.setenv("FAKE_MARKER", str(marker))
    monkeypatch.delenv("FAKE_EXIT", raising=False)
    return marker


class Client:
    """An MCP client's end of the pipes, with the server on a thread."""

    def __init__(self, server: protocol.Server) -> None:
        to_server, from_client = os.pipe()
        to_client, from_server = os.pipe()
        self._write = os.fdopen(from_client, "wb", buffering=0)
        self._read = os.fdopen(to_client, "rb")
        self._thread = threading.Thread(
            target=server.serve,
            args=(os.fdopen(to_server, "rb"), os.fdopen(from_server, "wb", buffering=0)),
            daemon=True,
        )
        self._thread.start()
        self._ids = 0

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method: str, params: dict[str, Any] | None = None) -> int:
        self._ids += 1
        self._send({"jsonrpc": "2.0", "id": self._ids, "method": method, "params": params or {}})
        return self._ids

    def raw(self, text: str) -> None:
        self._write.write(text.encode("utf-8") + b"\n")

    def _send(self, message: dict[str, Any]) -> None:
        self.raw(json.dumps(message))

    def read(self) -> dict[str, Any]:
        line = self._read.readline()
        assert line, "the server closed its stream"
        loaded: dict[str, Any] = json.loads(line)
        return loaded

    def answer(self, request_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """The response to one request, and every notification before it."""
        seen: list[dict[str, Any]] = []
        while True:
            message = self.read()
            if message.get("id") == request_id:
                return message, seen
            seen.append(message)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """A tool call, initialised first, answered and unpacked."""
        response, _ = self.answer(
            self.request("tools/call", {"name": name, "arguments": arguments or {}})
        )
        return response

    def leave(self) -> None:
        self._write.close()
        self._thread.join(timeout=10)
        assert not self._thread.is_alive(), "the server did not stop when the client left"


@pytest.fixture
def client() -> Any:
    made = Client(tools.build())
    yield made
    made.leave()


# -- the protocol ---------------------------------------------------------------------


def test_the_handshake_names_the_server_and_speaks_the_clients_version(client: Client) -> None:
    response, _ = client.answer(
        client.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    )
    result = response["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "Loriini"
    assert "tools" in result["capabilities"] and "logging" in result["capabilities"]
    assert "archicad_instances" in result["instructions"]
    client.notify("notifications/initialized")

    # A version this server has never heard of gets the newest it knows.
    response, _ = client.answer(client.request("initialize", {"protocolVersion": "1999-01-01"}))
    assert response["result"]["protocolVersion"] == protocol.PROTOCOL_VERSIONS[0]

    response, _ = client.answer(client.request("ping"))
    assert response["result"] == {}


def test_the_tools_are_listed_with_what_they_take(client: Client) -> None:
    response, _ = client.answer(client.request("tools/list"))
    listed = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert set(listed) == {
        "archicad_instances",
        "project_options",
        "loriini_help",
        "run_loriini",
        "site_analysis",
        "shadow_diagrams",
        "sun_views",
    }
    site = listed["site_analysis"]["inputSchema"]
    assert site["required"] == ["address"]
    assert site["additionalProperties"] is False, "a misspelled option is refused, not ignored"
    assert "port" in site["properties"] and "model_radius_m" in site["properties"]
    assert listed["project_options"]["annotations"]["readOnlyHint"] is True
    assert listed["shadow_diagrams"]["annotations"]["readOnlyHint"] is False


def test_what_is_not_a_request_is_answered_as_such(client: Client) -> None:
    client.raw("this is not json")
    assert client.read()["error"]["code"] == protocol.PARSE_ERROR
    response, _ = client.answer(client.request("resources/list"))
    assert response["error"]["code"] == protocol.METHOD_NOT_FOUND
    response = client.call("no_such_tool")
    assert response["error"]["code"] == protocol.INVALID_PARAMS
    assert "no_such_tool" in response["error"]["message"]


def test_bad_arguments_are_a_protocol_error_that_names_the_field(client: Client) -> None:
    response = client.call("site_analysis", {"port": 19723})
    assert response["error"]["code"] == protocol.INVALID_PARAMS
    assert "address" in response["error"]["message"]

    response = client.call("site_analysis", {"address": "1 Test St", "colour": "red"})
    assert response["error"]["code"] == protocol.INVALID_PARAMS
    assert "colour" in response["error"]["message"]

    response = client.call("run_loriini", {"args": ["mcp"]})
    assert response["error"]["code"] == protocol.INVALID_PARAMS


def test_a_run_is_streamed_while_a_ping_is_still_answered(client: Client, fake_cli: Path) -> None:
    """The study runs on its own thread: a ping sent after the call is
    answered before the call is, and every line the run prints reaches the
    client as it is printed, as a log message and as progress."""
    call_id = client.request(
        "tools/call",
        {"name": "run_loriini", "arguments": {"args": ["slow"]}, "_meta": {"progressToken": "p1"}},
    )
    ping_id = client.request("ping")
    response, before = client.answer(ping_id)
    assert response["result"] == {}
    response, streamed = client.answer(call_id)
    notes = before + streamed
    progress = [n["params"] for n in notes if n["method"] == "notifications/progress"]
    assert [p["message"] for p in progress] == ["args: slow", "one", "two"]
    assert [p["progress"] for p in progress] == [1, 2, 3] and all(
        p["progressToken"] == "p1" for p in progress
    )
    logged = [n["params"]["data"] for n in notes if n["method"] == "notifications/message"]
    assert logged == ["args: slow", "one", "two"]

    result = response["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == {"exit_code": 0, "lines": 3, "stopped": False}
    text = result["content"][0]["text"]
    assert text.startswith("sun-study slow\nexit code 0, 3 lines")
    assert text.endswith("args: slow\none\ntwo")


def test_a_failed_run_is_an_error_result_with_its_lines(
    client: Client, fake_cli: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_EXIT", "2")
    result = client.call("loriini_help", {"command": "site"})["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["exit_code"] == 2
    assert "args: site --help" in result["content"][0]["text"]


def test_a_cancelled_run_is_stopped_the_way_the_window_stops_one(
    client: Client, fake_cli: Path
) -> None:
    """The client cancels; the run is asked to stop through its stop file --
    not killed -- and the call gets no answer, while the server stays."""
    call_id = client.request("tools/call", {"name": "run_loriini", "arguments": {"args": ["wait"]}})
    first = client.read()
    assert first["method"] == "notifications/message" and first["params"]["data"] == "args: wait"
    client.notify("notifications/cancelled", {"requestId": call_id, "reason": "changed my mind"})
    for _ in range(100):
        if fake_cli.exists():
            break
        time.sleep(0.05)
    assert fake_cli.read_text(encoding="utf-8") == "stopped"

    response, seen = client.answer(client.request("ping"))
    assert response["result"] == {}
    assert not any(message.get("id") == call_id for message in seen), (
        "a cancelled call is not answered"
    )


def test_the_client_leaving_stops_a_running_study(fake_cli: Path) -> None:
    client = Client(tools.build())
    client.request("tools/call", {"name": "run_loriini", "arguments": {"args": ["wait"]}})
    assert client.read()["params"]["data"] == "args: wait"
    client.leave()
    assert fake_cli.read_text(encoding="utf-8") == "stopped"


def test_a_tools_own_failure_is_its_result_and_the_server_lives_on(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> list[Instance]:
        raise RuntimeError("the network cable")

    monkeypatch.setattr(probe, "running", broken)
    result = client.call("archicad_instances")["result"]
    assert result["isError"] is True and "the network cable" in result["content"][0]["text"]
    response, _ = client.answer(client.request("ping"))
    assert response["result"] == {}


# -- the listings ---------------------------------------------------------------------


def test_the_listings_read_the_project_as_the_window_does(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        probe, "running", lambda: [Instance(19723, "Tower.pln"), Instance(19724, "")]
    )
    result = client.call("archicad_instances")["result"]
    assert result["structuredContent"]["instances"] == [
        {"port": 19723, "project": "Tower.pln"},
        {"port": 19724, "project": ""},
    ]
    assert "port 19724: (no project open)" in result["content"][0]["text"]

    asked: list[int] = []

    def options(port: int) -> ProjectOptions:
        asked.append(port)
        return ProjectOptions(
            project="Tower.pln",
            layers=("06 | Zone.Units", "20 | Massing"),
            zone_layers=("06 | Zone.Units",),
            zone_kinds=(ZoneKind("06 | Zone.Units", "G08", 15, 74.0, "Apartment"),),
            combinations=("04 | Shadow Diagrams",),
            masters=("A1 Landscape",),
            pen_sets=("00 FA Pens",),
            storey_names=("Ground", "Level 1"),
            latitude=-33.9,
            longitude=151.2,
            tapir="1.5.8",
            problems=("layout subsets: the add-on is older than the command",),
        )

    monkeypatch.setattr(probe, "options", options)
    result = client.call("project_options", {"port": 19724})["result"]
    assert asked == [19724]
    text = result["content"][0]["text"]
    assert (
        "project: Tower.pln" in text and "G08 — Apartment (15 x 74 m2) on 06 | Zone.Units" in text
    )
    assert "could not read: layout subsets" in text
    assert result["structuredContent"]["masters"] == ["A1 Landscape"]
    assert result["structuredContent"]["zone_kinds"][0]["label"] == "G08"

    monkeypatch.setattr(
        probe, "options", lambda port: ProjectOptions(problems=("nothing on 19730",))
    )
    result = client.call("project_options", {"port": 19730})["result"]
    assert result["isError"] is True and "nothing on 19730" in result["content"][0]["text"]


# -- the studies' command lines ---------------------------------------------------------


def test_the_site_analysis_is_spelled_as_the_window_spells_it() -> None:
    plain = tools.site_argv(tools.SiteArguments(address="1 Test St, Newtown NSW 2042"))
    assert plain == [
        "site",
        "1 Test St, Newtown NSW 2042",
        "--port",
        "19723",
        "--timeout",
        "1800",
        "--context",
        "--site",
        "--summary",
    ]
    full = tools.site_argv(
        tools.SiteArguments(
            address="1 Test St",
            port=19724,
            timeout_seconds=600,
            layer_prefix="30",
            summary=False,
            model=True,
            model_radius_m=300,
            future=True,
            future_reach_m=100,
            set_location=False,
            scale=3000,
            anchor="site",
            out="C:/runs/test",
            master_layout="A1 Landscape",
        )
    )
    assert full == [
        "site",
        "1 Test St",
        "--port",
        "19724",
        "--timeout",
        "600",
        "--layer-prefix",
        "30",
        "--context",
        "--site",
        "--no-summary",
        "--model",
        "--model-radius",
        "300",
        "--future",
        "--future-reach",
        "100",
        "--keep-location",
        "--scale",
        "3000",
        "--anchor",
        "site",
        "--out",
        "C:/runs/test",
        "--master-layout",
        "A1 Landscape",
    ]


def test_the_shadow_diagrams_take_their_rows_days_and_hours() -> None:
    argv = tools.shadow_argv(
        tools.ShadowArguments(
            dates=["winter", "equinox", "03-21"],
            hours=[9, 12, 15],
            sources={"EXISTING": ["03 | Site Context.Buildings"]},
            scenarios={"PROPOSED": ["20 | Massing", "21 | Massing.Roof"]},
            terrain_layers=["03 | Site Context.Terrain"],
            storey=0,
            all_hours=True,
            sheets="two",
            year=2025,
        )
    )
    assert argv[:7] == [
        "shadows",
        "--timezone",
        "Australia/Sydney",
        "--port",
        "19723",
        "--timeout",
        "1800",
    ]
    assert argv[7:] == [
        "--shadow-source",
        "EXISTING=03 | Site Context.Buildings",
        "--shadow-scenario",
        "PROPOSED=20 | Massing,21 | Massing.Roof",
        "--shadow-terrain",
        "03 | Site Context.Terrain",
        "--export",
        "native",
        "--shadow-all-hours",
        "--shadow-date",
        "06-21,09-21,03-21",
        "--shadow-hour",
        "9,12,15",
        "--shadow-storey",
        "0",
        "--year",
        "2025",
        "--sheets",
        "two",
    ]
    with pytest.raises(protocol.InvalidArgumentsError, match="not a day"):
        tools.shadow_argv(tools.ShadowArguments(dates=["someday"]))
    with pytest.raises(protocol.InvalidArgumentsError, match="legend row"):
        tools.shadow_argv(tools.ShadowArguments(sources={"A=B": ["x"]}))
    with pytest.raises(protocol.InvalidArgumentsError, match="names no layers"):
        tools.shadow_argv(tools.ShadowArguments(scenarios={"PROPOSED": []}))


def test_the_sun_views_name_a_day_only_when_it_is_not_the_rulesets_own() -> None:
    winter = tools.sun_views_argv(tools.SunViewArguments(day="winter", hours=[9, 12]))
    assert winter == [
        "sun-views",
        "--timezone",
        "Australia/Sydney",
        "--port",
        "19723",
        "--timeout",
        "1800",
        "--hour",
        "9,12",
    ]
    equinox = tools.sun_views_argv(
        tools.SunViewArguments(day="equinox", pen_set="00 FA Pens", scale=500, title_block_mm=40)
    )
    assert equinox[7:] == [
        "--pen-set",
        "00 FA Pens",
        "--scale",
        "500",
        "--title-block-mm",
        "40",
        "--date",
        "equinox",
    ]
