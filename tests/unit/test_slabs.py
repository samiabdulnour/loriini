"""The massing slabs read out of a scripted Archicad: what is asked for, what
comes back, where each slab stands, and what is counted."""

from __future__ import annotations

import math
from typing import Any

import pytest

from sun_study.archicad.slabs import BY_LEVEL, MassingSlab, floors_from, read_slabs, ring_from
from sun_study.core.plan_area import Ring
from sun_study.rules.area_yield import COMMERCIAL, RESIDENTIAL, RETAIL
from tests.unit.test_archicad_adapter import connect


def outline(*corners: tuple[float, float]) -> list[dict[str, float]]:
    """Corners as Tapir reports them: closed by repeating the first."""
    return [{"x": x, "y": y} for x, y in [*corners, corners[0]]]


SQUARE = outline((0, 0), (20, 0), (20, 10), (0, 10))
CORE = outline((5, 3), (9, 3), (9, 7), (5, 7))
#: A 10 m square with its last edge -- from (0, 10) back to the start -- an
#: arc bulging out to the west: the arc ends on the repeated corner.
ROUNDED = outline((0, 0), (10, 0), (10, 10), (0, 10))


def row(layer: int, floor: int, polygon: list[dict[str, float]], **extra: Any) -> dict[str, Any]:
    details: dict[str, Any] = {"polygonOutline": polygon, "holes": extra.pop("holes", [])}
    if "arcs" in extra:
        details["polygonArcs"] = extra.pop("arcs")
    identifier = extra.pop("id", "")
    details.update(extra)
    return {
        "type": "Slab",
        "floorIndex": floor,
        "layerIndex": layer,
        "id": identifier,
        "details": details,
    }


def project(rows: list[dict[str, Any]], ground: str = "Ground") -> tuple[Any, Any]:
    return connect(
        {
            "GetElementsByType": {
                "elements": [{"elementId": {"guid": f"G{i}"}} for i in range(len(rows))]
            },
            "GetDetailsOfElements": {"detailsOfElements": rows},
            "GetAttributesByType": {
                "attributes": [
                    {"index": 1, "name": "05 | Mass.Residential "},
                    {"index": 2, "name": "05 | Mass.Retail"},
                    {"index": 3, "name": "03 | Site Context.Buildings"},
                    {"index": 4, "name": "01 | Floor.Structural"},
                ]
            },
            "GetStories": {
                "stories": [
                    {"index": 0, "level": 0.0, "name": ground},
                    {"index": 1, "level": 4.5, "name": "Level 1"},
                ]
            },
        }
    )


def test_tapirs_ring_is_closed_by_a_repeat_and_an_arc_can_end_on_it() -> None:
    ring = ring_from(ROUNDED, [{"begIndex": 3, "endIndex": 4, "arcAngle": math.pi}])
    assert ring is not None
    assert len(ring.points) == 4, "the repeated corner is dropped"
    assert ring.arcs[0].start == 3 and ring.arcs[0].end == 0, "and the arc points at the first"
    assert ring_from([{"x": 0, "y": 0}, {"x": 1, "y": 0}]) is None
    assert ring_from("nothing") is None
    assert ring_from([{"x": 0, "y": "a"}] * 4) is None


def test_the_slabs_come_with_their_storey_layer_holes_and_height() -> None:
    connection, transport = project(
        [
            row(1, 1, SQUARE, holes=[{"polygonOutline": CORE}]),
            row(
                2,
                0,
                SQUARE,
                id="Retail",
                zCoordinate=12.91,
                offsetFromTop=0.0,
                thickness=4.3,
                level=2.8,
            ),
        ]
    )
    reading = read_slabs(connection)
    assert transport.parameters_for("GetElementsByType") == {"elementType": "Slab"}
    first, second = reading.slabs
    assert first.layer == "05 | Mass.Residential "
    assert (first.storey, first.level_m) == ("Level 1", 4.5)
    assert first.area_m2 == pytest.approx(200.0 - 16.0), "the core is not floor"
    assert (first.bottom_m, first.thickness_m) == (4.5, 0.0), "no height given: the storey's"
    assert (second.storey, second.element_id) == ("Ground", "Retail")
    assert second.bottom_m == pytest.approx(12.91 - 4.3), "the top less the thickness"
    assert second.thickness_m == 4.3
    assert reading.ground_m == 0.0, "the storey called Ground"


