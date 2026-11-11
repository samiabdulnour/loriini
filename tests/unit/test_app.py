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

from sun_study import PRODUCT
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


def test_the_project_fills_in_what_its_contents_say_and_offers_the_rest(
    hidden_window: Any,
) -> None:
    """The point of the window: a person typing a layer name is the commonest
    way a run measures the wrong thing. But only what the project's contents
    show is picked -- the layer its apartment-sized zones are on. The
    combination and the subsets were picked by one office's words ('IFC',
    'SHADOW', 'ADG'); now they are offered and left blank, which the commands
    read as none (D156)."""
    assert hidden_window.apartments.get() == "06 | Zone.Units"
    assert hidden_window.combination.get() == ""
    assert tuple(hidden_window.combination.cget("values")) == (
        "01 | Plans - DA",
        "12 | IFC ARCH. EXPORT",
    )
    for subset in (hidden_window.shadow_subset, hidden_window.adg_subset):
        assert subset.get() == ""
        assert tuple(subset.cget("values")) == ("ADG DIAGRAMS", "PLANS", "SHADOW DIAGRAMS")

    # By size, not by name: dwellings on a layer no 'Zone.' word would find.
    hidden_window.options = replace(
        hidden_window.options,
        zone_layers=("05 | Dims/Notes.DA", "07 | Residential.Apartments"),
        zone_kinds=(
            probe.ZoneKind(layer="05 | Dims/Notes.DA", label="SC", count=6, area_m2=2.5),
            probe.ZoneKind(
                layer="07 | Residential.Apartments", label="G08", count=15, area_m2=74.0
            ),
        ),
    )
    hidden_window.apartments.set("")
    hidden_window._offer()
    assert hidden_window.apartments.get() == "07 | Residential.Apartments"


def test_the_master_layout_is_offered_and_never_picked(hidden_window: Any) -> None:
    """Which title block a study is issued on is the person's to say: the
    project's masters are offered and none is chosen for them. Run asks when
    it is still blank."""
    assert hidden_window.master.get() == ""
    assert tuple(hidden_window.master.cget("values")) == (
        "A4",
        "DA A1 - VERTICAL COVER/NO SCALE",
        "DA A1 - VERTICAL - No Scale",
    )


def test_a_project_never_located_puts_the_site_on_its_origin_at_a_corner(
    hidden_window: Any,
) -> None:
    """Nothing in an unlocated project for the site to line up with, so every
    panel puts its output on the project origin, at a corner of the lot as a
    model is set out -- each panel has an origin of its own now (D157)."""
    origins = (
        hidden_window.site_context_origin,
        hidden_window.site_sheet_origin,
        hidden_window.site_model_origin,
    )
    assert [origin.get() for origin in origins] == ["Bottom-left corner"] * 3
    hidden_window.do_site_context.set(True)
    hidden_window.site_address.insert(0, "26-30 Campsie St, Campsie NSW 2194")
    (site,) = [job for job in hidden_window.jobs() if job.label == window.SITE_CONTEXT_JOB]
    assert flag(site.args, "--anchor") == ["site"]
    assert flag(site.args, "--origin-at") == ["bottom-left"]


def test_the_facade_run_forces_the_zone_layers_into_the_export(hidden_window: Any) -> None:
    """Without an IfcSpace there is nothing to fit the skin onto the building
    against, and no IFC combination shows the zone layers -- the failure this
    produces is 'the skin cannot be placed', several minutes in."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    (facade,) = hidden_window.jobs()
    assert facade.args[0] == "massing"
    assert flag(facade.args, "--require-layer") == [
        "05 | Dims/Notes.DA",
        "06 | Zone.Balcony",
        "06 | Zone.Units",
    ]


def test_a_layer_that_holds_a_zone_is_exported_whatever_it_is_called(
    hidden_window: Any,
) -> None:
    """The zone layers used to be narrowed to the ones with 'Zone.' in the
    name, which is one office's spelling (D156). Every layer the project
    carries a Zone on is forced in, ``05 | Dims/Notes.DA`` included: which of
    them is the building is not something a layer's name can say."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    (facade,) = hidden_window.jobs()
    assert flag(facade.args, "--require-layer") == list(hidden_window.options.zone_layers)
    assert "05 | Dims/Notes.DA" in flag(facade.args, "--require-layer")


def test_the_floors_tick_is_what_puts_the_decks_in(hidden_window: Any) -> None:
    """Horizontal faces take more sun than any wall, so a study without them
    shows the least-lit half of the building."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    (with_floors,) = hidden_window.jobs()
    assert "--model-flat" in with_floors.args

    hidden_window.do_floors.set(False)
    (without,) = hidden_window.jobs()
    assert "--no-model-flat" in without.args and "--model-flat" not in without.args


def test_the_plans_sheets_go_at_the_root_until_a_subset_is_picked(
    hidden_window: Any,
) -> None:
    """No subset is picked by an office's words (D156): blank sends nothing,
    and the command files the sheets at the root of the book. The subsets the
    person picks from the project's own list are where they go."""
    hidden_window.do_facade.set(False)
    hidden_window.do_plans.set(True)
    (plans,) = hidden_window.jobs()

    assert plans.args[0] == "archicad-run"
    assert "--draw" in plans.args and "--sheet" in plans.args
    assert "--layout-subset" not in plans.args
    assert "--adg-subset" not in plans.args
    assert flag(plans.args, "--plan-instant") == ["09:00", "12:00", "15:00"]

    hidden_window.shadow_subset.set("SHADOW DIAGRAMS")
    hidden_window.adg_subset.set("ADG DIAGRAMS")
    (plans,) = hidden_window.jobs()
    assert flag(plans.args, "--layout-subset") == ["SHADOW DIAGRAMS"]
    assert flag(plans.args, "--adg-subset") == ["ADG DIAGRAMS"]


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


def test_every_solar_grid_offers_the_same_four_steps(hidden_window: Any) -> None:
    """Rough 1 m, Normal 0.5 m, Detailed 0.25 m, Finest 0.1 m -- on the facade
    skin, the communal ground and the apartments' floor alike, so a word on a
    tile means one grid whichever study it is pressed in.

    Each goes to the run as that study's own flag, and the defaults keep the
    metres they always had: 0.5 m on the facade and the communal space, 0.25 m
    on the apartments' floor.
    """
    steps = {"1.0": "Rough", "0.5": "Normal", "0.25": "Detailed", "0.1": "Finest"}
    rows = (hidden_window.grid_m, hidden_window.communal_grid, hidden_window.floor_grid)
    for row in rows:
        assert list(row._buttons) == list(steps)
        assert {value: button.cget("text") for value, button in row._buttons.items()} == steps
    assert [row.get() for row in rows] == ["0.5", "0.5", "0.25"]

    def only(tick: Any) -> None:
        for _name, other, _where in hidden_window._studies():
            other.set(False)
        tick.set(True)

    only(hidden_window.do_facade)
    hidden_window.grid_m.set("0.1")
    (facade,) = hidden_window.jobs()
    assert flag(facade.args, "--model-grid") == ["0.1"]

    only(hidden_window.do_communal)
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.communal_grid.set("0.25")
    (communal,) = hidden_window.jobs()
    assert flag(communal.args, "--zone-grid") == ["0.25"]

    only(hidden_window.do_plans)
    hidden_window.apartments.set("06 | Zone.Units")
    (plans,) = hidden_window.jobs()
    assert flag(plans.args, "--patch-grid") == ["0.25"]
    hidden_window.floor_grid.set("0.1")
    (plans,) = hidden_window.jobs()
    assert flag(plans.args, "--patch-grid") == ["0.1"]
    hidden_window.floor_grid.set("1.0")
    (plans,) = hidden_window.jobs()
    assert flag(plans.args, "--patch-grid") == ["1.0"]
    hidden_window.plan_kinds.set("Apartment total")
    (plans,) = hidden_window.jobs()
    assert not flag(plans.args, "--patch-grid"), "no floor plan, no second ray cast"

    hidden_window.apply({"floor_grid": "0.25"})
    assert hidden_window.floor_grid.get() == "0.25"


def test_a_step_from_before_the_four_is_kept_rather_than_rounded(hidden_window: Any) -> None:
    """0.2 m was Finest and 2 m was Rough until the steps were redone. A
    settings file holding either still sends it, with no tile lit, rather
    than being moved to a neighbour and measuring something else unsaid."""
    hidden_window.apply({"communal_grid": "0.2", "floor_grid": "0.2"})
    assert hidden_window.communal_grid.get() == "0.2"
    assert hidden_window.floor_grid.get() == "0.2"
    assert "0.2" not in hidden_window.communal_grid._on & set(hidden_window.communal_grid._buttons)


def test_see_through_glass_goes_to_all_three_solar_studies_and_no_other(
    hidden_window: Any,
) -> None:
    """One choice, in the card the three share. Solid sends nothing, which is
    the command's own default; the shadow diagram is not a solar study."""
    assert set(hidden_window.see_glass._buttons) == {"off", "30", "80"}
    assert hidden_window.see_glass.get() == "off"
    hidden_window.apartments.set("06 | Zone.Units")
    hidden_window.communal.set("06 | Zone.Balcony")
    for tick in (hidden_window.do_facade, hidden_window.do_plans, hidden_window.do_communal):
        tick.set(True)
    hidden_window.do_shadows.set(True)
    hidden_window.do_shadow_hours.set(True)

    assert not any("--see-through-glass" in job.args for job in hidden_window.jobs())

    hidden_window.see_glass.set("30")
    sent = {job.args[0]: flag(job.args, "--see-through-glass") for job in hidden_window.jobs()}
    assert sent["massing"] == ["30"]
    assert sent["archicad-run"] == ["30"]
    assert sent["shadow-plans"] == []
    assert sent["shadows"] == []
    assert (
        sum(flag(job.args, "--see-through-glass") == ["30"] for job in hidden_window.jobs()) == 3
    ), "the facade and the communal space are both massing runs"

    hidden_window.apply({"see_through_glass": "80"})
    assert hidden_window.see_glass.get() == "80"


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


def test_the_plans_are_drawn_over_the_plan_combination_the_person_picks(
    hidden_window: Any,
) -> None:
    """The plan a reader expects under the sunlight, not the model the study
    reads. Offered from the project and picked by the person -- not guessed
    from words like 'PLAN' or 'GA', which were one office's (D156) -- and
    passed to both plan studies under the names their commands use."""
    assert hidden_window.plan_combination.get() == "", "nothing picked by its name"
    assert "" in hidden_window.plan_combination.cget("values"), "blank: the model's"
    assert "01 | Plans - DA" in hidden_window.plan_combination.cget("values")

    hidden_window.plan_combination.set("01 | Plans - DA")
    hidden_window._offer()
    assert hidden_window.plan_combination.get() == "01 | Plans - DA", "kept across a Refresh"

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
    own = f"{naming.SOLAR_PREFIX} Sun Study Plan"
    hidden_window.options = replace(
        hidden_window.options,
        combinations=(own, "12 | IFC ARCH. EXPORT", "02 | GA Plans"),
    )
    hidden_window.plan_combination.set("")
    hidden_window._offer()

    offered = hidden_window.plan_combination.cget("values")
    assert own not in offered
    assert tuple(offered) == ("", "12 | IFC ARCH. EXPORT", "02 | GA Plans")
    assert hidden_window.plan_combination.get() == "", "offered, not picked"


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
    said one sheet; it now shows the geometry, one per day, and its header
    counts the models alone rather than "0 sheets" in front of them."""
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
    assert says.cget("text") == "2 models"
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


def test_the_context_sheet_is_centred_on_the_site_and_its_walk(hidden_window: Any) -> None:
    """The run centres the context sheet on the site, and the five-minute
    walk is the site's: the miniature had the site off to one side and the
    ring round the station. The station sits inside the walk, and nothing
    is drawn outside the frame, since a canvas clips nothing."""
    frame = (10.0, 20.0, 239.0, 176.0)
    paper: Any = tk.Canvas(hidden_window.root)
    window._draw_context(paper, frame)
    items = paper.find_all()

    def middle(item: int) -> tuple[float, float]:
        x0, y0, x1, y1 = paper.bbox(item)
        return (x0 + x1) / 2, (y0 + y1) / 2

    (site,) = [i for i in items if paper.itemcget(i, "fill") == window.CONTEXT_SITE]
    ovals = [i for i in items if paper.type(i) == "oval"]
    (walk,) = [i for i in ovals if paper.itemcget(i, "outline") == window.RING]
    (station,) = [i for i in ovals if paper.itemcget(i, "fill") == theme.BLUE]
    centre = ((frame[0] + frame[2]) / 2, (frame[1] + frame[3]) / 2)
    for item in (site, walk):
        assert middle(item) == pytest.approx(centre, abs=2)
    reach = (paper.bbox(walk)[2] - paper.bbox(walk)[0]) / 2
    sx, sy = middle(station)
    assert (sx - centre[0]) ** 2 + (sy - centre[1]) ** 2 < reach**2, "the station within the walk"
    for item in items:
        x0, y0, x1, y1 = paper.bbox(item)
        if item != walk:
            assert x0 >= frame[0] - 3 and y0 >= frame[1] - 3, paper.type(item)
            assert x1 <= frame[2] + 3 and y1 <= frame[3] + 3, paper.type(item)


def test_a_model_is_shown_as_geometry_and_not_counted_as_a_sheet(hidden_window: Any) -> None:
    """The site study's context model and future model are geometry on their
    own layers, not layouts. The panel shows them as what they are -- no
    paper -- and the count on the strip stays the count of sheets. One radius
    serves the model and the future's reach (D157), so both say it."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    for sheet_tick in (
        hidden_window.do_site_context,
        hidden_window.do_site_site,
        hidden_window.do_site_summary,
    ):
        sheet_tick.set(True)
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
        (window.FUTURE_MODEL, "300 m reach"),
    ]
    assert all(m.number == "" for m in models), "not numbered as sheets"
    assert all(m.job == window.SITE_MODEL_JOB for m in models), "both the 3D context's"
    assert hidden_window.dock.tally.cget("text") == "3", "three sheets, and the models are not"
    _box, says = hidden_window.study_boxes[window.SITE_MODEL_JOB]
    assert says.cget("text") == "2 models"

    paper = tk.Canvas(hidden_window.root)
    window.draw_model(paper, models[0], 300, 212)
    assert paper.find_withtag("edge"), "and it still takes the blue edge under the pointer"


