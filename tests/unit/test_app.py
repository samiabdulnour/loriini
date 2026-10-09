"""The window, tested without one on screen.

Two things are worth testing here and the rest is Tk's problem. The command
line the ticked boxes mean -- because a wrong flag is a wrong study, silently
-- and the probe's habit of answering with what it *could* read rather than
raising, because a project that will not give up one list is still worth
offering the other five for.

``Window`` is built against a withdrawn root: real widgets, never mapped, so
the argv it produces is the argv a colleague's click produces.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

# Skipped, not collected into an error, where Tk cannot be had: the Linux
# runners ship no tkinter at all, so a plain import failed the whole module
# before a single assertion ran. Under TYPE_CHECKING the real import still
# stands, so the annotations below stay checked instead of going Any.
#
# It has to come before the imports underneath: `sun_study.app.window` imports
# tkinter itself, so leaving this below them would raise on the runner exactly
# as the plain import did.
if TYPE_CHECKING:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter", reason="this machine has no tkinter")

from sun_study.app import icons, preferences, probe, run_log, theme, window
from sun_study.app.runner import CLI_MARKER, child_environment, command_prefix
from sun_study.archicad import naming
from sun_study.archicad.connection import DEFAULT_TIMEOUT_SECONDS, Instance


@pytest.fixture
def hidden_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """A real Window over a fake project, never shown.

    The saved settings are pointed somewhere disposable before it is built:
    the window reads them as it opens, and a test that passed or failed on
    whatever the developer last pressed Save on would be no test at all.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(
        probe,
        "running",
        lambda: [
            Instance(port=19723, project="SAMPLE"),
            Instance(port=19724, project="EXAMPLE"),
        ],
    )
    monkeypatch.setattr(
        probe,
        "options",
        lambda port: probe.ProjectOptions(
            project="SAMPLE",
            tapir="1.5.7",
            layers=(
                "01 | Wall.External",
                "01 | Floor.Structural",
                "05 | Dims/Notes.DA",
                "06 | Zone.Units",
            ),
            zone_layers=("05 | Dims/Notes.DA", "06 | Zone.Balcony", "06 | Zone.Units"),
            # The reference project's own shape: dwellings, balconies and
            # storage cupboards, all Zones, all on one layer, told apart only
            # by a name and a size.
            zone_kinds=(
                probe.ZoneKind(layer="06 | Zone.Units", label="G08", count=15, area_m2=74.0),
                probe.ZoneKind(layer="06 | Zone.Units", label="BY", count=20, area_m2=11.0),
                probe.ZoneKind(layer="06 | Zone.Units", label="SC", count=6, area_m2=2.5),
                probe.ZoneKind(layer="05 | Dims/Notes.DA", label="GFA", count=37, area_m2=310.0),
            ),
            combinations=("01 | Plans - DA", "12 | IFC ARCH. EXPORT"),
            masters=("A4", "DA A1 - VERTICAL COVER/NO SCALE", "DA A1 - VERTICAL - No Scale"),
            subsets=("ADG DIAGRAMS", "PLANS", "SHADOW DIAGRAMS"),
            overrides=("Clean", "Sun Eye Views", "Zone Colours"),
        ),
    )
    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - a machine with no display
        pytest.skip("no display for Tk")
    root.withdraw()
    made = window.Window(root)
    yield made
    root.destroy()


def flag(args: list[str], name: str) -> list[str]:
    """Every value given for one repeated option."""
    return [value for before, value in pairwise(args) if before == name]


def test_the_project_fills_in_what_nobody_should_have_to_type(hidden_window: Any) -> None:
    """The point of the window. Each of these is a property of the project,
    and a person typing one is the commonest way a run measures the wrong
    thing."""
    assert hidden_window.apartments.get() == "06 | Zone.Units"
    assert hidden_window.combination.get() == "12 | IFC ARCH. EXPORT"
    assert hidden_window.shadow_subset.get() == "SHADOW DIAGRAMS"
    assert hidden_window.adg_subset.get() == "ADG DIAGRAMS"


def test_the_no_scale_master_beats_the_no_scale_cover_sheet(hidden_window: Any) -> None:
    """Both say no scale and one of them is a cover sheet. A diagram shrunk to
    fit the page is at no stated scale, which is why no-scale is right -- but
    not the cover."""
    assert hidden_window.master.get() == "DA A1 - VERTICAL - No Scale"


def test_the_facade_run_forces_the_zone_layers_into_the_export(hidden_window: Any) -> None:
    """Without an IfcSpace there is nothing to fit the skin onto the building
    against, and no IFC combination shows the zone layers -- the failure this
    produces is 'the skin cannot be placed', several minutes in."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    (facade,) = hidden_window.jobs()
    assert facade.args[0] == "massing"
    assert flag(facade.args, "--require-layer") == ["06 | Zone.Balcony", "06 | Zone.Units"]


def test_an_annotation_layer_that_happens_to_hold_a_zone_is_not_exported(
    hidden_window: Any,
) -> None:
    """``05 | Dims/Notes.DA`` carries 37 Zones on the reference project. They
    are somebody's schedule, not the building."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    (facade,) = hidden_window.jobs()
    assert "05 | Dims/Notes.DA" not in flag(facade.args, "--require-layer")


def test_the_floors_tick_is_what_puts_the_decks_in(hidden_window: Any) -> None:
    """Horizontal faces take more sun than any wall, so a study without them
    shows the least-lit half of the building."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    (with_floors,) = hidden_window.jobs()
    assert "--model-flat" in with_floors.args

    hidden_window.do_floors.set(False)
    (without,) = hidden_window.jobs()
    assert "--no-model-flat" in without.args and "--model-flat" not in without.args


def test_the_plans_run_files_its_sheets_where_the_practice_keeps_them(
    hidden_window: Any,
) -> None:
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    (plans,) = hidden_window.jobs()

    assert plans.args[0] == "archicad-run"
    assert "--draw" in plans.args and "--sheet" in plans.args
    assert flag(plans.args, "--layout-subset") == ["SHADOW DIAGRAMS"]
    assert flag(plans.args, "--adg-subset") == ["ADG DIAGRAMS"]
    assert flag(plans.args, "--plan-instant") == ["09:00", "12:00", "15:00"]


def test_the_chosen_archicad_is_the_one_the_study_runs_against(hidden_window: Any) -> None:
    """Two projects open is ordinary, and each instance gets its own port, so
    the default is right only for whichever started first."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.instance.current(1)
    (facade,) = hidden_window.jobs()
    assert flag(facade.args, "--port") == ["19724"]


def test_both_ticked_runs_both_in_order(hidden_window: Any) -> None:
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.do_plans.set(True)
    assert [job.args[0] for job in hidden_window.jobs()] == ["massing", "archicad-run"]


def test_the_communal_study_needs_no_apartment_and_no_glazing(hidden_window: Any) -> None:
    """The point of that study: a Zone round an outdoor area and nothing else.

    None of the apartment machinery may reach the command line, or a
    playground gets assessed as a flat with no living room.
    """
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.communal_names.insert(0, "PLAYGROUND, COURTYARD")
    hidden_window.do_communal.set(True)
    (communal,) = hidden_window.jobs()

    assert communal.args[0] == "massing"
    assert flag(communal.args, "--zone-layer") == ["06 | Zone.Balcony"]
    assert flag(communal.args, "--zone-name") == ["PLAYGROUND", "COURTYARD"]
    assert "--zone-sheet" in communal.args
    for unwanted in (
        "--apartment-zone-layer",
        "--apartment-zone-name",
        "--open-space-zone-layer",
        "--livable-suffix",
    ):
        assert unwanted not in communal.args, unwanted


def test_the_communal_study_carries_a_second_zone_layer_for_the_fit(
    hidden_window: Any,
) -> None:
    """One zone layer gives one pair, and a plan transform needs two."""
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    (communal,) = hidden_window.jobs()
    assert flag(communal.args, "--require-layer"), "nothing to fit the drawing against"


def test_the_communal_study_carries_its_window_and_its_threshold(
    hidden_window: Any,
) -> None:
    """The default is 8 to 3 with a 2 hour split, which is what was asked for."""
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    (communal,) = hidden_window.jobs()

    assert flag(communal.args, "--window-start") == ["08:00"]
    assert flag(communal.args, "--window-end") == ["15:00"]
    assert flag(communal.args, "--zone-hours") == ["2"]
    assert "--zone-stats" in communal.args


def test_a_window_nobody_can_parse_is_left_to_the_ruleset(hidden_window: Any) -> None:
    """Passing half a window would move the study by an unstated amount.

    The ruleset's own hours are the safe way to be wrong, and the run says
    which window it used either way.
    """
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    for typed in ("", "08:00", "morning", "8-", "-15:00"):
        hidden_window.communal_window.delete(0, "end")
        hidden_window.communal_window.insert(0, typed)
        (communal,) = hidden_window.jobs()
        assert "--window-start" not in communal.args, typed
        assert "--window-end" not in communal.args, typed


def test_the_window_is_written_the_way_people_say_it(hidden_window: Any) -> None:
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    hidden_window.communal_window.delete(0, "end")
    hidden_window.communal_window.insert(0, "08:00 to 15:00")
    (communal,) = hidden_window.jobs()
    assert flag(communal.args, "--window-start") == ["08:00"]
    assert flag(communal.args, "--window-end") == ["15:00"]


def test_the_apartment_study_keeps_the_adg_window(hidden_window: Any) -> None:
    """4A-1 is 9 to 3. A communal window typed in this app must not move it."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    hidden_window.communal_window.delete(0, "end")
    hidden_window.communal_window.insert(0, "06:00-18:00")
    (plans,) = hidden_window.jobs()
    assert "--window-start" not in plans.args
    assert "--window-end" not in plans.args


def test_the_plans_row_says_which_kind_of_plan_each_study_draws(
    hidden_window: Any,
) -> None:
    """Bands are the whole day striped by hours of sun; times are the sun
    where it actually falls at each instant. Both by default, and either
    alone on request -- for the apartments and the communal space alike,
    each through its own command's flags."""
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    hidden_window.do_plans.set(True)
    hidden_window.apartments.set("06 | Zone.Units")

    plans, communal = hidden_window.jobs()
    assert "--draw" in plans.args and flag(plans.args, "--plan-instant")
    assert "--plan-bands" in plans.args
    assert "--zone-hourly" in communal.args and "--no-zone-bands" not in communal.args

    hidden_window.plan_kinds.set("Bands by hour")
    plans, communal = hidden_window.jobs()
    assert "--draw" in plans.args and not flag(plans.args, "--plan-instant")
    assert "--plan-bands" in plans.args, "the heat map is a whole-day plan too"
    assert "--zone-hourly" not in communal.args and "--no-zone-bands" not in communal.args
    assert window.APARTMENT_HEAT_MAP in {sheet.kind for sheet in hidden_window.planned()}

    hidden_window.plan_kinds.set("Sun at each time")
    plans, communal = hidden_window.jobs()
    assert "--no-draw" in plans.args and "--sheet" in plans.args
    assert "--plan-bands" not in plans.args
    assert flag(plans.args, "--plan-instant") == ["09:00", "12:00", "15:00"]
    assert "--zone-hourly" in communal.args and "--no-zone-bands" in communal.args

    kinds = {sheet.kind for sheet in hidden_window.planned()}
    assert "Apartments" in kinds and window.COMMUNAL_HOURLY in kinds
    assert "Apartments, ADG total" not in kinds and "Communal open space" not in kinds
    assert window.APARTMENT_HEAT_MAP not in kinds


def test_the_plans_row_lights_any_of_three(hidden_window: Any) -> None:
    """The times, the floor heat map and the apartment total are three
    switches, not one pick. All start lit, each turns off by itself, the
    last one lit stays lit, and a file saved when "Bands by hour" was the
    heat map and the total together restores as both."""
    row = hidden_window.plan_kinds
    assert row.get() == "Sun at each time, Floor heat map, Apartment total"
    assert hidden_window._plan_kinds() == (True, True, True)
    row._pick("Floor heat map")
    assert row.get() == "Sun at each time, Apartment total"
    assert hidden_window._plan_kinds() == (True, False, True)
    row._pick("Apartment total")
    row._pick("Sun at each time")
    assert row.get() == "Sun at each time", "the last one lit stays lit"
    assert hidden_window._plan_kinds() == (True, False, False)
    hidden_window.apply({"plan_kinds": "Bands by hour"})
    assert row.get() == "Floor heat map, Apartment total"
    assert hidden_window._plan_kinds() == (False, True, True)
    hidden_window.apply({"plan_kinds": "Bands and times"})
    assert row.get() == "Sun at each time, Floor heat map, Apartment total"


def test_each_plan_tile_is_its_own_flag_to_the_run(hidden_window: Any) -> None:
    """Three plans, three flags: the times are ``--plan-instant``, the heat
    map is ``--plan-bands`` and the apartment total is ``--draw`` -- so a
    council that wants the totals without the heat map gets exactly that,
    and the panel deals only the sheets those flags will make."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_plans.set(True)
    hidden_window.apartments.set("06 | Zone.Units")

    hidden_window.plan_kinds.set("Apartment total")
    (plans,) = hidden_window.jobs()
    assert "--draw" in plans.args and "--plan-bands" not in plans.args
    assert not flag(plans.args, "--plan-instant")
    kinds = {sheet.kind for sheet in hidden_window.planned()}
    assert kinds == {"Apartments, ADG total"}

    hidden_window.plan_kinds.set("Floor heat map")
    (plans,) = hidden_window.jobs()
    assert "--no-draw" in plans.args and "--plan-bands" in plans.args
    assert {sheet.kind for sheet in hidden_window.planned()} == {window.APARTMENT_HEAT_MAP}


def test_the_communal_study_sends_the_settings_that_change_the_answer(
    hidden_window: Any,
) -> None:
    """Ground level and half a metre are the defaults, and they are not cosmetic.

    At one metre and two metres this project reads 37%; at ground level and
    half a metre it reads 46.6%. An app that quietly used the old numbers
    would be answering a different question from the command line.
    """
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    (communal,) = hidden_window.jobs()

    assert flag(communal.args, "--zone-height") == ["0"]
    assert flag(communal.args, "--zone-grid") == ["0.5"]


def test_a_neighbouring_layer_is_exported_and_kept_out_of_the_denominator(
    hidden_window: Any,
) -> None:
    """Both halves, or it is wrong in one direction or the other.

    Not exported, a neighbour shades nothing and the study overstates the
    sunlight. Exported as subject, its facades join the area being measured
    and the percentage describes the neighbourhood.
    """
    hidden_window.do_facade.set(False)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.context.insert(0, "03 | Site.Neighboring Context")
    hidden_window.do_communal.set(True)
    (communal,) = hidden_window.jobs()

    assert "03 | Site.Neighboring Context" in flag(communal.args, "--require-layer")
    assert flag(communal.args, "--context-layer") == ["03 | Site.Neighboring Context"]


def test_the_neighbours_shade_every_solar_study_not_only_the_communal_one(
    hidden_window: Any,
) -> None:
    """The Model tab says it is what every solar study sees. It reached the
    communal study alone: with a combination that hides the neighbours, the
    facade and the apartments were measured with nothing next door."""
    neighbours = "03 | Site Context.Buildings"
    hidden_window.context.insert(0, neighbours)
    hidden_window.require.insert(0, "05 | Dims/Notes.DA")
    hidden_window.communal.set("06 | Zone.Balcony")
    for tick in (hidden_window.do_facade, hidden_window.do_plans, hidden_window.do_communal):
        tick.set(True)

    jobs = hidden_window.jobs()
    facade = next(job.args for job in jobs if job.label.startswith(window.FACADE_JOB))
    plans = next(job.args for job in jobs if job.label.startswith(window.PLANS_JOB))
    communal = next(job.args for job in jobs if job.label.startswith(window.COMMUNAL_JOB))

    for args in (facade, plans, communal):
        assert neighbours in flag(args, "--require-layer"), args
    # Only where it keeps them out of what is measured; on the facade it
    # would narrow the model to the named layers and drop the rest.
    assert flag(facade, "--context-layer") == []
    assert flag(communal, "--context-layer") == [neighbours]
    assert "05 | Dims/Notes.DA" in flag(plans, "--require-layer"), "forced visible, for all three"


def test_the_plans_are_drawn_over_the_offices_own_plan_combination(hidden_window: Any) -> None:
    """The plan a reader expects under the sunlight, not the model the study
    reads. Offered from the project, a plan-like one picked, and passed to
    both plan studies under the names their commands use."""
    assert hidden_window.plan_combination.get() == "01 | Plans - DA"
    assert "" in hidden_window.plan_combination.cget("values"), "blank: the model's"

    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)
    jobs = hidden_window.jobs()
    plans = next(job.args for job in jobs if job.label.startswith(window.PLANS_JOB))
    communal = next(job.args for job in jobs if job.label.startswith(window.COMMUNAL_JOB))

    assert flag(plans, "--plan-combination") == ["01 | Plans - DA"]
    assert flag(communal, "--zone-view-combination") == ["01 | Plans - DA"]

    hidden_window.plan_combination.set("")
    plans = next(job.args for job in hidden_window.jobs() if job.label.startswith(window.PLANS_JOB))
    assert "--plan-combination" not in plans, "blank sends nothing; the command falls back"


def test_the_tools_own_combination_is_never_offered_as_the_plan(hidden_window: Any) -> None:
    """It regenerates those every run: a base that is its own output is the
    drift a base exists to stop."""
    hidden_window.options = replace(
        hidden_window.options,
        combinations=("14 | Sun Study Plan", "12 | IFC ARCH. EXPORT", "02 | GA Plans"),
    )
    hidden_window.plan_combination.set("")
    hidden_window._offer()

    offered = hidden_window.plan_combination.cget("values")
    assert "14 | Sun Study Plan" not in offered
    assert hidden_window.plan_combination.get() == "02 | GA Plans"


def test_no_table_is_written_unless_a_folder_is_named(hidden_window: Any) -> None:
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)
    plans, communal = hidden_window.jobs()
    assert "--csv" not in plans.args
    assert "--zone-csv" not in communal.args and "--zone-table" not in communal.args


def test_one_tables_folder_takes_every_table(hidden_window: Any, tmp_path: Path) -> None:
    """One option, not one per table: the apartments and the communal open
    space all land in the folder named, under names the window chooses."""
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.tables.insert(0, str(tmp_path))
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)

    plans, communal = hidden_window.jobs()

    assert flag(plans.args, "--csv") == [str(tmp_path / window.APARTMENTS_TABLE)]
    assert flag(communal.args, "--zone-csv") == [str(tmp_path / window.COS_AREAS_TABLE)]
    assert flag(communal.args, "--zone-table") == [str(tmp_path / window.COS_SCHEDULE_TABLE)]
    assert hidden_window.settings()["tables_folder"] == str(tmp_path)


def test_the_tables_folder_can_be_browsed_for(hidden_window: Any) -> None:
    """A Browse button beside the box, as every folder in the window has."""
    holder = hidden_window.tables.master
    buttons = [child for child in holder.winfo_children() if isinstance(child, tk.ttk.Button)]
    assert buttons, "no Browse beside the tables folder"


def test_all_three_studies_run_in_order(hidden_window: Any) -> None:
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)
    assert [job.args[0] for job in hidden_window.jobs()] == [
        "massing",
        "archicad-run",
        "massing",
    ]


def test_nothing_ticked_asks_for_nothing(hidden_window: Any) -> None:
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(False)
    hidden_window.do_communal.set(False)
    assert hidden_window.jobs() == []


def test_the_basic_preset_queues_no_study(hidden_window: Any) -> None:
    """What the window opens with, and what Forget goes back to. A study
    ticked before anybody chose it runs because it went unnoticed -- and the
    facade study, which used to be the one, is the longest of them."""
    assert hidden_window.jobs() == [], "a study is queued on a window nobody has touched"

    hidden_window.do_facade.set(True)
    hidden_window._forget()

    assert not hidden_window.do_facade.get()
    assert hidden_window.jobs() == [], "Forget left a study queued"


def test_every_control_explains_itself(hidden_window: Any) -> None:
    """Most of these settings fail quietly -- a facade study missing its slab
    layers reports the least-lit half of the building rather than an error --
    so a control nobody can interpret is a real defect, not a polish item.
    A tooltip binds <Enter>, which is what this looks for."""
    from tkinter import ttk as widgets

    def controls(parent: tk.Misc) -> list[tk.Widget]:
        found: list[tk.Widget] = []
        for child in parent.winfo_children():
            kinds = widgets.Combobox | widgets.Entry | widgets.Checkbutton | widgets.Button
            if isinstance(child, kinds):
                found.append(child)
            found.extend(controls(child))
        return found

    bare = [str(widget) for widget in controls(hidden_window.root) if not widget.bind("<Enter>")]
    assert not bare, f"controls with no explanation: {bare}"


def test_the_explanation_lands_in_the_band_and_not_in_a_window(hidden_window: Any) -> None:
    """There are no popups any more.

    A Toplevel tooltip covered the thing you were pointing at, went away while
    you were still reading it, and could not be reached from the keyboard at
    all -- which for a window whose settings fail quietly is not a polish
    complaint. The sentence goes to one band at the foot instead, and the band
    is never empty.
    """
    from sun_study.app.window import Tooltip

    hidden_window.info.resting("general", "Solar analysis", "Hours of direct sun.")
    tip = Tooltip(
        hidden_window.apartments,
        "which layer the apartments are on",
        title="Apartment zones",
        short="The zone layer the flats are drawn on.",
    )

    tip._show()
    said = (
        hidden_window.info.title.cget("text"),
        hidden_window.info.detail.cget("text"),
    )
    tip._hide()
    after = hidden_window.info.title.cget("text")

    assert said == ("Apartment zones", "which layer the apartments are on")
    assert after == "Solar analysis", "and it goes back to saying what the tab is for"
    assert not [
        child for child in hidden_window.root.winfo_children() if isinstance(child, tk.Toplevel)
    ], "no window was opened to say it"


def test_a_chip_row_is_still_the_entry_the_settings_file_expects(hidden_window: Any) -> None:
    """The layer pickers are chips now. The settings file round-trips through
    ``get``, ``delete`` and ``insert``, so a file written by the window that
    had text boxes still has to restore into this one."""
    box = hidden_window.subject

    box.delete(0, "end")
    box.insert(0, "01 | Wall.External, 03 | Floor.Slab")
    assert box.get() == "01 | Wall.External, 03 | Floor.Slab"

    box.drop("03 | Floor.Slab")
    assert box.get() == "01 | Wall.External", "and a chip can be dropped on its own"

    box.delete(0, "end")
    assert box.get() == ""


def only_shadows(hidden_window: Any, *, dates: str, hours: str) -> None:
    """One study ticked, on its own days and hours, so a count means something."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)
    # The dates go in as typed days with every button off, which is how a
    # settings file from the old row of four dates restores.
    for lit in hidden_window.shadow_day_ticks.values():
        lit.set(False)
    hidden_window.shadow_custom_day.delete(0, "end")
    hidden_window.shadow_custom_day.insert(0, dates)
    hidden_window.shadow_hours.delete(0, "end")
    hidden_window.shadow_hours.insert(0, hours)


