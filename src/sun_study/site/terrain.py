"""Contours: whose, and where each set stops.

The state's contours are at 2 m. A few councils fly their own survey and
publish finer contours under an open licence -- the City of Sydney published
1 m contours from its 2020 aerial survey -- and where one covers the ground it
is used instead, with the sheet's legend and credit saying whose they are.
The same shape of registry as the tree inventories: a layer, the box it
covers, the field with the level, the interval, and the local government area
it stops at.

Two rules, because a sheet and a model want different things at a boundary:

* **A sheet** takes a council's set only where it covers at least 85% of
  the map field, and the state's everywhere otherwise. A set that stops at
  the council's boundary part-way across the sheet would leave the rest of it
  blank, which is worse than 2 m contours everywhere, and one sheet drawn to
  two intervals would need two legends. That is the ``au-site-analysis``
  generator's rule (``fetchContours``), with the council's own boundary added
  to its test of what "covers" means -- see ``sheet_contours``.
* **A model** takes both, cut at the boundary: the council's lines inside the
  council's area and the state's outside it, the area read from the state's
  own register of local government areas. A kilometre square around a site in
  Glebe or Redfern crosses into the next council more often than not, and the
  sheet's rule would then throw the council's lines away exactly where the
  model needs them -- around the site. Should the boundary not answer, the
  model falls back to the sheet's rule.

The model's fetch also asks the council's server to generalise its lines to a
tenth of a metre before sending them. A kilometre square of the City of
Sydney's contours is 440,000 vertices as published -- a vertex every quarter
of a metre, most of them the staircase of the grid they were traced from --
and 170,000 generalised; the mesh keeps far fewer than either (``ground``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from sun_study.site import nsw, sources
from sun_study.site.arcgis import paths_of, query_by_extent, rings_of
from sun_study.site.geo import Extent, Point, clip_ring, ring_area
from sun_study.site.ground import boundary_crossing, edges_of, points_in_rings

__all__ = [
    "COUNCIL_CONTOURS",
    "COVERAGE",
    "STATE_CONTOURS",
    "ContourSource",
    "councils_for",
    "coverage",
    "cut",
    "described",
    "model_contours",
    "share_inside",
    "sheet_contours",
]

Log = Callable[[str], None]


@dataclass(frozen=True)
class ContourSource:
    """One publisher's contours: where they are and what they are."""

    slug: str
    """The ``sources`` entry that is credited for them."""
    name: str
    """What the run's log and the documentation call them."""
    legend: str
    """Who drew them, as the sheet's legend says it."""
    layer: str
    field: str
    """The field holding the level, metres AHD."""
    interval_m: float
    bbox: tuple[float, float, float, float] | None = None
    """``(west, south, east, north)``: a site outside it never asks."""
    lga: str | None = None
    """The local government area, as the state's register names it, that the
    lines are the council's inside of."""


STATE_CONTOURS = ContourSource(
    slug=sources.SPATIAL,
    name="NSW Spatial Services 2 m contours",
    legend="NSW SPATIAL SERVICES",
    layer=f"{nsw.ELEVATION}/2",
    field="elevation",
    interval_m=2.0,
)

COUNCIL_CONTOURS: tuple[ContourSource, ...] = (
    ContourSource(
        slug=sources.CITY_OF_SYDNEY,
        name="City of Sydney 1 m contours, 2020 aerial survey",
        legend="CITY OF SYDNEY 2020 SURVEY",
        layer=(
            "https://services1.arcgis.com/cNVyNtjGVZybOQWZ/arcgis/rest/services/"
            "Terrain_Contours/FeatureServer/0"
        ),
        field="Contour",
        interval_m=1.0,
        bbox=(151.17, -33.93, 151.24, -33.85),
        lga="SYDNEY",
    ),
)

#: How much of a sheet a council's lines must reach across to be used on it.
COVERAGE = 0.85

#: How far the council's server may generalise the model's lines, metres.
MODEL_GENERALISE_M = 0.1

#: Degrees of latitude per metre, near enough, for a generalisation the
#: server takes in the output's units.
_DEGREES_PER_M = 1.0 / 111_320.0


def councils_for(extent: Extent) -> tuple[ContourSource, ...]:
    """The councils whose box the extent touches, in the registry's order."""
    south, west, north, east = extent.lonlat_bbox()
    return tuple(
        source
        for source in COUNCIL_CONTOURS
        if source.bbox is not None
        and west <= source.bbox[2]
        and east >= source.bbox[0]
        and south <= source.bbox[3]
        and north >= source.bbox[1]
    )


def _fetch(
    source: ContourSource, extent: Extent, generalise_m: float | None = None
) -> list[nsw.Contour]:
    extra = (
        {"maxAllowableOffset": f"{generalise_m * _DEGREES_PER_M:.12f}"} if generalise_m else None
    )
    collection = query_by_extent(source.layer, extent, source.field, extra=extra)
    found: list[nsw.Contour] = []
    for feature in collection["features"]:
        try:
            level = float(feature["properties"].get(source.field))
        except (TypeError, ValueError):
            continue
        for path in paths_of(feature.get("geometry")):
            if len(path) >= 2:
                found.append(nsw.Contour(level, tuple(path), source.slug))
    return found


