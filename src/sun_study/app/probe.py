"""What the open project can tell the window, so nobody has to type it.

Every list here is read from Archicad rather than configured. The alternative
is a settings file per project, which goes stale the first time somebody
renames a layer and is then wrong in a way nothing reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sun_study.archicad.connection import (
    ArchicadConnection,
    ArchicadError,
    HttpTransport,
    Instance,
    TapirUnavailableError,
    find_instances,
)
from sun_study.archicad.layers import read_layers
from sun_study.archicad.layout import _walk, master_layouts
from sun_study.archicad.read import read_geo_location
from sun_study.archicad.renovation import renovation_filters
from sun_study.archicad.series import ensure_model_database
from sun_study.archicad.sun_eyes import overrides_in_views

#: Floor area, in square metres, at or above which a zone is a dwelling
#: rather than something a dwelling contains. The ADG's smallest apartment is
#: a 35 m2 studio, so 30 leaves room for a zone drawn to the inside face
#: without admitting a balcony.
DWELLING_AREA_M2 = 30.0

#: And the range a private open space falls in. The ADG's balcony minimums run
#: 4 m2 for a studio to 12 m2 for three bedrooms; the floor keeps a storage
#: cupboard or a riser out, which is neither a dwelling nor somebody's balcony.
OPEN_SPACE_AREA_M2 = 4.0


@dataclass(frozen=True)
class ZoneKind:
    """One name the project's zones go by, on one layer, and how big they are.

    The window offers these instead of asking somebody to type a zone name.
    Which zones are dwellings is not something the layer alone can say: one
    project carries 15 apartments named ``G08``, 20 balconies named ``BY`` and
    the storage cupboards, all Zones, all on ``06 | Zone.Units``. Counting the
    balconies as apartments is silent -- they come out as flats with no living
    room and a third of the building fails -- so the names have to be
    separable, and a list read from the project is the only way somebody can
    separate them without knowing the model.

    Both of Archicad's fields are offered as labels because the IFC export
    puts one in ``Name`` and the other in ``LongName`` and which is which
    varies by translator. The assessment matches either, so a person picking
    from this list is right whichever way round their project has it.
    """

    layer: str
    label: str
    count: int
    area_m2: float
    """The median of that name's zones, which is what says what they are."""
    category: str = ""
    """The Zone Category most of that name's zones carry -- ``Apartment``,
    ``Balcony`` -- in the office's own words. Shown beside the name because a
    name is often a code (``G08``, ``BY``) that means nothing to somebody who
    did not model the project, and the category is what they would say."""

    @property
    def dwelling(self) -> bool:
        return self.area_m2 >= DWELLING_AREA_M2

    @property
    def open_space(self) -> bool:
        return OPEN_SPACE_AREA_M2 <= self.area_m2 < DWELLING_AREA_M2

    def described(self) -> str:
        """For the line under the field and the chooser, so a guess can be
        checked: the name, what the office calls that kind of zone, how many
        and how big."""
        kind = f" — {self.category}" if self.category else ""
        return f"{self.label}{kind} ({self.count} x {self.area_m2:.0f} m2)"


