"""Communal open space, one schedule per Zone: the hour, the sunlit area, the share.

The office's COS drawing carries exactly this beside each plan -- a small table
headed ``L2 COS SOLAR ANALYSIS`` with a row per hour -- and until this module it
was typed up by hand from the plans. A run that measures five levels at once
sums them into one figure, which is the right answer to "how much of the
communal open space" and the wrong one to "how does *this* terrace do", so the
figures are split back out by the Zone each sample was cut from.

Written as an ``.xlsx`` rather than a CSV because the table is the deliverable:
the merged heading, the bold header row and the percentages formatted as
percentages are what gets pasted into the drawing. The workbook is assembled
from the standard library -- an ``.xlsx`` is a zip of a handful of XML parts --
because the project's runtime dependencies are an approved list and a
spreadsheet library is not on it.

Each percentage is a formula over the cells beside it *and* carries its value,
so the sheet recalculates when somebody edits an area in Excel, and still reads
correctly in a previewer that never calculates anything.
"""

from __future__ import annotations

import datetime as dt
import re
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "SHEET_NAME",
    "HourArea",
    "ZoneTable",
    "clock_label",
    "storey_label",
    "write_workbook",
    "zone_tables",
]

SHEET_NAME = "COS Solar Analysis"


@dataclass(frozen=True)
class HourArea:
    """One row of a schedule: an hour, and how much of the Zone is in sun at it."""

    at: dt.time
    area_m2: float


@dataclass(frozen=True)
class ZoneTable:
    """Everything one Zone's schedule shows."""

    title: str
    """What heads the table, e.g. ``L2 COS SOLAR ANALYSIS``."""
    storey: str | None
    area_m2: float
    hours: tuple[HourArea, ...]
    threshold_hours: float | None = None
    """The minimum the study asked about. ``None`` leaves that row off."""
    achieved_m2: float | None = None
    """Area receiving at least ``threshold_hours``."""


def storey_label(storey: str | None) -> str:
    """The short name a drawing uses: ``LEVEL 02`` is ``L2``.

    Only the ``LEVEL nn`` pattern is shortened, because it is the only one
    whose short form is not a guess. ``GROUND`` or ``ROOF TERRACE`` stay as
    they are, and a Zone the export put on no storey is ``COS``.
    """
    if not storey:
        return "COS"
    match = re.fullmatch(r"\s*(?:LEVEL|LVL|L)\s*0*(\d+)\s*", storey, flags=re.IGNORECASE)
    if match:
        return f"L{int(match.group(1))}"
    return storey.strip()


def clock_label(at: dt.time) -> str:
    """``9AM``, ``12PM``, ``3PM`` -- the way the schedules write the hour."""
    hour = at.hour % 12 or 12
    suffix = "AM" if at.hour < 12 else "PM"
    if at.minute:
        return f"{hour}:{at.minute:02d}{suffix}"
    return f"{hour}{suffix}"


def zone_tables(
    parent_ids: Sequence[str],
    areas: NDArray[np.float64],
    heights: NDArray[np.float64],
    sunlit: NDArray[np.bool_],
    times: Sequence[dt.datetime],
    *,
    storey_of: Callable[[str], str | None],
    name_of: Callable[[str], str],
    minutes: NDArray[np.float64] | None = None,
    threshold_hours: float | None = None,
) -> list[ZoneTable]:
    """One schedule per Zone, lowest first, on the whole hours the study cast.

    ``sunlit`` is samples by instants, as the study stored it; only the
    instants on the hour are tabled, so a 10-minute study still gives the
    seven rows a 09:00-15:00 schedule has and never an hour it did not
    measure. Zones are ordered by the height of their samples rather than by
    storey name, because ``LEVEL 11`` sorts before ``LEVEL 2`` as text.

    Two Zones on one storey get their own names after the level, since a
    schedule titled ``L2`` twice is two tables nobody can tell apart.
    """
    ids = np.asarray(parent_ids)
    on_the_hour = [
        (index, when_at.time())
        for index, when_at in enumerate(times)
        if when_at.minute == 0 and when_at.second == 0
    ]
    order = sorted(
        dict.fromkeys(parent_ids),
        key=lambda zone: float(heights[ids == zone].min()),
    )
    storeys = {zone: storey_of(zone) for zone in order}
    crowded = {storey for storey in storeys.values() if list(storeys.values()).count(storey) > 1}

    tables: list[ZoneTable] = []
    for zone in order:
        mask = ids == zone
        weights = areas[mask]
        label = storey_label(storeys[zone])
        if storeys[zone] in crowded:
            label = f"{label} {name_of(zone)}".strip()
        achieved: float | None = None
        if threshold_hours is not None and minutes is not None:
            achieved = float(weights[minutes[mask] >= threshold_hours * 60.0].sum())
        tables.append(
            ZoneTable(
                title=f"{label} COS SOLAR ANALYSIS",
                storey=storeys[zone],
                area_m2=float(weights.sum()),
                hours=tuple(
                    HourArea(at=at, area_m2=float(weights[sunlit[mask, index]].sum()))
                    for index, at in on_the_hour
                ),
                threshold_hours=threshold_hours if achieved is not None else None,
                achieved_m2=achieved,
            )
        )
    return tables


