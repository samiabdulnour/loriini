"""The yield analysis's sheet and workbook.

The drawing is tested pure, as the other sheets are; drawing it onto a
layout is tested against a scripted Archicad; and the workbook's formulas
are read back and, where LibreOffice Calc is installed, recalculated by it
from nothing, so that what Excel shows after an edit is what Loriini said.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest

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
from sun_study.rules.area_yield import RESIDENTIAL, Feasibility, Floor, feasibility
from tests.unit.test_archicad_adapter import connect
from tests.unit.test_area_yield import template, template_floors

# -- the rows -------------------------------------------------------------------


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
    assert first["Total FSR"] == ("3.40", "3.39", "-0.01")
    assert first["Residential GFA"] == ("18,771 m²", "18,814 m²", "+43 m²")
    assert first["Total GFA"] == ("22,794 m²", "22,749 m²", "-45 m²")
    assert first["2-bed"] == ("75 m² / 70 %", "154.1", "154.4")
    assert first["Residential"] == ("15", "", "")
    assert first["Visitors"] == ("0.1 / 0 a unit", "22.1", "0.0")
    assert first["Total Parking"] == ("", "333.0", "208.4")
    assert first["Total Basements"] == ("", "5.0", "3.1")
    parking = [row.cells for row in listed if row.label == "2-bed"][1]
    assert parking == ("1 / 1 a unit", "154.4", "154.4")


def test_the_notes_say_the_efficiencies_the_averages_and_the_source() -> None:
    said = notes(template())
    assert said[0] == (
        "Building efficiencies (BEA to GFA / GFA to NLA) : Residential 0.725 / 0.85, "
        "Commercial 0.85 / 0.9, Retail 0.95 / 0.9"
    )
    assert said[1] == "Market units : average NLA 72.5 m², average GFA 85.3 m²"
    assert "Parking : 40 m² a space, basement over 40 % of the site" in said
    assert said[-1] == "BEA : 19 slabs"
    assert notes(template(), ["Measured from 13 slabs."])[-1] == "Measured from 13 slabs."


def test_the_printed_table_lines_up() -> None:
    printed = text_lines(template())
    assert any(line.startswith("  Total GFA") and "22,749 m²" in line for line in printed)
    assert any(line.startswith("  1-bed") and "44.1" in line for line in printed)
    assert any(line.startswith("  PARKING REQUIREMENTS") for line in printed)


# -- the sheet ---------------------------------------------------------------------


def test_the_sheet_carries_the_title_the_table_the_notes_and_the_legend() -> None:
    drawing = area_drawing(template(), ["Measured from 19 slabs."])
    said = [text.text for text in drawing.texts]
    assert said[:2] == ["PRELIMINARY YIELD ANALYSIS", "Option 01"]
    for expected in ("FSR", "Total GFA", "22,749 m²", "PARKING REQUIREMENTS", "Notes:", "Legend"):
        assert expected in said
    assert {"Residential", "Commercial", "Retail"} <= set(said)
    assert "Measured from 19 slabs." in said
    assert all(text.at[1] <= 0.0 for text in drawing.texts), "it hangs down from its corner"
    assert all(text.at[0] <= 0.2 for text in drawing.texts), "and stays in its columns"
    # Three swatches, each a box of close lines in its colour.
    colours = {line.colour for line in drawing.lines}
    assert {"#FFF4A8", "#B894F2", "#F6B8C8"} <= colours


def test_the_view_goes_right_of_the_table_and_left_of_the_title_block() -> None:
    a1 = LayoutSheet(841.0, 594.0, 10.0, 10.0, 10.0, 10.0)
    x0, y0, x1, y1 = view_frame(a1) or (0, 0, 0, 0)
    assert x0 == pytest.approx((10 + 15 + 200 + 15) / 1000)
    assert x1 == pytest.approx((841 - 10 - 100 - 15) / 1000)
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
    assert frame["xMin"] == pytest.approx(0.24) and frame["xMax"] == pytest.approx(0.716)


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


def test_the_workbook_is_the_template_cell_for_cell(tmp_path: Path) -> None:
    """The office's addresses, for a five-type mix: the site in C6, the
    permissible FSR in C10:C12, the proposed GFA in D17:D19 from the storey
    table's totals, the units in D29:E33, the efficiencies in C86:E88."""
    table = cells(write_workbook(tmp_path / "yield.xlsx", template()))
    assert table["A1"][1] == "Preliminary Yield Analysis" and table["A3"][1] == "Option 01"
    assert table["C6"] == ("", "6704.0")
    assert table["C10"] == ("", "2.8") and table["C11"] == ("", "0.2")
    assert table["D10"][0] == 'IF($C$6>0,D17/$C$6,"")'
    assert float(table["D10"][1]) == pytest.approx(2.80634696)
    assert table["C17"][0] == 'IF(C10<>"",$C$6*C10,"")'
    assert table["D17"][0] == "Q133", "the storey table's residential GFA total"
    assert float(table["D17"][1]) == pytest.approx(18813.75)
    assert table["E30"][0] == "$D$17/$C$96*C30*$C$23"
    assert float(table["E30"][1]) == pytest.approx(44.115)
    assert table["C96"][0] == "C95/$E$86" and float(table["C96"][1]) == pytest.approx(85.2941176)
    assert table["C86"] == ("", "0.725") and table["E88"] == ("", "0.9")
    assert table["D65"][0] == "E30*B65" and table["D79"][0] == "B79*$D$18"
    assert table["D82"][0] == 'IF($C$6>0,D81*C106/($C$6*C107),"")'
    assert float(table["D82"][1]) == pytest.approx(4.96748832)
    assert table["C56"][0] == 'COUNTIF(M115:M132,">0")' and table["C56"][1] == "15.0"
    # The storey table: the top level first, the ground at the foot, totals under.
    assert table["J115"][1] == "Level 17" and table["J132"][1] == "Ground Floor"
    assert table["M132"] == ("", "50.0") and table["O132"] == ("", "2800.0")
    assert table["Q115"][0] == "M115*$C$86" and table["U115"][0] == "Q115*$E$86"
    assert table["M133"][0] == "SUM(M115:M132)" and float(table["M133"][1]) == 25950.0
    assert table["L115"][0] == "L116+K115", "heights add up from the ground"


