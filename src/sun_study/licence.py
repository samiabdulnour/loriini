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

Licence keys (roadmap R5)
-------------------------
A build that carries a public key (``licence_public_key``) also asks for a
licence key: the one emailed to the subscriber, pasted in, kept in the user's
folder beside the settings, and checked offline at every start -- whole,
genuine, and not past its last day (``licence_key``, D124). Loriini is sold by
subscription, so every key is time-limited: it runs to the end of the period
paid for, plus a few days' grace, and each renewal brings a new one. A build
without a public key takes no keys and behaves exactly as above, so an office
build and a sold build are the same code with one line different.

The build's own term stays as the floor: a key good until 2028 does not make
a beta build that ends in 2027 run past its end. And the same speed bump
applies -- a key is checked against the system clock, and a key cannot be
revoked once issued, which is accepted for keys that run a year. What a
start without a usable key refuses is the work: the commands that only say
something (``--help``, ``rulesets``, ``info``) and the one that installs a key
stay open, so the refusal can always be acted on.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sun_study import AUTHOR, PRODUCT, __version__, licence_public_key, user_folder
from sun_study.licence_key import KeyExpiredError, KeyRefusedError, LicenceKey, read, tidy

__all__ = [
    "EXPIRES",
    "FREE_COMMANDS",
    "KEY_FILE",
    "NO_KEY",
    "SUMMARY",
    "LicenceError",
    "LicenceExpiredError",
    "LicenceKeyError",
    "Standing",
    "check",
    "credential",
    "file",
    "full_text",
    "has_expired",
    "install",
    "key_path",
    "keys_required",
    "needs_key",
    "public_key",
    "remove",
    "standing",
]

#: The last day this build runs. Chosen as a term, not a countdown -- see the
#: module docstring for why a prototype gets one at all.
EXPIRES = dt.date(2027, 1, 1)


class LicenceError(Exception):
    """Either reason a start is refused. The entry points catch this."""


class LicenceExpiredError(LicenceError):
    """Raised at the entry point when the build is past its term.

    Its own type, and not an ``ArchicadError`` or a ``typer.Exit``, because
    the two entry points report it differently -- the command line to stderr,
    the window in a dialog box, neither having a console the other can use.
    """


class LicenceKeyError(LicenceError):
    """A build that takes licence keys, started without a usable one.

    Apart from the build's own term because the window answers it
    differently: an expired build stops, while a missing key is asked for.
    """


def has_expired(today: dt.date | None = None) -> bool:
    """Whether this build is past its term.

    ``today`` is injectable so the behaviour either side of the date can be
    tested without touching the machine's clock.
    """
    return (today or dt.date.today()) >= EXPIRES


def check(today: dt.date | None = None, *, key_needed: bool = True) -> None:
    """Let the run proceed, or raise. Silent while valid.

    ``LicenceExpiredError`` past the build's own term, whatever key is held;
    then, with ``key_needed`` and a build that takes keys, ``LicenceKeyError``
    when this machine holds no key it can use. The window passes False and
    asks for a key itself, rather than refusing to open.
    """
    if has_expired(today):
        raise LicenceExpiredError(explain())
    if key_needed:
        found = standing(today)
        if not found.usable:
            raise LicenceKeyError(f"{found.problem} {HOW_TO_INSTALL}")


def credential(today: dt.date | None = None) -> str:
    """The one line the window carries at its foot: whose build this is,
    which one, and until when. Not a warning, so it is not set in red; the
    prototype disclaimer stays on every sheet, where the figures are.

    With a licence key, whose licence it is instead of whose build, and the
    earlier of the key's last day and the build's own end.
    """
    found = standing(today)
    if found.key is not None and found.usable:
        until = min(found.key.expires, EXPIRES)
        holder = found.key.holder or found.key.email
        return f"{PRODUCT} {__version__} · licensed to {holder} until {until.day} {until:%B %Y}"
    return f"{PRODUCT} {__version__} · {AUTHOR} · licensed until {EXPIRES.day} {EXPIRES:%B %Y}"


