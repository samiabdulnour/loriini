"""Themes: how the context and site sheets look, as data.

Everything about how a sheet *looks* -- the land-use palette, the inks, the
line styles, which marks stand for the sun and the winds -- lives here, so a
new house style is a data change and not a hunt through the drawing code.
What a sheet *says* (which data, which labels, the sheet's geometry) is
deliberately not part of a theme.

Ported from the office's ``au-site-analysis`` generator (``src/render/
template.ts``), colour for colour: its four graphic templates for the
context sheet -- Flamingo, Kingfisher, Heron, Canary -- and its four site
themes of the same names -- site-analyst.com's four, and only those (D152).
The office's own legend the sheets were drawn in before the themes was a
fifth, FUSE, until then; the fields' defaults below are still its values,
and every theme sets what it draws differently.

The generator prints to a PDF, where a tint has an opacity and a texture is a
pattern. Archicad has neither on a fill, so each is realised as what Archicad
does have: a tint on paper is the colour laid over white before it is sent
(``Category.on_paper``), a tint over the aerial is the project's percentage
fill in the colour (D82), and a texture is a hatch of the drawing's own lines
in the texture's ink, dotted or crossed where the texture is.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from sun_study.site import curate

__all__ = [
    "DEFAULT_SITE_THEME",
    "DEFAULT_THEME",
    "LEP_ZONE_FILL",
    "SITE_ANALYST",
    "SITE_THEMES",
    "THEMES",
    "Category",
    "SiteLook",
    "SiteTheme",
    "Theme",
    "blend",
    "is_site_theme",
    "is_theme",
    "rgb_hex",
    "site_theme",
    "site_theme_ids",
    "theme",
    "theme_ids",
    "zone_fill",
]

Texture = Literal["dots", "lines", "cross"]

#: Where the four styles are from, and named: the window links to it beside
#: the style rows and the info box credits it (D152).
SITE_ANALYST = "https://site-analyst.com"


@dataclass(frozen=True)
class Category:
    """One row of the land-use legend, as the theme prints it."""

    id: str
    label: str
    fill: str
    """``#rrggbb``: the tint's own colour, before any opacity."""
    opacity: float = 1.0
    """How strongly the tint is laid over what is under it."""
    stroke: str | None = None
    """Outline colour, for the categories a legend outlines."""
    texture: Texture | None = None
    """A hatch laid over the fill, so one hue can carry several categories."""
    texture_colour: str | None = None
    """The hatch's ink; the stroke, then the fill, where unset."""
    figure: str | None = None
    """The building footprints' ink on this ground."""

    def on_paper(self) -> str:
        """The colour a reader sees: the tint at its opacity over white."""
        return blend(self.fill, "#ffffff", self.opacity)

    @property
    def hatch_colour(self) -> str:
        return self.texture_colour or self.stroke or self.fill


def rgb_hex(r: float, g: float, b: float) -> str:
    """Channels in 0..1 to ``#rrggbb``."""
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in (r, g, b))


def blend(colour: str, over: str, opacity: float) -> str:
    """``colour`` laid over ``over`` at ``opacity``, as a printer would mix them."""
    a = max(0.0, min(1.0, opacity))
    top, under = curate.rgb(colour), curate.rgb(over)
    return rgb_hex(*(t * a + u * (1.0 - a) for t, u in zip(top, under, strict=True)))