def test_the_3d_context_panel_counts_its_models_and_no_sheets(hidden_window: Any) -> None:
    """The 3D context makes geometry and no paper, so its header counts the
    models alone. "0 sheets, 1 model" read as a panel that made nothing
    before it said what it did make."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.site_address.insert(0, "1 Example Street")
    hidden_window.do_site_model.set(True)
    hidden_window._sync()
    _box, says = hidden_window.study_boxes[window.SITE_MODEL_JOB]
    assert says.cget("text") == "1 model"

    hidden_window.do_site_future.set(True)
    hidden_window._sync()
    assert says.cget("text") == "2 models", "the future context is a model of its own"
    assert "sheet" not in says.cget("text")


def _texts(paper: Any) -> list[str]:
    """Every text item on a canvas, in the order it was drawn."""
    return [
        str(paper.itemcget(item, "text"))
        for item in paper.find_all()
        if str(paper.type(item)) == "text"
    ]


def _text_items(paper: Any, text: str) -> list[int]:
    """The text items on a canvas that say exactly ``text``."""
    return [
        item
        for item in paper.find_all()
        if str(paper.type(item)) == "text" and paper.itemcget(item, "text") == text
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
    assert "Communal open space" in texts
    assert not any("21 Jun" in text or "whole day" in text for text in texts), texts
    assert texts.count("Communal open space") == 1, "the block does not say the title again"

    paper = tk.Canvas(hidden_window.root)
    window.draw_sheet(paper, FOUR_HOUR_SHEET, 300, 212)
    texts = _texts(paper)
    assert "09:00-12:00   (1 of 2)" in texts, "the hours, and which of the pair"
    assert not any("21 Jun" in text or "drawings" in text or "°" in text for text in texts), texts
    assert texts.count("09:00") == 1, "each cell's own hour, once"


def test_a_cells_hour_clears_the_drawing_above_it(hidden_window: Any) -> None:
    """The room under a cell is measured from the type. A fixed 13 mm was
    shorter than a line of eight points on Windows, and every hour sat on
    the bottom of its drawing."""
    paper: Any = tk.Canvas(hidden_window.root)
    window.draw_sheet(paper, FOUR_HOUR_SHEET, window.Dock.SHEET_W, window.Dock.SHEET_H)
    sheet, edge = paper.find_all()[0], paper.find_withtag("edge")[0]
    (hour,) = _text_items(paper, "09:00")
    under = set(paper.find_overlapping(*paper.bbox(hour))) - {sheet, edge, hour}
    assert not under, [paper.type(item) for item in under]


def test_a_sheet_number_sits_inside_its_chip(hidden_window: Any) -> None:
    """The chip is as wide as its number and the padding. A fixed 34 mm was
    narrower than "SD.01" on Windows, and the number ran into its edges."""
    paper: Any = tk.Canvas(hidden_window.root)
    window.draw_sheet(paper, FOUR_HOUR_SHEET, window.Dock.SHEET_W, window.Dock.SHEET_H)
    (chip,) = paper.find_withtag("chip")
    (number,) = _text_items(paper, "SD.01")
    chip_left, _, chip_right, _ = paper.bbox(chip)
    # A text item's box is a pixel or so wider than its letters.
    number_left, _, number_right, _ = paper.bbox(number)
    assert chip_left + window.CHIP_PAD - 2 <= number_left
    assert number_right <= chip_right - window.CHIP_PAD + 2


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


def test_a_sheet_is_lettered_in_one_style_on_shared_lines(hidden_window: Any) -> None:
    """One size and one weight for every word on a miniature: at 300 px,
    three sizes read as clutter. Two inks, the way a card is set: the name
    and the number in ink, the hour and the scale in the hint grey (D136).
    The scale and the number sit in the block level with the two lines of
    the sheet's name beside them, the number in the sidebar's chip, and
    there is no north mark: the master carries one."""
    paper: Any = tk.Canvas(hidden_window.root)
    window.draw_sheet(paper, replace(FOUR_HOUR_SHEET, scale="1:50"), 300, 212)
    block_left = 300 * (1 - 53.0 / window.SHEET_MM_W)
    items = paper.find_all()
    texts = [i for i in items if str(paper.type(i)) == "text"]

    assert len({paper.itemcget(i, "font") for i in texts}) == 1, "one size and weight"
    assert {paper.itemcget(i, "fill") for i in texts} == {theme.INK, theme.HINT}, "two inks"

    def at(text: str) -> Any:
        (found,) = [i for i in texts if paper.itemcget(i, "text") == text]
        return paper.coords(found)

    def ink(text: str) -> str:
        (found,) = [i for i in texts if paper.itemcget(i, "text") == text]
        return str(paper.itemcget(found, "fill"))

    assert at("1:50")[0] >= block_left and at("SD.01")[0] >= block_left
    assert at("1:50")[1] == at("Shadow diagram")[1], "the scale beside the name"
    assert at("SD.01")[1] == at("09:00-12:00   (1 of 2)")[1], "the number beside the hours"
    assert ink("Shadow diagram") == ink("SD.01") == theme.INK
    assert ink("1:50") == ink("09:00-12:00   (1 of 2)") == theme.HINT, "what is second, in grey"

    ring = [i for i in items if str(paper.type(i)) == "oval" and paper.bbox(i)[0] >= block_left]
    assert not ring, "no north: the master carries one"
    (chip,) = paper.find_withtag("chip")
    assert paper.itemcget(chip, "fill") == theme.ACCENT_TINT, "the number in the sidebar's chip"
    assert paper.bbox(chip)[0] >= block_left and paper.bbox(chip)[1] < at("SD.01")[1]
    assert not [i for i in texts if paper.itemcget(i, "text") in {"N", "LORIINI"}]


def test_each_site_sheet_follows_its_own_tick(hidden_window: Any) -> None:
    """Three sheets, three switches, and the site sheet's run gets
    --no-context and --no-summary while those are off -- so the panel must
    drop them too."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.site_address.insert(0, "1 Example Street")
    hidden_window.do_site_site.set(True)

    assert [sheet.kind for sheet in hidden_window.planned()] == ["Site Analysis"]
    (site,) = hidden_window.jobs()
    assert site.label == window.SITE_SHEET_JOB
    assert "--no-summary" in site.args and "--no-context" in site.args and "--site" in site.args


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


def test_the_reference_image_is_a_page_under_tools_for_the_chosen_project(
    hidden_window: Any,
) -> None:
    """The reference image is a tool, so it is a page of its own under
    Tools: pressing for it opens that page, and its controls are told which
    project is chosen so that the Archicad window they look for is that one.
    No picture window is made until there is a picture to show."""
    hidden_window._reference()
    assert hidden_window.showing == window.Window.REFERENCE
    assert hidden_window.palette.project() == "SAMPLE"
    assert hidden_window.palette._overlay is None
    assert not hidden_window._picture_open()


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
    hidden_window.yield_slabs.set("Slabs on chosen layers")
    hidden_window.yield_massing.insert(0, "01 | Massing - Main Building.3D OPT2")
    hidden_window.yield_commercial_levels.insert(0, "Ground, Level 01")
    # Filled, but in rows this answer does not show: they must not count.
    hidden_window.yield_residential.insert(0, "01 | Wall.External")
    hidden_window.yield_commercial.insert(0, "01 | Floor.Structural")
    hidden_window.yield_renovation_status.set("As the floor plan's filter")
    hidden_window.yield_site_area.insert(0, "1386.78")
    hidden_window.yield_fsr_residential.insert(0, "2.8")
    hidden_window.yield_fsr_commercial.insert(0, "0.4")
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
    assert "--residential-layer" not in args and "--commercial-layer" not in args, (
        "a layer left in a hidden row changes nothing"
    )
    assert flag(args, "--massing-layer") == ["01 | Massing - Main Building.3D OPT2"]
    assert flag(args, "--commercial-level") == ["Ground", "Level 01"]
    assert not any("retail" in arg for arg in args), "shops are commercial (D159)"
    assert "--renovation-filter" in args
    assert flag(args, "--gfa-residential") == ["0.725"]
    assert flag(args, "--gfa-commercial") == ["0.85"]
    assert flag(args, "--nla-commercial") == ["0.9"]
    assert flag(args, "--affordable-share") == ["15"]
    assert flag(args, "--sqm-per-space") == ["40"]
    assert flag(args, "--basement-site-ratio") == ["0.4"]
    assert flag(args, "--site-area") == ["1386.78"]
    assert flag(args, "--fsr-residential") == ["2.8"]
    assert flag(args, "--fsr-commercial") == ["0.4"]
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
    hidden_window.yield_slabs.set("A layer per option")
    hidden_window.yield_option_layers.insert(0, "01 | Massing.3D OPT1, 01 | Massing.3D OPT2")
    hidden_window.yield_workbook.insert(0, r"P:³3\Yield.xlsx")
    hidden_window.tables.delete(0, "end")
    hidden_window.tables.insert(0, str(tmp_path))
    (job,) = hidden_window.jobs()
    assert flag(job.args, "--option-layer") == ["01 | Massing.3D OPT1", "01 | Massing.3D OPT2"]
    assert "--option" not in job.args, "each option is named after its layer"
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


def test_a_project_with_no_location_draws_sydneys_sun_and_says_so(
    hidden_window: Any,
) -> None:
    """A shadow diagram with no shadows on it shows nothing worth checking,
    so before a project has a location the panel puts Sydney's sun on it --
    Archicad's own preset -- and the card says that is what it is."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)

    without = hidden_window.planned()
    assert without, "the sheets are still listed"
    assert all(sheet.elevation is not None for sheet in without)
    assert any(sheet.reach is not None for sheet in without), "with shadows to draw"
    hidden_window._sheet_under(without[0])
    assert "Sydney" in hidden_window.info.detail.cget("text")

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


def test_a_project_never_saved_is_read_not_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new file has no name, only ``isUntitled``. The window took the blank
    name for a project it could not read and dropped every list it had read."""
    from sun_study.archicad.connection import ArchicadError

    class NewFile:
        tapir_version = "1.5.8"
        database = None

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def run_tapir(self, command: str, parameters: object = None) -> object:
            if command == "GetProjectInfo":
                return {"isUntitled": True, "isTeamwork": False}
            if command == "GetAttributesByType":
                return {"attributes": [{"name": "A1 Master"}]}
            raise ArchicadError(f"{command} is not faked")

        def __getattr__(self, name: str) -> Any:
            def refuse(*_args: object, **_kwargs: object) -> None:
                raise ArchicadError(f"{name} is not faked")

            return refuse

    monkeypatch.setattr(probe, "ArchicadConnection", NewFile)
    found = probe.options(19723)

    assert found.project == "Untitled"
    assert found.reachable is True


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

    assert flag(facade.args, "--layer-prefix") == [naming.SOLAR_PREFIX]
    assert flag(plans.args, "--layer-prefix") == [naming.SOLAR_PREFIX]


