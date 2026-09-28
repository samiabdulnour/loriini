"""The COS schedules: one table per Zone, split back out of a multi-level run.

The split is checked against arithmetic a person can do by hand, and the
workbook is read back as the XML it is, so neither needs a spreadsheet library.
"""

from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pytest
from typer.testing import CliRunner

from sun_study.cli import app
from sun_study.report.cos_table import (
    HourArea,
    ZoneTable,
    clock_label,
    storey_label,
    write_workbook,
    zone_tables,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = FIXTURES / "sample_building.ifc"
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@pytest.mark.parametrize(
    ("storey", "label"),
    [
        ("LEVEL 02", "L2"),
        ("LEVEL 11", "L11"),
        ("Level 00", "L0"),
        ("L03", "L3"),
        ("ROOF TERRACE", "ROOF TERRACE"),
        (None, "COS"),
        ("", "COS"),
    ],
)
def test_a_storey_is_named_the_way_the_drawing_names_it(storey: str | None, label: str) -> None:
    assert storey_label(storey) == label


@pytest.mark.parametrize(
    ("at", "label"),
    [
        (dt.time(9), "9AM"),
        (dt.time(11), "11AM"),
        (dt.time(12), "12PM"),
        (dt.time(15), "3PM"),
        (dt.time(0), "12AM"),
        (dt.time(9, 30), "9:30AM"),
    ],
)
def test_the_hour_is_written_the_way_the_schedule_writes_it(at: dt.time, label: str) -> None:
    assert clock_label(at) == label


def _day(step_minutes: int) -> list[dt.datetime]:
    start = dt.datetime(2024, 6, 21, 9, 0)
    return [
        start + dt.timedelta(minutes=step_minutes * i) for i in range(6 * 60 // step_minutes + 1)
    ]


def test_each_zone_gets_its_own_hours_lowest_first() -> None:
    """Two terraces measured together, handed in top one first.

    L11 is listed before L2 in the samples and as text; the tables come out
    L2 then L11 because that is the order of the building.
    """
    times = _day(60)  # 09:00 .. 15:00, seven instants
    ids = ["upper"] * 2 + ["lower"] * 3
    areas = np.array([1.0, 3.0, 2.0, 2.0, 4.0])
    heights = np.array([48.0, 48.0, 17.2, 17.2, 17.2])
    sunlit = np.zeros((5, len(times)), dtype=bool)
    sunlit[1, :] = True  # 3 m2 of the upper terrace in sun all day
    sunlit[2, :3] = True  # 2 m2 of the lower one until 11:00
    sunlit[4, 6] = True  # 4 m2 of the lower one only at 15:00
    minutes = np.array([0.0, 360.0, 180.0, 0.0, 10.0])

    tables = zone_tables(
        ids,
        areas,
        heights,
        sunlit,
        times,
        storey_of={"upper": "LEVEL 11", "lower": "LEVEL 02"}.get,
        name_of=str,
        minutes=minutes,
        threshold_hours=2.0,
    )

    assert [t.title for t in tables] == ["L2 COS SOLAR ANALYSIS", "L11 COS SOLAR ANALYSIS"]
    lower, upper = tables
    assert lower.area_m2 == pytest.approx(8.0)
    assert [h.area_m2 for h in lower.hours] == pytest.approx([2, 2, 2, 0, 0, 0, 4])
    assert [h.at for h in lower.hours] == [dt.time(h) for h in range(9, 16)]
    assert lower.achieved_m2 == pytest.approx(2.0)
    assert upper.area_m2 == pytest.approx(4.0)
    assert [h.area_m2 for h in upper.hours] == pytest.approx([3] * 7)
    assert upper.achieved_m2 == pytest.approx(3.0)


def test_the_zones_add_back_up_to_the_whole() -> None:
    """The split must not lose or double anything the combined figure counted."""
    rng = np.random.default_rng(7)
    times = _day(10)
    ids = [f"z{i % 4}" for i in range(200)]
    areas = rng.uniform(0.1, 0.5, 200)
    heights = np.array([float(i % 4) * 3.0 for i in range(200)])
    sunlit = rng.random((200, len(times))) > 0.5

    tables = zone_tables(ids, areas, heights, sunlit, times, storey_of=lambda z: z, name_of=str)

    hourly = [i for i, t in enumerate(times) if t.minute == 0]
    for row, index in enumerate(hourly):
        assert sum(t.hours[row].area_m2 for t in tables) == pytest.approx(
            float(areas[sunlit[:, index]].sum())
        )
    assert sum(t.area_m2 for t in tables) == pytest.approx(float(areas.sum()))


def test_only_the_whole_hours_are_tabled() -> None:
    """A 10-minute study still gives the seven rows a 9-to-3 schedule has."""
    times = _day(10)
    tables = zone_tables(
        ["a"],
        np.array([1.0]),
        np.array([0.0]),
        np.ones((1, len(times)), dtype=bool),
        times,
        storey_of=lambda _: "LEVEL 02",
        name_of=str,
    )
    assert len(tables[0].hours) == 7


def test_no_threshold_row_unless_the_study_asked_for_one() -> None:
    times = _day(60)
    (table,) = zone_tables(
        ["a"],
        np.array([1.0]),
        np.array([0.0]),
        np.ones((1, len(times)), dtype=bool),
        times,
        storey_of=lambda _: "LEVEL 02",
        name_of=str,
    )
    assert table.threshold_hours is None
    assert table.achieved_m2 is None


def test_two_zones_on_one_storey_are_told_apart_by_name() -> None:
    times = _day(60)
    (east, west) = zone_tables(
        ["e", "w"],
        np.array([1.0, 1.0]),
        np.array([17.2, 17.3]),
        np.ones((2, len(times)), dtype=bool),
        times,
        storey_of=lambda _: "LEVEL 02",
        name_of={"e": "COS EAST", "w": "COS WEST"}.__getitem__,
    )
    assert east.title == "L2 COS EAST COS SOLAR ANALYSIS"
    assert west.title == "L2 COS WEST COS SOLAR ANALYSIS"


# ---------------------------------------------------------------------------
# The workbook, read back as XML.
# ---------------------------------------------------------------------------
def _cells(path: Path) -> dict[str, tuple[str | None, str | None]]:
    """Every cell: its text or value, and its formula."""
    with zipfile.ZipFile(path) as package:
        sheet = ElementTree.fromstring(package.read("xl/worksheets/sheet1.xml"))
    found: dict[str, tuple[str | None, str | None]] = {}
    for cell in sheet.iterfind(".//x:c", NS):
        text = cell.find("x:is/x:t", NS)
        value = cell.find("x:v", NS)
        formula = cell.find("x:f", NS)
        shown = text.text if text is not None else (value.text if value is not None else None)
        found[cell.attrib["r"]] = (shown, formula.text if formula is not None else None)
    return found


@pytest.fixture
def schedule(tmp_path: Path) -> Path:
    table = ZoneTable(
        title="L2 COS SOLAR ANALYSIS",
        storey="LEVEL 02",
        area_m2=873.26,
        hours=tuple(
            HourArea(dt.time(h), area)
            for h, area in zip(
                range(9, 16), (550.4, 418.1, 395.5, 400.7, 426.2, 481.6, 588.4), strict=True
            )
        ),
        threshold_hours=2.0,
        achieved_m2=500.04,
    )
    path = tmp_path / "cos.xlsx"
    write_workbook(path, [table, table], heading="COS solar analysis", notes=("a note",))
    return path


def test_every_part_of_the_workbook_is_well_formed(schedule: Path) -> None:
    with zipfile.ZipFile(schedule) as package:
        names = set(package.namelist())
        assert {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/styles.xml",
            "xl/worksheets/sheet1.xml",
        } <= names
        for name in names:
            ElementTree.fromstring(package.read(name))


def test_the_table_reads_like_the_office_schedule(schedule: Path) -> None:
    cells = _cells(schedule)
    assert cells["A1"][0] == "COS solar analysis"
    assert cells["A2"][0] == "a note"
    # Heading, header row, then the hours.
    assert cells["A4"][0] == "L2 COS SOLAR ANALYSIS"
    assert [cells[f"{c}5"][0] for c in "ABC"] == ["TIME", "AREA (sqm)", "PERCENTAGE"]
    assert cells["A6"][0] == "9AM"
    assert cells["B6"][0] == "550.4"
    assert cells["A12"][0] == "3PM"
    assert cells["A13"][0] == "COS AREA"
    assert cells["B13"][0] == "873.3"
    assert cells["A14"][0] == "2 HRS OR MORE"
    assert cells["B14"][0] == "500"


def test_a_percentage_is_a_formula_that_also_carries_its_value(schedule: Path) -> None:
    """Recalculates in Excel, and still reads right in a previewer that never does."""
    value, formula = _cells(schedule)["C6"]
    assert formula == "IF($B$13=0,0,B6/$B$13)"
    assert float(value or "nan") == pytest.approx(550.4 / 873.3, rel=1e-5)


def test_each_table_title_spans_the_three_columns(schedule: Path) -> None:
    with zipfile.ZipFile(schedule) as package:
        sheet = ElementTree.fromstring(package.read("xl/worksheets/sheet1.xml"))
    merged = [m.attrib["ref"] for m in sheet.iterfind(".//x:mergeCell", NS)]
    # Two blank rows between tables: rows 4-14 are the first, 17 starts the next.
    assert merged == ["A4:C4", "A17:C17"]


def test_massing_writes_one_schedule_per_zone(tmp_path: Path) -> None:
    """Two Zones on two storeys, one table each, lowest first."""
    out = tmp_path / "cos.xlsx"
    invocation = CliRunner().invoke(
        app,
        [
            "massing",
            str(SAMPLE),
            "--timezone",
            "Australia/Sydney",
            "--zone-name",
            "Apartment L00-A",
            "--zone-name",
            "Apartment L01-A",
            "--zone-grid",
            "1.0",
            "--zone-hours",
            "2",
            "--zone-table",
            str(out),
        ],
    )
    assert invocation.exit_code == 0, invocation.output
    assert "wrote 2 COS schedule(s)" in invocation.output
    titles = [v for v, _ in _cells(out).values() if v and v.endswith("SOLAR ANALYSIS")]
    assert titles == ["L0 COS SOLAR ANALYSIS", "L1 COS SOLAR ANALYSIS"]


def test_a_table_without_a_zone_is_refused(tmp_path: Path) -> None:
    invocation = CliRunner().invoke(
        app,
        [
            "massing",
            str(SAMPLE),
            "--timezone",
            "Australia/Sydney",
            "--facade-grid",
            "3.0",
            "--zone-table",
            str(tmp_path / "cos.xlsx"),
        ],
    )
    assert invocation.exit_code == 2
    assert not (tmp_path / "cos.xlsx").exists()
