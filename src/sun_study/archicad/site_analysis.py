"""The context analysis, site analysis and development summary, drawn into
worksheets of the open project.

What the office's ``au-site-analysis`` generator prints to an A1 PDF, this
draws as native Archicad elements -- fills with the legend's own colours,
polylines and texts -- into a worksheet per sheet, at true ground scale in
the project's own coordinate frame, with a view of each at the sheet's scale
in the View Map. Everything lands on layers under the tool's prefix, so it
can be switched off or purged as a group, and a rerun clears the worksheet
before it draws.

Where the site lands
--------------------
A bundle is in longitude and latitude. The project has an origin and a north
angle -- ``GetGeoLocation`` -- so a point on the ground has one place in the
project frame: projected to the MGA grid, moved so the project origin's own
grid position is zero, then turned so true north sits where the project says
it does. The turn is the same one the sun eye views make in the other
direction (``docs/addon.md``); getting it wrong draws a plausible site facing
the wrong way, which is why ``Frame`` is tested against a hand-worked case.

A project whose location was never set -- a city preset, 11 km off -- would
put the site 11 km from the model. That is reported, and ``anchor="site"``
puts the site's centre at the project origin instead, which is the right
answer for a project that has nothing in it yet.

Why a worksheet, and what it costs
----------------------------------
The add-on's ``CreateWorksheet`` makes one and enters it in the same call, so
the run can draw into it; Tapir's own cannot (D33). ``CreateFills`` takes an
RGB directly, so the legend's colours arrive without pen matching (D82);
polylines and texts are Tapir's, and a text takes no layer, so each is moved
after it is made (D60). Nothing here is overlaid on the model: the worksheet
is a drawing of the neighbourhood, to be placed on a sheet or traced over.
"""

from __future__ import annotations

import base64
import math
import textwrap
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from pathlib import Path
from typing import Any

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.draw import (
    Pen,
    _looks_like,
    create_texts,
    ensure_layer,
    pen_table,
    place_texts,
)
from sun_study.archicad.layout import (
    MM_PER_M,
    LayoutSheet,
    _create_layout,
    _drawings_by_name,
    _walk,
    choose_master,
    layout_from_views,
    layout_sheet,
    master_layouts,
)
from sun_study.archicad.read import GeoLocation
from sun_study.archicad.series import _worksheets, clear_database, database_of
from sun_study.archicad.sun_eyes import TITLE_BLOCK_MM
from sun_study.archicad.views import (
    ModelSource,
    StoreyView,
    ensure_layer_combination,
    views_for_sources,
)
from sun_study.site import curate, marks, sources, terrain
from sun_study.site import theme as themes
from sun_study.site.arcgis import rings_of
from sun_study.site.envelope import ADG_SEPARATION, Envelope
from sun_study.site.geo import (
    Point,
    convex_hull,
    lonlat_to_mercator,
    lonlat_to_mga,
    mercator_to_lonlat,
    mga_to_lonlat,
    mga_zone,
    point_in_ring,
    polyline_length,
    ring_area,
    ring_centroid,
)
from sun_study.site.ground import Ground
from sun_study.site.imagery import toned
from sun_study.site.pipeline import (
    MAP_HEIGHT_MM,
    MAP_WIDTH_MM,
    ContextBundle,
    SiteBundle,
    SummaryBundle,
)
from sun_study.site.trees import ESTIMATED, NOMINAL, NOMINAL_CANOPY_M, Tree

__all__ = [
    "CONTEXT_WORD",
    "SITE_WORD",
    "SUMMARY_WORD",
    "Drawing",
    "Fit",
    "Frame",
    "LayoutReport",
    "Row",
    "WorksheetNotEnteredError",
    "WorksheetReport",
    "context_drawing",
    "draw_context",
    "draw_site",
    "draw_summary",
    "ensure_worksheet",
    "frame_for",
    "site_drawing",
    "summary_drawing",
    "summary_rows",
]

#: The words the three sheets are filed under, after the tool's prefix.
CONTEXT_WORD = "Context Analysis"
SITE_WORD = "Site Analysis"
SUMMARY_WORD = "Summary of Controls"

#: The View Map folder every sheet's view goes in.
FOLDER_WORD = "Site Analysis"

# Text heights, in millimetres on paper. A text keeps its paper size in any
# view, so these are what the sheet prints at whatever scale it is placed.
TITLE_MM = 3.0
LEGEND_MM = 3.0
STREET_MM = 3.0
LABEL_MM = 3.0
#: A stop or station roundel: radius, and the letter in it.
ROUNDEL_MM = 3.0
ROUNDEL_TEXT_MM = 3.0
#: The white double-headed band a street name sits in.
BAND_MM = 5.5
#: Spacing of the heritage hatch lines, on paper.
HATCH_MM = 2.5
#: Spacing of a category's texture lines, on paper: finer than the
#: heritage hatch, so a textured tint reads as a tone and not as stripes.
TEXTURE_MM = 2.0
#: The road reserve a street is drawn as on paper, by the register's function
#: hierarchy (1 a motorway, 6 a local street, 7 and beyond a lane), in metres.
RESERVE_M = {1: 30.0, 2: 24.0, 3: 20.0, 4: 16.0, 5: 12.0, 6: 10.0}
#: How far inside the map field a hole is cut, in metres on the ground.
HOLE_INSET_M = 0.3
#: How far a loop split off a pinched ring is parted from the vertex it shared.
PINCH_PART_M = 0.05
#: The prevailing winds the site sheet draws: the bearing each blows from, and its name.
WINDS = (
    (50.0, "NE SUMMER\nSEA BREEZE"),
    (150.0, "S & SE COOL\nSUMMER WIND"),
    (235.0, "W & SW\nWINTER WINDS"),
)
SMALL_MM = 3.0
#: The data credit under the map. Smaller than everything else on the sheet
#: on purpose: it is a statement of provenance, read once by whoever sends
#: the drawing out, and it must not compete with the drawing for a reader
#: who is looking at the buildings.
CREDIT_MM = 2.0
NEIGHBOUR_MM = 3.0
SUN_MM = 3.0

INK = "#111111"
SITE_RED = "#e30613"
DIMENSION_BLUE = "#2456c4"
WIND_BLUE = "#2f9fd6"
SUN_YELLOW = "#feefab"
CADASTRE_GREY = "#6f6f6f"
ROAD_GREY = "#8a8a8a"
#: The neighbouring buildings on the site sheet, filled so they read as masses.
BUILDING_GREY = "#d9d9d9"
#: The future context: what the controls would allow next door, drawn in a
#: colour nothing existing is drawn in.
FUTURE_MAGENTA = "#c2189a"
RAIL_BLACK = "#3b3b3b"
TRAM_PINK = "#d5006d"
BUS_BLUE = "#2f7fd6"
WALK_5 = "#e6007e"
WALK_10 = "#b5379b"
CONTOUR_BROWN = "#a07c3f"
NOISE_BLUE = "#3b4fd8"
TREE_GREEN = "#7dbb57"
TREE_EDGE = "#4e8c33"
TRUNK_GREEN = "#2f5e20"
HYDRANT_BLUE = "#1f78d1"
LAMP_YELLOW = "#f0c020"
POLE_GREY = "#333333"
PARKING_PLUM = "#9b5b6e"
DRIVEWAY_YELLOW = "#f5e400"
UTILITY = {"power": "#f2c200", "water": "#2f7fd6", "sewer": "#7db87d", "gas": "#e6007e"}


# -- the frame ---------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """Longitude and latitude to the project's own coordinates, in metres."""

    zone: int
    """The MGA zone everything is projected in."""
    origin: Point
    """The grid easting and northing that lands at the project origin."""
    plus_y_bearing_deg: float
    """Compass bearing of the project's +Y axis, as ``GeoLocation`` gives it."""
    convergence_deg: float = 0.0
    """Grid convergence at the origin: the grid bearing of true north.

    MGA's grid north is not true north -- they differ by about a degree at
    Sydney, more further from the zone's central meridian. The project's north
    angle is a true bearing, because the sun is worked from it, so a grid
    vector is turned by the convergence as well as by the project's angle.
    Without this a survey on the grid and a sun study would face different
    ways by that degree.
    """

    def project(self, lon: float, lat: float) -> Point:
        east, north = lonlat_to_mga(lon, lat, self.zone)
        de, dn = east - self.origin[0], north - self.origin[1]
        turn = math.radians(self.plus_y_bearing_deg + self.convergence_deg)
        return (
            de * math.cos(turn) - dn * math.sin(turn),
            de * math.sin(turn) + dn * math.cos(turn),
        )

    def unproject(self, x: float, y: float) -> tuple[float, float]:
        """Longitude and latitude of a point given in the project frame."""
        turn = math.radians(self.plus_y_bearing_deg + self.convergence_deg)
        de = x * math.cos(turn) + y * math.sin(turn)
        dn = -x * math.sin(turn) + y * math.cos(turn)
        return mga_to_lonlat(self.origin[0] + de, self.origin[1] + dn, self.zone)

    def turned_and_moved(self, delta_deg: float, shift: Point) -> Frame:
        """The frame whose projection is this one's, turned by ``delta_deg``
        anticlockwise about the origin and then moved by ``shift`` metres."""
        turn = math.radians(self.plus_y_bearing_deg + self.convergence_deg + delta_deg)
        de = shift[0] * math.cos(turn) + shift[1] * math.sin(turn)
        dn = -shift[0] * math.sin(turn) + shift[1] * math.cos(turn)
        return Frame(
            self.zone,
            (self.origin[0] - de, self.origin[1] - dn),
            self.plus_y_bearing_deg + delta_deg,
            self.convergence_deg,
        )

    def direction(self, bearing_deg: float) -> Point:
        """A unit vector along a compass bearing, in the project frame."""
        turn = math.radians(bearing_deg - self.plus_y_bearing_deg)
        return (math.sin(turn), math.cos(turn))

    def ring(self, ring: Iterable[Point]) -> list[Point]:
        return [self.project(lon, lat) for lon, lat in ring]


#: How far a drawn boundary may turn the context away from the project's
#: north before the run says so. A boundary traced by hand is out by a
#: degree or so either way; a survey placed as delivered, north up, in a
#: project whose north is turned is out by the whole of that turn -- 15
#: degrees on the Parramatta project where a context came in north up
#: under a north of 105 (23 October 2026).
FIT_TURN_NOTICE_DEG = 2.0


@dataclass(frozen=True)
class Fit:
    """How the fetched site had to move to land on the boundary drawn in the file."""

    frame: Frame
    turn_deg: float
    """Anticlockwise, from the unfitted frame."""
    shift: Point
    """Metres, in the project frame, after the turn."""
    residual_m: float
    """Mean distance from the drawn boundary's corners to the fitted lot's edge."""
    drawn_points: int

    def describe(self) -> str:
        return (
            f"turned {self.turn_deg:+.2f} deg and moved ({self.shift[0]:+.1f}, "
            f"{self.shift[1]:+.1f}) m to sit on the {self.drawn_points} boundary points "
            f"drawn in the file; residual {self.residual_m:.2f} m"
        )

    def turned_from_north(self, source: str) -> str | None:
        """What to say when this fit turned the context away from the
        project's north, or ``None`` when the turn is a drawing's tolerance.

        The fit wins over the north by design -- the drawing is where the
        model was drawn -- but silently it reads as the north being ignored,
        and the usual cause is a survey nobody turned to the project's north.
        ``source`` says which drawing: ``"on 'Site Boundary'"``.
        """
        if abs(self.turn_deg) <= FIT_TURN_NOTICE_DEG:
            return None
        return (
            f"the boundary {source} turns the context {self.turn_deg:+.1f} deg from the "
            "project's north: the context follows that drawing, not the north. If it is a "
            "survey placed as delivered, north up, turn it to the project's north, or skip "
            "the fit (--fit-layer none; in the window, Drawn boundary: ignore it)."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "zone": self.frame.zone,
            "origin": list(self.frame.origin),
            "plus_y_bearing_deg": self.frame.plus_y_bearing_deg,
            "convergence_deg": self.frame.convergence_deg,
            "turn_deg": self.turn_deg,
            "shift": list(self.shift),
            "residual_m": self.residual_m,
            "drawn_points": self.drawn_points,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fit:
        return cls(
            frame=Frame(
                int(data["zone"]),
                (float(data["origin"][0]), float(data["origin"][1])),
                float(data["plus_y_bearing_deg"]),
                float(data.get("convergence_deg", 0.0)),
            ),
            turn_deg=float(data["turn_deg"]),
            shift=(float(data["shift"][0]), float(data["shift"][1])),
            residual_m=float(data["residual_m"]),
            drawn_points=int(data.get("drawn_points", 0)),
        )


def _edge_bearing(hull: Sequence[Point]) -> float:
    """Direction of the hull's longest side, in degrees, folded to [0, 180)."""
    best, angle = -1.0, 0.0
    for a, b in zip(hull, [*hull[1:], hull[0]], strict=True):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length > best:
            best, angle = length, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
    return angle


def _turn_about_origin(points: Iterable[Point], degrees: float) -> list[Point]:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def _distance_to_ring(point: Point, ring: Sequence[Point]) -> float:
    best = math.inf
    for a, b in zip(ring, [*ring[1:], ring[0]], strict=True):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        t = (
            0.0
            if length2 == 0.0
            else max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2))
        )
        best = min(best, math.hypot(a[0] + t * dx - point[0], a[1] + t * dy - point[1]))
    return best


def fit_frame(frame: Frame, site_rings: Sequence[Sequence[Point]], drawn: Sequence[Point]) -> Fit:
    """Turn and move ``frame`` so the site's fetched boundary lands on the
    boundary drawn in the file.

    Both boundaries are taken by their convex hulls -- the drawn one may be a
    handful of corner markers, a polyline, a fill, or all three -- and the
    turn is the difference of their longest sides, the shift the difference
    of their centroids after that turn. A site is not a circle: its longest
    side says which way it faces, whatever else was drawn.

    ``site_rings`` are in longitude and latitude; ``drawn`` in project metres.
    """
    ours = convex_hull(p for ring in site_rings for p in frame.ring(ring))
    theirs = convex_hull(drawn)
    if len(ours) < 3 or len(theirs) < 3:
        raise ValueError("a boundary fit needs three points on each side")
    delta = (_edge_bearing(theirs) - _edge_bearing(ours) + 90.0) % 180.0 - 90.0
    turned = _turn_about_origin(ours, delta)
    c_ours, c_theirs = ring_centroid(turned), ring_centroid(theirs)
    shift = (c_theirs[0] - c_ours[0], c_theirs[1] - c_ours[1])
    landed = [(x + shift[0], y + shift[1]) for x, y in turned]
    residual = sum(_distance_to_ring(p, landed) for p in theirs) / len(theirs)
    return Fit(
        frame=frame.turned_and_moved(delta, shift),
        turn_deg=delta,
        shift=shift,
        residual_m=residual,
        drawn_points=len(theirs),
    )


#: Where the project origin may be put on the site: its centre, or one of
#: its corners as the drawing reads them, bottom-left being south-west on a
#: north-up frame and the left end of the long boundary on a squared one.
ORIGIN_CHOICES: tuple[str, ...] = ("centre", "bottom-left", "bottom-right", "top-left", "top-right")


def placed_frame(
    frame: Frame,
    site_rings: Sequence[Sequence[Point]],
    *,
    square: bool = False,
    origin_at: str = "centre",
) -> Frame:
    """The site-anchored frame, turned and moved the way the office sets a
    site up: ``square`` turns it so the site's longest boundary runs along
    +X, and ``origin_at`` names the corner of the site that is the project
    origin, the centre being where ``frame_for`` already put it.

    Asked for on 8 October 2026: a model is drawn with its long frontage
    level on the screen and its origin on a corner of the site, not on an
    address's centroid, and the context should come in to match. The turn
    is the one the boundary fit makes (``fit_frame``), applied to the site's
    own convex hull; a corner is the hull's vertex furthest that way, taken
    after the turn so "bottom-left" means what the drawing shows.

    The project's north follows the turn: ``plus_y_bearing_deg`` is the
    bearing to write into Project Location, or the sun is wrong by the turn.
    """
    if origin_at not in ORIGIN_CHOICES:
        raise ValueError(f"origin_at must be one of {ORIGIN_CHOICES}, not {origin_at!r}")
    placed = frame
    hull = convex_hull(p for ring in site_rings for p in placed.ring(ring))
    if square and len(hull) >= 2:
        delta = -((_edge_bearing(hull) + 90.0) % 180.0 - 90.0)
        placed = placed.turned_and_moved(delta, (0.0, 0.0))
        hull = convex_hull(p for ring in site_rings for p in placed.ring(ring))
    if origin_at != "centre" and hull:
        furthest: dict[str, Callable[[Point], float]] = {
            "bottom-left": lambda p: p[0] + p[1],
            "bottom-right": lambda p: p[1] - p[0],
            "top-left": lambda p: p[0] - p[1],
            "top-right": lambda p: -p[0] - p[1],
        }
        corner = min(hull, key=furthest[origin_at])
        placed = placed.turned_and_moved(0.0, (-corner[0], -corner[1]))
    return placed


def frame_for(
    geo: GeoLocation | None,
    *,
    site_centre: tuple[float, float],
    anchor: str = "location",
    north: str = "true",
) -> Frame:
    """Where the site lands: on the project's own georeferencing, or at its origin.

    ``anchor="location"`` uses ``GetGeoLocation`` for both the origin and
    north. ``anchor="site"`` puts the site's centre at ``(0, 0)`` and keeps
    the project's north when it has one, north-up otherwise -- for a project
    that has nothing in it yet and no location set.

    ``north="true"`` takes the project's north angle as a true bearing, which
    is what Archicad means by it; ``north="grid"`` takes it as an MGA grid
    bearing, which is what it is in a file whose north was typed from the
    survey plan, and skips the convergence.
    """
    if north not in ("true", "grid"):
        raise ValueError(f"north must be 'true' or 'grid', not {north!r}")
    zone = mga_zone(site_centre[0])
    bearing = geo.project_north_bearing_deg if geo is not None else 0.0
    if anchor == "site":
        lon, lat = site_centre
    elif anchor != "location":
        raise ValueError(f"anchor must be 'location' or 'site', not {anchor!r}")
    elif geo is None:
        raise ValueError("anchor='location' needs the project's geolocation")
    else:
        lon, lat = geo.longitude_deg, geo.latitude_deg
    origin = lonlat_to_mga(lon, lat, zone)
    # The convergence, measured rather than looked up: the grid bearing of a
    # short step due north from the origin.
    step = lonlat_to_mga(lon, lat + 1e-4, zone)
    convergence = math.degrees(math.atan2(step[0] - origin[0], step[1] - origin[1]))
    return Frame(zone, origin, bearing, convergence if north == "true" else 0.0)


# -- what gets drawn -----------------------------------------------------------


def _clean_ring(ring: Sequence[Point]) -> list[Point]:
    """The ring without its closing point or any repeated vertex.

    The add-on appends the closing point itself, and a polygon handed to
    Archicad with a zero-length edge is refused rather than repaired.
    """
    out: list[Point] = []
    for point in ring:
        if not out or math.hypot(point[0] - out[-1][0], point[1] - out[-1][1]) > 1e-6:
            out.append((float(point[0]), float(point[1])))
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-6:
        out.pop()
    return out


def _polygons(rings: Sequence[Sequence[Point]]) -> list[tuple[list[Point], list[list[Point]]]]:
    """Sort a feature's rings into polygons: ``(outer, holes)`` each.

    A cadastral or zoning feature arrives as every ring of a multipolygon in
    one list, outers and holes together, and a fill given a "hole" that lies
    outside its outer contour is refused (``APIERR_IRREGULARPOLY`` on the Kogarah
    run, for the first zoning polygon with two parts). So the rings are
    placed by containment, largest first: a ring inside an outer is that
    outer's hole, unless it sits inside one of its holes already, in which
    case it is an island and an outer of its own.
    """
    cleaned = [
        ring
        for ring in (_clean_ring(r) for r in rings)
        if len(ring) >= 3 and abs(ring_area(ring)) > 1e-4
    ]
    cleaned.sort(key=lambda ring: -abs(ring_area(ring)))
    polygons: list[tuple[list[Point], list[list[Point]]]] = []
    for ring in cleaned:
        probe = ring_centroid(ring) if point_in_ring(*ring_centroid(ring), ring) else ring[0]
        placed = False
        for outer, holes in polygons:
            if not point_in_ring(probe[0], probe[1], outer):
                continue
            if any(point_in_ring(probe[0], probe[1], hole) for hole in holes):
                continue
            holes.append(ring)
            placed = True
            break
        if not placed:
            polygons.append((ring, []))
    return polygons


#: The parts whose lettering is the sheet's and not the map's, so a theme's
#: text scale leaves it alone.
UNSCALED_PARTS = frozenset({"Frame", "Legend", "Table"})