# -- licence keys (roadmap R5) -----------------------------------------------

#: The file the key is kept in, in the user's own folder.
KEY_FILE = "licence.key"

#: The commands a start without a usable key still runs: the ones that only
#: say something, and the one that installs a key. Everything else touches a
#: project, and is the work a licence is for.
FREE_COMMANDS = frozenset({"licence", "rulesets", "info"})

#: What a start with no key at all says, before how to give it one.
NO_KEY = "Loriini needs a licence key, and none is installed."

#: What every refusal for want of a key ends with: how to give it one.
HOW_TO_INSTALL = (
    "Keys come by email with the subscription, a new one each time it renews. "
    "Loriini's window asks for the key when it opens; on a command line, run "
    f"Loriini.exe licence followed by the key. {AUTHOR} can send it again."
)


def public_key() -> bytes | None:
    """The public key this build checks licence keys against, if it takes any."""
    written = licence_public_key.PUBLIC_KEY
    return bytes.fromhex(written) if written else None


def keys_required() -> bool:
    """Whether this build asks for a licence key at all."""
    return public_key() is not None


def key_path() -> Path:
    """Where this user's licence key is kept."""
    return user_folder() / KEY_FILE


@dataclass(frozen=True)
class Standing:
    """This machine's licence, as a start sees it."""

    required: bool
    """Whether this build takes keys at all."""
    key: LicenceKey | None = None
    """The key held, when it is whole and genuine, whether or not in force."""
    problem: str = ""
    """Why it cannot be used, in a sentence. Empty when it can."""

    @property
    def usable(self) -> bool:
        return not self.required or (self.key is not None and not self.problem)

    def describe(self) -> str:
        if not self.required:
            return "This build takes no licence keys."
        if self.key is not None and not self.problem:
            return f"Licensed: {self.key.describe()}."
        return self.problem


def _expired(key: LicenceKey) -> KeyExpiredError:
    return KeyExpiredError(
        f"The licence key for {key.whose} ended on {key.expires.day} {key.expires:%B %Y}. "
        f"Renewing the subscription brings a new key by email."
    )


def standing(today: dt.date | None = None) -> Standing:
    """What key this machine holds, and whether a start can use it."""
    public = public_key()
    if public is None:
        return Standing(required=False)
    try:
        text = key_path().read_text(encoding="utf-8")
    except OSError:
        return Standing(required=True, problem=NO_KEY)
    try:
        key = read(text, public)
    except KeyRefusedError as problem:
        return Standing(
            required=True, problem=f"The licence key installed cannot be used. {problem}"
        )
    if not key.good_on(today or dt.date.today()):
        return Standing(required=True, key=key, problem=str(_expired(key)))
    return Standing(required=True, key=key)


def install(text: str, today: dt.date | None = None) -> LicenceKey:
    """Check a pasted key and keep it, or raise ``KeyRefusedError`` and keep nothing.

    Only a key that would let Loriini start is kept: whole, genuine and in
    force. A key refused leaves whatever was installed before where it was.
    """
    public = public_key()
    if public is None:
        raise KeyRefusedError("This build takes no licence keys, so there is nothing to install.")
    key = read(text, public)
    if not key.good_on(today or dt.date.today()):
        raise _expired(key)
    where = key_path()
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(tidy(text) + "\n", encoding="utf-8")
    return key


def remove() -> bool:
    """Forget the key this machine holds. False when there was none."""
    try:
        key_path().unlink()
    except FileNotFoundError:
        return False
    return True


def needs_key(argv: Sequence[str]) -> bool:
    """Whether the command line in ``argv`` needs a usable licence key.

    The command is the first word that is not an option. None at all --
    ``--help`` on its own -- needs nothing.
    """
    command = next((word for word in argv if not word.startswith("-")), None)
    return command is not None and command not in FREE_COMMANDS


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
