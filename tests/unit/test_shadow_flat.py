"""The flat shadow diagram's geometry: what is read out of a drawing, merged,
split between the rows and offered to Archicad. Nothing here needs Archicad."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from sun_study.archicad import shadow_flat
from sun_study.archicad.plan_sheet import PlanWindow


def _square(x: float, y: float, side: float, **more: object) -> dict[str, object]:
    """One polygon as the add-on hands it back: paper metres, closed."""
    xy = [x, y, x + side, y, x + side, y + side, x, y + side, x, y]
    return {"xy": xy, "ends": [5], "solid": True, "fillPen": 74, "pen": 0, **more}


def test_the_shadow_is_the_solid_polygons_in_its_pen_and_nothing_else() -> None:
    """A drawing of a document draws each fill twice, a solid polygon and the
    border of its hatch, and draws the surfaces too, in the transparent pen."""
    drawn = [
        _square(0.30, 0.30, 0.01),
        _square(0.30, 0.30, 0.01, solid=False, hatchPen=74),
        _square(0.40, 0.30, 0.01, fillPen=0),
        _square(0.50, 0.30, 0.01, fillPen=237),
    ]
    pieces = shadow_flat.shadow_pieces(drawn, 74, origin=(0.30, 0.30), scale=500.0)
    assert len(pieces) == 1
    assert pieces[0].bounds == pytest.approx((0.0, 0.0, 5.0, 5.0))


def test_a_piece_with_a_hole_keeps_it() -> None:
    xy = [
        0,
        0,
        0.1,
        0,
        0.1,
        0.1,
        0,
        0.1,
        0,
        0,
        0.04,
        0.04,
        0.06,
        0.04,
        0.06,
        0.06,
        0.04,
        0.06,
        0.04,
        0.04,
    ]
    piece = {"xy": xy, "ends": [5, 10], "solid": True, "fillPen": 74}
    (one,) = shadow_flat.shadow_pieces([piece], 74, origin=(0.0, 0.0), scale=100.0)
    assert len(one.interiors) == 1
    assert one.area == pytest.approx(100.0 - 4.0)


def test_pieces_a_hair_apart_are_one_shadow_and_the_window_cuts_it() -> None:
    """Archicad draws a shadow in a piece for every surface it falls on, and
    the pieces do not always meet to the last decimal."""
    pieces = [box(0.0, 0.0, 10.0, 10.0), box(10.0005, 0.0, 20.0, 10.0), box(40.0, 0.0, 50.0, 10.0)]
    whole = shadow_flat.merged(pieces)
    assert len(shadow_flat.drawable(whole)) == 2
    assert whole.area == pytest.approx(300.0, abs=0.1)
    cut = shadow_flat.merged(pieces, PlanWindow(5.0, -5.0, 45.0, 5.0))
    assert cut.area == pytest.approx((15.0 + 5.0) * 5.0, abs=0.1)
    assert shadow_flat.merged([]).is_empty


def test_a_row_is_seen_only_where_no_row_above_it_casts_a_shadow() -> None:
    """The stack's split, by subtracting: the rows bottom to top, the top one
    whole, each one under it what it adds."""
    existing = box(0.0, 0.0, 10.0, 10.0)
    proposed = box(5.0, 0.0, 20.0, 10.0)
    envelope = box(5.0, 0.0, 30.0, 10.0)
    seen = shadow_flat.seen_of_each(
        [("ENVELOPE", envelope), ("PROPOSED", proposed), ("EXISTING", existing)]
    )
    assert seen["EXISTING"].equals(existing)
    assert seen["PROPOSED"].area == pytest.approx(100.0)
    assert seen["PROPOSED"].bounds == pytest.approx((10.0, 0.0, 20.0, 10.0))
    assert seen["ENVELOPE"].bounds == pytest.approx((20.0, 0.0, 30.0, 10.0))
    total = sum(part.area for part in seen.values())
    assert total == pytest.approx(300.0), "no two fills lie over one another"


def test_what_archicad_is_offered_is_on_the_millimetre_grid_and_has_no_slivers() -> None:
    """Archicad refused 75 of 629 outlines the geometry library called valid,
    and 13 once they were on a grid: a vertex a fraction of a millimetre off
    a line reads to it as an outline crossing itself."""
    ragged = Polygon([(0.0, 0.0), (10.00004, 0.00003), (10.0, 10.0), (0.00002, 9.99996)])
    sliver = box(50.0, 0.0, 50.4, 0.4)
    parts = shadow_flat.drawable(ragged.union(sliver))
    assert len(parts) == 1
    for x, y in parts[0].exterior.coords:
        assert x == pytest.approx(round(x, 3), abs=1e-9) and y == pytest.approx(
            round(y, 3), abs=1e-9
        )
    assert parts[0].exterior.is_ccw, "every outline turned the one way"
    assert shadow_flat.drawable(Polygon()) == []


def test_an_outline_archicad_refuses_can_be_cut_so_no_piece_has_a_hole() -> None:
    holed = (
        box(0.0, 0.0, 30.0, 10.0)
        .difference(box(4.0, 4.0, 6.0, 6.0))
        .difference(box(20.0, 2.0, 24.0, 8.0))
    )
    pieces = shadow_flat.without_holes(shadow_flat.drawable(holed)[0])
    assert len(pieces) > 1
    assert all(not piece.interiors for piece in pieces)
    assert sum(piece.area for piece in pieces) == pytest.approx(holed.area, abs=0.01)
    plain = box(0.0, 0.0, 5.0, 5.0)
    assert shadow_flat.without_holes(plain) == [plain]


def test_the_dashed_outline_is_the_outside_of_each_part_closed() -> None:
    """The outside only: a lit courtyard is a hole in the fill, and a second
    ring inside the first would read as another building's shadow."""
    shadow = (
        box(0.0, 0.0, 20.0, 20.0)
        .difference(box(8.0, 8.0, 12.0, 12.0))
        .union(box(40.0, 0.0, 41.0, 1.0))
    )
    rings = shadow_flat.outline_rings(shadow)
    assert len(rings) == 1, "the courtyard is not outlined, and nor is a scrap"
    assert rings[0][0] == rings[0][-1]
    assert Polygon(rings[0]).area == pytest.approx(400.0)


def test_only_what_a_cell_shows_is_read() -> None:
    """Half a kilometre of context each way is several times a cell at any
    scale worth drawing at, and the cell's frame would clip the rest off."""
    everything = PlanWindow(-580.0, -590.0, 580.0, 590.0)
    shown = shadow_flat.window_a_cell_shows(everything, (175.0, 158.0), 1500.0)
    assert shown.centre == pytest.approx(everything.centre)
    assert (shown.width, shown.height) == pytest.approx((262.5, 237.0))
    small = PlanWindow(0.0, 0.0, 40.0, 30.0)
    assert shadow_flat.window_a_cell_shows(small, (175.0, 158.0), 1500.0) == small
    assert shadow_flat.hour_pitch(shown) == pytest.approx(262.5 * 1.25)
    assert shadow_flat.hour_pitch(small) == pytest.approx(60.0), "never nearer than 20 m"
