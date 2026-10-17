"""The tools an agent gets: what Loriini can tell it, and what it can run.

Two kinds. The listings -- which Archicads are running, what the open
project offers -- read the project the way the window's Refresh does
(``app.probe``), so the agent learns the layer and zone names before it
names them in a study. The studies run the command line in a child process
through ``app.runner``, exactly as the window runs them, and hand back the
run's last lines with its exit code; each line also goes to the client as
it is printed, so the agent and its person watch the study go.

The studies the office runs most have tools of their own, whose
arguments are the questions a person is asked on the window's pages, spelled
onto the command line the way ``Window.jobs`` spells them. Everything else
the command line offers is reached through ``run_loriini``, with
``loriini_help`` to read a command's options first -- breadth first, and a
typed tool where a study is asked for often enough to deserve one.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, BinaryIO, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sun_study import PRODUCT, __version__
from sun_study.agent.protocol import Call, InvalidArgumentsError, Server, Tool, ToolResult
from sun_study.app import probe
from sun_study.app.runner import Run
from sun_study.archicad.connection import DEFAULT_PORT, DEFAULT_TIMEOUT_SECONDS, PORT_RANGE
from sun_study.rules.days import ASSESSMENT_DAYS, day_name, parse_day

__all__ = ["TOOLS", "build", "run_command", "serve"]

#: The time zone every study is run in, as the window sends it: the office
#: is in Sydney, and so is every site the NSW rulesets apply to.
TIMEZONE = "Australia/Sydney"

#: How much of a run's output goes back in the answer. The whole run is
#: streamed as it happens; the answer is what a person reads afterwards, and
#: the last lines are where a run says what it made or why it stopped.
TAIL_LINES = 120

#: What the client shows the agent when it connects: what this is, and the
#: order to do things in.
INSTRUCTIONS = (
    f"{PRODUCT} draws sun, shadow and site studies into the Archicad project open on this "
    "machine, for a development application in New South Wales. Start with "
    "archicad_instances to find the port of the project, then project_options to read its "
    "layers, zone names, layer combinations, master layouts and pen sets: the studies take "
    "those names exactly as the project spells them. A study writes layouts, views and "
    "elements into the project on its own layers and takes minutes; its lines arrive as log "
    "messages while it runs, and the answer is the run's last lines with its exit code. Run "
    "one study at a time. loriini_help gives every option of a command, and run_loriini "
    "runs any command line the help describes, for what the named tools do not cover. A run "
    "changes the person's project: run into it only what they asked for. Before cos_solar, "
    "ask the person two layer combinations and a master layout, offering the ones "
    "project_options lists: the combination "
    "the model is exported under, which decides what casts shadow -- a guess brings in "
    "temporary and no-print geometry -- and the one the diagrams are drawn over, the plan "
    "the reader sees under the colours, usually the office's DA plans; left to default it "
    "is the export combination; and the master the sheets are made from, as the project's "
    "default places them wrong. Before any study, ask the person to close any open dialog "
    "and put a floor plan in front: Archicad refuses the whole API while a dialog is open, "
    "and refuses the save a study ends with while the 3D window is in front, which leaves "
    "the sheets without their tables."
)

T = TypeVar("T", bound="Arguments")


# -- what each tool takes ----------------------------------------------------------


class Arguments(BaseModel):
    """Every tool's arguments: named fields, and nothing the tool did not ask
    for, so a misspelled option is refused rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")


class NoArguments(Arguments):
    pass


class ProjectArguments(Arguments):
    port: int = Field(
        default=DEFAULT_PORT,
        description=(
            f"Archicad's JSON API port: {DEFAULT_PORT} for the first Archicad started on the "
            "machine, one more for each after it. archicad_instances lists them."
        ),
    )


class HelpArguments(Arguments):
    command: str = Field(
        default="",
        description=(
            "A command name -- site, shadows, shadow-plans, sun-views, massing, archicad-run, "
            "archicad-info -- for that command's options; blank for the list of commands."
        ),
    )


