"""The massing slabs, read out of the open project for the area calculation.

A massing is modelled in slabs, one per floor, and the area calculation
(roadmap R3, ``rules.area_yield``) is their areas added up. Which slabs are
the massing is the person's to say, in the two ways the office asked for:

* **by layer** -- the slabs on the layers named as residential, and on the
  layers named as non-residential. The layer is also what says a slab's use.
* **by the renovation filter** -- only the slabs the floor plan's renovation
  filter shows, so that a massing modelled as *New* over an existing
  building counts the new and not the old. Archicad decides what the filter
  shows (Tapir's ``IsVisibleByRenovation``), whichever filter is set.

With no layer named at all, every slab on a layer that is showing counts,
as residential: the quick answer to "what is the GBA of what I am looking
at", which is the third way it was asked for.

What comes back from Archicad
-----------------------------
``GetElementsByType`` finds the slabs, with the filters; ``GetDetailsOfElements``
gives each one's outline, holes and arcs in project metres, its storey and
its layer (``docs/archicad.md``). The outline is the slab's own polygon --
its reference line, which on a massing slab is its edge -- and its area is
worked here, arcs and holes and all (``core.plan_area``), not read back as
one of Archicad's properties: those arrive as display strings in the
project's own units and language.

Loriini's own slabs are never counted: the context model's neighbours and
the future context carry IDs that start ``SA``, and a GBA that included the
street would be a GBA of the suburb.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.read import layer_names
from sun_study.core.plan_area import Arc, Ring, floor_area
from sun_study.rules.area_yield import NON_RESIDENTIAL, RESIDENTIAL, Floor, Use

__all__ = [
    "OWN_ID_PREFIX",
    "Assignment",
    "MassingSlab",
    "SlabReading",
    "floors_from",
    "read_slabs",
    "ring_from",
]

#: What every element Loriini's site tools put in the model is marked with:
#: ``SA NEIGHBOUR``, ``SA TERRAIN``, ``SA BLOCK``, ``SA FUTURE``.
OWN_ID_PREFIX = "SA "

#: How many slabs' details are asked for in one request: the same batch the
#: Zones are read in, for the same reason -- one request for a thousand
#: outlines is one wait against one timeout.
BATCH = 300


@dataclass(frozen=True)
class MassingSlab:
    """One slab: which it is, where it is, and its floor."""

    guid: str
    element_id: str
    layer: str
    storey: str
    level_m: float
    outline: Ring
    holes: tuple[Ring, ...] = ()

    @property
    def area_m2(self) -> float:
        return floor_area(self.outline, self.holes)


@dataclass(frozen=True)
class SlabReading:
    """What was read, and what was passed over and why."""

    slabs: tuple[MassingSlab, ...]
    filters: tuple[str, ...] = ()
    own: int = 0
    """Loriini's own slabs, left out."""
    unreadable: tuple[str, ...] = field(default_factory=tuple)
    """Slabs Archicad would not describe, or that had no outline, by guid."""


def ring_from(points: Any, arcs: Any = None) -> Ring | None:
    """A ring as Tapir reports one: its corners, closed by repeating the
    first, and its arcs by corner index. ``None`` for anything that is not a
    ring of at least three corners.

    The repeated corner is dropped, and an arc that ends on it is pointed at
    the first corner, which is the same point.
    """
    if not isinstance(points, list):
        return None
    corners: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, dict):
            return None
        x, y = point.get("x"), point.get("y")
        if not isinstance(x, int | float) or not isinstance(y, int | float):
            return None
        corners.append((float(x), float(y)))
    if len(corners) > 1 and corners[0] == corners[-1]:
        corners.pop()
    if len(corners) < 3 and not arcs:
        return None
    if len(corners) < 2:
        return None
    count = len(corners)
    curves: list[Arc] = []
    for arc in arcs if isinstance(arcs, list) else []:
        if not isinstance(arc, dict):
            continue
        start, end, angle = arc.get("begIndex"), arc.get("endIndex"), arc.get("arcAngle")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if not isinstance(angle, int | float):
            continue
        curves.append(Arc(start % count, end % count, float(angle)))
    return Ring(tuple(corners), tuple(curves))


def _storeys(connection: ArchicadConnection) -> dict[int, tuple[str, float]]:
    """Storey index -> its name and level. Empty if the storeys will not read:
    the slabs are still counted, under their index."""
    try:
        answer = connection.run_tapir("GetStories", {})
    except ArchicadError:
        return {}
    rows = answer.get("stories") if isinstance(answer, dict) else None
    found: dict[int, tuple[str, float]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("index"), int):
            continue
        level = row.get("level")
        name = " ".join(str(row.get("name", "")).split()) or f"Storey {row['index']}"
        found[int(row["index"])] = (name, float(level) if isinstance(level, int | float) else 0.0)
    return found


