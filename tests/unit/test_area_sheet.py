"""The yield analysis's sheet and workbook.

The drawing is tested pure, as the other sheets are; drawing it onto a
layout is tested against a scripted Archicad; and the workbook's formulas
are read back and recalculated from nothing -- here, by the few words of
Excel the sheet uses, and by LibreOffice Calc where it is installed -- so
that what Excel shows after an edit is what Loriini said.
"""

from __future__ import annotations

import json
import operator
import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from sun_study.archicad import layout as layout_module
from sun_study.archicad import naming
from sun_study.archicad.area_sheet import (
    AREA_WORD,
    area_drawing,
    draw_area_sheet,
    sheet_word,
    view_frame,
)
from sun_study.archicad.layout import LayoutSheet
from sun_study.report import xlsx
from sun_study.report.area_table import (
    DATA_SHEET,
    feasibility_from_dict,
    feasibility_to_dict,
    notes,
    options_in,
    rows,
    text_lines,
    write_workbook,
)
from sun_study.rules.area_yield import (
    COMMERCIAL,
    RESIDENTIAL,
    Efficiencies,
    Feasibility,
    Floor,
    Permissible,
    UnitRates,
    feasibility,
)
from tests.unit.test_archicad_adapter import connect
from tests.unit.test_area_yield import SITE, template, template_floors

