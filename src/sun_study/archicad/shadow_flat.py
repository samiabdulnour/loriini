"""The shadow diagram drawn flat: Archicad's shadows, read out and drawn as fills.

The stacked shadow plans (``shadow_plans``, D142) put a 3D Document per legend
row and hour on the sheet, the rows of an hour laid over one another. That is
Archicad's own shadow in the legend's colours, and it is also three or four
live documents in every cell: seven hours of four rows is twenty-eight on one
layout, each one the whole site with its sun shadows worked out again whenever
the sheet is redrawn. On a real project the sheet did not open.

So the documents are kept as what casts the shadow and taken off the sheet.
Each one is placed on a working layout, a few at a time; the add-on reads
what the drawing draws (``GetDrawingPrimitives``), and the shadow is in it as
fills in the shadow's pen -- thousands of pieces, one for every surface the
shadow falls on. The pieces of a row are merged into its shadow, each row is
cut back to the ground no row above it already shades -- the split the stack
made by the order of its drawings -- and the result is drawn as plain fills
in one worksheet, an hour beside the next. The sheet then holds a drawing of
that worksheet in each cell and, over it, one document with no shadows for
the buildings and the streets.

A row that might be built is outlined as well: its own whole shadow, cast by
a set of documents that show it without the buildings around it, dashed,
over the fills -- so the reader sees how far the proposal's shadow reaches
where it falls on ground the neighbours already shade.

Measured on a tower in Darlinghurst, 10 November 2026, Archicad 26: a
document's drawing is read in a second and a half, eight thousand pieces
become twenty to sixty polygons, and seven hours of two rows are some six
hundred fills where the stack was fourteen documents.
"""

from __future__ import annotations

import colorsys
import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from shapely import make_valid, set_precision
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError, CommandFailedError
from sun_study.archicad.draw import clear_layer, ensure_layer, pen_table
from sun_study.archicad.layout import (
    LayoutReport,
    layout_from_views,
    layout_sheet,
    one_title_per_pile,
    remove_stale_layouts,
)
from sun_study.archicad.plan_sheet import PlanWindow, draw_legend_and_outline, nearest_pen
from sun_study.archicad.series import ensure_model_database
from sun_study.archicad.shadow_plans import (
    LEGEND_TITLE,
    OVERHEAD_DEG,
    PLAN_WORD,
    SET_WORD,
    MadePlan,
    ShadowPlanSettings,
    _dealt,
    _sheet_stem,
)
from sun_study.archicad.sheeting import DEFAULT_SHEET_MODE
from sun_study.archicad.sheets import LEGEND_COLUMN_MM, TITLE_BLOCK_MM
from sun_study.archicad.site_analysis import attribute_index, ensure_worksheet
from sun_study.archicad.sun_eyes import sheet_cells_for
from sun_study.archicad.views import StoreyView, three_d_sources, views_for_sources

__all__ = [
    "FLAT_LABEL",
    "FlatReport",
    "FlatRow",
    "draw_flat_worksheet",
    "drawable",
    "make_base_document",
    "make_flat_sheets",
    "merged",
    "outline_colour",
    "outline_colours",
    "outline_rings",
    "own_shadow",
    "read_shadows",
    "seen_of_each",
    "shadow_pieces",
    "smaller_above",
    "window_a_cell_shows",
    "without_holes",
]

#: The word the flat sheets, their worksheet and their layer carry after
#: ``Shadow Plans``, so a project keeps the stacked sheets beside them.
FLAT_LABEL = "Flat"
#: The working layout the documents are read on, and the base document.
STAGING_LABEL = "Working"
BASE_LABEL = "BASE"
#: What a row's documents without the buildings around it are called.
ALONE_WORD = "ALONE"

