"""The area calculation a massing is judged by: GBA, GFA, NSA, FSR and yield.

Asked on 28 September 2026 as roadmap item R3, with the office's own sheet
as the answer to copy: *Area calculation, GFA + Yield*. Massing is modelled
in slabs, one per floor, and the numbers the sheet carries follow from their
areas by the office's own factors:

* **GBA**, gross building area: the slabs themselves, to their outside
  edge -- a massing slab is drawn to the building's outside face.
* **GFA**, gross floor area: the GBA by a factor per use, 0.75 for
  residential and 0.9 for anything else, for the walls, the cores, the
  plant and the circulation the LEP's definition leaves out.
* **NSA**, net saleable area: the GFA by a second factor, 0.85 and 0.9.
* **FSR**: the GFA over the site's area, against the control.
* **Yield**: the residential NSA over the mix's average unit, split into
  the mix.

The four factors and the mix are the practice's, not the tool's; the
defaults are the ones on the office's sheet, and every one of them is a
setting. The sheet the defaults were read from has its two rows the wrong
way round -- the rows it labels non-residential were worked with the
residential factors, 0.75 and 0.85, and the tower they measure is the
building's yellow, residential bulk -- which is worth knowing when the two
are compared.

Where the numbers stop being arithmetic
---------------------------------------
Units come out whole. The count is the residential NSA over the average
unit, *rounded down*: a yield promises what fits, and the remainder of a
unit is not a unit. The count is then split into the mix by the largest
remainder, so the types always add back up to the count: each type gets
the whole part of its share, and what is left goes one at a time to the
types with the largest fractions, the first-listed first among equals.
The office's sheet, 112 units at 15, 70 and 15 per cent, is 16.8, 78.4 and
16.8: 16, 78 and 16 whole, and the two left over go to the two eights --
17, 78 and 17, which is what the sheet says.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

__all__ = [
    "DEFAULT_MIX",
    "NON_RESIDENTIAL",
    "RESIDENTIAL",
    "USES",
    "AreaSchedule",
    "Areas",
    "Floor",
    "Homes",
    "Ratios",
    "StoreyRow",
    "Targets",
    "UnitCount",
    "UnitType",
    "checked_mix",
    "homes_for",
    "parse_unit",
    "schedule",
    "unit_text",
]

RESIDENTIAL: Final = "residential"
NON_RESIDENTIAL: Final = "non-residential"
Use = Literal["residential", "non-residential"]
USES: tuple[Use, ...] = (RESIDENTIAL, NON_RESIDENTIAL)

#: How far the mix's shares may be from a hundred per cent between them and
#: still be read as a hundred: shares typed to one decimal, three of them.
SHARE_SLACK = 0.005


@dataclass(frozen=True)
class Ratios:
    """The office's four factors: how much of each area the next one is."""

    gfa_residential: float = 0.75
    gfa_non_residential: float = 0.90
    nsa_residential: float = 0.85
    nsa_non_residential: float = 0.90

    def __post_init__(self) -> None:
        for label, value in (
            ("GBA to GFA (residential)", self.gfa_residential),
            ("GBA to GFA (non-residential)", self.gfa_non_residential),
            ("GFA to NSA (residential)", self.nsa_residential),
            ("GFA to NSA (non-residential)", self.nsa_non_residential),
        ):
            if not (0.0 < value <= 1.0) or math.isnan(value):
                raise ValueError(
                    f"The {label} factor has to be more than 0 and at most 1, not {value:g}: "
                    "it is the share of one area that the next one is."
                )

    def gfa(self, use: Use) -> float:
        """GBA to GFA, for this use."""
        return self.gfa_residential if use == RESIDENTIAL else self.gfa_non_residential

    def nsa(self, use: Use) -> float:
        """GFA to NSA, for this use."""
        return self.nsa_residential if use == RESIDENTIAL else self.nsa_non_residential


@dataclass(frozen=True)
class UnitType:
    """One kind of apartment in the mix: its name, its share of the units,
    and its typical net saleable area."""

    name: str
    share: float
    """A fraction: 0.7 is seventy per cent."""
    size_m2: float


