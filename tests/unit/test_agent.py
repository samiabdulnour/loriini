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
    assert result["serverInfo"]["title"] == "Loriini"
    # The bird, for the client to show beside the name: the 256-pixel PNG
    # from the checkout's assets, as a data URI.
    (shown,) = result["serverInfo"]["icons"]
    assert shown["mimeType"] == "image/png"
    assert shown["src"].startswith("data:image/png;base64,iVBORw0KGgo")
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
        "shadow_diagram",
        "shadow_every_hour",
        "sun_views",
        "cos_solar",
    }
    cos = listed["cos_solar"]["inputSchema"]
    assert set(cos["required"]) == {
        "layer_combination",
        "view_combination",
        "master_layout",
        "zone_layer",
    }, "both combinations and the master are asked for, not defaulted"
    assert "Ask the person" in cos["properties"]["layer_combination"]["description"]
    assert "Ask the person" in cos["properties"]["view_combination"]["description"]
    assert "Ask the person" in cos["properties"]["master_layout"]["description"]
    site = listed["site_analysis"]["inputSchema"]
    assert site["required"] == ["address"]
    assert site["additionalProperties"] is False, "a misspelled option is refused, not ignored"
    assert "port" in site["properties"] and "model_radius_m" in site["properties"]
    assert listed["project_options"]["annotations"]["readOnlyHint"] is True
    assert listed["shadow_every_hour"]["annotations"]["readOnlyHint"] is False
    # The documents are the shadow diagram (D144, D160), and the combination
    # they show is the person's answer, as cos_solar's is.
    diagram = listed["shadow_diagram"]
    assert diagram["title"] == "Shadow diagram"
    assert diagram["inputSchema"]["required"] == ["layer_combination"]
    assert (
        "Ask the person" in diagram["inputSchema"]["properties"]["layer_combination"]["description"]
    )
    assert "only for that drawing" in listed["shadow_every_hour"]["description"].casefold()


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


def test_the_site_tool_can_set_the_origin_on_a_corner_and_square_the_site() -> None:
    argv = tools.site_argv(
        tools.SiteArguments(
            address="1 Test St", anchor="site", origin_at="bottom-left", square_to_site=True
        )
    )
    assert argv[argv.index("--origin-at") + 1] == "bottom-left"
    assert "--square-to-site" in argv
    assert "--square-to-site" not in tools.site_argv(tools.SiteArguments(address="1 Test St"))