@dataclass(frozen=True)
class Theme:
    """The context sheet's appearance: inks, line styles and the land-use palette."""

    id: str
    label: str
    note: str
    """One line, for a picker."""

    text_scale: float = 1.0
    """Multiplies every text height, so a theme can run larger or tighter."""

    ink: str = "#111111"
    """Primary text and line colour."""
    street_ink: str = "#111111"
    """Street names, and the stop labels: quieter than the ink."""
    rule: str = "#8a8a8a"
    site: str = "#e30613"
    dimension: str = "#2456c4"
    wind: str = "#2f9fd6"
    sun: str = "#feefab"
    road: str = "#8a8a8a"
    water: str = "#bcdcf0"
    transit: str = "#2f7fd6"
    """Bus routes and stop roundels."""
    tram: str = "#d5006d"
    rail: str = "#3b3b3b"
    walk5: str = "#e6007e"
    walk10: str = "#b5379b"
    bus_route: str = "#2f7fd6"
    heritage: str = "#a97b3f"
    cadastre: str = "#6f6f6f"

    isochrone: Literal["dashed", "line", "dotted", "walkers", "labelled"] = "dashed"
    """The walking catchments: a dashed line, a plain line, a dotted line
    with its time along it, a line with walker discs on it, or a line with
    its time and distance written along it."""
    roundel: Literal["ring", "solid"] = "ring"
    """The stop and station roundels: a white disc with a coloured ring and
    letter, or a solid disc with a white letter."""
    bus_line: Literal["dashed", "dotted"] = "dashed"
    rail_line: Literal["plain", "sleepers", "dotted"] = "plain"
    """The railway: a plain line in the rail colour, the dark line with white
    sleeper dashes, or a dotted line in the rail colour."""
    ground: Literal["paper", "aerial"] = "aerial"
    """What the map sits on: plain paper, or the orthophoto."""
    aerial_tone: Literal["colour", "grey"] = "colour"
    veil: float = 0.5
    """Over the aerial: how far it is washed back toward white, 0 to 1."""
    lots: Literal["faint", "white"] = "faint"
    """The cadastre: a faint hairline in the cadastre ink, or a white line."""
    lot_width_mm: float = 0.13
    streets: Literal["white", "lines", "none"] = "lines"
    """The roads: white strips over the tints (the paper styles), the centre
    lines in the road ink, or nothing (the aerial shows them)."""
    street_labels: Literal["plain", "band"] = "band"
    """A through street's name plain along the road, or in the white
    double-headed arrow band (lanes stay plain either way)."""
    places: Literal["numbers", "names"] = "names"
    """The institutions, parks and stations: a numbered disc on the map with
    the names in the legend's key, as site-analyst.com draws them, or each
    name written on the map, as the office's sheets first had it."""
    disc_ink: str = "#1c1c1c"
    """The institutions' number discs."""
    disc_park_ink: str = "#1c1c1c"
    """The parks' number discs, where they differ from the institutions'."""
    zoning: Literal["categories", "lep"] = "categories"
    """The zoning: the theme's land-use categories, or each zone in its own
    NSW ePlanning colour, keyed by zone code."""
    categories: tuple[Category, ...] = ()

    def category(self, identifier: str) -> Category:
        for cat in self.categories:
            if cat.id == identifier:
                return cat
        raise KeyError(identifier)

    @property
    def on_paper(self) -> bool:
        return self.ground == "paper"


# -- the palettes --------------------------------------------------------------

# Flamingo's land-use palette. Four hues, each a family: peach for the
# residential zones, sand for the centres, teal for open space and the
# institutions, blue for water -- and grey for what is neither. Within a
# family the categories differ by tone and by texture, not by another colour,
# so the sheet reads as paper with a few tints on it. The site is the one
# accent.
PEACH, PEACH_INK = "#f3b8a4", "#d48b75"
PEACH_DEEP, PEACH_DEEP_INK = "#e8957c", "#b5614a"
SAND, SAND_INK = "#f1cf98", "#c49a52"
TEAL, TEAL_INK = "#5a9c89", "#3f7f6d"
PAPER = "#ffffff"
BLUE = "#b4d0dc"
NAVY = "#3b4f8a"
GREY, GREY_INK = "#d9d9d9", "#8c8c8c"
CORAL = "#e8705a"

FLAMINGO_CATEGORIES: tuple[Category, ...] = (
    Category("site", "SITE", CORAL, 0.6),
    Category("medical", "MEDICAL", TEAL, 0.65, TEAL_INK, figure=TEAL_INK),
    Category("education", "EDUCATION", TEAL, 0.55, TEAL_INK, "lines", PAPER, TEAL_INK),
    Category("childCare", "CHILD CARE / AGED CARE", TEAL, 0.25, TEAL_INK, figure=TEAL_INK),
    Category(
        "mixedUse",
        "MIXED USE CLUSTER RESIDENTIAL/COMMERCIAL",
        SAND,
        0.55,
        texture="dots",
        texture_colour=SAND_INK,
        figure=SAND_INK,
    ),
    Category(
        "retail",
        "ACTIVE RETAIL",
        SAND,
        0.4,
        texture="cross",
        texture_colour=SAND_INK,
        figure=SAND_INK,
    ),
    Category(
        "openSpace", "OPEN SPACE", TEAL, 0.55, texture="dots", texture_colour=PAPER, figure=TEAL_INK
    ),
    Category("community", "COMMUNITY HUB", TEAL, 0.5, TEAL_INK, "cross", PAPER, TEAL_INK),
    Category("r2", "R2 LOW DENSITY RESIDENTIAL", PEACH, 0.22, figure=PEACH_INK),
    Category("r3", "R3 MEDIUM DENSITY RESIDENTIAL", PEACH, 0.5, figure=PEACH_INK),
    Category(
        "r4",
        "R4 HIGH DENSITY RESIDENTIAL",
        PEACH_DEEP,
        0.65,
        texture="lines",
        texture_colour=PEACH_DEEP_INK,
        figure=PEACH_DEEP_INK,
    ),
    Category("localCentre", "LOCAL CENTRE", SAND, 0.55, figure=SAND_INK),
    Category(
        "commercial",
        "COMMERCIAL CENTRE",
        SAND,
        0.55,
        texture="lines",
        texture_colour=SAND_INK,
        figure=SAND_INK,
    ),
    Category(
        "industrial",
        "GENERAL INDUSTRIAL",
        GREY,
        0.45,
        texture="lines",
        texture_colour=GREY_INK,
        figure=GREY_INK,
    ),
    Category("infrastructure", "INFRASTRUCTURE FACILITY", GREY, 0.4, GREY_INK, figure=GREY_INK),
    Category("water", "WATERWAY", BLUE, 0.75),
    Category("railway", "RAILWAY TRACKS", GREY, 0.6, GREY_INK, figure=GREY_INK),
    Category("heritage", "GENERAL HERITAGE SITE", SAND_INK, 0.55),
)