@dataclass(frozen=True)
class ProjectOptions:
    """The choices this project offers, each read from it."""

    project: str = ""
    layers: tuple[str, ...] = ()
    zone_layers: tuple[str, ...] = ()
    """Layers that carry Zones -- the apartment picker's candidates."""

    zone_kinds: tuple[ZoneKind, ...] = ()
    """What those zones are called, and how big they are, per layer."""

    combinations: tuple[str, ...] = ()
    masters: tuple[str, ...] = ()
    subsets: tuple[str, ...] = ()
    """Layout Book subsets, where the sheets can be filed."""

    pen_sets: tuple[str, ...] = ()
    """The project's pen tables, for the sun views to print in the office's."""

    overrides: tuple[str, ...] = ()
    """Graphic override combinations, for the sun views' glazing override.

    Read through the Loriini add-on, since Tapir can pin a view to one by name
    and cannot list them. Empty on an older add-on, and the field then takes a
    typed name as before.
    """

    renovation_filters: tuple[str, ...] = ()
    """The Renovation palette's filters, in its order -- where an office may
    keep its massing scenarios. Read through the Loriini add-on, since Tapir
    pins a view to a filter by GUID and cannot name one; empty on an older
    add-on."""

    storeys: tuple[int, ...] = ()

    storey_indices: tuple[tuple[str, int], ...] = ()
    """Each named storey with its index, bottom to top, so a storey picked by
    name on the window can be sent to a command that takes the index -- the
    shadow fills are placed by index, because that is how Archicad places
    them. Same order and same storeys as ``storey_names``."""

    storey_names: tuple[str, ...] = ()
    """Every storey's name, bottom to top, as Archicad spells it.

    So the window can offer the height band as two storeys rather than a
    figure in metres. Ordered by level and not by index, because that is the
    order a person reads them in on the storey settings dialog; unnamed
    storeys are left out, since a name is what the command line takes.
    """

    top_storey_m: float | None = None
    """Level of the highest storey, in metres above project zero.

    Read so the window can offer a height cut that belongs to *this* building
    instead of a placeholder. ``None`` when the storeys would not read, which
    the window takes as "leave the default alone" rather than as zero -- a cut
    at zero would drop the entire project.
    """

    latitude: float | None = None
    longitude: float | None = None
    """Where the project sits, so the window can work out the sun for itself.

    Read for the sheets panel, which draws each shadow at the bearing and
    length the study will actually use. ``core.solar`` works that out from a
    latitude and an instant, takes milliseconds over it and never touches
    Archicad, so the panel can redraw on every keystroke -- but only once
    somebody has set the project location. ``None`` means nobody has, and the
    panel says so on the sheet rather than drawing a shadow it has guessed.
    """

    north_radians: float = 0.0
    """Which way the project's north points, off the same read."""

    located: bool = False
    """Somebody has set the project location: it is readable and is not one
    of Archicad's city presets. A project that was not has nothing in it for
    a site to line up with, so the site page puts the site on the origin."""

    tapir: str = ""
    """The add-on's version, when it answered."""

    tapir_missing: bool = False
    """Archicad is there and the add-on is not.

    Worth its own flag rather than a line in ``problems``. Nothing in this
    tool works without it -- 116 of its 124 Archicad calls are Tapir commands
    -- so it is not a degraded run, it is no run at all, and the window says
    so instead of offering a Run button that cannot work.
    """

    problems: tuple[str, ...] = field(default_factory=tuple)
    """What could not be read. Shown rather than raised: a project missing one
    list is still worth offering the other five for."""

    @property
    def reachable(self) -> bool:
        return bool(self.project)


def running() -> list[Instance]:
    """Every Archicad on this machine, with the project each has open.

    Listed rather than assumed. Archicad hands each instance its own port, so
    the default is right only for whichever started first, and a colleague
    with two projects open would otherwise measure the wrong building.
    """
    try:
        return list(find_instances())
    except ArchicadError:
        return []


