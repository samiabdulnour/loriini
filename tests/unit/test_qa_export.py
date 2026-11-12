"""The QA export (D184): a project's own values read as the brief's, the units
worked out from the zones, the totals, and the IFC and spreadsheets written."""

from __future__ import annotations

from pathlib import Path

import pytest

from sun_study.archicad import qa_export as qa
from sun_study.archicad.qa_ifc import check_ifc, write_qa_ifc
from sun_study.report import qa_workbook
from sun_study.report.xlsx import read_text


def square(x: float, y: float, side: float) -> tuple[tuple[float, float], ...]:
    return ((x, y), (x + side, y), (x + side, y + side), (x, y + side))


def zone(guid: str, name: str, number: str, storey: int, outline, area: float) -> qa.QaZone:  # type: ignore[no-untyped-def]
    return qa.QaZone(
        guid=guid,
        name=name,
        number=number,
        storey_index=storey,
        storey=f"LEVEL {storey:02d}",
        layer="06 | Zone.Units",
        area_m2=area,
        outline=outline,
    )


def test_a_projects_own_words_are_read_as_the_briefs() -> None:
    assert [qa.yes_no(word) for word in ("Y", "yes", "N", "-", "0", "maybe", None)] == [
        "Yes",
        "Yes",
        "No",
        "No",
        "No",
        None,
        None,
    ]
    assert [qa.unit_type(word) for word in ("2B", "2 BED", "3br", "Studio", "1B.T02B", "A")] == [
        "2B",
        "2B",
        "3B",
        "Studio",
        "1B",
        None,
    ]
    assert qa.unit_type("A", bedrooms=0) == "Studio", "the bedrooms say it when the name cannot"
    assert [qa.livable(word) for word in ("Silver", "GOLD level", "-", "Y")] == [
        "Silver",
        "Gold",
        "None",
        None,
    ], "a plain Y says livable, not which"
    assert [qa.number(word) for word in ("21", "4.4", "12.5 m²", "1,234", "-")] == [
        21.0,
        4.4,
        12.5,
        1234.0,
        None,
    ]


def test_the_prefix_names_the_three_groups() -> None:
    assert qa.group_names("FUSE_") == {
        "UNIT": "FUSE_UNIT",
        "AREA": "FUSE_AREA",
        "PARKING": "FUSE_PARKING",
    }
    with pytest.raises(ValueError, match="prefix"):
        qa.group_names("  ")


def test_storeys_are_chosen_between_two_names_by_level() -> None:
    storeys = qa.Storeys(
        names={0: "AHD", 9: "LOWER GROUND", 10: "GROUND", 11: "LEVEL 01", 46: "UT2.01"},
        levels={0: -9.0, 9: 25.5, 10: 30.0, 11: 33.5, 46: 144.1},
    )
    assert storeys.between("lower ground", "LEVEL 01") == {9, 10, 11}
    assert storeys.between(None, None) is None
    with pytest.raises(Exception, match="No storey is named 'ROOF'"):
        storeys.between("ROOF", None)


def test_a_balcony_is_the_open_space_of_the_apartment_it_touches() -> None:
    flat = zone("A", "01", "2B", 11, square(0, 0, 8), 64.0)
    other = zone("B", "02", "1B", 11, square(20, 0, 8), 64.0)
    upstairs = zone("C", "01", "2B", 12, square(0, 0, 8), 64.0)
    balcony = zone("b1", "", "", 11, square(8, 0, 3), 9.0)
    far = zone("b2", "", "", 11, square(50, 50, 3), 9.0)
    space, alone = qa.pair_balconies([flat, other, upstairs], [balcony, far])
    assert space == {"A": 9.0}, "the balcony touching it, on its own storey"
    assert alone == 1


