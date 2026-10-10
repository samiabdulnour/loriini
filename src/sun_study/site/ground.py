"""The ground in metres: its level anywhere, and the lines a mesh is made of.

Both read contours already in the project's frame -- ``(level, points)`` in
metres -- so the site sheet's corner levels, the context model's slabs and
kerbs, and its terrain mesh all read the same ground the same way.

The level at a point
--------------------
Between two contours the ground is taken to run straight from one to the
other, so the level at a point is found by walking across the slope to the
first contour each way and interpolating by distance. The walk is tried in
twelve directions and the shortest crossing pair wins: that is the steepest
line through the point, the one the ground actually follows. Taking the two
nearest contours by distance is not enough -- the second-nearest is as often
the next line down on the far side of the nearest as the one across from it,
which put a corner half a metre low on a sheet of 1 m contours. That is the
generator's ``lib/levels.ts``, ported rule for rule; what is added here is an
index, so a model's thousands of kerb corners read a kilometre of contours in
seconds rather than minutes.

The lines a mesh is made of
---------------------------
Archicad triangulates between every vertex of a mesh's level lines, so the
terrain has a budget, and what matters is where it is spent. The old rule
halved contours and points everywhere until the budget was met, which kept a
kilometre of the state's 2 m contours as 4 m ones and would have kept the
City of Sydney's 1 m contours -- 440,000 vertices a square kilometre -- as
8 m ones: worse than what they replaced, everywhere, the site included.

So the detail now falls away from the site instead. Within ``NEAR_M`` of the
site's boundary every contour is kept, simplified only by a tenth of a metre
-- the staircase of the grid they were traced from, not the ground's shape.
Past it the tolerance grows with distance, and past ``NEAR_M`` and ``FAR_M``
only every second or fifth contour is kept where the budget needs it; the
plans are tried finest first and the first that fits is used. The
simplification is Douglas-Peucker with a tolerance of its own at every vertex,
so one contour running from the site to the edge is fine at one end and coarse
at the other. On Surry Hills' 1 m contours that is 8,300 vertices: every
contour within 100 m of the site, every second to 250 m, every fifth beyond.

Simplifying two lines independently can make them cross where the ground is
steep -- a retaining wall, a cutting -- and a mesh whose level lines cross
has to invent the ground between them. So the simplified lines are checked,
and the two spans of every crossing simplified again at half their tolerance,
and again, span by span, so a crossing costs a few vertices rather than a
line. A plan that crosses so much that mending it breaks the budget is too
coarse for its contours and gives way to the next. A crossing still there
once neither span moves a centimetre crossed as published: the City of
Sydney's contours touch and cross by millimetres where the ground drops at a
wall, and that is the survey's to mend, not the mesh's.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray

from sun_study.site.geo import Point

__all__ = [
    "BASE_TOLERANCE_M",
    "FAR_M",
    "MESH_POINTS",
    "NEAR_M",
    "PLANS",
    "Ground",
    "MeshLines",
    "Plan",
    "boundary_crossing",
    "crossings",
    "edges_of",
    "mesh_lines",
    "points_in_rings",
    "simplify",
]

Contours = Sequence[tuple[float, Sequence[Point]]]
Floats = NDArray[np.float64]


# -- rings, many points at a time --------------------------------------------------


def edges_of(rings: Iterable[Sequence[Point]]) -> Floats:
    """Every edge of every ring as an ``x1, y1, x2, y2`` row."""
    rows = [
        (a[0], a[1], b[0], b[1])
        for ring in rings
        if len(ring) >= 3
        for a, b in zip(ring, [*ring[1:], ring[0]], strict=True)
        if a != b
    ]
    return np.array(rows, dtype=np.float64).reshape(-1, 4)


def points_in_rings(points: Floats, edges: Floats) -> NDArray[np.bool_]:
    """Which of the ``(n, 2)`` points the rings hold, by the even-odd rule, so
    a hole is outside and an island inside it is in again."""
    held = np.zeros(len(points), dtype=bool)
    if not len(edges) or not len(points):
        return held
    x1, y1, x2, y2 = edges[:, 0], edges[:, 1], edges[:, 2], edges[:, 3]
    for start in range(0, len(points), 2048):
        x = points[start : start + 2048, 0:1]
        y = points[start : start + 2048, 1:2]
        straddles = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            across = (x2 - x1) * (y - y1) / (y2 - y1) + x1
        held[start : start + 2048] = np.count_nonzero(straddles & (x < across), axis=1) % 2 == 1
    return held


def boundary_crossing(a: Point, b: Point, edges: Floats, *, first: bool) -> Point:
    """Where the segment ``a``-``b`` meets the rings' edges: the crossing
    nearest ``a`` when ``first``, nearest ``b`` otherwise -- so a line cut at
    a boundary ends on it rather than at its last vertex short of it."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ex, ey = edges[:, 2] - edges[:, 0], edges[:, 3] - edges[:, 1]
    sx, sy = edges[:, 0] - a[0], edges[:, 1] - a[1]
    with np.errstate(divide="ignore", invalid="ignore"):
        den = dx * ey - dy * ex
        t = (sx * ey - sy * ex) / den
        u = (sx * dy - sy * dx) / den
    hit = (np.abs(den) > 0) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
    if not hit.any():
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    at = float(t[hit].min() if first else t[hit].max())
    return (a[0] + at * dx, a[1] + at * dy)


