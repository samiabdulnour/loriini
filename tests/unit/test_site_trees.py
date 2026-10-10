"""Trees with a size: the council's inventory first, OpenStreetMap around it.

The figures are the generator's (``au-site-analysis``, ``test/site-features``)
so the two draw the same tree the same size; the inventory is read through a
fake query that answers what the City of Sydney's layer answers.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from sun_study.site import sources, trees
from sun_study.site.geo import extent_for, lonlat_to_mercator
from sun_study.site.osm import Furniture
from sun_study.site.trees import (
    NOMINAL_CANOPY_M,
    Tree,
    council_trees,
    merge_trees,
    parse_metres,
    resolve_canopy,
    sources_for,
    tree_from_osm,
    trees_along_row,
)

# Surry Hills: inside the City of Sydney's box.
SURRY_HILLS = (151.2135, -33.8850)
# Campsie: outside every council inventory listed.
CAMPSIE = (151.1030, -33.9120)


def test_a_recorded_canopy_wins_then_the_height_then_the_trunk() -> None:
    assert resolve_canopy(8.0, 20.0, 90.0) == (8.0, "measured")
    height = resolve_canopy(None, 10.0, 90.0)
    assert height[0] == pytest.approx(6.0) and height[1] == "estimated"
    trunk = resolve_canopy(None, None, 40.0)
    assert trunk[0] == pytest.approx(8.0) and trunk[1] == "estimated"
    assert resolve_canopy() == (NOMINAL_CANOPY_M, "nominal")


def test_a_register_typing_error_does_not_become_a_tree_the_size_of_the_sheet() -> None:
    assert resolve_canopy(90.0) == (40.0, "measured")
    assert resolve_canopy(0.2) == (1.0, "measured")
    assert resolve_canopy(None, 80.0) == (25.0, "estimated")
    assert resolve_canopy(None, 1.0) == (2.0, "estimated")


@pytest.mark.parametrize(
    ("written", "metres"),
    [
        ("8", 8.0),
        ("8 m", 8.0),
        ("8.5m", 8.5),
        ("8,5 m", 8.5),
        ("800 cm", 8.0),
        ("30 ft", 30 * 0.3048),
        ("30'", 30 * 0.3048),
        (12, 12.0),
    ],
)
def test_lengths_read_the_way_mappers_write_them(written: Any, metres: float) -> None:
    assert parse_metres(written) == pytest.approx(metres)


@pytest.mark.parametrize("written", [None, "", "tall", "0", "-3", "8 storeys"])
def test_what_is_not_a_length_is_not_read_as_one(written: Any) -> None:
    assert parse_metres(written) is None


def test_an_osm_tree_takes_whatever_size_its_tags_record() -> None:
    crown = tree_from_osm(151.2, -33.9, {"diameter_crown": "9", "species": "Platanus x acerifolia"})
    assert (crown.canopy_m, crown.canopy_from) == (9.0, "measured")
    assert crown.species == "Platanus x acerifolia" and crown.source == sources.OSM

    tall = tree_from_osm(151.2, -33.9, {"height": "15 m", "species:en": "London Plane"})
    assert tall.canopy_m == pytest.approx(9.0) and tall.canopy_from == "estimated"
    assert tall.common == "London Plane"

    # A girth of 1.26 m is a trunk 40 cm across, under an 8 m crown.
    girth = tree_from_osm(151.2, -33.9, {"circumference": "1.2566"})
    assert girth.dbh_cm == pytest.approx(40.0, abs=0.01)
    assert girth.canopy_m == pytest.approx(8.0, abs=0.01)

    bare = tree_from_osm(151.2, -33.9, {"genus": "Eucalyptus"})
    assert (bare.canopy_m, bare.canopy_from) == (NOMINAL_CANOPY_M, "nominal")
    assert bare.species == "Eucalyptus"


def test_a_tree_row_is_a_row_of_trees_every_eight_metres() -> None:
    lon, lat = SURRY_HILLS
    east = lon + 98.0 / (111_320.0 * math.cos(math.radians(lat)))
    row = trees_along_row([(lon, lat), (east, lat)])
    # Half a spacing in, then every 8 m: 4, 12, ... 92 m along 98 -> twelve.
    assert len(row) == 12
    assert all(t.canopy_from == "nominal" for t in row)
    first = lonlat_to_mercator(row[0].lon, row[0].lat)
    second = lonlat_to_mercator(row[1].lon, row[1].lat)
    k = 1.0 / math.cos(math.radians(lat))
    assert math.dist(first, second) / k == pytest.approx(8.0, abs=0.01)
    assert trees_along_row([(lon, lat)]) == []


def test_only_a_site_inside_a_councils_box_asks_it() -> None:
    inside = extent_for(lonlat_to_mercator(*SURRY_HILLS), 690.0, 594.0, 500.0)
    outside = extent_for(lonlat_to_mercator(*CAMPSIE), 690.0, 594.0, 500.0)
    assert [s.slug for s in sources_for(inside)] == [sources.CITY_OF_SYDNEY]
    assert sources_for(outside) == ()


def inventory(*records: dict[str, Any]) -> dict[str, Any]:
    """What the City of Sydney's Trees layer answers, as GeoJSON features."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": properties,
            }
            for lon, lat, properties in (
                (r.pop("lon"), r.pop("lat"), r) for r in (dict(one) for one in records)
            )
        ],
    }


