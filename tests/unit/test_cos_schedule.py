"""The hourly COS figures as a live schedule: what is written, and where it goes.

Archicad makes no schedule through its API, so the scheme is the project's
and these test the two things around it: every sunlit fill of an hour gets
that hour's time and share -- the same two values on all of them, or the
schedule cannot merge them into one row -- and the schedule goes on the
sheet by its top-left corner, once.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.cos_schedule import (
    PERCENTAGE,
    PROPERTY_SET,
    TIME,
    HourFills,
    ScheduleView,
    clock_words,
    find_schedule,
    place_schedule,
    schedule_names,
    share_words,
    tag_hours,
)
from sun_study.archicad.layout import LayoutSheet
from sun_study.archicad.penetration import MeasuredFill
from sun_study.archicad.sheets import straighten_and_tile


class Scripted:
    """Answers add-on commands from a script, and records what was asked.

    A callable answer is given the parameters; anything else is returned as
    it stands. A command missing from the script answers the way Archicad
    does for a command no add-on registered.
    """

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload["parameters"]["addOnCommandId"]["commandName"]
        given = payload["parameters"].get("addOnCommandParameters") or {}
        self.asked.append((name, given))
        if name == "GetAddOnVersion":
            return {"succeeded": True, "result": {"addOnCommandResponse": {"version": "1.5.8"}}}
        if name not in self.answers:
            return {
                "succeeded": False,
                "error": {
                    "code": 4010,
                    "message": "Archicad does not have the registered Add-On command "
                    f"with the name : Loriini.{name}",
                },
            }
        answer = self.answers[name]
        answer = answer(given) if callable(answer) else answer
        return {"succeeded": True, "result": {"addOnCommandResponse": answer}}

    def given(self, command: str) -> list[dict[str, Any]]:
        return [given for name, given in self.asked if name == command]


def _fills(*guids: str) -> tuple[MeasuredFill, ...]:
    return tuple(MeasuredFill({"elementId": {"guid": guid}}, "in sun at 09:00") for guid in guids)


def _every_value_lands(given: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "results": [{"success": True} for _ in given["values"]]}


def test_the_hour_and_the_share_read_as_the_schedule_writes_them() -> None:
    assert clock_words(dt.datetime(2026, 6, 21, 9)) == "9 AM"
    assert clock_words(dt.time(12)) == "12 PM"
    assert clock_words(dt.time(15)) == "3 PM"
    assert clock_words(dt.time(0)) == "12 AM"
    assert share_words(0.68828) == "68.8%"
    assert share_words(1.0) == "100.0%"


def test_every_fill_of_an_hour_carries_that_hours_two_values() -> None:
    """The same time and share on every patch of the hour, or the schedule
    lists a row per patch instead of one per hour."""
    transport = Scripted({"SetIfcProperties": _every_value_lands})
    report = tag_hours(
        ArchicadConnection(transport),
        [
            HourFills("9 AM", 0.688, _fills("a", "b")),
            HourFills("10 AM", 0.646, _fills("c")),
        ],
    )

    written = transport.given("SetIfcProperties")[0]["values"]
    by_fill: dict[str, dict[str, str]] = {}
    for value in written:
        assert value["propertySet"] == PROPERTY_SET
        by_fill.setdefault(value["guid"], {})[value["name"]] = value["text"]
    assert by_fill == {
        "a": {TIME: "9 AM", PERCENTAGE: "68.8%"},
        "b": {TIME: "9 AM", PERCENTAGE: "68.8%"},
        "c": {TIME: "10 AM", PERCENTAGE: "64.6%"},
    }
    assert report.complete and report.written == 6
    assert "onto 3 sunlit fills" in report.describe()


def test_an_add_on_from_before_the_command_is_said_and_nothing_raises() -> None:
    report = tag_hours(ArchicadConnection(Scripted({})), [HourFills("9 AM", 0.5, _fills("a"))])
    assert not report.complete and report.written == 0
    assert "install the current one" in report.describe()


def test_an_archicad_that_cannot_store_them_is_named_as_the_reason() -> None:
    refusing = {
        "SetIfcProperties": {
            "success": False,
            "error": {"message": "Archicad 29 and later give an add-on no way", "code": -1},
        }
    }
    report = tag_hours(
        ArchicadConnection(Scripted(refusing)), [HourFills("9 AM", 0.5, _fills("a"))]
    )
    assert not report.complete
    assert "Archicad 29 and later" in report.describe()


def test_a_refused_value_is_counted_against_the_ones_that_landed() -> None:
    def half(given: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "results": [
                {"success": True}
                if value["name"] == TIME
                else {"success": False, "error": {"message": "locked", "code": 7}}
                for value in given["values"]
            ],
        }

    report = tag_hours(
        ArchicadConnection(Scripted({"SetIfcProperties": half})),
        [HourFills("9 AM", 0.5, _fills("a", "b"))],
    )
    assert (report.written, report.attempted) == (2, 4)
    assert "locked" in report.describe()


def _tree(*items: tuple[str, str, str]) -> dict[str, Any]:
    """A navigator tree of one folder holding ``(type, name, guid)`` items."""
    return {
        "navigatorItemTree": {
            "rootItem": {
                "navigatorItemId": {"guid": "root"},
                "type": "FolderItem",
                "name": "",
                "children": [
                    {
                        "navigatorItem": {
                            "navigatorItemId": {"guid": guid},
                            "type": kind,
                            "name": name,
                        }
                    }
                    for kind, name, guid in items
                ],
            }
        }
    }


PROJECT_MAP = _tree(
    ("ScheduleItem", "Areas COS solar", "pm-cos"),
    ("ScheduleItem", "Areas COS solar 2hr", "pm-2hr"),
    ("StoryItem", "GROUND", "pm-ground"),
)


def _maps(view_map: dict[str, Any]) -> Any:
    def answer(given: dict[str, Any]) -> dict[str, Any]:
        return PROJECT_MAP if given["navigatorMapId"] == "ProjectMap" else view_map

    return answer


def test_the_schedules_offered_are_the_project_maps() -> None:
    transport = Scripted({"GetNavigatorItemTree": _maps(_tree())})
    assert schedule_names(ArchicadConnection(transport)) == (
        "Areas COS solar",
        "Areas COS solar 2hr",
    )


def test_the_view_maps_own_view_of_the_schedule_is_placed_and_nothing_is_cloned() -> None:
    transport = Scripted(
        {"GetNavigatorItemTree": _maps(_tree(("ScheduleItem", "Areas COS solar", "vm-cos")))}
    )
    found = find_schedule(ArchicadConnection(transport), "areas cos SOLAR ")
    assert found == ScheduleView("Areas COS solar", "vm-cos")
    assert not transport.given("CloneProjectMapItemToViewMap")


def test_a_schedule_with_no_view_is_cloned_into_the_view_map() -> None:
    transport = Scripted(
        {
            "GetNavigatorItemTree": _maps(_tree()),
            "CloneProjectMapItemToViewMap": {
                "navigatorItems": [{"navigatorItemId": {"guid": "vm-new"}}]
            },
        }
    )
    found = find_schedule(ArchicadConnection(transport), "Areas COS solar")
    assert found == ScheduleView("Areas COS solar", "vm-new")
    cloned = transport.given("CloneProjectMapItemToViewMap")[0]["viewsData"]
    assert cloned == [{"navigatorItemId": {"guid": "pm-cos"}}]


def test_a_schedule_the_project_does_not_have_is_none() -> None:
    transport = Scripted({"GetNavigatorItemTree": _maps(_tree())})
    assert find_schedule(ArchicadConnection(transport), "Areas GFA") is None


SCHEDULE = ScheduleView("Areas COS solar", "vm-cos")


def test_the_schedule_is_placed_by_its_top_left_corner_square_and_full_size() -> None:
    transport = Scripted(
        {
            "GetDrawings": {"success": True, "drawings": [{"name": "GROUND 09:00"}]},
            "CreateDrawings": {"elements": [{"elementId": {"guid": "drawing"}}]},
        }
    )
    assert place_schedule(ArchicadConnection(transport), "layout", SCHEDULE, (0.55, 0.50))

    (drawing,) = transport.given("CreateDrawings")[0]["drawingsData"]
    assert drawing["navigatorItemId"] == {"guid": "vm-cos"}
    assert drawing["layoutDatabaseId"] == {"guid": "layout"}
    assert drawing["name"] == "Areas COS solar"
    assert drawing["position"] == {"x": 0.55, "y": 0.50}
    assert (drawing["anchor"], drawing["angle"], drawing["scale"]) == ("topLeft", 0.0, 1.0)


def test_a_sheet_already_carrying_the_schedule_is_left_alone() -> None:
    transport = Scripted(
        {"GetDrawings": {"success": True, "drawings": [{"name": "Areas COS solar"}]}}
    )
    assert not place_schedule(ArchicadConnection(transport), "layout", SCHEDULE, (0.5, 0.5))
    assert not transport.given("CreateDrawings")


def test_an_add_on_that_cannot_anchor_a_drawing_is_told_to_update() -> None:
    transport = Scripted(
        {
            "GetDrawings": {"success": True, "drawings": []},
            "CreateDrawings": {
                "success": False,
                "error": {
                    "code": 4002,
                    "message": "Invalid command parameters (Validation failed on schema "
                    "rule 'additionalProperties' while trying to validate field on path "
                    "'#/drawingsData/0/anchor'.)",
                },
            },
        }
    )
    with pytest.raises(ArchicadError, match="install the current one"):
        place_schedule(ArchicadConnection(transport), "layout", SCHEDULE, (0.5, 0.5))


def _tiled(leave: tuple[str, ...]) -> list[str]:
    """Which of a plan and a schedule a tiling pass moves."""
    elements = [{"elementId": {"guid": "plan"}}, {"elementId": {"guid": "schedule"}}]

    def one(name: str, x: float) -> dict[str, Any]:
        bounds = {"xMin": x, "yMin": 0.1, "xMax": x + 0.2, "yMax": 0.3}
        return {"details": {"customName": name, "angle": 0.0, "ratio": 1.0, "bounds": bounds}}

    transport = Scripted(
        {
            "ChangeWindow": {"success": True},
            "GetElementsByType": {"elements": elements},
            "GetDetailsOfElements": {
                "detailsOfElements": [one("GROUND 09:00", 0.1), one("Areas COS solar", 0.6)]
            },
            "MoveElements": {"executionResults": [{"success": True}]},
        }
    )
    straighten_and_tile(
        ArchicadConnection(transport),
        "layout",
        LayoutSheet(width_mm=841.0, height_mm=594.0),
        leave=leave,
    )
    return [
        move["elementId"]["guid"]
        for given in transport.given("MoveElements")
        for move in given["elementsWithMoveVectors"]
    ]


def test_the_tiling_leaves_the_schedule_where_it_was_put() -> None:
    """Shrunk with the plans to fit the page, the schedule's text would no
    longer be the size it was set to; dealt with them, it would take a cell."""
    assert _tiled(()) == ["plan", "schedule"]
    assert _tiled(("Areas COS solar",)) == ["plan"]


HOURS = [HourFills("9 AM", 0.688, _fills("a"))]


def test_the_run_swaps_the_table_for_the_schedule_once_the_values_are_on() -> None:
    from sun_study import cli

    transport = Scripted(
        {
            "SetIfcProperties": _every_value_lands,
            "GetNavigatorItemTree": _maps(_tree(("ScheduleItem", "Areas COS solar", "vm-cos"))),
        }
    )
    found = cli._cos_schedule(
        ArchicadConnection(transport), "Areas COS solar", HOURS, hourly=True, sheet=True
    )
    assert found == ScheduleView("Areas COS solar", "vm-cos")


@pytest.mark.parametrize(
    ("answers", "hourly", "why"),
    [
        ({}, True, "an add-on that cannot write the values"),
        ({"SetIfcProperties": _every_value_lands}, True, "a project without the schedule"),
        ({"SetIfcProperties": _every_value_lands}, False, "no hourly fills to list"),
    ],
)
def test_the_table_stays_when_the_schedule_would_be_short(
    answers: dict[str, Any], hourly: bool, why: str
) -> None:
    from sun_study import cli

    transport = Scripted({**answers, "GetNavigatorItemTree": _maps(_tree())})
    found = cli._cos_schedule(
        ArchicadConnection(transport), "Areas COS solar", HOURS, hourly=hourly, sheet=True
    )
    assert found is None, why
    if not hourly:
        assert not transport.given("SetIfcProperties"), "nothing is written for no fills"