def _distance_to_edges(points: Floats, edges: Floats) -> Floats:
    """The distance from each point to the nearest of the edges."""
    best = np.full(len(points), np.inf)
    for x1, y1, x2, y2 in edges:
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        if length2 > 0:
            t = np.clip(((points[:, 0] - x1) * dx + (points[:, 1] - y1) * dy) / length2, 0, 1)
        else:
            t = np.zeros(len(points))
        np.minimum(
            best, np.hypot(points[:, 0] - (x1 + t * dx), points[:, 1] - (y1 + t * dy)), out=best
        )
    return best


# -- the level at a point ------------------------------------------------------------


class Ground:
    """The ground level anywhere, from contours in metres.

    ``interval_m`` is the contour interval, which bounds how far the ground
    is carried past the last contour on a slope; ``reach_m`` how far across
    the slope a walk looks for a contour. Both are the generator's.
    """

    #: Directions tried through a point: every fifteen degrees, each walked
    #: both ways.
    DIRECTIONS = 12

    def __init__(
        self,
        contours: Contours,
        *,
        interval_m: float = 2.0,
        reach_m: float = 80.0,
        cell_m: float = 20.0,
    ) -> None:
        self.interval = interval_m
        self.reach = reach_m
        self.cell = cell_m
        starts: list[Point] = []
        ends: list[Point] = []
        levels: list[float] = []
        for level, points in contours:
            for start, end in pairwise(points):
                starts.append(start)
                ends.append(end)
                levels.append(level)
        head = np.array(starts, dtype=np.float64).reshape(-1, 2)
        tail = np.array(ends, dtype=np.float64).reshape(-1, 2)
        self.ax, self.ay, self.bx, self.by = head[:, 0], head[:, 1], tail[:, 0], tail[:, 1]
        self.z = np.array(levels, dtype=np.float64)
        self.count = len(levels)
        self.cells: dict[tuple[int, int], NDArray[np.int64]] = {}
        if self.count:
            self._index()
            self.bounds = (
                float(min(self.ax.min(), self.bx.min())),
                float(min(self.ay.min(), self.by.min())),
                float(max(self.ax.max(), self.bx.max())),
                float(max(self.ay.max(), self.by.max())),
            )

    @property
    def empty(self) -> bool:
        return self.count == 0

    def _index(self) -> None:
        """Each segment into every cell its box touches, most of them one."""

        def cell(values: Floats) -> NDArray[np.int64]:
            return np.floor(values / self.cell).astype(np.int64)

        self.cells = _cells(
            cell(np.minimum(self.ax, self.bx)),
            cell(np.minimum(self.ay, self.by)),
            cell(np.maximum(self.ax, self.bx)),
            cell(np.maximum(self.ay, self.by)),
        )

    def _within(self, x0: float, y0: float, x1: float, y1: float) -> NDArray[np.int64]:
        """The segments that may reach into the box, in the order they were given."""
        i0, i1 = math.floor(x0 / self.cell), math.floor(x1 / self.cell)
        j0, j1 = math.floor(y0 / self.cell), math.floor(y1 / self.cell)
        if (i1 - i0 + 1) * (j1 - j0 + 1) > 4 * len(self.cells):
            parts = [
                members for (i, j), members in self.cells.items() if i0 <= i <= i1 and j0 <= j <= j1
            ]
        else:
            parts = [
                self.cells[(i, j)]
                for i in range(i0, i1 + 1)
                for j in range(j0, j1 + 1)
                if (i, j) in self.cells
            ]
        if not parts:
            return np.zeros(0, dtype=np.int64)
        # Sorted, and a segment in two of the cells once: the order is the
        # order the contours were given in, which settles a tie as the
        # generator's stable sort does.
        found: NDArray[np.int64] = np.sort(np.concatenate(parts))
        unique: NDArray[np.int64] = found[np.concatenate([[True], found[1:] != found[:-1]])]
        return unique

    def _covers_all(self, x: float, y: float, radius: float) -> bool:
        x0, y0, x1, y1 = self.bounds
        return x - radius <= x0 and y - radius <= y0 and x + radius >= x1 and y + radius >= y1

    def _nearest(self, x: float, y: float) -> tuple[float, float, Point]:
        """The nearest point of any contour: its level, its distance, where it is."""
        radius = self.cell
        while True:
            found = self._within(x - radius, y - radius, x + radius, y + radius)
            everything = self._covers_all(x, y, radius)
            if len(found):
                ax, ay = self.ax[found], self.ay[found]
                dx, dy = self.bx[found] - ax, self.by[found] - ay
                length2 = dx * dx + dy * dy
                with np.errstate(divide="ignore", invalid="ignore"):
                    t = np.where(
                        length2 > 0, np.clip(((x - ax) * dx + (y - ay) * dy) / length2, 0, 1), 0.0
                    )
                qx, qy = ax + t * dx, ay + t * dy
                d = np.hypot(x - qx, y - qy)
                k = int(np.argmin(d))
                if d[k] <= radius or everything:
                    return float(self.z[found[k]]), float(d[k]), (float(qx[k]), float(qy[k]))
            if everything:  # pragma: no cover - an empty ground is answered before this
                return 0.0, math.inf, (x, y)
            radius *= 2.0

    def _hits(
        self, x: float, y: float, dx: Floats, dy: Floats, reach: float
    ) -> tuple[Floats, NDArray[np.int64]]:
        """Where the lines through the point along each direction cross the
        contours within ``reach``: signed distances, one row per direction,
        ``inf`` where there is no crossing, and which segment each column is."""
        found = self._within(x - reach, y - reach, x + reach, y + reach)
        ax, ay = self.ax[found][None, :], self.ay[found][None, :]
        ex, ey = self.bx[found][None, :] - ax, self.by[found][None, :] - ay
        sx, sy = ax - x, ay - y
        with np.errstate(divide="ignore", invalid="ignore"):
            den = dx[:, None] * ey - dy[:, None] * ex
            t = (sx * ey - sy * ex) / den
            u = (sx * dy[:, None] - sy * dx[:, None]) / den
        ok = (np.abs(den) >= 1e-12) & (u >= 0) & (u <= 1) & (np.abs(t) <= reach)
        return np.where(ok, t, np.inf), found

    def _across(self, x: float, y: float, reach: float) -> tuple[float, float] | None:
        """The level from the steepest pair of different levels either side,
        and the span between them; ``None`` when no direction has one."""
        angles = np.pi * np.arange(self.DIRECTIONS) / self.DIRECTIONS
        t, found = self._hits(x, y, np.cos(angles), np.sin(angles), reach)
        if not len(found):
            return None
        ahead = np.where((t > 0.02) & np.isfinite(t), t, np.inf)
        behind = np.where((t < -0.02) & np.isfinite(t), -t, np.inf)
        rows = np.arange(self.DIRECTIONS)
        fi, bi = np.argmin(ahead, axis=1), np.argmin(behind, axis=1)
        ft, bt = ahead[rows, fi], behind[rows, bi]
        fz, bz = self.z[found[fi]], self.z[found[bi]]
        valid = np.isfinite(ft) & np.isfinite(bt) & (fz != bz)
        if not valid.any():
            return None
        span = np.where(valid, ft + bt, np.inf)
        k = int(np.argmin(span))
        return float(bz[k] + (fz[k] - bz[k]) * bt[k] / span[k]), float(span[k])

    def at(self, point: Point) -> float | None:
        """The level at the point, or ``None`` when there are no contours at all."""
        if self.empty:
            return None
        x, y = float(point[0]), float(point[1])
        level, distance, (qx, qy) = self._nearest(x, y)
        if distance < 0.05:
            return level
        # Nearest first: a pair found within ``reach`` whose span is no longer
        # than ``reach`` cannot be beaten by any direction that needed to look
        # further, so the walk only widens when it has to.
        reach = min(10.0, self.reach)
        while True:
            best = self._across(x, y, reach)
            if best is not None and (best[1] <= reach or reach >= self.reach):
                return best[0]
            if reach >= self.reach:
                break
            reach = min(reach * 2.0, self.reach)

        # No two levels bracket the point: it is past the last contour on a
        # slope, or one level wraps it (a knoll inside a closed loop, a gully
        # in a bend). The ground is read by walking to the nearest contour and
        # on through it to the next level, and carrying that slope back across
        # the point -- at most one interval, since no further line was crossed.
        dx, dy = (qx - x) / distance, (qy - y) / distance
        t, found = self._hits(x, y, np.array([dx]), np.array([dy]), self.reach * 3.0)
        ahead = t[0]
        valid = np.flatnonzero(np.isfinite(ahead) & (ahead > 0.02))
        order = valid[np.argsort(ahead[valid], kind="stable")]
        levels, along = self.z[found[order]], ahead[order]
        first = (float(levels[0]), float(along[0])) if len(order) else (level, distance)
        other = np.flatnonzero(levels != first[0])
        if not len(other):
            return first[0]
        second = (float(levels[other[0]]), float(along[other[0]]))
        per_m = (first[0] - second[0]) / max(0.1, second[1] - first[1])
        return first[0] + math.copysign(min(self.interval, abs(per_m) * first[1]), per_m)


