"""The area calculation's sheet and workbook.

The drawing is tested pure, as the other sheets are; drawing it onto a
layout is tested against a scripted Archicad; and the workbook's formulas
are read back and, where LibreOffice Calc is installed, recalculated by it
from nothing, so that what Excel shows after an edit is what Loriini said.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest

from sun_study.archicad import naming
from sun_study.archicad.area_sheet import AREA_WORD, area_drawing, draw_area_sheet, view_frame
from sun_study.archicad.layout import LayoutSheet
from sun_study.report.area_table import notes, rows, text_lines, write_workbook
from sun_study.rules.area_yield import (
    NON_RESIDENTIAL,
    RESIDENTIAL,
    AreaSchedule,
    Floor,
    Targets,
    UnitType,
    schedule,
)
from tests.unit.test_archicad_adapter import connect


def office() -> AreaSchedule:
    floors = [
        Floor("Level 01", NON_RESIDENTIAL, 1387.68, 0.0),
        *(Floor(f"Level {n:02d}", RESIDENTIAL, 13219.56 / 12, 3.1 * n) for n in range(2, 14)),
    ]
    return schedule(floors, site_area_m2=1386.78, targets=Targets(fsr=8.0, units=110))


# -- the rows -------------------------------------------------------------------


def test_the_rows_are_the_office_sheets_in_its_order_and_words() -> None:
    labelled = [(row.label, row.count, row.proposed, row.target) for row in rows(office())]
    figures = [entry for entry in labelled if entry[0] or entry[1]]
    assert figures[:4] == [
        ("Total GBA", "", "14607.24 m²", ""),
        ("Non resi. GBA", "", "1387.68 m²", ""),
        ("Resi. GBA", "", "13219.56 m²", ""),
        ("Total GFA", "", "11163.58 m²", "11094.24 m²"),
    ]
    by_label = {entry[0]: entry for entry in labelled if entry[0]}
    assert by_label["Total FSR"][2:] == ("8.05", "8.00")
    assert by_label["Resi. FSR"][2] == "7.15"
    assert by_label["2 Bedroom"] == ("2 Bedroom", "78 units", "70 %", "70 %")
    assert by_label["GFA/unit"][2] == "88.52 m²"
    assert ("", "112 units", "Mix", "110 units") in labelled


def test_the_notes_say_the_factors_the_site_and_the_sizes() -> None:
    said = notes(office(), ["Measured from 13 slabs."])
    assert said[:4] == [
        "GBA to GFA (Residential) : 0.75",
        "GBA to GFA (Non-Residential) : 0.9",
        "GFA to NSA (Residential) : 0.85",
        "GFA to NSA (Non-Residential) : 0.9",
    ]
    assert "Site area : 1386.78 m²" in said
    assert any(line.startswith("Unit sizes (NSA) : 1 Bedroom 55 m²") for line in said)
    assert said[-1] == "Measured from 13 slabs."


def test_the_printed_table_lines_up() -> None:
    printed = text_lines(office())
    assert any(line.startswith("  Total GBA") and "14607.24 m²" in line for line in printed)
    assert any("17 units" in line and "15 %" in line for line in printed)


# -- the sheet ---------------------------------------------------------------------


def test_the_sheet_carries_the_title_the_table_the_notes_and_the_legend() -> None:
    drawing = area_drawing(office(), ["Measured from 13 slabs."])
    said = [text.text for text in drawing.texts]
    assert said[:2] == ["AREA CALCULATION", "GFA + Yield"]
    for expected in ("Total GBA", "14607.24 m²", "YIELD", "Notes:", "Legend", "Residential"):
        assert expected in said
    assert "Measured from 13 slabs." in said
    assert all(text.at[1] <= 0.0 for text in drawing.texts), "it hangs down from its corner"
    assert all(text.at[0] < 0.15 for text in drawing.texts), "and stays in its column"
    # Two swatches, each a box of close lines in its colour.
    colours = {line.colour for line in drawing.lines}
    assert {"#FFF4A8", "#B894F2"} <= colours


def test_the_view_goes_right_of_the_table_and_left_of_the_title_block() -> None:
    a1 = LayoutSheet(841.0, 594.0, 10.0, 10.0, 10.0, 10.0)
    x0, y0, x1, y1 = view_frame(a1) or (0, 0, 0, 0)
    assert x0 == pytest.approx((10 + 15 + 150 + 15) / 1000)
    assert x1 == pytest.approx((841 - 10 - 100 - 15) / 1000)
    assert (y0, y1) == pytest.approx((0.025, 0.569))
    assert view_frame(LayoutSheet(297.0, 210.0, 10.0, 10.0, 10.0, 10.0)) is None, "no room on A4"


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
    report = draw_area_sheet(connection, office(), master_layout="A1 no scale")
    assert report.name == naming.named(AREA_WORD) and report.database_id == "LAY"
    assert report.master == "A1 no scale" and report.view == ""
    assert report.texts > 30 and report.lines > 30
    texts = transport.parameters_for("CreateTexts")["texts"]
    title = next(t for t in texts if t["text"] == "AREA CALCULATION")
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
    report = draw_area_sheet(connection, office(), view=" yield axo ", master_layout="A1 no scale")
    assert report.view == "Yield Axo", report.notes
    arranged = transport.parameters_for("ArrangeDrawings")
    frame = arranged["drawings"][0]["frame"]
    assert arranged["drawings"][0]["guid"] == "D1"
    assert frame["xMin"] == pytest.approx(0.19) and frame["xMax"] == pytest.approx(0.716)


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
    report = draw_area_sheet(connection, office(), view="Nothing Like It")
    assert report.view == "" and report.texts > 30
    assert any("no view called 'Nothing Like It'" in note for note in report.notes)


# -- the workbook ------------------------------------------------------------------


def cells(path: Path) -> dict[str, tuple[str, str]]:
    """Every cell of the sheet: its formula, or empty, and its value."""
    with zipfile.ZipFile(path) as package:
        xml = package.read("xl/worksheets/sheet1.xml").decode()
    found: dict[str, tuple[str, str]] = {}
    for ref, body in re.findall(r'<c r="([A-Z]+\d+)"[^>]*?(?:/>|>(.*?)</c>)', xml):
        formula = re.search(r"<f>(.*?)</f>", body or "")
        value = re.search(r"<v>(.*?)</v>|<t[^>]*>(.*?)</t>", body or "")
        found[ref] = (
            formula.group(1) if formula else "",
            (value.group(1) or value.group(2) or "") if value else "",
        )
    return found


def row_of(table: dict[str, tuple[str, str]], label: str) -> int:
    return next(
        int(ref[1:]) for ref, (_, value) in table.items() if ref[0] == "A" and value == label
    )


def test_every_part_of_the_workbook_is_well_formed(tmp_path: Path) -> None:
    import xml.dom.minidom

    path = write_workbook(tmp_path / "area.xlsx", office(), note="Kogarah")
    with zipfile.ZipFile(path) as package:
        for name in package.namelist():
            xml.dom.minidom.parseString(package.read(name))


def test_the_workbook_works_from_its_inputs(tmp_path: Path) -> None:
    table = cells(write_workbook(tmp_path / "area.xlsx", office()))
    site = row_of(table, "Site area (m²)")
    factor = row_of(table, "GBA to GFA (Residential)")
    gba = row_of(table, "Resi. GBA")
    gfa = row_of(table, "Resi. GFA")
    assert table[f"B{site}"] == ("", "1386.78")
    assert table[f"B{gfa}"][0] == f"B{gba}*$B${factor}", "GFA is the GBA by the factor cell"
    assert float(table[f"B{gfa}"][1]) == pytest.approx(9914.67)
    total_fsr = row_of(table, "Total FSR")
    assert "/$B$" in table[f"B{total_fsr}"][0]
    storey_total = row_of(table, "Total")
    assert table[f"B{gba}"][0] == f"B{storey_total}", "the GBA is the storeys' measured sum"
    assert table[f"B{storey_total}"][0].startswith("SUM(")


def _calc_available() -> bool:
    return shutil.which("soffice") is not None


def test_libreoffice_calc_works_the_same_numbers_out_from_nothing(tmp_path: Path) -> None:
    """The workbook with every cached value taken out, recalculated by Calc:
    its figures are Loriini's. Skipped where Calc is not installed -- the CI
    runners have none."""
    if not _calc_available():
        pytest.skip("no LibreOffice here")
    thirds = [UnitType("A", 1 / 3, 60.0), UnitType("B", 1 / 3, 80.0), UnitType("C", 1 / 3, 100.0)]
    cases = {"office": office(), "thirds": schedule(office_floors(), mix=thirds)}
    for name, sch in cases.items():
        path = write_workbook(tmp_path / f"{name}.xlsx", sch)
        with zipfile.ZipFile(path) as package:
            parts = {part: package.read(part) for part in package.namelist()}
        sheet_xml = parts["xl/worksheets/sheet1.xml"].decode()
        bare = re.sub(r'( t="str")?>(<f>[^<]*</f>)<v>[^<]*</v></c>', r">\2</c>", sheet_xml)
        parts["xl/worksheets/sheet1.xml"] = bare.encode()
        with zipfile.ZipFile(tmp_path / f"{name}-bare.xlsx", "w") as package:
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
            str(tmp_path / "office-bare.xlsx"),
            str(tmp_path / "thirds-bare.xlsx"),
        ],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    if not (tmp_path / "office-bare.csv").exists():
        pytest.skip(f"LibreOffice here cannot open a spreadsheet: {run.stdout} {run.stderr}")
    office_rows = {
        line.split(",")[0]: line.split(",")
        for line in (tmp_path / "office-bare.csv").read_text().splitlines()
    }
    assert float(office_rows["Total GFA"][1]) == pytest.approx(11163.58, abs=0.01)
    assert float(office_rows["Total GFA"][2]) == pytest.approx(8.0 * 1386.78)
    assert float(office_rows["Total FSR"][1]) == pytest.approx(8.05, abs=0.005)
    assert office_rows["Units"][1] == "112"
    assert [office_rows[name][1] for name in ("1 Bedroom", "2 Bedroom", "3 Bedroom")] == [
        "17",
        "78",
        "17",
    ]
    thirds_rows = {
        line.split(",")[0]: line.split(",")
        for line in (tmp_path / "thirds-bare.csv").read_text().splitlines()
    }
    expected = schedule(office_floors(), mix=thirds).homes
    assert thirds_rows["Units"][1] == str(expected.units)
    assert [thirds_rows[name][1] for name in "ABC"] == [str(c.count) for c in expected.counts]


def office_floors() -> list[Floor]:
    return [
        Floor("Level 01", NON_RESIDENTIAL, 1387.68, 0.0),
        *(Floor(f"Level {n:02d}", RESIDENTIAL, 13219.56 / 12, 3.1 * n) for n in range(2, 14)),
    ]


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
    workbook = tmp_path / "area.xlsx"
    result = CliRunner().invoke(
        cli.app,
        [
            "yield",
            "--residential-layer",
            "05 | Mass.Residential",
            "--non-residential-layer",
            "05 | Mass.Retail",
            "--renovation-filter",
            "--site-area",
            "100",
            "--unit",
            "1 Bedroom=50,50",
            "--unit",
            "2 Bedroom=50,100",
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
    assert "05 | Mass.Retail: 1 slab, 100.00 m², non-residential" in out
    # 200 m² GBA residential -> 150 GFA -> 127.5 NSA; at an average of 75 m²,
    # one unit. Total GFA 150 + 90 over a 100 m² site is an FSR of 2.4.
    assert "Total GFA" in out and "240.00 m²" in out
    assert "2.40" in out
    assert "1 unit " in out
    assert workbook.is_file()
    assert "CreateLayout" not in transport.commands(), "--no-sheet draws nothing"


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
    result = CliRunner().invoke(cli.app, ["yield", "--unit", "2 Bedroom=90,75"])
    assert result.exit_code == 2
    assert "come to 90%" in result.output


def test_a_site_that_cannot_be_read_costs_the_fsr_and_not_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public services are slow and sometimes down; the area calculation
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
        cli.app, ["yield", "--address", "1 Example Street, Kogarah NSW", "--no-sheet"]
    )
    assert result.exit_code == 0, result.output
    assert "the site could not be read (NSW cadastre -> HTTP 503)" in result.output
    assert "Total GBA" in result.output
