"""Stripe's side: what a checkout, a payment, a failed card or a cancellation
does to a licence.

Stripe sends the licence service an event for each (a *webhook*), signed with
the endpoint's secret; ``verify`` checks the signature and its age before
anything is read, so an event from anyone but Stripe changes nothing. Then:

- ``checkout.session.completed`` -- somebody subscribed. A licence is made
  and its online key issued and emailed (``Service.issue``), numbered by the
  service, for the seats bought and the practice named at the checkout.
- ``invoice.paid`` -- a period was paid for. The licence's paid-to date moves
  to the end of it, and a failed payment is forgotten. This, and not the
  subscription's own dates, moves paid-to: a subscription starts its next
  period before the card has paid for it.
- ``invoice.payment_failed`` -- the card was refused. The date is kept so
  every lease says so, while Stripe tries again; the grace covers the tries.
- ``customer.subscription.created`` and ``.updated`` -- the seats bought, and
  whether the subscription is set to end. A subscription set to end loses its
  grace, since nobody is retrying a card for it; one set going again gets it
  back.
- ``customer.subscription.deleted`` -- it has ended. No grace: its licence
  lapses on the day it was paid to.

Stripe does not promise the order, or that an event comes only once. So an
event handled before is handled again as nothing (``Store.handled``); and what
arrives about a subscription before its checkout -- the seats, a payment -- is
noted against the subscription (``Store.note_subscription``) and taken up
when the licence is made.

Both of Stripe's shapes are read: before its 2025 API versions an invoice
named its subscription at the top, and after them under ``parent``, and a
subscription's quantity moved to its items.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from sun_study.licence_issue import term_end
from sun_study.licence_service.store import Licence, Store

__all__ = ["TOLERANCE", "NewSubscriber", "SignatureError", "handle", "verify"]

#: Seconds an event's signature stays good: Stripe's own libraries' default,
#: which is what stops an old event being sent again by somebody who saw it.
TOLERANCE = 300

#: Checkout fields a practice's name may be asked in.
_HOLDER_FIELDS = ("practice", "practicename", "practice_name", "company", "holder", "business")


class SignatureError(ValueError):
    """Not an event from Stripe, or one too old to believe."""


def verify(payload: bytes, header: str, secret: str, *, now: float) -> dict[str, Any]:
    """The event in ``payload``, once ``header`` (``Stripe-Signature``) shows
    it was signed with ``secret`` within ``TOLERANCE`` seconds of ``now``."""
    if not secret:
        raise SignatureError("The service has no Stripe webhook secret set.")
    stamp = ""
    signatures: list[str] = []
    for part in header.split(","):
        name, _, value = part.strip().partition("=")
        if name == "t":
            stamp = value
        elif name == "v1":
            signatures.append(value)
    if not stamp.isdigit() or not signatures:
        raise SignatureError("The event carries no Stripe signature.")
    expected = hmac.new(
        secret.encode("utf-8"), stamp.encode("ascii") + b"." + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise SignatureError("The event's signature is not Stripe's.")
    if abs(now - int(stamp)) > TOLERANCE:
        raise SignatureError("The event is too old to believe.")
    try:
        event = json.loads(payload)
    except ValueError as error:
        raise SignatureError("The event could not be read.") from error
    if not isinstance(event, dict):
        raise SignatureError("The event could not be read.")
    return event


#: What ``handle`` asks the service to do when somebody subscribes: issue the
#: licence and its key, email it, keep it -- and return it.
NewSubscriber = Callable[..., Licence]


def handle(
    event: Mapping[str, Any],
    store: Store,
    *,
    today: dt.date,
    grace_days: int,
    subscribe: NewSubscriber,
) -> str:
    """Do what ``event`` says to the licences, and say what that was."""
    kind = str(event.get("type", ""))
    identifier = str(event.get("id", ""))
    data = event.get("data")
    thing = data.get("object") if isinstance(data, dict) else None
    if not isinstance(thing, dict):
        return f"{kind}: no object"
    with store.lock:
        if identifier and store.handled(identifier):
            return f"{kind} {identifier}: handled before"
        if kind == "checkout.session.completed":
            said = _checkout(thing, store, today=today, subscribe=subscribe)
        elif kind == "invoice.paid":
            said = _paid(thing, store)
        elif kind == "invoice.payment_failed":
            said = _failed(thing, store, today=today)
        elif kind in ("customer.subscription.created", "customer.subscription.updated"):
            said = _subscription(thing, store, grace_days=grace_days)
        elif kind == "customer.subscription.deleted":
            said = _ended(thing, store)
        else:
            said = f"{kind}: nothing to do"
        if identifier:
            store.mark_handled(identifier)
    return said


def _identifier(value: Any) -> str | None:
    """An id Stripe sends either bare or as the object it names."""
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict) and isinstance(value.get("id"), str):
        return str(value["id"])
    return None


def _day(stamp: Any) -> dt.date | None:
    if isinstance(stamp, int | float) and stamp > 0:
        return dt.datetime.fromtimestamp(stamp, dt.UTC).date()
    return None


def _checkout(
    session: Mapping[str, Any], store: Store, *, today: dt.date, subscribe: NewSubscriber
) -> str:
    subscription = _identifier(session.get("subscription"))
    if session.get("mode") != "subscription" or subscription is None:
        return "checkout: not a subscription"
    known = store.by_subscription(subscription)
    if known is not None:
        return f"checkout: subscription {subscription} already has licence {known.number}"
    details = session.get("customer_details") or {}
    email = str(details.get("email") or session.get("customer_email") or "").strip()
    if "@" not in email:
        store.log(f"checkout for subscription {subscription} came with no email; no licence made")
        return "checkout: no email"
    noted = store.subscription(subscription)
    licence = subscribe(
        email=email,
        holder=_holder(session, details),
        seats=noted.quantity or 1,
        paid_to=noted.paid_to or term_end(today, 1),
        subscription=subscription,
        customer=_identifier(session.get("customer")),
        ended=noted.ended,
    )
    return f"checkout: licence {licence.number} for {email}"


def _holder(session: Mapping[str, Any], details: Mapping[str, Any]) -> str:
    """The practice's name: a checkout field for it if there is one, else the
    business name Stripe collected, else the buyer's own name."""
    for field in session.get("custom_fields") or []:
        key = str(field.get("key", "")).casefold()
        value = (field.get("text") or {}).get("value")
        if key in _HOLDER_FIELDS and isinstance(value, str) and value.strip():
            return value.strip()
    for name in (details.get("business_name"), details.get("name")):
        if isinstance(name, str) and name.strip():
            return name.strip()
    return ""


