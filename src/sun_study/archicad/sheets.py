"""Straightening and tiling the Drawings after they are on the sheet.

Why this is a second pass
------------------------
Neither the angle nor the true size of a Drawing can be chosen when it is
created. ``CreateDrawings`` takes a position, a name and a magnification, and
nothing else: the angle comes from the Drawing tool's own default -- on this
project 279.9 degrees, which is the project's north -- and the size follows
from the view's scale and extent, so it is only knowable once the drawing
exists.

Both are fixable afterwards, with ``RotateElements`` and ``MoveElements``. The
obstacle was reading the drawing back at all: a layout created in the same
session answers ``GetDetailsOfElements`` with a per-element error, which is
what made the first attempt at this impossible, and what took Archicad down
with it.

**Saving the project is what materialises the layout.** After ``SaveProject``
the same read answers normally. So the order is: create, save, measure,
straighten, measure again, move. Twice-measured because rotating changes the
bounding box, and the second measurement is the one the tiling needs.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from sun_study.archicad.connection import ArchicadConnection, ArchicadError, activate
from sun_study.archicad.draw import create_texts
from sun_study.archicad.layout import LayoutSheet, Tiling, tile_positions
from sun_study.archicad.paper import PaperFrame, StudyElements, onto_paper

__all__ = [
    "TITLE_BLOCK_MM",
    "DrawingPlacement",
    "PaperReport",
    "SheetReport",
    "TableRow",
    "draw_statistics",
    "draw_table",
    "enter_layout",
    "lay_study_on_sheet",
    "legend_place",
    "measure_drawings",
    "straighten_and_tile",
]


@dataclass(frozen=True)
class DrawingPlacement:
    """One Drawing as it currently sits on a sheet, in metres."""

    element: dict[str, Any]
    angle_rad: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    ratio: float = 1.0
    """The Drawing's magnification, which is how big it is *on the page*.

    Its scale cannot be changed from here -- ``SetDetailsOfElements`` accepts
    a ``drawingScale``, answers ``{"success": true}`` and leaves it exactly as
    it was, which is D43 again. ``ratio`` does change, and is therefore the
    only handle there is on a drawing that will not fit its sheet.
    """

    name: str = ""
    """The Drawing's own name, as the Layout Book shows it."""

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.x_min + self.x_max) / 2.0, (self.y_min + self.y_max) / 2.0)


def _frame_angle(details: Mapping[str, Any]) -> float:
    """How far the Drawing's frame is off upright, in radians, within +-45 deg.

    Taken from the ``clipPolygon`` -- the frame's own corners -- and **not**
    from the ``angle`` field beside it, which is the whole point. ``angle`` is
    writable and answers with whatever was last written to it: a run that set
    it to zero read zero back and reported six drawings straightened, while
    every frame on the sheet still stood at 279.9 degrees. The corners are the
    only account of where the drawing actually is.

    Reduced modulo a quarter turn, because a rectangle at 90 degrees is
    upright, and then signed so that rotating by its negative is the shorter
    way round.
    """
    polygon = details.get("clipPolygon")
    if not isinstance(polygon, list) or len(polygon) < 3:
        return float(details.get("angle", 0.0) or 0.0)
    try:
        first, second = polygon[0], polygon[1]
        edge = math.atan2(
            float(second["y"]) - float(first["y"]), float(second["x"]) - float(first["x"])
        )
    except (KeyError, TypeError, ValueError):
        return float(details.get("angle", 0.0) or 0.0)
    quarter = math.pi / 2.0
    off = edge % quarter
    return off - quarter if off > quarter / 2.0 else off


def _turn_by(angle_rad: float, origin: tuple[float, float]) -> dict[str, Any]:
    """A rotation of ``angle_rad`` about ``origin``, as two points on its arc.

    ``RotateElements`` takes no angle. It takes a centre and the two ends of an
    arc, and derives the angle from them -- so the caller has to build the arc.
    A unit radius keeps the numbers well away from the precision at which two
    points would read as the same one.

    Worth the arithmetic: this is what actually turns a Drawing. Writing
    ``angle`` through ``SetDetailsOfElements`` is shorter, reports success and
    reads back, and leaves the drawing exactly where it was.
    """
    x, y = origin
    return {
        "origin": {"x": x, "y": y},
        "beginPoint": {"x": x + 1.0, "y": y},
        "endPoint": {"x": x + math.cos(angle_rad), "y": y + math.sin(angle_rad)},
    }