# Heron's palette, sampled from the legend of the office sheet it follows,
# the swatch colours backed out of their opacity over white: tan mixed use
# and centres, peach residential, mint open space, the institutions in slate
# blues with dark outlines. Its red and its slate are the site sheet's too.
HERON_RED, HERON_SLATE = "#cf4a2e", "#3c4c5a"

HERON_CATEGORIES: tuple[Category, ...] = (
    Category("site", "SITE", HERON_RED, 0.5),
    Category("medical", "MEDICAL", "#ceddde", 0.55, "#4a5a63"),
    Category("education", "EDUCATION", "#b8d1d7", 0.55, "#3e5560"),
    Category("childCare", "CHILD CARE / AGED CARE", "#dfebee", 0.6, "#5f7480"),
    Category("mixedUse", "MIXED USE CLUSTER RESIDENTIAL/COMMERCIAL", "#e3c189", 0.5),
    Category("retail", "ACTIVE RETAIL", "#ecd4ac", 0.5),
    Category("openSpace", "OPEN SPACE", "#cae2cc", 0.55),
    Category("community", "COMMUNITY HUB", "#d3e6e3", 0.55, "#7f9c98"),
    Category("r2", "R2 LOW DENSITY RESIDENTIAL", "#f3ddd0", 0.5),
    Category("r3", "R3 MEDIUM DENSITY RESIDENTIAL", "#eccbb2", 0.5),
    Category("r4", "R4 HIGH DENSITY RESIDENTIAL", "#e2ae92", 0.5),
    Category("localCentre", "LOCAL CENTRE", "#e5b885", 0.5),
    Category("commercial", "COMMERCIAL CENTRE", "#daa66f", 0.5),
    Category("industrial", "GENERAL INDUSTRIAL", "#d8d0c4", 0.5),
    Category("infrastructure", "INFRASTRUCTURE FACILITY", "#eee7da", 0.55, "#8a8078"),
    Category("water", "WATERWAY", "#cbdae2", 0.6),
    Category("railway", "RAILWAY TRACKS", "#ddd6cc", 0.7, "#8a8078"),
    Category("heritage", "GENERAL HERITAGE SITE", "#c2b39a", 0.5),
)

# Kingfisher's palette, sampled from the masterplan reference it follows:
# every zone a pale ground with its buildings in the family's strong colour.
# The residential zones take the warm side -- a yellow ground with orange
# buildings for R2, pink for R3, cyan for R4, peach for mixed use -- and
# green is kept for green space alone. The centres, commercial and retail
# are the blue family, told apart by texture; the institutions lavender;
# industry grey on stone; water the bright cyan; heritage a purple.
F2_PINK, F2_PINK_GROUND = "#f8cee8", "#f9e3f1"
F2_CORAL, F2_CORAL_GROUND = "#efc0b2", "#f7e5e1"
F2_ORANGE, F2_YELLOW_GROUND = "#f2bf94", "#fbf4c9"
F2_MINT = "#8fcdb0"
F2_CYAN, F2_CYAN_GROUND = "#b3dadc", "#def5f8"
F2_BLUE, F2_BLUE_GROUND = "#7b91b0", "#e0e9f6"
F2_VIOLET, F2_VIOLET_GROUND = "#b6b2d3", "#e5e3f4"
F2_GREY, F2_STONE_GROUND = "#c2c2bc", "#e8e8d8"
F2_WATER, F2_MAGENTA, F2_PURPLE, F2_DOTS = "#81e0f9", "#c2367c", "#753583", "#1c1c1c"

