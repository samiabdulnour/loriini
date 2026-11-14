"""The neighbourhood in the model: the project's location, the terrain, the
buildings next door.

What the site sheet draws flat, this makes solid, from the same bundle:

* **The project location**, set from the address. With the site anchored at
  the project origin the origin's true position *is* the site's centre, so
  the location becomes exactly right and every later run and every sun
  study agrees with it. The survey point is written as the same point on the
  MGA2020 grid, so an IFC export carries a real georeference too.
* **The terrain**, one Mesh from the contours -- the City of Sydney's 1 m ones
  inside its area, the state's 2 m ones outside -- its outline the model's
  square at the ground level under each corner, and the contours level lines
  inside it: every one of them near the site, fewer and simpler towards the
  edge (``site.ground.mesh_lines``).
* **The neighbours**, one slab per building footprint OpenStreetMap records,
  standing on the ground under it, as tall as its storeys say -- or, where
  OSM records none, as tall as the LEP's height-of-building control allows,
  and said to be assumed. The site's own buildings are left out: what stands
  there is what the proposal replaces.

Everything lands on one layer, ``LORIINI``, to be filed properly once the
whole set of outputs is settled; every element carries an ID that says what
it is, so the filing can be done by a Find & Select.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from itertools import pairwise
from typing import Any

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.draw import ensure_layer, move_to_layer
from sun_study.archicad.ids import group_by_value, stamp_in_order
from sun_study.archicad.read import GeoLocation, north_radians_from_bearing, read_geo_location
from sun_study.archicad.site_analysis import Frame, _clean_ring, _map_rectangle
from sun_study.site.arcgis import rings_of
from sun_study.site.geo import (
    Point,
    clip_ring,
    convex_hull,
    dissolve,
    lonlat_to_mercator,
    lonlat_to_mga,
    mercator_to_lonlat,
    mga_zone,
    point_in_ring,
    ring_area,
    ring_centroid,
)
from sun_study.site.ground import MESH_POINTS, Ground, MeshLines, mesh_lines
from sun_study.site.pipeline import SiteBundle
from sun_study.site.terrain import described as whose_contours

__all__ = [
    "STOREY_M",
    "ContextModelReport",
    "layer_name",
    "model_context",
    "set_project_location",
    "storeys_of",
]


#: Where everything generated goes, until the office files it.
#: Deliberately not a constant: the site group is settable, and a name built
#: at import would freeze it at the default however the run was told otherwise
#: -- the run would then draw on one layer and look for its own work on
#: another, with both names looking right on their own.
def layer_name() -> str:
    """The layer the neighbouring buildings go on, in the office's own site
    group. The terrain and the street blocks have layers of their own."""
    return naming.buildings_layer()


#: Floor to floor, where nothing better is recorded. A NSW apartment floor
#: is 3.1 m under the ADG's 2.7 m ceilings; a house is a little less. One
#: figure, stated, rather than two guesses.
STOREY_M = 3.1

#: How far the street blocks stand above the terrain: a kerb. The roads
#: are not modelled; they are the terrain left showing between the blocks,
#: which is how the office's own files do it (a roads mesh with the blocks
#: as holes, and a footpath mesh per block).
KERB_M = 0.15

#: The surface a heritage item stands in, made in the project on the first
#: run that needs it: the sheets' heritage ochre, so the reader who saw the
#: hatch on the context analysis finds the same colour in the model.
HERITAGE_SURFACE = "LORIINI HERITAGE"
HERITAGE_RGB = (0.663, 0.482, 0.247)
#: What the terrain mesh and the street blocks stand in. The terrain is what
#: shows between the blocks, which is the roads; the blocks are the ground the
#: buildings stand on. Both were in the Mesh tool's own surface until 11
#: November 2026, which on the Australian template is grass: a model that was
#: one green, where a road could not be told from a lot.
ROAD_SURFACE = "LORIINI ROAD"
ROAD_RGB = (0.45, 0.46, 0.48)
GROUND_SURFACE = "LORIINI GROUND"
GROUND_RGB = (0.55, 0.65, 0.42)
#: Every surface the model names, with its colour, by name.
SURFACES: dict[str, tuple[float, float, float]] = {
    HERITAGE_SURFACE: HERITAGE_RGB,
    ROAD_SURFACE: ROAD_RGB,
    GROUND_SURFACE: GROUND_RGB,
}

#: How far the terrain's skirt drops below its lowest point.
SKIRT_M = 2.0


@dataclass(frozen=True)
class ContextModelReport:
    terrain: bool
    contours: int
    blocks: int
    """Street blocks as kerbed meshes; the roads are the terrain between them."""
    buildings: int
    assumed: int
    """Buildings whose storeys came from the LEP control or the default."""
    on_site: int
    """Footprints inside the site, left out."""
    layer: str
    """The buildings' layer."""
    notes: tuple[str, ...] = ()
    mesh: MeshLines | None = None
    """How the contours became the mesh's level lines."""
    contour_source: str = ""
    """Whose contours: ``CITY OF SYDNEY 2020 SURVEY / NSW SPATIAL SERVICES``."""
    terrain_layer: str = ""
    roads_layer: str = ""
    heritage: int = 0
    """Neighbours on a heritage item, stood in ``HERITAGE_SURFACE``."""

    def describe(self) -> str:
        made = f"one mesh from {self.contours} contours"
        if self.contour_source:
            made += f" ({self.contour_source})"
        if self.terrain_layer:
            made += f" on {self.terrain_layer!r}"
        if self.mesh is not None:
            made += f" -- {self.mesh.describe()}"
        lines = [
            "  terrain: " + (made if self.terrain else "not made"),
            f"  blocks: {self.blocks} meshes {KERB_M * 1000:.0f} mm above the ground"
            + (f" on {self.roads_layer!r}" if self.roads_layer else "")
            + "; the roads are the terrain between them",
            f"  neighbours: {self.buildings} slabs on {self.layer!r}, {self.assumed} with assumed "
            f"storeys, {self.on_site} footprints on the site left out"
            + (
                f"; {self.heritage} on heritage items in the {HERITAGE_SURFACE!r} surface"
                if self.heritage
                else ""
            ),
        ]
        lines.extend(f"    {note}" for note in self.notes)
        return "\n".join(lines)