def test_a_slab_homed_below_its_plane_is_placed_by_the_plane() -> None:
    connection, _ = project(
        [row(1, 0, SQUARE, zCoordinate=10.0, offsetFromTop=0.3, thickness=0.3)],
        ground="GF",
    )
    (slab,) = read_slabs(connection).slabs
    assert slab.bottom_m == pytest.approx(10.0), (
        "a bottom reference plane: the plane is the underside"
    )


def test_without_a_storey_called_ground_none_is_said() -> None:
    connection, _ = project([row(1, 0, SQUARE)], ground="Storey A")
    assert read_slabs(connection).ground_m is None


def test_the_renovation_filter_and_the_shown_layers_are_archicads_own_filters() -> None:
    connection, transport = project([row(1, 0, SQUARE)])
    reading = read_slabs(connection, renovation=True, shown_layers_only=True)
    assert transport.parameters_for("GetElementsByType") == {
        "elementType": "Slab",
        "filters": ["IsVisibleByRenovation", "IsVisibleByLayer"],
    }
    assert reading.filters == ("IsVisibleByRenovation", "IsVisibleByLayer")


def test_loriinis_own_slabs_and_unreadable_ones_are_left_out_and_counted() -> None:
    connection, _ = project(
        [
            row(3, 0, SQUARE, id="SA NEIGHBOUR 12"),
            {"error": {"code": -1, "message": "no"}},
            row(1, 0, [{"x": 0, "y": 0}]),
            row(1, 0, SQUARE),
        ]
    )
    reading = read_slabs(connection)
    assert len(reading.slabs) == 1 and reading.own == 1
    assert reading.unreadable == ("G1", "G2")


def test_no_slabs_is_an_empty_reading_and_not_an_error() -> None:
    connection, transport = connect({"GetElementsByType": {"elements": []}})
    assert read_slabs(connection).slabs == ()
    assert "GetDetailsOfElements" not in transport.commands()


def slab(layer: str, side: float, bottom: float = 0.0, thickness: float = 3.0) -> MassingSlab:
    square = Ring(((0.0, 0.0), (side, 0.0), (side, side), (0.0, side)))
    return MassingSlab("G", "", layer, "L1", 0.0, square, (), bottom, thickness)


def test_the_layer_says_the_use_and_a_layer_named_for_nothing_is_passed_over() -> None:
    slabs = [
        slab("05 | Mass.Residential ", 10.0, 3.0),
        slab("05 | Mass.Retail", 5.0, 0.0),
        slab("05 | Mass.Office", 6.0, 6.0),
        slab("01 | Floor.Structural", 30.0),
    ]
    made = floors_from(
        slabs,
        ["05 | mass.residential"],
        ["05 | Mass.Office", "05 | Mass.Podium"],
        ["05 | Mass.Retail"],
    )
    assert [(f.use, f.area_m2, f.bottom_m) for f in made.floors] == [
        (RESIDENTIAL, 100.0, 3.0),
        (RETAIL, 25.0, 0.0),
        (COMMERCIAL, 36.0, 6.0),
    ]
    assert made.passed_over == {"01 | Floor.Structural": 1}
    assert made.missing == ("05 | Mass.Podium",), "a named layer nothing stands on is said"
    assert made.by_layer["05 | Mass.Retail"] == (RETAIL, 1, 25.0)
    assert not made.levels_used, "no massing layer, no level told a use"


