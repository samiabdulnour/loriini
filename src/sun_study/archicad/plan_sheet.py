"""The combined shadow-plan sheet: the scale it is drawn at, the pens it is
printed in, and the legend and site outline drawn on it (D143).

Three things the first combined sheet got wrong on the sample project, each
answered here.

**The site did not fit.** Each drawing is placed by its own origin at the
centre of its cell and clipped to the cell, and a 420 m site drawn at 1:1000
in a cell 230 mm wide is cut at both edges. So the run measures the plan
extent of everything the stack's rows show -- ``plan_window``, read-only,
from the 2D bounding boxes of the model elements on the layers the rows'
combinations show -- and chooses the largest standard scale at which that
window fits a cell (``fitted_scale``); and each drawing's origin is put where
the window's centre lands in the middle of the cell, not the model origin.

**The colours were the project's, not the legend's.** A 3D Document's shadow
can only be a pen, and a pen is whatever the pen table says. The nearest pen
to the legend's pale grey in the sample project's table was a pale green.
So the run makes its own pen set, ``15 | Shadow Plans``, a copy of the one
the drawings print in with each row's pen -- the nearest one, so anything
else drawn in it hardly moves -- set to the legend's exact colour
(``legend_pen_set``), and each drawing on the sheet is told to print in it,
since a drawing of a 3D Document prints in the model's active pen table and
not in the pen set its view pins (measured; ``ArrangeDrawings``
``penTableIndex``). Archicad before 27 has no ``CreatePenTables``; there the
pens are the nearest the table has, and the run says how near.

**There was no legend and no site.** The legend is drawn on the sheet, in the
column left of the title block where every study's legend goes: a swatch per
row in the row's exact colour and the legend's words beside it. The site
boundary, read off the project's boundary layer, is drawn over every drawing
as an outline. Both go on the sheet itself, on Archicad's own layer, which
no combination can hide; and the sheet's earlier texts and fills are cleared
first, since a combined sheet is this tool's own and a rerun that appended
would print a second legend over the first.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.draw import Pen, create_texts
from sun_study.archicad.layers import combination_states
from sun_study.archicad.layout import LayoutSheet, layout_sheet
from sun_study.archicad.series import database_of
from sun_study.archicad.sheets import MM, enter_layout, legend_place
from sun_study.archicad.site_analysis import attribute_index
from sun_study.archicad.sun_eyes import sheet_cells_for

__all__ = [
    "ARCHICAD_LAYER_INDEX",
    "BOUNDARY_RGB",
    "CELL_FILL",
    "STANDARD_SCALES",
    "PlanWindow",
    "boundary_rings",
    "cell_size_mm",
    "draw_legend_and_outline",
    "fitted_scale",
    "legend_pen_set",
    "nearest_pen",
    "pen_table_index",
    "plan_window",
]

#: The scales a site plan is drawn at, smallest first. A fitted scale is the
#: first of these the window fits at, so a sheet reads 1:1500 and not 1:1437.
STANDARD_SCALES: tuple[int, ...] = (
    100,
    200,
    250,
    500,
    750,
    1000,
    1250,
    1500,
    2000,
    2500,
    5000,
    10000,
)

#: How much of a cell a drawing may fill, each way: room for the drawing's
#: title under it and a margin either side.
CELL_FILL = 0.92

#: Archicad's own layer, index 1 in every project. Nothing can hide or lock
#: it, which is what a legend on a sheet needs: a layer of the tool's own is
#: hidden in every layer combination the project already had, and a layout
#: shows what its combination shows.
ARCHICAD_LAYER_INDEX = 1

#: The site boundary's colour on the sheet: a red, matched to the nearest pen
#: of the layout's pen table, since an outline is a contour and a contour is
#: a pen.
BOUNDARY_RGB: tuple[int, int, int] = (220, 30, 30)

#: Model element types that stand in the 3D Documents, for the window. 2D
#: annotation -- texts, dimensions, markers, the fills a study draws -- is
#: left out: it is not in a document, and a dimension string run off the
#: page would size a plan of nothing.
MODEL_TYPES = frozenset(
    {
        "Wall",
        "Column",
        "Beam",
        "Window",
        "Door",
        "Object",
        "Lamp",
        "Slab",
        "Roof",
        "Mesh",
        "Shell",
        "Morph",
        "Stair",
        "Railing",
        "CurtainWall",
        "Skylight",
    }
)


@dataclass(frozen=True)
class PlanWindow:
    """A rectangle of the plan, in project metres."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def aspect(self) -> float:
        """Width over height, for the grid the drawings are dealt into."""
        return self.width / self.height if self.height > 0 else 1.0

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.x_min + self.x_max) / 2.0, (self.y_min + self.y_max) / 2.0)


