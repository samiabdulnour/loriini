"""Shadow plans as 3D Documents: Loriini prepares, Archicad draws the shadows.

Roadmap R1. The shadow diagram Loriini draws itself -- the model exported, the
shadows cast by its own ray caster, the split between what stands and what
the proposal adds traced as fills (``archicad.shadows``) -- is the argument a
DA makes, and on a larger model it is also the part that runs out of time or
memory. This is the other route, the one the office used to take by hand
twenty-one times over: a 3D Document per hour, looking straight down, with
the sun at that hour and Archicad's own vectorial sun shadows on. Archicad
casts the shadows, at any size of model it can display, from the sun it
works out from the project's own location.

What Loriini does is everything around the shadow. One document per date and
hour, named for it; the camera overhead with north up (the add-on snaps a
straight-down view to the plan's orientation); the sun set as a date so it is
Archicad's; the shadows switched on for the document as it is made, in the
fill asked for; the storey filter taken off, as for the sun views, since a
document keeps the filter it was made under (D98); a view of each document
pinned to a layer combination, the renovation filter and the scale; and the
views dealt onto sheets by day, a cell each, the way the fills' sheets are.

What one document does not give is what the fills give. A document shows
the whole shadow of whatever its layer combination shows, at one hour: there
is no "existing" and "additional" inside it. A stack of documents gives it,
one per row of the shadow legend -- the same rows as the fills', sources that
accumulate and scenarios that are compared. Each row's document shows that
row and everything it stands on, its shadow a solid in the row's colour, and
the documents of an hour are laid in one cell of one sheet: the scenarios at
the bottom in the order named, the sources above them from the last to the
first. A drawing is seen only where everything above it casts nothing, so
what shows of each row is what it adds. Archicad draws a document's shadows
only on filled surfaces (D141), so every document fills its surfaces in
the transparent pen, and every drawing above the lowest has a transparent
background (D142); filled with the materials' colours instead, a document
draws its shadows as darker material and not in its row's pen.
``LegendRow`` is a row, ``legend_combinations`` works the layer
combinations out from the layers, ``make_shadow_plan_stack`` makes the sets
and ``make_stack_sheets`` deals them onto the combined sheets. The plain mode
remains: one set under one combination, ``set_label`` naming it, read
against another set sheet by sheet. The two routes answer different
questions, and the office may want both: the documents as the record, the
fills as the argument (docs/shadow-plans.md).

A 3D Document cannot be deleted through the API (``APIDb_DeleteDatabaseID``
takes details, worksheets and layouts), so a rerun finds its own documents by
name. It re-aims them and re-sets their sun and fill (``SetDocumentFrom3D``),
and copies the shadow switch onto them from a document this run made with
it, so a second run leaves the same documents a first run would.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from sun_study.archicad import naming
from sun_study.archicad.clock import sun_date
from sun_study.archicad.connection import ArchicadConnection, ArchicadError, CommandFailedError
from sun_study.archicad.layout import (
    LayoutReport,
    layout_sheet,
    one_title_per_pile,
    remove_stale_layouts,
    update_drawings,
)
from sun_study.archicad.plan_sheet import PlanWindow, draw_legend_and_outline
from sun_study.archicad.read import GeoLocation
from sun_study.archicad.series import database_of
from sun_study.archicad.sheeting import DEFAULT_SHEET_MODE, cells_for, sheet_chunks
from sun_study.archicad.sheets import LEGEND_COLUMN_MM
from sun_study.archicad.sun_eyes import (
    TITLE_BLOCK_MM,
    place_on_sheets,
    place_stacks_on_sheets,
    sheet_cells_for,
)
from sun_study.archicad.views import (
    ModelSource,
    StoreyView,
    _check,
    three_d_sources,
    views_for_sources,
)
from sun_study.core.shadow import BASELINE, SCENARIO
from sun_study.core.solar import solar_position

__all__ = [
    "COMBINED_LABEL",
    "EXISTING_LABEL",
    "LEGEND_TITLE",
    "OVERHEAD_DEG",
    "PLAN_SCALE",
    "PLAN_WORD",
    "PROPOSED_LABEL",
    "SET_WORD",
    "STACK_SHADOW_FILLS",
    "STACK_SURFACES",
    "LegendRow",
    "MadePlan",
    "PlanSet",
    "ShadowPlan",
    "ShadowPlanSettings",
    "Stack",
    "legend_combinations",
    "legend_from_existing_and_proposed",
    "make_shadow_plan_sheets",
    "make_shadow_plan_stack",
    "make_shadow_plans",
    "make_stack_sheets",
    "plan_sheet_groups",
    "shadow_plans",
    "stack_labels",
    "stack_order",
    "stack_sheet_groups",
]

#: What one document is called, after the prefix, and what the set is.
PLAN_WORD = "Shadow Plan"
SET_WORD = "Shadow Plans"

#: What the stacked mode calls its sets: the one that stands, and the
#: proposals -- ``Proposed`` alone, or ``Proposed 1``, ``Proposed 2`` and on
#: in the order given. The office's own names for its massings (SEARs, the
#: building envelope) change from job to job; these do not.
EXISTING_LABEL = "Existing"
PROPOSED_LABEL = "Proposed"

#: The fills a stacked set's shadows are drawn in, first found first used. A
#: stack needs the upper document's shadow to cover the lower's: a hatch lets
#: the pen beneath show between its lines, and what is then on the page is
#: neither colour.
STACK_SHADOW_FILLS: tuple[str, ...] = ("Solid Fill", "100 %", "Solid")

#: The scale the shadow diagram's sheets are drawn at: a site plan at 1:1000
#: on an A1 is about half the page each way, so four hours fit on a sheet.
PLAN_SCALE = 1000.0

#: There is no default layer combination and no default shadow fill (D156).
#: Both were one office's -- "04 | Shadow Diagrams", and the "50 %" fill read
#: off its Kogarah file -- and in another project the one is missing and the
#: other a guess. The plans are pinned to the combination the run is given,
#: and the shadows keep the project's own 3D Document fill unless a run
#: names one.


def site_context_layers() -> tuple[str, ...]:
    """The layers the site tools draw the context on: what a shadow plan
    needs showing to have a ground and neighbours at all."""
    return (
        naming.terrain_layer(),
        naming.roads_layer(),
        naming.buildings_layer(),
        naming.future_layer(),
    )


def hidden_among(
    wanted: Iterable[str], names_by_guid: Mapping[str, str], hidden_by_guid: Mapping[str, bool]
) -> list[str]:
    """Which of ``wanted`` the project has and the combination hides.

    The first live run (Redfern, 8 October 2026): the office's combination
    hid every layer the site tools had drawn the context on, so the plans
    held the proposal's slab on a blank page. A layer the project does not
    have is nobody's to show, and one already showing needs nothing.
    """
    hidden = {
        " ".join(name.split()).casefold()
        for guid, name in names_by_guid.items()
        if hidden_by_guid.get(guid, False)
    }
    return [name for name in wanted if " ".join(name.split()).casefold() in hidden]


#: Straight down. The add-on snaps anything within a hundredth of a degree of
#: it to an exact top view with the project's +Y up the page, which is how
#: every plan in the project is drawn -- so the bearing sent with it is moot.
OVERHEAD_DEG = 90.0


@dataclass(frozen=True)
class ShadowPlan:
    """One hour of one day, as a document is made for it."""

    when: dt.datetime
    """Timezone-aware local time."""

    label: str
    """``9AM``: the hour as the shadow diagram's sheets name it."""

    altitude_deg: float
    """The sun's height, from this tool's own astronomy: said beside the
    document so a shadow that looks too long can be checked against it."""

    clock_minutes: int | None = None
    """Archicad's clock -- the project location's time zone, in minutes east
    of Greenwich -- or ``None`` for an add-on that cannot report it (D135)."""

    @property
    def caption(self) -> str:
        """``JUNE 21 -9AM``, the fills' sheets' own words, under the drawing."""
        return f"{self.when.strftime('%B %d').upper()} -{self.label}"

    @property
    def stamp(self) -> str:
        """``21 Jun 09:00``: the instant in a document's name."""
        return self.when.strftime("%d %b %H:%M").lstrip("0")

    @property
    def reference(self) -> str:
        """``SP0621-0900``: the reference ID beside the name in the Project Map."""
        return f"SP{self.when:%m%d-%H%M}"

    def name(self, set_label: str = "") -> str:
        """``Shadow | Shadow Plan 21 Jun 09:00``, or with the set's name in it."""
        word = f"{PLAN_WORD} {set_label}".strip() if set_label else PLAN_WORD
        return naming.named(f"{word} {self.stamp}")

    def sun_for_archicad(self) -> dict[str, Any]:
        """The date the add-on hands Archicad to work its own sun out from.

        A date rather than angles, as for the sun views: the shadow is then
        Archicad's, from the project's georeferencing, and a disagreement with
        this tool's astronomy shows on the drawing rather than being hidden.
        The hour is in Archicad's own clock where the add-on can say what that
        is, since Archicad reads a sun date in the project location's time
        zone and not in the one the hours were asked for (D135).
        """
        return sun_date(self.when, self.clock_minutes)