#: Pieces of one shadow meet along the edges of the surfaces they fall on,
#: and not always to the last decimal: grown by this and shrunk again, two
#: pieces a hair apart are one.
SEAM_M = 0.002
#: A vertex nearer than this to the line through its neighbours is dropped.
SIMPLIFY_M = 0.02
#: The grid every outline is drawn on. Archicad refuses a fill whose outline
#: it reads as crossing itself, and a vertex a fraction of a millimetre off a
#: line does: of 629 outlines valid to the geometry library, 75 were refused
#: as they were and 13 on this grid.
GRID_M = 0.001
#: The least shadow worth a fill, and the least worth an outline.
LEAST_M2 = 0.25
LEAST_OUTLINED_M2 = 4.0
#: How far an outline Archicad still refuses is drawn inside itself: enough
#: to part a hole from the edge it touches, far too little to see at 1:500.
HAIR_M = 0.004
#: How deep ``without_holes`` cuts before it hands back what it has.
CUTS_DEEP = 6
#: Fills in one ``CreateFills``, and polylines in one ``CreatePolylines``.
BATCH = 200
#: Parts of a row's own shadow nearer than twice this are one part.
JOIN_M = 1.5
#: How far past its own shadow a row's added shadow is still believed: the
#: two come from two documents, and do not agree to the millimetre.
REACH_MARGIN_M = 2.0
#: What the rows under the designed one are outlined in, nearest the
#: designed row first: the office's magenta for the envelope it is compared
#: with, then an orange and a green.
OTHER_OUTLINES: tuple[tuple[int, int, int], ...] = ((214, 0, 170), (230, 120, 0), (0, 150, 80))
#: An outline is a line to be read at 1:500 and smaller, not a survey.
OUTLINE_SIMPLIFY_M = 0.15
#: The gap between one hour's plan and the next in the worksheet, as a share
#: of the plan's width, and the least it is in metres.
GAP_SHARE = 0.25
GAP_LEAST_M = 20.0
#: Where the first working drawing's origin goes on the working layout, and
#: how far apart they are put, in metres of paper. Nobody reads that sheet.
WORKING_ORIGIN_M = (0.3, 0.3)

Ring = list[tuple[float, float]]


@dataclass(frozen=True)
class FlatRow:
    """One row of the legend, as the documents that cast it.

    ``documents`` show the row with everything that stands, so their shadow
    is the whole shadow with the row built; ``alone`` show the row without
    the buildings around it, for a row that might be built, and their shadow
    is the outline. Both are by hour, in the hours' order.
    """

    label: str
    rgb: tuple[int, int, int]
    shadow_pen: int
    documents: tuple[MadePlan, ...]
    alone: tuple[MadePlan, ...] = ()


@dataclass(frozen=True)
class FlatReport:
    """What a flat run drew, for the run to say."""

    worksheet: str
    fills: int
    outlines: int
    refused_m2: float
    sheets: tuple[LayoutReport, ...]
    removed: tuple[str, ...]
    notes: tuple[str, ...]

    def describe(self) -> str:
        lines = [
            f"  worksheet {self.worksheet!r}: {self.fills} fills and {self.outlines} dashed "
            "outlines, an hour beside the next"
        ]
        if self.refused_m2 > 0.5:
            lines.append(
                f"    {self.refused_m2:.0f} m2 of shadow could not be drawn: Archicad refused "
                "its outline every way it was offered"
            )
        lines.extend(report.describe() for report in self.sheets)
        return "\n".join(lines)


# -- geometry: nothing here asks Archicad anything ---------------------------


def shadow_pieces(
    polygons: Sequence[Mapping[str, Any]],
    pen: int,
    *,
    origin: tuple[float, float],
    scale: float,
) -> list[Polygon]:
    """The shadow's pieces among a drawing's polygons, in project metres.

    A drawing of a 3D Document draws each fill twice over, a solid polygon and
    the border of its hatch; the shadow is the solid ones filled in the
    shadow's pen. ``origin`` is where the drawing's own origin sits on the
    layout and ``scale`` the 500 of 1:500, which is all that lies between the
    paper and the project: a document seen from overhead is the plan.
    """
    ox, oy = origin
    pieces: list[Polygon] = []
    for one in polygons:
        if not one.get("solid") or one.get("fillPen") != pen:
            continue
        xy = one.get("xy") or []
        points = [
            ((x - ox) * scale, (y - oy) * scale) for x, y in zip(xy[0::2], xy[1::2], strict=True)
        ]
        rings: list[Ring] = []
        start = 0
        for end in one.get("ends") or [len(points)]:
            rings.append(points[start:end])
            start = end
        if not rings or len(rings[0]) < 4:
            continue
        shape: BaseGeometry = Polygon(rings[0], [ring for ring in rings[1:] if len(ring) >= 4])
        if not shape.is_valid:
            shape = make_valid(shape)
        pieces.extend(_polygons(shape, least=0.0))
    return pieces


def _polygons(shape: BaseGeometry, *, least: float = LEAST_M2) -> list[Polygon]:
    """The polygons of a geometry worth keeping, whatever kind it is."""
    if shape.is_empty:
        return []
    found = list(shape.geoms) if hasattr(shape, "geoms") else [shape]
    return [one for one in found if isinstance(one, Polygon) and one.area > least]


