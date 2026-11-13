"""The QA export: the per-apartment data a QA council builds its schedules from (D184).

An office's QA council writes the Development Summary, the ADG table and the
SEPP statement from one schedule: every apartment with its level, type,
bedrooms, internal area, private open space, storage and the ADG and SEPP
flags, and the totals of GFA, communal open space, deep soil and parking.
Typed by hand into a spreadsheet, those figures drift from the drawings. Here
they come out of the model.

Three property groups hold them, named from a prefix the office types once
(``QA_`` makes ``QA_UNIT``, ``QA_AREA``, ``QA_PARKING``): Loriini
ships no office's names (D156). Their fields and option sets are the brief's.

Most of the values are already in a project, under the office's own names --
a ``Beds`` property, an ``External Area``, a ``Daylight`` flag of ``Y`` and
``N``. Each field can be *copied* from such a property (``Field=Group/Name``),
read as the brief's value: ``Y`` is ``Yes``, ``2 BED`` is ``2B``, ``21 m3``
is 21. What a project does not hold is worked out where it can be: the unit
number and internal area from the zone, the private open space from the
balcony zones beside the apartment, the solar flags from Loriini's own solar
study. What cannot be read is left blank and listed, never guessed.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.read import ArchicadZone, layer_names, zones
from sun_study.archicad.rooms import polygon_area
from sun_study.archicad.write import all_properties, property_groups

YES_NO = ("Yes", "No")
UNIT_TYPES = ("Studio", "1B", "2B", "3B", "4B")
LIVABLE = ("None", "Silver", "Gold")
AREA_TYPES = (
    "Communal open space",
    "Deep soil",
    "GFA",
    "Non-GFA",
    "Retail",
    "Plant",
    "Circulation",
)
SPACE_TYPES = (
    "Resident",
    "Visitor",
    "Accessible",
    "Car share",
    "Retail",
    "Service",
    "Motorcycle",
    "Bicycle",
)


@dataclass(frozen=True)
class QaField:
    """One property of a QA group: its name, Tapir data type and options."""

    name: str
    kind: str
    options: tuple[str, ...] = ()
    description: str = ""


UNIT_FIELDS: tuple[QaField, ...] = (
    QaField("Unit No", "string", description="The unit label on the plans."),
    QaField("Building", "string", description="Per-building counts."),
    QaField("Core", "string", description="ADG 4F: apartments per core and per lift."),
    QaField("Unit Type", "singleEnum", UNIT_TYPES, "The mix; ADG 4D minimum sizes."),
    QaField("Bedrooms", "integer", description="Parking rates and the mix."),
    QaField("Internal area m²", "number", description="Measured from the zone (ADG 4D)."),
    QaField("POS area m²", "number", description="Balcony or terrace area (ADG 4E)."),
    QaField("Solar 2h", "singleEnum", YES_NO, "ADG 4A: 2 h of sun at midwinter."),
    QaField("No sun", "singleEnum", YES_NO, "ADG 4A: no direct sun at midwinter."),
    QaField("Cross vent", "singleEnum", YES_NO, "ADG 4B: naturally cross ventilated."),
    QaField("Adaptable", "singleEnum", YES_NO, "DCP adaptable housing."),
    QaField("Livable", "singleEnum", LIVABLE, "Livable Housing Design."),
    QaField("Affordable", "singleEnum", YES_NO, "Housing SEPP affordable share."),
    QaField("Storage in unit m³", "number", description="ADG 4G."),
    QaField(
        "Storage total m³", "number", description="In the unit and the basement cage (ADG 4G)."
    ),
)
AREA_FIELDS: tuple[QaField, ...] = (
    QaField("Area Type", "singleEnum", AREA_TYPES, "What the zone counts as."),
    QaField("Deep soil min. dimension m", "number", description="ADG 3E's 6 m test."),
)
PARKING_FIELDS: tuple[QaField, ...] = (
    QaField("Space Type", "singleEnum", SPACE_TYPES, "Parking by type against the rates."),
    QaField("Allocated to", "string", description="The unit number, where allocated."),
)
#: The groups by their suffix, in the brief's order.
GROUPS: dict[str, tuple[QaField, ...]] = {
    "UNIT": UNIT_FIELDS,
    "AREA": AREA_FIELDS,
    "PARKING": PARKING_FIELDS,
}

#: ADG 4D-1's minimum internal areas and 4E-1's minimum private open space,
#: by type. A bedroom past the third adds 12 m² of internal area.
MIN_INTERNAL_M2 = {"Studio": 35.0, "1B": 50.0, "2B": 70.0, "3B": 90.0, "4B": 102.0}
MIN_POS_M2 = {"Studio": 4.0, "1B": 8.0, "2B": 10.0, "3B": 12.0, "4B": 12.0}


def group_names(prefix: str) -> dict[str, str]:
    """Each group's name from the office's prefix: ``QA_`` gives ``QA_UNIT``
    and ``Qa_`` gives ``Qa_Unit``, the suffix in the prefix's own case."""
    tidy = prefix.strip()
    if not tidy:
        raise ValueError("The QA property groups need a prefix, such as QA_.")
    capitals = tidy == tidy.upper()
    return {suffix: f"{tidy}{suffix if capitals else suffix.title()}" for suffix in GROUPS}