def test_a_massing_layers_slabs_take_their_use_from_their_level() -> None:
    stack = [
        slab("OPT1", 20.0, 8.61, 4.3),  # the ground, 1.5 m under the ground storey
        slab("OPT1", 20.0, 12.91, 3.0),
        slab("OPT1", 20.0, 15.91, 3.0),
        slab("OPT1", 10.0, 18.91, 3.0),
        slab("OPT1", 10.0, 21.91, 3.0),
    ]
    made = floors_from(
        stack, massing=["opt1"], retail_levels=[0], commercial_levels=[1, 2], ground_m=10.11
    )
    assert [f.use for f in made.floors] == [
        RETAIL,
        COMMERCIAL,
        COMMERCIAL,
        RESIDENTIAL,
        RESIDENTIAL,
    ]
    assert made.by_layer["OPT1"] == (BY_LEVEL, 5, 1400.0)
    assert made.levels_used == {
        "Ground Floor": RETAIL,
        "Level 01": COMMERCIAL,
        "Level 02": COMMERCIAL,
        "Level 03": RESIDENTIAL,
        "Level 04": RESIDENTIAL,
    }


def test_another_options_slabs_keep_the_levels_lined_up() -> None:
    tower = [slab("OPT2", 10.0, 12.91, 3.0), slab("OPT2", 10.0, 15.91, 3.0)]
    alone = floors_from(tower, massing=["OPT2"], retail_levels=[0], ground_m=10.11)
    assert [f.use for f in alone.floors] == [RETAIL, RESIDENTIAL], "its lowest read as the ground"
    together = floors_from(
        tower, massing=["OPT2"], retail_levels=[0], ground_m=10.11, others_m=[8.61]
    )
    assert [f.use for f in together.floors] == [RESIDENTIAL, RESIDENTIAL]
    assert list(together.levels_used) == ["Level 01", "Level 02"]


def test_with_no_layer_named_everything_showing_is_massing() -> None:
    made = floors_from([slab("A", 10.0, 0.0), slab("B", 10.0, 3.0)], retail_levels=[0])
    assert [f.use for f in made.floors] == [RETAIL, RESIDENTIAL]
    assert not made.passed_over


def test_one_layer_cannot_be_two_things() -> None:
    with pytest.raises(ValueError, match="both residential and commercial"):
        floors_from([], ["05 | Mass"], [" 05 |  mass "])
    with pytest.raises(ValueError, match="both retail and massing"):
        floors_from([], retail=["05 | Mass"], massing=["05 | Mass"])


def test_slabs_are_chosen_by_their_own_renovation_status() -> None:
    from tests.unit.test_archicad_adapter import connect as connect_

    rows = [row(1, 0, SQUARE), row(1, 1, SQUARE), row(1, 0, SQUARE), row(1, 0, SQUARE)]
    statuses = ["New", "Existing", "To Be Demolished", "Unbekannt"]
    connection, transport = connect_(
        {
            "GetElementsByType": {
                "elements": [{"elementId": {"guid": f"G{i}"}} for i in range(len(rows))]
            },
            "GetAllProperties": {
                "properties": [
                    {"propertyId": {"guid": "P0"}, "propertyName": "Area"},
                    {"propertyId": {"guid": "RS"}, "propertyName": "Renovation Status"},
                ]
            },
            "GetPropertyValuesOfElements": {
                "propertyValuesForElements": [
                    {"propertyValues": [{"propertyValue": {"value": status}}]}
                    for status in statuses
                ]
            },
            "GetDetailsOfElements": {"detailsOfElements": rows[:1]},
            "GetAttributesByType": {"attributes": [{"index": 1, "name": "05 | Mass"}]},
            "GetStories": {"stories": [{"index": 0, "level": 0.0, "name": "Ground"}]},
        }
    )
    reading = read_slabs(connection, statuses=("new",))
    assert [slab.guid for slab in reading.slabs] == ["G0"], "the new one alone"
    assert reading.statuses == ("new",)
    assert reading.by_status == {"existing": 1, "demolished": 1}
    assert reading.unknown_status == {"Unbekannt": 1}, "never guessed"
    (details,) = transport.all_parameters_for("GetDetailsOfElements")
    assert [e["elementId"]["guid"] for e in details["elements"]] == ["G0"], (
        "only the chosen slabs are described"
    )