# ---------------------------------------------------------------------------
# The workbook. Style indices refer to the cellXfs list in _STYLES, in order.
# ---------------------------------------------------------------------------
(
    _PLAIN,
    _HEADING,
    _HEADER,
    _BODY,
    _AREA,
    _SHARE,
    _TOTAL,
    _TOTAL_AREA,
    _TOTAL_SHARE,
    _NOTE,
    _SHEET_TITLE,
) = range(11)

_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_OFFICE_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml"


def _xf(number: int, font: int, border: int, align: str = "") -> str:
    """One cell format: number format, font, border and horizontal alignment."""
    applies = ' applyNumberFormat="1"' if number else ""
    applies += ' applyFont="1"' if font else ""
    applies += ' applyBorder="1"' if border else ""
    head = f'<xf numFmtId="{number}" fontId="{font}" fillId="0" borderId="{border}" xfId="0"'
    if not align:
        return f"{head}{applies}/>"
    return f'{head}{applies} applyAlignment="1"><alignment horizontal="{align}"/></xf>'


def _font(size: int, *, bold: bool = False, italic: bool = False, grey: bool = False) -> str:
    return (
        "<font>"
        + ("<b/>" if bold else "")
        + ("<i/>" if italic else "")
        + f'<sz val="{size}"/>'
        + ('<color rgb="FF595959"/>' if grey else "")
        + '<name val="Arial"/><family val="2"/></font>'
    )


_EDGE = '<color rgb="FFBFBFBF"/>'
_BOX = "".join(
    f'<{side} style="thin">{_EDGE}</{side}>' for side in ("left", "right", "top", "bottom")
)
_PERCENT, _ONE_DECIMAL = 10, 164  # 10 is Excel's built-in 0.00%

# In the order of the style constants above: the index is the style.
_CELL_FORMATS = (
    _xf(0, 0, 0),  # plain
    _xf(0, 2, 1),  # table heading
    _xf(0, 1, 1, "center"),  # header row
    _xf(0, 0, 1),  # body text
    _xf(_ONE_DECIMAL, 0, 1, "left"),  # area
    _xf(_PERCENT, 0, 1, "left"),  # share
    _xf(0, 1, 1),  # total label
    _xf(_ONE_DECIMAL, 1, 1, "left"),  # total area
    _xf(_PERCENT, 1, 1, "left"),  # total share
    _xf(0, 3, 0),  # note
    _xf(0, 2, 0),  # sheet title
)

_STYLES = (
    _DECLARATION
    + f'<styleSheet xmlns="{_MAIN}">'
    + f'<numFmts count="1"><numFmt numFmtId="{_ONE_DECIMAL}" formatCode="0.0"/></numFmts>'
    + '<fonts count="4">'
    + _font(11)
    + _font(11, bold=True)
    + _font(12, bold=True)
    + _font(9, italic=True, grey=True)
    + "</fonts>"
    + '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    + '<fill><patternFill patternType="gray125"/></fill></fills>'
    + '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
    + f"<border>{_BOX}<diagonal/></border></borders>"
    + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    + f'<cellXfs count="{len(_CELL_FORMATS)}">{"".join(_CELL_FORMATS)}</cellXfs>'
    + '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    + "</styleSheet>\n"
)

_CONTENT_TYPES = (
    _DECLARATION
    + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    + '<Default Extension="rels" '
    + 'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    + '<Default Extension="xml" ContentType="application/xml"/>'
    + f'<Override PartName="/xl/workbook.xml" ContentType="{_OFFICE_TYPE}.sheet.main+xml"/>'
    + '<Override PartName="/xl/worksheets/sheet1.xml" '
    + f'ContentType="{_OFFICE_TYPE}.worksheet+xml"/>'
    + f'<Override PartName="/xl/styles.xml" ContentType="{_OFFICE_TYPE}.styles+xml"/>'
    + "</Types>\n"
)


def _relationships(*targets: tuple[str, str]) -> str:
    """A .rels part: each target with its relationship type."""
    return (
        _DECLARATION
        + f'<Relationships xmlns="{_PACKAGE_RELS}">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="{_DOC_RELS}/{kind}" Target="{target}"/>'
            for index, (kind, target) in enumerate(targets, start=1)
        )
        + "</Relationships>\n"
    )


_ROOT_RELS = _relationships(("officeDocument", "xl/workbook.xml"))
_WORKBOOK_RELS = _relationships(("worksheet", "worksheets/sheet1.xml"), ("styles", "styles.xml"))