# -- the location ---------------------------------------------------------------


def set_project_location(
    connection: ArchicadConnection,
    geo: GeoLocation | None,
    site_centre: tuple[float, float],
    *,
    ground_m: float | None = None,
    north_bearing_deg: float | None = None,
) -> GeoLocation:
    """Put the project at the site: ``SetGeoLocation`` with the centre's
    longitude and latitude and the survey point on the MGA2020 grid.

    North is kept as the project has it unless ``north_bearing_deg`` says
    otherwise. Keeping it is a design decision -- turning it would move
    nothing already modelled; only the sun and the georeference follow the
    location. The one caller that gives a bearing is the site tools squaring
    an empty project to the site, whose frame *is* the project's new north,
    and the sun would be wrong by the turn without it. Returns what was set.
    """
    lon, lat = site_centre
    zone = mga_zone(lon)
    east, north = lonlat_to_mga(lon, lat, zone)
    altitude = ground_m if ground_m is not None else (geo.altitude_m if geo else 0.0)
    if north_bearing_deg is not None:
        north_rad = north_radians_from_bearing(north_bearing_deg)
    else:
        north_rad = geo.north_radians if geo else 0.0
    response = connection.run_tapir(
        "SetGeoLocation",
        {
            "projectLocation": {
                "longitude": lon,
                "latitude": lat,
                "altitude": altitude,
                "north": north_rad,
            },
            "surveyPoint": {
                "position": {"eastings": east, "northings": north, "elevation": altitude},
                "geoReferencingParameters": {
                    "crsName": f"EPSG:{7800 + zone}",
                    "description": f"GDA2020 / MGA zone {zone}",
                    "geodeticDatum": "GDA2020",
                    "verticalDatum": "AHD",
                    "mapProjection": "Transverse Mercator",
                    "mapZone": str(zone),
                },
            },
        },
    )
    if isinstance(response, dict) and response.get("success") is False:
        raise ArchicadError(f"SetGeoLocation answered {response!r}")
    return GeoLocation(
        latitude_deg=lat, longitude_deg=lon, altitude_m=altitude, north_radians=north_rad
    )


# -- the ground and the storeys ---------------------------------------------------


def _contours(bundle: SiteBundle, frame: Frame) -> list[tuple[float, list[Point]]]:
    return [(c.elevation, frame.ring(c.coords)) for c in bundle.contours if len(c.coords) >= 2]


class _Ground:
    """The ground level anywhere, from the contours: ``site.ground.Ground``,
    the site sheet's own reading across the slope, answering zero where there
    are no contours at all -- the level the model stood on before it had any.

    The interval is read off the lines when not given: the finest of whoever
    drew them, which bounds how far a slope is carried past its last contour.
    """

    def __init__(
        self,
        contours: Sequence[tuple[float, Sequence[Point]]],
        interval_m: float | None = None,
    ) -> None:
        self.ground = Ground(contours, interval_m=interval_m or _interval(contours))
        self.empty = self.ground.empty

    def at(self, point: Point) -> float:
        level = self.ground.at(point)
        return 0.0 if level is None else level


def _ground_for(bundle: SiteBundle, contours: Sequence[tuple[float, Sequence[Point]]]) -> _Ground:
    """The ground under the model, read at the interval of whoever drew the
    bundle's contours: 1 m for the City of Sydney's, 2 m for the state's."""
    described = whose_contours(bundle.contours)
    return _Ground(contours, described[0] if described else None)


def _interval(contours: Sequence[tuple[float, Sequence[Point]]]) -> float:
    """The contour interval the levels show: the smallest step between two of
    them, and the state's 2 m when there are too few to tell."""
    levels = sorted({round(level, 3) for level, _ in contours})
    steps = [b - a for a, b in pairwise(levels) if b - a > 1e-6]
    return min(steps) if steps else 2.0


def storeys_of(
    levels: int | None,
    height_m: float | None,
    hob_m: float | None,
    *,
    storey_m: float = STOREY_M,
) -> tuple[int, bool]:
    """How many storeys a building gets, and whether that was assumed.

    OSM's storey count first, its recorded height next; failing both, the
    LEP height-of-building control at the point, which is what could stand
    there rather than what does; failing that, two.
    """
    if levels and levels > 0:
        return levels, False
    if height_m and height_m > 0:
        return max(1, round(height_m / storey_m)), False
    if hob_m and hob_m > 0:
        return max(1, int(hob_m / storey_m)), True
    return 2, True


class _Heights:
    """The LEP height-of-building control at a point, boxes checked first."""

    def __init__(self, bundle: SiteBundle) -> None:
        self.zones: list[tuple[tuple[float, float, float, float], list[list[Point]], float]] = []
        for feature in bundle.height_of_building.get("features", []):
            try:
                value = float(feature["properties"].get("MAX_B_H"))
            except (TypeError, ValueError):
                continue
            rings = rings_of(feature.get("geometry"))
            if not rings:
                continue
            xs = [x for ring in rings for x, _ in ring]
            ys = [y for ring in rings for _, y in ring]
            self.zones.append(((min(xs), min(ys), max(xs), max(ys)), rings, value))

    def at(self, lon: float, lat: float) -> float | None:
        for (x0, y0, x1, y1), rings, value in self.zones:
            if x0 <= lon <= x1 and y0 <= lat <= y1:
                if any(point_in_ring(lon, lat, ring) for ring in rings):
                    return value
        return None


# -- the model ----------------------------------------------------------------------


#: What the context model's own elements are marked with.
OWN_IDS: tuple[str, ...] = ("SA NEIGHBOUR", "SA TERRAIN", "SA BLOCK")


