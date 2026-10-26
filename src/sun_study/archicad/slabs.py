"""The massing slabs, read out of the open project for the yield analysis.

A massing is modelled in slabs, one per floor, and the yield analysis
(roadmap R3, ``rules.area_yield``) is their areas added up by level and by
use. Which slabs are the massing, and what each is, is the person's to say:

* **by layer** -- the slabs on the layers named as residential and as
  commercial. The layer is also what says a slab's use.
* **by layer and level** -- the slabs on the layers named as *massing*,
  whose use is told by the level they stand on: the levels named commercial
  are commercial, everything else residential. An option modelled on one
  layer -- a podium with a tower on it -- is read this way.

Commercial is every floor that is not a home, the shops with the offices: a
layer or a level of shops is named as commercial (D159).
* **by the renovation filter** -- only the slabs the floor plan's renovation
  filter shows, so that a massing modelled as *New* over an existing
  building counts the new and not the old. Archicad decides what the filter
  shows (Tapir's ``IsVisibleByRenovation``), whichever filter is set.
* **by renovation status** -- only the slabs whose own *Renovation Status*
  is one asked for: the new, or the new and the existing. The same question
  as a filter's, asked of each slab, so nothing has to be set on the floor
  plan first (D140).

With no layer named at all, every slab on a layer that is showing counts as
massing: the quick answer to "what is the yield of what I am looking at".

What comes back from Archicad
-----------------------------
``GetElementsByType`` finds the slabs, with the filters; ``GetDetailsOfElements``
gives each one's outline, holes and arcs in project metres, its storey and
its layer, and where it is in height (``docs/archicad.md``). The outline is
the slab's own polygon -- its reference line, which on a massing slab is its
edge -- and its area is worked here, arcs and holes and all
(``core.plan_area``), not read back as one of Archicad's properties: those
arrive as display strings in the project's own units and language.

Where a slab is in height is its own, not its storey's. A massing's slabs
are commonly homed on the ground storey and offset up, and a storey-thick
slab stands for the whole floor; so each slab's underside is worked from
its reference plane (``zCoordinate``), the offset of its top from that plane
and its thickness, and the levels are told from the undersides
(``rules.area_yield.levels_from``).

Loriini's own slabs are never counted: the context model's neighbours and
the future context carry IDs that start ``SA``, and a GBA that included the
street would be a GBA of the suburb.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.read import layer_names
from sun_study.core.plan_area import Arc, Ring, floor_area
from sun_study.rules.area_yield import (
    COMMERCIAL,
    RESIDENTIAL,
    Floor,
    Use,
    level_index,
    level_name,
)

__all__ = [
    "BY_LEVEL",
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

#: Archicad's three renovation statuses, by what it calls them in the
#: languages it is most often run in here. A status read that is none of
#: these is reported, never guessed.
RENOVATION_STATUSES: dict[str, str] = {
    "existing": "existing",
    "new": "new",
    "to be demolished": "demolished",
    "demolished": "demolished",
    "bestand": "existing",
    "neu": "new",
    "neubau": "new",
    "abbruch": "demolished",
    "existant": "existing",
    "nouveau": "new",
    "à démolir": "demolished",
    "a démolir": "demolished",
}
#: The property a slab's renovation status is read from.
RENOVATION_PROPERTY = "Renovation Status"


#: What a massing layer's use is said to be in the run's listing.
BY_LEVEL = "by level"

#: A storey called one of these is the ground, from which the levels count.
_GROUND = re.compile(r"^(?:ground(?: floor)?|gf|g|level 0+|l0+|0+)$", re.IGNORECASE)


@dataclass(frozen=True)
class MassingSlab:
    """One slab: which it is, where it is, and its floor."""

    guid: str
    element_id: str
    layer: str
    storey: str
    level_m: float
    """The home storey's level."""
    outline: Ring
    holes: tuple[Ring, ...] = ()
    bottom_m: float = 0.0
    """The elevation of the slab's underside."""
    thickness_m: float = 0.0

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
    ground_m: float | None = None
    """The level of the project's ground storey, when one is named for it."""
    statuses: tuple[str, ...] = ()
    """The renovation statuses kept, when only some were asked for."""
    by_status: Mapping[str, int] = field(default_factory=dict)
    """How many slabs were left out under each status not asked for."""
    unknown_status: Mapping[str, int] = field(default_factory=dict)
    """Statuses read that are none of the three, by what Archicad called them."""


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


