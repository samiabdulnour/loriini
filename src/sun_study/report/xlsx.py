"""A one-sheet ``.xlsx`` from the standard library: cells, formulas, a few styles.

An ``.xlsx`` is a zip of a handful of XML parts, and a table that is a
deliverable -- bold headings, percentages formatted as percentages, a formula
that recalculates when somebody edits a figure -- needs no more of the format
than this. The project's runtime dependencies are an approved list and a
spreadsheet library is not on it (D106); ``cos_table`` writes its schedule
the same way, with the parts spelled out in place.

Every formula carries its value as well, so a previewer that never
calculates shows the right number, and the workbook asks to be recalculated
when it is opened, so Excel and LibreOffice show their own.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

__all__ = ["PLAIN", "Format", "Sheet", "column", "write"]

_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml"
#: A number format sits in a double-quoted attribute, and its own literal
#: text -- the ``" m²"`` after an area -- is double-quoted inside it.
_QUOTE = {'"': "&quot;"}


def column(index: int) -> str:
    """The letters of a column, from one: 1 is A, 27 is AA."""
    letters = ""
    while index > 0:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


@dataclass(frozen=True)
class Format:
    """How one kind of cell looks."""

    number: str = ""
    """An Excel number format code: ``0.00``, ``0%``. Empty is General."""
    size: int = 11
    bold: bool = False
    italic: bool = False
    grey: bool = False
    boxed: bool = False
    shaded: bool = False
    """A pale fill: an input somebody is meant to change."""
    align: str = ""


#: The look of a cell nobody styled.
PLAIN = Format()


@dataclass
class Sheet:
    """The cells of one sheet, by row, and how wide its columns are."""

    name: str
    widths: Sequence[float] = ()
    formats: list[Format] = field(default_factory=lambda: [PLAIN])
    _rows: dict[int, dict[int, str]] = field(default_factory=dict)
    _merges: list[str] = field(default_factory=list)

    def style(self, look: Format) -> int:
        """The index of this format, adding it the first time it is asked for."""
        if look not in self.formats:
            self.formats.append(look)
        return self.formats.index(look)

    def _put(self, row: int, col: int, xml: str) -> None:
        self._rows.setdefault(row, {})[col] = xml

    def text(self, row: int, col: int, value: str, look: Format = PLAIN) -> None:
        ref = f"{column(col)}{row}"
        body = f'<is><t xml:space="preserve">{escape(value)}</t></is>'
        self._put(row, col, f'<c r="{ref}" s="{self.style(look)}" t="inlineStr">{body}</c>')

    def number(self, row: int, col: int, value: float, look: Format = PLAIN) -> None:
        ref = f"{column(col)}{row}"
        self._put(row, col, f'<c r="{ref}" s="{self.style(look)}"><v>{value!r}</v></c>')

    def formula(
        self, row: int, col: int, formula: str, value: float | str, look: Format = PLAIN
    ) -> None:
        """A formula, and the value it comes to now. A text value is written as
        a string result -- the empty one an ``IF`` gives when there is no
        answer yet."""
        ref = f"{column(col)}{row}"
        style = self.style(look)
        if isinstance(value, str):
            cached = f"<f>{escape(formula)}</f><v>{escape(value)}</v>"
            self._put(row, col, f'<c r="{ref}" s="{style}" t="str">{cached}</c>')
            return
        cached = f"<f>{escape(formula)}</f><v>{value!r}</v>"
        self._put(row, col, f'<c r="{ref}" s="{style}">{cached}</c>')

    def merge(self, first: str, last: str) -> None:
        self._merges.append(f"{first}:{last}")

    def xml(self) -> str:
        rows = "".join(
            f'<row r="{number}">{"".join(cells[col] for col in sorted(cells))}</row>'
            for number, cells in sorted(self._rows.items())
        )
        cols = "".join(
            f'<col min="{i}" max="{i}" width="{width:g}" customWidth="1"/>'
            for i, width in enumerate(self.widths, start=1)
        )
        merges = (
            f'<mergeCells count="{len(self._merges)}">'
            + "".join(f'<mergeCell ref="{ref}"/>' for ref in self._merges)
            + "</mergeCells>"
            if self._merges
            else ""
        )
        return (
            _DECLARATION
            + f'<worksheet xmlns="{_MAIN}">'
            + '<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>'
            + (f"<cols>{cols}</cols>" if cols else "")
            + f"<sheetData>{rows}</sheetData>{merges}</worksheet>\n"
        )


def _styles(formats: Sequence[Format]) -> str:
    codes = sorted({look.number for look in formats if look.number})
    number_ids = {code: 164 + i for i, code in enumerate(codes)}
    fonts = sorted({(f.size, f.bold, f.italic, f.grey) for f in formats})
    font_ids = {font: i for i, font in enumerate(fonts)}

    def font(size: int, bold: bool, italic: bool, grey: bool) -> str:
        return (
            "<font>"
            + ("<b/>" if bold else "")
            + ("<i/>" if italic else "")
            + f'<sz val="{size}"/>'
            + ('<color rgb="FF595959"/>' if grey else "")
            + '<name val="Arial"/><family val="2"/></font>'
        )

    edge = '<color rgb="FFBFBFBF"/>'
    box = "".join(
        f'<{side} style="thin">{edge}</{side}>' for side in ("left", "right", "top", "bottom")
    )
    cells = []
    for look in formats:
        number = number_ids.get(look.number, 0)
        font_id = font_ids[(look.size, look.bold, look.italic, look.grey)]
        head = (
            f'<xf numFmtId="{number}" fontId="{font_id}"'
            f' fillId="{2 if look.shaded else 0}" borderId="{1 if look.boxed else 0}" xfId="0"'
            + (' applyNumberFormat="1"' if number else "")
            + ' applyFont="1"'
            + (' applyFill="1"' if look.shaded else "")
            + (' applyBorder="1"' if look.boxed else "")
        )
        if look.align:
            cells.append(f'{head} applyAlignment="1"><alignment horizontal="{look.align}"/></xf>')
        else:
            cells.append(f"{head}/>")
    return (
        _DECLARATION
        + f'<styleSheet xmlns="{_MAIN}">'
        + (
            f'<numFmts count="{len(codes)}">'
            + "".join(
                f'<numFmt numFmtId="{number_ids[code]}" formatCode="{escape(code, _QUOTE)}"/>'
                for code in codes
            )
            + "</numFmts>"
            if codes
            else ""
        )
        + f'<fonts count="{len(fonts)}">'
        + "".join(font(*f) for f in fonts)
        + "</fonts>"
        + '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        + '<fill><patternFill patternType="gray125"/></fill>'
        + '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF6D5"/>'
        + '<bgColor indexed="64"/></patternFill></fill></fills>'
        + '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
        + f"<border>{box}<diagonal/></border></borders>"
        + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        + "</cellStyleXfs>"
        + f'<cellXfs count="{len(cells)}">{"".join(cells)}</cellXfs>'
        + '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        + "</styleSheet>\n"
    )


def _relationships(*targets: tuple[str, str]) -> str:
    return (
        _DECLARATION
        + f'<Relationships xmlns="{_PACKAGE_RELS}">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="{_DOC_RELS}/{kind}" Target="{target}"/>'
            for index, (kind, target) in enumerate(targets, start=1)
        )
        + "</Relationships>\n"
    )


def write(destination: Path, sheet: Sheet) -> Path:
    """The workbook, one sheet, at ``destination``; its folder is made."""
    name = escape(sheet.name[:31], _QUOTE)
    workbook = (
        _DECLARATION
        + f'<workbook xmlns="{_MAIN}" xmlns:r="{_DOC_RELS}">'
        + f'<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets>'
        + '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>\n'
    )
    content_types = (
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", _relationships(("officeDocument", "xl/workbook.xml")))
        package.writestr("xl/workbook.xml", workbook)
        package.writestr(
            "xl/_rels/workbook.xml.rels",
            _relationships(("worksheet", "worksheets/sheet1.xml"), ("styles", "styles.xml")),
        )
        package.writestr("xl/worksheets/sheet1.xml", sheet.xml())
        package.writestr("xl/styles.xml", _styles(sheet.formats))
    return destination
