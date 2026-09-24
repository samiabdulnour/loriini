"""The future context: the buildings next door, as tall as the controls allow.

Each existing neighbour within reach of the site keeps its own footprint and
is raised to the storeys the LEP's height-of-building control allows where it
stands. That is how the office reads a future context -- the building that is
there, built up to its limit -- and it is what a shadow diagram needs: the
same street, the same gaps between the buildings, and each one as high as it
may go. Never lowered: a building already over the control is its own
future, and is left to the existing context.

It replaces a lot-by-lot envelope (the lot set back by the ADG's separations,
stepped, capped by the ratio), which is still in ``site.envelope`` and is
the right tool for a different question -- what the *site* could hold -- but
which put buildings where there are none today and moved every neighbour off
the footprint a person recognises.

Which buildings: those the reach takes in, zoned where flats are permitted
(``DEFAULT_ZONES``, settable), with a height control. A house on land zoned
for houses is left as it is; its future is a house. The control is the LEP's
because that is what the register carries: a council's DCP can say less, and
is not open data.

A layer of its own, ``LORIINI FUTURE``, rather than the context model's:
the shadow diagram's saved views say what stands (D78), and a future
neighbour is a question a view answers -- with, without -- not a fact the
model asserts. Switch the layer on for the SEARs envelope study and off for
the DA's existing-conditions set.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection
from sun_study.archicad.context_model import (
    STOREY_M,
    _clear_previous,
    _contours,
    _create_slabs,
    _datum_storey,
    _Ground,
    _on_the_floor_plan,
    _send_through_the_addon,
    _Slab,
    _slab_outline,
    project_datum,
    storeys_of,
)
from sun_study.archicad.draw import ensure_layer
from sun_study.archicad.site_analysis import Frame, _clean_ring
from sun_study.site.arcgis import rings_of
from sun_study.site.envelope import (
    DEFAULT_FRONT_SETBACK_M,
    DEFAULT_REACH_M,
    DEFAULT_ZONES,
    Envelope,
    FutureReport,
    Lot,
    Tier,
    _permitted,
    _ring_distance,
)
from sun_study.site.geo import Point, point_in_ring, ring_area, ring_centroid
from sun_study.site.pipeline import SiteBundle

__all__ = [
    "DEFAULT_FRONT_SETBACK_M",
    "DEFAULT_REACH_M",
    "DEFAULT_ZONES",
    "ID_PREFIX",
    "FutureModelReport",
    "FutureOptions",
    "FutureReport",
    "future_envelopes",
    "layer_name",
    "lots_of",
    "model_future",
]


#: Where the envelopes stand. Not the context model's layer, so a view can
#: show the neighbourhood as it is or as the controls would have it.
#: A function rather than a constant, for the reason context_model.layer_name
#: gives: the site group is chosen per run.
def layer_name() -> str:
    """The layer the future envelopes go on, beside the context and not in it."""
    return naming.future_layer()


#: What every slab's Element ID starts with, and what a rerun deletes by.
ID_PREFIX = "SA FUTURE"

#: A footprint smaller than this is a shed or a bin store, not a building
#: anybody will raise.
LEAST_FOOTPRINT_M2 = 20.0


@dataclass(frozen=True)
class FutureOptions:
    """What the envelopes are worked out with; the command line's flags."""

    reach_m: float = DEFAULT_REACH_M
    front_setback_m: float = DEFAULT_FRONT_SETBACK_M
    """Kept for the lot envelope in ``site.envelope``; the raised buildings
    stand on their own footprints and are not set back."""
    zones: tuple[str, ...] = DEFAULT_ZONES
    storey_m: float = STOREY_M
    datum_m: float | None = None
    """What project zero stands for; ``None`` reads it from the project."""


@dataclass(frozen=True)
class FutureModelReport:
    """What went into the model."""

    future: FutureReport
    slabs: int
    layer: str
    notes: tuple[str, ...] = ()

    def describe(self) -> str:
        lines = [self.future.describe(), f"  {self.slabs} slabs on {self.layer!r}"]
        lines.extend(f"    {note}" for note in self.notes)
        return "\n".join(lines)