def test_the_workbook_wears_the_templates_own_look(tmp_path: Path) -> None:
    """The template's style table and theme, verbatim, and each cell styled
    as the template cell it stands for: the whole main block matches, and
    the storey table takes the template's first, middle and last level rows."""
    from sun_study.report import feasibility_style as look

    path = write_workbook(tmp_path / "yield.xlsx", template())
    with zipfile.ZipFile(path) as package:
        assert package.read("xl/styles.xml").decode() == look.STYLES_XML
        assert package.read("xl/theme/theme1.xml").decode() == look.THEME_XML
        sheet_xml = package.read("xl/worksheets/sheet1.xml").decode()
        book_xml = package.read("xl/workbook.xml").decode()
    styles = {ref: int(st) for ref, st in re.findall(r'<c r="([A-Z]+\d+)" s="(\d+)"', sheet_xml)}
    main = {ref: st for ref, st in look.CELLS.items() if int(re.sub("[A-Z]", "", ref)) <= 107}
    assert all(styles.get(ref) == st for ref, st in main.items()), "the main block, cell for cell"
    assert styles["C6"] == look.CELLS["C6"] and styles["A5"] == look.CELLS["A5"]
    assert styles["J115"] == look.CELLS["J115"], "the top level as the template's top row"
    assert styles["M116"] == look.CELLS["M116"] and styles["M132"] == look.CELLS["M135"]
    assert styles["M133"] == look.CELLS["M136"], "the total row"
    assert styles["AA115"] == look.CELLS["AA115"] and styles["AP115"] == look.CELLS["AP115"]
    assert look.COLS_XML in sheet_xml
    assert '<row r="3" ht="23.25" customHeight="1">' in sheet_xml
    assert 'sqref="AP114:AP133"' in sheet_xml, "the colour scale over the difference column"
    assert "'Option 01'!$A$3:$E$107" in book_xml, "the print area"