def _clear_previous(connection: ArchicadConnection, prefixes: Sequence[str] = OWN_IDS) -> int:
    """Delete the slabs and meshes of the last run: what sits on the tool's
    layer and carries its ID. Returns how many went.

    By the ID alone: the ID is the tool's own mark, and a slab a failed
    move left off the layer still carries it. Three runs had stacked ninety
    slabs before this existed. ``prefixes`` says whose: the context model's
    by default, the future context's when that is what is being remade, so
    neither run deletes the other's.
    """
    wanted = tuple(prefixes)
    doomed: list[dict[str, Any]] = []
    for kind in ("Slab", "Mesh"):
        found = connection.run_tapir("GetElementsByType", {"elementType": kind})
        # Blocks carry "SA BLOCK n"; they go with the rest.
        elements = found.get("elements") if isinstance(found, dict) else None
        if not isinstance(elements, list) or not elements:
            continue
        details = connection.run_tapir("GetDetailsOfElements", {"elements": elements})
        rows = details.get("detailsOfElements") if isinstance(details, dict) else None
        if not isinstance(rows, list) or len(rows) != len(elements):
            continue
        doomed.extend(
            element
            for element, row in zip(elements, rows, strict=True)
            if isinstance(row, dict) and str(row.get("id", "")).startswith(wanted)
        )
    if doomed:
        connection.run_tapir("DeleteElements", {"elements": doomed})
    return len(doomed)


def _on_the_floor_plan(connection: ArchicadConnection) -> None:
    """Make the floor plan the current database, and check that it is.

    A slab or a mesh is a model element and cannot be created while a
    worksheet or a layout is current, which is where the sheets leave the
    run standing. Tapir's ``ChangeWindow`` moves the database while the
    window stays (D40); the add-on's ``GetCurrentDatabase`` says whether it
    did, since the answer is not to be believed.
    """
    here = connection.run_loriini("GetCurrentDatabase", {})
    if not (isinstance(here, dict) and here.get("windowType") == "FloorPlan"):
        connection.run_tapir("ChangeWindow", {"windowType": "FloorPlan"})
        here = connection.run_loriini("GetCurrentDatabase", {})
    if isinstance(here, dict) and here.get("windowType") == "FloorPlan":
        # Tell the connection, which otherwise remembers the layout the
        # sheets left it in and refuses every layer read (D63).
        connection.note_model_database(str((here.get("databaseId") or {}).get("guid", "")))
        return
    if True:
        raise ArchicadError(
            "The floor plan could not be made the current database, and a slab or a "
            "mesh cannot be created anywhere else. Click a storey in the Project Map "
            "and run again."
        )


# -- the boundary drawn in the file --------------------------------------------------


def boundary_layer(connection: ArchicadConnection, wanted: str = "auto") -> str | None:
    """The layer the site boundary is drawn on: the one named, or with
    ``"auto"`` the first layer whose name mentions a boundary."""
    response = connection.run_tapir("GetAttributesByType", {"attributeType": "Layer"})
    attributes = response.get("attributes") if isinstance(response, dict) else None
    if not isinstance(attributes, list):
        return None
    names = [str(a.get("name", "")) for a in attributes if isinstance(a, dict)]
    if wanted != "auto":
        return next((n for n in names if n.casefold() == wanted.casefold()), None)
    return next((n for n in names if "boundar" in n.casefold()), None)


