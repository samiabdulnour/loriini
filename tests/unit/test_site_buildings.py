"""Every building OSM has, and every one of them in the model.

A context model that is short of buildings reports more sunlight than the
site gets, and says nothing about it: the gap looks like a car park. Three
ways it happened, each pinned here.

* **An answer the server cut short.** A busy Overpass stops at its timeout
  and still replies 200 with valid JSON -- the elements it had reached, and
  a ``remark``. That was taken for the whole answer and cached for a month.
* **Buildings drawn as relations.** A building with a courtyard is a
  multipolygon relation in OSM, with its tag on the relation and none on
  the member ways; a query for tagged ways never saw it.
* **One bad footprint, two hundred lost.** Archicad makes a request in one
  undo step and drops the step at the first slab it refuses.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from sun_study.archicad.connection import ArchicadError
from sun_study.site import http, osm

# -- Overpass: an answer cut short is not an answer ------------------------------


def _answers(monkeypatch: pytest.MonkeyPatch, by_mirror: dict[str, Any]) -> list[str]:
    """Every mirror answers with what it is given; returns the order asked."""
    asked: list[str] = []

    def fake_fetch(url: str, **_: Any) -> bytes:
        asked.append(url)
        answer = by_mirror.get(url)
        if answer is None:
            raise http.FetchError(f"{url} -> refused")
        return json.dumps(answer).encode()

    monkeypatch.setattr(http, "fetch", fake_fetch)
    monkeypatch.setattr(http, "_endpoints", lambda: list(by_mirror))
    monkeypatch.setattr("sun_study.site.http.time.sleep", lambda _s: None)
    return asked


TIMED_OUT = {
    "elements": [{"type": "way", "id": 1}],
    "remark": 'runtime error: Query timed out in "query" at line 2 after 120 seconds.',
}
COMPLETE = {"elements": [{"type": "way", "id": 1}, {"type": "way", "id": 2}]}


def test_a_cut_short_answer_is_tried_elsewhere_and_never_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked = _answers(monkeypatch, {"https://a": TIMED_OUT, "https://b": COMPLETE})

    got = http.overpass("[out:json];way;out;", cache_dir=tmp_path)

    assert got["elements"] == COMPLETE["elements"]
    assert asked == ["https://a", "https://b"], "the partial answer was taken as whole"
    cached = [json.loads(path.read_text()) for path in tmp_path.glob("*.json")]
    assert cached == [COMPLETE], "only the complete answer is kept"


def test_with_nothing_complete_anywhere_the_fullest_partial_is_used_and_said(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    thin = {"elements": [], "remark": "runtime error: out of memory"}
    _answers(monkeypatch, {"https://a": thin, "https://b": TIMED_OUT})
    said: list[str] = []

    got = http.overpass("[out:json];way;out;", cache_dir=tmp_path, rounds=1, log=said.append)

    assert got["elements"] == TIMED_OUT["elements"]
    assert any("partial" in line for line in said), "a partial answer must say so"
    assert not list(tmp_path.glob("*.json")), "and must not be cached"


def test_a_partial_answer_cached_by_an_older_version_is_not_served(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The month-long gap: an earlier build cached the partial answer."""
    query = "[out:json];way;out;"
    _answers(monkeypatch, {"https://a": COMPLETE})
    import hashlib

    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
    (tmp_path / f"{digest}.json").write_text(json.dumps(TIMED_OUT))

    got = http.overpass(query, cache_dir=tmp_path)

    assert got["elements"] == COMPLETE["elements"]


def test_the_mirror_with_the_expired_certificate_is_asked_last() -> None:
    assert http.OVERPASS_MIRRORS[-1] == "https://overpass.osm.jp/api/interpreter"
    assert "https://overpass.private.coffee/api/interpreter" in http.OVERPASS_MIRRORS


# -- OSM: the buildings drawn as relations ----------------------------------------


def _way(*points: tuple[float, float], **tags: str) -> dict[str, Any]:
    return {
        "type": "way",
        "tags": tags,
        "geometry": [{"lon": x, "lat": y} for x, y in points],
    }


def _member(role: str, *points: tuple[float, float]) -> dict[str, Any]:
    return {"type": "way", "role": role, "geometry": [{"lon": x, "lat": y} for x, y in points]}


def test_a_courtyard_block_is_found_though_its_ways_carry_no_tag() -> None:
    """The outline in two ways, joined at their ends, one of them the wrong
    way round; the courtyard a hole in it."""
    relation = {
        "type": "relation",
        "tags": {"type": "multipolygon", "building": "apartments", "building:levels": "6"},
        "members": [
            _member("outer", (0, 0), (10, 0), (10, 10)),
            _member("outer", (0, 0), (0, 10), (10, 10)),  # reversed: ends where the other ends
            _member("inner", (4, 4), (6, 4), (6, 6), (4, 6), (4, 4)),
        ],
    }

    found = osm._buildings_in([relation])

    assert len(found) == 1
    block = found[0]
    assert len(block.ring) == 5 and block.ring[0] == block.ring[-1], "closed"
    assert len(block.holes) == 1
    assert block.levels == 6


