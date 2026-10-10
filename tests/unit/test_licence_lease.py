"""Leases: what the licence service signs, and what Loriini believes.

Roadmap R5's second half (D125). A lease is believed only whole and signed by
the vendor; a refusal is signed the same way, so that Loriini can act on it and
nobody else can forge one; and its days hold across the date line.
"""

from __future__ import annotations

import base64
import datetime as dt

import pytest

from sun_study import licence_key, signing
from sun_study.licence_lease import (
    MACHINE_BYTES,
    Lease,
    LeaseRefusedError,
    Reason,
    make,
    read,
)

SEED = bytes(range(32))
PUBLIC = signing.public_key(SEED)
OTHER = bytes(range(1, 33))
COMPUTER = bytes(range(MACHINE_BYTES))
GIVEN = dt.date(2026, 9, 29)

GRANT = Lease(
    serial=42,
    machine=COMPUTER,
    given=GIVEN,
    until=dt.date(2026, 10, 13),
    paid_to=dt.date(2026, 10, 31),
    seats=5,
    in_use=4,
    build="1.2.0",
    notice="The payment for licence 0042 failed on 3 October 2026, and will be tried again.",
)


def test_a_lease_reads_back_as_what_was_signed() -> None:
    assert read(make(GRANT, SEED), PUBLIC) == GRANT


def test_a_refusal_is_signed_like_a_grant_and_says_why() -> None:
    refusal = Lease(
        serial=42,
        machine=COMPUTER,
        given=GIVEN,
        until=GIVEN,
        granted=False,
        reason=Reason.WITHDRAWN,
        notice="Licence 0042 has been withdrawn: refunded.",
    )
    back = read(make(refusal, SEED), PUBLIC)
    assert back == refusal
    assert not back.in_force(GIVEN)


def test_a_grant_has_no_reason_and_a_refusal_needs_one() -> None:
    with pytest.raises(ValueError, match="reason"):
        make(
            Lease(serial=1, machine=COMPUTER, given=GIVEN, until=GIVEN, reason=Reason.LAPSED), SEED
        )
    with pytest.raises(ValueError, match="reason"):
        make(Lease(serial=1, machine=COMPUTER, given=GIVEN, until=GIVEN, granted=False), SEED)


def test_a_licence_not_paid_by_the_period_has_no_paid_to_date() -> None:
    complimentary = Lease(serial=1, machine=COMPUTER, given=GIVEN, until=GIVEN, paid_to=None)
    assert read(make(complimentary, SEED), PUBLIC).paid_to is None


def test_a_lease_from_anyone_else_is_not_believed() -> None:
    with pytest.raises(LeaseRefusedError, match="not given by the licence service"):
        read(make(GRANT, OTHER), PUBLIC)


def test_a_lease_changed_after_it_was_signed_is_not_believed() -> None:
    body = bytearray(base64.urlsafe_b64decode(make(GRANT, SEED)))
    body[10] ^= 1  # a day of the lease, or the computer's name
    with pytest.raises(LeaseRefusedError):
        read(base64.urlsafe_b64encode(bytes(body)).decode("ascii"), PUBLIC)


@pytest.mark.parametrize("text", ["", "not a lease at all", "QUJD", "!!!!"])
def test_what_is_not_a_lease_is_refused_not_a_crash(text: str) -> None:
    with pytest.raises(LeaseRefusedError):
        read(text, PUBLIC)


def test_a_licence_key_cannot_be_passed_off_as_a_lease() -> None:
    """The two are signed under different domain tags with the same key."""
    key = licence_key.make(
        licence_key.LicenceKey(
            serial=42,
            email="office@fuse.example",
            holder="Fuse",
            seats=1,
            issued=GIVEN,
            expires=GIVEN,
        ),
        SEED,
    )
    raw = licence_key._unbase32(licence_key._compact(key))[:-4]  # the body, without its CRC
    with pytest.raises(LeaseRefusedError):
        read(base64.urlsafe_b64encode(raw).decode("ascii"), PUBLIC)


def test_a_reason_a_later_service_names_is_still_a_refusal() -> None:
    refusal = Lease(
        serial=1,
        machine=COMPUTER,
        given=GIVEN,
        until=GIVEN,
        granted=False,
        reason=Reason.OTHER,
        notice="A reason from the future.",
    )
    back = read(make(refusal, SEED), PUBLIC)
    assert not back.granted
    assert back.reason is Reason.OTHER


def test_a_lease_is_in_force_from_the_day_before_it_was_given_to_its_last_day() -> None:
    """The service keeps UTC: a computer a day behind it must not refuse a
    lease given "tomorrow"."""
    assert not GRANT.in_force(GIVEN - dt.timedelta(days=2))
    assert GRANT.in_force(GIVEN - dt.timedelta(days=1))
    assert GRANT.in_force(GIVEN)
    assert GRANT.in_force(dt.date(2026, 10, 13))
    assert not GRANT.in_force(dt.date(2026, 10, 14))


def test_a_clock_earlier_than_that_is_wrong_not_early() -> None:
    assert GRANT.clock_behind(GIVEN - dt.timedelta(days=2))
    assert not GRANT.clock_behind(GIVEN - dt.timedelta(days=1))


def test_what_a_lease_cannot_carry_is_refused_when_it_is_made() -> None:
    with pytest.raises(ValueError, match="bytes"):
        make(Lease(serial=1, machine=b"short", given=GIVEN, until=GIVEN), SEED)
    with pytest.raises(ValueError, match="longer"):
        make(Lease(serial=1, machine=COMPUTER, given=GIVEN, until=GIVEN, notice="x" * 5000), SEED)
    with pytest.raises(ValueError, match="out of range"):
        make(Lease(serial=-1, machine=COMPUTER, given=GIVEN, until=GIVEN), SEED)