def test_the_panel_holds_one_sheet_per_hour_per_day(hidden_window: Any) -> None:
    """What the panel draws is what Run will make, worked out from the ticks
    and the fields rather than from anything Archicad is asked."""
    only_shadows(hidden_window, dates="06-21, 12-21", hours="09:00, 12:00, 15:00")
    hidden_window.sheets.set("A layout per drawing")

    sheets = hidden_window.planned()

    assert len(sheets) == 6, "two days at three hours"
    assert [sheet.number for sheet in sheets[:3]] == ["SD.01", "SD.02", "SD.03"]
    assert {sheet.study for sheet in sheets} == {"Shadow diagram"}
    assert [sheet.day for sheet in sheets] == ["21 Jun"] * 3 + ["21 Dec"] * 3


def test_the_panel_deals_the_sheets_the_way_the_run_will(hidden_window: Any) -> None:
    """The Sheets row in General is what the run deals its drawings by, so the
    panel deals by it too -- through the same ``sheet_chunks`` -- and cannot
    show seven sheets where the run makes two. The short second sheet of a
    pair keeps the first one's grid with a cell empty, as the run leaves it."""
    from sun_study.archicad.sheeting import sheet_chunks

    only_shadows(hidden_window, dates="06-21, 12-21", hours="9,10,11,12,13,14,15")

    hidden_window.sheets.set("A layout per drawing")
    each = hidden_window.planned()
    assert len(each) == 14 and all(len(sheet.drawings) == 1 for sheet in each)
    assert each[0].time == "09:00", "a typed 9 is the 09:00 the sheet is named for"

    hidden_window.sheets.set("Two layouts, half each")
    two = hidden_window.planned()
    dealt = [stop - start for start, stop in sheet_chunks(7, "two")]
    assert [len(sheet.drawings) for sheet in two] == dealt * 2 == [4, 3, 4, 3]
    assert {sheet.cells for sheet in two} == {4}, "the short sheet keeps the full one's grid"
    assert [sheet.empty for sheet in two] == [0, 1, 0, 1]
    assert [(sheet.part, sheet.parts) for sheet in two[:2]] == [(1, 2), (2, 2)]
    assert [sheet.number for sheet in two] == ["SD.01", "SD.02", "SD.03", "SD.04"]
    assert (two[0].time, two[1].time) == ("09:00-12:00", "13:00-15:00")
    assert flag(hidden_window.jobs()[0].args, "--sheets") == ["two"], "and the run is told so"

    hidden_window.sheets.set("One layout, all drawings")
    one = hidden_window.planned()
    assert [len(sheet.drawings) for sheet in one] == [7, 7]
    assert [sheet.parts for sheet in one] == [1, 1], "not one of anything"


def test_a_blank_sheets_row_shows_each_tools_own_default(hidden_window: Any) -> None:
    """A blank row sends no ``--sheets``, and each tool then falls back to
    what it did before there was a choice -- two for the shadows, a sheet
    each for the apartment plans. The panel has to fall back the same way,
    or it shows a choice the run was never sent."""
    only_shadows(hidden_window, dates="06-21", hours="9,10,11,12,13,14,15")
    hidden_window.do_plans.set(True)
    hidden_window.instants.delete(0, "end")
    hidden_window.instants.insert(0, "09:00, 12:00, 15:00")
    hidden_window.sheets.set("")

    sheets = hidden_window.planned()

    shadows = [sheet for sheet in sheets if sheet.study == "Shadow diagram"]
    plans = [sheet for sheet in sheets if sheet.kind == "Apartments"]
    assert [len(sheet.drawings) for sheet in shadows] == [4, 3]
    assert [len(sheet.drawings) for sheet in plans] == [1, 1, 1]
    assert not any("--sheets" in job.args for job in hidden_window.jobs())


def test_the_shadow_sheets_follow_their_own_days_row(hidden_window: Any) -> None:
    """The shadow study is one job with its own box of days, not one run per
    lit day like the solar tools, so the Solar analysis page's days are not
    what it draws -- and the panel must not say they are."""
    only_shadows(hidden_window, dates="06-21", hours="12")
    for ticked in hidden_window.days.values():
        ticked.set(True)

    sheets = hidden_window.planned()

    assert [sheet.day for sheet in sheets] == ["21 Jun"]
    assert flag(hidden_window.jobs()[0].args, "--shadow-date") == ["06-21"]


def test_the_hourly_communal_plans_are_as_many_as_the_window_has_hours(
    hidden_window: Any,
) -> None:
    """Eight to three is eight plans and nine to three is seven, because the
    run draws every whole hour it measured -- and they are dealt onto sheets
    by the Sheets row, while the banded plan, the threshold plan and the
    areas table are one sheet each whatever it says."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_communal.set(True)
    for ticked in hidden_window.days.values():
        ticked.set(False)
    hidden_window.days["winter"].set(True)
    hidden_window.communal_window.delete(0, "end")
    hidden_window.communal_window.insert(0, "08:00-15:00")
    hidden_window.communal_hours.delete(0, "end")
    hidden_window.communal_hours.insert(0, "2")
    hidden_window.sheets.set("One layout, all drawings")

    sheets = hidden_window.planned()

    hourly = [sheet for sheet in sheets if sheet.kind == window.COMMUNAL_HOURLY]
    assert [len(sheet.drawings) for sheet in hourly] == [8]
    assert hourly[0].time == "08:00-15:00"
    assert [sheet.kind for sheet in sheets if sheet is not hourly[0]] == [
        "Communal open space",
        "Communal open space, 2 h or more",
        window.COMMUNAL_AREAS,
    ]
    assert all(not sheet.time for sheet in sheets if sheet is not hourly[0]), "whole-day sheets"

    hidden_window.plan_kinds.set("Bands by hour")
    assert not [s for s in hidden_window.planned() if s.kind == window.COMMUNAL_HOURLY]


def test_the_sun_views_follow_their_own_hours(hidden_window: Any) -> None:
    """Their Hours row, or the ruleset's nine to three when it is blank --
    which is what the command does with a blank ``--hour``."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_sun_eyes.set(True)
    for ticked in hidden_window.days.values():
        ticked.set(False)
    hidden_window.days["winter"].set(True)
    hidden_window.sheets.set("A layout per drawing")

    hidden_window.eye_hours.delete(0, "end")
    assert [sheet.time for sheet in hidden_window.planned()] == [
        f"{hour:02d}:00" for hour in range(9, 16)
    ]

    hidden_window.eye_hours.insert(0, "9, 3pm")
    assert [sheet.time for sheet in hidden_window.planned()] == ["09:00", "15:00"]


def test_the_hours_are_pressed_not_typed_and_still_read_as_the_run_reads_them(
    hidden_window: Any,
) -> None:
    """The rows of hours and days are buttons, and the field's text is what
    they mean, in the spelling each command takes: whole hours for the
    shadows, times of day for the plans, a range for the communal window,
    dates for the shadow days."""
    hours = hidden_window.shadow_hours
    hours.delete(0, "end")
    hours._toggle("9")
    hours._toggle("12")
    hours._toggle("15")
    assert hours.get() == "9, 12, 15"
    hours._toggle("12")
    assert hours.get() == "9, 15", "pressed again is off"

    times = hidden_window.instants
    times.delete(0, "end")
    times._toggle("12:00")
    assert times.get() == "12:00"

    window_row = hidden_window.communal_window
    window_row.delete(0, "end")
    window_row._toggle("08:00")
    window_row._toggle("15:00")
    assert window_row.get() == "08:00-15:00", "a span is its two ends"
    assert window_row._lit() == {f"{hour:02d}:00" for hour in range(8, 16)}, "lit between"

    # The shadow days are the same three buttons the other sun studies
    # press, with the diagram's own answer, sent as the dates the command
    # takes.
    hidden_window.shadow_day_ticks["summer"].set(True)
    assert hidden_window._shadow_days() == ["06-21", "12-21"]
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)
    hidden_window.sheets.set("One layout, all drawings")
    assert [sheet.day for sheet in hidden_window.planned()] == ["21 Jun", "21 Dec"]
    assert [sheet.time for sheet in hidden_window.planned()] == ["09:00-15:00"] * 2
    assert flag(hidden_window.jobs()[0].args, "--shadow-date") == ["06-21,12-21"]


def test_a_saved_field_lights_the_buttons_it_names_and_keeps_its_own_spelling(
    hidden_window: Any,
) -> None:
    """A settings file from the typed days -- ``9,10,11`` or ``9, 3pm`` --
    lights the right buttons and is sent exactly as it was saved. A value no
    button stands for lights nothing and is still sent, so a half hour saved
    on purpose is not rounded to the nearest button."""
    hours = hidden_window.shadow_hours
    hours.delete(0, "end")
    hours.insert(0, "9, 3pm")
    assert hours.get() == "9, 3pm"
    assert hours._lit() == {"9", "15"}

    hours.insert(0, "9:30, 12")
    assert hours.get() == "9:30, 12"
    assert hours._lit() == {"12"}, "the half hour lights nothing and is still sent"

    window_row = hidden_window.communal_window
    window_row.insert(0, "8am to 3pm")
    assert window_row.get() == "8am to 3pm"
    assert window_row._lit() == {f"{hour:02d}:00" for hour in range(8, 16)}

    # A file from the old row of four dates restores into the shadow box's
    # own custom-day field, which reads a comma list, by name or by date.
    hidden_window.apply({"shadow_dates": "winter, 12-21"})
    assert hidden_window.shadow_custom_day.get() == "winter, 12-21"
    assert hidden_window._shadow_days() == ["06-21", "12-21"], "a name is its date, once"


def test_every_sheet_says_the_scale_the_run_places_it_at(hidden_window: Any) -> None:
    """The block used to say 1:1000 on every sheet. It now says what each
    command sends: the sun views' own Scale row, the context sheet's, the
    shadow diagrams' 1:1000, the plans' 1:200 -- and, honestly, that the
    site sheet is fitted and the summary has no scale at all."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(True)
    hidden_window.site_address.insert(0, "1 Example Street")
    hidden_window.eye_scale.delete(0, "end")
    hidden_window.eye_scale.insert(0, "250")

    scales = {sheet.kind: sheet.scale for sheet in hidden_window.planned()}

    assert scales["Sun view"] == "1:250"
    assert scales["Context Analysis"] == "1:3000"
    assert scales["Site Analysis"] == "to fit"
    assert scales["Summary of Controls"] == ""
    assert scales["Shadow diagram"] == "1:1000"
    assert scales["Apartments"] == "1:200"
    assert scales["Communal open space"] == "1:300"
    assert scales[window.FACADE_MODEL] == "", "a model has no scale, being not a sheet"


def test_the_facade_study_is_a_model_and_not_a_sheet(hidden_window: Any) -> None:
    """The window never asks for the model-views sheet, so what the facade
    study makes is the coloured skin in 3D and nothing on paper. The panel
    said one sheet; it now shows the geometry, one per day."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_facade.set(True)
    for ticked in hidden_window.days.values():
        ticked.set(False)
    hidden_window.days["winter"].set(True)
    hidden_window.days["summer"].set(True)
    hidden_window._sync()

    made = hidden_window.planned()
    assert [(m.kind, m.day, m.paper) for m in made] == [
        (window.FACADE_MODEL, "21 Jun", False),
        (window.FACADE_MODEL, "21 Dec", False),
    ]
    assert not any("--model-views" in job.args for job in hidden_window.jobs())
    _box, says = hidden_window.study_boxes[window.FACADE_JOB]
    assert says.cget("text") == "0 sheets, 2 models"
    assert hidden_window.dock.tally.cget("text") == "0"


def test_a_long_chip_row_wraps_inside_the_pane_and_lines_up_by_row(hidden_window: Any) -> None:
    """Fourteen apartment names ran off the right of the page in one line,
    and the rows that did wrap lined up on the first row's column edges. The
    chips are placed by measuring, within the pane's width, and each row
    starts at the left."""
    chips = hidden_window.apartment_names
    chips.delete(0, "end")
    chips.insert(0, "FAST FOOD SHOP, 4B, RETAIL, 3B, UT1.A01, 2B, UT2.B02, XXX, UT3.C04, LOBBY")
    hidden_window.root.update_idletasks()

    chips._reflow(room=300)

    placed = [
        (int(w.place_info()["x"]), int(w.place_info()["y"]), w.winfo_reqwidth())
        for w in chips._made
    ]
    assert all(x + wide <= 300 for x, _y, wide in placed), "nothing past the edge"
    rows = sorted({y for _x, y, _w in placed})
    assert len(rows) >= 3, "three rows or more at that width"
    assert all(min(x for x, y, _w in placed if y == row) == 0 for row in rows), "each from the left"
    assert int(chips.cget("height")) > 0 and int(chips.cget("width")) == 300


def test_the_three_site_sheets_are_three_different_pictures(hidden_window: Any) -> None:
    """Context, site and summary are three drawings, and a panel that drew
    the same pin on all three said they were one."""
    drawn: dict[str, list[str]] = {}
    for kind in ("Context Analysis", "Site Analysis", "Summary of Controls"):
        paper = tk.Canvas(hidden_window.root)
        window._draw_drawing(paper, "Site analysis", window.Drawing(kind, "", ""), (0, 0, 150, 150))
        drawn[kind] = sorted(str(paper.type(item)) for item in paper.find_all())
    assert len({tuple(items) for items in drawn.values()}) == 3