def _zones_by_layer(connection: ArchicadConnection) -> tuple[tuple[str, ...], tuple[ZoneKind, ...]]:
    """Which layers carry Zones, and what those zones are called. One pass.

    Layers by asking the Zones, not by name. ``06 | Zone.Units`` looks obvious
    on this project and the apartments on the next one are on a layer called
    something else entirely, while three layers here are named ``Zone.*`` and
    hold nothing.

    The names come from the same read because the second question is the one
    that decides the answer -- a layer is where the apartments are, a name is
    which of the things on it *are* apartments -- and asking Archicad for
    every zone twice, on a project with 1341 of them, is the sort of thing a
    person notices while waiting for a window to fill in.
    """
    from collections import Counter
    from statistics import median

    from sun_study.archicad.read import layer_names, zone_categories
    from sun_study.archicad.read import zones as read_zones
    from sun_study.archicad.rooms import polygon_area

    names = layer_names(connection)
    # Softly: a category name is a courtesy on the list, and an add-on that
    # cannot say them is no reason to offer no zones at all.
    try:
        category_names = zone_categories(connection)
    except (ArchicadError, KeyError, ValueError, TypeError):
        category_names = {}
    carried: set[str] = set()
    areas: dict[tuple[str, str], list[float]] = {}
    categories: dict[tuple[str, str], Counter[str]] = {}
    for zone in read_zones(connection):
        # Not ``zone.layer_index or -1``: layer index 0 is a real Archicad
        # layer, and every zone on it would silently vanish from the list.
        if zone.layer_index is None:
            continue
        layer = names.get(zone.layer_index)
        if not layer:
            continue
        carried.add(layer)
        area = polygon_area(zone.outline) if zone.outline else 0.0
        category = category_names.get((zone.category_guid or "").upper(), "")
        for label in {zone.name.strip(), zone.number.strip()}:
            if label:
                areas.setdefault((layer, label), []).append(area)
                if category:
                    categories.setdefault((layer, label), Counter())[category] += 1

    kinds = tuple(
        sorted(
            (
                ZoneKind(
                    layer=layer,
                    label=label,
                    count=len(found),
                    area_m2=median(found),
                    category=(
                        categories[(layer, label)].most_common(1)[0][0]
                        if (layer, label) in categories
                        else ""
                    ),
                )
                for (layer, label), found in areas.items()
            ),
            # Biggest first, on each layer: the dwellings are what somebody is
            # looking for, and they are the largest thing a zone layer holds.
            key=lambda kind: (kind.layer, -kind.area_m2, kind.label),
        )
    )
    return tuple(sorted(carried)), kinds


#: How long the window waits on any one of the small reads below.
READING_SECONDS = 60.0


def options(port: int) -> ProjectOptions:
    """Read every list the window offers. Never raises: a project that will
    not answer one question is still worth offering the rest of."""
    problems: list[str] = []

    def attempt(what: str, read):  # type: ignore[no-untyped-def]
        try:
            return read()
        except (ArchicadError, KeyError, ValueError, TypeError) as error:
            problems.append(f"{what}: {error}")
            return None

    try:
        # Its own wait, and a short one. Every read below is a small one, and
        # this runs while somebody watches the window fill in -- it must not
        # inherit the export's half-hour, which would hang the window on an
        # Archicad that is merely busy.
        connection = ArchicadConnection(HttpTransport(port=port, timeout_seconds=READING_SECONDS))
        version = connection.tapir_version
        info = connection.run_tapir("GetProjectInfo", {}) or {}
        project = str(info.get("projectName") or "")
    except TapirUnavailableError:
        # Archicad answered; the add-on did not. A different failure from a
        # port with nothing on it, and a different thing to tell somebody.
        return ProjectOptions(
            tapir_missing=True,
            problems=(
                "Archicad is running but the Loriini add-on is not installed, or "
                "is too old to carry Tapir's commands. The study cannot read or "
                "draw anything without it.",
            ),
        )
    except ArchicadError as error:
        return ProjectOptions(problems=(f"cannot reach Archicad on port {port}: {error}",))

    attempt("current database", lambda: ensure_model_database(connection))

    layers = attempt("layers", lambda: read_layers(connection)) or []
    combinations = attempt(
        "layer combinations",
        lambda: connection.run_tapir("GetAttributesByType", {"attributeType": "LayerCombination"}),
    )
    masters = attempt("master layouts", lambda: master_layouts(connection)) or []
    pens = attempt(
        "pen sets",
        lambda: connection.run_tapir("GetAttributesByType", {"attributeType": "PenTable"}),
    )
    # Not through `attempt`: an add-on older than this command is not a
    # problem with the project, and the field simply stays typed.
    try:
        overrides = connection.run_loriini("GetGraphicOverrideCombinations", {})
    except ArchicadError:
        # An add-on without the command: the names the saved views use, which
        # misses only an override no view has.
        used = attempt("graphic overrides", lambda: overrides_in_views(connection)) or ()
        overrides = {"combinations": [{"name": name} for name in used]}
    # The same: an add-on without the command has no names to offer.
    try:
        filters, _ = renovation_filters(connection)
    except ArchicadError:
        filters = []
    book = attempt(
        "layout book",
        lambda: connection.run_tapir("GetNavigatorItemTree", {"navigatorMapId": "LayoutBook"}),
    )
    zoned = attempt("zones", lambda: _zones_by_layer(connection)) or ((), ())
    zones, kinds = zoned
    storeys = attempt("storeys", lambda: connection.run_tapir("GetStories", {}))
    # One more small read, for the sheets panel. A project whose location has
    # never been set answers with an error rather than a guess, and `attempt`
    # turns that into a line in `problems` -- which is right: the panel can
    # still draw every sheet, it simply cannot put a shadow on one.
    where = attempt("project location", lambda: read_geo_location(connection))

    return ProjectOptions(
        project=project,
        tapir=version,
        latitude=None if where is None else where.latitude_deg,
        longitude=None if where is None else where.longitude_deg,
        north_radians=0.0 if where is None else where.north_radians,
        located=where is not None and not where.looks_like_a_city_preset,
        layers=tuple(sorted(state.name for state in layers if state.name.strip())),
        zone_layers=tuple(zones),
        zone_kinds=tuple(kinds),
        combinations=tuple(
            sorted(
                str(entry.get("name", ""))
                for entry in ((combinations or {}).get("attributes") or [])
                if str(entry.get("name", "")).strip()
            )
        ),
        masters=tuple(item.name for item in masters),
        pen_sets=tuple(
            sorted(
                str(entry.get("name", ""))
                for entry in ((pens or {}).get("attributes") or [])
                if str(entry.get("name", "")).strip()
            )
        ),
        overrides=tuple(
            sorted(
                str(entry.get("name", ""))
                for entry in ((overrides or {}).get("combinations") or [])
                if isinstance(entry, dict) and str(entry.get("name", "")).strip()
            )
        ),
        renovation_filters=tuple(one.name for one in filters if one.name.strip()),
        subsets=tuple(
            sorted(
                {
                    item.name
                    for item in _walk((book or {}).get("navigatorItemTree") or {})
                    if item.kind == "SubSetItem" and item.name.strip()
                }
            )
        ),
        storeys=tuple(
            sorted(
                int(row["index"])
                for row in ((storeys or {}).get("stories") or [])
                if isinstance(row, dict) and isinstance(row.get("index"), int)
            )
        ),
        storey_indices=_storey_indices((storeys or {}).get("stories") or []),
        storey_names=_storey_names((storeys or {}).get("stories") or []),
        top_storey_m=_highest_storey((storeys or {}).get("stories") or []),
        problems=tuple(problems),
    )