def plan_window(connection: ArchicadConnection, combinations: Sequence[str]) -> PlanWindow | None:
    """The plan extent of the model elements any of these combinations shows.

    Read-only: the combinations' layer states are read and compared, nothing
    is switched. Archicad's element list carries the elements of hidden
    layers too (measured on the sample project, 6,115 of them), so the
    filtering is by layer here rather than by what happens to be on screen.
    ``None`` when no combination can be read or nothing is shown.
    """
    response = connection.run_tapir("GetAttributesByType", {"attributeType": "Layer"})
    attributes = response.get("attributes") if isinstance(response, dict) else None
    index_of = {
        str((a.get("attributeId") or {}).get("guid", "")): a.get("index")
        for a in attributes or []
        if isinstance(a, dict)
    }
    shown: set[int] = set()
    for name in combinations:
        states = combination_states(connection, name)
        for guid, hidden in (states or {}).items():
            index = index_of.get(guid)
            if not hidden and isinstance(index, int):
                shown.add(index)
    if not shown:
        return None

    listed = connection.run_official("API.GetAllElements")
    elements = listed.get("elements") if isinstance(listed, dict) else None
    if not isinstance(elements, list) or not elements:
        return None
    wanted: list[dict[str, Any]] = []
    for start in range(0, len(elements), 500):
        batch = elements[start : start + 500]
        details = connection.run_tapir("GetDetailsOfElements", {"elements": batch})
        rows = details.get("detailsOfElements") if isinstance(details, dict) else None
        if not isinstance(rows, list) or len(rows) != len(batch):
            continue
        wanted += [
            element
            for element, row in zip(batch, rows, strict=True)
            if isinstance(row, dict)
            and row.get("layerIndex") in shown
            and row.get("type") in MODEL_TYPES
        ]
    xs: list[float] = []
    ys: list[float] = []
    for start in range(0, len(wanted), 500):
        boxes = connection.run_official(
            "API.Get2DBoundingBoxes", {"elements": wanted[start : start + 500]}
        )
        for entry in (boxes or {}).get("boundingBoxes2D") or []:
            box = entry.get("boundingBox2D") if isinstance(entry, dict) else None
            if isinstance(box, dict):
                xs += [float(box["xMin"]), float(box["xMax"])]
                ys += [float(box["yMin"]), float(box["yMax"])]
    if not xs:
        return None
    return PlanWindow(min(xs), min(ys), max(xs), max(ys))


def fitted_scale(window: PlanWindow, cell_mm: tuple[float, float]) -> int:
    """The largest standard scale at which the window fits a cell.

    A window ``w`` metres wide is ``w * 1000 / scale`` millimetres on paper,
    and it has to be within ``CELL_FILL`` of the cell each way. Past the last
    standard scale, the next whole thousand.
    """
    width_mm, height_mm = cell_mm
    need = max(
        window.width * 1000.0 / max(width_mm * CELL_FILL, 1.0),
        window.height * 1000.0 / max(height_mm * CELL_FILL, 1.0),
    )
    for scale in STANDARD_SCALES:
        if scale >= need:
            return scale
    return int(math.ceil(need / 1000.0) * 1000)