def test_a_unit_is_copied_where_it_can_be_and_worked_out_where_it_cannot() -> None:
    flat = zone("A", "01", "2B", 11, square(0, 0, 8), 64.0)
    studio = zone("S", "05", "", 11, square(0, 20, 5), 25.0)
    paths = {"Apartments/Beds": "beds", "Apartments/Daylight": "day", "Apartments/Liveable": "liv"}
    copied = {
        "A": {"beds": "2", "day": "N", "liv": "Y"},
        "S": {"beds": "0", "day": "Y", "liv": "-"},
    }
    rows = qa.unit_rows(
        [flat, studio],
        copied=copied,
        copies={
            "Bedrooms": "Apartments/Beds",
            "Solar 2h": "Apartments/Daylight",
            "Livable": "Apartments/Liveable",
        },
        paths=paths,
        open_space={"A": 10.5},
        solar={"A": {"Meets Minimum": "Yes", "No Direct Sunlight": "No"}},
    )
    one, two = rows
    assert one.values["Solar 2h"] == "Yes", "the measured solar study wins over a typed copy"
    assert one.values["No sun"] == "No"
    assert one.values["Unit Type"] == "2B" and one.values["Bedrooms"] == 2
    assert one.values["Unit No"] == "01" and one.values["Internal area m²"] == 64.0
    assert one.values["POS area m²"] == 10.5
    assert "Livable" not in one.values and one.unread == ["Livable from Apartments/Liveable = 'Y'"]
    assert two.values["Unit Type"] == "Studio", "told by the bedrooms when the zone is not"
    assert two.values["Livable"] == "None" and two.values["Solar 2h"] == "Yes"


def test_the_totals_are_the_councils() -> None:
    rows = [
        qa.UnitRow(
            zone(str(i), f"0{i}", "2B", 11 if i < 3 else 20, (), 72.0),
            {
                "Unit Type": "2B",
                "Internal area m²": 72.0 if i else 65.0,
                "POS area m²": 10.0 if i else 6.0,
                "Solar 2h": "Yes" if i else "No",
                "No sun": "No" if i else "Yes",
                "Cross vent": "Yes",
            },
        )
        for i in range(4)
    ]
    totals = {
        what: figure for what, figure, _against in qa.summary(rows, [], [], first_nine={11}).lines
    }
    assert totals["Apartments"] == "4"
    assert totals["Below the 4D minimum area"] == "1"
    assert totals["Below the 4E minimum POS"] == "1"
    assert totals["Solar 2h"] == "3 of 4 (75.0 %)"
    assert totals["No sun"] == "1 of 4 (25.0 %)"
    assert totals["Cross vent, first nine storeys"] == "3 of 3 (100.0 %)", (
        "the storeys above left out"
    )


def test_loriinis_own_ifc_holds_a_space_per_zone_with_its_group(tmp_path: Path) -> None:
    storeys = qa.Storeys(names={11: "LEVEL 01", 12: "LEVEL 02"}, levels={11: 33.5, 12: 36.7})
    flat = zone("A", "01", "2B", 11, square(0, 0, 8), 64.0)
    cos = zone("C", "COS", "", 11, square(0, 20, 20), 400.0)
    path = write_qa_ifc(
        tmp_path / "0001_QA_261112_spaces.ifc",
        project="0001",
        storeys=storeys,
        spaces=[
            (flat, "FUSE_UNIT", {"Unit No": "01", "Unit Type": "2B", "Bedrooms": 2, "Core": None}),
            (cos, "FUSE_AREA", {"Area Type": "Communal open space"}),
        ],
    )
    report = check_ifc(path, ["FUSE_UNIT", "FUSE_AREA"], "FUSE_UNIT", ["Unit No", "Core"])
    assert report.spaces == 2 and report.proxies == 0
    assert report.with_groups == {"FUSE_UNIT": 1, "FUSE_AREA": 1}
    assert report.empty == {"Core": 1}, "a blank field is counted, not written"
    assert not any("NO SPACES" in line for line in report.lines())


def test_an_ifc_with_no_spaces_says_why(tmp_path: Path) -> None:
    import ifcopenshell
    import ifcopenshell.api.root

    model = ifcopenshell.api.project.create_file(version="IFC4")
    ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="x")
    for _ in range(3):
        ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingElementProxy")
    path = tmp_path / "office.ifc"
    model.write(str(path))
    lines = check_ifc(path, ["FUSE_UNIT"], "FUSE_UNIT", []).lines()
    assert any("NO SPACES" in line for line in lines)
    assert any("MOSTLY PROXIES" in line for line in lines)


def test_the_spreadsheets_are_written_from_the_rows(tmp_path: Path) -> None:
    flat = zone("A", "01", "2B", 11, (), 64.0)
    rows = [
        qa.UnitRow(
            flat, {"Unit No": "01", "Unit Type": "2B", "Bedrooms": 2, "Internal area m²": 64.0}
        )
    ]
    units = qa_workbook.write_units(tmp_path, rows)
    assert read_text(units, "QA_Units", "A1") == "Zone name"
    assert read_text(units, "QA_Units", "G2") == "2B", "Unit Type, the fourth field"
    areas = qa_workbook.write_areas(
        tmp_path, [(zone("C", "COS", "", 11, (), 400.0), "Communal open space")]
    )
    assert read_text(areas, "QA_Areas", "D2") == "Communal open space"
    totals = qa.summary(rows, [], [], first_nine=None)
    summary = qa_workbook.write_summary(tmp_path, totals, source="0001, read on 12 November 2026")
    assert read_text(summary, "QA_Summary", "A2") == "0001, read on 12 November 2026"


