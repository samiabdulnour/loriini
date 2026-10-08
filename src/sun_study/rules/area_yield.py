"""The preliminary yield analysis a massing is judged by, as the office's
feasibility sheet works it.

Asked on 28 September 2026 as roadmap item R3 and given its shape on 8
October by the office's *Feasibility template*, *Preliminary Yield
Analysis*: one sheet per option. Massing is modelled in slabs, one per
floor, and the sheet's figures follow from their areas by the office's own
efficiencies, which this module keeps as its defaults and follows to the
letter:

* **BEA**, the built envelope area: the slabs themselves, to their outside
  edge -- a massing slab is drawn to the building's outside face -- by
  level and by use: residential, commercial, retail.
* **GFA**, gross floor area: the BEA by *BEA to GFA*, 0.725 for residential,
  0.85 for commercial and 0.95 for retail.
* **NLA**, net lettable (saleable) area: the GFA by *GFA to NLA*, 0.85, 0.9
  and 0.9.
* **FSR**: each use's GFA over the site, against the permissible FSR the
  sheet splits by use, and the difference.
* **Units**: the residential GFA over the *average GFA* of a unit -- the
  mix's average NLA (its sizes by their shares, plus common area and a
  tolerance per unit) over the residential GFA-to-NLA -- shared into the
  mix, market and affordable apart. The sheet does not round: 44.1 units is
  what it says, and so does this.
* **Parking**: the units by a rate per type (SEPP and DCP columns), the
  visitors, the commercial and retail GFA by their rates, and the basements
  that parking needs at so many square metres a space over the share of the
  site the basement may take.

Every one of those numbers is the practice's, not the tool's, and every one
is a setting; the workbook the sheet is written to keeps them as input cells
so a what-if is typed into Excel.

Levels
------
The sheet's storey table is by level, and a massing's slabs say where they
are by their elevation, not by their home storey: a stack of storey-thick
slabs is usually homed on the ground storey and offset up. So the floors
are gathered into levels by the elevation of their underside, slabs within
half a metre of each other on one level, and named up from the ground --
*Ground Floor*, *Level 01*, *Level 02*; *B 01* below -- the ground being the
level nearest the project's ground storey, or the lowest when no storey is
known. The floor-to-floor of a level is the rise to the level above; the
top level's is its own slab's thickness when the slabs are storey-thick.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Final, Literal

__all__ = [
    "AFFORDABLE_MIX",
    "COMMERCIAL",
    "DEFAULT_MIX",
    "LABELS",
    "RESIDENTIAL",
    "RETAIL",
    "USES",
    "Efficiencies",
    "Feasibility",
    "Floor",
    "Level",
    "Mix",
    "ParkingRates",
    "Permissible",
    "UnitRates",
    "UnitType",
    "checked_mix",
    "default_rates",
    "feasibility",
    "level_index",
    "level_name",
    "levels_from",
    "parse_level",
    "parse_rates",
    "parse_unit",
    "unit_text",
]

RESIDENTIAL: Final = "residential"
COMMERCIAL: Final = "commercial"
RETAIL: Final = "retail"
Use = Literal["residential", "commercial", "retail"]
USES: tuple[Use, ...] = (RESIDENTIAL, COMMERCIAL, RETAIL)
#: The uses as the sheet writes them.
LABELS: Mapping[str, str] = {RESIDENTIAL: "Residential", COMMERCIAL: "Commercial", RETAIL: "Retail"}

#: How far the mix's shares may be from a hundred per cent between them and
#: still be read as a hundred: shares typed to one decimal, five of them.
SHARE_SLACK = 0.005

#: Slabs whose undersides are within this of each other are one level.
TOGETHER_M = 0.5

#: A slab at least this thick is a storey modelled as a solid, and its
#: thickness is the top level's floor-to-floor.
STOREY_THICK_M = 1.0


# -- the efficiencies ------------------------------------------------------------------


@dataclass(frozen=True)
class Efficiencies:
    """*Building Efficiencies* on the office's sheet: BEA to GFA and GFA to
    NLA, one of each per use."""

    gfa_residential: float = 0.725
    gfa_commercial: float = 0.85
    gfa_retail: float = 0.95
    nla_residential: float = 0.85
    nla_commercial: float = 0.90
    nla_retail: float = 0.90

    def __post_init__(self) -> None:
        for label, value in (
            ("BEA to GFA (Residential)", self.gfa_residential),
            ("BEA to GFA (Commercial)", self.gfa_commercial),
            ("BEA to GFA (Retail)", self.gfa_retail),
            ("GFA to NLA (Residential)", self.nla_residential),
            ("GFA to NLA (Commercial)", self.nla_commercial),
            ("GFA to NLA (Retail)", self.nla_retail),
        ):
            if not (0.0 < value <= 1.0) or math.isnan(value):
                raise ValueError(
                    f"The {label} efficiency has to be more than 0 and at most 1, not "
                    f"{value:g}: it is the share of one area that the next one is."
                )

    def gfa(self, use: str) -> float:
        """BEA to GFA, for this use."""
        return {
            RESIDENTIAL: self.gfa_residential,
            COMMERCIAL: self.gfa_commercial,
            RETAIL: self.gfa_retail,
        }[use]

    def nla(self, use: str) -> float:
        """GFA to NLA, for this use."""
        return {
            RESIDENTIAL: self.nla_residential,
            COMMERCIAL: self.nla_commercial,
            RETAIL: self.nla_retail,
        }[use]


# -- the unit mix --------------------------------------------------------------------


@dataclass(frozen=True)
class UnitType:
    """One kind of apartment in the mix: its name, its share of the units,
    and its size in net lettable area."""

    name: str
    share: float
    """A fraction: 0.7 is seventy per cent."""
    size_m2: float


#: The sheet's market mix: five types, two of them at nothing, an average
#: NLA of 72.5 m². Settings, not rules.
DEFAULT_MIX: tuple[UnitType, ...] = (
    UnitType("Studio", 0.0, 35.0),
    UnitType("1-bed", 0.20, 50.0),
    UnitType("2-bed", 0.70, 75.0),
    UnitType("3-bed", 0.10, 100.0),
    UnitType("4-bed", 0.0, 120.0),
)

#: The sheet's affordable mix: the same shares, the three-bedroom smaller.
AFFORDABLE_MIX: tuple[UnitType, ...] = (
    UnitType("Studio", 0.0, 35.0),
    UnitType("1-bed", 0.20, 50.0),
    UnitType("2-bed", 0.70, 75.0),
    UnitType("3-bed", 0.10, 95.0),
    UnitType("4-bed", 0.0, 120.0),
)

_NUMBER = r"\d+(?:\.\d+)?"
_UNIT = re.compile(
    rf"^\s*(?P<name>[^=]+?)\s*=\s*(?P<share>{_NUMBER})\s*%?\s*[,;]\s*"
    rf"(?P<size>{_NUMBER})\s*(?:m2|m²|sqm)?\s*$",
    re.IGNORECASE,
)
_RATES = re.compile(
    rf"^\s*(?P<name>[^=]+?)\s*=\s*(?P<sepp>{_NUMBER})\s*[,;]\s*(?P<dcp>{_NUMBER})\s*$"
)


def parse_unit(text: str) -> UnitType:
    """``2-bed=70,75`` -- the name, its share in per cent and its size in
    square metres -- as a unit type. Raises ``ValueError`` with a sentence."""
    found = _UNIT.match(text)
    if found is None:
        raise ValueError(
            f"{text!r} is not a unit type. Write it as the name, its share of the "
            "units in per cent and its size in m², like '2-bed=70,75'."
        )
    return UnitType(
        " ".join(found["name"].split()), float(found["share"]) / 100.0, float(found["size"])
    )


def unit_text(unit: UnitType) -> str:
    """The unit type as ``parse_unit`` reads it: the command line's spelling."""
    return f"{unit.name}={unit.share * 100:g},{unit.size_m2:g}"


