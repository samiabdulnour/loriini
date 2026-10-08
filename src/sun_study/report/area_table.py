"""The preliminary yield analysis as a table: the sheet's rows, its notes,
the workbook.

The rows are the office's feasibility sheet -- *Preliminary Yield
Analysis* -- in its order and its words: the site, the FSR and the GFA by
use against the permissible, the market and affordable unit mixes, the
storeys, the parking, and the efficiencies the figures were worked with.
One list of rows serves three readers, so they cannot disagree: the sheet
Loriini draws on a layout, the lines the command prints, and the workbook.

The workbook is the office's template, filled. Its cells are the template's
cells -- the site in C6, the permissible FSR in C10:C12, the storey table
from J113 -- so that somebody who knows the template finds everything where
it was; the inputs are red, as the template has them, and everything else
is a formula over them and over the storeys' measured BEA, so a what-if on
an efficiency, a share or a rate is typed into Excel rather than rerun.
One sheet per option: a run adds its option beside the ones already in the
workbook, which it reads back from a hidden sheet that keeps each option's
data.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sun_study.report import feasibility_style as look
from sun_study.report import xlsx
from sun_study.rules.area_yield import (
    AFFORDABLE_MIX,
    COMMERCIAL,
    LABELS,
    RESIDENTIAL,
    RETAIL,
    USES,
    Efficiencies,
    Feasibility,
    Level,
    Mix,
    ParkingRates,
    Permissible,
    UnitRates,
    UnitType,
)

__all__ = [
    "DATA_SHEET",
    "SUBTITLE",
    "TITLE",
    "TableRow",
    "count",
    "factor",
    "feasibility_from_dict",
    "feasibility_to_dict",
    "m2",
    "notes",
    "options_in",
    "percent",
    "rows",
    "text_lines",
    "write_workbook",
]

TITLE = "PRELIMINARY YIELD ANALYSIS"
SUBTITLE = "Feasibility"
#: The hidden sheet that carries each option's data, so a run can add to the book.
DATA_SHEET = "Loriini"


def m2(value: float) -> str:
    """An area the way the sheet writes one: ``14,607 m²``."""
    return f"{value:,.0f} m²"


def factor(value: float) -> str:
    """A factor or a ratio as typed: ``0.725``, ``0.9``."""
    return f"{value:g}"


def percent(value: float) -> str:
    """A share as the sheet writes one: ``15 %``."""
    return f"{value * 100:.0f} %"


def count(value: float | None) -> str:
    """A count of units or spaces as the sheet has it: to one decimal."""
    return "-" if value is None else f"{value:.1f}"


def _fsr(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _diff(proposed: float | None, permissible: float | None, how: str) -> str:
    if proposed is None or permissible is None:
        return ""
    difference = proposed - permissible
    text = _fsr(difference) if how == "fsr" else m2(difference)
    return f"+{text}" if difference > 0 else text


@dataclass(frozen=True)
class TableRow:
    """One line of the table: a heading, a figure, or the gap between groups."""

    kind: Literal["head", "row", "gap", "section", "total"]
    label: str = ""
    cells: tuple[str, str, str] = ("", "", "")


def rows(sheet: Feasibility) -> list[TableRow]:
    """The table, top to bottom, as the office's sheet has it."""
    out: list[TableRow] = []

    def row(label: str, *cells: str, kind: Literal["row", "total"] = "row") -> None:
        filled = tuple(cells) + ("",) * (3 - len(cells))
        out.append(TableRow(kind, label, filled[:3]))  # type: ignore[arg-type]

    site = m2(sheet.site_area_m2) if sheet.site_area_m2 else "-"
    out.append(TableRow("section", "Site Area", (site, "", "")))

    out.append(TableRow("gap"))
    out.append(TableRow("section", "FSR"))
    out.append(TableRow("head", "", ("Permissible", "Proposed", "Difference")))
    for use in USES:
        allowed = sheet.permissible.fsr(use)
        row(
            f"{LABELS[use]} FSR",
            _fsr(allowed) if allowed is not None else "",
            _fsr(sheet.fsr(use)),
            _diff(sheet.fsr(use), allowed, "fsr"),
        )
    allowed_total = sheet.permissible.total
    row(
        "Total FSR",
        _fsr(allowed_total) if allowed_total is not None else "",
        _fsr(sheet.total_fsr),
        _diff(sheet.total_fsr, allowed_total, "fsr"),
        kind="total",
    )

    out.append(TableRow("gap"))
    out.append(TableRow("section", "GFA"))
    out.append(TableRow("head", "", ("Permissible", "Proposed", "Difference")))
    for use in USES:
        allowed = sheet.permissible_gfa(use)
        row(
            f"{LABELS[use]} GFA",
            m2(allowed) if allowed is not None else "",
            m2(sheet.gfa(use)),
            _diff(sheet.gfa(use), allowed, "m2"),
        )
    allowed_gfa = sheet.total_permissible_gfa_m2
    row(
        "Total GFA",
        m2(allowed_gfa) if allowed_gfa is not None else "",
        m2(sheet.total_gfa_m2),
        _diff(sheet.total_gfa_m2, allowed_gfa, "m2"),
        kind="total",
    )

    out.append(TableRow("gap"))
    out.append(TableRow("section", "Residential GFA Split"))
    row("Market Unit", percent(sheet.market_share))
    row("Affordable Unit", percent(sheet.affordable_share))

    for title, mix, proposed, at_permissible in (
        ("Market Unit Mix", sheet.market, sheet.market_units, sheet.permissible_market_units),
        (
            "Affordable Unit Mix",
            sheet.affordable,
            sheet.affordable_units,
            sheet.permissible_affordable_units,
        ),
    ):
        if title.startswith("Affordable") and not sheet.affordable_share:
            continue
        out.append(TableRow("gap"))
        out.append(TableRow("section", title))
        out.append(TableRow("head", "", ("Size / Mix", "Permissible GFA", "Proposed GFA")))
        for i, (unit, now) in enumerate(zip(mix.types, proposed, strict=True)):
            row(
                unit.name,
                f"{unit.size_m2:g} m² / {percent(unit.share)}",
                count(at_permissible[i]) if at_permissible is not None else "",
                count(now),
            )
        row(
            "Total",
            "",
            count(sum(at_permissible)) if at_permissible is not None else "",
            count(sum(proposed)),
            kind="total",
        )

    out.append(TableRow("gap"))
    out.append(TableRow("section", "Number of Storeys"))
    row("Residential", str(sheet.residential_storeys))
    row("Podium", str(sheet.podium_storeys))
    row("Total", str(sheet.residential_storeys + sheet.podium_storeys), kind="total")

    out.append(TableRow("gap"))
    out.append(TableRow("section", "Parking Requirements"))
    out.append(TableRow("head", "", ("", "SEPP", "DCP")))
    sepp, dcp = sheet.parking_spaces("sepp"), sheet.parking_spaces("dcp")
    for unit, rates in zip(sheet.market.types, sheet.parking.market, strict=True):
        key = f"market {unit.name}"
        row(unit.name, f"{rates.sepp:g} / {rates.dcp:g} a unit", count(sepp[key]), count(dcp[key]))
    if sheet.affordable_share:
        for unit, rates in zip(sheet.affordable.types, sheet.parking.affordable, strict=True):
            key = f"affordable {unit.name}"
            row(
                f"{unit.name} (affordable)",
                f"{rates.sepp:g} / {rates.dcp:g} a unit",
                count(sepp[key]),
                count(dcp[key]),
            )
    visitors = sheet.parking.visitors
    row(
        "Visitors",
        f"{visitors.sepp:g} / {visitors.dcp:g} a unit",
        count(sepp["visitors"]),
        count(dcp["visitors"]),
    )
    row(
        "Total Residential", "", count(sepp["residential"]), count(dcp["residential"]), kind="total"
    )
    for use, rates in ((COMMERCIAL, sheet.parking.commercial), (RETAIL, sheet.parking.retail)):
        row(
            LABELS[use],
            f"1/{1 / rates.sepp:g} / 1/{1 / rates.dcp:g} m²" if rates.sepp and rates.dcp else "",
            count(sepp[use]),
            count(dcp[use]),
        )
    row("Total Parking", "", count(sepp["total"]), count(dcp["total"]), kind="total")
    row(
        "Total Basements",
        "",
        count(sheet.basements("sepp")),
        count(sheet.basements("dcp")),
        kind="total",
    )
    return out