# -- the lines a mesh is made of ------------------------------------------------------

#: How many level-line vertices a terrain mesh is allowed. Archicad
#: triangulates between every one of them; the figure is the one the model
#: has been run with since D85, now spent where the site is.
MESH_POINTS = 12_000

#: Within this far of the site's boundary every contour is kept, at the finest
#: tolerance.
NEAR_M = 100.0

#: Past this far, the plans keep fewer contours still.
FAR_M = 250.0

#: The finest simplification: the steps of the grid the contours were traced
#: from, not the ground's shape.
BASE_TOLERANCE_M = 0.1

#: The coarsest it gets, however far out.
MAX_TOLERANCE_M = 6.0


@dataclass(frozen=True)
class Plan:
    """How much of the contours a mesh keeps, and how exactly."""

    grow: float
    """How fast the tolerance grows past ``NEAR_M``, metres per metre."""
    mid: int = 1
    """Which contours are kept from ``NEAR_M`` to ``FAR_M``: every one, every
    second, every fifth -- a multiple of the interval."""
    far: int = 1
    """Which are kept past ``FAR_M``."""
    base: float = BASE_TOLERANCE_M
    """The tolerance near the site."""


#: The plans, finest first; the first that fits the budget is used. Far
#: contours go before the tolerance grows, because a coarse line among many
#: close ones crosses them. The last three give way at the site itself, which
#: only a kilometre of cliff would ask of them.
PLANS: tuple[Plan, ...] = (
    Plan(0.005),
    Plan(0.005, 1, 2),
    Plan(0.01, 2, 5),
    Plan(0.02, 2, 5),
    Plan(0.02, 5, 10),
    Plan(0.04, 5, 10),
    Plan(0.08, 10, 20),
    Plan(0.16, 10, 20),
    Plan(0.16, 10, 20, base=0.25),
    Plan(0.16, 10, 20, base=0.5),
    Plan(0.16, 10, 20, base=1.0),
)


