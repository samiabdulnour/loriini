"""A lease: the licence service's word that a licence is in force on one computer.

Roadmap R5's second half (D125, docs/licence-model.md §4). An online licence
key (``licence_key``) is the licence's identity, pasted once; what keeps it in
force is a lease, which Loriini fetches from the licence service by itself --
when the key is first used on a computer, and then once a day while it is.
A lease is small and signed:

    licence 0042 is in force on this computer until 14 October

with the day it was given, the day the subscription is paid to, the seats and
how many are in use, the version of Loriini it was given to, and -- when there
is one -- a notice for whoever looks: the payment failed, an update is due.

It is signed with the same Ed25519 key as the licence keys, under a domain tag
of its own, so that neither can ever be passed off as the other. Loriini checks
it against the public key compiled into the build: a lease from anywhere but
the licence service -- copied from another computer, written by hand, or
served by something pretending to be the service -- is refused.

A refusal is a lease too
------------------------
When the service will not renew -- the licence was withdrawn, the subscription
lapsed, every seat is in use, or this version has been recalled -- it says so
in a lease marked refused, signed like any other, with the reason in a
sentence. Loriini believes a signed refusal and stops at once, which is what
makes a withdrawal immediate on a computer that is online; and as nobody but
the vendor can sign one, nobody else can stop a practice with a forged one.
Anything unsigned from the network is only ever "the service could not be
reached", and changes nothing.

Days, and the clock
-------------------
Dates travel as days, as the key carries them. A lease is in force from the
day before it was given to its last day: the day before, because the service
keeps UTC and a computer in the Americas is often a day behind it, and must
not refuse a lease given "tomorrow". A computer whose clock reads earlier
still is not early but wrong, and ``licence`` says so rather than believing
the lease.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import enum
import struct
from dataclasses import dataclass

from sun_study import signing
from sun_study.licence_key import day_from_number, day_number

__all__ = [
    "MACHINE_BYTES",
    "VERSION",
    "Lease",
    "LeaseRefusedError",
    "Reason",
    "make",
    "read",
]

#: The lease format this Loriini writes and reads.
VERSION = 1

#: A computer is named by this many bytes of a one-way hash (``licence_online``).
MACHINE_BYTES = 16

#: Everything signed starts with this, so no signature made for anything else --
#: a licence key included -- can be passed off as a lease.
_DOMAIN = b"Loriini licence lease\x00"

#: version, granted, reason, licence number, computer, given, until, paid to,
#: seats, computers in use.
_HEAD = struct.Struct(f">BBBI{MACHINE_BYTES}sHHHHH")

#: ``paid_to`` for a licence that is not paid for by the period: complimentary.
_NOT_BY_PERIOD = 0xFFFF

_LONGEST_BUILD = 64
_LONGEST_NOTICE = 4000

#: How far before the day it was given a lease is already in force (the
#: module docstring: UTC against a computer's own day).
_SLACK = dt.timedelta(days=1)


class Reason(enum.IntEnum):
    """Why the service refused. ``NONE`` on a lease it granted."""

    NONE = 0
    WITHDRAWN = 1
    LAPSED = 2
    SEATS = 3
    RECALLED = 4
    NOT_KNOWN = 5
    OTHER = 255
    """A reason a later service gives that this Loriini has no name for."""


class LeaseRefusedError(ValueError):
    """Not a lease this build can believe: damaged, or not signed by the vendor."""


@dataclass(frozen=True)
class Lease:
    """What a lease says."""

    serial: int
    machine: bytes
    """The computer it was given to (``licence_online.machine``)."""
    given: dt.date
    """The service's own date when it gave the lease."""
    until: dt.date
    """The last day it is in force. On a refusal, the day it was given."""
    granted: bool = True
    reason: Reason = Reason.NONE
    paid_to: dt.date | None = None
    """The last day the subscription is paid for; ``None`` for a licence that is
    not paid for by the period."""
    seats: int = 0
    in_use: int = 0
    """Computers using the licence, this one included, as the service counts them."""
    build: str = ""
    """The version of Loriini it was given to."""
    notice: str = ""
    """On a grant, anything its holder should know; on a refusal, why, in a sentence."""

    @property
    def number(self) -> str:
        return f"{self.serial:04d}"

    def in_force(self, day: dt.date) -> bool:
        """Whether this is a grant, and ``day`` inside it."""
        return self.granted and self.given - _SLACK <= day <= self.until

    def clock_behind(self, day: dt.date) -> bool:
        """Whether ``day`` is earlier than any computer it was given to can read
        with its clock right: a wound-back clock, or a wrong one."""
        return day < self.given - _SLACK