def checked_mix(mix: Iterable[UnitType]) -> tuple[UnitType, ...]:
    """The mix as given, every type kept -- the sheet shows a type at nothing
    on its own row -- or a ``ValueError`` that says what is wrong with it.

    The shares have to come to a hundred per cent: a mix that comes to
    ninety would quietly leave a tenth of the building out of the yield.
    """
    kept: list[UnitType] = []
    seen: set[str] = set()
    for unit in mix:
        if unit.share < 0 or math.isnan(unit.share):
            raise ValueError(f"{unit.name} has a share below nothing.")
        if unit.share > 0 and not unit.size_m2 > 0:
            raise ValueError(f"{unit.name} has no size; it needs its typical area in m².")
        key = unit.name.casefold()
        if key in seen:
            raise ValueError(f"{unit.name} is in the mix twice.")
        seen.add(key)
        kept.append(unit)
    if not any(unit.share > 0 for unit in kept):
        raise ValueError("The mix has no unit types in it with a share.")
    total = sum(unit.share for unit in kept)
    if abs(total - 1.0) > SHARE_SLACK:
        raise ValueError(
            f"The mix's shares come to {total * 100:g}% and have to come to 100%: "
            + ", ".join(f"{unit.name} {unit.share * 100:g}%" for unit in kept if unit.share)
            + "."
        )
    return tuple(kept)