KINGFISHER_CATEGORIES: tuple[Category, ...] = (
    Category("site", "SITE", F2_MAGENTA, 0.3),
    Category("medical", "MEDICAL", F2_VIOLET_GROUND, 1, F2_VIOLET, figure=F2_VIOLET),
    Category(
        "education",
        "EDUCATION",
        F2_VIOLET_GROUND,
        1,
        texture="lines",
        texture_colour=F2_VIOLET,
        figure=F2_VIOLET,
    ),
    Category(
        "childCare",
        "CHILD CARE / AGED CARE",
        F2_VIOLET_GROUND,
        1,
        texture="dots",
        texture_colour=F2_VIOLET,
        figure=F2_VIOLET,
    ),
    Category(
        "mixedUse", "MIXED USE CLUSTER RESIDENTIAL/COMMERCIAL", F2_CORAL_GROUND, 1, figure=F2_CORAL
    ),
    Category(
        "retail",
        "ACTIVE RETAIL",
        F2_BLUE_GROUND,
        1,
        texture="cross",
        texture_colour=F2_BLUE,
        figure=F2_BLUE,
    ),
    Category(
        "openSpace",
        "OPEN SPACE",
        F2_MINT,
        1,
        texture="dots",
        texture_colour=F2_DOTS,
        figure=F2_MINT,
    ),
    Category(
        "community",
        "COMMUNITY HUB",
        F2_VIOLET_GROUND,
        1,
        texture="cross",
        texture_colour=F2_VIOLET,
        figure=F2_VIOLET,
    ),
    Category("r2", "R2 LOW DENSITY RESIDENTIAL", F2_YELLOW_GROUND, 1, figure=F2_ORANGE),
    Category("r3", "R3 MEDIUM DENSITY RESIDENTIAL", F2_PINK_GROUND, 1, figure=F2_PINK),
    Category("r4", "R4 HIGH DENSITY RESIDENTIAL", F2_CYAN_GROUND, 1, figure=F2_CYAN),
    Category("localCentre", "LOCAL CENTRE", F2_BLUE_GROUND, 1, figure=F2_BLUE),
    Category(
        "commercial",
        "COMMERCIAL CENTRE",
        F2_BLUE_GROUND,
        1,
        texture="lines",
        texture_colour=F2_BLUE,
        figure=F2_BLUE,
    ),
    Category("industrial", "GENERAL INDUSTRIAL", F2_STONE_GROUND, 1, figure=F2_GREY),
    Category(
        "infrastructure", "INFRASTRUCTURE FACILITY", F2_STONE_GROUND, 0.6, F2_GREY, figure=F2_GREY
    ),
    Category("water", "WATERWAY", F2_WATER, 1),
    Category("railway", "RAILWAY TRACKS", F2_STONE_GROUND, 0.8, figure=F2_GREY),
    Category("heritage", "GENERAL HERITAGE SITE", F2_PURPLE, 0.55),
)

# The statutory map colours, so a sheet in them reads like the LEP map a
# planner already knows. Taken from the renderers the NSW ePlanning services
# publish for their own Land Zoning layer, reduced to one colour per code.
LEP_ZONE_FILL: dict[str, str] = {
    "R1": "#ffcfff", "R2": "#ffa6a3", "R3": "#ff776e", "R4": "#ff483b", "R5": "#ffd9d9",
    "B1": "#c9fff9", "B2": "#62f0f5", "B3": "#00c2ed", "B4": "#959dc2", "B5": "#7da0ab",
    "B6": "#95bfcc", "B7": "#bad6de", "B8": "#c8e6e0",
    "E1": "#99ccff", "E2": "#b4c6e7", "E3": "#8ea9db", "E4": "#9999ff", "E5": "#9966ff",
    "MU1": "#959dc2", "MU": "#959dc2",
    "IN1": "#deb8f5", "IN2": "#f3dbff", "IN3": "#c595e8", "IN4": "#ae73de",
    "SP1": "#ffffa0", "SP2": "#ffff70", "SP3": "#ffff00", "SP4": "#ffff09", "SP5": "#e6e600",
    "RE1": "#55ff00", "RE2": "#d3ffbe",
    "C1": "#e69900", "C2": "#f0ae3c", "C3": "#f7c568", "C4": "#ffda96",
    "W1": "#d9fff2", "W2": "#99ffdd", "W3": "#33ffbb", "W4": "#00e6a9",
    "RU1": "#edd8ad", "RU2": "#e6cb97", "RU3": "#dec083", "RU4": "#d6b46f", "RU5": "#d7a39e",
    "RU6": "#c79e4c",
    "DM": "#ffffff", "UL": "#ffffff", "U": "#cafced", "RW": "#d3b8f5", "DR": "#ffff70",
}  # fmt: skip
#: The ePlanning heritage item tan.
LEP_HERITAGE_ITEM = "#dbbb7b"
#: And its conservation-area red.
LEP_HERITAGE_AREA = "#ff0000"


def zone_fill(code: str | None) -> str:
    """The ePlanning fill for a zone code; a neutral grey for one it has none for."""
    c = str(code or "").strip().upper()
    return LEP_ZONE_FILL.get(c) or LEP_ZONE_FILL.get(c.split(" ")[0], "#d9d9d9")


# -- the context sheet's themes ------------------------------------------------