class RunArguments(Arguments):
    args: list[str] = Field(
        min_length=1,
        description=(
            "The command line after the program's name, one item each: the command, then "
            "its options and values as loriini_help shows them, e.g. "
            '["archicad-info", "--port", "19723"].'
        ),
    )


class StudyArguments(ProjectArguments):
    timeout_seconds: float = Field(
        default=DEFAULT_TIMEOUT_SECONDS,
        gt=0,
        description="How long to wait for any one Archicad command before giving up.",
    )
    layer_prefix: str | None = Field(
        default=None,
        description=(
            "The number the study's layers, views and layouts are filed under, e.g. '14', "
            "instead of the tool's own."
        ),
    )
    master_layout: str | None = Field(
        default=None,
        description=(
            "The master layout the sheets are made from. Ask the person which one; never "
            "choose it yourself. project_options lists them. Without it a run that makes "
            "a sheet stops and lists the project's masters."
        ),
    )


class SheetedArguments(StudyArguments):
    sheets: Literal["one", "two", "each"] | None = Field(
        default=None,
        description=(
            "How the drawings are dealt onto layouts: all on one, a morning and an "
            "afternoon sheet, or one layout each. The command's own way otherwise."
        ),
    )
    year: int | None = Field(
        default=None,
        ge=1900,
        le=2200,
        description="The year the sun is computed for; 2024 otherwise.",
    )


class SiteArguments(StudyArguments):
    address: str = Field(
        min_length=3,
        description="The site, e.g. '26-30 Campsie St, Campsie NSW 2194'. New South Wales only.",
    )
    context: bool = Field(default=True, description="Draw the Context Analysis sheet.")
    site: bool = Field(default=True, description="Draw the Site Analysis sheet.")
    summary: bool = Field(default=True, description="Draw the Summary of Controls layout.")
    model: bool = Field(
        default=False,
        description="Also make the 3D context model: terrain, street blocks, neighbours.",
    )
    model_radius_m: float | None = Field(
        default=None,
        gt=0,
        description="How far around the site the context model reaches, in metres.",
    )
    future: bool = Field(
        default=False,
        description=(
            "Also make the future context: the neighbours raised to what the controls allow."
        ),
    )
    future_reach_m: float | None = Field(
        default=None, gt=0, description="How far the future context reaches, in metres."
    )
    set_location: bool = Field(
        default=True,
        description=(
            "Set the project location from the address, which is the default; false keeps "
            "the project's own."
        ),
    )
    scale: int | None = Field(
        default=None, gt=0, description="The context sheet's scale, e.g. 3000 for 1:3000."
    )
    anchor: Literal["location", "site"] | None = Field(
        default=None,
        description=(
            "Where the drawings are anchored: at the project location, or with the site at "
            "the project origin."
        ),
    )
    origin_at: Literal["centre", "bottom-left", "bottom-right", "top-left", "top-right"] | None = (
        Field(
            default=None,
            description=(
                "With anchor 'site': which point of the site is the project origin, its "
                "centre or one of its corners as the plan reads them."
            ),
        )
    )
    square_to_site: bool = Field(
        default=False,
        description=(
            "With anchor 'site': turn the site so its longest boundary runs level across "
            "the plan, and set the project's north to match."
        ),
    )
    context_prefix: str | None = Field(
        default=None,
        description="The number the context analysis is filed under, when not the site's.",
    )
    out: str | None = Field(
        default=None, description="A folder to save the fetched data and the aerial photo into."
    )