def test_the_councils_inventory_gives_every_tree_its_recorded_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    lon, lat = SURRY_HILLS

    def fake(layer: str, extent: Any, fields: str = "*", *args: Any, **kwargs: Any) -> Any:
        asked.append(fields)
        return inventory(
            {
                "lon": lon,
                "lat": lat,
                "SpeciesName": "Lophostemon confertus",
                "CommonName": "Brush Box",
                "TreeHeight": 10,
                "TreeCanopyNS": 4,
                "DBH_in_cm": 18,
                "Tree_Status": "Tree",
            },
            # A planting site with nothing in it yet is not a tree.
            {"lon": lon, "lat": lat + 0.0001, "Tree_Status": "Vacant", "TreeCanopyNS": 5},
            {"lon": lon + 0.0001, "lat": lat, "TreeHeight": 15, "TreeCanopyNS": 0},
        )

    monkeypatch.setattr(trees, "query_by_extent", fake)
    said: list[str] = []
    found = council_trees(
        extent_for(lonlat_to_mercator(lon, lat), 690.0, 594.0, 300.0), log=said.append
    )

    assert len(found) == 2
    brush = found[0]
    assert (brush.canopy_m, brush.canopy_from) == (4.0, "measured")
    assert (brush.height_m, brush.dbh_cm) == (10.0, 18.0)
    assert (brush.common, brush.species) == ("Brush Box", "Lophostemon confertus")
    assert brush.source == sources.CITY_OF_SYDNEY
    # No canopy recorded: worked out from the height.
    assert found[1].canopy_m == pytest.approx(9.0) and found[1].canopy_from == "estimated"
    assert "TreeCanopyNS" in asked[0] and "DBH_in_cm" in asked[0]
    assert said == ["  City of Sydney tree inventory: 2 trees"]


def test_a_site_outside_every_council_asks_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("asked a council whose box the site is not in")

    monkeypatch.setattr(trees, "query_by_extent", refuse)
    assert council_trees(extent_for(lonlat_to_mercator(*CAMPSIE), 690.0, 594.0, 300.0)) == []


def test_an_osm_tree_where_the_council_has_one_is_the_same_tree_mapped_twice() -> None:
    lon, lat = SURRY_HILLS
    metre = 1.0 / 111_320.0
    council = [Tree(lon, lat, 4.0, "measured", source=sources.CITY_OF_SYDNEY)]
    mapped = [
        Tree(lon, lat + 3.0 * metre),  # three metres off: the same tree
        Tree(lon, lat + 5.0 * metre),  # five: another one
        Tree(lon + 50.0 * metre, lat),  # well clear
    ]
    merged = merge_trees(council, mapped)
    assert len(merged) == 3
    assert merged[0].source == sources.CITY_OF_SYDNEY
    assert [t.lat for t in merged[1:]] == [lat + 5.0 * metre, lat]
    assert merge_trees([], mapped) == mapped


def test_a_tree_survives_the_bundle_and_an_old_bundles_tree_is_a_nominal_osm_one() -> None:
    brush = Tree(151.2, -33.9, 4.0, "measured", 10.0, 18.0, "Lophostemon confertus", "Brush Box")
    brush = Tree(**{**brush.__dict__, "source": sources.CITY_OF_SYDNEY})
    furniture = Furniture(trees=(brush,))
    assert Furniture.from_dict(furniture.as_dict()) == furniture

    old = Furniture.from_dict({"trees": [[151.2, -33.9]]})
    assert old.trees == (Tree(151.2, -33.9),)
    assert old.trees[0].canopy_from == "nominal" and old.trees[0].source == sources.OSM


def test_the_site_run_puts_the_councils_trees_first_and_says_how_many_of_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``run_site`` with every register stubbed: the council's inventory and
    OpenStreetMap both answer, the tree they both mapped is kept once, as the
    council's, and the sheet's contours are whatever ``terrain`` chose."""
    from sun_study.site import nsw, osm, pipeline, terrain, transport
    from sun_study.site.geocode import Geocode

    lon, lat = SURRY_HILLS
    metre = 1.0 / 111_320.0
    ring = [
        [lon - 10 * metre, lat - 10 * metre],
        [lon + 10 * metre, lat - 10 * metre],
        [lon + 10 * metre, lat + 10 * metre],
        [lon - 10 * metre, lat + 10 * metre],
        [lon - 10 * metre, lat - 10 * metre],
    ]
    lot = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"lotidstring": "1//DP1"},
    }
    centre = lonlat_to_mercator(lon, lat)
    monkeypatch.setattr(
        pipeline, "geocode", lambda address: Geocode((centre,), centre, ("1 TEST ST",), address)
    )
    monkeypatch.setattr(
        nsw, "site_lots", lambda points: {"type": "FeatureCollection", "features": [lot]}
    )

    def offline(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("offline")

    monkeypatch.setattr(nsw, "query_by_extent", offline)
    monkeypatch.setattr(transport, "tfnsw_key", lambda: None)
    line = nsw.Contour(30.0, ((lon - 0.001, lat), (lon + 0.001, lat)), sources.CITY_OF_SYDNEY)
    monkeypatch.setattr(terrain, "sheet_contours", lambda extent, log=None: [line])
    council = Tree(lon, lat + 30 * metre, 8.0, "measured", source=sources.CITY_OF_SYDNEY)
    monkeypatch.setattr(trees, "council_trees", lambda extent, log=None: [council])
    mapped = (Tree(lon, lat + 32 * metre), Tree(lon + 40 * metre, lat))
    monkeypatch.setattr(osm, "furniture", lambda extent, log=None: Furniture(trees=mapped))

    said: list[str] = []
    bundle = pipeline.run_site("1 Test St, Surry Hills", log=said.append)

    assert bundle.furniture.trees == (council, mapped[1])
    assert bundle.contours == (line,)
    assert any("trees:2 (council 1, OSM 2)" in s for s in said), said
    assert sources.CITY_OF_SYDNEY in bundle.sources_used()
