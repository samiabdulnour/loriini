"""Trees with a size.

OpenStreetMap knows where many street trees stand and almost never how big
they are: across inner Sydney, 37 of 24,638 mapped trees carry a crown
diameter. A council that keeps a tree inventory knows both, and a few publish
it under an open licence. Those are listed here and take precedence, OSM fills
in around them, and every tree comes out with a canopy figure marked as
measured, estimated from its height or trunk, or nominal -- so the sheet can
draw each one at ground scale and say which is which.

Adding a council is one entry in ``COUNCIL_TREES``: a public ArcGIS layer, the
box it covers, and which of its fields carry the height, the canopy, the trunk
and the species -- and an entry in ``sources`` for the credit. Only an
inventory with an explicit open licence belongs there. A public service with
no licence statement (Parramatta's 34,000 existing trees, for one) is not the
same as permission to redraw it on a DA sheet.

Ported from the office's ``au-site-analysis`` generator (``fetch/trees.ts``),
rule for rule and number for number, so the two draw the same tree the same
size.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from sun_study.site import sources
from sun_study.site.arcgis import query_by_extent
from sun_study.site.geo import Extent, Point, lonlat_to_mercator, mercator_to_lonlat, scale_factor
from sun_study.site.http import Log

__all__ = [
    "COUNCIL_TREES",
    "ESTIMATED",
    "MEASURED",
    "NOMINAL",
    "NOMINAL_CANOPY_M",
    "Tree",
    "TreeSource",
    "council_trees",
    "merge_trees",
    "parse_metres",
    "resolve_canopy",
    "sources_for",
    "tree_from_osm",
    "trees_along_row",
]

#: Where a canopy figure came from: recorded by the source, worked out from a
#: recorded height or trunk, or the nominal size of a tree nobody measured.
MEASURED = "measured"
ESTIMATED = "estimated"
NOMINAL = "nominal"

#: The canopy of a street tree nobody has measured, metres across.
NOMINAL_CANOPY_M = 6.0


@dataclass(frozen=True)
class Tree:
    """One tree: where it stands, and how big its canopy is drawn."""

    lon: float
    lat: float
    canopy_m: float = NOMINAL_CANOPY_M
    """The canopy's diameter to draw, metres. Always set."""
    canopy_from: str = NOMINAL
    """``measured``, ``estimated`` or ``nominal`` -- see ``resolve_canopy``."""
    height_m: float | None = None
    dbh_cm: float | None = None
    """The trunk's diameter at breast height."""
    species: str | None = None
    """The botanical name, where recorded."""
    common: str | None = None
    source: str = sources.OSM
    """Whose record this is: a slug from ``sources``, so the sheet can credit
    the council for its trees and OpenStreetMap for the rest."""

    @property
    def point(self) -> Point:
        return (self.lon, self.lat)

    def as_dict(self) -> dict[str, Any]:
        return {
            "lon": self.lon,
            "lat": self.lat,
            "canopy_m": self.canopy_m,
            "canopy_from": self.canopy_from,
            "height_m": self.height_m,
            "dbh_cm": self.dbh_cm,
            "species": self.species,
            "common": self.common,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Tree:
        """A saved tree. A bundle from before trees had a size saved each one
        as a bare ``[lon, lat]``, and that is an OSM tree of nominal size --
        which is what the run that saved it had drawn."""
        if isinstance(data, list | tuple):
            return cls(float(data[0]), float(data[1]))

        def number(key: str) -> float | None:
            value = data.get(key)
            return float(value) if value is not None else None

        return cls(
            lon=float(data["lon"]),
            lat=float(data["lat"]),
            canopy_m=float(data.get("canopy_m") or NOMINAL_CANOPY_M),
            canopy_from=str(data.get("canopy_from") or NOMINAL),
            height_m=number("height_m"),
            dbh_cm=number("dbh_cm"),
            species=data.get("species"),
            common=data.get("common"),
            source=str(data.get("source") or sources.OSM),
        )


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def resolve_canopy(
    canopy_m: float | None = None, height_m: float | None = None, dbh_cm: float | None = None
) -> tuple[float, str]:
    """The canopy to draw, and where the figure came from.

    A recorded spread wins. A height gives a crown about 0.6 of it across --
    open-grown urban trees run 0.5 to 0.8 -- and a trunk about 0.2 m of crown
    per centimetre of diameter, a 40 cm trunk under an 8 m crown. Anything
    else is the nominal street tree. Clamped, because a register that says a
    street tree is 90 m across has a typing error in it, not a tree.
    """
    if canopy_m and canopy_m > 0:
        return _clamp(canopy_m, 1.0, 40.0), MEASURED
    if height_m and height_m > 0:
        return _clamp(height_m * 0.6, 2.0, 25.0), ESTIMATED
    if dbh_cm and dbh_cm > 0:
        return _clamp(dbh_cm * 0.2, 2.0, 25.0), ESTIMATED
    return NOMINAL_CANOPY_M, NOMINAL


_METRES = re.compile(r"(\d+(?:[.,]\d+)?)\s*(m|cm|ft|')?")


def parse_metres(value: Any) -> float | None:
    """``8``, ``8 m``, ``8.5m``, ``800 cm``, ``30 ft`` -> metres; anything
    that does not read as a length -> ``None``. OSM's own tags, as mappers
    write them."""
    if value is None:
        return None
    match = _METRES.fullmatch(str(value).strip().lower())
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = match.group(2)
    if unit == "cm":
        number /= 100.0
    elif unit in ("ft", "'"):
        number *= 0.3048
    return number if number > 0 else None


def tree_from_osm(lon: float, lat: float, tags: Mapping[str, str]) -> Tree:
    """An OSM ``natural=tree`` node, with whatever size its tags record."""
    height = parse_metres(tags.get("height"))
    if height is None:
        height = parse_metres(tags.get("est_height"))
    # ``circumference`` is the trunk's girth in metres; the diameter at breast
    # height is what the canopy rule reads, in centimetres.
    girth = parse_metres(tags.get("circumference"))
    dbh = girth / math.pi * 100.0 if girth else None
    canopy, how = resolve_canopy(parse_metres(tags.get("diameter_crown")), height, dbh)
    return Tree(
        lon=lon,
        lat=lat,
        canopy_m=canopy,
        canopy_from=how,
        height_m=height,
        dbh_cm=dbh,
        species=tags.get("species") or tags.get("genus") or None,
        common=tags.get("species:en") or tags.get("genus:en") or None,
    )


def trees_along_row(coords: Sequence[Point], spacing_m: float = 8.0) -> list[Tree]:
    """Nominal trees every ``spacing_m`` along an OSM ``natural=tree_row``,
    the first half a spacing in -- a row mapped as one line is still a row of
    trees, each with a canopy of its own."""
    found: list[Tree] = []
    if len(coords) < 2:
        return found
    k = scale_factor(coords[0][1])
    points = [lonlat_to_mercator(lon, lat) for lon, lat in coords]
    step = spacing_m * k
    carry = step / 2.0
    for (ax, ay), (bx, by) in pairwise(points):
        length = math.hypot(bx - ax, by - ay)
        at = carry
        while at <= length:
            share = at / length
            lon, lat = mercator_to_lonlat(ax + (bx - ax) * share, ay + (by - ay) * share)
            found.append(Tree(lon, lat))
            at += step
        carry = at - length
    return found


# -- the councils ---------------------------------------------------------------


@dataclass(frozen=True)
class TreeSource:
    """A council's tree inventory: a public point layer and what its fields mean."""

    slug: str
    """The ``sources`` entry that is credited for it."""
    name: str
    layer: str
    """The ArcGIS feature layer, ``.../FeatureServer/0``. Points only."""
    bbox: tuple[float, float, float, float]
    """``(west, south, east, north)`` in degrees: a site outside it never asks."""
    fields: Mapping[str, str] = field(default_factory=dict)
    """Which field is the ``height`` (m), ``canopy`` (m across), ``dbh`` (cm),
    ``species`` and ``common`` name."""
    keep: Callable[[Mapping[str, Any]], bool] | None = None
    """Leave a record out: a stump, a vacant planting site."""


COUNCIL_TREES: tuple[TreeSource, ...] = (
    TreeSource(
        slug=sources.CITY_OF_SYDNEY,
        name="City of Sydney tree inventory",
        layer=(
            "https://services1.arcgis.com/cNVyNtjGVZybOQWZ/arcgis/rest/services/"
            "Trees/FeatureServer/0"
        ),
        # The local government area: Rozelle Bay to Centennial Park, Millers
        # Point to Rosebery.
        bbox=(151.17, -33.93, 151.24, -33.85),
        fields={
            "height": "TreeHeight",
            "canopy": "TreeCanopyNS",
            "dbh": "DBH_in_cm",
            "species": "SpeciesName",
            "common": "CommonName",
        },
        keep=lambda attributes: (attributes.get("Tree_Status") or "Tree") == "Tree",
    ),
)


def sources_for(extent: Extent) -> tuple[TreeSource, ...]:
    """The inventories whose box the extent touches, in the registry's order."""
    south, west, north, east = extent.lonlat_bbox()
    return tuple(
        source
        for source in COUNCIL_TREES
        if west <= source.bbox[2]
        and east >= source.bbox[0]
        and south <= source.bbox[3]
        and north >= source.bbox[1]
    )


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _text(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


def _field(source: TreeSource, attributes: Mapping[str, Any], key: str) -> Any:
    """What the record says for ``height``, ``canopy`` and the rest, under
    whatever this council calls it."""
    name = source.fields.get(key)
    return attributes.get(name) if name else None


def council_trees(extent: Extent, *, log: Log | None = None) -> list[Tree]:
    """Every inventory tree in the extent, from each council whose box it touches.

    Empty, and nothing asked, for a site outside every council listed -- which
    is most of NSW. A council whose service fails raises, and the pipeline's
    soft fetch turns that into a warning and the sheet's trees into OSM's.
    """
    found: list[Tree] = []
    for source in sources_for(extent):
        wanted = [source.fields[key] for key in ("height", "canopy", "dbh", "species", "common")]
        names = ",".join(name for name in wanted if name) or "*"
        collection = query_by_extent(source.layer, extent, names)
        kept = 0
        for feature in collection["features"]:
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "Point":
                continue
            attributes = feature.get("properties") or {}
            if source.keep is not None and not source.keep(attributes):
                continue
            height = _positive(_field(source, attributes, "height"))
            dbh = _positive(_field(source, attributes, "dbh"))
            canopy, how = resolve_canopy(
                _positive(_field(source, attributes, "canopy")), height, dbh
            )
            found.append(
                Tree(
                    lon=float(geometry["coordinates"][0]),
                    lat=float(geometry["coordinates"][1]),
                    canopy_m=canopy,
                    canopy_from=how,
                    height_m=height,
                    dbh_cm=dbh,
                    species=_text(_field(source, attributes, "species")),
                    common=_text(_field(source, attributes, "common")),
                    source=source.slug,
                )
            )
            kept += 1
        if log:
            log(f"  {source.name}: {kept} trees")
    return found


def merge_trees(
    council: Iterable[Tree], mapped: Iterable[Tree], tolerance_m: float = 4.0
) -> list[Tree]:
    """The council's trees first; an OSM tree within ``tolerance_m`` of one is
    the same tree mapped twice, and is dropped.

    Indexed by a grid of the tolerance, so a sheet with a thousand of each is
    a thousand lookups rather than a million distances.
    """
    ours = list(council)
    theirs = list(mapped)
    if not ours:
        return theirs
    k = scale_factor(ours[0].lat)
    reach = tolerance_m * k
    cells: dict[tuple[int, int], list[Point]] = {}
    for tree in ours:
        x, y = lonlat_to_mercator(tree.lon, tree.lat)
        cells.setdefault((int(x // reach), int(y // reach)), []).append((x, y))

    def known(tree: Tree) -> bool:
        x, y = lonlat_to_mercator(tree.lon, tree.lat)
        i, j = int(x // reach), int(y // reach)
        return any(
            math.hypot(px - x, py - y) < reach
            for di in (-1, 0, 1)
            for dj in (-1, 0, 1)
            for px, py in cells.get((i + di, j + dj), ())
        )

    return [*ours, *(tree for tree in theirs if not known(tree))]