#: Which of a sheet's five layers each part of the drawing goes on.
LAYER_GROUPS: dict[str, dict[str, str]] = {
    CONTEXT_WORD: {
        "Aerial": "Aerial",
        "Zoning": "Land Use",
        "Institutions": "Land Use",
        "Railway": "Land Use",
        "Heritage": "Land Use",
        "Site": "Land Use",
        "Streets": "Land Use",
        "Cadastre": "Lines",
        "Roads": "Lines",
        "Bus routes": "Lines",
        "Walking catchment": "Lines",
        "Bus stops": "Labels",
        "Stations": "Labels",
        "Labels": "Labels",
        "Road names": "Labels",
        "Frame": "Sheet",
        "Legend": "Sheet",
    },
    SITE_WORD: {
        "Aerial": "Aerial",
        "Site": "Site",
        "Site lots": "Site",
        "Dimensions": "Site",
        "Levels": "Site",
        "Cadastre": "Context",
        "Zoning": "Context",
        "Heritage": "Context",
        "Contours": "Context",
        "Roads": "Context",
        "Buildings": "Context",
        "Future": "Context",
        "Noise": "Furniture",
        "Traffic": "Furniture",
        "Utilities": "Furniture",
        "Parking": "Furniture",
        "Access": "Furniture",
        "Trees": "Furniture",
        "Services": "Furniture",
        "Bus stops": "Furniture",
        "Neighbours": "Furniture",
        "Road names": "Furniture",
        "Sun path": "Sheet",
        "Winds": "Sheet",
        "Climate": "Sheet",
        "Frame": "Sheet",
        "Legend": "Sheet",
    },
    SUMMARY_WORD: {"Table": "Table"},
}


def _hatch_segments(
    rings: Sequence[Sequence[Point]], spacing_m: float, angle_deg: float = 45.0
) -> list[tuple[Point, Point]]:
    """Parallel lines across a polygon with holes, clipped to it.

    Worked in a frame turned so the lines are horizontal: each line crosses
    the polygon's edges at an even number of points, and the crossings in
    pairs are what lies inside -- the even-odd rule, which handles a hole
    and a concave outline alike.
    """
    a = math.radians(angle_deg)
    c, sn = math.cos(a), math.sin(a)

    def turn(pt: Point) -> Point:
        return (pt[0] * c + pt[1] * sn, -pt[0] * sn + pt[1] * c)

    def back(pt: Point) -> Point:
        return (pt[0] * c - pt[1] * sn, pt[0] * sn + pt[1] * c)

    edges: list[tuple[Point, Point]] = []
    for ring in rings:
        turned = [turn(pt) for pt in ring]
        edges.extend(zip(turned, [*turned[1:], turned[0]], strict=True))
    if not edges or spacing_m <= 0:
        return []
    ys = [pt[1] for edge in edges for pt in edge]
    segments: list[tuple[Point, Point]] = []
    y = min(ys) + spacing_m / 2.0
    top = max(ys)
    while y < top:
        crossings: list[float] = []
        for (x1, y1), (x2, y2) in edges:
            if (y1 > y) != (y2 > y):
                crossings.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        crossings.sort()
        for left, right in zip(crossings[0::2], crossings[1::2], strict=False):
            if right - left > 1e-6:
                segments.append((back((left, y)), back((right, y))))
        y += spacing_m
    return segments


@dataclass
class Fill:
    layer: str
    rings: list[list[Point]]
    colour: str
    contour: str | None = None
    element_id: str = ""
    wash: bool = False
    """A percentage fill with a clear background, so what is under it shows
    through -- the zoning over the aerial, as the office's sheets have it."""
    hatch: bool = False
    """A diagonal hatch with a clear background: the heritage items."""
    weight_mm: float | None = None
    """The contour's pen weight."""
    dashed: bool = False
    """The contour dashed: a size the sheet draws without having it recorded."""


@dataclass
class Figure:
    """A picture placed on the drawing: a JPEG on disk, its bottom-left corner,
    its size on the ground and its turn, in project metres and radians."""

    layer: str
    path: str
    at: Point
    width_m: float
    height_m: float
    angle_rad: float = 0.0
    name: str = ""


@dataclass
class Line:
    layer: str
    points: list[Point]
    colour: str = INK
    dashed: bool = False
    weight_mm: float | None = None
    dotted: bool = False


@dataclass
class Text:
    layer: str
    text: str
    at: Point
    height_mm: float
    angle_rad: float = 0.0
    justification: str = "Center"
    colour: str = INK


@dataclass
class Drawing:
    """One sheet's worth of elements, in project metres, before any Archicad call.

    Built by the pure ``*_drawing`` functions so a test can count and place
    without a licence; ``_flush`` is what turns it into commands.
    """

    scale: float
    word: str
    fills: list[Fill] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    pictures_as: str = "figure"
    """``figure`` or ``drawing``: what the orthophoto is placed as. A Figure
    is a picture on the sheet; a Drawing has a frame, a ratio and a row in
    the Drawing Manager. Neither links to the file (D92)."""
    text_scale: float = 1.0
    """Multiplies every text height on the map: a theme can run its lettering
    larger. The sheet's own words -- the title, the legend, the credit -- keep
    their size, which is the sheet's and not the theme's."""

    def mm(self, value: float) -> float:
        """Millimetres on paper at this drawing's scale, as ground metres."""
        return value * self.scale / 1000.0

    def layer(self, part: str) -> str:
        """The layer a part goes on: one of five per sheet.

        Every element carries its meaning as its ID, so a layer per data
        class was bookkeeping nobody needed; five is what a person switches
        on and off -- the photo, the land use, the lines, the labels, the
        sheet furniture.
        """
        group = LAYER_GROUPS.get(self.word, {}).get(part, part)
        return naming.layer(group, self.word)

    def fill(
        self,
        part: str,
        rings: Sequence[Sequence[Point]],
        colour: str,
        *,
        contour: str | None = None,
        element_id: str = "",
        wash: bool = False,
        hatch: bool = False,
        weight_mm: float | None = None,
        dashed: bool = False,
        texture: str | None = None,
        texture_colour: str | None = None,
    ) -> None:
        # An ID on every fill, so a schedule or a Find & Select can pick the
        # railway, the heritage items or the wash out of six thousand fills:
        # the legend meaning where the caller gives one, the layer's part
        # otherwise.
        identifier = element_id or f"SA {part.upper()}"
        for outer, holes in _polygons(rings):
            if hatch:
                # The lines of the hatch are the drawing's own, so their
                # spacing is the sheet's and not a fill attribute's: a fill
                # pattern scaled for 1:100 reads solid at 1:3000.
                for segment in _hatch_segments([outer, *holes], self.mm(HATCH_MM)):
                    self.lines.append(
                        Line(self.layer(part), list(segment), contour or colour, False, 0.18)
                    )
            if texture:
                self._texture(part, [outer, *holes], texture, texture_colour or contour or colour)
            self.fills.append(
                Fill(
                    self.layer(part),
                    [outer, *holes],
                    colour,
                    contour,
                    identifier,
                    wash,
                    hatch,
                    weight_mm,
                    dashed,
                )
            )

    def _texture(
        self, part: str, rings: Sequence[Sequence[Point]], texture: str, colour: str
    ) -> None:
        """A category's texture as the drawing's own lines over its fill: a
        hatch, a cross-hatch, or rows of dots -- a hatch in the dotted line
        type, which is what Archicad has in place of a dot pattern that keeps
        its size on paper."""
        # Dots are the lightest of the three, so their rows are wider apart
        # and their pen finer: a dotted hatch as close as a lined one reads as
        # a second set of stripes.
        dots = texture == "dots"
        spacing = self.mm(TEXTURE_MM * (1.6 if dots else 1.0))
        for angle in (45.0, 135.0) if texture == "cross" else (45.0,):
            for segment in _hatch_segments(rings, spacing, angle):
                self.lines.append(
                    Line(
                        self.layer(part), list(segment), colour, False, 0.1 if dots else 0.13, dots
                    )
                )

    def figure(
        self,
        part: str,
        path: str,
        at: Point,
        width_m: float,
        height_m: float,
        *,
        angle_rad: float = 0.0,
        name: str = "",
    ) -> None:
        if width_m > 0 and height_m > 0:
            self.figures.append(
                Figure(self.layer(part), path, at, width_m, height_m, angle_rad, name)
            )

    def moved(self, dx: float, dy: float) -> Drawing:
        """The same drawing, every coordinate shifted."""
        out = Drawing(self.scale, self.word)
        for fill in self.fills:
            out.fills.append(
                replace(fill, rings=[[(x + dx, y + dy) for x, y in ring] for ring in fill.rings])
            )
        for line in self.lines:
            out.lines.append(replace(line, points=[(x + dx, y + dy) for x, y in line.points]))
        for text in self.texts:
            out.texts.append(replace(text, at=(text.at[0] + dx, text.at[1] + dy)))
        if self.figures:
            raise ValueError("a drawing with figures is not moved")
        return out

    def line(
        self,
        part: str,
        points: Sequence[Point],
        *,
        colour: str = INK,
        dashed: bool = False,
        weight_mm: float | None = None,
        closed: bool = False,
        dotted: bool = False,
    ) -> None:
        pts = list(points)
        if closed and pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        if len(pts) >= 2:
            self.lines.append(Line(self.layer(part), pts, colour, dashed, weight_mm, dotted))

    def text(
        self,
        part: str,
        text: str,
        at: Point,
        *,
        height_mm: float,
        angle_rad: float = 0.0,
        justification: str = "Center",
        colour: str = INK,
    ) -> None:
        if text:
            scale = 1.0 if part in UNSCALED_PARTS else self.text_scale
            self.texts.append(
                Text(
                    self.layer(part),
                    text,
                    at,
                    height_mm * scale,
                    angle_rad,
                    justification,
                    colour,
                )
            )

    def circle(
        self,
        part: str,
        centre: Point,
        radius_m: float,
        *,
        colour: str = INK,
        fill: str | None = None,
        dashed: bool = False,
        segments: int = 24,
        weight_mm: float | None = None,
        wash: bool = False,
        element_id: str = "",
        dotted: bool = False,
    ) -> None:
        ring = [
            (
                centre[0] + radius_m * math.cos(2 * math.pi * i / segments),
                centre[1] + radius_m * math.sin(2 * math.pi * i / segments),
            )
            for i in range(segments)
        ]
        if fill is not None:
            self.fill(
                part,
                [ring],
                fill,
                contour=colour,
                weight_mm=weight_mm,
                wash=wash,
                dashed=dashed,
                element_id=element_id,
            )
        else:
            self.line(
                part,
                ring,
                colour=colour,
                dashed=dashed,
                closed=True,
                weight_mm=weight_mm,
                dotted=dotted,
            )

    @property
    def layers(self) -> list[str]:
        return sorted(
            {
                *(f.layer for f in self.fills),
                *(line.layer for line in self.lines),
                *(t.layer for t in self.texts),
                *(g.layer for g in self.figures),
            }
        )


class Placer:
    """Keeps labels off each other: a label that collides is nudged outward
    through rings of candidates rather than dropped, and dropped only when
    every candidate still overlaps."""

    def __init__(self) -> None:
        self.boxes: list[tuple[float, float, float, float]] = []

    def reserve(self, x: float, y: float, w: float, h: float) -> None:
        self.boxes.append((x - w / 2, y - h / 2, w, h))

    def free(self, x: float, y: float, w: float, h: float, gap: float) -> bool:
        ax, ay = x - w / 2, y - h / 2
        return not any(
            ax < bx + bw + gap and ax + w + gap > bx and ay < by + bh + gap and ay + h + gap > by
            for bx, by, bw, bh in self.boxes
        )

    def place(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        step: float,
        max_radius: float,
        angle: float = 0.0,
    ) -> Point | None:
        width = abs(w * math.cos(angle)) + abs(h * math.sin(angle))
        height = abs(w * math.sin(angle)) + abs(h * math.cos(angle))
        gap = step / 4
        if self.free(x, y, width, height, gap):
            self.reserve(x, y, width, height)
            return (x, y)
        radius = step
        while radius <= max_radius:
            for degrees in range(0, 360, 30):
                nx = x + radius * math.cos(math.radians(degrees))
                ny = y + radius * math.sin(math.radians(degrees))
                if self.free(nx, ny, width, height, gap):
                    self.reserve(nx, ny, width, height)
                    return (nx, ny)
            radius += step
        return None


def _text_width_m(drawing: Drawing, text: str, height_mm: float) -> float:
    longest = max((len(line) for line in text.split("\n")), default=0)
    return drawing.mm(longest * height_mm * drawing.text_scale * 0.6)


def _text_height_m(drawing: Drawing, text: str, height_mm: float) -> float:
    return drawing.mm(height_mm * 1.5) * max(1, text.count("\n") + 1)


def _wrapped(label: str, width: int = 14) -> str:
    """A place name on two or three lines, as the office sets it: ``ST GEORGE
    / HOSPITAL`` rather than one long line across the parcel."""
    words = label.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def _roundel(
    drawing: Drawing,
    part: str,
    at: Point,
    letter: str,
    colour: str,
    meaning: str,
    *,
    solid: bool = False,
) -> None:
    """A letter in a circle: the office's stop and station symbol. A thin ring
    on white with the letter in the ring's colour, or a solid disc with the
    letter knocked out in white."""
    ring = [
        (
            at[0] + drawing.mm(ROUNDEL_MM) * math.cos(2 * math.pi * i / 24),
            at[1] + drawing.mm(ROUNDEL_MM) * math.sin(2 * math.pi * i / 24),
        )
        for i in range(24)
    ]
    drawing.fill(
        part,
        [ring],
        colour if solid else "#ffffff",
        contour=colour,
        weight_mm=0.2 if solid else 0.35,
        element_id=f"SA {meaning}",
    )
    drawing.text(part, letter, at, height_mm=ROUNDEL_TEXT_MM, colour="#ffffff" if solid else colour)


def _band(
    drawing: Drawing, part: str, centre: Point, angle: float, length_m: float, height_m: float
) -> None:
    """The white double-headed arrow a street name is set in."""
    dx, dy = math.cos(angle), math.sin(angle)
    nx, ny = -dy, dx
    half, head, hh = length_m / 2, height_m * 0.9, height_m / 2
    cx, cy = centre
    tip_l = (cx - dx * half, cy - dy * half)
    tip_r = (cx + dx * half, cy + dy * half)
    body_l = (cx - dx * (half - head), cy - dy * (half - head))
    body_r = (cx + dx * (half - head), cy + dy * (half - head))
    ring = [
        tip_l,
        (body_l[0] + nx * hh, body_l[1] + ny * hh),
        (body_r[0] + nx * hh, body_r[1] + ny * hh),
        tip_r,
        (body_r[0] - nx * hh, body_r[1] - ny * hh),
        (body_l[0] - nx * hh, body_l[1] - ny * hh),
    ]
    drawing.fill(
        part, [ring], "#ffffff", contour="#555555", weight_mm=0.2, element_id="SA STREET NAME BAND"
    )


def _along(points: Sequence[Point]) -> float:
    """The angle of the middle segment, kept readable: in (-90, 90] degrees."""
    if len(points) < 2:
        return 0.0
    i = len(points) // 2
    (ax, ay), (bx, by) = points[max(0, i - 1)], points[min(i, len(points) - 1)]
    if (ax, ay) == (bx, by) and len(points) > 2:
        (ax, ay), (bx, by) = points[0], points[-1]
    angle = math.atan2(by - ay, bx - ax)
    if angle > math.pi / 2:
        angle -= math.pi
    if angle <= -math.pi / 2:
        angle += math.pi
    return angle


def _midpoint(points: Sequence[Point]) -> Point:
    i = len(points) // 2
    (ax, ay), (bx, by) = points[max(0, i - 1)], points[min(i, len(points) - 1)]
    return ((ax + bx) / 2, (ay + by) / 2)


def _map_rectangle(bundle: ContextBundle | SiteBundle, frame: Frame) -> list[Point]:
    """The sheet's map field, as the project sees it: four corners, anticlockwise."""
    e = bundle.extent
    corners = [(e.xmin, e.ymin), (e.xmax, e.ymin), (e.xmax, e.ymax), (e.xmin, e.ymax)]
    return [frame.project(*mercator_to_lonlat(x, y)) for x, y in corners]


def _map_point(bundle: ContextBundle | SiteBundle, frame: Frame, x_mm: float, y_mm: float) -> Point:
    """A point given in sheet millimetres from the map field's top-left, north up."""
    e = bundle.extent
    x = e.xmin + x_mm / MAP_WIDTH_MM * e.width
    y = e.ymax - y_mm / MAP_HEIGHT_MM * e.height
    return frame.project(*mercator_to_lonlat(x, y))


def _street_labels(
    drawing: Drawing,
    frame: Frame,
    roads: Sequence[Any],
    placer: Placer,
    *,
    part: str,
    height_mm: float,
    arrows: bool,
    ink: str = INK,
) -> None:
    """One label per street name, on its longest piece, along the road.

    A street gets a double-headed arrow under its name; a laneway a plain
    label -- the distinction the office's sheets make, and it matters: the
    rear lane is often the widest thing on the site sheet after the street.
    """
    best: dict[str, tuple[float, list[Point], int, int | None]] = {}
    for road in roads:
        points = frame.ring(road.coords)
        length = polyline_length(points)
        current = best.get(road.name)
        hierarchy = min(current[2] if current else 9, road.hierarchy)
        lanes = (
            road.lanes
            if current is None or current[3] is None
            else max(current[3], road.lanes or 0)
        )
        if current is None or length > current[0]:
            best[road.name] = (length, points, hierarchy, lanes)
        else:
            best[road.name] = (current[0], current[1], hierarchy, lanes)

    for name, (length, points, hierarchy, lanes) in best.items():
        label = curate.short_street_name(name)
        width = _text_width_m(drawing, label, height_mm)
        banded = arrows and not curate.is_laneway(hierarchy, lanes, name)
        band_length = width + drawing.mm(BAND_MM * 2.6)
        if length < (band_length if banded else width) * 0.9:
            continue
        angle = _along(points)
        mx, my = _midpoint(points)
        spot = placer.place(
            mx,
            my,
            band_length if banded else width,
            drawing.mm(BAND_MM if banded else height_mm * 1.5),
            step=drawing.mm(4),
            max_radius=drawing.mm(12),
            angle=angle,
        )
        if spot is None:
            continue
        if banded:
            _band(drawing, part, spot, angle, band_length, drawing.mm(BAND_MM))
        drawing.text(part, label, spot, height_mm=height_mm, angle_rad=angle, colour=ink)


@dataclass(frozen=True)
class Row:
    """One legend row: a swatch and what it means.

    ``kind`` is ``fill``, ``dashed fill``, ``wash``, ``dashed wash``, ``hatch``
    (an empty fill with the hatch lines in the contour's ink), ``line``,
    ``dashed``, ``dotted`` or ``text``; a text swatch shows the label's own
    lettering, the way ``SB 30.48`` is explained on the site sheet.
    """

    kind: str
    colour: str
    contour: str | None
    label: str
    texture: str | None = None
    texture_colour: str | None = None


def _legend(
    drawing: Drawing,
    rows: Sequence[Row],
    origin: Point,
    *,
    title: str,
) -> None:
    """Swatches and labels down the right of the map field."""
    x, top = origin
    swatch_w, swatch_h, step = drawing.mm(16), drawing.mm(6.5), drawing.mm(10)
    drawing.text(
        "Legend", title, (x, top + drawing.mm(6)), height_mm=LEGEND_MM * 1.4, justification="Left"
    )
    for row, item in enumerate(rows):
        y = top - step * (row + 1)
        if item.kind in ("fill", "dashed fill", "wash", "dashed wash", "hatch"):
            drawing.fill(
                "Legend",
                [[(x, y), (x + swatch_w, y), (x + swatch_w, y + swatch_h), (x, y + swatch_h)]],
                item.colour,
                contour=item.contour or item.colour,
                wash="wash" in item.kind,
                hatch=item.kind == "hatch",
                dashed=item.kind.startswith("dashed"),
                texture=item.texture,
                texture_colour=item.texture_colour,
            )
        elif item.kind in ("line", "dashed", "dotted"):
            drawing.line(
                "Legend",
                [(x, y + swatch_h / 2), (x + swatch_w, y + swatch_h / 2)],
                colour=item.colour,
                dashed=item.kind == "dashed",
                dotted=item.kind == "dotted",
                weight_mm=0.5,
            )
        else:
            drawing.text(
                "Legend",
                item.colour,
                (x, y + swatch_h * 0.2),
                height_mm=LEGEND_MM,
                justification="Left",
            )
        drawing.text(
            "Legend",
            item.label,
            (x + swatch_w + drawing.mm(3), y + swatch_h * 0.2),
            height_mm=LEGEND_MM,
            justification="Left",
        )


def _furniture_of_sheet(
    drawing: Drawing,
    bundle: ContextBundle | SiteBundle,
    frame: Frame,
    *,
    title: str,
) -> Point:
    """Frame, title and north point. Returns where the legend should start."""
    corners = _map_rectangle(bundle, frame)
    drawing.line("Frame", corners, colour=INK, weight_mm=0.35, closed=True)
    right = max(x for x, _ in corners)
    top = max(y for _, y in corners)
    left = min(x for x, _ in corners)
    drawing.text(
        "Frame",
        f"{title}   1:{bundle.scale:g}   {bundle.matched[0] if bundle.matched else bundle.address}",
        (left, top + drawing.mm(8)),
        height_mm=TITLE_MM,
        justification="Left",
    )
    # North point: a line along true north, inside the top-right corner.
    nx, ny = frame.direction(0.0)
    base = (right - drawing.mm(30), top - drawing.mm(40))
    tip = (base[0] + nx * drawing.mm(20), base[1] + ny * drawing.mm(20))
    drawing.line("Frame", [base, tip], colour=INK, weight_mm=0.5)
    drawing.circle("Frame", base, drawing.mm(3), colour=INK)
    drawing.text(
        "Frame", "N", (tip[0] + nx * drawing.mm(4), tip[1] + ny * drawing.mm(4)), height_mm=LABEL_MM
    )
    _credit(drawing, bundle, corners)
    return (right + drawing.mm(15), top)


