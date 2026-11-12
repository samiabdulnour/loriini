"""The QA export's spreadsheets: QA_Units, QA_Areas, QA_Parking and QA_Summary (D184).

The brief has them saved as interactive schedules and published to Excel.
Archicad's API can make neither a schedule nor a Publisher set, and the
figures are in hand here anyway, so the files are written straight from the
model: one row per apartment, per area zone and per parking space, with the
same columns, and a fourth file with the totals the council builds from them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from sun_study.archicad.qa_export import UNIT_FIELDS, QaZone, Summary, UnitRow
from sun_study.report.xlsx import Format, Sheet, write

HEAD = Format(bold=True, shaded=True)
AREA = Format(number="0.00")


def _sheet(name: str, headings: Sequence[str], widths: Sequence[float]) -> Sheet:
    sheet = Sheet(name=name, widths=tuple(widths), formats=[Format(), HEAD, AREA])
    for col, heading in enumerate(headings, start=1):
        sheet.text(1, col, heading, HEAD)
    return sheet


def _cell(sheet: Sheet, row: int, col: int, value: object) -> None:
    if isinstance(value, bool):
        sheet.text(row, col, "Yes" if value else "No")
    elif isinstance(value, int | float):
        sheet.number(row, col, float(value), AREA if isinstance(value, float) else Format())
    elif value is not None and str(value) != "":
        sheet.text(row, col, str(value))


def write_units(folder: Path, units: Sequence[UnitRow]) -> Path:
    fields = [spec.name for spec in UNIT_FIELDS]
    sheet = _sheet(
        "QA_Units",
        ["Zone name", "Zone number", "Home story", *fields],
        [14, 12, 16, *([14] * len(fields))],
    )
    for index, row in enumerate(units, start=2):
        _cell(sheet, index, 1, row.zone.name)
        _cell(sheet, index, 2, row.zone.number)
        _cell(sheet, index, 3, row.zone.storey)
        for col, name in enumerate(fields, start=4):
            _cell(sheet, index, col, row.values.get(name))
    return write(folder / "QA_Units.xlsx", sheet)


def write_areas(
    folder: Path,
    areas: Sequence[tuple[QaZone, str]],
    deep_soil: Mapping[str, str | None] | None = None,
) -> Path:
    sheet = _sheet(
        "QA_Areas",
        ["Zone name", "Home story", "Area", "Area Type", "Deep soil min. dimension"],
        [24, 16, 12, 22, 22],
    )
    for index, (zone, kind) in enumerate(areas, start=2):
        _cell(sheet, index, 1, zone.name)
        _cell(sheet, index, 2, zone.storey)
        _cell(sheet, index, 3, round(zone.area_m2, 2))
        _cell(sheet, index, 4, kind)
        _cell(sheet, index, 5, (deep_soil or {}).get(zone.guid))
    return write(folder / "QA_Areas.xlsx", sheet)


def write_parking(
    folder: Path,
    spaces: Sequence[tuple[QaZone, str]],
    allocated: Mapping[str, str | None] | None = None,
) -> Path:
    sheet = _sheet("QA_Parking", ["Home story", "Space Type", "Allocated to"], [16, 16, 16])
    for index, (zone, kind) in enumerate(spaces, start=2):
        _cell(sheet, index, 1, zone.storey)
        _cell(sheet, index, 2, kind)
        _cell(sheet, index, 3, (allocated or {}).get(zone.guid))
    return write(folder / "QA_Parking.xlsx", sheet)


def write_summary(folder: Path, totals: Summary, *, source: str) -> Path:
    sheet = _sheet("QA_Summary", ["", "Figure", "Against"], [36, 24, 26])
    sheet.text(2, 1, source)
    for index, (what, figure, against) in enumerate(totals.lines, start=4):
        _cell(sheet, index, 1, what)
        _cell(sheet, index, 2, figure)
        _cell(sheet, index, 3, against)
    return write(folder / "QA_Summary.xlsx", sheet)