def coverage(lines: Iterable[nsw.Contour], extent: Extent) -> float:
    """How much of the extent the lines' own box reaches across, 0 to 1.

    The generator's measure, and deliberately a coarse one: it asks whether
    the set stops short of the sheet, not how densely it fills it -- a flat
    park has few contours and is still covered.
    """
    south, west, north, east = extent.lonlat_bbox()
    xs = [lon for line in lines for lon, _ in line.coords]
    ys = [lat for line in lines for _, lat in line.coords] if xs else []
    if not xs:
        return 0.0
    across = (min(max(xs), east) - max(min(xs), west)) / (east - west)
    up = (min(max(ys), north) - max(min(ys), south)) / (north - south)
    return max(0.0, across) * max(0.0, up)


def _say(log: Log | None, line: str) -> None:
    if log:
        log(line)


def sheet_contours(extent: Extent, *, log: Log | None = None) -> list[nsw.Contour]:
    """A sheet's contours: a council's where they cover the sheet, the
    state's otherwise. Raises only when the state's fetch does.

    Covered twice over: the lines reach across the sheet (the generator's
    test) *and* the council's area holds the sheet. The first alone is fooled
    by a boundary down the middle of the sheet -- King Street, Newtown, is one
    -- where the council's lines on one side reach every edge between them
    and the other side is another council's: 100% by the lines' box, 36% of
    the sheet in fact, and two thirds of it would have been drawn blank.
    """
    for council in councils_for(extent):
        try:
            lines = _fetch(council, extent)
        except Exception as error:
            _say(log, f"  WARN {council.name} failed: {error}")
            continue
        share = coverage(lines, extent)
        if council.lga and share >= COVERAGE:
            try:
                rings = _area(extent, council.lga)
            except Exception as error:
                _say(log, f"  WARN the local government areas failed: {error}")
            else:
                share = min(share, share_inside(rings, extent)) if rings else share
        if len(lines) >= 3 and share >= COVERAGE:
            _say(log, f"  contours: {council.name} ({len(lines)} lines)")
            return lines
        _say(log, f"  {council.name} cover {share:.0%} of the sheet -- the state's instead")
    return nsw.contours(extent)


def model_contours(
    extent: Extent, *, log: Log | None = None, generalise_m: float = MODEL_GENERALISE_M
) -> list[nsw.Contour]:
    """A model's contours: a council's inside its area, the state's outside.

    Falls back to the state's alone when no council answers for the square,
    and to the sheet's rule when the council does but its boundary cannot be
    read.
    """
    for council in councils_for(extent):
        try:
            theirs = _fetch(council, extent, generalise_m)
        except Exception as error:
            _say(log, f"  WARN {council.name} failed: {error}")
            continue
        if not theirs:
            continue
        try:
            rings = _area(extent, council.lga) if council.lga else []
        except Exception as error:
            _say(log, f"  WARN the local government areas failed: {error}")
            rings = []
        if not rings:
            share = coverage(theirs, extent)
            if len(theirs) >= 3 and share >= COVERAGE:
                _say(log, f"  contours: {council.name} ({len(theirs)} lines)")
                return theirs
            _say(log, f"  {council.name} cover {share:.0%} of the square -- the state's instead")
            continue
        share = share_inside(rings, extent)
        if share >= 0.999:
            _say(log, f"  contours: {council.name} ({len(theirs)} lines)")
            return theirs
        if share <= 0.001:
            continue
        box = _box(extent, margin=0.1)
        try:
            state = nsw.contours(extent)
        except Exception as error:
            _say(log, f"  WARN the state's contours failed: {error}; the council's alone")
            return cut(theirs, rings, keep_inside=True, box=box)
        inside = cut(theirs, rings, keep_inside=True, box=box)
        outside = cut(state, rings, keep_inside=False, box=box)
        _say(
            log,
            f"  contours: {council.name} inside {council.lga} ({share:.0%} of the square, "
            f"{len(inside)} lines), the state's 2 m outside it ({len(outside)} lines)",
        )
        return inside + outside
    return nsw.contours(extent)


def _area(extent: Extent, lga: str) -> list[list[Point]]:
    """The named local government area's rings, as far as the extent needs them.

    Clipped to the extent and a tenth of it again each way: the register sends
    the whole area, three thousand vertices for the City of Sydney, and every
    line's every vertex is tested against what is kept.
    """
    west, south, east, north = _box(extent, margin=0.1)
    clipped = (
        clip_ring(ring, west, south, east, north)
        for feature in nsw.local_government_areas(extent)["features"]
        if str(feature["properties"].get("lganame") or "").strip().upper() == lga.upper()
        for ring in rings_of(feature.get("geometry"))
    )
    return [ring for ring in clipped if ring]