def shadow_plans(
    geo: GeoLocation,
    moments: Sequence[dt.datetime],
    labels: Sequence[str],
    *,
    clock_minutes: int | None = None,
) -> tuple[list[ShadowPlan], list[ShadowPlan]]:
    """The hours to draw, and the ones left out because the sun is down.

    ``moments`` and ``labels`` are the shadow diagram's own, so the two routes
    draw the same hours under the same names. An hour with the sun below the
    horizon is left out rather than drawn: a document of it would be a plan
    with no sun at all, which is not a shadow diagram of anything.
    ``clock_minutes`` is Archicad's clock, carried onto every plan for the
    date it hands over (``clock.read_archicad_clock``).
    """
    if len(moments) != len(labels):
        raise ValueError(f"{len(moments)} moments but {len(labels)} labels")
    if not moments:
        return [], []
    position = solar_position(list(moments), geo.latitude_deg, geo.longitude_deg)
    up: list[ShadowPlan] = []
    down: list[ShadowPlan] = []
    for when, label, altitude in zip(moments, labels, position.elevation_deg, strict=True):
        plan = ShadowPlan(
            when=when, label=label, altitude_deg=float(altitude), clock_minutes=clock_minutes
        )
        (up if plan.altitude_deg > 0.0 else down).append(plan)
    return up, down


