"""A licence key: who holds it, for how many seats, until when -- signed.

Roadmap R5: a buyer is emailed a key, pastes it into Loriini once, and
Loriini checks it offline at every start (D124). This module is the key
itself -- what it says, how it is written down, and how it is read back and
checked. ``licence`` decides what a start does with it, and
``licence_issue`` is the vendor's side that makes one.

What a key says
---------------
The licence number, the buyer's email, the holder's name (a person or a
practice), the seats bought, the day it was issued and the last day it is good
for. Seats are what the buyer agreed to, not something counted: offline there
is nothing to count against, and a key is bound by its terms the way the
executable is.

How it is written
-----------------
``LORIINI-`` and then groups of five characters, in Crockford's base 32:
digits and capitals with no I, L, O or U, read back case-blind with O taken as
0 and I or L as 1. A key survives being read aloud, retyped from a printout,
lower-cased by a mail client or wrapped over three lines -- spaces, line
breaks and the dashes are ignored when it is read.

The last characters are a CRC-32 of everything before them, checked before
anything else. So a key cut short by an email client's line wrap, or with one
character wrong, is told as that -- "not the whole key, or a typo: copy it
again" -- and not as a forgery. The difference is a colleague pasting again
against a colleague phoning the vendor.

The signature
-------------
Ed25519 (``signing``) over a domain tag and the fields, so no signature made
for anything else can ever read as a licence, and a key made with another
signing key -- a test key, a key for another product -- is refused as not
genuine. The version byte comes first so a later key format can be told apart
and refused politely by an older Loriini, rather than misread.
"""

from __future__ import annotations

import datetime as dt
import struct
import zlib
from dataclasses import dataclass

from sun_study import signing

__all__ = [
    "PREFIX",
    "KeyExpiredError",
    "KeyIncompleteError",
    "KeyNotGenuineError",
    "KeyRefusedError",
    "KeyTooNewError",
    "LicenceKey",
    "lines",
    "make",
    "read",
    "tidy",
]

#: What every key starts with, so one in an email is recognisable at a glance.
PREFIX = "LORIINI"

#: Crockford's base 32: no I, L, O or U, so none can be mistaken for another.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_VALUES = {letter: value for value, letter in enumerate(ALPHABET)} | {
    "O": 0,
    "I": 1,
    "L": 1,
}

#: Characters to a group, and groups to a line when a key is set in an email.
GROUP = 5
GROUPS_PER_LINE = 6

#: The key format this Loriini writes and reads.
VERSION = 1

#: Dates are days after this, in two bytes: good until 2203.
_EPOCH = dt.date(2024, 1, 1)

#: version, licence number, issued, expires, seats, flags (none yet).
_HEAD = struct.Struct(">BIHHHB")

#: What is signed is always prefixed with this, so that no Ed25519 signature
#: made for anything else can be passed off as a licence.
_DOMAIN = b"Loriini licence key\x00"

_CHECK_BYTES = 4
_LONGEST_FIELD = 255


class KeyRefusedError(ValueError):
    """A key that cannot be used, with a sentence saying why."""


class KeyIncompleteError(KeyRefusedError):
    """Not the whole key, or a character wrong: copy it again."""


class KeyNotGenuineError(KeyRefusedError):
    """Complete and well formed, but not signed by the vendor this build trusts."""


class KeyTooNewError(KeyRefusedError):
    """A key in a format a later Loriini writes."""


class KeyExpiredError(KeyRefusedError):
    """Whole and genuine, and past its last day."""


@dataclass(frozen=True)
class LicenceKey:
    """What a key says."""

    serial: int
    email: str
    holder: str
    seats: int
    issued: dt.date
    expires: dt.date
    """The last day the key is good for."""

    @property
    def number(self) -> str:
        """``0042``: the licence number as the vendor and the buyer say it."""
        return f"{self.serial:04d}"

    @property
    def whose(self) -> str:
        """``Fuse Architects (office@fuse.com.au)``, or the email alone."""
        return f"{self.holder} ({self.email})" if self.holder else self.email

    def good_on(self, day: dt.date) -> bool:
        """Whether the key is in force on ``day``.

        Only the end is checked. A key issued in Sydney in the morning is
        issued "tomorrow" on a laptop in London the night before, and refusing
        it as not yet valid would be a support call about a time zone.
        """
        return day <= self.expires

    def describe(self) -> str:
        seats = "1 seat" if self.seats == 1 else f"{self.seats} seats"
        return f"licence {self.number}, {self.whose}, {seats}, until {_day(self.expires)}"


def _day(when: dt.date) -> str:
    return f"{when.day} {when:%B %Y}"


def _days(when: dt.date) -> int:
    days = (when - _EPOCH).days
    if not 0 <= days < 2**16:
        raise ValueError(f"{when} is outside the dates a key can carry")
    return days


def _field(text: str) -> bytes:
    data = text.encode("utf-8")
    if len(data) > _LONGEST_FIELD:
        raise ValueError(f"{text[:40]!r}... is longer than a key can carry")
    return bytes([len(data)]) + data


