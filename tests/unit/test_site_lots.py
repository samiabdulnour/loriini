"""Which lots are the site: the address's, or the ones named. No network."""

from __future__ import annotations

from typing import Any

import pytest

from sun_study.site import nsw, pipeline
from sun_study.site.geo import lonlat_to_mercator
from sun_study.site.geocode import Geocode, Place
from sun_study.site.nsw import lot_id

ADDRESS = "22A O'CONNELL STREET PARRAMATTA"
OWN = (151.001057, -33.811945)
SHARED = (151.000695, -33.813297)


def _lot(name: str, lon: float, lat: float) -> dict[str, Any]:
    d = 0.0001
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d]]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[*ring, ring[0]]]},
        "properties": {"lotidstring": name},
    }


def _found(*places: tuple[tuple[float, float], str]) -> Geocode:
    points = tuple(lonlat_to_mercator(*lonlat) for lonlat, _when in places)
    return Geocode(
        points=points,
        centre=points[0],
        matched=(ADDRESS,),
        query=ADDRESS,
        places=tuple(Place(ADDRESS, p, when) for p, (_, when) in zip(points, places, strict=True)),
    )


def test_a_lot_is_read_however_it_is_written() -> None:
    assert lot_id("34//DP1206876") == "34//DP1206876"
    assert lot_id("34/DP1206876") == "34//DP1206876"
    assert lot_id("Lot 34 DP1206876") == "34//DP1206876"
    assert lot_id(" lot 34  dp 1206876 ") == "34//DP1206876"
    assert lot_id("1/2/DP123") == "1/2/DP123"
    with pytest.raises(ValueError, match="34//DP1206876"):
        lot_id("22A O'Connell Street")


def test_an_address_on_two_lots_is_refused_with_both(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drawn on whichever point came back last, 22A became 22's lot."""
    monkeypatch.setattr(
        pipeline, "geocode", lambda _a: _found((OWN, "July 2019"), (SHARED, "May 2026"))
    )
    under = {OWN: "34//DP1206876", SHARED: "2//DP874120"}

    def site_lots(points: list[tuple[float, float]]) -> dict[str, Any]:
        (point,) = points
        lonlat = min(under, key=lambda ll: abs(lonlat_to_mercator(*ll)[0] - point[0]))
        return {"type": "FeatureCollection", "features": [_lot(under[lonlat], *lonlat)]}

    monkeypatch.setattr(nsw, "site_lots", site_lots)
    with pytest.raises(ValueError) as refused:
        pipeline.locate(ADDRESS)
    said = str(refused.value)
    assert "lot 34//DP1206876, registered July 2019" in said
    assert "lot 2//DP874120, registered May 2026" in said
    assert "--lot" in said


def test_an_address_twice_on_one_lot_is_not_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline, "geocode", lambda _a: _found((OWN, "July 2019"), (OWN, "May 2026"))
    )
    lot = {"type": "FeatureCollection", "features": [_lot("34//DP1206876", *OWN)]}
    monkeypatch.setattr(nsw, "site_lots", lambda _points: lot)
    _, site = pipeline.locate(ADDRESS)
    assert site is lot


def test_named_lots_are_the_site_and_the_address_is_not_looked_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_geocode(_address: str) -> Geocode:
        raise AssertionError("a named lot needs no address lookup")

    asked: list[list[str]] = []

    def lots_by_id(ids: list[str]) -> dict[str, Any]:
        asked.append(list(ids))
        return {"type": "FeatureCollection", "features": [_lot("34//DP1206876", *OWN)]}

    monkeypatch.setattr(pipeline, "geocode", no_geocode)
    monkeypatch.setattr(nsw, "lots_by_id", lots_by_id)
    found, site = pipeline.locate(ADDRESS, ["34/DP1206876"])
    assert asked == [["34//DP1206876"]]
    assert found.matched == (ADDRESS,)
    assert found.lonlat_points[0] == pytest.approx(OWN, abs=1e-6)
    assert site["features"][0]["properties"]["lotidstring"] == "34//DP1206876"


def test_a_named_lot_the_cadastre_does_not_have_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        nsw, "lots_by_id", lambda _ids: {"type": "FeatureCollection", "features": []}
    )
    with pytest.raises(ValueError, match=r"Not in the NSW cadastre: lot 34//DP1206876"):
        pipeline.locate(ADDRESS, ["34//DP1206876"])


def test_the_point_of_a_named_lot_is_on_the_lot() -> None:
    """The controls are read at it. A C-shaped lot's centroid is in the gap,
    on the lot next door; and taken straight in degrees, a 20 m lot's
    centroid landed 60 m out."""
    from sun_study.site.geo import point_in_ring

    lon, lat, s = 151.0, -33.8, 0.0001
    c_shape = [
        (lon + x * s, lat + y * s)
        for x, y in ((0, 0), (3, 0), (3, 1), (1, 1), (1, 2), (3, 2), (3, 3), (0, 3))
    ]
    x, y = pipeline.inside_point(c_shape)
    assert point_in_ring(x, y, c_shape)
    square = [*c_shape[:2], (lon + 3 * s, lat + 3 * s), (lon, lat + 3 * s)]
    assert pipeline.inside_point(square) == pytest.approx((lon + 1.5 * s, lat + 1.5 * s), abs=1e-9)