def make(lease: Lease, seed: bytes) -> str:
    """The lease, signed with the vendor's private key, as text for the wire and
    the lease file. The licence service's side: Loriini only reads them."""
    if len(lease.machine) != MACHINE_BYTES:
        raise ValueError(f"a computer is named by {MACHINE_BYTES} bytes")
    if not 0 <= lease.serial < 2**32:
        raise ValueError(f"licence number {lease.serial} is out of range")
    if not (0 <= lease.seats < 2**16 and 0 <= lease.in_use < 2**16):
        raise ValueError("seats out of range")
    if lease.granted == (lease.reason is not Reason.NONE):
        raise ValueError("a grant has no reason, and a refusal needs one")
    build = lease.build.encode("ascii")
    notice = lease.notice.encode("utf-8")
    if len(build) > _LONGEST_BUILD or len(notice) > _LONGEST_NOTICE:
        raise ValueError("the build or the notice is longer than a lease carries")
    paid_to = _NOT_BY_PERIOD if lease.paid_to is None else day_number(lease.paid_to)
    payload = (
        _HEAD.pack(
            VERSION,
            1 if lease.granted else 0,
            int(lease.reason),
            lease.serial,
            lease.machine,
            day_number(lease.given),
            day_number(lease.until),
            paid_to,
            lease.seats,
            lease.in_use,
        )
        + bytes([len(build)])
        + build
        + len(notice).to_bytes(2, "big")
        + notice
    )
    body = payload + signing.sign(seed, _DOMAIN + payload)
    return base64.urlsafe_b64encode(body).decode("ascii")


_DAMAGED = "The lease is damaged."


def read(text: str, public: bytes) -> Lease:
    """What a lease says, once it is known to be whole and signed by the
    private half of ``public``. Raises ``LeaseRefusedError`` otherwise."""
    try:
        body = base64.urlsafe_b64decode(text.strip().encode("ascii"))
    except (binascii.Error, ValueError) as damaged:
        raise LeaseRefusedError(_DAMAGED) from damaged
    if len(body) < _HEAD.size + 3 + signing.SIGNATURE_BYTES:
        raise LeaseRefusedError(_DAMAGED)
    payload, signature = body[: -signing.SIGNATURE_BYTES], body[-signing.SIGNATURE_BYTES :]
    if payload[0] != VERSION:
        raise LeaseRefusedError("The lease is in a format this Loriini does not read.")
    if not signing.verify(public, _DOMAIN + payload, signature):
        raise LeaseRefusedError("The lease was not given by the licence service.")

    (
        _version,
        granted,
        reason,
        serial,
        machine,
        given,
        until,
        paid_to,
        seats,
        in_use,
    ) = _HEAD.unpack_from(payload)
    at = _HEAD.size
    build_length = payload[at]
    build = payload[at + 1 : at + 1 + build_length]
    at += 1 + build_length
    notice_length = int.from_bytes(payload[at : at + 2], "big")
    notice = payload[at + 2 : at + 2 + notice_length]
    if at + 2 + notice_length != len(payload):
        raise LeaseRefusedError(_DAMAGED)
    try:
        why = Reason(reason)
    except ValueError:
        why = Reason.OTHER
    return Lease(
        serial=serial,
        machine=machine,
        given=day_from_number(given),
        until=day_from_number(until),
        granted=bool(granted),
        reason=Reason.NONE if granted else (why if why is not Reason.NONE else Reason.OTHER),
        paid_to=None if paid_to == _NOT_BY_PERIOD else day_from_number(paid_to),
        seats=seats,
        in_use=in_use,
        build=build.decode("ascii", "replace"),
        notice=notice.decode("utf-8", "replace"),
    )