def boundary_points(connection: ArchicadConnection, layer_name: str) -> list[Point]:
    """Every point of every 2D element on the layer, in project metres:
    object origins, line ends, polyline and fill vertices. Reads the current
    database, so it wants the floor plan in front."""
    response = connection.run_tapir("GetAttributesByType", {"attributeType": "Layer"})
    attributes = response.get("attributes") if isinstance(response, dict) else None
    indexes = {
        a.get("index")
        for a in (attributes or [])
        if isinstance(a, dict) and str(a.get("name", "")).casefold() == layer_name.casefold()
    }
    points: list[Point] = []
    for kind in ("Object", "Line", "PolyLine", "Hatch", "Arc"):
        try:
            found = connection.run_tapir("GetElementsByType", {"elementType": kind})
        except ArchicadError:
            continue
        elements = found.get("elements") if isinstance(found, dict) else None
        if not isinstance(elements, list) or not elements:
            continue
        details = connection.run_tapir("GetDetailsOfElements", {"elements": elements})
        rows = details.get("detailsOfElements") if isinstance(details, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("layerIndex") not in indexes:
                continue
            d = row.get("details") or {}
            for key in ("origin", "begCoordinate", "endCoordinate"):
                p = d.get(key)
                if isinstance(p, dict) and "x" in p and "y" in p:
                    points.append((float(p["x"]), float(p["y"])))
            for key in ("coordinates", "polygonCoordinates"):
                for p in d.get(key) or []:
                    if isinstance(p, dict) and "x" in p and "y" in p:
                        points.append((float(p["x"]), float(p["y"])))
    return points


# -- the blocks ---------------------------------------------------------------------


def _blocks(bundle: SiteBundle, frame: Frame) -> tuple[list[list[Point]], int]:
    """The street blocks, in the project frame: the cadastral lots clipped to
    the extent, grouped by touching, each group dissolved to its outline.

    The site's own lots are left out, so the block they sit in has a notch
    where the site is and the project's own site model shows there. A
    group whose lots will not dissolve cleanly (three edges meeting at a
    point) falls back to its lots one by one. Returns the rings and how many
    groups fell back.
    """
    e = bundle.extent
    inset = 1.0
    site_keys = {
        _ring_key(ring)
        for feature in bundle.site_lots.get("features", [])
        for ring in rings_of(feature.get("geometry"))
    }
    lots: list[list[Point]] = []
    for feature in bundle.all_lots.get("features", []):
        for ring in rings_of(feature.get("geometry")):
            if _ring_key(ring) in site_keys:
                continue
            merc = [lonlat_to_mercator(lon, lat) for lon, lat in ring]
            clipped = clip_ring(
                merc, e.xmin + inset, e.ymin + inset, e.xmax - inset, e.ymax - inset
            )
            if len(clipped) < 3:
                continue
            projected = _clean_ring(frame.ring([mercator_to_lonlat(x, y) for x, y in clipped]))
            if len(projected) >= 3 and abs(ring_area(projected)) > 1.0:
                lots.append(projected)
    # Strata lots stack on one footprint; one ring of each, or the shared
    # edges are counted five times and the block loses its side.
    seen: set[tuple[tuple[int, int], ...]] = set()
    unique: list[list[Point]] = []
    for ring in lots:
        signature = tuple(sorted((round(x / 0.05), round(y / 0.05)) for x, y in ring))
        if signature not in seen:
            seen.add(signature)
            unique.append(ring)
    lots = unique
    if not lots:
        return [], 0

    # Group by a shared vertex: lots across a road share none.
    def key(p: Point) -> tuple[int, int]:
        return (round(p[0] / 0.05), round(p[1] / 0.05))

    parent = list(range(len(lots)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first_seen: dict[tuple[int, int], int] = {}
    for i, ring in enumerate(lots):
        for p in ring:
            k = key(p)
            j = first_seen.setdefault(k, i)
            if j != i:
                parent[find(i)] = find(j)
    groups: dict[int, list[list[Point]]] = {}
    for i, ring in enumerate(lots):
        groups.setdefault(find(i), []).append(ring)

    blocks: list[list[Point]] = []
    fell_back = 0
    for members in groups.values():
        merged = dissolve(members, tolerance=0.05) if len(members) > 1 else members
        if not merged:
            fell_back += 1
            merged = members
        blocks.extend(ring for ring in merged if len(ring) >= 3 and abs(ring_area(ring)) > 1.0)
    return blocks, fell_back


def _ring_key(ring: Sequence[Point]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((round(x * 1e6), round(y * 1e6)) for x, y in ring))


#: How far apart a block's outline is sampled for its ground level. A block's
#: corners alone left its long sides straight across a slope the terrain
#: curves over, and the terrain showed through.
BLOCK_EDGE_STEP_M = 4.0


def _densified(ring: Sequence[Point], step: float = BLOCK_EDGE_STEP_M) -> list[Point]:
    """The ring with a point at least every ``step`` metres along each edge."""
    out: list[Point] = []
    for a, b in pairwise([*ring, ring[0]]):
        out.append(a)
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        pieces = max(1, math.ceil(length / step - 1e-9))
        for k in range(1, pieces):
            t = k / pieces
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def _lines_inside(
    lines: Sequence[tuple[float, Sequence[Point]]], ring: Sequence[Point]
) -> list[tuple[float, list[Point]]]:
    """The terrain's level lines, cut to what lies inside one block.

    Vertex by vertex: a run of vertices inside the ring is one piece, and a
    vertex outside ends it. The stretch between the last vertex in and the
    block's edge is left to the edge's own samples (``_densified``), which
    keeps every level line point clear of the mesh's outline -- Archicad
    refuses a mesh whose level line touches its boundary.
    """
    xs = [x for x, _ in ring]
    ys = [y for _, y in ring]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pieces: list[tuple[float, list[Point]]] = []
    for level, points in lines:
        run: list[Point] = []
        for x, y in points:
            if x0 < x < x1 and y0 < y < y1 and point_in_ring(x, y, ring):
                run.append((x, y))
                continue
            if len(run) >= 2:
                pieces.append((level, run))
            run = []
        if len(run) >= 2:
            pieces.append((level, run))
    return pieces


def _block_meshes(
    connection: ArchicadConnection,
    blocks: Sequence[Sequence[Point]],
    ground: _Ground,
    layer_index: int,
    floor_index: int,
    floor_level: float,
    datum_m: float = 0.0,
    terrain_lines: Sequence[tuple[float, Sequence[Point]]] = (),
    notes: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """One kerbed mesh per block, draped over the ground the terrain mesh is:
    its outline sampled every few metres, and the terrain's own level lines
    inside it, all lifted by the kerb. Without the lines a block is flat
    between its corners and the terrain shows through it wherever the ground
    rises inside (asked 17 October 2026). Returns the meshes made and what
    was refused."""
    made: list[dict[str, Any]] = []
    problems: list[str] = []
    lift = KERB_M - floor_level - datum_m
    # Asked for until one is refused: an add-on that takes no surface on a
    # mesh takes none on the next, and each refusal is a request wasted.
    surfaced = True
    for i, ring in enumerate(blocks):
        outline = [{"x": x, "y": y, "z": ground.at((x, y)) + lift} for x, y in _densified(ring)]
        inside = [
            [{"x": x, "y": y, "z": level + lift} for x, y in points]
            for level, points in _lines_inside(terrain_lines, ring)
        ]
        lowest = min([p["z"] for p in outline] + [line[0]["z"] for line in inside])
        try:
            answer, took = _create_mesh(
                connection,
                {
                    "outline": outline,
                    "levelLines": inside,
                    "skirt": "solid",
                    "skirtLevel": _skirt_depth(lowest - SKIRT_M),
                    "layerIndex": layer_index,
                    "floorIndex": floor_index,
                    "elementId": f"SA BLOCK {i + 1}",
                },
                GROUND_SURFACE if surfaced else None,
            )
            surfaced = surfaced and took
        except ArchicadError as error:
            problems.append(str(error))
            continue
        if isinstance(answer, dict) and answer.get("success", True) and answer.get("guid"):
            made.append({"elementId": {"guid": str(answer["guid"])}})
        else:
            problems.append(str(answer))
    if made and not surfaced and notes is not None and _NO_MESH_SURFACE not in notes:
        notes.append(_NO_MESH_SURFACE)
    return made, problems


#: Said once a run when the add-on installed is older than the surfaces.
_NO_MESH_SURFACE = (
    "this add-on takes no surface on a mesh, so the roads and the blocks are both in the "
    "Mesh tool's own; a newer add-on colours them apart."
)


def _create_mesh(
    connection: ArchicadConnection, request: dict[str, Any], surface: str | None
) -> tuple[Any, bool]:
    """Loriini's ``CreateMesh``, in a surface where the add-on takes one.

    The command's schema refuses a field it does not know, so an add-on built
    before meshes took a surface answers the whole request with an error. It
    is asked again without, and the caller told the surface was not taken:
    a model in one colour is better than no model. A refusal that was about
    something else comes back from the second request as it did the first.
    """
    if surface is not None:
        try:
            with_surface = {**request, "surface": _surface_request(surface)}
            return connection.run_loriini("CreateMesh", with_surface), True
        except ArchicadError as error:
            if "not have the registered" in str(error):
                raise
    return connection.run_loriini("CreateMesh", request), False


#: What ``--datum`` takes, and what each means as a level to subtract.
#: ``project`` reads Project Location's altitude; ``sea`` subtracts nothing,
#: which puts the model at true AHD and is right for a project whose zero
#: already is sea level.
DATUM_CHOICES = ("project", "sea")

DATUM_HELP = (
    "What project zero stands for, which is what the model is placed against: "
    "'project' reads Project Location's altitude (the site's ground), 'sea' "
    "places at true AHD levels, or give the metres yourself."
)


def parse_datum(text: str | None) -> float | None:
    """``project`` -> ``None`` (read it from the project), ``sea`` -> ``0.0``,
    or a number of metres. Raises ``ValueError`` naming the words."""
    wanted = " ".join((text or "").split()).lower()
    if not wanted or wanted == "project":
        return None
    if wanted in ("sea", "ahd", "0", "sealevel", "sea level"):
        return 0.0
    try:
        return float(wanted)
    except ValueError as bad:
        raise ValueError(
            f"--datum takes 'project', 'sea', or a number of metres. {text!r} is none of those."
        ) from bad


def project_datum(connection: ArchicadConnection) -> float:
    """The RL that project zero stands for: Project Location's altitude.

    The contours are AHD levels and the project's altitude says what RL the
    project's own zero is, so a model placed at the raw contour level counts
    the site's height above sea level twice -- at Bondi that stood the whole
    neighbourhood 75.8 m above the storeys it was supposed to sit around
    (measured, 14 September 2026). Everything the model places is therefore
    put at ``level - datum``.

    Zero when the location cannot be read, which is the old behaviour and
    right for a project whose zero already is sea level.
    """
    try:
        geo = read_geo_location(connection)
    except ArchicadError:
        return 0.0
    return float(geo.altitude_m or 0.0)


def _datum_storey(connection: ArchicadConnection) -> tuple[int, float]:
    """The storey nearest level zero, and its level: ``(index, level)``.

    Absolute heights go in relative to it. ``(0, 0.0)`` when the storeys
    cannot be read, which is right for a project whose first storey is the
    datum, as the office's are.
    """
    try:
        response = connection.run_tapir("GetStories", {})
    except ArchicadError:
        return 0, 0.0
    stories = response.get("stories") if isinstance(response, dict) else None
    best: tuple[int, float] | None = None
    for story in stories if isinstance(stories, list) else []:
        if not isinstance(story, dict):
            continue
        try:
            index, level = int(story["index"]), float(story.get("level", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if best is None or abs(level) < abs(best[1]):
            best = (index, level)
    return best or (0, 0.0)


def _skirt_depth(lowest: float, mesh_level: float = 0.0) -> float:
    """What to send as ``skirtLevel`` to put the skirt's bottom at ``lowest``.

    Not the level. Archicad stores the skirt as a *depth below the mesh's own
    level, positive downward*, which is not what the field's name suggests and
    is the opposite sign of everything else in this module.

    Measured on the Bondi context, 15 September 2026, after the terrain came
    out as a solid plate above the neighbourhood with the ground hanging under
    it. The mesh surface was right -- west high toward Bondi Junction, east low
    toward the beach -- and the body was inside out: a skirt sent as -53.818
    put the solid between the surface and *+53.8*, mirrored about the mesh
    level, and Archicad then read the field back as +53.818 for a skirt whose
    bottom sits 53.8 m down. Sending the depth puts it where the name implied.

    Kept as a function with the measurement beside it because the sign is
    invisible in the result until somebody looks at the model from below: a
    run reports the same counts either way.
    """
    return mesh_level - lowest


def level_lines(
    bundle: SiteBundle,
    frame: Frame,
    contours: Sequence[tuple[float, list[Point]]],
    *,
    budget: int = MESH_POINTS,
) -> MeshLines:
    """The contours as the terrain mesh's level lines: cut to the model's
    square, every one kept and barely simplified near the site, fewer and
    simpler towards the edge, in no more than ``budget`` vertices."""
    described = whose_contours(bundle.contours)
    return mesh_lines(
        contours,
        focus=[frame.ring(ring) for ring in bundle.site_rings],
        within=_map_rectangle(bundle, frame),
        budget=budget,
        interval_m=described[0] if described else _interval(contours),
    )


def _terrain(
    connection: ArchicadConnection,
    bundle: SiteBundle,
    frame: Frame,
    contours: Sequence[tuple[float, list[Point]]],
    layer_index: int,
    datum_m: float = 0.0,
    ground: _Ground | None = None,
    notes: list[str] | None = None,
) -> tuple[list[dict[str, Any]], MeshLines]:
    """One Mesh: the model's square at ground level, with the contours as its
    level lines. Returns what was made and how the lines were chosen."""
    # A mesh's levels are relative to its home storey, and the Mesh tool's
    # default storey was 39 on the Kogarah study, which put the terrain a
    # hundred metres in the air. Home it on the storey nearest level zero
    # and give every point its height above that.
    floor_index, floor_level = _datum_storey(connection)
    ground = ground or _ground_for(bundle, contours)
    corners = _map_rectangle(bundle, frame)
    outline = [{"x": x, "y": y, "z": ground.at((x, y)) - floor_level - datum_m} for x, y in corners]
    lines = level_lines(bundle, frame, contours)
    sublines: list[dict[str, Any]] = [
        {"coordinates": [{"x": x, "y": y, "z": level - floor_level - datum_m} for x, y in points]}
        for level, points in lines.lines
        if len(points) >= 2
    ]
    lowest = min([p["z"] for p in outline] + [s["coordinates"][0]["z"] for s in sublines])
    # The add-on's command first: Tapir's CreateMeshes answers APIERR_BADINDEX
    # for every mesh on Archicad 26 (measured), so it is only the fallback
    # for an add-on built before the command existed.
    try:
        answer, took = _create_mesh(
            connection,
            {
                "outline": outline,
                "levelLines": [s["coordinates"] for s in sublines],
                "skirt": "solid",
                "skirtLevel": _skirt_depth(lowest - SKIRT_M),
                "layerIndex": layer_index,
                "floorIndex": floor_index,
                "elementId": "SA TERRAIN",
            },
            ROAD_SURFACE,
        )
        guid = str(answer.get("guid", "")) if isinstance(answer, dict) else ""
        if guid:
            if not took and notes is not None and _NO_MESH_SURFACE not in notes:
                notes.append(_NO_MESH_SURFACE)
            return [{"elementId": {"guid": guid}}], lines
        raise ArchicadError(f"CreateMesh answered {answer!r}")
    except ArchicadError as error:
        if "not have the registered" not in str(error):
            raise
    response = connection.run_tapir(
        "CreateMeshes",
        {
            "meshesData": [
                {
                    "level": 0.0,
                    "polygonCoordinates": outline,
                    "sublines": sublines,
                    "skirtType": "SolidBodyWithSkirt",
                    "skirtLevel": _skirt_depth(lowest - SKIRT_M),
                    "ridges": "UserDefined",
                    "showLines": False,
                }
            ]
        },
    )
    made = _elements(response, "CreateMeshes")
    move_to_layer(connection, made, layer_index)
    stamp_in_order(connection, made, ["SA TERRAIN"])
    return made, lines


def _elements(response: Any, command: str) -> list[dict[str, Any]]:
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
    return [e for e in elements if isinstance(e, dict) and "elementId" in e]


def _heritage_rings(bundle: SiteBundle, frame: Frame) -> list[list[Point]]:
    """The heritage items' outlines in the frame: the LEP's items, not its
    conservation areas, which take in whole streets of ordinary houses. The
    same reading the context sheet makes of the layer."""
    rings: list[list[Point]] = []
    for feature in bundle.heritage.get("features", []):
        if not str(feature.get("properties", {}).get("LAY_CLASS") or "Item").startswith("Item"):
            continue
        for ring in rings_of(feature.get("geometry")):
            placed = frame.ring(ring)
            if len(placed) >= 3:
                rings.append(placed)
    return rings


def model_context(
    connection: ArchicadConnection,
    bundle: SiteBundle,
    frame: Frame,
    *,
    terrain: bool = True,
    buildings: bool = True,
    blocks: bool = True,
    storey_m: float = STOREY_M,
    datum_m: float | None = None,
    say: Callable[[str], None] | None = None,
) -> ContextModelReport:
    """The terrain, the street blocks and the neighbours, each on its own
    layer under the office's site group -- see ``naming.TERRAIN_PART``."""
    _on_the_floor_plan(connection)
    # Made only for what is asked for, so a run of buildings alone does not
    # leave two empty layers behind it.
    ground_layer = ensure_layer(connection, naming.terrain_layer()) if terrain else None
    roads_layer = ensure_layer(connection, naming.roads_layer()) if blocks else None
    layer = ensure_layer(connection, layer_name())
    contours = _contours(bundle, frame)
    ground = _ground_for(bundle, contours)
    datum = project_datum(connection) if datum_m is None else datum_m
    heights = _Heights(bundle)
    notes: list[str] = []
    if datum:
        notes.append(f"placed against a datum of {datum:,.2f} m.")
    removed = _clear_previous(connection)
    if removed:
        notes.append(f"{removed} slabs and meshes from the last run removed first.")

    made_terrain = False
    lines: MeshLines | None = None
    if terrain:
        if not contours:
            notes.append("no contours in the bundle; the terrain is not made.")
        else:
            try:
                assert ground_layer is not None
                _, lines = _terrain(
                    connection,
                    bundle,
                    frame,
                    contours,
                    ground_layer.index,
                    datum,
                    ground=ground,
                    notes=notes,
                )
                made_terrain = True
            except ArchicadError as error:
                notes.append(f"the terrain mesh was refused: {error}")

    made_blocks = 0
    block_meshes: list[dict[str, Any]] = []
    if blocks and bundle.all_lots.get("features"):
        rings, fell_back = _blocks(bundle, frame)
        if fell_back:
            notes.append(f"{fell_back} blocks would not dissolve and are drawn lot by lot.")
        if rings:
            floor_index, floor_level = _datum_storey(connection)
            block_meshes, refused = _block_meshes(
                connection,
                rings,
                ground,
                roads_layer.index if roads_layer is not None else layer.index,
                floor_index,
                floor_level,
                datum,
                terrain_lines=(
                    lines.lines
                    if lines is not None
                    else level_lines(bundle, frame, contours).lines
                    if contours
                    else ()
                ),
                notes=notes,
            )
            made_blocks = len(block_meshes)
            if refused:
                notes.append(f"{len(refused)} block meshes were refused, e.g. {refused[0][:120]}")
    lift = KERB_M if made_blocks else 0.0

    site_rings = [frame.ring(ring) for ring in bundle.site_rings]
    heritage_rings = _heritage_rings(bundle, frame)
    slabs: list[_Slab] = []
    assumed = 0
    on_site = 0
    unusable = 0
    listed = 0
    if buildings:
        for building in bundle.furniture.buildings:
            ring = _slab_outline(frame.ring(building.ring))
            if len(ring) < 3 or abs(ring_area(ring)) < 4.0:
                unusable += int(len(building.ring) >= 3)
                continue
            centre = ring_centroid(ring)
            if any(point_in_ring(centre[0], centre[1], site) for site in site_rings):
                on_site += 1
                continue
            storeys, guessed = storeys_of(
                building.levels,
                building.height_m,
                heights.at(building.lon, building.lat),
                storey_m=storey_m,
            )
            assumed += int(guessed)
            holes = [
                hole
                for hole in (_slab_outline(frame.ring(h)) for h in building.holes)
                if len(hole) >= 3 and abs(ring_area(hole)) >= 1.0
            ]
            heritage = any(point_in_ring(centre[0], centre[1], r) for r in heritage_rings)
            listed += int(heritage)
            slabs.append(
                _Slab(
                    outline=ring,
                    holes=holes,
                    level=ground.at(centre) + lift - datum,
                    thickness=storeys * storey_m,
                    identifier=(
                        f"SA NEIGHBOUR {storeys} STOREY ({'ASSUMED' if guessed else 'OSM'})"
                        + (" HERITAGE" if heritage else "")
                    ),
                    surface=HERITAGE_SURFACE if heritage else None,
                )
            )
    if unusable:
        notes.append(
            f"{unusable} footprints were too small or too broken to stand up after tidying."
        )
    floor_index = _datum_storey(connection)[0]
    # The add-on's CreateSlabs takes the layer, the storey and the ID with
    # the outline, so the three passes Tapir needs (create, move, stamp) are
    # one; Tapir's is the fallback for an add-on built before it existed.
    outcome = _create_slabs(
        partial(_send_through_the_addon, connection, layer.index, floor_index), slabs
    )
    if outcome is None:
        outcome = _create_slabs(partial(_send_through_tapir, connection), slabs)
        if listed:
            notes.append(
                f"{listed} neighbours on heritage items stand in the default surface: "
                "Tapir's CreateSlabs takes no surface, and the add-on predates its own."
            )
        if outcome is not None and outcome.made:
            elements = [element for element, _ in outcome.made]
            moved = move_to_layer(connection, elements, layer.index)
            if moved != len(elements):
                notes.append(
                    f"{len(elements) - moved} slabs stayed on the Slab tool's default layer."
                )
            stamp_in_order(connection, elements, [name for _, name in outcome.made])
    made = [] if outcome is None else [element for element, _ in outcome.made]
    if outcome is not None:
        notes.extend(outcome.describe())
    notes.extend(
        _grouped(connection, [(block_meshes, "street blocks"), (made, "neighbouring buildings")])
    )
    if say:
        say(
            f"  {len(made)} neighbours as slabs, {assumed} with assumed storeys"
            + (f", {listed} on heritage items" if listed else "")
        )
    described = whose_contours(bundle.contours)
    return ContextModelReport(
        terrain=made_terrain,
        contours=len(contours),
        blocks=made_blocks,
        buildings=len(made),
        assumed=assumed,
        on_site=on_site,
        layer=layer.name,
        notes=tuple(notes),
        mesh=lines,
        contour_source=described[1] if described else "",
        terrain_layer=ground_layer.name if ground_layer is not None else "",
        roads_layer=roads_layer.name if roads_layer is not None else "",
        heritage=listed,
    )


def _grouped(
    connection: ArchicadConnection, kinds: Sequence[tuple[Sequence[dict[str, Any]], str]]
) -> list[str]:
    """One Archicad Group per kind -- all the blocks, all the neighbours.

    So a click selects the whole street, and the neighbourhood moves, hides
    or deletes as the one thing it is, while every slab stays a slab of its
    own with its own storeys in its ID. Grouping never raises: a project that
    will not group still has its model, and the note says why it is loose.
    """
    said: list[str] = []
    for elements, what in kinds:
        if len(elements) < 2:
            continue
        report = group_by_value(connection, [(element, what) for element in elements])
        if report.complete:
            said.append(f"the {len(elements)} {what} are one group.")
        else:
            said.append(f"the {what} were not grouped: {report.problem}")
    return said


#: How many slabs go in one request. Each request is one undo step in
#: Archicad, which is also why one refused slab takes its whole request with
#: it -- see ``_create_slabs``.
SLAB_BATCH = 200


@dataclass(frozen=True)
class _Slab:
    """One neighbour, ready to send: its outline and holes in project
    metres, the level its bottom sits at, how tall it is, and its ID."""

    outline: list[Point]
    holes: list[list[Point]]
    level: float
    thickness: float
    identifier: str
    surface: str | None = None
    """A surface for every face, by name -- a key of ``SURFACES`` -- or the
    Slab tool's own."""

    def simpler(self) -> list[_Slab]:
        """What to try when Archicad will not take this one as drawn.

        First without its holes -- a courtyard filled in shades a little
        more than it should, which is the safe side for a sun study -- then
        as its convex hull, which is the same building with its notches
        filled. Either is better than a gap where a building stands.
        """
        tries: list[_Slab] = []
        if self.holes:
            tries.append(replace(self, holes=[]))
        hull = [(float(x), float(y)) for x, y in convex_hull(self.outline)]
        hull = _clean_ring(hull)
        if len(hull) >= 3 and hull != self.outline:
            tries.append(replace(self, outline=hull, holes=[]))
        return tries


class _NoSuchCommandError(Exception):
    """The add-on predates its own ``CreateSlabs``."""


@dataclass
class _Created:
    """What ``_create_slabs`` managed, and what it had to give up on."""

    made: list[tuple[dict[str, Any], str]] = field(default_factory=list)
    simplified: int = 0
    lost: list[str] = field(default_factory=list)

    def describe(self) -> list[str]:
        said: list[str] = []
        if self.simplified:
            said.append(
                f"{self.simplified} footprints Archicad would not take as drawn were "
                "stood up simplified -- holes filled, or as their convex hull."
            )
        if self.lost:
            said.append(
                f"{len(self.lost)} footprints were refused even simplified and are "
                f"missing, e.g. {self.lost[0][:160]}"
            )
        return said


def _create_slabs(
    send: Callable[[Sequence[_Slab]], list[dict[str, Any]]],
    slabs: Sequence[_Slab],
) -> _Created | None:
    """Every slab that Archicad will take, and only the bad ones lost.

    Archicad makes a whole request in one undo step and abandons the step at
    the first slab it refuses, so one footprint OSM drew with a spike or a
    crossing edge used to take up to 199 good neighbours out of the model
    with it -- a street with a gap in it, and a note nobody reads. A refused
    request is now halved and each half tried again, down to the one slab
    that is the problem, which is then tried simplified before it is given
    up on. A clean model costs the same one request per two hundred as
    before; a dirty one costs a few more requests and no buildings.

    ``None`` when the add-on has no ``CreateSlabs`` at all, so the caller
    can go the Tapir way instead.
    """
    done = _Created()

    def attempt(chunk: Sequence[_Slab]) -> None:
        try:
            elements = send(chunk)
        except ArchicadError as error:
            if len(chunk) > 1:
                middle = len(chunk) // 2
                attempt(chunk[:middle])
                attempt(chunk[middle:])
                return
            for simpler in chunk[0].simpler():
                try:
                    elements = send([simpler])
                except ArchicadError:
                    continue
                done.simplified += 1
                done.made.extend(zip(elements, [simpler.identifier], strict=False))
                return
            done.lost.append(str(error))
            return
        done.made.extend(zip(elements, [slab.identifier for slab in chunk], strict=False))

    try:
        for start in range(0, len(slabs), SLAB_BATCH):
            attempt(slabs[start : start + SLAB_BATCH])
    except _NoSuchCommandError:
        if done.made:  # pragma: no cover - a command does not vanish mid-run
            raise
        return None
    return done


def _surface_request(name: str) -> dict[str, Any]:
    """The surface as ``CreateSlabs`` takes it: its name, and the colour to
    make it in when the project has none by that name."""
    red, green, blue = SURFACES[name]
    return {"name": name, "colour": {"red": red, "green": green, "blue": blue}}


def _send_through_the_addon(
    connection: ArchicadConnection,
    layer_index: int,
    floor_index: int,
    chunk: Sequence[_Slab],
) -> list[dict[str, Any]]:
    """One request to Loriini's ``CreateSlabs``: the created slabs, in order."""
    batch = [
        {
            "contours": [
                {"points": [{"x": x, "y": y} for x, y in ring]}
                for ring in (slab.outline, *slab.holes)
            ],
            "level": slab.level,
            "thickness": slab.thickness,
            "referencePlane": "bottom",
            "layerIndex": layer_index,
            "floorIndex": floor_index,
            "elementId": slab.identifier[:255],
            **({"surface": _surface_request(slab.surface)} if slab.surface else {}),
        }
        for slab in chunk
    ]
    try:
        response = connection.run_loriini("CreateSlabs", {"slabs": batch})
    except ArchicadError as error:
        if "not have the registered" in str(error):
            raise _NoSuchCommandError from error
        raise
    elements = response.get("elements") if isinstance(response, dict) else None
    if not isinstance(elements, list) or len(elements) != len(chunk):
        raise ArchicadError(f"CreateSlabs answered without one element per slab: {response!r}")
    return [{"elementId": {"guid": str(e.get("guid", ""))}} for e in elements]


def _send_through_tapir(
    connection: ArchicadConnection, chunk: Sequence[_Slab]
) -> list[dict[str, Any]]:
    """One request to Tapir's ``CreateSlabs``. Holes are not sent this way:
    it is the path for an add-on too old to have its own, and a courtyard
    filled in is the safe side for a sun study."""
    response = connection.run_tapir(
        "CreateSlabs",
        {
            "slabsData": [
                {
                    "polygonCoordinates": [{"x": x, "y": y} for x, y in slab.outline],
                    "level": slab.level,
                    "thickness": slab.thickness,
                    "referencePlaneLocation": "Bottom",
                }
                for slab in chunk
            ]
        },
    )
    elements = _elements(response, "CreateSlabs")
    if len(elements) != len(chunk):
        raise ArchicadError(f"CreateSlabs made {len(elements)} of {len(chunk)} slabs.")
    return elements


def _slab_outline(ring: Sequence[Point]) -> list[Point]:
    """A footprint Archicad will take, as near to the one drawn as it can be.

    OSM outlines are drawn by hand, and what Archicad refuses in them is not
    exotic: two nodes a millimetre apart, a spike where a node was dragged
    out and back, three nodes in a line that make an edge of no width. So
    points closer than 5 mm are merged, and a vertex whose corner encloses
    less than a square centimetre -- a spike, or a point on a straight run --
    is taken out, until none is left. The building is the same building.
    """
    points = _clean_ring(ring)
    merged: list[Point] = []
    for point in points:
        if not merged or math.dist(point, merged[-1]) > 0.005:
            merged.append(point)
    if len(merged) > 1 and math.dist(merged[0], merged[-1]) <= 0.005:
        merged.pop()
    changed = True
    while changed and len(merged) > 3:
        changed = False
        for i in range(len(merged)):
            a, b, c = merged[i - 1], merged[i], merged[(i + 1) % len(merged)]
            corner = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0
            if corner < 1e-4:
                del merged[i]
                changed = True
                break
    return merged


def ground_at_site(bundle: SiteBundle, frame: Frame) -> float | None:
    """The ground level at the site's centre, for the project's altitude."""
    contours = _contours(bundle, frame)
    if not contours:
        return None
    centre = frame.project(*mercator_to_lonlat(*bundle.centre))
    return _ground_for(bundle, contours).at(centre)
