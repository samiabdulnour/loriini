"""The QA export's IFC, two ways, and the check every one of them gets (D184).

**Loriini's own.** One IfcSpace per zone -- apartments, area zones, parking
-- on its storey, its outline extruded to the storey's height, carrying the
QA groups as property sets of the same names and its area as
``Qto_SpaceBaseQuantities``. Written with ifcopenshell, so it needs no
translator and comes out the same on every Archicad: the brief's own fallback
("a translator that exports Zones only is enough for the schedule").

**Archicad's, through a named translator.** The whole model as the office's
QA translator exports it: Archicad's API can choose a translator by name but
not make or change one, so the translator is set up once by hand (or
imported from the .xml Loriini keeps) and the export finds it.

**The check.** Either file is opened again and counted: spaces, typed
elements against generic proxies, and whether the QA property sets are on the
spaces and filled. The two faults the brief found in the office's IFCs -- no
spaces, everything a proxy -- are said in so many words.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sun_study.archicad.qa_export import QaZone, Storeys

#: Above a level, a space this tall when its storey's height is not known.
DEFAULT_HEIGHT_M = 3.0


def write_qa_ifc(
    path: Path,
    *,
    project: str,
    storeys: Storeys,
    spaces: Sequence[tuple[QaZone, str, Mapping[str, Any]]],
) -> Path:
    """Write ``spaces`` -- ``(zone, property set name, values)`` -- as IfcSpaces."""
    import numpy as np
    from ifcopenshell.api import (
        aggregate,
        context,
        geometry,
        pset,
        root,
        unit,
    )
    from ifcopenshell.api import (
        project as ifc_project,
    )

    model = ifc_project.create_file(version="IFC4")
    ifc_root = root.create_entity(model, ifc_class="IfcProject", name=project)
    unit.assign_unit(model)
    model_context = context.add_context(model, context_type="Model")
    body = context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_context,
    )
    site = root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = root.create_entity(model, ifc_class="IfcBuilding", name=project)
    aggregate.assign_object(model, products=[site], relating_object=ifc_root)
    aggregate.assign_object(model, products=[building], relating_object=site)

    order = sorted(storeys.levels, key=lambda index: storeys.levels[index])
    used = sorted({zone.storey_index for zone, _g, _v in spaces if zone.storey_index is not None})
    made: dict[int, Any] = {}
    for index in used:
        storey = root.create_entity(
            model, ifc_class="IfcBuildingStorey", name=storeys.names.get(index) or f"Storey {index}"
        )
        storey.Elevation = storeys.levels.get(index, 0.0)
        matrix = np.eye(4)
        matrix[2, 3] = storeys.levels.get(index, 0.0)
        geometry.edit_object_placement(model, product=storey, matrix=matrix)
        aggregate.assign_object(model, products=[storey], relating_object=building)
        made[index] = storey

    def height(index: int | None) -> float:
        if index is None or index not in order:
            return DEFAULT_HEIGHT_M
        above = order.index(index) + 1
        if above < len(order):
            gap = storeys.levels[order[above]] - storeys.levels[index]
            if 1.5 <= gap <= 12.0:
                return gap
        return DEFAULT_HEIGHT_M

    by_storey: dict[int | None, list[Any]] = {}
    for zone, group, values in spaces:
        space = root.create_entity(model, ifc_class="IfcSpace", name=zone.number or zone.name)
        space.LongName = zone.name or None
        if len(zone.outline) >= 3:
            ring = list(zone.outline)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            points = [model.createIfcCartesianPoint((float(x), float(y))) for x, y in ring]
            profile = model.createIfcArbitraryClosedProfileDef(
                "AREA", None, model.createIfcPolyline(points)
            )
            solid = model.createIfcExtrudedAreaSolid(
                profile,
                model.createIfcAxis2Placement3D(model.createIfcCartesianPoint((0.0, 0.0, 0.0))),
                model.createIfcDirection((0.0, 0.0, 1.0)),
                height(zone.storey_index),
            )
            representation = model.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
            geometry.assign_representation(model, product=space, representation=representation)
        matrix = np.eye(4)
        matrix[2, 3] = (
            storeys.levels.get(zone.storey_index, 0.0) if zone.storey_index is not None else 0.0
        )
        geometry.edit_object_placement(model, product=space, matrix=matrix)
        filled = {name: value for name, value in values.items() if value is not None}
        if filled:
            properties = pset.add_pset(model, product=space, name=group)
            pset.edit_pset(model, pset=properties, properties=filled)
        quantities = pset.add_qto(model, product=space, name="Qto_SpaceBaseQuantities")
        pset.edit_qto(model, qto=quantities, properties={"NetFloorArea": round(zone.area_m2, 3)})
        by_storey.setdefault(zone.storey_index, []).append(space)
    for at, members in by_storey.items():
        parent = made.get(at) if at is not None else None
        aggregate.assign_object(model, products=members, relating_object=parent or building)

    path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(path))
    return path


@dataclass(frozen=True)
class IfcCheck:
    """What an exported IFC holds, for the schedule's sake."""

    path: Path
    spaces: int
    proxies: int
    typed: Mapping[str, int]
    with_groups: Mapping[str, int]
    """Spaces carrying each QA property set, by its name."""
    empty: Mapping[str, int]
    """Of the unit spaces, how many leave each unit field blank."""

    def lines(self) -> list[str]:
        said = [f"{self.path.name}: {self.spaces} spaces, {self.proxies} generic proxies"]
        if self.typed:
            said.append(
                "  typed: "
                + ", ".join(f"{count} {name}" for name, count in sorted(self.typed.items()))
            )
        if not self.spaces:
            said.append(
                "  NO SPACES: the zones were not exported. In the translator, turn off "
                "'Export only elements for collision detection' and include Zones."
            )
        if self.proxies and self.proxies > sum(self.typed.values()):
            said.append(
                "  MOSTLY PROXIES: the translator maps every element to a generic proxy. "
                "Set its type mapping to map by element type."
            )
        for name, count in sorted(self.with_groups.items()):
            said.append(f"  {name}: on {count} spaces")
        for name, count in sorted(self.empty.items()):
            if count:
                said.append(f"    {name}: blank on {count}")
        return said


TYPED = (
    "IfcWall",
    "IfcSlab",
    "IfcColumn",
    "IfcBeam",
    "IfcDoor",
    "IfcWindow",
    "IfcStair",
    "IfcRailing",
    "IfcRoof",
)


def check_ifc(
    path: Path, groups: Sequence[str], unit_group: str, unit_fields: Sequence[str]
) -> IfcCheck:
    """Open an IFC and count what the schedule needs of it."""
    import ifcopenshell
    import ifcopenshell.util.element

    model = ifcopenshell.open(str(path))
    spaces = model.by_type("IfcSpace")
    typed: Counter[str] = Counter()
    for name in TYPED:
        try:
            count = len(model.by_type(name))
        except RuntimeError:
            count = 0
        if count:
            typed[name] = count
    with_groups: Counter[str] = Counter()
    empty: Counter[str] = Counter()
    for space in spaces:
        sets = ifcopenshell.util.element.get_psets(space)
        for name in groups:
            if name in sets:
                with_groups[name] += 1
        unit = sets.get(unit_group)
        if unit is not None:
            for field_name in unit_fields:
                if unit.get(field_name) in (None, ""):
                    empty[field_name] += 1
    return IfcCheck(
        path=path,
        spaces=len(spaces),
        proxies=len(model.by_type("IfcBuildingElementProxy")),
        typed=dict(typed),
        with_groups=dict(with_groups),
        empty=dict(empty),
    )
