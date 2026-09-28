"""When this build stops working, and how it says so.

Sun Study goes out to offices as a packaged executable, and this is the term
on that build. Past the date below it refuses to run and asks whoever has it
to come back for a current one.

Why a build expires at all
--------------------------
It is a PROTOTYPE, and it says so on every sheet it draws. The disclaimer is
the honest version of that while somebody is reading it; this is the version
that still works in two years, when the executable has been copied to a
network drive, the person who was told what it is has moved on, and it is
producing ADG figures for a DA nobody here has seen. An unmaintained tool
that quietly keeps answering is worse than one that stops.

What is deliberately not here
-----------------------------
Nothing counts down. There is no banner, no nag, no line in ``--help``, and
nothing in the window while the build is inside its term -- the tool behaves
exactly as though this module did not exist. That is the point: the term is
not the subject of the software, and a warning every run would be noise on a
tool somebody uses twice a week for a year.

What *is* here is the message it gives when it fires, and it names the reason.
Refusing to run is a decision this tool is entitled to make; refusing to run
while pretending to be broken is not. The person it stops is an architect on a
deadline, and the difference between "the licence ran out on 1 January 2027"
and an inscrutable failure is a phone call versus a day lost to a bug hunt.

How much protection this is
---------------------------
A speed bump. It reads the system clock, so winding the clock back defeats it,
and a PyInstaller bundle can be unpacked by anyone who wants to. It is here to
stop a stale build being used by accident, which is the thing that actually
happens. It is not a copy protection scheme and should not be sold as one.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from sun_study import AUTHOR, PRODUCT, __version__

__all__ = [
    "EXPIRES",
    "SUMMARY",
    "LicenceExpiredError",
    "check",
    "credential",
    "file",
    "full_text",
    "has_expired",
]

#: The last day this build runs. Chosen as a term, not a countdown -- see the
#: module docstring for why a prototype gets one at all.
EXPIRES = dt.date(2027, 1, 1)


class LicenceExpiredError(Exception):
    """Raised at the entry point when the build is past its term.

    Its own type, and not an ``ArchicadError`` or a ``typer.Exit``, because
    the two entry points report it differently -- the command line to stderr,
    the window in a dialog box, neither having a console the other can use.
    """


def has_expired(today: dt.date | None = None) -> bool:
    """Whether this build is past its term.

    ``today`` is injectable so the behaviour either side of the date can be
    tested without touching the machine's clock.
    """
    return (today or dt.date.today()) >= EXPIRES


def check(today: dt.date | None = None) -> None:
    """Let the run proceed, or raise ``LicenceExpiredError``. Silent while valid."""
    if has_expired(today):
        raise LicenceExpiredError(explain())


def credential() -> str:
    """The one line the window carries at its foot: whose build this is,
    which one, and until when. Not a warning, so it is not set in red; the
    prototype disclaimer stays on every sheet, where the figures are."""
    return f"{PRODUCT} {__version__} · {AUTHOR} · licensed until {EXPIRES.day} {EXPIRES:%B %Y}"


def explain() -> str:
    """What the person holding an expired build is told.

    Names the date and who to ask, and nothing else. There is no fault to
    report and no setting to change, so anything further would only read as an
    error to be worked around.
    """
    return (
        f"{PRODUCT}'s licence period ended on {EXPIRES:%d %B %Y} and this "
        f"build no longer runs. Nothing is wrong with the model or the "
        f"project -- the build itself has reached the end of its term. "
        f"Contact {AUTHOR} for a current one."
    )


# -- the terms themselves ----------------------------------------------------
#
# The other half of the word, and the reason it is here rather than in a
# module of its own: what this build is, and what somebody holding it may do
# with it, are the same question asked before and after the date above.
#
# Nothing below mentions the term, and nothing may. The silence the docstring
# describes is a property of the *window*, not only of ``--help``: an info box
# that named a date would be the countdown this module refuses to give, put
# somewhere a colleague trips over it a year early. ``test_licence`` pins it.

#: The licence in the short form the info box shows, clause for clause with
#: the LICENSE file, which is the authority and says so. Written as separate
#: lines because they are read as a list and not as a paragraph: a person
#: opening this wants to know whether they may pass the executable to a
#: consultant, and that is one line, not a page of prose.
SUMMARY: tuple[str, ...] = (
    "Source-available, not open source. Anyone may read the source; every "
    "right not granted below is reserved.",
    "Fuse Architects and its employees and contractors may install it, run it "
    "on the firm's own client projects, and modify the source for that "
    "internal use, at no charge.",
    "Passing it outside the firm needs written permission -- as does selling "
    "it, sublicensing it, hosting it as a service, or using it to provide a "
    "paid service to third parties.",
    "The authorship and copyright statements it shows, and the ones it writes "
    "onto the drawings it makes, may not be removed.",
    "Versions published before 25 August 2026 were MIT and stay MIT. This "
    "licence governs this one.",
    "No warranty of any kind. In particular it computes figures that bear on "
    "planning compliance, is not validated for submission, and its author "
    "accepts no liability for any use of its output in a development "
    "application.",
)


def file() -> Path | None:
    """The LICENSE file itself, wherever this is running from, or ``None``.

    Two places, for the same two ways the program runs that ``app.icons``
    handles: PyInstaller unpacks what it was given beside ``sys._MEIPASS``,
    and a checkout keeps it at the top of the repository, two levels up from
    this module. ``None`` when it is neither, because a build whose licence
    file did not make it in is still a build that should run -- the summary
    above is in the executable and does not depend on it.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    root = Path(bundled) if bundled is not None else Path(__file__).resolve().parents[2]
    found = root / "LICENSE"
    return found if found.is_file() else None


def full_text() -> str | None:
    """The whole licence as written, or ``None`` where the file is not there."""
    found = file()
    if found is None:
        return None
    try:
        return found.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - unreadable file on a locked profile
        return None