def test_a_model_is_shown_as_geometry_and_not_counted_as_a_sheet(hidden_window: Any) -> None:
    """The site study's context model and future model are geometry on their
    own layers, not layouts. The panel shows them as what they are -- no
    paper -- and the count on the strip stays the count of sheets."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_site.set(True)
    hidden_window.site_address.insert(0, "1 Example Street")
    hidden_window.site_radius.delete(0, "end")
    hidden_window.site_radius.insert(0, "300")

    assert all(sheet.paper for sheet in hidden_window.planned()), "no model ticked"

    hidden_window.do_site_model.set(True)
    hidden_window.do_site_future.set(True)
    hidden_window._sync()
    made = hidden_window.planned()
    models = [sheet for sheet in made if not sheet.paper]
    assert [(m.kind, m.day) for m in models] == [
        (window.CONTEXT_MODEL, "300 m"),
        (window.FUTURE_MODEL, "100 m reach"),
    ]
    assert all(m.number == "" for m in models), "not numbered as sheets"
    assert hidden_window.dock.tally.cget("text") == "3", "three sheets, and the models are not"
    _box, says = hidden_window.study_boxes[window.SITE_JOB]
    assert says.cget("text") == "3 sheets, 2 models"

    paper = tk.Canvas(hidden_window.root)
    window.draw_model(paper, models[0], 300, 212)
    assert paper.find_withtag("edge"), "and it still takes the blue edge under the pointer"


def _texts(paper: Any) -> list[str]:
    """Every text item on a canvas, in the order it was drawn."""
    return [
        str(paper.itemcget(item, "text"))
        for item in paper.find_all()
        if str(paper.type(item)) == "text"
    ]


#: A whole-day plan, and a layout carrying four hours of a study: the two
#: shapes of sheet the panel draws, at the day the panel has as a heading.
WHOLE_DAY_SHEET = window.Sheet(
    "Communal open space",
    "communal",
    "SA.01",
    "Communal open space",
    "21 Jun",
    (window.Drawing("Communal open space", "21 Jun", ""),),
    scale="1:300",
)
FOUR_HOUR_SHEET = window.Sheet(
    "Shadow diagram",
    "shadow",
    "SD.01",
    "Shadow diagram",
    "21 Jun",
    tuple(
        window.Drawing("Shadow diagram", "21 Jun", f"{hour:02d}:00", 30.0 + hour, 20.0 + hour)
        for hour in (9, 10, 11, 12)
    ),
    cells=4,
    part=1,
    parts=2,
    scale="1:1000",
)
A_MODEL = window.Sheet("Site analysis", "site", "", window.CONTEXT_MODEL, "300 m", paper=False)


def test_a_sheet_says_only_what_the_panel_does_not_say_beside_it(hidden_window: Any) -> None:
    """The panel prints the day once, as a heading over the sheets of that
    day, and the band under it says what the sun is doing while the pointer
    is on a sheet. So the sheet itself carries its name, its hour and which
    of a pair it is -- and not the day again, not "the whole day", not the
    sun's figures, and not its name and day a second time in the title block
    at a size nobody can read."""
    paper = tk.Canvas(hidden_window.root)
    window.draw_sheet(paper, WHOLE_DAY_SHEET, 300, 212)
    texts = _texts(paper)
    assert "COMMUNAL OPEN SPACE" in texts
    assert not any("21 Jun" in text or "whole day" in text for text in texts), texts
    assert "Communal open space" not in texts, "the block does not say the title again"

    paper = tk.Canvas(hidden_window.root)
    window.draw_sheet(paper, FOUR_HOUR_SHEET, 300, 212)
    texts = _texts(paper)
    assert "09:00-12:00   (1 of 2)" in texts, "the hours, and which of the pair"
    assert not any("21 Jun" in text or "drawings" in text or "°" in text for text in texts), texts
    assert texts.count("09:00") == 1, "each cell's own hour, once"


def test_the_blue_edge_rims_the_whole_sheet(hidden_window: Any) -> None:
    """The title block is drawn over the paper's right-hand edge, and it was
    drawn over the edge item too: lit blue under the pointer, the rim showed
    on three sides and stopped at the block. The edge is the topmost item
    now, and hollow, so it lies over everything and hides nothing."""
    for sheet, draw in ((WHOLE_DAY_SHEET, window.draw_sheet), (A_MODEL, window.draw_model)):
        paper: Any = tk.Canvas(hidden_window.root)
        draw(paper, sheet, 300, 212)
        (edge,) = paper.find_withtag("edge")
        assert edge == paper.find_all()[-1], f"over everything on {sheet.kind}"
        assert paper.itemcget(edge, "fill") == "", "and hollow, so that it covers nothing"


def test_the_scale_is_set_to_be_read_and_north_is_beside_the_drawings(hidden_window: Any) -> None:
    """A reader checks the block for the scale, so it is set like the sheet
    number and not in the block's five-point grey. And the north arrow is in
    the block: at the top right of the drawing area it sat on the corner
    cell of a sheet carrying four."""
    paper: Any = tk.Canvas(hidden_window.root)
    # A short scale, so the size it is set at is the size it keeps whatever
    # typeface this machine has: a long one is shrunk to fit the strip.
    window.draw_sheet(paper, replace(FOUR_HOUR_SHEET, scale="1:50"), 300, 212)
    block_left = 300 * (1 - 40.0 / window.SHEET_MM_W)
    items = paper.find_all()

    (scale,) = [
        i for i in items if str(paper.type(i)) == "text" and paper.itemcget(i, "text") == "1:50"
    ]
    face = hidden_window.root.tk.splitlist(paper.itemcget(scale, "font"))
    assert int(face[1]) >= 8, face
    assert paper.bbox(scale)[0] >= block_left

    (north,) = [
        i for i in items if str(paper.type(i)) == "text" and paper.itemcget(i, "text") == "N"
    ]
    ring = [i for i in items if str(paper.type(i)) == "oval" and paper.bbox(i)[0] >= block_left]
    assert paper.bbox(north)[0] >= block_left and len(ring) == 1, "in the block, not on a cell"
    cells = [
        i for i in items if str(paper.type(i)) == "rectangle" and paper.bbox(i)[2] < block_left
    ]
    assert all(paper.bbox(i)[2] < paper.bbox(ring[0])[0] for i in cells), "clear of every cell"


def test_each_site_sheet_follows_its_own_tick(hidden_window: Any) -> None:
    """Three sheets, three ticks, and the command gets --no-summary when the
    summary is unticked -- so the panel must drop it too."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_site.set(True)
    hidden_window.site_address.insert(0, "1 Example Street")
    hidden_window.do_site_summary.set(False)
    hidden_window.do_site_context.set(False)

    assert [sheet.kind for sheet in hidden_window.planned()] == ["Site Analysis"]
    args = hidden_window.jobs()[0].args
    assert "--no-summary" in args and "--no-context" in args and "--site" in args


def test_the_pen_set_is_chosen_from_the_projects_own_and_blank_is_kept(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typed, a pen set name was one more thing to misspell. The project's
    pen tables are offered, blank first -- blank keeps each view's own, which
    is what the command does -- and nothing is guessed on the person's behalf."""
    from dataclasses import replace

    found = hidden_window.options
    monkeypatch.setattr(
        probe, "options", lambda port: replace(found, pen_sets=("00 FA Pens", "Archicad"))
    )
    hidden_window.refresh()

    assert list(hidden_window.eye_pen_set.cget("values")) == ["", "00 FA Pens", "Archicad"]
    assert hidden_window.eye_pen_set.get() == "", "blank stays blank"
    assert "--pen-set" not in " ".join(job.args[0] for job in hidden_window.jobs())

    hidden_window.eye_pen_set.set("00 FA Pens")
    hidden_window.do_sun_eyes.set(True)
    assert flag(hidden_window.jobs()[-1].args, "--pen-set") == ["00 FA Pens"]


def test_the_foot_of_the_window_carries_the_licence_not_a_warning(hidden_window: Any) -> None:
    from tkinter import ttk as widgets

    from sun_study import AUTHOR
    from sun_study.licence import EXPIRES, credential

    assert AUTHOR in credential() and str(EXPIRES.year) in credential()

    def labels(parent: Any) -> list[str]:
        found: list[str] = []
        for child in parent.winfo_children():
            if isinstance(child, widgets.Label):
                found.append(str(child.cget("text")))
            found.extend(labels(child))
        return found

    said = labels(hidden_window.root)
    assert credential() in said
    assert not [line for line in said if "PROTOTYPE" in line], "the warning lives on the sheets"


def test_the_reference_image_opens_one_palette_for_the_chosen_project(
    hidden_window: Any,
) -> None:
    """The button above the tabs opens the picture's palette, told which
    project is chosen so that the Archicad window it looks for is that one.
    A second press raises the same palette rather than opening a twin."""
    from sun_study.app import overlay

    hidden_window._reference()
    opened = overlay._open
    assert opened is not None
    try:
        assert opened.project() == "SAMPLE"
        hidden_window._reference()
        assert overlay._open is opened
    finally:
        opened.close()
        hidden_window.root.update()
    assert overlay._open is None


def only_yield(hidden_window: Any) -> None:
    """The yield analysis ticked on its own."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_yield.set(True)


def test_the_yield_page_is_the_command_line_the_office_would_type(
    hidden_window: Any, tmp_path: Path
) -> None:
    only_yield(hidden_window)
    hidden_window.yield_option.delete(0, "end")
    hidden_window.yield_option.insert(0, "Option 02")
    hidden_window.yield_residential.insert(0, "01 | Wall.External")
    hidden_window.yield_retail.insert(0, "01 | Floor.Structural")
    hidden_window.yield_massing.insert(0, "01 | Massing - Main Building.3D OPT2")
    hidden_window.yield_retail_levels.insert(0, "Ground")
    hidden_window.yield_commercial_levels.insert(0, "Level 01, Level 02")
    hidden_window.yield_renovation.set(True)
    hidden_window.yield_site_area.insert(0, "1386.78")
    hidden_window.yield_fsr_residential.insert(0, "2.8")
    hidden_window.yield_fsr_retail.insert(0, "0.4")
    hidden_window.yield_affordable_share.delete(0, "end")
    hidden_window.yield_affordable_share.insert(0, "15")
    hidden_window.yield_view.insert(0, "Yield Axo")
    hidden_window.tables.delete(0, "end")
    hidden_window.tables.insert(0, str(tmp_path))
    hidden_window.site_address.insert(0, "1 Example Street")
    (job,) = hidden_window.jobs()
    args = job.args
    assert job.label == window.YIELD_JOB
    assert args[0] == "yield"
    assert flag(args, "--option") == ["Option 02"]
    assert flag(args, "--residential-layer") == ["01 | Wall.External"]
    assert flag(args, "--retail-layer") == ["01 | Floor.Structural"]
    assert flag(args, "--massing-layer") == ["01 | Massing - Main Building.3D OPT2"]
    assert flag(args, "--retail-level") == ["Ground"]
    assert flag(args, "--commercial-level") == ["Level 01", "Level 02"]
    assert "--renovation-filter" in args
    assert flag(args, "--gfa-residential") == ["0.725"]
    assert flag(args, "--gfa-retail") == ["0.95"]
    assert flag(args, "--nla-commercial") == ["0.9"]
    assert flag(args, "--affordable-share") == ["15"]
    assert flag(args, "--sqm-per-space") == ["40"]
    assert flag(args, "--basement-site-ratio") == ["0.4"]
    assert flag(args, "--site-area") == ["1386.78"]
    assert flag(args, "--fsr-residential") == ["2.8"] and flag(args, "--fsr-retail") == ["0.4"]
    assert "--fsr-commercial" not in args
    assert "--address" not in args, "the site and the permissible FSR are both typed"
    # Every type goes, the two at nothing included: the sheet keeps their rows.
    assert flag(args, "--unit") == [
        "Studio=0,35",
        "1-bed=20,50",
        "2-bed=70,75",
        "3-bed=10,100",
        "4-bed=0,120",
    ]
    assert flag(args, "--view") == ["Yield Axo"]
    assert flag(args, "--xlsx") == [str(tmp_path / window.AREA_TABLE)]
    assert flag(args, "--port") == ["19723"]
    assert "--option-layer" not in args


def test_the_workbook_is_chosen_with_a_save_dialog(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Not typed: a Save dialog, opened in the tables folder with the
    workbook's own name, and the answer shown in the box."""
    from tkinter import filedialog

    only_yield(hidden_window)
    hidden_window.tables.delete(0, "end")
    hidden_window.tables.insert(0, str(tmp_path))
    asked: dict[str, Any] = {}

    def save(**kwargs: Any) -> str:
        asked.update(kwargs)
        return str(tmp_path / "Yield.xlsx")

    monkeypatch.setattr(filedialog, "asksaveasfilename", save)
    hidden_window._browse_file(
        hidden_window.yield_workbook, "Workbook", (("Excel workbook", "*.xlsx"),), "Default.xlsx"
    )
    assert asked["initialdir"] == str(tmp_path) and asked["initialfile"] == "Default.xlsx"
    assert asked["filetypes"] == [("Excel workbook", "*.xlsx")]
    assert hidden_window.yield_workbook.get() == str(tmp_path / "Yield.xlsx")
    (job,) = hidden_window.jobs()
    assert flag(job.args, "--xlsx") == [str(tmp_path / "Yield.xlsx")]
    # Cancelled: the box keeps what it had.
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **_k: "")
    hidden_window._browse_file(hidden_window.yield_workbook, "Workbook", (), "x")
    assert hidden_window.yield_workbook.get() == str(tmp_path / "Yield.xlsx")


def test_option_layers_and_a_workbook_of_their_own(hidden_window: Any, tmp_path: Path) -> None:
    only_yield(hidden_window)
    hidden_window.yield_option_layers.insert(0, "01 | Massing.3D OPT1, 01 | Massing.3D OPT2")
    hidden_window.yield_workbook.insert(0, r"P:³3\Yield.xlsx")
    hidden_window.tables.delete(0, "end")
    hidden_window.tables.insert(0, str(tmp_path))
    (job,) = hidden_window.jobs()
    assert flag(job.args, "--option-layer") == ["01 | Massing.3D OPT1", "01 | Massing.3D OPT2"]
    assert flag(job.args, "--xlsx") == [r"P:³3\Yield.xlsx"], "the typed path over the folder"
    hidden_window.yield_xlsx.set(False)
    (job,) = hidden_window.jobs()
    assert "--xlsx" not in job.args
    saved = hidden_window.settings()
    assert saved["yield_xlsx"] is False and saved["yield_workbook"] == r"P:³3\Yield.xlsx"


def test_what_the_yield_page_does_not_say_about_the_site_is_read_at_the_address(
    hidden_window: Any,
) -> None:
    only_yield(hidden_window)
    hidden_window.site_address.insert(0, "1 Example Street")
    (job,) = hidden_window.jobs()
    assert flag(job.args, "--address") == ["1 Example Street"]
    assert "--renovation-filter" not in job.args
    assert "--residential-layer" not in job.args, "empty counts what is showing"
    assert flag(job.args, "--option") == ["Option 01"]


def test_a_studio_given_a_share_joins_the_mix_at_its_size(hidden_window: Any) -> None:
    only_yield(hidden_window)
    share, size = hidden_window.yield_mix["Studio"]
    share.delete(0, "end")
    share.insert(0, "10%")
    size.delete(0, "end")
    (job,) = hidden_window.jobs()
    assert flag(job.args, "--unit")[0] == "Studio=10,35", "a blank size is the row's own"


def test_the_yield_analysis_is_one_sheet_in_the_panel(hidden_window: Any) -> None:
    only_yield(hidden_window)
    (sheet,) = hidden_window.planned()
    assert (sheet.study, sheet.number, sheet.kind) == ("Yield", "AC.01", window.AREA_SHEET)
    assert sheet.paper and not sheet.time
    assert "massing slabs" in window._untimed_note(sheet)


def test_the_yield_page_is_saved_and_restored(hidden_window: Any) -> None:
    only_yield(hidden_window)
    hidden_window.yield_commercial.insert(0, "01 | Floor.Structural")
    hidden_window.yield_gfa_residential.delete(0, "end")
    hidden_window.yield_gfa_residential.insert(0, "0.8")
    saved = hidden_window.settings()
    assert saved["study_yield"] is True
    assert saved["yield_gfa_residential"] == "0.8"
    assert saved["yield_commercial_layers"] == "01 | Floor.Structural"
    assert saved["yield_mix_2-bed_share"] == "70"
    assert saved["yield_option"] == "Option 01"
    hidden_window.apply({**saved, "yield_gfa_residential": "0.7", "yield_renovation": True})
    assert hidden_window.yield_gfa_residential.get() == "0.7"
    assert hidden_window.yield_renovation.get() is True


def test_a_typed_hour_is_spelled_the_way_the_sheet_is_named() -> None:
    assert [window._clock_text(word) for word in ("9", "9am", "3pm", "09:30", "12", "noon")] == [
        "09:00",
        "09:00",
        "15:00",
        "09:30",
        "12:00",
        "noon",
    ]


def test_the_thumbnail_grid_is_the_runs_grid() -> None:
    """Four drawings are two by two and not four across, which is the rule
    the run lays a sheet out by; the panel copies it rather than choosing its
    own, or the thumbnail shows a row where the sheet has a block."""
    area = (0.0, 0.0, 200.0, 160.0)
    four = window._grid(4, area)
    assert len({round(cell[0]) for cell in four}) == 2, "two columns"
    assert len({round(cell[1]) for cell in four}) == 2, "two rows"
    three = window._grid(3, area)
    assert len({round(cell[0]) for cell in three}) == 3, "three across, none wasted"
    assert window._grid(0, area) == []


# -- presets: the page in a file of the person's choosing -----------------


def test_a_preset_is_the_page_in_a_file_and_comes_back_from_it(
    hidden_window: Any, settings_file: Path, tmp_path: Path
) -> None:
    """The Silverwater setup, saved beside the job and loaded on the next desk.
    The saved defaults are not touched by either half of the trip."""
    hidden_window.prefix_solar.delete(0, "end")
    hidden_window.prefix_solar.insert(0, "99 |")
    hidden_window.do_plans.set(True)
    where = tmp_path / "job" / "silverwater.json"

    assert hidden_window.save_preset(where) == where
    assert where.is_file()
    assert not settings_file.exists(), "a preset is not the defaults"

    hidden_window.apply(hidden_window.factory)
    assert hidden_window.prefix_solar.get() != "99 |", "back to the defaults first"

    assert hidden_window.load_preset(where) is True
    assert hidden_window.prefix_solar.get() == "99 |"
    assert hidden_window.do_plans.get() is True
    assert "silverwater.json" in hidden_window.lines[-1]


def test_a_preset_and_the_defaults_are_one_file_format(
    hidden_window: Any, settings_file: Path, tmp_path: Path
) -> None:
    """So a preset copied over settings.json is the defaults, and the
    defaults copied out are a preset somebody can send on."""
    hidden_window.livable.insert(0, "_L")
    where = hidden_window.save_preset(tmp_path / "preset.json")
    assert where is not None

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_bytes(where.read_bytes())

    assert preferences.load()["livable_suffix"] == "_L"


