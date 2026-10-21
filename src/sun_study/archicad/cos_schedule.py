"""Communal open space by the hour, as a schedule Archicad keeps live.

The office's COS sheet carries a schedule rather than a drawn table: ``Areas
COS solar``, which lists the sunlit fills a row per hour -- the hour's layer,
the time, the area, the share. Archicad sums the area itself, from the fills,
so it is always the drawing's own. The time and the share it cannot work out,
and until now somebody typed them into the schedule's cells, seven rows per
storey per run.

This writes them, and puts the schedule on the sheet in place of the table.

What the API cannot do
----------------------
Make the schedule. No version of Archicad's API up to 30 has a function for a
schedule scheme -- the Interactive Schedule is Graphisoft's own add-on and its
schemes are reached only through its dialog -- so the scheme is the
project's. The office template carries ``Areas COS solar``; a project made
from something else imports it once, through Scheme Settings > Import.

Why IFC properties
------------------
A custom property reaches an element only through its classification, and
Archicad will not classify a Fill (``docs/archicad.md``). On Gordon, 15,373
fills, every one unclassified, and not one of the project's 185 custom
properties available to any of them. What a fill does keep is an IFC
property, which is where a value typed into a schedule cell lands, and the
add-on can write one on Archicad 26 to 28. Archicad 29 and 30 have no call
that stores one; there the run says so and the drawn table goes on the sheet
as before.

Every fill of an hour carries the same two values, the hour's own: ``9 AM``
and the share of the communal open space in sun at nine. That is what lets a
schedule merge them into one row and sum their area -- a value that differed
from fill to fill would give a row per patch.

Never fatal
-----------
As with the Element IDs: a project that will not take the values still has
its fills and its sheets, and the report says how many values landed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError, CommandFailedError
from sun_study.archicad.layout import NavigatorItem, _walk
from sun_study.archicad.penetration import MeasuredFill
from sun_study.archicad.sheets import LEGEND_COLUMN_MM, TITLE_BLOCK_MM

__all__ = [
    "KEEP_CLEAR_MM",
    "PERCENTAGE",
    "PROPERTY_SET",
    "TIME",
    "HourFills",
    "ScheduleView",
    "TagReport",
    "clock_words",
    "find_schedule",
    "place_schedule",
    "schedule_names",
    "share_words",
    "tag_hours",
]

#: The IFC property set the two values are written into, and their names --
#: the column headings of the office's schedule.
PROPERTY_SET = naming.GROUP_WORD
TIME = "Time"
PERCENTAGE = "Percentage"

#: Taken off the right of a sheet for the schedule: the column beside the
#: title block, where the paper route puts its table. The plans are dealt
#: across what is left, so the schedule never lands on one of them.
KEEP_CLEAR_MM = TITLE_BLOCK_MM + LEGEND_COLUMN_MM

#: Values per request, as for the Element IDs.
BATCH = 500


def clock_words(when: dt.datetime | dt.time) -> str:
    """``9 AM``, ``12 PM``, ``3 PM`` -- the hour as the schedule writes it."""
    return f"{when.hour % 12 or 12} {'AM' if when.hour < 12 else 'PM'}"


def share_words(share: float) -> str:
    """``68.8%``: the share as the schedule writes it, from 0..1."""
    return f"{share * 100:.1f}%"


@dataclass(frozen=True)
class HourFills:
    """One hour's sunlit fills, and the share of the space in sun at it."""

    time: str
    share: float
    fills: tuple[MeasuredFill, ...]


@dataclass(frozen=True)
class TagReport:
    """How many of the values landed, and why any did not."""

    written: int
    attempted: int
    problem: str = ""

    @property
    def complete(self) -> bool:
        return self.written == self.attempted and not self.problem

    def describe(self) -> str:
        if self.complete:
            return (
                f"  wrote {TIME} and {PERCENTAGE} onto {self.written // 2} sunlit fills, "
                f"in the IFC property set {PROPERTY_SET!r}"
            )
        return (
            f"  WARNING: {self.written} of {self.attempted} {TIME}/{PERCENTAGE} values landed"
            + (f" -- {self.problem}" if self.problem else "")
            + ". The fills are drawn; the schedule's time and share columns are not filled."
        )


def tag_hours(connection: ArchicadConnection, hours: Sequence[HourFills]) -> TagReport:
    """Write each hour's time and share onto its fills. Never raises."""
    values: list[dict[str, Any]] = []
    for hour in hours:
        for fill in hour.fills:
            guid = (fill.element.get("elementId") or {}).get("guid")
            if not guid:
                continue
            values.append(
                {"guid": guid, "propertySet": PROPERTY_SET, "name": TIME, "text": hour.time}
            )
            values.append(
                {
                    "guid": guid,
                    "propertySet": PROPERTY_SET,
                    "name": PERCENTAGE,
                    "text": share_words(hour.share),
                }
            )
    if not values:
        return TagReport(0, 0)

    written = 0
    problems: list[str] = []
    for start in range(0, len(values), BATCH):
        chunk = values[start : start + BATCH]
        try:
            answer = connection.run_loriini("SetIfcProperties", {"values": chunk})
        except ArchicadError as refused:
            # One refusal of the command is every batch's: an add-on from
            # before it, or an Archicad that cannot store the values at all.
            return TagReport(written, len(values), _why(refused))
        results = answer.get("results") if isinstance(answer, dict) else None
        if not isinstance(results, list) or len(results) != len(chunk):
            problems.append("SetIfcProperties answered with a list of a different length")
            continue
        for result in results:
            if isinstance(result, dict) and result.get("success"):
                written += 1
            elif isinstance(result, dict):
                error = result.get("error") or {}
                problems.append(f"{error.get('message', 'refused')} (code {error.get('code')})")
    return TagReport(written, len(values), "; ".join(sorted(set(problems))[:3]))