def _norm(text: str) -> str:
    """A name as it is compared: case, spaces and their kinds aside."""
    return " ".join(text.replace("\u00a0", " ").split()).casefold()


#: Other spellings an office's own setup of the brief uses for a field.
SPELLINGS: dict[str, tuple[str, ...]] = {
    "unit no": ("unit number", "unit no.", "unit nr"),
    "bedrooms": ("beds", "bedroom"),
    "pos area m²": ("pos area", "pos m²", "private open space m²"),
}


def find_field(paths: Mapping[str, str], group: str, field_name: str) -> str | None:
    """The identifier of ``group``'s ``field_name`` among ``paths``, matched
    without regard to case or spacing (``Qa_Unit/Internal area  m²`` is
    ``QA_UNIT/Internal area m²``), and by the spellings an office uses."""
    wanted = {_norm(field_name), *SPELLINGS.get(_norm(field_name), ())}
    for path, ident in paths.items():
        owner, _slash, name = path.partition("/")
        if _norm(owner) == _norm(group) and _norm(name) in wanted:
            return ident
    return None


def fit_option(value: Any, options: Sequence[str]) -> Any:
    """``value`` as one of an existing option set's own options: ``Yes`` is
    ``Y`` where the set says Y and N. ``None`` when none fits."""
    if not options:
        return value
    text = str(value)
    for option in options:
        if _norm(option) == _norm(text):
            return option
    if text in ("Yes", "No"):
        for option in options:
            if _norm(option) in ({"y", "true"} if text == "Yes" else {"n", "false"}):
                return option
    return None


def drop_doubles(
    zones_: Sequence[QaZone], *, share: float = 0.5
) -> tuple[list[QaZone], list[QaZone]]:
    """The zones with any drawn over another on its storey left out: a zone
    covering more than ``share`` of a larger one's area is the same apartment
    drawn twice -- once in a module and once in the host, say. Returns the
    kept and the dropped."""
    from shapely.geometry import Polygon

    kept: list[QaZone] = []
    dropped: list[QaZone] = []
    shapes: dict[str, Any] = {}
    for zone in sorted(zones_, key=lambda one: -one.area_m2):
        shape = Polygon(zone.outline).buffer(0) if len(zone.outline) >= 3 else None
        twin = shape is not None and any(
            other.storey_index == zone.storey_index
            and shapes.get(other.guid) is not None
            and shape.intersection(shapes[other.guid]).area
            > share * max(shape.area, shapes[other.guid].area)
            for other in kept
        )
        if twin:
            dropped.append(zone)
            continue
        kept.append(zone)
        shapes[zone.guid] = shape
    order = {zone.guid: index for index, zone in enumerate(zones_)}
    return sorted(kept, key=lambda one: order[one.guid]), dropped


# -- reading a project's own values as the brief's -----------------------------------


def yes_no(text: str | None) -> str | None:
    """``Y``, ``Yes``, ``True``, ``1`` are Yes; ``N``, ``No``, ``-``, ``0`` are No."""
    word = (text or "").strip().casefold()
    if word in ("y", "yes", "true", "1", "✓", "x"):
        return "Yes"
    if word in ("n", "no", "false", "0", "-", "none", "nil"):
        return "No"
    return None


_TYPE = re.compile(r"\b([1-4])\s*(?:b|br|bed|bedroom|beds|bedrooms)\b", re.IGNORECASE)


