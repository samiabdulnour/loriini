"""An ``.xlsx`` from the standard library: sheets, cells, formulas, a few styles.

An ``.xlsx`` is a zip of a handful of XML parts, and a table that is a
deliverable -- bold headings, percentages formatted as percentages, a formula
that recalculates when somebody edits a figure -- needs no more of the format
than this. The project's runtime dependencies are an approved list and a
spreadsheet library is not on it (D106); ``cos_table`` writes its schedule
the same way, with the parts spelled out in place.

Every formula carries its value as well, so a previewer that never
calculates shows the right number, and the workbook asks to be recalculated
when it is opened, so Excel and LibreOffice show their own.

A workbook may hold several sheets, one of them hidden: the yield workbook
keeps a sheet per option and, hidden, the data each was made from, so a run
can add an option beside the ones already there (``read_text``). That
workbook also wears the office's template's own styles: a ``Workbook`` made
with ``raw_styles`` takes a style table verbatim and its cells are styled by
index into it, rather than by a ``Format`` of this module's.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

__all__ = ["PLAIN", "Format", "Sheet", "Workbook", "column", "read_text", "sheet_names", "write"]

_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml"
#: A number format sits in a double-quoted attribute, and its own literal
#: text -- the ``" m²"`` after an area -- is double-quoted inside it.
_QUOTE = {'"': "&quot;"}

#: The pale fill of an input cell, and the grey of a note.
SHADE = "FFF6D5"
GREY = "595959"


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
    colour: str = ""
    """The text's colour as six hex digits, ``FF0000``; empty is the default."""
    fill: str = ""
    """A fill colour as six hex digits; ``shaded`` is the pale one."""

    @property
    def font_colour(self) -> str:
        return self.colour or (GREY if self.grey else "")

    @property
    def fill_colour(self) -> str:
        return self.fill or (SHADE if self.shaded else "")


#: The look of a cell nobody styled.
PLAIN = Format()

#: How a cell is styled: one of this module's formats, or an index into a
#: style table taken verbatim (``Workbook.raw_styles``).
Look = Format | int


@dataclass
class Sheet:
    """The cells of one sheet, by row, and how wide its columns are."""

    name: str
    widths: Sequence[float] = ()
    formats: list[Format] = field(default_factory=lambda: [PLAIN])
    """Shared with the workbook's other sheets, so one style table serves all."""
    hidden: bool = False
    raw: bool = False
    """The workbook's styles are a table taken verbatim: a ``Format`` here is
    the table's first style, and an index is used as it is."""
    cols_xml: str = ""
    """A ``<cols>`` element verbatim, in place of ``widths``."""
    row_heights: dict[int, float] = field(default_factory=dict)
    tail_xml: str = ""
    """Anything that follows the merged cells: a conditional format, the
    page setup."""
    zoom: int = 0
    print_area: str = ""
    """A range, ``$A$3:$E$107``, printed as the sheet's print area."""
    _rows: dict[int, dict[int, str]] = field(default_factory=dict)
    _merges: list[str] = field(default_factory=list)

    def style(self, look: Look) -> int:
        """The index of this format, adding it the first time it is asked for."""
        if isinstance(look, int):
            return look
        if self.raw:
            return 0
        if look not in self.formats:
            self.formats.append(look)
        return self.formats.index(look)

    def _put(self, row: int, col: int, xml: str) -> None:
        self._rows.setdefault(row, {})[col] = xml

    def has(self, row: int, col: int) -> bool:
        return col in self._rows.get(row, {})

    def text(self, row: int, col: int, value: str, look: Look = PLAIN) -> None:
        ref = f"{column(col)}{row}"
        body = f'<is><t xml:space="preserve">{escape(value)}</t></is>'
        self._put(row, col, f'<c r="{ref}" s="{self.style(look)}" t="inlineStr">{body}</c>')

    def number(self, row: int, col: int, value: float, look: Look = PLAIN) -> None:
        ref = f"{column(col)}{row}"
        self._put(row, col, f'<c r="{ref}" s="{self.style(look)}"><v>{value!r}</v></c>')

    def blank(self, row: int, col: int, look: Look = PLAIN) -> None:
        """An empty cell with a look: an input left for somebody to fill, or
        a border carried across a gap."""
        ref = f"{column(col)}{row}"
        self._put(row, col, f'<c r="{ref}" s="{self.style(look)}"/>')

    def formula(
        self, row: int, col: int, formula: str, value: float | str, look: Look = PLAIN
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
            f'<row r="{number}"'
            + (
                f' ht="{self.row_heights[number]:g}" customHeight="1"'
                if number in self.row_heights
                else ""
            )
            + f">{''.join(cells[col] for col in sorted(cells))}</row>"
            for number, cells in sorted(self._rows.items())
        )
        cols = self.cols_xml or (
            "<cols>"
            + "".join(
                f'<col min="{i}" max="{i}" width="{width:g}" customWidth="1"/>'
                for i, width in enumerate(self.widths, start=1)
            )
            + "</cols>"
            if self.widths
            else ""
        )
        merges = (
            f'<mergeCells count="{len(self._merges)}">'
            + "".join(f'<mergeCell ref="{ref}"/>' for ref in self._merges)
            + "</mergeCells>"
            if self._merges
            else ""
        )
        view = '<sheetView workbookViewId="0"' + (
            f' zoomScale="{self.zoom}" zoomScaleNormal="{self.zoom}"/>'
            if self.zoom
            else ' showGridLines="0"/>'
        )
        return (
            _DECLARATION
            + f'<worksheet xmlns="{_MAIN}">'
            + f"<sheetViews>{view}</sheetViews>"
            + cols
            + f"<sheetData>{rows}</sheetData>{merges}{self.tail_xml}</worksheet>\n"
        )


