"""The yield analysis: slab areas with arcs and holes, the floors gathered
into levels, and the office's feasibility sheet worked from them.

The office's template is the fixture. Its *Option 01* -- a 6,704 m² site,
fourteen tower floors of 1,850 m² over a commercial level and a retail
ground floor -- is reproduced here to the cent: its GFA by use, its FSR,
its 220.575 units, its 333.02 parking spaces and its 4.97 basements.
"""

from __future__ import annotations

import math

import pytest

from sun_study.core.plan_area import Arc, Ring, floor_area, ring_area, segment_area, signed_area
from sun_study.rules.area_yield import (
    AFFORDABLE_MIX,
    COMMERCIAL,
    DEFAULT_MIX,
    RESIDENTIAL,
    RETAIL,
    Efficiencies,
    Feasibility,
    Floor,
    Mix,
    ParkingRates,
    Permissible,
    UnitRates,
    UnitType,
    checked_mix,
    feasibility,
    level_index,
    level_name,
    levels_from,
    parse_level,
    parse_rates,
    parse_unit,
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


# -- the unit mix ------------------------------------------------------------------


def test_a_unit_type_is_written_as_name_share_and_size() -> None:
    assert parse_unit("2-bed=70,75") == UnitType("2-bed", 0.70, 75.0)
    assert parse_unit(" Studio = 10% ; 38.5 m2 ") == UnitType("Studio", 0.10, 38.5)
    assert unit_text(UnitType("2-bed", 0.70, 75.0)) == "2-bed=70,75"
    with pytest.raises(ValueError, match="like '2-bed=70,75'"):
        parse_unit("2 Bedroom 70 75")


def test_a_mix_has_to_come_to_a_hundred_per_cent_and_keeps_a_type_at_nothing() -> None:
    with pytest.raises(ValueError, match="come to 90%"):
        checked_mix([UnitType("1-bed", 0.2, 50), UnitType("2-bed", 0.7, 75)])
    with pytest.raises(ValueError, match="twice"):
        checked_mix([UnitType("2-bed", 0.5, 75), UnitType("2-Bed", 0.5, 75)])
    with pytest.raises(ValueError, match="no size"):
        checked_mix([UnitType("Studio", 1.0, 0.0)])
    with pytest.raises(ValueError, match="no unit types"):
        checked_mix([UnitType("Studio", 0.0, 35.0)])
    # The sheet shows a type at nothing on its own row, so it stays.
    kept = checked_mix(DEFAULT_MIX)
    assert [unit.name for unit in kept] == ["Studio", "1-bed", "2-bed", "3-bed", "4-bed"]


def test_the_mixs_averages_are_the_sheets() -> None:
    market = Mix(DEFAULT_MIX)
    assert market.average_nla_m2 == pytest.approx(72.5)
    assert market.average_gfa_m2(Efficiencies()) == pytest.approx(85.294117647)
    assert Mix(AFFORDABLE_MIX).average_nla_m2 == pytest.approx(72.0)
    padded = Mix(DEFAULT_MIX, common_m2=5.0, tolerance_m2=2.5)
    assert padded.average_nla_m2 == pytest.approx(80.0)


# -- the levels --------------------------------------------------------------------


def test_floors_within_half_a_metre_are_one_level_counted_from_the_ground() -> None:
    bottoms = [8.61, 8.62, 13.11, 16.31, 5.61]
    assert level_index(bottoms) == [1, 1, 2, 3, 0], "the lowest is the ground when none is known"
    assert level_index(bottoms, ground_m=10.11) == [0, 0, 1, 2, -1], "the nearest to the storey"
    assert level_index([]) == []


def test_levels_are_named_as_the_sheet_names_them() -> None:
    assert [level_name(i) for i in (-2, -1, 0, 1, 12)] == [
        "B 02",
        "B 01",
        "Ground Floor",
        "Level 01",
        "Level 12",
    ]
    assert [parse_level(t) for t in ("Ground", "ground floor", "GF", "0", "Level 01", "L3")] == [
        0,
        0,
        0,
        0,
        1,
        3,
    ]
    assert [parse_level(t) for t in ("7", "B 01", "basement 2", "-3")] == [7, -1, -2, -3]
    with pytest.raises(ValueError, match="not a level"):
        parse_level("Mezzanine")


def test_a_levels_rise_is_to_the_one_above_and_the_tops_is_its_own_slab() -> None:
    floors = [
        Floor(RETAIL, 1500.0, 8.61, 4.3),
        Floor(COMMERCIAL, 1500.0, 13.11, 3.0),
        Floor(RESIDENTIAL, 900.0, 16.31, 3.0),
        Floor(RESIDENTIAL, 300.0, 16.35, 3.0),
    ]
    levels = levels_from(floors, ground_m=10.11)
    assert [level.name for level in levels] == ["Ground Floor", "Level 01", "Level 02"]
    assert [level.floor_to_floor_m for level in levels] == pytest.approx([4.5, 3.2, 3.0])
    assert levels[2].residential_m2 == pytest.approx(1200.0), "two slabs on one level add up"
    assert (levels[0].retail_m2, levels[1].commercial_m2) == (1500.0, 1500.0)
    # Thin slabs with air between: the top one takes the rise below it.
    thin = levels_from([Floor(RESIDENTIAL, 100.0, 0.0, 0.2), Floor(RESIDENTIAL, 100.0, 3.1, 0.2)])
    assert [level.floor_to_floor_m for level in thin] == pytest.approx([3.1, 3.1])


# -- the office's template, Option 01 -----------------------------------------------

SITE = 6704.0


def template_floors() -> list[Floor]:
    """The template's storey table: a 5 m retail ground floor with 50 m² of
    residential lobby, a 3.8 m commercial level, two empty levels, and
    fourteen 3.2 m tower floors of 1,850 m²."""
    floors = [
        Floor(RETAIL, 2800.0, 0.0, 5.0),
        Floor(RESIDENTIAL, 50.0, 0.0, 5.0),
        Floor(COMMERCIAL, 1500.0, 5.0, 3.8),
        Floor(RESIDENTIAL, 0.0, 8.8, 3.8),
        Floor(RESIDENTIAL, 0.0, 12.6, 3.8),
    ]
    bottom = 16.4
    for _ in range(14):
        floors.append(Floor(RESIDENTIAL, 1850.0, bottom, 3.2))
        bottom += 3.2
    return floors


def template() -> Feasibility:
    return feasibility(
        template_floors(),
        site_area_m2=SITE,
        permissible=Permissible(2.8, 0.2, 0.4),
        source=["BEA : 19 slabs"],
    )


def test_the_templates_areas_come_out_of_its_bea() -> None:
    sheet = template()
    assert sheet.bea(RESIDENTIAL) == pytest.approx(25950.0)
    assert (sheet.bea(COMMERCIAL), sheet.bea(RETAIL)) == (1500.0, 2800.0)
    assert sheet.gfa(RESIDENTIAL) == pytest.approx(18813.75)
    assert sheet.gfa(COMMERCIAL) == pytest.approx(1275.0)
    assert sheet.gfa(RETAIL) == pytest.approx(2660.0)
    assert sheet.total_gfa_m2 == pytest.approx(22748.75)
    assert sheet.nla(RESIDENTIAL) == pytest.approx(15991.6875)
    assert sheet.nla(COMMERCIAL) == pytest.approx(1147.5)
    assert sheet.nla(RETAIL) == pytest.approx(2394.0)


def test_the_templates_fsr_is_against_the_permissible_by_use() -> None:
    sheet = template()
    assert sheet.fsr(RESIDENTIAL) == pytest.approx(2.80634696)
    assert sheet.fsr(COMMERCIAL) == pytest.approx(0.19018496)
    assert sheet.fsr(RETAIL) == pytest.approx(0.39677804)
    assert sheet.total_fsr == pytest.approx(3.39330996)
    assert sheet.permissible.total == pytest.approx(3.4)
    assert sheet.permissible_gfa(RESIDENTIAL) == pytest.approx(18771.2)
    assert sheet.total_permissible_gfa_m2 == pytest.approx(22793.6)


def test_the_templates_units_are_not_rounded() -> None:
    sheet = template()
    assert sheet.market_units == pytest.approx((0.0, 44.115, 154.4025, 22.0575, 0.0))
    assert sheet.total_units == pytest.approx(220.575)
    assert sheet.permissible_market_units == pytest.approx(
        (0.0, 44.0152276, 154.0532966, 22.0076138, 0.0)
    )
    assert sheet.affordable_units == (0.0,) * 5, "no affordable share, no affordable units"


def test_the_templates_parking_and_basements() -> None:
    sheet = template()
    sepp, dcp = sheet.parking_spaces("sepp"), sheet.parking_spaces("dcp")
    assert sepp["market 1-bed"] == pytest.approx(22.0575)
    assert sepp["market 3-bed"] == pytest.approx(33.08625)
    assert dcp["market 3-bed"] == pytest.approx(22.0575)
    assert sepp["visitors"] == pytest.approx(22.0575) and dcp["visitors"] == 0.0
    assert sepp["residential"] == pytest.approx(231.60375)
    assert (sepp["commercial"], sepp["retail"]) == pytest.approx((12.75, 88.6666667))
    assert (dcp["commercial"], dcp["retail"]) == pytest.approx((3.1875, 6.65))
    assert sepp["total"] == pytest.approx(333.0204167)
    assert dcp["total"] == pytest.approx(208.355)
    assert sheet.basements("sepp") == pytest.approx(4.96748832)
    assert sheet.basements("dcp") == pytest.approx(3.10792064)


def test_the_storeys_are_counted_from_the_levels() -> None:
    sheet = template()
    assert [level.name for level in sheet.levels[:3]] == ["Ground Floor", "Level 01", "Level 02"]
    assert sheet.levels[-1].name == "Level 17"
    assert sheet.residential_storeys == 15, "fourteen tower floors and the lobby"
    assert sheet.podium_storeys == 1, "the commercial level; empty levels are not storeys"


def test_an_affordable_share_splits_the_units_between_the_two_mixes() -> None:
    sheet = feasibility(template_floors(), site_area_m2=SITE, affordable_share=0.25)
    assert sum(sheet.market_units) == pytest.approx(220.575 * 0.75)
    affordable_average = Mix(AFFORDABLE_MIX).average_gfa_m2(Efficiencies())
    assert sum(sheet.affordable_units) == pytest.approx(18813.75 / affordable_average * 0.25)
    sepp = sheet.parking_spaces("sepp")
    assert sepp["affordable 1-bed"] == pytest.approx(sheet.affordable_units[1] * 0.4)


def test_without_a_site_there_is_no_fsr_and_nothing_permissible() -> None:
    sheet = feasibility([Floor(RESIDENTIAL, 1000.0)], permissible=Permissible(3.0))
    assert sheet.fsr(RESIDENTIAL) is None and sheet.total_fsr is None
    assert sheet.permissible_gfa(RESIDENTIAL) is None
    assert sheet.permissible_market_units is None
    assert sheet.basements("sepp") is None
    assert sheet.gfa(RESIDENTIAL) == pytest.approx(725.0)


# -- the settings ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"site_area_m2": 0.0}, "site area"),
        ({"affordable_share": 1.5}, "affordable share"),
        ({"market": Mix((UnitType("2-bed", 0.9, 75.0),))}, "come to 90%"),
    ],
)
def test_a_setting_that_cannot_be_right_is_said(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        feasibility([Floor(RESIDENTIAL, 100.0)], **kwargs)  # type: ignore[arg-type]


def test_an_efficiency_outside_nothing_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match=r"BEA to GFA \(Residential\)"):
        Efficiencies(gfa_residential=1.2)
    with pytest.raises(ValueError, match="permissible retail FSR"):
        Permissible(retail=-1.0)