def _why(refused: ArchicadError) -> str:
    text = str(refused)
    if "registered" in text or "not found" in text.lower():
        return (
            "the Loriini add-on installed is older than this Loriini and cannot write "
            "them; install the current one and restart Archicad"
        )
    return text


@dataclass(frozen=True)
class ScheduleView:
    """A schedule of the project's, and the View Map item that places it."""

    name: str
    view_id: str


def _schedules(connection: ArchicadConnection, map_id: str) -> list[NavigatorItem]:
    response = connection.run_tapir("GetNavigatorItemTree", {"navigatorMapId": map_id})
    tree = response.get("navigatorItemTree") if isinstance(response, dict) else None
    root = tree.get("rootItem", tree) if isinstance(tree, dict) else None
    if not isinstance(root, dict):
        return []
    return [item for item in _walk(root) if item.kind == "ScheduleItem"]


def schedule_names(connection: ArchicadConnection) -> tuple[str, ...]:
    """The element schedules in the Project Map, by name, for offering."""
    return tuple(sorted({item.name for item in _schedules(connection, "ProjectMap")} - {""}))


def find_schedule(connection: ArchicadConnection, name: str) -> ScheduleView | None:
    """The schedule called ``name``, ready to place; ``None`` if the project has none.

    A Drawing is placed from a View, so the View Map's own view of it is used
    when there is one -- the office template keeps one for every schedule --
    and the Project Map's is cloned into the View Map when there is not.
    Matched on the name as typed, ignoring case.
    """
    wanted = name.strip().casefold()
    if not wanted:
        return None
    for item in _schedules(connection, "PublicViewMap"):
        if item.name.strip().casefold() == wanted:
            return ScheduleView(item.name, item.identifier)
    for item in _schedules(connection, "ProjectMap"):
        if item.name.strip().casefold() == wanted:
            response = connection.run_tapir(
                "CloneProjectMapItemToViewMap",
                {"viewsData": [{"navigatorItemId": {"guid": item.identifier}}]},
            )
            made = response.get("navigatorItems") if isinstance(response, dict) else None
            first = made[0] if isinstance(made, list) and made else None
            view = (
                (first.get("navigatorItemId") or {}).get("guid")
                if isinstance(first, dict)
                else None
            )
            if not view:
                raise ArchicadError(
                    f"the schedule {item.name!r} would not go into the View Map, "
                    f"which is where a sheet places it from: {response!r}"
                )
            return ScheduleView(item.name, str(view))
    return None


def place_schedule(
    connection: ArchicadConnection,
    layout_database_id: str,
    schedule: ScheduleView,
    at: tuple[float, float],
) -> bool:
    """Put the schedule on a sheet by its top-left corner. False if already there.

    By the corner, not the middle: a schedule's size is not known until
    Archicad draws it, and it changes whenever a row does, so placing its
    middle would put its top edge somewhere new on every sheet. The corner
    stays where it was put and the schedule grows down and to the right.

    Raises ``ArchicadError`` when the drawing is refused, so the caller can put
    the table on the sheet instead.
    """
    answer = connection.run_loriini(
        "GetDrawings", {"layoutDatabaseId": {"guid": layout_database_id}}
    )
    rows = answer.get("drawings") if isinstance(answer, dict) else None
    if isinstance(rows, list) and any(
        isinstance(row, dict) and row.get("name") == schedule.name for row in rows
    ):
        return False
    x, y = at
    try:
        response = connection.run_tapir(
            "CreateDrawings",
            {
                "drawingsData": [
                    {
                        "navigatorItemId": {"guid": schedule.view_id},
                        "layoutDatabaseId": {"guid": layout_database_id},
                        "name": schedule.name,
                        "position": {"x": x, "y": y},
                        "scale": 1.0,
                        "angle": 0.0,
                        "anchor": "topLeft",
                    }
                ]
            },
        )
    except CommandFailedError as refused:
        if "anchor" in str(refused) or "angle" in str(refused):
            raise ArchicadError(
                "the Loriini add-on installed is older than this Loriini and cannot place "
                "a schedule by its corner; install the current one and restart Archicad"
            ) from refused
        raise
    elements = response.get("elements") if isinstance(response, dict) else None
    first = elements[0] if isinstance(elements, list) and elements else None
    if not isinstance(first, dict) or "error" in first:
        problem = (first.get("error") if isinstance(first, dict) else None) or {}
        raise ArchicadError(
            f"CreateDrawings refused the schedule {schedule.name!r}: "
            f"{problem.get('message', response)} (code {problem.get('code')})"
        )
    return True
