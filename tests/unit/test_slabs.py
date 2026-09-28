"""The massing slabs read out of a scripted Archicad: what is asked for, what
comes back, and what is counted."""

from __future__ import annotations

import math
from typing import Any

import pytest

from sun_study.archicad.slabs import MassingSlab, floors_from, read_slabs, ring_from
from sun_study.core.plan_area import Ring
from sun_study.rules.area_yield import NON_RESIDENTIAL, RESIDENTIAL
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
    return {
        "type": "Slab",
        "floorIndex": floor,
        "layerIndex": layer,
        "id": extra.pop("id", ""),
        "details": details,
    }


def project(rows: list[dict[str, Any]]) -> tuple[Any, Any]:
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
                    {"index": 0, "level": 0.0, "name": "Ground"},
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


def test_the_slabs_come_with_their_storey_layer_and_holes() -> None:
    connection, transport = project(
        [
            row(1, 1, SQUARE, holes=[{"polygonOutline": CORE}]),
            row(2, 0, SQUARE, id="Retail"),
        ]
    )
    reading = read_slabs(connection)
    assert transport.parameters_for("GetElementsByType") == {"elementType": "Slab"}
    first, second = reading.slabs
    assert first.layer == "05 | Mass.Residential "
    assert (first.storey, first.level_m) == ("Level 1", 4.5)
    assert first.area_m2 == pytest.approx(200.0 - 16.0), "the core is not floor"
    assert (second.storey, second.element_id) == ("Ground", "Retail")


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


def slab(layer: str, area_side: float, storey: str = "L1") -> MassingSlab:
    square = Ring(((0.0, 0.0), (area_side, 0.0), (area_side, area_side), (0.0, area_side)))
    return MassingSlab("G", "", layer, storey, 0.0, square)


def test_the_layer_says_the_use_and_a_layer_named_for_neither_is_passed_over() -> None:
    slabs = [
        slab("05 | Mass.Residential ", 10.0),
        slab("05 | Mass.Retail", 5.0),
        slab("01 | Floor.Structural", 30.0),
    ]
    made = floors_from(slabs, ["05 | mass.residential"], ["05 | Mass.Retail", "05 | Mass.Office"])
    assert [(f.use, f.area_m2) for f in made.floors] == [
        (RESIDENTIAL, 100.0),
        (NON_RESIDENTIAL, 25.0),
    ]
    assert made.passed_over == {"01 | Floor.Structural": 1}
    assert made.missing == ("05 | Mass.Office",), "a named layer nothing stands on is said"
    assert made.by_layer["05 | Mass.Retail"] == (NON_RESIDENTIAL, 1, 25.0)


def test_with_no_layer_named_everything_showing_is_residential() -> None:
    made = floors_from([slab("A", 10.0), slab("B", 10.0)])
    assert [f.use for f in made.floors] == [RESIDENTIAL, RESIDENTIAL]
    assert not made.passed_over


def test_one_layer_cannot_be_two_uses() -> None:
    with pytest.raises(ValueError, match="both residential and non-residential"):
        floors_from([], ["05 | Mass"], [" 05 |  mass "])
