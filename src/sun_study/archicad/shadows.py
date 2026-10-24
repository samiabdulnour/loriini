"""Shadow diagrams drawn into the plan, one layer to an hour.

The office's shadow diagrams were made from a 3D Document: model the scheme,
set the sun, place the document on a sheet, repeat twenty-one times. That
works and has two costs. A 3D Document cannot be created through the add-on at
all (D49), so every one of them is somebody's hand work before the tool can
touch it; and it renders *a* shadow, never the split between the shadow that
was already there and the shadow the proposal adds -- which is the only thing
a consent authority is reading the sheet for.

Drawn as fills in the plan instead, both go away. ``core.shadow`` does the
attribution arithmetic, and what arrives here is already rings: outlines where
the shadow is solid, tiled rectangles where it has a sunlit courtyard in it.
This module's whole job is putting them into Archicad and building the sheets.

One layer to an hour, and a combination to match
------------------------------------------------
Twenty-one hours of shadow on one layer would be twenty-one overlapping fills
and one unreadable plan. They could go on twenty-one worksheets instead, which
is what the communal hourly plans do -- but a worksheet carries only what this
tool draws into it, and a shadow diagram is meaningless without the
neighbourhood under it. The reference sheets show roads, boundaries and every
neighbouring building; that context is the *model*, and the only way to keep
it under each drawing is to stay on the plan.

So each hour gets a layer of its own and a Layer Combination that shows that
layer and hides its twenty siblings. A View pinned to that combination is a
drawing of the site plan with exactly one hour's shadow on it. The legend and
the site boundary go on a shared layer that every combination shows, because
they are the same at every hour and twenty-one copies of a legend is twenty-one
things to fix when the pen table changes.

Nothing here deletes a layer or a combination. Neither can be deleted through
the add-on -- ``DeleteAttributes`` refuses a ``LayerCombination`` outright
(D63) -- so both are reused by name, and a second run over the same project
redraws into the layers the first one made.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError, CommandFailedError
from sun_study.archicad.draw import (
    DRAWING_MINIMUM_TAPIR_VERSION,
    BandStyle,
    clear_layer,
    create_elements,
    ensure_layer,
    place_texts,
)
from sun_study.archicad.ids import (
    NOT_GROUPED,
    SHADOW,
    GroupReport,
    StampReport,
    fill_id,
    group_by_value,
    stamp_in_order,
)
from sun_study.archicad.layers import ensure_combination, read_layers
from sun_study.archicad.layout import (
    Filing,
    file_under_subset,
    layout_from_views,
    remove_stale_layouts,
    storey_items,
)
from sun_study.archicad.read import elements_by_ifc_ids
from sun_study.archicad.sheeting import DEFAULT_SHEET_MODE, cells_for, sheet_chunks
from sun_study.archicad.site_analysis import attribute_index
from sun_study.archicad.views import views_for_storeys
from sun_study.core.geometry import PlanTransform, rotation_about_z
from sun_study.core.patches import Ring
from sun_study.core.shadow import (
    BASELINE,
    SCENARIO,
    ShadowSeries,
    SourceSpec,
)

__all__ = [
    "ALL_HOURS_WORD",
    "BASELINE_RAMP",
    "DEFAULT_SHEETS",
    "LEGEND",
    "SCENARIO_RAMP",
    "ShadowDrawReport",
    "ShadowSheetReport",
    "all_hours_combination_name",
    "all_hours_layer_name",
    "build_shadow_sheets",
    "combination_name",
    "designed_source",
    "draw_shadow_series",
    "drawing_order",
    "layer_name",
    "legend_colour",
    "project_frame",
    "require_hatch_favourite",
    "sheet_name",
    "styles_for",
]

#: The greys a baseline is drawn in, lightest first, and the blues a scenario
#: is drawn in, palest first.
#:
#: Not a guess and not a taste. These six are sampled straight out of the
#: legend of SSDA 401 -- the Campsie SSDA sheet -- so a run reproduces the
#: sheet the office already draws by hand rather than approximating it. The
#: split is the one the sheet itself makes: what will be there is grey and
#: recedes, what is being argued about is blue and comes forward, and within
#: each ramp the later entry is the stronger one because it is the newer claim.
#:
#: Both ramps repeat if a project names more sources than there are steps.
#: Six is what the busiest reference sheet needed; a seventh would cycle back
#: to the lightest, which is visibly wrong on the sheet and is meant to be --
#: the answer then is to pass a colour, not to have the tool invent one.
BASELINE_RAMP: tuple[tuple[int, int, int], ...] = (
    (235, 235, 235),
    (216, 216, 216),
    (158, 158, 158),
)
SCENARIO_RAMP: tuple[tuple[int, int, int], ...] = (
    (207, 215, 224),
    (175, 191, 204),
    (156, 172, 191),
)

#: The ADG envelope's colour: a lilac, not a fourth blue. It is the proposal
#: with room to move -- the same building a little larger -- so it is drawn
#: just under the proposal and what shows of it is the fringe the extra room
#: would add; in a fourth blue that fringe could not be told from the
#: proposal's own edge.
ADG_ENVELOPE_RGB: tuple[int, int, int] = (192, 182, 214)

#: The office's shadow legend, row by row: the short name a run is given, the
#: words on the sheet, whether it accumulates or is compared, and its colour.
#:
#: Colours read off the marked-up legend of 21 September 2026 pixel by pixel.
#: The greys agree with the SSDA 401 ramp exactly; the blues sit a few units
#: from the ramp's first sampling and are what the sheet shows now.
#:
#: Matched by name rather than dealt out by position, so a project that has no
#: future context still draws its proposal in the proposal's blue. By
#: position, leaving a row out would have shifted every later row one colour.
LEGEND: tuple[tuple[str, str, str, tuple[int, int, int]], ...] = (
    ("EXISTING", "EXISTING NEIGHBOURING BUILDINGS", BASELINE, BASELINE_RAMP[0]),
    ("FUTURE", "FUTURE NEIGHBOURING CONTEXT BUILDINGS", BASELINE, BASELINE_RAMP[1]),
    ("EXISTING ON SITE", "EXISTING STRUCTURES WITHIN THE SITE", BASELINE, BASELINE_RAMP[2]),
    ("TOD", "CURRENT LEP 2023 BUILDING HEIGHT LIMIT", SCENARIO, SCENARIO_RAMP[0]),
    ("SEARS", "CANTERBURY BANKSTOWN LEP BUILDING HEIGHT LIMIT", SCENARIO, SCENARIO_RAMP[1]),
    ("ADG ENVELOPE", "ADG BUILDING ENVELOPE", SCENARIO, ADG_ENVELOPE_RGB),
    ("PROPOSED", "PROPOSED BUILDING ENVELOPE", SCENARIO, SCENARIO_RAMP[2]),
)


def legend_colour(label: str) -> tuple[int, int, int] | None:
    """The legend's colour for a row named either way, or ``None``."""
    wanted = " ".join(label.split()).casefold()
    for short, words, _role, rgb in LEGEND:
        if wanted in (short.casefold(), words.casefold()):
            return rgb
    return None


