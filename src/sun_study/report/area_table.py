"""The area calculation as a table: the sheet's rows, its notes, the workbook.

The rows are the office's sheet -- *Area calculation, GFA + Yield* -- in its
order and its words: the totals first and then the two uses, GBA, GFA, NSA
and FSR, then the yield. One list of rows serves three readers, so they can
not disagree: the sheet Loriini draws on a layout, the lines the command
prints, and the workbook.

The workbook is the one that can be argued with. Its inputs are cells --
the site, the targets, the four factors, the mix -- and everything else is a
formula over them and over the storeys' measured GBA, so a what-if on a
factor or a share is typed into Excel rather than rerun. The split of the
units into the mix is Loriini's largest remainder, written out in working
columns beside it, so what Excel shows after an edit is what Loriini would
have said.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sun_study.report import xlsx
from sun_study.rules.area_yield import Areas, AreaSchedule

__all__ = [
    "SHEET_NAME",
    "SUBTITLE",
    "TITLE",
    "TableRow",
    "factor",
    "m2",
    "notes",
    "percent",
    "rows",
    "text_lines",
    "units",
    "write_workbook",
]

TITLE = "AREA CALCULATION"
SUBTITLE = "GFA + Yield"
SHEET_NAME = "Area calculation"


def m2(value: float) -> str:
    """An area the way the sheet writes one: ``14607.24 m²``."""
    return f"{value:.2f} m²"


def factor(value: float) -> str:
    """A factor or a ratio as typed: ``0.75``, ``0.9``."""
    return f"{value:g}"


def percent(value: float) -> str:
    """A share as the sheet writes one: ``15 %``."""
    return f"{round(value * 100):d} %"


def units(count: int) -> str:
    """A count of units: ``17 units``, ``1 unit``."""
    return f"{count} unit" if count == 1 else f"{count} units"


def _fsr(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


@dataclass(frozen=True)
class TableRow:
    """One line of the table: a heading, a figure, or the gap between groups."""

    kind: Literal["head", "row", "gap", "section"]
    label: str = ""
    count: str = ""
    """The yield's own column, between the label and Proposed: ``17 units``."""
    proposed: str = ""
    target: str = ""


def rows(schedule: AreaSchedule) -> list[TableRow]:
    """The table, top to bottom, as the office's sheet has it."""
    total, non, res = schedule.total, schedule.non_residential, schedule.residential
    target_gfa = schedule.target_gfa_m2
    out: list[TableRow] = [TableRow("head", proposed="Proposed", target="Target")]

    def group(word: str, pick: str, total_target: str = "") -> None:
        def figure(areas: Areas) -> str:
            return m2(float(getattr(areas, pick)))

        out.append(TableRow("gap"))
        out.append(TableRow("row", f"Total {word}", proposed=figure(total), target=total_target))
        out.append(TableRow("row", f"Non resi. {word}", proposed=figure(non)))
        out.append(TableRow("row", f"Resi. {word}", proposed=figure(res)))

    group("GBA", "gba_m2")
    group("GFA", "gfa_m2", m2(target_gfa) if target_gfa is not None else "")
    group("NSA", "nsa_m2")
    out.append(TableRow("gap"))
    fsr_target = _fsr(schedule.targets.fsr) if schedule.targets.fsr is not None else ""
    out.append(TableRow("row", "Total FSR", proposed=_fsr(schedule.fsr(total)), target=fsr_target))
    out.append(TableRow("row", "Non resi. FSR", proposed=_fsr(schedule.fsr(non))))
    out.append(TableRow("row", "Resi. FSR", proposed=_fsr(schedule.fsr(res))))

    homes = schedule.homes
    out.append(TableRow("gap"))
    out.append(TableRow("section", "YIELD", proposed="Proposed", target="Target"))
    wanted = schedule.targets.units
    out.append(
        TableRow(
            "row",
            count=units(homes.units),
            proposed="Mix",
            target=units(wanted) if wanted is not None else "",
        )
    )
    for count in homes.counts:
        out.append(
            TableRow(
                "row",
                count.unit.name,
                count=units(count.count),
                proposed=percent(homes.share(count)),
                target=percent(count.unit.share),
            )
        )
    per_unit = schedule.gfa_per_unit_m2
    out.append(TableRow("row", "GFA/unit", proposed=m2(per_unit) if per_unit else "-"))
    return out