def test_the_wait_is_an_hour_and_not_on_the_page(hidden_window: Any) -> None:
    """The wait field was for the IFC export, which on a big project ran to
    minutes, and the studies no longer export that way (D156). Every run is
    still told how long to wait on one command -- an hour, so a genuinely
    slow command is waited on and a stuck Archicad is not waited on for ever
    -- and a settings file saved while the field was there still opens."""
    assert not hasattr(hidden_window, "wait_min")
    assert "Archicad wait (min)" not in every_text(hidden_window.root)
    hidden_window.apply({"archicad_wait_minutes": "45"})
    assert "archicad_wait_minutes" not in hidden_window.settings()

    for _name, tick, _where in hidden_window._studies():
        tick.set(True)
    hidden_window.site_address.insert(0, "212 Bondi Rd, Bondi")
    hidden_window.communal.set("06 | Zone.Balcony")
    jobs = hidden_window.jobs()

    assert len(jobs) > 1
    for job in jobs:
        assert flag(job.args, "--timeout") == ["3600"], job.label


def test_reading_the_project_does_not_wait_the_exports_wait() -> None:
    """The window fills its lists in while somebody watches. Inheriting the
    half-hour meant for the export would hang it on an Archicad that is merely
    busy, so the reads keep a wait of their own."""
    assert probe.READING_SECONDS < DEFAULT_TIMEOUT_SECONDS


def test_another_offices_numbering_reaches_the_command_line(hidden_window: Any) -> None:
    """The default is the tool's own word, 'Solar |'. An office that numbers
    its layer groups types its own number in, which is the whole reason for
    the field."""
    hidden_window.do_facade.set(True)  # off in the basic preset
    hidden_window.prefix_solar.delete(0, "end")
    hidden_window.prefix_solar.insert(0, "ZZ |")
    (facade,) = hidden_window.jobs()

    assert flag(facade.args, "--layer-prefix") == ["ZZ |"]


def test_each_tool_files_its_work_under_its_own_number(hidden_window: Any) -> None:
    """Four drawings, four numbers. Under one prefix the layer list ran the
    apartment results, the shadow sheets, the sun views and the site analysis
    together, and only the group word after the number told them apart.

    Each tool's default is its own word (D156). Read off the argv rather than
    the boxes, because the argv is what Archicad ends up being told.
    """
    hidden_window.do_facade.set(True)
    hidden_window.do_plans.set(True)
    hidden_window.do_shadows.set(True)
    hidden_window.do_sun_eyes.set(True)
    hidden_window.do_site_context.set(True)
    hidden_window.do_site_model.set(True)
    hidden_window.site_address.insert(0, "212 Bondi Rd, Bondi")

    under = {job.label: flag(job.args, "--layer-prefix") for job in hidden_window.jobs()}

    assert under[window.FACADE_JOB] == [naming.SOLAR_PREFIX]
    assert under[window.PLANS_JOB] == [naming.SOLAR_PREFIX]
    assert under[window.SHADOW_JOB] == [naming.SHADOW_PREFIX]
    assert under[window.SUN_EYE_JOB] == [naming.SUN_VIEW_PREFIX]
    assert under[window.SITE_CONTEXT_JOB] == [naming.SITE_PREFIX]
    assert under[window.SITE_MODEL_JOB] == [naming.SITE_PREFIX], "each site run, not the first"
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
    others would be an option they do not have. Every site run hears it: the
    3D context stands the neighbours in that group, and a sheet's run may be
    the one that does when the panels run apart (D157)."""
    hidden_window.do_site_context.set(True)
    hidden_window.do_site_model.set(True)
    hidden_window.do_shadows.set(True)
    hidden_window.site_address.insert(0, "212 Bondi Rd, Bondi")
    hidden_window.prefix_context.delete(0, "end")
    hidden_window.prefix_context.insert(0, "50 |")

    by_tool = {job.label: job.args for job in hidden_window.jobs()}

    for site_run in (window.SITE_CONTEXT_JOB, window.SITE_MODEL_JOB):
        assert flag(by_tool[site_run], "--context-prefix") == ["50 |"], site_run
        assert flag(by_tool[site_run], "--layer-prefix") == [naming.SITE_PREFIX], (
            "and the site analysis is still filed under its own number"
        )
    assert "--context-prefix" not in by_tool[window.SHADOW_JOB]


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

    Off a Mac, which is asked here so the macOS runner checks this branch too;
    the Mac's own is in test_macos.
    """
    monkeypatch.setattr(theme, "MACOS", False)
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


def test_a_mac_trackpad_glides_the_page(hidden_window: Any) -> None:
    """Tk 9 sends a Mac trackpad's two fingers as an event of its own, by the
    pixel; bound to the wheel alone, the page stood still under them."""
    form = hidden_window.panes[0]
    form.canvas.configure(scrollregion=(0, 0, 100, 4000))

    form.glide(-200)  # fingers up: the page moves on
    moved = form.canvas.yview()[0]
    form.glide(10_000)  # and far past the top is held at the top

    assert moved > 0.0
    assert form.canvas.yview()[0] == 0.0
    if hidden_window.root.tk.call("info", "patchlevel").startswith("9"):
        assert hidden_window.root.bind_all("<TouchpadScroll>"), "and the event is listened for"


def test_a_shadow_is_held_to_the_site() -> None:
    """A long morning shadow ran out of its cell and over the hour under it."""
    cut = window._clip_to([(0, 0), (300, 0), (300, 300), (0, 300)], (10, 20, 50, 60))

    assert {(round(x), round(y)) for x, y in cut} == {(10, 20), (50, 20), (50, 60), (10, 60)}


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
    """The point of the whole thing: the layer prefix and the living-room
    suffix are properties of the practice, not of the job, and retyping them
    every time is both tedious and a way to get one subtly wrong."""
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
    # An office that numbers its layer groups types its number in once.
    hidden_window.prefix_solar.delete(0, "end")
    hidden_window.prefix_solar.insert(0, "14 |")
    hidden_window._remember()

    # Never shown, like the window it reopens: what is read back is the
    # point, and a window on the screen is laid out and drawn for nothing.
    top = tk.Toplevel(hidden_window.root)
    top.withdraw()
    reopened = window.Window(top)  # type: ignore[arg-type]

    assert reopened.livable.get() == "_L"
    assert reopened.prefix_solar.get() == "14 |"
    assert flag(reopened.jobs()[0].args, "--layer-prefix") == ["14 |"], "and it reaches the run"


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
    assert hidden_window.master.cget("values"), "and the project's own lists are read again"


def test_the_open_project_overrules_a_saved_name_it_does_not_have(
    hidden_window: Any,
) -> None:
    """A saved layer name from another job must not make a run measure a
    layer that is not in this one. The lists are refilled from Archicad after
    the settings land, and a name the project cannot offer is cleared -- a
    master is then asked for at Run, never guessed."""
    hidden_window.apply({"master_layout": "A0 - SOMEBODY ELSE'S TITLE BLOCK"})

    hidden_window.refresh()

    assert hidden_window.master.get() == ""
    hidden_window.apply({"master_layout": "DA A1 - VERTICAL - No Scale"})
    hidden_window.refresh()
    assert hidden_window.master.get() == "DA A1 - VERTICAL - No Scale", "a name it has is kept"


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
    model rather than an IFC or a folder of published views (D113). The
    every-hour drawing of a named design is read out of 3D Documents, so it
    is the documents' command that takes the rows."""
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    hidden_window.do_facade.set(False)
    hidden_window.do_shadow_hours.set(True)
    rows["EXISTING"].insert(0, "01 | Wall.External, 01 | Floor.Structural")
    rows["PROPOSED"].insert(0, "06 | Zone.Units")
    hidden_window.terrain_layers.insert(0, "05 | Dims/Notes.DA")

    (job,) = hidden_window.jobs()

    assert job.args[0] == "shadow-plans"
    assert "--every-hour-only" in job.args
    assert flag(job.args, "--shadow-source") == [
        "EXISTING=01 | Wall.External,01 | Floor.Structural"
    ]
    assert flag(job.args, "--shadow-scenario") == ["PROPOSED=06 | Zone.Units"]
    assert "--shadow-from-views" not in job.args
    assert "--shadow-favourite" not in job.args


def test_every_study_that_exports_asks_for_the_native_model(hidden_window: Any) -> None:
    """No job is left on ``auto``, which falls back to an IFC export when the
    add-on is out of date: the run is to stop and say so instead."""
    hidden_window.do_facade.set(True)
    hidden_window.do_plans.set(True)
    hidden_window.do_communal.set(True)
    hidden_window.do_shadow_hours.set(True)

    exporting = [job for job in hidden_window.jobs() if job.args[0] != "site"]

    assert {job.args[0] for job in exporting} >= {"massing", "archicad-run", "shadows"}
    for job in exporting:
        assert flag(job.args, "--export") == ["native"], job.args[0]


def test_every_hour_on_one_drawing_is_asked_for_only_when_ticked(hidden_window: Any) -> None:
    """The shadow diagram is the documents; the fills run only for the
    every-hour drawing, and then for nothing else (D144, D160)."""
    hidden_window.do_facade.set(False)
    hidden_window.do_shadows.set(True)
    (job,) = hidden_window.jobs()
    assert job.label == window.SHADOW_JOB
    assert job.args[0] == "shadow-plans"

    hidden_window.do_shadow_hours.set(True)
    (_documents, job) = hidden_window.jobs()
    assert job.label == window.SHADOW_HOURS_JOB
    assert job.args[0] == "shadows"
    assert "--shadow-all-hours-only" in job.args
    # Drawn and sheeted: without these the command measures and draws nothing,
    # which is what the window's fills job had always sent it.
    assert "--draw" in job.args and "--sheet" in job.args
    assert flag(job.args, "--shadow-all-hours-colour") == ["red"]
    # The sun studies' four grid steps, Normal to start with (D161).
    assert flag(job.args, "--shadow-grid") == ["0.5"]
    hidden_window.shadow_grid.set("0.1")
    assert flag(hidden_window.jobs()[1].args, "--shadow-grid") == ["0.1"]
    assert hidden_window.settings()["shadow_grid"] == "0.1"
    assert hidden_window.settings()["study_shadow_hours"] is True

    hidden_window.shadow_hours_colour.set("blue")
    assert flag(hidden_window.jobs()[1].args, "--shadow-all-hours-colour") == ["blue"]


def test_the_legend_rows_are_the_legends_own(hidden_window: Any) -> None:
    """Three that accumulate, then three that are compared, Proposed first on
    the page; the short names are what the drawing matches to the legend's
    colours (D178)."""
    from sun_study.archicad.shadows import LEGEND

    rows = [(short, role) for short, role, _box in hidden_window.shadow_rows]
    assert [short for short, _role in rows] == [
        "EXISTING",
        "FUTURE",
        "EXISTING ON SITE",
        "PROPOSED",
        "PROPOSED 2",
        "PROPOSED 3",
    ]
    assert sorted(rows) == sorted((short, role) for short, _words, role, _rgb in LEGEND)


def test_the_proposals_are_compared_and_proposed_is_drawn_on_top(
    hidden_window: Any,
) -> None:
    """Proposed 2 and 3 are scenarios, compared rather than added. Listed
    after Proposed on the page, they are sent before it, in the legend's
    order, so Proposed is drawn last and lies on top."""
    rows = {short: (role, box) for short, role, box in hidden_window.shadow_rows}
    assert rows["PROPOSED 2"][0] == rows["PROPOSED 3"][0] == "scenario"

    hidden_window.do_shadows.set(True)
    rows["PROPOSED"][1].insert(0, "20 | Massing")
    rows["PROPOSED 2"][1].insert(0, "20 | Massing.Option")
    rows["PROPOSED 3"][1].insert(0, "01 | Floor.Structural")
    job = next(job for job in hidden_window.jobs() if job.args[0] == "shadow-plans")

    assert flag(job.args, "--shadow-scenario") == [
        "PROPOSED 2=20 | Massing.Option",
        "PROPOSED 3=01 | Floor.Structural",
        "PROPOSED=20 | Massing",
    ]