def read_slabs(
    connection: ArchicadConnection,
    *,
    renovation: bool = False,
    shown_layers_only: bool = False,
) -> SlabReading:
    """Every slab in the floor plan, with its outline, storey and layer.

    ``renovation`` keeps only what the floor plan's renovation filter shows;
    ``shown_layers_only`` only what is on a layer that is showing. Both are
    Archicad's own filters, applied before anything comes down the wire.
    """
    filters: list[str] = []
    if renovation:
        filters.append("IsVisibleByRenovation")
    if shown_layers_only:
        filters.append("IsVisibleByLayer")
    asked: dict[str, Any] = {"elementType": "Slab"}
    if filters:
        asked["filters"] = filters
    found = connection.run_tapir("GetElementsByType", asked)
    elements = found.get("elements") if isinstance(found, dict) else None
    if not isinstance(elements, list):
        raise ArchicadError(f"GetElementsByType returned no element list: {found!r}")
    if not elements:
        return SlabReading((), tuple(filters))

    rows: list[Any] = []
    for start in range(0, len(elements), BATCH):
        part = elements[start : start + BATCH]
        details = connection.run_tapir("GetDetailsOfElements", {"elements": part})
        listed = details.get("detailsOfElements") if isinstance(details, dict) else None
        if not isinstance(listed, list) or len(listed) != len(part):
            raise ArchicadError(
                f"GetDetailsOfElements returned "
                f"{len(listed) if isinstance(listed, list) else 'no'} rows for "
                f"{len(part)} slabs; the lists must be parallel."
            )
        rows.extend(listed)

    layers = layer_names(connection)
    storeys = _storeys(connection)
    slabs: list[MassingSlab] = []
    own = 0
    unreadable: list[str] = []
    for element, row in zip(elements, rows, strict=True):
        guid = str(((element or {}).get("elementId") or {}).get("guid", ""))
        if not isinstance(row, dict) or "error" in row:
            unreadable.append(guid)
            continue
        element_id = str(row.get("id", ""))
        if element_id.upper().startswith(OWN_ID_PREFIX):
            own += 1
            continue
        detail = row.get("details") or {}
        outline = ring_from(detail.get("polygonOutline"), detail.get("polygonArcs"))
        if outline is None:
            unreadable.append(guid)
            continue
        holes = tuple(
            ring
            for hole in (detail.get("holes") or [])
            if isinstance(hole, dict)
            for ring in (ring_from(hole.get("polygonOutline"), hole.get("polygonArcs")),)
            if ring is not None
        )
        floor = row.get("floorIndex")
        index = int(floor) if isinstance(floor, int | float) else None
        storey, level = (
            storeys.get(index, (f"Storey {index}", 0.0)) if index is not None else ("", 0.0)
        )
        layer_index = row.get("layerIndex")
        layer = (
            layers.get(int(layer_index), f"layer {layer_index}")
            if isinstance(layer_index, int | float)
            else ""
        )
        slabs.append(MassingSlab(guid, element_id, layer, storey, level, outline, holes))
    return SlabReading(tuple(slabs), tuple(filters), own, tuple(unreadable))


def _tidy(name: str) -> str:
    """A layer name the way a person means it: spaces collapsed, case folded.
    Archicad layer names carry trailing spaces more often than anyone expects."""
    return " ".join(name.split()).casefold()


@dataclass(frozen=True)
class Assignment:
    """The slabs' floors, and what the layers came to."""

    floors: tuple[Floor, ...]
    by_layer: Mapping[str, tuple[Use, int, float]]
    """Each counted layer: its use, how many slabs, their area."""
    passed_over: Mapping[str, int]
    """Layers with slabs on them that were named as neither use."""
    missing: tuple[str, ...]
    """Layers named that no slab stands on."""


def floors_from(
    slabs: Iterable[MassingSlab],
    residential: Sequence[str] = (),
    non_residential: Sequence[str] = (),
) -> Assignment:
    """Each slab's floor, its use told by its layer.

    With no layer named for either use, every slab counts as residential:
    the quick GBA of what is showing. A layer named for both is refused,
    since one slab cannot be two uses.
    """
    homes = {_tidy(name) for name in residential if name.strip()}
    other = {_tidy(name) for name in non_residential if name.strip()}
    both = homes & other
    if both:
        named = sorted(name for name in [*residential, *non_residential] if _tidy(name) in both)
        raise ValueError(
            f"{named[0]!r} is named as both residential and non-residential; "
            "a slab on it can only be one."
        )
    everything = not homes and not other
    floors: list[Floor] = []
    by_layer: dict[str, tuple[Use, int, float]] = {}
    passed_over: dict[str, int] = {}
    seen: set[str] = set()
    for slab in slabs:
        key = _tidy(slab.layer)
        seen.add(key)
        use: Use
        if everything or key in homes:
            use = RESIDENTIAL
        elif key in other:
            use = NON_RESIDENTIAL
        else:
            passed_over[slab.layer] = passed_over.get(slab.layer, 0) + 1
            continue
        area = slab.area_m2
        floors.append(Floor(slab.storey, use, area, slab.level_m))
        _, count, total = by_layer.get(slab.layer, (use, 0, 0.0))
        by_layer[slab.layer] = (use, count + 1, total + area)
    missing = tuple(
        name
        for name in [*residential, *non_residential]
        if name.strip() and _tidy(name) not in seen
    )
    return Assignment(tuple(floors), by_layer, passed_over, missing)