# -- the rows -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def a_person_who_picks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Somebody asked which master layout the sheet goes on, who picks the
    first the project offers."""
    monkeypatch.setattr(layout_module, "ask_master", lambda names: names[0])


def test_the_rows_are_the_office_sheets_in_its_order_and_words() -> None:
    listed = rows(template())
    sections = [row.label for row in listed if row.kind == "section"]
    assert sections == [
        "Site Area",
        "FSR",
        "GFA",
        "Residential GFA Split",
        "Market Unit Mix",
        "Number of Storeys",
        "Parking Requirements",
    ], "no affordable block without an affordable share"
    # The same label serves two blocks -- a unit type in the mix and in the
    # parking -- so the rows are read in order, the first of each name first.
    first = {}
    for row in listed:
        if row.label and row.label not in first:
            first[row.label] = row.cells
    assert first["Site Area"] == ("6,704 m²", "", "")
    assert first["Residential FSR"] == ("2.80", "2.81", "+0.01")
    assert first["Commercial FSR"] == ("0.60", "0.55", "-0.05")
    assert first["Total FSR"] == ("3.40", "3.35", "-0.05")
    assert first["Residential GFA"] == ("18,771 m²", "18,814 m²", "+43 m²")
    assert first["Commercial GFA"] == ("4,022 m²", "3,655 m²", "-367 m²")
    assert first["Total GFA"] == ("22,794 m²", "22,469 m²", "-325 m²")
    assert first["2-bed"] == ("75 m² / 70 %", "154.1", "154.4")
    assert first["Residential"] == ("15", "", "")
    assert first["Visitors"] == ("0.1 / 0 a unit", "22.1", "0.0")
    assert first["Commercial"] == ("1/100 / 1/400 m²", "36.6", "9.1")
    assert first["Total Parking"] == ("", "268.2", "207.7")
    assert first["Total Basements"] == ("", "4.0", "3.1")
    parking = [row.cells for row in listed if row.label == "2-bed"][1]
    assert parking == ("1 / 1 a unit", "154.4", "154.4")
    assert not any("Retail" in row.label for row in listed), "the shops are commercial (D159)"


def test_the_notes_say_the_efficiencies_the_averages_and_the_source() -> None:
    said = notes(template())
    assert said[0] == (
        "Building efficiencies (BEA to GFA / GFA to NLA) : Residential 0.725 / 0.85, "
        "Commercial 0.85 / 0.9"
    )
    assert said[1] == "Market units : average NLA 72.5 m², average GFA 85.3 m²"
    assert "Parking : 40 m² a space, basement over 40 % of the site" in said
    assert said[-1] == "BEA : 19 slabs"
    assert notes(template(), ["Measured from 13 slabs."])[-1] == "Measured from 13 slabs."


def test_the_printed_table_lines_up() -> None:
    printed = text_lines(template())
    assert any(line.startswith("  Total GFA") and "22,469 m²" in line for line in printed)
    assert any(line.startswith("  1-bed") and "44.1" in line for line in printed)
    assert any(line.startswith("  PARKING REQUIREMENTS") for line in printed)


# -- the sheet ---------------------------------------------------------------------


def test_the_sheet_carries_the_title_the_table_the_notes_and_the_legend() -> None:
    drawing = area_drawing(template(), ["Measured from 19 slabs."])
    said = [text.text for text in drawing.texts]
    assert said[:2] == ["PRELIMINARY YIELD ANALYSIS", "Option 01"]
    for expected in ("FSR", "Total GFA", "22,469 m²", "PARKING REQUIREMENTS", "Notes:", "Legend"):
        assert expected in said
    assert {"Residential", "Commercial"} <= set(said)
    assert not any("Retail" in text for text in said), "one use for the shops and the offices"
    assert "Measured from 19 slabs." in said
    assert all(text.at[1] <= 0.0 for text in drawing.texts), "it hangs down from its corner"
    assert all(text.at[0] <= 0.2 for text in drawing.texts), "and stays in its columns"
    # Two swatches, each a box of close lines in its colour; the shops' blush is gone.
    colours = {line.colour for line in drawing.lines}
    assert {"#FFF4A8", "#B894F2"} <= colours and "#F6B8C8" not in colours
    # A heading sits on its rule, not across it, and the row under clears it.
    rules = sorted(
        {line.points[0][1] for line in drawing.lines if line.weight_mm == 0.25}, reverse=True
    )
    headings = [text for text in drawing.texts if text.height_mm == 4.5]
    assert len(rules) == len({text.at[1] for text in headings}) > 5
    for text in drawing.texts:
        half = text.height_mm / 2000.0
        for rule in rules:
            assert not (text.at[1] - half - 0.0005 < rule < text.at[1] + half + 0.0005), text.text


def test_the_view_goes_right_of_the_table_and_left_of_the_title_block() -> None:
    a1 = LayoutSheet(841.0, 594.0, 10.0, 10.0, 10.0, 10.0)
    x0, y0, x1, y1 = view_frame(a1) or (0, 0, 0, 0)
    assert x0 == pytest.approx((10 + 15 + 200 + 15) / 1000)
    assert x1 == pytest.approx((841 - 10 - 115 - 15) / 1000)
    assert (y0, y1) == pytest.approx((0.025, 0.569))
    assert view_frame(LayoutSheet(297.0, 210.0, 10.0, 10.0, 10.0, 10.0)) is None, "no room on A4"


def test_the_sheet_is_named_for_its_option() -> None:
    assert sheet_word("Option 01") == f"{AREA_WORD} - Option 01"
    assert sheet_word("  Tower  B ") == f"{AREA_WORD} - Tower B"
    assert sheet_word("") == AREA_WORD


def layout_book(*extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "navigatorItemTree": {
            "navigatorItemId": {"guid": "ROOT"},
            "name": "root",
            "children": [
                {
                    "navigatorItem": {
                        "type": "MasterLayoutItem",
                        "name": "A1 no scale",
                        "navigatorItemId": {"guid": "M1"},
                        "children": [],
                    }
                },
                *extra,
            ],
        }
    }


SHEET_SETTINGS = {
    "layoutSettings": [
        {
            "horizontalSize": 841.0,
            "verticalSize": 594.0,
            "leftMargin": 10.0,
            "topMargin": 10.0,
            "rightMargin": 10.0,
            "bottomMargin": 10.0,
        }
    ]
}


def test_the_sheet_is_drawn_straight_onto_a_layout_of_its_own() -> None:
    connection, transport = connect(
        {
            "GetNavigatorItemTree": layout_book(),
            "CreateLayout": {"databases": [{"databaseId": {"guid": "LAY"}}]},
            "GetLayoutSettings": SHEET_SETTINGS,
            "SetCurrentDatabase": {"success": True},
            "GetCurrentDatabase": {"databaseId": {"guid": "LAY"}, "windowType": "Layout"},
            "GetAttributesByType": {"attributes": []},
            "GetPenTables": {"penTables": []},
            "CreatePolylines": {"elements": [{"elementId": {"guid": "P"}}]},
            "CreateTexts": {"success": True, "elements": [{"guid": "T"}]},
        }
    )
    report = draw_area_sheet(connection, template(), master_layout="A1 no scale")
    assert report.name == naming.named(sheet_word("Option 01")) and report.database_id == "LAY"
    assert report.master == "A1 no scale" and report.view == ""
    assert report.texts > 60 and report.lines > 30
    texts = transport.parameters_for("CreateTexts")["texts"]
    title = next(t for t in texts if t["text"] == "PRELIMINARY YIELD ANALYSIS")
    assert 0.02 < title["coordinate"]["x"] < 0.03 and 0.55 < title["coordinate"]["y"] < 0.58
    assert all(0.0 < t["coordinate"]["y"] < 0.58 for t in texts), "everything on the sheet"
    assert "CreateDrawings" not in transport.commands(), "no view was asked for"


def test_a_named_view_is_placed_beside_the_table_and_framed() -> None:
    axo = {
        "navigatorItem": {
            "type": "AxonometryItem",
            "name": "Yield Axo",
            "navigatorItemId": {"guid": "VIEW"},
            "children": [],
        }
    }
    connection, transport = connect(
        {
            "GetNavigatorItemTree": layout_book(axo),
            "CreateLayout": {"databases": [{"databaseId": {"guid": "LAY"}}]},
            "GetLayoutSettings": SHEET_SETTINGS,
            "GetViewSettings": {"viewSettings": [{}]},
            "ChangeWindow": {"success": True},
            "GetElementsByType": {"elements": [{"elementId": {"guid": "D1"}}]},
            "GetDetailsOfElements": {
                "detailsOfElements": [{"details": {"customName": "Yield Axo"}}]
            },
            "CreateDrawings": {"elements": [{"elementId": {"guid": "D1"}}]},
            "SetCurrentDatabase": {"success": True},
            "GetCurrentDatabase": {"databaseId": {"guid": "LAY"}, "windowType": "Layout"},
            "GetAttributesByType": {"attributes": []},
            "GetPenTables": {"penTables": []},
            "CreatePolylines": {"elements": [{"elementId": {"guid": "P"}}]},
            "CreateTexts": {"success": True, "elements": [{"guid": "T"}]},
            "ArrangeDrawings": {"success": True, "arranged": 1},
        }
    )
    report = draw_area_sheet(
        connection, template(), view=" yield axo ", master_layout="A1 no scale"
    )
    assert report.view == "Yield Axo", report.notes
    arranged = transport.parameters_for("ArrangeDrawings")
    frame = arranged["drawings"][0]["frame"]
    assert arranged["drawings"][0]["guid"] == "D1"
    assert frame["xMin"] == pytest.approx(0.24) and frame["xMax"] == pytest.approx(0.701)


def test_a_view_nobody_has_costs_the_picture_and_not_the_sheet() -> None:
    connection, _ = connect(
        {
            "GetNavigatorItemTree": layout_book(),
            "CreateLayout": {"databases": [{"databaseId": {"guid": "LAY"}}]},
            "GetLayoutSettings": SHEET_SETTINGS,
            "SetCurrentDatabase": {"success": True},
            "GetCurrentDatabase": {"databaseId": {"guid": "LAY"}, "windowType": "Layout"},
            "GetAttributesByType": {"attributes": []},
            "GetPenTables": {"penTables": []},
            "CreatePolylines": {"elements": [{"elementId": {"guid": "P"}}]},
            "CreateTexts": {"success": True, "elements": [{"guid": "T"}]},
        }
    )
    report = draw_area_sheet(connection, template(), view="Nothing Like It")
    assert report.view == "" and report.texts > 60
    assert any("no view called 'Nothing Like It'" in note for note in report.notes)


# -- the workbook ------------------------------------------------------------------


def cells(path: Path, part: str = "xl/worksheets/sheet1.xml") -> dict[str, tuple[str, str]]:
    """Every cell of a sheet: its formula, or empty, and its value."""
    with zipfile.ZipFile(path) as package:
        xml = package.read(part).decode()
    found: dict[str, tuple[str, str]] = {}
    for ref, body in re.findall(r'<c r="([A-Z]+\d+)"[^>]*?(?:/>|>(.*?)</c>)', xml):
        formula = re.search(r"<f>(.*?)</f>", body or "")
        value = re.search(r"<v>(.*?)</v>|<t[^>]*>(.*?)</t>", body or "")
        found[ref] = (
            formula.group(1).replace("&gt;", ">").replace("&lt;", "<") if formula else "",
            (value.group(1) or value.group(2) or "") if value else "",
        )
    return found


def test_every_part_of_the_workbook_is_well_formed(tmp_path: Path) -> None:
    import xml.dom.minidom

    path = write_workbook(tmp_path / "yield.xlsx", template(), note="Darlinghurst")
    with zipfile.ZipFile(path) as package:
        for name in package.namelist():
            xml.dom.minidom.parseString(package.read(name))
    assert xlsx.sheet_names(path) == ["Option 01", DATA_SHEET]


def test_the_workbook_is_the_template_with_its_retail_rows_and_columns_closed_up(
    tmp_path: Path,
) -> None:
    """The office's addresses, for a five-type mix, less the template's row
    or column for retail wherever it has one a use (D159): the site in C6,
    the permissible FSR in C10:C11, the proposed GFA in D16:D17 from the
    storey table's totals, the units in D27:E31, the commercial parking in
    row 77, the efficiencies in C83:E84, and the storey table's BEA, GFA and
    NSA in M:O, P:R and S:U, the unit mix from X."""
    table = cells(write_workbook(tmp_path / "yield.xlsx", template()))
    assert table["A1"][1] == "Preliminary Yield Analysis" and table["A3"][1] == "Option 01"
    assert table["C6"] == ("", "6704.0")
    assert table["C10"] == ("", "2.8") and table["C11"] == ("", "0.6")
    assert [table[f"A{row}"][1] for row in (10, 11, 12)] == [
        "Residential FSR",
        "Commercial FSR",
        "Total FSR",
    ]
    assert table["C12"][0] == "SUM(C10:C11)" and float(table["C12"][1]) == pytest.approx(3.4)
    assert table["D10"][0] == 'IF($C$6>0,D16/$C$6,"")'
    assert float(table["D10"][1]) == pytest.approx(2.80634696)
    assert table["A14"][1] == "GFA" and table["A18"][1] == "Total GFA"
    assert table["C16"][0] == 'IF(C10<>"",$C$6*C10,"")'
    assert table["D16"][0] == "P133", "the storey table's residential GFA total"
    assert float(table["D16"][1]) == pytest.approx(18813.75)
    assert table["D17"][0] == "Q133", "and its commercial"
    assert float(table["D17"][1]) == pytest.approx(3655.0)
    assert table["D18"][0] == "SUM(D16:D17)" and float(table["D18"][1]) == pytest.approx(22468.75)
    assert table["A24"][1] == "Market Unit Mix" and table["A27"][1] == "Studio"
    assert table["E28"][0] == "$D$16/$C$92*C28*$C$21"
    assert float(table["E28"][1]) == pytest.approx(44.115)
    assert table["C92"][0] == "C91/$E$83" and float(table["C92"][1]) == pytest.approx(85.2941176)
    assert table["C83"] == ("", "0.725") and table["E84"] == ("", "0.9")
    assert [table[f"A{row}"][1] for row in (83, 84)] == ["Residential", "Commercial"]
    assert table["D63"][0] == "E28*B63"
    assert table["A77"][1] == "Commercial" and table["D77"][0] == "B77*$D$17"
    assert table["D78"][0] == "SUM(D76:D77)" and float(table["D78"][1]) == pytest.approx(268.15375)
    assert table["D79"][0] == 'IF($C$6>0,D78*C102/($C$6*C103),"")'
    assert float(table["D79"][1]) == pytest.approx(3.99990677)
    assert table["C54"][0] == 'COUNTIF(M115:M132,">0")' and table["C54"][1] == "15.0"
    assert table["C55"][0] == 'COUNTIF(O115:O132,">0")-C54', "the BEA's total column"
    # The storey table: the top level first, the ground at the foot, totals under.
    assert table["J115"][1] == "Level 17" and table["J132"][1] == "Ground Floor"
    assert [table[f"{col}113"][1] for col in "MNOPQRSTU"] == ["Resi", "Comm", "Total"] * 3
    assert table["M132"] == ("", "50.0") and table["N132"] == ("", "2800.0")
    assert table["O132"][0] == "SUM(M132:N132)"
    assert table["P115"][0] == "M115*$C$83" and table["S115"][0] == "P115*$E$83"
    assert table["Q132"][0] == "N132*$C$84" and table["T132"][0] == "Q132*$E$84"
    assert table["M133"][0] == "SUM(M115:M132)" and float(table["M133"][1]) == 25950.0
    assert float(table["N133"][1]) == 4300.0
    assert table["L115"][0] == "L116+K115", "heights add up from the ground"
    assert table["X113"][1] == "St" and table["AM113"][1] == "GFA", "the mix, three columns over"
    assert "Retail" not in {value for _formula, value in table.values()}


def test_the_workbook_wears_the_templates_own_look(tmp_path: Path) -> None:
    """The template's style table and theme, verbatim, and each cell styled
    as the template cell it stands for: the main block is the template's
    with its four retail rows closed up, and the storey table the
    template's with its three retail columns closed up, taking its first,
    middle and last level rows for however many levels the massing has."""
    from sun_study.report import feasibility_style as look

    path = write_workbook(tmp_path / "yield.xlsx", template())
    with zipfile.ZipFile(path) as package:
        assert package.read("xl/styles.xml").decode() == look.STYLES_XML
        assert package.read("xl/theme/theme1.xml").decode() == look.THEME_XML
        sheet_xml = package.read("xl/worksheets/sheet1.xml").decode()
        book_xml = package.read("xl/workbook.xml").decode()
    styles = {ref: int(st) for ref, st in re.findall(r'<c r="([A-Z]+\d+)" s="(\d+)"', sheet_xml)}
    by_row: dict[int, dict[int, int]] = {}
    for ref, st in look.CELLS.items():
        letters = re.sub(r"\d", "", ref)
        by_row.setdefault(int(ref[len(letters) :]), {})[column_number(letters)] = st
    # The template's rows for retail -- its FSR, GFA, parking, efficiencies --
    # and its columns: the BEA's, the GFA's and the NSA's third, O, S and W.
    retail_rows, retail_cols = {12, 19, 80, 88}, {15, 19, 23}
    kept = [row for row in range(1, 108) if row not in retail_rows]
    for mine, theirs in enumerate(kept, start=1):
        for col, st in by_row.get(theirs, {}).items():
            ref = f"{xlsx.column(col)}{mine}"
            assert styles.get(ref) == st, f"{ref} as the template's {xlsx.column(col)}{theirs}"
    assert styles["C6"] == look.CELLS["C6"] and styles["A5"] == look.CELLS["A5"]

    def closed_up(col: int) -> int:
        return col - sum(1 for retail in retail_cols if retail < col)

    level_rows = [(115, 115), (116, 116), (116, 131), (135, 132), (136, 133)]
    head_and_foot = [(row, row) for row in range(111, 115)] + [(137 + i, 134 + i) for i in range(5)]
    for theirs, mine in level_rows + head_and_foot:
        for col, st in by_row[theirs].items():
            if col < 10 or col in retail_cols:
                continue
            ref = f"{xlsx.column(closed_up(col))}{mine}"
            assert styles.get(ref) == st, f"{ref} as the template's {xlsx.column(col)}{theirs}"
    assert styles["J115"] == look.CELLS["J115"], "the top level as the template's top row"
    assert styles["M116"] == look.CELLS["M116"] and styles["M132"] == look.CELLS["M135"]
    assert styles["M133"] == look.CELLS["M136"], "the total row"
    assert styles["O115"] == look.CELLS["P115"], "the BEA's total, where retail's was"
    assert styles["X115"] == look.CELLS["AA115"] and styles["AM115"] == look.CELLS["AP115"]
    widths = re.search(r"<cols>.*?</cols>", sheet_xml)
    assert widths is not None
    # The template's widths go with their columns: the main block's where they
    # are, the narrow gap (Y), the labels (Z) and the difference (AP) moved.
    assert '<col min="1" max="1" width="25.85546875" customWidth="1"/>' in widths.group(0)
    assert '<col min="8" max="8" width="10.5703125" style="11" customWidth="1"/>' in widths.group(0)
    assert '<col min="22" max="22" width="4.7109375" customWidth="1"/>' in widths.group(0)
    assert '<col min="23" max="23" width="10.7109375" customWidth="1"/>' in widths.group(0)
    assert '<col min="39" max="39" width="17" bestFit="1" customWidth="1"/>' in widths.group(0)
    assert 'min="25"' not in widths.group(0) and 'min="42"' not in widths.group(0)
    assert '<row r="3" ht="23.25" customHeight="1">' in sheet_xml
    assert 'sqref="AM114:AM133"' in sheet_xml, "the colour scale over the difference column"
    assert "'Option 01'!$A$3:$E$103" in book_xml, "the print area"


def column_number(letters: str) -> int:
    """A column's number from its letters: A is 1, AA is 27."""
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - ord("A") + 1
    return number