def unit_type(text: str | None, bedrooms: int | None = None) -> str | None:
    """``2B``, ``2 BED``, ``2BR`` are 2B; ``Studio``, ``STU``, ``0B`` are Studio.
    With nothing readable, the bedrooms say it."""
    word = (text or "").strip()
    if re.fullmatch(r"(?i)studio|stu|s|0\s*b(?:ed)?|0br", word):
        return "Studio"
    found = _TYPE.search(word)
    if found:
        return f"{found.group(1)}B"
    if bedrooms is not None:
        return "Studio" if bedrooms == 0 else f"{bedrooms}B" if 1 <= bedrooms <= 4 else None
    return None


def livable(text: str | None) -> str | None:
    """Silver, Gold, or None for a plain no; ``Y`` says livable but not which."""
    word = (text or "").strip().casefold()
    if word.startswith("silver"):
        return "Silver"
    if word.startswith("gold") or word.startswith("platinum"):
        return "Gold"
    if word in ("-", "n", "no", "none", "nil", ""):
        return "None" if word else None
    return None


def number(text: str | None) -> float | None:
    """A figure out of a display string: ``21``, ``4.4``, ``12.5 m²``, ``1,234``."""
    found = re.search(r"-?\d[\d,]*(?:\.\d+)?", (text or "").replace(" ", ""))
    if not found:
        return None
    try:
        return float(found.group(0).replace(",", ""))
    except ValueError:
        return None


def integer(text: str | None) -> int | None:
    value = number(text)
    return round(value) if value is not None else None


#: A zone's own name and number, as sources a copy may name beside the
#: project's properties: an office that keeps the type in the zone number
#: says ``Unit Type=Zone/Number``.
ZONE_NAME = "Zone/Name"
ZONE_NUMBER = "Zone/Number"
ZONE_SOURCES = (ZONE_NAME, ZONE_NUMBER)

#: How a copied value is read, by the field it goes to.
READERS: dict[str, Any] = {
    "Solar 2h": yes_no,
    "No sun": yes_no,
    "Cross vent": yes_no,
    "Adaptable": yes_no,
    "Affordable": yes_no,
    "Livable": livable,
    "Bedrooms": integer,
    "POS area m²": number,
    "Internal area m²": number,
    "Storage in unit m³": number,
    "Storage total m³": number,
    "Deep soil min. dimension m": number,
}


def read_as(field_name: str, text: str | None) -> Any:
    """``text`` as the field's value, or None where it cannot be read."""
    if field_name == "Unit Type":
        return unit_type(text)
    reader = READERS.get(field_name)
    if reader is not None:
        return reader(text)
    tidy = (text or "").strip()
    return tidy or None


# -- the zones ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QaZone:
    """A zone the QA export reads: an apartment, a balcony, an area, a space."""

    guid: str
    name: str
    number: str
    storey_index: int | None
    storey: str
    layer: str
    area_m2: float
    outline: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Storeys:
    """The project's storeys, by index: name and level, bottom to top."""

    names: Mapping[int, str]
    levels: Mapping[int, float]

    def between(self, lowest: str | None, highest: str | None) -> set[int] | None:
        """The storey indices from ``lowest`` to ``highest``, by name; ``None``
        when neither is given (every storey)."""
        if not lowest and not highest:
            return None
        order = sorted(self.levels, key=lambda index: self.levels[index])

        def at(name: str | None, default: int) -> int:
            if not name:
                return default
            for index in order:
                if self.names.get(index, "").strip().casefold() == name.strip().casefold():
                    return order.index(index)
            raise ArchicadError(
                f"No storey is named {name!r}. The storeys are: "
                + ", ".join(self.names[i] for i in order if self.names.get(i))
            )

        first = at(lowest, 0)
        last = at(highest, len(order) - 1)
        return set(order[min(first, last) : max(first, last) + 1])


def read_storeys(connection: ArchicadConnection) -> Storeys:
    rows = (connection.run_tapir("GetStories", {}) or {}).get("stories") or []
    names: dict[int, str] = {}
    levels: dict[int, float] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("index"), int):
            names[row["index"]] = str(row.get("name") or "")
            levels[row["index"]] = float(row.get("level") or 0.0)
    return Storeys(names=names, levels=levels)


def _tidy(text: str) -> str:
    return " ".join(text.split()).casefold()