def simplify(points: Floats, tolerance: Floats) -> NDArray[np.int64]:
    """Douglas-Peucker with a tolerance of its own at every vertex: which
    vertices to keep, the two ends always among them.

    A vertex is kept when leaving it out would move the line by more than its
    own tolerance, so a contour running from the site to the edge of the model
    is exact at one end and coarse at the other.
    """
    n = len(points)
    if n < 3:
        return np.arange(n, dtype=np.int64)
    tolerance = np.maximum(tolerance, 1e-6)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        a, b = points[i], points[j]
        between = points[i + 1 : j]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            off = np.hypot(between[:, 0] - a[0], between[:, 1] - a[1])
        else:
            off = np.abs(dx * (between[:, 1] - a[1]) - dy * (between[:, 0] - a[0])) / length
        ratio = off / tolerance[i + 1 : j]
        k = int(np.argmax(ratio))
        if ratio[k] > 1.0:
            k += i + 1
            keep[k] = True
            stack.append((i, k))
            stack.append((k, j))
    return np.flatnonzero(keep).astype(np.int64)


def _cells(
    x0: NDArray[np.int64], y0: NDArray[np.int64], x1: NDArray[np.int64], y1: NDArray[np.int64]
) -> dict[tuple[int, int], NDArray[np.int64]]:
    """Which items touch each cell, from each item's range of cells: most
    items touch one, and those are grouped without a loop."""
    gathered: dict[tuple[int, int], list[NDArray[np.int64]]] = {}
    single = (x0 == x1) & (y0 == y1)
    which = np.flatnonzero(single)
    if len(which):
        keys = np.stack([x0[which], y0[which]], axis=1)
        unique, inverse = np.unique(keys, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        order = np.argsort(inverse, kind="stable")
        breaks = np.flatnonzero(np.diff(inverse[order])) + 1
        for key, members in zip(unique, np.split(which[order], breaks), strict=True):
            gathered.setdefault((int(key[0]), int(key[1])), []).append(members)
    for item in np.flatnonzero(~single):
        for i in range(int(x0[item]), int(x1[item]) + 1):
            for j in range(int(y0[item]), int(y1[item]) + 1):
                gathered.setdefault((i, j), []).append(np.array([item], dtype=np.int64))
    return {key: np.concatenate(parts) for key, parts in gathered.items()}


#: Cell coordinates packed into one integer: plenty for metres around a site.
_STRIDE = 1 << 32


def _membership(
    x0: NDArray[np.int64], y0: NDArray[np.int64], x1: NDArray[np.int64], y1: NDArray[np.int64]
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Every cell each item's range of cells covers, as packed cell keys and
    the item under each, sorted by key -- a grid index in two flat arrays."""
    width, count = x1 - x0 + 1, (x1 - x0 + 1) * (y1 - y0 + 1)
    items = np.repeat(np.arange(len(x0), dtype=np.int64), count)
    step = np.arange(len(items), dtype=np.int64) - np.repeat(np.cumsum(count) - count, count)
    across = np.repeat(width, count)
    keys = (np.repeat(x0, count) + step % across) * _STRIDE + np.repeat(y0, count) + step // across
    order = np.argsort(keys, kind="stable")
    return keys[order], items[order]


def crossings(
    pieces: Sequence[Floats], cell: float = 20.0
) -> list[tuple[int, int, int, int, Point]]:
    """Every proper crossing between segments of the pieces, a piece's own
    included: ``(piece, segment, other piece, other segment, where)``.

    Two lines that touch, or a line's neighbouring segments meeting at their
    shared vertex, do not cross. Every pair of segments sharing a cell of the
    grid is tested, all at once; a pair sharing several cells is tested once.
    """
    rows: list[Floats] = []
    owners: list[NDArray[np.int64]] = []
    orders: list[NDArray[np.int64]] = []
    for k, piece in enumerate(pieces):
        if len(piece) >= 2:
            rows.append(np.hstack([piece[:-1], piece[1:]]))
            owners.append(np.full(len(piece) - 1, k, dtype=np.int64))
            orders.append(np.arange(len(piece) - 1, dtype=np.int64))
    if not rows:
        return []
    seg = np.vstack(rows)
    owner = np.concatenate(owners)
    order = np.concatenate(orders)

    def at(values: Floats) -> NDArray[np.int64]:
        return np.floor(values / cell).astype(np.int64)

    keys, items = _membership(
        at(np.minimum(seg[:, 0], seg[:, 2])),
        at(np.minimum(seg[:, 1], seg[:, 3])),
        at(np.maximum(seg[:, 0], seg[:, 2])),
        at(np.maximum(seg[:, 1], seg[:, 3])),
    )
    # Every pair within a cell: each entry against those after it in its cell.
    starts = np.flatnonzero(np.concatenate([[True], keys[1:] != keys[:-1]]))
    sizes = np.diff(np.concatenate([starts, [len(keys)]]))
    position = np.arange(len(keys), dtype=np.int64)
    partners = np.repeat(starts + sizes, sizes) - position - 1
    left = np.repeat(position, partners)
    right = (
        left
        + 1
        + np.arange(int(partners.sum()), dtype=np.int64)
        - np.repeat(np.cumsum(partners) - partners, partners)
    )
    a, b, here = items[left], items[right], keys[left]
    # A pair sharing several cells is tested in one: the cell holding the
    # corner of the box the two share. A pair whose boxes do not overlap
    # cannot cross, and has no such cell.
    x0 = np.maximum(np.minimum(seg[a, 0], seg[a, 2]), np.minimum(seg[b, 0], seg[b, 2]))
    y0 = np.maximum(np.minimum(seg[a, 1], seg[a, 3]), np.minimum(seg[b, 1], seg[b, 3]))
    once = at(x0) * _STRIDE + at(y0) == here
    neighbours = (owner[a] == owner[b]) & (np.abs(order[a] - order[b]) <= 1)
    wanted = once & ~neighbours & (a != b)
    a, b = a[wanted], b[wanted]

    def side(o: NDArray[np.int64], qx: Floats, qy: Floats) -> Floats:
        """Which side of segment ``o`` the points are on."""
        ox, oy, px, py = seg[o, 0], seg[o, 1], seg[o, 2], seg[o, 3]
        return np.asarray((px - ox) * (qy - oy) - (py - oy) * (qx - ox), dtype=np.float64)

    o1, o2 = side(a, seg[b, 0], seg[b, 1]), side(a, seg[b, 2], seg[b, 3])
    o3, o4 = side(b, seg[a, 0], seg[a, 1]), side(b, seg[a, 2], seg[a, 3])
    proper = (o1 * o2 < 0) & (o3 * o4 < 0)
    a, b, o1, o2 = a[proper], b[proper], o1[proper], o2[proper]
    # Along ``b``, as far as ``a``'s line cuts it.
    share = o1 / (o1 - o2)
    x = seg[b, 0] + share * (seg[b, 2] - seg[b, 0])
    y = seg[b, 1] + share * (seg[b, 3] - seg[b, 1])
    return [
        (int(owner[i]), int(order[i]), int(owner[j]), int(order[j]), (float(px), float(py)))
        for i, j, px, py in zip(a, b, x, y, strict=True)
    ]


@dataclass(frozen=True)
class MeshLines:
    """The level lines for a terrain mesh, and how they were arrived at."""

    lines: tuple[tuple[float, tuple[Point, ...]], ...]
    vertices: int
    contours: int
    """How many contour lines went in."""
    plan: Plan
    """The plan used, one of ``PLANS``."""
    interval_m: float
    kept_clear: int = 0
    """Lines simplified again, less, because the first pass made them cross
    a neighbour."""

    def describe(self) -> str:
        """``1,480 level lines, 11,902 vertices: every 1 m contour within 100 m
        of the site, true to 0.1 m; every 2 m contour to 250 m and every 5 m
        beyond, the tolerance growing 2 cm a metre past 100 m``."""
        grow, mid, far = self.plan.grow, self.plan.mid, self.plan.far
        step = self.interval_m
        text = (
            f"{len(self.lines):,} level lines, {self.vertices:,} vertices: every {step:g} m "
            f"contour within {NEAR_M:g} m of the site, true to {self.plan.base:g} m; "
        )
        if mid == far == 1:
            text += "every contour beyond"
        elif mid == far:
            text += f"every {mid * step:g} m beyond"
        else:
            text += (
                f"every {mid * step:g} m contour to {FAR_M:g} m and every {far * step:g} m beyond"
            )
        text += f", the tolerance growing {grow * 100:g} cm a metre past {NEAR_M:g} m"
        if self.kept_clear:
            text += f"; {self.kept_clear} lines kept clear of their neighbours where it is steep"
        return text


def _pieces(
    level: float, points: Floats, distance: Floats, gate: NDArray[np.bool_]
) -> list[tuple[float, Floats, Floats]]:
    """The runs of consecutive vertices ``gate`` lets through."""
    runs: list[tuple[float, Floats, Floats]] = []
    if not gate.any():
        return runs
    edges = np.flatnonzero(np.diff(np.concatenate([[0], gate.astype(np.int8), [0]])))
    for start, stop in zip(edges[0::2], edges[1::2], strict=True):
        if stop - start >= 2:
            runs.append((level, points[start:stop], distance[start:stop]))
    return runs


#: How far inside the outline a line carried to it stops: a vertex a hair
#: outside a mesh's polygon, which rounding can make of one on its edge, is
#: not a level point Archicad has been asked to take.
EDGE_INSET_M = 0.05


def _short_of(edge: Point, inside: Floats) -> Floats:
    """``edge``, moved ``EDGE_INSET_M`` towards the vertex inside it."""
    x, y = edge
    dx, dy = float(inside[0]) - x, float(inside[1]) - y
    length = math.hypot(dx, dy)
    share = min(0.5, EDGE_INSET_M / length) if length > 0 else 0.0
    return np.array([x + dx * share, y + dy * share])


def _to_the_edge(
    level: float, points: Floats, distance: Floats, held: NDArray[np.bool_], outline: Floats
) -> list[tuple[float, Floats, Floats]]:
    """The runs of a line the mesh's outline holds, each carried on to where
    the line crosses the outline, less a few centimetres: at the state's
    vertex spacing the last vertex inside can be twenty metres short of it."""
    runs: list[tuple[float, Floats, Floats]] = []
    if not held.any():
        return runs
    bounds = np.flatnonzero(np.diff(np.concatenate([[0], held.astype(np.int8), [0]])))
    for start, stop in zip(bounds[0::2], bounds[1::2], strict=True):
        run, far_from = points[start:stop], distance[start:stop]
        if start > 0:
            edge = boundary_crossing(
                tuple(points[start - 1]), tuple(points[start]), outline, first=False
            )
            run = np.vstack([_short_of(edge, points[start]), run])
            far_from = np.concatenate([far_from[:1], far_from])
        if stop < len(points):
            edge = boundary_crossing(
                tuple(points[stop - 1]), tuple(points[stop]), outline, first=True
            )
            run = np.vstack([run, _short_of(edge, points[stop - 1])])
            far_from = np.concatenate([far_from, far_from[-1:]])
        if len(run) >= 2:
            runs.append((level, run, far_from))
    return runs


def _multiple(level: float, interval: float, every: int) -> bool:
    step = interval * every
    return abs(level / step - round(level / step)) < 1e-6


def _gated(
    lines: Sequence[tuple[float, Floats, Floats]], plan: Plan, interval: float
) -> list[tuple[float, Floats, Floats]]:
    """The pieces of the lines one plan keeps."""
    kept: list[tuple[float, Floats, Floats]] = []
    for level, points, distance in lines:
        keep_mid = _multiple(level, interval, plan.mid)
        keep_far = _multiple(level, interval, plan.far)
        gate = (distance <= NEAR_M) | ((distance <= FAR_M) & keep_mid) | keep_far
        kept.extend(_pieces(level, points, distance, gate))
    return kept


def _tolerance(distance: Floats, plan: Plan) -> Floats:
    """How far a vertex this far from the site may move."""
    return np.minimum(
        plan.base + plan.grow * np.maximum(0.0, distance - NEAR_M),
        max(MAX_TOLERANCE_M, plan.base),
    )


#: How fine a span is simplified before a crossing there is taken to be the
#: survey's own: two lines that still cross with neither moved a centimetre
#: crossed as published.
SETTLED_M = 0.01


def _kept_clear(
    pieces: Sequence[Floats],
    tolerances: Sequence[Floats],
    kept: list[NDArray[np.int64]],
    rounds: int = 8,
    ceiling: int | None = None,
) -> int | None:
    """Where simplifying made two lines cross, simplify the two spans that
    cross again at half the tolerance, and again. Returns how many lines it
    took -- or ``None`` as soon as the lines hold more than ``ceiling``
    vertices, because a plan that crosses that much is too coarse for its
    contours and the next one will do better for less.

    The spans only: the rest of each line is left as it was, so a crossing
    costs a few vertices rather than a line. A span still crossing once its
    tolerance is under a centimetre crosses as published -- the City of
    Sydney's contours do, by millimetres, where the ground drops at a wall --
    and is left: it is the survey's, and a mesh cannot mend it.
    """
    tolerance = [t.copy() for t in tolerances]
    mended: set[int] = set()
    for _ in range(rounds):
        spans: dict[int, set[tuple[int, int]]] = {}
        for piece, segment, other, other_segment, _where in crossings(
            [points[k] for points, k in zip(pieces, kept, strict=True)]
        ):
            for k, s in ((piece, segment), (other, other_segment)):
                i, j = int(kept[k][s]), int(kept[k][s + 1])
                if j - i >= 2 and float(tolerance[k][i + 1 : j].max()) >= SETTLED_M:
                    spans.setdefault(k, set()).add((i, j))
        if not spans:
            break
        for k, wanted in spans.items():
            mended.add(k)
            keep = np.zeros(len(pieces[k]), dtype=bool)
            keep[kept[k]] = True
            for i, j in wanted:
                tolerance[k][i : j + 1] /= 2.0
                keep[i + simplify(pieces[k][i : j + 1], tolerance[k][i : j + 1])] = True
            kept[k] = np.flatnonzero(keep).astype(np.int64)
        if ceiling is not None and sum(len(k) for k in kept) > ceiling:
            return None
    return len(mended)


def mesh_lines(
    contours: Contours,
    *,
    focus: Sequence[Sequence[Point]],
    within: Sequence[Point] | None = None,
    budget: int = MESH_POINTS,
    interval_m: float = 1.0,
) -> MeshLines:
    """The contours as a terrain mesh's level lines, fine at the site and
    coarse at the edge, in no more than ``budget`` vertices where any plan
    fits.

    ``focus`` is the site's boundary: distance is measured from it, and
    nothing inside it is thinned. ``within`` is the mesh's outline: the lines
    are cut to it before they are simplified, so each ends at the edge rather
    than at whichever vertex the simplification last kept short of it.
    """
    used = [(float(level), points) for level, points in contours if len(points) >= 2]
    prepared: list[tuple[float, Floats, Floats]] = []
    if used:
        # Every vertex at once: its distance from the site, nothing inside the
        # site further than nothing, and whether the mesh's outline holds it.
        xy = np.array([p for _, points in used for p in points], dtype=np.float64).reshape(-1, 2)
        focus_edges = edges_of(focus)
        if len(focus_edges):
            distance = _distance_to_edges(xy, focus_edges)
            distance[points_in_rings(xy, focus_edges)] = 0.0
        else:
            distance = np.hypot(xy[:, 0], xy[:, 1])
        outline = edges_of([within]) if within else np.zeros((0, 4))
        held = np.ones(len(xy), dtype=bool)
        if within:
            # On the edge is outside: the line is carried to it and stops short.
            held = points_in_rings(xy, outline) & (
                _distance_to_edges(xy, outline) > EDGE_INSET_M / 2.0
            )
        at = 0
        for level, points in used:
            end = at + len(points)
            prepared.extend(
                _to_the_edge(level, xy[at:end], distance[at:end], held[at:end], outline)
            )
            at = end

    # The first plan whose simplification fits, with the lines it made cross
    # simplified again; should that cost the budget, the next plan.
    chosen = PLANS[-1]
    gated: list[tuple[float, Floats, Floats]] = []
    kept: list[NDArray[np.int64]] = []
    cleared: int | None = 0
    for plan in PLANS:
        chosen = plan
        last = plan == PLANS[-1]
        gated = _gated(prepared, plan, interval_m)
        tolerances = [_tolerance(distance, plan) for _, _, distance in gated]
        kept = [
            simplify(points, tolerance)
            for (_, points, _), tolerance in zip(gated, tolerances, strict=True)
        ]
        if sum(len(k) for k in kept) > budget and not last:
            continue
        cleared = _kept_clear(
            [points for _, points, _ in gated],
            tolerances,
            kept,
            ceiling=None if last else budget,
        )
        if cleared is not None:
            break

    lines = tuple(
        (level, tuple((float(x), float(y)) for x, y in points[k]))
        for (level, points, _), k in zip(gated, kept, strict=True)
    )
    return MeshLines(
        lines=lines,
        vertices=sum(len(points) for _, points in lines),
        contours=len(used),
        plan=chosen,
        interval_m=interval_m,
        kept_clear=cleared or 0,
    )