def _credit_lines(credit: str, width_mm: float) -> list[str]:
    """The credit broken into lines that fit ``width_mm`` of paper.

    0.55 of the text height is about what this lettering averages per
    character; erring narrow costs a second line, which is cheap, while
    erring wide runs the credit off the sheet, which is not.
    """
    return textwrap.wrap(credit, max(40, int(width_mm / (CREDIT_MM * 0.55))))


def _credit(drawing: Drawing, bundle: ContextBundle | SiteBundle, corners: Sequence[Point]) -> None:
    """Whose data this sheet is drawn from, along the foot of the map.

    Under the frame rather than in the legend: the legend says what a colour
    means and is read while looking at the map, and this is read once, by
    whoever sends the sheet out. It is the standard place for a credit on a
    map, which is the other reason.

    What it names is what the bundle actually holds -- see ``sources_used``.
    Every fetch but the site's own fails soft, so crediting the full list
    would put OpenStreetMap on a sheet whose Overpass mirrors were all down
    that morning, and a credit is a statement about where a line came from.
    """
    line = sources.credit_line(sources.named(bundle.sources_used()))
    if not line:  # pragma: no cover - a bundle with nothing in it at all
        return
    left = min(x for x, _ in corners)
    bottom = min(y for _, y in corners)
    # Measured off the frame rather than assumed to be the A1 map field: the
    # width in ground metres divided by a paper millimetre is the width in
    # paper millimetres, whatever scale this sheet chose for itself.
    width_mm = (max(x for x, _ in corners) - left) / drawing.mm(1.0)
    for row, part in enumerate(_credit_lines(line, width_mm)):
        drawing.text(
            "Frame",
            part,
            (left, bottom - drawing.mm(6) - row * drawing.mm(CREDIT_MM * 1.6)),
            height_mm=CREDIT_MM,
            justification="Left",
            colour=CADASTRE_GREY,
        )


def _aerial(
    drawing: Drawing,
    bundle: ContextBundle | SiteBundle,
    frame: Frame,
    *,
    grey: bool = False,
    veil: float = 0.0,
    keep: Sequence[Sequence[Point]] = (),
) -> bool:
    """The orthophoto tiles as Figures, under everything else. True if any.

    A tile is north-up in Web Mercator; in the project frame it is turned by
    the frame's angle and sized by its corners' distances on the ground, so
    it lands under the cadastre it was fetched with.

    A theme that wants the photograph in grey, or washed back toward white,
    has it toned first (``imagery.toned``): a copy beside the tile, the
    polygons in ``keep`` -- the site, in longitude and latitude -- left in
    their own colours. Archicad can neither tone a Figure nor mask one, and
    a white wash over the whole photo cannot leave the site out of it.
    """
    aerial = bundle.aerial
    if aerial is None or not aerial.tiles:
        return False
    e = bundle.extent
    keep_xy = [[lonlat_to_mercator(lon, lat) for lon, lat in ring] for ring in keep]
    placed = 0
    for tile in aerial.tiles:
        x0 = e.xmin + e.width * tile.left
        x1 = x0 + e.width * tile.width
        y1 = e.ymax - e.height * tile.top
        y0 = y1 - e.height * tile.height
        sw = frame.project(*mercator_to_lonlat(x0, y0))
        se = frame.project(*mercator_to_lonlat(x1, y0))
        nw = frame.project(*mercator_to_lonlat(x0, y1))
        path = Path(aerial.folder) / tile.file
        if not path.is_file():
            continue
        if grey or veil > 0.0:
            px_w = max(1, round(aerial.px_width * tile.width))
            px_h = max(1, round(aerial.px_height * tile.height))
            pixels = [
                [((x - x0) / (x1 - x0) * px_w, (y1 - y) / (y1 - y0) * px_h) for x, y in ring]
                for ring in keep_xy
            ]
            path = toned(path, grey=grey, veil=veil, keep=pixels)
        drawing.figure(
            "Aerial",
            str(path),
            sw,
            math.dist(sw, se),
            math.dist(sw, nw),
            angle_rad=math.atan2(se[1] - sw[1], se[0] - sw[0]),
            name=tile.file,
        )
        placed += 1
    return placed > 0


def _reserve_m(hierarchy: int) -> float:
    return RESERVE_M.get(hierarchy, 6.0)


def _buffered(points: Sequence[Point], half: float) -> list[Point]:
    """A polyline widened to a strip: offset to both sides, mitred at each
    bend (the mitre clamped at twice the width, so a sharp turn does not
    throw a spike), and rounded at each end."""
    pts = [pt for i, pt in enumerate(points) if i == 0 or pt != points[i - 1]]
    if len(pts) < 2 or half <= 0:
        return []
    n = len(pts)
    left: list[Point] = []
    right: list[Point] = []
    for i, (x, y) in enumerate(pts):
        if 0 < i < n - 1:
            ax, ay = x - pts[i - 1][0], y - pts[i - 1][1]
            bx, by = pts[i + 1][0] - x, pts[i + 1][1] - y
            la, lb = math.hypot(ax, ay) or 1.0, math.hypot(bx, by) or 1.0
            ua, ub = (ax / la, ay / la), (bx / lb, by / lb)
            sx, sy = ua[0] + ub[0], ua[1] + ub[1]
            sl = math.hypot(sx, sy)
            if sl < 1e-9:
                dx, dy, k = ua[0], ua[1], 1.0
            else:
                dx, dy = sx / sl, sy / sl
                k = max(0.5, ua[0] * dx + ua[1] * dy)
        else:
            (px, py), (qx, qy) = (pts[0], pts[1]) if i == 0 else (pts[-2], pts[-1])
            length = math.hypot(qx - px, qy - py) or 1.0
            dx, dy, k = (qx - px) / length, (qy - py) / length, 1.0
        nx, ny = -dy, dx
        off = half / k
        left.append((x + nx * off, y + ny * off))
        right.append((x - nx * off, y - ny * off))

    def cap(centre: Point, out: tuple[float, float]) -> list[Point]:
        ox, oy = out
        nx, ny = -oy, ox
        return [
            (
                centre[0] + half * (math.cos(t) * ox + math.sin(t) * nx),
                centre[1] + half * (math.cos(t) * oy + math.sin(t) * ny),
            )
            for t in (math.radians(d) for d in (60, 30, 0, -30, -60))
        ]

    (sx0, sy0), (sx1, sy1) = pts[0], pts[1]
    l0 = math.hypot(sx1 - sx0, sy1 - sy0) or 1.0
    (ex0, ey0), (ex1, ey1) = pts[-2], pts[-1]
    l1 = math.hypot(ex1 - ex0, ey1 - ey0) or 1.0
    return [
        *left,
        *cap(pts[-1], ((ex1 - ex0) / l1, (ey1 - ey0) / l1)),
        *right[::-1],
        *cap(pts[0], ((sx0 - sx1) / l0, (sy0 - sy1) / l0)),
    ]


def _clip_edge(ring: Sequence[Point], a: Point, b: Point, anticlockwise: bool) -> list[Point]:
    """What of a ring lies on the inner side of one edge of a convex window,
    the crossings cut in."""
    (ax, ay), (bx, by) = a, b
    ex, ey = bx - ax, by - ay

    def inside(pt: Point) -> bool:
        cross = ex * (pt[1] - ay) - ey * (pt[0] - ax)
        return cross >= 0 if anticlockwise else cross <= 0

    def crossing(p: Point, q: Point) -> Point:
        dx, dy = q[0] - p[0], q[1] - p[1]
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-12:
            return q
        t = ((ax - p[0]) * ey - (ay - p[1]) * ex) / denominator
        return (p[0] + dx * t, p[1] + dy * t)

    kept: list[Point] = []
    previous = ring[-1]
    for current in ring:
        if inside(current):
            if not inside(previous):
                kept.append(crossing(previous, current))
            kept.append(current)
        elif inside(previous):
            kept.append(crossing(previous, current))
        previous = current
    return kept


def _clip_ring(ring: Sequence[Point], window: Sequence[Point]) -> list[Point]:
    """The part of a ring inside a convex window (Sutherland-Hodgman): each
    edge of the window in turn keeps what lies on its inner side and cuts the
    crossings. Empty when nothing is inside."""
    out = [pt for i, pt in enumerate(ring) if i == 0 or pt != ring[i - 1]]
    n = len(window)
    anticlockwise = ring_area(list(window)) > 0
    for k in range(n):
        if len(out) < 3:
            return []
        out = _clip_edge(out, window[k], window[(k + 1) % n], anticlockwise)
    return out if len(out) >= 3 else []


def _self_crossing(ring: Sequence[Point]) -> bool:
    """Whether any two edges of the ring cross; a fill Archicad refuses."""

    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    n = len(ring)
    edges = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        a, b = edges[i]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            c, d = edges[j]
            if orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0:
                return True
    return False


def _strips(points: Sequence[Point], half: float) -> list[list[Point]]:
    """A road as white fills: the one mitred strip where it holds, or, where a
    tight bend makes that strip cross itself, a rectangle per segment and a
    disc at each joint -- more fills, none refused."""
    ring = _buffered(points, half)
    if not ring:
        return []
    if not _self_crossing(ring):
        return [ring]
    out: list[list[Point]] = []
    pts = [pt for i, pt in enumerate(points) if i == 0 or pt != points[i - 1]]
    for (ax, ay), (bx, by) in pairwise(pts):
        length = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = -(by - ay) / length * half, (bx - ax) / length * half
        out.append([(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)])
    for x, y in pts:
        out.append(
            [
                (x + half * math.cos(math.pi * k / 6), y + half * math.sin(math.pi * k / 6))
                for k in range(12)
            ]
        )
    return out


def _clipped(rings: Sequence[Sequence[Point]], window: Sequence[Point]) -> list[list[Point]]:
    """Rings cut to the map field, so a zone that runs a kilometre past the
    sheet ends at its edge; a ring left with nothing inside is dropped.

    A hole is cut to a window a hand's width inside the field instead, so
    that where both it and its outer ran past the sheet the hole still sits
    strictly inside the outer's cut edge: Archicad refuses a fill whose hole
    touches its contour, and a few centimetres of wash at the sheet's edge
    is cheaper than the fill.
    """
    outers = [_clip_ring(ring, window) for ring in rings]
    outers = [ring for ring in outers if ring]
    if len(outers) < 2:
        return [loop for ring in outers for loop in _loops(ring)]
    cx = sum(x for x, _ in window) / len(window)
    cy = sum(y for _, y in window) / len(window)
    inset = []
    for x, y in window:
        dx, dy = cx - x, cy - y
        length = math.hypot(dx, dy) or 1.0
        inset.append((x + dx / length * HOLE_INSET_M * 1.5, y + dy / length * HOLE_INSET_M * 1.5))
    out: list[list[Point]] = []
    for ring in outers:
        # Probed at its centroid: a cut ring's first point may sit on the
        # outer's own cut edge, which is neither inside nor out.
        probe = ring_centroid(ring)
        size = abs(ring_area(ring))
        in_other = any(
            other is not ring
            and abs(ring_area(other)) > size
            and point_in_ring(probe[0], probe[1], other)
            for other in outers
        )
        if in_other:
            out.extend(_loops(_clip_ring(ring, inset)))
        else:
            out.extend(_loops(ring))
    return out


def _loops(ring: Sequence[Point]) -> list[list[Point]]:
    """A ring that comes back through a point it has already passed, split
    there into the loops it is made of; a loop with no area dropped. Cutting
    a concave polygon to a window can pinch it so, and Archicad refuses a
    fill whose contour touches itself."""
    if not ring:
        return []
    ring = _pinched(ring)
    out: list[list[Point]] = []
    stack: list[Point] = []
    seen: dict[tuple[float, float], int] = {}
    for pt in ring:
        key = (round(pt[0], 3), round(pt[1], 3))
        at = seen.get(key)
        if at is not None:
            loop = stack[at:]
            if len(loop) >= 3 and abs(ring_area(loop)) > 1e-3:
                out.append(loop)
            for dropped in loop:
                seen.pop((round(dropped[0], 3), round(dropped[1], 3)), None)
            stack = stack[:at]
        seen[key] = len(stack)
        stack.append(pt)
    if len(stack) >= 3 and abs(ring_area(stack)) > 1e-3:
        out.append(stack)
    return _parted(out)


def _pinched(ring: Sequence[Point], tolerance: float = PINCH_PART_M) -> list[Point]:
    """A ring that comes back within a hair of itself -- a vertex within
    ``tolerance`` of an edge it is not on -- made to touch there exactly, the
    vertex snapped onto the edge and the edge given that point, so the loops
    can be split at it. Archicad refuses the near miss as it refuses the
    touch, and a cut polygon makes both."""
    pts = list(ring)
    for _ in range(8):
        n = len(pts)
        found = False
        for i in range(n):
            px, py = pts[i]
            for j in range(n):
                if j in (i, (i - 1) % n):
                    continue
                (ax, ay), (bx, by) = pts[j], pts[(j + 1) % n]
                dx, dy = bx - ax, by - ay
                l2 = dx * dx + dy * dy
                if l2 < 1e-12:
                    continue
                t = ((px - ax) * dx + (py - ay) * dy) / l2
                if t <= 0.0 or t >= 1.0:
                    continue
                qx, qy = ax + dx * t, ay + dy * t
                if math.hypot(px - qx, py - qy) < tolerance:
                    pts[i] = (qx, qy)
                    pts.insert(j + 1, (qx, qy))
                    found = True
                    break
            if found:
                break
        if not found:
            break
    return pts


def _parted(loops: list[list[Point]]) -> list[list[Point]]:
    """Loops that still share a vertex -- the pinch they were split at --
    parted there: the smaller loop's copy of it is moved a few centimetres
    toward its own centroid, so a loop that becomes a hole no longer touches
    its outer. A sibling moved the same way loses nothing."""
    where: dict[tuple[float, float], list[tuple[int, int]]] = {}
    for i, loop in enumerate(loops):
        for j, (x, y) in enumerate(loop):
            where.setdefault((round(x, 3), round(y, 3)), []).append((i, j))
    for shared in where.values():
        if len({i for i, _ in shared}) < 2:
            continue
        largest = max(shared, key=lambda ij: abs(ring_area(loops[ij[0]])))[0]
        for i, j in shared:
            if i == largest:
                continue
            cx, cy = ring_centroid(loops[i])
            x, y = loops[i][j]
            length = math.hypot(cx - x, cy - y) or 1.0
            step = min(PINCH_PART_M, length / 2)
            loops[i][j] = (x + (cx - x) / length * step, y + (cy - y) / length * step)
    return loops


def _sheet_mm(bundle: ContextBundle | SiteBundle, frame: Frame, at: Point) -> tuple[float, float]:
    """A project point as sheet millimetres from the map field's top-left, north up."""
    x, y = lonlat_to_mercator(*frame.unproject(*at))
    e = bundle.extent
    return ((x - e.xmin) / e.width * MAP_WIDTH_MM, (e.ymax - y) / e.height * MAP_HEIGHT_MM)


def _along_ring(points: Sequence[Point], count: int, phase: float) -> list[Point]:
    """``count`` points spaced evenly round a ring by its own length, the
    first ``phase`` of the way round."""
    ring = [*points, points[0]] if points and points[0] != points[-1] else list(points)
    total = polyline_length(ring)
    if total <= 0 or count <= 0:
        return []
    wanted = [((phase + k / count) % 1.0) * total for k in range(count)]
    out: list[Point] = []
    for target in sorted(wanted):
        run = 0.0
        for (ax, ay), (bx, by) in pairwise(ring):
            seg = math.hypot(bx - ax, by - ay)
            if run + seg >= target and seg > 0:
                t = (target - run) / seg
                out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
                break
            run += seg
    return out


def _lep_label(code: str, lay_class: object) -> str:
    """A zone keyed by code and name, as the ePlanning legend has it."""
    name = str(lay_class or "").strip().upper()
    if name and not name.startswith(code.upper()):
        return f"{code.upper()} {name}"
    return name or curate.zone_label(code) or code.upper()


def _lep_order(code: str) -> int:
    keys = list(themes.LEP_ZONE_FILL)
    c = code.upper()
    return keys.index(c) if c in keys else len(keys)


def _rail(
    drawing: Drawing, part: str, lines: Sequence[list[Point]], t: themes.Theme, weight_mm: float
) -> None:
    """Heavy rail: a plain line, the dark line with white sleeper dashes, or
    a dotted line in the rail colour, as the theme has it."""
    for points in lines:
        if t.rail_line == "dotted":
            drawing.line(part, points, colour=t.rail, dotted=True, weight_mm=weight_mm)
            continue
        drawing.line(part, points, colour=t.rail, weight_mm=weight_mm)
        if t.rail_line == "sleepers":
            drawing.line(part, points, colour="#ffffff", dashed=True, weight_mm=weight_mm * 0.6)


def _catchments(
    drawing: Drawing, bundle: ContextBundle, frame: Frame, t: themes.Theme
) -> list[Row]:
    """The walking catchments in the theme's style, and their legend rows."""
    rows: list[Row] = []
    style = t.isochrone
    part = "Walking catchment"
    for isochrone in bundle.isochrones:
        minutes = isochrone.minutes
        colour = t.walk5 if minutes <= 5 else t.walk10
        label = {5: "400m (5-MIN WALK)", 10: "800m (10-MIN WALK)"}.get(
            minutes, f"{minutes}-MIN WALK"
        )
        rings = [frame.ring(r) for r in isochrone.rings]
        for points in rings:
            drawing.line(
                part,
                points,
                colour=colour,
                dashed=style == "dashed",
                dotted=style == "dotted",
                weight_mm={"dashed": 0.5, "dotted": 0.6, "walkers": 0.7, "labelled": 0.45}.get(
                    style, 0.6
                ),
                closed=True,
            )
        if rings:
            outer = max(rings, key=lambda r: abs(ring_area(r)))
            if style == "walkers":
                for at in _along_ring(outer, 4, 0.15 if minutes <= 5 else 0.6):
                    drawing.circle(
                        part,
                        at,
                        drawing.mm(3.4),
                        colour=colour,
                        fill=colour,
                        element_id="SA WALKER",
                    )
            else:
                i = max(range(len(outer)), key=lambda k: outer[k][1])
                top = outer[i]
                along = style in ("dotted", "labelled")
                text = (
                    f"{minutes} MIN · {minutes * 80}M"
                    if style == "labelled"
                    else f"{minutes} MIN"
                    if style == "dotted"
                    else label
                )
                angle = _along([outer[i - 1], top, outer[(i + 1) % len(outer)]]) if along else 0.0
                drawing.text(
                    part,
                    text,
                    (top[0], top[1] + drawing.mm(3)),
                    height_mm=STREET_MM,
                    angle_rad=angle,
                    colour=colour if along else INK,
                )
        kind = "dashed" if style == "dashed" else "dotted" if style == "dotted" else "line"
        rows.append(Row(kind, colour, None, label))
    return rows


def _category_row(cat: themes.Category, *, on_paper: bool, wash: bool) -> Row:
    return Row(
        "fill" if on_paper or not wash else "wash",
        cat.on_paper() if on_paper else cat.fill,
        cat.stroke,
        cat.label,
        cat.texture,
        cat.hatch_colour if cat.texture else None,
    )


# -- the context analysis ------------------------------------------------------