def zones_on(
    connection: ArchicadConnection,
    layers: Iterable[str],
    *,
    storeys: Storeys,
    within: set[int] | None,
    every: Sequence[ArchicadZone] | None = None,
) -> list[QaZone]:
    """The zones on ``layers`` (by name, either spelling of spaces and case),
    on the storeys ``within`` -- every storey when it is None."""
    wanted = {_tidy(layer) for layer in layers if layer.strip()}
    if not wanted:
        return []
    names = layer_names(connection)
    found: list[QaZone] = []
    for zone in every if every is not None else zones(connection):
        layer = names.get(zone.layer_index, "") if zone.layer_index is not None else ""
        if _tidy(layer) not in wanted:
            continue
        if within is not None and zone.storey_index not in within:
            continue
        found.append(
            QaZone(
                guid=zone.guid,
                name=zone.name.strip(),
                number=zone.number.strip(),
                storey_index=zone.storey_index,
                storey=storeys.names.get(zone.storey_index, "")
                if zone.storey_index is not None
                else "",
                layer=layer,
                area_m2=polygon_area(zone.outline) if zone.outline else 0.0,
                outline=tuple(zone.outline),
            )
        )
    return found


def pair_balconies(
    apartments: Sequence[QaZone], balconies: Sequence[QaZone], *, reach_m: float = 1.0
) -> tuple[dict[str, float], int]:
    """Each apartment's private open space: the area of the balcony zones on
    its storey that touch it, each balcony given to the nearest apartment
    within ``reach_m``. Returns the areas by apartment and how many balconies
    reached none."""
    from shapely.geometry import Polygon

    shapes = {
        zone.guid: Polygon(zone.outline).buffer(0)
        for zone in (*apartments, *balconies)
        if len(zone.outline) >= 3
    }
    by_storey: dict[int | None, list[QaZone]] = {}
    for apartment in apartments:
        if apartment.guid in shapes:
            by_storey.setdefault(apartment.storey_index, []).append(apartment)
    open_space: dict[str, float] = {}
    alone = 0
    for balcony in balconies:
        shape = shapes.get(balcony.guid)
        near = (
            [
                (shapes[apartment.guid].distance(shape), apartment.guid)
                for apartment in by_storey.get(balcony.storey_index, [])
            ]
            if shape is not None
            else []
        )
        near = [pair for pair in near if pair[0] <= reach_m]
        if not near:
            alone += 1
            continue
        _gap, owner = min(near)
        open_space[owner] = open_space.get(owner, 0.0) + balcony.area_m2
    return open_space, alone


def from_store(
    apartments: Sequence[QaZone], records: Sequence[Mapping[str, Any]], *, reach_m: float = 1.5
) -> dict[str, dict[str, str | None]]:
    """Each apartment's kept solar verdict (D185), as ``unit_rows`` takes a
    measured one: found by the zone's id, or -- a hotlinked zone renumbered by
    its module's reload -- by its storey, name, number and a centre within
    ``reach_m``."""
    by_guid = {str(row.get("guid", "")).upper(): row for row in records}
    found: dict[str, dict[str, str | None]] = {}
    for zone in apartments:
        row = by_guid.get(zone.guid.upper())
        if row is None and zone.outline:
            cx = sum(x for x, _y in zone.outline) / len(zone.outline)
            cy = sum(y for _x, y in zone.outline) / len(zone.outline)
            near = [
                candidate
                for candidate in records
                if candidate.get("storey") == zone.storey_index
                and str(candidate.get("name", "")).strip() == zone.name
                and str(candidate.get("number", "")).strip() == zone.number
                and abs(float(candidate.get("x", 1e9)) - cx) <= reach_m
                and abs(float(candidate.get("y", 1e9)) - cy) <= reach_m
            ]
            row = near[0] if len(near) == 1 else None
        if row is not None:
            found[zone.guid] = {
                "Meets Minimum": row.get("meets"),
                "No Direct Sunlight": row.get("noSun"),
            }
    return found


# -- the properties ------------------------------------------------------------------------


def property_paths(connection: ArchicadConnection) -> dict[str, str]:
    """``Group/Name`` -> identifier, for every property a copy may name."""
    return {
        f"{detail.group}/{detail.name}": detail.identifier for detail in all_properties(connection)
    }