def test_a_second_option_is_added_beside_the_first_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "yield.xlsx"
    write_workbook(path, template())
    second = feasibility(template_floors()[:5], option="Option 02", site_area_m2=6704.0)
    write_workbook(path, second)
    assert xlsx.sheet_names(path) == ["Option 01", "Option 02", DATA_SHEET]
    kept = options_in(path)
    assert [option.option for option in kept] == ["Option 01", "Option 02"]
    assert kept[0].gfa(RESIDENTIAL) == pytest.approx(18813.75)
    assert kept[0].permissible.commercial == 0.6 and kept[0].source == ("BEA : 19 slabs",)
    assert cells(path, "xl/worksheets/sheet2.xml")["A3"][1] == "Option 02"
    # The same name again replaces its sheet rather than adding a third.
    write_workbook(path, feasibility(template_floors()[:3], option="option 01"))
    assert [option.option for option in options_in(path)] == ["Option 02", "option 01"]


def test_the_options_data_round_trips() -> None:
    sheet = feasibility(template_floors(), site_area_m2=6704.0, affordable_share=0.2)
    back = feasibility_from_dict(json.loads(json.dumps(feasibility_to_dict(sheet))))
    assert back == sheet


def older_option_data() -> dict[str, Any]:
    """The template's Option 01 as a workbook saved while retail was a use of
    its own kept it: the shops in a retail column, a retail FSR of 0.4 beside
    a commercial 0.2, retail efficiencies and a retail parking rate."""
    data = feasibility_to_dict(template())
    ground = data["levels"][0]
    ground["retail_m2"], ground["commercial_m2"] = ground["commercial_m2"], 0.0
    data["permissible"] = {"residential": 2.8, "commercial": 0.2, "retail": 0.4}
    data["efficiencies"].update(gfa_retail=0.95, nla_retail=0.90)
    data["parking"]["retail"] = {"sepp": 1 / 30, "dcp": 1 / 400}
    return data