@dataclass(frozen=True)
class Mix:
    """A unit mix and what the sheet adds to its average: *Common areas per
    unit* and *Unit size tolerance*, in m² of NLA each."""

    types: tuple[UnitType, ...] = DEFAULT_MIX
    common_m2: float = 0.0
    tolerance_m2: float = 0.0

    @property
    def average_nla_m2(self) -> float:
        """The sheet's *Average NLA*: the sizes by their shares, plus the two
        allowances."""
        return (
            sum(unit.share * unit.size_m2 for unit in self.types)
            + self.common_m2
            + self.tolerance_m2
        )

    def average_gfa_m2(self, efficiencies: Efficiencies) -> float:
        """The sheet's *Average GFA*: the average NLA over the residential GFA
        to NLA. What one unit costs in GFA."""
        return self.average_nla_m2 / efficiencies.nla_residential


# -- parking -----------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitRates:
    """Spaces per unit (or per m² of GFA), under the SEPP and under the DCP."""

    sepp: float
    dcp: float


#: The sheet's rates per unit type, market and affordable, by the type's name.
_MARKET_RATES: Mapping[str, UnitRates] = {
    "studio": UnitRates(0.5, 0.5),
    "1-bed": UnitRates(0.5, 0.5),
    "2-bed": UnitRates(1.0, 1.0),
    "3-bed": UnitRates(1.5, 1.0),
    "4-bed": UnitRates(1.5, 1.0),
}
_AFFORDABLE_RATES: Mapping[str, UnitRates] = {
    "studio": UnitRates(0.0, 0.5),
    "1-bed": UnitRates(0.4, 0.5),
    "2-bed": UnitRates(0.5, 1.0),
    "3-bed": UnitRates(1.5, 1.0),
    "4-bed": UnitRates(1.5, 1.0),
}


def _rate_key(name: str) -> str:
    """``1 Bedroom``, ``1 bed``, ``1B`` and ``1-bed`` are one rate."""
    tidy = " ".join(name.split()).casefold()
    bedrooms = re.match(r"^(\d+)\s*-?\s*(?:b|bed|bedroom|bedrooms)$", tidy)
    if bedrooms:
        return f"{bedrooms.group(1)}-bed"
    return tidy


def default_rates(mix: Sequence[UnitType], *, affordable: bool = False) -> tuple[UnitRates, ...]:
    """The sheet's parking rate for each type in this mix; a type the sheet
    does not know takes a space a unit under both."""
    table = _AFFORDABLE_RATES if affordable else _MARKET_RATES
    return tuple(table.get(_rate_key(unit.name), UnitRates(1.0, 1.0)) for unit in mix)


