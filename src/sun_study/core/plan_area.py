"""The area of a polygon as Archicad keeps one: straight edges, arcs and holes.

A massing slab is drawn with the slab tool, and the slab tool draws curves: a
tower's rounded corner is one edge of the outline with an angle on it, not a
run of short straight edges. Reading only the corners and joining them with
straight lines cuts every such corner off, and on a floor plate with a
quarter-circle corner of four metres that is three and a half square metres
per floor, forty storeys high. So the arcs are counted.

How an arc is written
---------------------
Archicad keeps a polygon as its corners and, separately, a list of the edges
that are arcs: which two corners each joins, and the angle it turns through.
``API_PolyArc.arcAngle`` is in radians, **positive when the arc runs
counter-clockwise** from its first corner to its second -- the same sense
as every other angle in the API, and as GDL's. An arc is the straight edge
between its corners plus a circular segment, and the segment's area has the
sign of its angle:

    segment = r² / 2 · (θ - sin θ),   r = chord / (2 sin(θ/2))

So the signed area of a ring is the shoelace sum of its corners plus the
signed segment of each arc, whichever way round the ring runs: a convex
rounded corner on a counter-clockwise ring turns counter-clockwise and adds,
and the same corner on a clockwise ring turns clockwise, subtracts from a
negative sum, and adds to its size. The ring's area is the size of that.

Checked here against closed forms -- a circle kept as two corners and two
half-circle arcs, a square with one corner rounded -- and not yet against
Archicad's own figure for a rounded slab, which is the first thing to read
on a workstation; ``docs/yield.md`` says how.

Holes
-----
A slab's outline and its holes are separate rings: the first is the outline,
every further one a hole, each with its own arcs. A floor's area is the
outline less its holes -- a lift core cut through the slab is not floor.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["Arc", "Ring", "floor_area", "ring_area", "segment_area", "signed_area"]

Point = tuple[float, float]

#: Below this an arc is a straight edge: the segment of a chord of a hundred
#: metres turning through a nanoradian is far below a square millimetre, and
#: the closed form divides by the sine of half the angle.
STRAIGHT = 1e-9


@dataclass(frozen=True)
class Arc:
    """One curved edge of a ring: from corner ``start`` to corner ``end``,
    turning ``angle`` radians, positive counter-clockwise."""

    start: int
    end: int
    angle: float


@dataclass(frozen=True)
class Ring:
    """One closed boundary: its corners in order, the first not repeated at
    the end, and which of its edges are arcs."""

    points: tuple[Point, ...]
    arcs: tuple[Arc, ...] = ()


def segment_area(chord: float, angle: float) -> float:
    """The signed area between a chord of this length and an arc on it
    turning through ``angle`` radians: positive for a counter-clockwise arc,
    negative for a clockwise one, nothing for a straight edge."""
    if abs(angle) < STRAIGHT or chord <= 0.0:
        return 0.0
    half = math.sin(angle / 2.0)
    radius_squared = chord * chord / (4.0 * half * half)
    return radius_squared / 2.0 * (angle - math.sin(angle))


def signed_area(ring: Ring) -> float:
    """The ring's area, positive when it runs counter-clockwise.

    An arc whose corners are not both on the ring is left out rather than
    guessed at: it can only come from a polygon read wrongly, and the
    straight edge under it is still counted.
    """
    points = ring.points
    count = len(points)
    if count < 2:
        return 0.0
    twice = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % count]
        twice += x0 * y1 - x1 * y0
    area = twice / 2.0
    for arc in ring.arcs:
        if not (0 <= arc.start < count and 0 <= arc.end < count):
            continue
        (x0, y0), (x1, y1) = points[arc.start], points[arc.end]
        area += segment_area(math.hypot(x1 - x0, y1 - y0), arc.angle)
    return area


def ring_area(ring: Ring) -> float:
    """The ring's area, whichever way round it runs."""
    return abs(signed_area(ring))


def floor_area(outline: Ring, holes: Sequence[Ring] = ()) -> float:
    """The outline's area less its holes', never below nothing."""
    return max(0.0, ring_area(outline) - sum(ring_area(hole) for hole in holes))