def _base32(data: bytes) -> str:
    bits = len(data) * 8
    pad = -bits % 5
    number = int.from_bytes(data, "big") << pad
    count = (bits + pad) // 5
    return "".join(ALPHABET[(number >> (5 * (count - 1 - i))) & 31] for i in range(count))


def _unbase32(text: str) -> bytes:
    number = 0
    for character in text:
        value = _VALUES.get(character)
        if value is None:
            raise KeyIncompleteError(
                f"The key has {character!r} in it, which no key contains. Copy it again "
                f"from the email, the whole of it."
            )
        number = (number << 5) | value
    bits = len(text) * 5
    pad = bits % 8
    if number & ((1 << pad) - 1):
        raise KeyIncompleteError(_INCOMPLETE)
    return (number >> pad).to_bytes(bits // 8, "big")


_INCOMPLETE = (
    "That is not the whole key, or a character in it is wrong. Copy it again from "
    "the email -- all of it, from LORIINI to the last group."
)


def make(key: LicenceKey, seed: bytes) -> str:
    """The key, signed with the vendor's private key and written for a person.

    The vendor's side: nothing in Loriini itself calls this.
    """
    if not 0 <= key.serial < 2**32:
        raise ValueError(f"licence number {key.serial} is out of range")
    if not 1 <= key.seats < 2**16:
        raise ValueError(f"{key.seats} seats is out of range")
    if key.expires < key.issued:
        raise ValueError("a key cannot end before it is issued")
    if "@" not in key.email:
        raise ValueError(f"{key.email!r} is not an email address")
    payload = (
        _HEAD.pack(VERSION, key.serial, _days(key.issued), _days(key.expires), key.seats, 0)
        + _field(key.email.strip())
        + _field(key.holder.strip())
    )
    body = payload + signing.sign(seed, _DOMAIN + payload)
    code = _base32(body + zlib.crc32(body).to_bytes(_CHECK_BYTES, "big"))
    return "-".join([PREFIX, *(code[i : i + GROUP] for i in range(0, len(code), GROUP))])


def _compact(text: str) -> str:
    """The key's characters alone: no prefix, spaces, breaks or dashes, in
    capitals, with O read as 0 and I and L as 1."""
    compact = "".join(text.split()).upper().replace("-", "")
    if compact.startswith(PREFIX):
        compact = compact[len(PREFIX) :]
    return compact.translate(str.maketrans("OIL", "011"))


def tidy(text: str) -> str:
    """A key as it was issued, however it was pasted: ``LORIINI-`` and groups."""
    code = _compact(text)
    return "-".join([PREFIX, *(code[i : i + GROUP] for i in range(0, len(code), GROUP))])


def lines(text: str, groups: int = GROUPS_PER_LINE) -> list[str]:
    """A key broken into lines of ``groups`` groups, to set in an email.

    Read back whatever a mail client does to the breaks, since ``read``
    ignores them.
    """
    parts = text.split("-")
    return ["-".join(parts[i : i + groups]) for i in range(0, len(parts), groups)]


def read(text: str, public: bytes) -> LicenceKey:
    """What a pasted key says, once it is known to be whole and genuine.

    Raises ``KeyIncompleteError`` for a key cut short or mistyped, ``KeyTooNewError``
    for a format this Loriini does not know, and ``KeyNotGenuineError`` for one
    not signed with the private half of ``public``. Whether it is still in
    force is the caller's question (``LicenceKey.good_on``).
    """
    compact = _compact(text)
    if not compact:
        raise KeyIncompleteError("There is no key there. Paste the whole key from the email.")
    data = _unbase32(compact)
    fixed = _HEAD.size + 2 + signing.SIGNATURE_BYTES + _CHECK_BYTES
    if len(data) < fixed:
        raise KeyIncompleteError(_INCOMPLETE)
    body, check = data[:-_CHECK_BYTES], data[-_CHECK_BYTES:]
    if zlib.crc32(body).to_bytes(_CHECK_BYTES, "big") != check:
        raise KeyIncompleteError(_INCOMPLETE)

    payload, signature = body[: -signing.SIGNATURE_BYTES], body[-signing.SIGNATURE_BYTES :]
    version, serial, issued, expires, seats, _flags = _HEAD.unpack_from(payload)
    if version > VERSION:
        raise KeyTooNewError(
            "This key is for a newer Loriini than this one. Install the current build, "
            "then paste the key again."
        )
    if version != VERSION or not signing.verify(public, _DOMAIN + payload, signature):
        raise KeyNotGenuineError(
            "This is not a licence key for this Loriini. It is complete, but it was not "
            "issued for this build -- check it is the key from your licence email."
        )

    fields: list[str] = []
    at = _HEAD.size
    for _ in range(2):
        length = payload[at]
        fields.append(payload[at + 1 : at + 1 + length].decode("utf-8"))
        at += 1 + length
    return LicenceKey(
        serial=serial,
        email=fields[0],
        holder=fields[1],
        seats=seats,
        issued=_EPOCH + dt.timedelta(days=issued),
        expires=_EPOCH + dt.timedelta(days=expires),
    )