THEMES: tuple[Theme, ...] = (
    Theme(
        "flamingo",
        "Flamingo",
        "paper and four tints with textures; white streets, green street names",
        text_scale=0.96,
        ink="#1c1c1c",
        street_ink="#5f9a58",
        site=CORAL,
        dimension="#56616b",
        wind="#87959d",
        sun="#efe8d4",
        road=GREY_INK,
        water=BLUE,
        transit=NAVY,
        tram="#d43d33",
        rail="#d43d33",
        walk5="#1f8a5a",
        walk10="#6fb88c",
        bus_route="#7a8bb0",
        heritage=SAND_INK,
        cadastre=GREY_INK,
        isochrone="dotted",
        roundel="solid",
        bus_line="dotted",
        rail_line="dotted",
        ground="paper",
        lots="faint",
        streets="white",
        street_labels="plain",
        places="numbers",
        disc_ink=SAND_INK,
        disc_park_ink="#5f9a58",
        categories=FLAMINGO_CATEGORIES,
    ),
    Theme(
        "kingfisher",
        "Kingfisher",
        "the masterplan palette: pale zone grounds, a white cadastre, peach street names",
        text_scale=0.96,
        ink="#1c1c1c",
        street_ink="#e39a6f",
        site=F2_MAGENTA,
        dimension="#56616b",
        wind="#87959d",
        sun="#efe8d4",
        road=F2_GREY,
        water=F2_WATER,
        transit="#365696",
        tram="#e8835e",
        rail="#e8835e",
        walk5="#1f8a5a",
        walk10="#6fb88c",
        bus_route="#5b8fd6",
        heritage=F2_PURPLE,
        cadastre="#ffffff",
        isochrone="dotted",
        roundel="solid",
        bus_line="dotted",
        rail_line="dotted",
        ground="paper",
        lots="white",
        lot_width_mm=0.45,
        streets="white",
        street_labels="plain",
        places="numbers",
        disc_ink="#e39a6f",
        disc_park_ink="#8faf6a",
        categories=KINGFISHER_CATEGORIES,
    ),
    Theme(
        "heron",
        "Heron",
        "the original office sheet over a grey aerial, white lots and lettering",
        text_scale=0.96,
        ink="#1c1c1c",
        street_ink="#ffffff",
        site=HERON_RED,
        dimension=HERON_SLATE,
        wind="#6d8a99",
        sun="#f0e4c0",
        road="#7d7d7d",
        water="#cbdae2",
        transit=NAVY,
        tram="#d43d33",
        rail="#d43d33",
        walk5="#1f7a4d",
        walk10="#6aaf88",
        bus_route="#7a8bb0",
        heritage="#94836a",
        cadastre="#ffffff",
        isochrone="walkers",
        roundel="solid",
        bus_line="dashed",
        rail_line="dotted",
        ground="aerial",
        aerial_tone="grey",
        veil=0.36,
        lots="white",
        lot_width_mm=0.45,
        streets="none",
        street_labels="plain",
        places="numbers",
        disc_ink="#9c4a36",
        disc_park_ink="#1f7a4d",
        categories=HERON_CATEGORIES,
    ),
    Theme(
        "canary",
        "Canary",
        "Heron with the zoning in the NSW ePlanning colours, keyed by zone code",
        text_scale=0.96,
        ink="#1c1c1c",
        street_ink="#ffffff",
        site=HERON_RED,
        dimension=HERON_SLATE,
        wind="#6d8a99",
        sun="#f0e4c0",
        road="#7d7d7d",
        water="#cbdae2",
        transit=NAVY,
        tram="#d43d33",
        rail="#d43d33",
        walk5="#1c1c1c",
        walk10="#1c1c1c",
        bus_route="#7a8bb0",
        heritage=LEP_HERITAGE_ITEM,
        cadastre="#ffffff",
        isochrone="labelled",
        roundel="solid",
        bus_line="dashed",
        rail_line="dotted",
        ground="aerial",
        aerial_tone="grey",
        veil=0.36,
        lots="white",
        lot_width_mm=0.45,
        streets="none",
        street_labels="plain",
        zoning="lep",
        places="numbers",
        disc_ink="#1c1c1c",
        disc_park_ink="#1c1c1c",
        categories=HERON_CATEGORIES,
    ),
)

DEFAULT_THEME = "flamingo"

# Retired names still resolve, as the generator's do.
_ALIASES: dict[str, str] = {
    "flamingo-white": "flamingo",
    "flamingo-2": "kingfisher",
    "conure": "canary",
}


def theme_ids() -> tuple[str, ...]:
    return tuple(t.id for t in THEMES)


def is_theme(identifier: str | None) -> bool:
    """Whether an id names a context theme, by its own name or a former one."""
    want = (identifier or "").strip().lower()
    return want in _ALIASES or any(t.id == want for t in THEMES)


def theme(identifier: str | None) -> Theme:
    """The theme an id (or a former name) names; the default for anything unknown."""
    want = (identifier or "").strip().lower()
    want = _ALIASES.get(want, want)
    for t in THEMES:
        if t.id == want:
            return t
    return next(t for t in THEMES if t.id == DEFAULT_THEME)