def parse_rates(text: str) -> tuple[str, UnitRates]:
    """``2-bed=1,1`` -- a unit type's spaces per unit under the SEPP and the
    DCP -- as its name and rates."""
    found = _RATES.match(text)
    if found is None:
        raise ValueError(
            f"{text!r} is not a parking rate. Write it as the unit type, its spaces per "
            "unit under the SEPP and under the DCP, like '2-bed=1,1'."
        )
    return " ".join(found["name"].split()), UnitRates(float(found["sepp"]), float(found["dcp"]))


@dataclass(frozen=True)
class ParkingRates:
    """*Parking Requirements* and *Parking Efficiencies* on the sheet."""

    market: tuple[UnitRates, ...] = default_rates(DEFAULT_MIX)
    """One per type of the market mix, in its order."""
    affordable: tuple[UnitRates, ...] = default_rates(AFFORDABLE_MIX, affordable=True)
    """One per type of the affordable mix, in its order."""
    visitors: UnitRates = UnitRates(0.1, 0.0)
    """Spaces per unit, over every unit."""
    commercial: UnitRates = UnitRates(1 / 100, 1 / 400)
    """Spaces per m² of commercial GFA."""
    retail: UnitRates = UnitRates(1 / 30, 1 / 400)
    """Spaces per m² of retail GFA."""
    sqm_per_space: float = 40.0
    basement_site_ratio: float = 0.4
    """The share of the site a basement level may take."""

    def __post_init__(self) -> None:
        if not self.sqm_per_space > 0:
            raise ValueError(
                f"The m² per parking space has to be more than nothing, not {self.sqm_per_space:g}."
            )
        if not (0.0 < self.basement_site_ratio <= 1.0):
            raise ValueError(
                "The basement site ratio is the share of the site a basement may take, "
                f"more than 0 and at most 1, not {self.basement_site_ratio:g}."
            )

    def for_mixes(
        self,
        mix: Sequence[UnitType],
        affordable_mix: Sequence[UnitType],
        market: Mapping[str, UnitRates] | None = None,
        affordable: Mapping[str, UnitRates] | None = None,
    ) -> ParkingRates:
        """The rates for these mixes: the sheet's for each type unless one is
        named here. A name that is in neither mix is refused."""
        market_by = {_rate_key(name): rate for name, rate in (market or {}).items()}
        affordable_by = {_rate_key(name): rate for name, rate in (affordable or {}).items()}
        for given, types, what in (
            (market_by, mix, "market"),
            (affordable_by, affordable_mix, "affordable"),
        ):
            known = {_rate_key(unit.name) for unit in types}
            for key in given:
                if key not in known:
                    raise ValueError(
                        f"A parking rate is given for {key!r}, which is not in the {what} mix "
                        f"({', '.join(unit.name for unit in types)})."
                    )
        return replace(
            self,
            market=tuple(
                market_by.get(_rate_key(unit.name), rate)
                for unit, rate in zip(mix, default_rates(mix), strict=True)
            ),
            affordable=tuple(
                affordable_by.get(_rate_key(unit.name), rate)
                for unit, rate in zip(
                    affordable_mix, default_rates(affordable_mix, affordable=True), strict=True
                )
            ),
        )


# -- the floors and their levels ----------------------------------------------------------


@dataclass(frozen=True)
class Floor:
    """One slab's worth of floor: what it is, how big, and where its
    underside is."""

    use: Use
    area_m2: float
    bottom_m: float = 0.0
    """The elevation of the slab's underside, in project metres."""
    thickness_m: float = 0.0
    storey: str = ""
    """The slab's home storey, only said."""


@dataclass(frozen=True)
class Level:
    """One row of the sheet's storey table: a level and its BEA by use."""

    index: int
    """Floors above the ground: 0 is the ground floor, -1 the first basement."""
    bottom_m: float
    floor_to_floor_m: float
    residential_m2: float = 0.0
    commercial_m2: float = 0.0
    retail_m2: float = 0.0

    @property
    def name(self) -> str:
        return level_name(self.index)

    def bea(self, use: str) -> float:
        return {
            RESIDENTIAL: self.residential_m2,
            COMMERCIAL: self.commercial_m2,
            RETAIL: self.retail_m2,
        }[use]

    @property
    def total_m2(self) -> float:
        return self.residential_m2 + self.commercial_m2 + self.retail_m2


