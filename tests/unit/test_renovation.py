"""Renovation filters by name: what the add-on lists, and what a run resolves.

An office that keeps its massing scenarios as renovation filters names a
scenario the way the Renovation palette does (Crows Nest, October 2026); the
views take the filter's GUID. Nothing here needs Archicad: the add-on's
answer is scripted.
"""

from __future__ import annotations

from typing import Any

import pytest

from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.renovation import (
    RenovationFilter,
    renovation_filters,
    resolve_renovation_filter,
    set_renovation_filter,
)

PLANNED = "38FD3426-70C5-9C4D-ACA5-877D4A623A36"
TOD = "62AA7A95-BEAD-4C9C-8A4B-72C128F11D7B"


class FilterTransport:
    """An add-on that lists the palette's filters, or one too old to."""

    def __init__(self, *, has_command: bool = True) -> None:
        self.has_command = has_command

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.has_command:
            answer: dict[str, Any] = {
                "error": {"code": 4010, "message": "does not have the registered Add-On command"}
            }
        else:
            answer = {
                "success": True,
                "renovationFilters": [
                    {"guid": PLANNED, "name": "04 Planned Status"},
                    {"guid": TOD, "name": "SCENARIO 2_COMPLIANT TOD"},
                ],
                "current": TOD,
            }
        return {"succeeded": True, "result": {"addOnCommandResponse": answer}}


def test_the_filters_come_in_the_palettes_order_with_the_one_shown_now() -> None:
    filters, current = renovation_filters(ArchicadConnection(FilterTransport()))
    assert [one.name for one in filters] == ["04 Planned Status", "SCENARIO 2_COMPLIANT TOD"]
    assert current == TOD


def test_a_name_is_found_whatever_its_case_and_spacing() -> None:
    connection = ArchicadConnection(FilterTransport())
    found = resolve_renovation_filter(connection, "  scenario 2_compliant   TOD ")
    assert found == RenovationFilter(guid=TOD, name="SCENARIO 2_COMPLIANT TOD")


def test_a_guid_is_found_and_named() -> None:
    found = resolve_renovation_filter(ArchicadConnection(FilterTransport()), "{" + PLANNED + "}")
    assert found.name == "04 Planned Status"


def test_a_name_the_project_lacks_is_refused_with_the_names_it_has() -> None:
    with pytest.raises(ArchicadError) as refused:
        resolve_renovation_filter(ArchicadConnection(FilterTransport()), "SCENARIO 9")
    assert "04 Planned Status; SCENARIO 2_COMPLIANT TOD" in str(refused.value)


def test_an_older_add_on_takes_a_guid_as_given_and_says_a_name_needs_the_current_build() -> None:
    connection = ArchicadConnection(FilterTransport(has_command=False))
    assert resolve_renovation_filter(connection, TOD) == RenovationFilter(guid=TOD, name="")
    with pytest.raises(ArchicadError, match="Install the current build"):
        resolve_renovation_filter(connection, "SCENARIO 2_COMPLIANT TOD")


class SettingTransport(FilterTransport):
    """The palette, and an add-on that switches the filter, or one too old to."""

    def __init__(self, *, has_set: bool = True) -> None:
        super().__init__()
        self.has_set = has_set
        self.set: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload["parameters"]["addOnCommandId"]["commandName"]
        if name != "SetRenovationFilter":
            return super().send(payload)
        self.set.append(payload["parameters"].get("addOnCommandParameters") or {})
        answer: dict[str, Any] = (
            {"success": True, "name": "04 Planned Status"}
            if self.has_set
            else {"error": {"code": 4010, "message": "does not have the registered Add-On command"}}
        )
        return {"succeeded": True, "result": {"addOnCommandResponse": answer}}


def test_switching_to_a_filter_by_name_sends_its_guid_and_returns_it() -> None:
    """D162: the switch is what puts the model into a scenario."""
    transport = SettingTransport()
    found = set_renovation_filter(ArchicadConnection(transport), "04 planned status")
    assert found == RenovationFilter(guid=PLANNED, name="04 Planned Status")
    assert transport.set == [{"guid": PLANNED}]


def test_an_add_on_that_cannot_switch_says_so() -> None:
    with pytest.raises(ArchicadError, match="Install the current build"):
        set_renovation_filter(ArchicadConnection(SettingTransport(has_set=False)), TOD)


def test_the_command_lists_the_filters_marks_the_one_shown_and_switches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typer.testing import CliRunner

    from sun_study import cli

    transport = SettingTransport()
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: ArchicadConnection(transport))

    result = CliRunner().invoke(cli.app, ["renovation-filters"])
    assert result.exit_code == 0, result.output
    assert "2 renovation filters" in result.output
    assert "SCENARIO 2_COMPLIANT TOD" in result.output
    lines = [line for line in result.output.splitlines() if "shown now" in line]
    assert len(lines) == 1 and "SCENARIO 2_COMPLIANT TOD" in lines[0]
    assert transport.set == []

    result = CliRunner().invoke(cli.app, ["renovation-filters", "--set", "04 Planned Status"])
    assert result.exit_code == 0, result.output
    assert transport.set == [{"guid": PLANNED}]
    assert "switched the project to '04 Planned Status'" in result.output
    lines = [line for line in result.output.splitlines() if "shown now" in line]
    assert len(lines) == 1 and "04 Planned Status" in lines[0]

    result = CliRunner().invoke(cli.app, ["renovation-filters", "--set", "SCENARIO 9"])
    assert result.exit_code == 2
    assert "04 Planned Status; SCENARIO 2_COMPLIANT TOD" in result.output
