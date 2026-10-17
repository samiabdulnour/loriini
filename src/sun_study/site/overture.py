"""Building footprints with heights from Overture Maps, for the context model.

OpenStreetMap is only as complete as the people who traced it. Around
Campsie station it had 304 buildings in the half kilometre each way and a
whole quarter of the square empty; Overture, which merges OSM with
Microsoft's and others' machine-traced footprints, had 1,058 there, 895 of
them with a measured height (17 October 2026). The recipe is the one
au-site-analysis uses (``src/py/overture_buildings.py``): DuckDB reads the
buildings theme straight from Overture's public bucket, keeping only the
row groups whose boxes touch the window, and falls back to the same release
on Overture's Azure mirror when the S3 scan keeps failing.

The answer is cached for a month, as Overpass answers are: Overture
publishes monthly, and a minute's scan is worth not repeating for every run
of the same address. ``None`` means DuckDB is not installed, and the caller
falls back to OpenStreetMap.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sun_study.site.geo import Extent
from sun_study.site.http import overpass_cache_dir
from sun_study.site.osm import Building

__all__ = ["RELEASE", "buildings"]

Log = Callable[[str], None]

#: The Overture release read, overridable as au-site-analysis allows. A
#: release stays in the bucket for a few months after the next one is out.
RELEASE = os.environ.get("OVERTURE_RELEASE", "2026-09-23.1")

#: How long a cached answer is served without asking again.
MAX_AGE_S = 30 * 24 * 3600.0

_SELECT = """
    SELECT height, num_floors, ST_AsGeoJSON(geometry) AS geojson
    FROM read_parquet('{path}', hive_partitioning=1)
    WHERE bbox.xmin <= {east} AND bbox.xmax >= {west}
      AND bbox.ymin <= {north} AND bbox.ymax >= {south}
"""


def _cache_file(west: float, south: float, east: float, north: float) -> Path:
    key = f"{RELEASE}:{west:.5f},{south:.5f},{east:.5f},{north:.5f}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return overpass_cache_dir().parent / "overture" / f"{digest}.json"


def _scan(duckdb: Any, where: str, box: dict[str, float]) -> list[tuple[Any, ...]]:
    """One scan of the release, from S3 or from the Azure mirror."""
    suffix = f"release/{RELEASE}/theme=buildings/type=building/*"
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    proxy_url = urlparse(proxy) if proxy else None
    con = duckdb.connect()
    if where == "s3":
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
        con.execute(
            "SET s3_region='us-west-2'; SET s3_access_key_id=''; SET s3_secret_access_key='';"
        )
        if proxy_url:
            con.execute(f"SET http_proxy='{proxy_url.hostname}:{proxy_url.port}';")
        path = f"s3://overturemaps-us-west-2/{suffix}"
    else:
        con.execute("INSTALL azure; LOAD azure; INSTALL spatial; LOAD spatial;")
        con.execute("SET azure_transport_option_type='curl';")
        if proxy_url:
            con.execute(f"SET azure_http_proxy='http://{proxy_url.hostname}:{proxy_url.port}';")
        con.execute(
            "SET azure_storage_connection_string='DefaultEndpointsProtocol=https;"
            "AccountName=overturemapswestus2;EndpointSuffix=core.windows.net';"
        )
        path = f"az://{suffix}"
    rows: list[tuple[Any, ...]] = con.execute(_SELECT.format(path=path, **box)).fetchall()
    return rows


def _rings(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    """A GeoJSON polygon or multipolygon as its polygons, each outer ring
    first and its holes after."""
    kind = geometry.get("type")
    if kind == "Polygon":
        return [geometry["coordinates"]]
    if kind == "MultiPolygon":
        return list(geometry["coordinates"])
    return []


def _building(polygon: Sequence[Sequence[Sequence[float]]], height: Any, floors: Any) -> Building:
    outer = tuple((float(x), float(y)) for x, y, *_ in polygon[0])
    if len(outer) > 1 and outer[0] == outer[-1]:
        outer = outer[:-1]
    holes = tuple(
        tuple((float(x), float(y)) for x, y, *_ in ring[:-1] if ring) for ring in polygon[1:]
    )
    return Building(
        lon=sum(p[0] for p in outer) / len(outer),
        lat=sum(p[1] for p in outer) / len(outer),
        ring=outer,
        levels=int(floors) if floors and int(floors) > 0 else None,
        height_m=float(height) if height and float(height) > 0 else None,
        holes=tuple(hole for hole in holes if len(hole) >= 3),
    )


def buildings(extent: Extent, *, log: Log | None = None) -> tuple[Building, ...] | None:
    """Every Overture building touching the extent, or ``None`` without DuckDB.

    Raises when every scan failed, so the caller can say so and fall back.
    """
    say = log or (lambda _message: None)
    south, west, north, east = extent.lonlat_bbox()
    cache = _cache_file(west, south, east, north)
    if cache.is_file() and time.time() - cache.stat().st_mtime < MAX_AGE_S:
        rows = json.loads(cache.read_text(encoding="utf-8"))
    else:
        try:
            import duckdb
        except ImportError:
            say("  buildings: DuckDB is not installed, so OpenStreetMap's are used")
            return None
        box = {"west": west, "south": south, "east": east, "north": north}
        started = time.time()
        # The scan reads the footer of every part file of the theme, a few
        # hundred small requests, and one stray 404 kills the whole query; so
        # S3 is tried twice and then the Azure mirror, down a different path.
        found: list[tuple[Any, ...]] | None = None
        attempts = ("s3", "s3", "azure")
        for number, where in enumerate(attempts):
            try:
                found = _scan(duckdb, where, box)
                break
            except Exception as error:
                if number == len(attempts) - 1:
                    raise
                first = str(error).splitlines()[0][:120]
                say(f"  Overture {where} scan failed ({first}); trying {attempts[number + 1]}")
        assert found is not None
        rows = [[height, floors, json.loads(geojson)] for height, floors, geojson in found]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows), encoding="utf-8")
        say(f"  buildings: {len(rows)} from Overture {RELEASE} in {time.time() - started:.0f} s")
    made: list[Building] = []
    for height, floors, geometry in rows:
        for polygon in _rings(geometry):
            if polygon and len(polygon[0]) >= 4:
                made.append(_building(polygon, height, floors))
    return tuple(made)