#: Where the shadow pens start. A pen number means whatever one project's pen
#: table says it means, so these are meant to be overridden; the colours above
#: are what lets a pen be *matched* rather than picked, and
#: ``draw.match_pens`` is what does the matching.
FIRST_SHADOW_PEN = 93


def styles_for(sources: Sequence[SourceSpec]) -> dict[str, BandStyle]:
    """A style per source, coloured by role and by position within its role.

    Derived from the source list rather than written out, because the legend
    is now the project's to declare: a sheet with six rows and a sheet with
    two are the same code path, and a table of hard-coded categories could
    only ever draw the one it was written for.
    """
    styles: dict[str, BandStyle] = {}
    seen = {BASELINE: 0, SCENARIO: 0}
    for index, source in enumerate(sources):
        ramp = BASELINE_RAMP if source.role == BASELINE else SCENARIO_RAMP
        position = seen[source.role]
        seen[source.role] += 1
        styles[source.key] = BandStyle(
            source.label.upper(),
            float("inf"),
            fill_pen=FIRST_SHADOW_PEN + index,
            rgb=legend_colour(source.label) or ramp[position % len(ramp)],
        )
    return styles


def drawing_order(sources: Sequence[SourceSpec]) -> tuple[str, ...]:
    """Back to front: every baseline, then every scenario.

    The baselines are the ground the rest is read against, so they go down
    first whatever order they were named in; the scenarios go on top in the
    order the project named them, which is the order its argument runs --
    what the controls allow, then what is being asked for.

    Scenarios genuinely do overlap (see ``core.shadow.SCENARIO``), so unlike
    the old three-fill drawing this order decides what a reader actually sees
    where two of them cover the same ground, not merely which hairline wins on
    a shared edge. Last named is on top, and that is the one being applied for.
    """
    return tuple(s.key for s in sources if s.role == BASELINE) + tuple(
        s.key for s in sources if s.role == SCENARIO
    )


#: How far a turned element may miss its Archicad counterpart before the run
#: says so. Generous, because the check is against bounding-box centres and
#: those carry their own error -- it is looking for a frame that is wrong, not
#: for a frame that is imprecise.
FRAME_CHECK_TOLERANCE_M = 5.0


#: How far the fitted rotation may sit from the one the project's own north
#: angle implies before the run says so. A north-aligned export is rotated by
#: exactly (90 degrees - the project's north bearing); the fit is done on
#: geometry instead, so the two agreeing is an independent check that the
#: right thing is being corrected for. A degree is far wider than the
#: bounding-box noise the fit carries and far narrower than any real mistake.
#: How far a turned element may miss its Archicad counterpart before the run
#: says so. Generous, because the check is against bounding-box centres and
#: those carry their own error -- it is looking for a frame that is wrong, not
#: for a frame that is imprecise.
FRAME_CHECK_TOLERANCE_M = 5.0


