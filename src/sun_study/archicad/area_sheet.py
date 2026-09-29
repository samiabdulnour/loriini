"""The area calculation drawn on a layout: the office's own sheet.

*Area calculation, GFA + Yield* -- the title in two lines, the table of
proposed and target figures, the yield, the notes that say which factors
the figures were worked with, and a legend -- drawn straight onto a layout
of its own, the way the Summary of Controls is (``site_analysis.draw_summary``):
texts and lines on the sheet, no worksheet, no view of it to keep.

Beside the table the office's sheet has the massing, in an axonometric
where the residential floors are yellow. That picture is the project's own:
a 3D view the office sets up once, with the graphic override that colours
the massing by use. Named, it is placed on the sheet beside the table and
framed to the rest of the page; the legend's colours are the office's
yellow and lilac, which the override should match. Unnamed, the sheet is
the table, and the view can be dragged onto it from the View Map.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.layout import (
    MM_PER_M,
    LayoutSheet,
    _create_layout,
    _drawings_by_name,
    _master_named,
    layout_from_views,
    layout_sheet,
    master_layouts,
)
from sun_study.archicad.site_analysis import (
    A1_MASTER,
    INK,
    Drawing,
    _attributes,
    _enter_layout,
    _flush_on_paper,
    _remove_layout,
)
from sun_study.archicad.sun_eyes import TITLE_BLOCK_MM, arrange_drawings
from sun_study.archicad.views import _by_name
from sun_study.report.area_table import SUBTITLE, TITLE, notes, rows
from sun_study.rules.area_yield import AreaSchedule

__all__ = [
    "AREA_WORD",
    "NON_RESIDENTIAL_COLOUR",
    "RESIDENTIAL_COLOUR",
    "AreaSheetReport",
    "area_drawing",
    "draw_area_sheet",
    "view_frame",
]

#: What the sheet is called, after the prefix.
AREA_WORD = "Area Calculation"

#: The legend's two colours, off the office's sheet.
RESIDENTIAL_COLOUR = "#FFF4A8"
NON_RESIDENTIAL_COLOUR = "#B894F2"

#: Paper millimetres from the sheet's usable corner to the table's.
MARGIN_MM = 15.0

#: How wide the table and its notes run, and the gap between them and the view.
TABLE_WIDTH_MM = 150.0
GAP_MM = 15.0

#: The narrowest a view is placed at: less than this is a stamp, not a picture.
LEAST_VIEW_MM = 80.0

# The table, in paper millimetres: the columns, the step between rows, and
# the text. Read off the office's sheet, where the table is set at 3.5 mm.
_LABEL_X, _COUNT_X, _PROPOSED_X, _TARGET_X = 0.0, 32.0, 56.0, 98.0
_BODY_MM, _STEP_MM, _GAP_ROW_MM = 3.5, 5.2, 2.6
_TITLE_MM, _NOTE_MM, _LEGEND_MM = 9.0, 3.2, 5.0

#: How far apart the lines that fill a legend swatch are, and how heavy, so
#: that on paper they read as the colour and not as stripes.
_SWATCH_PITCH_MM, _SWATCH_PEN_MM = 0.35, 0.35


def area_drawing(schedule: AreaSchedule, source: Sequence[str] = ()) -> Drawing:
    """The sheet's table, notes and legend, in paper metres, hanging down
    from ``(0, 0)`` at its top-left corner."""
    drawing = Drawing(1.0, AREA_WORD)
    mm = drawing.mm
    part = "Table"

    def text(value: str, x_mm: float, y_mm: float, height_mm: float = _BODY_MM) -> None:
        drawing.text(part, value, (mm(x_mm), mm(y_mm)), height_mm=height_mm, justification="Left")

    text(TITLE, 0.0, 0.0, _TITLE_MM)
    text(SUBTITLE, 0.0, -_TITLE_MM * 1.25, _TITLE_MM)
    y = -34.0
    for row in rows(schedule):
        if row.kind == "gap":
            y -= _GAP_ROW_MM
            continue
        text(row.label, _LABEL_X, y)
        text(row.count, _COUNT_X, y)
        text(row.proposed, _PROPOSED_X, y)
        text(row.target, _TARGET_X, y)
        y -= _STEP_MM

    y -= 10.0
    text("Notes:", 0.0, y, _NOTE_MM)
    for line in notes(schedule, source):
        y -= _NOTE_MM * 1.55
        text(line, 0.0, y, _NOTE_MM)

    y -= 14.0
    text("Legend", 0.0, y, _LEGEND_MM)
    for label, colour in (
        ("Residential", RESIDENTIAL_COLOUR),
        ("Non-Residential", NON_RESIDENTIAL_COLOUR),
    ):
        y -= 9.0
        _swatch(drawing, part, 0.0, y - 1.0, 8.0, 6.5, colour)
        text(label, 12.0, y + 0.8)
    return drawing


def _swatch(
    drawing: Drawing, part: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float, colour: str
) -> None:
    """A legend swatch: a small box filled with close lines in the colour.

    Lines rather than a fill, because the sheet is drawn with the rules and
    texts a layout takes from a request (``_flush_on_paper``); at a third of
    a millimetre apart and as heavy, they print as the colour.
    """
    mm = drawing.mm
    rows_ = max(1, round(h_mm / _SWATCH_PITCH_MM))
    for i in range(rows_ + 1):
        at = y_mm + h_mm * i / rows_
        drawing.line(
            part,
            [(mm(x_mm), mm(at)), (mm(x_mm + w_mm), mm(at))],
            colour=colour,
            weight_mm=_SWATCH_PEN_MM,
        )
    drawing.line(
        part,
        [
            (mm(x_mm), mm(y_mm)),
            (mm(x_mm + w_mm), mm(y_mm)),
            (mm(x_mm + w_mm), mm(y_mm + h_mm)),
            (mm(x_mm), mm(y_mm + h_mm)),
        ],
        colour=INK,
        closed=True,
    )


def view_frame(
    sheet: LayoutSheet, *, title_block_mm: float = TITLE_BLOCK_MM
) -> tuple[float, float, float, float] | None:
    """Where the massing view goes: the page right of the table, left of the
    title block, inside the margins, as ``(xMin, yMin, xMax, yMax)`` in
    metres. ``None`` on a sheet with no room for one."""
    x0 = sheet.left_mm + MARGIN_MM + TABLE_WIDTH_MM + GAP_MM
    x1 = sheet.width_mm - sheet.right_mm - title_block_mm - MARGIN_MM
    y0 = sheet.bottom_mm + MARGIN_MM
    y1 = sheet.height_mm - sheet.top_mm - MARGIN_MM
    if x1 - x0 < LEAST_VIEW_MM or y1 - y0 < LEAST_VIEW_MM:
        return None
    return (x0 / MM_PER_M, y0 / MM_PER_M, x1 / MM_PER_M, y1 / MM_PER_M)


def _tidy(name: str) -> str:
    return " ".join(name.split()).casefold()


def _view_named(connection: ArchicadConnection, wanted: str) -> tuple[str, str] | None:
    """The View Map item called this, as ``(navigator id, its own name)``."""
    for name, identifier in _by_name(connection, "PublicViewMap").items():
        if _tidy(name) == _tidy(wanted):
            return identifier, name
    return None


@dataclass(frozen=True)
class AreaSheetReport:
    """What went onto the sheet."""

    name: str
    database_id: str
    master: str
    lines: int
    texts: int
    view: str = ""
    notes: tuple[str, ...] = ()

    def describe(self) -> str:
        said = [
            f"  layout {self.name!r} on {self.master!r}: {self.texts} texts and "
            f"{self.lines} lines"
            + (f", with the view {self.view!r} beside the table" if self.view else "")
        ]
        said.extend(f"    {note}" for note in self.notes)
        return "\n".join(said)


def draw_area_sheet(
    connection: ArchicadConnection,
    schedule: AreaSchedule,
    *,
    source: Sequence[str] = (),
    master_layout: str | None = None,
    view: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
    say: Callable[[str], None] | None = None,
) -> AreaSheetReport:
    """The area calculation on a layout of its own, remade on every run.

    ``view`` names a 3D view (or any view) in the View Map to place beside
    the table. A view that is not there, or will not place, costs the
    picture and not the sheet: the run says so and the table is drawn.
    """
    name = naming.named(AREA_WORD)
    said: list[str] = []
    _remove_layout(connection, name)
    master = _master_named(master_layouts(connection), master_layout or A1_MASTER)

    database_id = ""
    placed = ""
    if view:
        found = _view_named(connection, view)
        if found is None:
            said.append(f"no view called {view!r} in the View Map; the sheet has the table alone.")
        else:
            identifier, exact = found
            try:
                report = layout_from_views(
                    connection, [(identifier, exact)], layout_name=name, master_layout=master.name
                )
                database_id, placed = report.database_id or "", exact
            except ArchicadError as error:
                said.append(f"the view {exact!r} could not be placed: {error}")
    if not database_id:
        database_id = _create_layout(connection, name, master)

    sheet, assumed = layout_sheet(connection, database_id)
    if assumed:
        said.append("the sheet size could not be read; an A1 is assumed.")
    if not _enter_layout(connection, database_id):
        raise ArchicadError(
            f"the layout {name!r} was made but could not be entered to draw on; "
            "open it in the Layout Book and run again."
        )
    left, top, _width, _height = sheet.usable
    x0 = (left + MARGIN_MM) / MM_PER_M
    y0 = (sheet.height_mm - top - MARGIN_MM) / MM_PER_M
    drawing = area_drawing(schedule, source).moved(x0, y0)
    attributes = _attributes(connection)
    if not attributes.pens:
        said.append("the pen table could not be read; lines take the tool's current pen.")
    lines, texts = _flush_on_paper(connection, drawing, attributes)
    if say:
        say(f"  {texts} texts and {lines} lines on the layout")

    if placed:
        frame = view_frame(sheet, title_block_mm=title_block_mm)
        drawings = _drawings_by_name(connection, database_id)
        if frame is None:
            said.append("the sheet has no room right of the table; the view is where it landed.")
        elif placed not in drawings:
            said.append(f"the view {placed!r} is not on the sheet after all.")
        else:
            try:
                guid = str(drawings[placed]["elementId"]["guid"])
                arrange_drawings(connection, database_id, [(guid, frame)])
            except (ArchicadError, KeyError, TypeError) as error:
                said.append(f"the view is on the sheet but could not be framed: {error}")
    return AreaSheetReport(
        name=name,
        database_id=database_id,
        master=master.name,
        lines=lines,
        texts=texts,
        view=placed,
        notes=tuple(said),
    )