def test_parking_rates_are_the_sheets_unless_named() -> None:
    rates = ParkingRates()
    assert rates.market[2] == UnitRates(1.0, 1.0) and rates.affordable[1] == UnitRates(0.4, 0.5)
    assert parse_rates("2-bed=1.5,1") == ("2-bed", UnitRates(1.5, 1.0))
    with pytest.raises(ValueError, match="like '2-bed=1,1'"):
        parse_rates("2-bed 1 1")
    changed = rates.for_mixes(DEFAULT_MIX, AFFORDABLE_MIX, {"2 Bedroom": UnitRates(0.8, 0.8)})
    assert changed.market[2] == UnitRates(0.8, 0.8), "'2 Bedroom' is the sheet's '2-bed'"
    assert changed.market[1] == UnitRates(0.5, 0.5)
    with pytest.raises(ValueError, match="not in the market mix"):
        rates.for_mixes(DEFAULT_MIX, AFFORDABLE_MIX, {"Penthouse": UnitRates(2.0, 2.0)})
    with pytest.raises(ValueError, match="basement site ratio"):
        ParkingRates(basement_site_ratio=0.0)
    # A mix of other types gets a space a unit where the sheet has no rate.
    odd = feasibility(
        [Floor(RESIDENTIAL, 1000.0)],
        market=Mix((UnitType("Loft", 1.0, 60.0),)),
    )
    assert odd.parking.market == (UnitRates(1.0, 1.0),)