@dataclass(frozen=True)
class ShadowPlanSettings:
    """What a shadow plan's view is pinned to, and the fill its shadows take."""

    layer_combination: str
    renovation_filter_guid: str | None = None
    model_view_options: str | None = None
    pen_set: str | None = None
    graphic_override: str | None = None
    scale: float = PLAN_SCALE
    shadow_fill: dict[str, int] = field(default_factory=dict)
    """``fillIndex``, ``fillPen``, ``backgroundPen``, ``contourPen``, each
    optional: what is left out keeps the project's own 3D Document default."""
    shadow_contours: bool = False
    fill_uncut_surfaces: bool | None = None
    """Whether the document fills its uncut surfaces -- roofs, the ground.
    ``False`` leaves them as outlines and draws no shadow either (D141);
    ``None`` keeps the project's own default, and sends nothing, so an add-on
    built before the switch is not handed a field it refuses."""
    uncut_surfaces: dict[str, Any] | None = None
    """``{fill, fillType, pen}`` for the add-on's ``uncutSurfaces``: how the
    uncut surfaces are filled, as ``UPPER_SURFACES`` and ``LOWEST_SURFACES``
    ask for them in a stack (D142). ``None`` sends nothing."""

    def for_view(self) -> dict[str, Any]:
        """Tapir's ``viewSettings`` for the view of one document.

        No 3D style: a document has its own drawing settings, and Tapir
        refuses a style on a view of one (the sun views found that).
        """
        settings: dict[str, Any] = {
            "layerCombination": self.layer_combination,
            "drawingScale": int(self.scale),
            "rotation": 0,
            "structureDisplay": "EntireStructure",
        }
        if self.renovation_filter_guid:
            settings["renovationFilterGuid"] = {"guid": self.renovation_filter_guid}
        if self.model_view_options:
            settings["modelViewOptions"] = self.model_view_options
        if self.pen_set:
            settings["penSetName"] = self.pen_set
        if self.graphic_override:
            settings["graphicOverrideCombination"] = self.graphic_override
        return settings


@dataclass(frozen=True)
class MadePlan:
    """One document as the run left it."""

    plan: ShadowPlan
    view: StoreyView
    reused: bool
    """The document was already there under its name, and was re-set."""
    effects: int | None = None
    """The document's effects flags as read back, where the add-on said."""