#: The office's sheet: fifteen, seventy and fifteen per cent. The sizes are
#: the ones that give its 112 units from its residential NSA -- an average
#: of 75 m² -- and sit above the ADG's minimum internal areas (50, 70 and 90
#: m²) by what a balcony and a second bathroom add. Settings, not rules.
DEFAULT_MIX: tuple[UnitType, ...] = (
    UnitType("1 Bedroom", 0.15, 55.0),
    UnitType("2 Bedroom", 0.70, 75.0),
    UnitType("3 Bedroom", 0.15, 95.0),
)

_NUMBER = r"\d+(?:\.\d+)?"
_UNIT = re.compile(
    rf"^\s*(?P<name>[^=]+?)\s*=\s*(?P<share>{_NUMBER})\s*%?\s*[,;]\s*"
    rf"(?P<size>{_NUMBER})\s*(?:m2|m²|sqm)?\s*$",
    re.IGNORECASE,
)


def parse_unit(text: str) -> UnitType:
    """``2 Bedroom=70,75`` -- the name, its share in per cent and its size in
    square metres -- as a unit type. Raises ``ValueError`` with a sentence."""
    found = _UNIT.match(text)
    if found is None:
        raise ValueError(
            f"{text!r} is not a unit type. Write it as the name, its share of the "
            "units in per cent and its size in m², like '2 Bedroom=70,75'."
        )
    return UnitType(
        " ".join(found["name"].split()), float(found["share"]) / 100.0, float(found["size"])
    )


def unit_text(unit: UnitType) -> str:
    """The unit type as ``parse_unit`` reads it: the command line's spelling."""
    return f"{unit.name}={unit.share * 100:g},{unit.size_m2:g}"


def checked_mix(mix: Iterable[UnitType]) -> tuple[UnitType, ...]:
    """The mix, with the types that have no share left out, or a
    ``ValueError`` that says what is wrong with it.

    The shares have to come to a hundred per cent: a mix that comes to
    ninety would quietly leave a tenth of the building out of the yield.
    """
    kept: list[UnitType] = []
    seen: set[str] = set()
    for unit in mix:
        if unit.share < 0 or math.isnan(unit.share):
            raise ValueError(f"{unit.name} has a share below nothing.")
        if unit.share == 0:
            continue
        if not unit.size_m2 > 0:
            raise ValueError(f"{unit.name} has no size; it needs its typical area in m².")
        key = unit.name.casefold()
        if key in seen:
            raise ValueError(f"{unit.name} is in the mix twice.")
        seen.add(key)
        kept.append(unit)
    if not kept:
        raise ValueError("The mix has no unit types in it with a share.")
    total = sum(unit.share for unit in kept)
    if abs(total - 1.0) > SHARE_SLACK:
        raise ValueError(
            f"The mix's shares come to {total * 100:g}% and have to come to 100%: "
            + ", ".join(f"{unit.name} {unit.share * 100:g}%" for unit in kept)
            + "."
        )
    return tuple(kept)


@dataclass(frozen=True)
class Floor:
    """One slab's worth of floor: where it is, what it is, how big."""

    storey: str
    use: Use
    area_m2: float
    level_m: float = 0.0
    """For putting storeys in order; the storey's own level."""


@dataclass(frozen=True)
class Areas:
    """GBA, GFA and NSA, for one use or both."""

    gba_m2: float = 0.0
    gfa_m2: float = 0.0
    nsa_m2: float = 0.0

    def __add__(self, other: Areas) -> Areas:
        return Areas(
            self.gba_m2 + other.gba_m2, self.gfa_m2 + other.gfa_m2, self.nsa_m2 + other.nsa_m2
        )


@dataclass(frozen=True)
class StoreyRow:
    """One storey's GBA by use."""

    storey: str
    level_m: float
    residential_m2: float
    non_residential_m2: float

    @property
    def total_m2(self) -> float:
        return self.residential_m2 + self.non_residential_m2


@dataclass(frozen=True)
class UnitCount:
    unit: UnitType
    count: int


@dataclass(frozen=True)
class Homes:
    """The yield: how many units, of which kind, at what average."""

    units: int
    counts: tuple[UnitCount, ...]
    average_m2: float
    """The mix's average net saleable area per unit."""

    def share(self, count: UnitCount) -> float:
        """This type's share of the units actually counted."""
        return count.count / self.units if self.units else 0.0