def test_a_file_that_is_not_a_preset_is_reported_not_raised(
    hidden_window: Any, tmp_path: Path
) -> None:
    """The person chose the file and wants to know why it did not take. A
    window that closes over a wrong file is the worse answer, and a window
    that silently loads nothing is the next worse."""
    before = hidden_window.settings()
    notes = tmp_path / "notes.json"
    notes.write_text("{ this is not json", encoding="utf-8")

    assert hidden_window.load_preset(notes) is False
    assert "Could not load notes.json" in hidden_window.lines[-1]
    assert hidden_window.load_preset(tmp_path / "missing.json") is False
    assert "missing.json" in hidden_window.lines[-1]

    notes.write_text('["a list, not a mapping"]', encoding="utf-8")
    assert hidden_window.load_preset(notes) is False
    assert hidden_window.settings() == before, "and nothing on the page moved"


def test_a_preset_from_another_job_is_overruled_by_the_open_project(
    hidden_window: Any, tmp_path: Path
) -> None:
    """The one way a loaded setting could make a run measure the wrong thing,
    closed the same way it is for the saved defaults: the project drops what
    it does not have, says so, and fills the emptied field itself."""
    where = tmp_path / "elsewhere.json"
    preferences.write(where, {"subject_layers": "01 | Wall.External, 09 | SOMEBODY ELSE'S SLABS"})

    assert hidden_window.load_preset(where) is True

    assert hidden_window._listed(hidden_window.subject) == ["01 | Wall.External"]
    assert "SOMEBODY ELSE" in "\n".join(hidden_window.lines), "and it is said out loud"


def test_a_preset_that_cannot_be_written_is_said_not_raised(
    hidden_window: Any, tmp_path: Path
) -> None:
    """A folder that is a file: the nearest a test can get to a locked share."""
    blocked = tmp_path / "blocked"
    blocked.write_text("in the way", encoding="utf-8")

    assert hidden_window.save_preset(blocked / "preset.json") is None
    assert "Could not save the preset" in hidden_window.lines[-1]


def test_the_preset_buttons_wear_their_own_pictures(hidden_window: Any) -> None:
    """Two more sheets in the run bar, told apart by which way the arrow
    goes. A button without its picture is a button that was renamed in one
    place and not the other."""
    assert icons.named("save_preset", 16) is not None
    assert icons.named("load_preset", 16) is not None


def test_a_project_with_no_location_draws_the_sheet_and_says_it_has_no_sun(
    hidden_window: Any,
) -> None:
    """A shadow at a guessed latitude is a drawing that looks right and is
    not, which is the one thing this window exists to prevent."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)

    without = hidden_window.planned()
    assert without, "the sheets are still listed"
    assert all(sheet.elevation is None for sheet in without)
    assert all(sheet.reach is None for sheet in without), "and nothing to draw with"

    hidden_window.options = replace(hidden_window.options, latitude=-33.9663, longitude=151.1340)
    hidden_window.days["winter"].set(True)
    hidden_window.custom_day.delete(0, "end")
    hidden_window.shadow_hours.delete(0, "end")
    hidden_window.shadow_hours.insert(0, "12:00")

    noon = hidden_window.planned()[0]

    # Winter noon at latitude -34: the sun is due north, 90 - 34 - 23.44 up.
    assert noon.elevation is not None
    assert abs(noon.elevation - 32.6) < 0.5, f"sun at {noon.elevation}"
    assert abs(noon.azimuth - 0.0) % 360 < 2 or abs(noon.azimuth - 360.0) < 2
    assert noon.reach is not None and abs(noon.reach - 1.56) < 0.05


# -- the add-on everything depends on -------------------------------------


def test_a_missing_add_on_is_told_apart_from_a_dead_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Archicad answering with no add-on is a different thing from nothing
    listening, and needs a different sentence: one is "open a project", the
    other is "install this"."""
    from sun_study.archicad.connection import TapirUnavailableError

    class NoAddOn:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        @property
        def tapir_version(self) -> str:
            raise TapirUnavailableError("no add-on response")

    monkeypatch.setattr(probe, "ArchicadConnection", NoAddOn)
    found = probe.options(19723)

    assert found.tapir_missing is True
    assert found.reachable is False
    assert "Tapir" in found.problems[0]


