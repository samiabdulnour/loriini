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
    MadePlan,
    ShadowPlan,
    ShadowPlanSettings,
    make_shadow_plans,
    plan_sheet_groups,
    shadow_plans,
)
from sun_study.archicad.views import StoreyView

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


def _made(day: dt.date, hours: list[int]) -> list[MadePlan]:
    times, labels = moments(day, hours)
    plans = shadow_plans(SYDNEY, times, labels)[0]
    return [
        MadePlan(plan=plan, view=StoreyView(0, plan.name(), f"VIEW-{plan.stamp}"), reused=False)
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