def _box(extent: Extent, margin: float = 0.0) -> tuple[float, float, float, float]:
    """``(west, south, east, north)``, widened by ``margin`` of its size each way."""
    south, west, north, east = extent.lonlat_bbox()
    dx, dy = (east - west) * margin, (north - south) * margin
    return west - dx, south - dy, east + dx, north + dy


def share_inside(rings: Sequence[Sequence[Point]], extent: Extent) -> float:
    """How much of the extent lies inside the rings, 0 to 1.

    Clipped ring by ring and summed signed, so a hole takes its area back off:
    the register's outer rings run one way and its holes the other.
    """
    west, south, east, north = _box(extent)
    whole = (east - west) * (north - south)
    if whole <= 0:
        return 0.0
    area = sum(ring_area(clip_ring(ring, west, south, east, north)) for ring in rings)
    return min(1.0, abs(area) / whole)


#: The longest step a line is cut in before it is tested against a boundary,
#: degrees: about five metres. A vertex is inside or outside, and a segment
#: longer than this could cross into an area and out again between two.
_STEP = 5.0 / 111_320.0


def _densified(coords: Sequence[Point]) -> tuple[Point, ...]:
    """The line with a vertex at least every ``_STEP``."""
    xy = np.array(coords, dtype=np.float64)
    pieces = np.maximum(1, np.ceil(np.hypot(*np.diff(xy, axis=0).T) / _STEP)).astype(int)
    if pieces.max() == 1:
        return tuple(coords)
    out: list[Point] = []
    for (ax, ay), (bx, by), n in zip(xy[:-1], xy[1:], pieces, strict=True):
        out.extend((ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n))
    out.append((float(xy[-1, 0]), float(xy[-1, 1])))
    return tuple((float(x), float(y)) for x, y in out)


def cut(
    lines: Sequence[nsw.Contour],
    rings: Sequence[Sequence[Point]],
    *,
    keep_inside: bool,
    box: tuple[float, float, float, float] | None = None,
) -> list[nsw.Contour]:
    """The parts of the lines inside the rings, or outside them, and inside
    ``box`` -- ``(west, south, east, north)`` -- when one is given, each
    ending on the boundary where it crosses it rather than at its last vertex
    short of it.

    The state's lines are sparse, so each is given a vertex every five metres
    first: a long segment could otherwise run through a corner of the
    council's area with both its ends outside it. The box is where the rings
    were clipped to, so nothing beyond it is taken for outside the council.
    """
    if not lines:
        return []
    edges = edges_of(rings)
    lines = [nsw.Contour(line.elevation, _densified(line.coords), line.source) for line in lines]
    everything = np.array([p for line in lines for p in line.coords], dtype=np.float64)
    everything = everything.reshape(-1, 2)
    wanted = points_in_rings(everything, edges) == keep_inside
    frame = np.zeros((0, 4))
    if box is not None:
        west, south, east, north = box
        frame = edges_of([[(west, south), (east, south), (east, north), (west, north)]])
        in_box = (
            (everything[:, 0] >= west)
            & (everything[:, 0] <= east)
            & (everything[:, 1] >= south)
            & (everything[:, 1] <= north)
        )
        wanted &= in_box
    else:
        in_box = np.ones(len(everything), dtype=bool)

    def edge(a: Point, b: Point, *, leaving: bool, outside_box: bool) -> Point:
        """Where the line crosses whichever boundary it crossed."""
        return boundary_crossing(a, b, frame if outside_box else edges, first=leaving)

    kept: list[nsw.Contour] = []
    at = 0
    for line in lines:
        flags, boxed = wanted[at : at + len(line.coords)], in_box[at : at + len(line.coords)]
        at += len(line.coords)
        run: list[Point] = []
        for i, point in enumerate(line.coords):
            if flags[i]:
                if not run and i > 0:
                    run.append(
                        edge(line.coords[i - 1], point, leaving=False, outside_box=not boxed[i - 1])
                    )
                run.append(point)
            elif run:
                run.append(edge(line.coords[i - 1], point, leaving=True, outside_box=not boxed[i]))
                if len(run) >= 2:
                    kept.append(nsw.Contour(line.elevation, tuple(run), line.source))
                run = []
        if len(run) >= 2:
            kept.append(nsw.Contour(line.elevation, tuple(run), line.source))
    return kept


def described(lines: Iterable[nsw.Contour]) -> tuple[float, str, tuple[str, ...]] | None:
    """The finest interval among the lines, who drew them as the legend says
    it, and the slugs to credit -- or ``None`` when there are none."""
    by_slug = {source.slug: source for source in (*COUNCIL_CONTOURS, STATE_CONTOURS)}
    seen: dict[str, ContourSource] = {}
    for line in lines:
        if line.source not in seen:
            seen[line.source] = by_slug.get(line.source, STATE_CONTOURS)
    if not seen:
        return None
    interval = min(source.interval_m for source in seen.values())
    who = " / ".join(dict.fromkeys(source.legend for source in seen.values()))
    return interval, who, tuple(seen)
