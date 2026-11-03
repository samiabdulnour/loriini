"""An amalgamated site, read through fake services.

An address point sits on one lot, but a property is often several: 99-107
Riley Street, Darlinghurst is three lots under one address. The site takes
every lot of each property an address names, found by a point inside each
lot; the neighbour on the property's edge is not taken. The geocoder does not
ask again for a number a range it found already covers, and the site is named
by every address it joins, in street order.
"""

from __future__ import annotations

from typing import Any

import pytest

from sun_study.site import geocode as geocode_module
from sun_study.site import nsw
from sun_study.site.geo import (
    Extent,
    Point,
    interior_point,
    lonlat_to_mercator,
    mercator_to_lonlat,
    point_in_ring,
    point_in_rings,
)
from sun_study.site.geocode import geocode, site_address_of

# Riley Street, Darlinghurst. Lots are made-up squares a few metres across.
LON, LAT = 151.2149, -33.8752
STEP = 0.0001  # about 10 m


def square(x0: float, y0: float, x1: float, y1: float) -> list[Point]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def lot(name: str, ring: list[Point]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"lotidstring": name},
    }


def collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


# 99-107: three lots side by side, west to east, its address point on the west one.
WEST = square(LON, LAT, LON + STEP, LAT + STEP)
MIDDLE = square(LON + STEP, LAT, LON + 2 * STEP, LAT + STEP)
EAST = square(LON + 2 * STEP, LAT, LON + 3 * STEP, LAT + STEP)
NEIGHBOUR = square(LON + 3 * STEP, LAT, LON + 4 * STEP, LAT + STEP)
LOTS = [
    lot("1//DP87611", WEST),
    lot("1//DP53785", MIDDLE),
    lot("1//DP87698", EAST),
    lot("1//DP99999", NEIGHBOUR),
]
PROPERTY = square(LON, LAT, LON + 3 * STEP, LAT + STEP)
ON_WEST = lonlat_to_mercator(LON + STEP / 2, LAT + STEP / 2)


class Cadastre:
    """The lot and property layers, answering by point and by window."""

    def __init__(self, property_lots: int | None) -> None:
        self.property_lots = property_lots
        self.windows: list[Extent] = []

    def by_point(self, url: str, point: Point, _fields: str = "*") -> dict[str, Any]:
        lon, lat = mercator_to_lonlat(*point)
        if url.endswith("/8"):
            return collection(
                *(f for f in LOTS if point_in_ring(lon, lat, f["geometry"]["coordinates"][0]))
            )
        assert url.endswith("/12")
        if self.property_lots is None or not point_in_ring(lon, lat, PROPERTY):
            return collection()
        feature = lot("", PROPERTY)
        feature["properties"] = {
            "propid": 2142555,
            "address": "99-107 RILEY STREET DARLINGHURST",
            "dissolveparcelcount": self.property_lots,
            "valnetlotcount": self.property_lots,
        }
        return collection(feature)

    def by_extent(self, url: str, extent: Extent, _fields: str = "*") -> dict[str, Any]:
        assert url.endswith("/8")
        self.windows.append(extent)
        return collection(*LOTS)


def names(site: dict[str, Any]) -> list[str]:
    return [f["properties"]["lotidstring"] for f in site["features"]]


def test_every_lot_of_the_property_is_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    cadastre = Cadastre(property_lots=3)
    monkeypatch.setattr(nsw, "query_by_point", cadastre.by_point)
    monkeypatch.setattr(nsw, "query_by_extent", cadastre.by_extent)
    site = nsw.site_lots([ON_WEST])
    assert names(site) == ["1//DP87611", "1//DP53785", "1//DP87698"]


def test_a_single_lot_property_asks_for_nothing_more(monkeypatch: pytest.MonkeyPatch) -> None:
    cadastre = Cadastre(property_lots=1)
    monkeypatch.setattr(nsw, "query_by_point", cadastre.by_point)
    monkeypatch.setattr(nsw, "query_by_extent", cadastre.by_extent)
    assert names(nsw.site_lots([ON_WEST])) == ["1//DP87611"]
    assert cadastre.windows == []


def test_a_property_too_big_to_be_a_site_keeps_the_lot_under_the_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cadastre = Cadastre(property_lots=nsw.PROPERTY_MAX_LOTS + 1)
    monkeypatch.setattr(nsw, "query_by_point", cadastre.by_point)
    monkeypatch.setattr(nsw, "query_by_extent", cadastre.by_extent)
    assert names(nsw.site_lots([ON_WEST])) == ["1//DP87611"]


