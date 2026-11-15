"""Issuing licence keys: the vendor's side of roadmap R5.

Nothing in Loriini imports this; ``scripts/licence.py`` does, on the vendor's
own machine, and the tests do. It is in the package rather than beside the
script so that what it does is tested like everything else (D124).

Three jobs
----------
**The key pair**, once. ``new_key_pair`` makes it; the private half goes into
a file of the vendor's choosing -- never this repository, whose history would
keep it for ever -- and the public half into ``licence_public_key.py``, which
is what the next build carries and checks keys against. Lose the private half
and no further key can be issued for the builds in circulation; publish it
and anybody can issue one. It is a file to keep the way a certificate's
private key is kept.

**A key for each paid period.** Loriini is sold by subscription, so a key
is time-limited by design: it runs to the end of the period paid for, plus a
few days' grace, and each renewal brings a new key by email. There is nothing
to revoke -- a subscription that is not renewed simply lapses when its last
key does. ``issue`` signs a ``LicenceKey`` for an order -- who, how many
seats, paid to when -- with the next licence number from the ledger, and the
ledger records it: a CSV beside the private key, so the vendor always knows
what is out there and a lost email can be answered by sending the same key
again.

**The email.** ``email`` writes the message a buyer receives: the key set in
lines that paste back whole, what it covers, and how to install it. It can
be sent over SMTP, or written as an unsent draft (``X-Unsent: 1``) that
Outlook and Windows Mail open ready to send -- which is the way to start,
checking each by eye, before the shop's webhook does it (R7).
"""

from __future__ import annotations

import calendar
import copy
import csv
import datetime as dt
import os
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from sun_study import AUTHOR, PRODUCT, signing
from sun_study.licence_key import LicenceKey, lines, make

__all__ = [
    "GRACE_DAYS",
    "LEDGER_FIELDS",
    "NO_END",
    "PUBLIC_KEY_MODULE",
    "TRIAL_DAYS",
    "Order",
    "draft",
    "email",
    "issue",
    "new_key_pair",
    "next_serial",
    "public_key_module",
    "read_signing_key",
    "record",
    "send",
    "term_end",
]

#: The module a build reads its public key from.
PUBLIC_KEY_MODULE = Path(__file__).resolve().parent / "licence_public_key.py"

#: The first line of a private key file, so it says what it is when opened.
_SIGNING_KEY_HEADER = "# Loriini licence signing key. Private: keep it out of every repository."

#: The ledger's columns, in order.
LEDGER_FIELDS = ("serial", "issued", "expires", "seats", "email", "holder", "key")


# -- the key pair --------------------------------------------------------------------


def new_key_pair(private: Path, *, force: bool = False) -> bytes:
    """Make a key pair, keep the private half in ``private``, return the public.

    Refuses to overwrite a private key that is already there unless
    ``force``: replacing it silently would orphan every key issued with it.
    """
    if private.exists() and not force:
        raise FileExistsError(
            f"{private} already holds a signing key. Every key issued with it is "
            f"checked against its public half; replace it only on purpose (--force)."
        )
    seed = signing.new_seed()
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_text(f"{_SIGNING_KEY_HEADER}\n{seed.hex()}\n", encoding="utf-8")
    if os.name == "posix":
        private.chmod(0o600)
    return signing.public_key(seed)


def read_signing_key(private: Path) -> bytes:
    """The private key in a file ``new_key_pair`` wrote."""
    for line in private.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            seed = bytes.fromhex(line)
            if len(seed) != signing.KEY_BYTES:
                raise ValueError(f"{private} does not hold a signing key")
            return seed
    raise ValueError(f"{private} does not hold a signing key")