def context_drawing(
    bundle: ContextBundle, frame: Frame, theme: str | themes.Theme | None = None
) -> Drawing:
    """The context sheet as elements: zoning wash, institutions, transport,
    walking catchments, labels, the site on top, and a legend of what is there.

    ``theme`` is the house style it is drawn in (``site.theme``): the palette,
    the inks and the line styles. What is drawn is the same in every theme.
    """
    t = theme if isinstance(theme, themes.Theme) else themes.theme(theme)
    drawing = Drawing(bundle.scale, CONTEXT_WORD, text_scale=t.text_scale)
    placer = Placer()
    present: dict[str, themes.Category] = {}
    on_paper = t.on_paper
    # The photo under everything, unless the theme sits on paper. Over it the
    # zoning is a wash rather than a coat, as on the office's sheets, so the
    # streets stay visible through it. A theme that tones the photo grey has
    # its veil baked into the tiles; one that keeps the colours is washed
    # back with a white percentage fill instead.
    wash = False
    if not on_paper:
        grey = t.aerial_tone == "grey"
        wash = _aerial(drawing, bundle, frame, grey=grey, veil=t.veil if grey else 0.0)
        if wash and not grey and t.veil > 0.0:
            drawing.fill(
                "Aerial",
                [_map_rectangle(bundle, frame)],
                "#ffffff",
                contour="#ffffff",
                wash=True,
                element_id="SA AERIAL WASH",
            )

    field = _map_rectangle(bundle, frame)

    def tint(part: str, rings: Sequence[Sequence[Point]], cat: themes.Category, ident: str) -> None:
        rings = _clipped(rings, field)
        if not rings:
            return
        present[cat.id] = cat
        colour = cat.on_paper() if on_paper else cat.fill
        drawing.fill(
            part,
            rings,
            colour,
            contour=cat.stroke or colour,
            element_id=ident,
            wash=wash,
            texture=cat.texture,
            texture_colour=cat.hatch_colour,
        )

    # Zoning first, so everything else sits over it: the theme's categories,
    # or each zone in its own ePlanning colour, keyed by code.
    lep_seen: dict[str, str] = {}
    for feature in bundle.zoning["features"]:
        props = feature["properties"]
        code = props.get("SYM_CODE")
        rings = [frame.ring(r) for r in rings_of(feature.get("geometry"))]
        if not rings or not code:
            continue
        if t.zoning == "lep":
            rings = _clipped(rings, field)
            if not rings:
                continue
            label = _lep_label(str(code), props.get("LAY_CLASS"))
            lep_seen[str(code)] = label
            colour = themes.zone_fill(str(code))
            drawing.fill(
                "Zoning", rings, colour, contour=colour, element_id=f"SA {label}", wash=wash
            )
            continue
        identifier = curate.zone_to_category(code)
        if not identifier:
            continue
        cat = t.category(identifier)
        tint("Zoning", rings, cat, f"SA {cat.label} ({code})")

    # One parcel once. Fifty named complexes around a hospital resolve to the
    # hospital's own parcel, and the first run drew it seventy times over. On
    # the statutory colours no institution tint is laid over the zoning.
    drawn: set[tuple[tuple[float, float], ...]] = set()
    for institution in bundle.institutions:
        key = tuple((round(x, 6), round(y, 6)) for x, y in institution.rings[0][:8])
        if key in drawn or t.zoning == "lep":
            continue
        drawn.add(key)
        cat = t.category(institution.category)
        tint(
            "Institutions",
            [frame.ring(r) for r in institution.rings],
            cat,
            f"SA {cat.label}: {institution.name}",
        )

    if t.zoning != "lep":
        railway = t.category("railway")
        for feature in bundle.rail_corridors["features"]:
            rings = [frame.ring(r) for r in rings_of(feature.get("geometry"))]
            if rings:
                present["railway"] = railway
                drawing.fill(
                    "Railway",
                    rings,
                    railway.on_paper() if on_paper else railway.fill,
                    contour=railway.stroke,
                    element_id="SA RAILWAY TRACKS",
                    texture=railway.texture,
                    texture_colour=railway.hatch_colour,
                )

    heritage = t.category("heritage")
    for feature in bundle.heritage["features"]:
        if not str(feature["properties"].get("LAY_CLASS") or "Item").startswith("Item"):
            continue
        rings = [frame.ring(r) for r in rings_of(feature.get("geometry"))]
        if rings:
            present["heritage"] = heritage
            drawing.fill(
                "Heritage",
                rings,
                t.heritage,
                contour=t.heritage,
                hatch=True,
                weight_mm=0.25,
                element_id="SA GENERAL HERITAGE SITE",
            )

    # The streets: white strips over the tints on paper, the road reserve
    # scaled from the register's function hierarchy; the centre lines in the
    # road ink; or nothing, where the photograph shows them -- unless there is
    # no photograph after all, when the centre lines come back.
    streets = t.streets if (t.streets != "none" or wash) else "lines"
    if streets == "white":
        for road in bundle.roads:
            for strip in _strips(frame.ring(road.coords), _reserve_m(road.hierarchy) / 2.0):
                drawing.fill(
                    "Streets", [strip], "#ffffff", contour="#ffffff", element_id="SA STREET"
                )

    lot_colour = "#ffffff" if t.lots == "white" else t.cadastre
    for feature in bundle.all_lots["features"]:
        for ring in rings_of(feature.get("geometry")):
            drawing.line(
                "Cadastre",
                frame.ring(ring),
                colour=lot_colour,
                closed=True,
                weight_mm=t.lot_width_mm,
            )

    if streets == "lines":
        for road in bundle.roads:
            drawing.line("Roads", frame.ring(road.coords), colour=t.road, weight_mm=0.18)
    _rail(drawing, "Railway", [frame.ring(line) for line in bundle.rail_lines.train], t, 0.5)
    for line in bundle.rail_lines.tram:
        drawing.line("Railway", frame.ring(line), colour=t.tram, dashed=True, weight_mm=0.5)
    for line in bundle.bus.routes:
        drawing.line(
            "Bus routes",
            frame.ring(line),
            colour=t.bus_route,
            dashed=t.bus_line == "dashed",
            dotted=t.bus_line == "dotted",
            weight_mm=0.3,
        )
    for line in bundle.bus.tram_routes:
        drawing.line("Bus routes", frame.ring(line), colour=t.tram, dashed=True, weight_mm=0.3)

    catchment_rows = _catchments(drawing, bundle, frame, t)

    # Stops and stations: a letter in a circle, the office's own symbol.
    solid = t.roundel == "solid"
    radius = drawing.mm(ROUNDEL_MM)
    for stop in bundle.bus.stops:
        at = frame.project(stop.lon, stop.lat)
        _roundel(drawing, "Bus stops", at, "B", t.transit, "BUS STOP", solid=solid)
        placer.reserve(at[0], at[1], radius * 2, radius * 2)
    for stop in bundle.bus.tram_stops:
        at = frame.project(stop.lon, stop.lat)
        _roundel(drawing, "Stations", at, "L", t.tram, "TRAM STOP", solid=solid)
    for station in bundle.stations:
        at = frame.project(station.lon, station.lat)
        tram = "LIGHT RAIL" in station.name.upper() or "TRAM" in station.name.upper()
        _roundel(
            drawing,
            "Stations",
            at,
            "L" if tram else "T",
            t.tram if tram else t.site,
            "LIGHT RAIL STOP" if tram else "TRAIN STATION",
            solid=solid,
        )
        placer.reserve(at[0], at[1], radius * 2, radius * 2)
        name = _wrapped(station.name.upper())
        spot = placer.place(
            at[0],
            at[1] + drawing.mm(10),
            _text_width_m(drawing, name, LABEL_MM),
            _text_height_m(drawing, name, LABEL_MM),
            step=drawing.mm(4),
            max_radius=drawing.mm(20),
        )
        if spot:
            drawing.text("Labels", name, spot, height_mm=LABEL_MM, colour=t.street_ink)

    # Place names before street names: they belong to a parcel and cannot move.
    seen: set[str] = set()
    named: list[tuple[str, Point]] = [
        (area.name.upper(), frame.project(area.lon, area.lat)) for area in bundle.park_areas
    ]
    named += [
        (p.name.upper(), frame.project(p.lon, p.lat))
        for p in bundle.park_points
        if p.name.upper() not in {a.name.upper() for a in bundle.park_areas}
    ]
    named += [(p.name.upper(), frame.project(p.lon, p.lat)) for p in bundle.complexes if p.category]
    for label, at in named:
        if label in seen:
            continue
        seen.add(label)
        text = _wrapped(label)
        spot = placer.place(
            at[0],
            at[1],
            _text_width_m(drawing, text, LABEL_MM),
            _text_height_m(drawing, text, LABEL_MM),
            step=drawing.mm(4),
            max_radius=drawing.mm(16),
        )
        if spot:
            drawing.text("Labels", text, spot, height_mm=LABEL_MM, colour=t.street_ink)

    _street_labels(
        drawing,
        frame,
        bundle.roads,
        placer,
        part="Road names",
        height_mm=STREET_MM,
        arrows=t.street_labels == "band",
        ink=t.street_ink,
    )

    site = t.category("site")
    present["site"] = site
    for feature in bundle.site_lots["features"]:
        for ring in rings_of(feature.get("geometry")):
            points = frame.ring(ring)
            # A wash with a heavy dashed edge, and no word on it: the legend
            # says what the colour is.
            drawing.fill(
                "Site",
                [points],
                site.on_paper() if on_paper else site.fill,
                contour=t.site,
                wash=not on_paper,
                element_id="SA SITE",
            )
            drawing.line("Site", points, colour=t.site, dashed=True, weight_mm=0.9, closed=True)

    legend_at = _furniture_of_sheet(drawing, bundle, frame, title="CONTEXT ANALYSIS")
    rows: list[Row] = [Row("dashed", t.site, None, "SITE")]
    for code, label in sorted(lep_seen.items(), key=lambda pair: _lep_order(pair[0])):
        rows.append(Row("wash" if wash else "fill", themes.zone_fill(code), None, label))
    rows += [
        _category_row(cat, on_paper=on_paper, wash=wash)
        for cat in t.categories
        if cat.id in present and cat.id != "site"
    ]
    if bundle.stations:
        rows.append(Row("text", "T", None, "TRAIN STATION"))
    if bundle.bus.stops:
        rows.append(Row("text", "B", None, "BUS STOP"))
    if bundle.bus.routes:
        rows.append(
            Row("dotted" if t.bus_line == "dotted" else "dashed", t.bus_route, None, "BUS ROUTE")
        )
    rows += catchment_rows
    _legend(drawing, rows, legend_at, title="CONTEXT ANALYSIS")
    return drawing


# -- the site analysis ----------------------------------------------------------


def _zigzag(points: Sequence[Point], amplitude: float, step: float) -> list[Point]:
    """A noise-source band: the line, jogged side to side along its length."""
    out: list[Point] = []
    side = 1.0
    for (ax, ay), (bx, by) in pairwise(points):
        length = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = -(by - ay) / length, (bx - ax) / length
        count = max(1, int(length / step))
        if not out:
            out.append((ax, ay))
        for i in range(count):
            t0, t1 = i / count, (i + 1) / count
            mid = (t0 + t1) / 2
            out.append(
                (
                    ax + (bx - ax) * mid + nx * amplitude * side,
                    ay + (by - ay) * mid + ny * amplitude * side,
                )
            )
            out.append((ax + (bx - ax) * t1, ay + (by - ay) * t1))
            side = -side
    return out


def _arrow(
    drawing: Drawing,
    part: str,
    tail: Point,
    head: Point,
    *,
    colour: str,
    size_m: float,
    dashed: bool = False,
) -> None:
    drawing.line(part, [tail, head], colour=colour, dashed=dashed, weight_mm=0.5)
    angle = math.atan2(head[1] - tail[1], head[0] - tail[0])
    for spread in (-0.42, 0.42):
        drawing.line(
            part,
            [
                (
                    head[0] - math.cos(angle + spread) * size_m,
                    head[1] - math.sin(angle + spread) * size_m,
                ),
                head,
            ],
            colour=colour,
            weight_mm=0.5,
        )


def _significant_corners(ring: Sequence[Point], threshold_deg: float = 12.0) -> list[int]:
    """Vertices where the boundary turns; a survey corner, not a digitising node."""
    keep: list[int] = []
    n = len(ring)
    for i in range(n):
        a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
        first = math.atan2(b[1] - a[1], b[0] - a[0])
        second = math.atan2(c[1] - b[1], c[0] - b[0])
        turn = abs(math.degrees(second - first)) % 360
        if turn > 180:
            turn = 360 - turn
        if turn > threshold_deg:
            keep.append(i)
    return keep if len(keep) >= 3 else list(range(n))


def _tree_id(tree: Tree) -> str:
    """What the tree is, as a schedule of the sheet's trees would read it:
    ``SA TREE Brush Box (Lophostemon confertus), canopy 4 m, 10 m high, trunk
    18 cm``. The sheet draws the canopy; the rest is here or nowhere."""
    name = (
        f"{tree.common} ({tree.species})"
        if tree.common and tree.species
        else tree.common or tree.species or ""
    )
    parts = [f"SA TREE {name}".rstrip()]
    if tree.canopy_from == NOMINAL:
        parts.append(f"canopy not recorded, {tree.canopy_m:g} m shown")
    else:
        how = " estimated" if tree.canopy_from == ESTIMATED else ""
        parts.append(f"canopy {round(tree.canopy_m, 1):g} m{how}")
    if tree.height_m:
        parts.append(f"{round(tree.height_m, 1):g} m high")
    if tree.dbh_cm:
        parts.append(f"trunk {round(tree.dbh_cm):g} cm")
    return ", ".join(parts)


@dataclass(frozen=True)
class _Solstices:
    """What the climate marks share: the site's centre, the bearing the sun
    rises at on each solstice, and the two arcs' radii, the summer outer."""

    centroid: Point
    winter: float
    summer: float
    outer: float
    inner: float


def _solstices(bundle: SiteBundle, centroid: Point, map_w: float, map_h: float) -> _Solstices:
    lat_r = math.radians(abs(bundle.centre_lonlat[1]))
    declination = math.radians(23.44)

    def rise_azimuth(dec: float) -> float:
        return math.degrees(math.acos(max(-1.0, min(1.0, math.sin(dec) / math.cos(lat_r)))))

    outer = min(map_w, map_h) * 0.42
    return _Solstices(
        centroid, rise_azimuth(declination), rise_azimuth(-declination), outer, outer * 0.72
    )


def _on_arc(frame: Frame, centroid: Point, bearing: float, radius: float) -> Point:
    dx, dy = frame.direction(bearing)
    return (centroid[0] + dx * radius, centroid[1] + dy * radius)


def _arc(
    frame: Frame, centroid: Point, rise: float, radius: float, step: float = 4.0
) -> list[Point]:
    """The sun's path from its rise bearing over north to its set, as points."""
    points: list[Point] = []
    bearing = rise
    while bearing >= -rise:
        points.append(_on_arc(frame, centroid, bearing, radius))
        bearing -= step
    return points


def _angle_of(frame: Frame, bearing: float) -> float:
    """A compass bearing as the project frame's own angle, from +x anticlockwise."""
    dx, dy = frame.direction(bearing)
    return math.atan2(dy, dx)


def _solstice_hours(lat_deg: float) -> tuple[list[tuple[float, str]], list[tuple[float, str]]]:
    """The sun's bearing at each solar hour it is up on the two solstices,
    winter then summer, with the hour's name."""
    phi = math.radians(lat_deg)
    winter_dec = 23.44 if lat_deg < 0 else -23.44

    def marks_for(dec_deg: float) -> list[tuple[float, str]]:
        dec = math.radians(dec_deg)
        out: list[tuple[float, str]] = []
        for hour in range(5, 20):
            h = math.radians((hour - 12) * 15)
            up = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(h) > 0.02
            if not up:
                continue
            az = (
                math.degrees(
                    math.atan2(
                        math.sin(h), math.cos(h) * math.sin(phi) - math.tan(dec) * math.cos(phi)
                    )
                )
                + 180
            )
            if az > 180:
                az -= 360
            label = f"{hour}AM" if hour < 12 else "12PM" if hour == 12 else f"{hour - 12}PM"
            out.append((az, label))
        return out

    return marks_for(winter_dec), marks_for(-winter_dec)


def _climate_radius(
    drawing: Drawing, bundle: SiteBundle, frame: Frame, centroid: Point, site: Sequence[Point]
) -> float:
    """The climate circle's radius: clear of the lot with room for the suns'
    names inside it, and short of the sheet's edge with the winds' names and
    north outside it."""
    mm = drawing.mm
    reach = max((math.dist(centroid, pt) for pt in site), default=mm(20))
    cx, cy = _sheet_mm(bundle, frame, centroid)
    room = min(cx, MAP_WIDTH_MM - cx, cy, MAP_HEIGHT_MM - cy) - (5 + 16)
    wanted = max(reach * 1.3, reach + mm(17 + 17 + 13.8 + 30 + 7))
    return max(mm(40), min(wanted, mm(room)))


def _suns(
    drawing: Drawing,
    frame: Frame,
    placer: Placer,
    look: themes.SiteLook,
    sol: _Solstices,
    lat_deg: float,
) -> None:
    """The sun paths and the four suns, in the theme's hand."""
    mm = drawing.mm
    c = sol.centroid
    suns = (
        (sol.winter, sol.inner, "WINTER\nSUNRISE", "W\nAM"),
        (-sol.winter, sol.inner, "WINTER\nSUNSET", "W\nPM"),
        (sol.summer, sol.outer, "SUMMER\nSUNRISE", "S\nAM"),
        (-sol.summer, sol.outer, "SUMMER\nSUNSET", "S\nPM"),
    )
    summer_arc = _arc(frame, c, sol.summer, sol.outer)
    winter_arc = _arc(frame, c, sol.winter, sol.inner)

    if look.sun == "discs":
        # Winter inner, summer outer, discs with rays at rise and set, N at the top.
        drawing.line("Sun path", summer_arc, colour=look.sun_pen, weight_mm=0.9)
        drawing.line("Sun path", winter_arc, colour=look.sun_pen, weight_mm=0.9, dashed=True)
        for bearing, radius, _name, short in suns:
            at = _on_arc(frame, c, bearing, radius)
            for degrees in range(0, 360, 30):
                theta = math.radians(degrees)
                drawing.line(
                    "Sun path",
                    [
                        (at[0] + mm(6.0) * math.cos(theta), at[1] + mm(6.0) * math.sin(theta)),
                        (at[0] + mm(10.0) * math.cos(theta), at[1] + mm(10.0) * math.sin(theta)),
                    ],
                    colour=look.sun_pen,
                    weight_mm=1.0,
                )
            drawing.circle("Sun path", at, mm(6.0), colour=look.sun_fill, fill=look.sun_fill)
            drawing.text(
                "Sun path",
                short,
                (at[0], at[1] - mm(SUN_MM * 0.9)),
                height_mm=SUN_MM,
                colour=look.sun_ink,
            )
            placer.reserve(at[0], at[1], mm(22), mm(22))
        north = _on_arc(frame, c, 0.0, sol.outer)
        drawing.circle("Sun path", north, mm(6.0), colour=look.sun_fill, fill=look.sun_fill)
        drawing.text(
            "Sun path",
            "N",
            (north[0], north[1] - mm(SUN_MM * 0.45)),
            height_mm=SUN_MM,
            colour=look.sun_ink,
        )
        return

    if look.sun == "circle":
        return  # drawn with the climate circle, below

    if look.sun == "crown":
        drawing.line("Sun path", summer_arc, colour=look.sun_pen, weight_mm=0.7)
        drawing.line("Sun path", winter_arc, colour=look.sun_pen, weight_mm=0.7, dashed=True)
    elif look.sun == "drawn":
        # The office's drawn suns sit on dashed arcs, summer dashed and winter
        # dotted; where the winds are drawn too, the summer ring goes on round
        # the side the sun never reaches, dashed in the wind's pen.
        drawing.line("Sun path", summer_arc, colour=look.sun_pen, weight_mm=0.5, dashed=True)
        drawing.line("Sun path", winter_arc, colour=look.sun_pen, weight_mm=0.5, dotted=True)
        if look.wind == "drawn":
            rest = [
                _on_arc(frame, c, b, sol.outer)
                for b in range(int(sol.summer) + 4, int(360 - sol.summer) - 3, 4)
            ]
            drawing.line("Winds", rest, colour=look.wind_pen, weight_mm=0.5, dashed=True)
    elif look.sun == "band":
        # Each solstice's path a crescent, deepest at noon, in the yellow
        # between its ends' colour and its middle's, laid over the paper at
        # half strength.
        colour = themes.blend(themes.blend(look.sun_band[0], look.sun_band[1], 0.5), "#ffffff", 0.5)
        for az, radius in ((sol.summer, sol.outer), (sol.winter, sol.inner)):
            start = _angle_of(frame, az)
            ring = marks.crescent(c, radius, start, start + 2 * math.radians(az), mm(16))
            drawing.fill("Sun path", [ring], colour, contour=colour, element_id="SA SUN PATH")

    if look.sun_hours:
        winter_hours, summer_hours = _solstice_hours(lat_deg)
        for hours, radius, label_radius, edge in (
            (winter_hours, sol.inner, sol.inner - mm(10), sol.winter),
            (summer_hours, sol.outer, sol.outer + mm(10), sol.summer),
        ):
            for az, label in hours:
                if abs(abs(az) - edge) < 9:
                    continue
                at = _on_arc(frame, c, az, radius)
                drawing.circle(
                    "Sun path", at, mm(2), colour=look.sun_pen, fill="#ffffff", weight_mm=0.35
                )
                lx, ly = _on_arc(frame, c, az, label_radius)
                drawing.text(
                    "Sun path",
                    label,
                    (lx, ly - mm(SUN_MM * 0.5)),
                    height_mm=SUN_MM,
                    colour=look.sun_ink,
                )

    for seed, (bearing, radius, name, _short) in enumerate(suns, start=1):
        at = _on_arc(frame, c, bearing, radius)
        if look.sun == "crown":
            ring, inner_r = marks.crown_sun(at, mm(1.0), seed)
            drawing.fill(
                "Sun path",
                [ring],
                look.sun_fill,
                contour=look.sun_edge,
                weight_mm=0.35,
                element_id="SA SUN",
            )
            drawing.circle(
                "Sun path",
                at,
                inner_r,
                colour=look.sun_edge,
                fill=look.sun_fill,
                weight_mm=0.35,
                element_id="SA SUN",
            )
            below = mm(28)
        elif look.sun == "drawn":
            for outer, holes in marks.polygons(marks.SUN, mm(13), at):
                drawing.fill(
                    "Sun path",
                    [outer, *holes],
                    look.sun_ink,
                    contour=look.sun_ink,
                    weight_mm=0.35,
                    element_id="SA SUN",
                )
            below = mm(21)
        else:
            for outer, holes in marks.polygons(marks.RAY_SUN, mm(8), at):
                drawing.fill(
                    "Sun path",
                    [outer, *holes],
                    look.sun_fill,
                    contour=look.sun_fill,
                    element_id="SA SUN",
                )
            below = mm(16)
        drawing.text(
            "Sun path", name, (at[0], at[1] - below), height_mm=SUN_MM, colour=look.sun_ink
        )
        placer.reserve(at[0], at[1] - below / 2, mm(46), below * 2 + mm(16))
    # North sits just beyond the summer noon mark.
    north = _on_arc(frame, c, 0.0, sol.outer + mm(24))
    drawing.circle(
        "Sun path",
        north,
        mm(6.4),
        colour=look.sun_edge,
        fill="#ffffff",
        weight_mm=0.35,
        element_id="SA NORTH",
    )
    drawing.text(
        "Sun path",
        "N",
        (north[0], north[1] - mm(SUN_MM * 0.45)),
        height_mm=SUN_MM,
        colour=look.sun_ink,
    )