def make_shadow_plans(
    connection: ArchicadConnection,
    plans: Sequence[ShadowPlan],
    *,
    settings: ShadowPlanSettings,
    set_label: str = "",
    fresh: int | None = None,
) -> tuple[list[MadePlan], list[str]]:
    """One 3D Document per hour, overhead with its sun and shadows, and a view
    of each pinned to ``settings``. Returns them and anything worth saying.

    Made in order, then the ones already there are re-set in a second pass:
    re-setting copies the shadow switch from a document made in the first,
    and there is only one to copy from once one has been made.
    """
    if not plans:
        return [], []
    said: list[str] = []
    existing = {s.name: s for s in three_d_sources(connection) if s.kind == "DocumentFrom3DItem"}

    made: list[tuple[ShadowPlan, str, bool, int | None]] = []
    #: The effects flags of a document this run made with the shadows on --
    #: given, from a set made earlier in the same run, or found below.
    for plan in plans:
        name = plan.name(set_label)
        if name in existing:
            made.append((plan, name, True, None))
            continue
        asked: dict[str, Any] = {
            "name": name,
            "referenceId": plan.reference,
            "viewAzimuth": 0.0,
            "viewAltitude": OVERHEAD_DEG,
            "sun": plan.sun_for_archicad(),
            "sunShadows": True,
            "shadowContours": settings.shadow_contours,
        }
        if settings.shadow_fill:
            asked["shadowFill"] = dict(settings.shadow_fill)
        if settings.fill_uncut_surfaces is not None:
            asked["fillUncutSurfaces"] = settings.fill_uncut_surfaces
        if settings.uncut_surfaces is not None:
            asked["uncutSurfaces"] = dict(settings.uncut_surfaces)
        try:
            response = connection.run_loriini("CreateDocumentFrom3D", asked)
        except CommandFailedError as error:
            raise ArchicadError(
                f"Archicad would not make the shadow plan {name!r}: {error}. An add-on "
                f"built before shadow plans cannot turn a document's sun shadows on; "
                f"install the current build."
            ) from error
        identifier = (
            str(((response or {}).get("databaseId") or {}).get("guid", ""))
            if isinstance(response, dict)
            else ""
        )
        if not identifier:
            raise ArchicadError(f"CreateDocumentFrom3D for {plan.stamp} answered {response!r}")
        effects = response.get("effects3D") if isinstance(response, dict) else None
        effects = int(effects) if isinstance(effects, int | float) else None
        if fresh is None and effects is not None:
            fresh = effects
        made.append((plan, name, False, effects))

    reset: list[tuple[ShadowPlan, str, bool, int | None]] = []
    for plan, name, reused, effects in made:
        if reused:
            effects = _reset(connection, existing[name], plan, settings, fresh, said)
        reset.append((plan, name, reused, effects))

    sources = [(_document_item(connection, name, existing), name) for _, name, _, _ in reset]
    views = views_for_sources(
        connection,
        sources,
        combination=settings.layer_combination,
        folder=_folder(set_label),
        drawing_scale=settings.scale,
    )
    _check(
        connection.run_tapir(
            "SetViewSettings",
            {
                "navigatorItemIdsWithViewSettings": [
                    {
                        "navigatorItemId": {"guid": view.navigator_id},
                        "viewSettings": settings.for_view(),
                    }
                    for view in views
                ]
            },
        ),
        "SetViewSettings",
    )
    return [
        MadePlan(plan=plan, view=view, reused=reused, effects=effects)
        for (plan, _, reused, effects), view in zip(reset, views, strict=True)
    ], said


def _reset(
    connection: ArchicadConnection,
    source: ModelSource,
    plan: ShadowPlan,
    settings: ShadowPlanSettings,
    fresh: int | None,
    said: list[str],
) -> int | None:
    """Re-aim a document an earlier run made, and set its sun and fill again.

    Its shadow switch is copied from ``fresh``, a document this run made with
    the shadows on; with none made this run, the switch stays as the earlier
    run left it and the run says so. An add-on too old for the command keeps
    the document exactly as it was, and says that instead.
    """
    asked: dict[str, Any] = {
        "databaseId": {"guid": database_of(connection, source.identifier)},
        "viewAzimuth": 0.0,
        "viewAltitude": OVERHEAD_DEG,
        "sun": plan.sun_for_archicad(),
    }
    if settings.shadow_fill:
        asked["shadowFill"] = dict(settings.shadow_fill)
    if settings.fill_uncut_surfaces is not None:
        asked["fillUncutSurfaces"] = settings.fill_uncut_surfaces
    if settings.uncut_surfaces is not None:
        asked["uncutSurfaces"] = dict(settings.uncut_surfaces)
    if fresh is not None:
        asked["effects3D"] = fresh
    try:
        answer = connection.run_loriini("SetDocumentFrom3D", asked)
    except CommandFailedError as error:
        if "not have the registered" not in str(error):
            raise
        note = (
            "the installed Loriini add-on has no SetDocumentFrom3D, so the documents "
            "already there are kept as they were made; install the current build"
        )
        if note not in said:
            said.append(note)
        return None
    if fresh is None:
        note = (
            "every document was already there, so their sun shadows are as the last run "
            "left them; delete one in the Project Map and run again to have it remade"
        )
        if note not in said:
            said.append(note)
    effects = answer.get("effects3D") if isinstance(answer, dict) else None
    return int(effects) if isinstance(effects, int | float) else None