def notes(sheet: Feasibility, source: Sequence[str] = ()) -> list[str]:
    """The notes under the table: the efficiencies the figures were worked
    with, the mix's averages, the parking efficiencies, and where the BEA
    came from."""
    e = sheet.efficiencies
    lines = [
        "Building efficiencies (BEA to GFA / GFA to NLA) : "
        + ", ".join(f"{LABELS[use]} {factor(e.gfa(use))} / {factor(e.nla(use))}" for use in USES),
        f"Market units : average NLA {sheet.market.average_nla_m2:.1f} m², "
        f"average GFA {sheet.market.average_gfa_m2(e):.1f} m²",
    ]
    if sheet.affordable_share:
        lines.append(
            f"Affordable units : average NLA {sheet.affordable.average_nla_m2:.1f} m², "
            f"average GFA {sheet.affordable.average_gfa_m2(e):.1f} m²"
        )
    lines.append(
        f"Parking : {sheet.parking.sqm_per_space:g} m² a space, basement over "
        f"{percent(sheet.parking.basement_site_ratio)} of the site"
    )
    lines.extend(source or sheet.source)
    return lines


def text_lines(sheet: Feasibility) -> list[str]:
    """The table as the command prints it, in columns."""
    out: list[str] = []
    for row in rows(sheet):
        if row.kind == "gap":
            out.append("")
            continue
        a, b, c = row.cells
        label = row.label.upper() if row.kind == "section" else row.label
        out.append(f"  {label:<24}{a:>22}{b:>18}{c:>18}".rstrip())
    return out


# -- the workbook -------------------------------------------------------------------

_INPUT_RED = "FF0000"
_HEAD_GREEN = "65A368"
_ACCOUNTING = '_-* #,##0_-;\\-* #,##0_-;_-* "-"??_-;_-@_-'

_TITLE = xlsx.Format(size=12)
_OPTION = xlsx.Format(size=18, bold=True, colour=_INPUT_RED)
_SECTION = xlsx.Format(size=12, bold=True, fill=_HEAD_GREEN)
_SUBSECTION = xlsx.Format(size=12, bold=True)
_HEAD = xlsx.Format(size=10, bold=True)
_HEAD_CENTRE = xlsx.Format(size=10, bold=True, align="center")
_LABEL = xlsx.Format(size=10)
_TOTAL_LABEL = xlsx.Format(size=10, bold=True)
_NOTE = xlsx.Format(size=8, italic=True, grey=True)
_UNIT = xlsx.Format(size=10)
_IN = xlsx.Format(size=10, colour=_INPUT_RED)
_IN_RATIO = xlsx.Format(number="0.00", size=10, colour=_INPUT_RED)
_IN_SHARE = xlsx.Format(number="0%", size=10, colour=_INPUT_RED)
_IN_COUNT = xlsx.Format(number="0", size=10, colour=_INPUT_RED)
_IN_AREA = xlsx.Format(number=_ACCOUNTING, size=10, colour=_INPUT_RED)
_IN_RATE = xlsx.Format(number="0.000", size=10, colour=_INPUT_RED)
_IN_RATE4 = xlsx.Format(number="0.0000", size=10, colour=_INPUT_RED)
_RATIO = xlsx.Format(number="0.00", size=10)
_RATIO_BOLD = xlsx.Format(number="0.00", size=10, bold=True)
_AREA = xlsx.Format(number=_ACCOUNTING, size=10)
_AREA_BOLD = xlsx.Format(number=_ACCOUNTING, size=10, bold=True)
_UNITS = xlsx.Format(number="0.0", size=10)
_UNITS_BOLD = xlsx.Format(number="0.0", size=10, bold=True)
_SHARE = xlsx.Format(number="0%", size=10)
_SHARE_BOLD = xlsx.Format(number="0%", size=10, bold=True)
_SHARE1 = xlsx.Format(number="0.0%", size=10)
_COUNT = xlsx.Format(number="0", size=10)
_COUNT_BOLD = xlsx.Format(number="0", size=10, bold=True)
_PLAIN = xlsx.Format(size=10)
_PLAIN_BOLD = xlsx.Format(size=10, bold=True)

#: The storey table's first column (J) and first row, as the template has them.
_TABLE_COL = 10
_TABLE_ROW = 111


def _col(index: int) -> str:
    return xlsx.column(index)


def write_workbook(
    destination: Path, sheet: Feasibility, *, note: str = "", keep_others: bool = True
) -> Path:
    """The office's feasibility template, filled from this option, as a live
    workbook: one sheet per option, this one added to, or replacing, the
    option of the same name already in the workbook at ``destination``.

    A workbook at ``destination`` that Loriini did not write is left alone,
    and ``FileExistsError`` says so: the office's own template is not to be
    overwritten by a tool.
    """
    others: list[Feasibility] = []
    if destination.exists():
        if DATA_SHEET not in xlsx.sheet_names(destination):
            raise FileExistsError(
                f"{destination} is a workbook Loriini did not write; name another file "
                "for the yield analysis, or move that one aside."
            )
        if keep_others:
            others = [
                found
                for found in options_in(destination)
                if found.option.casefold() != sheet.option.casefold()
            ]
    options = [*others, sheet]
    book = xlsx.Workbook(raw_styles=look.STYLES_XML, theme=look.THEME_XML)
    for option in options:
        _option_sheet(book.sheet(option.option), option, note)
    data = book.sheet(DATA_SHEET, (120,), hidden=True)
    data.text(1, 1, json.dumps([feasibility_to_dict(option) for option in options]), _NOTE)
    data.text(
        2,
        1,
        "Loriini keeps each option's data here so a later run can add an option beside "
        "the ones already in this workbook. Leave it be.",
        _NOTE,
    )
    return book.write(destination)


