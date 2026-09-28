"""Whose contours a sheet and a model take, read through fake services.

The City of Sydney answers inside its box; the state's register answers
everywhere; the local government areas say where the council's stop. Each
is a stand-in function here, so the rules are tested without a network: the
sheet takes the council's only where they cover it, the model takes both,
cut at the boundary, and a council that fails costs nothing but its lines.
"""

from __future__ import annotations

from typing import Any

import pytest

from sun_study.site import nsw, sources, terrain
from sun_study.site.geo import Extent, extent_for, lonlat_to_mercator, mercator_to_lonlat

# Surry Hills, inside the City of Sydney's box.
LON, LAT = 151.2135, -33.8850


def sheet() -> Extent:
    return extent_for(lonlat_to_mercator(LON, LAT), 690.0, 594.0, 300.0)


def corners(extent: Extent) -> tuple[float, float, float, float]:
    west, south = mercator_to_lonlat(extent.xmin, extent.ymin)
    east, north = mercator_to_lonlat(extent.xmax, extent.ymax)
    return west, south, east, north


def lines_across(extent: Extent, *, west_share: float = 0.0, levels: int = 6) -> dict[str, Any]:
    """Contours running north-south across the extent, from ``west_share`` of
    the way across to its east edge, as the council's layer answers them."""
    west, south, east, north = corners(extent)
    start = west + (east - west) * west_share
    features = []
    for k in range(levels):
        # The first on the west edge of the council's part, the last just
        # past the extent's east edge.
        x = start + (east + 0.0001 - start) * k / (levels - 1)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [[[x, south - 0.001], [x, north + 0.001]]],
                },
                "properties": {"Contour": 30.0 + k},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def area(extent: Extent, *, west_share: float, name: str = "SYDNEY") -> dict[str, Any]:
    """A local government area holding the extent from ``west_share`` of the
    way across to well past its east edge."""
    west, south, east, north = corners(extent)
    edge = west + (east - west) * west_share
    ring = [
        [edge, south - 1.0],
        [east + 1.0, south - 1.0],
        [east + 1.0, north + 1.0],
        [edge, north + 1.0],
        [edge, south - 1.0],
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"lganame": name},
            }
        ],
    }