def read_values(
    connection: ArchicadConnection, guids: Sequence[str], identifiers: Sequence[str]
) -> dict[str, dict[str, str | None]]:
    """Element -> property -> its display string, or None where the property
    is not available on it or holds nothing."""
    if not guids or not identifiers:
        return {}
    found: dict[str, dict[str, str | None]] = {}
    for start in range(0, len(guids), 200):
        batch = list(guids[start : start + 200])
        answer = connection.run_tapir(
            "GetPropertyValuesOfElements",
            {
                "elements": [{"elementId": {"guid": guid}} for guid in batch],
                "properties": [{"propertyId": {"guid": ident}} for ident in identifiers],
            },
        )
        rows = (answer or {}).get("propertyValuesForElements") or []
        for guid, row in zip(batch, rows, strict=False):
            values: dict[str, str | None] = {}
            for ident, cell in zip(
                identifiers, (row or {}).get("propertyValues") or [], strict=False
            ):
                value = (cell or {}).get("propertyValue") or {}
                if not value or value.get("status") in ("notAvailable", "userUndefined"):
                    values[ident] = None
                    continue
                shown = value.get("value")
                if isinstance(shown, dict):
                    shown = shown.get("displayValue") or shown.get("nonLocalizedValue")
                elif isinstance(shown, list):
                    shown = ", ".join(
                        str((one or {}).get("displayValue", one))
                        if isinstance(one, dict)
                        else str(one)
                        for one in shown
                    )
                text = "" if shown is None else str(shown)
                values[ident] = None if text in ("", "<Undefined>") else text
            found[guid] = values
    return found


def _created(answer: Any, what: str) -> list[str]:
    created = (answer or {}).get("propertyIds") if isinstance(answer, dict) else None
    out: list[str] = []
    for item in created or []:
        if isinstance(item, dict) and "error" in item:
            error = item["error"] or {}
            raise ArchicadError(
                f"Archicad would not create {what}: {error.get('message')} "
                f"[code {error.get('code', 'none')}]"
            )
        out.append(str(((item or {}).get("propertyId") or {}).get("guid", "")))
    return out


def ensure_groups(
    connection: ArchicadConnection,
    prefix: str,
    availability: Mapping[str, Sequence[str]],
) -> tuple[dict[tuple[str, str], str], list[str]]:
    """Make the three groups and their properties where they are missing.

    ``availability`` gives, by group suffix, the classification items its
    properties are available to; a group with none is left out and said so.
    A property already there is kept as it is, its options and availability
    with it: a person may have widened them. Returns ``(suffix, field)`` ->
    identifier, and what was done.
    """
    names = group_names(prefix)
    said: list[str] = []
    paths = property_paths(connection)
    groups = {_norm(name): ident for name, ident in property_groups(connection).items()}
    spelt = {_norm(path.partition("/")[0]): path.partition("/")[0] for path in paths}
    made: dict[tuple[str, str], str] = {}
    for suffix, fields in GROUPS.items():
        group = spelt.get(_norm(names[suffix]), names[suffix])
        items = list(availability.get(suffix) or [])
        have = {
            spec.name: ident
            for spec in fields
            if (ident := find_field(paths, group, spec.name)) is not None
        }
        missing = [spec for spec in fields if spec.name not in have]
        if missing and not items:
            said.append(f"{group}: no classified elements to make it available to; left out")
            made.update({(suffix, name): ident for name, ident in have.items()})
            continue
        if missing:
            group_id = groups.get(_norm(group))
            if group_id is None:
                answer = connection.run_tapir(
                    "CreatePropertyGroups",
                    {
                        "propertyGroups": [
                            {
                                "propertyGroup": {
                                    "name": group,
                                    "description": "The QA council's data, made by Loriini.",
                                }
                            }
                        ]
                    },
                )
                ids = (answer or {}).get("propertyGroupIds") or []
                first = ids[0] if ids and isinstance(ids[0], dict) else {}
                if "error" in first:
                    raise ArchicadError(
                        f"Archicad would not create the group {group!r}: "
                        f"{(first['error'] or {}).get('message')}"
                    )
                group_id = str((first.get("propertyGroupId") or {}).get("guid", "")) or None
                if group_id is None:
                    group_id = property_groups(connection).get(group)
                if group_id is None:
                    raise ArchicadError(f"Made the group {group!r} but Archicad does not list it.")
                said.append(f"{group}: group made")
            answer = connection.run_tapir(
                "CreatePropertyDefinitions",
                {
                    "propertyDefinitions": [
                        {
                            "propertyDefinition": {
                                "name": spec.name,
                                "description": spec.description,
                                "type": spec.kind,
                                "isEditable": True,
                                # Undefined until filled: a 0 would read as a
                                # measured POS or storage, and Archicad refuses
                                # a definition with no default at all (D21).
                                "defaultValue": {"basicDefaultValue": {"status": "userUndefined"}},
                                **(
                                    {
                                        "possibleEnumValues": [
                                            {"enumValue": {"displayValue": option}}
                                            for option in spec.options
                                        ]
                                    }
                                    if spec.options
                                    else {}
                                ),
                                "availability": [
                                    {"classificationItemId": {"guid": item}} for item in items
                                ],
                                "group": {"propertyGroupId": {"guid": group_id}},
                            }
                        }
                        for spec in missing
                    ]
                },
            )
            for spec, ident in zip(missing, _created(answer, f"{group}'s properties"), strict=True):
                have[spec.name] = ident
            said.append(f"{group}: {len(missing)} properties made")
        else:
            said.append(f"{group}: already there")
        made.update({(suffix, name): ident for name, ident in have.items()})
    return made, said


