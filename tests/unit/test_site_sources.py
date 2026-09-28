"""Who the site analysis owes, and the one way that list goes wrong.

The list itself is prose and needs no test. What needs one is the drift: a
new endpoint goes into ``site`` next month, nobody thinks about attribution
while writing a query, and a sheet then carries data from a publisher the
info box has never heard of. So the test below reads the URLs out of the
package and refuses any host that has not been placed against a source --
which makes adding an endpoint a decision about credit rather than an
omission.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from sun_study.site.sources import SOURCES, Source, credit_line, needing_a_key

SITE = Path(__file__).resolve().parents[2] / "src" / "sun_study" / "site"

#: Every host the package fetches from, and the source that answers for it.
#: The value is a fragment of the source's ``name``, so a renamed source
#: fails here rather than quietly leaving a host uncredited.
ANSWERED_BY: dict[str, str] = {
    "portal.spatial.nsw.gov.au": "NSW Spatial Services",
    "maps.six.nsw.gov.au": "SIX Maps",
    "mapprod3.environment.nsw.gov.au": "ePlanning",
    "overpass-api.de": "OpenStreetMap",
    "lz4.overpass-api.de": "OpenStreetMap",
    "z.overpass-api.de": "OpenStreetMap",
    "overpass.kumi.systems": "OpenStreetMap",
    "overpass.private.coffee": "OpenStreetMap",
    "overpass.osm.jp": "OpenStreetMap",
    "valhalla1.openstreetmap.de": "Valhalla",
    "api.transport.nsw.gov.au": "Transport for NSW",
    # Esri's shared ArcGIS Online host, where the City of Sydney publishes its
    # contours and its trees. Another publisher's layer on the same host
    # would pass this test uncredited, so a new service here is worth a look
    # at its organisation id in the path, not just its host.
    "services1.arcgis.com": "City of Sydney",
}

#: Hosts that appear in the package and are not where any data comes from.
#: One entry, and it is the contact address in the User-Agent header -- which
#: the Overpass mirrors ask for and which credits nobody.
NOT_A_SOURCE = {"github.com"}


def _hosts_fetched() -> set[str]:
    """Every host named in an ``https://`` literal under ``site``."""
    found: set[str] = set()
    for path in sorted(SITE.glob("*.py")):
        if path.name == "sources.py":
            continue  # the terms links, which are not what is fetched
        for url in re.findall(r"https://[^\s\"']+", path.read_text(encoding="utf-8")):
            host = urlsplit(url).hostname
            if host:
                found.add(host)
    return found


def test_every_endpoint_the_package_fetches_from_is_credited() -> None:
    """The test this module exists for.

    A new host in ``site`` and no entry here is a fetch nobody has decided
    the attribution for. The fix is one line in ``sources`` and one here --
    or, if it really credits nobody, an entry in ``NOT_A_SOURCE`` saying so.
    """
    unplaced = _hosts_fetched() - set(ANSWERED_BY) - NOT_A_SOURCE
    assert not unplaced, (
        "these hosts are fetched from and no source answers for them: "
        + ", ".join(sorted(unplaced))
    )


@pytest.mark.parametrize(("host", "names"), sorted(ANSWERED_BY.items()))
def test_the_source_that_answers_for_a_host_is_still_called_that(host: str, names: str) -> None:
    assert any(names in source.name for source in SOURCES), (
        f"nothing in SOURCES is named for {names!r}, which {host} was placed against"
    )


@pytest.mark.parametrize("source", SOURCES, ids=lambda source: source.name)
def test_every_source_says_who_what_and_on_what_terms(source: Source) -> None:
    """The four fields a credit cannot be written without."""
    assert source.publisher
    assert source.provides
    assert source.licence
    assert source.credit
    assert source.terms.startswith("https://"), "the terms link is the authority; it must be one"


def test_the_credit_line_says_each_publisher_once() -> None:
    """Spatial Services answers for the cadastre, the contours and the
    aerial. A sheet that credited it three times would read as a mistake."""
    line = credit_line()
    assert line.count("Spatial Services") == 1
    assert "OpenStreetMap contributors" in line
    assert "Transport for NSW" in line
    assert line.endswith(".")


def test_the_credit_line_carries_the_wording_the_publishers_ask_for() -> None:
    """Not a paraphrase. Both of these are the publisher's own form, and
    neither is what anybody would write from memory."""
    line = credit_line()
    assert "© State of New South Wales (Spatial Services" in line
    assert "Department of Planning, Housing and Infrastructure" in line


def test_the_one_source_needing_a_key_is_the_one_that_needs_a_key() -> None:
    """And it names the variable, because that is the whole of the fix."""
    keyed = needing_a_key()
    assert [source.name for source in keyed] == ["Transport for NSW Open Data Hub"]
    assert keyed[0].key_var == "TFNSW_API_KEY"


def test_the_city_of_sydney_is_credited_in_its_own_words_and_the_licence_it_asks_for() -> None:
    """The one council here, and the only credit that names its licence: the
    council states none, and CC BY asks for the licence to be named."""
    line = credit_line()
    assert "© City of Sydney, CC BY 4.0" in line
    council = next(source for source in SOURCES if source.slug == "cityofsydney")
    assert "boundary" in council.note, "a council's register stops at its boundary"


def test_the_share_alike_one_says_so() -> None:
    """ODbL is the only licence here with an obligation beyond the credit,
    and the note is where a person meets it before publishing the data."""
    osm = next(source for source in SOURCES if "OpenStreetMap" in source.name)
    assert "share-alike" in osm.note
