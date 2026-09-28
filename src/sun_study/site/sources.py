"""Whose data the site analysis draws, and on what terms.

Every line on a Context or Site Analysis sheet came out of somebody else's
register, and all but one of those registers is published under a licence
that asks for a credit in return. This is the list, written down once, in the
same spirit as ``disclaimer``: the window's info box, the documentation and
anything that ever prints a credit on a sheet read it from here, so the three
cannot come to disagree about who a drawing owes.

Why it is worth a module at all
-------------------------------
A sheet drawn from open data is a *produced work* under most of these
licences, and a produced work carries the credit. Nobody can supply that
credit from memory at four o'clock on the day a DA goes in: the site analysis
touches seven publishers, they are not the same seven every run -- a service
that is down costs the sheet its layer, and with it the reason to credit that
publisher, and a council's register answers only inside the council's area --
and two of them ask for particular wording. So the office needs
one place that says it, and it has to be beside the code that does the
fetching or it goes stale the first time an endpoint moves.

What it is not
--------------
Not legal advice, and not the licence. The ``terms`` link on each entry is the
authority; what is written here is the short form, accurate as at the date of
this file, and a publisher may change its terms without telling a tool that
reads its endpoints. Anything going out of the office on a drawing should be
checked against the link.

Attribution is also not the whole of a licence. ODbL, which OpenStreetMap is
under, asks for a credit on a produced work -- a drawing, a PDF, a render --
and asks for rather more than that of anyone who publishes a derived
*database*. Drawing the neighbourhood on a DA sheet is the first; handing
somebody the fetched JSON is closer to the second. ``note`` says so on the
entries where it matters.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "CITY_OF_SYDNEY",
    "EPLANNING",
    "IMAGERY",
    "OSM",
    "SOURCES",
    "SPATIAL",
    "TFNSW",
    "VALHALLA",
    "Source",
    "credit_line",
    "named",
    "needing_a_key",
]

#: What a bundle calls a source when it says which ones its own contents came
#: from. Short names rather than the publishers' own, because they are written
#: down in ``pipeline`` and read back out of saved runs: a title that gains a
#: department's new name must not orphan last month's bundle.
SPATIAL = "nsw-spatial"
EPLANNING = "nsw-eplanning"
IMAGERY = "nsw-imagery"
CITY_OF_SYDNEY = "cityofsydney"
OSM = "openstreetmap"
VALHALLA = "valhalla"
TFNSW = "tfnsw"


@dataclass(frozen=True)
class Source:
    """One publisher, and what the site analysis takes from them.

    ``credit`` is the wording that goes on a drawing, and is the publisher's
    own where the publisher states one -- Spatial Services and Transport for
    NSW both do, and neither is the form anybody would guess at.
    """

    #: How the rest of the program refers to this source: one of the
    #: constants above, stable across a rename of the service.
    slug: str
    #: What the service is called, as the endpoint and the documentation call
    #: it, so that a line on a sheet can be traced back to a URL in ``site``.
    name: str
    #: Who publishes it. The legal entity where the credit needs one.
    publisher: str
    #: What the sheets get out of it, in the words the window uses for those
    #: layers rather than the register's own field names.
    provides: str
    #: The licence, short form. The ``terms`` link is the authority.
    licence: str
    #: Where that licence is published.
    terms: str
    #: The attribution line for a drawing made from this data.
    credit: str
    #: Anything a person needs beyond the credit: a share-alike obligation, a
    #: fair-use policy, a service that is somebody's goodwill rather than a
    #: product. Empty where there is nothing to add.
    note: str = ""
    #: The environment variable holding this service's key, where it needs
    #: one. Empty for the five that are open.
    key_var: str = ""


#: Every source a site analysis run can touch, in the order the run meets
#: them: the address first, because nothing happens without it, then the
#: registers that answer for the site, then the two shared services that are
#: somebody else's generosity rather than a government product.
SOURCES: tuple[Source, ...] = (
    Source(
        slug=SPATIAL,
        name="NSW Spatial Services (Spatial Collaboration Portal)",
        publisher="Spatial Services, NSW Department of Customer Service",
        provides=(
            "The address register the site is found in, the lot boundaries and "
            "their dimensions, the rail corridor, roads and railways, parks, "
            "schools, hospitals and named complexes, train stations, the 2 m "
            "contours the levels and the terrain are taken from wherever no "
            "council publishes finer ones, the council boundaries that say "
            "where one does, and the neighbours' address points."
        ),
        licence="Creative Commons Attribution 4.0 (CC BY 4.0)",
        terms="https://www.spatial.nsw.gov.au/copyright",
        credit=(
            "© State of New South Wales (Spatial Services, a business unit of "
            "the Department of Customer Service NSW)"
        ),
    ),
    Source(
        slug=EPLANNING,
        name="NSW ePlanning (EPI Primary Planning Layers)",
        publisher="NSW Department of Planning, Housing and Infrastructure",
        provides=(
            "The planning controls: land use zone, height of building, floor "
            "space ratio, minimum lot size and heritage items -- at the site "
            "for the Summary of Controls, and across the neighbourhood for the "
            "height the future context raises each neighbour to."
        ),
        licence="Creative Commons Attribution 4.0 (CC BY 4.0)",
        terms="https://www.planningportal.nsw.gov.au/copyright-and-disclaimer",
        credit="© State of New South Wales and Department of Planning, Housing and Infrastructure",
        note=(
            "The register is the mapped control, not the instrument. The LEP "
            "and the council's DCP are what a consent is read against, and the "
            "DCP is not open data at all -- which is why the future context is "
            "raised to the LEP's height control and not to a DCP's."
        ),
    ),
    Source(
        slug=IMAGERY,
        name="NSW SIX Maps imagery",
        publisher="Spatial Services, NSW Department of Customer Service",
        provides=(
            "The aerial orthophoto, saved beside the run as JPEG tiles with "
            "world files on the MGA grid when the aerial is asked for."
        ),
        licence="Creative Commons Attribution 4.0 (CC BY 4.0)",
        terms="https://www.spatial.nsw.gov.au/copyright",
        credit=(
            "© State of New South Wales (Spatial Services, a business unit of "
            "the Department of Customer Service NSW)"
        ),
        note=(
            "An aerial placed on a sheet is the one layer a reader takes for a "
            "photograph of today. It is not: the imagery is flown on a cycle "
            "and the capture date is the service's, not the run's."
        ),
    ),
    Source(
        slug=CITY_OF_SYDNEY,
        name="City of Sydney Data Hub (terrain contours, trees)",
        publisher="Council of the City of Sydney",
        provides=(
            "Inside the City of Sydney's own area, two registers no statewide "
            "layer matches: the 1 m contours from its 2020 aerial survey, which "
            "the Site Analysis sheet draws and the context model's terrain is "
            "made from in place of the state's 2 m ones, and its tree inventory "
            "-- every street and park tree where it stands, with its height, "
            "canopy spread, trunk diameter and species -- which the site sheet "
            "draws to the size of its canopy."
        ),
        licence="Creative Commons Attribution 4.0 (CC BY 4.0)",
        terms="https://data.cityofsydney.nsw.gov.au/pages/disclaimer",
        credit="© City of Sydney, CC BY 4.0",
        note=(
            "A council's register stops at the council's boundary. A sheet "
            "that reaches past it takes the state's contours instead, and the "
            "trees past it come from OpenStreetMap; the model takes the "
            "council's contours inside the boundary and the state's outside. "
            "The contours are the ground as the 2020 survey found it, "
            "interpolated under buildings, and a canopy is the spread the "
            "council recorded north to south: records, not a survey of the site."
        ),
    ),
    Source(
        slug=OSM,
        name="OpenStreetMap, through the public Overpass mirrors",
        publisher="OpenStreetMap contributors",
        provides=(
            "What no government register carries at this scale: street trees "
            "where no council publishes its own (drawn at a nominal size unless "
            "a mapper recorded one), hydrants, poles and lamps, driveways and "
            "kerbside parking, one-way streets, bus stops and routes, utilities, "
            "and the building footprints the context model stands its "
            "neighbours on."
        ),
        licence="Open Data Commons Open Database Licence 1.0 (ODbL)",
        terms="https://www.openstreetmap.org/copyright",
        credit="© OpenStreetMap contributors",
        note=(
            "ODbL is share-alike. A drawing made from it is a produced work and "
            "needs the credit above and nothing more; publishing the fetched "
            "data itself, or a database derived from it, is the other half of "
            "the licence and should be read before it is done. The Overpass "
            "mirrors are volunteer infrastructure under a fair-use policy -- "
            "which is why answers are cached for a month rather than re-asked."
        ),
    ),
    Source(
        slug=VALHALLA,
        name="Valhalla routing (valhalla1.openstreetmap.de)",
        publisher="FOSSGIS e.V., on OpenStreetMap data",
        provides="The 5 and 10 minute walking catchments on the Context Analysis sheet.",
        licence="Routing engine: MIT. Underlying data: ODbL, as OpenStreetMap above.",
        terms="https://valhalla.openstreetmap.de/",
        credit="Walking catchments: Valhalla (FOSSGIS e.V.)",
        note=(
            "A public demo server run on somebody else's goodwill, under the "
            "same fair-use expectation as the OSRM and Nominatim demos. One "
            "request per run, and a catchment that does not come back costs "
            "the sheet its catchment and nothing else."
        ),
    ),
    Source(
        slug=TFNSW,
        name="Transport for NSW Open Data Hub",
        publisher="Transport for NSW",
        provides=(
            "Bus stops, from the authoritative register rather than from "
            "OpenStreetMap. Without a key the OSM stops that came with the "
            "route query stand in, and the sheet says so."
        ),
        licence="Creative Commons Attribution 4.0 (CC BY 4.0)",
        terms="https://opendata.transport.nsw.gov.au/datalicence",
        credit="© Transport for NSW",
        note=(
            "The one source here that needs a key. It is free, from "
            "opendata.transport.nsw.gov.au, and is read out of the "
            "environment -- it is never written into a project or a run folder."
        ),
        key_var="TFNSW_API_KEY",
    ),
)


def named(slugs: Iterable[str]) -> tuple[Source, ...]:
    """The sources those slugs name, in this list's order.

    The list's order and not the caller's, so two sheets that used the same
    registers in a different sequence still credit them the same way round --
    and a slug nothing answers to is dropped rather than raising, because a
    saved bundle from an older run may name a source that has since gone.
    """
    wanted = set(slugs)
    return tuple(source for source in SOURCES if source.slug in wanted)


def credit_line(sources: Iterable[Source] | None = None) -> str:
    """The line that goes on a drawing, with each credit said once.

    De-duplicated rather than listed per service: Spatial Services answers for
    the cadastre, the contours and the aerial, and a sheet that credited it
    three times would read as a mistake.

    ``sources`` is what a particular sheet was drawn from -- see the bundles'
    ``sources_used`` -- and the default is all of them, which is what the info
    box shows, because that box is about the tool rather than about one run.
    Crediting a publisher whose service was down that morning is not a
    courtesy, it is a claim about where a line came from, so the sheets pass
    their own.
    """
    seen: list[str] = []
    for source in SOURCES if sources is None else sources:
        if source.credit not in seen:
            seen.append(source.credit)
    if not seen:  # pragma: no cover - a sheet with nothing on it
        return ""
    return "Site and context data: " + "; ".join(seen) + "."


def needing_a_key() -> tuple[Source, ...]:
    """The sources that answer nothing without a key in the environment."""
    return tuple(source for source in SOURCES if source.key_var)
