"""Archicad's clock (D135): read from the add-on, and the hour it is handed."""

from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from sun_study.archicad.clock import describe_clock, read_archicad_clock, sun_date
from sun_study.archicad.connection import ArchicadConnection

DUBAI = ZoneInfo("Asia/Dubai")
SYDNEY = ZoneInfo("Australia/Sydney")


class Transport:
    """An Archicad that answers add-on commands from a script."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.commands: list[str] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["command"] != "API.ExecuteAddOnCommand":
            return {"succeeded": True, "result": {}}
        name = payload["parameters"]["addOnCommandId"]["commandName"]
        self.commands.append(name)
        if name not in self.responses:
            raise AssertionError(f"unscripted command {name!r}")
        return {"succeeded": True, "result": {"addOnCommandResponse": self.responses[name]}}


def connect(responses: dict[str, Any]) -> tuple[ArchicadConnection, Transport]:
    transport = Transport({"GetAddOnVersion": {"version": "1.5.7"}, **responses})
    return ArchicadConnection(transport), transport


def test_the_clock_is_the_project_locations_time_zone_in_minutes() -> None:
    connection, transport = connect(
        {"GetPlace": {"success": True, "timeZoneInMinutes": 180, "summerTime": False}}
    )
    assert read_archicad_clock(connection) == 180
    assert transport.commands == ["GetPlace"]


def test_an_add_on_built_before_get_place_leaves_the_clock_unknown() -> None:
    connection, _ = connect({"GetPlace": {"error": {"code": 4010, "message": "no such command"}}})
    assert read_archicad_clock(connection) is None


def test_an_answer_without_a_zone_leaves_the_clock_unknown() -> None:
    connection, _ = connect({"GetPlace": {"success": True}})
    assert read_archicad_clock(connection) is None


def test_the_instant_is_expressed_in_archicads_clock() -> None:
    nine_dubai = dt.datetime(2024, 6, 21, 9, tzinfo=DUBAI)
    assert sun_date(nine_dubai, 180)["hour"] == 8
    assert sun_date(nine_dubai, 240)["hour"] == 9
    # Across midnight the day moves with the hour.
    late = dt.datetime(2024, 6, 21, 1, tzinfo=DUBAI)
    sent = sun_date(late, -300)
    assert (sent["day"], sent["hour"]) == (20, 16)


def test_the_run_says_whose_clock_the_hours_are_in() -> None:
    nine_dubai = dt.datetime(2024, 6, 21, 9, tzinfo=DUBAI)
    differs = describe_clock("Asia/Dubai", 180, nine_dubai)
    assert "UTC+03:00" in differs and "09:00 as 08:00" in differs

    nine_sydney = dt.datetime(2024, 6, 21, 9, tzinfo=SYDNEY)
    same = describe_clock("Australia/Sydney", 600, nine_sydney)
    assert "handed over as they are" in same

    unknown = describe_clock("Australia/Sydney", None, nine_sydney)
    assert "cannot say" in unknown and "D135" in unknown