def notes(schedule: AreaSchedule, source: Sequence[str] = ()) -> list[str]:
    """The notes under the table: the factors the figures were worked with,
    the site, the unit sizes, and where the GBA came from."""
    r = schedule.ratios
    lines = [
        f"GBA to GFA (Residential) : {factor(r.gfa_residential)}",
        f"GBA to GFA (Non-Residential) : {factor(r.gfa_non_residential)}",
        f"GFA to NSA (Residential) : {factor(r.nsa_residential)}",
        f"GFA to NSA (Non-Residential) : {factor(r.nsa_non_residential)}",
    ]
    if schedule.site_area_m2:
        lines.append(f"Site area : {m2(schedule.site_area_m2)}")
    lines.append(
        "Unit sizes (NSA) : "
        + ", ".join(f"{unit.name} {unit.size_m2:g} m²" for unit in schedule.mix)
    )
    lines.append(f"Average unit (NSA) : {schedule.homes.average_m2:.1f} m²")
    lines.extend(source)
    return lines


def text_lines(schedule: AreaSchedule) -> list[str]:
    """The table as the command prints it, in columns."""
    out: list[str] = []
    for row in rows(schedule):
        if row.kind == "gap":
            out.append("")
            continue
        out.append(f"  {row.label:<16}{row.count:>11}  {row.proposed:<15}{row.target}".rstrip())
    return out


# -- the workbook -------------------------------------------------------------------

_TITLE = xlsx.Format(size=14, bold=True)
_NOTE = xlsx.Format(size=9, italic=True, grey=True)
_SECTION = xlsx.Format(bold=True)
_HEAD = xlsx.Format(bold=True, boxed=True, align="center")
_LABEL = xlsx.Format(boxed=True)
_TOTAL_LABEL = xlsx.Format(boxed=True, bold=True)
_INPUT = xlsx.Format(number="0.00", boxed=True, shaded=True)
_INPUT_COUNT = xlsx.Format(number="0", boxed=True, shaded=True)
_INPUT_SHARE = xlsx.Format(number="0.0%", boxed=True, shaded=True)
_INPUT_TEXT = xlsx.Format(boxed=True, shaded=True)
_AREA = xlsx.Format(number='0.00" m²"', boxed=True)
_TOTAL_AREA = xlsx.Format(number='0.00" m²"', boxed=True, bold=True)
_RATIO = xlsx.Format(number="0.00", boxed=True)
_UNITS = xlsx.Format(number='0" units"', boxed=True)
_SHARE = xlsx.Format(number="0%", boxed=True)
_WORK = xlsx.Format(number="0.000", size=9, grey=True)
_WORK_HEAD = xlsx.Format(size=9, italic=True, grey=True)

#: The working columns' headings: the split of the units into the mix, by
#: the largest remainder, one step per column.
_WORKING = ("quota", "whole", "remainder", "rank")