def _winds(
    drawing: Drawing,
    bundle: SiteBundle,
    frame: Frame,
    placer: Placer,
    look: themes.SiteLook,
    sol: _Solstices,
) -> None:
    """The prevailing winds, in the theme's hand."""
    mm = drawing.mm
    c = sol.centroid
    if look.wind == "banners":
        # The office's white banners at the reference sheet's corners, pointing in.
        for x_mm, y_mm, label in (
            (MAP_WIDTH_MM - 95, 55, "NE SUMMER SEA BREEZE"),
            (MAP_WIDTH_MM - 85, MAP_HEIGHT_MM - 75, "S & SE COOL SUMMER WIND"),
            (90, MAP_HEIGHT_MM - 60, "W & SW WINTER WINDS"),
        ):
            at = _map_point(bundle, frame, x_mm, y_mm)
            width, height = _text_width_m(drawing, label, STREET_MM) + mm(22), mm(14)
            angle = math.atan2(c[1] - at[1], c[0] - at[0])
            if angle > math.pi / 2 or angle < -math.pi / 2:
                angle += math.pi
            dx, dy = math.cos(angle), math.sin(angle)
            px, py = -dy, dx
            facing = 1.0 if math.cos(angle - math.atan2(c[1] - at[1], c[0] - at[0])) > 0 else -1.0
            hw, hh = width / 2, height / 2
            banner = [
                (at[0] - dx * hw * facing - px * hh, at[1] - dy * hw * facing - py * hh),
                (
                    at[0] + dx * (hw - mm(6)) * facing - px * hh,
                    at[1] + dy * (hw - mm(6)) * facing - py * hh,
                ),
                (at[0] + dx * hw * facing, at[1] + dy * hw * facing),
                (
                    at[0] + dx * (hw - mm(6)) * facing + px * hh,
                    at[1] + dy * (hw - mm(6)) * facing + py * hh,
                ),
                (at[0] - dx * hw * facing + px * hh, at[1] - dy * hw * facing + py * hh),
            ]
            drawing.fill("Winds", [banner], "#ffffff", contour=look.wind_pen)
            drawing.text(
                "Winds",
                label,
                (at[0] - px * mm(1.2), at[1] - py * mm(1.2)),
                height_mm=STREET_MM,
                angle_rad=angle,
                colour=look.climate_ink,
            )
            placer.reserve(at[0], at[1], width, height)
        return

    if look.wind == "circle":
        return  # drawn with the climate circle, below

    if look.wind == "strands":
        # Three of the sheet's hand-drawn arrows side by side, bowing
        # alternately, from where a ray along the wind's bearing meets a
        # frame kept clear of the sheet's edge, pointing in at the site.
        cx, cy = _sheet_mm(bundle, frame, c)
        # A wind and a sun can come from the same quarter (the SE summer
        # wind and the summer sunrise do); the strand then stops short of
        # the sun rather than running through it.
        suns = [
            _on_arc(frame, c, b, r)
            for b, r in (
                (sol.winter, sol.inner),
                (-sol.winter, sol.inner),
                (sol.summer, sol.outer),
                (-sol.summer, sol.outer),
            )
        ]

        def clear_of_suns(pt: Point) -> bool:
            return all(math.dist(pt, (sx, sy + mm(8))) > mm(36) for sx, sy in suns)

        for bearing, label in WINDS:
            a = math.radians(bearing)
            ux, uy = math.sin(a), -math.cos(a)
            x0, x1, y0, y1 = 90.0, MAP_WIDTH_MM - 90.0, 55.0, MAP_HEIGHT_MM - 60.0
            tx = (x1 - cx) / ux if ux > 0 else (x0 - cx) / ux if ux < 0 else math.inf
            ty = (y1 - cy) / uy if uy > 0 else (y0 - cy) / uy if uy < 0 else math.inf
            t = max(0.0, min(tx, ty))
            entry = _map_point(bundle, frame, cx + ux * t, cy + uy * t)
            dx, dy = c[0] - entry[0], c[1] - entry[1]
            length = math.hypot(dx, dy) or 1.0
            u = (dx / length, dy / length)
            n = (-u[1], u[0])
            for off, bow, strand in ((-14.0, 3.2, 84.0), (0.0, -3.2, 96.0), (14.0, 3.2, 76.0)):
                start = (entry[0] + n[0] * mm(off), entry[1] + n[1] * mm(off))
                while strand > 40.0 and not all(
                    clear_of_suns(
                        (start[0] + u[0] * mm(strand) * f, start[1] + u[1] * mm(strand) * f)
                    )
                    for f in (0.6, 0.8, 1.0)
                ):
                    strand -= 4.0
                ring = marks.sketch_arrow(
                    start, u, mm(strand), bow=mm(bow), w0=mm(1.6), w1=mm(4.6), head=mm(11)
                )
                drawing.fill(
                    "Winds",
                    [ring],
                    "#ffffff",
                    contour=look.wind_pen,
                    weight_mm=0.35,
                    element_id="SA WIND",
                )
            at = (entry[0] - u[0] * mm(18), entry[1] - u[1] * mm(18))
            drawing.text("Winds", label, at, height_mm=STREET_MM, colour=look.climate_ink)
            placer.reserve(at[0], at[1], mm(40), mm(14))
        return

    # The office's winds on the summer ring, each pointing in at the site,
    # its name just outside the ring: drawn, the wind solid in the ink of its
    # name; banded, three white arrows on a blue crescent over its quarter.
    wind_outer = sol.outer + mm(7.5)
    for bearing, label in WINDS:
        at = _on_arc(frame, c, bearing, sol.outer)
        inward = math.atan2(c[1] - at[1], c[0] - at[0])
        if look.wind == "drawn":
            for outer, holes in marks.polygons(marks.WIND, mm(17), at, inward):
                drawing.fill(
                    "Winds",
                    [outer, *holes],
                    look.climate_ink,
                    contour=look.climate_ink,
                    weight_mm=0.35,
                    element_id="SA WIND",
                )
        else:
            from_angle = _angle_of(frame, bearing + 24.0)
            ring = marks.crescent(
                c, wind_outer, from_angle, from_angle + math.radians(48.0), mm(15)
            )
            colour = themes.blend(look.wind_band, "#ffffff", 0.45)
            drawing.fill("Winds", [ring], colour, contour=colour, element_id="SA WIND")
            for off in (-24.0 * 0.42, 0.0, 24.0 * 0.42):
                depth = mm(15) * math.sin(math.pi * (0.5 + off / 48.0))
                spot = _on_arc(frame, c, bearing + off, wind_outer - depth / 2)
                towards = math.atan2(c[1] - spot[1], c[0] - spot[0])
                for outer, holes in marks.polygons(marks.ARROW, mm(5.5), spot, towards):
                    drawing.fill(
                        "Winds",
                        [outer, *holes],
                        "#ffffff",
                        contour="#ffffff",
                        element_id="SA WIND ARROW",
                    )
        name_at = _on_arc(frame, c, bearing, wind_outer + mm(16))
        drawing.text("Winds", label, name_at, height_mm=STREET_MM, colour=look.climate_ink)
        placer.reserve(name_at[0], name_at[1], mm(40), mm(14))


def _climate_circle(
    drawing: Drawing,
    bundle: SiteBundle,
    frame: Frame,
    placer: Placer,
    look: themes.SiteLook,
    sol: _Solstices,
    site: Sequence[Point],
) -> None:
    """One dashed ring about the site: the winds named around it outside over
    hatched quarters, the four suns on the solstices' paths inside it with
    their names, and north an arrowhead standing out of it."""
    if look.sun != "circle" and look.wind != "circle":
        return
    mm = drawing.mm
    c = sol.centroid
    radius = _climate_radius(drawing, bundle, frame, c, site)
    drawing.circle(
        "Climate", c, radius, colour=look.sun_pen, dashed=True, weight_mm=0.6, segments=72
    )
    if look.sun == "circle":
        r_summer = radius - mm(17)
        r_winter = r_summer - mm(17)
        drawing.line(
            "Climate", _arc(frame, c, sol.summer, r_summer), colour=look.sun_pen, weight_mm=0.7
        )
        drawing.line(
            "Climate",
            _arc(frame, c, sol.winter, r_winter),
            colour=look.sun_pen,
            weight_mm=0.7,
            dashed=True,
        )
        for az, r, name in (
            (sol.winter, r_winter, "WINTER\nSUNRISE"),
            (-sol.winter, r_winter, "WINTER\nSUNSET"),
            (sol.summer, r_summer, "SUMMER\nSUNRISE"),
            (-sol.summer, r_summer, "SUMMER\nSUNSET"),
        ):
            at = _on_arc(frame, c, az, r)
            disc, rays = marks.plain_sun(at, mm(2.4))
            drawing.fill(
                "Climate",
                [disc],
                look.sun_fill,
                contour=look.sun_edge,
                weight_mm=0.35,
                element_id="SA SUN",
            )
            for a, b in rays:
                drawing.line("Climate", [a, b], colour=look.sun_edge, weight_mm=0.35)
            name_at = _on_arc(frame, c, az, r - mm(29))
            drawing.text(
                "Climate",
                name,
                (name_at[0], name_at[1] + mm(SUN_MM * 0.6)),
                height_mm=SUN_MM,
                colour=look.sun_ink,
            )
            placer.reserve(name_at[0], name_at[1], mm(30), mm(14))
        base = _on_arc(frame, c, 0.0, radius + mm(1))
        tip = _on_arc(frame, c, 0.0, radius + mm(12))
        nx, ny = frame.direction(90.0)
        drawing.fill(
            "Climate",
            [
                [
                    (base[0] - nx * mm(3), base[1] - ny * mm(3)),
                    tip,
                    (base[0] + nx * mm(3), base[1] + ny * mm(3)),
                ]
            ],
            look.sun_pen,
            contour=look.sun_pen,
            element_id="SA NORTH",
        )
        n_at = _on_arc(frame, c, 0.0, radius + mm(17.5))
        drawing.text(
            "Climate",
            "N",
            (n_at[0], n_at[1] - mm(SUN_MM * 0.45)),
            height_mm=SUN_MM,
            colour=look.sun_ink,
        )
    if look.wind == "circle":
        band = mm(5)
        for bearing, label in WINDS:
            outer = [_on_arc(frame, c, bearing - 22 + k * 4, radius + band) for k in range(12)]
            inner = [_on_arc(frame, c, bearing + 22 - k * 4, radius) for k in range(12)]
            drawing.fill(
                "Climate",
                [[*outer, *inner]],
                look.wind_pen,
                contour=look.wind_pen,
                hatch=True,
                weight_mm=0.35,
                element_id="SA WIND",
            )
            name_at = _on_arc(frame, c, bearing, radius + band + mm(2.4 + SUN_MM * 0.6))
            tangent = _angle_of(frame, bearing) + math.pi / 2
            while tangent > math.pi / 2:
                tangent -= math.pi
            while tangent <= -math.pi / 2:
                tangent += math.pi
            drawing.text(
                "Climate",
                label.replace("\n", " "),
                name_at,
                height_mm=STREET_MM,
                angle_rad=tangent,
                colour=look.climate_ink,
            )
            placer.reserve(name_at[0], name_at[1], mm(50), mm(10))