class ShadowArguments(SheetedArguments):
    dates: list[str] = Field(
        default_factory=lambda: ["winter"],
        min_length=1,
        description=(
            "The days to draw: winter, equinox, summer, or MM-DD; several for a sheet each."
        ),
    )
    hours: list[int] | None = Field(
        default=None,
        description="Whole hours of the day to draw, e.g. [9, 12, 15]; 9 to 15 otherwise.",
    )
    sources: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "The shadow that already stands, one legend row each: the row's short name to "
            "the layers that hold it, e.g. {'EXISTING': ['03 | Site Context.Buildings']}. "
            "Rows accumulate: each is charged only for ground the earlier ones left lit."
        ),
    )
    scenarios: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Each proposal, drawn against every source and against no other scenario: the "
            "row's short name to its layers, e.g. {'PROPOSED': ['20 | Massing']}."
        ),
    )
    terrain_layers: list[str] = Field(
        default_factory=list,
        description=(
            "The ground the shadows land on: the layers, or element ID prefixes, of the "
            "terrain mesh. The terrain receives shadow and casts none."
        ),
    )
    terrain_floor_m: float | None = Field(
        default=None, description="The level below which nothing counts as terrain, in metres."
    )
    storey: int | None = Field(
        default=None, ge=0, description="The index of the storey the fills are placed on."
    )
    all_hours: bool = Field(
        default=False,
        description=(
            "Also draw the proposal's own shadow at every hour on one plan, as outlines "
            "labelled by hour."
        ),
    )
    subset: str | None = Field(
        default=None, description="The Layout Book subset the sheets are filed in."
    )


class ShadowPlanArguments(SheetedArguments):
    dates: list[str] = Field(
        default_factory=lambda: ["winter"],
        min_length=1,
        description=(
            "The days to draw: winter, equinox, summer, or MM-DD; a sheet or two for each."
        ),
    )
    hours: list[int] | None = Field(
        default=None,
        description="Whole hours of the day to draw, e.g. [9, 12, 15]; 9 to 15 otherwise.",
    )
    layer_combination: str | None = Field(
        default=None,
        description=(
            "The layer combination the plans show -- what casts the shadows and what they "
            "fall on, so the ground must be in it; the office's shadow diagram one otherwise."
        ),
    )
    label: str | None = Field(
        default=None,
        description=(
            "A word in the documents' and sheets' names, e.g. 'Existing' or 'Proposed', so "
            "two sets under two layer combinations sit side by side. Not with proposals, "
            "which name their sets themselves."
        ),
    )
    existing: list[str] | None = Field(
        default=None,
        description=(
            "The layers that hold what already stands -- the neighbouring buildings, e.g. "
            "['03 | Site Context.Buildings']. Shown in every set of a stack; the ground "
            "and the rest come from the layer combination. project_options lists the layers."
        ),
    )
    proposals: list[list[str]] | None = Field(
        default=None,
        description=(
            "The stacked mode: one list of layers per proposal, e.g. [['20 | Massing.SEARs'], "
            "['20 | Massing.Envelope']]. Named Proposed 1, Proposed 2 and on in this order, "
            "or Proposed alone. For each, a sheet per day with the existing set's document "
            "laid over the proposal's in every cell: the existing shadow in one pen, and "
            "what the proposal adds in another, both cast by Archicad, on one plan."
        ),
    )
    existing_pen: int | None = Field(
        default=None,
        ge=0,
        description=(
            "With proposals: the pen the existing shadow is filled in. Left out, the pen "
            "nearest the legend's grey in the project's pen table."
        ),
    )
    proposed_pens: list[int] | None = Field(
        default=None,
        description=(
            "With proposals: the pen each proposal's shadow is filled in, in order. Left "
            "out, the pens nearest the legend's blues."
        ),
    )
    pen_set: str | None = Field(default=None, description="The pen set the plans print in.")
    shadow_pen: int | None = Field(
        default=None, ge=0, description="The pen the shadows are filled in, in the plain mode."
    )
    scale: int | None = Field(
        default=None, gt=0, description="The scale the plans are placed at, e.g. 1000."
    )
    subset: str | None = Field(
        default=None, description="The Layout Book subset the sheets are filed in."
    )


class SunViewArguments(SheetedArguments):
    day: str | None = Field(
        default=None,
        description="The day: winter, equinox, summer, or MM-DD; the ruleset's own day otherwise.",
    )
    hours: list[int] | None = Field(
        default=None,
        description=(
            "Whole hours to make a view at, e.g. [9, 12, 15]; the ruleset's window otherwise."
        ),
    )
    pen_set: str | None = Field(default=None, description="The pen set the views print in.")
    override: str | None = Field(
        default=None, description="The graphic override combination the views are pinned to."
    )
    base_combination: str | None = Field(
        default=None, description="The layer combination the views start from."
    )
    scale: int | None = Field(
        default=None, gt=0, description="The scale the documents are placed at, e.g. 500 for 1:500."
    )
    title_block_mm: float | None = Field(
        default=None,
        gt=0,
        description="The width of the master's title block, kept clear of drawings.",
    )