def test_run_is_switched_off_when_the_add_on_is_absent(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """116 of the tool's 124 Archicad calls are Tapir commands, so this is not
    a degraded run, it is no run at all. Better refused here than failed
    several steps in."""
    monkeypatch.setattr(probe, "options", lambda port: probe.ProjectOptions(tapir_missing=True))
    hidden_window.refresh()

    assert str(hidden_window.go.cget("state")) == "disabled"
    assert "not installed" in hidden_window.status.cget("text")


def test_the_add_on_version_is_shown_because_support_always_asks(
    hidden_window: Any,
) -> None:
    assert "Tapir" in hidden_window.status.cget("text")


# -- picking layers instead of typing them --------------------------------

LAYERS = (
    "01 ------------------------------ STRUCTURAL/MODEL",
    "01 | Wall.External",
    "01 | Floor.Structural",
    "06 ------------------------------ ZONES",
    "06 | Zone.Units",
)


def test_the_palettes_own_dividers_are_not_offered_as_layers() -> None:
    """They sort to the top of a search, hold nothing, and are the likeliest
    thing to tick: searching "zone" offered the divider before the zones."""
    from sun_study.app.window import pickable

    assert pickable(LAYERS) == [
        "01 | Wall.External",
        "01 | Floor.Structural",
        "06 | Zone.Units",
    ]


def test_a_project_without_dividers_loses_nothing() -> None:
    from sun_study.app.window import pickable

    plain = ("Walls", "Floors")
    assert pickable(plain) == list(plain)


def test_every_word_matches_anywhere_so_nobody_has_to_recall_the_format() -> None:
    """Layer names carry a group number, a bar, a dot and a space. Making
    somebody reproduce that order is a memory test, not a search."""
    from sun_study.app.window import matching, pickable

    names = pickable(LAYERS)
    assert matching(names, "floor str") == ["01 | Floor.Structural"]
    assert matching(names, "STRUCTURAL floor") == ["01 | Floor.Structural"]
    assert matching(names, "") == names
    assert matching(names, "nothing here") == []


def test_a_tick_survives_the_search_that_hides_it(hidden_window: Any) -> None:
    """Narrowing the list must not quietly untick what scrolled out of sight,
    which is how a facade study loses a slab layer nobody noticed choosing."""
    from sun_study.app.window import LayerChooser

    chooser = LayerChooser(
        hidden_window.root,
        title="Facade layers",
        hint="pick them",
        available=["01 | Wall.External", "01 | Floor.Structural"],
        chosen=["01 | Wall.External"],
    )
    chooser.query.insert(0, "floor")
    chooser._repaint()
    assert list(chooser._boxes) == ["01 | Floor.Structural"], "the wall is filtered out"

    chooser._accept()
    assert chooser.result == ["01 | Wall.External"], "and still chosen"
    chooser.destroy()


def test_cancelling_is_told_apart_from_choosing_nothing(hidden_window: Any) -> None:
    """Both leave an empty list. Only one of them should overwrite the field."""
    from sun_study.app.window import LayerChooser

    cancelled = LayerChooser(
        hidden_window.root,
        title="Facade layers",
        hint="pick them",
        available=["01 | Wall.External"],
        chosen=["01 | Wall.External"],
    )
    cancelled.destroy()
    assert cancelled.result is None

    emptied = LayerChooser(
        hidden_window.root,
        title="Facade layers",
        hint="pick them",
        available=["01 | Wall.External"],
        chosen=["01 | Wall.External"],
    )
    emptied._clear()
    emptied._accept()
    assert emptied.result == []


def test_the_chosen_come_back_in_the_projects_order(hidden_window: Any) -> None:
    """Not in the order somebody happened to click, so the field can be read
    against the layer palette."""
    from sun_study.app.window import LayerChooser

    chooser = LayerChooser(
        hidden_window.root,
        title="Facade layers",
        hint="pick them",
        available=["01 | Wall.External", "01 | Floor.Structural", "06 | Zone.Units"],
        chosen=["06 | Zone.Units", "01 | Wall.External"],
    )
    chooser._accept()
    assert chooser.result == ["01 | Wall.External", "06 | Zone.Units"]
    chooser.destroy()


def test_a_project_that_will_not_answer_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A window that dies on a bad port is worse than one that says so."""
    from sun_study.archicad.connection import ArchicadError

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise ArchicadError("nothing listening")

    monkeypatch.setattr(probe, "ArchicadConnection", refuse)
    found = probe.options(19999)

    assert found.reachable is False
    assert found.problems and "19999" in found.problems[0]


def test_the_child_is_told_to_be_the_command_line_and_not_to_buffer() -> None:
    """A progress line held in a pipe buffer for four minutes is worse than no
    progress line, and the window renders text rather than ANSI escapes."""
    env = child_environment()
    assert env[CLI_MARKER] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["NO_COLOR"] == "1"


def test_unpackaged_runs_the_module_and_packaged_runs_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A packaged app is one executable: sys.executable is the app, not a
    Python that can be asked for -m sun_study.cli."""
    monkeypatch.delattr("sys.frozen", raising=False)
    assert command_prefix()[1:] == ["-u", "-m", "sun_study.cli"]

    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert len(command_prefix()) == 1


# ---------------------------------------------------------------------------
# Which zones are apartments, and which are somebody's balcony.
# ---------------------------------------------------------------------------
def test_the_dwellings_and_the_balconies_are_told_apart_by_size(hidden_window: Any) -> None:
    """The names are an office's own codes and mean nothing outside it. The
    sizes mean the same thing everywhere: a flat is tens of square metres, a
    balcony is a few, a storage cupboard is less."""
    assert hidden_window.apartment_names.get() == "G08"
    assert hidden_window.balconies.get() == "06 | Zone.Units"
    assert hidden_window.balcony_names.get() == "BY"


def test_the_zones_that_are_neither_are_left_out(hidden_window: Any) -> None:
    """A 2.5 m2 storage cupboard is not a dwelling and not private open space,
    and counted as either it is a wrong number rather than a missing one."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    (plans,) = hidden_window.jobs()

    assert "SC" not in flag(plans.args, "--apartment-zone-name")
    assert "SC" not in flag(plans.args, "--open-space-zone-name")


def test_the_plans_run_says_which_zones_are_apartments(hidden_window: Any) -> None:
    """Without this the layer alone decides, and this layer carries 15
    dwellings, 20 balconies and the storage. Two thirds of what it would
    assess has no living room, so the building fails on zones nobody lives
    in."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    (plans,) = hidden_window.jobs()

    assert flag(plans.args, "--apartment-zone-layer") == ["06 | Zone.Units"]
    assert flag(plans.args, "--apartment-zone-name") == ["G08"]


def test_the_plans_run_says_which_zones_are_the_open_space(hidden_window: Any) -> None:
    """The other half of the ADG test. With none named, every apartment is
    assessed on its living room alone and the result is worse than the
    building is."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    (plans,) = hidden_window.jobs()

    assert flag(plans.args, "--open-space-zone-layer") == ["06 | Zone.Units"]
    assert flag(plans.args, "--open-space-zone-name") == ["BY"]


def test_an_unnarrowed_balcony_layer_is_not_passed_at_all(hidden_window: Any) -> None:
    """Naming the apartments' own layer as the open space, with no names to
    narrow it, would take every apartment for a balcony and leave the
    assessment with no apartments in it."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    hidden_window.balcony_names.delete(0, "end")
    (plans,) = hidden_window.jobs()

    assert flag(plans.args, "--open-space-zone-layer") == []


def test_a_balcony_layer_of_its_own_needs_no_names(hidden_window: Any) -> None:
    """Where the practice keeps its balconies on a layer of their own, the
    layer is the whole answer."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    hidden_window.balconies.set("06 | Zone.Balcony")
    hidden_window.balcony_names.delete(0, "end")
    (plans,) = hidden_window.jobs()

    assert flag(plans.args, "--open-space-zone-layer") == ["06 | Zone.Balcony"]


def test_the_living_room_glazing_is_only_named_when_it_is_set(hidden_window: Any) -> None:
    """It replaces the room-name route rather than narrowing it, so passing an
    empty one would be a different study, not a tidier command line."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    assert flag(hidden_window.jobs()[0].args, "--livable-suffix") == []

    hidden_window.livable.insert(0, "_L")
    assert flag(hidden_window.jobs()[0].args, "--livable-suffix") == ["_L"]


# ---------------------------------------------------------------------------
# The prefix everything created is named with.
# ---------------------------------------------------------------------------
def test_both_runs_are_told_the_same_layer_prefix(hidden_window: Any) -> None:
    """One field, and every layer, view and sheet either run leaves behind
    carries it -- so all of it can be found, and deleted, in one search."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.do_plans.set(True)
    facade, plans = hidden_window.jobs()

    assert flag(facade.args, "--layer-prefix") == ["14 |"]
    assert flag(plans.args, "--layer-prefix") == ["14 |"]


def test_the_archicad_wait_reaches_both_runs_in_seconds(hidden_window: Any) -> None:
    """Minutes on screen, seconds on the command line.

    The field exists because five minutes was not enough for a 455 MB export
    and there was no way to say so from the window -- the run stopped partway,
    having already done the slow part.
    """
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.do_plans.set(True)
    hidden_window.wait_min.delete(0, "end")
    hidden_window.wait_min.insert(0, "45")
    facade, plans = hidden_window.jobs()

    assert flag(facade.args, "--timeout") == ["2700"]
    assert flag(plans.args, "--timeout") == ["2700"]


@pytest.mark.parametrize("typed", ["", "   ", "half an hour", "0", "-5"])
def test_a_wait_that_is_not_a_number_falls_back_rather_than_stopping_the_study(
    hidden_window: Any, typed: str
) -> None:
    """A mistyped wait is not a reason to refuse a run. The command line's own
    default is right for every project but the largest, so it is what an
    unreadable field means."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.wait_min.delete(0, "end")
    hidden_window.wait_min.insert(0, typed)
    (facade,) = hidden_window.jobs()

    assert flag(facade.args, "--timeout") == ["1800"]


def test_reading_the_project_does_not_wait_the_exports_wait() -> None:
    """The window fills its lists in while somebody watches. Inheriting the
    half-hour meant for the export would hang it on an Archicad that is merely
    busy, so the reads keep a wait of their own."""
    assert probe.READING_SECONDS < DEFAULT_TIMEOUT_SECONDS


def test_another_offices_numbering_reaches_the_command_line(hidden_window: Any) -> None:
    """``14`` is right for a project whose layer groups end at 13. The next
    office numbers differently, which is the whole reason for the field."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.prefix_solar.delete(0, "end")
    hidden_window.prefix_solar.insert(0, "ZZ |")
    (facade,) = hidden_window.jobs()

    assert flag(facade.args, "--layer-prefix") == ["ZZ |"]


def test_each_tool_files_its_work_under_its_own_number(hidden_window: Any) -> None:
    """Four drawings, four numbers. Under one prefix the layer list ran the
    apartment results, the shadow sheets, the sun views and the site analysis
    together, and only the group word after the number told them apart.

    The solar analysis keeps 14 so nothing already drawn moves; the rest step
    up from it. Read off the argv rather than the boxes, because the argv is
    what Archicad ends up being told.
    """
    hidden_window.do_facade.set(True)
    hidden_window.do_plans.set(True)
    hidden_window.do_shadows.set(True)
    hidden_window.do_sun_eyes.set(True)
    hidden_window.do_site.set(True)
    hidden_window.site_address.insert(0, "212 Bondi Rd, Bondi")

    under = {job.label: flag(job.args, "--layer-prefix") for job in hidden_window.jobs()}

    assert under[window.FACADE_JOB] == [naming.SOLAR_PREFIX]
    assert under[window.PLANS_JOB] == [naming.SOLAR_PREFIX]
    assert under[window.SHADOW_JOB] == [naming.SHADOW_PREFIX]
    assert under[window.SUN_EYE_JOB] == [naming.SUN_VIEW_PREFIX]
    assert under[window.SITE_JOB] == [naming.SITE_PREFIX]
    assert len({naming.SHADOW_PREFIX, naming.SUN_VIEW_PREFIX, naming.SITE_PREFIX}) == 3, (
        "three tools sharing a number is the thing this is here to prevent"
    )


def test_one_tool_renumbered_leaves_the_others_where_they_were(hidden_window: Any) -> None:
    """The boxes are independent, which is the point of there being four.
    Somebody whose project already uses 15 moves the shadow diagram alone."""
    hidden_window.do_shadows.set(True)
    hidden_window.do_sun_eyes.set(True)
    hidden_window.prefix_shadow.delete(0, "end")
    hidden_window.prefix_shadow.insert(0, "25 |")

    under = {job.label: flag(job.args, "--layer-prefix") for job in hidden_window.jobs()}

    assert under[window.SHADOW_JOB] == ["25 |"]
    assert under[window.SUN_EYE_JOB] == [naming.SUN_VIEW_PREFIX], "and the sun views did not follow"


def test_an_emptied_prefix_box_leaves_the_tool_its_own_default(hidden_window: Any) -> None:
    """Empty means "whatever the command already defaults to", not an empty
    prefix -- the CLI refuses that, since it matches every layout there is."""
    hidden_window.do_shadows.set(True)
    hidden_window.prefix_shadow.delete(0, "end")

    (shadow,) = [job for job in hidden_window.jobs() if job.label == window.SHADOW_JOB]

    assert flag(shadow.args, "--layer-prefix") == []
    assert "--layer-prefix" not in shadow.args


def test_the_site_group_reaches_only_the_command_that_makes_the_context(
    hidden_window: Any,
) -> None:
    """The office's site group is not one of the tool's four numbers, and only
    the site command creates the context that goes in it. Passing it to the
    others would be an option they do not have."""
    hidden_window.do_site.set(True)
    hidden_window.do_shadows.set(True)
    hidden_window.site_address.insert(0, "212 Bondi Rd, Bondi")
    hidden_window.prefix_context.delete(0, "end")
    hidden_window.prefix_context.insert(0, "50 |")

    by_tool = {job.label: job.args for job in hidden_window.jobs()}

    assert flag(by_tool[window.SITE_JOB], "--context-prefix") == ["50 |"]
    assert "--context-prefix" not in by_tool[window.SHADOW_JOB]
    assert flag(by_tool[window.SITE_JOB], "--layer-prefix") == [naming.SITE_PREFIX], (
        "and the site analysis is still filed under its own number"
    )


def test_a_zone_is_offered_under_both_of_the_names_archicad_gives_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The IFC export puts one of them in ``Name`` and the other in
    ``LongName``, and which is which varies by translator. The assessment
    matches either, so offering both means a person picking from the list is
    right whichever way round their project has it."""
    from sun_study.archicad import read
    from sun_study.archicad.read import ArchicadZone

    def square(side: float) -> tuple[tuple[float, float], ...]:
        return ((0.0, 0.0), (side, 0.0), (side, side), (0.0, side))

    monkeypatch.setattr(read, "layer_names", lambda _c: {4: "06 | Zone.Units"})
    monkeypatch.setattr(read, "zone_categories", lambda _c: {})
    monkeypatch.setattr(
        read,
        "zones",
        lambda _c: (
            ArchicadZone(guid="a", name="3B", number="G08", outline=square(8.0), layer_index=4),
            ArchicadZone(guid="b", name="3B", number="G08", outline=square(9.0), layer_index=4),
            ArchicadZone(guid="c", name="BALC", number="BY", outline=square(3.0), layer_index=4),
            # No layer, so it cannot be attributed and is not offered.
            ArchicadZone(guid="d", name="LOOSE", number="", outline=square(9.0)),
        ),
    )

    layers, kinds = probe._zones_by_layer(object())  # type: ignore[arg-type]
    by_label = {kind.label: kind for kind in kinds}

    assert layers == ("06 | Zone.Units",)
    assert set(by_label) == {"3B", "G08", "BALC", "BY"}
    assert by_label["G08"].count == 2
    assert by_label["G08"].area_m2 == pytest.approx(72.5)  # the median of 64 and 81
    assert by_label["G08"].dwelling and not by_label["G08"].open_space
    assert by_label["BY"].open_space and not by_label["BY"].dwelling
    assert "LOOSE" not in by_label


def test_each_zone_name_says_its_zone_category(monkeypatch: pytest.MonkeyPatch) -> None:
    """``G08`` and ``BY`` are codes to anybody who did not model the project;
    ``Apartment`` and ``Balcony`` are not. The category most of a name's
    zones carry is shown beside it in the chooser."""
    from sun_study.archicad import read
    from sun_study.archicad.read import ArchicadZone

    square = ((0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0))
    small = ((0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0))
    monkeypatch.setattr(read, "layer_names", lambda _c: {4: "06 | Zone.Units"})
    monkeypatch.setattr(
        read, "zone_categories", lambda _c: {"CAT-A": "Apartment", "CAT-B": "Balcony"}
    )
    monkeypatch.setattr(
        read,
        "zones",
        lambda _c: (
            ArchicadZone("a", "", "G08", outline=square, layer_index=4, category_guid="cat-a"),
            ArchicadZone("b", "", "G08", outline=square, layer_index=4, category_guid="CAT-A"),
            ArchicadZone("c", "", "BY", outline=small, layer_index=4, category_guid="CAT-B"),
            ArchicadZone("d", "", "SC", outline=small, layer_index=4),
        ),
    )

    _, kinds = probe._zones_by_layer(object())  # type: ignore[arg-type]
    by_label = {kind.label: kind for kind in kinds}

    assert by_label["G08"].category == "Apartment", "GUIDs are matched without regard to case"
    assert by_label["BY"].category == "Balcony"
    assert by_label["SC"].category == ""
    assert "Apartment" in by_label["G08"].described()
    assert by_label["SC"].described().startswith("SC (")


def test_a_project_whose_categories_cannot_be_read_still_offers_its_zones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sun_study.archicad import read
    from sun_study.archicad.connection import ArchicadError
    from sun_study.archicad.read import ArchicadZone

    def refuse(_c: object) -> dict[str, str]:
        raise ArchicadError("no ZoneCategory here")

    monkeypatch.setattr(read, "layer_names", lambda _c: {4: "06 | Zone.Units"})
    monkeypatch.setattr(read, "zone_categories", refuse)
    monkeypatch.setattr(
        read,
        "zones",
        lambda _c: (ArchicadZone("a", "", "G08", outline=((0, 0), (8, 0), (8, 8)), layer_index=4),),
    )

    _, kinds = probe._zones_by_layer(object())  # type: ignore[arg-type]

    assert [kind.label for kind in kinds] == ["G08"]


def test_the_biggest_zones_are_listed_first_because_they_are_what_is_wanted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Somebody opening the list is looking for the apartments, and they are
    the largest thing a zone layer holds."""
    from sun_study.archicad import read
    from sun_study.archicad.read import ArchicadZone

    def square(side: float) -> tuple[tuple[float, float], ...]:
        return ((0.0, 0.0), (side, 0.0), (side, side), (0.0, side))

    monkeypatch.setattr(read, "layer_names", lambda _c: {1: "06 | Zone.Units"})
    monkeypatch.setattr(read, "zone_categories", lambda _c: {})
    monkeypatch.setattr(
        read,
        "zones",
        lambda _c: (
            ArchicadZone(guid="a", name="SC", number="", outline=square(1.5), layer_index=1),
            ArchicadZone(guid="b", name="G08", number="", outline=square(8.0), layer_index=1),
            ArchicadZone(guid="c", name="BY", number="", outline=square(3.0), layer_index=1),
        ),
    )

    _, kinds = probe._zones_by_layer(object())  # type: ignore[arg-type]

    assert [kind.label for kind in kinds] == ["G08", "BY", "SC"]


# ---------------------------------------------------------------------------
# Stopping a run, and what it owes the project on the way out.
# ---------------------------------------------------------------------------
#: A stand-in for a run: it holds something it must give back, and it is
#: *executing* while it waits rather than sleeping in one call. That is not
#: incidental. On Windows a pending interrupt is delivered between bytecodes,
#: so a single long ``time.sleep`` swallows it until the sleep is over --
#: measured at 10 s of 10 -- while a run doing work takes it at the next call
#: boundary, measured at 1.01 s of a 10 s wait.
HOLDS_THE_LAYERS = """
import time
from sun_study.cli import listen_for_stop

listen_for_stop()
print("holding the layer state", flush=True)
try:
    for _ in range(1200):
        time.sleep(0.05)
except KeyboardInterrupt:
    print("put the layers back", flush=True)
"""


def test_a_stopped_run_puts_the_project_back_before_it_goes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of the Stop button. A run holds the project at the
    export's layer state and restores it in a ``finally``; a process that is
    merely killed never reaches it, and Windows ``terminate()`` is
    ``TerminateProcess``, which kills. So the stop arrives as a signal the run
    can unwind from, and this is the proof it does.
    """
    import sys
    import time

    from sun_study.app import runner

    monkeypatch.setattr(runner, "command_prefix", lambda: [sys.executable, "-u"])
    said: list[str] = []
    ended: list[int] = []
    run = runner.Run(["-c", HOLDS_THE_LAYERS], on_line=said.append, on_done=ended.append)
    run.start()

    deadline = time.monotonic() + 30.0
    while "holding the layer state" not in said and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "holding the layer state" in said, said

    asked_at = time.monotonic()
    run.stop()
    while run.running and time.monotonic() < deadline:
        time.sleep(0.05)
    took = time.monotonic() - asked_at

    assert "put the layers back" in said, said
    assert ended, "the run never reported that it had finished"
    # Comfortably inside the grace period, which is what says the run stopped
    # because it was asked rather than because it was killed at the deadline.
    assert took < runner.GRACE_SECONDS / 2, f"took {took:.1f}s to come back"


def test_the_stop_signal_becomes_an_exception_the_finally_blocks_answer_to() -> None:
    """Installed rather than relied on: neither signal's default disposition
    unwinds, so without this the handlers are the operating system's and the
    layer state is lost whichever way the run is stopped."""
    import signal

    from sun_study.cli import listen_for_stop

    before = {
        name: signal.getsignal(getattr(signal, name))
        for name in ("SIGTERM", "SIGBREAK", "SIGINT")
        if hasattr(signal, name)
    }
    try:
        listen_for_stop()
        for name in before:
            handler = signal.getsignal(getattr(signal, name))
            assert callable(handler), f"{name} left at its default"
            with pytest.raises(KeyboardInterrupt):
                handler(getattr(signal, name), None)
    finally:
        for name, handler in before.items():
            signal.signal(getattr(signal, name), handler)


# ---------------------------------------------------------------------------
# The application icon.
# ---------------------------------------------------------------------------
def test_the_icon_ships_with_every_size_windows_asks_for() -> None:
    """One .ico, seven sizes.

    Windows asks at 16 in the title bar, 32 in the task bar, 48 in a folder
    and 256 in Alt-Tab, and an .ico carrying only the big one is resampled
    down to a smear at the size somebody actually sees most often.
    """
    import struct

    found = window.icon_path()
    assert found is not None, "the icon must be in the checkout, not just the build"

    raw = found.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", raw[:6])
    assert (reserved, kind) == (0, 1), "not an .ico at all"

    sizes = {struct.unpack("<BB", raw[6 + i * 16 : 8 + i * 16]) for i in range(count)}
    widths = {width or 256 for width, _ in sizes}
    assert {16, 32, 48, 256} <= widths, f"missing a size Windows asks for: {sorted(widths)}"


def test_a_checkout_with_no_icon_still_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    """How the window looks, not whether the study runs."""
    monkeypatch.setattr(window, "icon_path", lambda: None)
    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - Tk present but with no init.tcl
        pytest.skip("no display for Tk")
    root.withdraw()
    try:
        window.wear_the_icon(root)
    finally:
        root.destroy()


def test_the_window_is_dressed_before_it_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--icon`` at build time reaches Explorer and the task bar and never
    reaches Tk. Without this the .exe carries the right icon in the folder and
    opens a window wearing the Tk feather, which is the half a job somebody
    notices immediately.

    ``default=`` rather than a plain call, so the dialogs and message boxes
    raised later inherit it instead of each needing to be found.
    """
    worn: list[dict[str, Any]] = []

    class Fake:
        def iconbitmap(self, **kwargs: Any) -> None:
            worn.append(kwargs)

    window.wear_the_icon(Fake())  # type: ignore[arg-type]

    assert worn, "the window was never given the icon"
    assert worn[0]["default"].endswith("loriini.ico")


def test_the_packaged_build_looks_where_it_unpacked_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A --onefile build unpacks to a fresh temp directory on every start, so
    the icon is neither beside the .exe nor beside the module -- it is
    wherever ``sys._MEIPASS`` points this time."""
    bundled = tmp_path / "assets" / "loriini.ico"
    bundled.parent.mkdir()
    bundled.touch()  # icon_path only asks whether it is there
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert window.icon_path() == bundled


# -- a form taller than the screen ----------------------------------------


def in_a_section(hidden_window: Any, widget: tk.Misc) -> bool:
    """Whether that widget sits inside one of the scrolling section panes."""
    above: Any = widget
    while above is not None:
        if above in hidden_window.panes:
            return True
        above = getattr(above, "master", None)
    return False


def test_the_settings_scroll_and_the_run_button_does_not(hidden_window: Any) -> None:
    """Sections shorten the page but do not fix it -- Solar analysis alone is
    three studies and a dozen questions, each with its explanation underneath,
    and no laptop shows that at once -- so every section scrolls. Run, the
    progress bar and the line a run reports itself on do not: a note that
    scrolls out of view is a note nobody reads, and Run somewhere down a long
    page is worse than a Run that never moves.
    """
    assert in_a_section(hidden_window, hidden_window.prefix_solar), "a setting in General"
    assert in_a_section(hidden_window, hidden_window.grid_m), "and one in Facade skin"
    assert in_a_section(hidden_window, hidden_window.communal_grid), "and one in Solar diagrams"
    assert not in_a_section(hidden_window, hidden_window.go), "Run must stay where it is"
    assert not in_a_section(hidden_window, hidden_window.note), "and so must what it says"
    assert not in_a_section(hidden_window, hidden_window.instance), (
        "and so must the project it all runs against"
    )


def test_the_wheel_moves_the_page(hidden_window: Any) -> None:
    """A scroll bar nobody can reach with the wheel is half a fix."""
    form = hidden_window.panes[0]
    form.canvas.configure(scrollregion=(0, 0, 100, 4000), yscrollincrement=10)

    form.spin(-120)  # one notch down
    assert form.canvas.yview()[0] > 0.0

    form.spin(120)  # and back up
    assert form.canvas.yview()[0] == 0.0


def test_a_page_that_fits_does_not_slide_off_the_top(hidden_window: Any) -> None:
    """A canvas will scroll past its own scroll region without complaint, so
    the wheel over a short form would leave an empty pane behind."""
    form = hidden_window.panes[0]
    form.canvas.configure(scrollregion=(0, 0, 1, 1), yscrollincrement=10)

    form.spin(-120)

    assert form.canvas.yview() == (0.0, 1.0)


def test_the_wheel_does_not_quietly_change_a_setting(hidden_window: Any) -> None:
    """ttk binds the wheel on a combobox to changing its own value. On a page
    that scrolls, rolling past 'Sheet master' would build the sheets on a
    different title block with nothing on screen to say so."""
    assert hidden_window.root.bind_class("TCombobox", "<MouseWheel>") == ""
    assert hidden_window.root.bind_all("<MouseWheel>"), "and the page scrolls instead"


def test_the_window_opens_no_taller_than_the_screen(hidden_window: Any) -> None:
    """A window opened past the bottom edge cannot be dragged back up by its
    title bar, which is how the settings below the fold became unreachable."""
    asked = hidden_window._on_the_screen(880, 10_000)
    _, _, tall = asked.partition("x")

    assert int(tall) <= hidden_window.root.winfo_screenheight()


def test_a_touchpad_scrolls_both_ways(hidden_window: Any) -> None:
    """A mouse sends 120 to the notch; a precision touchpad sends whatever the
    finger did. Dividing first rounds a gentle push down to nothing while a
    gentle pull up still moves, and a page that scrolls one way only is worse
    than one that does not scroll at all."""
    form = hidden_window.panes[0]
    form.canvas.configure(scrollregion=(0, 0, 100, 4000), yscrollincrement=10)

    form.spin(-40)  # less than a notch, downward
    moved = form.canvas.yview()[0]
    form.spin(40)

    assert moved > 0.0, "a small gesture down has to move the page"
    assert form.canvas.yview()[0] == 0.0, "and the same gesture up puts it back"


def test_the_wheel_over_an_open_dropdown_says_nothing(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A combobox's dropdown is a window Tk made for itself and never told
    Python about, so asking what is under the pointer raises. The list scrolls
    on its own; all the form's handler has to do is not print a traceback over
    somebody choosing a layer."""
    complaints: list[Any] = []
    hidden_window.root.report_callback_exception = lambda *bad: complaints.append(bad)

    def never_heard_of_it(*_where: int) -> None:
        raise KeyError("popdown")

    monkeypatch.setattr(hidden_window.root, "winfo_containing", never_heard_of_it)
    hidden_window.root.event_generate("<MouseWheel>", delta=-120, when="now")

    assert not complaints


# -- settings that outlive the window --------------------------------------


@pytest.fixture
def settings_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Where those settings land. The same disposable place the window fixture
    already points at, named here so a test can look in it."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return preferences.path()


def test_what_was_saved_is_what_opens(hidden_window: Any, settings_file: Path) -> None:
    """The point of the whole thing: the layer prefix, the living-room suffix
    and the Archicad wait are properties of the practice, not of the job, and
    retyping them every time is both tedious and a way to get one subtly
    wrong."""
    hidden_window.prefix_solar.delete(0, "end")
    hidden_window.prefix_solar.insert(0, "14 |")
    hidden_window.livable.insert(0, "_L")
    hidden_window.do_plans.set(True)

    hidden_window._remember()
    assert settings_file.is_file()

    hidden_window.apply(hidden_window.factory)
    assert hidden_window.livable.get() == "", "back to the defaults"

    hidden_window.apply(preferences.load())
    assert hidden_window.prefix_solar.get() == "14 |"
    assert hidden_window.livable.get() == "_L"
    assert hidden_window.do_plans.get() is True


def test_a_window_opened_afterwards_is_already_filled_in(
    hidden_window: Any, settings_file: Path
) -> None:
    """The whole point is what happens tomorrow morning, so the reopening is
    what is tested: a second window over the same fake project, reading the
    file the first one wrote."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.livable.insert(0, "_L")
    hidden_window.wait_min.delete(0, "end")
    hidden_window.wait_min.insert(0, "45")
    hidden_window._remember()

    reopened = window.Window(tk.Toplevel(hidden_window.root))  # type: ignore[arg-type]

    assert reopened.livable.get() == "_L"
    assert reopened.wait_min.get() == "45"
    assert flag(reopened.jobs()[0].args, "--timeout") == ["2700"], "and it reaches the run"


def test_the_port_is_not_a_preference(hidden_window: Any) -> None:
    """Which Archicad answered, on which port, is a fact about this afternoon.
    Restored next week it would point the study at whatever holds that port
    today, which is the one mistake this window exists to prevent."""
    saved = hidden_window.settings()

    assert not [name for name in saved if "port" in name or "instance" in name]


def test_which_section_was_open_is_remembered(hidden_window: Any, settings_file: Path) -> None:
    """Somebody who only ever runs the diagrams should open on the diagrams,
    not on a page of layer settings they set up once in March. And the
    notebook has to move, not only the saved string."""
    hidden_window._show_section(window.Window.DIAGRAMS)
    hidden_window._remember()

    hidden_window.apply(hidden_window.factory)
    assert hidden_window._open_section() == window.Window.GENERAL, "back to the first tab"

    hidden_window.apply(preferences.load())
    assert hidden_window._open_section() == window.Window.DIAGRAMS


def test_a_section_this_version_has_never_heard_of_leaves_the_tabs_alone(
    hidden_window: Any,
) -> None:
    """A settings file from a version that named its sections differently, or
    that carried one this build does not. Losing which tab was open is the
    cheapest thing in the file to lose; refusing to open is the dearest."""
    hidden_window._show_section(window.Window.FACADE)

    hidden_window.apply({"open_section": "Sun eye view over the harbour"})

    assert hidden_window._open_section() == window.Window.FACADE


def test_a_settings_file_nobody_can_read_leaves_the_window_alone(
    settings_file: Path,
) -> None:
    """Hand-edited into nonsense, written by a later version, sitting on a
    locked profile: a window that will not open is a far worse failure than a
    window that opens on its own defaults."""
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text("{ this is not json", encoding="utf-8")
    assert preferences.load() == {}

    settings_file.write_text('["a list, not a mapping"]', encoding="utf-8")
    assert preferences.load() == {}

    settings_file.unlink()
    assert preferences.load() == {}


def test_a_setting_of_the_wrong_shape_costs_only_itself(
    hidden_window: Any, settings_file: Path
) -> None:
    """One bad line should not condemn the other twenty-five."""
    hidden_window.apply({"layer_prefix": "14 |", "year": 2024, "study_plans": "yes"})

    assert hidden_window.prefix_solar.get() == "14 |"
    assert hidden_window.year.get() == "2024", "the number is not a field's text"
    assert hidden_window.do_plans.get() is False, "and the string is not a tick"


def test_forget_puts_back_what_the_window_opens_with(
    hidden_window: Any, settings_file: Path
) -> None:
    """Not 'whatever was on screen when it was pressed'."""
    hidden_window.prefix_solar.delete(0, "end")
    hidden_window.prefix_solar.insert(0, "99 |")
    hidden_window._remember()

    hidden_window._forget()

    assert not settings_file.exists()
    assert hidden_window.prefix_solar.get() == naming.SOLAR_PREFIX
    assert hidden_window.master.get(), "and the project's own lists are read again"


def test_the_open_project_overrules_a_saved_name_it_does_not_have(
    hidden_window: Any,
) -> None:
    """A saved layer name from another job must not make a run measure a
    layer that is not in this one. The lists are refilled from Archicad after
    the settings land, and a name the project cannot offer is replaced by one
    it can."""
    hidden_window.apply({"master_layout": "A0 - SOMEBODY ELSE'S TITLE BLOCK"})

    hidden_window.refresh()

    assert hidden_window.master.get() in hidden_window.options.masters


def test_a_layer_saved_on_another_job_is_not_measured_here(hidden_window: Any) -> None:
    """The one way a saved setting can make a run measure the wrong thing. The
    pickers are filled from the project only when they are empty, so a facade
    list carried over from another job would sit there unchallenged and
    produce a study of nothing -- no error anywhere, which is the failure this
    window exists to prevent."""
    hidden_window.apply({"subject_layers": "01 | Wall.External, 09 | SOMEBODY ELSE'S SLABS"})

    hidden_window.refresh()

    assert hidden_window._listed(hidden_window.subject) == ["01 | Wall.External"]
    assert "SOMEBODY ELSE" in "\n".join(hidden_window.lines), "and it is said out loud"


def test_a_layer_the_project_spells_differently_is_corrected(hidden_window: Any) -> None:
    """What goes to the command line has to be the project's own spelling, and
    a name pasted out of a report is nobody's memory test."""
    hidden_window.apply({"hide_layers": "05 |   Dims/Notes.DA"})

    hidden_window.refresh()

    assert hidden_window._listed(hidden_window.hide) == ["05 | Dims/Notes.DA"]


def test_a_zone_name_that_is_not_on_the_chosen_layer_goes(hidden_window: Any) -> None:
    """The same fault one level down, and it arrives by two doors: a name
    saved on another project, and a layer changed under names guessed for the
    one before it. Either way the assessment is of nothing, or of half a
    building."""
    hidden_window.apartment_names.delete(0, "end")
    hidden_window.apartment_names.insert(0, "G08, NOT-A-ZONE-HERE")

    hidden_window._offer_zone_names()

    assert hidden_window._listed(hidden_window.apartment_names) == ["G08"]


def test_a_layer_that_read_as_empty_costs_nobody_their_names(hidden_window: Any) -> None:
    """A layer that gave up no zones is a failure to read, not a statement
    that the names are wrong."""
    hidden_window.apartments.set("01 | Wall.External")  # carries no Zones
    hidden_window.apartment_names.delete(0, "end")
    hidden_window.apartment_names.insert(0, "G08")

    hidden_window._offer_zone_names()

    assert hidden_window._listed(hidden_window.apartment_names) == ["G08"]


def test_a_settings_file_that_is_not_even_text(settings_file: Path) -> None:
    """Not JSON is one thing; not decodable at all is another, and it raises a
    ValueError rather than an OSError. Through a narrower guard it would reach
    the window's own construction and stop it opening -- the one failure this
    module promises cannot happen."""
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_bytes(b"\xff\xfe\x00 not text")

    assert preferences.load() == {}


# -- finding a layer without retyping its punctuation ----------------------


def test_a_layer_is_found_however_its_punctuation_is_typed() -> None:
    """Layer names carry punctuation nobody reproduces from memory. Somebody
    looking for the core types '1| core', and the group number, the bar and
    the spacing round it are the part they are least likely to get right."""
    names = ["01 | Core", "01 | Wall.External", "05 | Dims/Notes.DA"]

    for query in ("core", "CORE", "1| core", "01|core", "1|core", "core 1"):
        assert window.matching(names, query) == ["01 | Core"], query


def test_words_still_match_in_any_order_and_anywhere() -> None:
    names = ["01 | Floor.Structural", "01 | Wall.External"]

    assert window.matching(names, "floor str") == ["01 | Floor.Structural"]
    assert window.matching(names, "str floor") == ["01 | Floor.Structural"]
    assert window.matching(names, "dimsnotes") == []


def test_an_empty_search_offers_everything() -> None:
    names = ["01 | Core", "01 | Wall.External"]

    assert window.matching(names, "") == names
    assert window.matching(names, "   ") == names
    assert window.matching(names, "|| //") == names, "punctuation alone narrows nothing"


# -- the zone rows' Add: it opens whatever the read found ----------------------


class _Recorded:
    """Stands in for the chooser: remembers how it was opened, answers with
    what it is told to."""

    opened: ClassVar[list[dict[str, Any]]] = []
    answer: ClassVar[list[str] | None] = None

    def __init__(self, parent: Any, **kwargs: Any) -> None:
        type(self).opened.append(kwargs)
        self.result = type(self).answer


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, hidden_window: Any) -> type[_Recorded]:
    _Recorded.opened = []
    _Recorded.answer = None
    monkeypatch.setattr(window, "LayerChooser", _Recorded)
    monkeypatch.setattr(hidden_window.root, "wait_window", lambda _dialog: None)
    return _Recorded


def test_the_zone_add_opens_even_when_the_read_found_no_zones_there(
    hidden_window: Any, recorded: type[_Recorded]
) -> None:
    """It used to write one line at the foot of the window and do nothing,
    which from where the button is reads as a button that does not work.
    It opens now, says why the list is empty, and takes a typed name."""
    hidden_window.apartments.set("01 | Wall.External")  # carries no Zones
    recorded.answer = ["G08"]

    hidden_window._choose_zone_names(
        hidden_window.apartment_names, hidden_window.apartments, "Apartment zones"
    )

    assert len(recorded.opened) == 1, "the chooser did not open"
    opened = recorded.opened[0]
    assert opened["typed"] is True
    assert opened["available"] == []
    assert "01 | Wall.External" in opened["empty"], "it does not say which layer was empty"
    assert "Refresh" in opened["empty"]
    assert hidden_window._listed(hidden_window.apartment_names) == ["G08"]


def test_the_balcony_add_opens_the_same_way(hidden_window: Any, recorded: type[_Recorded]) -> None:
    """Both rows are the same row, and both were reported broken."""
    hidden_window.balconies.set("06 | Zone.Units")
    recorded.answer = ["BY"]

    hidden_window._choose_zone_names(
        hidden_window.balcony_names, hidden_window.balconies, "Balcony zones"
    )

    opened = recorded.opened[0]
    assert "BY" in opened["available"], "the zones the read did find are offered"
    assert opened["empty"] == "", "nothing to apologise for when the list is full"
    assert hidden_window._listed(hidden_window.balcony_names) == ["BY"]


def test_a_read_that_failed_is_named_rather_than_blamed_on_the_layer(
    hidden_window: Any, recorded: type[_Recorded]
) -> None:
    hidden_window.options = replace(
        hidden_window.options, zone_kinds=(), problems=("zones: Archicad did not answer",)
    )
    hidden_window.apartments.set("06 | Zone.Units")

    hidden_window._choose_zone_names(
        hidden_window.apartment_names, hidden_window.apartments, "Apartment zones"
    )

    assert "Archicad did not answer" in recorded.opened[0]["empty"]


def test_without_a_layer_the_zone_add_says_so_where_the_button_is(
    monkeypatch: pytest.MonkeyPatch, hidden_window: Any, recorded: type[_Recorded]
) -> None:
    from tkinter import messagebox

    said: list[tuple[str, str]] = []
    monkeypatch.setattr(
        messagebox, "showinfo", lambda title, message, **_: said.append((title, message))
    )
    hidden_window.apartments.set("")

    hidden_window._choose_zone_names(
        hidden_window.apartment_names, hidden_window.apartments, "Apartment zones"
    )

    assert not recorded.opened, "nothing to list names from without a layer"
    assert said and "layer" in said[0][1].lower()


def test_a_typed_zone_name_is_added_ticked_and_spelt_as_the_project_spells_it(
    hidden_window: Any,
) -> None:
    chooser = window.LayerChooser(
        hidden_window.root, title="Zones", hint="", available=["G08"], chosen=[], typed=True
    )
    assert chooser.typed is not None
    chooser.typed.insert(0, "  g08 ")
    chooser._add_typed()
    chooser.typed.insert(0, "SC  1")
    chooser._add_typed()
    chooser._accept()

    assert chooser.result == ["G08", "SC 1"]


def test_a_chosen_zone_name_the_list_lacks_is_kept_not_dropped(hidden_window: Any) -> None:
    """A saved name the read did not see is still what the office meant, and
    pressing Use these must not quietly take it away."""
    chooser = window.LayerChooser(
        hidden_window.root, title="Zones", hint="", available=["BY"], chosen=["G08"], typed=True
    )
    chooser._accept()

    assert chooser.result == ["G08"]


def test_a_layer_list_still_drops_what_the_project_does_not_have(hidden_window: Any) -> None:
    """Layers are the other way round on purpose: a layer typed or saved
    wrongly is a study that measures nothing, so it goes."""
    chooser = window.LayerChooser(
        hidden_window.root, title="Layers", hint="", available=["01 | Core"], chosen=["gone"]
    )
    assert chooser.typed is None
    chooser._accept()

    assert chooser.result == []


# -- the chooser opening where it was left ---------------------------------


def test_the_chooser_reopens_where_it_was_closed(hidden_window: Any) -> None:
    """A colleague setting a project up opens it six or seven times in a row.
    One that jumps back to the middle of the screen every time is one they
    have to drag off the form every time."""
    monkey = window.LayerChooser(
        hidden_window.root,
        title="Facade layers",
        hint="",
        available=["01 | Core"],
        chosen=[],
    )
    monkey.geometry("640x500+321+123")
    monkey.update_idletasks()
    monkey._close()

    again = window.LayerChooser(
        hidden_window.root, title="Also export", hint="", available=["01 | Core"], chosen=[]
    )
    again.update_idletasks()
    remembered = again.wm_geometry()
    again._close()

    assert "+321+123" in remembered, f"opened at {remembered}, not where it was left"


def test_cancelling_remembers_the_place_too(hidden_window: Any) -> None:
    """A dialog that remembers only when dismissed one particular way looks
    broken rather than absent."""
    first = window.LayerChooser(
        hidden_window.root, title="One", hint="", available=["01 | Core"], chosen=[]
    )
    first.geometry("600x480+250+180")
    first.update_idletasks()
    first._close()  # what Cancel, Escape and the window manager's X all call

    assert first.result is None, "cancelling still answers with nothing chosen"
    assert "+250+180" in (window._chooser_geometry or "")


# -- a height band, as two of this building's own storeys --------------------


def test_the_band_pickers_are_filled_from_the_projects_own_storeys(hidden_window: Any) -> None:
    """A band is chosen from what the building has, not typed from memory."""
    hidden_window.options = replace(
        hidden_window.options, storey_names=("AHD", "GROUND", "LEVEL 01", "ROOF")
    )
    hidden_window._offer_height_cut()

    assert list(hidden_window.storey_from["values"]) == ["AHD", "GROUND", "LEVEL 01", "ROOF"]
    assert list(hidden_window.storey_to["values"]) == ["AHD", "GROUND", "LEVEL 01", "ROOF"]


def test_nothing_is_chosen_for_the_person(hidden_window: Any) -> None:
    """Which storeys are the building and which are parked geometry is a
    judgement this cannot make: one real project defines 134 storeys running
    to 422.5 m at a regular 3.2 m spacing, with no gap to say where the tower
    stops. A band guessed too low silently removes the top of the building
    from every percentage and nothing in the drawing shows it."""
    hidden_window.options = replace(hidden_window.options, storey_names=("AHD", "LEVEL 01", "ROOF"))
    hidden_window._offer_height_cut()

    assert hidden_window.storey_from.get() == "", "an empty band measures everything"
    assert hidden_window.storey_to.get() == ""
    assert hidden_window._band_args() == []


def test_storeys_that_will_not_read_leave_the_pickers_alone(hidden_window: Any) -> None:
    """An unreadable storey list is a failure to read, not a statement that
    the project has no storeys."""
    hidden_window.storey_from.set("GROUND")
    hidden_window.options = replace(hidden_window.options, storey_names=())
    hidden_window._offer_height_cut()

    assert hidden_window.storey_from.get() == "GROUND", "a chosen storey is a decision"


def test_a_chosen_band_becomes_the_two_storey_flags(hidden_window: Any) -> None:
    """Either end may be left open, and both open is the whole model."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.storey_from.set("AHD")
    hidden_window.storey_to.set("ROOF")
    assert hidden_window._band_args() == [
        "--exclude-below-storey",
        "AHD",
        "--exclude-above-storey",
        "ROOF",
    ]

    hidden_window.storey_from.set("")
    assert hidden_window._band_args() == ["--exclude-above-storey", "ROOF"]

    (facade,) = hidden_window.jobs()
    assert flag(facade.args, "--exclude-above-storey") == ["ROOF"]
    assert "--exclude-above" not in facade.args, "the metre flag is gone from the window"


def test_the_shadow_study_sends_one_flag_per_legend_row_by_layer(hidden_window: Any) -> None:
    """Layers out of the open project, one legend row each, and the native
    model rather than an IFC or a folder of published views (D113)."""
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    hidden_window.do_facade.set(False)
    hidden_window.do_shadows.set(True)
    rows["EXISTING"].insert(0, "01 | Wall.External, 01 | Floor.Structural")
    rows["PROPOSED"].insert(0, "06 | Zone.Units")
    hidden_window.terrain_layers.insert(0, "05 | Dims/Notes.DA")

    (job,) = hidden_window.jobs()

    assert job.args[0] == "shadows"
    assert flag(job.args, "--shadow-source") == [
        "EXISTING=01 | Wall.External,01 | Floor.Structural"
    ]
    assert flag(job.args, "--shadow-scenario") == ["PROPOSED=06 | Zone.Units"]
    assert flag(job.args, "--shadow-terrain") == ["05 | Dims/Notes.DA"]
    assert flag(job.args, "--export") == ["native"]
    assert "--shadow-from-views" not in job.args
    assert "--shadow-favourite" not in job.args


def test_every_study_that_exports_asks_for_the_native_model(hidden_window: Any) -> None:
    """No job is left on ``auto``, which falls back to an IFC export when the
    add-on is out of date: the run is to stop and say so instead."""
    hidden_window.do_facade.set(True)
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)
    hidden_window.do_shadows.set(True)

    exporting = [job for job in hidden_window.jobs() if job.args[0] != "site"]

    assert {job.args[0] for job in exporting} >= {"massing", "archicad-run", "shadows"}
    for job in exporting:
        assert flag(job.args, "--export") == ["native"], job.args[0]


def test_every_hour_on_one_drawing_is_asked_for_only_when_ticked(hidden_window: Any) -> None:
    hidden_window.do_facade.set(False)
    hidden_window.do_shadows.set(True)
    (job,) = hidden_window.jobs()
    assert "--shadow-all-hours" not in job.args

    hidden_window.do_shadow_all_hours.set(True)
    (job,) = hidden_window.jobs()
    assert "--shadow-all-hours" in job.args
    assert hidden_window.settings()["shadow_all_hours"] is True


def test_the_legend_rows_are_the_legends_own_in_its_order(hidden_window: Any) -> None:
    """Three that accumulate, then four that are compared; the short names are
    what the drawing matches to the legend's colours."""
    from sun_study.archicad.shadows import LEGEND

    assert [(short, role) for short, role, _box in hidden_window.shadow_rows] == [
        (short, role) for short, _words, role, _rgb in LEGEND
    ]


def test_the_adg_envelope_is_compared_like_the_proposal_and_drawn_under_it(
    hidden_window: Any,
) -> None:
    """The proposal with room to move: a scenario, so it is compared rather
    than added, and named just before the proposal so the proposal is drawn
    on top and what shows of the envelope is the extra it would cost."""
    rows = {short: (role, box) for short, role, box in hidden_window.shadow_rows}
    shorts = [short for short, _role, _box in hidden_window.shadow_rows]
    assert rows["ADG ENVELOPE"][0] == "scenario"
    assert shorts.index("ADG ENVELOPE") == shorts.index("PROPOSED") - 1

    hidden_window.do_shadows.set(True)
    rows["ADG ENVELOPE"][1].insert(0, "01 | Floor.Structural")
    job = next(job for job in hidden_window.jobs() if job.args[0] == "shadows")

    assert flag(job.args, "--shadow-scenario") == ["ADG ENVELOPE=01 | Floor.Structural"]


def test_the_legend_rows_survive_a_save(hidden_window: Any) -> None:
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    rows["TOD"].insert(0, "01 | Floor.Structural")
    saved = hidden_window.settings()
    assert saved["shadow_layers_tod"] == "01 | Floor.Structural"


def test_the_shadow_study_sends_only_what_was_filled_in(hidden_window: Any) -> None:
    """Blank fields are left off so the command's own defaults stand.

    A favourite passed as an empty string is not "no favourite" to Archicad,
    it is a Favorite with no name, and the run fails on it several minutes in.
    """
    hidden_window.do_facade.set(False)
    hidden_window.do_shadows.set(True)

    (job,) = hidden_window.jobs()

    assert "--shadow-terrain-floor" not in job.args
    assert "--shadow-terrain" not in job.args
    assert "--shadow-source" not in job.args, "an empty row is left off"
    # The dates and hours have defaults on the page, so they do travel.
    assert "--shadow-date" in job.args
    assert "--shadow-hour" in job.args


def test_the_shadow_study_runs_after_the_others(hidden_window: Any) -> None:
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)
    hidden_window.do_shadows.set(True)

    assert [job.args[0] for job in hidden_window.jobs()] == [
        "massing",
        "archicad-run",
        "massing",
        "shadows",
    ]