def _folder(set_label: str) -> str:
    """The View Map folder a set's views go in."""
    return naming.named(f"{SET_WORD} {set_label}".strip() if set_label else SET_WORD)


def _document_item(
    connection: ArchicadConnection, name: str, existing: dict[str, ModelSource]
) -> ModelSource:
    """The Project Map item of a document, found by its name.

    The add-on answers with the database's own id and the navigator carries a
    different one, so a document just made is looked up rather than derived.
    """
    if name in existing:
        return existing[name]
    for source in three_d_sources(connection):
        if source.kind == "DocumentFrom3DItem" and source.name == name:
            existing[name] = source
            return source
    raise ArchicadError(f"The 3D Document {name!r} was created but is not in the Project Map.")


# -- the sheets -----------------------------------------------------------------


def _sheet_stem(set_label: str) -> str:
    """``Shadow | Shadow Plans - ``, or with the set's name in it."""
    word = f"{SET_WORD} {set_label}".strip() if set_label else SET_WORD
    return naming.named(f"{word} - ")


def plan_sheet_groups(
    made: Sequence[MadePlan], *, sheets: str = DEFAULT_SHEET_MODE, set_label: str = ""
) -> tuple[list[tuple[str, list[tuple[str, str]]]], int]:
    """The documents dealt onto sheets, a day at a time, and the cells a sheet has.

    A sheet is a day, as for the fills: *Shadow | Shadow Plans - JUNE 21*, or
    ``(1 of 2)`` after it when the day's hours are split, or the hour after it
    when a sheet holds one. Each drawing is captioned as the fills' are,
    ``JUNE 21 -9AM``. The cell count is the fullest sheet's, so every sheet of
    the run shares one grid.
    """
    dealt, cells = _dealt(made, sheets=sheets, set_label=set_label)
    return [
        (name, [(one.view.navigator_id, one.plan.caption) for one in on_sheet])
        for name, on_sheet in dealt
    ], cells


def _dealt(
    made: Sequence[MadePlan], *, sheets: str, set_label: str
) -> tuple[list[tuple[str, list[MadePlan]]], int]:
    """The documents dealt onto named sheets, a day at a time, and the cells
    the fullest sheet has. The naming ``plan_sheet_groups`` describes; shared
    with the stacked sheets, which deal a proposal's documents the same way
    and then put the existing set's on top of each."""
    days: dict[str, list[MadePlan]] = {}
    for one in made:
        days.setdefault(one.plan.when.strftime("%B %d").upper(), []).append(one)
    stem = _sheet_stem(set_label)
    dealt: list[tuple[str, list[MadePlan]]] = []
    cells = 0
    for day, hours in days.items():
        chunks = sheet_chunks(len(hours), sheets)
        cells = max(cells, cells_for(chunks))
        for part, (start, stop) in enumerate(chunks, start=1):
            on_sheet = hours[start:stop]
            if len(chunks) == 1:
                name = f"{stem}{day}"
            elif len(on_sheet) == 1:
                name = f"{stem}{day} {on_sheet[0].plan.label}"
            else:
                name = f"{stem}{day} ({part} of {len(chunks)})"
            dealt.append((name, on_sheet))
    return dealt, cells