def cell_size_mm(
    connection: ArchicadConnection,
    master_item: str,
    cells: int,
    *,
    title_block_mm: float,
    aspect: float | None = None,
) -> tuple[float, float] | None:
    """The size of one cell of a sheet on this master, before the sheet exists.

    ``master_item`` is the master's navigator id, as ``choose_master`` gives
    it. The master's own page, read as a layout's is, is cut into ``cells`` as
    the sheet will be. ``None`` when the master will not describe itself.
    """
    if cells <= 0 or not master_item:
        return None
    try:
        sheet, assumed = layout_sheet(connection, database_of(connection, master_item))
    except ArchicadError:
        return None
    if assumed:
        return None
    x0, y0, x1, y1 = sheet_cells_for(sheet, cells, title_block_mm=title_block_mm, aspect=aspect)[0]
    return ((x1 - x0) * 1000.0, (y1 - y0) * 1000.0)


def pen_table_index(connection: ArchicadConnection, guid: str) -> int | None:
    """A pen table's attribute index, which is how a drawing names it."""
    response = connection.run_tapir("GetAttributesByType", {"attributeType": "PenTable"})
    for entry in (response or {}).get("attributes") or []:
        if isinstance(entry, dict) and (entry.get("attributeId") or {}).get("guid") == guid:
            index = entry.get("index")
            return int(index) if isinstance(index, int | float) else None
    return None


def legend_pen_set(
    connection: ArchicadConnection,
    name: str,
    source_guid: str,
    colours: Mapping[int, tuple[int, int, int]],
) -> int | None:
    """Make (or remake) the stack's own pen set; its attribute index, or ``None``.

    A copy of ``source_guid``'s 255 pens with each pen in ``colours`` set to
    the colour given. Remade from the source on every run, so a pen table the
    office has changed since is followed. ``None`` on an Archicad without
    ``CreatePenTables`` (before 27), where the caller keeps the nearest pens.
    """
    try:
        answer = connection.run_tapir(
            "CreatePenTables",
            {
                "penTableDataArray": [
                    {
                        "name": name,
                        "sourceAttributeId": {"attributeId": {"guid": source_guid}},
                        "pens": [
                            {
                                "index": pen,
                                "color": {
                                    "red": rgb[0] / 255.0,
                                    "green": rgb[1] / 255.0,
                                    "blue": rgb[2] / 255.0,
                                },
                            }
                            for pen, rgb in sorted(colours.items())
                        ],
                    }
                ],
                "overwriteExisting": True,
            },
        )
    except ArchicadError:
        return None
    made = (answer or {}).get("attributeIds") if isinstance(answer, dict) else None
    first = made[0] if isinstance(made, list) and made else None
    guid = ((first or {}).get("attributeId") or {}).get("guid") if isinstance(first, dict) else None
    return pen_table_index(connection, str(guid)) if guid else None


def boundary_rings(
    connection: ArchicadConnection, layer_name: str
) -> list[list[tuple[float, float]]]:
    """The outlines on the boundary layer, in project metres.

    A slab's ``polygonOutline`` -- the sample project draws its site as three
    slabs -- and a fill's or a polyline's own points. Anything else on the
    layer, a line or a text, is not an outline and is left out. Read from the
    whole model's element list, as the window is, since Tapir's per-type list
    answers for the current database and a run that has just made a sheet is
    standing in a layout.
    """
    response = connection.run_tapir("GetAttributesByType", {"attributeType": "Layer"})
    indexes = {
        a.get("index")
        for a in (response or {}).get("attributes") or []
        if isinstance(a, dict) and str(a.get("name", "")).casefold() == layer_name.casefold()
    }
    if not indexes:
        return []
    listed = connection.run_official("API.GetAllElements")
    elements = listed.get("elements") if isinstance(listed, dict) else None
    rings: list[list[tuple[float, float]]] = []
    for start in range(0, len(elements or []), 500):
        batch = (elements or [])[start : start + 500]
        details = connection.run_tapir("GetDetailsOfElements", {"elements": batch})
        for row in (details or {}).get("detailsOfElements") or []:
            if not isinstance(row, dict) or row.get("layerIndex") not in indexes:
                continue
            if row.get("type") not in ("Slab", "Hatch", "PolyLine", "Mesh"):
                continue
            d = row.get("details") or {}
            for key in ("polygonOutline", "polygonCoordinates", "coordinates"):
                points = [
                    (float(p["x"]), float(p["y"]))
                    for p in d.get(key) or []
                    if isinstance(p, dict) and "x" in p and "y" in p
                ]
                if len(points) >= 3:
                    rings.append(points)
                    break
    return rings