def public_key_module(public: bytes | None, service: str | None = None) -> str:
    """``licence_public_key.py``, carrying this public key and this service."""
    return (
        '"""The public half of the key Loriini\'s licence keys are signed with,\n'
        "and where the licence service is.\n"
        "\n"
        "Written by ``scripts/licence.py keygen`` and ``service``: the private half\n"
        "is kept by the vendor, outside this repository. A build carrying a key\n"
        "here asks for a licence key and checks it at every start; with a service\n"
        "as well, it takes the online keys the service keeps in force\n"
        "(docs/licensing.md).\n"
        '"""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "#: 32 bytes of Ed25519 public key, as 64 hex digits, or ``None``.\n"
        f"PUBLIC_KEY: str | None = {_literal(public.hex() if public else None)}\n"
        "\n"
        "#: The licence service's address, ``https://...``, or ``None``.\n"
        f"SERVICE: str | None = {_literal(service)}\n"
    )


def _literal(value: str | None) -> str:
    return "None" if value is None else f'"{value}"'


# -- a key from an order ---------------------------------------------------------------


#: Days a key runs past the end of the period paid for, so that a renewal
#: whose key reaches somebody a day or two late -- a card retried, an email
#: in a junk folder -- does not stop them on a deadline.
GRACE_DAYS = 7


#: The last day of a complimentary online key: no end the service will reach.
NO_END = dt.date(2099, 12, 31)

#: A trial's length, in days, when an order does not say.
TRIAL_DAYS = 14


@dataclass(frozen=True)
class Order:
    """One paid period of a subscription -- or, online, the first of them."""

    email: str
    holder: str = ""
    seats: int = 1
    months: int = 12
    """How long the period is, when ``paid_to`` is not given."""
    starts: dt.date | None = None
    """The first day; today when not given."""
    paid_to: dt.date | None = None
    """The last day paid for, as the shop says it; overrides ``months``."""
    grace_days: int = GRACE_DAYS
    online: bool = False
    """An online key: kept in force by the licence service's leases (D125)."""
    trial: bool = False
    """A trial, online, for ``days`` days."""
    days: int = TRIAL_DAYS
    complimentary: bool = False
    """Online and never lapsing: the first practice's grant (LICENSE clause 1)."""


def term_end(start: dt.date, months: int) -> dt.date:
    """The last day of a term of ``months`` from ``start``: the day before the
    same date that many months on, or the day before the month's end where
    that month is shorter -- 31 January for a month ends on 27 or 28
    February, not in March."""
    if months < 1:
        raise ValueError("a licence runs at least a month")
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day) - dt.timedelta(days=1)


def next_serial(ledger: Path) -> int:
    """One more than the highest licence number the ledger holds, or 1."""
    try:
        with ledger.open(newline="", encoding="utf-8") as opened:
            numbers = [int(row["serial"]) for row in csv.DictReader(opened) if row.get("serial")]
    except FileNotFoundError:
        return 1
    return max(numbers, default=0) + 1


def issue(
    order: Order, seed: bytes, *, serial: int, today: dt.date | None = None
) -> tuple[LicenceKey, str]:
    """The licence and its key, signed with the vendor's private key.

    An offline key's last day is the period's, plus the grace. An online key's
    is the period's alone: the day the licence service starts from, which then
    moves it on as payments arrive (``licence_key``). A trial's is its last
    day; a complimentary key's is ``NO_END``.
    """
    if order.grace_days < 0:
        raise ValueError("the grace cannot be negative")
    online = order.online or order.trial or order.complimentary
    starts = order.starts or today or dt.date.today()
    if order.complimentary:
        last = NO_END
    elif order.trial:
        if order.days < 1:
            raise ValueError("a trial runs at least a day")
        last = starts + dt.timedelta(days=order.days - 1)
    else:
        paid_to = order.paid_to or term_end(starts, order.months)
        last = paid_to if online else paid_to + dt.timedelta(days=order.grace_days)
    licence = LicenceKey(
        serial=serial,
        email=order.email.strip(),
        holder=order.holder.strip(),
        seats=order.seats,
        issued=starts,
        expires=last,
        online=online,
        trial=order.trial,
    )
    return licence, make(licence, seed)