def test_the_sun_eye_run_sends_what_is_filled_in_and_nothing_else(hidden_window: Any) -> None:
    hidden_window.do_facade.set(False)
    hidden_window.do_sun_eyes.set(True)
    hidden_window.eye_pen_set.insert(0, "00 FA Pens")
    (job,) = hidden_window.jobs()
    assert job.label == window.SUN_EYE_JOB
    assert job.args[:3] == ["sun-views", "--timezone", "Australia/Sydney"]
    assert job.args[job.args.index("--port") + 1] == "19723"
    assert job.args[job.args.index("--pen-set") + 1] == "00 FA Pens"
    assert job.args[job.args.index("--scale") + 1] == "500"
    assert job.args[job.args.index("--sheets") + 1] == "two"
    assert job.args[job.args.index("--override") + 1] == "Sun Eye Views"
    # Blank hours: the ruleset's own window, not an empty flag.
    assert "--hour" not in job.args


def test_the_sun_eye_override_and_layers_are_picked_from_the_project(
    hidden_window: Any,
) -> None:
    """Both lists are the open project's own: the overrides through the
    add-on, which is the only thing that can list them, and the layer
    combinations through Tapir."""
    assert list(hidden_window.eye_override.cget("values")) == [
        "",
        "Clean",
        "Sun Eye Views",
        "Zone Colours",
    ]
    assert hidden_window.eye_override.get() == "Sun Eye Views"
    assert "12 | IFC ARCH. EXPORT" in hidden_window.eye_base_combination.cget("values")
    assert hidden_window.eye_base_combination.get() in hidden_window.eye_base_combination.cget(
        "values"
    )


