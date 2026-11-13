"""Scenarios as Archicad keeps them: renovation filters in 26, Design Options from 27.

An office compares massing options -- an envelope under the LEP, one of
twelve storeys -- against the proposal. In Archicad 26 the way to keep them is
a renovation filter per option, each massing shown only under its own filter;
Archicad 27 brought Design Options, where each option is a design option and
a *combination* says which options a view shows. Loriini asks which Archicad
it is talking to (``ArchicadConnection.archicad_version``) and offers the one
that version has.

Two things are done with a scenario:

* **a view is pinned to it**, so a 3D Document shows that option: a renovation
  filter through Tapir's ``SetViewSettings``, a combination through the
  add-on's ``SetViewDesignOptions`` (Archicad 27 on);
* **the Yield counts only its slabs**: under a renovation filter by showing
  the filter on the floor plan and keeping what it shows; under a combination
  by leaving out the slabs of every design option the combination does not
  have on. Archicad 29 is the first whose API says which elements belong to
  which option, so the second needs 29.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sun_study.archicad.connection import ArchicadConnection, ArchicadError

#: The first Archicad with Design Options.
DESIGN_OPTIONS_FROM = 27

#: The first whose API says which elements a design option holds.
ELEMENTS_OF_OPTIONS_FROM = 29

_GUID = re.compile(r"^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")


def uses_design_options(version: int | None) -> bool:
    """Whether a project in this Archicad keeps its options as Design Options.

    ``None`` -- a version that would not be read -- is taken as 26's way,
    which is what an older Archicad that cannot say its version has.
    """
    return version is not None and version >= DESIGN_OPTIONS_FROM


def _spelt(name: str) -> str:
    return " ".join(name.split()).casefold()


@dataclass(frozen=True)
class Combination:
    """One Design Option Combination, as Tapir lists it."""

    name: str
    guid: str
    active: tuple[str, ...] | None = None
    """The guids of the design options it has on; ``None`` before Archicad
    29, which does not say."""


def combinations(connection: ArchicadConnection) -> list[Combination]:
    """The project's Design Option Combinations, in Archicad's order.

    Empty before Archicad 27, which has none, and on a project with none.
    """
    try:
        answer = connection.run_tapir("GetDesignOptionCombinations", {})
    except ArchicadError:
        return []
    found: list[Combination] = []
    for entry in (answer or {}).get("designOptionCombinations") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        guid = str((entry.get("designOptionCombinationId") or {}).get("guid", ""))
        if not name or not guid:
            continue
        listed = entry.get("activeDesignOptions")
        active = (
            tuple(
                str((one.get("designOptionId") or {}).get("guid", ""))
                for one in listed
                if isinstance(one, dict)
            )
            if isinstance(listed, list)
            else None
        )
        found.append(Combination(name=name, guid=guid, active=active))
    return found


def combination_named(
    given: str, listed: Sequence[Combination], *, what: str = "The Yield"
) -> Combination:
    """The combination ``given`` names, by its name or its guid."""
    for one in listed:
        if one.guid.casefold() == given.strip().casefold() or _spelt(one.name) == _spelt(given):
            return one
    raise ArchicadError(
        f"{what} is to be seen under the Design Option Combination {given!r}, and the "
        f"project has none of that name. It has: "
        f"{', '.join(one.name for one in listed) or 'none'}."
    )


def require_design_options(connection: ArchicadConnection, what: str) -> None:
    """Refuse, saying why, on an Archicad before Design Options."""
    version = connection.archicad_version
    if not uses_design_options(version):
        raise ArchicadError(
            f"{what} is to be seen under a Design Option Combination, and this is "
            + (f"Archicad {version}" if version else "an Archicad")
            + " with no Design Options: they came in Archicad 27. Before it, keep the "
            "options as renovation filters and choose one of those."
        )


def combination_guids(connection: ArchicadConnection, wanted: Mapping[str, str]) -> dict[str, str]:
    """Each legend row's combination as its guid, given by name or guid."""
    if not wanted:
        return {}
    require_design_options(connection, "A shadow row")
    listed = combinations(connection)
    return {
        label: combination_named(value, listed, what=label).guid for label, value in wanted.items()
    }