def level_name(index: int) -> str:
    """How the sheet names a level: *Ground Floor*, *Level 01*, *B 01*."""
    if index == 0:
        return "Ground Floor"
    return f"Level {index:02d}" if index > 0 else f"B {-index:02d}"


_GROUND_WORDS = {"ground", "gf", "g", "0", "00", "level 0", "level 00", "l0", "l00"}


def parse_level(text: str) -> int:
    """A level as somebody types it -- ``Ground``, ``Level 01``, ``L2``,
    ``3``, ``B 01``, ``-1`` -- as floors above the ground."""
    tidy = " ".join(text.split()).casefold().removesuffix(" floor")
    if tidy in _GROUND_WORDS:
        return 0
    above = re.match(r"^(?:level|lvl|l)?\s*\+?(\d+)$", tidy)
    if above:
        return int(above.group(1))
    below = re.match(r"^(?:b|basement|-)\s*(\d+)$", tidy)
    if below:
        return -int(below.group(1))
    raise ValueError(
        f"{text!r} is not a level. Write the ground as 'Ground', a floor above it by its "
        "number ('Level 01', '3'), and a basement as 'B 01'."
    )


def level_index(bottoms_m: Sequence[float], ground_m: float | None = None) -> list[int]:
    """Each floor's level, by its underside: floors within ``TOGETHER_M`` of
    one another are one level, numbered from the one nearest the ground
    storey -- or the lowest, when no ground is known."""
    if not bottoms_m:
        return []
    order = sorted(range(len(bottoms_m)), key=lambda i: bottoms_m[i])
    cluster = [0] * len(bottoms_m)
    starts: list[float] = []
    for i in order:
        if not starts or bottoms_m[i] - starts[-1] > TOGETHER_M:
            starts.append(bottoms_m[i])
        cluster[i] = len(starts) - 1
    ground = 0
    if ground_m is not None:
        ground = min(range(len(starts)), key=lambda k: (abs(starts[k] - ground_m), k))
    return [k - ground for k in cluster]


def levels_from(floors: Sequence[Floor], ground_m: float | None = None) -> tuple[Level, ...]:
    """The floors gathered into levels, lowest first, their BEA by use."""
    indices = level_index([floor.bottom_m for floor in floors], ground_m)
    gathered: dict[int, list[Floor]] = {}
    for floor, index in zip(floors, indices, strict=True):
        gathered.setdefault(index, []).append(floor)
    ordered = sorted(gathered)
    levels: list[Level] = []
    for place, index in enumerate(ordered):
        members = gathered[index]
        bottom = min(floor.bottom_m for floor in members)
        if place + 1 < len(ordered):
            rise = min(floor.bottom_m for floor in gathered[ordered[place + 1]]) - bottom
        else:
            thickest = max(floor.thickness_m for floor in members)
            below = levels[-1].floor_to_floor_m if levels else 0.0
            rise = thickest if thickest >= STOREY_THICK_M else below
        by_use = dict.fromkeys(USES, 0.0)
        for floor in members:
            by_use[floor.use] += floor.area_m2
        levels.append(
            Level(index, bottom, rise, by_use[RESIDENTIAL], by_use[COMMERCIAL], by_use[RETAIL])
        )
    return tuple(levels)


# -- the sheet ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Permissible:
    """The permissible FSR, split by use as the sheet has it. A use left
    ``None`` has no control written against it."""

    residential: float | None = None
    commercial: float | None = None
    retail: float | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("residential", self.residential),
            ("commercial", self.commercial),
            ("retail", self.retail),
        ):
            if value is not None and (value < 0 or math.isnan(value)):
                raise ValueError(
                    f"The permissible {label} FSR cannot be below nothing ({value:g})."
                )

    def fsr(self, use: str) -> float | None:
        return {RESIDENTIAL: self.residential, COMMERCIAL: self.commercial, RETAIL: self.retail}[
            use
        ]

    @property
    def total(self) -> float | None:
        given = [
            value for value in (self.residential, self.commercial, self.retail) if value is not None
        ]
        return sum(given) if given else None

    @property
    def any(self) -> bool:
        return self.total is not None


