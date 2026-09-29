"""The area calculation: slab areas with arcs and holes, and the office's
arithmetic from GBA to yield.

The office's own sheet is the fixture. Its numbers are reproduced here from
its two GBAs and its site, with its two rows the right way round: the bulk
it calls non-residential was worked with the residential factors.
"""

from __future__ import annotations

import math

import pytest

from sun_study.core.plan_area import Arc, Ring, floor_area, ring_area, segment_area, signed_area
from sun_study.rules.area_yield import (
    DEFAULT_MIX,
    NON_RESIDENTIAL,
    RESIDENTIAL,
    AreaSchedule,
    Floor,
    Ratios,
    Targets,
    UnitType,
    checked_mix,
    homes_for,
    parse_unit,
    schedule,
    unit_text,
)

# -- the area of a polygon as Archicad keeps one ------------------------------


def test_a_square_is_its_side_squared_whichever_way_it_runs() -> None:
    square = Ring(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)))
    assert signed_area(square) == pytest.approx(100.0)
    backwards = Ring(tuple(reversed(square.points)))
    assert signed_area(backwards) == pytest.approx(-100.0)
    assert ring_area(backwards) == pytest.approx(100.0)


def test_a_circle_kept_as_two_corners_and_two_arcs_is_pi_r_squared() -> None:
    """Archicad draws a circular slab as two points and two half-circle arcs:
    the corners alone enclose nothing at all."""
    circle = Ring(((3.0, 0.0), (-3.0, 0.0)), (Arc(0, 1, math.pi), Arc(1, 0, math.pi)))
    assert ring_area(circle) == pytest.approx(math.pi * 9.0)
    clockwise = Ring(((3.0, 0.0), (-3.0, 0.0)), (Arc(0, 1, -math.pi), Arc(1, 0, -math.pi)))
    assert ring_area(clockwise) == pytest.approx(math.pi * 9.0)


def test_a_rounded_corner_adds_its_segment_to_the_cut_corner() -> None:
    """A 10 m square with one corner rounded to a 2 m radius: the square less
    the corner's square plus the quarter disc, 96 + pi. The corners alone,
    joined straight, cut the corner off at 98 and miss the segment."""
    points = ((0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (8.0, 10.0), (0.0, 10.0))
    rounded = Ring(points, (Arc(2, 3, math.pi / 2),))
    assert ring_area(Ring(points)) == pytest.approx(98.0)
    assert ring_area(rounded) == pytest.approx(96.0 + math.pi)
    # The same slab traced the other way: the corner turns the other way too.
    back = tuple(reversed(points))
    assert ring_area(Ring(back, (Arc(1, 2, -math.pi / 2),))) == pytest.approx(96.0 + math.pi)


def test_a_concave_arc_takes_its_segment_away() -> None:
    """A bite out of the edge: the same arc turning into the floor."""
    points = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0))
    bitten = Ring(points, (Arc(1, 2, -math.pi),))
    assert ring_area(bitten) == pytest.approx(16.0 - math.pi * 2.0**2 / 2.0)


def test_a_hole_is_not_floor() -> None:
    outline = Ring(((0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)))
    core = Ring(((5.0, 3.0), (9.0, 3.0), (9.0, 7.0), (5.0, 7.0)))
    assert floor_area(outline, [core]) == pytest.approx(200.0 - 16.0)
    assert floor_area(core, [outline]) == 0.0, "never below nothing"


def test_a_straight_arc_and_an_arc_off_the_ring_add_nothing() -> None:
    assert segment_area(5.0, 0.0) == 0.0
    square = Ring(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), (Arc(7, 8, 1.0),))
    assert ring_area(square) == pytest.approx(1.0)


# -- the unit mix ------------------------------------------------------------------


def test_a_unit_type_is_written_as_name_share_and_size() -> None:
    assert parse_unit("2 Bedroom=70,75") == UnitType("2 Bedroom", 0.70, 75.0)
    assert parse_unit(" Studio = 10% ; 38.5 m2 ") == UnitType("Studio", 0.10, 38.5)
    assert unit_text(UnitType("2 Bedroom", 0.70, 75.0)) == "2 Bedroom=70,75"
    with pytest.raises(ValueError, match="like '2 Bedroom=70,75'"):
        parse_unit("2 Bedroom 70 75")


def test_a_mix_has_to_come_to_a_hundred_per_cent() -> None:
    with pytest.raises(ValueError, match="come to 90%"):
        checked_mix([UnitType("1 Bedroom", 0.2, 50), UnitType("2 Bedroom", 0.7, 75)])
    with pytest.raises(ValueError, match="twice"):
        checked_mix([UnitType("2 Bedroom", 0.5, 75), UnitType("2 bedroom", 0.5, 75)])
    with pytest.raises(ValueError, match="no size"):
        checked_mix([UnitType("Studio", 1.0, 0.0)])
    # A type with no share is simply not in the mix.
    kept = checked_mix([UnitType("Studio", 0.0, 35), *DEFAULT_MIX])
    assert [unit.name for unit in kept] == ["1 Bedroom", "2 Bedroom", "3 Bedroom"]