# -- the site sheet's themes ------------------------------------------------------


@dataclass(frozen=True)
class SiteLook:
    """How a site theme draws what the site sheet shows: which marks, in which pens."""

    ground: Literal["aerial", "paper"] = "aerial"
    aerial: Literal["colour", "grey"] = "colour"
    """The aerial outside the site in its own colours or in greyscale; the
    site keeps its colours either way."""
    veil: float = 0.0
    """The white veil over the aerial outside the site."""
    site: str = "#e30613"
    """The site's pen: its boundary, corners and levels."""
    site_weight_mm: float = 1.0
    dimension_ink: str = "#111111"
    """The boundary dimensions' ink."""
    fall: str = "#2456c4"
    """The fall of terrain's arrow."""
    fall_ink: str = "#111111"
    """The FALL and AREA words."""
    level_ink: str = "#111111"
    """The corner levels (``RL``)."""
    text_scale: float = 1.0
    streets: Literal["lines", "none"] = "lines"
    """The roads: their centre lines in the base theme's road ink, or nothing
    (the photograph, or the white between the zoned lots, shows them)."""
    buildings: Literal["mass", "outline", "colour", "white"] = "mass"
    """The neighbours: a grey mass, a white outline over the aerial's roofs,
    filled in their zone family's strong colour with a white edge, or white
    with a heavy outline of the family's ink and a fine hatch in it."""
    building_edge_mm: float = 0.18
    neighbour_ink: str = "#111111"
    """The neighbours' number and storeys."""
    neighbour_zone: bool = True
    """Whether a neighbour's zone is written under its number."""
    zones: Literal["outline", "hatch", "lep", "fill", "none"] = "outline"
    """The zoning: its boundaries as fine lines, hatched over the aerial in
    the family colours, filled in the ePlanning colours, filled on the lots
    as the context theme's grounds, or not drawn."""
    zone_tint: float = 0.0
    """With ``hatch``: the tint laid under the hatch, 0 for the hatch alone."""
    heritage: bool = False
    heritage_ink: tuple[str, str] = ("#e39a3b", "#c8372d")
    """The LEP heritage items' and conservation areas' hatch inks."""
    contours: bool = True
    contour_ink: str = "#a07c3f"
    contour_label_ink: str | None = None
    """The contours' levels; the ink where unset."""
    street_ink: str = "#111111"
    street_labels: Literal["plain", "band"] = "band"
    lot_ink: str = "#6f6f6f"
    lot_width_mm: float | None = None
    sun: Literal["discs", "crown", "circle", "drawn", "band"] = "discs"
    """The suns: yellow discs with rays at each solstice's rise and set, an
    open jagged crown at each, four plain suns inside a climate circle with
    their names, the office's drawn sun on dashed arcs, or its small rayed
    sun at the tips of a crescent band for each solstice."""
    sun_pen: str = "#e0c860"
    sun_fill: str = "#feefab"
    sun_edge: str = "#e0c860"
    sun_ink: str = "#111111"
    sun_hours: bool = False
    wind: Literal["banners", "strands", "circle", "drawn", "band"] = "banners"
    """The winds: the office's white banners at the sheet's corners, three
    hand-drawn strands abreast, each named around the climate circle over a
    hatched quarter, the office's drawn wind on the sun ring, or its
    broken-shaft arrows on a crescent band over the quarter it blows from."""
    wind_pen: str = "#2f9fd6"
    climate_ink: str = "#111111"
    """The winds' and the suns' words."""
    tree_fill: str = "#7dbb57"
    """A tree's canopy, and its edge and trunk."""
    tree_edge: str = "#4e8c33"
    tree_trunk: str = "#2f5e20"
    tree_opacity: float = 1.0
    """How strong the canopy is: on paper the fill is blended over white at
    it; over the photograph the canopy is a wash whatever it is."""
    park_fill: str = "#9b5b6e"
    """Kerbside parking, and its ink: the bays at ``park_opacity``, the
    hatched zone at ``park_zone_opacity`` under hatch lines in the ink."""
    park_ink: str = "#7a3c50"
    park_opacity: float = 1.0
    park_zone_opacity: float = 0.18
    quiet: str = "#c2c2bc"
    """A building whose zone has no colour, or that stands on the site."""
    contour_weight_mm: float | None = None
    traffic_ink: str | None = None
    """The one-way and lane arrows; the base theme's road ink where unset."""
    rail: bool = True
    """The railway's own line on the sheet. The generator draws none on the
    site sheet: the photograph shows the track and the noise band runs beside it."""
    noise: Literal["centre", "band", "zigzag"] = "centre"
    """Noise beside the busy roads and the railway: a zigzag on the road's
    own line, as the sheets were first drawn; or, as the generator draws it,
    beside the source on the site's side -- a white band swelling gently in
    the noise pen, or the office's zigzag -- broken where it would cross the
    site or leave the sheet."""
    noise_pen: str = "#3b4fd8"
    parking: Literal["bays", "hatch"] = "bays"
    marks_fill: str = "#ffffff"
    marks_edge: str = "#ffffff"
    sun_band: tuple[str, str] = ("#f7a21b", "#ffd12e")
    """The sun's crescent, from its rising end's colour to its noon's."""
    wind_band: str = "#4aa3e8"