@dataclass(frozen=True)
class Feasibility:
    """One option's sheet: its inputs, and every figure worked from them."""

    option: str
    levels: tuple[Level, ...]
    site_area_m2: float | None = None
    permissible: Permissible = field(default_factory=Permissible)
    efficiencies: Efficiencies = field(default_factory=Efficiencies)
    market: Mix = field(default_factory=Mix)
    affordable: Mix = field(default_factory=lambda: Mix(AFFORDABLE_MIX))
    affordable_share: float = 0.0
    """The share of the residential GFA that is affordable housing; the
    rest is market."""
    parking: ParkingRates = field(default_factory=ParkingRates)
    source: tuple[str, ...] = ()
    """Where the BEA came from, for the notes."""

    @property
    def market_share(self) -> float:
        return 1.0 - self.affordable_share

    # -- areas --

    def bea(self, use: str) -> float:
        return sum(level.bea(use) for level in self.levels)

    def gfa(self, use: str) -> float:
        return self.bea(use) * self.efficiencies.gfa(use)

    def nla(self, use: str) -> float:
        return self.gfa(use) * self.efficiencies.nla(use)

    @property
    def total_bea_m2(self) -> float:
        return sum(self.bea(use) for use in USES)

    @property
    def total_gfa_m2(self) -> float:
        return sum(self.gfa(use) for use in USES)

    @property
    def total_nla_m2(self) -> float:
        return sum(self.nla(use) for use in USES)

    # -- against the control --

    def fsr(self, use: str) -> float | None:
        """This use's GFA over the site, or ``None`` with no site area."""
        return self.gfa(use) / self.site_area_m2 if self.site_area_m2 else None

    @property
    def total_fsr(self) -> float | None:
        return self.total_gfa_m2 / self.site_area_m2 if self.site_area_m2 else None

    def permissible_gfa(self, use: str) -> float | None:
        """The GFA this use's permissible FSR allows on the site."""
        control = self.permissible.fsr(use)
        if control is None or not self.site_area_m2:
            return None
        return control * self.site_area_m2

    @property
    def total_permissible_gfa_m2(self) -> float | None:
        if not self.permissible.any or not self.site_area_m2:
            return None
        return sum(self.permissible_gfa(use) or 0.0 for use in USES)

    # -- units --

    def units(self, gfa_m2: float, mix: Mix, share: float) -> tuple[float, ...]:
        """Units of each type in this residential GFA: the GFA over the mix's
        average GFA, by the type's share of the mix and this mix's share of
        the GFA. Not rounded; the sheet's figure."""
        average = mix.average_gfa_m2(self.efficiencies)
        if not average > 0:
            return tuple(0.0 for _ in mix.types)
        return tuple(gfa_m2 / average * unit.share * share for unit in mix.types)

    @property
    def market_units(self) -> tuple[float, ...]:
        """At the proposed residential GFA."""
        return self.units(self.gfa(RESIDENTIAL), self.market, self.market_share)

    @property
    def affordable_units(self) -> tuple[float, ...]:
        return self.units(self.gfa(RESIDENTIAL), self.affordable, self.affordable_share)

    @property
    def permissible_market_units(self) -> tuple[float, ...] | None:
        allowed = self.permissible_gfa(RESIDENTIAL)
        if allowed is None:
            return None
        return self.units(allowed, self.market, self.market_share)

    @property
    def permissible_affordable_units(self) -> tuple[float, ...] | None:
        allowed = self.permissible_gfa(RESIDENTIAL)
        if allowed is None:
            return None
        return self.units(allowed, self.affordable, self.affordable_share)

    @property
    def total_units(self) -> float:
        return sum(self.market_units) + sum(self.affordable_units)

    @property
    def total_permissible_units(self) -> float | None:
        market, affordable = self.permissible_market_units, self.permissible_affordable_units
        if market is None or affordable is None:
            return None
        return sum(market) + sum(affordable)

    # -- storeys --

    @property
    def residential_storeys(self) -> int:
        """Levels with residential floor on them."""
        return sum(1 for level in self.levels if level.residential_m2 > 0)

    @property
    def podium_storeys(self) -> int:
        """Levels with floor on them and none of it residential."""
        return sum(
            1 for level in self.levels if level.total_m2 > 0 and not level.residential_m2 > 0
        )

    # -- parking --

    def parking_spaces(self, column: Literal["sepp", "dcp"]) -> dict[str, float]:
        """The sheet's parking rows for one column: each market and
        affordable type, the visitors, the commercial and the retail, and
        the totals."""

        def rate(rates: UnitRates) -> float:
            return rates.sepp if column == "sepp" else rates.dcp

        out: dict[str, float] = {}
        residential = 0.0
        for unit, count, rates in zip(
            self.market.types, self.market_units, self.parking.market, strict=True
        ):
            out[f"market {unit.name}"] = count * rate(rates)
            residential += out[f"market {unit.name}"]
        for unit, count, rates in zip(
            self.affordable.types, self.affordable_units, self.parking.affordable, strict=True
        ):
            out[f"affordable {unit.name}"] = count * rate(rates)
            residential += out[f"affordable {unit.name}"]
        out["visitors"] = self.total_units * rate(self.parking.visitors)
        residential += out["visitors"]
        out["residential"] = residential
        out["commercial"] = self.gfa(COMMERCIAL) * rate(self.parking.commercial)
        out["retail"] = self.gfa(RETAIL) * rate(self.parking.retail)
        out["total"] = residential + out["commercial"] + out["retail"]
        return out

    def basements(self, column: Literal["sepp", "dcp"]) -> float | None:
        """Basement levels the parking takes, at so many m² a space over the
        share of the site a basement may cover."""
        if not self.site_area_m2:
            return None
        spaces = self.parking_spaces(column)["total"]
        return (
            spaces
            * self.parking.sqm_per_space
            / (self.site_area_m2 * self.parking.basement_site_ratio)
        )