def test_the_every_hour_drawing_takes_its_rows_days_and_hours() -> None:
    """The fills, for the design's every hour on one drawing and nothing
    else (D160): never a fill per hour, which the documents draw."""
    argv = tools.shadow_argv(
        tools.ShadowArguments(
            dates=["winter", "equinox", "03-21"],
            hours=[9, 12, 15],
            sources={"EXISTING": ["03 | Site Context.Buildings"]},
            scenarios={"PROPOSED": ["20 | Massing", "21 | Massing.Roof"]},
            terrain_layers=["03 | Site Context.Terrain"],
            storey=0,
            colour="blue",
            grid_m="0.25",
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
        "--shadow-all-hours-only",
        "--draw",
        "--sheet",
        "--shadow-grid",
        "0.25",
        "--shadow-all-hours-colour",
        "blue",
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
    design = {"PROPOSED": ["20 | Massing"]}
    with pytest.raises(protocol.InvalidArgumentsError, match="not a day"):
        tools.shadow_argv(tools.ShadowArguments(dates=["someday"], scenarios=design))
    with pytest.raises(protocol.InvalidArgumentsError, match="legend row"):
        tools.shadow_argv(tools.ShadowArguments(sources={"A=B": ["x"]}))
    with pytest.raises(protocol.InvalidArgumentsError, match="names no layers"):
        tools.shadow_argv(tools.ShadowArguments(scenarios={"PROPOSED": []}))


def test_the_every_hour_drawing_is_refused_without_a_design() -> None:
    """With nothing to outline the command would draw a fill per hour -- the
    diagram the documents draw -- so the tool refuses before anything runs.
    A source named PROPOSED is the design as well, as the command reads it."""
    stands = {"EXISTING": ["03 | Site Context.Buildings"]}
    with pytest.raises(protocol.InvalidArgumentsError, match="needs the design"):
        tools.shadow_argv(tools.ShadowArguments(sources=stands))
    argv = tools.shadow_argv(
        tools.ShadowArguments(sources={**stands, "PROPOSED": ["20 | Massing"]})
    )
    assert "--shadow-all-hours-only" in argv
    assert "--shadow-all-hours-colour" not in argv, "the command's red unless asked"


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


def test_the_shadow_diagram_takes_its_days_and_hours() -> None:
    """Roadmap R1: the instants as documents, with the set named."""
    argv = tools.shadow_plans_argv(
        tools.ShadowPlanArguments(
            dates=["winter", "12-21"],
            hours=[9, 12, 15],
            layer_combination="04 | Shadow Diagrams",
            label="Proposed",
            shadow_pen=3,
        )
    )
    assert argv[:3] == ["shadow-plans", "--timezone", "Australia/Sydney"]
    assert argv[argv.index("--shadow-date") + 1] == "06-21,12-21"
    assert argv[argv.index("--shadow-hour") + 1] == "9,12,15"
    assert argv[argv.index("--layer-combination") + 1] == "04 | Shadow Diagrams"
    assert argv[argv.index("--label") + 1] == "Proposed"
    assert argv[argv.index("--shadow-pen") + 1] == "3"
    assert "--pen-set" not in argv, "left to the command when not given"


def test_the_stacked_shadow_diagram_names_the_layers_of_what_stands_and_each_proposal() -> None:
    """One --existing per layer, one --proposed per proposal with its layers
    comma separated, and the pens in order; nothing of it without proposals."""
    argv = tools.shadow_plans_argv(
        tools.ShadowPlanArguments(
            layer_combination="04 | Shadow Diagrams",
            existing=["03 | Site Context.Buildings"],
            proposals=[["20 | Massing.SEARs"], ["20 | Massing.Envelope", "20 | Massing.Podium"]],
            existing_pen=93,
            proposed_pens=[94, 95],
        )
    )
    assert argv[argv.index("--existing") + 1] == "03 | Site Context.Buildings"
    proposed = [argv[i + 1] for i, word in enumerate(argv) if word == "--proposed"]
    assert proposed == ["20 | Massing.SEARs", "20 | Massing.Envelope,20 | Massing.Podium"]
    assert argv[argv.index("--existing-pen") + 1] == "93"
    assert [argv[i + 1] for i, word in enumerate(argv) if word == "--proposed-pen"] == ["94", "95"]
    plain = tools.shadow_plans_argv(
        tools.ShadowPlanArguments(layer_combination="04 | Shadow Diagrams")
    )
    assert not {"--existing", "--proposed", "--existing-pen", "--proposed-pen"} & set(plain)


def test_cos_solar_is_the_windows_communal_job_under_the_combination_asked_for() -> None:
    """The layer combination is the person's answer, and the export is native."""
    argv = tools.cos_argv(
        tools.CosArguments(
            layer_combination="IFC Export",
            view_combination="01 | Plans - DA",
            master_layout="DA B1 - VERTICAL - 1:250",
            zone_layer="06 | Zone.SEPP 65",
            zone_names=["COS"],
            storeys=["LEVEL 01 (2)", "LEVEL 08 (9)"],
            storey_to="LIFT OVERRUN",
            hours=2,
        ),
        zone_layers=["06 | Zone.SEPP 65", "06 | Zone.Units", "10 | Calc.GFA"],
    )
    assert argv[:3] == ["massing", "--timezone", "Australia/Sydney"]
    assert argv[argv.index("--export") + 1] == "native"
    assert argv[argv.index("--layer-combination") + 1] == "IFC Export"
    assert argv[argv.index("--zone-view-combination") + 1] == "01 | Plans - DA", (
        "the diagrams are drawn over the plans asked for, not the export combination"
    )
    assert argv[argv.index("--master-layout") + 1] == "DA B1 - VERTICAL - 1:250"
    assert argv[argv.index("--zone-layer") + 1] == "06 | Zone.SEPP 65"
    assert [argv[i + 1] for i, v in enumerate(argv) if v == "--zone-storey"] == [
        "LEVEL 01 (2)",
        "LEVEL 08 (9)",
    ]
    assert [argv[i + 1] for i, v in enumerate(argv) if v == "--require-layer"] == [
        "06 | Zone.SEPP 65",
        "06 | Zone.Units",
    ], "the zone layers, not somebody's area schedule"
    assert argv[argv.index("--exclude-above-storey") + 1] == "LIFT OVERRUN"
    assert argv[argv.index("--zone-hours") + 1] == "2"
    assert {"--zone-sheet", "--zone-stats", "--zone-hourly"} <= set(argv)
    assert "--date" not in argv, "midwinter keeps the command's own names"


def test_cos_solar_without_a_layer_combination_is_refused() -> None:
    with pytest.raises(protocol.InvalidArgumentsError, match="layer_combination"):
        tools._validated(
            tools.CosArguments,
            {
                "zone_layer": "06 | Zone.SEPP 65",
                "view_combination": "01 | Plans - DA",
                "master_layout": "DA B1 - VERTICAL - 1:250",
            },
        )


def test_cos_solar_without_a_view_combination_is_refused() -> None:
    """Left out, the diagrams are drawn over the export combination: on Kogarah
    that put the colours over IFC export geometry instead of the DA plans."""
    with pytest.raises(protocol.InvalidArgumentsError, match="view_combination"):
        tools._validated(
            tools.CosArguments,
            {
                "zone_layer": "06 | Zone.SEPP 65",
                "layer_combination": "12 | IFC ARCH. EXPORT",
                "master_layout": "DA B1 - VERTICAL - 1:250",
            },
        )


def test_cos_solar_without_a_master_layout_is_refused() -> None:
    """Left out, the sheets are made from the project's default master: on
    Kogarah that placed them wrong, and they were deleted by hand."""
    with pytest.raises(protocol.InvalidArgumentsError, match="master_layout"):
        tools._validated(
            tools.CosArguments,
            {
                "zone_layer": "06 | Zone.SEPP 65",
                "layer_combination": "12 | IFC ARCH. EXPORT",
                "view_combination": "01 | Plans - DA",
            },
        )


def test_cos_solar_names_the_schedule_with_the_hourly_plans_only() -> None:
    def argv(**more: Any) -> list[str]:
        return tools.cos_argv(
            tools.CosArguments(
                layer_combination="IFC Export",
                view_combination="01 | Plans - DA",
                master_layout="DA B1 - VERTICAL - 1:250",
                zone_layer="06 | Zone.SEPP 65",
                schedule="Areas COS solar",
                **more,
            ),
            zone_layers=["06 | Zone.SEPP 65"],
        )

    hourly = argv()
    assert hourly[hourly.index("--zone-schedule") + 1] == "Areas COS solar"
    assert "--zone-schedule" not in argv(hourly=False)