def test_the_sun_eye_settings_survive_a_save(hidden_window: Any) -> None:
    hidden_window.eye_scale.delete(0, "end")
    hidden_window.eye_scale.insert(0, "200")
    hidden_window.do_sun_eyes.set(True)
    saved = hidden_window.settings()
    assert saved["eye_scale"] == "200"
    assert saved["study_sun_eyes"] is True


def test_the_site_analysis_runs_from_an_address_and_names_its_sheets(hidden_window: Any) -> None:
    """The one study that reads nothing off the project: an address in, the
    sheets ticked, and the anchor said in words on the page and as a keyword
    on the command line."""
    hidden_window.do_facade.set(False)
    hidden_window.do_site.set(True)
    hidden_window.site_address.insert(0, "26-30 Campsie St, Campsie NSW 2194")
    hidden_window.do_site_summary.set(False)
    hidden_window.site_anchor.set("Project origin")
    (site,) = hidden_window.jobs()
    assert site.label == window.SITE_JOB
    assert site.args[:2] == ["site", "26-30 Campsie St, Campsie NSW 2194"]
    assert "--context" in site.args and "--site" in site.args and "--no-summary" in site.args
    assert flag(site.args, "--anchor") == ["site"]
    assert flag(site.args, "--scale") == ["3000"]
    assert flag(site.args, "--port") == ["19723"]
    # The aerial is not a choice on the page: the CLI fetches and places it
    # by default, so the window neither asks nor passes a flag.
    assert "--aerial" not in site.args and "--no-aerial" not in site.args
    assert not hasattr(hidden_window, "do_site_aerial")
    assert "--model" not in site.args and "--keep-location" not in site.args
    hidden_window.do_site_model.set(True)
    hidden_window.do_site_location.set(False)
    (site,) = hidden_window.jobs()
    assert "--model" in site.args and "--keep-location" in site.args


def test_the_site_can_be_set_on_a_corner_and_turned_level_from_the_page(
    hidden_window: Any,
) -> None:
    """Two words on the page, two flags on the command line, and neither
    sent unless the site is placed at the project origin, where they mean
    something."""
    hidden_window.do_facade.set(False)
    hidden_window.do_site.set(True)
    hidden_window.site_address.insert(0, "59 Great Buckingham St, Redfern NSW 2016")
    hidden_window.site_anchor.set("Project origin")
    hidden_window.site_origin.set("Bottom-left corner")
    hidden_window.site_turn.set("Long boundary level")
    (site,) = hidden_window.jobs()
    assert flag(site.args, "--anchor") == ["site"]
    assert flag(site.args, "--origin-at") == ["bottom-left"]
    assert "--square-to-site" in site.args
    hidden_window.site_anchor.set("Project location")
    (site,) = hidden_window.jobs()
    assert "--origin-at" not in site.args and "--square-to-site" not in site.args
    saved = hidden_window.settings()
    assert saved["site_origin"] == "Bottom-left corner"
    assert saved["site_turn"] == "Long boundary level"


def test_the_site_analysis_waits_for_an_address(hidden_window: Any) -> None:
    """Ticked with nothing typed, there is no job: the address is the study."""
    hidden_window.do_facade.set(False)
    hidden_window.do_site.set(True)
    assert hidden_window.jobs() == []
    assert "study_site" in hidden_window.settings()
    assert hidden_window.settings()["site_anchor"] == "Project location"


def test_a_lit_day_reaches_the_three_solar_studies_and_no_other_page(
    hidden_window: Any,
) -> None:
    """One box of days on the Solar analysis page, and the plans, the facade
    and the communal study run on those days. The sun views and the shadow
    diagram each have a box of their own on their own page, and neither
    hears this one: a day lit for the apartments no longer quietly runs
    the sun views on it too."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)
    hidden_window.do_shadows.set(True)
    hidden_window.do_sun_eyes.set(True)
    hidden_window.days["winter"].set(False)
    hidden_window.days["summer"].set(True)

    by_name = {job.label: job.args for job in hidden_window.jobs()}
    assert flag(by_name["solar analysis: facade"], "--date") == ["summer"]
    assert flag(by_name["solar analysis: apartments"], "--date") == ["summer"]
    assert flag(by_name["solar analysis: communal open space"], "--date") == ["summer"]
    assert "--date" not in by_name["sun views"], "the views keep their own midwinter"
    assert flag(by_name["shadow diagram"], "--shadow-date") == ["06-21"]


def test_the_sun_views_and_the_shadows_run_on_their_own_days(hidden_window: Any) -> None:
    """The same three buttons on three pages, and three answers. The views
    lit for the equinox run once per lit day and say which; the shadows
    lit for every day are one job with every date."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_sun_eyes.set(True)
    hidden_window.do_shadows.set(True)
    hidden_window.eye_days["equinox"].set(True)
    for lit in hidden_window.shadow_day_ticks.values():
        lit.set(True)

    jobs = hidden_window.jobs()
    views = [job for job in jobs if job.label.startswith("sun views")]
    assert [flag(job.args, "--date") for job in views] == [[], ["equinox"]]
    assert "21 September" in views[1].label
    (shadows,) = [job for job in jobs if job.label == "shadow diagram"]
    assert flag(shadows.args, "--shadow-date") == ["06-21,09-21,12-21"]
    assert hidden_window.chosen_days() == ["winter"], "the solar box did not move"

    saved = hidden_window.settings()
    assert saved["sun_view_day_equinox"] is True and saved["day_equinox"] is False
    assert saved["shadow_day_summer"] is True


def test_the_site_outputs_are_buttons_over_the_same_ticks(hidden_window: Any) -> None:
    """Six lines of small print became two rows of buttons, worded short,
    over the very same variables -- so a preset that ticked the context
    model still lights the button, and pressing the button is the tick."""
    buttons = hidden_window.site_buttons
    assert list(buttons) == [
        "Context Analysis sheet",
        "Site Analysis sheet",
        "Summary of Controls layout",
        "Future Context (what the controls allow next door)",
        "Context Model in 3D (terrain, blocks, neighbours)",
        "Set the project location from the address",
    ]
    assert buttons["Context Model in 3D (terrain, blocks, neighbours)"].cget("text") == "3D context"
    assert all(button.cget("image") for button in buttons.values()), "each wears its drawing"

    assert hidden_window.do_site_model.get() is False
    buttons["Context Model in 3D (terrain, blocks, neighbours)"].invoke()
    assert hidden_window.do_site_model.get() is True
    hidden_window.apply({"site_model": False})
    assert str(buttons["Context Model in 3D (terrain, blocks, neighbours)"].cget("style")) == (
        "Tile.TButton"
    ), "a preset that unticks it unlights it"


def test_the_shadow_storey_is_picked_by_name_and_sent_by_index(hidden_window: Any) -> None:
    """The command places the fills by storey index, and the window offers
    the project's storey names -- the same list the height band picks
    from. A number typed the old way still goes through as the index."""
    hidden_window.options = replace(
        hidden_window.options,
        storey_names=("AHD", "GROUND", "LEVEL 01"),
        storey_indices=(("AHD", -1), ("GROUND", 6), ("LEVEL 01", 7)),
    )
    hidden_window._offer_height_cut()
    assert list(hidden_window.shadow_storey["values"]) == ["AHD", "GROUND", "LEVEL 01"]
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)

    hidden_window.shadow_storey.set("GROUND")
    assert flag(hidden_window.jobs()[0].args, "--shadow-storey") == ["6"]
    hidden_window.shadow_storey.set("2")
    assert flag(hidden_window.jobs()[0].args, "--shadow-storey") == ["2"]
    hidden_window.shadow_storey.set("")
    assert "--shadow-storey" not in hidden_window.jobs()[0].args


def test_several_ticked_days_run_each_tool_once_per_day(hidden_window: Any) -> None:
    """The reason the box became ticks. A council wants midwinter for the test
    and the equinox beside it to show the year, and picking one at a time meant
    running the tool again and remembering to change the box.

    Each run carries its own date, so the sets stand beside each other in the
    project rather than the second replacing the first -- and the queued jobs
    say which day they are for, or two identical labels would be waiting."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.days["equinox"].set(True)

    jobs = hidden_window.jobs()
    assert len(jobs) == 2, "one facade run per day"
    assert [flag(job.args, "--date") for job in jobs] == [[], ["equinox"]]
    assert "21 June" in jobs[0].label and "21 September" in jobs[1].label


def test_the_rulesets_own_day_sends_nothing_so_the_names_stay_as_they_were(
    hidden_window: Any,
) -> None:
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.do_plans.set(True)
    facade, plans = hidden_window.jobs()
    assert "--date" not in facade.args
    assert "--date" not in plans.args

    # Typed as a date rather than ticked, and still the ruleset's own day.
    hidden_window.days["winter"].set(False)
    hidden_window.custom_day.insert(0, "06-21")
    assert "--date" not in hidden_window.jobs()[0].args


def test_a_custom_day_runs_as_well_as_the_ticks_and_is_judged_by_the_command(
    hidden_window: Any,
) -> None:
    """As well as, not instead of: the usual pair plus one is three runs."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.custom_day.insert(0, "9-22")
    jobs = hidden_window.jobs()
    assert [flag(job.args, "--date") for job in jobs] == [[], ["09-22"]]

    hidden_window.custom_day.delete(0, "end")
    hidden_window.custom_day.insert(0, "autumn")
    assert flag(hidden_window.jobs()[1].args, "--date") == ["autumn"]

    # Ticked and typed as the same day is one run, not two over the top.
    hidden_window.custom_day.delete(0, "end")
    hidden_window.custom_day.insert(0, "06-21")
    assert len(hidden_window.jobs()) == 1


def test_the_future_context_tick_reaches_the_site_command_with_its_settings(
    hidden_window: Any,
) -> None:
    """The reach is the one thing a designer changes; the zones stay put."""
    hidden_window.do_site.set(True)
    hidden_window.site_address.insert(0, "1 Test St, Kogarah NSW")
    hidden_window.do_site_future.set(True)
    hidden_window.site_future_reach.delete(0, "end")
    hidden_window.site_future_reach.insert(0, "80")

    site = next(job for job in hidden_window.jobs() if job.args[0] == "site")
    assert "--future" in site.args
    assert flag(site.args, "--future-reach") == ["80"]
    assert "--future-setback" not in site.args, "the raised buildings are not set back"
    assert flag(site.args, "--model-radius") == ["500"], "the model's square is what it reads"
    assert "--model" not in site.args

    hidden_window.do_site_future.set(False)
    site = next(job for job in hidden_window.jobs() if job.args[0] == "site")
    assert "--future" not in site.args


def test_a_zone_layer_can_be_any_layer_the_project_has(hidden_window: Any) -> None:
    """Which layer holds the Zones is the office's decision, not a fact this
    can derive.

    The picker used to offer only layers the probe had found Zones on, which
    looked like help and was a trap: a project keeping its communal areas on a
    fills layer, or one whose zones sit on a storey the probe did not read, had
    no way to say so -- the answer was simply not in the list.

    Reported from the window on 17 September 2026: "there is only few layer
    selections in selection zone option ... companies could have completely
    different structure".
    """
    hidden_window.options = replace(
        hidden_window.options,
        layers=("06 | Zone.Units", "07 | Fills.Areas", "10 | Calc.COS", "01 | Wall.External"),
        zone_layers=("06 | Zone.Units",),
    )
    hidden_window._offer()

    for picker in (hidden_window.apartments, hidden_window.balconies, hidden_window.communal):
        offered = list(picker["values"])
        assert "07 | Fills.Areas" in offered, "a fills layer is where one real project keeps them"
        assert "10 | Calc.COS" in offered
        assert "01 | Wall.External" in offered, "even a layer with no zones on it today"
        # The help survives the widening: a layer that really does carry zones
        # is still offered first.
        assert offered[0] == "06 | Zone.Units"


def test_a_rerun_clears_the_last_one_under_the_same_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running after the model changed is the ordinary case.

    Geometry moves, the study is asked again, and what it drew before is a
    picture of a building that no longer exists. The fills were always
    replaced -- each layer is cleared before it is drawn -- but the views and
    layouts were only reused by name, so a run producing a different set left
    the old ones standing beside the new, and somebody had to know which sheet
    was which.

    The prefix is what makes the other half of the rule work: the same one
    replaces, a different one leaves the first alone, so two options can stand
    side by side in one project (D93). That is why this asserts the prefix it
    was given rather than merely that something was cleared.
    """
    from types import SimpleNamespace

    import typer

    from sun_study import cli

    asked: list[str] = []
    monkeypatch.setattr(typer, "echo", lambda *a, **k: None)
    monkeypatch.setattr(typer, "secho", lambda *a, **k: None)

    def remember(_connection: object, prefix: str) -> tuple[int, int]:
        asked.append(prefix)
        return 3, 0

    monkeypatch.setattr(cli, "remove_previous", remember)
    # Stops the run immediately after the clearing, which is all this pins.
    monkeypatch.setattr(cli, "elements_by_ifc_ids", lambda *a, **k: {})

    result = SimpleNamespace(
        zone=object(),
        zone_minutes=(0.0,),
        model=SimpleNamespace(of_class=lambda _kind: []),
        scene=SimpleNamespace(zone_samples=(1.0,)),
    )

    cli.report_zone_bands(object(), result, layer_prefix="14 |", spacing_m=0.5)  # type: ignore[arg-type]

    assert asked == ["14 |"], "cleared, and scoped to this run's own prefix"


# -- the icons -------------------------------------------------------------
#
# The set is drawn by ``scripts/make_icons.py`` and looked up by each field's
# own label, which buys a small diff at forty call sites and costs exactly one
# thing: a renamed label silently loses its picture. That is the intended
# failure -- a bare label beats a wrong one -- so it is the thing worth a test.


def every_text(widget: Any) -> set[str]:
    """Every piece of text on this widget and everything under it."""
    found: set[str] = set()
    try:
        text = widget.cget("text")
    except (tk.TclError, AttributeError):
        text = ""
    if isinstance(text, str) and text:
        found.add(text)
    for child in widget.winfo_children():
        found |= every_text(child)
    return found


def test_every_icon_the_tables_name_is_actually_on_disk(hidden_window: Any) -> None:
    """A table entry pointing at a file nobody drew would fail silently."""
    named = (
        set(icons.BY_LABEL.values()) | set(icons.BY_SECTION.values()) | set(icons.BY_STUDY.values())
    )
    missing = sorted(name for name in named if icons.named(name, icons.DEFAULT_SIZE) is None)
    assert not missing, f"named in a table but not drawn: {missing}"


def test_every_labelled_icon_matches_a_label_the_window_really_uses(
    hidden_window: Any,
) -> None:
    """The lookup is by label, so a typo in the table is an icon that never shows.

    Worth pinning because the labels are not identifiers: four of them carry
    an em dash and one is the word "Days". A table keyed on a string nobody
    renders is dead weight that looks like a working icon.
    """
    on_screen = every_text(hidden_window.root)
    orphans = sorted(label for label in icons.BY_LABEL if label not in on_screen)
    assert not orphans, f"in BY_LABEL but no such label in the window: {orphans}"


def test_every_tab_carries_its_own_drawing_above_its_name(hidden_window: Any) -> None:
    """A tab is a drawing and a name. Without the drawing it is a small word.

    Above the name and not beside it, which is what lets the drawing be 32 px:
    beside it, an icon can be no taller than one line of text, and that is how
    the strip this replaces ended up with six pictures nobody could tell apart.
    """
    for title in hidden_window.titles:
        tab = hidden_window.tabs[title]
        assert tab.cget("image"), f"{title} has no icon"
        assert str(tab.cget("compound")) == "top", f"{title} wears its icon beside the name"
        # A tab whose study is queued also carries a dot, which `_sync` puts
        # there -- the fixture opens with the facade study on.
        assert tab.cget("text").rstrip(" •") == title, f"{title} is not named"


def test_the_strip_always_has_exactly_one_tab_open(hidden_window: Any) -> None:
    """There is no state of this window with no page showing, which is the one
    thing the launcher it replaces could be."""
    assert hidden_window._open_section() == window.Window.GENERAL
    hidden_window._show_section(window.Window.SHADOWS)
    assert hidden_window._open_section() == window.Window.SHADOWS
    # What a settings file from the launcher version wrote for "nothing open".
    # There is nowhere to put that now, so it opens the first tab.
    hidden_window._show_section("")
    assert hidden_window._open_section() == window.Window.GENERAL
    # A name from an older file leaves the page alone rather than moving
    # somebody somewhere they did not ask for.
    hidden_window._show_section(window.Window.SHADOWS)
    hidden_window._show_section("Solar tools")
    assert hidden_window._open_section() == window.Window.SHADOWS


def test_open_and_queued_are_two_marks_and_never_the_same_one(hidden_window: Any) -> None:
    """The fault the launcher had: one blue tint that had to mean both "this
    is the page you are on" and "this will run", and so meant neither.

    Four styles, two axes. A tab can be open, queued, both or neither, and all
    four are told apart -- and only the open ones wear the face with the blue
    cap, which is a shape and so cannot be mistaken for the queued tint.
    """
    capped = {name for name, worn in theme.WEARS.items() if worn == "tabopen"}
    hidden_window._show_section(window.Window.GENERAL)
    tab = hidden_window.tabs[window.Window.SHADOWS]

    hidden_window.do_shadows.set(False)
    hidden_window._sync()
    assert tab.cget("style") == "Tab.TButton", "neither"
    assert tab.cget("style") not in capped

    hidden_window.do_shadows.set(True)
    hidden_window._sync()
    assert tab.cget("style") == "TabQueued.TButton", "queued but not open"
    assert tab.cget("text").endswith("•")

    hidden_window._show_section(window.Window.SHADOWS)
    assert tab.cget("style") == "TabOpenQueued.TButton", "open and queued"
    assert tab.cget("style") in capped, "and it is the capped face that says open"

    hidden_window.do_shadows.set(False)
    hidden_window._sync()
    assert tab.cget("style") == "TabOpen.TButton", "open but not queued"
    assert hidden_window.tabs[window.Window.GENERAL].cget("style") not in capped


def test_only_the_tabs_that_draw_something_can_be_queued(hidden_window: Any) -> None:
    """The taxonomy, and the reason the strip is grouped rather than flat: two
    pages set the job up and four draw something, and a tick belongs only to
    the four. A queued mark on General would be a promise nothing keeps."""
    setting_up = dict(window.Window.GROUPS)[window.Window.SET_UP]
    drawn = dict(window.Window.GROUPS)[window.Window.DRAWS]

    assert set(setting_up) | set(drawn) == set(hidden_window.titles), "every tab in a group"
    assert not set(setting_up) & set(drawn), "and in only one"

    for _name, tick, _where in hidden_window._studies():
        tick.set(True)
    hidden_window._sync()

    for title in setting_up:
        assert hidden_window.tabs[title].cget("style") in {"Tab.TButton", "TabOpen.TButton"}, (
            f"{title} sets the job up and cannot be queued"
        )
    for title in drawn:
        assert hidden_window.tabs[title].cget("style").endswith("Queued.TButton"), (
            f"{title} draws something and every one of its studies is ticked"
        )


def test_a_coarseness_nobody_offered_is_kept_rather_than_rounded(
    hidden_window: Any,
) -> None:
    """Skin cell used to be a typed field and is now three tiles.

    A settings file saved before that can hold 1.25, and rounding somebody to
    the nearest tile would change what a study measures without saying so.
    """
    hidden_window.apply({"skin_grid": "1.25"})
    assert hidden_window.grid_m.get() == "1.25"
    hidden_window.apply({"skin_grid": "2.0"})
    assert hidden_window.grid_m.get() == "2.0"


@pytest.mark.parametrize(
    ("asked", "tick", "section"),
    [
        ("facade", "study_facade", window.Window.FACADE),
        ("apartments", "study_plans", window.Window.DIAGRAMS),
        ("communal", "study_communal", window.Window.DIAGRAMS),
        ("shadow", "study_shadows", window.Window.SHADOWS),
        ("views", "study_sun_eyes", window.Window.EYE),
        ("site", "study_site", window.Window.SITE),
    ],
)
def test_a_palette_button_ticks_its_study_and_opens_its_section(
    hidden_window: Any, asked: str, tick: str, section: str
) -> None:
    """What the add-on's palette buttons reach, one per study."""
    assert hidden_window.ask_for(asked) is True
    assert hidden_window._ticks()[tick].get() is True, f"{asked} was not ticked"
    showing = hidden_window._open_section()
    assert showing == section, f"{asked} opened {showing} rather than {section}"