def pin_views(
    connection: ArchicadConnection, navigator_ids: Iterable[str], combination: str | None
) -> int:
    """Pin saved views to a combination, by guid; ``None`` to the Main Model
    alone. Returns how many views were set."""
    views = [{"guid": guid} for guid in navigator_ids if guid]
    if not views:
        return 0
    asked: dict[str, Any] = {"navigatorItemIds": views}
    if combination:
        asked["combination"] = combination
    try:
        answer = connection.run_loriini("SetViewDesignOptions", asked)
    except ArchicadError as error:
        raise ArchicadError(
            f"Archicad would not pin the views to the Design Option Combination "
            f"{combination!r}: {error}. An add-on built before Design Options cannot; "
            f"install the current one."
        ) from error
    return int((answer or {}).get("views", len(views))) if isinstance(answer, dict) else len(views)


# -- the Yield ---------------------------------------------------------------


@dataclass(frozen=True)
class RenovationFilters:
    """The project's renovation filters, and the one the floor plan shows."""

    listed: tuple[tuple[str, str], ...]
    """``(name, guid)`` in the Renovation palette's order."""
    actual: str | None


def renovation_filters(connection: ArchicadConnection) -> RenovationFilters:
    try:
        answer = connection.run_loriini("GetRenovationFilters", {})
    except ArchicadError as error:
        raise ArchicadError(
            f"This add-on cannot list the project's renovation filters ({error}). "
            "Install the current add-on."
        ) from error
    listed = tuple(
        (str(one.get("name", "")), str(one.get("guid", "")))
        for one in (answer or {}).get("renovationFilters") or []
        if isinstance(one, dict) and one.get("guid")
    )
    actual = (answer or {}).get("actual") if isinstance(answer, dict) else None
    return RenovationFilters(listed=listed, actual=str(actual) if actual else None)


def renovation_filter_guid(given: str, filters: RenovationFilters) -> str:
    """The filter ``given`` names, by its name or its guid, as its guid."""
    for name, guid in filters.listed:
        if guid.casefold() == given.strip().casefold() or _spelt(name) == _spelt(given):
            return guid
    if _GUID.match(given.strip()):
        return given.strip()
    raise ArchicadError(
        f"The Yield is to count what the renovation filter {given!r} shows, and the "
        f"project has none of that name. It has: "
        f"{', '.join(name for name, _ in filters.listed) or 'none'}."
    )


def show_renovation_filter(connection: ArchicadConnection, guid: str) -> str:
    """Show a renovation filter on the floor plan. Returns its name."""
    try:
        answer = connection.run_loriini("SetRenovationFilter", {"guid": guid})
    except ArchicadError as error:
        raise ArchicadError(
            f"Archicad would not show the renovation filter: {error}. An add-on built "
            "before the Yield could choose one cannot; install the current one."
        ) from error
    return str((answer or {}).get("name", "")) if isinstance(answer, dict) else ""


def left_out_by(connection: ArchicadConnection, combination: Combination) -> set[str]:
    """The guids of the elements a combination does not show: every element of
    a design option it does not have on. What is in no option -- the main
    model -- is always shown, and is not in here.

    Archicad 29 on: before it the API cannot say which elements an option
    holds, nor which options a combination has on.
    """
    version = connection.archicad_version or 0
    if version < ELEMENTS_OF_OPTIONS_FROM or combination.active is None:
        raise ArchicadError(
            f"Counting the Yield under a Design Option Combination needs Archicad "
            f"{ELEMENTS_OF_OPTIONS_FROM}: before it Archicad cannot say which slabs "
            f"belong to which design option"
            + (f", and this is Archicad {version}." if version else ".")
            + " Until then, measure each option from layers of its own, a run each."
        )
    answer = connection.run_tapir("GetDesignOptions", {})
    every = {
        str((one.get("designOptionId") or {}).get("guid", "")).upper()
        for one in (answer or {}).get("designOptions") or []
        if isinstance(one, dict)
    }
    on = {guid.upper() for guid in combination.active}
    off = sorted(guid for guid in every - on if guid)
    if not off:
        return set()
    held = connection.run_tapir(
        "GetElementsOfDesignOptions",
        {"designOptions": [{"designOptionId": {"guid": guid}} for guid in off]},
    )
    left: set[str] = set()
    for entry in (held or {}).get("elementsOfDesignOptions") or []:
        if not isinstance(entry, dict):
            continue
        for element in entry.get("elements") or []:
            if isinstance(element, dict):
                guid = str((element.get("elementId") or {}).get("guid", ""))
                if guid:
                    left.add(guid.upper())
    return left