def make_shadow_plan_sheets(
    connection: ArchicadConnection,
    made: Sequence[MadePlan],
    *,
    sheets: str = DEFAULT_SHEET_MODE,
    set_label: str = "",
    scale: float = PLAN_SCALE,
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
    window: PlanWindow | None = None,
) -> tuple[list[LayoutReport], list[str]]:
    """The documents on sheets, and this set's earlier sheets that are not
    being remade removed. Each drawing is clipped to its cell, as for the sun
    views, with its origin at the cell's centre -- or, given a ``window``,
    placed so the window's centre is there (D143)."""
    groups, cells = plan_sheet_groups(made, sheets=sheets, set_label=set_label)
    removed = remove_stale_layouts(connection, _sheet_stem(set_label), {name for name, _ in groups})
    offset = (0.0, 0.0)
    if window is not None:
        cx, cy = window.centre
        offset = (-cx / scale, -cy / scale)
    reports = place_on_sheets(
        connection,
        groups,
        cells=cells,
        scale=scale,
        master_layout=master_layout,
        title_block_mm=title_block_mm,
        offset=offset,
        aspect=window.aspect if window is not None else None,
    )
    return reports, removed


# -- the stack: every legend row, one drawing per hour -------------------------


@dataclass(frozen=True)
class LegendRow:
    """One row of the shadow legend, as the layers that hold it.

    The same rows as the fills' legend (``archicad.shadows.LEGEND``) and the
    same two roles: a **baseline** accumulates -- existing neighbours, then
    future neighbours, each charged only for the ground the ones before had
    not darkened -- and a **scenario** is compared, cast against every
    baseline and no other scenario, so two scenarios overlap.
    """

    label: str
    """The legend's words, and the word in this set's names: ``EXISTING``,
    ``TOD - scenario 2``."""
    layers: tuple[str, ...]
    role: str
    """``BASELINE`` or ``SCENARIO``, from ``core.shadow``."""


@dataclass(frozen=True)
class PlanSet:
    """One row of a stack as it is drawn: the layer combination its documents'
    views pin, and the solid pen its shadows are drawn in."""

    label: str
    layer_combination: str
    shadow_pen: int


@dataclass(frozen=True)
class Stack:
    """Every set's documents for one stacked drawing per hour, bottom to top.

    ``piles`` is ``(label, documents)`` per set in drawing order: the
    scenarios first in the order named, then the baselines from the last to
    the first. A document draws the whole shadow of everything its set shows,
    so stacked in that order each one is seen only where everything above it
    casts nothing -- the first baseline's shadow in its colour, what the
    second adds in its colour, and each scenario's addition beneath them all,
    the last named over the earlier ones where two overlap. That is the fills'
    legend, cast by Archicad, with the split made by the order on the sheet
    instead of by subtracting.
    """

    piles: tuple[tuple[str, tuple[MadePlan, ...]], ...]


#: The word the combined sheets carry after ``Shadow Plans``. Their own word,
#: so a project that also has a plain set keeps both: a sheet finds its
#: drawings by name and never clears the ones it does not know.
COMBINED_LABEL = "Combined"

#: What the legend on a combined sheet is headed.
LEGEND_TITLE = "SHADOW LEGEND"

#: How every document of a stack fills its uncut surfaces: filled, so
#: Archicad draws its shadows -- it draws them on filled surfaces and on
#: nothing else (D141) -- in one pen colour, the transparent pen, so the
#: surfaces themselves draw nothing and the documents beneath show (D142).
#: The lowest document too: filled with the materials' own colours, Archicad
#: draws a shadow as the material shaded darker and ignores the shadow's pen,
#: and the lowest row came out a dark grey on the sample project instead of
#: its legend blue.
STACK_SURFACES: dict[str, Any] = {"fill": True, "fillType": "penColor", "pen": 0}


def stack_labels(count: int) -> list[str]:
    """What ``--proposed`` sets are called: ``Proposed`` alone, or numbered.

    Numbered in the order given, whatever the office calls them this week --
    the SEARs massing, the building envelope -- so a reader of the Layout Book
    meets ``Proposed 1`` and ``Proposed 2`` and reads the legend for which is
    which.
    """
    if count <= 1:
        return [PROPOSED_LABEL] * count
    return [f"{PROPOSED_LABEL} {number}" for number in range(1, count + 1)]


