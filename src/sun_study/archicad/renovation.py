"""The project's renovation filters, by name.

Tapir pins a view to a renovation filter by its GUID and has no way to list
the filters or say what one is called, so a run could only take the filter
most of the project's views carry (``sun_eyes.planned_renovation_filter``).
That was enough while a filter was the planned state and nothing more. An
office that keeps its massing scenarios as renovation filters -- each massing
shown on its own filter only, chosen from the Renovation palette as
*SCENARIO 2_COMPLIANT TOD* (Crows Nest, October 2026) -- tells its scenarios
apart by the filter, and a person names a scenario by what the palette calls
it. The Loriini add-on's ``GetRenovationFilters`` lists them with their
names; this resolves a name to the GUID a view takes. Its
``SetRenovationFilter`` switches the project to one -- what the floor plan
and the 3D window show, as picking it in the palette does -- which is how a
script puts the model into a scenario (D162).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sun_study.archicad.connection import ArchicadConnection, ArchicadError, CommandFailedError

__all__ = [
    "RenovationFilter",
    "renovation_filters",
    "resolve_renovation_filter",
    "set_renovation_filter",
]

#: A GUID as Archicad writes one, with or without braces.
_GUID = re.compile(r"^\{?[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}?$")


@dataclass(frozen=True)
class RenovationFilter:
    """One filter of the Renovation palette."""

    guid: str
    name: str


def _tidy(text: str) -> str:
    return " ".join(text.split()).casefold()


def renovation_filters(connection: ArchicadConnection) -> tuple[list[RenovationFilter], str | None]:
    """Every renovation filter, in the palette's order, and the one the project
    shows now. Raises ``ArchicadError`` when the add-on is too old to say."""
    try:
        answer = connection.run_loriini("GetRenovationFilters", {})
    except CommandFailedError as error:
        if "not have the registered" in str(error):
            raise ArchicadError(
                "The installed Loriini add-on cannot list renovation filters by name. "
                "Install the current build, or give the filter's GUID instead."
            ) from error
        raise
    rows = (answer or {}).get("renovationFilters") if isinstance(answer, dict) else None
    filters = [
        RenovationFilter(guid=str(row.get("guid", "")), name=str(row.get("name", "")))
        for row in rows or []
        if isinstance(row, dict) and row.get("guid")
    ]
    current = answer.get("current") if isinstance(answer, dict) else None
    return filters, str(current) if current else None


def resolve_renovation_filter(connection: ArchicadConnection, wanted: str) -> RenovationFilter:
    """The filter ``wanted`` names: its name as the palette spells it, case and
    spacing aside, or its GUID.

    A GUID is taken as given when the add-on cannot list the filters, so a
    run that worked before the add-on could name them still does. A name
    the project does not have is refused with the names it does have, which
    is the list a person picks the right one from.
    """
    text = wanted.strip()
    is_guid = bool(_GUID.match(text))
    try:
        filters, _ = renovation_filters(connection)
    except ArchicadError:
        if is_guid:
            return RenovationFilter(guid=text.strip("{}"), name="")
        raise
    if is_guid:
        bare = text.strip("{}").casefold()
        for one in filters:
            if one.guid.strip("{}").casefold() == bare:
                return one
        return RenovationFilter(guid=text.strip("{}"), name="")
    for one in filters:
        if _tidy(one.name) == _tidy(text):
            return one
    known = "; ".join(one.name for one in filters) or "none"
    raise ArchicadError(f"No renovation filter called {wanted!r} in this project. It has: {known}.")


def set_renovation_filter(connection: ArchicadConnection, wanted: str) -> RenovationFilter:
    """Switch the project to the filter ``wanted`` names -- by name or GUID,
    as ``resolve_renovation_filter`` takes it -- and return it.

    What the floor plan and the 3D window then show is what picking the
    filter in the Renovation palette shows; a view pinned to another filter
    keeps its own. Through the add-on's ``SetRenovationFilter``; an add-on
    too old for it is said plainly.
    """
    found = resolve_renovation_filter(connection, wanted)
    try:
        connection.run_loriini("SetRenovationFilter", {"guid": found.guid})
    except CommandFailedError as error:
        if "not have the registered" in str(error):
            raise ArchicadError(
                "The installed Loriini add-on cannot switch the renovation filter. "
                "Install the current build."
            ) from error
        raise
    return found