def project_frame(
    connection: ArchicadConnection,
    samples: Sequence[tuple[str, float, float]],
    *,
    north_radians: float,
    export_bearing_deg: float,
    archicad_guids: bool = False,
) -> tuple[PlanTransform, str]:
    """The rotation and shift taking export coordinates into the project's.

    The rotation is *derived*, not fitted. Both frames say plainly which way
    they think north is -- Archicad through its georeferencing, the export
    through ``IfcSite`` -- and the angle between those two answers is the
    angle between the frames. On Crows Nest the export reports north along its
    own +Y and the project reports +Y at a bearing of 328.4 degrees, so the
    turn is -31.6, exactly.

    It was fitted from geometry first, and that was the wrong way round. The
    pairs available are an element's plan centre against the centre of its
    *bounding box* as Archicad reports it, and a box is axis-aligned in
    whichever frame it is measured, so a long element's pair is mismatched by
    metres through no fault of the join; a GlobalId can also answer with
    several Archicad elements. Measured on this project the fit gave -33.12
    degrees over 400 pairs, +0.00 over the compact ones alone -- which were
    all on one facade and could not pin a rotation at all -- and -32.37 with
    both fixed. The true answer never moved. Two numbers Archicad states
    outright beat a regression over noisy pairs.

    The shift is still measured, because nothing states it: it is the median
    of what is left after turning, which ignores a mismatched pair instead of
    being dragged by it. Geometry then gets the last word as a *check* -- if
    the turned pairs do not land on their Archicad counterparts, something
    here is wrong and the run says so rather than drawing a plausible sheet.

    ``archicad_guids`` is for a native export, whose samples already carry
    Archicad's own guids rather than IFC GlobalIds, so there is nothing to
    look up. Its geometry is in the project's frame to begin with and both
    norths come from the same ``place.north``, so the turn comes out zero and
    the check is then a check that the identity really is the identity.
    """
    project_bearing = (270.0 + math.degrees(north_radians)) % 360.0
    turn = ((project_bearing - export_bearing_deg + 180.0) % 360.0) - 180.0
    rotation = rotation_about_z(turn)[:2, :2]

    offset = np.zeros(2, dtype=np.float64)
    residual = float("nan")
    used = 0
    if not samples:
        found: dict[str, list[str]] = {}
    elif archicad_guids:
        found = {gid: [gid] for gid, _, _ in samples}
    else:
        found = elements_by_ifc_ids(connection, [gid for gid, _, _ in samples])
    pairs = [(x, y, found[gid][0]) for gid, x, y in samples if found.get(gid)]
    if pairs:
        boxes: list[Any] = []
        for start_at in range(0, len(pairs), 500):
            chunk = pairs[start_at : start_at + 500]
            boxes.extend(
                connection.run_tapir(
                    "Get3DBoundingBoxes",
                    {"elements": [{"elementId": {"guid": g}} for _, _, g in chunk]},
                )["boundingBoxes3D"]
            )
        source: list[list[float]] = []
        target: list[list[float]] = []
        for (x, y, _), entry in zip(pairs, boxes, strict=False):
            box = entry.get("boundingBox3D") if isinstance(entry, dict) else None
            if box:
                source.append([x, y])
                target.append(
                    [(box["xMin"] + box["xMax"]) / 2.0, (box["yMin"] + box["yMax"]) / 2.0]
                )
        if source:
            turned = np.array(source) @ rotation.T
            gaps = np.array(target) - turned
            # Median per axis: a mismatched pair moves it by one place in the
            # ordering rather than by its whole error.
            offset = np.median(gaps, axis=0)
            residual = float(np.median(np.linalg.norm(gaps - offset, axis=1)))
            used = len(source)

    fitted = PlanTransform(rotation=rotation, offset=offset, rmse_m=residual)
    note = (
        f"  drawing frame: rotated {turn:+.2f} deg from the two norths "
        f"(project +Y at {project_bearing:.2f}, export at {export_bearing_deg:.2f}), "
        f"shifted {offset[0]:+.2f}, {offset[1]:+.2f} m"
    )
    if used:
        note += f", checked against {used} elements (typical miss {residual:.2f} m)"
        if residual > FRAME_CHECK_TOLERANCE_M:
            note += (
                "\n  WARNING: turned by that angle, the export's elements do not land "
                "on their Archicad counterparts. Check a fill against the model before "
                "the sheet goes anywhere."
            )
    else:
        note += ", with nothing to check it against"
    return fitted, note


def layer_name(label: str) -> str:
    """The layer one hour's shadow is drawn on.

    The hour is in the name because it is the only thing that separates the
    twenty-one, and because a colleague switching layers by hand in the Layer
    Settings dialog is reading this string and nothing else.
    """
    return naming.layer(label, naming.SHADOW_WORD)


def combination_name(label: str) -> str:
    """The Layer Combination that shows exactly that hour."""
    return naming.named(f"{naming.SHADOW_WORD} {label}")


#: What the drawing of every hour at once is called, after its day.
ALL_HOURS_WORD = "ALL HOURS"


def all_hours_layer_name(date_label: str) -> str:
    """The layer one day's every-hour outlines are drawn on."""
    return naming.layer(f"{date_label} {ALL_HOURS_WORD}", naming.SHADOW_WORD)


def all_hours_combination_name(date_label: str) -> str:
    """The combination that shows one day's every-hour drawing and no hour alone."""
    return naming.named(f"{naming.SHADOW_WORD} {date_label} {ALL_HOURS_WORD}")


def designed_source(sources: Sequence[SourceSpec]) -> str | None:
    """The source whose shadow the every-hour drawing shows.

    The legend's PROPOSED row when there is one, and otherwise the last
    scenario, which is the one being applied for (see ``drawing_order``).
    ``None`` with no scenario at all -- a sheet of baselines has no design on it.
    """
    for source in sources:
        if source.key.casefold() in ("proposed", "additional"):
            return source.key
    scenarios = [source.key for source in sources if source.role == SCENARIO]
    return scenarios[-1] if scenarios else None


def shared_layer_name() -> str:
    """Where the legend and the site boundary live.

    One layer, shown by every hour's combination. They are identical at every
    instant, and twenty-one copies of a legend is twenty-one things to correct
    when somebody changes a pen.
    """
    return naming.layer("Legend", naming.SHADOW_WORD)


@dataclass(frozen=True)
class ShadowDrawReport:
    """What was drawn, and everything a reader should be suspicious of."""

    fills: int
    sources: tuple[SourceSpec, ...]
    """The legend this run drew, in order. Needed to read ``areas_m2``."""

    layers: tuple[str, ...]
    combinations: tuple[str, ...]
    cleared: int
    below_horizon: tuple[str, ...]
    permanently_dark_share: float
    stamped: StampReport
    grouped: GroupReport
    areas_m2: dict[str, dict[str, float]]
    """Per instant label, per category. The numbers behind the colours.

    Written out because a shadow diagram is read by area -- "the proposal adds
    340 m2 at 9am" -- and a figure somebody has to measure off a drawing with
    a scale rule is a figure that will be measured wrongly.
    """
    note: str = ""
    """Said when the fills could not be drawn in the legend's own colours."""
    all_hours: tuple[str, ...] = ()
    """The combinations of the every-hour drawings, one per day, if asked for."""
    refused: tuple[str, ...] = ()
    """The fills Archicad would not draw, each said as which and how big.
    Left out of the drawing and of every total; see ``_create_legend_fills``."""

    def describe(self) -> str:
        if not self.fills and not self.combinations and self.all_hours:
            lines = [f"drew the every-hour drawing only, on {len(self.layers)} layer(s)"]
        else:
            lines = [
                f"drew {self.fills} shadow fills across {len(self.layers)} layers, "
                f"{len(self.combinations)} layer combinations"
            ]
        if self.refused:
            lines.append(
                f"  Archicad refused {len(self.refused)} fill(s), left out of the drawing -- "
                "the areas below still count them, so compare the plan with the table:"
            )
            lines.extend(f"    {refused}" for refused in self.refused[:12])
            if len(self.refused) > 12:
                lines.append(f"    and {len(self.refused) - 12} more")
        if self.cleared:
            lines.append(f"  cleared {self.cleared} fills from an earlier run")
        if self.below_horizon:
            lines.append(
                "  the sun is below the horizon at "
                + ", ".join(self.below_horizon)
                + " -- those sheets are blank, which is the honest drawing of an "
                "hour before sunrise or after sunset"
            )
        if self.permanently_dark_share > 0.5:
            lines.append(
                f"  WARNING: {self.permanently_dark_share * 100:.0f}% of the plane is "
                "shaded at every hour. That is what handing the site mesh in as "
                "context looks like -- the shadow is being cast onto a datum "
                "below the terrain. Take the terrain layer out of the context "
                "layers, or move the datum with --shadow-datum."
            )
        if self.all_hours:
            lines.append(
                f"  every hour of the design's own shadow on one drawing: "
                f"{', '.join(self.all_hours)}"
            )
        if self.note:
            lines.append(f"  {self.note}")
        if self.fills:
            lines.append(self.stamped.describe())
        if self.grouped.describe():
            lines.append(self.grouped.describe())
        for label, areas in self.areas_m2.items():
            written = ", ".join(
                f"{source.key} {areas.get(source.key, 0.0):,.0f}" for source in self.sources
            )
            lines.append(f"  {label}: {written} m2")
        return "\n".join(lines)