@dataclass(frozen=True)
class SiteTheme:
    id: str
    label: str
    note: str
    base: str
    """The context theme this draws on for what it does not set itself: the
    zones' palette and the categories' inks."""
    look: SiteLook = field(default_factory=SiteLook)


CLIMATE_GREY = "#6f7377"

#: What the generator's site sheet draws in the same colours whatever the
#: theme (``siteSheet.ts``): the trees in Flamingo's park teal at 38%, the
#: parking in its plum, the muted building, contours at 0.6 mm, no railway
#: line.
GENERATOR_SITE = {
    "tree_fill": TEAL,
    "tree_edge": TEAL_INK,
    "tree_trunk": TEAL_INK,
    "tree_opacity": 0.38,
    "park_fill": "#9b5b6e",
    "park_ink": "#7a3c50",
    "park_opacity": 0.35,
    "park_zone_opacity": 0.18,
    "quiet": "#d9d9d6",
    "contour_weight_mm": 0.6,
    "rail": False,
}

# Heron: the aerial in grey outside the site, the zones hatched and tinted in
# Heron's palette, the site, its levels and boundary dimensions in Heron's
# red, the fall in its slate; the climate drawn quietly -- the sun, its path
# and the winds in one grey, the contours a lighter one; the neighbours
# white in a fine outline. Every word a fifth larger.
HERON_LOOK = SiteLook(
    **GENERATOR_SITE,  # type: ignore[arg-type]
    ground="aerial",
    aerial="grey",
    veil=0.55,
    site=HERON_RED,
    dimension_ink=HERON_RED,
    fall=HERON_SLATE,
    fall_ink=HERON_RED,
    level_ink=HERON_RED,
    text_scale=1.2,
    streets="none",
    buildings="outline",
    building_edge_mm=0.3,
    neighbour_ink="#ffffff",
    neighbour_zone=False,
    zones="hatch",
    zone_tint=0.55,
    contours=True,
    contour_ink="#a9adb1",
    contour_label_ink="#a9adb1",
    street_ink="#ffffff",
    street_labels="plain",
    lot_ink="#ffffff",
    lot_width_mm=0.7,
    sun="crown",
    sun_pen=CLIMATE_GREY,
    sun_fill="#ffffff",
    sun_edge=CLIMATE_GREY,
    sun_ink=CLIMATE_GREY,
    sun_hours=True,
    wind="strands",
    wind_pen=CLIMATE_GREY,
    climate_ink=CLIMATE_GREY,
    traffic_ink="#ffffff",
    noise="band",
    noise_pen="#3f6fc2",
)

# Canary: the office's classic site sheet in the colours of the context
# sheet's Canary -- a grey aerial under its veil, the zones in the ePlanning
# colours, the site a dash in Canary's red with its levels, the boundary
# dimensions and the fall in its slate; each neighbour's number and storeys
# in black straight on the map; the sun, the winds and the views one black
# circle about the site.
CANARY_LOOK = SiteLook(
    **GENERATOR_SITE,  # type: ignore[arg-type]
    ground="aerial",
    aerial="grey",
    veil=0.36,
    site=HERON_RED,
    site_weight_mm=0.8,
    dimension_ink=HERON_SLATE,
    fall=HERON_SLATE,
    fall_ink=HERON_RED,
    level_ink=HERON_RED,
    text_scale=1.0,
    streets="none",
    buildings="outline",
    building_edge_mm=0.55,
    neighbour_ink="#111111",
    neighbour_zone=False,
    zones="lep",
    heritage=True,
    heritage_ink=(LEP_HERITAGE_ITEM, LEP_HERITAGE_AREA),
    contours=False,
    contour_ink="#3f9a5c",
    street_ink="#1c1c1c",
    street_labels="plain",
    lot_ink="#ffffff",
    lot_width_mm=0.7,
    sun="circle",
    sun_pen="#1c1c1c",
    sun_fill="#ffffff",
    sun_edge="#1c1c1c",
    sun_ink="#1c1c1c",
    wind="circle",
    wind_pen="#1c1c1c",
    climate_ink="#1c1c1c",
    traffic_ink="#ffffff",
    noise="zigzag",
    noise_pen=NAVY,
    parking="hatch",
)

