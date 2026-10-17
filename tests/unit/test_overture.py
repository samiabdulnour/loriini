"""Overture's building footprints, as the context model takes them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sun_study.site import osm, overture, pipeline
from sun_study.site.geo import Extent
from sun_study.site.osm import Building

EXTENT = Extent(16820000.0, -4017000.0, 16821000.0, -4016000.0)

SQUARE = [[151.10, -33.91], [151.11, -33.91], [151.11, -33.90], [151.10, -33.90], [151.10, -33.91]]
HOLE = [[151.104, -33.906], [151.106, -33.906], [151.106, -33.904], [151.104, -33.906]]


def _cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rows: list[list[object]]) -> None:
    cache = tmp_path / "overture.json"
    cache.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(overture, "_cache_file", lambda *box: cache)


def test_a_cached_answer_becomes_footprints_with_their_heights(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A measured height, a storey count, a courtyard, and a multipolygon's
    parts as buildings of their own -- read back without DuckDB at all."""
    _cached(
        monkeypatch,
        tmp_path,
        [
            [12.5, None, {"type": "Polygon", "coordinates": [SQUARE, HOLE]}],
            [None, 4, {"type": "MultiPolygon", "coordinates": [[SQUARE], [SQUARE]]}],
            [-1.0, 0, {"type": "Polygon", "coordinates": [SQUARE]}],
        ],
    )

    found = overture.buildings(EXTENT)

    assert found is not None and len(found) == 4
    first = found[0]
    assert first.height_m == 12.5 and first.levels is None
    assert len(first.ring) == 4, "the closing point is not kept twice"
    assert len(first.holes) == 1
    assert (found[1].levels, found[1].height_m) == (4, None)
    assert (found[3].levels, found[3].height_m) == (None, None), "unknowns stay unknown"


def test_openstreetmap_stands_in_when_overture_cannot_be_had(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overture first; a failure, or no DuckDB, falls back to OSM's and says so."""
    from_osm = (Building(lon=151.1, lat=-33.9, ring=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))),)
    monkeypatch.setattr(osm, "buildings", lambda extent, log=None: from_osm)
    said: list[str] = []

    def broken(extent: Extent, log: object = None) -> None:
        raise RuntimeError("HTTP 404\nmore detail")

    monkeypatch.setattr(overture, "buildings", broken)
    assert pipeline.building_footprints(EXTENT, said.append) == from_osm
    assert any("Overture buildings failed: HTTP 404;" in line for line in said)

    monkeypatch.setattr(overture, "buildings", lambda extent, log=None: None)
    assert pipeline.building_footprints(EXTENT, said.append) == from_osm
