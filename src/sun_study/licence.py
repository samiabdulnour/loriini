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

The build's own term stays as the floor for those keys: a key good until 2028
does not make a beta build that ends in 2027 run past its end. And the same
speed bump applies -- a key is checked against the system clock, and a key
cannot be revoked once issued, which is accepted for keys that run a year.
What a start without a usable key refuses is the work: the commands that only
say something (``--help``, ``rulesets``, ``info``) and the one that installs a
key stay open, so the refusal can always be acted on.

Online keys and leases (R5's second half, D125)
-----------------------------------------------
An online key is pasted once and kept for as long as the subscription lasts.
What keeps it in force is a *lease* from the licence service
(``licence_lease``): fetched when the key is installed, renewed once a day in
the background while Loriini is used, and good for a fortnight without
contact, so a day offline changes nothing and a monthly subscription renews
without anyone pasting anything. A start waits on the network only when no
lease is in force -- the first time, or after a fortnight offline -- and then
for a few seconds at most. The service's refusal is a lease too, signed, so a
withdrawn licence, a lapsed subscription or a recalled version stops at the
next contact with the reason in a sentence.

The build's term does not apply to an online key: the service stands in for
it, and does it better. It can stop one version found to be wrong on the day
that is found (a *recall*), where the term stops every version on a fixed
date, paying subscribers included. It stays for builds that take no keys and
for offline keys, where nothing else can.
"""

from __future__ import annotations

import datetime as dt
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from sun_study import (
    AUTHOR,
    PRODUCT,
    SUPPORT_EMAIL,
    __version__,
    licence_online,
    licence_public_key,
    user_folder,
)
from sun_study.licence_key import KeyExpiredError, KeyRefusedError, LicenceKey, read, tidy
from sun_study.licence_lease import Lease, LeaseRefusedError, Reason
from sun_study.licence_lease import read as read_lease

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
    "describe_lease",
    "file",
    "full_text",
    "has_expired",
    "install",
    "key_path",
    "keys_required",
    "licensee",
    "needs_key",
    "public_key",
    "refresh",
    "remove",
    "renew",
    "renewal_finished",
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

    ``LicenceExpiredError`` past the build's own term, where the term applies
    (not to an online key); then, with ``key_needed`` and a build that takes
    keys, ``LicenceKeyError`` when this machine holds no key it can use. An
    online key's lease is renewed on the way: now when none is in force, in
    the background when the one held was fetched on an earlier day. The window
    passes False and asks for a key itself, rather than refusing to open.
    """
    found = standing(today)
    if _term_applies(found) and has_expired(today):
        raise LicenceExpiredError(explain())
    if key_needed:
        found = refresh(found, today)
        if not found.usable:
            raise LicenceKeyError(refusal(found))


def refusal(found: Standing) -> str:
    """What a start refused for want of a usable licence says: the problem, and
    how to install a key where a key is what is missing."""
    if found.online:
        return found.problem
    return f"{found.problem} {HOW_TO_INSTALL}"


def _term_applies(found: Standing) -> bool:
    """The build's term binds a build that takes no keys and an offline key --
    and not a keyed build before it holds a key, which is asked for first."""
    return not found.required or (found.key is not None and not found.key.online)


def credential(today: dt.date | None = None) -> str:
    """The one line the window carries at its foot: whose build this is,
    which one, and until when. Not a warning, so it is not set in red; the
    prototype disclaimer stays on every sheet, where the figures are.

    With a licence key, whose licence it is instead of whose build: with an
    offline key, until the earlier of its last day and the build's own end; a
    trial, until the trial's end; an online key, no date, since it renews.
    """
    found = standing(today)
    if found.key is not None and found.usable:
        holder = found.key.holder or found.key.email
        if found.key.trial:
            ends = _day(found.key.expires)
            return f"{PRODUCT} {__version__} · trial licence for {holder} until {ends}"
        if found.key.online:
            noted = " · a licence notice in ⓘ" if found.lease and found.lease.notice else ""
            return f"{PRODUCT} {__version__} · licensed to {holder}{noted}"
        until = min(found.key.expires, EXPIRES)
        return f"{PRODUCT} {__version__} · licensed to {holder} until {_day(until)}"
    return f"{PRODUCT} {__version__} · {AUTHOR} · licensed until {_day(EXPIRES)}"


def _day(when: dt.date) -> str:
    return f"{when.day} {when:%B %Y}"


def licensee() -> str:
    """Whose licence a run is made under, as its results record it: ``licence
    0042, Fuse Architects``, ``trial licence 0042, ...`` -- or nothing, in a
    build that takes no keys (D125)."""
    found = standing()
    if found.key is None or not found.usable:
        return ""
    holder = found.key.holder or found.key.email
    trial = "trial " if found.key.trial else ""
    return f"{trial}licence {found.key.number}, {holder}"


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
    "Keys come by email with the subscription. Loriini's window asks for the key "
    "when it opens; on a command line, run Loriini.exe licence followed by the "
    f"key. {SUPPORT_EMAIL} can send it again."
)