def test_a_preset_with_the_older_envelope_rows_opens_in_the_proposals(
    hidden_window: Any,
) -> None:
    """The TOD, SEARs and ADG envelope rows of an older preset move into
    Proposed 2 and 3, the first two filled, and the log names a third rather
    than dropping it unseen (D178)."""
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    hidden_window.apply(
        {
            "shadow_layers_tod": "20 | Massing.TOD",
            "shadow_layers_sears": "20 | Massing.SEARs",
            "shadow_layers_adg envelope": "20 | Massing.ADG",
            "shadow_layers_proposed": "20 | Massing",
        }
    )
    assert rows["PROPOSED"].get() == "20 | Massing"
    assert rows["PROPOSED 2"].get() == "20 | Massing.TOD"
    assert rows["PROPOSED 3"].get() == "20 | Massing.SEARs"
    assert "ADG ENVELOPE row (20 | Massing.ADG)" in hidden_window.lines[-1]

    # A preset of this version is read as it is.
    hidden_window.apply({"shadow_layers_proposed 2": "", "shadow_layers_tod": "20 | Massing.TOD"})
    assert rows["PROPOSED 2"].get() == ""


def test_the_legend_rows_survive_a_save(hidden_window: Any) -> None:
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    rows["PROPOSED 2"].insert(0, "01 | Floor.Structural")
    saved = hidden_window.settings()
    assert saved["shadow_layers_proposed 2"] == "01 | Floor.Structural"