def _ground_of(storeys: Mapping[int, tuple[str, float]]) -> float | None:
    """The level of the storey named as the ground, if one is."""
    for _index, (name, level) in sorted(storeys.items()):
        if _GROUND.match(name.strip()):
            return level
    return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _height_of(detail: Mapping[str, Any], storey_level: float) -> tuple[float, float]:
    """A slab's underside and thickness, from its details.

    Tapir gives the reference plane's absolute height (``zCoordinate``), the
    offset of the slab's top from that plane (``offsetFromTop``) and the
    thickness; the top is the plane plus the offset and the underside is
    the thickness below it. Without them -- an older add-on -- the slab's
    ``level`` above its storey stands in, and it has no thickness.
    """
    thickness = _number(detail.get("thickness")) or 0.0
    plane = _number(detail.get("zCoordinate"))
    if plane is None:
        offset = _number(detail.get("level")) or 0.0
        return storey_level + offset, thickness
    top = plane + (_number(detail.get("offsetFromTop")) or 0.0)
    return top - thickness, thickness


def read_slabs(
    connection: ArchicadConnection,
    *,
    renovation: bool = False,
    shown_layers_only: bool = False,
    statuses: Iterable[str] | None = None,
) -> SlabReading:
    """Every slab in the floor plan, with its outline, storey, layer and height.

    ``renovation`` keeps only what the floor plan's renovation filter shows;
    ``shown_layers_only`` only what is on a layer that is showing. Both are
    Archicad's own filters, applied before anything comes down the wire.
    ``statuses`` keeps only the slabs whose own renovation status is one of
    them -- ``existing``, ``new``, ``demolished`` -- read off each slab.
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

    kept_statuses: tuple[str, ...] = ()
    by_status: dict[str, int] = {}
    unknown: dict[str, int] = {}
    if statuses is not None:
        kept_statuses = tuple(sorted(set(statuses)))
        status_of = _renovation_statuses(connection, elements)
        chosen: list[Any] = []
        for element in elements:
            guid = str(((element or {}).get("elementId") or {}).get("guid", ""))
            said = status_of.get(guid, "")
            status = RENOVATION_STATUSES.get(said.strip().casefold())
            if status is None:
                unknown[said or "(none)"] = unknown.get(said or "(none)", 0) + 1
            elif status in kept_statuses:
                chosen.append(element)
            else:
                by_status[status] = by_status.get(status, 0) + 1
        elements = chosen
        if not elements:
            return SlabReading(
                (),
                tuple(filters),
                statuses=kept_statuses,
                by_status=by_status,
                unknown_status=unknown,
            )

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
        bottom, thickness = _height_of(detail, level)
        slabs.append(
            MassingSlab(guid, element_id, layer, storey, level, outline, holes, bottom, thickness)
        )
    return SlabReading(
        tuple(slabs),
        tuple(filters),
        own,
        tuple(unreadable),
        _ground_of(storeys),
        kept_statuses,
        by_status,
        unknown,
    )


def _renovation_statuses(connection: ArchicadConnection, elements: Sequence[Any]) -> dict[str, str]:
    """Each element's renovation status as Archicad words it, by guid.

    ``GetAllProperties`` is the only way to find the built-in property by
    name; the values then come back as the enumeration's own words, in the
    project's language, which is why ``RENOVATION_STATUSES`` knows several.
    """
    listed = connection.run_tapir("GetAllProperties")
    properties = listed.get("properties") if isinstance(listed, dict) else None
    found = next(
        (
            entry.get("propertyId")
            for entry in properties or []
            if isinstance(entry, dict)
            and str(entry.get("propertyName", "")).strip().casefold()
            == RENOVATION_PROPERTY.casefold()
        ),
        None,
    )
    if not isinstance(found, dict):
        raise ArchicadError(
            "The project has no Renovation Status property to read, so the slabs cannot be "
            "chosen by their status."
        )
    out: dict[str, str] = {}
    for start in range(0, len(elements), BATCH):
        part = list(elements[start : start + BATCH])
        response = connection.run_tapir(
            "GetPropertyValuesOfElements",
            {"elements": part, "properties": [{"propertyId": found}]},
        )
        rows = response.get("propertyValuesForElements") if isinstance(response, dict) else None
        for element, row in zip(part, rows or [], strict=False):
            guid = str(((element or {}).get("elementId") or {}).get("guid", ""))
            values = (row or {}).get("propertyValues") if isinstance(row, dict) else None
            first = values[0] if isinstance(values, list) and values else {}
            value = (first or {}).get("propertyValue", first) if isinstance(first, dict) else {}
            out[guid] = str((value or {}).get("value", "")) if isinstance(value, dict) else ""
    return out


def _tidy(name: str) -> str:
    """A layer name the way a person means it: spaces collapsed, case folded.
    Archicad layer names carry trailing spaces more often than anyone expects."""
    return " ".join(name.split()).casefold()


@dataclass(frozen=True)
class Assignment:
    """The slabs' floors, and what the layers came to."""

    floors: tuple[Floor, ...]
    by_layer: Mapping[str, tuple[str, int, float]]
    """Each counted layer: its use (or ``BY_LEVEL``), how many slabs, their area."""
    passed_over: Mapping[str, int]
    """Layers with slabs on them that were named for nothing."""
    missing: tuple[str, ...]
    """Layers named that no slab stands on."""
    levels_used: Mapping[str, str] = field(default_factory=dict)
    """For the massing layers: each level's name and the use its slabs took."""