def _invoice_subscription(invoice: Mapping[str, Any]) -> str | None:
    found = _identifier(invoice.get("subscription"))
    if found is not None:
        return found
    parent = invoice.get("parent") or {}
    details = parent.get("subscription_details") or {}
    found = _identifier(details.get("subscription"))
    if found is not None:
        return found
    for line in (invoice.get("lines") or {}).get("data") or []:
        found = _identifier(line.get("subscription"))
        if found is None:
            item = (line.get("parent") or {}).get("subscription_item_details") or {}
            found = _identifier(item.get("subscription"))
        if found is not None:
            return found
    return None


def _period_end(invoice: Mapping[str, Any]) -> dt.date | None:
    """The last day an invoice pays for: the latest end among its lines."""
    ends = [
        _day((line.get("period") or {}).get("end"))
        for line in (invoice.get("lines") or {}).get("data") or []
    ]
    found = [end for end in ends if end is not None]
    return max(found) if found else _day(invoice.get("period_end"))


def _paid(invoice: Mapping[str, Any], store: Store) -> str:
    subscription = _invoice_subscription(invoice)
    paid_to = _period_end(invoice)
    if subscription is None or paid_to is None:
        return "invoice paid: not for a subscription"
    licence = store.by_subscription(subscription)
    if licence is None:
        noted = store.subscription(subscription)
        later = max(filter(None, (noted.paid_to, paid_to)))
        store.note_subscription(replace(noted, paid_to=later))
        return f"invoice paid: subscription {subscription} noted, paid to {later}"
    later = max(filter(None, (licence.paid_to, paid_to)))
    store.save(replace(licence, paid_to=later, payment_failed=None))
    store.log(f"paid to {later.isoformat()} (Stripe)", licence.serial)
    return f"invoice paid: licence {licence.number} paid to {later}"


def _failed(invoice: Mapping[str, Any], store: Store, *, today: dt.date) -> str:
    subscription = _invoice_subscription(invoice)
    licence = store.by_subscription(subscription) if subscription else None
    if licence is None:
        return "payment failed: no licence for it"
    store.save(replace(licence, payment_failed=licence.payment_failed or today))
    store.log("a payment failed (Stripe)", licence.serial)
    return f"payment failed: licence {licence.number}"


def _quantity(subscription: Mapping[str, Any]) -> int | None:
    items = (subscription.get("items") or {}).get("data") or []
    quantities = [int(item["quantity"]) for item in items if isinstance(item.get("quantity"), int)]
    if quantities:
        return max(1, sum(quantities))
    quantity = subscription.get("quantity")
    return max(1, quantity) if isinstance(quantity, int) else None


def _subscription(subscription: Mapping[str, Any], store: Store, *, grace_days: int) -> str:
    identifier = _identifier(subscription.get("id"))
    if identifier is None:
        return "subscription: no id"
    quantity = _quantity(subscription)
    ending = bool(subscription.get("cancel_at_period_end")) or bool(subscription.get("cancel_at"))
    licence = store.by_subscription(identifier)
    if licence is None:
        noted = store.subscription(identifier)
        store.note_subscription(replace(noted, quantity=quantity or noted.quantity))
        return f"subscription {identifier} noted"
    status = str(subscription.get("status", ""))
    changed = replace(
        licence,
        seats=quantity or licence.seats,
        grace_days=0 if ending else (licence.grace_days or grace_days),
        payment_failed=None if status == "active" else licence.payment_failed,
        customer=licence.customer or _identifier(subscription.get("customer")),
    )
    if changed != licence:
        store.save(changed)
        store.log(
            f"subscription: {changed.seats} seats"
            + (", set to end" if ending else "")
            + f" (Stripe, {status or 'no status'})",
            licence.serial,
        )
    return f"subscription: licence {licence.number}"


def _ended(subscription: Mapping[str, Any], store: Store) -> str:
    identifier = _identifier(subscription.get("id"))
    if identifier is None:
        return "subscription ended: no id"
    licence = store.by_subscription(identifier)
    if licence is None:
        noted = store.subscription(identifier)
        store.note_subscription(replace(noted, ended=True))
        return f"subscription {identifier} ended before its licence was made"
    store.save(replace(licence, grace_days=0))
    store.log("subscription ended (Stripe)", licence.serial)
    return f"subscription ended: licence {licence.number}"