def test_an_offices_own_setup_of_the_groups_is_found_and_used() -> None:
    """2524's by hand: Fuse_Unit, 'Unit Number', 'Internal area  m²', Y and N."""
    assert qa.group_names("Fuse_")["UNIT"] == "Fuse_Unit", "the suffix in the prefix's case"
    paths = {
        "Fuse_Unit/Unit Number": "no",
        "Fuse_Unit/Internal area  m²": "area",
        "Apartments/Unit Number": "other",
    }
    assert qa.find_field(paths, "FUSE_UNIT", "Unit No") == "no"
    assert qa.find_field(paths, "FUSE_UNIT", "Internal area m²") == "area"
    assert qa.find_field(paths, "FUSE_UNIT", "Core") is None
    assert qa.fit_option("Yes", ("Y", "N")) == "Y"
    assert qa.fit_option("No", ("Y", "N")) == "N"
    assert qa.fit_option("2B", ("1B", "2B")) == "2B"
    assert qa.fit_option("Silver", ("Y", "N")) is None
    assert qa.fit_option("Yes", ()) == "Yes", "no option set, nothing to fit"


def test_an_apartment_drawn_twice_is_counted_once() -> None:
    one = zone("A", "G04", "2B", 10, square(0, 0, 9.7), 94.57)
    two = zone("B", "G04", "2B", 10, square(0.1, 0, 9.7), 94.52)
    upstairs = zone("C", "104", "2B", 11, square(0, 0, 9.7), 94.5)
    beside = zone("D", "G05", "2B", 10, square(10, 0, 9), 81.0)
    kept, dropped = qa.drop_doubles([one, two, upstairs, beside])
    assert [z.guid for z in kept] == ["A", "C", "D"], "in their own order, the larger kept"
    assert [z.guid for z in dropped] == ["B"]


def test_a_kept_verdict_is_found_by_id_or_by_where_the_apartment_is() -> None:
    """D185: a hotlinked zone may be renumbered when its module reloads, so a
    verdict kept in the project is found by storey, name, number and centre
    when the id no longer answers."""
    same = zone("A", "01", "1B", 17, square(0, 0, 8), 64.0)
    renumbered = zone("NEW", "09", "1B", 17, square(20, 0, 8), 64.0)
    moved = zone("M", "10", "3B", 17, square(40, 0, 8), 64.0)
    records = [
        {
            "guid": "a",
            "storey": 17,
            "name": "01",
            "number": "1B",
            "x": 4,
            "y": 4,
            "meets": "Yes",
            "noSun": "No",
        },
        {
            "guid": "OLD",
            "storey": 17,
            "name": "09",
            "number": "1B",
            "x": 24,
            "y": 4,
            "meets": "No",
            "noSun": "Yes",
        },
        {
            "guid": "GONE",
            "storey": 17,
            "name": "10",
            "number": "3B",
            "x": 80,
            "y": 4,
            "meets": "Yes",
            "noSun": "No",
        },
    ]
    found = qa.from_store([same, renumbered, moved], records)
    assert found["A"] == {"Meets Minimum": "Yes", "No Direct Sunlight": "No"}
    assert found["NEW"] == {"Meets Minimum": "No", "No Direct Sunlight": "Yes"}
    assert "M" not in found, "a centre too far off is not the same apartment"


def test_the_kept_verdicts_are_read_back_from_the_project() -> None:
    import json

    from sun_study.archicad.write import stored_assessment
    from tests.unit.test_archicad_adapter import connect

    kept = {
        "version": 1,
        "run": "2026-11-12 03:00 UTC",
        "apartments": [{"guid": "a", "meets": "Yes"}],
    }
    connection, transport = connect(
        {"GetProjectData": {"success": True, "found": True, "content": json.dumps(kept)}}
    )
    run, rows = stored_assessment(connection)
    assert run == "2026-11-12 03:00 UTC" and rows == [{"guid": "a", "meets": "Yes"}]
    assert transport.parameters_for("GetProjectData") == {"name": "solar"}
    nothing, _ = connect({"GetProjectData": {"success": True, "found": False}})
    assert stored_assessment(nothing) == ("", [])