def test_an_older_workbooks_retail_floor_reads_back_as_commercial(tmp_path: Path) -> None:
    """A workbook written while retail was a use of its own: its options come
    back with the retail floor and the retail FSR added to the commercial,
    not dropped, and the shops at commercial's efficiencies and parking rate
    (D159). A run that adds an option keeps them so."""
    path = tmp_path / "yield.xlsx"
    book = xlsx.Workbook()
    book.sheet("Option 01").text(1, 1, "Preliminary Yield Analysis")
    book.sheet(DATA_SHEET, hidden=True).text(1, 1, json.dumps([older_option_data()]))
    book.write(path)
    (old,) = options_in(path)
    assert old.levels[0].commercial_m2 == 2800.0, "the shops on the ground, as commercial"
    assert old.bea(COMMERCIAL) == pytest.approx(4300.0) and old.gfa(COMMERCIAL) == 3655.0
    assert old.permissible.commercial == pytest.approx(0.6)
    assert old.efficiencies == Efficiencies() and old.parking.commercial == UnitRates(0.01, 0.0025)
    assert replace(old, permissible=Permissible(2.8, 0.6)) == template()
    write_workbook(path, feasibility(template_floors()[:5], option="Option 02", site_area_m2=SITE))
    kept = options_in(path)
    assert [option.option for option in kept] == ["Option 01", "Option 02"]
    assert kept[0].gfa(COMMERCIAL) == pytest.approx(3655.0)
    table = cells(path)
    assert table["A3"][1] == "Option 01" and table["N132"] == ("", "2800.0")
    assert table["D17"][0] == "Q133" and float(table["D17"][1]) == pytest.approx(3655.0)