@dataclass
class Workbook:
    """Several sheets sharing one style table."""

    formats: list[Format] = field(default_factory=lambda: [PLAIN])
    sheets: list[Sheet] = field(default_factory=list)
    raw_styles: str = ""
    """A ``styles.xml`` taken verbatim; the sheets' looks are indices into it."""
    theme: str = ""
    """A ``theme1.xml``, for a style table that names theme colours."""

    def sheet(self, name: str, widths: Sequence[float] = (), *, hidden: bool = False) -> Sheet:
        """A new sheet at the end of the book. A name over 31 characters,
        Excel's limit, is cut to it."""
        made = Sheet(name[:31], widths, self.formats, hidden, raw=bool(self.raw_styles))
        self.sheets.append(made)
        return made

    def write(self, destination: Path) -> Path:
        """The workbook at ``destination``; its folder is made."""
        if not self.sheets:
            raise ValueError("a workbook needs at least one sheet")
        return _write(destination, self.sheets, self.formats, self.raw_styles, self.theme)


def _styles(formats: Sequence[Format]) -> str:
    codes = sorted({look.number for look in formats if look.number})
    number_ids = {code: 164 + i for i, code in enumerate(codes)}
    fonts = sorted({(f.size, f.bold, f.italic, f.font_colour) for f in formats})
    font_ids = {font: i for i, font in enumerate(fonts)}
    fill_colours = sorted({f.fill_colour for f in formats if f.fill_colour})
    fill_ids = {colour: 2 + i for i, colour in enumerate(fill_colours)}

    def font(size: int, bold: bool, italic: bool, colour: str) -> str:
        return (
            "<font>"
            + ("<b/>" if bold else "")
            + ("<i/>" if italic else "")
            + f'<sz val="{size}"/>'
            + (f'<color rgb="FF{colour}"/>' if colour else "")
            + '<name val="Arial"/><family val="2"/></font>'
        )

    edge = '<color rgb="FFBFBFBF"/>'
    box = "".join(
        f'<{side} style="thin">{edge}</{side}>' for side in ("left", "right", "top", "bottom")
    )
    cells = []
    for look in formats:
        number = number_ids.get(look.number, 0)
        font_id = font_ids[(look.size, look.bold, look.italic, look.font_colour)]
        fill_id = fill_ids.get(look.fill_colour, 0)
        head = (
            f'<xf numFmtId="{number}" fontId="{font_id}"'
            f' fillId="{fill_id}" borderId="{1 if look.boxed else 0}" xfId="0"'
            + (' applyNumberFormat="1"' if number else "")
            + ' applyFont="1"'
            + (' applyFill="1"' if fill_id else "")
            + (' applyBorder="1"' if look.boxed else "")
        )
        if look.align:
            cells.append(f'{head} applyAlignment="1"><alignment horizontal="{look.align}"/></xf>')
        else:
            cells.append(f"{head}/>")
    fills = (
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        + "".join(
            f'<fill><patternFill patternType="solid"><fgColor rgb="FF{colour}"/>'
            '<bgColor indexed="64"/></patternFill></fill>'
            for colour in fill_colours
        )
    )
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
        + f'<fills count="{2 + len(fill_colours)}">{fills}</fills>'
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


def _sheet_name_for_formula(name: str) -> str:
    """A sheet's name as a formula quotes it: in single quotes, with a quote
    inside doubled."""
    return "'" + name.replace("'", "''") + "'"