class CosArguments(SheetedArguments):
    master_layout: str = Field(
        min_length=1,
        description=(
            "The master layout the sheets are made from, e.g. the office's B1 DA master: the "
            "project's default puts the drawings in the wrong place. Ask the person which "
            "one; never choose it yourself. project_options lists them."
        ),
    )
    layer_combination: str = Field(
        min_length=1,
        description=(
            "The layer combination the model is exported under -- what casts shadow on the "
            "communal open space. Ask the person which one; never choose it yourself. "
            "project_options lists them, and the office's is usually its IFC export one."
        ),
    )
    zone_layer: str = Field(
        min_length=1,
        description="The layer the communal open space Zones are on, from project_options.",
    )
    zone_names: list[str] = Field(
        default_factory=list,
        description="Only the Zones with these names, e.g. ['COS']; all on the layer otherwise.",
    )
    storeys: list[str] = Field(
        default_factory=list,
        description=(
            "Only the Zones on these storeys, spelled as project_options lists them, e.g. "
            "['LEVEL 01 (2)']. Everything above still shades them."
        ),
    )
    storey_from: str | None = Field(
        default=None,
        description="The storey the building starts at; geometry below it is dropped.",
    )
    storey_to: str | None = Field(
        default=None,
        description=(
            "The storey the building ends at, e.g. 'LIFT OVERRUN'; geometry above it -- parked "
            "hotlink masters -- is dropped."
        ),
    )
    require_layers: list[str] = Field(
        default_factory=list,
        description=(
            "Zone layers forced into the export whatever the combination shows; the project's "
            "'Zone.' layers otherwise, which is what places the drawing."
        ),
    )
    hours: float | None = Field(
        default=None,
        gt=0,
        description="Also split the Zones at this many hours of sun: 2 in Sydney's metro area.",
    )
    hourly: bool = Field(default=True, description="Also draw a plan at each whole hour.")
    day: str | None = Field(
        default=None,
        description="The day: winter, equinox, summer, or MM-DD; the ruleset's own day otherwise.",
    )
    zone_height_m: float | None = Field(
        default=None, ge=0, description="Height above the Zone floor to assess; 1 m otherwise."
    )
    zone_grid_m: float | None = Field(
        default=None, gt=0, description="Grid spacing over the Zones, in metres."
    )
    view_combination: str = Field(
        min_length=1,
        description=(
            "The layer combination the diagrams are drawn over -- the plan the reader sees "
            "under the colours, usually the office's DA plans. Ask the person which one; "
            "never choose it yourself. project_options lists them."
        ),
    )
    subset: str | None = Field(
        default=None, description="The Layout Book subset the sheets are filed in."
    )
    table: str | None = Field(
        default=None, description="Write the COS schedules, one per Zone, to this .xlsx."
    )
    csv: str | None = Field(default=None, description="Write every area figure to this CSV.")


def _validated(model: type[T], arguments: Mapping[str, Any]) -> T:
    try:
        return model.model_validate(dict(arguments))
    except ValidationError as wrong:
        said = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'arguments'}: {error['msg']}"
            for error in wrong.errors()
        )
        raise InvalidArgumentsError(said) from wrong


# -- the command lines ---------------------------------------------------------------


def _common(arguments: StudyArguments) -> list[str]:
    """What every study is sent, as the window sends it."""
    return ["--port", str(arguments.port), "--timeout", f"{arguments.timeout_seconds:g}"]


def _option(flag: str, value: object) -> list[str]:
    """One option and its value, or nothing for a value nobody gave: the
    command's own default is the honest reading of a field left empty."""
    if value is None or value == "":
        return []
    if isinstance(value, float):
        return [flag, f"{value:g}"]
    return [flag, str(value)]