def test_a_workbook_loriini_did_not_write_is_left_alone(tmp_path: Path) -> None:
    theirs = tmp_path / "Feasibility template.xlsx"
    book = xlsx.Workbook()
    book.sheet("Option 01").text(1, 1, "theirs")
    book.write(theirs)
    with pytest.raises(FileExistsError, match="did not write"):
        write_workbook(theirs, template())
    assert cells(theirs)["A1"][1] == "theirs"
    assert options_in(theirs) == []


# -- the workbook worked out again, here ------------------------------------------

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_TOKEN = re.compile(
    r'\s*(?:(?P<number>\d+(?:\.\d+)?)|(?P<text>"[^"]*")'
    r"|(?P<ref>\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)"
    r"|(?P<function>[A-Z]+)\(|(?P<op><>|>=|<=|[-+*/(),<>=]))"
)
_ARITHMETIC: dict[str, Callable[[float, float], float]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
}
Value = float | str | bool | None
Node = Callable[[], Any]


def written_cells(path: Path) -> dict[str, tuple[str, Value]]:
    """Every cell the first sheet has: its formula, or empty, and what it
    holds -- a number, a text, or ``None`` for a cell written empty."""
    with zipfile.ZipFile(path) as package:
        root = ElementTree.fromstring(package.read("xl/worksheets/sheet1.xml"))
    found: dict[str, tuple[str, Value]] = {}
    for cell in root.iter(f"{_MAIN}c"):
        kind, formula = cell.get("t", ""), cell.findtext(f"{_MAIN}f") or ""
        value = cell.findtext(f"{_MAIN}v")
        held: Value
        if kind == "inlineStr":
            held = "".join(t.text or "" for t in cell.iter(f"{_MAIN}t"))
        elif kind == "str":
            held = value or ""
        else:
            held = None if value is None else float(value)
        found[str(cell.get("r"))] = (formula, held)
    return found


def _number(value: Value) -> float:
    """A value in arithmetic, as Excel takes it: an empty cell is nothing,
    and a text is an error -- a formula that names a label or an empty
    answer where it wants a number is wrong."""
    assert not isinstance(value, str), f"arithmetic on the text {value!r}"
    return float(value or 0.0)


def _compare(left: Value, op: str, right: Value) -> bool:
    if left is None:
        left = "" if isinstance(right, str) else 0.0
    if right is None:
        right = "" if isinstance(left, str) else 0.0
    if isinstance(left, str) != isinstance(right, str):
        equal, less = False, not isinstance(left, str)  # a number sorts before a text
    else:
        equal, less = left == right, left < right  # type: ignore[operator]
    return {
        "=": equal,
        "<>": not equal,
        "<": less,
        "<=": less or equal,
        ">": not (less or equal),
        ">=": not less,
    }[op]


