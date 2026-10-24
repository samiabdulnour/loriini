"""Archicad's clock: the time zone a sun given by date is read in.

Archicad works a sun given by date out from the project location, and the
hour in that date is read in the location's own time zone --
``API_PlaceInfo::timeZoneInMinutes``, the zone set with the latitude and
longitude in Options > Project Preferences > Project Location -- with the
date's daylight-saving flag taking an hour off. Tapir's ``GetGeoLocation``
reports the latitude, the longitude and north and leaves the zone out, so
until D135 the hour was handed over as the wall-clock of ``--timezone`` and
agreed with Archicad only where the project's zone happened to be that
zone's standard offset. On the sample project, which keeps UTC+3 while its
hours were asked for in Asia/Dubai (UTC+4), every shadow plan was drawn an
hour late: the 09:00 document carried the sun of 10:00, measured by reading
the window's sun back after setting the same date (D135).

So the add-on reports the zone (``Loriini.GetPlace``), and the instant is
turned into Archicad's own clock before it is handed over: 09:00 in Dubai
is sent as 08:00 with daylight saving off, and Archicad draws the shadows
of 09:00 Dubai time under a document still named for 09:00. An add-on built
before ``GetPlace`` cannot say what the clock is; the hour then goes over as
it always did, and the run says so, because a quiet guess here is exactly
the hour's error that was found.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sun_study.archicad.connection import (
    ArchicadConnection,
    CommandFailedError,
    TapirUnavailableError,
)

__all__ = ["describe_clock", "read_archicad_clock", "sun_date"]


def read_archicad_clock(connection: ArchicadConnection) -> int | None:
    """The project location's time zone, in minutes east of Greenwich.

    ``None`` when the add-on in this Archicad was built before ``GetPlace``,
    or answers without a zone: the caller then hands the hour over as the
    asked-for wall-clock and says that it did.
    """
    try:
        response = connection.run_loriini("GetPlace")
    except (CommandFailedError, TapirUnavailableError):
        return None
    if not isinstance(response, dict):
        return None
    minutes = response.get("timeZoneInMinutes")
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)):
        return None
    return int(minutes)


def sun_date(when: dt.datetime, clock_minutes: int | None) -> dict[str, Any]:
    """The date the add-on hands Archicad, in Archicad's own clock.

    With the clock known, ``when`` is expressed in that zone and daylight
    saving is left off, so the instant is the one asked for whatever the
    project keeps. Without it, the wall-clock of ``when`` goes over with its
    own daylight-saving flag, which is right wherever the project's zone is
    that wall-clock's standard offset -- the pre-D135 behaviour, kept for an
    add-on that cannot say better.
    """
    if clock_minutes is None:
        local = when
        summer = bool(when.dst())
    else:
        local = when.astimezone(dt.timezone(dt.timedelta(minutes=clock_minutes)))
        summer = False
    return {
        "year": local.year,
        "month": local.month,
        "day": local.day,
        "hour": local.hour,
        "minute": local.minute,
        "second": 0,
        "summerTime": summer,
    }


def _offset_text(delta: dt.timedelta | None) -> str:
    if delta is None:
        return "UTC"
    minutes = round(delta.total_seconds() / 60.0)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def describe_clock(timezone: str, clock_minutes: int | None, when: dt.datetime) -> str:
    """One line for the run's output on whose clock the hours are in.

    ``when`` is one of the instants asked for, used to say what the zone
    asked for is at that date (daylight saving or not) and to give one
    worked example of the hour handed over.
    """
    asked = _offset_text(when.utcoffset())
    if clock_minutes is None:
        return (
            f"  this add-on cannot say which time zone Archicad's clock keeps (built before "
            f"GetPlace), so the hours are handed over as {timezone} wall-clock and Archicad "
            f"reads them in the project location's zone; check one document's sun against "
            f"the altitude printed beside it (D135)"
        )
    archicad = _offset_text(dt.timedelta(minutes=clock_minutes))
    if when.utcoffset() == dt.timedelta(minutes=clock_minutes):
        return (
            f"  Archicad's clock is {archicad}, the project location's time zone, which is "
            f"{timezone}'s at these dates; the hours are handed over as they are"
        )
    sent = sun_date(when, clock_minutes)
    return (
        f"  Archicad's clock is {archicad}, the project location's time zone; the hours asked "
        f"for are {timezone} ({asked}), so each is handed over in Archicad's clock -- "
        f"{when:%H:%M} as {sent['hour']:02d}:{sent['minute']:02d} -- and the shadows are "
        f"those of the hour asked for"
    )