def legend_from_existing_and_proposed(
    existing_layers: Sequence[str], proposals: Sequence[Sequence[str]]
) -> list[LegendRow]:
    """``--existing`` and ``--proposed`` as legend rows: what stands as one
    baseline, each proposal as a scenario named by ``stack_labels``."""
    rows: list[LegendRow] = []
    if existing_layers:
        rows.append(LegendRow(EXISTING_LABEL, tuple(existing_layers), BASELINE))
    rows += [
        LegendRow(label, tuple(layers), SCENARIO)
        for label, layers in zip(stack_labels(len(proposals)), proposals, strict=True)
    ]
    return rows


def stack_order(rows: Sequence[LegendRow]) -> list[LegendRow]:
    """The rows bottom to top, as ``Stack`` describes: scenarios in the order
    named, then baselines from the last named to the first."""
    scenarios = [row for row in rows if row.role == SCENARIO]
    baselines = [row for row in rows if row.role == BASELINE]
    return scenarios + baselines[::-1]


def legend_combinations(
    rows: Sequence[LegendRow], *, also_show: Sequence[str] = ()
) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """What each set's layer combination shows and hides, in legend order.

    ``(label, show, hide)`` per row. A baseline shows its own layers and every
    earlier baseline's; a scenario shows every baseline's and its own. Each
    hides every other row's layers it does not show, so a layer two rows
    share is shown by both. Anything else keeps the state the base
    combination gives it -- the ground among it -- and ``also_show`` is what
    the base hides that every set needs, the site context the plain mode
    switches on the same way.
    """
    every = [layer for row in rows for layer in row.layers]
    out: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    standing: list[str] = []
    for row in rows:
        if row.role != BASELINE:
            continue
        standing = [*standing, *row.layers]
        out.append((row.label, *_show_hide(also_show, standing, every)))
    for row in rows:
        if row.role == SCENARIO:
            out.append((row.label, *_show_hide(also_show, [*standing, *row.layers], every)))
    order = [row.label for row in rows]
    return sorted(out, key=lambda entry: order.index(entry[0]))