def _storey_indices(rows: object) -> tuple[tuple[str, int], ...]:
    """Each named storey and its index, in the order a person reads them:
    lowest first.

    By level rather than by index. The two usually agree, and where they do
    not it is the level that matches the storey settings dialog somebody is
    looking at while they choose.

    A storey with no name is skipped rather than given a made-up one: the
    command line takes a name, and a blank cannot be typed or matched. One
    with no index is skipped too, since the index is what this is for.
    """
    named: list[tuple[float, str, int]] = []
    if not isinstance(rows, list):
        return ()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        level = row.get("level")
        index = row.get("index")
        if name and isinstance(level, (int, float)) and isinstance(index, int):
            named.append((float(level), name, index))
    return tuple((name, index) for _, name, index in sorted(named))


def _storey_names(rows: object) -> tuple[str, ...]:
    """The names alone, in the same order, for the pickers that take one."""
    return tuple(name for name, _index in _storey_indices(rows))


def _highest_storey(rows: object) -> float | None:
    """The level of the topmost storey, in metres, or ``None``.

    ``level`` is what Tapir calls it and what every Archicad this runs against
    has answered with; ``elevation`` is accepted too, because the cost of
    reading a second key is nothing and the cost of a height cut silently
    falling back to a placeholder is a study that measures parked hotlink
    masters.

    ``None`` on anything unreadable, never zero: a project whose storeys will
    not parse should keep the window's own default, and a cut at zero would
    drop the whole building.
    """
    if not isinstance(rows, list):
        return None
    levels = [
        float(value)
        for row in rows
        if isinstance(row, dict)
        for value in (row.get("level", row.get("elevation")),)
        if isinstance(value, int | float)
    ]
    return max(levels) if levels else None