class Recalculation:
    """The sheet's formulas worked out from its inputs, in the words of Excel
    the sheet uses -- IF, AND, SUM, COUNTIF, SUMPRODUCT, arithmetic and
    comparison -- with every cell a formula names kept, to be checked."""

    def __init__(self, cells_: dict[str, tuple[str, Value]]) -> None:
        self.cells = cells_
        self.done: dict[str, Value] = {}
        self.working: set[str] = set()
        self.named: set[str] = set()

    def value(self, ref: str) -> Value:
        ref = ref.replace("$", "")
        self.named.add(ref)
        if ref not in self.done:
            assert ref not in self.working, f"{ref} is worked out from itself"
            self.working.add(ref)
            formula, held = self.cells.get(ref, ("", None))
            self.done[ref] = self.evaluate(formula) if formula else held
            self.working.discard(ref)
        return self.done[ref]

    def area(self, first: str, last: str) -> list[Value]:
        def split(ref: str) -> tuple[int, int]:
            letters = re.sub(r"[\d$]", "", ref)
            return column_number(letters), int(re.sub(r"[A-Z$]", "", ref))

        (c0, r0), (c1, r1) = split(first), split(last)
        self.named.update({first.replace("$", ""), last.replace("$", "")})
        return [
            self.value(f"{xlsx.column(col)}{row}")
            for row in range(r0, r1 + 1)
            for col in range(c0, c1 + 1)
        ]

    def evaluate(self, formula: str) -> Value:
        tokens: list[tuple[str, str]] = []
        at = 0
        while at < len(formula):
            found = _TOKEN.match(formula, at)
            assert found and found.lastgroup, f"cannot read {formula[at:]!r} in {formula!r}"
            tokens.append((found.lastgroup, found[found.lastgroup]))
            at = found.end()
        self.tokens, self.at = tokens, 0
        node = self._comparison()
        assert self.at == len(tokens), f"{formula!r} has more than one expression"
        return node()  # type: ignore[no-any-return]

    def _peek(self) -> str | None:
        return self.tokens[self.at][1] if self.at < len(self.tokens) else None

    def _take(self) -> tuple[str, str]:
        self.at += 1
        return self.tokens[self.at - 1]

    def _comparison(self) -> Node:
        left = self._sum()
        if self._peek() in ("=", "<>", "<", "<=", ">", ">="):
            op = self._take()[1]
            right = self._sum()
            return lambda: _compare(left(), op, right())
        return left

    def _sum(self) -> Node:
        node = self._product()
        while self._peek() in ("+", "-"):
            node = self._binary(self._take()[1], node, self._product())
        return node

    def _product(self) -> Node:
        node = self._unary()
        while self._peek() in ("*", "/"):
            node = self._binary(self._take()[1], node, self._unary())
        return node

    @staticmethod
    def _binary(op: str, left: Node, right: Node) -> Node:
        return lambda: _ARITHMETIC[op](_number(left()), _number(right()))

    def _unary(self) -> Node:
        if self._peek() == "-":
            self._take()
            operand = self._unary()
            return lambda: -_number(operand())
        return self._primary()

    def _primary(self) -> Node:
        kind, text = self._take()
        if kind == "number":
            return lambda: float(text)
        if kind == "text":
            return lambda: text[1:-1]
        if kind == "ref":
            if ":" in text:
                first, last = text.split(":")
                return lambda: self.area(first, last)
            return lambda: self.value(text)
        if kind == "function":
            args: list[Node] = []
            while self._peek() != ")":
                args.append(self._comparison())
                if self._peek() == ",":
                    self._take()
            self._take()
            return self._function(text, args)
        assert text == "(", f"{text!r} where a value was wanted"
        node = self._comparison()
        assert self._take()[1] == ")"
        return node

    @staticmethod
    def _function(name: str, args: list[Node]) -> Node:
        def flat(value: Any) -> list[Value]:
            return value if isinstance(value, list) else [value]

        def truth(value: Value) -> bool:
            assert not isinstance(value, str), f"a condition that is the text {value!r}"
            return bool(value)

        if name == "IF":
            condition, yes, no = args
            return lambda: yes() if truth(condition()) else no()
        if name == "AND":
            return lambda: all(truth(arg()) for arg in args)
        if name == "SUM":
            return lambda: sum(
                (value for arg in args for value in flat(arg()) if isinstance(value, float)), 0.0
            )
        if name == "COUNTIF":
            area, criterion = args

            def counted() -> float:
                rule = criterion()
                assert isinstance(rule, str) and rule.startswith(">"), rule
                bound = float(rule[1:])
                return float(sum(1 for v in area() if isinstance(v, float) and v > bound))

            return counted
        if name == "SUMPRODUCT":
            first, second = args
            return lambda: sum(
                (_number(a) * _number(b) for a, b in zip(first(), second(), strict=True)), 0.0
            )
        raise AssertionError(f"{name} is not a function the sheet uses")


def test_every_formula_comes_to_the_value_written_beside_it(tmp_path: Path) -> None:
    """Calc is not on every machine, so the workbook is worked out again
    here from its inputs alone: every formula must come to the value Loriini
    cached beside it, name only cells the sheet has, and never itself. A
    formula left pointing at a row or a column that was retail's names the
    wrong figure, a label, or nothing at all."""
    affordable = feasibility(
        template_floors(),
        site_area_m2=SITE,
        permissible=Permissible(2.8, 0.6),
        affordable_share=0.2,
    )
    for case, sheet in (("template", template()), ("affordable", affordable)):
        written = written_cells(write_workbook(tmp_path / f"{case}.xlsx", sheet))
        book = Recalculation(written)
        formulas = {ref: (f, held) for ref, (f, held) in written.items() if f}
        assert len(formulas) > 350, "the whole sheet, not a corner of it"
        for ref, (formula, cached) in formulas.items():
            got = book.value(ref)
            if isinstance(cached, str):
                assert got == cached, f"{case} {ref} ={formula} came to {got!r}"
            else:
                assert isinstance(got, float), f"{case} {ref} ={formula} came to {got!r}"
                assert got == pytest.approx(cached, rel=1e-9, abs=1e-9), (
                    f"{case} {ref} ={formula} came to {got!r}, not {cached!r}"
                )
        unwritten = sorted(book.named - set(written))
        assert not unwritten, f"{case}: formulas name cells the sheet does not have: {unwritten}"