def test_a_failed_property_query_still_gives_the_lot(monkeypatch: pytest.MonkeyPatch) -> None:
    cadastre = Cadastre(property_lots=3)

    def refuse(url: str, point: Point, fields: str = "*") -> dict[str, Any]:
        if url.endswith("/12"):
            raise RuntimeError("property layer down")
        return cadastre.by_point(url, point, fields)

    monkeypatch.setattr(nsw, "query_by_point", refuse)
    monkeypatch.setattr(nsw, "query_by_extent", cadastre.by_extent)
    assert names(nsw.site_lots([ON_WEST])) == ["1//DP87611"]


def test_a_point_inside_an_l_shaped_lot_is_inside_it() -> None:
    ell = [(0.0, 0.0), (20.0, 0.0), (20.0, 4.0), (4.0, 4.0), (4.0, 20.0), (0.0, 20.0)]
    inside = interior_point([ell])
    assert inside is not None
    assert point_in_ring(inside[0], inside[1], ell)
    assert interior_point([]) is None


def test_a_hole_is_outside_and_the_ring_around_it_inside() -> None:
    holed = [square(0, 0, 30, 30), square(10, 10, 20, 20)]
    assert not point_in_rings(15.0, 15.0, holed)
    assert point_in_rings(5.0, 5.0, holed)


def test_a_range_found_whole_is_not_asked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    register = {
        "91-93": (151.21495, -33.87495),
        "95-97": (151.21489, -33.87504),
        "99-107": (151.21486, -33.87518),
    }
    asked: list[str] = []

    def fake_query(
        _url: str, where: str, _fields: str, _count: int | None = None
    ) -> dict[str, Any]:
        asked.append(where)
        features = []
        for number, (lon, lat) in register.items():
            address = f"{number} RILEY STREET DARLINGHURST"
            anchor = where.split("'")[1] if where.startswith("address LIKE") else ""
            prefix = anchor.rstrip("%")
            if anchor and address.startswith(prefix):
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "properties": {"address": address, "housenumber": number},
                    }
                )
        return collection(*features)

    monkeypatch.setattr(geocode_module, "query_where", fake_query)
    found = geocode("91-107 Riley Street, Darlinghurst NSW")
    assert sorted(found.matched) == [
        "91-93 RILEY STREET DARLINGHURST",
        "95-97 RILEY STREET DARLINGHURST",
        "99-107 RILEY STREET DARLINGHURST",
    ]
    # Only 91, 95 and 99 are looked up by prefix; 93, 97 and 101-107 are covered.
    prefixed = {
        w.split("'")[1].rstrip("%").rstrip(" -") for w in asked if w.startswith("address LIKE")
    }
    assert prefixed == {"91", "95", "99"}


@pytest.mark.parametrize(
    ("matched", "named"),
    [
        (["109 RILEY STREET DARLINGHURST"], "109 RILEY STREET DARLINGHURST"),
        ([], None),
        (
            [
                "109 RILEY STREET DARLINGHURST",
                "91-93 RILEY STREET DARLINGHURST",
                "95-97 RILEY STREET DARLINGHURST",
                "99-107 RILEY STREET DARLINGHURST",
            ],
            "91-93, 95-97, 99-107, 109 RILEY STREET DARLINGHURST",
        ),
        (
            [
                "136 SHOWGROUND ROAD CASTLE HILL",
                "134-134A SHOWGROUND ROAD CASTLE HILL",
                "136A SHOWGROUND ROAD CASTLE HILL",
            ],
            "134-134A, 136, 136A SHOWGROUND ROAD CASTLE HILL",
        ),
        (
            ["140 SHOWGROUND ROAD CASTLE HILL", "134, 136, 136A, 138 SHOWGROUND ROAD CASTLE HILL"],
            "134, 136, 136A, 138, 140 SHOWGROUND ROAD CASTLE HILL",
        ),
        (
            ["9 7 HILLS ROAD BAULKHAM HILLS", "7 7 HILLS ROAD BAULKHAM HILLS"],
            "7, 9 7 HILLS ROAD BAULKHAM HILLS",
        ),
        (
            ["5 JONES ROAD CAMPSIE", "2 SMITH STREET CAMPSIE"],
            "2 SMITH STREET CAMPSIE; 5 JONES ROAD CAMPSIE",
        ),
        (
            ["26 CAMPSIE STREET CAMPSIE", "26 CAMPSIE STREET CAMPSIE"],
            "26 CAMPSIE STREET CAMPSIE",
        ),
    ],
)
def test_the_site_is_named_by_every_address_it_joins(matched: list[str], named: str | None) -> None:
    assert site_address_of(matched) == named
