"""OpenStreetMap through Overpass: what NSW open data lacks.

Bus stops and routes for the context sheet; trees, hydrants, poles, lamps,
one-way streets, driveways, kerbside parking, utilities and building
footprints for the site sheet. Failure is soft: the sheet is drawn without.

Building footprints carry their ring and any recorded storey count, which is
what the next step -- a massing of the neighbours in the model -- will read.

Trees carry whatever size their tags record, through ``trees.tree_from_osm``;
where a council publishes its own inventory, the pipeline puts the council's
trees first and keeps OSM's only where the council has none.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sun_study.site.geo import Extent, Point, point_in_ring
from sun_study.site.http import Log, overpass
from sun_study.site.trees import Tree, tree_from_osm, trees_along_row

__all__ = [
    "Building",
    "BusData",
    "Furniture",
    "Stop",
    "Utility",
    "buildings",
    "bus_data",
    "cluster_stops",
    "furniture",
]


@dataclass(frozen=True)
class Stop:
    lon: float
    lat: float
    name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"lon": self.lon, "lat": self.lat, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Stop:
        return cls(float(data["lon"]), float(data["lat"]), data.get("name"))


def cluster_stops(stops: Sequence[Stop], within_m: float = 30.0) -> list[Stop]:
    """Stands, platforms and the two kerbs of one stop, as one symbol.

    Greedy, in metres: a stop within ``within_m`` of one already taken joins
    it, and the symbol sits at their mean. The office's sheets draw one
    roundel per stop; OSM records one node per kerb.
    """
    used = [False] * len(stops)
    clustered: list[Stop] = []
    metres_per_degree = 111_320.0
    for i, stop in enumerate(stops):
        if used[i]:
            continue
        group = [stop]
        used[i] = True
        for j in range(i + 1, len(stops)):
            if used[j]:
                continue
            dx = (stops[j].lon - stop.lon) * metres_per_degree * math.cos(math.radians(stop.lat))
            dy = (stops[j].lat - stop.lat) * metres_per_degree
            if math.hypot(dx, dy) < within_m:
                group.append(stops[j])
                used[j] = True
        clustered.append(
            Stop(
                sum(s.lon for s in group) / len(group),
                sum(s.lat for s in group) / len(group),
                group[0].name,
            )
        )
    return clustered


Line = tuple[Point, ...]


def _lines(data: list[Any]) -> tuple[Line, ...]:
    return tuple(tuple((float(x), float(y)) for x, y in line) for line in data or [])


def _lines_out(lines: tuple[Line, ...]) -> list[list[list[float]]]:
    return [[list(p) for p in line] for line in lines]


@dataclass(frozen=True)
class BusData:
    stops: tuple[Stop, ...] = ()
    routes: tuple[Line, ...] = ()
    tram_stops: tuple[Stop, ...] = ()
    tram_routes: tuple[Line, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "stops": [s.as_dict() for s in self.stops],
            "routes": _lines_out(self.routes),
            "tram_stops": [s.as_dict() for s in self.tram_stops],
            "tram_routes": _lines_out(self.tram_routes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BusData:
        return cls(
            tuple(Stop.from_dict(s) for s in data.get("stops") or []),
            _lines(data.get("routes") or []),
            tuple(Stop.from_dict(s) for s in data.get("tram_stops") or []),
            _lines(data.get("tram_routes") or []),
        )


def bus_data(extent: Extent, *, log: Log | None = None) -> BusData:
    south, west, north, east = extent.lonlat_bbox()
    bbox = f"{south},{west},{north},{east}"
    query = f"""[out:json][timeout:60];