def record(ledger: Path, licence: LicenceKey, text: str) -> None:
    """Add a licence to the ledger, writing its header if the ledger is new."""
    fresh = not ledger.exists()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", newline="", encoding="utf-8") as opened:
        writer = csv.writer(opened)
        if fresh:
            writer.writerow(LEDGER_FIELDS)
        writer.writerow(
            [
                licence.number,
                licence.issued.isoformat(),
                licence.expires.isoformat(),
                licence.seats,
                licence.email,
                licence.holder,
                text,
            ]
        )


# -- the email ------------------------------------------------------------------------


def email(licence: LicenceKey, text: str, *, sender: str) -> EmailMessage:
    """The message the buyer receives: the key, what it covers, how to install it."""
    seats = "one person" if licence.seats == 1 else f"{licence.seats} people"
    greeting = f"Hello {licence.holder}," if licence.holder else "Hello,"
    key = "\n".join(f"    {line}" for line in lines(text))
    until = f"{licence.expires.day} {licence.expires:%B %Y}"
    if licence.trial:
        opening = f"Thank you for trying {PRODUCT}. Your trial licence key is:"
        covers = f"It is licence {licence.number}, for {seats}, and the trial runs until {until}."
        after = (
            "Everything works during the trial; what it makes says it came from a\n"
            "trial. A subscription carries on from it without a new install.\n"
        )
    elif licence.online and licence.expires >= NO_END:
        opening = f"Your {PRODUCT} licence key is:"
        covers = f"It is licence {licence.number}, for {seats}, and it does not lapse."
        after = _ONLINE_AFTER
    elif licence.online:
        opening = f"Thank you for subscribing to {PRODUCT}. Your licence key is:"
        covers = (
            f"It is licence {licence.number}, for {seats}, for as long as the subscription runs."
        )
        after = _ONLINE_AFTER
    else:
        opening = f"Thank you for subscribing to {PRODUCT}. Your licence key is:"
        covers = f"It is licence {licence.number}, for {seats}, and it works until {until}."
        after = (
            "Each time the subscription renews, a new key comes by email before this\n"
            "one runs out; install it the same way, or from the info box (Enter licence\n"
            "key).\n"
        )
    body = (
        f"{greeting}\n"
        "\n"
        f"{opening}\n"
        "\n"
        f"{key}\n"
        "\n"
        f"{covers}\n"
        "\n"
        "To install it, open Loriini. It asks for the key when it opens: paste all\n"
        "of it, from LORIINI to the last group -- the line breaks do not matter --\n"
        "and press Use this key. Each person using Loriini under this licence\n"
        "does the same on their own machine. On a command line instead:\n"
        "\n"
        "    Loriini.exe licence <the key>\n"
        "\n"
        f"{after}"
        "Keep this email: the key is needed again on a new machine.\n"
        "\n"
        f"{AUTHOR}\n"
    )
    message = EmailMessage()
    message["Subject"] = f"Your {PRODUCT} licence key (licence {licence.number})"
    message["From"] = sender
    message["To"] = licence.email
    message.set_content(body)
    return message


#: What an online key's email says about keeping it in force.
_ONLINE_AFTER = (
    "Loriini checks the licence online by itself, once a day while it is used,\n"
    "and works for a fortnight without a connection. Nothing more needs doing\n"
    "when the subscription renews: there is no new key. A computer that stops\n"
    "using Loriini frees its seat after a fortnight, or at once with Log out\n"
    "in Loriini's About box.\n"
)


def draft(message: EmailMessage) -> bytes:
    """The message as an ``.eml`` that Outlook and Windows Mail open as an
    unsent draft, ready to check and send."""
    unsent = copy.deepcopy(message)
    unsent["X-Unsent"] = "1"
    return unsent.as_bytes()


def send(
    message: EmailMessage,
    *,
    host: str,
    port: int = 587,
    user: str | None = None,
    password: str | None = None,
    connect: Callable[..., Any] = smtplib.SMTP,
) -> None:
    """Send over SMTP, upgraded to TLS before any password is sent."""
    with connect(host, port, timeout=60) as server:
        server.starttls()
        if user:
            server.login(user, password or "")
        server.send_message(message)