def merged(pieces: Sequence[Polygon], window: PlanWindow | None = None) -> BaseGeometry:
    """One shadow from its pieces, cut to the window of the plan."""
    if not pieces:
        return Polygon()
    whole = unary_union([piece.buffer(SEAM_M, join_style="mitre") for piece in pieces])
    whole = whole.buffer(-SEAM_M, join_style="mitre").simplify(SIMPLIFY_M)
    if window is not None:
        whole = whole.intersection(box(window.x_min, window.y_min, window.x_max, window.y_max))
    return whole


def seen_of_each(bottom_to_top: Sequence[tuple[str, BaseGeometry]]) -> dict[str, BaseGeometry]:
    """What is seen of each row: its shadow where no row above it casts one.

    The order is the stack's, bottom to top -- the rows that might be built in
    the order named, then what stands from the last named to the first -- and
    the split is the one the stack made by laying its drawings in that order,
    made here by subtracting, so the fills never lie over one another.
    """
    seen: dict[str, BaseGeometry] = {}
    above: BaseGeometry = Polygon()
    for label, shadow in reversed(list(bottom_to_top)):
        seen[label] = shadow if above.is_empty else shadow.difference(above)
        above = shadow if above.is_empty else unary_union([above, shadow])
    return seen


def smaller_above(
    bottom_to_top: Sequence[tuple[str, BaseGeometry]], own_m2: Mapping[str, float]
) -> list[tuple[str, BaseGeometry]]:
    """The stack with the rows that might be built put largest lowest.

    ``own_m2`` is the area of each such row's own shadow. A row is seen only
    where no row above it casts a shadow, so an envelope lying under a
    taller proposal is covered by it altogether and the reader has its
    outline and nothing else; the smaller over the larger, both are seen.
    The rows change places among themselves only: what stands keeps its
    place over them all.
    """
    stack = list(bottom_to_top)
    places = [index for index, (label, _) in enumerate(stack) if label in own_m2]
    ranked = sorted((stack[index] for index in places), key=lambda one: -own_m2[one[0]])
    for index, one in zip(places, ranked, strict=True):
        stack[index] = one
    return stack


def outline_colours(rows: Sequence[FlatRow]) -> dict[str, tuple[int, int, int]]:
    """What each row with a shadow of its own is outlined in, by its label.

    ``rows`` are bottom to top as named. The designed row -- the topmost of
    them -- is outlined in its legend colour at full strength; the rows
    under it are every one a pale blue in the legend, which at full strength
    is the same blue, so each takes a colour of its own instead.
    """
    colours: dict[str, tuple[int, int, int]] = {}
    for depth, row in enumerate(reversed([row for row in rows if row.alone])):
        colours[row.label] = (
            outline_colour(row.rgb)
            if depth == 0
            else OTHER_OUTLINES[(depth - 1) % len(OTHER_OUTLINES)]
        )
    return colours


def drawable(shape: BaseGeometry) -> list[Polygon]:
    """A shadow as the polygons Archicad is offered: on the grid, each turned
    the one way, the slivers left out."""
    if shape.is_empty:
        return []
    return [orient(one, 1.0) for one in _polygons(set_precision(shape, GRID_M))]


def without_holes(part: Polygon, depth: int = 0) -> list[Polygon]:
    """A polygon cut through its holes, so no piece has one.

    The last thing tried for an outline Archicad refuses: it is cut along a
    line through each hole, across and then up, and a hole a cut passes
    through is a notch in the piece either side.
    """
    if not part.interiors or depth >= CUTS_DEEP:
        return [part]
    x0, y0, x1, y1 = part.bounds
    across = depth % 2 == 0
    middles = [Polygon(hole).representative_point() for hole in part.interiors]
    cuts = sorted({round(middle.x if across else middle.y, 3) for middle in middles})
    edges = [(x0 if across else y0) - 1.0, *cuts, (x1 if across else y1) + 1.0]
    pieces: list[Polygon] = []
    for low, high in pairwise(edges):
        strip = box(low, y0 - 1.0, high, y1 + 1.0) if across else box(x0 - 1.0, low, x1 + 1.0, high)
        for one in drawable(part.intersection(strip)):
            pieces.extend(without_holes(one, depth + 1))
    return pieces


def outline_rings(shape: BaseGeometry) -> list[Ring]:
    """The outer edge of each part of a shadow, closed, for a dashed line.

    The outside only: a courtyard the shadow leaves lit is a hole in the
    fill, and a second dashed ring inside the first reads as another
    building's shadow.
    """
    rings: list[Ring] = []
    for part in _polygons(
        set_precision(shape.simplify(SIMPLIFY_M), GRID_M), least=LEAST_OUTLINED_M2
    ):
        rings.append([(float(x), float(y)) for x, y in part.exterior.coords])
    return rings