def feasibility(
    floors: Iterable[Floor],
    *,
    option: str = "Option 01",
    site_area_m2: float | None = None,
    permissible: Permissible | None = None,
    efficiencies: Efficiencies | None = None,
    market: Mix | None = None,
    affordable: Mix | None = None,
    affordable_share: float = 0.0,
    parking: ParkingRates | None = None,
    ground_m: float | None = None,
    source: Sequence[str] = (),
) -> Feasibility:
    """The sheet for these floors.

    Raises ``ValueError`` for a mix that does not come to a hundred per
    cent, a site with no area, or a share outside nothing to one -- each a
    setting somebody typed, so each is said rather than worked around.
    """
    market = market or Mix()
    affordable = affordable or Mix(AFFORDABLE_MIX)
    market = replace(market, types=checked_mix(market.types))
    affordable = replace(affordable, types=checked_mix(affordable.types))
    if site_area_m2 is not None and not site_area_m2 > 0:
        raise ValueError(f"The site area has to be more than nothing, not {site_area_m2:g} m².")
    if not (0.0 <= affordable_share <= 1.0) or math.isnan(affordable_share):
        raise ValueError(
            "The affordable share is the part of the residential GFA that is affordable "
            f"housing, from 0 to 1, not {affordable_share:g}."
        )
    rates = parking or ParkingRates()
    if len(rates.market) != len(market.types) or len(rates.affordable) != len(affordable.types):
        rates = rates.for_mixes(market.types, affordable.types)
    return Feasibility(
        option=" ".join(option.split()) or "Option 01",
        levels=levels_from(list(floors), ground_m),
        site_area_m2=site_area_m2,
        permissible=permissible or Permissible(),
        efficiencies=efficiencies or Efficiencies(),
        market=market,
        affordable=affordable,
        affordable_share=affordable_share,
        parking=rates,
        source=tuple(source),
    )