def _workbook(sheet_name: str) -> str:
    name = escape(sheet_name, {'"': "&quot;"})
    return (
        _DECLARATION
        + f'<workbook xmlns="{_MAIN}" xmlns:r="{_DOC_RELS}">'
        + f'<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets>'
        + '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>\n'
    )


def _text(ref: str, value: str, style: int) -> str:
    body = f'<is><t xml:space="preserve">{escape(value)}</t></is>'
    return f'<c r="{ref}" s="{style}" t="inlineStr">{body}</c>'


def _number(ref: str, value: float, style: int) -> str:
    return f'<c r="{ref}" s="{style}"><v>{value:.6g}</v></c>'


def _formula(ref: str, formula: str, value: float, style: int) -> str:
    return f'<c r="{ref}" s="{style}"><f>{escape(formula)}</f><v>{value:.6g}</v></c>'


def _empty(ref: str, style: int) -> str:
    return f'<c r="{ref}" s="{style}"/>'


def write_workbook(
    destination: Path,
    tables: Sequence[ZoneTable],
    *,
    heading: str,
    notes: Sequence[str] = (),
    sheet_name: str = SHEET_NAME,
) -> None:
    """One sheet, one table per Zone stacked down it, under a heading and notes.

    The layout matches the office schedule: the Zone's title merged across the
    three columns, then TIME / AREA (sqm) / PERCENTAGE, a row per hour, and
    under them the Zone's own area and, when the study asked for a minimum,
    the area that reaches it. Areas are rounded to 0.1 m2 as written, so a
    percentage recalculated in Excel matches the one printed beside it.
    """
    rows: list[str] = []
    merges: list[str] = []

    def row(number: int, cells: list[str]) -> None:
        rows.append(f'<row r="{number}">{"".join(cells)}</row>')

    # Bold like a table's title, but unboxed: it names the sheet, not a table.
    row(1, [_text("A1", heading, _SHEET_TITLE)])
    line = 2
    for note in notes:
        row(line, [_text(f"A{line}", note, _NOTE)])
        line += 1
    line += 1

    for table in tables:
        title_row = line
        row(
            title_row,
            [
                _text(f"A{title_row}", table.title, _HEADING),
                _empty(f"B{title_row}", _HEADING),
                _empty(f"C{title_row}", _HEADING),
            ],
        )
        merges.append(f"A{title_row}:C{title_row}")
        header_row = title_row + 1
        row(
            header_row,
            [
                _text(f"A{header_row}", "TIME", _HEADER),
                _text(f"B{header_row}", "AREA (sqm)", _HEADER),
                _text(f"C{header_row}", "PERCENTAGE", _HEADER),
            ],
        )
        first = header_row + 1
        total_row = first + len(table.hours)
        total = round(table.area_m2, 1)
        for offset, hour in enumerate(table.hours):
            at = first + offset
            area = round(hour.area_m2, 1)
            row(
                at,
                [
                    _text(f"A{at}", clock_label(hour.at), _BODY),
                    _number(f"B{at}", area, _AREA),
                    _formula(
                        f"C{at}",
                        f"IF($B${total_row}=0,0,B{at}/$B${total_row})",
                        area / total if total else 0.0,
                        _SHARE,
                    ),
                ],
            )
        row(
            total_row,
            [
                _text(f"A{total_row}", "COS AREA", _TOTAL),
                _number(f"B{total_row}", total, _TOTAL_AREA),
                _formula(
                    f"C{total_row}", f"IF(B{total_row}=0,0,1)", 1.0 if total else 0.0, _TOTAL_SHARE
                ),
            ],
        )
        line = total_row + 1
        if table.threshold_hours is not None and table.achieved_m2 is not None:
            achieved = round(table.achieved_m2, 1)
            row(
                line,
                [
                    _text(f"A{line}", f"{table.threshold_hours:g} HRS OR MORE", _TOTAL),
                    _number(f"B{line}", achieved, _TOTAL_AREA),
                    _formula(
                        f"C{line}",
                        f"IF($B${total_row}=0,0,B{line}/$B${total_row})",
                        achieved / total if total else 0.0,
                        _TOTAL_SHARE,
                    ),
                ],
            )
            line += 1
        line += 2

    merge_xml = (
        f'<mergeCells count="{len(merges)}">'
        + "".join(f'<mergeCell ref="{ref}"/>' for ref in merges)
        + "</mergeCells>"
        if merges
        else ""
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>'
        '<cols><col min="1" max="1" width="22" customWidth="1"/>'
        '<col min="2" max="2" width="18" customWidth="1"/>'
        '<col min="3" max="3" width="16" customWidth="1"/></cols>'
        f"<sheetData>{''.join(rows)}</sheetData>{merge_xml}</worksheet>\n"
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _CONTENT_TYPES)
        package.writestr("_rels/.rels", _ROOT_RELS)
        package.writestr("xl/workbook.xml", _workbook(sheet_name))
        package.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        package.writestr("xl/styles.xml", _STYLES)
        package.writestr("xl/worksheets/sheet1.xml", sheet)