def test_a_second_option_is_added_beside_the_first_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "yield.xlsx"
    write_workbook(path, template())
    second = feasibility(template_floors()[:5], option="Option 02", site_area_m2=6704.0)
    write_workbook(path, second)
    assert xlsx.sheet_names(path) == ["Option 01", "Option 02", DATA_SHEET]
    kept = options_in(path)
    assert [option.option for option in kept] == ["Option 01", "Option 02"]
    assert kept[0].gfa(RESIDENTIAL) == pytest.approx(18813.75)
    assert kept[0].permissible.retail == 0.4 and kept[0].source == ("BEA : 19 slabs",)
    assert cells(path, "xl/worksheets/sheet2.xml")["A3"][1] == "Option 02"
    # The same name again replaces its sheet rather than adding a third.
    write_workbook(path, feasibility(template_floors()[:3], option="option 01"))
    assert [option.option for option in options_in(path)] == ["Option 02", "option 01"]


def test_the_options_data_round_trips() -> None:
    sheet = feasibility(template_floors(), site_area_m2=6704.0, affordable_share=0.2)
    back = feasibility_from_dict(json.loads(json.dumps(feasibility_to_dict(sheet))))
    assert back == sheet


def test_a_workbook_loriini_did_not_write_is_left_alone(tmp_path: Path) -> None:
    theirs = tmp_path / "Feasibility template.xlsx"
    book = xlsx.Workbook()
    book.sheet("Option 01").text(1, 1, "theirs")
    book.write(theirs)
    with pytest.raises(FileExistsError, match="did not write"):
        write_workbook(theirs, template())
    assert cells(theirs)["A1"][1] == "theirs"
    assert options_in(theirs) == []


def _calc_available() -> bool:
    return shutil.which("soffice") is not None


def test_libreoffice_calc_works_the_same_numbers_out_from_nothing(tmp_path: Path) -> None:
    """The workbook with every cached value taken out, recalculated by Calc:
    its figures are the template's. Skipped where Calc is not installed --
    the CI runners have none."""
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
    assert float(fields[16][3]) == pytest.approx(18813.75), "D17, the residential GFA"
    assert float(fields[29][4]) == pytest.approx(44.115, abs=0.01), "E30, the 1-bed units"
    assert float(fields[80][3]) == pytest.approx(333.02, abs=0.01), "D81, the SEPP parking"
    assert float(fields[81][3]) == pytest.approx(4.97, abs=0.01), "D82, the basements"


# -- the command -------------------------------------------------------------------


def scripted_project(connect_: Any) -> tuple[Any, Any]:
    """Two slabs of massing on a scripted project: a 20 by 10 m residential
    floor on Level 1 and a 10 by 10 m retail podium on the ground."""

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
                    {"index": 2, "name": "05 | Mass.Retail"},
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
            "--retail-layer",
            "05 | Mass.Retail",
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
    assert "05 | Mass.Retail: 1 slab, 100.00 m², retail" in out
    assert "Scheme A" in out
    # 200 m² of residential BEA -> 145 GFA; 100 m² of retail -> 95; 240 over a
    # 100 m² site is an FSR of 2.40. At an average NLA of 75 m², an average
    # GFA of 88.2 m², the homes come to 1.6 units.
    assert "Total GFA" in out and "240 m²" in out
    assert "2.40" in out
    assert "1.6" in out
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
            "05 | Mass.Retail",
            "--retail-level",
            "Ground",
            "--no-sheet",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Ground Floor: retail" in result.output and "Level 01: residential" in result.output
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
            "05 | Mass.Retail",
            "--retail-level",
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
    assert [option.option for option in options_in(workbook)] == ["Tower A", "Retail"]
    out = result.output
    assert "Tower A" in out and "Retail" in out
    assert "Level 01: residential" in out and "Ground Floor: retail" in out
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
    clash = CliRunner().invoke(
        cli.app, ["yield", "--retail-level", "Ground", "--commercial-level", "0"]
    )
    assert clash.exit_code == 2 and "both retail and commercial" in clash.output


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
