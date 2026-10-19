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