#: An online key held, and no lease yet: what a start says before it asks.
NOT_YET_CHECKED = (
    "Loriini checks this licence with the licence service, and has not been able to yet."
)

#: An online key in a build that does not know where the service is.
NO_SERVICE = (
    "This key is checked online, and this build of Loriini does not know where the "
    "licence service is. Install the current build."
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
    lease: Lease | None = None
    """For an online key: the lease held for this computer -- a grant, or the
    service's refusal -- once it is believed."""
    fetched: dt.date | None = None
    """This computer's own day when that lease was fetched."""

    @property
    def usable(self) -> bool:
        return not self.required or (self.key is not None and not self.problem)

    @property
    def online(self) -> bool:
        return self.key is not None and self.key.online

    def due(self, today: dt.date) -> bool:
        """Whether a start should renew the lease, in the background: it is in
        force, and was fetched on an earlier day than ``today``."""
        return self.online and self.usable and (self.fetched is None or self.fetched < today)

    def describe(self) -> str:
        if not self.required:
            return "This build takes no licence keys."
        if self.key is not None and not self.problem:
            said = f"Licensed: {self.key.describe()}."
            if self.lease is not None:
                said = f"{said} {describe_lease(self.lease)}"
            return said
        return self.problem


def describe_lease(lease: Lease) -> str:
    """What a grant says to whoever holds it: paid to when, the seats in use,
    when the service was last asked, and its notice, if it has one."""
    parts = []
    if lease.paid_to is not None:
        parts.append(f"Paid to {_day(lease.paid_to)}")
    seats = "seat" if lease.seats == 1 else "seats"
    parts.append(f"{lease.in_use} of {lease.seats} {seats} in use")
    parts.append(f"checked with the licence service on {_day(lease.given)}")
    said = "; ".join(parts) + "."
    said = said[0].upper() + said[1:]
    return f"{said} {lease.notice}" if lease.notice else said


def _expired(key: LicenceKey) -> KeyExpiredError:
    return KeyExpiredError(
        f"The licence key for {key.whose} ended on {key.expires.day} {key.expires:%B %Y}. "
        f"Renewing the subscription brings a new key by email."
    )


def standing(today: dt.date | None = None) -> Standing:
    """What key this machine holds, and whether a start can use it. Reads the
    key and the lease held; asks nothing of the network."""
    public = public_key()
    if public is None:
        return Standing(required=False)
    day = today or dt.date.today()
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
    if key.online:
        return _online(key, public, day)
    if not key.good_on(day):
        return Standing(required=True, key=key, problem=str(_expired(key)))
    return Standing(required=True, key=key)


def _online(key: LicenceKey, public: bytes, day: dt.date) -> Standing:
    """An online key's standing, from the lease held for it on this computer."""
    if licence_online.service() is None:
        return Standing(required=True, key=key, problem=NO_SERVICE)
    kept = licence_online.kept_lease()
    lease = _believed(kept.text, key, public) if kept is not None else None
    if kept is None or lease is None:
        return Standing(required=True, key=key, problem=NOT_YET_CHECKED)
    held = Standing(required=True, key=key, lease=lease, fetched=kept.fetched)
    if not lease.granted:
        if lease.reason is Reason.RECALLED and lease.build != __version__:
            # Another version was recalled, not this one: ask again.
            return replace(held, lease=None, problem=NOT_YET_CHECKED)
        return replace(held, problem=lease.notice or "The licence service refused this licence.")
    if lease.clock_behind(day):
        return replace(
            held,
            problem=(
                f"This computer's date, {_day(day)}, is earlier than the licence service's, "
                f"{_day(lease.given)}. Set the computer's clock right, then start Loriini again."
            ),
        )
    if not lease.in_force(day):
        return replace(
            held,
            problem=(
                f"Loriini last reached the licence service on {_day(lease.given)}, and its "
                f"lease ran to {_day(lease.until)}. It needs to reach the service again: "
                f"check this computer's internet connection."
            ),
        )
    return held


def _believed(text: str, key: LicenceKey, public: bytes) -> Lease | None:
    """The lease in ``text`` if it is genuine and was given to this key on this
    computer; ``None`` for anything else, which a start treats as no lease."""
    try:
        lease = read_lease(text, public)
    except LeaseRefusedError:
        return None
    if lease.serial != key.serial or lease.machine != licence_online.machine():
        return None
    return lease


# -- asking the licence service ------------------------------------------------------

#: The renewal started in the background, if one was: for the window to wait
#: on before it closes, and for a test to wait on at all.
_renewal: threading.Thread | None = None


def refresh(found: Standing | None = None, today: dt.date | None = None) -> Standing:
    """Renew an online key's lease when a start should, and say where that
    leaves it: at once when no lease is in force, in the background when the
    one held was fetched on an earlier day, and not at all otherwise."""
    found = found if found is not None else standing(today)
    if not found.online or licence_online.service() is None:
        return found
    day = today or dt.date.today()
    if not found.usable:
        return renew(day)
    if found.due(day):
        global _renewal
        _renewal = threading.Thread(
            target=_renew_quietly, args=(day,), name="licence renewal", daemon=True
        )
        _renewal.start()
    return found


def _renew_quietly(day: dt.date) -> None:
    # Nothing a background renewal meets is worth a start's attention: the
    # lease held is in force, and the next start asks again.
    try:
        renew(day)
    except Exception:
        pass


def renewal_finished(timeout: float | None = None) -> bool:
    """Wait up to ``timeout`` seconds for a background renewal. True when none
    is running."""
    running = _renewal
    if running is None:
        return True
    running.join(timeout)
    return not running.is_alive()


def renew(today: dt.date | None = None) -> Standing:
    """Ask the licence service for a lease now, keep what it gives -- a grant,
    or its refusal -- and say where that leaves this computer.

    When the service cannot be asked, or answers with something this build
    cannot believe, nothing is kept and the lease held stands; if it is not in
    force, the reason is added to the problem, so the sentence says both what
    is wrong and why it could not be put right.
    """
    day = today or dt.date.today()
    found = standing(day)
    public = public_key()
    service = licence_online.service()
    if not found.online or public is None or service is None or found.key is None:
        return found
    try:
        text = licence_online.ask_for_lease(
            key_path().read_text(encoding="utf-8").strip(),
            service=service,
            machine=licence_online.machine(),
            name=licence_online.machine_name(),
        )
        lease = _believed(text, found.key, public)
        if lease is None:
            raise licence_online.ServiceError(
                "The licence service's answer was not a lease this build can believe."
            )
    except (licence_online.ServiceError, OSError) as trouble:
        return found if found.usable else replace(found, problem=f"{found.problem} {trouble}")
    licence_online.keep_lease(text, day)
    return standing(day)


def install(text: str, today: dt.date | None = None) -> LicenceKey:
    """Check a pasted key and keep it, or raise ``KeyRefusedError`` and keep nothing.

    Only a key that could let Loriini start is kept: whole, genuine, and --
    for an offline key -- in force. An online key's last day is not its
    business (``licence_key``); whether it is in force is the service's answer,
    asked for next (``renew``). A key refused leaves whatever was installed
    before where it was.
    """
    public = public_key()
    if public is None:
        raise KeyRefusedError("This build takes no licence keys, so there is nothing to install.")
    key = read(text, public)
    if key.online and licence_online.service() is None:
        raise KeyRefusedError(NO_SERVICE)
    if not key.online and not key.good_on(today or dt.date.today()):
        raise _expired(key)
    where = key_path()
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(tidy(text) + "\n", encoding="utf-8")
    kept = licence_online.kept_lease()
    if kept is not None and _believed(kept.text, key, public) is None:
        licence_online.forget_lease()
    return key


def remove() -> str | None:
    """Forget the key this machine holds, and free its seat first when it is an
    online key. What happened, in a sentence; ``None`` when there was no key.

    The seat is freed with the service while the key is still here to prove
    whose it is. When the service cannot be reached the key goes anyway, and
    the sentence says when the seat frees itself instead.
    """
    where = key_path()
    try:
        text = where.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        text = ""
    found = standing()
    said = f"Removed the licence key from {where}."
    service = licence_online.service()
    if found.online and service is not None and text:
        try:
            freed = licence_online.release(text, service=service, machine=licence_online.machine())
        except licence_online.ServiceError:
            freed = False
        if freed:
            said = f"{said} Its seat is free for another computer."
        elif found.lease is not None and found.lease.granted:
            frees = found.lease.until + dt.timedelta(days=1)
            said = (
                f"{said} The licence service could not be told, so its seat frees itself "
                f"on {_day(frees)}."
            )
    licence_online.forget_lease()
    try:
        where.unlink()
    except FileNotFoundError:
        pass
    return said


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
