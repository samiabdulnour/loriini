"""Shadow plans as 3D Documents: the hours, the documents, the rerun, the sheets.

Roadmap R1. What is worth proving without a live Archicad is everything
Loriini decides: which hours are drawn and what each is called, that every
document is made looking straight down with its own sun and with the shadows
switched on, that a rerun re-sets the documents it finds instead of piling up
copies, that an older add-on is said plainly, and how the plans are dealt
onto sheets. What Archicad then draws is for the workstation (see
``docs/shadow-plans.md``).
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.read import GeoLocation
from sun_study.archicad.shadow_plans import (
    OVERHEAD_DEG,
    STACK_SURFACES,
    LegendRow,
    MadePlan,
    PlanSet,
    ShadowPlan,
    ShadowPlanSettings,
    Stack,
    hidden_among,
    legend_combinations,
    legend_from_existing_and_proposed,
    make_shadow_plan_stack,
    make_shadow_plans,
    make_stack_sheets,
    plan_sheet_groups,
    shadow_plans,
    site_context_layers,
    stack_labels,
    stack_order,
    stack_sheet_groups,
)
from sun_study.archicad.views import StoreyView
from sun_study.core.shadow import BASELINE, SCENARIO

SYDNEY = GeoLocation(
    latitude_deg=-33.866667,
    longitude_deg=151.216667,
    altitude_m=0.0,
    north_radians=math.radians(49.052),
)
ZONE = ZoneInfo("Australia/Sydney")


def moments(day: dt.date, hours: list[int]) -> tuple[list[dt.datetime], list[str]]:
    times = [dt.datetime.combine(day, dt.time(hour), tzinfo=ZONE) for hour in hours]
    labels = [f"{h if h <= 12 else h - 12}{'AM' if h < 12 else 'PM'}" for h in hours]
    return times, labels


class PlanTransport:
    """A project whose Project Map grows as documents are made.

    Answers by what is asked rather than by command name alone, because the
    one tree command serves the Project Map and the View Map, and the Project
    Map has to hold a document once -- and only once -- it has been made.
    """

    def __init__(self, existing: tuple[str, ...] = (), *, has_set_command: bool = True) -> None:
        #: Document name -> navigator id, in the Project Map.
        self.documents: dict[str, str] = {name: f"NAV-{name}" for name in existing}
        self.has_set_command = has_set_command
        self.refuse_create = False
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["command"] != "API.ExecuteAddOnCommand":
            return {"succeeded": True, "result": {}}
        name = payload["parameters"]["addOnCommandId"]["commandName"]
        given = payload["parameters"].get("addOnCommandParameters") or {}
        self.sent.append((name, given))
        return {"succeeded": True, "result": {"addOnCommandResponse": self._answer(name, given)}}

    def _answer(self, command: str, given: dict[str, Any]) -> dict[str, Any]:
        if command == "GetCurrentWindowType":
            return {"currentWindowType": "FloorPlan"}
        if command == "GetAttributesByType":
            # A project with no fill called "50 %": the shadows keep the pen
            # asked for and nothing else.
            return {"attributes": []}
        if command == "GetNavigatorItemTree":
            children: list[dict[str, Any]] = []
            if given.get("navigatorMapId") == "ProjectMap":
                children = [
                    {
                        "navigatorItem": {
                            "name": name,
                            "type": "DocumentFrom3DItem",
                            "navigatorItemId": {"guid": guid},
                        }
                    }
                    for name, guid in self.documents.items()
                ]
            return {"navigatorItemTree": {"rootItem": {"name": "root", "children": children}}}
        if command == "CreateDocumentFrom3D":
            if self.refuse_create:
                return {"error": {"code": 4002, "message": "unexpected property 'sunShadows'"}}
            self.documents[given["name"]] = f"NAV-{given['name']}"
            return {
                "success": True,
                "databaseId": {"guid": f"DB-{given['name']}"},
                "effects3D": 7,
                "shadowFill": {"fillIndex": 65, "fillPen": 3, "backgroundPen": 0, "contourPen": 3},
            }
        if command == "SetDocumentFrom3D":
            if not self.has_set_command:
                return {
                    "error": {
                        "code": 4010,
                        "message": "does not have the registered Add-On command",
                    }
                }
            return {"success": True, "effects3D": given.get("effects3D", 3)}
        if command == "GetDatabaseIdFromNavigatorItemId":
            navigator = given["navigatorItemIds"][0]["navigatorItemId"]["guid"]
            return {"databases": [{"databaseId": {"guid": f"DB-of-{navigator}"}}]}
        if command == "CreateViewMapFolder":
            return {"navigatorItemId": {"guid": "FOLDER"}}
        if command == "CreateViewsInViewMap":
            return {
                "navigatorItems": [
                    {"navigatorItemId": {"guid": f"VIEW-{view['name']}"}}
                    for view in given["viewsData"]
                ]
            }
        if command == "SetViewSettings":
            return {
                "executionResults": [
                    {"success": True} for _ in given["navigatorItemIdsWithViewSettings"]
                ]
            }
        if command == "GetPlace":
            # A Sydney project keeping AEST (D135): the hours go over unchanged.
            return {"success": True, "timeZoneInMinutes": 600, "summerTime": False}
        raise AssertionError(f"unscripted command {command!r}")

    def asked(self, command: str) -> list[dict[str, Any]]:
        return [given for name, given in self.sent if name == command]


SS = naming.prefix()


# -- the hours -----------------------------------------------------------------


def test_the_hours_are_the_shadow_diagrams_and_the_sun_down_is_left_out() -> None:
    times, labels = moments(dt.date(2024, 6, 21), [6, 9, 12, 15, 18])
    up, down = shadow_plans(SYDNEY, times, labels)

    assert [plan.label for plan in up] == ["9AM", "12PM", "3PM"]
    assert [plan.label for plan in down] == ["6AM", "6PM"]
    assert all(plan.altitude_deg > 0 for plan in up)
    # About 32.7 degrees at noon on the winter solstice in Sydney.
    assert up[1].altitude_deg == pytest.approx(32.7, abs=0.5)


def test_a_plan_is_named_captioned_and_referenced_for_its_hour() -> None:
    plan = ShadowPlan(when=dt.datetime(2024, 6, 21, 9, tzinfo=ZONE), label="9AM", altitude_deg=19.0)
    assert plan.caption == "JUNE 21 -9AM"  # the fills' sheets' own words
    assert plan.name() == f"{SS} Shadow Plan 21 Jun 09:00"
    assert plan.name("Existing") == f"{SS} Shadow Plan Existing 21 Jun 09:00"
    assert plan.reference == "SP0621-0900"
    assert plan.sun_for_archicad() == {
        "year": 2024,
        "month": 6,
        "day": 21,
        "hour": 9,
        "minute": 0,
        "second": 0,
        "summerTime": False,
    }


def test_a_plan_view_carries_no_3d_style() -> None:
    """Tapir refuses a 3D style on a view of a document, as the sun views
    found; a plan's drawing settings are the document's own."""
    settings = ShadowPlanSettings(
        layer_combination="04 | Shadow Diagrams",
        renovation_filter_guid="PLANNED",
        graphic_override="Shadow Plans",
        scale=1000,
    ).for_view()
    assert "d3styleName" not in settings
    assert settings["layerCombination"] == "04 | Shadow Diagrams"
    assert settings["drawingScale"] == 1000
    assert settings["renovationFilterGuid"] == {"guid": "PLANNED"}
    assert settings["graphicOverrideCombination"] == "Shadow Plans"


# -- the documents -------------------------------------------------------------------


def _plans(hours: list[int]) -> list[ShadowPlan]:
    times, labels = moments(dt.date(2024, 6, 21), hours)
    return shadow_plans(SYDNEY, times, labels)[0]


def test_every_document_looks_straight_down_with_its_own_sun_and_shadows_on() -> None:
    transport = PlanTransport()
    settings = ShadowPlanSettings(shadow_fill={"fillIndex": 65, "fillPen": 3})

    made, said = make_shadow_plans(
        ArchicadConnection(transport), _plans([9, 12, 15]), settings=settings
    )

    created = transport.asked("CreateDocumentFrom3D")
    assert [c["name"] for c in created] == [
        f"{SS} Shadow Plan 21 Jun 09:00",
        f"{SS} Shadow Plan 21 Jun 12:00",
        f"{SS} Shadow Plan 21 Jun 15:00",
    ]
    assert all(c["viewAltitude"] == OVERHEAD_DEG for c in created)
    assert all(c["sunShadows"] is True for c in created)
    assert all(c["shadowFill"] == {"fillIndex": 65, "fillPen": 3} for c in created)
    assert [c["sun"]["hour"] for c in created] == [9, 12, 15]
    assert [c["referenceId"] for c in created] == ["SP0621-0900", "SP0621-1200", "SP0621-1500"]
    assert not transport.asked("SetDocumentFrom3D"), "nothing to re-set on a first run"
    assert said == []

    assert [one.reused for one in made] == [False, False, False]
    assert [one.effects for one in made] == [7, 7, 7]
    # One view per document, in the set's own folder, pinned as asked.
    views = transport.asked("CreateViewsInViewMap")
    assert [v["name"] for call in views for v in call["viewsData"]] == [c["name"] for c in created]
    assert transport.asked("CreateViewMapFolder") == [{"folderName": f"{SS} Shadow Plans"}]
    pinned = transport.asked("SetViewSettings")[-1]["navigatorItemIdsWithViewSettings"]
    assert all(p["viewSettings"]["layerCombination"] == "04 | Shadow Diagrams" for p in pinned)


def test_a_rerun_re_sets_what_it_finds_and_copies_the_shadow_switch() -> None:
    """A 3D Document cannot be deleted through the API, so a rerun finds the
    last run's. It re-aims them and copies the shadow switch from one it made
    itself, rather than making a second document under the same name."""
    plans = _plans([9, 12])
    transport = PlanTransport(existing=(plans[0].name(),))

    made, said = make_shadow_plans(
        ArchicadConnection(transport), plans, settings=ShadowPlanSettings()
    )

    assert [c["name"] for c in transport.asked("CreateDocumentFrom3D")] == [plans[1].name()]
    (reset,) = transport.asked("SetDocumentFrom3D")
    assert reset["databaseId"] == {"guid": f"DB-of-NAV-{plans[0].name()}"}
    assert reset["viewAltitude"] == OVERHEAD_DEG
    assert reset["sun"]["hour"] == 9
    assert reset["effects3D"] == 7, "copied from the document this run made"
    assert [one.reused for one in made] == [True, False]
    assert said == []


def test_a_rerun_that_made_nothing_says_the_shadows_are_as_they_were() -> None:
    plans = _plans([9, 12])
    transport = PlanTransport(existing=tuple(plan.name() for plan in plans))

    made, said = make_shadow_plans(
        ArchicadConnection(transport), plans, settings=ShadowPlanSettings()
    )

    assert not transport.asked("CreateDocumentFrom3D")
    assert all("effects3D" not in reset for reset in transport.asked("SetDocumentFrom3D"))
    assert [one.reused for one in made] == [True, True]
    assert len(said) == 1 and "as the last run left them" in said[0]


def test_an_add_on_without_the_re_set_keeps_the_documents_and_says_so() -> None:
    plans = _plans([9])
    transport = PlanTransport(existing=(plans[0].name(),), has_set_command=False)

    made, said = make_shadow_plans(
        ArchicadConnection(transport), plans, settings=ShadowPlanSettings()
    )

    assert made[0].reused and made[0].effects is None
    assert len(said) == 1 and "no SetDocumentFrom3D" in said[0]


def test_an_add_on_that_cannot_turn_the_shadows_on_is_said_plainly() -> None:
    transport = PlanTransport()
    transport.refuse_create = True
    with pytest.raises(ArchicadError, match="install the current build"):
        make_shadow_plans(ArchicadConnection(transport), _plans([9]), settings=ShadowPlanSettings())


# -- the sheets ------------------------------------------------------------------------


def _made(day: dt.date, hours: list[int], set_label: str = "") -> list[MadePlan]:
    times, labels = moments(day, hours)
    plans = shadow_plans(SYDNEY, times, labels)[0]
    tag = f"{set_label}-" if set_label else ""
    return [
        MadePlan(
            plan=plan,
            view=StoreyView(0, plan.name(set_label), f"VIEW-{tag}{plan.stamp}"),
            reused=False,
        )
        for plan in plans
    ]


def test_a_sheet_is_a_day_dealt_as_the_fills_are() -> None:
    made = _made(dt.date(2024, 6, 21), list(range(9, 16))) + _made(dt.date(2024, 12, 21), [12])

    groups, cells = plan_sheet_groups(made, sheets="two")

    assert [name for name, _ in groups] == [
        f"{SS} Shadow Plans - JUNE 21 (1 of 2)",
        f"{SS} Shadow Plans - JUNE 21 (2 of 2)",
        f"{SS} Shadow Plans - DECEMBER 21",
    ]
    assert [caption for _, caption in groups[0][1]] == [
        "JUNE 21 -9AM",
        "JUNE 21 -10AM",
        "JUNE 21 -11AM",
        "JUNE 21 -12PM",
    ]
    assert cells == 4, "every sheet shares the fullest sheet's grid"


def test_a_labelled_set_has_sheets_of_its_own() -> None:
    groups, _ = plan_sheet_groups(
        _made(dt.date(2024, 6, 21), [9, 12]), sheets="each", set_label="Proposed"
    )
    assert [name for name, _ in groups] == [
        f"{SS} Shadow Plans Proposed - JUNE 21 9AM",
        f"{SS} Shadow Plans Proposed - JUNE 21 12PM",
    ]


# -- the command ---------------------------------------------------------------------


def test_the_command_draws_the_hours_the_sun_is_up_and_mends_what_it_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end over the scripted project: the hour before sunrise is said
    and skipped, the fill asked for reaches every document, the storey filter
    is taken off after the documents exist (D98), and the log says how long."""
    from typer.testing import CliRunner

    from sun_study import cli

    transport = PlanTransport()
    order: list[str] = []

    def mend(_connection: object) -> tuple[int, int, str]:
        order.append("mend")
        return 2, 2, ""

    sheets: list[Any] = []

    def place(_connection: object, made: Any, **kwargs: Any) -> tuple[list[Any], list[str]]:
        sheets.append((list(made), kwargs))
        return [], []

    monkeypatch.setattr(cli, "_connect", lambda *a, **k: ArchicadConnection(transport))
    monkeypatch.setattr(cli, "read_geo_location", lambda *a, **k: SYDNEY)

    def unfilter(_connection: object) -> str:
        order.append("unfilter")
        return ""

    monkeypatch.setattr(cli, "show_every_storey", unfilter)
    monkeypatch.setattr(cli, "mend_document_filters", mend)
    monkeypatch.setattr(cli, "planned_renovation_filter", lambda *a, **k: "PLANNED")
    monkeypatch.setattr(cli, "make_shadow_plan_sheets", place)
    # The command sets the global layer prefix to the shadow diagram's; put
    # it back after, so the site tests that follow see their own.
    monkeypatch.setattr(naming, "_prefix", naming.prefix())

    result = CliRunner().invoke(
        cli.app,
        [
            "shadow-plans",
            "--shadow-date",
            "06-21",
            "--shadow-hour",
            "6,9,12",
            "--shadow-pen",
            "3",
            "--label",
            "Proposed",
            # The combination is taken as it is: what it hides is the live
            # project's business, and the scripted one has no layers to read.
            "--no-site-context",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "JUNE 21 -6AM: the sun is below the horizon" in result.output
    created = transport.asked("CreateDocumentFrom3D")
    assert [c["sun"]["hour"] for c in created] == [9, 12]
    assert all(c["shadowFill"] == {"fillPen": 3} for c in created)
    assert all("Proposed" in c["name"] for c in created)
    assert order == ["unfilter", "mend"], "the filter off before, and mended after"
    ((placed, kwargs),) = sheets
    assert [one.plan.label for one in placed] == ["9AM", "12PM"]
    assert kwargs["set_label"] == "Proposed"
    assert "timing: made the documents in" in result.output
    assert "timing: the whole run took" in result.output


def test_the_context_the_site_tools_drew_is_shown_when_the_combination_hides_it() -> None:
    """Redfern, 8 October 2026: the office's combination hid every layer the
    site tools had drawn the context on, and the plans held the proposal's
    slab on a blank page. What the project has and the combination hides is
    what the plans switch on; a layer the project lacks is nobody's."""
    wanted = site_context_layers()
    assert [w.split(" | ")[1] for w in wanted] == [
        "Site Context.Terrain",
        "Site Context.Roads",
        "Site Context.Buildings",
        "Site Context.Future buildings",
    ]
    names = {"t": wanted[0], "b": wanted[2], "s": "01 | Floor.Structural"}
    hidden = {"t": True, "b": False, "s": False}
    assert hidden_among(wanted, names, hidden) == [wanted[0]]
    assert hidden_among(wanted, names, {"t": False, "b": False}) == []
    assert hidden_among(("01 | Floor.Structural",), names, {"s": True}) == ["01 | Floor.Structural"]


# -- the stack -----------------------------------------------------------------------

EXISTING = LegendRow("EXISTING", ("03 | Site Context.Buildings",), BASELINE)
FUTURE = LegendRow("FUTURE", ("03 | Site Context.Future",), BASELINE)
TOD = LegendRow("TOD", ("20 | Massing.TOD",), SCENARIO)
PROPOSED = LegendRow("PROPOSED", ("20 | Massing.Envelope", "20 | Massing.Podium"), SCENARIO)


def test_the_proposals_are_named_proposed_and_numbered_in_the_order_given() -> None:
    """Whatever the office calls its massings this week, the sets are
    Proposed 1, 2, 3 -- or Proposed alone when there is one."""
    assert stack_labels(0) == []
    assert stack_labels(1) == ["Proposed"]
    assert stack_labels(3) == ["Proposed 1", "Proposed 2", "Proposed 3"]


def test_existing_and_proposed_are_one_source_and_a_scenario_each() -> None:
    rows = legend_from_existing_and_proposed(
        ["03 | Site Context.Buildings"], [["20 | Massing.SEARs"], ["20 | Massing.Envelope"]]
    )
    assert [(row.label, row.role) for row in rows] == [
        ("Existing", BASELINE),
        ("Proposed 1", SCENARIO),
        ("Proposed 2", SCENARIO),
    ]
    assert legend_from_existing_and_proposed([], [["P"]])[0] == LegendRow(
        "Proposed", ("P",), SCENARIO
    )


def test_sources_accumulate_and_scenarios_stand_on_every_source() -> None:
    """A source shows itself and every earlier source; a scenario shows every
    source and itself; each hides the other rows. What the base combination
    hides that every set needs rides along as also_show."""
    rows = legend_combinations(
        [EXISTING, FUTURE, TOD, PROPOSED], also_show=["03 | Site Context.Terrain"]
    )
    assert [label for label, _, _ in rows] == ["EXISTING", "FUTURE", "TOD", "PROPOSED"]
    existing, future, tod, proposed = rows
    assert existing[1] == ("03 | Site Context.Terrain", "03 | Site Context.Buildings")
    assert existing[2] == (
        "03 | Site Context.Future",
        "20 | Massing.TOD",
        "20 | Massing.Envelope",
        "20 | Massing.Podium",
    )
    assert future[1][-2:] == ("03 | Site Context.Buildings", "03 | Site Context.Future")
    assert tod[1] == (
        "03 | Site Context.Terrain",
        "03 | Site Context.Buildings",
        "03 | Site Context.Future",
        "20 | Massing.TOD",
    )
    assert tod[2] == ("20 | Massing.Envelope", "20 | Massing.Podium")
    assert proposed[2] == ("20 | Massing.TOD",)


def test_the_legend_order_is_kept_however_the_roles_are_interleaved() -> None:
    rows = legend_combinations([TOD, EXISTING])
    assert [label for label, _, _ in rows] == ["TOD", "EXISTING"]
    assert rows[0][1] == ("03 | Site Context.Buildings", "20 | Massing.TOD")


def test_a_layer_two_scenarios_share_is_shown_by_both() -> None:
    first = LegendRow("A", ("20 | Podium", "20 | Tower A"), SCENARIO)
    second = LegendRow("B", ("20 | Podium", "20 | Tower B"), SCENARIO)
    (_, show_a, hide_a), (_, show_b, hide_b) = legend_combinations([first, second])
    assert "20 | Podium" in show_a and "20 | Podium" not in hide_a
    assert "20 | Podium" in show_b and "20 | Podium" not in hide_b
    assert hide_a == ("20 | Tower B",) and hide_b == ("20 | Tower A",)


def test_the_stack_reads_scenarios_first_then_sources_last_to_first() -> None:
    """Bottom to top. The first source is on top, so its shadow is drawn in
    its colour; each later source is seen only where those above cast nothing;
    the scenarios lie under every source, the last named over the earlier."""
    order = stack_order([EXISTING, FUTURE, TOD, PROPOSED])
    assert [row.label for row in order] == ["TOD", "PROPOSED", "FUTURE", "EXISTING"]
    assert [row.label for row in stack_order([EXISTING])] == ["EXISTING"]


def test_a_stack_makes_a_set_per_row_and_lets_the_lower_ones_show_through() -> None:
    """Each set under its own combination and label, each solid in its own
    pen, every set's surfaces filled in the transparent pen: the shadows are
    drawn, in the row's pen, and nothing else is (D142)."""
    transport = PlanTransport()
    settings = ShadowPlanSettings(shadow_fill={"fillIndex": 1})

    stack, said = make_shadow_plan_stack(
        ArchicadConnection(transport),
        _plans([9, 12]),
        settings=settings,
        members=[
            PlanSet("PROPOSED", f"{SS} Shadow Plans PROPOSED", 95),
            PlanSet("FUTURE", f"{SS} Shadow Plans FUTURE", 94),
            PlanSet("EXISTING", f"{SS} Shadow Plans EXISTING", 93),
        ],
    )

    assert said == []
    assert [label for label, _ in stack.piles] == ["PROPOSED", "FUTURE", "EXISTING"]
    created = transport.asked("CreateDocumentFrom3D")
    assert [c["name"] for c in created[::2]] == [
        f"{SS} Shadow Plan PROPOSED 21 Jun 09:00",
        f"{SS} Shadow Plan FUTURE 21 Jun 09:00",
        f"{SS} Shadow Plan EXISTING 21 Jun 09:00",
    ]
    assert all("fillUncutSurfaces" not in c for c in created)
    assert [c["uncutSurfaces"] for c in created[::2]] == [STACK_SURFACES] * 3
    assert STACK_SURFACES == {"fill": True, "fillType": "penColor", "pen": 0}
    assert [c["shadowFill"] for c in created[::2]] == [
        {"fillIndex": 1, "fillPen": 95, "backgroundPen": 95},
        {"fillIndex": 1, "fillPen": 94, "backgroundPen": 94},
        {"fillIndex": 1, "fillPen": 93, "backgroundPen": 93},
    ]
    pinned = transport.asked("SetViewSettings")
    combinations = dict.fromkeys(
        row["viewSettings"]["layerCombination"]
        for ask in pinned
        for row in ask["navigatorItemIdsWithViewSettings"]
    )
    assert list(combinations) == [
        f"{SS} Shadow Plans PROPOSED",
        f"{SS} Shadow Plans FUTURE",
        f"{SS} Shadow Plans EXISTING",
    ], "each set's views pinned to its own combination"


def test_a_rerun_of_a_stack_re_sets_the_surfaces_too() -> None:
    """A document an earlier run made is put back the way this run wants it."""
    transport = PlanTransport(
        existing=(
            f"{SS} Shadow Plan PROPOSED 21 Jun 09:00",
            f"{SS} Shadow Plan EXISTING 21 Jun 09:00",
        )
    )
    make_shadow_plan_stack(
        ArchicadConnection(transport),
        _plans([9]),
        settings=ShadowPlanSettings(),
        members=[PlanSet("PROPOSED", "P", 94), PlanSet("EXISTING", "X", 93)],
    )
    lowest, upper = transport.asked("SetDocumentFrom3D")
    assert lowest["uncutSurfaces"] == STACK_SURFACES == upper["uncutSurfaces"]
    assert upper["shadowFill"] == {"fillPen": 93, "backgroundPen": 93}


def _stack(day: dt.date, hours: list[int], *labels: str) -> Stack:
    """A stack of the labels, bottom to top, every set with every hour."""
    return Stack(piles=tuple((label, tuple(_made(day, hours, label))) for label in labels))


def test_a_combined_sheet_holds_every_set_of_an_hour_in_one_cell() -> None:
    """Named for the combined set; each cell's pile reads bottom to top, and
    the drawings of a cell are named apart for the hour and the set, since a
    sheet finds its drawings by name."""
    stack = _stack(dt.date(2024, 6, 21), [9, 12, 15], "PROPOSED", "FUTURE", "EXISTING")

    groups, cells = stack_sheet_groups(stack, sheets="one")

    assert [name for name, _ in groups] == [f"{SS} Shadow Plans Combined - JUNE 21"]
    assert cells == 3
    first_cell = groups[0][1][0]
    assert first_cell == [
        ("VIEW-PROPOSED-21 Jun 09:00", "JUNE 21 -9AM PROPOSED"),
        ("VIEW-FUTURE-21 Jun 09:00", "JUNE 21 -9AM FUTURE"),
        ("VIEW-EXISTING-21 Jun 09:00", "JUNE 21 -9AM EXISTING"),
    ]
    assert [len(pile) for pile in groups[0][1]] == [3, 3, 3]


def test_an_hour_a_set_lacks_is_left_out_of_that_cell() -> None:
    day = dt.date(2024, 6, 21)
    stack = Stack(
        piles=(
            ("PROPOSED", tuple(_made(day, [9, 12], "PROPOSED"))),
            ("EXISTING", tuple(_made(day, [9], "EXISTING"))),
        )
    )
    groups, _ = stack_sheet_groups(stack, sheets="one")
    assert [len(pile) for pile in groups[0][1]] == [2, 1]


def test_the_combined_sheets_remove_their_stale_sheets_and_clear_the_upper_drawings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sun_study.archicad import shadow_plans as module

    removed: list[tuple[str, set[str]]] = []
    placed: list[Any] = []

    def forget(_connection: object, stem: str, keep: Any) -> list[str]:
        removed.append((stem, set(keep)))
        return [f"{stem}OLD"]

    def place(_connection: object, groups: Any, **kwargs: Any) -> list[Any]:
        placed.append((groups, kwargs))
        return []

    from sun_study.archicad.layout import LayoutReport

    redrawn: list[str] = []

    def place_one(_connection: object, groups: Any, **kwargs: Any) -> list[Any]:
        place(_connection, groups, **kwargs)
        return [
            LayoutReport(name, 2, (), 500.0, (), database_id=f"DB-{name}") for name, _ in groups
        ]

    def redraw(_connection: object, database_id: str) -> str | None:
        redrawn.append(database_id)
        return "could not redraw"

    monkeypatch.setattr(module, "remove_stale_layouts", forget)
    monkeypatch.setattr(module, "place_stacks_on_sheets", place_one)
    monkeypatch.setattr(module, "update_drawings", redraw)
    stack = _stack(dt.date(2024, 6, 21), [9, 12], "PROPOSED", "EXISTING")

    reports, gone, said = make_stack_sheets(
        ArchicadConnection(PlanTransport()), stack, sheets="one", scale=500.0
    )

    assert len(reports) == 1
    assert redrawn == [f"DB-{SS} Shadow Plans Combined - JUNE 21"], "every sheet redrawn"
    assert said == ["could not redraw"]

    assert removed == [
        (f"{SS} Shadow Plans Combined - ", {f"{SS} Shadow Plans Combined - JUNE 21"})
    ]
    assert gone == [f"{SS} Shadow Plans Combined - OLD"]
    ((groups, kwargs),) = placed
    assert len(groups) == 1 and kwargs["cells"] == 2 and kwargs["scale"] == 500.0
    assert kwargs["transparent_above_lowest"] is True


class ArrangeTransport:
    """Answers ArrangeDrawings and records what was asked."""

    def __init__(self) -> None:
        self.asked: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        given = payload["parameters"].get("addOnCommandParameters") or {}
        self.asked.append(given)
        return {
            "succeeded": True,
            "result": {
                "addOnCommandResponse": {"success": True, "arranged": len(given["drawings"])}
            },
        }


def test_the_stacking_order_is_asked_of_the_add_on_only_when_wanted() -> None:
    """An add-on built before the switch refuses a field it does not know, so
    the plain placement sends none."""
    from sun_study.archicad.sun_eyes import arrange_drawings

    transport = ArrangeTransport()
    cell = (0.1, 0.1, 0.4, 0.4)
    arrange_drawings(ArchicadConnection(transport), "LAYOUT", [("A", cell)])
    arrange_drawings(
        ArchicadConnection(transport), "LAYOUT", [("P", cell), ("E", cell)], stack=True
    )
    plain, stacked = transport.asked
    assert "stack" not in plain
    assert stacked["stack"] is True
    assert [d["guid"] for d in stacked["drawings"]] == ["P", "E"], "bottom to top"
    assert stacked["drawings"][0]["frame"] == stacked["drawings"][1]["frame"]
    assert all("transparentBackground" not in d for d in stacked["drawings"])


def test_a_transparent_background_is_sent_per_drawing_only_when_asked() -> None:
    from sun_study.archicad.sun_eyes import arrange_drawings

    transport = ArrangeTransport()
    cell = (0.1, 0.1, 0.4, 0.4)
    arrange_drawings(
        ArchicadConnection(transport),
        "LAYOUT",
        [("P", cell), ("F", cell), ("E", cell)],
        stack=True,
        transparent=[False, True, True],
    )
    (asked,) = transport.asked
    assert [d["transparentBackground"] for d in asked["drawings"]] == [False, True, True]
    with pytest.raises(ValueError, match="2 transparency flags for 1 drawings"):
        arrange_drawings(
            ArchicadConnection(transport), "LAYOUT", [("P", cell)], transparent=[False, True]
        )


def cli_module() -> Any:
    from sun_study import cli

    return cli


def _stacked_command(
    monkeypatch: pytest.MonkeyPatch, *legend_args: str
) -> tuple[Any, PlanTransport, list[tuple[str, list[str], list[str], str]], list[Any]]:
    """Run shadow-plans over the scripted project with the given legend."""
    from typer.testing import CliRunner

    from sun_study import cli

    transport = PlanTransport()
    combinations: list[tuple[str, list[str], list[str], str]] = []

    def pin(_connection: object, name: str, *, show: Any, hide: Any, base: str = "") -> str:
        combinations.append((name, list(show), list(hide), base))
        return name

    sheets: list[Any] = []

    def place(
        _connection: object, stack: Any, **kwargs: Any
    ) -> tuple[list[Any], list[str], list[str]]:
        sheets.append((stack, kwargs))
        return [], [], []

    monkeypatch.setattr(cli, "_connect", lambda *a, **k: ArchicadConnection(transport))
    monkeypatch.setattr(cli, "read_geo_location", lambda *a, **k: SYDNEY)
    monkeypatch.setattr(cli, "show_every_storey", lambda _c: "")
    monkeypatch.setattr(cli, "mend_document_filters", lambda _c: (0, 0, ""))
    monkeypatch.setattr(cli, "planned_renovation_filter", lambda *a, **k: "PLANNED")
    monkeypatch.setattr(cli, "ensure_layer_combination", pin)
    from sun_study.archicad.layout import NavigatorItem
    from sun_study.archicad.plan_sheet import PlanWindow

    pen_sets: list[tuple[str, str, dict[int, Any]]] = []

    def make_pen_set(_c: object, name: str, source: str, colours: Any) -> int:
        pen_sets.append((name, source, dict(colours)))
        return 42

    monkeypatch.setattr(cli, "pen_table", lambda _c, **_k: ())
    monkeypatch.setattr(cli, "_pen_source", lambda _c, _p: ("PT-GUID", "Office Pens"))
    monkeypatch.setattr(cli, "legend_pen_set", make_pen_set)
    monkeypatch.setattr(cli, "plan_window", lambda _c, _n: PlanWindow(-100.0, -60.0, 100.0, 140.0))
    monkeypatch.setattr(cli, "master_layouts", lambda _c: ())
    monkeypatch.setattr(
        cli,
        "choose_master",
        lambda _m, wanted: NavigatorItem("MASTER", wanted or "A1", "MasterLayoutItem", ""),
    )
    monkeypatch.setattr(cli, "cell_size_mm", lambda *_a, **_k: (230.0, 540.0))
    from sun_study.archicad import context_model

    monkeypatch.setattr(context_model, "boundary_layer", lambda *_a: None)
    monkeypatch.setattr(cli, "make_stack_sheets", place)
    monkeypatch.setattr(naming, "_prefix", naming.prefix())
    monkeypatch.setattr(cli, "_PEN_SETS_MADE", pen_sets, raising=False)

    result = CliRunner().invoke(
        cli.app,
        [
            "shadow-plans",
            "--shadow-date",
            "06-21",
            "--shadow-hour",
            "9,12",
            "--layer-combination",
            "04 | Shadow Diagrams",
            "--no-site-context",
            *legend_args,
        ],
    )
    return result, transport, combinations, sheets


def test_the_stacked_command_takes_the_shadow_diagrams_legend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: --shadow-source and --shadow-scenario as the shadow diagram
    takes them, a combination per row made from the base, a set of documents
    per row in stacking order, the lowest filled and the rest transparent, and
    one combined sheet set."""
    result, transport, combinations, sheets = _stacked_command(
        monkeypatch,
        "--shadow-source",
        "EXISTING=03 | Site Context.Buildings",
        "--shadow-source",
        "FUTURE=03 | Site Context.Future",
        "--shadow-scenario",
        "TOD=20 | Massing.TOD",
        "--shadow-scenario",
        "PROPOSED=20 | Massing.Envelope, 20 | Massing.Podium",
        "--label",
        "Ignored",
    )

    assert result.exit_code == 0, result.output
    assert "--label 'Ignored' is set aside" in result.output
    prefix = naming.SHADOW_PREFIX
    assert [row[0] for row in combinations] == [
        f"{prefix} Shadow Plans EXISTING",
        f"{prefix} Shadow Plans FUTURE",
        f"{prefix} Shadow Plans TOD",
        f"{prefix} Shadow Plans PROPOSED",
    ]
    assert all(row[3] == "04 | Shadow Diagrams" for row in combinations)
    assert combinations[1][1] == ["03 | Site Context.Buildings", "03 | Site Context.Future"]
    assert combinations[3][2] == ["20 | Massing.TOD"]
    created = transport.asked("CreateDocumentFrom3D")
    assert [c["name"] for c in created[::2]] == [
        f"{prefix} Shadow Plan TOD 21 Jun 09:00",
        f"{prefix} Shadow Plan PROPOSED 21 Jun 09:00",
        f"{prefix} Shadow Plan FUTURE 21 Jun 09:00",
        f"{prefix} Shadow Plan EXISTING 21 Jun 09:00",
    ], "made bottom to top"
    assert [c["uncutSurfaces"] for c in created[::2]] == [STACK_SURFACES] * 4
    pens = {c["name"].split()[-4]: c["shadowFill"]["fillPen"] for c in created[::2]}
    assert list(pens) == ["TOD", "PROPOSED", "FUTURE", "EXISTING"]
    assert len(set(pens.values())) == 4, "a pen of its own for every row"
    ((stack, kwargs),) = sheets
    assert [label for label, _ in stack.piles] == ["TOD", "PROPOSED", "FUTURE", "EXISTING"]
    assert kwargs["sheets"] == "two"
    assert "TOD < PROPOSED < FUTURE < EXISTING" in result.output
    # D143: a 200 m window in a 230 mm cell is 1:1000; the drawings print in
    # the stack's own pen set; the legend is in the legend's words and colours.
    assert kwargs["scale"] == 1000.0
    assert kwargs["window"].centre == (0.0, 40.0)
    assert kwargs["pen_table_index"] == 42
    assert kwargs["legend"][0] == ("EXISTING NEIGHBOURING BUILDINGS", (235, 235, 235))
    assert [words for words, _ in kwargs["legend"]][2:] == [
        "CURRENT LEP 2023 BUILDING HEIGHT LIMIT",
        "PROPOSED BUILDING ENVELOPE",
    ]
    ((name, source, colours),) = cli_module()._PEN_SETS_MADE
    assert name == f"{prefix} Shadow Plans" and source == "PT-GUID"
    assert set(colours.values()) == {
        (235, 235, 235),
        (216, 216, 216),
        (207, 215, 224),
        (156, 172, 191),
    }, "every row's pen set to its legend colour"
    assert "drawn at 1:1000" in result.output


def test_existing_and_proposed_still_make_a_stack_and_take_their_pens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, transport, combinations, sheets = _stacked_command(
        monkeypatch,
        "--existing",
        "03 | Site Context.Buildings",
        "--proposed",
        "20 | Massing.SEARs",
        "--proposed",
        "20 | Massing.Envelope, 20 | Massing.Podium",
        "--proposed-pen",
        "150",
    )

    assert result.exit_code == 0, result.output
    prefix = naming.SHADOW_PREFIX
    assert [row[0] for row in combinations] == [
        f"{prefix} Shadow Plans Existing",
        f"{prefix} Shadow Plans Proposed 1",
        f"{prefix} Shadow Plans Proposed 2",
    ]
    assert combinations[2][2] == ["20 | Massing.SEARs"]
    created = transport.asked("CreateDocumentFrom3D")
    pens = [c["shadowFill"]["fillPen"] for c in created[::2]]
    assert pens[0] == 150, "the pen given for Proposed 1, at the bottom"
    assert "pen 150  given" in result.output
    ((_, _, colours),) = cli_module()._PEN_SETS_MADE
    assert 150 not in colours, "a pen somebody gave keeps its own colour"
    ((stack, _),) = sheets
    assert [label for label, _ in stack.piles] == ["Proposed 1", "Proposed 2", "Existing"]


def test_the_two_ways_of_naming_the_legend_do_not_mix(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _, _, _ = _stacked_command(
        monkeypatch,
        "--shadow-source",
        "EXISTING=03 | Site Context.Buildings",
        "--proposed",
        "20 | Massing.SEARs",
    )
    assert result.exit_code != 0
    assert "Name the legend one way" in result.output


def test_the_sun_date_is_in_archicads_own_clock_when_the_add_on_reports_one() -> None:
    """D135. Archicad reads a sun date in the project location's time zone.
    The sample project keeps UTC+3 while its hours were asked for in Dubai
    (UTC+4), and every document was drawn an hour late. With the clock
    known, 09:00 Dubai goes over as 08:00 in Archicad's clock, daylight
    saving off, and the document is still named for 09:00."""
    dubai = ZoneInfo("Asia/Dubai")
    plan = ShadowPlan(
        when=dt.datetime(2024, 6, 21, 9, tzinfo=dubai),
        label="9AM",
        altitude_deg=43.6,
        clock_minutes=180,
    )
    assert plan.sun_for_archicad() == {
        "year": 2024,
        "month": 6,
        "day": 21,
        "hour": 8,
        "minute": 0,
        "second": 0,
        "summerTime": False,
    }
    assert plan.name() == f"{SS} Shadow Plan 21 Jun 09:00"
    assert plan.reference == "SP0621-0900"


def test_daylight_saving_is_folded_into_archicads_clock_rather_than_flagged() -> None:
    """A Sydney 21 December 09:00 is AEDT, UTC+11; a project keeping AEST,
    UTC+10, is handed 08:00 with the flag off, which is the same instant."""
    plan = ShadowPlan(
        when=dt.datetime(2024, 12, 21, 9, tzinfo=ZONE),
        label="9AM",
        altitude_deg=50.0,
        clock_minutes=600,
    )
    sent = plan.sun_for_archicad()
    assert (sent["day"], sent["hour"], sent["summerTime"]) == (21, 8, False)


def test_without_a_clock_the_wall_clock_and_its_daylight_flag_go_over_as_before() -> None:
    plan = ShadowPlan(
        when=dt.datetime(2024, 12, 21, 9, tzinfo=ZONE), label="9AM", altitude_deg=50.0
    )
    sent = plan.sun_for_archicad()
    assert (sent["hour"], sent["summerTime"]) == (9, True)


def test_shadow_plans_carry_the_clock_onto_every_plan() -> None:
    moments = [dt.datetime(2024, 6, 21, hour, tzinfo=ZONE) for hour in (9, 12)]
    up, _ = shadow_plans(SYDNEY, moments, ["9AM", "12PM"], clock_minutes=600)
    assert [plan.clock_minutes for plan in up] == [600, 600]
    assert [plan.sun_for_archicad()["hour"] for plan in up] == [9, 12]


class RedrawTransport:
    """Answers UpdateDrawings with success, or with Tapir's error, and records it."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload["parameters"]["addOnCommandId"]["commandName"]
        given = payload["parameters"].get("addOnCommandParameters") or {}
        self.sent.append((name, given))
        if name == "GetAddOnVersion":
            answer: dict[str, Any] = {"version": "1.5.8"}
        elif self.refuse:
            answer = {"error": {"code": 1, "message": "needs Archicad 27"}}
        else:
            answer = {"success": True}
        return {"succeeded": True, "result": {"addOnCommandResponse": answer}}


def test_a_sheet_is_redrawn_through_tapir_and_a_refusal_is_said_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D142: a drawing of a 3D Document is not redrawn when the document is
    re-set, so the combined sheet asks for it; an Archicad that cannot is
    told about, and the sheet stands."""
    from sun_study.archicad import layout as module

    monkeypatch.setattr(
        module,
        "_drawings_by_name",
        lambda _c, _d: {"A": {"elementId": {"guid": "G1"}}, "B": {"elementId": {"guid": "G2"}}},
    )
    ok = RedrawTransport()
    assert module.update_drawings(ArchicadConnection(ok), "LAYOUT") is None
    asked = [given for name, given in ok.sent if name == "UpdateDrawings"]
    assert asked == [{"elements": [{"elementId": {"guid": "G1"}}, {"elementId": {"guid": "G2"}}]}]

    note = module.update_drawings(ArchicadConnection(RedrawTransport(refuse=True)), "LAYOUT")
    assert note is not None and "redrawn" in note

    monkeypatch.setattr(module, "_drawings_by_name", lambda _c, _d: {})
    quiet = RedrawTransport()
    assert module.update_drawings(ArchicadConnection(quiet), "LAYOUT") is None
    assert not [name for name, _ in quiet.sent if name == "UpdateDrawings"]