def homes_for(nsa_m2: float, mix: Sequence[UnitType]) -> Homes:
    """The units a residential NSA holds at this mix, split by the largest
    remainder so the types add back up to the count."""
    average = sum(unit.share * unit.size_m2 for unit in mix)
    units = math.floor(nsa_m2 / average + 1e-9) if average > 0 and nsa_m2 > 0 else 0
    quotas = [units * unit.share for unit in mix]
    whole = [math.floor(quota + 1e-9) for quota in quotas]
    left = units - sum(whole)
    # The largest fractions first; among equals, the type listed first.
    order = sorted(range(len(mix)), key=lambda i: (-(quotas[i] - whole[i]), i))
    for i in order[: max(left, 0)]:
        whole[i] += 1
    counts = tuple(UnitCount(unit, count) for unit, count in zip(mix, whole, strict=True))
    return Homes(units, counts, average)


@dataclass(frozen=True)
class Targets:
    """What the massing is measured against: the FSR control and the unit
    count the brief asks for. Either may be unknown."""

    fsr: float | None = None
    units: int | None = None


@dataclass(frozen=True)
class AreaSchedule:
    """Everything the sheet and the workbook say."""

    residential: Areas
    non_residential: Areas
    storeys: tuple[StoreyRow, ...]
    ratios: Ratios
    mix: tuple[UnitType, ...]
    homes: Homes
    site_area_m2: float | None = None
    targets: Targets = field(default_factory=Targets)

    @property
    def total(self) -> Areas:
        return self.residential + self.non_residential

    def fsr(self, areas: Areas) -> float | None:
        """This GFA over the site, or ``None`` with no site area."""
        return areas.gfa_m2 / self.site_area_m2 if self.site_area_m2 else None

    @property
    def target_gfa_m2(self) -> float | None:
        """The GFA the FSR control allows on this site."""
        if self.targets.fsr is None or not self.site_area_m2:
            return None
        return self.targets.fsr * self.site_area_m2

    @property
    def gfa_per_unit_m2(self) -> float | None:
        """The residential GFA over the units: what each costs in GFA."""
        return self.residential.gfa_m2 / self.homes.units if self.homes.units else None


def _areas(gba_m2: float, ratios: Ratios, use: Use) -> Areas:
    gfa = gba_m2 * ratios.gfa(use)
    return Areas(gba_m2, gfa, gfa * ratios.nsa(use))


def schedule(
    floors: Iterable[Floor],
    *,
    ratios: Ratios | None = None,
    mix: Sequence[UnitType] = DEFAULT_MIX,
    site_area_m2: float | None = None,
    targets: Targets | None = None,
) -> AreaSchedule:
    """The area calculation for these floors.

    Raises ``ValueError`` for a mix that does not come to a hundred per
    cent, a site with no area, or a target below nothing -- each a setting
    somebody typed, so each is said rather than worked around.
    """
    ratios = ratios or Ratios()
    targets = targets or Targets()
    kept_mix = checked_mix(mix)
    if site_area_m2 is not None and not site_area_m2 > 0:
        raise ValueError(f"The site area has to be more than nothing, not {site_area_m2:g} m².")
    if targets.fsr is not None and not targets.fsr > 0:
        raise ValueError(f"The target FSR has to be more than nothing, not {targets.fsr:g}.")
    if targets.units is not None and targets.units < 0:
        raise ValueError(f"The target unit count cannot be below nothing ({targets.units}).")

    by_storey: dict[str, list[float]] = {}
    levels: dict[str, float] = {}
    gba = {RESIDENTIAL: 0.0, NON_RESIDENTIAL: 0.0}
    for floor in floors:
        gba[floor.use] += floor.area_m2
        row = by_storey.setdefault(floor.storey, [0.0, 0.0])
        row[0 if floor.use == RESIDENTIAL else 1] += floor.area_m2
        levels[floor.storey] = min(levels.get(floor.storey, floor.level_m), floor.level_m)
    storeys = tuple(
        StoreyRow(name, levels[name], row[0], row[1])
        for name, row in sorted(by_storey.items(), key=lambda item: (levels[item[0]], item[0]))
    )
    residential = _areas(gba[RESIDENTIAL], ratios, RESIDENTIAL)
    non_residential = _areas(gba[NON_RESIDENTIAL], ratios, NON_RESIDENTIAL)
    return AreaSchedule(
        residential=residential,
        non_residential=non_residential,
        storeys=storeys,
        ratios=ratios,
        mix=kept_mix,
        homes=homes_for(residential.nsa_m2, kept_mix),
        site_area_m2=site_area_m2,
        targets=targets,
    )