def write_values(
    connection: ArchicadConnection, values: Mapping[str, Mapping[str, Any]]
) -> tuple[int, list[str]]:
    """Write element -> property identifier -> value. Returns how many landed
    and what did not, element by element."""
    payload = [
        {
            "elementId": {"guid": guid},
            "propertyId": {"guid": ident},
            "propertyValue": {"value": _shown(value)},
        }
        for guid, row in values.items()
        for ident, value in row.items()
        if value is not None
    ]
    landed = 0
    refused: list[str] = []
    for start in range(0, len(payload), 500):
        batch = payload[start : start + 500]
        answer = connection.run_tapir(
            "SetPropertyValuesOfElements", {"elementPropertyValues": batch}
        )
        results = (answer or {}).get("executionResults") or []
        for sent, result in zip(batch, results, strict=False):
            if isinstance(result, dict) and result.get("success"):
                landed += 1
            else:
                message = ((result or {}).get("error") or {}).get("message", "refused")
                refused.append(f"{sent['elementId']['guid']}: {message}")
    return landed, refused


def _shown(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


# -- what the export works out ---------------------------------------------------------------


@dataclass
class UnitRow:
    """One apartment as the schedule lists it."""

    zone: QaZone
    values: dict[str, Any] = field(default_factory=dict)
    unread: list[str] = field(default_factory=list)


def unit_rows(
    apartments: Sequence[QaZone],
    *,
    copied: Mapping[str, Mapping[str, str | None]],
    copies: Mapping[str, str],
    paths: Mapping[str, str],
    open_space: Mapping[str, float],
    solar: Mapping[str, Mapping[str, str | None]] | None = None,
    unit_no: str = "name",
) -> list[UnitRow]:
    """Every apartment's values: copied where a copy names a property, worked
    out where the zone says it, blank and listed where neither can.

    ``copies`` is field -> ``Group/Name``; ``copied`` is element -> property
    identifier -> display string. ``solar`` is element -> ``Meets Minimum`` /
    ``No Direct Sunlight`` from Loriini's own solar study, which wins over a
    copy for the two solar fields: it is measured, a copy is typed.
    """
    rows: list[UnitRow] = []
    for zone in apartments:
        row = UnitRow(zone)
        own = copied.get(zone.guid, {})
        for field_name, path in copies.items():
            if path in ZONE_SOURCES:
                text: str | None = zone.number if path == ZONE_NUMBER else zone.name
            else:
                ident = paths.get(path)
                if ident is None:
                    continue
                text = own.get(ident)
            value = read_as(field_name, text)
            if value is None and text not in (None, ""):
                row.unread.append(f"{field_name} from {path} = {text!r}")
            if value is not None:
                row.values[field_name] = value
        if "Unit No" not in row.values:
            label = zone.number if unit_no == "number" else zone.name
            if label:
                row.values["Unit No"] = label
        if "Internal area m²" not in row.values:
            row.values["Internal area m²"] = round(zone.area_m2, 2)
        if "POS area m²" not in row.values and zone.guid in open_space:
            row.values["POS area m²"] = round(open_space[zone.guid], 2)
        if solar and zone.guid in solar:
            measured = solar[zone.guid]
            meets = yes_no(measured.get("Meets Minimum"))
            none = yes_no(measured.get("No Direct Sunlight"))
            if meets is not None:
                row.values["Solar 2h"] = meets
            if none is not None:
                row.values["No sun"] = none
        if "Unit Type" not in row.values:
            # From the bedrooms, which are a count; never from the zone's
            # name or number unless a copy says so: "4B" is as often level
            # four, unit B, as it is four bedrooms.
            told = unit_type(None, row.values.get("Bedrooms"))
            if told:
                row.values["Unit Type"] = told
        if "Bedrooms" not in row.values and row.values.get("Unit Type") in UNIT_TYPES:
            kind = row.values["Unit Type"]
            row.values["Bedrooms"] = 0 if kind == "Studio" else int(kind[0])
        rows.append(row)
    return rows


@dataclass(frozen=True)
class Summary:
    """The council's totals, from the rows."""

    lines: tuple[tuple[str, str, str], ...]
    """``(what, figure, against)`` in the order they are written."""


def summary(
    units: Sequence[UnitRow],
    areas: Sequence[tuple[QaZone, str]],
    spaces: Sequence[tuple[QaZone, str]],
    *,
    first_nine: set[int] | None,
) -> Summary:
    lines: list[tuple[str, str, str]] = []
    total = len(units)

    def share(count: int, of: int) -> str:
        return f"{count} of {of} ({100.0 * count / of:.1f} %)" if of else "-"

    lines.append(("Apartments", str(total), ""))
    mix = Counter(row.values.get("Unit Type", "unknown") for row in units)
    for kind in (*UNIT_TYPES, "unknown"):
        if mix.get(kind):
            lines.append((f"  {kind}", share(mix[kind], total), "mix"))
    for key in ("Building", "Core"):
        counted = Counter(str(row.values[key]) for row in units if row.values.get(key))
        for name, count in sorted(counted.items()):
            lines.append((f"{key} {name}", str(count), "ADG 4F" if key == "Core" else ""))
    small = [
        row
        for row in units
        if row.values.get("Unit Type") in MIN_INTERNAL_M2
        and float(row.values.get("Internal area m²") or 0.0)
        < MIN_INTERNAL_M2[row.values["Unit Type"]]
    ]
    lines.append(("Below the 4D minimum area", str(len(small)), "ADG 4D-1"))
    tight = [
        row
        for row in units
        if row.values.get("Unit Type") in MIN_POS_M2
        and row.values.get("POS area m²") is not None
        and float(row.values["POS area m²"]) < MIN_POS_M2[row.values["Unit Type"]]
    ]
    lines.append(("Below the 4E minimum POS", str(len(tight)), "ADG 4E-1"))
    solar = sum(1 for row in units if row.values.get("Solar 2h") == "Yes")
    lines.append(("Solar 2h", share(solar, total), "ADG 4A: at least 70 %"))
    dark = sum(1 for row in units if row.values.get("No sun") == "Yes")
    lines.append(("No sun", share(dark, total), "ADG 4A: at most 15 %"))
    low = [row for row in units if first_nine is None or row.zone.storey_index in first_nine]
    vented = sum(1 for row in low if row.values.get("Cross vent") == "Yes")
    lines.append(
        ("Cross vent, first nine storeys", share(vented, len(low)), "ADG 4B: at least 60 %")
    )
    for key, words in (("Adaptable", "Yes"), ("Affordable", "Yes")):
        lines.append((key, str(sum(1 for row in units if row.values.get(key) == words)), ""))
    for grade in ("Silver", "Gold"):
        lines.append(
            (
                f"Livable {grade}",
                str(sum(1 for row in units if row.values.get("Livable") == grade)),
                "",
            )
        )
    by_type: dict[str, float] = {}
    for zone, kind in areas:
        by_type[kind] = by_type.get(kind, 0.0) + zone.area_m2
    for kind in AREA_TYPES:
        if kind in by_type:
            lines.append((kind, f"{by_type[kind]:,.1f} m²", ""))
    parking = Counter(kind for _zone, kind in spaces)
    for kind in SPACE_TYPES:
        if parking.get(kind):
            lines.append((f"Parking: {kind}", str(parking[kind]), ""))
    return Summary(tuple(lines))