def _show_hide(
    also_show: Sequence[str], shown: Sequence[str], every: Sequence[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    show = tuple(dict.fromkeys([*also_show, *shown]))
    on = {layer.casefold() for layer in show}
    hide = tuple(dict.fromkeys(layer for layer in every if layer.casefold() not in on))
    return show, hide


def make_shadow_plan_stack(
    connection: ArchicadConnection,
    plans: Sequence[ShadowPlan],
    *,
    settings: ShadowPlanSettings,
    members: Sequence[PlanSet],
) -> tuple[Stack, list[str]]:
    """Every set's documents, ``members`` bottom to top, as one stack.

    Each set is made as ``make_shadow_plans`` makes one, under its own
    combination and label, with its shadows a solid in its own pen -- the
    background pen the fill pen, so a hatch left in the settings covers as a
    solid would -- and its uncut surfaces filled in the transparent pen, so
    its drawing shows its shadows and lets the ones beneath show everywhere
    else (``STACK_SURFACES``).
    """
    said: list[str] = []
    piles: list[tuple[str, tuple[MadePlan, ...]]] = []
    #: A document made by any set of this run carries the shadow switch the
    #: sets already there are re-set with; without it, a stack whose new row
    #: was made below an old one said every document had been there before.
    fresh: int | None = None
    for member in members:
        fill = dict(settings.shadow_fill)
        fill["fillPen"] = member.shadow_pen
        fill["backgroundPen"] = member.shadow_pen
        own = replace(
            settings,
            layer_combination=member.layer_combination,
            shadow_fill=fill,
            fill_uncut_surfaces=None,
            uncut_surfaces=dict(STACK_SURFACES),
        )
        made, notes = make_shadow_plans(
            connection, plans, settings=own, set_label=member.label, fresh=fresh
        )
        for note in notes:
            if note not in said:
                said.append(note)
        fresh = next(
            (one.effects for one in made if not one.reused and one.effects is not None), fresh
        )
        piles.append((member.label, tuple(made)))
    return Stack(piles=tuple(piles)), said


def stack_sheet_groups(
    stack: Stack, *, sheets: str = DEFAULT_SHEET_MODE
) -> tuple[list[tuple[str, list[list[tuple[str, str]]]]], int]:
    """The stack's sheets, a cell per hour holding every set's drawing, and the
    cells the fullest sheet has.

    ``(layout name, [[(navigator id, drawing name), ...] per cell])``, each
    cell's list bottom to top. The sheets are dealt as a labelled set's are,
    by the lowest set's hours, and named *Shadow | Shadow Plans Combined - JUNE
    21*. The top drawing of a cell is named for the hour alone, ``JUNE 21
    -9AM``, as the one title the cell shows (D148); each drawing under it for
    the hour and its set, ``JUNE 21 -9AM TOD``, since a sheet finds its
    drawings by name and two of one name would be one. A set that lacks an
    hour -- a rerun over a Project Map somebody has pruned -- is left out of
    that hour's cell.
    """
    if not stack.piles:
        return [], 0
    _, lowest = stack.piles[0]
    by_hour = [{one.plan.when: one for one in made} for _, made in stack.piles]
    dealt, cells = _dealt(lowest, sheets=sheets, set_label=COMBINED_LABEL)
    groups: list[tuple[str, list[list[tuple[str, str]]]]] = []
    for name, on_sheet in dealt:
        cells_here: list[list[tuple[str, str]]] = []
        for one in on_sheet:
            pile = [
                (found.view.navigator_id, f"{one.plan.caption} {label.upper()}")
                for (label, _), hours in zip(stack.piles, by_hour, strict=True)
                if (found := hours.get(one.plan.when)) is not None
            ]
            if pile:
                pile[-1] = (pile[-1][0], one.plan.caption)
            cells_here.append(pile)
        groups.append((name, cells_here))
    return groups, cells


def make_stack_sheets(
    connection: ArchicadConnection,
    stack: Stack,
    *,
    sheets: str = DEFAULT_SHEET_MODE,
    scale: float = PLAN_SCALE,
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
    window: PlanWindow | None = None,
    pen_table_index: int | None = None,
    legend: Sequence[tuple[str, tuple[int, int, int]]] = (),
    legend_title: str = LEGEND_TITLE,
    rings: Sequence[Sequence[tuple[float, float]]] = (),
    outline_pen: int | None = None,
) -> tuple[list[LayoutReport], list[str], list[str]]:
    """The stack on its sheets, every set's drawing of an hour in one cell.

    Each drawing above the lowest has a transparent background; with a
    ``window``, every drawing's origin is put where the window's centre lands
    in the middle of its cell at ``scale``; with ``pen_table_index``, every
    drawing prints in that pen table. The combined sheets an earlier run made
    and this one is not remaking are removed, only the top drawing of each
    cell keeps a title (D148), every drawing is redrawn, and
    with a ``legend`` the legend is drawn in the column left of the title
    block -- which the cells then keep clear of -- and the site's ``rings``
    over every drawing in ``outline_pen`` (D143). Returns the sheets, the
    names removed, and anything worth saying.
    """
    groups, cells = stack_sheet_groups(stack, sheets=sheets)
    stem = _sheet_stem(COMBINED_LABEL)
    removed = remove_stale_layouts(connection, stem, {name for name, _ in groups})
    clear_of = title_block_mm + (LEGEND_COLUMN_MM if legend else 0.0)
    offset = (0.0, 0.0)
    if window is not None:
        cx, cy = window.centre
        offset = (-cx / scale, -cy / scale)
    reports = place_stacks_on_sheets(
        connection,
        groups,
        cells=cells,
        scale=scale,
        master_layout=master_layout,
        title_block_mm=clear_of,
        transparent_above_lowest=True,
        offset=offset,
        pen_table_index=pen_table_index,
        aspect=window.aspect if window is not None else None,
    )
    said: list[str] = []
    for report, (_, piles) in zip(reports, groups, strict=True):
        if not report.database_id:
            continue
        for note in (
            one_title_per_pile(connection, report.database_id, piles),
            update_drawings(connection, report.database_id),
        ):
            if note and note not in said:
                said.append(note)
        if not legend and not rings:
            continue
        sheet, _ = layout_sheet(connection, report.database_id)
        grid = sheet_cells_for(
            sheet,
            cells,
            title_block_mm=clear_of,
            aspect=window.aspect if window is not None else None,
        )[: len(piles)]
        try:
            draw_legend_and_outline(
                connection,
                report.database_id,
                title=legend_title,
                rows=legend,
                cells=grid,
                window=window,
                scale=scale,
                rings=rings,
                outline_pen=outline_pen,
                title_block_mm=title_block_mm,
            )
        except ArchicadError as error:
            note = f"the legend and the site outline could not be drawn on the sheet: {error}"
            if note not in said:
                said.append(note)
    return reports, removed, said