def options_in(path: Path) -> list[Feasibility]:
    """The options a workbook Loriini wrote holds, in its order; empty for
    any other file."""
    text = xlsx.read_text(path, DATA_SHEET, "A1")
    if not text:
        return []
    try:
        listed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(listed, list):
        return []
    found: list[Feasibility] = []
    for item in listed:
        if isinstance(item, dict):
            try:
                found.append(feasibility_from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
    return found


class _TemplateSheet:
    """A sheet written as the template is styled.

    Every cell Loriini writes stands for a cell of the template, and takes
    that cell's style index: the same row for the blocks that do not move,
    a role's row for the ones that do -- a mix of six types has a sixth row
    styled like the second -- and the storey table's first, middle and last
    level rows for however many levels the massing has. The ``Format`` the
    caller names is ignored; the look is the template's. When the sheet is
    finished, every template cell in a mapped row that was not written is
    written blank with its style, so the boxes close and the bars run
    across.
    """

    def __init__(self, raw: xlsx.Sheet) -> None:
        self.raw = raw
        self.rows: dict[int, int] = {}
        """My row -> the template's row."""
        self.cols: dict[int, int] = {}
        """My column -> the template's column, where they differ."""

    def _style(self, row: int, col: int) -> int:
        template_row = self.rows.get(row, row)
        template_col = self.cols.get(col, col)
        return look.CELLS.get(f"{xlsx.column(template_col)}{template_row}", 0)

    def text(self, row: int, col: int, value: str, _look: object = None) -> None:
        self.raw.text(row, col, value, self._style(row, col))

    def number(self, row: int, col: int, value: float, _look: object = None) -> None:
        self.raw.number(row, col, value, self._style(row, col))

    def blank(self, row: int, col: int, _look: object = None) -> None:
        self.raw.blank(row, col, self._style(row, col))

    def formula(
        self, row: int, col: int, formula: str, value: float | str, _look: object = None
    ) -> None:
        self.raw.formula(row, col, formula, value, self._style(row, col))

    def merge(self, first: str, last: str) -> None:
        self.raw.merge(first, last)

    def finish(self, last_main_row: int, main_cols: int, table_cols: range) -> None:
        """The rest of the template's look: its blank styled cells, its
        column widths, its row heights, its zoom, its print area."""
        by_template_row: dict[int, dict[int, int]] = {}
        for ref, style in look.CELLS.items():
            letters = ref.rstrip("0123456789")
            number = int(ref[len(letters) :])
            col = 0
            for ch in letters:
                col = col * 26 + ord(ch) - ord("A") + 1
            by_template_row.setdefault(number, {})[col] = style
        mine_for: dict[int, list[int]] = {}
        for col in table_cols:
            mine_for.setdefault(self.cols.get(col, col), []).append(col)
        for row, template_row in self.rows.items():
            for template_col, style in by_template_row.get(template_row, {}).items():
                if row <= last_main_row and template_col <= main_cols:
                    targets = [template_col]
                elif row > last_main_row:
                    targets = mine_for.get(template_col, [])
                else:
                    continue
                for col in targets:
                    if not self.raw.has(row, col):
                        self.raw.blank(row, col, style)
            if template_row in look.ROW_HEIGHTS:
                self.raw.row_heights[row] = look.ROW_HEIGHTS[template_row]
        self.raw.cols_xml = look.COLS_XML
        self.raw.zoom = 85
        self.raw.print_area = f"$A$3:$E${last_main_row}"


def _option_sheet(raw: xlsx.Sheet, sheet: Feasibility, note: str) -> None:
    """One option on one sheet, cell for cell as the template has it."""
    ws = _TemplateSheet(raw)
    market, affordable = sheet.market.types, sheet.affordable.types
    n_market, n_affordable = len(market), len(affordable)
    e = sheet.efficiencies

    # -- where everything lands, worked out first: the template's rows for a
    # five-type mix, moving down when a mix has more types.
    site_row = 6
    fsr_head, fsr_first = 9, 10  # residential, commercial, retail; total after
    fsr_total = fsr_first + 3
    gfa_head, gfa_first = 16, 17
    gfa_total = gfa_first + 3
    split_head = 22
    market_share_row, affordable_share_row = 23, 24
    market_title = 26
    market_head = 28
    market_first = 29
    market_total = market_first + n_market
    affordable_title = market_total + 2
    affordable_head = affordable_title + 1
    affordable_first = affordable_head + 1
    affordable_total = affordable_first + n_affordable
    all_title = affordable_total + 2
    all_head = all_title + 1
    all_first = all_head + 1
    all_total = all_first + max(n_market, n_affordable)
    storeys_title = all_total + 2
    storeys_resi, storeys_podium, storeys_total = (
        storeys_title + 2,
        storeys_title + 3,
        storeys_title + 4,
    )
    parking_title = storeys_total + 2
    parking_head1, parking_head2 = parking_title + 1, parking_title + 2
    market_parking_head = parking_head2 + 1
    market_parking_first = market_parking_head + 1
    affordable_parking_head = market_parking_first + n_market
    affordable_parking_first = affordable_parking_head + 1
    visitors_row = affordable_parking_first + n_affordable + 1
    resi_parking_total = visitors_row + 2
    commercial_parking, retail_parking = resi_parking_total + 1, resi_parking_total + 2
    parking_total, basements_row = resi_parking_total + 3, resi_parking_total + 4
    eff_title = basements_row + 2
    eff_head = eff_title + 1
    eff_first = eff_head + 1  # residential, commercial, retail
    market_eff_title = eff_first + 5
    market_avg_nla, market_avg_gfa = market_eff_title + 1, market_eff_title + 5
    affordable_eff_title = market_avg_gfa + 2
    affordable_avg_nla, affordable_avg_gfa = affordable_eff_title + 1, affordable_eff_title + 5
    parking_eff_title = affordable_avg_gfa + 2
    sqm_row, basement_ratio_row = parking_eff_title + 1, parking_eff_title + 2

    # The storey table: J111 on, the levels top down, a total, and the
    # summary rows beneath.
    t = _TABLE_ROW
    tc = _TABLE_COL
    levels = tuple(reversed(sheet.levels))  # top down, as the sheet reads
    level_first = t + 4
    level_last = level_first + len(levels) - 1
    level_total = level_last + 1
    summary_head = level_total + 2
    target_row, proposed_row, difference_row = summary_head + 1, summary_head + 2, summary_head + 3
    # Columns of the storey table.
    c_level, c_f2f, c_height = tc, tc + 1, tc + 2
    c_bea = tc + 3  # resi, comm, retail, total
    c_gfa = c_bea + 4
    c_nsa = c_gfa + 4
    c_mix = c_nsa + 6  # one per market type, then total; the column before is labels
    c_adg = c_mix + n_market + 1  # C Vent, Solar >2hr, <2hr, 0hr
    c_back = c_adg + 5  # GBA, GFA, NLA from the mix
    c_diff = c_back + 4

    site = f"$C${site_row}"
    gfa_cell = {use: f"$D${gfa_first + i}" for i, use in enumerate(USES)}
    eff_gfa = {use: f"$C${eff_first + i}" for i, use in enumerate(USES)}
    eff_nla = {use: f"$E${eff_first + i}" for i, use in enumerate(USES)}

    # -- which template cell each of mine stands for ------------------------------
    rows_map: dict[int, int] = {row: row for row in range(1, market_first)}

    def map_block(mine_first: int, template_first: int, count: int, template_count: int) -> None:
        for i in range(count):
            rows_map[mine_first + i] = template_first + min(i, template_count - 1)

    map_block(market_first, 29, n_market, 5)
    rows_map[market_total] = 34
    rows_map[market_total + 1] = 35
    rows_map[affordable_title] = 36
    rows_map[affordable_head] = 37
    map_block(affordable_first, 38, n_affordable, 5)
    rows_map[affordable_total] = 43
    rows_map[affordable_total + 1] = 44
    rows_map[all_title] = 45
    rows_map[all_head] = 46
    map_block(all_first, 47, all_total - all_first, 5)
    rows_map[all_total] = 52
    rows_map[all_total + 1] = 53
    for offset, template_row in enumerate((54, 55, 56, 57, 58, 59, 60, 61, 62, 63)):
        rows_map[storeys_title + offset] = template_row
    map_block(market_parking_first, 64, n_market, 5)
    rows_map[affordable_parking_head] = 69
    map_block(affordable_parking_first, 70, n_affordable, 5)
    rows_map[visitors_row - 1] = 75
    rows_map[visitors_row] = 76
    rows_map[visitors_row + 1] = 77
    for offset, template_row in enumerate(range(78, 108)):
        rows_map[resi_parking_total + offset] = template_row
    for offset in range(4):
        rows_map[t + offset] = _TABLE_ROW + offset
    for i in range(len(levels)):
        rows_map[level_first + i] = 115 if i == 0 else (135 if i == len(levels) - 1 else 116)
    rows_map[level_total] = 136
    rows_map[level_total + 1] = 137
    for offset, template_row in enumerate((138, 139, 140, 141)):
        rows_map[summary_head + offset] = template_row
    ws.rows.update(rows_map)
    cols_map: dict[int, int] = {}
    for j in range(n_market):
        cols_map[c_mix + j] = 27 + min(j, 4)  # AA to AE
    cols_map[c_mix + n_market] = 32  # AF
    for j in range(4):
        cols_map[c_adg + j] = 33 + j  # AG to AJ
    cols_map[c_adg + 4] = 37  # AK, the gap
    for j in range(3):
        cols_map[c_back + j] = 38 + j  # AL to AN
    cols_map[c_back + 3] = 41  # AO, the gap
    cols_map[c_diff] = 42  # AP
    ws.cols.update(cols_map)

    # -- the head of the sheet ------------------------------------------------
    ws.text(1, 1, "Preliminary Yield Analysis", _TITLE)
    ws.text(3, 1, sheet.option, _OPTION)
    if note:
        ws.text(2, 1, note, _NOTE)

    def section(row: int, title: str) -> None:
        ws.text(row, 1, title, _SECTION)
        for col in range(2, 6):
            ws.blank(row, col, _SECTION)
        ws.merge(f"A{row}", f"E{row}")

    section(5, "Site Area")
    if sheet.site_area_m2:
        ws.number(site_row, 3, sheet.site_area_m2, _IN)
    else:
        ws.blank(site_row, 3, _IN)
    ws.text(site_row, 4, "sqm", _LABEL)
    ws.text(site_row, 7, "introduce site area", _NOTE)

    # -- FSR ------------------------------------------------------------------
    section(8, "FSR")
    for col, head in enumerate(("Permissible", "Proposed", "Difference"), start=3):
        ws.text(fsr_head, col, head, _HEAD)
    for i, use in enumerate(USES):
        row = fsr_first + i
        ws.text(row, 1, f"{LABELS[use]} FSR", _LABEL)
        allowed = sheet.permissible.fsr(use)
        if allowed is not None:
            ws.number(row, 3, allowed, _IN_RATIO)
        else:
            ws.blank(row, 3, _IN_RATIO)
        fsr = sheet.fsr(use)
        ws.formula(
            row,
            4,
            f'IF({site}>0,D{gfa_first + i}/{site},"")',
            fsr if fsr is not None else "",
            _RATIO,
        )
        diff = _value_diff(fsr, allowed)
        ws.formula(row, 5, f'IF(AND(D{row}<>"",C{row}<>""),D{row}-C{row},"")', diff, _RATIO)
    ws.text(fsr_head + 1, 7, "introduce permissible FSR", _NOTE)
    ws.text(fsr_total, 1, "Total FSR", _TOTAL_LABEL)
    total_allowed = sheet.permissible.total
    ws.formula(
        fsr_total,
        3,
        f"SUM(C{fsr_first}:C{fsr_first + 2})",
        total_allowed if total_allowed is not None else 0.0,
        _RATIO_BOLD,
    )
    total_fsr = sheet.total_fsr
    ws.formula(
        fsr_total,
        4,
        f"SUM(D{fsr_first}:D{fsr_first + 2})",
        total_fsr if total_fsr is not None else 0.0,
        _RATIO_BOLD,
    )
    ws.formula(
        fsr_total,
        5,
        f"SUM(E{fsr_first}:E{fsr_first + 2})",
        _value_diff(total_fsr, total_allowed) if total_allowed is not None else 0.0,
        _RATIO_BOLD,
    )

    # -- GFA ------------------------------------------------------------------
    section(15, "GFA")
    for col, head in enumerate(("Permissible", "Proposed", "Difference"), start=3):
        ws.text(gfa_head, col, head, _HEAD)
    for i, use in enumerate(USES):
        row = gfa_first + i
        ws.text(row, 1, f"{LABELS[use]} GFA", _LABEL)
        allowed = sheet.permissible_gfa(use)
        ws.formula(
            row,
            3,
            f'IF(C{fsr_first + i}<>"",{site}*C{fsr_first + i},"")',
            allowed if allowed is not None else "",
            _AREA,
        )
        ws.formula(row, 4, f"{_col(c_gfa + i)}{level_total}", sheet.gfa(use), _AREA)
        ws.formula(
            row,
            5,
            f'IF(C{row}<>"",D{row}-C{row},"")',
            _value_diff(sheet.gfa(use), allowed),
            _AREA,
        )
    ws.text(gfa_total, 1, "Total GFA", _TOTAL_LABEL)
    allowed_total = sheet.total_permissible_gfa_m2
    ws.formula(
        gfa_total,
        3,
        f"SUM(C{gfa_first}:C{gfa_first + 2})",
        allowed_total if allowed_total is not None else 0.0,
        _AREA_BOLD,
    )
    ws.formula(gfa_total, 4, f"SUM(D{gfa_first}:D{gfa_first + 2})", sheet.total_gfa_m2, _AREA_BOLD)
    ws.formula(
        gfa_total,
        5,
        f"SUM(E{gfa_first}:E{gfa_first + 2})",
        _value_diff(sheet.total_gfa_m2, allowed_total) if allowed_total is not None else 0.0,
        _AREA_BOLD,
    )

    # -- the split ------------------------------------------------------------
    section(split_head, "Residential GFA Split")
    ws.text(market_share_row, 1, "Market Unit", _LABEL)
    ws.formula(market_share_row, 3, f"1-C{affordable_share_row}", sheet.market_share, _SHARE)
    ws.text(affordable_share_row, 1, "Affordable Unit", _LABEL)
    ws.number(affordable_share_row, 3, sheet.affordable_share, _IN_SHARE)

    # -- the mixes --------------------------------------------------------------
    section(market_title, "Market Unit Mix")

    def mix_block(
        title_row: int,
        head_row: int,
        first: int,
        total: int,
        mix: Sequence[UnitType],
        share_row: int,
        avg_gfa_row: int,
        proposed: Sequence[float],
        allowed: Sequence[float] | None,
    ) -> None:
        ws.text(title_row, 2, title_row_name[title_row], _SUBSECTION)
        ws.merge(f"B{title_row}", f"E{title_row}")
        for col, head in enumerate(("Size", "Mix", "Permisible GFA", "Proposed GFA"), start=2):
            ws.text(head_row, col, head, _HEAD)
        for i, unit in enumerate(mix):
            row = first + i
            ws.text(row, 1, unit.name, _UNIT)
            ws.number(row, 2, unit.size_m2, _IN)
            ws.number(row, 3, unit.share, _IN_SHARE)
            gfa_allowed = f"$C${gfa_first}"
            ws.formula(
                row,
                4,
                f'IF({gfa_allowed}<>"",{gfa_allowed}/$C${avg_gfa_row}*C{row}*$C${share_row},"")',
                allowed[i] if allowed is not None else "",
                _UNITS,
            )
            ws.formula(
                row,
                5,
                f"{gfa_cell[RESIDENTIAL]}/$C${avg_gfa_row}*C{row}*$C${share_row}",
                proposed[i],
                _UNITS,
            )
        last = first + len(mix) - 1
        ws.text(total, 1, "Total", _TOTAL_LABEL)
        ws.formula(total, 3, f"SUM(C{first}:C{last})", sum(u.share for u in mix), _SHARE_BOLD)
        ws.formula(
            total,
            4,
            f"SUM(D{first}:D{last})",
            sum(allowed) if allowed is not None else 0.0,
            _UNITS_BOLD,
        )
        ws.formula(total, 5, f"SUM(E{first}:E{last})", sum(proposed), _UNITS_BOLD)

    title_row_name = {market_title + 1: "Market Unit Mix", affordable_title: "Affordable Unit Mix"}
    mix_block(
        market_title + 1,
        market_head,
        market_first,
        market_total,
        market,
        market_share_row,
        market_avg_gfa,
        sheet.market_units,
        sheet.permissible_market_units,
    )
    mix_block(
        affordable_title,
        affordable_head,
        affordable_first,
        affordable_total,
        affordable,
        affordable_share_row,
        affordable_avg_gfa,
        sheet.affordable_units,
        sheet.permissible_affordable_units,
    )

    # -- every unit --------------------------------------------------------------
    section(all_title, "Total Unit Mix")
    for col, head in enumerate(("Permisible GFA", "Proposed GFA", "Proof of concept"), start=3):
        ws.text(all_head, col, head, _HEAD)
    names = list(dict.fromkeys([u.name for u in market] + [u.name for u in affordable]))
    market_by = {u.name: market_first + i for i, u in enumerate(market)}
    affordable_by = {u.name: affordable_first + i for i, u in enumerate(affordable)}
    market_units = dict(zip([u.name for u in market], sheet.market_units, strict=True))
    affordable_units = dict(zip([u.name for u in affordable], sheet.affordable_units, strict=True))
    allowed_market = sheet.permissible_market_units
    allowed_affordable = sheet.permissible_affordable_units
    market_allowed_by = (
        dict(zip([u.name for u in market], allowed_market, strict=True)) if allowed_market else {}
    )
    affordable_allowed_by = (
        dict(zip([u.name for u in affordable], allowed_affordable, strict=True))
        if allowed_affordable
        else {}
    )
    for i, name in enumerate(names):
        row = all_first + i
        ws.text(row, 1, name, _UNIT)
        parts_allowed = [f"D{by[name]}" for by in (market_by, affordable_by) if name in by]
        parts_proposed = [f"E{part[1:]}" for part in parts_allowed]
        allowed_value: float | str = (
            market_allowed_by.get(name, 0.0) + affordable_allowed_by.get(name, 0.0)
            if allowed_market is not None
            else ""
        )
        ws.formula(
            row,
            3,
            f'IF($C${gfa_first}<>"",{"+".join(parts_allowed)},"")',
            allowed_value,
            _UNITS,
        )
        ws.formula(
            row,
            4,
            "+".join(parts_proposed),
            market_units.get(name, 0.0) + affordable_units.get(name, 0.0),
            _UNITS,
        )
        if name in market_by:
            mix_col = _col(c_mix + [u.name for u in market].index(name))
            ws.formula(row, 5, f"{mix_col}{level_total}", 0.0, _UNITS)
        else:
            ws.blank(row, 5, _UNITS)
    all_last = all_first + len(names) - 1
    ws.text(all_total, 1, "Total", _TOTAL_LABEL)
    ws.formula(
        all_total,
        3,
        f"SUM(C{all_first}:C{all_last})",
        sheet.total_permissible_units if sheet.total_permissible_units is not None else 0.0,
        _UNITS_BOLD,
    )
    ws.formula(all_total, 4, f"SUM(D{all_first}:D{all_last})", sheet.total_units, _UNITS_BOLD)
    ws.formula(all_total, 5, f"SUM(E{all_first}:E{all_last})", 0.0, _UNITS_BOLD)

    # -- storeys ---------------------------------------------------------------------
    section(storeys_title, "Number of Storeys")
    ws.text(storeys_resi, 1, "Residential", _LABEL)
    resi_col, total_col = _col(c_bea), _col(c_bea + 3)
    ws.formula(
        storeys_resi,
        3,
        f'COUNTIF({resi_col}{level_first}:{resi_col}{level_last},">0")',
        float(sheet.residential_storeys),
        _COUNT,
    )
    ws.text(storeys_podium, 1, "Podium", _LABEL)
    ws.formula(
        storeys_podium,
        3,
        f'COUNTIF({total_col}{level_first}:{total_col}{level_last},">0")-C{storeys_resi}',
        float(sheet.podium_storeys),
        _COUNT,
    )
    ws.text(storeys_total, 1, "Total", _TOTAL_LABEL)
    ws.formula(
        storeys_total,
        3,
        f"SUM(C{storeys_resi}:C{storeys_podium})",
        float(sheet.residential_storeys + sheet.podium_storeys),
        _COUNT_BOLD,
    )

    # -- parking -----------------------------------------------------------------------
    section(parking_title, "Parking Requirements")
    ws.text(parking_head1, 2, "Required", _HEAD_CENTRE)
    ws.merge(f"B{parking_head1}", f"C{parking_head1}")
    ws.text(parking_head1, 4, "Proposed", _HEAD_CENTRE)
    ws.merge(f"D{parking_head1}", f"E{parking_head1}")
    for col, head in enumerate(("Sepp", "DCP", "Sepp", "DCP"), start=2):
        ws.text(parking_head2, col, head, _HEAD)
    sepp, dcp = sheet.parking_spaces("sepp"), sheet.parking_spaces("dcp")
    ws.text(market_parking_head, 1, "Non Affordable", _PLAIN)
    for i, (unit, rates) in enumerate(zip(market, sheet.parking.market, strict=True)):
        row = market_parking_first + i
        ws.text(row, 1, unit.name, _LABEL)
        ws.number(row, 2, rates.sepp, _IN)
        ws.number(row, 3, rates.dcp, _IN)
        ws.formula(row, 4, f"E{market_first + i}*B{row}", sepp[f"market {unit.name}"], _UNITS)
        ws.formula(row, 5, f"E{market_first + i}*C{row}", dcp[f"market {unit.name}"], _UNITS)
    ws.text(affordable_parking_head, 1, "Affordable", _PLAIN_BOLD)
    for i, (unit, rates) in enumerate(zip(affordable, sheet.parking.affordable, strict=True)):
        row = affordable_parking_first + i
        ws.text(row, 1, unit.name, _LABEL)
        ws.number(row, 2, rates.sepp, _IN)
        ws.number(row, 3, rates.dcp, _IN)
        ws.formula(
            row, 4, f"E{affordable_first + i}*B{row}", sepp[f"affordable {unit.name}"], _UNITS
        )
        ws.formula(
            row, 5, f"E{affordable_first + i}*C{row}", dcp[f"affordable {unit.name}"], _UNITS
        )
    ws.text(visitors_row, 1, "Visitors", _LABEL)
    ws.number(visitors_row, 2, sheet.parking.visitors.sepp, _IN)
    ws.number(visitors_row, 3, sheet.parking.visitors.dcp, _IN)
    ws.formula(visitors_row, 4, f"D{all_total}*B{visitors_row}", sepp["visitors"], _UNITS)
    ws.formula(visitors_row, 5, f"D{all_total}*C{visitors_row}", dcp["visitors"], _UNITS)
    ws.text(resi_parking_total, 1, "Total Residential", _TOTAL_LABEL)
    ws.formula(
        resi_parking_total,
        4,
        f"SUM(D{market_parking_first}:D{visitors_row})",
        sepp["residential"],
        _COUNT_BOLD,
    )
    ws.formula(
        resi_parking_total,
        5,
        f"SUM(E{market_parking_first}:E{visitors_row})",
        dcp["residential"],
        _COUNT_BOLD,
    )
    for row, use, rates in (
        (commercial_parking, COMMERCIAL, sheet.parking.commercial),
        (retail_parking, RETAIL, sheet.parking.retail),
    ):
        ws.text(row, 1, LABELS[use], _TOTAL_LABEL)
        ws.number(row, 2, rates.sepp, _IN_RATE)
        ws.number(row, 3, rates.dcp, _IN_RATE4)
        ws.formula(row, 4, f"B{row}*{gfa_cell[use]}", sepp[use], _COUNT_BOLD)
        ws.formula(row, 5, f"C{row}*{gfa_cell[use]}", dcp[use], _COUNT_BOLD)
    ws.text(parking_total, 1, "Total Parking", _TOTAL_LABEL)
    ws.formula(
        parking_total,
        4,
        f"SUM(D{resi_parking_total}:D{retail_parking})",
        sepp["total"],
        _COUNT_BOLD,
    )
    ws.formula(
        parking_total, 5, f"SUM(E{resi_parking_total}:E{retail_parking})", dcp["total"], _COUNT_BOLD
    )
    ws.text(basements_row, 1, "Total Basements", _TOTAL_LABEL)
    for col, column_name in ((4, "sepp"), (5, "dcp")):
        basements = sheet.basements(column_name)  # type: ignore[arg-type]
        ws.formula(
            basements_row,
            col,
            f'IF({site}>0,{_col(col)}{parking_total}*C{sqm_row}/({site}*C{basement_ratio_row}),"")',
            basements if basements is not None else "",
            _UNITS_BOLD,
        )

    # -- the efficiencies -----------------------------------------------------------------
    ws.text(eff_title, 1, "Building Efficiencies", _SUBSECTION)
    ws.text(eff_head, 3, "BEA to GFA", _HEAD)
    ws.text(eff_head, 5, "GFA to NLA", _HEAD)
    for i, use in enumerate(USES):
        row = eff_first + i
        ws.text(row, 1, LABELS[use], _LABEL)
        ws.number(row, 3, e.gfa(use), _IN)
        ws.number(row, 5, e.nla(use), _IN)

    def averages(
        title_row: int, title: str, mix: Mix, first_row: int, avg_row: int, mix_first: int
    ) -> None:
        ws.text(title_row, 1, title, _SUBSECTION)
        ws.text(first_row, 1, "Average NLA", _UNIT)
        last = mix_first + len(mix.types) - 1
        ws.formula(
            first_row,
            3,
            f"SUMPRODUCT(B{mix_first}:B{last},C{mix_first}:C{last})",
            sum(u.share * u.size_m2 for u in mix.types),
            _PLAIN,
        )
        ws.text(first_row + 1, 1, "Common areas per unit", _UNIT)
        ws.number(first_row + 1, 3, mix.common_m2, _IN)
        ws.text(first_row + 2, 1, "Unit size tolerance", _UNIT)
        ws.number(first_row + 2, 3, mix.tolerance_m2, _IN)
        ws.text(first_row + 3, 1, "Average NLA", _UNIT)
        ws.formula(
            first_row + 3,
            3,
            f"C{first_row}+C{first_row + 1}+C{first_row + 2}",
            mix.average_nla_m2,
            _PLAIN,
        )
        ws.text(avg_row, 1, "Average GFA", _TOTAL_LABEL)
        ws.formula(
            avg_row,
            3,
            f"C{first_row + 3}/{eff_nla[RESIDENTIAL]}",
            mix.average_gfa_m2(e),
            _UNITS_BOLD,
        )

    averages(
        market_eff_title,
        "Market Units Efficiencies",
        sheet.market,
        market_avg_nla,
        market_avg_gfa,
        market_first,
    )
    averages(
        affordable_eff_title,
        "Affordable Units Efficiencies",
        sheet.affordable,
        affordable_avg_nla,
        affordable_avg_gfa,
        affordable_first,
    )
    ws.text(parking_eff_title, 1, "Parking  Efficiencies", _SUBSECTION)
    ws.text(sqm_row, 1, "SQM per parking", _LABEL)
    ws.number(sqm_row, 3, sheet.parking.sqm_per_space, _IN)
    ws.text(sqm_row, 4, "sqm", _LABEL)
    ws.text(basement_ratio_row, 1, "Basement Site ratio", _LABEL)
    ws.number(basement_ratio_row, 3, sheet.parking.basement_site_ratio, _IN_SHARE)
    ws.text(basement_ratio_row, 4, "percentage of the site dedicated to basement", _PLAIN)

    # -- the storey table ------------------------------------------------------------------
    ws.formula(t, c_level, "A3", sheet.option, _OPTION)
    ws.merge(f"{_col(c_level)}{t}", f"{_col(c_nsa + 3)}{t}")
    for start, title in (
        (c_bea, "BEA"),
        (c_gfa, "GFA"),
        (c_nsa, "NSA"),
    ):
        ws.text(t + 1, start, title, _HEAD_CENTRE)
        ws.merge(f"{_col(start)}{t + 1}", f"{_col(start + 3)}{t + 1}")
    ws.text(t + 1, c_mix, "Unit Mix", _HEAD_CENTRE)
    ws.merge(f"{_col(c_mix)}{t + 1}", f"{_col(c_mix + n_market)}{t + 1}")
    ws.text(t + 1, c_adg, "ADG", _HEAD_CENTRE)
    ws.merge(f"{_col(c_adg)}{t + 1}", f"{_col(c_adg + 3)}{t + 1}")
    ws.text(t + 1, c_back, "Total", _HEAD_CENTRE)
    ws.merge(f"{_col(c_back)}{t + 1}", f"{_col(c_back + 2)}{t + 1}")
    ws.text(t + 1, c_diff, "Difference", _HEAD)
    for col, head in ((c_level, "Level"), (c_f2f, "F to F"), (c_height, "Height")):
        ws.text(t + 2, col, head, _HEAD)
    for start in (c_bea, c_gfa, c_nsa):
        for i, head in enumerate(("Resi", "Comm", "Retail", "Total")):
            ws.text(t + 2, start + i, head, _HEAD)
    for i, unit in enumerate(market):
        ws.text(t + 2, c_mix + i, _short(unit.name), _HEAD)
    ws.text(t + 2, c_mix + n_market, "Total", _HEAD)
    ws.text(t + 2, c_adg, "C Vent", _HEAD)
    ws.text(t + 2, c_adg + 1, "Solar A", _HEAD)
    for i, head in enumerate((">2hr", "<2hr", "0hr")):
        ws.text(t + 3, c_adg + 1 + i, head, _HEAD)
    for i, head in enumerate(("GBA", "GFA", "NLA")):
        ws.text(t + 2, c_back + i, head, _HEAD)
    ws.text(t + 2, c_diff, "GFA", _HEAD)

    mix_total_col = _col(c_mix + n_market)
    for i, level in enumerate(levels):
        row = level_first + i
        below = row + 1
        ws.text(row, c_level, level.name, _LABEL)
        ws.number(row, c_f2f, level.floor_to_floor_m, _IN_RATIO)
        if i == len(levels) - 1:
            ws.formula(row, c_height, f"{_col(c_f2f)}{row}", level.floor_to_floor_m, _RATIO)
        else:
            height = sum(lv.floor_to_floor_m for lv in levels[i:])
            ws.formula(row, c_height, f"{_col(c_height)}{below}+{_col(c_f2f)}{row}", height, _RATIO)
        for j, use in enumerate(USES):
            ws.number(row, c_bea + j, level.bea(use), _IN_AREA)
            ws.formula(
                row,
                c_gfa + j,
                f"{_col(c_bea + j)}{row}*{eff_gfa[use]}",
                level.bea(use) * e.gfa(use),
                _AREA,
            )
            ws.formula(
                row,
                c_nsa + j,
                f"{_col(c_gfa + j)}{row}*{eff_nla[use]}",
                level.bea(use) * e.gfa(use) * e.nla(use),
                _AREA,
            )
        for start, value in (
            (c_bea, level.total_m2),
            (c_gfa, sum(level.bea(u) * e.gfa(u) for u in USES)),
            (c_nsa, sum(level.bea(u) * e.gfa(u) * e.nla(u) for u in USES)),
        ):
            ws.formula(
                row, start + 3, f"SUM({_col(start)}{row}:{_col(start + 2)}{row})", value, _AREA
            )
        for j in range(n_market):
            ws.blank(row, c_mix + j, _IN_COUNT)
        ws.formula(
            row,
            c_mix + n_market,
            f"SUM({_col(c_mix)}{row}:{_col(c_mix + n_market - 1)}{row})",
            0.0,
            _COUNT,
        )
        for j in range(4):
            ws.blank(row, c_adg + j, _IN_COUNT)
        sizes = "+".join(f"{_col(c_mix + j)}{row}*$B${market_first + j}" for j in range(n_market))
        ws.formula(row, c_back + 2, sizes, 0.0, _AREA)
        ws.formula(row, c_back + 1, f"{_col(c_back + 2)}{row}/{eff_nla[RESIDENTIAL]}", 0.0, _AREA)
        ws.formula(row, c_back, f"{_col(c_back + 1)}{row}/{eff_gfa[RESIDENTIAL]}", 0.0, _AREA)
        ws.formula(
            row,
            c_diff,
            f"{_col(c_back + 1)}{row}-{_col(c_gfa)}{row}",
            -level.bea(RESIDENTIAL) * e.gfa(RESIDENTIAL),
            _AREA,
        )

    ws.text(level_total, c_level, "Total", _TOTAL_LABEL)
    if levels:
        ws.formula(
            level_total,
            c_height,
            f"{_col(c_height)}{level_first}",
            sum(lv.floor_to_floor_m for lv in levels),
            _RATIO_BOLD,
        )
    totals = {
        c_bea: [sheet.bea(u) for u in USES] + [sheet.total_bea_m2],
        c_gfa: [sheet.gfa(u) for u in USES] + [sheet.total_gfa_m2],
        c_nsa: [sheet.nla(u) for u in USES] + [sheet.total_nla_m2],
    }
    for start, values in totals.items():
        for j, value in enumerate(values):
            letter = _col(start + j)
            ws.formula(
                level_total,
                start + j,
                f"SUM({letter}{level_first}:{letter}{level_last})",
                value,
                _AREA_BOLD,
            )
    for j in range(n_market + 1):
        letter = _col(c_mix + j)
        ws.formula(
            level_total,
            c_mix + j,
            f"SUM({letter}{level_first}:{letter}{level_last})",
            0.0,
            _COUNT_BOLD,
        )
    for j in range(4):
        letter = _col(c_adg + j)
        ws.formula(
            level_total,
            c_adg + j,
            f"SUM({letter}{level_first}:{letter}{level_last})",
            0.0,
            _COUNT_BOLD,
        )
    for j in range(3):
        letter = _col(c_back + j)
        ws.formula(
            level_total,
            c_back + j,
            f"SUM({letter}{level_first}:{letter}{level_last})",
            0.0,
            _AREA_BOLD,
        )
    letter = _col(c_diff)
    ws.formula(
        level_total,
        c_diff,
        f"SUM({letter}{level_first}:{letter}{level_last})",
        -sheet.gfa(RESIDENTIAL),
        _AREA_BOLD,
    )

    # The summary under the table: target, proposed, difference by use; the
    # mix proposed against the target; the ADG shares.
    for i, head in enumerate(("Resi", "Comm", "Retail", "Total")):
        ws.text(summary_head, c_gfa + i, head, _HEAD)
    for i, unit in enumerate(market):
        ws.text(summary_head, c_mix + i, _short(unit.name), _HEAD)
    ws.text(summary_head, c_mix + n_market, "Total", _HEAD)
    ws.text(summary_head, c_adg, "C Vent", _HEAD)
    ws.text(summary_head, c_adg + 1, "Solar A", _HEAD)
    ws.text(target_row, c_height, "Target GFA", _HEAD)
    ws.text(proposed_row, c_height, "Proposed GFA", _LABEL)
    ws.text(difference_row, c_height, "Difference", _LABEL)
    summary: list[tuple[str | None, int]] = [
        *((use, gfa_first + i) for i, use in enumerate(USES)),
        (None, gfa_total),
    ]
    for i, (kind, source_row) in enumerate(summary):
        at = c_gfa + i
        letter = _col(at)
        allowed = (
            sheet.permissible_gfa(kind) if kind is not None else sheet.total_permissible_gfa_m2
        )
        proposed = sheet.gfa(kind) if kind is not None else sheet.total_gfa_m2
        ws.formula(target_row, at, f"C{source_row}", allowed if allowed is not None else "", _AREA)
        ws.formula(proposed_row, at, f"{letter}{level_total}", proposed, _AREA)
        ws.formula(
            difference_row,
            at,
            f'IF({letter}{target_row}<>"",{letter}{proposed_row}-{letter}{target_row},"")',
            _value_diff(proposed, allowed),
            _AREA,
        )
    ws.text(level_total, c_mix - 1, "Total", _HEAD)
    ws.text(target_row, c_mix - 1, "Proposed", _HEAD)
    ws.text(proposed_row, c_mix - 1, "Target", _HEAD)
    ws.text(difference_row, c_mix - 1, "Diff", _HEAD)
    total_mix = f"${mix_total_col}${level_total}"
    for j in range(n_market):
        letter = _col(c_mix + j)
        ws.formula(
            target_row,
            c_mix + j,
            f'IF({total_mix}>0,{letter}{level_total}/{total_mix},"")',
            "",
            _SHARE1,
        )
        ws.formula(proposed_row, c_mix + j, f"C{market_first + j}", market[j].share, _SHARE1)
        ws.formula(
            difference_row,
            c_mix + j,
            f'IF({letter}{target_row}<>"",{letter}{target_row}-{letter}{proposed_row},"")',
            "",
            _SHARE1,
        )
    ws.formula(proposed_row, c_mix + n_market, f"D{all_total}", sheet.total_units, _UNITS)
    ws.formula(
        difference_row,
        c_mix + n_market,
        f"{mix_total_col}{proposed_row}-{mix_total_col}{level_total}",
        sheet.total_units,
        _UNITS,
    )
    for j, target in enumerate((0.6, 0.7, None, 0.15)):
        letter = _col(c_adg + j)
        ws.formula(
            target_row,
            c_adg + j,
            f'IF({total_mix}>0,{letter}{level_total}/{total_mix},"")',
            "",
            _SHARE1,
        )
        if target is not None:
            ws.number(proposed_row, c_adg + j, target, _IN_SHARE)
            ws.formula(
                difference_row,
                c_adg + j,
                f'IF({letter}{target_row}<>"",{letter}{target_row}-{letter}{proposed_row},"")',
                "",
                _SHARE1,
            )

    diff_col = _col(c_diff)
    raw.tail_xml = (
        f'<conditionalFormatting sqref="{diff_col}{t + 3}:{diff_col}{level_total}">'
        + look.COLOUR_SCALE
        + "</conditionalFormatting>"
        + '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        + '<pageSetup paperSize="8" scale="79" orientation="portrait"/>'
    )
    ws.finish(basement_ratio_row, 9, range(c_level, c_diff + 1))


def _short(name: str) -> str:
    """A unit type's name as the storey table heads a column: ``1-B``, ``St``."""
    tidy = name.strip()
    if tidy.casefold().startswith("studio"):
        return "St"
    digits = "".join(ch for ch in tidy if ch.isdigit())
    return f"{digits}-B" if digits else tidy[:4]


def _value_diff(proposed: float | None, allowed: float | None) -> float | str:
    if proposed is None or allowed is None:
        return ""
    return proposed - allowed


# -- the option's data, for the hidden sheet -----------------------------------------------


def feasibility_to_dict(sheet: Feasibility) -> dict[str, Any]:
    """Everything the sheet was made from, as plain JSON."""
    return {
        "option": sheet.option,
        "site_area_m2": sheet.site_area_m2,
        "permissible": asdict(sheet.permissible),
        "efficiencies": asdict(sheet.efficiencies),
        "market": _mix_dict(sheet.market),
        "affordable": _mix_dict(sheet.affordable),
        "affordable_share": sheet.affordable_share,
        "parking": {
            "market": [asdict(r) for r in sheet.parking.market],
            "affordable": [asdict(r) for r in sheet.parking.affordable],
            "visitors": asdict(sheet.parking.visitors),
            "commercial": asdict(sheet.parking.commercial),
            "retail": asdict(sheet.parking.retail),
            "sqm_per_space": sheet.parking.sqm_per_space,
            "basement_site_ratio": sheet.parking.basement_site_ratio,
        },
        "levels": [asdict(level) for level in sheet.levels],
        "source": list(sheet.source),
    }


def _mix_dict(mix: Mix) -> dict[str, Any]:
    return {
        "types": [asdict(unit) for unit in mix.types],
        "common_m2": mix.common_m2,
        "tolerance_m2": mix.tolerance_m2,
    }


def _mix_from(data: Mapping[str, Any], fallback: Sequence[UnitType]) -> Mix:
    types = tuple(
        UnitType(str(u["name"]), float(u["share"]), float(u["size_m2"]))
        for u in data.get("types", [])
    ) or tuple(fallback)
    return Mix(types, float(data.get("common_m2", 0.0)), float(data.get("tolerance_m2", 0.0)))


def feasibility_from_dict(data: Mapping[str, Any]) -> Feasibility:
    """A sheet back from ``feasibility_to_dict``."""
    parking = data.get("parking", {})

    def rates(item: Any) -> UnitRates:
        return UnitRates(float(item["sepp"]), float(item["dcp"]))

    market = _mix_from(data.get("market", {}), ())
    affordable = _mix_from(data.get("affordable", {}), AFFORDABLE_MIX)
    return Feasibility(
        option=str(data["option"]),
        levels=tuple(
            Level(
                int(lv["index"]),
                float(lv["bottom_m"]),
                float(lv["floor_to_floor_m"]),
                float(lv.get("residential_m2", 0.0)),
                float(lv.get("commercial_m2", 0.0)),
                float(lv.get("retail_m2", 0.0)),
            )
            for lv in data.get("levels", [])
        ),
        site_area_m2=data.get("site_area_m2"),
        permissible=Permissible(**data.get("permissible", {})),
        efficiencies=Efficiencies(**data.get("efficiencies", {})),
        market=market,
        affordable=affordable,
        affordable_share=float(data.get("affordable_share", 0.0)),
        parking=ParkingRates(
            market=tuple(rates(r) for r in parking.get("market", [])),
            affordable=tuple(rates(r) for r in parking.get("affordable", [])),
            visitors=rates(parking.get("visitors", {"sepp": 0.1, "dcp": 0.0})),
            commercial=rates(parking.get("commercial", {"sepp": 1 / 100, "dcp": 1 / 400})),
            retail=rates(parking.get("retail", {"sepp": 1 / 30, "dcp": 1 / 400})),
            sqm_per_space=float(parking.get("sqm_per_space", 40.0)),
            basement_site_ratio=float(parking.get("basement_site_ratio", 0.4)),
        ),
        source=tuple(str(line) for line in data.get("source", [])),
    )
