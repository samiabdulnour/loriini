"""The ground in metres: the level at a point, and a terrain mesh's lines.

The level cases are the generator's own (``au-site-analysis``,
``test/site-features``, "the level at a point, between the contours that
bracket it"), figure for figure, so the site sheet here and the PDF there
print the same RL at the same corner. The mesh cases are what the new rule
promises: the budget kept, the site's contours kept, and no two lines made to
cross that did not cross before.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from sun_study.site.geo import Point
from sun_study.site.ground import (
    NEAR_M,
    PLANS,
    Ground,
    crossings,
    mesh_lines,
    simplify,
)

Line = tuple[float, list[Point]]


def line(level: float, y: float) -> Line:
    """A straight contour running east-west at ``y``."""
    return (level, [(-100.0, y), (100.0, y)])


# -- the level at a point ----------------------------------------------------------

SLOPE = [line(40, 0), line(41, 10), line(42, 20), line(43, 30)]


def test_a_point_part_way_up_a_rise_is_that_far_up_it() -> None:
    ground = Ground(SLOPE, interval_m=1.0)
    assert ground.at((0.0, 13.0)) == pytest.approx(41.3, abs=0.01)
    assert ground.at((5.0, 20.0)) == 42.0, "on the line is the line"


def test_past_the_last_contour_the_slope_carries_on_but_one_interval_at_most() -> None:
    ground = Ground(SLOPE, interval_m=1.0)
    assert ground.at((0.0, 35.0)) == pytest.approx(43.5, abs=0.01)
    assert ground.at((0.0, 60.0)) == pytest.approx(44.0, abs=0.01)
    assert ground.at((0.0, -4.0)) == pytest.approx(39.6, abs=0.01)


def test_the_contour_on_the_far_side_of_the_nearest_one_is_ignored() -> None:
    """The case that put a corner half a metre low: the 43 line is closer
    than the 45, but it is on the far side of the 44. The point is between 44
    and 45, and the nearest-two average said 43.7."""
    nose = [line(43, -7), line(44, 0), line(45, 13)]
    assert Ground(nose, interval_m=1.0).at((0.0, 3.6)) == pytest.approx(44.28, abs=0.01)


BEND: list[Line] = [
    (41, [(-30.0, 20.0), (-6.0, 20.0), (-6.0, 0.0), (6.0, 0.0), (6.0, 20.0), (30.0, 20.0)]),
    (42, [(-30.0, -10.0), (30.0, -10.0)]),
]


def test_inside_a_bend_the_level_follows_the_slope_through_it() -> None:
    """The 41 line wraps the point on three sides and the 42 lies beyond its
    bottom: a gully coming down from the open side, below 41."""
    assert Ground(BEND, interval_m=1.0).at((0.0, 5.0)) == pytest.approx(40.5, abs=0.01)


def test_a_line_through_the_opening_brackets_the_gully() -> None:
    gully = [*BEND, line(40, 15)]
    assert Ground(gully, interval_m=1.0).at((0.0, 5.0)) == pytest.approx(41 - 5 / 15, abs=0.01)


def test_inside_a_closed_loop_is_above_it() -> None:
    knoll: list[Line] = [
        (45, [(-8.0, -8.0), (8.0, -8.0), (8.0, 8.0), (-8.0, 8.0), (-8.0, -8.0)]),
        (44, [(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0), (-20.0, -20.0)]),
    ]
    top = Ground(knoll, interval_m=1.0).at((0.0, 0.0))
    assert top is not None and 45.0 < top <= 46.0


def test_no_contours_gives_nothing() -> None:
    assert Ground([], interval_m=1.0).at((0.0, 0.0)) is None


def test_the_index_answers_as_a_scan_of_every_line_would() -> None:
    """A walk that looks near first must agree with one that looks as far as
    it may from the start: the same levels on a random scatter of points
    over a wavy slope, with a cell small enough that most walks widen."""
    rng = np.random.default_rng(7)
    wavy = [
        (float(level), [(x, level * 6.0 + 3.0 * math.sin(x / 9.0)) for x in range(-120, 121, 3)])
        for level in range(0, 20)
    ]
    indexed = Ground(wavy, interval_m=1.0, cell_m=5.0)
    whole = Ground(wavy, interval_m=1.0, cell_m=500.0)
    for x, y in rng.uniform([-100, -10], [100, 130], size=(60, 2)):
        assert indexed.at((x, y)) == pytest.approx(whole.at((x, y)), abs=1e-9)


# -- simplifying -----------------------------------------------------------------------


def test_a_straight_line_needs_its_two_ends() -> None:
    points = np.array([(float(x), 0.0) for x in range(50)])
    assert list(simplify(points, np.full(50, 0.1))) == [0, 49]


def test_every_vertex_keeps_its_own_tolerance() -> None:
    """Wiggles of 0.3 m: kept where the tolerance is a tenth of a metre,
    gone where it is a metre."""
    points = np.array([(float(x), 0.3 * (x % 2)) for x in range(40)])
    tolerance = np.where(points[:, 0] < 20, 0.1, 1.0)
    kept = simplify(points, tolerance)
    assert all(i in kept for i in range(20)), "the fine half keeps every wiggle"
    assert sum(1 for i in kept if i >= 20) <= 2, "the coarse half keeps its ends"


def test_crossings_are_found_and_touching_is_not_crossing() -> None:
    x_mark = [np.array([(0.0, 0.0), (10.0, 10.0)]), np.array([(0.0, 10.0), (10.0, 0.0)])]
    found = crossings(x_mark)
    assert len(found) == 1
    assert found[0][4] == pytest.approx((5.0, 5.0))
    touching = [np.array([(0.0, 0.0), (5.0, 5.0)]), np.array([(5.0, 5.0), (10.0, 0.0)])]
    assert crossings(touching) == []
    bent = [np.array([(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)])]
    assert crossings(bent) == [], "a line's own neighbouring segments meet, not cross"


# -- the mesh's lines --------------------------------------------------------------------


def wavy(level: float, y: float, reach: float = 500.0, wiggle: float = 0.4) -> Line:
    """A contour across the whole model, a vertex every two metres, each
    alternate one ``wiggle`` off the line: a shape only a fine tolerance keeps."""
    return (
        level,
        [(float(x), y + wiggle * ((x // 2) % 2)) for x in range(int(-reach), int(reach) + 1, 2)],
    )


SITE = [[(-15.0, -20.0), (15.0, -20.0), (15.0, 20.0), (-15.0, 20.0)]]
SQUARE = [(-500.0, -500.0), (500.0, -500.0), (500.0, 500.0), (-500.0, 500.0)]


def test_the_budget_is_kept_and_spent_at_the_site() -> None:
    """A metre contour every ten metres across a kilometre square, every
    vertex a wiggle: fifty thousand vertices for a budget of twelve. Every
    contour that passes the site keeps its every wiggle there."""
    contours = [wavy(float(level), level * 10.0) for level in range(-50, 50)]
    lines = mesh_lines(contours, focus=SITE, within=SQUARE, budget=12_000, interval_m=1.0)
    assert lines.vertices <= 12_000
    for level in range(-2, 3):
        near = [p for z, points in lines.lines if z == level for p in points if abs(p[0]) <= 15.0]
        assert len(near) >= 15, f"the {level} m contour lost its shape across the site"
    # Far out the same wiggles are simplified away: a line and not a wave.
    far = [len(points) for z, points in lines.lines if z == 45]
    assert far and max(far) <= 10, far
    assert "every 1 m contour within 100 m of the site, true to 0.1 m" in lines.describe()


def test_every_contour_is_kept_when_they_all_fit() -> None:
    contours = [wavy(float(level), level * 20.0, reach=200.0) for level in range(-10, 10)]
    lines = mesh_lines(contours, focus=SITE, within=SQUARE, interval_m=1.0)
    assert lines.plan == PLANS[0]
    assert {z for z, _ in lines.lines} == set(range(-10, 10))


def test_when_the_site_alone_is_over_budget_it_gives_way_too() -> None:
    """Only a cliff would ask it: the contours within reach of the site hold
    more than the budget, and a mesh that cannot be made is worse than one a
    quarter of a metre coarser at the site."""
    contours = [wavy(float(level), level * 2.0, reach=150.0) for level in range(-60, 60)]
    lines = mesh_lines(contours, focus=SITE, within=SQUARE, budget=3_000, interval_m=1.0)
    assert lines.vertices <= 3_000
    assert lines.plan.base > PLANS[0].base


def test_simplifying_makes_no_two_lines_cross_that_did_not() -> None:
    """Far from the site, two contours a metre apart with a two-metre wave
    each, out of step: simplified independently to the far tolerance they
    would cross, and the mesh has to invent the ground where they do."""
    far = 400.0
    contours = [
        (
            float(level),
            [(x, far + level * 1.0 + 0.9 * math.sin(x / 3.0 + level)) for x in range(-300, 300)],
        )
        for level in range(0, 8)
    ]
    published = crossings([np.array(points) for _, points in contours])
    assert published == [], "the fixture's own lines do not cross"
    lines = mesh_lines(contours, focus=SITE, within=SQUARE, interval_m=1.0)
    assert crossings([np.array(points) for _, points in lines.lines]) == []


def test_the_lines_are_cut_to_the_mesh_and_end_at_its_edge() -> None:
    contours = [wavy(5.0, 0.0, reach=700.0)]
    lines = mesh_lines(contours, focus=SITE, within=SQUARE, interval_m=1.0)
    xs = [x for _, points in lines.lines for x, _ in points]
    assert min(xs) > -500.0 and max(xs) < 500.0, "inside the outline, never on it"
    assert min(xs) <= -499.9 and max(xs) >= 499.9, "each run reaches the edge"


def test_a_site_bigger_than_near_is_kept_whole() -> None:
    """Distance is from the site's boundary, not its centre: nothing inside
    a large site is thinned, however far from the middle."""
    big = [[(-300.0, -30.0), (300.0, -30.0), (300.0, 30.0), (-300.0, 30.0)]]
    contours = [wavy(float(level), level * 10.0) for level in range(-50, 50)]
    lines = mesh_lines(contours, focus=big, within=SQUARE, budget=12_000, interval_m=1.0)
    at_the_end = [
        p for z, points in lines.lines if z == 0 for p in points if 250.0 <= p[0] <= 290.0
    ]
    assert NEAR_M < 250.0
    assert len(at_the_end) >= 18, "the far end of a big site is the site"