def test_the_split_always_adds_back_up_to_the_count() -> None:
    thirds = [UnitType(name, 1 / 3, 70.0) for name in ("A", "B", "C")]
    homes = homes_for(100 * 70.0, thirds)
    assert homes.units == 100
    assert [count.count for count in homes.counts] == [34, 33, 33], "the first-listed first"
    fifths = [UnitType(str(i), 0.2, 50.0) for i in range(5)]
    assert sum(c.count for c in homes_for(3 * 50.0, fifths).counts) == 3


def test_a_part_unit_is_not_a_unit() -> None:
    assert homes_for(74.9 * 1, [UnitType("2 Bedroom", 1.0, 75.0)]).units == 0
    assert homes_for(75.0 * 1, [UnitType("2 Bedroom", 1.0, 75.0)]).units == 1
    assert homes_for(0.0, DEFAULT_MIX).units == 0


# -- the office's own sheet --------------------------------------------------------

#: Read off the sheet: the two GBAs and the site its FSR implies.
TOWER_GBA = 13219.56
PODIUM_GBA = 1387.68
SITE = 1386.78


def office_sheet() -> AreaSchedule:
    floors = [
        Floor("Level 01", NON_RESIDENTIAL, PODIUM_GBA, 0.0),
        *(Floor(f"Level {n:02d}", RESIDENTIAL, TOWER_GBA / 12, 3.1 * n) for n in range(2, 14)),
    ]
    return schedule(floors, site_area_m2=SITE, targets=Targets(fsr=8.0, units=110))


def test_the_office_sheet_comes_out_of_its_own_gba() -> None:
    result = office_sheet()
    assert result.total.gba_m2 == pytest.approx(14607.24)
    assert result.residential.gfa_m2 == pytest.approx(9914.67, abs=0.01)
    assert result.non_residential.gfa_m2 == pytest.approx(1248.91, abs=0.01)
    assert result.total.gfa_m2 == pytest.approx(11163.58, abs=0.01)
    assert result.residential.nsa_m2 == pytest.approx(8427.47, abs=0.01)
    assert result.non_residential.nsa_m2 == pytest.approx(1124.02, abs=0.01)
    assert result.total.nsa_m2 == pytest.approx(9551.49, abs=0.01)
    assert result.fsr(result.total) == pytest.approx(8.05, abs=0.005)
    assert result.fsr(result.residential) == pytest.approx(7.15, abs=0.005)
    assert result.fsr(result.non_residential) == pytest.approx(0.90, abs=0.005)


def test_the_office_sheets_yield_is_112_units_at_17_78_and_17() -> None:
    result = office_sheet()
    assert result.homes.average_m2 == pytest.approx(75.0)
    assert result.homes.units == 112
    assert [(c.unit.name, c.count) for c in result.homes.counts] == [
        ("1 Bedroom", 17),
        ("2 Bedroom", 78),
        ("3 Bedroom", 17),
    ]
    assert result.gfa_per_unit_m2 == pytest.approx(9914.67 / 112, abs=0.01)


def test_the_targets_are_the_control_on_this_site() -> None:
    result = office_sheet()
    assert result.target_gfa_m2 == pytest.approx(8.0 * SITE)
    assert result.targets.units == 110


def test_the_storeys_are_in_level_order_with_their_uses_apart() -> None:
    result = office_sheet()
    assert [row.storey for row in result.storeys][:3] == ["Level 01", "Level 02", "Level 03"]
    assert result.storeys[0].non_residential_m2 == pytest.approx(PODIUM_GBA)
    assert result.storeys[0].residential_m2 == 0.0
    assert sum(row.total_m2 for row in result.storeys) == pytest.approx(14607.24)


def test_without_a_site_there_is_no_fsr_and_no_target_gfa() -> None:
    result = schedule([Floor("L1", RESIDENTIAL, 1000.0)], targets=Targets(fsr=3.0))
    assert result.fsr(result.total) is None
    assert result.target_gfa_m2 is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"site_area_m2": 0.0}, "site area"),
        ({"targets": Targets(fsr=-1.0)}, "target FSR"),
        ({"targets": Targets(units=-3)}, "target unit count"),
    ],
)
def test_a_setting_that_cannot_be_right_is_said(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        schedule([Floor("L1", RESIDENTIAL, 100.0)], **kwargs)  # type: ignore[arg-type]


def test_a_factor_outside_nothing_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match=r"GBA to GFA \(residential\)"):
        Ratios(gfa_residential=1.2)
    with pytest.raises(ValueError, match="GFA to NSA"):
        Ratios(nsa_non_residential=0.0)