# Kingfisher: on Kingfisher's paper, no photograph: the zones as its pale
# grounds on the lots only, every building in its family's strong colour with
# a white edge, the white cadastre, its peach street names, its magenta site.
# The climate as the office drew it for this palette: each solstice's path a
# crescent in warm yellow with the small rayed sun at each rise and set, each
# wind a blue crescent over the quarter it blows from with white arrows on it.
KINGFISHER_LOOK = SiteLook(
    **GENERATOR_SITE,  # type: ignore[arg-type]
    ground="paper",
    aerial="colour",
    veil=0.0,
    site=F2_MAGENTA,
    dimension_ink="#56616b",
    fall="#56616b",
    fall_ink="#56616b",
    level_ink=F2_MAGENTA,
    text_scale=1.0,
    streets="none",
    buildings="colour",
    building_edge_mm=0.4,
    neighbour_ink="#ffffff",
    neighbour_zone=False,
    zones="fill",
    contours=True,
    contour_ink="#a9adb1",
    contour_label_ink="#a9adb1",
    street_ink="#e39a6f",
    street_labels="plain",
    lot_ink="#ffffff",
    lot_width_mm=0.7,
    sun="band",
    sun_pen="#f2c200",
    sun_fill="#f5a800",
    sun_edge="#f5a800",
    sun_ink="#c98a00",
    wind="band",
    wind_pen="#4aa3e8",
    climate_ink="#2f86c9",
    noise="band",
    noise_pen="#3f6fc2",
    marks_fill="#ffffff",
    marks_edge="#ffffff",
    sun_band=("#f7a21b", "#ffd12e"),
    wind_band="#4aa3e8",
)

# Flamingo: the same paper and plan in Flamingo's palette, as its context
# sheet draws them: the zones as its tints and textures, every building white
# in a heavy outline of its family's ink and finely hatched in it, the
# cadastre the context sheet's fine grey, the site in its coral, the street
# names and the neighbours' numbers in its green. The climate in the office's
# drawn marks: a sun at each rise and set on the solstices' dashed arcs, the
# winds on the same ring, each a pale peach shape in a fine blue outline.
FLAMINGO_LOOK = replace(
    KINGFISHER_LOOK,
    site=CORAL,
    level_ink=CORAL,
    street_ink="#5f9a58",
    buildings="white",
    building_edge_mm=1.5,
    # The road grey at 60%, 0.3 mm: the generator's lot ink and opacity.
    lot_ink=blend(GREY_INK, PAPER, 0.6),
    lot_width_mm=0.3,
    neighbour_ink="#5f9a58",
    sun="drawn",
    sun_pen="#f5b400",
    sun_fill="#fcddd4",
    sun_edge="#5ba8e1",
    sun_ink="#d48f00",
    wind="drawn",
    wind_pen="#5ba8e1",
    climate_ink="#3d8fd1",
    marks_fill="#fcddd4",
    marks_edge="#5ba8e1",
    wind_band="#5ba8e1",
)

SITE_THEMES: tuple[SiteTheme, ...] = (
    SiteTheme(
        "heron",
        "Heron",
        "the grey aerial with the zones in Heron's palette; the site in Heron's red, "
        "the sun crowns and the winds in grey, the contours in light grey",
        "heron",
        HERON_LOOK,
    ),
    SiteTheme(
        "kingfisher",
        "Kingfisher",
        "Kingfisher on paper, no aerial: the zones as its pale grounds, the buildings in "
        "their family colour, the sun paths as yellow crescents, the winds as blue ones",
        "kingfisher",
        KINGFISHER_LOOK,
    ),
    SiteTheme(
        "flamingo",
        "Flamingo",
        "Flamingo on paper, as its context sheet: the zones as its tints and textures, "
        "the buildings white and hatched; the office's suns in amber and winds in blue",
        "flamingo",
        FLAMINGO_LOOK,
    ),
    SiteTheme(
        "canary",
        "Canary",
        "the office classic in the context Canary's colours: a grey aerial with the zones "
        "in the ePlanning colours, one black circle for the sun and the winds",
        "flamingo",
        CANARY_LOOK,
    ),
)

DEFAULT_SITE_THEME = "heron"

_SITE_ALIASES: dict[str, str] = {
    "dove": "heron",
    "cardinal": "heron",
    "kookaburra": "kingfisher",
}


def site_theme_ids() -> tuple[str, ...]:
    return tuple(t.id for t in SITE_THEMES)


def is_site_theme(identifier: str | None) -> bool:
    """Whether an id names a site theme, by its own name or a former one."""
    want = (identifier or "").strip().lower()
    return want in _SITE_ALIASES or any(t.id == want for t in SITE_THEMES)


def site_theme(identifier: str | None) -> SiteTheme:
    """The site theme an id (or a former name) names; the default for anything unknown."""
    want = (identifier or "").strip().lower()
    want = _SITE_ALIASES.get(want, want)
    for t in SITE_THEMES:
        if t.id == want:
            return t
    return next(t for t in SITE_THEMES if t.id == DEFAULT_SITE_THEME)