def write_workbook(destination: Path, schedule: AreaSchedule, *, note: str = "") -> Path:
    """The area calculation as a live workbook: inputs, areas, yield, storeys."""
    sheet = xlsx.Sheet(SHEET_NAME, widths=(32, 18, 18, 18, 10, 10, 10, 10))
    sheet.text(1, 1, f"{TITLE} — {SUBTITLE}", _TITLE)
    if note:
        sheet.text(2, 1, note, _NOTE)
    line = 4

    # -- the inputs: every figure the rest is worked from ---------------------
    sheet.text(line, 1, "INPUTS", _SECTION)
    line += 1
    site_row = line
    sheet.text(line, 1, "Site area (m²)", _LABEL)
    if schedule.site_area_m2:
        sheet.number(line, 2, schedule.site_area_m2, _INPUT)
    else:
        sheet.text(line, 2, "", _INPUT)
    line += 1
    fsr_row = line
    sheet.text(line, 1, "Target FSR", _LABEL)
    if schedule.targets.fsr is not None:
        sheet.number(line, 2, schedule.targets.fsr, _INPUT)
    else:
        sheet.text(line, 2, "", _INPUT)
    line += 1
    units_target_row = line
    sheet.text(line, 1, "Target units", _LABEL)
    if schedule.targets.units is not None:
        sheet.number(line, 2, float(schedule.targets.units), _INPUT_COUNT)
    else:
        sheet.text(line, 2, "", _INPUT_COUNT)
    line += 1
    r = schedule.ratios
    factor_rows: dict[str, int] = {}
    for key, label, value in (
        ("gfa_res", "GBA to GFA (Residential)", r.gfa_residential),
        ("gfa_non", "GBA to GFA (Non-Residential)", r.gfa_non_residential),
        ("nsa_res", "GFA to NSA (Residential)", r.nsa_residential),
        ("nsa_non", "GFA to NSA (Non-Residential)", r.nsa_non_residential),
    ):
        factor_rows[key] = line
        sheet.text(line, 1, label, _LABEL)
        sheet.number(line, 2, value, _INPUT)
        line += 1

    line += 1
    sheet.text(line, 1, "UNIT MIX", _SECTION)
    line += 1
    for col, head in enumerate(("Type", "Share", "Size (m² NSA)"), start=1):
        sheet.text(line, col, head, _HEAD)
    line += 1
    mix_first = line
    for unit in schedule.mix:
        sheet.text(line, 1, unit.name, _INPUT_TEXT)
        sheet.number(line, 2, unit.share, _INPUT_SHARE)
        sheet.number(line, 3, unit.size_m2, _INPUT)
        line += 1
    mix_last = line - 1
    average_row = line
    sheet.text(line, 1, "Average unit (m² NSA)", _TOTAL_LABEL)
    sheet.formula(
        line,
        2,
        f"SUMPRODUCT(B{mix_first}:B{mix_last},C{mix_first}:C{mix_last})",
        schedule.homes.average_m2,
        _TOTAL_AREA,
    )
    line += 2

    # Where each part of what follows lands, worked out before any of it is
    # written: the areas add up the storey table at the foot of the sheet.
    areas_head = line
    fsr_total_row = areas_head + 10
    yield_head = fsr_total_row + 4
    per_unit_row = yield_head + 2 + len(schedule.homes.counts)
    storeys_head = per_unit_row + 3
    storey_first = storeys_head + 1
    storey_total = storey_first + len(schedule.storeys)

    # -- the areas ------------------------------------------------------------
    site = f"$B${site_row}"
    for col, head in enumerate(("AREAS", "Proposed", "Target"), start=1):
        sheet.text(line, col, head, _HEAD if col > 1 else _SECTION)
    line += 1
    area_rows: dict[str, tuple[int, int, int]] = {}
    for word, key in (("GBA", "gba"), ("GFA", "gfa"), ("NSA", "nsa")):
        total_row, non_row, res_row = line, line + 1, line + 2
        area_rows[key] = (total_row, non_row, res_row)
        sheet.text(total_row, 1, f"Total {word}", _TOTAL_LABEL)
        sheet.text(non_row, 1, f"Non resi. {word}", _LABEL)
        sheet.text(res_row, 1, f"Resi. {word}", _LABEL)
        totals = {
            "gba": (
                schedule.total.gba_m2,
                schedule.non_residential.gba_m2,
                schedule.residential.gba_m2,
            ),
            "gfa": (
                schedule.total.gfa_m2,
                schedule.non_residential.gfa_m2,
                schedule.residential.gfa_m2,
            ),
            "nsa": (
                schedule.total.nsa_m2,
                schedule.non_residential.nsa_m2,
                schedule.residential.nsa_m2,
            ),
        }[key]
        sheet.formula(total_row, 2, f"B{non_row}+B{res_row}", totals[0], _TOTAL_AREA)
        if key == "gba":
            non_formula, res_formula = f"C{storey_total}", f"B{storey_total}"
        elif key == "gfa":
            _, gba_non, gba_res = area_rows["gba"]
            non_formula = f"B{gba_non}*$B${factor_rows['gfa_non']}"
            res_formula = f"B{gba_res}*$B${factor_rows['gfa_res']}"
        else:
            _, gfa_non, gfa_res = area_rows["gfa"]
            non_formula = f"B{gfa_non}*$B${factor_rows['nsa_non']}"
            res_formula = f"B{gfa_res}*$B${factor_rows['nsa_res']}"
        sheet.formula(non_row, 2, non_formula, totals[1], _AREA)
        sheet.formula(res_row, 2, res_formula, totals[2], _AREA)
        for row_number in (total_row, non_row, res_row):
            if not (key == "gfa" and row_number == total_row):
                sheet.text(row_number, 3, "", _AREA)
        if key == "gfa":
            target = schedule.target_gfa_m2
            sheet.formula(
                total_row,
                3,
                f'IF(AND({site}>0,$B${fsr_row}>0),{site}*$B${fsr_row},"")',
                target if target is not None else "",
                _TOTAL_AREA,
            )
        line += 3
    assert line == fsr_total_row
    for offset, (label, areas, gfa_row) in enumerate(
        (
            ("Total FSR", schedule.total, area_rows["gfa"][0]),
            ("Non resi. FSR", schedule.non_residential, area_rows["gfa"][1]),
            ("Resi. FSR", schedule.residential, area_rows["gfa"][2]),
        )
    ):
        at = line + offset
        sheet.text(at, 1, label, _TOTAL_LABEL if offset == 0 else _LABEL)
        fsr = schedule.fsr(areas)
        sheet.formula(
            at, 2, f'IF({site}>0,B{gfa_row}/{site},"")', fsr if fsr is not None else "", _RATIO
        )
        if offset == 0:
            wanted = schedule.targets.fsr
            sheet.formula(
                at,
                3,
                f'IF($B${fsr_row}>0,$B${fsr_row},"")',
                wanted if wanted is not None else "",
                _RATIO,
            )
        else:
            sheet.text(at, 3, "", _RATIO)
    line = yield_head

    # -- the yield ------------------------------------------------------------
    for col, head in enumerate(("YIELD", "Units", "Mix", "Target"), start=1):
        sheet.text(line, col, head, _HEAD if col > 1 else _SECTION)
    for col, head in enumerate(_WORKING, start=5):
        sheet.text(line, col, head, _WORK_HEAD)
    line += 1
    units_row = line
    homes = schedule.homes
    res_nsa = area_rows["nsa"][2]
    sheet.text(line, 1, "Units", _TOTAL_LABEL)
    sheet.formula(
        line,
        2,
        f"IF(AND($B${average_row}>0,B{res_nsa}>0),INT(B{res_nsa}/$B${average_row}+1E-9),0)",
        float(homes.units),
        _UNITS,
    )
    sheet.text(line, 3, "", _SHARE)
    sheet.formula(
        line,
        4,
        f'IF($B${units_target_row}="","",$B${units_target_row})',
        float(schedule.targets.units) if schedule.targets.units is not None else "",
        _UNITS,
    )
    line += 1
    type_first = line
    type_last = line + len(homes.counts) - 1
    quotas = [homes.units * count.unit.share for count in homes.counts]
    wholes = [int(q + 1e-9) for q in quotas]
    fractions = [q - w for q, w in zip(quotas, wholes, strict=True)]
    order = sorted(range(len(quotas)), key=lambda i: (-fractions[i], i))
    ranks = {index: place + 1 for place, index in enumerate(order)}
    for offset, count in enumerate(homes.counts):
        at = type_first + offset
        mix_row = mix_first + offset
        sheet.formula(at, 1, f"A{mix_row}", count.unit.name, _LABEL)
        sheet.formula(
            at,
            2,
            f"F{at}+IF(H{at}<=($B${units_row}-SUM($F${type_first}:$F${type_last})),1,0)",
            float(count.count),
            _UNITS,
        )
        sheet.formula(
            at, 3, f"IF($B${units_row}>0,B{at}/$B${units_row},0)", homes.share(count), _SHARE
        )
        sheet.formula(at, 4, f"B{mix_row}", count.unit.share, _SHARE)
        sheet.formula(at, 5, f"$B${units_row}*B{mix_row}", quotas[offset], _WORK)
        sheet.formula(at, 6, f"INT(E{at}+1E-9)", float(wholes[offset]), _WORK)
        sheet.formula(at, 7, f"E{at}-F{at}", fractions[offset], _WORK)
        tie = f"+COUNTIF($G${type_first}:G{at - 1},G{at})" if offset else ""
        sheet.formula(
            at,
            8,
            f"RANK(G{at},$G${type_first}:$G${type_last},0){tie}",
            float(ranks[offset]),
            _WORK,
        )
    line = type_last + 1
    assert line == per_unit_row
    per_unit = schedule.gfa_per_unit_m2
    sheet.text(line, 1, "GFA/unit", _LABEL)
    sheet.formula(
        line,
        2,
        f'IF($B${units_row}>0,B{area_rows["gfa"][2]}/$B${units_row},"")',
        per_unit if per_unit is not None else "",
        _AREA,
    )

    # -- the storeys ------------------------------------------------------------
    for col, head in enumerate(("BY STOREY", "Resi. GBA", "Non resi. GBA", "Total GBA"), start=1):
        sheet.text(storeys_head, col, head, _HEAD if col > 1 else _SECTION)
    for offset, storey in enumerate(schedule.storeys):
        at = storey_first + offset
        sheet.text(at, 1, storey.storey or "(no storey)", _LABEL)
        sheet.number(at, 2, storey.residential_m2, _AREA)
        sheet.number(at, 3, storey.non_residential_m2, _AREA)
        sheet.formula(at, 4, f"B{at}+C{at}", storey.total_m2, _AREA)
    sheet.text(storey_total, 1, "Total", _TOTAL_LABEL)
    last = storey_total - 1
    if schedule.storeys:
        sheet.formula(
            storey_total,
            2,
            f"SUM(B{storey_first}:B{last})",
            schedule.residential.gba_m2,
            _TOTAL_AREA,
        )
        sheet.formula(
            storey_total,
            3,
            f"SUM(C{storey_first}:C{last})",
            schedule.non_residential.gba_m2,
            _TOTAL_AREA,
        )
    else:
        sheet.number(storey_total, 2, 0.0, _TOTAL_AREA)
        sheet.number(storey_total, 3, 0.0, _TOTAL_AREA)
    sheet.formula(
        storey_total, 4, f"B{storey_total}+C{storey_total}", schedule.total.gba_m2, _TOTAL_AREA
    )
    return xlsx.write(destination, sheet)