def site_drawing(
    bundle: SiteBundle,
    frame: Frame,
    *,
    future: Sequence[Envelope] = (),
    theme: str | themes.SiteTheme | None = None,
) -> Drawing:
    """The site sheet: boundary with dimensions and levels, fall, sun path,
    prevailing winds, neighbours, street furniture, noise and access.

    ``future`` is the future context, already worked out in this frame: each
    envelope's footprint is drawn dashed in magenta with what the controls
    allow written in it, on the Context layer with the buildings that stand
    there today.

    ``theme`` is the site theme it is drawn in (``site.theme``): which marks
    stand for the sun and the winds, how the zones, the buildings and the
    site are drawn, and in which inks. What is drawn is the same in every
    theme.
    """
    st = theme if isinstance(theme, themes.SiteTheme) else themes.site_theme(theme)
    look = st.look
    base = themes.theme(st.base)
    drawing = Drawing(bundle.scale, SITE_WORD, text_scale=look.text_scale)
    placer = Placer()
    mm = drawing.mm
    on_paper = look.ground == "paper"

    site_rings = [frame.ring(ring) for ring in bundle.site_rings]
    site = max(site_rings, key=lambda r: abs(ring_area(r))) if site_rings else []
    centroid = ring_centroid(site) if site else frame.project(*bundle.centre_lonlat)
    map_w = MAP_WIDTH_MM * bundle.scale / 1000.0
    map_h = MAP_HEIGHT_MM * bundle.scale / 1000.0

    # Reserve the fixed furniture first so every later label keeps clear.
    placer.reserve(centroid[0], centroid[1], mm(56), mm(24))
    photo = False
    if not on_paper:
        # The site keeps its own colours whatever is done to the rest.
        photo = _aerial(
            drawing,
            bundle,
            frame,
            grey=look.aerial == "grey",
            veil=look.veil,
            keep=[list(ring) for ring in bundle.site_rings],
        )

    zone_rings = [
        (feature["properties"].get("SYM_CODE"), rings_of(feature.get("geometry")), feature)
        for feature in bundle.zoning["features"]
    ]

    def zone_code_at(lon: float, lat: float) -> str | None:
        for code, rings, _feature in zone_rings:
            if code and any(point_in_ring(lon, lat, ring) for ring in rings):
                return str(code)
        return None

    def category_of(code: str | None) -> themes.Category | None:
        identifier = curate.zone_to_category(code)
        return base.category(identifier) if identifier else None

    rows: list[Row] = []
    zone_rows: list[Row] = []
    present: dict[str, themes.Category] = {}
    field = _map_rectangle(bundle, frame)

    # The zoning: its boundaries, hatched over the aerial in the family
    # colours, filled in the ePlanning colours, filled on the lots as the
    # theme's pale grounds, or not drawn.
    if look.zones == "outline":
        for _code, rings, _feature in zone_rings:
            for ring in rings:
                drawing.line("Zoning", frame.ring(ring), colour="#bbbbbb", closed=True)
    elif look.zones in ("hatch", "lep"):
        lep_seen: dict[str, str] = {}
        for code, rings, feature in zone_rings:
            if not code or not rings:
                continue
            projected = _clipped([frame.ring(r) for r in rings], field)
            if not projected:
                continue
            # The site keeps the photograph's own colours: its lot is cut out
            # of the zone it lies in, a hole in the wash and the hatch alike.
            if site and any(point_in_ring(*centroid, ring) for ring in projected):
                projected.append(list(site))
            if look.zones == "lep":
                label = _lep_label(str(code), feature["properties"].get("LAY_CLASS"))
                lep_seen[str(code)] = label
                colour = themes.zone_fill(str(code))
                drawing.fill(
                    "Zoning", projected, colour, contour=colour, wash=True, element_id=f"SA {label}"
                )
                continue
            cat = category_of(str(code))
            if cat is None:
                continue
            present[cat.id] = cat
            ink = cat.stroke or cat.fill
            if look.zone_tint > 0:
                drawing.fill(
                    "Zoning",
                    projected,
                    cat.fill,
                    contour=ink,
                    wash=True,
                    element_id=f"SA {cat.label} ({code})",
                    texture="lines",
                    texture_colour=ink,
                )
            else:
                drawing.fill(
                    "Zoning",
                    projected,
                    ink,
                    contour=ink,
                    hatch=True,
                    weight_mm=0.2,
                    element_id=f"SA {cat.label} ({code})",
                )
        for code, label in sorted(lep_seen.items(), key=lambda pair: _lep_order(pair[0])):
            zone_rows.append(Row("wash", themes.zone_fill(code), None, label))
        for cat in base.categories:
            if cat.id in present:
                ink = cat.stroke or cat.fill
                zone_rows.append(
                    Row("wash", cat.fill, ink, cat.label, "lines", ink)
                    if look.zone_tint > 0
                    else Row("hatch", ink, ink, cat.label)
                )
    elif look.zones == "fill":
        # Each lot in its zone's ground, so the roads stay white; water drawn whole.
        for feature in bundle.all_lots["features"]:
            lot_rings = rings_of(feature.get("geometry"))
            if not lot_rings:
                continue
            lon, lat = ring_centroid(lot_rings[0])
            if site and point_in_ring(*frame.project(lon, lat), site):
                continue  # the site takes its own tint, below
            cat = category_of(zone_code_at(lon, lat))
            if cat is None or cat.id == "water":
                continue
            present[cat.id] = cat
            drawing.fill(
                "Zoning",
                [frame.ring(r) for r in lot_rings],
                cat.on_paper(),
                contour=look.lot_ink,
                weight_mm=look.lot_width_mm,
                element_id=f"SA {cat.label}",
                texture=cat.texture,
                texture_colour=cat.hatch_colour,
            )
        for code, rings, _feature in zone_rings:
            cat = category_of(str(code) if code else None)
            if cat is not None and cat.id == "water":
                present[cat.id] = cat
                water = _clipped([frame.ring(r) for r in rings], field)
                if water:
                    drawing.fill(
                        "Zoning",
                        water,
                        cat.on_paper(),
                        contour=cat.on_paper(),
                        element_id=f"SA {cat.label}",
                    )
        for cat in base.categories:
            if cat.id in present:
                zone_rows.append(_category_row(cat, on_paper=True, wash=False))

    if look.heritage:
        kinds: set[str] = set()
        for feature in bundle.heritage["features"]:
            rings = _clipped([frame.ring(r) for r in rings_of(feature.get("geometry"))], field)
            if not rings:
                continue
            conservation = "Conservation" in str(feature["properties"].get("LAY_CLASS") or "")
            ink = look.heritage_ink[1] if conservation else look.heritage_ink[0]
            kinds.add("area" if conservation else "item")
            drawing.fill(
                "Heritage",
                rings,
                ink,
                contour=ink,
                hatch=True,
                weight_mm=0.25,
                element_id="SA HERITAGE CONSERVATION AREA" if conservation else "SA HERITAGE ITEM",
            )
        if "item" in kinds:
            zone_rows.append(
                Row("hatch", look.heritage_ink[0], look.heritage_ink[0], "HERITAGE ITEM")
            )
        if "area" in kinds:
            zone_rows.append(
                Row(
                    "hatch",
                    look.heritage_ink[1],
                    look.heritage_ink[1],
                    "HERITAGE CONSERVATION AREA",
                )
            )

    for feature in bundle.all_lots["features"]:
        for ring in rings_of(feature.get("geometry")):
            drawing.line(
                "Cadastre",
                frame.ring(ring),
                colour=look.lot_ink,
                closed=True,
                weight_mm=look.lot_width_mm,
            )

    contours: list[tuple[float, list[Point]]] = []
    tagged: list[Point] = []
    for contour in bundle.contours:
        points = frame.ring(contour.coords)
        contours.append((contour.elevation, points))
        if not look.contours:
            continue
        drawing.line("Contours", points, colour=look.contour_ink)
        if len(points) < 3:
            continue
        at = _midpoint(points)
        if any(math.dist(at, t) < mm(45) for t in tagged):
            continue
        tagged.append(at)
        drawing.text(
            "Contours",
            f"RL {contour.elevation:.0f}",
            (at[0], at[1] + mm(1.4)),
            height_mm=SMALL_MM,
            angle_rad=_along(points),
            colour=look.contour_label_ink or INK,
        )

    if look.streets == "lines" or (not on_paper and not photo):
        for road in bundle.roads:
            drawing.line("Roads", frame.ring(road.coords), colour=base.road)
    _rail(
        drawing,
        "Roads",
        [frame.ring(line) for line in (*bundle.rail_lines.train, *bundle.rail_lines.tram)],
        base,
        0.5,
    )

    # Noise: one zigzag per main road, and the longest rail line.
    noisy: set[str] = set()
    for road in bundle.roads:
        if road.hierarchy > 4 or road.name in noisy:
            continue
        noisy.add(road.name)
        drawing.line(
            "Noise", _zigzag(frame.ring(road.coords), mm(1.1), mm(2.4)), colour=look.noise_pen
        )
    for group in (bundle.rail_lines.train, bundle.rail_lines.tram):
        if group:
            longest = max((frame.ring(line) for line in group), key=polyline_length)
            drawing.line("Noise", _zigzag(longest, mm(1.1), mm(2.4)), colour=look.noise_pen)

    for _name, coords in bundle.furniture.oneway_roads:
        points = frame.ring(coords)
        if len(points) < 2:
            continue
        i = len(points) // 2
        (ax, ay), (bx, by) = points[max(0, i - 1)], points[i]
        angle = math.atan2(by - ay, bx - ax)
        cx, cy = (ax + bx) / 2, (ay + by) / 2
        half = mm(3.5)
        _arrow(
            drawing,
            "Traffic",
            (cx - math.cos(angle) * half, cy - math.sin(angle) * half),
            (cx + math.cos(angle) * half, cy + math.sin(angle) * half),
            colour=base.road,
            size_m=mm(2.2),
        )

    shown: set[str] = set()
    for road in bundle.roads:
        if not road.lanes or road.hierarchy > 5 or road.name in shown:
            continue
        points = frame.ring(road.coords)
        if len(points) < 2:
            continue
        i = len(points) // 2
        (ax, ay), (bx, by) = points[max(0, i - 1)], points[i]
        angle = math.atan2(by - ay, bx - ax)
        spot = placer.place(
            (ax + bx) / 2, (ay + by) / 2, mm(10), mm(12), step=mm(4), max_radius=mm(12)
        )
        if spot is None:
            continue
        shown.add(road.name)
        lanes = min(4, road.lanes)
        across = (-math.sin(angle), math.cos(angle))
        for n in range(lanes):
            offset = (n - (lanes - 1) / 2) * mm(2.6)
            up = 1 if n % 2 == 0 else -1
            at = (spot[0] + across[0] * offset, spot[1] + across[1] * offset)
            tail = (at[0] - math.cos(angle) * mm(4) * up, at[1] - math.sin(angle) * mm(4) * up)
            head = (at[0] + math.cos(angle) * mm(4) * up, at[1] + math.sin(angle) * mm(4) * up)
            _arrow(drawing, "Traffic", tail, head, colour=base.road, size_m=mm(1.8))

    for utility in bundle.furniture.utilities:
        drawing.line(
            "Utilities",
            frame.ring(utility.coords),
            colour=UTILITY.get(utility.kind, "#9b59b6"),
            dashed=True,
            weight_mm=0.5,
        )

    for side, coords in bundle.furniture.parking_lanes:
        points = frame.ring(coords)
        for sign in (1, -1) if side == "both" else ((-1,) if side == "left" else (1,)):
            for (ax, ay), (bx, by) in pairwise(points):
                length = math.hypot(bx - ax, by - ay) or 1.0
                nx, ny = -(by - ay) / length * sign, (bx - ax) / length * sign
                off, width = mm(2.2), mm(2.4)
                bay = [
                    (ax + nx * off, ay + ny * off),
                    (bx + nx * off, by + ny * off),
                    (bx + nx * (off + width), by + ny * (off + width)),
                    (ax + nx * (off + width), ay + ny * (off + width)),
                ]
                if look.parking == "hatch":
                    drawing.fill(
                        "Parking", [bay], base.ink, contour=base.ink, hatch=True, weight_mm=0.2
                    )
                else:
                    drawing.fill("Parking", [bay], PARKING_PLUM, contour="#7a3c50")

    for coords in bundle.furniture.driveways:
        points = frame.ring(coords)
        if len(points) < 2:
            continue
        # The end further from the site is the street end.
        if math.dist(points[0], centroid) > math.dist(points[-1], centroid):
            tip, next_point = points[0], points[1]
        else:
            tip, next_point = points[-1], points[-2]
        angle = math.atan2(next_point[1] - tip[1], next_point[0] - tip[0])
        across = (-math.sin(angle), math.cos(angle))
        drawing.fill(
            "Access",
            [
                [
                    (
                        tip[0] + across[0] * mm(3.4) - math.cos(angle) * mm(3),
                        tip[1] + across[1] * mm(3.4) - math.sin(angle) * mm(3),
                    ),
                    (
                        tip[0] - across[0] * mm(3.4) - math.cos(angle) * mm(3),
                        tip[1] - across[1] * mm(3.4) - math.sin(angle) * mm(3),
                    ),
                    (tip[0] + math.cos(angle) * mm(3), tip[1] + math.sin(angle) * mm(3)),
                ]
            ],
            DRIVEWAY_YELLOW,
            contour="#c9bb00",
        )

    # The neighbours: a grey mass over the aerial, edged in the road grey, so
    # the built form reads at a glance; a white outline over the photograph's
    # own roofs; filled in the zone family's strong colour with a white edge;
    # or white in a heavy outline of the family's ink, finely hatched in it,
    # so it stands clear of its tinted ground and of the white roads alike.
    quiet = "#c2c2bc"
    for building in bundle.furniture.buildings:
        if len(building.ring) < 3:
            continue
        ring = frame.ring(building.ring)
        if look.buildings == "mass":
            drawing.fill("Buildings", [ring], BUILDING_GREY, contour=base.road, weight_mm=0.18)
        elif look.buildings == "outline":
            drawing.line(
                "Buildings", ring, colour="#ffffff", closed=True, weight_mm=look.building_edge_mm
            )
        else:
            cat = category_of(zone_code_at(building.lon, building.lat))
            on_site = bool(site) and point_in_ring(*frame.project(building.lon, building.lat), site)
            figure = quiet if cat is None or on_site or not cat.figure else cat.figure
            if look.buildings == "colour":
                drawing.fill(
                    "Buildings",
                    [ring],
                    figure,
                    contour="#ffffff",
                    weight_mm=look.building_edge_mm,
                    element_id="SA BUILDINGS",
                )
            else:
                # The building on the site itself stands plain in the site's
                # tint: its hatch would be drawn over the tint, not under it.
                drawing.fill(
                    "Buildings",
                    [ring],
                    "#ffffff",
                    contour=figure,
                    weight_mm=look.building_edge_mm,
                    element_id="SA BUILDINGS",
                    texture=None if on_site else "lines",
                    texture_colour=figure,
                )
    # Trees at the size of their canopy, on the ground. A size somebody
    # recorded -- the council's inventory, or a mapper's measurement -- has a
    # solid edge; the nominal canopy of a tree nobody measured is dashed, so the
    # sheet never claims a size it does not have. A wash, so the kerb and the
    # parking under a canopy still show; never smaller than a dot a reader can
    # find, and never so big that a register's typing error covers the sheet.
    for tree in bundle.furniture.trees:
        at = frame.project(tree.lon, tree.lat)
        drawing.circle(
            "Trees",
            at,
            min(mm(45), max(mm(1.6), tree.canopy_m / 2.0)),
            colour=TREE_EDGE,
            fill=TREE_GREEN,
            wash=True,
            dashed=tree.canopy_from == NOMINAL,
            weight_mm=0.25,
            element_id=_tree_id(tree),
        )
        drawing.circle(
            "Trees",
            at,
            mm(0.55),
            colour=TRUNK_GREEN,
            fill=TRUNK_GREEN,
            segments=12,
            element_id="SA TREE TRUNK",
        )
    for lon, lat in bundle.furniture.hydrants:
        drawing.circle(
            "Services", frame.project(lon, lat), mm(1.4), colour=HYDRANT_BLUE, fill=HYDRANT_BLUE
        )
    for lon, lat in bundle.furniture.power_poles:
        at = frame.project(lon, lat)
        drawing.line(
            "Services", [(at[0] - mm(1.8), at[1]), (at[0] + mm(1.8), at[1])], colour=POLE_GREY
        )
        drawing.circle("Services", at, mm(0.9), colour=POLE_GREY)
    for lon, lat in bundle.furniture.street_lamps:
        at = frame.project(lon, lat)
        drawing.circle("Services", at, mm(1), colour="#a8860b", fill=LAMP_YELLOW)
        for degrees in range(0, 360, 60):
            theta = math.radians(degrees)
            drawing.line(
                "Services",
                [
                    (at[0] + mm(1.3) * math.cos(theta), at[1] + mm(1.3) * math.sin(theta)),
                    (at[0] + mm(2.1) * math.cos(theta), at[1] + mm(2.1) * math.sin(theta)),
                ],
                colour="#a8860b",
            )
    # The future context: the lowest tier's footprint, which is the largest,
    # and the upper tiers inside it where the envelope steps.
    for envelope in future:
        for tier in envelope.tiers:
            for outline in tier.rings:
                drawing.line(
                    "Future",
                    list(outline),
                    colour=FUTURE_MAGENTA,
                    dashed=True,
                    weight_mm=0.5,
                    closed=True,
                )
        lines = envelope.caption.split("\n")
        at = ring_centroid(list(envelope.footprint))
        width = _text_width_m(drawing, max(lines, key=len), NEIGHBOUR_MM)
        height = mm(NEIGHBOUR_MM * 1.3) * len(lines)
        spot = placer.place(at[0], at[1], width, height, step=mm(2), max_radius=mm(12))
        if spot:
            drawing.text(
                "Future", "\n".join(lines), spot, height_mm=NEIGHBOUR_MM, colour=FUTURE_MAGENTA
            )
    solid = base.roundel == "solid"
    for stop in bundle.bus_stops:
        at = frame.project(stop.lon, stop.lat)
        if solid:
            drawing.circle("Bus stops", at, mm(4), colour=base.transit, fill=base.transit)
            drawing.text(
                "Bus stops", "B", (at[0], at[1] - mm(1.6)), height_mm=LABEL_MM, colour="#ffffff"
            )
        else:
            drawing.circle("Bus stops", at, mm(4), colour=base.transit, fill="#ffffff")
            drawing.text("Bus stops", "B", (at[0], at[1] - mm(1.6)), height_mm=LABEL_MM)
        placer.reserve(at[0], at[1], mm(8), mm(8))

    # Neighbours: number, storeys where known, zone -- within 70 m of the boundary.
    levelled = [
        (frame.project(b.lon, b.lat), b.levels) for b in bundle.furniture.buildings if b.levels
    ]

    def storeys_at(at: Point) -> int | None:
        best, best_d = None, 25.0
        for where, levels in levelled:
            d = math.dist(where, at)
            if d < best_d:
                best, best_d = levels, d
        return best

    def distance_to_site(at: Point) -> float:
        if not site:
            return math.inf
        best = math.inf
        for a, b in zip(site, [*site[1:], site[0]], strict=True):
            dx, dy = b[0] - a[0], b[1] - a[1]
            l2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((at[0] - a[0]) * dx + (at[1] - a[1]) * dy) / l2)) if l2 else 0.0
            best = min(best, math.dist(at, (a[0] + t * dx, a[1] + t * dy)))
        return best

    near = sorted(
        ((distance_to_site(frame.project(n.lon, n.lat)), n) for n in bundle.neighbours),
        key=lambda pair: pair[0],
    )
    for distance, neighbour in near:
        if distance > 70.0:
            break
        at = frame.project(neighbour.lon, neighbour.lat)
        if site and point_in_ring(at[0], at[1], site):
            continue
        lines = [neighbour.house_number.upper()]
        storeys = storeys_at(at)
        if storeys:
            lines.append(f"{storeys} STOREY")
        zone = curate.zone_label(zone_code_at(neighbour.lon, neighbour.lat))
        if zone and look.neighbour_zone:
            lines.append(zone)
        width = _text_width_m(drawing, max(lines, key=len), NEIGHBOUR_MM)
        height = mm(NEIGHBOUR_MM * 1.3) * len(lines)
        spot = placer.place(at[0], at[1], width, height, step=mm(4), max_radius=mm(30))
        if spot:
            drawing.text(
                "Neighbours",
                "\n".join(lines),
                spot,
                height_mm=NEIGHBOUR_MM,
                colour=look.neighbour_ink,
            )

    _street_labels(
        drawing,
        frame,
        bundle.roads,
        placer,
        part="Road names",
        height_mm=STREET_MM * 1.15,
        arrows=look.street_labels == "band",
        ink=look.street_ink,
    )

    # The site: boundary, corners, dimensions, levels, fall and area. On
    # paper the lot takes the theme's site tint, as the context sheet's does.
    if on_paper:
        site_cat = base.category("site")
        for ring in site_rings:
            drawing.fill(
                "Site", [ring], site_cat.on_paper(), contour=look.site, element_id="SA SITE"
            )
    for ring in site_rings:
        drawing.line(
            "Site", ring, colour=look.site, dashed=True, weight_mm=look.site_weight_mm, closed=True
        )
    for feature in bundle.site_lots["features"]:
        for ring in rings_of(feature.get("geometry")):
            drawing.line("Site lots", frame.ring(ring), colour=look.site, closed=True)

    # Levels across the slope, between the contours that bracket each corner.
    described = terrain.described(bundle.contours)
    ground = Ground(contours, interval_m=described[0]) if described else None
    corner_levels: list[tuple[int, float]] = []
    if site:
        corners = _significant_corners(site)
        for i in corners:
            drawing.circle("Site", site[i], mm(1.7), colour=look.site)
        for k, i0 in enumerate(corners):
            i1 = corners[(k + 1) % len(corners)]
            length = 0.0
            i = i0
            while i != i1:
                j = (i + 1) % len(site)
                length += math.dist(site[i], site[j])
                i = j
            if length < 3.0 or math.dist(site[i0], site[i1]) < mm(14):
                continue
            a, b = site[i0], site[i1]
            angle = _along([a, b])
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            ox, oy = mx - centroid[0], my - centroid[1]
            norm = math.hypot(ox, oy) or 1.0
            label = f"SB {length:.2f}"
            spot = placer.place(
                mx + ox / norm * mm(5),
                my + oy / norm * mm(5),
                _text_width_m(drawing, label, STREET_MM),
                mm(6.4),
                step=mm(4),
                max_radius=mm(16),
                angle=angle,
            )
            if spot:
                drawing.text(
                    "Dimensions",
                    label,
                    spot,
                    height_mm=STREET_MM,
                    angle_rad=angle,
                    colour=look.dimension_ink,
                )
        for i in corners:
            level = ground.at(site[i]) if ground is not None else None
            if level is None:
                continue
            corner_levels.append((i, level))
            x, y = site[i]
            ox, oy = x - centroid[0], y - centroid[1]
            norm = math.hypot(ox, oy) or 1.0
            label = f"RL {level:.2f}"
            spot = placer.place(
                x + ox / norm * mm(10),
                y + oy / norm * mm(10) - mm(3.5),
                _text_width_m(drawing, label, STREET_MM),
                mm(6.4),
                step=mm(4),
                max_radius=mm(18),
            )
            if spot:
                drawing.text("Levels", label, spot, height_mm=STREET_MM, colour=look.level_ink)

    fall: float | None = None
    fall_angle = 0.0
    if len(corner_levels) >= 2:
        hi = max(corner_levels, key=lambda pair: pair[1])
        lo = min(corner_levels, key=lambda pair: pair[1])
        if hi[0] != lo[0] and hi[1] - lo[1] >= 0.3:
            a, b = site[hi[0]], site[lo[0]]
            angle = math.atan2(b[1] - a[1], b[0] - a[0])
            shrink = mm(8)
            _arrow(
                drawing,
                "Levels",
                (a[0] + math.cos(angle) * shrink, a[1] + math.sin(angle) * shrink),
                (b[0] - math.cos(angle) * shrink, b[1] - math.sin(angle) * shrink),
                colour=look.fall,
                size_m=mm(4),
                dashed=True,
            )
            fall = hi[1] - lo[1]
            fall_angle = _along([a, b])

    area = abs(ring_area(site)) if site else 0.0
    info = [f"AREA {area:,.0f} m²"]
    if fall is not None:
        info.insert(0, f"FALL {fall:.2f}m")
    drawing.text(
        "Dimensions",
        "\n".join(info),
        centroid,
        height_mm=STREET_MM,
        angle_rad=fall_angle,
        colour=look.fall_ink,
    )

    # The climate: the sun paths and the suns, the prevailing winds, in the
    # theme's hand. The winds' crescents go down before the suns, so a sun
    # from the same quarter stands on its wind's band rather than under it.
    sol = _solstices(bundle, centroid, map_w, map_h)
    _winds(drawing, bundle, frame, placer, look, sol)
    _suns(drawing, frame, placer, look, sol, bundle.centre_lonlat[1])
    _climate_circle(drawing, bundle, frame, placer, look, sol, site)

    legend_at = _furniture_of_sheet(drawing, bundle, frame, title="SITE ANALYSIS")
    rows = [
        Row("dashed", look.site, None, "SITE"),
        Row("dashed", look.fall, None, "FALL OF TERRAIN"),
        Row("text", "SB 30.48", None, "BOUNDARY DIMENSION (m)"),
        Row("text", "RL 24.5", None, "SURFACE LEVEL (AHD)"),
    ]
    if described and look.contours:
        # The interval, and whose: the City of Sydney's 1 m or the state's 2 m.
        interval, who, _ = described
        rows.append(Row("line", look.contour_ink, None, f"CONTOURS AT {interval:g} m AHD, {who}"))
    rows.append(
        Row("text", "12 / R3", None, "NEIGHBOUR: NUMBER, STOREYS, ZONE")
        if look.neighbour_zone
        else Row("text", "12 / 2 STOREY", None, "NEIGHBOUR: NUMBER, STOREYS")
    )
    rows += zone_rows
    if bundle.furniture.parking_lanes:
        rows.append(
            Row("hatch", base.ink, base.ink, "STREET PARKING ZONE")
            if look.parking == "hatch"
            else Row("fill", PARKING_PLUM, "#7a3c50", "STREET PARKING ZONE")
        )
    if bundle.furniture.driveways:
        rows.append(Row("fill", DRIVEWAY_YELLOW, "#c9bb00", "VEHICULAR ACCESS"))
    if any(r.lanes for r in bundle.roads) or bundle.furniture.oneway_roads:
        rows.append(Row("line", base.road, None, "TRAFFIC DIRECTION AND LANES"))
    if any(tree.canopy_from != NOMINAL for tree in bundle.furniture.trees):
        rows.append(Row("wash", TREE_GREEN, TREE_EDGE, "TREE, CANOPY TO SCALE"))
    if any(tree.canopy_from == NOMINAL for tree in bundle.furniture.trees):
        rows.append(
            Row(
                "dashed wash",
                TREE_GREEN,
                TREE_EDGE,
                f"TREE, SIZE NOT RECORDED ({NOMINAL_CANOPY_M:g} m SHOWN)",
            )
        )
    if bundle.furniture.power_poles:
        rows.append(Row("line", POLE_GREY, None, "POWER POLE"))
    if bundle.furniture.street_lamps:
        rows.append(Row("fill", LAMP_YELLOW, "#a8860b", "LIGHT POLE"))
    if bundle.furniture.hydrants:
        rows.append(Row("fill", HYDRANT_BLUE, None, "HYDRANT"))
    if bundle.bus_stops:
        rows.append(Row("text", "B", None, "BUS STOPS"))
    if bundle.furniture.buildings:
        if look.buildings == "mass":
            rows.append(Row("fill", BUILDING_GREY, base.road, "BUILDING FOOTPRINTS (OSM)"))
        elif look.buildings == "outline":
            rows.append(Row("line", "#ffffff", None, "BUILDING FOOTPRINTS (OSM)"))
        elif look.buildings == "colour":
            rows.append(Row("fill", quiet, "#ffffff", "BUILDING, IN ITS ZONE'S COLOUR (OSM)"))
        else:
            rows.append(
                Row("fill", "#ffffff", quiet, "BUILDING, IN ITS ZONE'S INK (OSM)", "lines", quiet)
            )
    if future:
        rows.append(Row("dashed", FUTURE_MAGENTA, None, "FUTURE CONTEXT: LEP + ADG 3F ENVELOPE"))
    rows.append(Row("line", look.noise_pen, None, "NOISE SOURCE"))
    if look.wind in ("banners", "strands"):
        rows.append(Row("fill", "#ffffff", look.wind_pen, "PREVAILING BREEZES"))
    elif look.wind == "circle":
        rows.append(Row("hatch", look.wind_pen, look.wind_pen, "PREVAILING BREEZES"))
    elif look.wind == "drawn":
        rows.append(Row("fill", look.climate_ink, look.climate_ink, "PREVAILING BREEZES"))
    else:
        rows.append(
            Row("fill", themes.blend(look.wind_band, "#ffffff", 0.45), None, "PREVAILING BREEZES")
        )
    if look.sun == "band":
        rows.append(
            Row(
                "fill",
                themes.blend(themes.blend(look.sun_band[0], look.sun_band[1], 0.5), "#ffffff", 0.5),
                look.sun_fill,
                "SUN PATH, SUMMER AND WINTER",
            )
        )
    elif look.sun == "drawn":
        rows.append(Row("fill", look.sun_ink, look.sun_ink, "WINTER / SUMMER SUNRISE AND SUNSET"))
    else:
        rows.append(Row("fill", look.sun_fill, look.sun_edge, "WINTER / SUMMER SUN (AM/PM)"))
    for kind in sorted({u.kind for u in bundle.furniture.utilities}):
        rows.append(Row("dashed", UTILITY.get(kind, "#9b59b6"), None, f"{kind.upper()} MAIN"))
    _legend(drawing, rows, legend_at, title="LEGEND")
    return drawing


# -- the development summary ------------------------------------------------------


def _fmt(value: float, places: int = 1) -> str:
    return f"{value:,.{places}f}"


