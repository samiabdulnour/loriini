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

What it does not give is what the fills give. A document shows the whole
shadow of whatever its layer combination shows, at one hour: there is no
"existing" and "additional", and layouts do not composite drawings. The
comparison is made by running the set twice under two layer combinations --
``set_label`` names each, so the two sit side by side in the Project Map and
the Layout Book -- and reading the sheets against each other. The two routes
answer different questions, and the office may want both: the documents as
the record, the fills as the argument (docs/shadow-plans.md).

A 3D Document cannot be deleted through the API (``APIDb_DeleteDatabaseID``
takes details, worksheets and layouts), so a rerun finds its own documents by
name. It re-aims them and re-sets their sun and fill (``SetDocumentFrom3D``),
and copies the shadow switch onto them from a document this run made with
it, so a second run leaves the same documents a first run would.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError, CommandFailedError
from sun_study.archicad.layout import LayoutReport, remove_stale_layouts
from sun_study.archicad.read import GeoLocation
from sun_study.archicad.series import database_of
from sun_study.archicad.sheeting import DEFAULT_SHEET_MODE, cells_for, sheet_chunks
from sun_study.archicad.sun_eyes import TITLE_BLOCK_MM, place_on_sheets
from sun_study.archicad.views import (
    ModelSource,
    StoreyView,
    _check,
    three_d_sources,
    views_for_sources,
)
from sun_study.core.solar import solar_position

__all__ = [
    "DEFAULT_COMBINATION",
    "OVERHEAD_DEG",
    "PLAN_SCALE",
    "PLAN_WORD",
    "SET_WORD",
    "MadePlan",
    "ShadowPlan",
    "ShadowPlanSettings",
    "make_shadow_plan_sheets",
    "make_shadow_plans",
    "plan_sheet_groups",
    "shadow_plans",
]

#: What one document is called, after the prefix, and what the set is.
PLAN_WORD = "Shadow Plan"
SET_WORD = "Shadow Plans"

#: The scale the shadow diagram's sheets are drawn at: a site plan at 1:1000
#: on an A1 is about half the page each way, so four hours fit on a sheet.
PLAN_SCALE = 1000.0

#: The office's own layer combination for its shadow diagrams, which the sun
#: views start from too.
DEFAULT_COMBINATION = "04 | Shadow Diagrams"

#: The fill the office draws its shadow documents in, read off the Kogarah
#: file on 8 October 2026 (fill 200, "50 %", on nine of its hour documents).
#: A project's own 3D Document default was "zz Fire Brick" on the mark-up
#: pen, which on the first live plans showed as no shadow at all.
DEFAULT_SHADOW_FILL = "50 %"


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
        """``15 | Shadow Plan 21 Jun 09:00``, or with the set's name in it."""
        word = f"{PLAN_WORD} {set_label}".strip() if set_label else PLAN_WORD
        return naming.named(f"{word} {self.stamp}")

    def sun_for_archicad(self) -> dict[str, Any]:
        """The date the add-on hands Archicad to work its own sun out from.

        A date rather than angles, as for the sun views: the shadow is then
        Archicad's, from the project's georeferencing, and a disagreement with
        this tool's astronomy shows on the drawing rather than being hidden.
        """
        return {
            "year": self.when.year,
            "month": self.when.month,
            "day": self.when.day,
            "hour": self.when.hour,
            "minute": self.when.minute,
            "second": 0,
            "summerTime": bool(self.when.dst()),
        }


def shadow_plans(
    geo: GeoLocation, moments: Sequence[dt.datetime], labels: Sequence[str]
) -> tuple[list[ShadowPlan], list[ShadowPlan]]:
    """The hours to draw, and the ones left out because the sun is down.

    ``moments`` and ``labels`` are the shadow diagram's own, so the two routes
    draw the same hours under the same names. An hour with the sun below the
    horizon is left out rather than drawn: a document of it would be a plan
    with no sun at all, which is not a shadow diagram of anything.
    """
    if len(moments) != len(labels):
        raise ValueError(f"{len(moments)} moments but {len(labels)} labels")
    if not moments:
        return [], []
    position = solar_position(list(moments), geo.latitude_deg, geo.longitude_deg)
    up: list[ShadowPlan] = []
    down: list[ShadowPlan] = []
    for when, label, altitude in zip(moments, labels, position.elevation_deg, strict=True):
        plan = ShadowPlan(when=when, label=label, altitude_deg=float(altitude))
        (up if plan.altitude_deg > 0.0 else down).append(plan)
    return up, down


@dataclass(frozen=True)
class ShadowPlanSettings:
    """What a shadow plan's view is pinned to, and the fill its shadows take."""

    layer_combination: str = DEFAULT_COMBINATION
    renovation_filter_guid: str | None = None
    model_view_options: str | None = None
    pen_set: str | None = None
    graphic_override: str | None = None
    scale: float = PLAN_SCALE
    shadow_fill: dict[str, int] = field(default_factory=dict)
    """``fillIndex``, ``fillPen``, ``backgroundPen``, ``contourPen``, each
    optional: what is left out keeps the project's own 3D Document default."""
    shadow_contours: bool = False

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
    #: The effects flags of a document this run made with the shadows on.
    fresh: int | None = None
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
    """``15 | Shadow Plans - ``, or with the set's name in it."""
    word = f"{SET_WORD} {set_label}".strip() if set_label else SET_WORD
    return naming.named(f"{word} - ")


def plan_sheet_groups(
    made: Sequence[MadePlan], *, sheets: str = DEFAULT_SHEET_MODE, set_label: str = ""
) -> tuple[list[tuple[str, list[tuple[str, str]]]], int]:
    """The documents dealt onto sheets, a day at a time, and the cells a sheet has.

    A sheet is a day, as for the fills: *15 | Shadow Plans - JUNE 21*, or
    ``(1 of 2)`` after it when the day's hours are split, or the hour after it
    when a sheet holds one. Each drawing is captioned as the fills' are,
    ``JUNE 21 -9AM``. The cell count is the fullest sheet's, so every sheet of
    the run shares one grid.
    """
    days: dict[str, list[MadePlan]] = {}
    for one in made:
        days.setdefault(one.plan.when.strftime("%B %d").upper(), []).append(one)
    stem = _sheet_stem(set_label)
    groups: list[tuple[str, list[tuple[str, str]]]] = []
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
            groups.append((name, [(one.view.navigator_id, one.plan.caption) for one in on_sheet]))
    return groups, cells


def make_shadow_plan_sheets(
    connection: ArchicadConnection,
    made: Sequence[MadePlan],
    *,
    sheets: str = DEFAULT_SHEET_MODE,
    set_label: str = "",
    scale: float = PLAN_SCALE,
    master_layout: str | None = None,
    title_block_mm: float = TITLE_BLOCK_MM,
) -> tuple[list[LayoutReport], list[str]]:
    """The documents on sheets, and this set's earlier sheets that are not
    being remade removed. Each drawing's origin goes at the centre of its cell
    and its frame is clipped to the cell, as for the sun views."""
    groups, cells = plan_sheet_groups(made, sheets=sheets, set_label=set_label)
    removed = remove_stale_layouts(connection, _sheet_stem(set_label), {name for name, _ in groups})
    reports = place_on_sheets(
        connection,
        groups,
        cells=cells,
        scale=scale,
        master_layout=master_layout,
        title_block_mm=title_block_mm,
    )
    return reports, removed