def measure_drawings(
    connection: ArchicadConnection, layout_database_id: str
) -> list[DrawingPlacement]:
    """Every Drawing on one layout, with its angle and bounds.

    Requires the project to have been saved since the layout was made: an
    unsaved layout answers with a per-element error instead.
    """
    activate(connection, layout_database_id, "Layout")
    found = connection.run_tapir("GetElementsByType", {"elementType": "Drawing"})
    elements = found.get("elements") if isinstance(found, dict) else None
    if not isinstance(elements, list) or not elements:
        return []

    response = connection.run_tapir("GetDetailsOfElements", {"elements": elements})
    rows = response.get("detailsOfElements") if isinstance(response, dict) else None
    if not isinstance(rows, list) or len(rows) != len(elements):
        raise ArchicadError(
            "The layout would not describe its drawings. It has probably not "
            "been saved since it was created, which is what makes a layout "
            "readable at all."
        )

    placements: list[DrawingPlacement] = []
    for element, row in zip(elements, rows, strict=True):
        details = (row or {}).get("details") or {}
        bounds = details.get("bounds") or {}
        try:
            placements.append(
                DrawingPlacement(
                    element=element,
                    angle_rad=_frame_angle(details),
                    x_min=float(bounds["xMin"]),
                    y_min=float(bounds["yMin"]),
                    x_max=float(bounds["xMax"]),
                    y_max=float(bounds["yMax"]),
                    ratio=float(details.get("ratio", 1.0)) or 1.0,
                    name=str(details.get("customName", "") or ""),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return placements


@dataclass(frozen=True)
class SheetReport:
    """What the second pass over a sheet did."""

    straightened: int
    moved: int
    shrunk_to: float = 1.0
    """The magnification the drawings had to be reduced to, 1.0 for none.

    Always reported. A drawing brought down to 47% of the size its scale asks
    for is no longer at that scale, and a run that did that quietly would be
    handing somebody a sheet whose title block lies about it.
    """

    def __iter__(self) -> Iterator[int]:
        """``turned, moved = straighten_and_tile(...)`` still works."""
        return iter((self.straightened, self.moved))

    def describe(self) -> str:
        said = f"straightened {self.straightened}, tiled {self.moved}"
        if self.shrunk_to < 1.0:
            per_cent = f"{self.shrunk_to * 100:.1f}".rstrip("0").rstrip(".")
            said += (
                f", and set every drawing to {per_cent}% to fit the page -- so they "
                f"are no longer at the scale the run asked for"
            )
        if self.shrunk_to < 0.25:
            said += (
                ". A quarter or less is not a page too small, it is the wrong "
                "scale for this sheet: raise the scale or use a bigger master"
            )
        return said


def straighten_and_tile(
    connection: ArchicadConnection,
    layout_database_id: str,
    sheet: LayoutSheet,
    *,
    gap_m: float = 0.012,
    tolerance_rad: float = 1e-4,
    cells: int | None = None,
    leave: Collection[str] = (),
) -> SheetReport:
    """Turn every Drawing upright, size it to the page, and lay them out.

    ``cells`` fits and tiles the sheet as one carrying that many drawings,
    when it is more than are on it, so a short second sheet keeps the
    first sheet's grid and size.

    ``leave`` names drawings that are not plans and are not tiled -- a
    schedule placed beside them, which keeps its own size and its corner.
    Shrunk with the plans to fit the page, its text would no longer be the
    size the schedule was set to.

    The sheet is described in millimetres and the drawings live in metres,
    which is the unit everything here works in.

    A Drawing's angle is one of the few things ``SetDetailsOfElements`` will
    change directly, through ``DrawingSettings``, so the angle is *set* rather
    than rotated away. ``RotateElements`` did work and had to be handed a
    centre and two points on an arc to imply the angle, which is a lot of
    arithmetic to express "north up".

    Fitting is the other half, and it is not optional: a drawing made from a
    3D view came out 1,429 mm wide on an 841 mm page, and no arrangement of
    one drawing makes that fit. The shrink is applied to **every** drawing on
    the sheet by the same factor, even the ones that would have fitted. Three
    diagrams of the same building at three times of day are read against each
    other, and two of them at one size beside a third at another is a picture
    of nothing.
    """
    placements = [
        p for p in measure_drawings(connection, layout_database_id) if p.name not in leave
    ]
    if not placements:
        return SheetReport(0, 0)

    crooked = [p for p in placements if abs(p.angle_rad) > tolerance_rad]
    if crooked:
        connection.run_tapir(
            "RotateElements",
            {
                "elementsWithRotations": [
                    {
                        "elementId": placement.element["elementId"],
                        "rotation": _turn_by(-placement.angle_rad, placement.centre),
                    }
                    for placement in crooked
                ]
            },
        )
        # Rotating moves the bounding box, and the tiling needs the new one.
        # Also the only proof it happened: the response says nothing.
        placements = [
            p for p in measure_drawings(connection, layout_database_id) if p.name not in leave
        ]
        still = [p for p in placements if abs(p.angle_rad) > tolerance_rad]
        if still:
            raise ArchicadError(
                f"{len(still)} of {len(crooked)} drawings would not straighten. "
                f"They are on a locked layout, or the layout has not been saved "
                f"since it was made."
            )

    magnification, tiling = _fit_to_page(
        connection, placements, sheet, gap_m, max(cells or 0, len(placements))
    )

    # The arrangement comes from the same tiling that chose the magnification,
    # and the sheet is deliberately not re-measured to check it. A drawing's
    # bounds do not follow its magnification until Archicad regenerates it, so
    # a read here would answer with the size from before the change and put
    # the grid back where it was.
    moves = _moves_onto(placements, tiling.positions[: len(placements)])
    if moves:
        connection.run_tapir("MoveElements", {"elementsWithMoveVectors": moves})
    return SheetReport(len(crooked), len(moves), magnification or 1.0)


def _fit_to_page(
    connection: ArchicadConnection,
    placements: Sequence[DrawingPlacement],
    sheet: LayoutSheet,
    gap_m: float,
    count: int | None = None,
) -> tuple[float | None, Tiling]:
    """Set every Drawing to the one magnification that fits the sheet.

    Returns what they were set to -- ``None`` when nothing was changed -- and
    the arrangement that decision was made from, which is the arrangement the
    drawings then have to be moved into. The two come back together because
    they are one answer: the magnification is what makes the grid fit, and the
    grid is what the magnification was chosen for.

    **A Drawing's bounds do not follow its magnification**, and everything
    here is shaped by that. Setting a drawing to 46.9% stores 46.9%, and it
    reads back, while the bounds go on reporting the size it had before --
    until Archicad regenerates the drawing, which happens when somebody opens
    the layout. Changing it and reading it back therefore proves nothing, and
    a re-read after the change is worse than none: it is D40 with the answer
    arriving from a database that has not caught up.

    What *is* dependable is that a drawing's bounds and its magnification
    agree until this function touches them, because Archicad drew them
    together. So the size at full magnification is bounds over magnification,
    and the answer is written once, from that, without reading back.

    Three states, one rule each. At full size, fit it. Above full size it is
    the old fault -- the scale denominator written into the magnification
    field, eighteen storey plans standing at 200x and 187 metres across -- and
    bounds over magnification is exactly the repair. Below full size it has
    been fitted already, and is left alone: nothing readable distinguishes a
    drawing that has regenerated from one that has not, and shrinking on that
    evidence went 46.9%, 22.1%, and on down by half every run.

    The cost of the last rule is that a sheet does not re-fit itself when the
    building outgrows it. The run says what magnification it left, which is
    the handle: delete the drawings and let the next run place them fresh.

    Uniform across the sheet, including drawings that would have fitted on
    their own. Three diagrams of one building at three times of day are read
    against each other, and two at one size beside a third at another is a
    picture of nothing.
    """
    if any(placement.ratio < 1.0 for placement in placements):
        # Already fitted. The bounds may or may not have caught up with it, so
        # they are used as they are: whichever they report, they are the same
        # multiple of the truth for every drawing, and a grid is a set of
        # proportions.
        return None, tile_positions(
            sheet,
            count or len(placements),
            (max(p.width for p in placements), max(p.height for p in placements)),
            gap_m,
        )

    tiling = tile_positions(
        sheet,
        count or len(placements),
        (
            max(p.width / p.ratio for p in placements),
            max(p.height / p.ratio for p in placements),
        ),
        gap_m,
    )
    if tiling.fits and all(placement.ratio == 1.0 for placement in placements):
        return None, tiling

    connection.run_tapir(
        "SetDetailsOfElements",
        {
            "elementsWithDetails": [
                {
                    "elementId": placement.element["elementId"],
                    "details": {"typeSpecificDetails": {"ratio": tiling.fit}},
                }
                for placement in placements
            ]
        },
    )
    return tiling.fit, tiling


def _moves_onto(
    placements: Sequence[DrawingPlacement], positions: Sequence[tuple[float, float]]
) -> list[dict[str, Any]]:
    """Move vectors taking each drawing from where it is to where it belongs.

    The positions are ``tile_positions``', shared with the placement pass, so
    that where a drawing is first put and where it is later moved cannot
    disagree.
    """
    if not placements:
        return []
    moves: list[dict[str, Any]] = []
    for placement, (target_x, target_y) in zip(placements, positions, strict=True):
        centre_x, centre_y = placement.centre
        moves.append(
            {
                "elementId": placement.element["elementId"],
                "moveVector": {
                    "x": target_x - centre_x,
                    "y": target_y - centre_y,
                    "z": 0.0,
                },
            }
        )
    return moves


@dataclass(frozen=True)
class TableRow:
    """One line of the figures table: a swatch, a label and its numbers."""

    label: str
    area_m2: float
    share: float
    fill_pen: int | None = None
    background_pen: int = 19
    heading: bool = False
    """A line that names the drawing the rows under it belong to, on a
    sheet carrying several drawings' figures: the label alone, no numbers."""


#: Archicad takes a Text's height in the database's own length unit, which on
#: a layout is metres of paper. Every other number on a sheet here is already
#: in those metres -- ``step_m``, ``swatch_m``, ``left_m`` -- and the height
#: was the one left in millimetres, so a 2.2 mm line was created 2.2 *metres*
#: tall on an 841 mm sheet. What that looks like is one letter filling the
#: page and the rest of the string off the edge of it, which is exactly how it
#: was reported.
MM = 0.001


def draw_statistics(
    connection: ArchicadConnection,
    layout_database_id: str,
    *,
    title: str,
    rows: Sequence[tuple[str, str]],
    height_mm: float = 2.6,
    step_m: float = 0.011,
    left_m: float = 0.030,
    top_m: float = 0.240,
) -> int:
    """Write a sheet of label-and-number lines. Returns the lines written.

    A sheet of its own rather than a corner of a drawing, because the numbers
    are what somebody quotes and a figure read off a plan at 1:300 beside a
    coloured patch is a figure nobody can check. Here they are typed out, one
    per line, with the settings that produced them beside the results they
    produced -- a page that answers "what does this study say" without anybody
    having to open the model.

    An empty label draws nothing but still steps the cursor, so a caller can
    group lines without this needing to know what the groups mean.

    The layout is cleared first. Everything on a study sheet is this tool's
    own, and a rerun that appended would print the new numbers over the old.
    """
    activate(connection, layout_database_id, "Layout")
    for kind in ("Text", "Hatch"):
        found = connection.run_tapir("GetElementsByType", {"elementType": kind})
        elements = found.get("elements") if isinstance(found, dict) else None
        if isinstance(elements, list) and elements:
            connection.run_tapir("DeleteElements", {"elements": elements})

    texts: list[dict[str, Any]] = [
        {
            "coordinate": {"x": left_m, "y": top_m + step_m * 2, "z": 0.0},
            "text": title,
            "height": height_mm * 1.5 * MM,
            "justification": "Left",
        }
    ]
    written = 0
    for index, (label, value) in enumerate(rows):
        if not label and not value:
            continue
        texts.append(
            {
                "coordinate": {"x": left_m, "y": top_m - index * step_m, "z": 0.0},
                # Two columns from one string: a Text is placed at a point and
                # carries no tab stops, so a second column means a second
                # element and twice the clutter on the layer.
                "text": f"{label:<34}{value}",
                "height": height_mm * MM,
                "justification": "Left",
            }
        )
        written += 1

    create_texts(connection, texts, heights_in_metres=True)
    return written


def draw_table(
    connection: ArchicadConnection,
    layout_database_id: str,
    *,
    title: str,
    rows: Sequence[TableRow],
    height_mm: float = 2.2,
    swatch_m: float = 0.006,
    step_m: float = 0.009,
    beside: bool = False,
    placements: Sequence[DrawingPlacement] | None = None,
    at: tuple[float, float] | None = None,
) -> int:
    """Put the figures table on the sheet itself. Returns the rows drawn.

    ``placements`` is where the drawings are, from a caller that put them
    there -- ``lay_study_on_sheet``. Given it, the layout is taken to be the
    current database already and is neither cleared nor measured: measuring
    needs a saved project, which that route exists to do without, and
    clearing would delete the study it has just drawn on the sheet.

    On the **layout**, not on the plan. Drawn into the model it has to be
    repeated on every storey, so a six-storey study carries six copies of one
    table and each one sits somewhere in the building; on the sheet there is
    one, beside the drawings, where a reader looks for it.

    This works only because the project has been saved since the layout was
    made -- an unsaved layout cannot be activated, and creation follows the
    current database. Everything is in metres, as on any layout.
    """
    if not rows:
        return 0

    if placements is None:
        activate(connection, layout_database_id, "Layout")
        # The sheet is regenerated with its layout, so anything here is this
        # tool's own from an earlier pass over the same sheet.
        for kind in ("Text", "Hatch"):
            found = connection.run_tapir("GetElementsByType", {"elementType": kind})
            elements = found.get("elements") if isinstance(found, dict) else None
            if isinstance(elements, list) and elements:
                connection.run_tapir("DeleteElements", {"elements": elements})
        placements = measure_drawings(connection, layout_database_id)

    if at is not None:
        # One place on every sheet, chosen by the caller from the page and not
        # from the drawings: a legend that follows the plan is somewhere else
        # on each sheet of a set, and a reader has to find it each time.
        left, top = at
    elif not placements:
        left, top = 0.02, 0.20
    elif beside:
        # To the right of the drawing, starting level with its top edge. A
        # tiled plan uses a fraction of an A1 and leaves the whole right of
        # the sheet empty, while the strip under it is where a title block
        # and a scale bar end up -- so the figures went in the one place on
        # the page somebody was not looking.
        left = max(p.x_max for p in placements) + step_m * 2
        top = max(p.y_max for p in placements)
    else:
        left = min(p.x_min for p in placements)
        top = min(p.y_min for p in placements) - step_m * 2

    fills: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = [
        {
            "coordinate": {"x": left, "y": top + step_m * 1.6, "z": 0.0},
            "text": title,
            "height": height_mm * 1.3 * MM,
            "justification": "Left",
        }
    ]
    for index, row in enumerate(rows):
        bottom = top - index * step_m
        if row.heading:
            texts.append(
                {
                    "coordinate": {"x": left, "y": bottom, "z": 0.0},
                    "text": row.label,
                    "height": height_mm * 1.15 * MM,
                    "justification": "Left",
                }
            )
            continue
        if row.fill_pen is not None:
            fills.append(
                {
                    "coordinates": [
                        {"x": left, "y": bottom},
                        {"x": left + swatch_m, "y": bottom},
                        {"x": left + swatch_m, "y": bottom + swatch_m},
                        {"x": left, "y": bottom + swatch_m},
                    ],
                    "fillPenIndex": row.fill_pen,
                    "fillBackgroundPenIndex": row.background_pen,
                    "contourPenIndex": row.fill_pen,
                    "showArea": False,
                }
            )
        texts.append(
            {
                "coordinate": {"x": left + swatch_m * 1.6, "y": bottom, "z": 0.0},
                "text": f"{row.label:<10} {row.area_m2:9.1f} m²   {row.share:6.1%}",
                "height": height_mm * MM,
                "justification": "Left",
            }
        )

    if fills:
        connection.run_tapir("CreateHatches", {"hatchesData": fills})
    create_texts(connection, texts, heights_in_metres=True)
    return len(rows)


# -- the study drawn on the sheet, over the plan ------------------------------

#: The strip down the right of the practice's masters that the title block
#: occupies. Archicad reports a layout's margins and nothing about its master,
#: so drawings tiled to the page edge run under the title block -- measured at
#: about 100 mm on the ``DA B1 - VERTICAL`` masters, and the same figure
#: ``sun_eyes`` keeps clear for the same reason.
TITLE_BLOCK_MM = 100.0

#: The column kept for the legend, down the right of the sheet beside the
#: title block, and how far below the top edge it starts. The plans are tiled
#: in what is left, so the legend never sits on one.
LEGEND_COLUMN_MM = 95.0
LEGEND_DROP_MM = 45.0


def legend_place(sheet: LayoutSheet, title_block_mm: float = TITLE_BLOCK_MM) -> tuple[float, float]:
    """Where the legend's top-left corner goes, in metres up from bottom-left.

    Top right, in the column beside the title block: the same spot on every
    sheet of every study, which is the point of choosing it from the page.
    """
    left, top, width, _ = sheet.usable
    x = left + width - title_block_mm - LEGEND_COLUMN_MM
    y = sheet.height_mm - top - LEGEND_DROP_MM
    return (max(x, left) / 1000.0, y / 1000.0)


@dataclass(frozen=True)
class PaperReport:
    """What went onto one sheet, and how."""

    drawings: int
    fills: int
    polylines: int
    texts: int
    missing: tuple[str, ...] = ()
    """Drawings the layout should hold by name and does not."""
    ratio: float = 1.0
    ratio_refused: bool = False

    def describe(self) -> str:
        line = (
            f"{self.drawings} drawing(s) placed by their origin, and on the sheet over them: "
            f"{self.fills} fills, {self.polylines} outlines, {self.texts} texts"
        )
        if self.ratio < 1.0:
            line += f"; shrunk to {self.ratio:.0%} to fit"
        if self.ratio_refused:
            line += " -- Archicad refused the shrink, so the frames crop the plans instead"
        if self.missing:
            line += f"; not found on the layout: {', '.join(self.missing)}"
        return line


def enter_layout(connection: ArchicadConnection, layout_database_id: str) -> None:
    """Make a layout the current database, through the add-on.

    Not ``activate``: Tapir's ``ChangeWindow`` reaches a layout only once the
    project has been saved since the layout was made, and the add-on's
    ``SetCurrentDatabase`` enters one made a second ago -- and reads back where
    it ended up before saying so (docs/addon.md).
    """
    answer = connection.run_loriini(
        "SetCurrentDatabase",
        {"databaseId": {"guid": layout_database_id}, "windowType": "Layout"},
    )
    if not isinstance(answer, dict) or not answer.get("success"):
        raise ArchicadError(f"the layout could not be entered to draw on: {answer!r}")


def lay_study_on_sheet(
    connection: ArchicadConnection,
    layout_database_id: str,
    sheet: LayoutSheet,
    *,
    drawings: Sequence[tuple[str, StudyElements]],
    zoom: tuple[float, float, float, float],
    scale: float,
    cells: int | None = None,
    gap_m: float = 0.012,
    title_block_mm: float = TITLE_BLOCK_MM,
) -> tuple[PaperReport, list[DrawingPlacement]]:
    """Tile the plans on the sheet and draw each one's study over it.

    ``drawings`` names each placed Drawing, in reading order, with the
    elements that belong over it -- still in project metres, exactly as the
    floor-plan route would have created them. ``zoom`` is the project-space
    box every plan shows and ``scale`` its denominator.

    **Nothing here reads a drawing's size back, which is what frees the sheet
    from the save.** The old route placed the drawings, saved the project so
    they could be measured, and then straightened and tiled what it measured;
    a project that refused the save kept its drawings wherever they fell, off
    the page as often as on it. Here the size is *chosen*: every Drawing is
    pinned by its own origin -- the project origin -- with a clip frame that
    is the zoom box at scale, so where the model lands on the paper is known
    by construction and the study is laid over it with the same arithmetic.

    Returns the report and where each drawing now is, which ``draw_table``
    takes in place of measuring.
    """
    answer = connection.run_loriini(
        "GetDrawings", {"layoutDatabaseId": {"guid": layout_database_id}}
    )
    rows = answer.get("drawings") if isinstance(answer, dict) else None
    if not isinstance(rows, list):
        raise ArchicadError(f"GetDrawings answered {answer!r}")
    by_name = {str(row.get("name", "")): row for row in rows if isinstance(row, dict)}

    x_min, y_min, x_max, y_max = zoom
    tile = ((x_max - x_min) / scale, (y_max - y_min) / scale)
    room = replace(sheet, right_mm=sheet.right_mm + title_block_mm + LEGEND_COLUMN_MM)
    tiling = tile_positions(room, max(cells or 0, len(drawings)), tile, gap_m)

    ratio, refused = 1.0, False
    present = [(name, held) for name, held in drawings if name in by_name]
    missing = tuple(name for name, _ in drawings if name not in by_name)
    if not tiling.fits and present:
        try:
            connection.run_tapir(
                "SetDetailsOfElements",
                {
                    "elementsWithDetails": [
                        {
                            "elementId": {"guid": str(by_name[name]["guid"])},
                            "details": {"typeSpecificDetails": {"ratio": tiling.fit}},
                        }
                        for name, _ in present
                    ]
                },
            )
            ratio = tiling.fit
        except ArchicadError:
            refused = True

    frames: list[PaperFrame] = []
    arranged: list[dict[str, Any]] = []
    placements: list[DrawingPlacement] = []
    for (name, _), centre in zip(present, tiling.positions, strict=False):
        k = ratio / scale
        width, height = (x_max - x_min) * k, (y_max - y_min) * k
        left, bottom = centre[0] - width / 2.0, centre[1] - height / 2.0
        frame = PaperFrame(origin=(left - x_min * k, bottom - y_min * k), scale=scale, ratio=ratio)
        clip = {"xMin": left, "yMin": bottom, "xMax": left + width, "yMax": bottom + height}
        if refused:
            # Unshrunk, the plan is bigger than its cell: keep the cell and
            # let the frame crop, centred, rather than run over its neighbour.
            shown = (tile[0] * tiling.fit, tile[1] * tiling.fit)
            clip = {
                "xMin": centre[0] - shown[0] / 2.0,
                "yMin": centre[1] - shown[1] / 2.0,
                "xMax": centre[0] + shown[0] / 2.0,
                "yMax": centre[1] + shown[1] / 2.0,
            }
        frames.append(frame)
        arranged.append(
            {
                "guid": str(by_name[name]["guid"]),
                "x": frame.origin[0],
                "y": frame.origin[1],
                "frame": clip,
            }
        )
        placements.append(
            DrawingPlacement(
                element={"elementId": {"guid": str(by_name[name]["guid"])}},
                angle_rad=0.0,
                x_min=clip["xMin"],
                y_min=clip["yMin"],
                x_max=clip["xMax"],
                y_max=clip["yMax"],
                ratio=ratio,
            )
        )

    if arranged:
        placed = connection.run_loriini(
            "ArrangeDrawings",
            {
                "layoutDatabaseId": {"guid": layout_database_id},
                "drawings": arranged,
                "anchor": "origin",
                "frameRelativeToOrigin": False,
                "autoUpdate": True,
            },
        )
        if not isinstance(placed, dict) or not placed.get("success") or placed.get("failures"):
            raise ArchicadError(f"ArrangeDrawings answered {placed!r}")

    # The drawers' own creators, so a fill with no contour still goes through
    # the one command that can draw it. Imported here because that module
    # builds on the drawing ones and this one must not depend on it at import.
    from sun_study.archicad.penetration import _create, _create_fills

    enter_layout(connection, layout_database_id)
    fills = polylines = texts = 0
    for (_, held), frame in zip(present, frames, strict=True):
        # A cell a quarter of a metre across is under a millimetre at 1:300,
        # and one that loses nodes to `paper._ring` may have no area left.
        on_paper = [
            fill
            for fill in (onto_paper(fill, frame) for fill in held.fills)
            if len(fill.get("coordinates") or ()) >= 3
        ]
        fills += len(_create_fills(connection, on_paper, outline=held.outline))
        lines = [
            line
            for line in (onto_paper(line, frame) for line in held.polylines)
            if len(line.get("coordinates") or ()) >= 2
        ]
        polylines += len(_create(connection, "CreatePolylines", "polylinesData", lines))
        words = [onto_paper(one, frame) for one in held.texts]
        made, _ = create_texts(connection, words)
        texts += len(made)

    return (
        PaperReport(len(present), fills, polylines, texts, missing, ratio, refused),
        placements,
    )