def _calc_available() -> bool:
    return shutil.which("soffice") is not None


def test_libreoffice_calc_works_the_same_numbers_out_from_nothing(tmp_path: Path) -> None:
    """The workbook with every cached value taken out, recalculated by Calc:
    its figures are the template's massing at two uses. Skipped where Calc
    is not installed -- the CI runners have none; the recalculation above
    stands in for it."""
    if not _calc_available():
        pytest.skip("no LibreOffice here")
    path = write_workbook(tmp_path / "yield.xlsx", template())
    with zipfile.ZipFile(path) as package:
        parts = {part: package.read(part) for part in package.namelist()}
    sheet_xml = parts["xl/worksheets/sheet1.xml"].decode()
    bare = re.sub(r'( t="str")?>(<f>[^<]*</f>)<v>[^<]*</v></c>', r">\2</c>", sheet_xml)
    parts["xl/worksheets/sheet1.xml"] = bare.encode()
    with zipfile.ZipFile(tmp_path / "bare.xlsx", "w") as package:
        for part, data in parts.items():
            package.writestr(part, data)
    run = subprocess.run(
        [
            "soffice",
            f"-env:UserInstallation=file://{tmp_path / 'profile'}",
            "--headless",
            "--convert-to",
            "csv",
            "--outdir",
            str(tmp_path),
            str(tmp_path / "bare.xlsx"),
        ],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    if not (tmp_path / "bare.csv").exists():
        pytest.skip(f"LibreOffice here cannot open a spreadsheet: {run.stdout} {run.stderr}")
    lines = (tmp_path / "bare.csv").read_text().splitlines()
    fields = [line.split(",") for line in lines]
    assert float(fields[15][3]) == pytest.approx(18813.75), "D16, the residential GFA"
    assert float(fields[16][3]) == pytest.approx(3655.0), "D17, the commercial GFA"
    assert float(fields[27][4]) == pytest.approx(44.115, abs=0.01), "E28, the 1-bed units"
    assert float(fields[77][3]) == pytest.approx(268.15, abs=0.01), "D78, the SEPP parking"
    assert float(fields[78][3]) == pytest.approx(4.00, abs=0.01), "D79, the basements"


# -- the command -------------------------------------------------------------------


def scripted_project(connect_: Any) -> tuple[Any, Any]:
    """Two slabs of massing on a scripted project: a 20 by 10 m residential
    floor on Level 1 and a 10 by 10 m podium of shops on the ground."""

    def outline(*corners: tuple[float, float]) -> list[dict[str, float]]:
        return [{"x": x, "y": y} for x, y in [*corners, corners[0]]]

    details = [
        {
            "floorIndex": 1,
            "layerIndex": 1,
            "id": "",
            "details": {"polygonOutline": outline((0, 0), (20, 0), (20, 10), (0, 10))},
        },
        {
            "floorIndex": 0,
            "layerIndex": 2,
            "id": "",
            "details": {"polygonOutline": outline((0, 0), (10, 0), (10, 10), (0, 10))},
        },
    ]
    made: tuple[Any, Any] = connect_(
        {
            "GetElementsByType": {"elements": [{"elementId": {"guid": g}} for g in ("A", "B")]},
            "GetDetailsOfElements": {"detailsOfElements": details},
            "GetAttributesByType": {
                "attributes": [
                    {"index": 1, "name": "05 | Mass.Residential"},
                    {"index": 2, "name": "05 | Mass.Podium"},
                ]
            },
            "GetStories": {
                "stories": [
                    {"index": 0, "level": 0.0, "name": "Ground"},
                    {"index": 1, "level": 4.0, "name": "Level 1"},
                ]
            },
        }
    )
    return made


def test_the_command_prints_the_table_and_writes_the_workbook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from typer.testing import CliRunner

    import sun_study.cli as cli

    connection, transport = scripted_project(connect)
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: connection)
    workbook = tmp_path / "yield.xlsx"
    result = CliRunner().invoke(
        cli.app,
        [
            "yield",
            "--option",
            "Scheme A",
            "--residential-layer",
            "05 | Mass.Residential",
            "--commercial-layer",
            "05 | Mass.Podium",
            "--renovation-filter",
            "--site-area",
            "100",
            "--fsr-residential",
            "2",
            "--unit",
            "1-bed=50,50",
            "--unit",
            "2-bed=50,100",
            "--xlsx",
            str(workbook),
            "--no-sheet",
        ],
    )
    assert result.exit_code == 0, result.output
    assert transport.parameters_for("GetElementsByType") == {
        "elementType": "Slab",
        "filters": ["IsVisibleByRenovation"],
    }
    out = result.output
    assert "05 | Mass.Residential: 1 slab, 200.00 m², residential" in out
    assert "05 | Mass.Podium: 1 slab, 100.00 m², commercial" in out
    assert "Scheme A" in out
    # 200 m² of residential BEA -> 145 GFA; 100 m² of shops, commercial at
    # 0.85 -> 85; 230 over a 100 m² site is an FSR of 2.30. At an average NLA
    # of 75 m², an average GFA of 88.2 m², the homes come to 1.6 units.
    assert "Total GFA" in out and "230 m²" in out
    assert "2.30" in out
    assert "1.6" in out
    assert "Retail" not in out, "the storey table has two uses' columns"
    assert [option.option for option in options_in(workbook)] == ["Scheme A"]
    assert "CreateLayout" not in transport.commands(), "--no-sheet draws nothing"