def test_the_shadow_study_sends_only_what_was_filled_in(hidden_window: Any) -> None:
    """Blank fields are left off so the command's own defaults stand.

    A favourite passed as an empty string is not "no favourite" to Archicad,
    it is a Favorite with no name, and the run fails on it several minutes in.
    """
    hidden_window.do_facade.set(False)
    hidden_window.do_shadow_hours.set(True)

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
    hidden_window.do_shadow_hours.set(True)

    assert [job.args[0] for job in hidden_window.jobs()] == [
        "massing",
        "archicad-run",
        "massing",
        "shadow-plans",
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
    # No override and no base picked for the person (D156): blank sends
    # nothing, and the command keeps the plan as it stands.
    assert "--override" not in job.args
    assert "--base-combination" not in job.args
    hidden_window.eye_override.set("Sun Eye Views")
    (job,) = hidden_window.jobs()
    assert job.args[job.args.index("--override") + 1] == "Sun Eye Views"
    # The hours open lit at the ruleset's window, and lit exactly so they
    # send nothing: the ruleset's own window stands, not a copy of it.
    assert hidden_window.eye_hours.get(), "the row shows the hours it will draw"
    assert "--hour" not in job.args
    # Blank hours are the same answer.
    hidden_window.eye_hours.delete(0, "end")
    (job,) = hidden_window.jobs()
    assert "--hour" not in job.args
    # And a narrower set is sent as pressed.
    hidden_window.eye_hours.insert(0, "9, 12")
    (job,) = hidden_window.jobs()
    assert "--hour" in job.args


def test_the_sun_eye_override_and_layers_are_offered_from_the_project_and_none_picked(
    hidden_window: Any,
) -> None:
    """Both lists are the open project's own: the overrides through the
    add-on, which is the only thing that can list them, and the layer
    combinations through Tapir. Blank first in both, and blank is what they
    open on: 'Sun Eye Views' and '04 | Shadow Diagrams' were one office's
    names, not anything a project says about itself (D156)."""
    assert list(hidden_window.eye_override.cget("values")) == [
        "",
        "Clean",
        "Sun Eye Views",
        "Zone Colours",
    ]
    assert hidden_window.eye_override.get() == ""
    assert list(hidden_window.eye_base_combination.cget("values")) == [
        "",
        "01 | Plans - DA",
        "12 | IFC ARCH. EXPORT",
    ]
    assert hidden_window.eye_base_combination.get() == ""

    hidden_window.eye_override.set("Sun Eye Views")
    hidden_window.eye_base_combination.set("01 | Plans - DA")
    hidden_window._offer()
    assert hidden_window.eye_override.get() == "Sun Eye Views", "a choice survives a Refresh"
    assert hidden_window.eye_base_combination.get() == "01 | Plans - DA"


def test_the_sun_eye_settings_survive_a_save(hidden_window: Any) -> None:
    hidden_window.eye_scale.delete(0, "end")
    hidden_window.eye_scale.insert(0, "200")
    hidden_window.do_sun_eyes.set(True)
    saved = hidden_window.settings()
    assert saved["eye_scale"] == "200"
    assert saved["study_sun_eyes"] is True


def test_the_site_analysis_runs_from_an_address_and_names_its_sheets(hidden_window: Any) -> None:
    """The one study that reads nothing off the project: an address in, a
    panel switched on, and its origin said in words on the page and as a
    keyword on the command line."""
    hidden_window.do_facade.set(False)
    hidden_window.do_site_context.set(True)
    hidden_window.site_address.insert(0, "26-30 Campsie St, Campsie NSW 2194")
    hidden_window.site_context_origin.set("Site centre")
    (site,) = hidden_window.jobs()
    assert site.label == window.SITE_CONTEXT_JOB
    assert site.args[:2] == ["site", "26-30 Campsie St, Campsie NSW 2194"]
    assert "--context" in site.args and "--no-site" in site.args and "--no-summary" in site.args
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
    model, context = hidden_window.jobs()
    assert model.label == window.SITE_MODEL_JOB and "--model" in model.args
    assert "--model" not in context.args, "the model is a run of its own"
    assert "--keep-location" in model.args and "--keep-location" in context.args


def test_the_site_can_be_set_on_a_corner_and_turned_level_from_the_page(
    hidden_window: Any,
) -> None:
    """Two words on the panel, two flags on the command line, and neither
    sent while the panel trusts the project's location, where the project
    already says where the site is and which way it faces. The north is kept
    on the page for when the origin comes back to a point of the site."""
    hidden_window.do_facade.set(False)
    hidden_window.do_site_site.set(True)
    hidden_window.site_address.insert(0, "59 Great Buckingham St, Redfern NSW 2016")
    hidden_window.site_sheet_origin.set("Bottom-left corner")
    hidden_window.site_sheet_north.set("Long boundary level")
    (site,) = hidden_window.jobs()
    assert flag(site.args, "--anchor") == ["site"]
    assert flag(site.args, "--origin-at") == ["bottom-left"]
    assert "--square-to-site" in site.args
    hidden_window.site_sheet_origin.set("Project location")
    (site,) = hidden_window.jobs()
    assert flag(site.args, "--anchor") == ["location"]
    assert "--origin-at" not in site.args and "--square-to-site" not in site.args
    saved = hidden_window.settings()
    assert saved["site_sheet_origin"] == "Project location"
    assert saved["site_sheet_north"] == "Long boundary level"


def test_every_site_run_is_placed_by_its_panel_and_never_fitted_to_a_drawn_boundary(
    hidden_window: Any,
) -> None:
    """D158. The fit to a boundary drawn in the file overrode each panel's
    Origin and North without saying so on the page, so the window has no
    such option and tells every run not to fit. The model levels are the 3D
    context's own, so only its run hears them; a typed RL goes through as
    the datum, a trailing 'm' and all."""
    hidden_window.do_facade.set(False)
    hidden_window.do_site_model.set(True)
    hidden_window.site_address.insert(0, "22A O'Connell Street, Parramatta")
    (site,) = hidden_window.jobs()
    assert flag(site.args, "--fit-layer") == ["none"]
    assert "--datum" not in site.args
    assert not hasattr(hidden_window, "site_fit")
    # Nor a run folder to pick: the command keeps its own, one per address.
    assert "--out" not in site.args
    assert not hasattr(hidden_window, "site_out")

    hidden_window.do_site_context.set(True)
    hidden_window.site_levels.set("Project zero is sea level (AHD)")
    model, context = hidden_window.jobs()
    assert flag(model.args, "--fit-layer") == flag(context.args, "--fit-layer") == ["none"]
    assert flag(model.args, "--datum") == ["sea"]
    assert "--datum" not in context.args, "a sheet has no levels to place"

    hidden_window.site_levels.set("5.85 m")
    model, _context = hidden_window.jobs()
    assert flag(model.args, "--datum") == ["5.85"]

    saved = hidden_window.settings()
    assert "site_fit" not in saved
    assert saved["site_levels"] == "5.85 m"


def test_the_site_analysis_waits_for_an_address(hidden_window: Any) -> None:
    """Every panel switched on with nothing typed, and there is no job: the
    address is the study, for each of its four runs alike."""
    hidden_window.do_facade.set(False)
    for site_tick in (
        hidden_window.do_site_context,
        hidden_window.do_site_site,
        hidden_window.do_site_model,
        hidden_window.do_site_summary,
    ):
        site_tick.set(True)
    assert hidden_window.jobs() == []
    saved = hidden_window.settings()
    assert {"site_context", "site_site", "site_model", "site_summary"} <= set(saved)
    assert "study_site" not in saved, "one switch per panel now, and no master tick"
    # The sample project was never located, so each panel puts the site on its origin.
    assert (
        saved["site_context_origin"]
        == saved["site_sheet_origin"]
        == saved["site_model_origin"]
        == "Bottom-left corner"
    )


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
    """What is not a panel of its own is a button, worded short, over the very
    same variable -- so a preset that ticked the future context still lights
    the button, and pressing the button is the tick. The two sheets and the
    model moved into panels headed by their own switches (D157); the
    controls table and the location stay buttons in the Address panel, and
    the future context is one in the 3D context's."""
    buttons = hidden_window.site_buttons
    assert list(buttons) == [
        "Summary of Controls layout",
        "Set the project location from the address",
        "Future Context (what the controls allow next door)",
    ]
    assert [button.cget("text") for button in buttons.values()] == [
        "Controls",
        "Location",
        "Future context",
    ]
    assert not any(button.cget("image") for button in buttons.values()), "words, not drawings"

    future = buttons["Future Context (what the controls allow next door)"]
    assert hidden_window.do_site_future.get() is False
    future.invoke()
    assert hidden_window.do_site_future.get() is True
    hidden_window.apply({"site_future": False})
    assert str(future.cget("style")) == "Tile.TButton", "a preset that unticks it unlights it"

    assert hidden_window.do_site_summary.get() is False
    buttons["Summary of Controls layout"].invoke()
    assert hidden_window.do_site_summary.get() is True, "the button is the Controls study's tick"


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
    hidden_window.do_shadow_hours.set(True)

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
    """The reach is the one thing a designer changes; the zones stay put. One
    radius serves the model and the future's reach, as asked (D157), where
    there used to be two fields."""
    hidden_window.site_address.insert(0, "1 Test St, Kogarah NSW")
    hidden_window.do_site_model.set(True)
    hidden_window.do_site_future.set(True)
    hidden_window.site_radius.delete(0, "end")
    hidden_window.site_radius.insert(0, "80")

    (model,) = [job for job in hidden_window.jobs() if job.label == window.SITE_MODEL_JOB]
    assert "--future" in model.args and "--model" in model.args
    assert flag(model.args, "--future-reach") == ["80"]
    assert flag(model.args, "--model-radius") == ["80"], "the model's square is the same radius"
    assert "--future-setback" not in model.args, "the raised buildings are not set back"

    hidden_window.do_site_future.set(False)
    (model,) = [job for job in hidden_window.jobs() if job.label == window.SITE_MODEL_JOB]
    assert "--future" not in model.args and "--future-reach" not in model.args


def test_the_site_command_puts_its_sheets_on_the_chosen_master(hidden_window: Any) -> None:
    """Left off, the site run drew its worksheets and stopped at the first
    sheet asking which master (23 October 2026). Every panel's run gets it,
    since each one may be the run that draws a sheet."""
    for site_tick in (
        hidden_window.do_site_context,
        hidden_window.do_site_site,
        hidden_window.do_site_model,
        hidden_window.do_site_summary,
    ):
        site_tick.set(True)
    hidden_window.site_address.insert(0, "1 Test St, Kogarah NSW")
    runs = [job for job in hidden_window.jobs() if job.args[0] == "site"]
    assert len(runs) == 4
    assert not any("--master-layout" in job.args for job in runs)

    hidden_window.master.set("A1 Landscape Titleblock")
    runs = [job for job in hidden_window.jobs() if job.args[0] == "site"]
    assert [flag(job.args, "--master-layout") for job in runs] == [["A1 Landscape Titleblock"]] * 4


#: The flags that say which of the site command's outputs a run makes.
SITE_OUTPUTS = frozenset(
    {"--context", "--no-context", "--site", "--no-site", "--summary", "--no-summary", "--model"}
)


def _site_panels_only(hidden_window: Any, *ticks: tk.BooleanVar) -> None:
    """Every study off, then only these site panels on, at an address."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.site_address.insert(0, "1 Example Street")
    for tick in ticks:
        tick.set(True)


def test_each_lit_panel_is_a_run_of_its_own_with_only_its_own_output_on(
    hidden_window: Any,
) -> None:
    """The command places everything one run draws in one frame, so a panel
    placed its own way is a run of its own (D157), and a run that drew the
    others' outputs too would draw them in the wrong frame. The 3D context
    goes first: the model has to line up with the building."""
    _site_panels_only(
        hidden_window,
        hidden_window.do_site_summary,
        hidden_window.do_site_site,
        hidden_window.do_site_context,
        hidden_window.do_site_model,
    )

    runs = hidden_window.jobs()

    assert [job.label for job in runs] == [
        window.SITE_MODEL_JOB,
        window.SITE_CONTEXT_JOB,
        window.SITE_SHEET_JOB,
        window.SITE_CONTROLS_JOB,
    ]
    assert all(job.args[:2] == ["site", "1 Example Street"] for job in runs)
    outputs = [[word for word in job.args if word in SITE_OUTPUTS] for job in runs]
    assert outputs == [
        ["--no-context", "--no-site", "--no-summary", "--model"],
        ["--context", "--no-site", "--no-summary"],
        ["--no-context", "--site", "--no-summary"],
        ["--no-context", "--no-site", "--summary"],
    ]
    assert [sheet.job for sheet in hidden_window.planned() if sheet.paper] == [
        window.SITE_CONTEXT_JOB,
        window.SITE_SHEET_JOB,
        window.SITE_CONTROLS_JOB,
    ], "and each sheet is counted under the panel that makes it"


def test_only_the_first_run_writes_the_project_location(hidden_window: Any) -> None:
    """The project has one location and one north, and every run placed at
    the origin would write its own (D157). So the first run writes it and
    every later one is told to keep it -- it goes first so that a later panel
    placed by the project's location finds the one it wrote. With Location
    off, none writes it; the controls table places nothing, so never does."""
    _site_panels_only(
        hidden_window,
        hidden_window.do_site_context,
        hidden_window.do_site_site,
        hidden_window.do_site_summary,
    )
    first, *later = hidden_window.jobs()
    assert first.label == window.SITE_CONTEXT_JOB
    assert "--keep-location" not in first.args
    assert [("--keep-location" in job.args) for job in later] == [True, True]

    hidden_window.do_site_model.set(True)
    first, *later = hidden_window.jobs()
    assert first.label == window.SITE_MODEL_JOB, "the model leads when it is on"
    assert "--keep-location" not in first.args
    assert all("--keep-location" in job.args for job in later)

    hidden_window.do_site_location.set(False)
    assert all("--keep-location" in job.args for job in hidden_window.jobs())

    hidden_window.do_site_location.set(True)
    for panel in (
        hidden_window.do_site_context,
        hidden_window.do_site_site,
        hidden_window.do_site_model,
    ):
        panel.set(False)
    (controls,) = hidden_window.jobs()
    assert controls.label == window.SITE_CONTROLS_JOB
    assert "--keep-location" in controls.args, "a table does not say where the project is"


def test_each_panels_own_origin_and_north_reach_only_its_own_run(hidden_window: Any) -> None:
    """Origin and north are one per panel, as asked (D157): a site sheet
    turned to its long boundary beside a model on the project's north, and a
    context sheet where the project's own location puts it."""
    _site_panels_only(
        hidden_window,
        hidden_window.do_site_model,
        hidden_window.do_site_context,
        hidden_window.do_site_site,
    )
    hidden_window.site_context_origin.set("Project location")
    hidden_window.site_context_north.set("Long boundary level")
    hidden_window.site_sheet_origin.set("Bottom-left corner")
    hidden_window.site_sheet_north.set("Long boundary level")
    hidden_window.site_model_origin.set("Site centre")
    hidden_window.site_model_north.set("To the project's north")

    by_run = {job.label: job.args for job in hidden_window.jobs()}

    context = by_run[window.SITE_CONTEXT_JOB]
    assert flag(context, "--anchor") == ["location"]
    assert "--origin-at" not in context and "--square-to-site" not in context, (
        "the project already says where the site is and which way it faces"
    )
    site = by_run[window.SITE_SHEET_JOB]
    assert flag(site, "--anchor") == ["site"]
    assert flag(site, "--origin-at") == ["bottom-left"]
    assert "--square-to-site" in site
    model = by_run[window.SITE_MODEL_JOB]
    assert flag(model, "--anchor") == ["site"]
    assert "--origin-at" not in model, "the centre is the command's own default"
    assert "--square-to-site" not in model


def test_a_blank_radius_is_the_500_m_the_panel_shows_for_the_model_and_the_future(
    hidden_window: Any,
) -> None:
    """Left to the command, a blank radius was a 500 m model and a 100 m reach,
    where the sheets panel said 500 m for both."""
    hidden_window.site_address.delete(0, "end")
    hidden_window.site_address.insert(0, "1 Test St, Kogarah NSW")
    hidden_window.do_site_model.set(True)
    hidden_window.do_site_future.set(True)
    hidden_window.site_radius.delete(0, "end")
    (run,) = [job for job in hidden_window.jobs() if job.label == window.SITE_MODEL_JOB]
    assert flag(run.args, "--model-radius") == ["500"]
    assert flag(run.args, "--future-reach") == ["500"]


def test_the_future_context_is_stood_by_the_3d_run_alone(hidden_window: Any) -> None:
    """The slabs stand in the 3D context's frame. The site sheet's run draws
    the same envelopes dashed in its own frame and stands nothing, or two
    runs would stand the future twice in two places (D157). One radius
    serves the model and the reach in both. And the future is the 3D
    context's: with that panel off, no run works it out at all."""
    _site_panels_only(
        hidden_window,
        hidden_window.do_site_model,
        hidden_window.do_site_site,
        hidden_window.do_site_future,
    )
    hidden_window.site_radius.delete(0, "end")
    hidden_window.site_radius.insert(0, "250")

    by_run = {job.label: job.args for job in hidden_window.jobs()}

    model, site = by_run[window.SITE_MODEL_JOB], by_run[window.SITE_SHEET_JOB]
    assert "--future" in model and "--no-future-slabs" not in model
    assert "--future" in site and "--no-future-slabs" in site
    assert flag(model, "--future-reach") == flag(site, "--future-reach") == ["250"]
    assert flag(site, "--model-radius") == ["250"], "worked out over the model's own square"
    assert "--model" not in site

    hidden_window.do_site_model.set(False)
    hidden_window.do_site_context.set(True)
    runs = hidden_window.jobs()
    assert [job.label for job in runs] == [window.SITE_CONTEXT_JOB, window.SITE_SHEET_JOB]
    assert not any("--future" in job.args for job in runs)


def test_the_site_sheets_own_scale_reaches_its_run_and_fit_the_site_sends_none(
    hidden_window: Any,
) -> None:
    """The site sheet has a scale of its own (D157), picked from a list
    (D158): 'Fit the site' leaves the run to fit it, so nothing is sent and
    the sheets panel says so; a scale picked is sent as its denominator."""
    assert not str(hidden_window.site_sheet_scale.cget("state")) == "normal", "no typing"
    assert hidden_window.site_sheet_scale.get() == window.FIT_THE_SITE
    _site_panels_only(hidden_window, hidden_window.do_site_site)
    (site,) = hidden_window.jobs()
    assert "--site-scale" not in site.args
    assert "--scale" not in site.args, "the context sheet's scale is the context run's"
    assert [sheet.scale for sheet in hidden_window.planned()] == ["to fit"]

    hidden_window.site_sheet_scale.set("1:500")
    (site,) = hidden_window.jobs()
    assert flag(site.args, "--site-scale") == ["500"]
    assert "--scale" not in site.args
    assert [sheet.scale for sheet in hidden_window.planned()] == ["1:500"]


def test_the_context_scale_is_picked_from_a_list_and_sent_as_its_denominator(
    hidden_window: Any,
) -> None:
    assert tuple(hidden_window.site_scale.cget("values")) == window.CONTEXT_SCALES
    assert hidden_window.site_scale.get() == "1:3000"
    _site_panels_only(hidden_window, hidden_window.do_site_context)
    hidden_window.site_scale.set("1:2000")
    (context,) = hidden_window.jobs()
    assert flag(context.args, "--scale") == ["2000"]
    assert [sheet.scale for sheet in hidden_window.planned()] == ["1:2000"]


def test_a_saved_choice_in_a_list_that_cannot_be_typed_in_comes_back(
    hidden_window: Any,
) -> None:
    """A read-only list ignores delete and insert, which is how saved
    settings were put back, so every saved style, origin and scale was lost
    on the next opening. It is set now, and only to a value it offers."""
    hidden_window.apply(
        {
            "site_scale": "1:2000",
            "site_sheet_scale": "1:500",
            "site_theme": "Kingfisher",
            "site_sheet_origin": "Bottom-left corner",
            "site_model_north": "Long boundary level",
        }
    )
    assert hidden_window.site_scale.get() == "1:2000"
    assert hidden_window.site_sheet_scale.get() == "1:500"
    assert hidden_window.site_theme.get() == "Kingfisher"
    assert hidden_window.site_sheet_origin.get() == "Bottom-left corner"
    assert hidden_window.site_model_north.get() == "Long boundary level"

    # One the list does not offer -- an older file's typed "3000" -- keeps
    # what the page has rather than becoming a value it cannot run.
    hidden_window.apply({"site_scale": "3000"})
    assert hidden_window.site_scale.get() == "1:2000"


def test_run_asks_for_the_address_whichever_site_panel_is_on(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The master tick that used to guard this is gone, so each of the four
    panels guards it: Controls alone, with no address, says so on Run rather
    than starting nothing in silence."""
    hidden_window.master.set("A4")  # so Run has no master to ask for
    started: list[str] = []
    monkeypatch.setattr(hidden_window, "_next", lambda: started.append("run"))
    monkeypatch.setattr(hidden_window, "_start_log", lambda _studies: None)
    for site_tick in (
        hidden_window.do_site_context,
        hidden_window.do_site_site,
        hidden_window.do_site_model,
        hidden_window.do_site_summary,
    ):
        for _name, tick, _where in hidden_window._studies():
            tick.set(False)
        site_tick.set(True)
        hidden_window._start()
        assert started == [], "nothing was run"
        assert "no address" in hidden_window.lines[-1]


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


def test_every_page_is_a_named_row_in_the_sidebar(hidden_window: Any) -> None:
    """A page in the sidebar is its name, in three groups under their own
    captions; the drawing that sat over each tab took the page's height."""
    for title in hidden_window.titles:
        tab = hidden_window.tabs[title]
        assert tab.cget("text") == title, f"{title} is not named"
        assert not tab.cget("image"), f"{title} still wears a drawing"
    assert [kind for kind, _group in window.Window.GROUPS] == ["SET UP", "STUDIES", "TOOLS"]
    assert dict(window.Window.GROUPS)["TOOLS"] == (window.Window.REFERENCE,)


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


def test_a_page_settles_in_from_the_side_you_came_from(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Down the sidebar, the page rises into place; up it, the page drops.
    Only on a screen, and only where the system has not asked for less
    movement; the page is in place from the moment it is opened either way,
    so nothing in the window waits on the movement."""
    from sun_study.app import motion

    made = hidden_window
    asked: list[bool] = []

    def arrive(self: Any, from_below: bool) -> None:
        asked.append(from_below)

    monkeypatch.setattr(window.Scroller, "arrive", arrive)
    made._show_section(window.Window.GENERAL)
    made._show_section(window.Window.SHADOWS)
    assert asked == [], "a window nobody can see has nothing to show arriving"

    monkeypatch.setattr(made, "_on_screen", lambda: True)
    monkeypatch.setattr(motion, "reduced", lambda: True)
    made._show_section(window.Window.GENERAL)
    assert asked == [], "and none where the system was asked for none"

    monkeypatch.setattr(motion, "reduced", lambda: False)
    made._show_section(window.Window.SHADOWS)
    made._show_section(window.Window.GENERAL)
    made._show_section(window.Window.GENERAL)
    assert asked == [True, False], "down, then up, and not at all for the same page"
    assert made._open_section() == window.Window.GENERAL


def test_open_and_queued_are_two_marks_and_never_the_same_one(hidden_window: Any) -> None:
    """The fault the launcher had: one blue tint that had to mean both "this
    is the page you are on" and "this will run", and so meant neither.

    Two marks on two things. Open is the row's blue bar; queued is the row's
    switch, with what it is worth in the pill beside it. A row can be open,
    queued, both or neither, and all four are told apart.
    """
    hidden_window._show_section(window.Window.GENERAL)
    row, pill, switch, lit = hidden_window.side_rows[window.Window.SHADOWS]
    name = hidden_window.tabs[window.Window.SHADOWS]

    hidden_window.do_shadows.set(False)
    hidden_window._sync()
    assert row.cget("style") == "SideRow.TFrame", "neither"
    assert lit.get() is False and not pill.winfo_manager()

    hidden_window.do_shadows.set(True)
    hidden_window._sync()
    assert row.cget("style") == "SideRow.TFrame", "queued but not open"
    assert lit.get() is True and pill.cget("text"), "the switch, and what it will make"

    hidden_window._show_section(window.Window.SHADOWS)
    assert row.cget("style") == "SideRowOpen.TFrame", "open and queued"
    assert name.cget("style") == "SideOpen.TButton"
    assert switch.cget("style") == "SwitchOpen.TCheckbutton" and lit.get() is True

    hidden_window.do_shadows.set(False)
    hidden_window.do_shadow_hours.set(False)
    hidden_window._sync()
    assert row.cget("style") == "SideRowOpen.TFrame", "open but not queued"
    assert lit.get() is False


def test_only_the_pages_that_draw_something_can_be_queued(hidden_window: Any) -> None:
    """The taxonomy, and the reason the sidebar is grouped rather than flat:
    two pages set the job up, five draw something, and one is a tool. A
    switch belongs only to the five; one on General would be a promise
    nothing keeps."""
    groups = dict(window.Window.GROUPS)
    setting_up = groups[window.Window.SET_UP]
    drawn = groups[window.Window.DRAWS]
    tools = groups[window.Window.TOOLS]

    assert set(setting_up) | set(drawn) | set(tools) == set(hidden_window.titles)
    assert len(setting_up) + len(drawn) + len(tools) == len(hidden_window.titles)

    for _name, tick, _where in hidden_window._studies():
        tick.set(True)
    hidden_window._sync()

    for title in (*setting_up, *tools):
        assert hidden_window.side_rows[title][2] is None, f"{title} cannot be queued"
    for title in drawn:
        assert hidden_window.side_rows[title][3].get() is True, f"{title} is queued"


def test_a_pages_switch_turns_its_lead_study_on_and_every_study_off(
    hidden_window: Any,
) -> None:
    """The switch on a page with several studies turns its main one on --
    the apartments, on Solar analysis -- and, pressed again, every study on
    the page off."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window._sync()
    hidden_window._flip_section(window.Window.DIAGRAMS)
    assert hidden_window.do_plans.get() is True
    assert hidden_window.do_facade.get() is False and hidden_window.do_communal.get() is False
    hidden_window.do_communal.set(True)
    hidden_window._flip_section(window.Window.DIAGRAMS)
    assert not (hidden_window.do_plans.get() or hidden_window.do_communal.get())


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
        # The site page's lead: the sidebar's switch and the palette button
        # both turn on the Context Analysis (D157).
        ("site", "site_context", window.Window.SITE),
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
    """Not a study: the add-on's eighth button starts the window on the
    reference image's page, so the next click is Open picture."""
    assert hidden_window.ask_for("reference") is True
    assert hidden_window._open_section() == window.Window.REFERENCE


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
    figure the panel down the side draws, said where the decision is made.
    All but the Controls: one table and nothing to set, so it is a button in
    the site page's Address panel rather than a box of its own (D157)."""
    assert set(hidden_window.study_boxes) == {
        name for name, _t, _w in hidden_window._studies() if name != window.SITE_CONTROLS_JOB
    }
    assert "Summary of Controls layout" in hidden_window.site_buttons

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
    every_hour_box, _ = hidden_window.study_boxes[window.SHADOW_HOURS_JOB]
    plans_box, _ = hidden_window.study_boxes[window.PLANS_JOB]
    assert inside(hidden_window.shadow_plan_combination, shadow_box)
    assert inside(hidden_window.terrain_layers, every_hour_box)
    # The legend rows and the hours are both drawings', in a panel of their
    # own above the two switches (D160).
    for shared in (hidden_window.shadow_hours, hidden_window.shadow_rows[0][2]):
        assert not inside(shared, shadow_box) and not inside(shared, every_hour_box)
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
    for sheet_tick in (
        hidden_window.do_site_context,
        hidden_window.do_site_site,
        hidden_window.do_site_summary,
    ):
        sheet_tick.set(True)

    sheets = hidden_window.planned()

    assert [sheet.kind for sheet in sheets] == [
        "Context Analysis",
        "Site Analysis",
        "Summary of Controls",
    ]
    assert all(sheet.time == "" and sheet.day == "" for sheet in sheets)
    assert all(sheet.elevation is None for sheet in sheets)


class Resized:
    """What a <Configure> event says: which widget, and how wide."""

    def __init__(self, widget: Any, width: int) -> None:
        self.widget, self.width = widget, width


def roomy(made: Any) -> None:
    """The window wide enough for the page and the sheets panel side by side,
    whatever the screen of the machine the tests run on."""
    made.root.geometry(f"{made.fold_below + 40}x800")
    made.root.update_idletasks()
    made._fit(Resized(made.root, made.fold_below + 40))


def test_the_sheets_panel_folds_when_the_window_cannot_hold_both(hidden_window: Any) -> None:
    """Only on *crossing* the line. In between, the chevron is the user's:
    somebody who opened the panel in a narrow window meant to, and having it
    snap shut on the next pixel of a resize would be the window arguing."""
    roomy(hidden_window)
    root, dock = hidden_window.root, hidden_window.dock
    # With a sheet to show; an empty panel waits at its edge (the test below).
    hidden_window.do_shadows.set(True)
    hidden_window._sync()
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


def test_an_empty_sheets_panel_waits_at_its_edge(hidden_window: Any) -> None:
    """Nothing ticked is nothing to draw, and a third of the window saying so
    on every page was a third of the window. The first tick brings it out,
    the last one puts it away, and a panel opened by hand stays open."""
    roomy(hidden_window)
    dock = hidden_window.dock
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window._sync()
    assert dock.folded, "nothing ticked, so nothing to show"

    hidden_window.do_shadows.set(True)
    hidden_window._sync()
    assert not dock.folded, "the first tick brings the sheets out"

    hidden_window.do_shadows.set(False)
    hidden_window._sync()
    assert dock.folded, "and the last one puts them away"

    dock.fold(False)  # the chevron, pressed by hand
    hidden_window._sync()
    assert not dock.folded, "opened on purpose, so it stays open"


def test_run_says_what_it_will_run(hidden_window: Any) -> None:
    """A Run button that looked ready with nothing switched on answered a
    press with a line at the foot of the window. It now counts the sheets
    the panel draws, and is off when there are none to make."""
    go = hidden_window.go
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window._sync()
    assert str(go.cget("state")) == "disabled"
    assert go.cget("text") == "Switch on a study"
    assert hidden_window.queue_line.cget("text") == ""

    hidden_window.do_shadows.set(True)
    hidden_window._sync()
    made = sum(1 for sheet in hidden_window.planned() if sheet.paper)
    assert made > 1
    assert str(go.cget("state")) == "normal"
    assert go.cget("text") == f"Run {made} sheets"
    assert hidden_window.queue_line.cget("text") == f"Queued: Shadow diagram ({made})"


def test_the_progress_bar_is_there_only_while_a_run_is(hidden_window: Any) -> None:
    """An empty trough between runs was a strip of nothing under every page."""
    assert hidden_window.progress_row.winfo_manager() == ""


def test_every_choice_tile_names_itself(hidden_window: Any) -> None:
    """A row of drawings was learnable only by hovering each one. Every tile
    now carries a word on its face as well as its picture."""
    rows = [hidden_window.sheets]
    for row in rows:
        for button in row._buttons.values():
            assert str(button.cget("text")).strip(), "a tile with a picture and no word"
    for label, words in window.Window.TILE_WORDS.items():
        offered = {value for value, _icon, _detail in window.Window.TILE_CHOICES[label]}
        assert set(words) == offered, f"{label}: a tile without its word, or a word without a tile"


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
        for clause in licence.summary():
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


# -- the shadow diagram as 3D Documents (roadmap R1, D144) ------------------


def test_the_shadow_diagram_draws_its_days_and_hours_as_documents(
    hidden_window: Any,
) -> None:
    """The page's own days and hours go with it, what was filled in is sent,
    and a blank is left to the command."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)
    for name, lit in hidden_window.shadow_day_ticks.items():
        lit.set(name in ("winter", "summer"))
    hidden_window.shadow_plan_label.insert(0, "Proposed")
    hidden_window.shadow_plan_pen.insert(0, "3")
    # The project's own list, and none of it picked by a name (D156): the
    # person says which combination shows the ground under the buildings.
    assert hidden_window.shadow_plan_combination.get() == ""
    assert tuple(hidden_window.shadow_plan_combination.cget("values")) == (
        "01 | Plans - DA",
        "12 | IFC ARCH. EXPORT",
    )
    hidden_window.shadow_plan_combination.set("01 | Plans - DA")

    (job,) = hidden_window.jobs()

    assert job.label == window.SHADOW_JOB
    assert job.args[:3] == ["shadow-plans", "--timezone", "Australia/Sydney"]
    assert flag(job.args, "--shadow-date") == ["06-21,12-21"]
    assert flag(job.args, "--shadow-hour") == [hidden_window.shadow_hours.get().strip()]
    assert flag(job.args, "--layer-combination") == ["01 | Plans - DA"]
    assert flag(job.args, "--label") == ["Proposed"]
    assert flag(job.args, "--shadow-pen") == ["3"]
    assert "--pen-set" not in job.args, "a blank keeps each view's own"

    sheets = hidden_window.planned()
    assert {sheet.study for sheet in sheets} == {"Shadow diagram"}
    assert {sheet.day for sheet in sheets} == {"21 Jun", "21 Dec"}
    assert {sheet.scale for sheet in sheets} == {"1:1000"}, "a plain set is at 1:1000"

    saved = hidden_window.settings()
    assert saved["study_shadows"] is True
    assert saved["shadow_plan_label"] == "Proposed"


def test_run_asks_for_the_shadow_diagrams_combination_rather_than_guessing_one(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There is no office combination to fall back on (D156), and the
    documents are pinned to the one given. Blank, Run says so and starts
    nothing -- in the window, where somebody can pick one, not several steps
    into the command. Picked, the same press goes ahead."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)
    hidden_window.master.set("A4")  # so Run has no master to ask for
    started: list[str] = []
    monkeypatch.setattr(hidden_window, "_next", lambda: started.append("run"))
    monkeypatch.setattr(hidden_window, "_start_log", lambda _studies: None)

    hidden_window._start()

    assert started == [], "nothing was run"
    assert "The shadow documents need a layer combination" in hidden_window.lines[-1]

    hidden_window.shadow_plan_combination.set("01 | Plans - DA")
    hidden_window._start()
    assert started == ["run"]


def test_the_shadow_diagram_stacks_its_legend_rows(
    hidden_window: Any,
) -> None:
    """The rows filled on the Shadow diagram page go to the documents as
    sources and scenarios, which turns on the stacked mode (D142), and the
    set name and shadow pen, which are for a plain set, are not sent with
    them. A stack is fitted to the whole site, not set at 1:1000 (D143)."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadows.set(True)
    hidden_window.shadow_plan_label.insert(0, "Proposed")
    hidden_window.shadow_plan_pen.insert(0, "3")
    rows = {short: (role, box) for short, role, box in hidden_window.shadow_rows}
    baseline = next(short for short, (role, _) in rows.items() if role == "baseline")
    scenario = next(short for short, (role, _) in rows.items() if role == "scenario")
    rows[baseline][1].insert(0, "03 | Site Context.Buildings")
    rows[scenario][1].insert(0, "20 | Massing.Envelope, 20 | Massing.Podium")

    (job,) = hidden_window.jobs()

    assert flag(job.args, "--shadow-source") == [f"{baseline}=03 | Site Context.Buildings"]
    assert flag(job.args, "--shadow-scenario") == [
        f"{scenario}=20 | Massing.Envelope,20 | Massing.Podium"
    ]
    assert "--label" not in job.args and "--shadow-pen" not in job.args
    assert {sheet.scale for sheet in hidden_window.planned()} == {"to fit"}


def test_the_every_hour_drawing_is_one_sheet_a_day_from_the_same_legend(
    hidden_window: Any,
) -> None:
    """The design's every hour on one drawing (D144), read out of 3D
    Documents of the design alone: the legend's rows say what the design is,
    and a day is one sheet fitted to its shadows, not a sheet per hour."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadow_hours.set(True)
    for name, lit in hidden_window.shadow_day_ticks.items():
        lit.set(name in ("winter", "summer"))
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    rows["EXISTING"].insert(0, "03 | Site Context.Buildings")
    rows["PROPOSED"].insert(0, "20 | Massing.Envelope")
    hidden_window.terrain_layers.insert(0, "03 | Site Context.Terrain")

    (job,) = hidden_window.jobs()

    assert job.label == window.SHADOW_HOURS_JOB
    assert job.args[0] == "shadow-plans"
    assert "--every-hour-only" in job.args
    assert flag(job.args, "--shadow-source") == ["EXISTING=03 | Site Context.Buildings"]
    assert flag(job.args, "--shadow-scenario") == ["PROPOSED=20 | Massing.Envelope"]
    assert flag(job.args, "--shadow-date") == ["06-21,12-21"]

    sheets = hidden_window.planned()
    assert [(sheet.study, sheet.day, sheet.scale) for sheet in sheets] == [
        ("Every hour", "21 Jun", "to fit"),
        ("Every hour", "21 Dec", "to fit"),
    ]


def test_run_asks_for_the_design_before_the_every_hour_drawing(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no row being compared there is no design to outline, and the
    command would draw a fill per hour instead -- the diagram the documents
    draw. So Run says so and starts nothing; a row being compared, Proposed
    or another, is enough."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    hidden_window.do_shadow_hours.set(True)
    hidden_window.master.set("A4")  # so Run has no master to ask for
    started: list[str] = []
    monkeypatch.setattr(hidden_window, "_next", lambda: started.append("run"))
    monkeypatch.setattr(hidden_window, "_start_log", lambda _studies: None)
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    rows["EXISTING"].insert(0, "03 | Site Context.Buildings")

    hidden_window._start()

    assert started == [], "nothing was run"
    assert "Every hour on one drawing needs the design" in hidden_window.lines[-1]
    assert hidden_window._designed_row() == ""

    rows["PROPOSED 2"].insert(0, "20 | Massing.Option")
    assert hidden_window._designed_row() == "PROPOSED 2"
    rows["PROPOSED"].insert(0, "20 | Massing.Envelope")
    assert hidden_window._designed_row() == "PROPOSED"
    # Its documents are pinned to a layer combination, asked for like the diagram's.
    hidden_window._start()
    assert started == []
    assert "need a layer combination" in hidden_window.lines[-1]
    hidden_window.shadow_plan_combination.set("Shadow Diagrams")
    hidden_window._start()
    assert started == ["run"]


def test_the_every_hour_panel_says_which_massing_it_draws(hidden_window: Any) -> None:
    """The massing is chosen once, in Layers and hours, with every other row;
    the every-hour panel names the row it will draw and its layers, so nobody
    looks in it for a picker it does not have (D160)."""
    said = hidden_window.shadow_hours_design
    hidden_window._sync()
    assert "choose the Proposed row" in said.cget("text")

    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    rows["EXISTING"].insert(0, "03 | Site Context.Buildings")
    rows["PROPOSED 2"].insert(0, "20 | Massing.Option")
    hidden_window._sync()
    assert said.cget("text") == "Proposed 2: 20 | Massing.Option"

    rows["PROPOSED"].insert(0, "20 | Massing.Envelope, 20 | Massing.Podium")
    hidden_window._sync()
    assert said.cget("text") == "Proposed: 20 | Massing.Envelope, 20 | Massing.Podium"


def test_a_preset_from_when_the_fills_were_the_diagram_opens_as_it_meant(
    hidden_window: Any,
) -> None:
    """Its shadow plans were the documents under their older name, and its
    every-hour tick ran beside the fills' diagram: both are read as the
    switches they are now (D160). A preset of this version is left alone."""
    hidden_window.apply({"study_shadows": False, "study_shadow_plans": True})
    assert hidden_window.do_shadows.get() is True
    assert hidden_window.do_shadow_hours.get() is False

    hidden_window.apply({"study_shadows": True, "shadow_all_hours": True})
    assert hidden_window.do_shadows.get() is True
    assert hidden_window.do_shadow_hours.get() is True

    hidden_window.apply(
        {
            "study_shadows": False,
            "study_shadow_hours": False,
            "study_shadow_plans": True,
            "shadow_all_hours": True,
        }
    )
    assert hidden_window.do_shadows.get() is False
    assert hidden_window.do_shadow_hours.get() is False


def test_the_shadow_pages_switch_turns_on_the_documents(hidden_window: Any) -> None:
    """The sidebar's switch, and the palette's Shadow button, turn on what
    the page is for: the documents, not the fills (D144)."""
    assert window.Window.LEADS[window.Window.SHADOWS] == window.SHADOW_JOB
    for _name, tick, _where in hidden_window._studies():
        tick.set(False)
    assert hidden_window.ask_for("shadow") is True
    assert hidden_window.do_shadows.get() is True
    assert hidden_window.do_shadow_hours.get() is False


# -- the run bar, the project bar and the sheets strip, after the design review


def test_with_no_archicad_open_the_window_says_what_to_do_not_that_it_failed(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Archicad is where a session starts. The picker names the state and
    the line under it gives the next step, without the red mark kept for a
    project that answered and could not be read."""
    monkeypatch.setattr(probe, "running", lambda: [])
    hidden_window.refresh()

    assert hidden_window.instance.get() == "No Archicad open"
    assert hidden_window.status.cget("text") == "Open a project in Archicad, then press Refresh."
    shown = hidden_window.root.tk.splitlist(hidden_window.status.cget("image"))
    assert list(shown) == [str(icons.named("waiting", 16))]


def test_an_archicad_found_after_none_is_chosen(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The placeholder is not one of the picker's values, so the first
    Archicad to answer replaces it -- and Tk 9's empty answer to ``current``
    for text outside the list must not stop that."""
    found = [Instance(port=19723, project="SAMPLE")]
    monkeypatch.setattr(probe, "running", lambda: [])
    hidden_window.refresh()
    monkeypatch.setattr(probe, "running", lambda: found)
    hidden_window.refresh()

    assert hidden_window.instance.get().startswith("SAMPLE")


def test_the_programs_actions_share_one_menu(hidden_window: Any) -> None:
    """Connect Claude is set up once and then forgotten, so it is in the menu
    with the settings rather than a button in the tool bar."""
    menu = hidden_window.settings_menu
    labels = [
        menu.entrycget(index, "label")
        for index in range(menu.index("end") + 1)
        if menu.type(index) == "command"
    ]
    expected = [
        "Connect Claude…",
        "Save as default",
        "Save preset…",
        "Load preset…",
        "Forget saved settings",
        f"About {PRODUCT}",
        "loriini.app ↗",
    ]
    assert labels == expected


def test_run_is_the_one_filled_button(hidden_window: Any) -> None:
    style = tk.ttk.Style(hidden_window.root)
    assert hidden_window.go.cget("style") == "Run.TButton"
    assert style.lookup("Run.TButton", "foreground") == theme.INK


@pytest.mark.skipif(not theme.MACOS, reason="the program menu is a Mac's")
def test_on_a_mac_about_is_in_the_programs_own_menu(hidden_window: Any) -> None:
    bar = hidden_window.menu_bar
    own = hidden_window.root.nametowidget(bar.entrycget(0, "menu"))
    assert own.entrycget(0, "label") == "About Loriini"


def test_the_folded_sheets_strip_says_what_it_holds_in_words() -> None:
    assert window.Dock._spell(0) == "No sheets yet"
    assert window.Dock._spell(1) == "1 sheet"
    assert window.Dock._spell(21) == "21 sheets"


@pytest.mark.skipif(not theme.MACOS, reason="the cap is a Mac's")
def test_on_a_mac_the_window_opens_on_at_most_three_quarters_of_the_screen(
    hidden_window: Any,
) -> None:
    root = hidden_window.root
    wide, tall = (int(n) for n in hidden_window._on_the_screen(5000, 5000).split("x"))
    assert wide <= max(880, round(root.winfo_screenwidth() * 0.75))
    assert tall <= max(620, round(root.winfo_screenheight() * 0.75))


def test_opening_a_tab_moves_no_other_tab(hidden_window: Any) -> None:
    """The open tab's name is bold. Each tab keeps the room for that, so the
    strip stands still as tabs are opened."""
    root = hidden_window.root

    def where() -> list[int]:
        root.update_idletasks()
        return [tab.winfo_x() for tab in hidden_window.tabs.values()]

    hidden_window._show_section(hidden_window.GENERAL)
    first = where()
    hidden_window._show_section(hidden_window.SHADOWS)
    assert where() == first


def test_a_narrow_page_rearranges_rather_than_cutting_its_rows_off(hidden_window: Any) -> None:
    """With the sheets panel open on a laptop the page is about 560 px wide:
    less than a row of choices beside a 200 px label column. The label column
    narrows and wraps, every row of buttons wraps inside its panel, and the
    fields still start at one place down the page."""
    made = hidden_window
    # Shown for this one: a page is rearranged for the width it has on the
    # screen, and a window never shown has none. Windows keeps a window on
    # its screen, and GitHub's Windows runners have a 1024 px one: there the
    # window comes out narrower than asked, the sheets panel rightly folds,
    # and the page is wide again -- which is the window working, not failing.
    wanted = made.fold_below + 10
    if made.root.winfo_screenwidth() < wanted:
        pytest.skip(f"needs a screen at least {wanted} px wide")
    made.root.deiconify()
    made.root.geometry(f"{wanted}x800")
    made.dock.fold(False)
    made.root.update()
    made._show_section(window.Window.GENERAL)
    made._rearrange()
    page = made.pane_of[made.showing].canvas.winfo_width()
    assert made._narrow_page, (
        f"page {page} px in a window {made.root.winfo_width()} px wide, asked for "
        f"{made.fold_below + 10} on a screen {made.root.winfo_screenwidth()} px wide"
    )
    for row in made._flowing():
        holder = made._box_of(row)
        if holder is None or not row.winfo_ismapped():
            continue
        right = row.winfo_rootx() + row.winfo_reqwidth()
        assert right <= holder.winfo_rootx() + holder.winfo_width(), f"{row} runs off its panel"
    assert len({line for line, _column in made.sheets._flow_lines}) > 1, "Sheets wraps"
    starts = {
        child.winfo_x()
        for box in made.boxes
        if box.winfo_ismapped()
        for child in box.grid_slaves(column=1)
        if int(child.grid_info().get("columnspan", 1)) == 1 and child.winfo_ismapped()
    }
    assert len(starts) == 1, starts

    made.root.geometry("1800x900")
    made.root.update()
    made._rearrange()
    assert not made._narrow_page
    assert len({line for line, _column in made.sheets._flow_lines}) == 1, "one line again"


def test_labels_keep_one_line_while_their_fields_have_room(hidden_window: Any) -> None:
    """The labels wrap to make room for their fields, not because the page
    is under some fixed width: on a laptop with the sheets panel open the
    page is about 640 px, and the fields beside full-width labels still had
    a third of it spare while every label wrapped onto two lines."""
    made = hidden_window
    roomy = made._label_wide + made.FIELD_LEAST + 400
    cramped = made._label_wide + made.FIELD_LEAST + 50
    assert made._room_with_full_labels(roomy) >= made.FIELD_LEAST
    assert made._room_with_full_labels(cramped) < made.FIELD_LEAST
    assert made._room_with_full_labels(640) >= made.FIELD_LEAST, "the laptop page keeps its labels"


def test_the_sheets_panel_is_not_redrawn_when_nothing_on_it_changed(
    hidden_window: Any,
) -> None:
    """Every keystroke syncs the window; redrawing a dozen miniatures for a
    keystroke that changed none of them was the lag felt typing."""
    made = hidden_window
    made.do_shadows.set(True)
    made._sync()
    drawn = list(made.dock._drawn)
    assert drawn
    made._sync()
    assert all(a is b for a, b in zip(made.dock._drawn, drawn, strict=True)), "drawn again"
    made.do_shadows.set(False)
    made._sync()
    assert not any(a is b for a, b in zip(made.dock._drawn, drawn, strict=False))


def test_switching_one_study_on_keeps_the_miniatures_of_the_others(hidden_window: Any) -> None:
    """Every miniature was destroyed and drawn again whenever any of them
    changed, with the panel blank in between: the flash down the right of the
    window on every click. What is still wanted is kept, in its place."""
    made = hidden_window
    made.do_shadows.set(True)
    made._sync()
    shadows = [one for one in made.dock._drawn if isinstance(one, tk.Canvas)]
    assert shadows
    made.do_sun_eyes.set(True)
    made._sync()
    now = [one for one in made.dock._drawn if isinstance(one, tk.Canvas)]
    assert len(now) > len(shadows), "the sun views' sheets joined them"
    assert all(any(one is kept for one in now) for kept in shadows), "drawn again"
    assert all(one.winfo_exists() for one in made.dock._drawn)
    # In the order the sheets are planned in, whatever was kept or made.
    made.root.update_idletasks()
    packed = made.dock.pane.content.pack_slaves()
    assert packed == made.dock._drawn
    made.do_shadows.set(False)
    made._sync()
    assert not any(one.winfo_exists() for one in shadows), "and gone when not wanted"
    assert made.dock.pane.content.pack_slaves() == made.dock._drawn


def test_a_page_is_raised_over_the_others_and_tab_keeps_to_the_one_on_top(
    hidden_window: Any,
) -> None:
    """The pages lie one over another and the open one is raised, since taking
    one off the screen and putting the next on was a blink on every click. A
    page underneath is still on the screen as far as Tk's Tab knows, so the
    window says which controls can be seen."""
    made = hidden_window
    made._show_section(made.SHADOWS)
    made._show_section(made.YIELD)
    made.root.update_idletasks()
    shadows, yields = made.pane_of[made.SHADOWS], made.pane_of[made.YIELD]
    assert shadows.winfo_manager() == "place" and yields.winfo_manager() == "place"
    stacked = [
        str(one)
        for one in made.stack.tk.splitlist(made.stack.tk.call("winfo", "children", made.stack))
    ]
    assert made.showing == made.YIELD
    assert made._on_this_page(made.study_bars[window.YIELD_JOB])
    assert not made._on_this_page(made.study_bars[window.SHADOW_JOB])
    assert made._on_this_page(made.go), "the run bar is on no page"
    assert str(yields) in stacked
    # Every page is made ready under the open one, one at a time.
    for _ in made.panes:
        made._warm_pages()
    assert all(pane.winfo_manager() == "place" for pane in made.panes)
    assert made.showing == made.YIELD


def test_a_widget_is_told_only_what_it_does_not_already_have(hidden_window: Any) -> None:
    """Tk lays a widget out and paints it again when told the style it
    already wears, so a sync that changed nothing repainted the page."""
    made = hidden_window
    told: list[dict[str, object]] = []
    button = made.go
    real = button.configure

    def telling(**options: object) -> object:
        told.append(options)
        return real(**options)

    button.configure = telling
    try:
        window.put(button, text=str(button.cget("text")), state=str(button.cget("state")))
        assert told == []
        window.put(button, text="Run 99 sheets", state=str(button.cget("state")))
        assert told == [{"text": "Run 99 sheets"}]
    finally:
        del button.configure


def test_the_project_picker_is_as_wide_as_the_longest_project(
    hidden_window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An office names its project files for the job and the street, and 34
    characters cut most of them off before the port."""
    made = hidden_window
    assert int(made.instance.cget("width")) == made.PICKER_LEAST
    long_name = "2524_Maroubra_86-90 Maroubra Rd_Temp_Project_File"
    monkeypatch.setattr(probe, "running", lambda: [Instance(port=19723, project=long_name)])
    made.refresh()
    width = int(made.instance.cget("width"))
    assert width >= len(f"{long_name}  ·  port 19723")
    assert width <= made.PICKER_MOST
    monkeypatch.setattr(probe, "running", lambda: [Instance(port=19723, project="x" * 200)])
    made.refresh()
    assert int(made.instance.cget("width")) == made.PICKER_MOST


def test_a_long_queue_is_counted_rather_than_listed(hidden_window: Any) -> None:
    """Every study queued is a line that runs into the build's; the sidebar
    and the panel already say which, so the bar says how many."""
    for _name, tick, _where in hidden_window._studies():
        tick.set(True)
    hidden_window._sync()
    said = hidden_window.queue_line.cget("text")
    assert len(said) <= window.Window.QUEUE_LONGEST
    assert said.startswith(f"Queued: {len(hidden_window._studies())} studies")


def test_the_communal_schedule_goes_with_the_hourly_plans_and_only_when_chosen(
    hidden_window: Any,
) -> None:
    """The schedule lists the hourly plans' fills, so it rides on the hours:
    asked for without them it would have nothing to list."""
    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    hidden_window.do_plans.set(True)
    hidden_window.apartments.set("06 | Zone.Units")

    hidden_window.cos_schedule.set("")
    _, communal = hidden_window.jobs()
    assert "--zone-schedule" not in communal.args, "blank draws the table as before"

    hidden_window.cos_schedule.set("Areas COS solar")
    _, communal = hidden_window.jobs()
    assert flag(communal.args, "--zone-schedule") == ["Areas COS solar"]

    hidden_window.plan_kinds.set("Bands by hour")
    _, communal = hidden_window.jobs()
    assert "--zone-schedule" not in communal.args


def test_the_drawn_table_is_offered_first_and_no_schedule_is_picked_by_its_name(
    hidden_window: Any,
) -> None:
    """A schedule with 'COS solar' in its name used to be picked wherever a
    project had one -- one office's name for its scheme (D156). Now the drawn
    table is what opens, whatever schedules the project has, rather than one
    picked by its name or whichever sorts first; and a choice made by hand,
    a schedule or "None", survives a Refresh."""
    hidden_window.options = replace(
        hidden_window.options, schedules=("Areas COS solar", "Areas COS solar 2hr")
    )
    hidden_window.cos_schedule.set("")
    hidden_window._offer()
    assert tuple(hidden_window.cos_schedule.cget("values")) == (
        window.NO_SCHEDULE,
        "Areas COS solar",
        "Areas COS solar 2hr",
    )
    assert hidden_window.cos_schedule.get() == window.NO_SCHEDULE

    hidden_window.cos_schedule.set("Areas COS solar")
    hidden_window._offer()
    assert hidden_window.cos_schedule.get() == "Areas COS solar", "a choice survives a Refresh"

    hidden_window.cos_schedule.set(window.NO_SCHEDULE)
    hidden_window._offer()
    assert hidden_window.cos_schedule.get() == window.NO_SCHEDULE

    hidden_window.communal.set("06 | Zone.Balcony")
    hidden_window.do_communal.set(True)
    communal = hidden_window.jobs()[-1]
    assert "--zone-hourly" in communal.args and "--zone-schedule" not in communal.args


def test_the_yield_page_shows_only_the_rows_its_slabs_answer_needs(hidden_window: Any) -> None:
    """One question, four answers, and the rows each one reads (D140)."""
    made = hidden_window
    only_yield(made)

    def showing(widget: Any) -> bool:
        return bool(widget.winfo_manager())

    made.yield_slabs.set("Every slab showing")
    made._sync()
    assert showing(made.yield_commercial_levels) and not showing(made.yield_massing)
    assert not showing(made.yield_residential) and not showing(made.yield_option_layers)
    made.yield_slabs.set("A layer per use")
    made._sync()
    assert showing(made.yield_residential) and showing(made.yield_commercial)
    assert not showing(made.yield_commercial_levels), "a layer per use tells the use itself"
    made.yield_slabs.set("A layer per option")
    made._sync()
    assert showing(made.yield_option_layers) and not showing(made.yield_option)
    assert made._label_wide < 400, "no hint line dropped into the label column"


def test_the_yield_page_has_two_uses_and_three_panels(hidden_window: Any) -> None:
    """D159. Shops and offices are one use, commercial, at the commercial
    rates: no retail field is left on the page. The site and the controls
    have a panel of their own between the study's and the efficiencies."""
    made = hidden_window
    assert not [name for name in vars(made) if "retail" in name], "no retail field"
    assert made.yield_site_area.master is made.yield_fsr_residential.master
    assert made.yield_site_area.master is made.yield_fsr_commercial.master
    assert made.yield_site_area.master is not made.yield_option.master, "a panel of its own"
    assert made.yield_gfa_commercial.master is not made.yield_site_area.master


def test_an_older_presets_retail_joins_the_commercial_rows(hidden_window: Any) -> None:
    """A preset saved before D159 kept retail apart. Its retail layers and
    levels are commercial now, added to the commercial ones, not dropped."""
    made = hidden_window
    made.apply(
        {
            "yield_commercial_layers": "01 | Offices",
            "yield_retail_layers": "01 | Shops, 01 | Offices",
            "yield_commercial_levels": "Level 01",
            "yield_retail_levels": "Ground",
        }
    )
    assert made._listed(made.yield_commercial) == ["01 | Offices", "01 | Shops"]
    assert made._listed(made.yield_commercial_levels) == ["Level 01", "Ground"]


def test_renovation_is_read_off_each_slab_or_the_floor_plans_filter(hidden_window: Any) -> None:
    made = hidden_window
    only_yield(made)
    (job,) = made.jobs()
    assert "--renovation-status" not in job.args and "--renovation-filter" not in job.args
    made.yield_renovation_status.set("New only")
    (job,) = made.jobs()
    assert flag(job.args, "--renovation-status") == ["new"]
    made.yield_renovation_status.set("Existing and new")
    (job,) = made.jobs()
    assert flag(job.args, "--renovation-status") == ["existing-and-new"]


def test_a_preset_saved_before_the_slabs_row_opens_as_what_it_meant(hidden_window: Any) -> None:
    made = hidden_window
    made.apply({"yield_massing_layers": "01 | Massing.3D", "yield_renovation": True})
    assert made.yield_slabs.get() == "Slabs on chosen layers"
    assert made.yield_renovation_status.get() == "As the floor plan's filter"
    made.apply({"yield_residential_layers": "05 | Mass.Residential"})
    assert made.yield_slabs.get() == "A layer per use"
    made.apply({"yield_slabs": "Every slab showing", "yield_massing_layers": "x"})
    assert made.yield_slabs.get() == "Every slab showing", "a saved answer is kept as it is"


def test_the_shadow_diagram_is_drawn_as_worksheet_fills_unless_live_documents_is_picked(
    hidden_window: Any,
) -> None:
    hidden_window.do_facade.set(False)
    hidden_window.do_shadows.set(True)
    # No legend rows: the plain set, which has one route.
    if not hidden_window._legend_args():
        (job,) = hidden_window.jobs()
        assert "--flat" not in job.args
    hidden_window._legend_args = lambda: ["--shadow-scenario", "PROPOSED=Massing"]
    assert hidden_window.shadow_plan_route.get() == "Worksheet fills"
    (job,) = hidden_window.jobs()
    assert "--flat" in job.args
    hidden_window.shadow_plan_route.set("Live 3D Documents")
    (job,) = hidden_window.jobs()
    assert "--flat" not in job.args


def test_every_hour_is_read_out_of_the_documents_when_the_legend_names_a_design(
    hidden_window: Any,
) -> None:
    hidden_window.do_facade.set(False)
    hidden_window._legend_args = lambda: ["--shadow-scenario", "PROPOSED=Massing"]
    hidden_window.do_shadows.set(False)
    hidden_window.do_shadow_hours.set(True)
    (job,) = hidden_window.jobs()
    assert job.label == window.SHADOW_HOURS_JOB
    assert job.args[0] == "shadow-plans"
    assert "--every-hour-only" in job.args
    # With the diagram ticked it rides on the diagram's run.
    hidden_window.do_shadows.set(True)
    (job,) = hidden_window.jobs()
    assert job.label == window.SHADOW_JOB
    assert "--every-hour" in job.args and "--every-hour-only" not in job.args


def test_a_compared_row_is_named_filtered_and_hatched_from_the_window(hidden_window: Any) -> None:
    rows = {short: box for short, _role, box in hidden_window.shadow_rows}
    hidden_window.do_facade.set(False)
    hidden_window.do_shadows.set(True)
    hidden_window.shadow_plan_combination.set("Shadow Diagrams")
    rows["PROPOSED"].insert(0, "01 | Wall.External")
    rows["PROPOSED 2"].insert(0, "01 | Floor.Structural")
    hidden_window.shadow_row_names["PROPOSED 2"].insert(0, "LEP + 30%")
    hidden_window.shadow_row_filters["PROPOSED 2"].set("LEP + 30% Bonus")
    hidden_window.shadow_row_hatches["PROPOSED 2"].set("zz Brick Common")
    # A row with no layers sends nothing, whatever is typed beside it.
    hidden_window.shadow_row_hatches["PROPOSED 3"].set("Dashed")

    (job,) = hidden_window.jobs()

    assert flag(job.args, "--shadow-scenario") == [
        "LEP + 30%=01 | Floor.Structural",
        "PROPOSED=01 | Wall.External",
    ]
    assert flag(job.args, "--scenario-filter") == ["LEP + 30%=LEP + 30% Bonus"]
    assert flag(job.args, "--scenario-fill") == ["LEP + 30%=zz Brick Common"]