@dataclass(frozen=True)
class ShadowSheetReport:
    """The views and layouts built from a drawn series."""

    views: tuple[str, ...]
    sheets: tuple[str, ...]
    drawings: int
    filing: Filing | None
    removed: tuple[str, ...] = ()
    """Earlier sheets under the same stem this run did not remake."""

    def describe(self) -> str:
        lines = [
            f"made {len(self.views)} views and {len(self.sheets)} sheets "
            f"carrying {self.drawings} drawings"
        ]
        lines.extend(f"  {name}" for name in self.sheets)
        lines.extend(f"  removed {name!r}, a sheet of an earlier run" for name in self.removed)
        if self.filing is not None:
            lines.append("  " + self.filing.describe())
        return "\n".join(lines)


def require_hatch_favourite(connection: ArchicadConnection, favourite: str) -> None:
    """Stop unless the project really has a Fill Favorite by that name.

    An unknown name is not refused by ``CreateHatches`` -- it draws the hatch
    anyway, with the tool's own settings and a contour round every cell. That
    is a plan of boxes rather than a shadow, and it reads as a drawing defect
    rather than as a missing Favorite, so it is worth failing over.
    """
    known = connection.run_tapir("GetFavoritesByType", {"elementType": "Hatch"})
    names = known.get("favorites") if isinstance(known, dict) else None
    if isinstance(names, list) and favourite not in [str(name) for name in names]:
        raise ArchicadError(
            f"No Fill favorite named {favourite!r}. Make one in Archicad from a fill "
            f"with its contour switched off and the fill type you want, name it "
            f"{favourite!r}, and run this again. The project has: "
            + ", ".join(sorted(str(name) for name in names)[:12])
        )


def _fill(
    ring: Ring,
    style: BandStyle,
    layer_index: int,
    storey: int | None,
    favourite: str | None = None,
) -> dict[str, Any]:
    """One ring as a hatch on one layer.

    ``floorInd`` is sent only when there is a storey to send. A worksheet has
    none, and Tapir's own tracker records a floor index silently destroying
    elements in a database that has none -- so it is omitted rather than
    defaulted.
    """
    hatch: dict[str, Any] = {
        "coordinates": [{"x": x, "y": y} for x, y in ring],
        "layerIndex": layer_index,
        "fillPenIndex": style.fill_pen,
        # Explicitly off. A Fill inherits the Fill tool's current default, and
        # on a real project that default has "Show Area Text" on -- which
        # prints a square-metre figure across every rectangle of a tiled
        # shadow, and a shadow with a courtyard in it is tiled.
        "showArea": False,
    }
    if favourite is None:
        # ``CreateHatches`` has a contour pen and no switch to turn the
        # contour off, so the nearest reachable thing is to draw it in the
        # fill's own pen and let it disappear against it.
        hatch["contourPenIndex"] = style.outline_pen
        hatch["fillBackgroundPenIndex"] = style.background_pen
    else:
        # A Favorite's settings are applied first and the explicit fields over
        # the top, so anything named here is a setting taken *back* off it.
        # Two are therefore left alone.
        #
        # The contour, because removing it is the whole reason a Favorite is
        # wanted: ``CreateHatches`` has a contour pen and no switch to turn
        # the contour off, so hand-made is the only contour-less fill there is.
        #
        # And the background pen, which decides whether the fill is opaque.
        # A shadow diagram is read *through* -- the roads, the boundaries and
        # every neighbouring building are underneath it -- so a shadow with an
        # opaque background is a grey rectangle where the drawing should be.
        # The Favorite is where a project says which it wants.
        #
        # The fill pen is still ours, because it is what separates one legend
        # row from the next, and a Favorite has only one of those.
        hatch["favoriteName"] = favourite
    if storey is not None:
        hatch["floorInd"] = storey
    return hatch


def _as_legend_fill(
    hatch: dict[str, Any], rgb: tuple[int, int, int] | None, solid: int | None
) -> dict[str, Any]:
    """One hatch re-spelled for the add-on's ``CreateFills``, in its own colour.

    The legend is a set of colours, and a pen can only approximate one: pen
    93 means whatever one project's pen table says. ``CreateFills`` takes the
    colour itself, and takes contour pen 0, which is no contour at all -- the
    two things ``CreateHatches`` could not do, and the reason a hand-made Fill
    Favorite was ever needed.

    ``rgb`` of ``None`` is the site boundary, which is an outline and keeps
    its pen.
    """
    one: dict[str, Any] = {
        "contours": [{"points": list(hatch["coordinates"])}],
        "layerIndex": hatch["layerIndex"],
        "fillPen": hatch["fillPenIndex"],
        "showArea": False,
    }
    if "floorInd" in hatch:
        one["floorIndex"] = hatch["floorInd"]
    if rgb is None:
        one["contourPen"] = hatch.get("contourPenIndex", hatch["fillPenIndex"])
        one["backgroundPen"] = hatch.get("fillBackgroundPenIndex", 0)
        return one
    colour = {"red": rgb[0] / 255.0, "green": rgb[1] / 255.0, "blue": rgb[2] / 255.0}
    one["contourPen"] = 0
    one["foregroundColour"] = colour
    one["backgroundColour"] = colour
    if solid is not None:
        one["fillIndex"] = solid
    return one