def _mmdd(day: str) -> str:
    try:
        return parse_day(day)
    except ValueError as wrong:
        raise InvalidArgumentsError(
            f"not a day: {day!r} (winter, equinox, summer, or MM-DD)"
        ) from wrong


def _date_args(day: str | None) -> list[str]:
    """``--date`` for a day, or nothing for the ruleset's own, as the window
    does: the command's names stay the ones it has always made on midwinter."""
    if not day:
        return []
    mmdd = _mmdd(day)
    return [] if mmdd == ASSESSMENT_DAYS["winter"][0] else ["--date", day_name(mmdd)]


def _rows(flag: str, rows: Mapping[str, Sequence[str]]) -> list[str]:
    """Legend rows as ``NAME=layer,layer``, one flag each."""
    argv: list[str] = []
    for name, layers in rows.items():
        if not name.strip() or "=" in name or "," in name:
            raise InvalidArgumentsError(f"a legend row's name is a short word, not {name!r}")
        if not layers:
            raise InvalidArgumentsError(f"row {name!r} names no layers")
        argv += [flag, f"{name}={','.join(layers)}"]
    return argv


def site_argv(arguments: SiteArguments) -> list[str]:
    a = arguments
    argv = ["site", a.address, *_common(a)]
    argv += _option("--layer-prefix", a.layer_prefix) + _option(
        "--context-prefix", a.context_prefix
    )
    argv += ["--context" if a.context else "--no-context"]
    argv += ["--site" if a.site else "--no-site"]
    argv += ["--summary" if a.summary else "--no-summary"]
    if a.model:
        argv += ["--model"]
    if a.model or a.future:
        argv += _option("--model-radius", a.model_radius_m)
    if a.future:
        argv += ["--future", *_option("--future-reach", a.future_reach_m)]
    if not a.set_location:
        argv += ["--keep-location"]
    argv += _option("--scale", a.scale) + _option("--anchor", a.anchor)
    argv += _option("--origin-at", a.origin_at)
    if a.square_to_site:
        argv += ["--square-to-site"]
    argv += _option("--out", a.out) + _option("--master-layout", a.master_layout)
    return argv


def shadow_argv(arguments: ShadowArguments) -> list[str]:
    a = arguments
    argv = [
        "shadows",
        "--timezone",
        TIMEZONE,
        *_common(a),
        *_option("--layer-prefix", a.layer_prefix),
    ]
    argv += _rows("--shadow-source", a.sources) + _rows("--shadow-scenario", a.scenarios)
    for layer in a.terrain_layers:
        argv += ["--shadow-terrain", layer]
    # The native model and never an IFC, as every study of the window's.
    argv += ["--export", "native"]
    if a.all_hours:
        argv += ["--shadow-all-hours"]
    argv += _option("--shadow-terrain-floor", a.terrain_floor_m)
    argv += ["--shadow-date", ",".join(_mmdd(day) for day in a.dates)]
    if a.hours:
        argv += ["--shadow-hour", ",".join(str(hour) for hour in a.hours)]
    argv += _option("--shadow-storey", a.storey) + _option("--master-layout", a.master_layout)
    argv += _option("--shadow-subset", a.subset) + _option("--year", a.year)
    argv += _option("--sheets", a.sheets)
    return argv


def shadow_plans_argv(arguments: ShadowPlanArguments) -> list[str]:
    a = arguments
    argv = [
        "shadow-plans",
        "--timezone",
        TIMEZONE,
        *_common(a),
        *_option("--layer-prefix", a.layer_prefix),
    ]
    argv += ["--shadow-date", ",".join(_mmdd(day) for day in a.dates)]
    if a.hours:
        argv += ["--shadow-hour", ",".join(str(hour) for hour in a.hours)]
    argv += _option("--layer-combination", a.layer_combination) + _option("--label", a.label)
    for layer in a.existing or []:
        argv += ["--existing", layer]
    for layers in a.proposals or []:
        argv += ["--proposed", ",".join(layers)]
    argv += _option("--existing-pen", a.existing_pen)
    for pen in a.proposed_pens or []:
        argv += ["--proposed-pen", str(pen)]
    argv += _option("--pen-set", a.pen_set) + _option("--shadow-pen", a.shadow_pen)
    argv += _option("--scale", a.scale) + _option("--master-layout", a.master_layout)
    argv += _option("--subset", a.subset) + _option("--year", a.year)
    argv += _option("--sheets", a.sheets)
    return argv