def floors_from(
    slabs: Iterable[MassingSlab],
    residential: Sequence[str] = (),
    commercial: Sequence[str] = (),
    massing: Sequence[str] = (),
    *,
    commercial_levels: Sequence[int] = (),
    ground_m: float | None = None,
    others_m: Sequence[float] = (),
) -> Assignment:
    """Each slab's floor, its use told by its layer, or by its level on a
    massing layer.

    With no layer named at all, every slab counts as massing, its use by
    level: the quick yield of what is showing. A layer named for two things
    is refused, since one slab cannot be two uses. ``others_m`` are the
    undersides of slabs in the same grid of levels that this call does not
    count -- the other options' -- so every option's levels line up.
    """
    named: dict[str, set[str]] = {
        RESIDENTIAL: {_tidy(name) for name in residential if name.strip()},
        COMMERCIAL: {_tidy(name) for name in commercial if name.strip()},
        BY_LEVEL: {_tidy(name) for name in massing if name.strip()},
    }
    words = {RESIDENTIAL: "residential", COMMERCIAL: "commercial", BY_LEVEL: "massing"}
    kinds = list(named)
    for i, first in enumerate(kinds):
        for second in kinds[i + 1 :]:
            both = named[first] & named[second]
            if both:
                layer = sorted(both)[0]
                raise ValueError(
                    f"{layer!r} is named as both {words[first]} and {words[second]}; "
                    "a slab on it can only be one."
                )
    everything = not any(named.values())
    listed = list(slabs)
    kept: list[tuple[MassingSlab, str]] = []
    passed_over: dict[str, int] = {}
    seen: set[str] = set()
    for slab in listed:
        key = _tidy(slab.layer)
        seen.add(key)
        if everything or key in named[BY_LEVEL]:
            kept.append((slab, BY_LEVEL))
        elif key in named[RESIDENTIAL]:
            kept.append((slab, RESIDENTIAL))
        elif key in named[COMMERCIAL]:
            kept.append((slab, COMMERCIAL))
        else:
            passed_over[slab.layer] = passed_over.get(slab.layer, 0) + 1

    # The levels are told across every counted slab, so a level is the same
    # level whichever layer its slabs are on.
    indices = level_index([slab.bottom_m for slab, _ in kept], ground_m, others_m)
    floors: list[Floor] = []
    by_layer: dict[str, tuple[str, int, float]] = {}
    levels_used: dict[str, str] = {}
    for (slab, kind), index in zip(kept, indices, strict=True):
        use: Use
        if kind == BY_LEVEL:
            use = COMMERCIAL if index in commercial_levels else RESIDENTIAL
            levels_used[level_name(index)] = use
        else:
            use = kind  # type: ignore[assignment]
        area = slab.area_m2
        floors.append(Floor(use, area, slab.bottom_m, slab.thickness_m, slab.storey))
        _, count, total = by_layer.get(slab.layer, (kind, 0, 0.0))
        by_layer[slab.layer] = (kind, count + 1, total + area)
    missing = tuple(
        name
        for name in [*residential, *commercial, *massing]
        if name.strip() and _tidy(name) not in seen
    )
    ordered = dict(sorted(levels_used.items(), key=lambda item: _level_order(item[0])))
    return Assignment(tuple(floors), by_layer, passed_over, missing, ordered)


def _level_order(name: str) -> tuple[int, str]:
    """Levels in height order: basements, the ground, the floors above."""
    if name.startswith("B "):
        return (-int(name[2:]), name)
    if name.startswith("Level "):
        return (int(name[6:]), name)
    return (0, name)