(
  node["highway"="bus_stop"]({bbox});
  node["railway"="tram_stop"]({bbox});
  relation["route"="bus"]({bbox});
  relation["route"~"^(tram|light_rail)$"]({bbox});
);
out geom;"""
    data = overpass(query, log=log)

    stops: list[Stop] = []
    tram_stops: list[Stop] = []
    routes: list[Line] = []
    tram_routes: list[Line] = []
    seen_bus: set[int] = set()
    seen_tram: set[int] = set()
    for element in data.get("elements") or []:
        tags = element.get("tags") or {}
        if element.get("type") == "node":
            stop = Stop(float(element["lon"]), float(element["lat"]), tags.get("name"))
            if tags.get("highway") == "bus_stop":
                stops.append(stop)
            elif tags.get("railway") == "tram_stop":
                tram_stops.append(stop)
        elif element.get("type") == "relation":
            is_bus = tags.get("route") == "bus"
            is_tram = tags.get("route") in ("tram", "light_rail")
            if not is_bus and not is_tram:
                continue
            seen = seen_bus if is_bus else seen_tram
            target = routes if is_bus else tram_routes
            for member in element.get("members") or []:
                if member.get("type") != "way" or not member.get("geometry"):
                    continue
                if member.get("ref") in seen:
                    continue
                seen.add(member["ref"])
                target.append(tuple((float(g["lon"]), float(g["lat"])) for g in member["geometry"]))
    return BusData(
        tuple(cluster_stops(stops)),
        tuple(routes),
        tuple(cluster_stops(tram_stops)),
        tuple(tram_routes),
    )


@dataclass(frozen=True)
class Building:
    """A footprint, with its storeys and height where OSM records them."""

    lon: float
    lat: float
    ring: Line
    levels: int | None = None
    height_m: float | None = None
    holes: tuple[Line, ...] = ()
    """Courtyards and light wells. Only a multipolygon building has them."""

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "lon": self.lon,
            "lat": self.lat,
            "ring": [list(p) for p in self.ring],
            "levels": self.levels,
            "height_m": self.height_m,
        }
        if self.holes:
            data["holes"] = [[list(p) for p in hole] for hole in self.holes]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Building:
        return cls(
            float(data["lon"]),
            float(data["lat"]),
            tuple((float(x), float(y)) for x, y in data.get("ring") or []),
            int(data["levels"]) if data.get("levels") is not None else None,
            float(data["height_m"]) if data.get("height_m") is not None else None,
            tuple(tuple((float(x), float(y)) for x, y in hole) for hole in data.get("holes") or []),
        )


@dataclass(frozen=True)
class Utility:
    kind: str
    """``power``, ``water``, ``sewer`` or ``gas``."""
    coords: Line

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "coords": [list(p) for p in self.coords]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Utility:
        return cls(str(data["kind"]), tuple((float(x), float(y)) for x, y in data["coords"]))


@dataclass(frozen=True)
class Furniture:
    trees: tuple[Tree, ...] = ()
    """Every tree, each with a canopy to draw and whose record it is --
    OpenStreetMap's or a council's (``site.trees``)."""
    hydrants: tuple[Point, ...] = ()
    power_poles: tuple[Point, ...] = ()
    street_lamps: tuple[Point, ...] = ()
    oneway_roads: tuple[tuple[str | None, Line], ...] = ()
    buildings: tuple[Building, ...] = ()
    utilities: tuple[Utility, ...] = ()
    driveways: tuple[Line, ...] = ()
    parking_lanes: tuple[tuple[str, Line], ...] = field(default=())
    """``(side, line)`` with side ``left``, ``right`` or ``both``."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "trees": [t.as_dict() for t in self.trees],
            "hydrants": [list(p) for p in self.hydrants],
            "power_poles": [list(p) for p in self.power_poles],
            "street_lamps": [list(p) for p in self.street_lamps],
            "oneway_roads": [
                {"name": name, "coords": [list(p) for p in line]}
                for name, line in self.oneway_roads
            ],
            "buildings": [b.as_dict() for b in self.buildings],
            "utilities": [u.as_dict() for u in self.utilities],
            "driveways": _lines_out(self.driveways),
            "parking_lanes": [
                {"side": side, "coords": [list(p) for p in line]}
                for side, line in self.parking_lanes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Furniture:
        def points(key: str) -> tuple[Point, ...]:
            return tuple((float(x), float(y)) for x, y in data.get(key) or [])

        return cls(
            trees=tuple(Tree.from_dict(t) for t in data.get("trees") or []),
            hydrants=points("hydrants"),
            power_poles=points("power_poles"),
            street_lamps=points("street_lamps"),
            oneway_roads=tuple(
                (entry.get("name"), tuple((float(x), float(y)) for x, y in entry["coords"]))
                for entry in data.get("oneway_roads") or []
            ),
            buildings=tuple(Building.from_dict(b) for b in data.get("buildings") or []),
            utilities=tuple(Utility.from_dict(u) for u in data.get("utilities") or []),
            driveways=_lines(data.get("driveways") or []),
            parking_lanes=tuple(
                (str(entry["side"]), tuple((float(x), float(y)) for x, y in entry["coords"]))
                for entry in data.get("parking_lanes") or []
            ),
        )


def _parked(value: Any) -> bool:
    return bool(value) and value not in ("no", "none")


def _number(value: Any) -> float | None:
    try:
        return float(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _levels(tags: dict[str, Any]) -> int | None:
    """Storeys above ground, as OSM records them.

    ``building:levels`` first. A value OSM writes as a range or a list --
    ``3;4``, ``3-4`` -- is read as its largest, which is the one that casts
    the shadow; ``roof:levels`` is added, because a storey in the roof is a
    storey of height all the same.
    """
    raw = tags.get("building:levels")
    if raw is None:
        return None
    parts = [_number(part) for part in re.split(r"[;,\-]", str(raw))]
    counted = [part for part in parts if part is not None and part >= 0]
    if not counted:
        return None
    roof = _number(tags.get("roof:levels")) or 0.0
    return int(max(counted) + max(roof, 0.0))


def _building(tags: dict[str, Any], ring: Line, holes: Sequence[Line] = ()) -> Building:
    return Building(
        lon=sum(p[0] for p in ring) / len(ring),
        lat=sum(p[1] for p in ring) / len(ring),
        ring=ring,
        levels=_levels(tags),
        height_m=_number(tags.get("height")),
        holes=tuple(holes),
    )


def _stitched(pieces: Sequence[Line]) -> list[Line]:
    """Closed rings out of the ways a multipolygon's outline is split into.

    A courtyard block is often drawn as four ways, one per street front,
    and only their ends say how they join: each is appended to whichever
    open ring ends where it starts (turned round if it ends there instead)
    until the ring comes back to its own start. A ring that never closes is
    dropped -- it is a relation cut by the query's box, and half a building
    is worse than none.
    """
    open_rings: list[list[Point]] = []
    closed: list[Line] = []
    for piece in pieces:
        if len(piece) < 2:
            continue
        line = list(piece)
        joined = True
        while joined:
            joined = False
            for ring in open_rings:
                if ring[-1] == line[0]:
                    ring.extend(line[1:])
                elif ring[-1] == line[-1]:
                    ring.extend(reversed(line[:-1]))
                elif ring[0] == line[-1]:
                    ring[:0] = line[:-1]
                elif ring[0] == line[0]:
                    ring[:0] = list(reversed(line[1:]))
                else:
                    continue
                open_rings.remove(ring)
                line = ring
                joined = True
                break
        if len(line) >= 4 and line[0] == line[-1]:
            closed.append(tuple(line))
        else:
            open_rings.append(line)
    return closed


def _multipolygon(element: dict[str, Any]) -> list[tuple[Line, list[Line]]]:
    """A building relation's outlines, each with the holes that fall in it."""
    outer: list[Line] = []
    inner: list[Line] = []
    for member in element.get("members") or []:
        geometry = member.get("geometry")
        if member.get("type") != "way" or not geometry:
            continue
        line: Line = tuple((float(g["lon"]), float(g["lat"])) for g in geometry if g and "lon" in g)
        (inner if member.get("role") == "inner" else outer).append(line)
    shapes: list[tuple[Line, list[Line]]] = [(ring, []) for ring in _stitched(outer)]
    for hole in _stitched(inner):
        for ring, holes in shapes:
            if point_in_ring(hole[0][0], hole[0][1], list(ring)):
                holes.append(hole)
                break
    return shapes


def _buildings_in(elements: Sequence[dict[str, Any]]) -> list[Building]:
    """Every building in an Overpass answer: plain ways and multipolygons.

    The multipolygons are the ones that matter most and were the ones not
    asked for. OSM draws a building with a courtyard -- the perimeter
    apartment block, the shopping centre, the hospital -- as a relation, not
    a way, and the building tag sits on the relation: its member ways carry
    none, so a query for tagged ways alone returned nothing of them at all.
    Around Kogarah station both of the relations are apartment blocks.

    Each outline once. A member way that is tagged as a building as well --
    it happens -- would otherwise stand as a second slab inside the first.
    """
    found: list[Building] = []
    seen: set[tuple[tuple[float, float], ...]] = set()

    def key(ring: Line) -> tuple[tuple[float, float], ...]:
        return tuple(sorted({(round(x, 6), round(y, 6)) for x, y in ring}))

    for element in elements:
        tags = element.get("tags") or {}
        if not tags.get("building"):
            continue
        if element.get("type") == "relation":
            for ring, holes in _multipolygon(element):
                if key(ring) not in seen:
                    seen.add(key(ring))
                    found.append(_building(tags, ring, holes))
            continue
        if element.get("type") != "way" or not element.get("geometry"):
            continue
        ring = tuple((float(g["lon"]), float(g["lat"])) for g in element["geometry"])
        if len(ring) < 3 or key(ring) in seen:
            continue
        seen.add(key(ring))
        found.append(_building(tags, ring))
    return found


def buildings(extent: Extent, *, log: Log | None = None) -> tuple[Building, ...]:
    """Every building footprint in the extent, and nothing else.

    The furniture query asks for fifteen things at once and is sized for a
    site sheet; a context model half a kilometre each way wants the
    footprints alone, thousands of them, in one answer.
    """
    south, west, north, east = extent.lonlat_bbox()
    bbox = f"{south},{west},{north},{east}"
    query = f"""[out:json][timeout:120];
(
  way["building"]({bbox});
  relation["building"]["type"="multipolygon"]({bbox});
);
out geom;"""
    data = overpass(query, timeout=120.0, log=log)
    return tuple(_buildings_in(data.get("elements") or []))


def furniture(extent: Extent, *, log: Log | None = None) -> Furniture:
    south, west, north, east = extent.lonlat_bbox()
    bbox = f"{south},{west},{north},{east}"
    query = f"""[out:json][timeout:60];
(
  node["natural"="tree"]({bbox});
  way["natural"="tree_row"]({bbox});
  node["emergency"="fire_hydrant"]({bbox});
  node["power"="pole"]({bbox});
  node["highway"="street_lamp"]({bbox});
  way["highway"]["oneway"="yes"]({bbox});
  way["building"]({bbox});
  relation["building"]["type"="multipolygon"]({bbox});
  way["power"="line"]({bbox});
  way["power"="minor_line"]({bbox});
  way["man_made"="pipeline"]({bbox});
  way["service"="driveway"]({bbox});
  way["highway"]["parking:lane:left"]({bbox});
  way["highway"]["parking:lane:right"]({bbox});
  way["highway"]["parking:both"]({bbox});
  way["highway"]["parking:left"]({bbox});
  way["highway"]["parking:right"]({bbox});
);
out geom;"""
    data = overpass(query, log=log)

    trees: list[Tree] = []
    hydrants: list[Point] = []
    poles: list[Point] = []
    lamps: list[Point] = []
    oneway: list[tuple[str | None, Line]] = []
    buildings: list[Building] = []
    utilities: list[Utility] = []
    driveways: list[Line] = []
    parking: list[tuple[str, Line]] = []

    for element in data.get("elements") or []:
        tags = element.get("tags") or {}
        if element.get("type") == "node":
            point = (float(element["lon"]), float(element["lat"]))
            if tags.get("natural") == "tree":
                trees.append(tree_from_osm(point[0], point[1], tags))
            elif tags.get("emergency") == "fire_hydrant":
                hydrants.append(point)
            elif tags.get("power") == "pole":
                poles.append(point)
            elif tags.get("highway") == "street_lamp":
                lamps.append(point)
            continue
        if element.get("type") != "way" or not element.get("geometry"):
            continue
        coords: Line = tuple((float(g["lon"]), float(g["lat"])) for g in element["geometry"])
        if tags.get("natural") == "tree_row":
            trees.extend(trees_along_row(coords))
            continue
        if tags.get("service") == "driveway":
            driveways.append(coords)
            continue
        left = tags.get("parking:lane:left") or tags.get("parking:left")
        right = tags.get("parking:lane:right") or tags.get("parking:right")
        both = tags.get("parking:both")
        if tags.get("highway") and (_parked(left) or _parked(right) or _parked(both)):
            parking.append(
                ("both" if _parked(both) else "left" if _parked(left) else "right", coords)
            )
            continue
        if tags.get("building"):
            continue  # all of them together below, the multipolygons with them
        elif tags.get("power") in ("line", "minor_line"):
            utilities.append(Utility("power", coords))
        elif tags.get("man_made") == "pipeline":
            substance = (tags.get("substance") or "").lower()
            kind = "gas" if substance == "gas" else "sewer" if substance == "sewage" else "water"
            utilities.append(Utility(kind, coords))
        elif tags.get("highway") and tags.get("oneway") == "yes":
            oneway.append((tags.get("name"), coords))

    buildings = _buildings_in(data.get("elements") or [])
    return Furniture(
        trees=tuple(trees),
        hydrants=tuple(hydrants),
        power_poles=tuple(poles),
        street_lamps=tuple(lamps),
        oneway_roads=tuple(oneway),
        buildings=tuple(buildings),
        utilities=tuple(utilities),
        driveways=tuple(driveways),
        parking_lanes=tuple(parking),
    )