def sun_views_argv(arguments: SunViewArguments) -> list[str]:
    a = arguments
    argv = [
        "sun-views",
        "--timezone",
        TIMEZONE,
        *_common(a),
        *_option("--layer-prefix", a.layer_prefix),
    ]
    argv += _option("--pen-set", a.pen_set) + _option("--override", a.override)
    argv += _option("--base-combination", a.base_combination) + _option("--scale", a.scale)
    argv += _option("--title-block-mm", a.title_block_mm)
    if a.hours:
        argv += ["--hour", ",".join(str(hour) for hour in a.hours)]
    argv += _option("--master-layout", a.master_layout) + _option("--year", a.year)
    argv += _date_args(a.day) + _option("--sheets", a.sheets)
    return argv


def cos_argv(arguments: CosArguments, zone_layers: Sequence[str] = ()) -> list[str]:
    """The window's communal job. ``zone_layers`` are the project's, forced
    into the export when the agent names none, as the window forces them."""
    a = arguments
    argv = [
        "massing",
        "--timezone",
        TIMEZONE,
        *_common(a),
        *_option("--layer-prefix", a.layer_prefix),
        "--export",
        "native",
        "--zone-layer",
        a.zone_layer,
    ]
    for name in a.zone_names:
        argv += ["--zone-name", name]
    for storey in a.storeys:
        argv += ["--zone-storey", storey]
    for name in a.require_layers or [n for n in zone_layers if "Zone." in n] or zone_layers:
        argv += ["--require-layer", name]
    argv += ["--layer-combination", a.layer_combination]
    argv += _option("--exclude-below-storey", a.storey_from)
    argv += _option("--exclude-above-storey", a.storey_to)
    argv += _option("--master-layout", a.master_layout) + _option("--zone-subset", a.subset)
    argv += _option("--zone-view-combination", a.view_combination)
    argv += _option("--zone-height", a.zone_height_m) + _option("--zone-grid", a.zone_grid_m)
    argv += _option("--zone-csv", a.csv) + _option("--zone-table", a.table)
    argv += _option("--zone-hours", a.hours)
    # The areas always, as the window: a plan without them invites a figure
    # read off a colour.
    argv += ["--zone-sheet", "--zone-stats"]
    if a.hourly:
        argv += ["--zone-hourly"]
    argv += _option("--year", a.year) + _date_args(a.day) + _option("--sheets", a.sheets)
    return argv


# -- running one --------------------------------------------------------------------


def run_command(argv: Sequence[str], call: Call) -> ToolResult:
    """The command line, run as the window runs it, its lines streamed as they
    come and its last ones returned with its exit code."""
    lines: list[str] = []
    finished = threading.Event()
    exit_codes: list[int] = []

    def on_line(line: str) -> None:
        lines.append(line)
        call.say(line)

    def on_done(code: int) -> None:
        exit_codes.append(code)
        finished.set()

    run = Run(argv, on_line=on_line, on_done=on_done)
    call.when_stopped(run.stop)
    run.start()
    finished.wait()
    code = exit_codes[0]
    shown = lines[-TAIL_LINES:]
    head = [f"sun-study {' '.join(argv)}", f"exit code {code}, {len(lines)} lines"]
    if len(lines) > len(shown):
        head.append(
            f"(the first {len(lines) - len(shown)} lines were streamed and are not repeated)"
        )
    return ToolResult(
        text="\n".join([*head, "", *shown]),
        structured={"exit_code": code, "lines": len(lines), "stopped": call.stopped},
        is_error=code != 0,
    )


# -- the tools ------------------------------------------------------------------------