def own_shadow(shape: BaseGeometry) -> BaseGeometry:
    """A row's own shadow from what its document alone draws: the largest
    part, whole, and nothing else.

    The document shows the row on the bare ground, so its shadow is one
    shape reaching from the building. What else is in the shadow's pen is
    the ground's own doing -- a road set into the terrain was drawn dark at
    every hour of the day, the same shape each time, a block from the
    building -- and the row's shadow on its own roofs, which is inside the
    building. So the parts are joined where they all but touch, the largest
    is kept, and the lit courts inside it are filled: one outline.
    """
    if shape.is_empty:
        return Polygon()
    closed = shape.buffer(JOIN_M, join_style="mitre").buffer(-JOIN_M, join_style="mitre")
    parts = _polygons(closed, least=LEAST_OUTLINED_M2)
    if not parts:
        return Polygon()
    largest = max(parts, key=lambda part: part.area)
    whole = Polygon(largest.exterior).simplify(OUTLINE_SIMPLIFY_M)
    # On the grid here, and the largest again: snapped, a shape that narrows
    # to a point parts there, and the outline was two rings touching.
    snapped = _polygons(set_precision(whole, GRID_M), least=0.0)
    return max(snapped, key=lambda part: part.area) if snapped else Polygon()


def outline_colour(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """The colour a row is outlined in: its legend colour at full strength.

    The legend's colours are pale, to be read through; an outline is a line,
    and a line in a pale colour is lost on the fill it runs across. The hue
    is kept, so the proposal's outline is the blue of its fill and a second
    row's is its own; a grey, which has no hue, is drawn dark.
    """
    hue, _lightness, saturation = colorsys.rgb_to_hls(*(channel / 255.0 for channel in rgb))
    if saturation < 0.05:
        return (60, 60, 60)
    red, green, blue = colorsys.hls_to_rgb(hue, 0.42, 1.0)
    return (round(red * 255), round(green * 255), round(blue * 255))


def window_a_cell_shows(
    window: PlanWindow, cell_mm: tuple[float, float], scale: float
) -> PlanWindow:
    """The part of the window a cell of the sheet shows at this scale: the
    cell's size about the window's centre, and never more than the window."""
    cx, cy = window.centre
    half_w = min(window.width, cell_mm[0] / 1000.0 * scale) / 2.0
    half_h = min(window.height, cell_mm[1] / 1000.0 * scale) / 2.0
    return PlanWindow(cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def hour_pitch(window: PlanWindow) -> float:
    """How far one hour's plan is from the next in the worksheet, in metres."""
    return window.width + max(window.width * GAP_SHARE, GAP_LEAST_M)


# -- the documents ------------------------------------------------------------


def make_base_document(
    connection: ArchicadConnection, *, settings: ShadowPlanSettings
) -> StoreyView:
    """The one document with no shadows, and the view of it the sheets place.

    Overhead, north up, its surfaces left as outlines: the buildings and the
    streets every cell of a flat sheet shows over its fills. One, for every
    hour, since nothing in it moves with the sun. Found by its name on a
    second run, since a document cannot be deleted.
    """
    name = naming.named(f"{PLAN_WORD} {BASE_LABEL}")
    sources = {s.name: s for s in three_d_sources(connection) if s.kind == "DocumentFrom3DItem"}
    if name not in sources:
        connection.run_loriini(
            "CreateDocumentFrom3D",
            {
                "name": name,
                "referenceId": "SPBASE",
                "viewAzimuth": 0.0,
                "viewAltitude": OVERHEAD_DEG,
                "sunShadows": False,
                "fillUncutSurfaces": False,
            },
        )
        sources = {s.name: s for s in three_d_sources(connection) if s.kind == "DocumentFrom3DItem"}
        if name not in sources:
            raise ArchicadError(f"The 3D Document {name!r} was made but is not in the Project Map.")
    views = views_for_sources(
        connection,
        [(sources[name], name)],
        combination=settings.layer_combination,
        folder=naming.named(f"{SET_WORD} {FLAT_LABEL}"),
        drawing_scale=settings.scale,
    )
    connection.run_tapir(
        "SetViewSettings",
        {
            "navigatorItemIdsWithViewSettings": [
                {
                    "navigatorItemId": {"guid": views[0].navigator_id},
                    "viewSettings": settings.for_view(),
                }
            ]
        },
    )
    return views[0]


# -- reading the shadows out --------------------------------------------------


def _drawings(connection: ArchicadConnection, layout: str) -> dict[str, dict[str, Any]]:
    answer = connection.run_loriini("GetDrawings", {"layoutDatabaseId": {"guid": layout}})
    return {str(one.get("name", "")): one for one in (answer or {}).get("drawings") or []}


def _arrange(
    connection: ArchicadConnection,
    layout: str,
    drawings: Sequence[Mapping[str, Any]],
    *,
    stack: bool = False,
) -> None:
    """Each drawing's own origin put at its ``x`` and ``y`` and clipped to its
    ``frame``, in layout metres."""
    asked: dict[str, Any] = {
        "layoutDatabaseId": {"guid": layout},
        "drawings": [dict(one) for one in drawings],
        "anchor": "origin",
        "frameRelativeToOrigin": False,
        "autoUpdate": True,
    }
    if stack:
        asked["stack"] = True
    answer = connection.run_loriini("ArrangeDrawings", asked)
    failures = (answer or {}).get("failures") if isinstance(answer, dict) else None
    if not isinstance(answer, dict) or not answer.get("success") or failures:
        raise ArchicadError(f"ArrangeDrawings answered {answer!r}")


def read_shadows(
    connection: ArchicadConnection,
    rows: Sequence[FlatRow],
    *,
    scale: float,
    window: PlanWindow,
    master_layout: str | None = None,
    say: Callable[[str], None] | None = None,
) -> tuple[
    dict[tuple[str, dt.datetime], BaseGeometry], dict[tuple[str, dt.datetime], BaseGeometry]
]:
    """Every row's shadow at every hour, and every outlined row's own.

    An hour at a time: that hour's documents are placed on the working
    layout, each clipped to the window of the plan, read, and taken off
    again, so the layout never holds more than one hour's -- the sheet that
    held them all is the one that would not open. Returns the shadows with
    what stands and the shadows alone, each by row and instant, in project
    metres.
    """
    name = naming.named(f"{SET_WORD} {STAGING_LABEL}")
    whole: dict[tuple[str, dt.datetime], BaseGeometry] = {}
    alone: dict[tuple[str, dt.datetime], BaseGeometry] = {}
    hours = sorted({one.plan.when for row in rows for one in (*row.documents, *row.alone)})
    spacing = window.width / scale + 0.05
    for when in hours:
        wanted: list[tuple[FlatRow, MadePlan, bool]] = []
        for row in rows:
            wanted += [(row, one, False) for one in row.documents if one.plan.when == when]
            wanted += [(row, one, True) for one in row.alone if one.plan.when == when]
        views = [
            (
                one.view.navigator_id,
                f"{row.label}{' ' + ALONE_WORD if apart else ''} {one.plan.stamp}",
            )
            for row, one, apart in wanted
        ]
        report = layout_from_views(
            connection, views, layout_name=name, scale=scale, master_layout=master_layout
        )
        layout = report.database_id
        placed = _drawings(connection, layout)
        origins: dict[str, tuple[float, float]] = {}
        arranged: list[dict[str, Any]] = []
        for index, (_, drawing_name) in enumerate(views):
            ox = WORKING_ORIGIN_M[0] + index * spacing
            oy = WORKING_ORIGIN_M[1]
            origins[drawing_name] = (ox, oy)
            arranged.append(
                {
                    "guid": placed[drawing_name]["guid"],
                    "x": ox,
                    "y": oy,
                    "frame": {
                        "xMin": ox + window.x_min / scale,
                        "yMin": oy + window.y_min / scale,
                        "xMax": ox + window.x_max / scale,
                        "yMax": oy + window.y_max / scale,
                    },
                }
            )
        _arrange(connection, layout, arranged)
        for (row, _one, apart), (_, drawing_name) in zip(wanted, views, strict=True):
            answer = connection.run_loriini(
                "GetDrawingPrimitives",
                {
                    "layoutDatabaseId": {"guid": layout},
                    "drawing": placed[drawing_name]["guid"],
                    "pens": [row.shadow_pen],
                },
            )
            pieces = shadow_pieces(
                (answer or {}).get("polygons") or [],
                row.shadow_pen,
                origin=origins[drawing_name],
                scale=scale,
            )
            shadow = merged(pieces, window)
            (alone if apart else whole)[(row.label, when)] = shadow
            if say:
                say(
                    f"    {drawing_name:<34} {len(pieces):>6} pieces, "
                    f"{len(_polygons(shadow)):>3} polygons, {shadow.area:>9,.0f} m2"
                )
        # Done with: the working drawings come off the layout again.
        try:
            connection.run_loriini(
                "SetCurrentDatabase", {"databaseId": {"guid": layout}, "windowType": "Layout"}
            )
            connection.run_tapir(
                "DeleteElements",
                {"elements": [{"elementId": {"guid": placed[n]["guid"]}} for _, n in views]},
            )
        except ArchicadError as error:
            if say:
                say(f"    the working drawings of {when:%H:%M} are still on {name!r}: {error}")
    ensure_model_database(connection)
    return whole, alone


# -- drawing them flat --------------------------------------------------------


def _fill(part: Polygon, rgb: tuple[int, int, int], *, layer: int, solid: int | None,
          dx: float, dy: float, element_id: str) -> dict[str, Any]:  # fmt: skip
    colour = {"red": rgb[0] / 255.0, "green": rgb[1] / 255.0, "blue": rgb[2] / 255.0}
    rings = [list(part.exterior.coords)[:-1], *(list(hole.coords)[:-1] for hole in part.interiors)]
    data: dict[str, Any] = {
        "contours": [
            {"points": [{"x": x + dx, "y": y + dy} for x, y in ring]}
            for ring in rings
            if len(ring) >= 3
        ],
        "layerIndex": layer,
        "determination": "drafting",
        "showArea": False,
        "contourPen": 0,
        "foregroundColour": colour,
        "backgroundColour": colour,
        "elementId": element_id,
    }
    if solid is not None:
        data["fillIndex"] = solid
    return data


def _draw_all(connection: ArchicadConnection, fills: Sequence[dict[str, Any]]) -> list[int]:
    """Draw these fills; the positions of the ones Archicad refused.

    A batch is one undo step and is taken back whole when one fill in it is
    refused, so a refused batch is halved down to the fill that is.
    """
    refused: list[int] = []

    def send(start: int, stop: int) -> None:
        if start >= stop:
            return
        try:
            connection.run_loriini("CreateFills", {"fills": list(fills[start:stop])})
        except CommandFailedError as error:
            if "not have the registered" in str(error):
                raise
            if stop - start == 1:
                refused.append(start)
                return
            middle = (start + stop) // 2
            send(start, middle)
            send(middle, stop)

    for start in range(0, len(fills), BATCH):
        send(start, min(start + BATCH, len(fills)))
    return refused


def draw_flat_worksheet(
    connection: ArchicadConnection,
    rows: Sequence[FlatRow],
    hours: Sequence[dt.datetime],
    whole: Mapping[tuple[str, dt.datetime], BaseGeometry],
    alone: Mapping[tuple[str, dt.datetime], BaseGeometry],
    *,
    name: str,
    window: PlanWindow,
    say: Callable[[str], None] | None = None,
) -> tuple[str, int, int, float]:
    """One day's hours as fills in one worksheet, an hour beside the next.

    ``rows`` are bottom to top, and the rows with a shadow of their own are
    put, hour by hour, the smaller over the larger (``smaller_above``). Hour
    ``n`` is drawn with the window's centre
    at ``(n x hour_pitch, 0)``, which is where the sheets look for it. Each
    row is filled where no row above it casts a shadow, in its legend colour
    and no contour; each row with a shadow of its own is outlined, dashed, in
    that colour darker. The layer is cleared first, so a second run draws
    over nothing. Returns the worksheet's Project Map id, the fills and the
    outlines drawn, and the square metres Archicad would not draw.
    """
    _, navigator_id, _ = ensure_worksheet(connection, name, say=say)
    layer = ensure_layer(connection, naming.named(f"{SET_WORD}.{FLAT_LABEL}"))
    clear_layer(connection, layer.index)
    solid = attribute_index(connection, "Fill", ("Solid Fill", "Solid", "Foreground"))
    dashed = attribute_index(connection, "Line", ("Dashed", "Dashed Line", "Dash"))
    try:
        pens = pen_table(connection)
    except ArchicadError:
        pens = ()
    cx, cy = window.centre
    pitch = hour_pitch(window)

    outline_of = outline_colours(rows)

    parts: list[tuple[Polygon, FlatRow, float, float, str]] = []
    lines: list[dict[str, Any]] = []
    for position, when in enumerate(hours):
        dx, dy = position * pitch - cx, -cy
        present = [
            (row.label, whole[(row.label, when)]) for row in rows if (row.label, when) in whole
        ]
        reaches = {
            row.label: own_shadow(alone[(row.label, when)])
            for row in rows
            if (row.label, when) in alone
        }
        seen = seen_of_each(
            smaller_above(present, {label: reach.area for label, reach in reaches.items()})
        )
        for row in rows:
            added = seen.get(row.label, Polygon())
            reach = reaches.get(row.label)
            if reach is not None and not reach.is_empty:
                # A row that might be built adds shadow only where its own
                # shadow reaches. Two documents of one hour do not draw the
                # shadows they share piece for piece alike, and the scraps
                # between them were filled in the row's colour a street away.
                added = added.intersection(reach.buffer(REACH_MARGIN_M))
            for part in drawable(added):
                parts.append((part, row, dx, dy, f"{row.label} {when:%H:%M}"))
            if reach is None:
                continue
            pen = nearest_pen(pens, outline_of[row.label])
            for ring in outline_rings(reach):
                line: dict[str, Any] = {
                    "coordinates": [{"x": x + dx, "y": y + dy} for x, y in ring],
                    "layerIndex": layer.index,
                }
                if pen is not None:
                    line["linePenIndex"] = pen
                if dashed is not None:
                    line["lineTypeIndex"] = dashed
                lines.append(line)

    def as_fills(
        these: Sequence[tuple[Polygon, FlatRow, float, float, str]],
    ) -> list[dict[str, Any]]:
        return [
            _fill(part, row.rgb, layer=layer.index, solid=solid, dx=dx, dy=dy, element_id=word)
            for part, row, dx, dy, word in these
        ]

    drawn = len(parts)
    refused = [parts[index] for index in _draw_all(connection, as_fills(parts))]
    drawn -= len(refused)
    lost = 0.0
    if refused:
        # A hair inside itself first, which parts an outline that touches
        # itself; then cut through its holes; and what is refused even so is
        # said, in square metres, rather than left out in silence.
        smaller = [
            (one, row, dx, dy, word)
            for part, row, dx, dy, word in refused
            for one in drawable(part.buffer(-HAIR_M, join_style="mitre"))
        ]
        still = [smaller[index] for index in _draw_all(connection, as_fills(smaller))]
        drawn += len(smaller) - len(still)
        cut = [
            (one, row, dx, dy, word)
            for part, row, dx, dy, word in still
            for one in without_holes(part)
        ]
        last = [cut[index] for index in _draw_all(connection, as_fills(cut))]
        drawn += len(cut) - len(last)
        lost = sum(part.area for part, *_ in last)
        if say:
            say(
                f"    {len(refused)} outlines Archicad refused as they were: "
                f"{len(smaller) - len(still)} drawn a hair smaller, {len(cut) - len(last)} "
                f"pieces cut through their holes"
            )
    for start in range(0, len(lines), BATCH):
        connection.run_tapir("CreatePolylines", {"polylinesData": lines[start : start + BATCH]})
    return navigator_id, drawn, len(lines), lost


# -- the sheets ----------------------------------------------------------------


def _worksheet_view(connection: ArchicadConnection, worksheet_item: str, name: str) -> str:
    """The View Map's view of the worksheet, made once and found after."""
    tree = connection.run_official(
        "API.GetNavigatorItemTree", {"navigatorTreeId": {"type": "ViewMap"}}
    )
    root = ((tree or {}).get("navigatorTree") or {}).get("rootItem") or {}

    def find(node: Mapping[str, Any]) -> str:
        item = node.get("navigatorItem", node)
        if item.get("type") == "WorksheetItem" and str(item.get("name", "")) == name:
            return str((item.get("navigatorItemId") or {}).get("guid", ""))
        for child in item.get("children") or []:
            found = find(child)
            if found:
                return found
        return ""

    found = find(root)
    if found:
        return found
    made = connection.run_tapir(
        "CloneProjectMapItemToViewMap",
        {"viewsData": [{"navigatorItemId": {"guid": worksheet_item}}]},
    )
    items = (made or {}).get("navigatorItems") or []
    guid = str(((items[0] if items else {}).get("navigatorItemId") or {}).get("guid", ""))
    if not guid:
        raise ArchicadError(f"No view could be made of the worksheet {name!r}: {made!r}")
    return guid


def make_flat_sheets(
    connection: ArchicadConnection,
    hours: Sequence[MadePlan],
    worksheets: Mapping[str, tuple[str, str]],
    base: StoreyView,
    *,
    sheets: str = DEFAULT_SHEET_MODE,
    scale: float,
    window: PlanWindow,
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
    legend: Sequence[tuple[str, tuple[int, int, int]]] = (),
    rings: Sequence[Sequence[tuple[float, float]]] = (),
    outline_pen: int | None = None,
    aspect: float | None = None,
    legend_outlines: Sequence[tuple[int, int, int] | None] = (),
) -> tuple[list[LayoutReport], list[str], list[str]]:
    """The flat worksheets on their sheets: in each cell a drawing of the
    day's worksheet, and the base document over it.

    ``hours`` are one row's documents, for the hours and their captions;
    ``worksheets`` is each day's worksheet as ``(Project Map id, name)``,
    by the day's words (``JUNE 21``). Dealt as the stacked sheets are, named
    *Shadow | Shadow Plans Flat - JUNE 21*; the worksheet's drawing is put so
    that hour's plan is in the cell, the base document's so the window's
    centre is, its background clear, and only it keeps a title. The legend
    and the site are drawn as on a combined sheet; ``legend_outlines`` is,
    row for row of the legend, the colour its shadow is outlined in on the
    plans or ``None``, and the swatch is edged in it, dashed. ``aspect`` is the shape
    the cells were dealt for, when it is not the window's own. Returns the sheets, the
    earlier flat sheets removed, and anything worth saying.
    """
    dealt, cells = _dealt(list(hours), sheets=sheets, set_label=FLAT_LABEL)
    removed = remove_stale_layouts(connection, _sheet_stem(FLAT_LABEL), {name for name, _ in dealt})
    clear_of = title_block_mm + (LEGEND_COLUMN_MM if legend else 0.0)
    pitch = hour_pitch(window)
    cx, cy = window.centre
    place: dict[dt.datetime, int] = {}
    count: dict[str, int] = {}
    for one in hours:
        day = one.plan.when.strftime("%B %d").upper()
        place[one.plan.when] = count.get(day, 0)
        count[day] = count.get(day, 0) + 1
    views_of: dict[str, str] = {}
    for day, (item, name) in worksheets.items():
        views_of[day] = _worksheet_view(connection, item, name)
    connection.run_tapir(
        "SetViewSettings",
        {
            "navigatorItemIdsWithViewSettings": [
                {"navigatorItemId": {"guid": view}, "viewSettings": {"drawingScale": int(scale)}}
                for view in views_of.values()
            ]
        },
    )

    edges: list[int | None] = []
    dashed: int | None = None
    if any(legend_outlines):
        dashed = attribute_index(connection, "Line", ("Dashed", "Dashed Line", "Dash"))
        try:
            pens = pen_table(connection)
        except ArchicadError:
            pens = ()
        edges = [nearest_pen(pens, rgb) if rgb else None for rgb in legend_outlines]

    reports: list[LayoutReport] = []
    said: list[str] = []
    for name, on_sheet in dealt:
        piles = [
            [
                (views_of[one.plan.when.strftime("%B %d").upper()], f"{one.plan.caption} SHADOWS"),
                (base.navigator_id, one.plan.caption),
            ]
            for one in on_sheet
        ]
        report = layout_from_views(
            connection,
            [view for pile in piles for view in pile],
            layout_name=name,
            scale=scale,
            master_layout=master_layout,
            cells=max(cells, len(piles)),
        )
        reports.append(report)
        if not report.database_id:
            continue
        sheet, _ = layout_sheet(connection, report.database_id)
        grid = sheet_cells_for(
            sheet,
            cells,
            title_block_mm=clear_of,
            aspect=aspect if aspect is not None else window.aspect,
        )[: len(piles)]
        placed = _drawings(connection, report.database_id)
        arranged: list[dict[str, Any]] = []
        for upper in (False, True):
            for one, (x0, y0, x1, y1) in zip(on_sheet, grid, strict=True):
                frame = {"xMin": x0, "yMin": y0, "xMax": x1, "yMax": y1}
                mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                drawing_name = one.plan.caption if upper else f"{one.plan.caption} SHADOWS"
                if drawing_name not in placed:
                    continue
                arranged.append(
                    {
                        "guid": placed[drawing_name]["guid"],
                        # The base document's origin is the project's; the
                        # worksheet's is the first hour's window centre.
                        "x": mx - cx / scale
                        if upper
                        else mx - place[one.plan.when] * pitch / scale,
                        "y": my - cy / scale if upper else my,
                        "frame": frame,
                        "transparentBackground": upper,
                    }
                )
        _arrange(connection, report.database_id, arranged, stack=True)
        note = one_title_per_pile(connection, report.database_id, piles)
        if note and note not in said:
            said.append(note)
        if not legend and not rings:
            continue
        try:
            draw_legend_and_outline(
                connection,
                report.database_id,
                title=LEGEND_TITLE,
                rows=legend,
                cells=grid,
                window=window,
                scale=scale,
                rings=rings,
                outline_pen=outline_pen,
                title_block_mm=title_block_mm,
                row_edges=edges,
                edge_line=dashed,
            )
        except ArchicadError as error:
            note = f"the legend and the site outline could not be drawn on the sheet: {error}"
            if note not in said:
                said.append(note)
    ensure_model_database(connection)
    return reports, removed, said


def worksheet_name(day: str) -> str:
    """``Shadow | Shadow Plans Flat - JUNE 21``: a day's worksheet, named as
    its sheet is."""
    return f"{_sheet_stem(FLAT_LABEL)}{day}"