class _Control:
    """A polygon-valued control at a point: the height, the ratio, the zone."""

    def __init__(self, collection: dict[str, Any], field: str) -> None:
        self.zones: list[tuple[tuple[float, float, float, float], list[list[Point]], Any]] = []
        for feature in collection.get("features", []):
            value = (feature.get("properties") or {}).get(field)
            if value is None or value == "":
                continue
            rings = rings_of(feature.get("geometry"))
            if not rings:
                continue
            xs = [x for ring in rings for x, _ in ring]
            ys = [y for ring in rings for _, y in ring]
            self.zones.append(((min(xs), min(ys), max(xs), max(ys)), rings, value))

    def at(self, lon: float, lat: float) -> Any:
        for (x0, y0, x1, y1), rings, value in self.zones:
            if x0 <= lon <= x1 and y0 <= lat <= y1:
                if any(point_in_ring(lon, lat, ring) for ring in rings):
                    return value
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def lots_of(bundle: SiteBundle, frame: Frame) -> list[Lot]:
    """Every lot in the bundle's cadastre, projected, with its controls read
    at its centroid. Strata lots stacked on one footprint are one lot."""
    heights = _Control(bundle.height_of_building, "MAX_B_H")
    ratios = _Control(bundle.floor_space_ratio, "FSR")
    zoning = _Control(bundle.zoning, "SYM_CODE")
    seen: set[tuple[tuple[int, int], ...]] = set()
    lots: list[Lot] = []
    for feature in bundle.all_lots.get("features", []):
        name = str((feature.get("properties") or {}).get("lotidstring") or "").strip()
        for ring in rings_of(feature.get("geometry")):
            projected = _clean_ring(frame.ring(ring))
            if len(projected) < 3:
                continue
            signature = tuple(sorted((round(x / 0.05), round(y / 0.05)) for x, y in projected))
            if signature in seen:
                continue
            seen.add(signature)
            lon, lat = frame.unproject(*ring_centroid(projected))
            zone = zoning.at(lon, lat)
            lots.append(
                Lot(
                    identifier=name or f"LOT {len(lots) + 1}",
                    ring=tuple(projected),
                    zone=str(zone) if zone is not None else None,
                    height_m=_number(heights.at(lon, lat)),
                    fsr=_number(ratios.at(lon, lat)),
                )
            )
    return lots