def summary_rows(bundle: SummaryBundle) -> list[tuple[str, str, list[str]]]:
    """``(kind, label, controls)`` per row: ``section``, ``head`` or ``row``.

    Every LEP control is published, so every one is filled. Council DCP
    controls are not open data, so those rows are ruled up and left for a
    person, rather than guessed at.
    """
    c = bundle.controls
    area = bundle.site_area_m2
    rows: list[tuple[str, str, list[str]]] = []
    rows.append(("section", "SITE INFO", []))
    rows.append(("row", "ADDRESS", [bundle.site_address]))
    rows.append(("row", "DP", [bundle.lot_description]))
    rows.append(
        (
            "row",
            "SITE AREA",
            [f"{_fmt(area)} sqm", "(cadastral boundary, confirm against survey)"]
            if area
            else ["-"],
        )
    )
    rows.append(("section", "PROJECT SUMMARY", []))
    for label in ("RESIDENTIAL MIX", "COMMERCIAL AREA (sqm)", "CAR PARKING"):
        rows.append(("row", label, []))

    lep = (
        (c.epi_name or "LOCAL ENVIRONMENTAL PLAN")
        .upper()
        .replace("LOCAL ENVIRONMENTAL PLAN", "LEP")
    )
    rows.append(("section", lep, []))
    rows.append(("head", "", ["CONTROLS"]))
    rows.append(
        ("row", "LAND USE", [" - ".join(p for p in (c.zone_code, c.zone_purpose) if p) or "-"])
    )
    rows.append(
        (
            "row",
            "BUILDING HEIGHT (m)",
            [
                f"{_fmt(c.max_height_m, 0)}m"
                if c.max_height_m
                else "No height of building control mapped"
            ],
        )
    )
    rows.append(
        ("row", "FLOOR SPACE RATIO", [f"{c.fsr:.2f}:1" if c.fsr else "No FSR control mapped"])
    )
    rows.append(
        (
            "row",
            "GROSS FLOOR AREA (sqm)",
            [f"{_fmt(c.fsr * area)} sqm", f"({c.fsr:.2f} x {_fmt(area)} sqm site area)"]
            if c.fsr and area
            else ["-"],
        )
    )
    rows.append(
        (
            "row",
            "MIN. LOT SIZE (sqm)",
            [
                f"{_fmt(c.min_lot_size_m2, 0)} sqm"
                if c.min_lot_size_m2
                else "No minimum lot size mapped"
            ],
        )
    )
    rows.append(
        (
            "row",
            "HERITAGE",
            [f"{name}{f' ({sig})' if sig else ''}" for name, sig in c.heritage]
            or ["No heritage item mapped on the site"],
        )
    )

    lga = (c.lga_name or "").strip()
    rows.append(("section", f"{lga + ' ' if lga else ''}DEVELOPMENT CONTROL PLAN", []))
    rows.append(("head", "", ["CONTROLS"]))
    for label in (
        "DWELLING MIX",
        "SETBACK",
        "MIN. LANDSCAPE AREA",
        "CAR PARKING",
        "BICYCLE PARKING",
        "MOTORCYCLE PARKING",
    ):
        rows.append(("row", label, []))

    rows.append(("section", "APARTMENT DESIGN GUIDE", []))
    rows.append(("head", "", ["CONTROLS"]))
    rows.append(
        (
            "row",
            "3F. VISUAL PRIVACY / BUILDING SEPARATION",
            [
                f"{band.storeys}: {band.between_m:g} m between habitable rooms, "
                f"{band.boundary_m:g} m to a side or rear boundary"
                for band in ADG_SEPARATION
            ],
        )
    )
    rows.append(
        (
            "row",
            "3D. COMMUNAL OPEN SPACE",
            [
                "Communal open space has a minimum area equal to 25% of the site",
                *([f"= {_fmt(area * 0.25)} sqm"] if area else []),
            ],
        )
    )
    rows.append(
        (
            "row",
            "3E. DEEP SOIL ZONE",
            [
                "6m minimum dimension, and equal to 7% of the site area",
                *([f"= {_fmt(area * 0.07)} sqm"] if area else []),
            ],
        )
    )
    rows.append(
        (
            "row",
            "4A. SOLAR AND DAYLIGHT ACCESS",
            [
                "Living rooms and private open spaces of at least 70% of apartments in a",
                "building receive a minimum of 2 hours direct sunlight between 9 am and 3 pm",
                "at mid winter in the Sydney Metropolitan Area",
            ],
        )
    )
    rows.append(
        (
            "row",
            "4B. NATURAL VENTILATION",
            [
                "At least 60% of apartments are naturally cross ventilated in the first nine",
                "storeys of the building. Apartments at ten storeys or greater are deemed to",
                "be cross ventilated only if any enclosure of the balconies at these levels",
                "allows adequate natural ventilation and cannot be fully enclosed",
            ],
        )
    )
    return rows


#: The summary is a table, not a map; it is drawn at 1:100 so a text of
#: 3.9 mm on paper is 0.39 m on the worksheet and the rows step by 0.52 m.
SUMMARY_SCALE = 100.0

#: Where the controls column starts, in paper millimetres, and the most
#: characters of a row's label that fit before it. The column was 60.4 mm
#: and the labels ran into the controls (the Redfern sheet, 7 October 2026:
#: "3F. VISUAL PRIVACY / BUILDING SEPARATION" over "6 to 12 m between
#: habitable rooms"); Archicad's capitals at 3.9 mm run about 0.72 of the
#: height each, so 80 mm less the margins holds 27 of them. A longer label
#: is wrapped at a word onto as many lines as it needs, and the row grows.
SUMMARY_LABEL_MM = 80.0
SUMMARY_LABEL_CHARS = 27


def summary_label_lines(label: str) -> list[str]:
    """A row's label on as many lines as fit the label column."""
    return textwrap.wrap(label, SUMMARY_LABEL_CHARS) or [label]


def summary_drawing(bundle: SummaryBundle, scale: float = SUMMARY_SCALE) -> Drawing:
    """The planning-controls table, as texts and rules.

    At ``scale`` 1 the millimetres are paper millimetres, which is what a
    layout wants; the table then runs down from ``(0, 0)``.
    """
    drawing = Drawing(scale, SUMMARY_WORD)
    mm = drawing.mm
    body, lead, pad = 3.9, mm(5.2), mm(5.2)
    left, right = 0.0, mm(372)
    label_x, controls_x = mm(0.7), mm(SUMMARY_LABEL_MM)
    y = 0.0
    drawing.text(
        "Table", "SUMMARY OF CONTROLS", (label_x, y + mm(2)), height_mm=8.2, justification="Left"
    )
    y -= mm(6.3)
    drawing.line("Table", [(left, y), (right, y)], colour=INK)
    for kind, label, controls in summary_rows(bundle):
        names = summary_label_lines(label) if kind == "row" else [label]
        lines = max(len(controls), len(names), 1)
        height = mm(9.6) if kind == "section" else max(mm(7.6), pad + (lines - 1) * lead + mm(2.4))
        base = y - pad
        if kind == "section":
            drawing.text("Table", label, (label_x, base), height_mm=body, justification="Left")
        elif kind == "head":
            drawing.text(
                "Table", "CONTROLS", (controls_x, base), height_mm=body, justification="Left"
            )
        else:
            for i, name in enumerate(names):
                drawing.text(
                    "Table", name, (label_x, base - i * lead), height_mm=body, justification="Left"
                )
            for i, line in enumerate(controls):
                drawing.text(
                    "Table",
                    line,
                    (controls_x, base - i * lead),
                    height_mm=body,
                    justification="Left",
                )
        y -= height
        drawing.line("Table", [(left, y), (right, y)], colour=INK)
    drawing.text(
        "Table",
        "Controls are read from the NSW ePlanning register at the site. "
        "Council DCP rows are left for manual entry.",
        (label_x, y - mm(8)),
        height_mm=SMALL_MM,
        justification="Left",
    )
    # The same credit the two sheets carry, under the same note that already
    # says where the figures came from. A table of somebody else's numbers is
    # as much a produced work as a map of their lines.
    credit = sources.credit_line(sources.named(bundle.sources_used()))
    for row, part in enumerate(_credit_lines(credit, 372.0)):
        drawing.text(
            "Table",
            part,
            (label_x, y - mm(13) - row * mm(4)),
            height_mm=CREDIT_MM,
            justification="Left",
            colour=CADASTRE_GREY,
        )
    return drawing


# -- into Archicad --------------------------------------------------------------------


@dataclass(frozen=True)
class WorksheetReport:
    name: str
    database_id: str
    reused: bool
    cleared: int
    fills: int
    lines: int
    texts: int
    texts_on_layer: int
    figures: int
    layers: tuple[str, ...]
    view: str
    notes: tuple[str, ...] = ()
    layout: str = ""

    def describe(self) -> str:
        made = f"reused, cleared {self.cleared} elements" if self.reused else "created"
        # The orthophoto is counted out loud. It is the one element a run can
        # fail to place in silence -- a tile whose file has gone is skipped
        # without a word -- and the sheet then looks bare rather than wrong,
        # which is a great deal harder to notice than a number that says 0.
        photo = f", {self.figures} orthophoto tiles" if self.figures else ""
        head = (
            f"  worksheet {self.name!r} ({made}): {self.fills} fills, {self.lines} polylines, "
            f"{self.texts} texts{photo} on {len(self.layers)} layers"
        )
        lines = [head]
        if self.texts_on_layer != self.texts:
            lines.append(
                f"    {self.texts - self.texts_on_layer} of {self.texts} texts stayed on the Text "
                f"tool's default layer; the study's layer or that one is hidden or locked."
            )
        if self.view:
            lines.append(f"    view {self.view!r} in the View Map")
        if self.layout:
            lines.append(
                f"    layout {self.layout!r} in the Layout Book, the sheet centred on the site"
            )
        lines.extend(f"    {note}" for note in self.notes)
        return "\n".join(lines)


@dataclass(frozen=True)
class _Attributes:
    solid_fill: int | None
    dashed: int | None
    pens: tuple[Pen, ...]
    wash_fill: int | None = None
    """A percentage fill, for a wash the photo shows through."""
    empty_fill: int | None = None
    """An empty fill with a contour: what a drawn hatch sits in."""
    dotted: int | None = None
    """A dotted line type; the dashed one stands in where a project has none."""

    @property
    def dotted_or_dashed(self) -> int | None:
        return self.dotted if self.dotted is not None else self.dashed

    def pen(self, colour: str) -> int | None:
        if not self.pens:
            return None
        r, g, b = curate.rgb(colour)
        wanted = (round(r * 255), round(g * 255), round(b * 255))
        return min(self.pens, key=lambda pen: _looks_like(pen.rgb, wanted)).index


def attribute_index(connection: ArchicadConnection, kind: str, wanted: Sequence[str]) -> int | None:
    """The index of the first attribute whose name matches one of ``wanted``,
    in order of preference; ``None`` when the project has none."""
    try:
        response = connection.run_tapir("GetAttributesByType", {"attributeType": kind})
    except ArchicadError:
        return None
    attributes = response.get("attributes") if isinstance(response, dict) else None
    if not isinstance(attributes, list):
        return None
    by_name: dict[str, int] = {}
    for attribute in attributes:
        if isinstance(attribute, dict) and isinstance(attribute.get("index"), (int, float)):
            by_name.setdefault(str(attribute.get("name", "")).casefold(), int(attribute["index"]))
    for name in wanted:
        if name.casefold() in by_name:
            return by_name[name.casefold()]
    for name in wanted:
        for key, index in by_name.items():
            if name.casefold() in key:
                return index
    return None


def _attributes(connection: ArchicadConnection) -> _Attributes:
    try:
        pens = pen_table(connection)
    except ArchicadError:
        pens = ()
    return _Attributes(
        solid_fill=attribute_index(connection, "Fill", ("Solid Fill", "Solid", "Foreground")),
        dashed=attribute_index(connection, "Line", ("Dashed", "Dashed Line", "Dash")),
        wash_fill=attribute_index(
            connection, "Fill", ("50%", "50 %", "Percent 50", "Percentage 50")
        ),
        empty_fill=attribute_index(connection, "Fill", ("Empty Fill", "Empty")),
        dotted=attribute_index(connection, "Line", ("Dotted", "Dotted Line", "Dot")),
        pens=pens,
    )


class WorksheetNotEnteredError(ArchicadError):
    """The worksheet exists and Archicad will not make it current from outside.

    Measured on 11 September 2026 against the Kogarah solar study: a worksheet
    made in this session, by Tapir's ``CreateWorksheets``, answers
    ``APIERR_BADDATABASE`` (-2130313110) to ``APIDb_ChangeCurrentDatabaseID``
    -- the add-on's own call, not only Tapir's ``ChangeWindow``. A worksheet
    that is *open in front* is current by definition, so the way through is
    a person opening it, which the message says.
    """


def _tidy(name: str) -> str:
    return " ".join(name.split()).casefold()


def _worksheet_by_name(connection: ArchicadConnection, name: str) -> str:
    """The Project Map id of the worksheet called ``name``, or empty."""
    response = connection.run_tapir("GetNavigatorItemTree", {"navigatorMapId": "ProjectMap"})
    root = response.get("navigatorItemTree") if isinstance(response, dict) else None
    if not isinstance(root, dict):
        return ""
    wanted = _tidy(name)
    for item_name, identifier in _worksheets(root.get("rootItem", root)):
        if _tidy(item_name) == wanted:
            return identifier
    return ""


def _standing_in(connection: ArchicadConnection) -> tuple[str, str, str]:
    """``(database id, window type, name)`` of the current database, asked
    of the add-on; empty strings when it will not say."""
    try:
        here = connection.run_loriini("GetCurrentDatabase", {})
    except ArchicadError:
        return "", "", ""
    if not isinstance(here, dict):
        return "", "", ""
    return (
        str((here.get("databaseId") or {}).get("guid", "")),
        str(here.get("windowType", "")),
        str(here.get("name", "")),
    )


def _enter(connection: ArchicadConnection, database_id: str) -> bool:
    """Try to make the worksheet current through the add-on. False if refused.

    Two tries. The plain move first, which enters any worksheet a person has
    ever opened (D96). Then the move with the window opened first -- the
    add-on's ``open``, the call a double-click makes -- which is the one
    route D95 left unread for a worksheet nobody has opened; an older add-on
    refuses the unknown parameter, which reads as refused and costs nothing.
    """
    where = {"databaseId": {"guid": database_id}, "windowType": "Worksheet"}
    for parameters in (where, {**where, "open": True}):
        try:
            moved = connection.run_loriini("SetCurrentDatabase", parameters)
        except ArchicadError:
            continue
        if isinstance(moved, dict) and bool(moved.get("success")):
            return True
    return False


def _wait_until_in_front(
    connection: ArchicadConnection,
    database_id: str,
    name: str,
    *,
    wait_s: float,
    say: Callable[[str], None] | None,
) -> None:
    """Poll until the worksheet is the current database, or give up.

    A worksheet made in this session refuses every move from outside, and a
    person opening it is the only thing that makes it current. So the run
    asks, and waits: two seconds between looks, ``wait_s`` in all.
    """
    deadline = time.monotonic() + wait_s
    if say and wait_s > 0:
        say(
            f"  waiting for {name!r} to become current -- save the project (Ctrl+S), "
            f"and double-click the worksheet under Worksheets in the Project Map -- "
            f"within {wait_s / 60:.0f} minutes..."
        )
    while True:
        here_id, here_kind, _ = _standing_in(connection)
        if here_id == database_id and here_kind == "Worksheet":
            return
        # A save may be what makes the database enterable (D39 found that
        # for a layout), so the move is retried on every look as well.
        if _enter(connection, database_id):
            return
        if time.monotonic() >= deadline:
            break
        time.sleep(2.0)
    raise WorksheetNotEnteredError(
        f"The worksheet {name!r} is in the project but Archicad refused to make it "
        f"current, and it was not opened while the run waited. Open it -- double-click "
        f"it under Worksheets in the Project Map -- and run again; the run draws into the "
        f"worksheet in front."
    )


def ensure_worksheet(
    connection: ArchicadConnection,
    name: str,
    *,
    wait_s: float = 0.0,
    say: Callable[[str], None] | None = None,
) -> tuple[str, str, bool]:
    """A worksheet by this name, current. Returns ``(database id, navigator id, reused)``.

    In order of what works: the worksheet already current, by its database
    id; an existing one entered through the add-on's ``SetCurrentDatabase``,
    which reads back rather than claims; a new one from the add-on's
    ``CreateWorksheet``; and, when that is refused, Tapir's
    ``CreateWorksheets`` followed by the same entering step.

    A worksheet made in this session refuses to be entered by either route
    (measured, 11 September 2026). It is created all the same, and the run
    then waits ``wait_s`` for a person to open it, since a worksheet in front
    is current by definition.
    """
    navigator_id = _worksheet_by_name(connection, name)
    database_id = database_of(connection, navigator_id) if navigator_id else ""
    reused = bool(navigator_id)

    if not database_id:
        try:
            made = connection.run_loriini("CreateWorksheet", {"name": name, "makeCurrent": True})
            if isinstance(made, dict):
                database_id = str((made.get("databaseId") or {}).get("guid", ""))
                if database_id and made.get("isCurrent"):
                    return database_id, _worksheet_by_name(connection, name), False
        except ArchicadError:
            # APIERR_REFUSEDCMD from the undo scope the first build wrapped it
            # in; Tapir's own creation is the same call outside one.
            pass
        if not database_id:
            # Look again before making a second. The add-on creates the
            # worksheet and *then* enters it, so a refusal at the entering
            # step leaves a worksheet behind that this call never saw --
            # and Tapir's fallback below made another, which is how a run
            # left two of every sheet in the Project Map (measured at
            # Bondi, 14 September 2026).
            navigator_id = _worksheet_by_name(connection, name)
            if navigator_id:
                database_id = database_of(connection, navigator_id)
                reused = True
        if not database_id:
            made = connection.run_tapir(
                "CreateWorksheets",
                {"worksheetsData": [{"name": name, "referenceId": name[:31]}]},
            )
            databases = made.get("databases") if isinstance(made, dict) else None
            first = databases[0] if isinstance(databases, list) and databases else None
            database_id = (
                str((first.get("databaseId") or {}).get("guid", ""))
                if isinstance(first, dict)
                else ""
            )
            if not database_id:
                raise ArchicadError(f"CreateWorksheets for {name!r} answered {made!r}")
        navigator_id = _worksheet_by_name(connection, name)

    here_id, here_kind, _ = _standing_in(connection)
    if here_id == database_id and here_kind == "Worksheet":
        return database_id, navigator_id, reused
    if _enter(connection, database_id):
        # Read back rather than believed: a move answered as made and not
        # made is how a run once drew a second copy of a sheet over the
        # first, having found nothing to clear.
        here_id, here_kind, _ = _standing_in(connection)
        if here_id == database_id and here_kind == "Worksheet":
            return database_id, navigator_id, reused
    _wait_until_in_front(connection, database_id, name, wait_s=wait_s, say=say)
    return database_id, navigator_id, reused


