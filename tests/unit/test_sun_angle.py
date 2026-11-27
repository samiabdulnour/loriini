"""The angle off a wall from which the sun lights it (D199).

A wall the sun stands a degree off is "facing" it by the dot product's sign,
and its samples were lit; behind a real window that sun does nothing. The
ruleset now says from how many degrees off the wall, in plan, the sun counts:
5 by convention, 0 for the sign alone. Floors, roofs and the ground are not
walls and keep the sign alone.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from sun_study.core.analysis import (
    DEFAULT_MIN_SUN_ANGLE_DEG,
    candidate_rays,
    faces_sun,
    reached_by_sun,
    sunlit_matrix,
)
from sun_study.core.geometry import TriangleMesh
from sun_study.core.occlusion import Occluder
from sun_study.core.sampling import single_sample
from sun_study.rules.ruleset import load_ruleset

EMPTY = Occluder(TriangleMesh.empty())
EAST = (1.0, 0.0, 0.0)
UP = (0.0, 0.0, 1.0)


def sun(
    off_wall_deg: float, altitude_deg: float, wall_normal: tuple[float, float, float] = EAST
) -> np.ndarray:
    """A unit vector to a sun ``off_wall_deg`` off an east-facing wall's plane in
    plan (on the north side of its normal), ``altitude_deg`` up."""
    bearing_off_normal = math.radians(90.0 - off_wall_deg)
    nx, ny = wall_normal[0], wall_normal[1]
    # rotate the wall's normal towards north by (90 - off) degrees, in plan
    hx = nx * math.cos(bearing_off_normal) - ny * math.sin(bearing_off_normal)
    hy = nx * math.sin(bearing_off_normal) + ny * math.cos(bearing_off_normal)
    alt = math.radians(altitude_deg)
    return np.array([[hx * math.cos(alt), hy * math.cos(alt), math.sin(alt)]])


def test_the_default_is_five_degrees() -> None:
    assert DEFAULT_MIN_SUN_ANGLE_DEG == 5.0
    assert load_ruleset("nsw_adg").assessment.min_sun_angle_deg == 5.0


@pytest.mark.parametrize(
    ("off_wall", "angle", "lit"),
    [
        (4.0, 5.0, False),  # within the cut-off
        (6.0, 5.0, True),  # past it
        (4.0, 0.0, True),  # 0 is the sign alone
        (0.5, 0.0, True),
        (-0.5, 0.0, False),  # behind the wall, whatever the angle
        (20.0, 15.0, True),
        (14.0, 15.0, False),
    ],
)
def test_a_wall_is_lit_from_the_angle_off_it_in_plan(
    off_wall: float, angle: float, lit: bool
) -> None:
    point = single_sample((0.0, 0.0, 1.0), EAST, "wall")
    assert (
        bool(sunlit_matrix(point, EMPTY, sun(off_wall, 25.0), min_sun_angle_deg=angle)[0, 0]) is lit
    )


def test_the_angle_is_measured_in_plan_not_against_the_tilted_ray() -> None:
    """At 33 degrees up and 5.5 off the wall in plan, the ray itself is 4.6
    off the wall's plane. Practice and the court measure the horizontal angle,
    so this is past a 5 degree cut-off."""
    direction = sun(5.5, 33.0)
    assert math.degrees(math.asin(float(direction[0] @ np.array(EAST)))) < 5.0
    point = single_sample((0.0, 0.0, 1.0), EAST, "wall")
    assert sunlit_matrix(point, EMPTY, direction, min_sun_angle_deg=5.0)[0, 0]


def test_floors_roofs_and_the_ground_are_not_walls() -> None:
    """A sun three degrees up is on a floor's side of it; the cut-off is about
    a wall's plane, and does not ask a floor for an altitude."""
    floor = single_sample((0.0, 0.0, 0.0), UP, "floor")
    low = np.array([[0.0, math.cos(math.radians(3.0)), math.sin(math.radians(3.0))]])
    assert sunlit_matrix(floor, EMPTY, low, min_sun_angle_deg=5.0)[0, 0]


def test_a_sun_overhead_stands_in_every_walls_plane() -> None:
    wall = single_sample((0.0, 0.0, 1.0), EAST, "wall")
    overhead = np.array([[0.0, 0.0, 1.0]])
    assert not faces_sun(wall.normals, overhead, 5.0)[0, 0]


def test_the_ray_count_and_the_reach_use_the_same_test() -> None:
    wall = single_sample((0.0, 0.0, 1.0), EAST, "wall")
    suns = np.vstack([sun(4.0, 25.0), sun(10.0, 25.0)])
    assert candidate_rays(wall, suns, 5.0) == 1
    assert candidate_rays(wall, suns, 0.0) == 2
    assert reached_by_sun(wall, sun(4.0, 25.0), 5.0) == {"wall": False}
    assert reached_by_sun(wall, sun(4.0, 25.0), 0.0) == {"wall": True}


@pytest.mark.parametrize("angle", [-1.0, 90.0])
def test_an_angle_that_is_not_one_is_refused(angle: float) -> None:
    with pytest.raises(ValueError, match="min_sun_angle_deg"):
        faces_sun(np.array([EAST]), sun(10.0, 25.0), angle)


def test_the_header_says_which_angle() -> None:
    rules = load_ruleset("nsw_adg")
    assert "a wall lit from 5 deg off its plane" in rules.describe("sydney_metro")