def state(extent: Extent) -> list[nsw.Contour]:
    """The state's 2 m contours, running east-west across the whole extent."""
    west, south, east, north = corners(extent)
    return [
        nsw.Contour(20.0 + 2 * k, ((west - 0.001, y), (east + 0.001, y)), sources.SPATIAL)
        for k, y in enumerate(south + (north - south) * (i + 0.5) / 4 for i in range(4))
    ]


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stand-ins for the three registers, and a record of what was asked."""
    answers: dict[str, Any] = {"council": None, "area": None, "asked": []}

    def council(layer: str, extent: Extent, fields: str = "*", *args: Any, **kwargs: Any) -> Any:
        answers["asked"].append(("council", kwargs.get("extra")))
        if isinstance(answers["council"], Exception):
            raise answers["council"]
        return answers["council"](extent)

    def areas(extent: Extent) -> Any:
        answers["asked"].append(("area", None))
        if isinstance(answers["area"], Exception):
            raise answers["area"]
        return answers["area"](extent)

    monkeypatch.setattr(terrain, "query_by_extent", council)
    monkeypatch.setattr(nsw, "local_government_areas", areas)
    monkeypatch.setattr(nsw, "contours", state)
    return answers


def test_a_sheet_the_council_covers_takes_the_councils_contours(services: dict[str, Any]) -> None:
    services["council"] = lambda e: lines_across(e)
    services["area"] = lambda e: area(e, west_share=-1.0)
    said: list[str] = []
    lines = terrain.sheet_contours(sheet(), log=said.append)
    assert lines and {line.source for line in lines} == {sources.CITY_OF_SYDNEY}
    assert terrain.described(lines) == (1.0, "CITY OF SYDNEY 2020 SURVEY", ("cityofsydney",))
    assert said == ["  contours: City of Sydney 1 m contours, 2020 aerial survey (6 lines)"]
    assert ("council", None) in services["asked"], "a sheet asks for the lines as published"


def test_a_sheet_the_lines_reach_across_but_the_council_only_half_holds_takes_the_states(
    services: dict[str, Any],
) -> None:
    """King Street, Newtown: the council's lines on its side of the street
    reach every edge of the sheet between them, and the other side is another
    council's. The lines' box says 100%; the boundary says a third."""
    services["council"] = lambda e: lines_across(e)
    services["area"] = lambda e: area(e, west_share=0.64)
    said: list[str] = []
    lines = terrain.sheet_contours(sheet(), log=said.append)
    assert {line.source for line in lines} == {sources.SPATIAL}
    assert any("cover 36% of the sheet" in line for line in said), said


def test_a_sheet_the_councils_lines_stop_short_of_takes_the_states(
    services: dict[str, Any],
) -> None:
    services["council"] = lambda e: lines_across(e, west_share=0.5)
    services["area"] = lambda e: area(e, west_share=-1.0)
    lines = terrain.sheet_contours(sheet())
    assert {line.source for line in lines} == {sources.SPATIAL}


def test_a_council_that_fails_costs_the_sheet_its_lines_and_nothing_else(
    services: dict[str, Any],
) -> None:
    services["council"] = RuntimeError("503 from the council")
    said: list[str] = []
    lines = terrain.sheet_contours(sheet(), log=said.append)
    assert {line.source for line in lines} == {sources.SPATIAL}
    assert any("WARN City of Sydney" in line for line in said)


def test_a_site_outside_every_council_asks_only_the_state(services: dict[str, Any]) -> None:
    campsie = extent_for(lonlat_to_mercator(151.1030, -33.9120), 690.0, 594.0, 300.0)
    lines = terrain.sheet_contours(campsie)
    assert {line.source for line in lines} == {sources.SPATIAL}
    assert services["asked"] == []


def test_a_model_takes_the_councils_lines_inside_its_area_and_the_states_outside(
    services: dict[str, Any],
) -> None:
    services["council"] = lambda e: lines_across(e)
    services["area"] = lambda e: area(e, west_share=0.5)
    square = sheet()
    lines = terrain.model_contours(square)
    west, _, east, _ = corners(square)
    middle = (west + east) / 2.0
    council = [line for line in lines if line.source == sources.CITY_OF_SYDNEY]
    state_lines = [line for line in lines if line.source == sources.SPATIAL]
    assert council and state_lines
    assert all(lon >= middle - 1e-9 for line in council for lon, _ in line.coords)
    assert all(lon <= middle + 1e-9 for line in state_lines for lon, _ in line.coords)
    # Cut on the boundary, not at the last vertex short of it.
    assert any(abs(line.coords[-1][0] - middle) < 1e-9 for line in state_lines)
    described = terrain.described(lines)
    assert described is not None and described[0] == 1.0
    assert set(described[2]) == {sources.CITY_OF_SYDNEY, sources.SPATIAL}
    # The model asks the council to generalise its lines to a tenth of a metre.
    extra = next(asked for kind, asked in services["asked"] if kind == "council")
    assert extra is not None and float(extra["maxAllowableOffset"]) == pytest.approx(
        0.1 / 111_320, rel=1e-6
    )


def test_a_model_wholly_in_the_councils_area_asks_the_state_nothing(
    services: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    services["council"] = lambda e: lines_across(e)
    services["area"] = lambda e: area(e, west_share=-1.0)

    def refuse(extent: Extent) -> list[nsw.Contour]:
        raise AssertionError("asked the state for a square the council holds")

    monkeypatch.setattr(nsw, "contours", refuse)
    lines = terrain.model_contours(sheet())
    assert lines and {line.source for line in lines} == {sources.CITY_OF_SYDNEY}


def test_without_the_boundary_a_model_falls_back_to_the_sheets_rule(
    services: dict[str, Any],
) -> None:
    services["council"] = lambda e: lines_across(e)
    services["area"] = RuntimeError("the boundaries are down")
    lines = terrain.model_contours(sheet())
    assert {line.source for line in lines} == {sources.CITY_OF_SYDNEY}

    services["council"] = lambda e: lines_across(e, west_share=0.5)
    lines = terrain.model_contours(sheet())
    assert {line.source for line in lines} == {sources.SPATIAL}


def test_the_share_of_the_extent_a_council_holds_counts_its_holes_out() -> None:
    square = sheet()
    west, south, east, north = corners(square)
    outer = [
        (west - 1, south - 1),
        (east + 1, south - 1),
        (east + 1, north + 1),
        (west - 1, north + 1),
    ]
    hole_w, hole_e = west + (east - west) * 0.25, west + (east - west) * 0.75
    hole = [(hole_w, north + 1), (hole_e, north + 1), (hole_e, south - 1), (hole_w, south - 1)]
    assert terrain.share_inside([outer], square) == pytest.approx(1.0)
    assert terrain.share_inside([outer, hole], square) == pytest.approx(0.5, abs=0.01)


def test_contours_say_whose_they_are_through_a_saved_bundle() -> None:
    line = nsw.Contour(24.0, ((151.2, -33.9), (151.21, -33.9)), sources.CITY_OF_SYDNEY)
    assert nsw.Contour.from_dict(line.as_dict()) == line
    old = nsw.Contour.from_dict({"elevation": 24.0, "coords": [[151.2, -33.9], [151.21, -33.9]]})
    assert old.source == sources.SPATIAL, "before contours said whose, they were the state's"