def _batched(items: Sequence[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def _created(response: Any, command: str) -> list[dict[str, Any]]:
    elements = response.get("elements") if isinstance(response, dict) else None
    if not isinstance(elements, list):
        raise ArchicadError(f"{command} returned no element list: {response!r}")
    problems = sorted(
        {
            str((e.get("error") or {}).get("message", "unknown error"))
            for e in elements
            if isinstance(e, dict) and "error" in e
        }
    )
    if problems:
        raise ArchicadError(f"{command} failed for some elements:\n  " + "\n  ".join(problems[:5]))
    return [e for e in elements if isinstance(e, dict) and ("elementId" in e or "guid" in e)]


#: What a justification means for where the text hangs off its point. A
#: label is placed at its centre, a legend row at its left edge.
_ANCHORS = {"Center": "MiddleMiddle", "Left": "LeftMiddle", "Right": "RightMiddle"}


def _texts(
    connection: ArchicadConnection,
    texts: Sequence[Text],
    indices: dict[str, int],
    attributes: _Attributes,
) -> int:
    """Write the texts on their layers. Returns how many ended there.

    Through ``draw.place_texts``, which is every study's route: the add-on's
    command with the layer and the anchor, or Tapir's and a move for an
    add-on too old to have it.
    """
    on_layer = 0
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for text in texts:
        pen = attributes.pen(text.colour)
        one: dict[str, Any] = {
            "coordinate": {"x": text.at[0], "y": text.at[1], "z": 0.0},
            "text": text.text,
            "height": text.height_mm,
            "justification": text.justification,
        }
        if text.justification in _ANCHORS:
            one["anchor"] = _ANCHORS[text.justification]
        if abs(text.angle_rad) > 1e-9:
            one["angle"] = text.angle_rad
        if pen is not None:
            one["pen"] = pen
        by_layer.setdefault(text.layer, []).append(one)
    for layer, rows in by_layer.items():
        on_layer += place_texts(connection, rows, indices[layer])
    return on_layer


def _figures(
    connection: ArchicadConnection,
    figures: Sequence[Figure],
    indices: dict[str, int],
    pictures_as: str = "figure",
) -> int:
    """Place the pictures through the add-on. Returns how many were placed.

    Each file goes over the wire as base64 inside the request, which for a
    4000-pixel JPEG tile is a few megabytes; no command can point Archicad at
    a path. An add-on without the command costs the sheet its photo and says
    so, not the run.

    ``pictures_as`` chooses the element: a Figure, which is what the sheets
    have always used, or a Drawing through ``PlaceDrawings`` -- a frame, a
    ratio and a row in the Drawing Manager. Neither links to the file: the
    API has no way to (D92).
    """
    command = "PlaceDrawings" if pictures_as == "drawing" else "PlaceFigures"
    placed = 0
    for figure in figures:
        try:
            data = base64.b64encode(Path(figure.path).read_bytes()).decode("ascii")
        except OSError:
            continue
        one: dict[str, Any] = {
            "data": data,
            "format": Path(figure.path).suffix.lstrip(".").lower() or "jpeg",
            "box": {
                "xMin": figure.at[0],
                "yMin": figure.at[1],
                "xMax": figure.at[0] + figure.width_m,
                "yMax": figure.at[1] + figure.height_m,
            },
            "angle": figure.angle_rad,
            "layerIndex": indices[figure.layer],
            "name": figure.name or Path(figure.path).name,
        }
        if command == "PlaceFigures":
            # A Figure is anchored by a corner; a Drawing is positioned by
            # its box and needs no anchor.
            one["anchor"] = "LeftBottom"
        request = {"figures" if command == "PlaceFigures" else "drawings": [one]}
        try:
            _created(connection.run_loriini(command, request), command)
        except ArchicadError as error:
            if "not have the registered" in str(error):
                raise ArchicadError(
                    f"The installed Loriini add-on has no {command} command, so the aerial "
                    f"cannot be placed; install the current build."
                ) from error
            raise
        placed += 1
    return placed


def _flush(
    connection: ArchicadConnection, drawing: Drawing, attributes: _Attributes
) -> tuple[int, int, int, int, int, int]:
    """Create every element of the drawing in the current database.

    Returns ``(figures, fills, lines, texts, texts on their layer, fills refused)``.

    The figure count is returned and not discarded, because the orthophoto is
    the one element here that a run could silently fail to place -- a missing
    tile file is skipped without a word -- and the sheet looks merely bare
    rather than wrong. Counting it is the only way the report can say.
    """
    indices = {name: ensure_layer(connection, name).index for name in drawing.layers}

    figures = _figures(connection, drawing.figures, indices, drawing.pictures_as)

    fills: list[dict[str, Any]] = []
    for fill in drawing.fills:
        r, g, b = curate.rgb(fill.colour)
        data: dict[str, Any] = {
            "contours": [{"points": [{"x": x, "y": y} for x, y in ring]} for ring in fill.rings],
            "layerIndex": indices[fill.layer],
            "determination": "drafting",
            "showArea": False,
            "foregroundColour": {"red": r, "green": g, "blue": b},
            "backgroundColour": {"red": r, "green": g, "blue": b},
        }
        if fill.hatch and attributes.empty_fill is not None:
            data["fillIndex"] = attributes.empty_fill
            data["backgroundPen"] = 0
            del data["backgroundColour"]
        elif fill.wash and attributes.wash_fill is not None:
            data["fillIndex"] = attributes.wash_fill
            data["backgroundPen"] = 0
            del data["backgroundColour"]
        elif attributes.solid_fill is not None:
            data["fillIndex"] = attributes.solid_fill
        contour_pen = attributes.pen(fill.contour or fill.colour)
        if contour_pen is not None:
            data["contourPen"] = contour_pen
        if fill.dashed and attributes.dashed is not None:
            data["lineTypeIndex"] = attributes.dashed
        if fill.weight_mm is not None:
            data["penWeight"] = fill.weight_mm
        if fill.element_id:
            data["elementId"] = fill.element_id[:255]
        fills.append(data)
    refused = 0
    for batch in _batched(fills, 300):
        try:
            _created(connection.run_loriini("CreateFills", {"fills": batch}), "CreateFills")
        except ArchicadError:
            # The whole batch rolls back on one refusal, so it goes again one
            # fill at a time and the refused ones are counted rather than
            # costing the sheet.
            for one in batch:
                try:
                    _created(connection.run_loriini("CreateFills", {"fills": [one]}), "CreateFills")
                except ArchicadError:
                    refused += 1

    lines: list[dict[str, Any]] = []
    for line in drawing.lines:
        data = {
            "coordinates": [{"x": x, "y": y} for x, y in line.points],
            "layerIndex": indices[line.layer],
        }
        pen = attributes.pen(line.colour)
        if pen is not None:
            data["linePenIndex"] = pen
        if line.dashed and attributes.dashed is not None:
            data["lineTypeIndex"] = attributes.dashed
        elif line.dotted and attributes.dotted_or_dashed is not None:
            data["lineTypeIndex"] = attributes.dotted_or_dashed
        if line.weight_mm is not None:
            data["penWeightMm"] = line.weight_mm
        lines.append(data)
    for batch in _batched(lines, 500):
        _created(
            connection.run_tapir("CreatePolylines", {"polylinesData": batch}), "CreatePolylines"
        )

    on_layer = _texts(connection, drawing.texts, indices, attributes)

    return figures, len(fills) - refused, len(lines), len(drawing.texts), on_layer, refused


def _view_of(
    connection: ArchicadConnection, navigator_id: str, name: str, drawing: Drawing
) -> StoreyView | None:
    """A view of the worksheet at the sheet's scale, showing the drawing's layers."""
    if not navigator_id:
        return None
    combination = ensure_layer_combination(
        connection, naming.named(drawing.word), show=drawing.layers, hide=[]
    )
    views = views_for_sources(
        connection,
        [(ModelSource(navigator_id, name, "WorksheetDrawingItem"), name)],
        combination=combination,
        folder=naming.named(FOLDER_WORD),
        drawing_scale=drawing.scale,
    )
    if not views:
        return None
    # The sheet's own colours, not the project's: a graphic override
    # combination in force on the window greys every 2D element, which is
    # how the first live site sheet came out in one grey. And the office's
    # pen table for these sheets, when it has one.
    settings: dict[str, Any] = {"graphicOverrideCombination": NO_OVERRIDES}
    pen_set = _site_pen_set(connection)
    if pen_set:
        settings["penSetName"] = pen_set
    for attempt in (
        settings,
        {k: v for k, v in settings.items() if k != "graphicOverrideCombination"},
    ):
        if not attempt:
            break
        try:
            connection.run_tapir(
                "SetViewSettings",
                {
                    "navigatorItemIdsWithViewSettings": [
                        {
                            "navigatorItemId": {"guid": views[0].navigator_id},
                            "viewSettings": attempt,
                        }
                    ]
                },
            )
            break
        except ArchicadError:
            continue
    return views[0]


#: Archicad's built-in graphic override combination that overrides nothing.
NO_OVERRIDES = "No Overrides"


def _site_pen_set(connection: ArchicadConnection) -> str | None:
    """The pen table the office keeps for site analysis, if it has one."""
    try:
        response = connection.run_tapir("GetAttributesByType", {"attributeType": "PenTable"})
    except ArchicadError:
        return None
    attributes = response.get("attributes") if isinstance(response, dict) else None
    for attribute in attributes if isinstance(attributes, list) else []:
        name = str((attribute or {}).get("name", "")) if isinstance(attribute, dict) else ""
        if "site analysis" in name.casefold():
            return name
    return None


def _remove_layout(connection: ArchicadConnection, name: str) -> None:
    """Delete the layout called ``name``, if the Layout Book has one.

    Never while standing in it. Archicad went away mid-call the one time a
    run deleted the layout that was its current database (11 September
    2026, the summary sheet drawn twice in a row), so the database is moved
    to the floor plan first. A layout, unlike a worksheet, can be entered
    again afterwards, so nothing is lost by leaving it.
    """
    response = connection.run_tapir("GetNavigatorItemTree", {"navigatorMapId": "LayoutBook"})
    root = response.get("navigatorItemTree") if isinstance(response, dict) else None
    if not isinstance(root, dict):
        return
    stale = [
        item
        for item in _walk(root)
        if item.kind == "LayoutItem" and _tidy(item.name) == _tidy(name)
    ]
    if stale:
        _, here_kind, here_name = _standing_in(connection)
        if here_kind == "Layout" and _tidy(here_name) == _tidy(name):
            connection.run_tapir("ChangeWindow", {"windowType": "FloorPlan"})
        connection.run_tapir(
            "DeleteNavigatorItems",
            {
                "navigatorItemIds": [
                    {"navigatorItemId": {"guid": item.identifier}} for item in stale
                ]
            },
        )


def _sheet_frame(
    sheet: LayoutSheet, *, width_mm: float, height_mm: float, title_block_mm: float
) -> tuple[float, float, float, float]:
    """The map field on the page, in metres: as big as the sheet allows up
    to the field's own size, centred in what is left beside the title block."""
    left, top, width, height = sheet.usable
    room = max(width - title_block_mm, 1.0)
    fw, fh = min(width_mm, room), min(height_mm, height)
    x0 = left + (room - fw) / 2.0
    y0 = top + (height - fh) / 2.0
    return (x0 / MM_PER_M, y0 / MM_PER_M, (x0 + fw) / MM_PER_M, (y0 + fh) / MM_PER_M)


def place_on_layout(
    connection: ArchicadConnection,
    view: StoreyView,
    drawing: Drawing,
    *,
    site_centre: Point,
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
) -> str:
    """The view on a sheet of its own, the map field centred on the site.

    Tapir places the drawing clipped to a placeholder and anchored by a
    corner (D51); the add-on's ``ArrangeDrawings`` then sets the frame to the
    map field and puts the drawing's own origin where the site's centre lands
    at the field's centre -- the worksheet origin is the project origin, and
    the site sits ``site_centre`` metres from it. Returns the layout's name.
    """
    name = view.name
    # Remade, not reused: a layout keeps the master it was made on and nothing
    # can change that after, so a sheet from an earlier run on another master
    # would stay wrong for good. The sheet is the tool's own, and the drawing
    # on it is regenerated either way.
    _remove_layout(connection, name)
    report = layout_from_views(
        connection,
        [(view.navigator_id, name)],
        layout_name=name,
        scale=drawing.scale,
        master_layout=master_layout,
    )
    if not report.database_id:
        raise ArchicadError(f"the layout {name!r} was not made")
    sheet, _ = layout_sheet(connection, report.database_id)
    placed = _drawings_by_name(connection, report.database_id)
    if name not in placed:
        raise ArchicadError(f"the drawing {name!r} is not on the layout {name!r}")
    x0, y0, x1, y1 = _sheet_frame(
        sheet, width_mm=MAP_WIDTH_MM, height_mm=MAP_HEIGHT_MM, title_block_mm=title_block_mm
    )
    origin = (
        (x0 + x1) / 2.0 - site_centre[0] / drawing.scale,
        (y0 + y1) / 2.0 - site_centre[1] / drawing.scale,
    )
    response = connection.run_loriini(
        "ArrangeDrawings",
        {
            "layoutDatabaseId": {"guid": report.database_id},
            "drawings": [
                {
                    "guid": str(placed[name]["elementId"]["guid"]),
                    "x": origin[0],
                    "y": origin[1],
                    "frame": {"xMin": x0, "yMin": y0, "xMax": x1, "yMax": y1},
                }
            ],
            "anchor": "origin",
            "frameRelativeToOrigin": False,
            "autoUpdate": True,
        },
    )
    if not isinstance(response, dict) or not response.get("success"):
        raise ArchicadError(f"ArrangeDrawings answered {response!r}")
    return report.layout_name


def _draw(
    connection: ArchicadConnection,
    drawing: Drawing,
    name: str,
    *,
    view: bool,
    wait_s: float = 0.0,
    say: Callable[[str], None] | None = None,
    layout: bool = False,
    site_centre: Point = (0.0, 0.0),
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
    pictures_as: str = "figure",
) -> WorksheetReport:
    drawing.pictures_as = pictures_as
    attributes = _attributes(connection)
    notes: list[str] = []
    if attributes.solid_fill is None:
        notes.append(
            "no fill attribute named 'Solid Fill'; fills take the Fill tool's current pattern."
        )
    if attributes.dashed is None:
        notes.append("no line type named 'Dashed'; dashed lines are drawn solid.")
    if not attributes.pens:
        notes.append("the pen table could not be read; lines take the tool's current pen.")

    database_id, navigator_id, reused = ensure_worksheet(connection, name, wait_s=wait_s, say=say)
    cleared = 0
    if reused:
        cleared, left = clear_database(connection)
        if left:
            notes.append(
                f"{left} elements from the last run could not be deleted and are still there."
            )
        # Emptying a worksheet has been seen to move the current database
        # off it -- a clear of 449 elements recounted as 6,875, the other
        # sheet's, and the redraw landed there -- so the worksheet is entered
        # again before anything is drawn, and the run stops rather than draw
        # into the wrong one.
        here_id, _, _ = _standing_in(connection)
        if here_id and here_id != database_id and not _enter(connection, database_id):
            raise ArchicadError(
                f"The worksheet {name!r} stopped being current after it was cleared and "
                f"could not be entered again. Open it and run again."
            )
    if drawing.figures and attributes.wash_fill is None:
        notes.append("no percentage fill named '50%'; the zoning is drawn solid over the aerial.")
    # Counted before the flush, because the fallback below empties the list and
    # the question afterwards is how many were *asked for*, not how many are
    # left to ask for.
    wanted = len(drawing.figures)
    try:
        figures, fills, lines, texts, on_layer, refused = _flush(connection, drawing, attributes)
    except ArchicadError as error:
        if "PlaceFigures" not in str(error):
            raise
        notes.append(str(error))
        drawing.figures.clear()
        figures, fills, lines, texts, on_layer, refused = _flush(connection, drawing, attributes)
    if refused:
        notes.append(f"Archicad refused {refused} fills; they are left out of the sheet.")
    # The silent one. A tile whose file has gone is skipped by `_aerial` and by
    # `_figures` without a word, and the sheet then comes out bare rather than
    # wrong -- which nobody notices, because a site plan with no photo under it
    # looks like a site plan. Saying nothing here is what let the orthophoto be
    # missing from Redfern for a day without a single line of output admitting
    # it. So a shortfall is stated, whether it is some of them or all of them.
    if wanted and figures < wanted:
        notes.append(
            f"{wanted - figures} of {wanted} orthophoto tiles were not placed; their files "
            f"are missing from the run folder, or Archicad refused them."
        )
    view_name = ""
    layout_name = ""
    if view:
        try:
            made_view = _view_of(connection, navigator_id, name, drawing)
            view_name = made_view.name if made_view else ""
        except ArchicadError as error:
            notes.append(f"the worksheet is drawn; its view is not: {error}")
            made_view = None
        if layout and made_view is not None:
            try:
                layout_name = place_on_layout(
                    connection,
                    made_view,
                    drawing,
                    site_centre=site_centre,
                    master_layout=master_layout,
                    title_block_mm=title_block_mm,
                )
            except ArchicadError as error:
                notes.append(f"the view is made; its sheet is not: {error}")
    return WorksheetReport(
        name=name,
        database_id=database_id,
        reused=reused,
        cleared=cleared,
        fills=fills,
        lines=lines,
        texts=texts,
        texts_on_layer=on_layer,
        figures=figures,
        layers=tuple(drawing.layers),
        view=view_name,
        notes=tuple(notes),
        layout=layout_name,
    )


def draw_context(
    connection: ArchicadConnection,
    bundle: ContextBundle,
    frame: Frame,
    *,
    view: bool = True,
    wait_s: float = 0.0,
    say: Callable[[str], None] | None = None,
    layout: bool = False,
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
    pictures_as: str = "figure",
    theme: str | None = None,
) -> WorksheetReport:
    return _draw(
        connection,
        context_drawing(bundle, frame, theme=theme),
        naming.named(CONTEXT_WORD),
        view=view,
        wait_s=wait_s,
        say=say,
        layout=layout,
        site_centre=frame.project(*bundle.centre_lonlat),
        master_layout=master_layout,
        title_block_mm=title_block_mm,
        pictures_as=pictures_as,
    )


def draw_site(
    connection: ArchicadConnection,
    bundle: SiteBundle,
    frame: Frame,
    *,
    view: bool = True,
    wait_s: float = 0.0,
    say: Callable[[str], None] | None = None,
    layout: bool = False,
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
    future: Sequence[Envelope] = (),
    pictures_as: str = "figure",
    theme: str | None = None,
) -> WorksheetReport:
    return _draw(
        connection,
        site_drawing(bundle, frame, future=future, theme=theme),
        naming.named(SITE_WORD),
        view=view,
        wait_s=wait_s,
        say=say,
        layout=layout,
        site_centre=frame.project(*bundle.centre_lonlat),
        master_layout=master_layout,
        title_block_mm=title_block_mm,
        pictures_as=pictures_as,
    )


@dataclass(frozen=True)
class LayoutReport:
    """A sheet drawn on directly: no worksheet, no view, no drawing."""

    name: str
    database_id: str
    master: str
    lines: int
    texts: int
    notes: tuple[str, ...] = ()

    def describe(self) -> str:
        lines = [
            f"  layout {self.name!r} on {self.master!r}: {self.lines} rules and {self.texts} "
            "texts, drawn on the sheet itself"
        ]
        lines.extend(f"    {note}" for note in self.notes)
        return "\n".join(lines)


#: Paper millimetres from the sheet's usable corner to the table's corner.
SUMMARY_MARGIN_MM = 15.0


def draw_summary(
    connection: ArchicadConnection,
    bundle: SummaryBundle,
    *,
    master_layout: str | None = None,
    margin_mm: float = SUMMARY_MARGIN_MM,
    say: Callable[[str], None] | None = None,
) -> LayoutReport:
    """The summary of controls, drawn straight onto a layout of its own.

    A table is paper, not model: it has no scale to keep and nothing to
    place it over, so it goes on the sheet as texts and rules rather than
    into a worksheet with a view and a drawing on top. A layout made in the
    session *can* be entered through the add-on -- unlike a worksheet (D84);
    measured on the Kogarah solar study, 11 September 2026 -- and texts,
    polylines and fills draw into it. Element IDs are the one thing a layout
    element will not take, and a table does not need them.

    Layout coordinates are metres, upward from the sheet's bottom-left
    (``docs/addon.md``); the table hangs from the usable area's top-left
    corner, ``margin_mm`` in.
    """
    name = naming.named(SUMMARY_WORD)
    notes: list[str] = []
    _remove_layout(connection, name)
    masters = master_layouts(connection)
    master = choose_master(masters, master_layout)
    database_id = _create_layout(connection, name, master)
    sheet, assumed = layout_sheet(connection, database_id)
    if assumed:
        notes.append("the sheet size could not be read; an A1 is assumed.")
    if not _enter_layout(connection, database_id):
        raise ArchicadError(
            f"the layout {name!r} was made but could not be entered to draw on; "
            "open it in the Layout Book and run again."
        )
    left, top, _width, _height = sheet.usable
    x0 = (left + margin_mm) / MM_PER_M
    y0 = (sheet.height_mm - top - margin_mm) / MM_PER_M
    drawing = summary_drawing(bundle, scale=1.0).moved(x0, y0)
    attributes = _attributes(connection)
    if not attributes.pens:
        notes.append("the pen table could not be read; lines take the tool's current pen.")
    lines, texts = _flush_on_paper(connection, drawing, attributes)
    if say:
        say(f"  {lines} rules and {texts} texts on the layout")
    return LayoutReport(
        name=name,
        database_id=database_id,
        master=master.name,
        lines=lines,
        texts=texts,
        notes=tuple(notes),
    )


def _flush_on_paper(
    connection: ArchicadConnection, drawing: Drawing, attributes: _Attributes
) -> tuple[int, int]:
    """The drawing's rules and texts into the current layout, on no layer of
    the tool's own: a layout element sits on the Archicad layer, and a layer
    made for a table on paper is one more layer for nothing. Fills and
    figures are not drawn on paper here. Returns ``(lines, texts)``."""
    lines: list[dict[str, Any]] = []
    for line in drawing.lines:
        data: dict[str, Any] = {"coordinates": [{"x": x, "y": y} for x, y in line.points]}
        pen = attributes.pen(line.colour)
        if pen is not None:
            data["linePenIndex"] = pen
        if line.weight_mm is not None:
            data["penWeightMm"] = line.weight_mm
        lines.append(data)
    for batch in _batched(lines, 500):
        _created(
            connection.run_tapir("CreatePolylines", {"polylinesData": batch}), "CreatePolylines"
        )
    rows: list[dict[str, Any]] = []
    for text in drawing.texts:
        one: dict[str, Any] = {
            "coordinate": {"x": text.at[0], "y": text.at[1], "z": 0.0},
            "text": text.text,
            "height": text.height_mm,
            "justification": text.justification,
        }
        if text.justification in _ANCHORS:
            one["anchor"] = _ANCHORS[text.justification]
        pen = attributes.pen(text.colour)
        if pen is not None:
            one["pen"] = pen
        rows.append(one)
    create_texts(connection, rows)
    return len(lines), len(rows)


def _enter_layout(connection: ArchicadConnection, database_id: str) -> bool:
    """Make a layout the current database through the add-on. False if refused
    or if Archicad says it stands somewhere else afterwards."""
    try:
        connection.run_loriini(
            "SetCurrentDatabase", {"databaseId": {"guid": database_id}, "windowType": "Layout"}
        )
    except ArchicadError:
        return False
    here_id, _, _ = _standing_in(connection)
    return here_id == database_id
