"""Read the office's feasibility template and write the module that carries
its look: ``src/sun_study/report/feasibility_style.py``.

The yield workbook is the template filled in, cell for cell, and it should
look like the template too -- its green section bars, its boxed blocks, its
red inputs, its column widths. The look is in the template's ``styles.xml``
(190 cell styles over 34 borders), its theme, and the style index each cell
carries; this script lifts those out once and writes them as Python
literals, so the program ships no data file and never reads the template at
run time. Run it again when the office changes the template::

    uv run python scripts/extract_feasibility_style.py "..\\Feasibility template.xlsx"

The generated module is committed; ``report.area_table`` maps every cell it
writes onto the template cell it stands for and takes that cell's style.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE.parent / "src" / "sun_study" / "report" / "feasibility_style.py"


def main(template: Path) -> None:
    with zipfile.ZipFile(template) as package:
        styles = package.read("xl/styles.xml").decode("utf-8")
        theme = package.read("xl/theme/theme1.xml").decode("utf-8")
        sheet = package.read("xl/worksheets/sheet1.xml").decode("utf-8")

    cells: dict[str, int] = {}
    for ref, style in re.findall(r'<c r="([A-Z]+\d+)" s="(\d+)"', sheet):
        cells[ref] = int(style)
    heights: dict[int, float] = {}
    for row, attrs in re.findall(r"<row r=\"(\d+)\"([^>]*)>", sheet):
        height = re.search(r' ht="([\d.]+)"', attrs)
        if height:
            heights[int(row)] = float(height.group(1))
    cols = re.search(r"<cols>.*?</cols>", sheet, re.S)
    merges = re.findall(r'<mergeCell ref="([A-Z]+\d+:[A-Z]+\d+)"/>', sheet)
    colour_scale = re.search(r"<cfRule.*?</cfRule>", sheet, re.S)

    def literal(text: str) -> str:
        return repr(text)

    lines = [
        '"""The office\'s feasibility template\'s look, lifted out of it by',
        "``scripts/extract_feasibility_style.py``. Generated; do not edit.",
        "",
        "``STYLES_XML`` and ``THEME_XML`` are the template's own parts, verbatim;",
        "``CELLS`` is the style index of every cell on its *Option 01* sheet, by",
        "address, which ``report.area_table`` looks up for each cell it writes;",
        "``COLS_XML`` its column widths, ``ROW_HEIGHTS`` the rows it sets a height",
        "on, ``MERGES`` its merged ranges, and ``COLOUR_SCALE`` the rule that",
        "shades the storey table's difference column.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "# ruff: noqa: E501  -- the parts are one line each, as Excel wrote them",
        "",
        f"STYLES_XML = {literal(styles)}",
        "",
        f"THEME_XML = {literal(theme)}",
        "",
        f"COLS_XML = {literal(cols.group(0) if cols else '')}",
        "",
        f"COLOUR_SCALE = {literal(colour_scale.group(0) if colour_scale else '')}",
        "",
        "CELLS: dict[str, int] = {",
        *(f"    {ref!r}: {style}," for ref, style in cells.items()),
        "}",
        "",
        "ROW_HEIGHTS: dict[int, float] = {",
        *(f"    {row}: {height}," for row, height in sorted(heights.items())),
        "}",
        "",
        "MERGES: tuple[str, ...] = (",
        *(f"    {ref!r}," for ref in merges),
        ")",
        "",
    ]
    TARGET.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {TARGET}: {len(cells)} cells, {len(heights)} row heights, {len(merges)} merges")


if __name__ == "__main__":
    main(
        Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent.parent / "Feasibility template.xlsx")
    )