#: Fills sent in one ``CreateFills``. The add-on draws a batch as one undo
#: step and takes all of it back if Archicad refuses any one fill.
FILL_BATCH = 500

#: How many single fills may be refused before any fill has been drawn at
#: all, or one after another at any point, before the refusals are taken to
#: be about every fill -- a layer that is not there, a Fill tool that will not
#: give its defaults, an Archicad out of memory -- and the run stops rather
#: than trying the rest one at a time.
REFUSED_BEFORE_ANY = 3
REFUSED_IN_A_ROW = 25


def _create_legend_fills(
    connection: ArchicadConnection,
    hatches: Sequence[dict[str, Any]],
    colours: Sequence[tuple[int, int, int] | None],
) -> list[dict[str, Any] | None]:
    """Every fill through the add-on, answered in Tapir's shape, one answer per
    fill asked for and ``None`` for a fill Archicad refused.

    Re-shaped because ``ids.stamp_in_order`` reads ``elementId`` and the
    add-on answers ``guid``: handed the add-on's shape it would stamp nothing
    and every schedule would total an empty drawing.

    One refusal no longer costs the run. The add-on draws each batch as one
    undo step and rolls all of it back when Archicad will not take one fill,
    which is right for an undo and was fatal for a run: on a larger model a
    single outline Archicad would not draw -- a sliver, a ring that touches
    itself -- stopped the whole diagram with nothing on the plan and nothing
    said about which fill it was (roadmap R1). So a refused batch is halved
    and each half sent again, down to the fill that is refused, which is left
    out and answered ``None``; everything else is drawn. A refusal of every
    fill, which is about the run and not about a fill, still stops it.
    """
    solid = attribute_index(connection, "Fill", ("Solid Fill", "Solid", "Foreground"))
    shaped = [
        _as_legend_fill(hatch, colour, solid)
        for hatch, colour in zip(hatches, colours, strict=True)
    ]
    answers: list[dict[str, Any] | None] = []
    refused = in_a_row = 0

    def send(start: int, stop: int) -> None:
        nonlocal refused, in_a_row
        try:
            answer = connection.run_loriini("CreateFills", {"fills": shaped[start:stop]})
        except CommandFailedError as error:
            if "not have the registered" in str(error):
                raise
            if stop - start > 1:
                middle = (start + stop) // 2
                send(start, middle)
                send(middle, stop)
                return
            refused += 1
            in_a_row += 1
            if (refused >= REFUSED_BEFORE_ANY and not any(answers)) or (
                in_a_row >= REFUSED_IN_A_ROW
            ):
                raise ArchicadError(
                    f"Archicad refuses every fill, not one in particular: {error}"
                ) from error
            answers.append(None)
            return
        in_a_row = 0
        elements = answer.get("elements") if isinstance(answer, dict) else None
        if not isinstance(elements, list):
            raise ArchicadError(f"CreateFills returned no element list: {answer!r}")
        made = [
            {"elementId": entry["elementId"]}
            if "elementId" in entry
            else {"elementId": {"guid": entry["guid"]}}
            for entry in elements
            if isinstance(entry, dict) and ("elementId" in entry or "guid" in entry)
        ]
        if len(made) != stop - start:
            raise ArchicadError(
                f"CreateFills made {len(made)} fills of {stop - start} and did not say "
                f"which, so none can be matched to what it was drawn for"
            )
        answers.extend(made)

    for start in range(0, len(shaped), FILL_BATCH):
        send(start, min(start + FILL_BATCH, len(shaped)))
    return answers


#: The fill an hour's outline is drawn in: empty, so the seven hours drawn
#: over one another all show, each as its contour. First found first used.
ALL_HOURS_FILLS: tuple[str, ...] = ("Empty Fill", "Empty", "Background")

#: The line type of that contour: continuous. Named, because a fill takes the
#: Fill tool's line type otherwise, and the polylines this replaced came out
#: in the Polyline tool's -- dense dotted on the sample project (D145).
ALL_HOURS_LINES: tuple[str, ...] = ("Solid Line", "Solid", "Continuous")