def _clear(connection: ArchicadConnection) -> None:
    """Every text and fill on the current layout: the last run's legend and
    outlines. The drawings are another element type and stay."""
    for kind in ("Text", "Hatch"):
        found = connection.run_tapir("GetElementsByType", {"elementType": kind})
        elements = found.get("elements") if isinstance(found, dict) else None
        if isinstance(elements, list) and elements:
            connection.run_tapir("DeleteElements", {"elements": elements})


def _open(ring: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """A ring without its closing point, and without a point repeated in a row.

    The add-on closes every contour itself, and Archicad refuses a fill with a
    zero-length edge -- which is what a ring that already ends where it began
    becomes: a slab's ``polygonOutline`` does, and so did the first legend
    swatch drawn on the sample project, refused with -2130313102 (D143).
    """
    points: list[tuple[float, float]] = []
    for point in ring:
        if not points or math.dist(point, points[-1]) > 1e-9:
            points.append(point)
    while len(points) > 1 and math.dist(points[0], points[-1]) <= 1e-9:
        points.pop()
    return points


def _rgb(colour: tuple[int, int, int]) -> dict[str, float]:
    return {"red": colour[0] / 255.0, "green": colour[1] / 255.0, "blue": colour[2] / 255.0}


#: The legend's swatch and spacing, in millimetres on paper.
SWATCH_MM = (12.0, 6.0)
ROW_STEP_MM = 9.0
TEXT_MM = 2.5
TITLE_MM = 3.5


def draw_legend_and_outline(
    connection: ArchicadConnection,
    layout_database_id: str,
    *,
    title: str,
    rows: Sequence[tuple[str, tuple[int, int, int]]],
    cells: Sequence[tuple[float, float, float, float]],
    window: PlanWindow | None,
    scale: float,
    rings: Sequence[Sequence[tuple[float, float]]] = (),
    outline_pen: int | None = None,
    title_block_mm: float,
) -> tuple[int, int]:
    """The legend beside the title block, and the site over every drawing.

    ``rows`` are the legend's words and the exact colour each is printed in.
    ``cells`` are the sheet's filled cells, in layout metres, each holding a
    drawing whose window centre is at the cell's centre at ``scale``;
    ``rings`` are the boundary in project metres, drawn in ``outline_pen``
    with the project's empty fill, so only the contour shows. Returns the
    legend rows and the outlines drawn.
    """
    enter_layout(connection, layout_database_id)
    _clear(connection)
    sheet: LayoutSheet
    sheet, _ = layout_sheet(connection, layout_database_id)
    left, top = legend_place(sheet, title_block_mm)
    solid = attribute_index(connection, "Fill", ("Solid Fill", "Solid", "Foreground"))
    swatch_w, swatch_h = SWATCH_MM[0] * MM, SWATCH_MM[1] * MM
    fills: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = [
        {
            "coordinate": {"x": left, "y": top, "z": 0.0},
            "text": title,
            "height": TITLE_MM * MM,
            "justification": "Left",
        }
    ]
    for number, (words, colour) in enumerate(rows, start=1):
        y = top - number * ROW_STEP_MM * MM
        # Open: the add-on closes every contour itself, and a repeated first
        # point is a zero-length edge Archicad refuses the fill for.
        box = [
            {"x": left, "y": y - swatch_h},
            {"x": left + swatch_w, "y": y - swatch_h},
            {"x": left + swatch_w, "y": y},
            {"x": left, "y": y},
        ]
        fill: dict[str, Any] = {
            "contours": [{"points": box}],
            "layerIndex": ARCHICAD_LAYER_INDEX,
            "fillPen": 1,
            "contourPen": 0,
            "foregroundColour": _rgb(colour),
            "backgroundColour": _rgb(colour),
            "showArea": False,
        }
        if solid is not None:
            fill["fillIndex"] = solid
        fills.append(fill)
        # A text is placed by its top-left corner (measured on the sample
        # project's sheet), so it is set down by half the gap between the
        # swatch's height and its own to sit level with the swatch.
        texts.append(
            {
                "coordinate": {
                    "x": left + swatch_w + 4 * MM,
                    "y": y - (swatch_h - TEXT_MM * MM) / 2.0,
                    "z": 0.0,
                },
                "text": words,
                "height": TEXT_MM * MM,
                "justification": "Left",
            }
        )

    outlines = 0
    empty = attribute_index(connection, "Fill", ("Empty Fill", "Empty", "Background"))
    # Continuous, named: a fill given no line type takes the Fill tool's (D146).
    continuous = attribute_index(connection, "Line", ("Solid Line", "Solid", "Continuous"))
    if rings and window is not None and outline_pen is not None and empty is not None:
        cx, cy = window.centre
        for x0, y0, x1, y1 in cells:
            mid_x, mid_y = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            for ring in rings:
                points = [
                    {"x": mid_x + (x - cx) / scale, "y": mid_y + (y - cy) / scale}
                    for x, y in _open(ring)
                ]
                if len(points) < 3:
                    continue
                fills.append(
                    {
                        "contours": [{"points": points}],
                        "layerIndex": ARCHICAD_LAYER_INDEX,
                        "fillIndex": empty,
                        "fillPen": outline_pen,
                        "backgroundPen": 0,
                        "contourPen": outline_pen,
                        "showArea": False,
                        **({"lineTypeIndex": continuous} if continuous is not None else {}),
                    }
                )
                outlines += 1
    if fills:
        connection.run_loriini("CreateFills", {"fills": fills})
    create_texts(connection, texts, layer_index=ARCHICAD_LAYER_INDEX, heights_in_metres=True)
    _to_the_top(connection)
    return len(rows), outlines


#: The highest display level. The drawings are brought to the front as they
#: are stacked, which puts them at this level; a fill drawn on the sheet after
#: them still lands at its tool's own level, 6, and the site outline drawn
#: over a plan was under the plan's opaque lowest drawing, invisible (D143).
TOP_LEVEL = 14


def _to_the_top(connection: ArchicadConnection) -> None:
    """Every fill and text on the current layout to the top display level,
    after the drawings, so the outline lies over the plans. Tapir moves an
    element a level at a time to the one asked for; moved last, these sit
    above the drawings already there."""
    asked: list[dict[str, Any]] = []
    for kind in ("Hatch", "Text"):
        found = connection.run_tapir("GetElementsByType", {"elementType": kind})
        elements = found.get("elements") if isinstance(found, dict) else None
        asked += [
            {"elementId": element["elementId"], "details": {"drawIndex": TOP_LEVEL}}
            for element in elements or []
            if isinstance(element, dict) and "elementId" in element
        ]
    if asked:
        connection.run_tapir("SetDetailsOfElements", {"elementsWithDetails": asked})


def nearest_pen(pens: Sequence[Pen], rgb: tuple[int, int, int]) -> int | None:
    """The pen nearest a colour, for the outline."""
    if not pens:
        return None
    return min(
        pens, key=lambda pen: sum((a - b) ** 2 for a, b in zip(pen.rgb, rgb, strict=True))
    ).index
