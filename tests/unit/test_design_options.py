"""Scenarios as each Archicad keeps them: renovation filters in 26, Design
Options from 27 (``archicad.design_options``), and the Yield counting one."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sun_study.archicad import design_options, naming
from sun_study.archicad.connection import ArchicadError
from tests.unit.test_archicad_adapter import connect
from tests.unit.test_area_sheet import scripted_project

LEP = "11111111-1111-1111-1111-111111111111"
TWELVE = "22222222-2222-2222-2222-222222222222"
OPTION_LEP = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
OPTION_TWELVE = "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB"


@pytest.fixture(autouse=True)
def naming_left_as_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """The yield command sets the run's prefix and day for the whole
    process; put them back, so a later test meets them as it would have."""
    for held in ("_prefix", "_context_prefix", "_day"):
        monkeypatch.setattr(naming, held, getattr(naming, held))


def product(version: int) -> dict[str, Any]:
    return {"API.GetProductInfo": {"version": version, "buildNumber": 3000, "languageCode": "AUS"}}


def listed(*, active: bool) -> dict[str, Any]:
    """Two combinations, each with one option on -- as 29 lists them, or as
    27 and 28 do, which do not say which options a combination has on."""

    def one(name: str, guid: str, option: str) -> dict[str, Any]:
        entry: dict[str, Any] = {"designOptionCombinationId": {"guid": guid}, "name": name}
        if active:
            entry["activeDesignOptions"] = [{"designOptionId": {"guid": option}}]
        return entry

    return {
        "GetDesignOptionCombinations": {
            "designOptionCombinations": [
                one("Main + LEP", LEP, OPTION_LEP),
                one("Main + 12 storeys", TWELVE, OPTION_TWELVE),
            ]
        }
    }


# -- which Archicad --------------------------------------------------------------


def test_the_version_is_archicads_own_and_read_once() -> None:
    connection, transport = connect(product(27))
    assert connection.archicad_version == 27
    assert connection.archicad_version == 27
    assert transport.commands().count("API.GetProductInfo") == 1
    assert design_options.uses_design_options(27)
    assert not design_options.uses_design_options(26)
    assert not design_options.uses_design_options(None), "unknown is taken as 26"


def test_an_archicad_that_will_not_say_its_version_is_none() -> None:
    class Refusing:
        def send(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"succeeded": False, "error": {"code": 1, "message": "no such command"}}

    from sun_study.archicad.connection import ArchicadConnection

    assert ArchicadConnection(Refusing()).archicad_version is None


# -- the combinations ----------------------------------------------------------------


def test_combinations_are_found_by_name_or_guid() -> None:
    connection, _ = connect(listed(active=False))
    found = design_options.combinations(connection)
    assert [one.name for one in found] == ["Main + LEP", "Main + 12 storeys"]
    assert found[0].active is None, "27 and 28 do not say which options are on"
    assert design_options.combination_named("main  +  lep", found).guid == LEP
    assert design_options.combination_named(TWELVE.lower(), found).name == "Main + 12 storeys"
    with pytest.raises(ArchicadError, match="It has: Main \\+ LEP, Main \\+ 12 storeys"):
        design_options.combination_named("Main + 30 storeys", found)


def test_rows_are_given_their_combination_on_27_and_refused_on_26() -> None:
    connection, _ = connect({**product(27), **listed(active=False)})
    assert design_options.combination_guids(connection, {"LEP + 30%": "Main + LEP"}) == {
        "LEP + 30%": LEP
    }
    older, _ = connect(product(26))
    with pytest.raises(ArchicadError, match="Archicad 26 with no Design Options"):
        design_options.combination_guids(older, {"LEP + 30%": "Main + LEP"})
    assert design_options.combination_guids(older, {}) == {}, "nothing asked, nothing refused"


def test_views_are_pinned_through_the_add_on() -> None:
    connection, transport = connect({"SetViewDesignOptions": {"success": True, "views": 2}})
    assert design_options.pin_views(connection, ["v1", "", "v2"], LEP) == 2
    assert transport.parameters_for("SetViewDesignOptions") == {
        "navigatorItemIds": [{"guid": "v1"}, {"guid": "v2"}],
        "combination": LEP,
    }
    connection, transport = connect({"SetViewDesignOptions": {"success": True, "views": 1}})
    design_options.pin_views(connection, ["v1"], None)
    assert "combination" not in transport.parameters_for("SetViewDesignOptions"), (
        "no combination is the Main Model alone"
    )


# -- the Yield -------------------------------------------------------------------------


def options_project() -> dict[str, Any]:
    return {
        "GetDesignOptions": {
            "designOptions": [
                {"designOptionId": {"guid": OPTION_LEP}, "name": "LEP"},
                {"designOptionId": {"guid": OPTION_TWELVE}, "name": "12 storeys"},
            ]
        },
        "GetElementsOfDesignOptions": {
            "elementsOfDesignOptions": [
                {
                    "designOptionId": {"guid": OPTION_TWELVE},
                    "elements": [{"elementId": {"guid": "b"}}],
                }
            ]
        },
    }


def test_a_combination_leaves_out_the_elements_of_the_options_it_has_off() -> None:
    connection, transport = connect({**product(29), **listed(active=True), **options_project()})
    (lep, _) = design_options.combinations(connection)
    assert design_options.left_out_by(connection, lep) == {"B"}
    assert transport.parameters_for("GetElementsOfDesignOptions") == {
        "designOptions": [{"designOptionId": {"guid": OPTION_TWELVE}}]
    }


def test_before_29_a_combination_cannot_say_what_it_holds() -> None:
    connection, _ = connect({**product(28), **listed(active=False)})
    (lep, _) = design_options.combinations(connection)
    with pytest.raises(ArchicadError, match=r"needs Archicad 29.*this is Archicad 28"):
        design_options.left_out_by(connection, lep)


def run_yield(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extra: dict[str, Any], *args: str):  # type: ignore[no-untyped-def]
    from typer.testing import CliRunner

    import sun_study.cli as cli

    connection, transport = scripted_project(lambda responses: connect({**responses, **extra}))
    monkeypatch.setattr(cli, "_connect", lambda *a, **k: connection)
    result = CliRunner().invoke(
        cli.app,
        [
            "yield",
            "--residential-layer",
            "05 | Mass.Residential",
            "--commercial-layer",
            "05 | Mass.Podium",
            "--xlsx",
            str(tmp_path / "yield.xlsx"),
            "--no-sheet",
            *args,
        ],
    )
    return result, transport


def test_the_yield_counts_what_a_renovation_filter_shows_and_puts_the_floor_plan_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    filters = {
        "GetRenovationFilters": {
            "success": True,
            "renovationFilters": [
                {"guid": LEP, "name": "OPTION 03"},
                {"guid": TWELVE, "name": "OPTION 10"},
            ],
            "actual": TWELVE,
        },
        "SetRenovationFilter": {"success": True, "name": "OPTION 03"},
    }
    result, transport = run_yield(
        monkeypatch, tmp_path, filters, "--renovation-filter-name", "option 03"
    )
    assert result.exit_code == 0, result.output
    assert transport.all_parameters_for("SetRenovationFilter") == [{"guid": LEP}, {"guid": TWELVE}]
    assert transport.parameters_for("GetElementsByType")["filters"] == ["IsVisibleByRenovation"]
    assert "only those the renovation filter 'OPTION 03' shows" in result.output


def test_the_yield_counts_what_a_design_option_combination_shows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    extra = {**product(29), **listed(active=True), **options_project()}
    result, transport = run_yield(monkeypatch, tmp_path, extra, "--design-option", "Main + LEP")
    assert result.exit_code == 0, result.output
    assert "only those the Design Option Combination 'Main + LEP' shows" in result.output
    assert "1 slab left out, in design options the combination has off" in result.output
    assert "05 | Mass.Residential: 1 slab" in result.output
    assert "SetRenovationFilter" not in transport.commands()


def test_the_yield_refuses_a_design_option_on_archicad_26(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, _ = run_yield(monkeypatch, tmp_path, product(26), "--design-option", "Main + LEP")
    assert result.exit_code == 2
    assert "came in Archicad 27" in result.output


def test_a_shadow_colour_is_drawn_in_the_pen_that_looks_most_like_it() -> None:
    import typer

    import sun_study.cli as cli

    pens = [
        {"index": 1, "color": {"red": 0.0, "green": 0.0, "blue": 0.0}},
        {"index": 45, "color": {"red": 0.8, "green": 0.1, "blue": 0.1}},
        {"index": 70, "color": {"red": 0.2, "green": 0.4, "blue": 0.8}},
    ]
    connection, _ = connect(
        {
            "GetAttributesByType": {
                "attributes": [{"attributeId": {"guid": "PT"}, "index": 1, "name": "Office"}]
            },
            "GetPenTables": {"penTables": [{"penTableAttribute": {"pens": pens}}]},
        }
    )
    assert cli.parse_colour("#3366cc") == (51, 102, 204)
    assert cli.parse_colour("51,102,204") == (51, 102, 204)
    with pytest.raises(typer.BadParameter):
        cli.parse_colour("blue")
    assert cli._pen_for_colour(connection, "#3366cc", None) == 70
    assert cli._pen_for_colour(connection, "#cc2222", "office") == 45
