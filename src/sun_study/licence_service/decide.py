"""The one decision the licence service makes: what lease a computer gets.

In this order, which is the policy (docs/licence-model.md §2 and §4):

1. **Recalled.** A version of Loriini below the minimum the vendor set is
   refused, with why and where the current one is. A recall stops a build
   known to give a wrong result on the day it is found -- the job the build's
   fixed term did for every build at once.
2. **Withdrawn.** A licence the vendor withdrew is refused, with the reason.
3. **Lapsed.** A licence whose paid-to date is more than its grace behind
   today is refused, and says how to start again.
4. **Seats.** A computer new to the licence is refused when the computers
   already using it number its seats and the margin. A practice one computer
   over is *told*, in the lease's notice, and not stopped: the overlap is
   nearly always an old computer that has not yet freed its seat.
5. **Granted**, until the paid-to date plus the grace or a lease's length from
   today, whichever comes first, with a notice for anything its holder should
   know: a payment being retried, seats over, a subscription or trial about to
   end, and the vendor's notice for everybody.

A computer is using a licence while its last lease could still be in force:
seen within a lease's length, and not freed since. So a seat frees itself a
lease's length after the computer holding it stops being used, and at once
when ``Loriini.exe licence --remove`` frees it.

Every refusal is a signed lease like a grant (``licence_lease``): Loriini
believes it and stops, and says the sentence written here, which is why each
one ends with what to do.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass

from sun_study import AUTHOR
from sun_study.licence_lease import Lease, Reason
from sun_study.licence_service.store import Computer, Licence

__all__ = ["LEASE_DAYS", "SEAT_MARGIN", "Terms", "decide", "recalled", "version_tuple"]

#: A lease's length, and how long a seat stays taken after its computer's
#: last contact (docs/licence-model.md §4.2).
LEASE_DAYS = 14

#: Computers over its seats a licence may be on and still be granted.
SEAT_MARGIN = 1

#: Names listed in a refusal for seats, before "and N more".
_NAMES_SHOWN = 6


@dataclass(frozen=True)
class Terms:
    """What the vendor has set that bears on every decision."""

    lease_days: int = LEASE_DAYS
    seat_margin: int = SEAT_MARGIN
    minimum_build: str = ""
    """Versions below this are recalled. Empty for none."""
    recall_reason: str = ""
    download: str = ""
    """Where the current version is, for a recall's sentence."""
    portal: str = ""
    """Where a subscriber changes their card and seats (Stripe's portal)."""
    notice: str = ""
    """Said on every grant, to everybody: an update, a planned outage."""


def version_tuple(text: str) -> tuple[int, ...]:
    """``"1.2.10"`` as ``(1, 2, 10)``, so versions compare as numbers."""
    return tuple(int(part) for part in re.findall(r"\d+", text)) or (0,)


def recalled(build: str, minimum: str) -> bool:
    return bool(minimum) and version_tuple(build) < version_tuple(minimum)


def _day(when: dt.date) -> str:
    return f"{when.day} {when:%B %Y}"


def _names(computers: Sequence[Computer]) -> str:
    names = [computer.name or "a computer with no name" for computer in computers]
    if len(names) > _NAMES_SHOWN:
        shown = ", ".join(names[:_NAMES_SHOWN])
        return f"{shown} and {len(names) - _NAMES_SHOWN} more"
    if len(names) > 1:
        return ", ".join(names[:-1]) + " and " + names[-1]
    return names[0] if names else "no computer"


def decide(
    licence: Licence,
    computers: Sequence[Computer],
    *,
    machine: bytes,
    build: str,
    today: dt.date,
    terms: Terms,
) -> Lease:
    """The lease ``machine`` gets for ``licence`` today."""
    number = licence.number
    in_use = [c for c in computers if c.in_use(today, terms.lease_days)]
    mine = any(c.machine == machine.hex() for c in in_use)

    def refused(reason: Reason, sentence: str) -> Lease:
        return Lease(
            serial=licence.serial,
            machine=machine,
            given=today,
            until=today,
            granted=False,
            reason=reason,
            paid_to=licence.paid_to,
            seats=licence.seats,
            in_use=len(in_use),
            build=build,
            notice=sentence,
        )

    if recalled(build, terms.minimum_build):
        why = f": {terms.recall_reason.rstrip('.')}" if terms.recall_reason else ""
        where = f" from {terms.download}" if terms.download else ""
        return refused(
            Reason.RECALLED,
            f"Loriini {build or 'of this version'} has been withdrawn{why}. Install the "
            f"current version{where}; the licence carries over to it.",
        )
    if licence.withdrawn is not None:
        why = f": {licence.withdrawn.rstrip('.')}" if licence.withdrawn else ""
        return refused(
            Reason.WITHDRAWN,
            f"Licence {number} has been withdrawn{why}. {AUTHOR} can say more.",
        )
    good_to = licence.good_to
    if good_to is not None and good_to < today and licence.paid_to is not None:
        if licence.trial:
            sentence = (
                f"The trial of Loriini (licence {number}) ended on {_day(licence.paid_to)}. "
                f"A subscription lets it start again at once."
            )
        else:
            where = f": {terms.portal}" if terms.portal else ""
            sentence = (
                f"The subscription for licence {number} was paid to "
                f"{_day(licence.paid_to)} and has not been renewed. Renewing it lets "
                f"Loriini start again at once{where}."
            )
        return refused(Reason.LAPSED, sentence)
    if not mine and len(in_use) >= licence.seats + terms.seat_margin:
        seats = "seat" if licence.seats == 1 else "seats"
        return refused(
            Reason.SEATS,
            f"All {licence.seats} {seats} of licence {number} are in use, on "
            f"{_names(in_use)}. Run Loriini.exe licence --remove on a computer that no "
            f"longer needs its seat, or add a seat. A computer unused for "
            f"{terms.lease_days} days frees its seat by itself.",
        )

    counted = len(in_use) + (0 if mine else 1)
    until = today + dt.timedelta(days=terms.lease_days)
    if good_to is not None:
        until = min(until, good_to)
    notices: list[str] = []
    if licence.payment_failed is not None and good_to is not None:
        where = f" at {terms.portal}" if terms.portal else ""
        notices.append(
            f"The payment for licence {number} failed on {_day(licence.payment_failed)}, "
            f"and will be tried again. Update the card{where} to keep Loriini running "
            f"after {_day(good_to)}."
        )
    if counted > licence.seats:
        oldest = min(
            (c.last_seen for c in in_use if c.machine != machine.hex()),
            default=today,
        )
        frees = oldest + dt.timedelta(days=terms.lease_days + 1)
        notices.append(
            f"Licence {number} is on {counted} computers for {licence.seats} seats. The "
            f"one used longest ago frees its seat on {_day(frees)}; add a seat to keep "
            f"them all."
        )
    ending = licence.paid_to is not None and (licence.trial or licence.grace_days == 0)
    if ending and licence.paid_to is not None:
        left = (licence.paid_to - today).days
        if 0 <= left <= terms.lease_days:
            what = "The trial" if licence.trial else f"The subscription for licence {number}"
            notices.append(f"{what} ends on {_day(licence.paid_to)}.")
    if terms.notice:
        notices.append(terms.notice)
    return Lease(
        serial=licence.serial,
        machine=machine,
        given=today,
        until=until,
        paid_to=licence.paid_to,
        seats=licence.seats,
        in_use=counted,
        build=build,
        notice=" ".join(notices),
    )