def test_an_outline_cut_by_the_box_is_dropped_rather_than_half_built() -> None:
    relation = {
        "type": "relation",
        "tags": {"type": "multipolygon", "building": "yes"},
        "members": [_member("outer", (0, 0), (10, 0), (10, 10))],
    }

    assert osm._buildings_in([relation]) == []


def test_a_way_that_is_also_the_relations_outline_stands_once() -> None:
    ring = ((0, 0), (10, 0), (10, 10), (0, 10), (0, 0))
    relation = {
        "type": "relation",
        "tags": {"type": "multipolygon", "building": "yes"},
        "members": [_member("outer", *ring)],
    }

    found = osm._buildings_in([_way(*ring, building="yes"), relation])

    assert len(found) == 1


def test_untagged_ways_are_not_buildings() -> None:
    assert osm._buildings_in([_way((0, 0), (1, 0), (1, 1), (0, 0), highway="service")]) == []


@pytest.mark.parametrize(
    ("tags", "storeys"),
    [
        ({"building:levels": "4"}, 4),
        ({"building:levels": "3;4"}, 4),  # a list: the taller casts the shadow
        ({"building:levels": "2-5"}, 5),
        ({"building:levels": "3", "roof:levels": "1"}, 4),
        ({"building:levels": "two"}, None),
        ({}, None),
    ],
)
def test_storeys_are_read_the_way_osm_writes_them(
    tags: dict[str, str], storeys: int | None
) -> None:
    assert osm._levels(tags) == storeys


def test_a_building_with_holes_survives_being_saved() -> None:
    block = osm.Building(
        5.0, 5.0, ((0, 0), (10, 0), (10, 10), (0, 0)), 6, None, (((4, 4), (6, 4), (6, 6)),)
    )

    assert osm.Building.from_dict(json.loads(json.dumps(block.as_dict()))) == block


# -- Archicad: one bad footprint costs one building -------------------------------


def _slab(name: str, *, holes: bool = False) -> Any:
    from sun_study.archicad.context_model import _Slab

    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    return _Slab(
        outline=square,
        holes=[[(4.0, 4.0), (6.0, 4.0), (6.0, 6.0)]] if holes else [],
        level=0.0,
        thickness=6.2,
        identifier=name,
    )


class _Archicad:
    """Refuses any request holding a slab whose name is on its list, the way
    Archicad abandons the whole undo step."""

    def __init__(self, refuses: Sequence[str], *, holes_refused: bool = False) -> None:
        self.refuses = set(refuses)
        self.holes_refused = holes_refused
        self.requests = 0

    def send(self, chunk: Sequence[Any]) -> list[dict[str, Any]]:
        self.requests += 1
        for slab in chunk:
            # Refused as drawn; with ``holes_refused`` only while it has holes.
            if slab.identifier in self.refuses and (slab.holes or not self.holes_refused):
                raise ArchicadError("Archicad refused to create a slab.")
        return [{"elementId": {"guid": slab.identifier}} for slab in chunk]


def test_one_refused_footprint_costs_that_footprint_and_no_other() -> None:
    from sun_study.archicad.context_model import _create_slabs

    slabs = [_slab(f"S{i}") for i in range(200)]
    archicad = _Archicad(["S137"])

    done = _create_slabs(archicad.send, slabs)

    assert done is not None
    made = [name for _, name in done.made]
    assert len(made) == 199, "the neighbours of a bad slab were lost with it"
    assert "S137" not in made
    assert len(done.lost) == 1
    assert archicad.requests < 40, "found by halving, not one by one"


def test_a_refused_footprint_is_tried_without_its_courtyard_before_it_is_lost() -> None:
    from sun_study.archicad.context_model import _create_slabs

    archicad = _Archicad(["COURT"], holes_refused=True)

    done = _create_slabs(archicad.send, [_slab("OK"), _slab("COURT", holes=True)])

    assert done is not None
    assert [name for _, name in done.made] == ["OK", "COURT"]
    assert done.simplified == 1
    assert "simplified" in " ".join(done.describe())


def test_an_add_on_without_create_slabs_hands_over_to_tapir() -> None:
    from sun_study.archicad.context_model import _create_slabs, _NoSuchCommandError

    def send(_chunk: Sequence[Any]) -> list[dict[str, Any]]:
        raise _NoSuchCommandError

    assert _create_slabs(send, [_slab("A")]) is None


def test_a_hand_drawn_outline_is_tidied_to_one_archicad_will_take() -> None:
    """A node doubled a millimetre away, a spike dragged out and back, and a
    node on a straight run: the same square, four corners."""
    from sun_study.archicad.context_model import _slab_outline

    drawn = [
        (0.0, 0.0),
        (0.001, 0.0),  # doubled
        (5.0, 0.0),  # on a straight run
        (10.0, 0.0),
        (10.0, 10.0),
        (10.0, 15.0),  # a spike out ...
        (10.0, 10.0000001),  # ... and straight back
        (0.0, 10.0),
        (0.0, 0.0),
    ]

    tidy = _slab_outline(drawn)

    assert len(tidy) == 4, tidy