def future_envelopes(
    bundle: SiteBundle, frame: Frame, options: FutureOptions | None = None
) -> FutureReport:
    """Each existing neighbour near the site, raised to its height control.

    In the envelope shapes the site sheet and the model already draw: one
    tier, the building's own footprint, from the ground to the top of the
    last whole storey under the control.
    """
    options = options or FutureOptions()
    site_rings = [_clean_ring(frame.ring(ring)) for ring in bundle.site_rings]
    heights = _Control(bundle.height_of_building, "MAX_B_H")
    zoning = _Control(bundle.zoning, "SYM_CODE")
    lots = lots_of(bundle, frame)

    found: list[Envelope] = []
    beyond = on_site = other_zones = no_height = too_small = at_limit = 0
    for number, building in enumerate(bundle.furniture.buildings, start=1):
        ring = _slab_outline(frame.ring(building.ring))
        if len(ring) < 3 or abs(ring_area(ring)) < LEAST_FOOTPRINT_M2:
            too_small += 1
            continue
        cx, cy = ring_centroid(ring)
        if any(point_in_ring(cx, cy, site) for site in site_rings if len(site) >= 3):
            on_site += 1
            continue
        if (
            site_rings
            and min(_ring_distance(ring, site) for site in site_rings if len(site) >= 3)
            > options.reach_m
        ):
            beyond += 1
            continue
        lon, lat = frame.unproject(cx, cy)
        zone = zoning.at(lon, lat)
        if options.zones and not _permitted(None if zone is None else str(zone), options.zones):
            other_zones += 1
            continue
        control = _number(heights.at(lon, lat))
        if control is None:
            no_height += 1
            continue
        allowed = int(control // options.storey_m)
        standing, _ = storeys_of(
            building.levels, building.height_m, None, storey_m=options.storey_m
        )
        if allowed <= standing:
            at_limit += 1
            continue
        lot = next(
            (lot for lot in lots if point_in_ring(cx, cy, list(lot.ring))),
            None,
        )
        top = allowed * options.storey_m
        found.append(
            Envelope(
                # The lot for its name, which the slab's ID and the caption
                # carry; its ratio is dropped because nothing here applies it,
                # and a caption quoting an FSR invites the reading that it did.
                lot=Lot(
                    identifier=lot.identifier if lot is not None else f"BUILDING {number}",
                    ring=tuple(ring),
                    zone=None if zone is None else str(zone),
                    height_m=control,
                    fsr=None,
                ),
                tiers=(Tier(rings=(tuple(ring),), bottom_m=0.0, top_m=top, boundary_m=0.0),),
                storeys=allowed,
                height_m=round(top, 2),
                gfa_m2=abs(ring_area(ring)) * allowed,
                allowed_gfa_m2=None,
                binding="height",
                street_edges=0,
            )
        )
    return FutureReport(
        envelopes=tuple(found),
        beyond_reach=beyond,
        on_site=on_site,
        other_zones=other_zones,
        no_height=no_height,
        too_small=too_small,
        at_limit=at_limit,
        raised=True,
    )


def _identifier(envelope: Envelope, tier_index: int) -> str:
    tier = envelope.tiers[tier_index]
    binding = " FSR" if envelope.binding == "fsr" else ""
    return (
        f"{ID_PREFIX} {envelope.lot.identifier} {envelope.storeys} STOREY "
        f"{tier.bottom_m:g}-{tier.top_m:g} m{binding}"
    )


def model_future(
    connection: ArchicadConnection,
    bundle: SiteBundle,
    frame: Frame,
    *,
    options: FutureOptions | None = None,
    found: FutureReport | None = None,
    say: Callable[[str], None] | None = None,
) -> FutureModelReport:
    """The envelopes as slabs, one per tier, on ``LORIINI FUTURE``.

    ``found`` is the report already worked out for the site sheet, so the
    model and the sheet cannot disagree; left out, it is worked out here.
    """
    options = options or FutureOptions()
    _on_the_floor_plan(connection)
    layer = ensure_layer(connection, layer_name())
    notes: list[str] = []
    removed = _clear_previous(connection, prefixes=(ID_PREFIX,))
    if removed:
        notes.append(f"{removed} slabs from the last run removed first.")

    report = found if found is not None else future_envelopes(bundle, frame, options)
    datum = project_datum(connection) if options.datum_m is None else options.datum_m
    if datum:
        notes.append(f"placed against a datum of {datum:,.2f} m.")
    contours = _contours(bundle, frame)
    ground = _Ground(contours) if contours else None
    if ground is None:
        notes.append("no contours in the bundle; the envelopes stand at level zero.")

    slabs: list[_Slab] = []
    for envelope in report.envelopes:
        base = (ground.at(ring_centroid(list(envelope.footprint))) if ground else 0.0) - datum
        for i, tier in enumerate(envelope.tiers):
            for ring in tier.rings:
                outline = _slab_outline(ring)
                if len(outline) < 3:
                    continue
                slabs.append(
                    _Slab(
                        outline=outline,
                        holes=[],
                        level=base + tier.bottom_m,
                        thickness=tier.top_m - tier.bottom_m,
                        identifier=_identifier(envelope, i),
                    )
                )

    made = 0
    if slabs:
        outcome = _create_slabs(
            partial(
                _send_through_the_addon,
                connection,
                layer.index,
                _datum_storey(connection)[0],
            ),
            slabs,
        )
        if outcome is None:
            notes.append(
                "the add-on has no CreateSlabs; the future context needs a Loriini build "
                "that does, and was not modelled."
            )
        else:
            made = len(outcome.made)
            notes.extend(outcome.describe())
    if say:
        say(f"  {made} future slabs, {len(report.envelopes)} envelopes")
    return FutureModelReport(report, made, layer.name, tuple(notes))