def _all_hours_elements(
    hours: Sequence[tuple[str, Sequence[Ring]]],
    layer_index: int,
    storey: int | None,
    pen: int,
    height_mm: float,
    *,
    fill_index: int | None = None,
    line_type_index: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One day's outlines as fills, in the add-on's ``CreateFills`` shape, and
    each hour's label.

    A fill per ring, its contour in ``pen`` on the continuous line type, its
    pattern ``fill_index`` -- the project's empty fill -- on a transparent
    background, so every hour's shadow shows through the others as its
    outline, and each is a fill a person can select, measure, or give a
    pattern of their own (D145). The ring goes open: the add-on closes it.

    The label sits on the vertex of that hour's outline farthest from the
    middle of all of them -- the tip of the shadow, which is where the hours
    fan apart and where a reader looks for which outline is which.
    """
    everything = [point for _label, rings in hours for ring in rings for point in ring]
    if not everything:
        return [], []
    middle = np.mean(np.asarray(everything, dtype=np.float64), axis=0)

    fills: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    for label, rings in hours:
        tip: tuple[float, float] | None = None
        reach = -1.0
        for ring in rings:
            points = list(ring)
            while len(points) > 1 and points[0] == points[-1]:
                points.pop()
            if len(points) < 3:
                continue
            fill: dict[str, Any] = {
                "contours": [{"points": [{"x": x, "y": y} for x, y in points]}],
                "layerIndex": layer_index,
                "fillPen": pen,
                "contourPen": pen,
                "backgroundPen": 0,
                "showArea": False,
            }
            if fill_index is not None:
                fill["fillIndex"] = fill_index
            if line_type_index is not None:
                fill["lineTypeIndex"] = line_type_index
            if storey is not None:
                fill["floorIndex"] = storey
            fills.append(fill)
            for x, y in points:
                far = float(np.hypot(x - middle[0], y - middle[1]))
                if far > reach:
                    reach, tip = far, (x, y)
        if tip is None:
            continue
        text: dict[str, Any] = {
            "coordinate": {"x": tip[0], "y": tip[1], "z": 0.0},
            "text": label,
            "height": height_mm,
            "justification": "Center",
        }
        if storey is not None:
            text["floorIndex"] = storey
        texts.append(text)
    return fills, texts


def _visibility(
    layers: Sequence[Any], showing: str, shared: str, mine: Sequence[str]
) -> dict[str, bool]:
    """Layer states for one hour's combination: guid -> hidden.

    Every layer of the project keeps whatever it is doing, so the site plan
    underneath still shows the neighbours, the roads and the boundary. Only
    the tool's own shadow layers are decided here: the hour being drawn on,
    every other hour off, and the shared legend on.

    Written as "leave everything else alone" rather than "show what the study
    needs" on purpose. What belongs on a site plan is the practice's decision
    and it is already recorded in whatever combination they draw site plans
    with; a combination built from scratch here would be this tool's opinion
    of somebody else's drawing.
    """
    ours = {name.casefold() for name in mine}
    states: dict[str, bool] = {}
    for layer in layers:
        name = str(layer.name).casefold()
        if name == showing.casefold() or name == shared.casefold():
            states[layer.identifier] = False
        elif name in ours:
            states[layer.identifier] = True
        else:
            states[layer.identifier] = bool(layer.hidden)
    return states


def draw_shadow_series(
    connection: ArchicadConnection,
    series: ShadowSeries,
    *,
    styles: Mapping[str, BandStyle] | None = None,
    storey_index: int | None = 0,
    boundary: Ring | None = None,
    boundary_pen: int = 1,
    transform: PlanTransform | None = None,
    favourite: str | None = None,
    all_hours: str | None = None,
    all_hours_pen: int = 1,
    label_height_mm: float = 2.5,
    only_all_hours: bool = False,
) -> ShadowDrawReport:
    """Draw every instant onto its own layer, and record a combination for each.

    ``only_all_hours`` draws the every-hour drawing and nothing else: no
    layer, fill or combination per hour. It is what the fills are for now
    that the stacked 3D Documents draw the comparison with the neighbours
    (D144): the designed building's own shadow, every hour, on one plan.

    ``all_hours`` names a source whose own shadow was outlined (see
    ``cast_shadows``); each day then also gets one layer carrying that shadow
    at every hour, each hour a fill with an empty pattern, a transparent
    background and a continuous contour, labelled with its hour at the tip,
    and a combination showing that layer alone. Empty, because fills laid
    over one another hide each other, and the point of the drawing is to see
    every hour at once (D145).

    ``storey_index`` is which storey the fills belong to; ``None`` omits the
    floor index entirely, which is what a worksheet needs and what a plan must
    not have omitted.

    ``boundary`` is the site outline, drawn once on the shared layer. It is a
    ring rather than a layer name because by the time the shadows have been
    computed the boundary is already known -- it is what the planning envelope
    was extruded from -- and reading it back out of Archicad a second time
    would be a second chance to read a different polygon.

    Every layer is cleared before it is drawn, so a rerun replaces its own work
    rather than stacking a second set of fills on the first. Nothing outside
    the tool's own layers is touched.
    """
    connection.require_tapir_at_least(
        DRAWING_MINIMUM_TAPIR_VERSION, "CreateHatches, which draws the shadow,"
    )
    if favourite:
        require_hatch_favourite(connection, favourite)
    if not series.instants:
        raise ArchicadError("No instants to draw.")

    def placed(ring: Ring) -> Ring:
        """One ring, moved from the export's frame into the project's.

        Every ring goes through here, so a run either corrects all of them or
        none. Half-corrected is the one outcome worth engineering against: the
        fills would still tile against each other and still look like a
        shadow, while sitting somewhere the model is not.
        """
        if transform is None:
            return ring
        moved = transform.apply(np.asarray(ring, dtype=np.float64))
        return tuple((float(x), float(y)) for x, y in moved)

    palette = styles_for(series.sources)
    palette.update(styles or {})
    order = drawing_order(series.sources)

    if only_all_hours and not all_hours:
        raise ArchicadError(
            "Only the every-hour drawing was asked for, and no designed building names "
            "whose shadow it shows: name a PROPOSED row or a --shadow-scenario."
        )
    hourly = [] if only_all_hours else list(series.instants)
    shared = ensure_layer(connection, shared_layer_name())
    wanted = [layer_name(instant.label) for instant in hourly]
    days = _by_date(series) if all_hours else {}
    # Looked up before anything is drawn, so a project that cannot take the
    # every-hour drawing stops here and not halfway through.
    empty = attribute_index(connection, "Fill", ALL_HOURS_FILLS) if days else None
    continuous = attribute_index(connection, "Line", ALL_HOURS_LINES) if days else None
    if days and empty is None:
        raise ArchicadError(
            f"The every-hour drawing is drawn as fills with an empty pattern, so the hours "
            f"show through one another, and the project has no fill called "
            f"{' or '.join(repr(name) for name in ALL_HOURS_FILLS)}. Add one to the "
            f"project's fill types and run again."
        )
    # Hidden in every hour's combination too, so a single hour never shows
    # the every-hour lines over it.
    wanted += [all_hours_layer_name(day) for day in days]

    fills: list[dict[str, Any]] = []
    #: One ID per fill, in the same order. The create command answers in the
    #: order it was given, and that order is the only thing linking a hatch
    #: back to the hour and the category it was drawn for.
    #: ``None`` for a fill that must never be totalled -- see the site
    #: boundary below.
    element_ids: list[str | None] = []
    #: The legend colour of each fill, in the same order; ``None`` for the
    #: boundary, which is an outline and not a legend row.
    colours: list[tuple[int, int, int] | None] = []
    cleared = 0
    made_layers: list[str] = []
    for instant in hourly:
        name = layer_name(instant.label)
        layer = ensure_layer(connection, name)
        made_layers.append(name)
        cleared += clear_layer(connection, layer.index)
        for category in order:
            style = palette.get(category)
            if style is None:
                continue
            for ring in instant.regions.get(category, ()):
                fills.append(_fill(placed(ring), style, layer.index, storey_index, favourite))
                colours.append(style.rgb)
                # The hour *and* the category, so one schedule breaks down by
                # both: how much shadow at 9am, and how much of it is ours.
                element_ids.append(fill_id(SHADOW, instant.caption, category.upper()))

    if boundary is not None:
        cleared += clear_layer(connection, shared.index)
        fills.append(
            _fill(
                placed(boundary),
                BandStyle("SITE BOUNDARY", float("inf"), fill_pen=boundary_pen, background_pen=0),
                shared.index,
                storey_index,
                favourite,
            )
        )
        # Deliberately *not* given an Element ID. A schedule that totals
        # every fill whose ID contains SHADOW would otherwise add the whole
        # site to the shadow area and report a number nobody could explain.
        # Only measured fills are tagged; the boundary is furniture.
        element_ids.append(None)
        colours.append(None)

    # Batched: twenty-one hours of a tiled shadow is thousands of hatches, and
    # one request carrying all of them is a payload Archicad parses in one go.
    #
    # Through the add-on unless a Favorite was named, so each fill is the
    # legend's own colour with no contour. A Favorite is Tapir's route, and an
    # add-on too old for CreateFills falls back to it and says so.
    made: list[dict[str, Any]] = []
    note = ""
    refused: list[str] = []
    if not favourite:
        try:
            answered = _create_legend_fills(connection, fills, colours)
        except ArchicadError as error:
            if "not have the registered" not in str(error):
                raise
            note = (
                "the installed Loriini add-on has no CreateFills, so these are pen "
                "colours with a contour, not the legend's. Install the current build."
            )
        else:
            # The refused fills leave the lists here, so every list after
            # this still pairs one element with the ID it was drawn for.
            refused = [
                _refused_fill(fills[index], element_ids[index])
                for index, answer in enumerate(answered)
                if answer is None
            ]
            element_ids = [
                element_id
                for element_id, answer in zip(element_ids, answered, strict=True)
                if answer is not None
            ]
            made = [answer for answer in answered if answer is not None]
    if fills and not made and not refused:
        for start in range(0, len(fills), 500):
            made.extend(
                create_elements(
                    connection, "CreateHatches", "hatchesData", fills[start : start + 500]
                )
            )

    # Positional pairing, and the boundary's ``None`` drops out there: see
    # ``ids.stamp_in_order`` for why a mismatch is refused rather than trimmed.
    stamped = stamp_in_order(connection, made, element_ids) if made else StampReport(0, 0)
    # One group per hour *and* category, so a colleague can pick up all of
    # 9am's additional shadow in one click without disturbing the existing
    # shadow underneath it.
    grouped = (
        group_by_value(connection, list(zip(made, element_ids, strict=True)))
        if made and len(made) == len(element_ids)
        else NOT_GROUPED
    )

    for day, instants in days.items():
        layer = ensure_layer(connection, all_hours_layer_name(day))
        cleared += clear_layer(connection, layer.index)
        outlines, texts = _all_hours_elements(
            [(i.label, [placed(r) for r in i.outlines.get(all_hours or "", ())]) for i in instants],
            layer.index,
            storey_index,
            all_hours_pen,
            label_height_mm,
            fill_index=empty,
            line_type_index=continuous,
        )
        if outlines:
            connection.run_loriini("CreateFills", {"fills": outlines})
        if texts:
            place_texts(connection, texts, layer.index)

    # After the fills, so the combinations are recorded against layers that
    # certainly exist and carry the right visibility.
    project = read_layers(connection)
    combinations: list[str] = []
    for instant in hourly:
        name = combination_name(instant.label)
        ensure_combination(
            connection,
            name,
            _visibility(project, layer_name(instant.label), shared.name, wanted),
        )
        combinations.append(name)
    every_hour: list[str] = []
    for day in days:
        name = all_hours_combination_name(day)
        ensure_combination(
            connection,
            name,
            _visibility(project, all_hours_layer_name(day), shared.name, wanted),
        )
        every_hour.append(name)

    return ShadowDrawReport(
        fills=len(made),
        sources=series.sources,
        layers=tuple(made_layers) + tuple(all_hours_layer_name(day) for day in days),
        combinations=tuple(combinations),
        cleared=cleared,
        below_horizon=tuple(i.label for i in series.instants if i.below_horizon),
        permanently_dark_share=series.permanently_dark_share,
        stamped=stamped,
        grouped=grouped,
        areas_m2={instant.label: dict(instant.areas_m2) for instant in series.instants},
        note=note,
        all_hours=tuple(every_hour),
        refused=tuple(refused),
    )


def _refused_fill(hatch: Mapping[str, Any], element_id: str | None) -> str:
    """One refused fill, as the run says it: which it was, and how big."""
    points = hatch.get("coordinates") or []
    xs = [float(point["x"]) for point in points if isinstance(point, dict) and "x" in point]
    ys = [float(point["y"]) for point in points if isinstance(point, dict) and "y" in point]
    where = (
        f" around ({(min(xs) + max(xs)) / 2:,.1f}, {(min(ys) + max(ys)) / 2:,.1f})"
        if xs and ys
        else ""
    )
    return f"{element_id or 'the site boundary'}, {len(points)} corners{where}"


def instant_captions(series: ShadowSeries) -> dict[str, str]:
    """What each hour's drawing is called on the sheet, keyed by its label.

    ``JUNE 21 -9AM``, in the reference sheets' own words including the space
    before the dash. Kept next to the drawing code rather than derived at the
    layout end so the caption on a sheet and the layer a colleague switches on
    can never disagree about which hour is which.
    """
    return {instant.label: instant.caption for instant in series.instants}


#: How a day's drawings are dealt onto sheets. Two is what the reference
#: sheets carry -- 9, 10, 11 and 12 on one, 1, 2 and 3 on the next -- and
#: it is a real constraint as much as a preference: a site plan at 1:1000 on
#: an A1 sheet is about half the page in each direction, so four fit and
#: five do not. The other modes are ``sheeting``'s.
DEFAULT_SHEETS = DEFAULT_SHEET_MODE


def _by_date(series: ShadowSeries) -> dict[str, list[Any]]:
    """Instants grouped by the day they belong to, in the order given.

    A sheet is a day: *SHADOW DIAGRAMS - JUNE 21*. Mixing 21 June and 21
    December onto one page would be four drawings that cannot be compared with
    each other, which is the only thing a reader does with them.
    """
    days: dict[str, list[Any]] = {}
    for instant in series.instants:
        days.setdefault(instant.moment.strftime("%B %d").upper(), []).append(instant)
    return days


def sheet_name(date_label: str, part: int, parts: int, labels: Sequence[str] = ()) -> str:
    """What one sheet of shadow diagrams is called.

    Numbered only when there is more than one, because *SHADOW DIAGRAMS - JUNE
    21 (1 of 1)* is a sheet number nobody wants and a title block nobody wants
    to read. A sheet of one drawing is named for its hour -- *JUNE 21 9AM* --
    because *(3 of 7)* says nothing a reader is looking for.
    """
    stem = f"{naming.SHADOW_WORD}s - {date_label}"
    if parts == 1:
        return naming.named(stem)
    if len(labels) == 1:
        return naming.named(f"{stem} {labels[0]}")
    return naming.named(f"{stem} ({part} of {parts})")


def build_shadow_sheets(
    connection: ArchicadConnection,
    series: ShadowSeries,
    *,
    storey_index: int = 0,
    drawing_scale: float = 1000.0,
    master_layout: str | None = None,
    subset: str | None = None,
    sheets: str = DEFAULT_SHEETS,
    zoom: tuple[float, float, float, float] | None = None,
    all_hours: bool = False,
    only_all_hours: bool = False,
) -> ShadowSheetReport:
    """One View per hour, then the day's Layouts as ``sheets`` says, filed.

    ``all_hours`` adds, per day, a View of that day's every-hour drawing (see
    ``draw_shadow_series``) and a sheet of its own carrying it;
    ``only_all_hours`` makes that and no view or sheet per hour.

    The View is the piece that makes this work: it is a view of the *site
    plan*, pinned to that hour's Layer Combination, so the drawing carries the
    neighbours and the roads with exactly one hour's shadow over them. That is
    the whole reason the fills went onto the plan rather than into worksheets.

    ``zoom`` pins what the drawing covers. Worth passing: a view otherwise
    inherits whatever the storey happened to be zoomed to, so a sheet made on
    a Monday crops the site wherever somebody left the screen on Friday. The
    shadow grid's own extent is the right answer and the caller has it.

    Sheets are made per day and filed under ``subset``. A subset that does not
    exist is reported rather than created -- the Layout Book is the office's
    structure to organise, not this tool's (D66).
    """
    found, missing = storey_items(connection, [storey_index])
    if missing or storey_index not in found:
        raise ArchicadError(
            f"No storey with index {storey_index} in the Project Map, so there is no "
            f"site plan to draw the shadows on. Choose the storey the site plan is "
            f"drawn at with --shadow-storey."
        )
    storey = found[storey_index]

    hourly = [] if only_all_hours else list(series.instants)
    made: list[tuple[str, str]] = []
    for instant in hourly:
        views = views_for_storeys(
            connection,
            [storey],
            combination=combination_name(instant.label),
            suffix=f"Shadow {instant.label}",
            drawing_scale=drawing_scale,
            zoom=zoom,
        )
        made.extend((view.navigator_id, instant.caption) for view in views)

    names: list[str] = []
    placed = 0
    position = 0
    for date_label, instants in (_by_date(series) if hourly else {}).items():
        chunks = sheet_chunks(len(instants), sheets)
        cells = cells_for(chunks)
        for part, (start, stop) in enumerate(chunks, start=1):
            on_this_sheet = made[position : position + (stop - start)]
            position += stop - start
            name = sheet_name(
                date_label, part, len(chunks), [i.label for i in instants[start:stop]]
            )
            report = layout_from_views(
                connection,
                on_this_sheet,
                layout_name=name,
                scale=drawing_scale,
                master_layout=master_layout,
                cells=cells,
            )
            names.append(name)
            placed += report.drawings_placed

    for date_label in _by_date(series) if (all_hours or only_all_hours) else {}:
        caption = f"{date_label} {ALL_HOURS_WORD}"
        views = views_for_storeys(
            connection,
            [storey],
            combination=all_hours_combination_name(date_label),
            suffix=f"Shadow {caption}",
            drawing_scale=drawing_scale,
            zoom=zoom,
        )
        made.extend((view.navigator_id, caption) for view in views)
        name = naming.named(f"{naming.SHADOW_WORD}s - {caption}")
        report = layout_from_views(
            connection,
            [(view.navigator_id, caption) for view in views],
            layout_name=name,
            scale=drawing_scale,
            master_layout=master_layout,
            cells=cells_for(sheet_chunks(1, sheets)),
        )
        names.append(name)
        placed += report.drawings_placed

    # The sheets an earlier run made under another mode -- ``(1 of 2)``
    # beside a new ``JUNE 21`` -- would otherwise stand looking as current.
    removed = remove_stale_layouts(connection, naming.named(f"{naming.SHADOW_WORD}s - "), names)
    filing = file_under_subset(connection, names, subset) if subset else None
    return ShadowSheetReport(
        views=tuple(name for _, name in made),
        sheets=tuple(names),
        drawings=placed,
        filing=filing,
        removed=tuple(removed),
    )