def _write(
    destination: Path,
    sheets: Sequence[Sheet],
    formats: Sequence[Format],
    raw_styles: str = "",
    theme: str = "",
) -> Path:
    listed = "".join(
        f'<sheet name="{escape(sheet.name, _QUOTE)}" sheetId="{index}"'
        + (' state="hidden"' if sheet.hidden else "")
        + f' r:id="rId{index}"/>'
        for index, sheet in enumerate(sheets, start=1)
    )
    print_areas = "".join(
        f'<definedName name="_xlnm.Print_Area" localSheetId="{index}">'
        f"{escape(_sheet_name_for_formula(sheet.name), _QUOTE)}!{sheet.print_area}"
        "</definedName>"
        for index, sheet in enumerate(sheets)
        if sheet.print_area
    )
    workbook = (
        _DECLARATION
        + f'<workbook xmlns="{_MAIN}" xmlns:r="{_DOC_RELS}">'
        + f"<sheets>{listed}</sheets>"
        + (f"<definedNames>{print_areas}</definedNames>" if print_areas else "")
        + '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>\n'
    )
    content_types = (
        _DECLARATION
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" '
        + 'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + f'<Override PartName="/xl/workbook.xml" ContentType="{_OFFICE_TYPE}.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            f'ContentType="{_OFFICE_TYPE}.worksheet+xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + f'<Override PartName="/xl/styles.xml" ContentType="{_OFFICE_TYPE}.styles+xml"/>'
        + (
            '<Override PartName="/xl/theme/theme1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            if theme
            else ""
        )
        + "</Types>\n"
    )
    relationships = [
        ("worksheet", f"worksheets/sheet{index}.xml") for index in range(1, len(sheets) + 1)
    ]
    relationships.append(("styles", "styles.xml"))
    if theme:
        relationships.append(("theme", "theme/theme1.xml"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", _relationships(("officeDocument", "xl/workbook.xml")))
        package.writestr("xl/workbook.xml", workbook)
        package.writestr("xl/_rels/workbook.xml.rels", _relationships(*relationships))
        for index, sheet in enumerate(sheets, start=1):
            package.writestr(f"xl/worksheets/sheet{index}.xml", sheet.xml())
        package.writestr("xl/styles.xml", raw_styles or _styles(formats))
        if theme:
            package.writestr("xl/theme/theme1.xml", theme)
    return destination


def write(destination: Path, sheet: Sheet) -> Path:
    """A workbook of one sheet, at ``destination``; its folder is made."""
    return _write(destination, [sheet], sheet.formats)


# -- reading one cell back ---------------------------------------------------------------

_NS = {"m": _MAIN, "r": _DOC_RELS, "p": _PACKAGE_RELS}


def _sheet_parts(package: zipfile.ZipFile) -> dict[str, str]:
    """Sheet name -> its part's path inside the package."""
    book = ElementTree.fromstring(package.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(package.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.get("Id"): rel.get("Target", "")
        for rel in rels.findall("p:Relationship", _NS)
        if rel.get("Id")
    }
    parts: dict[str, str] = {}
    for sheet in book.findall("m:sheets/m:sheet", _NS):
        name = sheet.get("name")
        target = targets.get(sheet.get(f"{{{_DOC_RELS}}}id", ""), "")
        if not name or not target:
            continue
        parts[name] = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    return parts


def sheet_names(path: Path) -> list[str]:
    """The sheets of a workbook, in order; empty for a file that is not one."""
    try:
        with zipfile.ZipFile(path) as package:
            return list(_sheet_parts(package))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError):
        return []


def read_text(path: Path, sheet_name: str, ref: str) -> str | None:
    """The text in one cell of a workbook -- written here as an inline string,
    or by Excel afterwards as a shared one -- or ``None`` when the sheet or
    the cell is not there."""
    try:
        with zipfile.ZipFile(path) as package:
            part = _sheet_parts(package).get(sheet_name)
            if part is None or part not in package.namelist():
                return None
            sheet = ElementTree.fromstring(package.read(part))
            shared: list[str] = []
            if "xl/sharedStrings.xml" in package.namelist():
                strings = ElementTree.fromstring(package.read("xl/sharedStrings.xml"))
                shared = [
                    "".join(t.text or "" for t in item.iter(f"{{{_MAIN}}}t"))
                    for item in strings.findall("m:si", _NS)
                ]
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError):
        return None
    for cell in sheet.iter(f"{{{_MAIN}}}c"):
        if cell.get("r") != ref:
            continue
        kind = cell.get("t", "")
        if kind == "inlineStr":
            return "".join(t.text or "" for t in cell.iter(f"{{{_MAIN}}}t"))
        value = cell.find("m:v", _NS)
        if value is None:
            return None
        if kind == "s":
            index = int(value.text or "0")
            return shared[index] if 0 <= index < len(shared) else None
        return value.text
    return None