def test_a_massing_layers_levels_are_told_in_the_log(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import sun_study.cli as cli

    connection, _ = scripted_project(connect)
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: connection)
    result = CliRunner().invoke(
        cli.app,
        [
            "yield",
            "--massing-layer",
            "05 | Mass.Residential",
            "--massing-layer",
            "05 | Mass.Podium",
            "--commercial-level",
            "Ground",
            "--no-sheet",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Ground Floor: commercial" in result.output
    assert "Level 01: residential" in result.output
    assert "by level" in result.output


def test_several_options_come_out_of_one_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two option layers: the slabs read once, a sheet each in the workbook,
    a comparison line each at the foot of the log."""
    from typer.testing import CliRunner

    import sun_study.cli as cli

    connection, transport = scripted_project(connect)
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: connection)
    workbook = tmp_path / "yield.xlsx"
    result = CliRunner().invoke(
        cli.app,
        [
            "yield",
            "--option-layer",
            "Tower A=05 | Mass.Residential",
            "--option-layer",
            "05 | Mass.Podium",
            "--commercial-level",
            "Ground",
            "--site-area",
            "100",
            "--xlsx",
            str(workbook),
            "--no-sheet",
        ],
    )
    assert result.exit_code == 0, result.output
    assert transport.commands().count("GetDetailsOfElements") == 1, "one read for both"
    assert [option.option for option in options_in(workbook)] == ["Tower A", "Podium"]
    out = result.output
    assert "Tower A" in out and "Podium" in out
    assert "Level 01: residential" in out and "Ground Floor: commercial" in out
    assert "Option" in out and "Total GFA" in out, "the comparison at the foot"
    clash = CliRunner().invoke(
        cli.app, ["yield", "--option-layer", "A=x", "--option-layer", "a=y", "--no-sheet"]
    )
    assert clash.exit_code == 2 and "same option name" in clash.output
    assert cli.option_from_layer("01 | Massing - Main Building.3D OPT2") == (
        "Option 02",
        "01 | Massing - Main Building.3D OPT2",
    )
    assert cli.option_from_layer("05 | Mass.Tower B")[0] == "Tower B"


def test_the_command_says_when_nothing_was_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import sun_study.cli as cli

    connection, _ = scripted_project(connect)
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: connection)
    result = CliRunner().invoke(
        cli.app, ["yield", "--residential-layer", "99 | Nothing", "--no-sheet"]
    )
    assert result.exit_code == 1
    assert "99 | Nothing: named, and no slab stands on it" in result.output
    assert "No slab was counted" in result.output


def test_a_mix_that_does_not_add_up_is_refused_before_archicad_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typer.testing import CliRunner

    import sun_study.cli as cli

    monkeypatch.setattr(cli, "_connect", lambda *a, **k: pytest.fail("Archicad was asked"))
    result = CliRunner().invoke(cli.app, ["yield", "--unit", "2-bed=90,75"])
    assert result.exit_code == 2
    assert "come to 90%" in result.output


@pytest.mark.parametrize(
    "gone", ["--retail-layer", "--retail-level", "--gfa-retail", "--nla-retail", "--fsr-retail"]
)
def test_retail_is_no_option_of_its_own_any_more(
    monkeypatch: pytest.MonkeyPatch, gone: str
) -> None:
    """The shops are commercial floor (D159), and the retail options are gone
    rather than kept hidden: a script that still names one is stopped and
    told, not quietly run without it."""
    from typer.testing import CliRunner

    import sun_study.cli as cli

    monkeypatch.setattr(cli, "_connect", lambda *a, **k: pytest.fail("Archicad was asked"))
    result = CliRunner().invoke(cli.app, ["yield", gone, "1"])
    assert result.exit_code == 2
    assert "No such option" in result.output and gone in result.output


def test_a_site_that_cannot_be_read_costs_the_fsr_and_not_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public services are slow and sometimes down; the yield analysis
    does not need them for anything but the FSR."""
    from typer.testing import CliRunner

    import sun_study.cli as cli
    from sun_study.site import pipeline as site_pipeline
    from sun_study.site.http import FetchError

    def unreachable(*_args: Any, **_kwargs: Any) -> Any:
        raise FetchError("NSW cadastre -> HTTP 503")

    connection, _ = scripted_project(connect)
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: connection)
    monkeypatch.setattr(site_pipeline, "run_summary", unreachable)
    result = CliRunner().invoke(
        cli.app,
        [
            "yield",
            "--residential-layer",
            "05 | Mass.Residential",
            "--address",
            "1 Example St",
            "--no-sheet",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "the site could not be read" in result.output
    assert "Total GFA" in result.output


def test_the_leps_one_fsr_goes_on_the_residential_row_with_a_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typer.testing import CliRunner

    import sun_study.cli as cli

    connection, _ = scripted_project(connect)
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: connection)
    result = CliRunner().invoke(
        cli.app,
        [
            "yield",
            "--residential-layer",
            "05 | Mass.Residential",
            "--site-area",
            "100",
            "--target-fsr",
            "3",
            "--no-sheet",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Permissible FSR : the LEP's 3:1 is one figure" in result.output
    assert any(
        line.startswith("  Residential FSR") and "3.00" in line
        for line in result.output.splitlines()
    )


def office_feasibility() -> Feasibility:
    """A small scheme, for tests that need any sheet at all."""
    return feasibility([Floor(RESIDENTIAL, 1000.0, 0.0, 3.0)], site_area_m2=500.0)