def test_the_palettes_last_button_opens_the_reference_image(hidden_window: Any) -> None:
    """Not a study: the add-on's eighth button starts the window with the
    reference-image palette already up, so the next click is Open picture."""
    from sun_study.app import overlay

    assert overlay._open is None
    try:
        assert hidden_window.ask_for("reference") is True
        assert overlay._open is not None
        assert overlay._open.winfo_exists()
    finally:
        if overlay._open is not None:
            overlay._open.close()
            hidden_window.root.update()


def test_a_study_nobody_has_heard_of_leaves_the_window_alone(hidden_window: Any) -> None:
    """A misspelt environment variable must not stop the window opening."""
    before = {name: box.get() for name, box in hidden_window._ticks().items()}
    assert hidden_window.ask_for("shadow-diagrams") is False
    assert hidden_window.ask_for("") is False
    after = {name: box.get() for name, box in hidden_window._ticks().items()}
    assert after == before, "an unknown study changed something"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ""),
        (["--study", "shadow"], "shadow"),
        (["--study", "site"], "site"),
        # A flag with nothing after it must not read past the end.
        (["--study"], ""),
        # Not ours, and not an error either.
        (["--verbose"], ""),
        (["/dde", "--study", "facade"], "facade"),
    ],
)
def test_the_palette_argument_is_read_off_the_command_line(argv: list[str], expected: str) -> None:
    """How a palette button says which study it stood for.

    An argument rather than an environment variable: the add-on would have to
    set the variable on Archicad's own process, and every program Archicad
    started afterwards would inherit it.
    """
    assert window.wanted_study(argv) == expected


# -- the boxes, the band at rest, and the panel that folds ------------------


def test_every_study_heads_a_box_that_says_what_its_tick_is_worth(hidden_window: Any) -> None:
    """A page was a flat run of rows with a rule between the groups, which is
    what made it read as a form. Each study is a box now, headed by its own
    tick, and the header says what that tick costs in sheets -- the same
    figure the panel down the side draws, said where the decision is made."""
    assert set(hidden_window.study_boxes) == {name for name, _t, _w in hidden_window._studies()}

    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)
    hidden_window._sync()

    box, says = hidden_window.study_boxes[window.SHADOW_JOB]
    made = sum(1 for sheet in hidden_window.planned() if sheet.job == window.SHADOW_JOB)
    assert made > 0
    assert says.cget("text") == f"{made} sheets"
    assert str(box.cget("style")) == "Box.TFrame"

    off_box, off_says = hidden_window.study_boxes[window.SUN_EYE_JOB]
    assert off_says.cget("text") == "off"
    assert str(off_box.cget("style")) == "BoxOff.TFrame", "a study nobody switched on goes grey"


def test_a_study_s_rows_are_inside_its_own_box(hidden_window: Any) -> None:
    """The rows are built by the code that always built them, pointed at the
    box instead of at the page. Worth pinning because nothing else would
    notice a row that ended up outside: it would simply sit on the page."""

    def inside(widget: Any, box: Any) -> bool:
        above = widget
        while above is not None:
            if above is box:
                return True
            above = getattr(above, "master", None)
        return False

    shadow_box, _ = hidden_window.study_boxes[window.SHADOW_JOB]
    plans_box, _ = hidden_window.study_boxes[window.PLANS_JOB]
    assert inside(hidden_window.shadow_hours, shadow_box)
    assert inside(hidden_window.instants, plans_box)
    assert not inside(hidden_window.instants, shadow_box)
    assert not inside(hidden_window.adg_subset, plans_box), "and the page's own rows stay out"


def test_the_band_is_never_empty(hidden_window: Any) -> None:
    """With nothing under the pointer the band says what the open tab is for.
    A strip that blanks itself is dead space at the foot of the window, which
    is exactly what the log was."""
    for title in hidden_window.titles:
        hidden_window._show_section(title)
        assert hidden_window.info.title.cget("text") == title
        assert hidden_window.info.short.cget("text") == window.Window.SECTION_BLURB[title]


def test_a_site_sheet_is_not_at_an_hour_of_the_day(hidden_window: Any) -> None:
    """The site sheets are drawn from an address, not from the sun, so they
    carry no day and no hour -- and a sheet titled "21 JUN 12:00" that is
    really a Summary of Controls is a miniature of something the run will
    not make."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_site.set(True)

    sheets = hidden_window.planned()

    assert [sheet.kind for sheet in sheets] == [
        "Context Analysis",
        "Site Analysis",
        "Summary of Controls",
    ]
    assert all(sheet.time == "" and sheet.day == "" for sheet in sheets)
    assert all(sheet.elevation is None for sheet in sheets)


def test_the_sheets_panel_folds_when_the_window_cannot_hold_both(hidden_window: Any) -> None:
    """Only on *crossing* the line. In between, the chevron is the user's:
    somebody who opened the panel in a narrow window meant to, and having it
    snap shut on the next pixel of a resize would be the window arguing."""

    class Resized:
        def __init__(self, widget: Any, width: int) -> None:
            self.widget, self.width = widget, width

    root, dock = hidden_window.root, hidden_window.dock
    assert not dock.folded
    assert hidden_window.fold_below >= window.Window.FOLD_BELOW

    hidden_window._fit(Resized(root, hidden_window.fold_below - 1))
    assert dock.folded, "too narrow for both, so the panel goes to its edge"

    dock.fold(False)  # the chevron, pressed by hand
    hidden_window._fit(Resized(root, hidden_window.fold_below - 40))
    assert not dock.folded, "still narrow, and still open: it was opened on purpose"

    hidden_window._fit(Resized(root, hidden_window.fold_below + 1))
    hidden_window._fit(Resized(root, hidden_window.fold_below - 1))
    assert dock.folded, "crossing the line again folds it again"

    hidden_window._fit(Resized(hidden_window.dock, 10))
    assert dock.folded, "and a child being resized is not the window being resized"


def test_the_sheets_panel_folds_before_it_pushes_a_tab_off_the_window(
    hidden_window: Any,
) -> None:
    """Every tab has to fit beside the panel while the panel is open: a tab
    past the edge of the window is a page nobody can open. The strip is
    measured, so a seventh tab or a wider font moves the line with it."""
    needed = hidden_window.strip.winfo_reqwidth() + window.Dock.WIDTH + 1
    assert hidden_window.fold_below >= needed
    assert window.Window.YIELD in hidden_window.tabs


def test_a_faced_control_stands_on_its_own_colour(hidden_window: Any) -> None:
    """The third trap of the rounded theme, checked on the real window.

    A face is a rounded shape in a square widget, and what shows through its
    four corners is the *style's* background -- not whatever the widget has
    been put on. A button styled for the white page and placed on the grey
    run bar has four white nicks in its corners, which at 4 px is a fault
    nobody can name and everybody can see. So every control that wears a face
    is compared with what it actually stands on.
    """
    from tkinter import ttk as widgets

    style = widgets.Style(hidden_window.root)

    def style_of(widget: Any) -> str:
        """The style a widget is actually drawn with. One it was not given is
        its class name -- except for the two that lie along an axis, whose
        style is the class with the axis in front of it."""
        given = str(widget.cget("style"))
        if given:
            return given
        name = str(widget.winfo_class())
        if name in {"TProgressbar", "TScrollbar", "TScale", "TSeparator"}:
            return f"{str(widget.cget('orient')).title()}.{name}"
        return name

    def ground_of(widget: Any) -> str:
        try:
            return str(style.lookup(style_of(widget), "background")).upper()
        except tk.TclError:
            return str(widget.cget("background")).upper()

    def walk(widget: Any) -> list[Any]:
        found = [widget]
        for child in widget.winfo_children():
            found.extend(walk(child))
        return found

    wrong = []
    for widget in walk(hidden_window.root):
        if not isinstance(widget, widgets.Widget):
            continue
        layout = style.layout(style_of(widget))
        if not layout or not str(layout[0][0]).startswith("Loriini."):
            continue
        parent = widget.master
        if isinstance(parent, widgets.Widget):
            # A card's style colour is the page, for its corners; what sits
            # on the card sits on its white fill. ``theme.INSIDE`` says so.
            stands_on = theme.INSIDE.get(style_of(parent), "") or ground_of(parent)
        else:
            stands_on = str(parent.cget("background")).upper()
        if ground_of(widget) != stands_on.upper():
            wrong.append(f"{style_of(widget)} is styled for {ground_of(widget)} on {stands_on}")

    assert not wrong, sorted(set(wrong))


# ---------------------------------------------------------------------------
# The info box. Two buttons, one box, and the two things it must say.
# ---------------------------------------------------------------------------
def _every_word(widget: Any) -> str:
    """All the text under a widget, as one string.

    The box is built out of forty labels and what matters is that a given
    sentence reached the screen, not which label carries it.
    """
    said = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except tk.TclError:  # pragma: no cover - a widget with no text option
            text = ""
        if text:
            said.append(str(text))
        said.append(_every_word(child))
    return "\n".join(said)


def test_the_info_box_names_every_publisher_and_its_licence(hidden_window: Any) -> None:
    """The question it exists to answer: whose data is on this sheet, and on
    what terms. A source the box does not mention is a credit nobody gives."""
    from sun_study.app import about
    from sun_study.site.sources import SOURCES

    box = about.show(hidden_window.root)
    try:
        said = _every_word(box)
        for source in SOURCES:
            assert source.name in said, f"{source.name} is fetched from and not named"
            assert source.licence in said, f"{source.name} is named without its licence"
            assert source.terms in said, f"{source.name} is named without its terms"
    finally:
        box._close()


def test_the_info_box_hands_over_the_credit_rather_than_describing_it(
    hidden_window: Any,
) -> None:
    """Ready to copy, in the publishers' own wording. Retyping it is how a
    title block ends up crediting 'NSW Spatial' and nobody else."""
    from sun_study.app import about
    from sun_study.site.sources import credit_line

    box = about.show(hidden_window.root)
    try:
        assert box.credit.get("1.0", "end").strip() == credit_line()
    finally:
        box._close()


def test_the_info_box_carries_the_licence_and_the_prototype_notice(
    hidden_window: Any,
) -> None:
    """The other half of what it is for, and the notice that is on every
    sheet, the README and the run bar already."""
    from sun_study import licence
    from sun_study.app import about
    from sun_study.disclaimer import STATUS

    box = about.show(hidden_window.root)
    try:
        said = _every_word(box)
        assert STATUS in said
        for clause in licence.SUMMARY:
            assert clause in said
    finally:
        box._close()


def test_the_site_pages_button_opens_the_box_at_the_registers(hidden_window: Any) -> None:
    """The question occurs on that page, so the button lands on the answer
    rather than at the top of a box the person then has to read through."""
    from sun_study.app import about

    hidden_window._about(about.SOURCES_SECTION)
    box = about._open
    assert box is not None
    try:
        box.update_idletasks()
        assert box._scroller.canvas.yview()[0] > 0.0, "it opened at the top"
    finally:
        box._close()


def test_pressing_it_twice_raises_the_box_rather_than_making_a_second(
    hidden_window: Any,
) -> None:
    """Two copies of an info box is never what anybody meant; the first is
    simply behind the window."""
    from sun_study.app import about

    first = about.show(hidden_window.root)
    try:
        assert about.show(hidden_window.root) is first
    finally:
        first._close()
    assert about._open is None, "closing it must leave nothing behind to raise"

    second = about.show(hidden_window.root)
    assert second is not first
    second._close()


# -- the transcript kept on disk (roadmap R1) ------------------------------


def test_a_run_is_kept_in_a_log_file_and_the_link_opens_it(
    hidden_window: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window shows one line of a run; a failure forty minutes into a
    larger model has to be readable after the fact, so every line goes to a
    file as it comes, and the line left on screen says where."""
    assert hidden_window.log_link.winfo_manager() == "", "no link before there is a log"

    hidden_window._start_log(["shadow diagram"])
    hidden_window._write("── Shadow diagram ──")
    hidden_window._write("  timing: exported the model in 3 min 12 s, memory at most 1.2 GB")

    path = hidden_window.last_log
    assert path is not None
    assert path.parent == tmp_path / "Loriini" / "Logs"
    assert "exported the model in 3 min 12 s" in path.read_text(encoding="utf-8")
    assert hidden_window.log_link.winfo_manager() == "grid"

    hidden_window.incoming.put(("done", 1))
    hidden_window._drain()
    assert hidden_window.log is None, "closed with the run"
    text = path.read_text(encoding="utf-8")
    assert "[the study stopped, exit code 1]" in text
    assert f"The whole run is in {path}" in text
    assert hidden_window.note.cget("text") == f"The whole run is in {path}"

    opened: list[Path] = []

    def opening(where: Path) -> bool:
        opened.append(where)
        return True

    monkeypatch.setattr(run_log, "open_file", opening)
    hidden_window._open_log()
    assert opened == [path]


# -- shadow plans as 3D Documents (roadmap R1) ------------------------------


def test_the_shadow_plans_draw_the_diagrams_days_and_hours_as_documents(
    hidden_window: Any,
) -> None:
    """The same instants, a second way: the diagram's own days and hours go
    with it, what was filled in is sent, and a blank is left to the command."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadow_plans.set(True)
    for name, lit in hidden_window.shadow_day_ticks.items():
        lit.set(name in ("winter", "summer"))
    hidden_window.shadow_plan_label.insert(0, "Proposed")
    hidden_window.shadow_plan_pen.insert(0, "3")

    (job,) = hidden_window.jobs()

    assert job.label == window.SHADOW_PLAN_JOB
    assert job.args[:3] == ["shadow-plans", "--timezone", "Australia/Sydney"]
    assert flag(job.args, "--shadow-date") == ["06-21,12-21"]
    assert flag(job.args, "--shadow-hour") == [hidden_window.shadow_hours.get().strip()]
    # The project's own list: this one has no shadow diagram combination.
    assert flag(job.args, "--layer-combination") == [hidden_window.shadow_plan_combination.get()]
    assert hidden_window.shadow_plan_combination.get() in (
        hidden_window.shadow_plan_combination.cget("values")
    )
    assert flag(job.args, "--label") == ["Proposed"]
    assert flag(job.args, "--shadow-pen") == ["3"]
    assert "--pen-set" not in job.args, "a blank keeps each view's own"

    sheets = hidden_window.planned()
    assert {sheet.study for sheet in sheets} == {"Shadow plans"}
    assert {sheet.day for sheet in sheets} == {"21 Jun", "21 Dec"}

    saved = hidden_window.settings()
    assert saved["study_shadow_plans"] is True
    assert saved["shadow_plan_label"] == "Proposed"