def archicad_instances(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    _validated(NoArguments, arguments)
    found = probe.running()
    rows = [{"port": one.port, "project": one.project} for one in found]
    if not found:
        return ToolResult(
            f"No Archicad is answering on any port ({PORT_RANGE.start} to {PORT_RANGE.stop - 1}). "
            "Check that it is running with a project open, and that the JSON interface is on "
            "in Options > Work Environment > Model Compare and JSON Interface.",
            structured={"instances": rows},
        )
    text = "\n".join(f"port {one.port}: {one.project or '(no project open)'}" for one in found)
    return ToolResult(text, structured={"instances": rows})


def project_options(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    a = _validated(ProjectArguments, arguments)
    found = probe.options(a.port)
    if not found.reachable:
        return ToolResult(
            f"Nothing answered on port {a.port}: " + ("; ".join(found.problems) or "no project"),
            is_error=True,
        )
    lines = [f"project: {found.project}"]
    if found.tapir_missing:
        lines.append("the Loriini add-on is not installed in this Archicad: no study can run")
    elif found.tapir:
        lines.append(f"add-on: {found.tapir}")
    if found.latitude is not None and found.longitude is not None:
        lines.append(f"location: {found.latitude:.5f}, {found.longitude:.5f}")
    else:
        lines.append("location: not set (Options > Project Preferences > Project Location)")

    def listed(title: str, names: Sequence[str]) -> None:
        if names:
            lines.append(f"{title} ({len(names)}): " + "; ".join(names))

    listed("layers", found.layers)
    listed("layers carrying zones", found.zone_layers)
    if found.zone_kinds:
        lines.append(
            "zones by name: "
            + "; ".join(f"{kind.described()} on {kind.layer}" for kind in found.zone_kinds)
        )
    listed("layer combinations", found.combinations)
    listed("master layouts", found.masters)
    listed("layout subsets", found.subsets)
    listed("pen sets", found.pen_sets)
    listed("graphic overrides", found.overrides)
    listed("storeys, bottom to top", found.storey_names)
    for problem in found.problems:
        lines.append(f"could not read: {problem}")
    return ToolResult("\n".join(lines), structured=asdict(found))


def loriini_help(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    a = _validated(HelpArguments, arguments)
    return run_command([a.command, "--help"] if a.command else ["--help"], call)


def run_loriini(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    a = _validated(RunArguments, arguments)
    if a.args[0] == "mcp":
        raise InvalidArgumentsError("run_loriini cannot start another agent server")
    return run_command(a.args, call)


def site_analysis(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    return run_command(site_argv(_validated(SiteArguments, arguments)), call)


def shadow_diagrams(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    return run_command(shadow_argv(_validated(ShadowArguments, arguments)), call)


def shadow_plans(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    return run_command(shadow_plans_argv(_validated(ShadowPlanArguments, arguments)), call)


def sun_views(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    return run_command(sun_views_argv(_validated(SunViewArguments, arguments)), call)


def cos_solar(arguments: Mapping[str, Any], call: Call) -> ToolResult:
    a = _validated(CosArguments, arguments)
    zone_layers = () if a.require_layers else probe.options(a.port).zone_layers
    return run_command(cos_argv(a, zone_layers), call)


TOOLS: tuple[Tool, ...] = (
    Tool(
        "archicad_instances",
        "Every Archicad running on this machine, with the project each has open and the "
        "port to reach it on. Run this first.",
        NoArguments.model_json_schema(),
        archicad_instances,
        title="Running Archicads",
        read_only=True,
    ),
    Tool(
        "project_options",
        "What the open project offers, read from it: its layers, the layers that carry "
        "zones and what the zones are called, layer combinations, master layouts, layout "
        "subsets, pen sets, graphic overrides, storeys and location. The studies take "
        "these names exactly as spelled here.",
        ProjectArguments.model_json_schema(),
        project_options,
        title="The project's options",
        read_only=True,
    ),
    Tool(
        "loriini_help",
        "The command line's own help: the list of commands, or every option of one command "
        "with what it means. Read it before run_loriini.",
        HelpArguments.model_json_schema(),
        loriini_help,
        title="Command help",
        read_only=True,
    ),
    Tool(
        "run_loriini",
        "Run any Loriini command line, for what the named tools do not cover: the apartment "
        "solar analysis (archicad-run), massing studies, the reports, the checks -- "
        "communal open space is cos_solar's. It runs into the open "
        "project and takes minutes; its lines are streamed and the last ones returned.",
        RunArguments.model_json_schema(),
        run_loriini,
        title="Run a command",
    ),
    Tool(
        "site_analysis",
        "The site tools for an address: the Context Analysis and Site Analysis sheets and the "
        "Summary of Controls from NSW open data (and the City of Sydney's inside its area), "
        "drawn into the open project; optionally the 3D context model and the future "
        "context. Sets the project location from the address unless told to keep it.",
        SiteArguments.model_json_schema(),
        site_analysis,
        title="Site analysis",
    ),
    Tool(
        "shadow_diagrams",
        "Shadow diagrams for the days and hours asked, cast by the layers named as the "
        "existing shadow and the proposal onto the terrain, drawn as fills on layouts in "
        "the legend's colours. The layer names come from project_options.",
        ShadowArguments.model_json_schema(),
        shadow_diagrams,
        title="Shadow diagrams",
    ),
    Tool(
        "shadow_plans",
        "The same days and hours as 3D Documents looking straight down, each with "
        "Archicad's own sun and vectorial shadows for that hour, placed on layouts by day. "
        "Archicad casts the shadows, so it suits a model too large for shadow_diagrams. One "
        "document shows the whole shadow of what the layer combination shows; given "
        "existing and proposals, the stacked mode lays the existing set's document over "
        "each proposal's on one sheet, so the existing shadow and what each proposal adds "
        "are in two pens on one plan, both cast by Archicad. Without proposals, run it once "
        "per combination with a label each.",
        ShadowPlanArguments.model_json_schema(),
        shadow_plans,
        title="Shadow plans",
    ),
    Tool(
        "sun_views",
        "The sun's-eye views: a view of the model from the sun at each hour of the day, "
        "each as a 3D Document, placed on layouts.",
        SunViewArguments.model_json_schema(),
        sun_views,
        title="Sun views",
    ),
    Tool(
        "cos_solar",
        "Solar access to communal open space: the Zones asked for, banded by hours of direct "
        "sun, split at the threshold and drawn at each hour, on layouts with their areas, and "
        "the COS schedule per Zone. Ask the person first which layer combination to export "
        "under, which one to draw the diagrams over and which master layout the sheets go on, "
        "and to put a floor plan in front.",
        CosArguments.model_json_schema(),
        cos_solar,
        title="COS solar",
    ),
)


#: The server's icon: the bird, as the window's own icon is, for the client
#: to show beside the server's name. The 256-pixel PNG, about 70 kilobytes,
#: sent once a session in the reply to ``initialize``.
ICON_NAME = "loriini-icon-256.png"


def icon() -> bytes | None:
    """The bytes of the bird, or nothing where the file is not to be found:
    a server without an icon is still a server. The bundle carries it under
    ``assets`` beside the window's icons (``Loriini.spec``); a checkout has
    it in ``assets`` at the top."""
    bundled = getattr(sys, "_MEIPASS", None)
    root = Path(bundled) if bundled else Path(__file__).resolve().parents[3]
    try:
        return (root / "assets" / ICON_NAME).read_bytes()
    except OSError:
        return None


def build() -> Server:
    return Server(
        name=PRODUCT, version=__version__, tools=TOOLS, instructions=INSTRUCTIONS, icon=icon()
    )


def serve() -> None:
    """Serve the client that started this process, on its stdin and stdout.

    The windowed executable has no console, so its standard streams are
    whatever the process that started it gave it -- pipes, from an MCP
    client -- and Python may not have wrapped them. The descriptors are
    opened directly then, in binary, which is how the protocol wants them:
    one UTF-8 line per message, no newline translation.
    """
    inp: BinaryIO = sys.stdin.buffer if sys.stdin is not None else open(0, "rb", closefd=False)
    out: BinaryIO = sys.stdout.buffer if sys.stdout is not None else open(1, "wb", closefd=False)
    build().serve(inp, out)
