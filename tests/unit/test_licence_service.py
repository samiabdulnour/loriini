"""The licence service: the decision it makes, what it keeps, what it answers,
and what Stripe's events do to a licence.

Roadmap R5's second half (D125). The decision is tested as the pure function
it is; the rest through the service's own WSGI door, the way the host's server
calls it, with a clock and a mail server of the test's own. Loriini talking to
it over a real socket is ``test_licence_online``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import io
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from sun_study import licence_issue, licence_key, signing
from sun_study.licence_lease import MACHINE_BYTES, Reason
from sun_study.licence_lease import read as read_lease
from sun_study.licence_service import app, stripe_events
from sun_study.licence_service.decide import Terms, decide, recalled, version_tuple
from sun_study.licence_service.store import Computer, Licence, Store
from tests.unit.licence_service_helpers import PUBLIC, SEED, STRIPE_SECRET, TOKEN

TODAY = dt.date(2026, 9, 29)
HERE = bytes(range(MACHINE_BYTES))
THERE = bytes(range(1, MACHINE_BYTES + 1))

LICENCE = Licence(
    serial=42,
    email="office@fuse.example",
    holder="Fuse Architects",
    seats=2,
    paid_to=dt.date(2026, 10, 31),
    grace_days=14,
)


def computer(
    machine: bytes, *, seen: dt.date = TODAY, name: str = "", freed: dt.date | None = None
) -> Computer:
    return Computer(
        serial=42,
        machine=machine.hex(),
        name=name or f"someone on PC-{machine[0]}",
        build="1.0.0",
        first_seen=dt.date(2026, 9, 1),
        last_seen=seen,
        freed=freed,
    )


def lease_for(
    licence: Licence = LICENCE, computers: list[Computer] | None = None, **how: Any
) -> Any:
    how.setdefault("machine", HERE)
    how.setdefault("build", "1.0.0")
    how.setdefault("today", TODAY)
    how.setdefault("terms", Terms())
    return decide(licence, computers or [], **how)


# -- the decision ---------------------------------------------------------------------


def test_a_paid_licence_is_granted_a_fortnight() -> None:
    lease = lease_for()
    assert lease.granted
    assert lease.until == TODAY + dt.timedelta(days=14)
    assert (lease.seats, lease.in_use) == (2, 1)
    assert lease.paid_to == dt.date(2026, 10, 31)
    assert lease.notice == ""


def test_a_lease_never_runs_past_what_is_paid_and_the_grace() -> None:
    near_the_end = Licence(**{**LICENCE.__dict__, "paid_to": TODAY + dt.timedelta(days=3)})
    assert lease_for(near_the_end).until == TODAY + dt.timedelta(days=14)
    no_grace = Licence(**{**near_the_end.__dict__, "grace_days": 0})
    assert lease_for(no_grace).until == TODAY + dt.timedelta(days=3)


def test_the_grace_covers_a_card_being_retried_and_no_more() -> None:
    paid_to = TODAY - dt.timedelta(days=14)
    in_grace = Licence(**{**LICENCE.__dict__, "paid_to": paid_to})
    assert lease_for(in_grace).granted
    assert lease_for(in_grace).until == TODAY
    lapsed = Licence(**{**LICENCE.__dict__, "paid_to": paid_to - dt.timedelta(days=1)})
    refusal = lease_for(lapsed)
    assert not refusal.granted
    assert refusal.reason is Reason.LAPSED
    assert "was paid to 14 September 2026 and has not been renewed" in refusal.notice


def test_a_trial_ends_on_its_last_day_and_says_how_to_go_on() -> None:
    trial = Licence(**{**LICENCE.__dict__, "trial": True, "grace_days": 0, "paid_to": TODAY})
    assert lease_for(trial).granted
    assert "The trial ends on 29 September 2026." in lease_for(trial).notice
    over = lease_for(trial, today=TODAY + dt.timedelta(days=1))
    assert over.reason is Reason.LAPSED
    assert "A subscription lets it start again at once." in over.notice


def test_a_complimentary_licence_never_lapses() -> None:
    free = Licence(**{**LICENCE.__dict__, "paid_to": None})
    lease = lease_for(free, today=dt.date(2040, 1, 1))
    assert lease.granted
    assert lease.until == dt.date(2040, 1, 15)
    assert lease.paid_to is None


def test_a_withdrawn_licence_is_refused_with_the_reason() -> None:
    withdrawn = Licence(**{**LICENCE.__dict__, "withdrawn": "refunded"})
    refusal = lease_for(withdrawn)
    assert refusal.reason is Reason.WITHDRAWN
    assert (
        refusal.notice == "Licence 0042 has been withdrawn: refunded. Sami Abdulnour can say more."
    )


def test_a_recalled_version_is_refused_and_told_where_the_current_one_is() -> None:
    terms = Terms(
        minimum_build="1.2.1",
        recall_reason="it overstates the hours behind deep balconies",
        download="https://loriini.example/download",
    )
    refusal = lease_for(build="1.2.0", terms=terms)
    assert refusal.reason is Reason.RECALLED
    assert refusal.notice == (
        "Loriini 1.2.0 has been withdrawn: it overstates the hours behind deep balconies. "
        "Install the current version from https://loriini.example/download; the licence "
        "carries over to it."
    )
    assert lease_for(build="1.2.1", terms=terms).granted
    assert lease_for(build="1.10.0", terms=terms).granted, "versions compare as numbers"


def test_versions_compare_as_numbers() -> None:
    assert version_tuple("1.10.0") > version_tuple("1.9.3")
    assert recalled("0.0.1", "1.0")
    assert not recalled("1.0.0", "")


def test_a_recall_comes_before_everything_else() -> None:
    withdrawn = Licence(**{**LICENCE.__dict__, "withdrawn": "refunded"})
    assert (
        lease_for(withdrawn, build="0.1", terms=Terms(minimum_build="1.0")).reason
        is Reason.RECALLED
    )


def test_a_practice_one_computer_over_is_told_and_two_over_is_stopped() -> None:
    both = [computer(THERE, name="amy on PC-2"), computer(bytes(16), name="ben on PC-3")]
    one_over = lease_for(computers=[both[0], computer(b"\x09" * 16, name="cat on PC-4")])
    assert one_over.granted
    assert one_over.in_use == 3
    assert "Licence 0042 is on 3 computers for 2 seats." in one_over.notice
    assert "frees its seat on 14 October 2026" in one_over.notice

    full = [*both, computer(b"\x09" * 16, name="cat on PC-4")]
    refusal = lease_for(computers=full)
    assert refusal.reason is Reason.SEATS
    assert refusal.notice.startswith(
        "All 2 seats of licence 0042 are in use, on amy on PC-2, ben on PC-3 and cat on PC-4."
    )
    assert "Loriini.exe licence --remove" in refusal.notice


def test_a_computer_already_counted_is_never_refused_for_seats() -> None:
    full = [computer(HERE), computer(THERE), computer(b"\x09" * 16)]
    assert lease_for(computers=full).granted


def test_a_seat_frees_itself_a_fortnight_after_its_computer_stops() -> None:
    stale = [
        computer(THERE, seen=TODAY - dt.timedelta(days=15)),
        computer(b"\x09" * 16, seen=TODAY - dt.timedelta(days=15)),
    ]
    lease = lease_for(computers=stale)
    assert lease.granted
    assert lease.in_use == 1
    still = [
        computer(THERE, seen=TODAY - dt.timedelta(days=14)),
        computer(b"\x09" * 16, seen=TODAY),
    ]
    assert "is on 3 computers" in lease_for(computers=still).notice


def test_a_freed_seat_is_free_at_once() -> None:
    freed = [computer(THERE, freed=TODAY), computer(b"\x09" * 16, freed=TODAY)]
    assert lease_for(computers=freed).in_use == 1


def test_a_failed_payment_is_said_on_every_lease_while_it_is_retried() -> None:
    failing = Licence(**{**LICENCE.__dict__, "payment_failed": dt.date(2026, 11, 1)})
    lease = lease_for(failing, terms=Terms(portal="https://billing.example/p/1"))
    assert lease.granted
    assert "failed on 1 November 2026, and will be tried again" in lease.notice
    assert "Update the card at https://billing.example/p/1" in lease.notice
    assert "after 14 November 2026" in lease.notice


def test_the_vendors_notice_goes_to_everybody() -> None:
    assert lease_for(terms=Terms(notice="Loriini 1.3 is out.")).notice == "Loriini 1.3 is out."


# -- what the service keeps ----------------------------------------------------------------


def test_the_store_keeps_licences_computers_and_settings(tmp_path: Path) -> None:
    store = Store(tmp_path / "licences.sqlite3")
    store.save(LICENCE)
    assert store.licence(42) == LICENCE
    assert store.next_serial() == 43
    store.set_setting("serial_floor", "500")
    assert store.next_serial() == 501
    store.seen(42, HERE.hex(), "amy on PC-1", "1.0.0", TODAY)
    store.seen(42, HERE.hex(), "amy on PC-1", "1.0.1", TODAY + dt.timedelta(days=1))
    [only] = store.computers(42)
    assert (only.build, only.first_seen, only.last_seen) == (
        "1.0.1",
        TODAY,
        TODAY + dt.timedelta(days=1),
    )
    assert store.free(42, "AMY ON PC-1", TODAY) == 1, "freed by name, as a person says it"
    assert store.computers(42)[0].freed == TODAY
    store.seen(42, HERE.hex(), "amy on PC-1", "1.0.1", TODAY)
    assert store.computers(42)[0].freed is None, "used again, it takes its seat again"
    store.close()

    reopened = Store(tmp_path / "licences.sqlite3")
    assert reopened.licence(42) == LICENCE
    assert reopened.settings() == {"serial_floor": "500"}
    reopened.close()


def test_a_backup_is_the_whole_database(tmp_path: Path) -> None:
    store = Store(tmp_path / "licences.sqlite3")
    store.save(LICENCE)
    store.backup(tmp_path / "copy.sqlite3")
    copy = sqlite3.connect(tmp_path / "copy.sqlite3")
    assert copy.execute("SELECT email FROM licences").fetchall() == [("office@fuse.example",)]
    copy.close()
    store.close()


# -- the service's doors ----------------------------------------------------------------------


class Asked:
    """The service, called the way a WSGI server calls it."""

    def __init__(self, folder: Path, *, mail: bool = False) -> None:
        self.now = [dt.datetime(2026, 9, 29, 12, tzinfo=dt.UTC)]
        self.sent: list[Any] = []
        settings = app.Settings(
            seed=SEED,
            database=folder / "licences.sqlite3",
            admin_token=TOKEN,
            stripe_secret=STRIPE_SECRET,
            smtp_host="smtp.example.com" if mail else "",
            sender="sami@example.com" if mail else "",
        )
        self.service = app.Service(
            settings,
            clock=lambda: self.now[0],
            send=lambda message, **how: self.sent.append((message, how)),
        )

    def __call__(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        token: str | None = TOKEN,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        data = raw if raw is not None else (b"" if body is None else json.dumps(body).encode())
        environ: dict[str, Any] = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(data)),
            "wsgi.input": io.BytesIO(data),
        }
        if token is not None:
            environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        for name, value in (headers or {}).items():
            environ["HTTP_" + name.upper().replace("-", "_")] = value
        said: list[str] = []
        answer = b"".join(self.service(environ, lambda status, _headers: said.append(status)))
        status = int(said[0].split()[0])
        try:
            return status, json.loads(answer)
        except ValueError:
            return status, answer

    def issue(self, **order: Any) -> Licence:
        order.setdefault("email", "office@fuse.example")
        order.setdefault("holder", "Fuse Architects")
        order.setdefault("online", True)
        return self.service.issue(licence_issue.Order(**order))


@pytest.fixture
def asked(tmp_path: Path) -> Asked:
    return Asked(tmp_path)


def test_the_service_says_it_is_up(asked: Asked) -> None:
    assert asked("GET", "/v1/health", token=None) == (200, {"ok": True})
    assert asked("GET", "/v1/nothing", token=None)[0] == 404


def test_a_lease_is_asked_for_with_the_key_and_given_signed(asked: Asked) -> None:
    issued = asked.issue(seats=3)
    status, answer = asked(
        "POST",
        "/v1/lease",
        {"key": issued.key, "machine": HERE.hex(), "name": "amy on PC-1", "build": "1.0.0"},
        token=None,
    )
    assert status == 200
    lease = read_lease(answer["lease"], PUBLIC)
    assert lease.granted
    assert (lease.serial, lease.machine, lease.given) == (issued.serial, HERE, TODAY)
    [seen] = asked.service.store.computers(issued.serial)
    assert (seen.name, seen.build) == ("amy on PC-1", "1.0.0")


@pytest.mark.parametrize(
    ("body", "status", "said"),
    [
        (None, 400, "no licence key"),
        ({"key": "LORIINI-ABCDE", "machine": HERE.hex()}, 403, "cannot accept that key"),
        ({"key": "{key}", "machine": "abc"}, 400, "which computer"),
        ({"key": "{offline}", "machine": HERE.hex()}, 400, "offline licence key"),
    ],
)
def test_a_request_the_service_cannot_answer_says_why(
    asked: Asked, body: dict[str, str] | None, status: int, said: str
) -> None:
    online = asked.issue()
    offline = asked.issue(online=False)
    if body is not None:
        body = {
            name: value.format(key=online.key, offline=offline.key) for name, value in body.items()
        }
    answer = asked("POST", "/v1/lease", body, token=None)
    assert answer[0] == status
    assert said in answer[1]["error"]


def test_a_key_signed_by_anybody_else_is_refused(asked: Asked) -> None:
    _stranger, text = licence_issue.issue(
        licence_issue.Order(email="a@b.example", online=True), bytes(range(1, 33)), serial=1
    )
    status, answer = asked("POST", "/v1/lease", {"key": text, "machine": HERE.hex()}, token=None)
    assert status == 403
    assert "not issued for this build" in answer["error"]


def test_a_key_the_service_signed_but_never_saw_is_taken_in_on_first_use(asked: Asked) -> None:
    """Issued before the service ran, or lost with a database: what the key
    says is where the licence starts."""
    _key, text = licence_issue.issue(
        licence_issue.Order(
            email="old@practice.example",
            holder="Old Practice",
            seats=4,
            online=True,
            paid_to=dt.date(2026, 12, 31),
        ),
        SEED,
        serial=7,
        today=TODAY,
    )
    status, _answer = asked("POST", "/v1/lease", {"key": text, "machine": HERE.hex()}, token=None)
    assert status == 200
    kept = asked.service.store.licence(7)
    assert kept is not None
    assert (kept.holder, kept.seats, kept.paid_to, kept.grace_days) == (
        "Old Practice",
        4,
        dt.date(2026, 12, 31),
        14,
    )
    assert asked.service.store.next_serial() == 8


def test_a_computer_frees_its_seat_with_its_key(asked: Asked) -> None:
    issued = asked.issue()
    asked("POST", "/v1/lease", {"key": issued.key, "machine": HERE.hex()}, token=None)
    assert asked("POST", "/v1/release", {"key": issued.key, "machine": HERE.hex()}, token=None) == (
        200,
        {"released": True},
    )
    assert asked("POST", "/v1/release", {"key": issued.key, "machine": HERE.hex()}, token=None) == (
        200,
        {"released": False},
    )


def test_a_request_too_large_is_refused_unread(asked: Asked) -> None:
    status, _answer = asked("POST", "/v1/lease", raw=b"x" * (app.LONGEST_BODY + 1), token=None)
    assert status == 413


def test_the_vendors_side_needs_the_admin_token(asked: Asked, tmp_path: Path) -> None:
    assert asked("GET", "/v1/admin/licences", token=None)[0] == 401
    assert asked("GET", "/v1/admin/licences", token="guess")[0] == 401
    tokenless = Asked(tmp_path / "other")
    tokenless.service = app.Service(
        app.Settings(seed=SEED, database=tmp_path / "other.sqlite3"), clock=lambda: tokenless.now[0]
    )
    assert tokenless("GET", "/v1/admin/licences")[0] == 403


def test_the_vendor_issues_looks_up_changes_and_frees(tmp_path: Path) -> None:
    asked = Asked(tmp_path, mail=True)
    status, answer = asked(
        "POST",
        "/v1/admin/licences",
        {
            "email": "office@fuse.example",
            "holder": "Fuse Architects",
            "seats": 12,
            "paid_to": "2026-10-31",
            "send": True,
        },
    )
    assert status == 200, answer
    assert answer["licence"]["number"] == "0001"
    assert answer["sent"] is True
    key = licence_key.read(answer["key"], PUBLIC)
    assert key.online and key.expires == dt.date(2026, 10, 31)
    [(message, how)] = asked.sent
    assert message["To"] == "office@fuse.example"
    assert "there is no new key" in message.get_content()
    assert how["host"] == "smtp.example.com"

    asked(
        "POST",
        "/v1/lease",
        {"key": answer["key"], "machine": HERE.hex(), "name": "amy on PC-1"},
        token=None,
    )
    status, detail = asked("GET", "/v1/admin/licences/1")
    assert status == 200
    assert detail["licence"]["in_use"] == 1
    assert detail["computers"][0]["name"] == "amy on PC-1"
    assert detail["key"] == answer["key"]
    assert any("first lease for amy on PC-1" in event["what"] for event in detail["events"])

    status, changed = asked(
        "POST",
        "/v1/admin/licences/1",
        {"paid_to": "2026-11-30", "seats": 14, "withdraw": "refunded"},
    )
    assert status == 200
    assert changed["licence"]["paid_to"] == "2026-11-30"
    assert changed["licence"]["seats"] == 14
    assert changed["licence"]["withdrawn"] == "refunded"
    assert (
        asked("POST", "/v1/admin/licences/1", {"restore": True})[1]["licence"]["withdrawn"] is None
    )
    assert asked("POST", "/v1/admin/licences/1/free", {"computer": "amy on PC-1"})[1] == {
        "freed": 1
    }
    assert asked("POST", "/v1/admin/licences/1/send", {})[1] == {"sent": True}
    assert asked("GET", "/v1/admin/licences/99")[0] == 404
    listed = asked("GET", "/v1/admin/licences")[1]["licences"]
    assert [row["number"] for row in listed] == ["0001"]


def test_trials_and_complimentary_licences_are_issued_as_such(asked: Asked) -> None:
    trial = asked(
        "POST", "/v1/admin/licences", {"email": "try@practice.example", "trial": True, "seats": 3}
    )[1]
    assert trial["licence"]["trial"] is True
    assert trial["licence"]["paid_to"] == "2026-10-12"
    assert trial["licence"]["grace_days"] == 0
    free = asked(
        "POST",
        "/v1/admin/licences",
        {"email": "office@fuse.example", "complimentary": True, "seats": 50},
    )[1]
    assert free["licence"]["paid_to"] is None
    assert free["licence"]["good_to"] is None


def test_the_vendors_settings_reach_every_lease(asked: Asked) -> None:
    issued = asked.issue()
    status, answer = asked(
        "POST",
        "/v1/admin/settings",
        {"minimum_build": "2.0", "recall_reason": "wrong north", "notice": None},
    )
    assert status == 200
    assert answer["settings"] == {"minimum_build": "2.0", "recall_reason": "wrong north"}
    lease = read_lease(
        asked(
            "POST",
            "/v1/lease",
            {"key": issued.key, "machine": HERE.hex(), "build": "1.0"},
            token=None,
        )[1]["lease"],
        PUBLIC,
    )
    assert lease.reason is Reason.RECALLED
    assert "wrong north" in lease.notice
    assert asked("POST", "/v1/admin/settings", {"colour": "red"})[0] == 400


def test_keys_from_the_old_ledger_are_taken_in(asked: Asked) -> None:
    _key, text = licence_issue.issue(
        licence_issue.Order(email="old@practice.example"), SEED, serial=17, today=TODAY
    )
    status, answer = asked("POST", "/v1/admin/register", {"key": text})
    assert status == 200
    assert answer["licence"]["online"] is False
    assert asked.service.store.next_serial() == 18


def test_the_backup_is_the_database_itself(asked: Asked, tmp_path: Path) -> None:
    asked.issue()
    status, data = asked("GET", "/v1/admin/backup")
    assert status == 200
    (tmp_path / "backup.sqlite3").write_bytes(data)
    copy = sqlite3.connect(tmp_path / "backup.sqlite3")
    assert copy.execute("SELECT COUNT(*) FROM licences").fetchone() == (1,)
    copy.close()


def test_a_service_needs_a_signing_key_to_start() -> None:
    with pytest.raises(ValueError, match="LORIINI_SIGNING_KEY"):
        app.Settings.from_environment({})
    with pytest.raises(ValueError, match="not a signing key"):
        app.Settings.from_environment({"LORIINI_SIGNING_KEY": "abcd"})
    settings = app.Settings.from_environment(
        {
            "LORIINI_SIGNING_KEY": SEED.hex(),
            "LORIINI_DATABASE": "/tmp/x.sqlite3",
            "LORIINI_SMTP_PORT": "2525",
        }
    )
    assert signing.public_key(settings.seed) == PUBLIC
    assert settings.smtp_port == 2525


# -- Stripe ----------------------------------------------------------------------------------


def signed(
    event: dict[str, Any], *, secret: str = STRIPE_SECRET, at: float | None = None
) -> tuple[bytes, str]:
    payload = json.dumps(event).encode()
    stamp = str(int(time.time() if at is None else at))
    signature = hmac.new(
        secret.encode(), stamp.encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    return payload, f"t={stamp},v1={signature}"


def stripe(asked: Asked, event: dict[str, Any], **how: Any) -> tuple[int, Any]:
    payload, header = signed(event, **how)
    return asked(
        "POST", "/v1/stripe", raw=payload, token=None, headers={"Stripe-Signature": header}
    )


def event(kind: str, thing: dict[str, Any], identifier: str = "") -> dict[str, Any]:
    return {
        "id": identifier or f"evt_{kind}_{thing.get('id', '')}",
        "type": kind,
        "data": {"object": thing},
    }


def by_subscription(asked: Asked, subscription: str = "sub_1") -> Licence:
    found = asked.service.store.by_subscription(subscription)
    assert found is not None, f"no licence follows {subscription}"
    return found


def stamp(day: dt.date) -> int:
    return int(dt.datetime.combine(day, dt.time(6), dt.UTC).timestamp())


CHECKOUT = {
    "id": "cs_1",
    "mode": "subscription",
    "subscription": "sub_1",
    "customer": "cus_1",
    "customer_details": {"email": "office@fuse.example", "name": "Amy Architect"},
    "custom_fields": [{"key": "practice", "text": {"value": "Fuse Architects"}}],
}


def test_only_stripe_can_tell_the_service_of_a_payment(asked: Asked) -> None:
    payload, header = signed(event("invoice.paid", {"id": "in_1"}))
    assert (
        stripe_events.verify(payload, header, STRIPE_SECRET, now=time.time())["type"]
        == "invoice.paid"
    )
    with pytest.raises(stripe_events.SignatureError, match="not Stripe's"):
        stripe_events.verify(payload, header, "whsec_other", now=time.time())
    with pytest.raises(stripe_events.SignatureError, match="too old"):
        stripe_events.verify(payload, header, STRIPE_SECRET, now=time.time() + 3600)
    with pytest.raises(stripe_events.SignatureError, match="no Stripe signature"):
        stripe_events.verify(payload, "", STRIPE_SECRET, now=time.time())
    assert stripe(asked, event("invoice.paid", {"id": "in_1"}), secret="whsec_other")[0] == 400


def test_a_checkout_makes_a_licence_and_emails_its_key(tmp_path: Path) -> None:
    asked = Asked(tmp_path, mail=True)
    stripe(
        asked,
        event(
            "customer.subscription.created",
            {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "active",
                "items": {"data": [{"quantity": 5}]},
            },
        ),
    )
    stripe(
        asked,
        event(
            "invoice.paid",
            {
                "id": "in_1",
                "subscription": "sub_1",
                "lines": {"data": [{"period": {"end": stamp(dt.date(2026, 10, 29))}}]},
            },
        ),
    )
    status, answer = stripe(asked, event("checkout.session.completed", CHECKOUT))
    assert status == 200
    assert answer["said"] == "checkout: licence 0001 for office@fuse.example"
    made = asked.service.store.by_subscription("sub_1")
    assert made is not None
    assert (made.holder, made.seats, made.paid_to, made.customer) == (
        "Fuse Architects",
        5,
        dt.date(2026, 10, 29),
        "cus_1",
    )
    key = licence_key.read(made.key, PUBLIC)
    assert key.online and key.holder == "Fuse Architects"
    [(message, _how)] = asked.sent
    assert message["To"] == "office@fuse.example"

    # Stripe sends an event again when it is not sure the first arrived.
    again = stripe(asked, event("checkout.session.completed", CHECKOUT))[1]
    assert again["said"].endswith("handled before")
    assert len(asked.service.store.licences()) == 1


def test_a_payment_moves_the_licence_on_and_forgets_a_failed_one(asked: Asked) -> None:
    stripe(asked, event("checkout.session.completed", CHECKOUT))
    stripe(asked, event("invoice.payment_failed", {"id": "in_2", "subscription": "sub_1"}))
    assert by_subscription(asked).payment_failed == TODAY
    # Stripe's shape since its 2025 API versions: the subscription under "parent".
    paid = {
        "id": "in_3",
        "parent": {"subscription_details": {"subscription": "sub_1"}},
        "lines": {"data": [{"period": {"end": stamp(dt.date(2026, 11, 29))}}]},
    }
    stripe(asked, event("invoice.paid", paid))
    licence = by_subscription(asked)
    assert (licence.paid_to, licence.payment_failed) == (dt.date(2026, 11, 29), None)
    # A late event for an earlier period never moves it back.
    stripe(
        asked,
        event(
            "invoice.paid",
            {
                "id": "in_0",
                "subscription": "sub_1",
                "lines": {"data": [{"period": {"end": stamp(dt.date(2026, 10, 29))}}]},
            },
        ),
    )
    assert by_subscription(asked).paid_to == dt.date(2026, 11, 29)


def test_the_seats_follow_the_subscription_and_a_cancellation_drops_the_grace(asked: Asked) -> None:
    stripe(asked, event("checkout.session.completed", CHECKOUT))
    stripe(
        asked,
        event(
            "customer.subscription.updated",
            {"id": "sub_1", "status": "active", "quantity": 8},
            "evt_a",
        ),
    )
    assert by_subscription(asked).seats == 8
    stripe(
        asked,
        event(
            "customer.subscription.updated",
            {
                "id": "sub_1",
                "status": "active",
                "cancel_at_period_end": True,
                "items": {"data": [{"quantity": 8}]},
            },
            "evt_b",
        ),
    )
    assert by_subscription(asked).grace_days == 0
    stripe(
        asked,
        event(
            "customer.subscription.updated",
            {
                "id": "sub_1",
                "status": "active",
                "cancel_at_period_end": False,
                "items": {"data": [{"quantity": 8}]},
            },
            "evt_c",
        ),
    )
    assert by_subscription(asked).grace_days == 14
    stripe(asked, event("customer.subscription.deleted", {"id": "sub_1", "status": "canceled"}))
    assert by_subscription(asked).grace_days == 0


def test_an_event_the_service_has_no_use_for_changes_nothing(asked: Asked) -> None:
    status, answer = stripe(asked, event("charge.refunded", {"id": "ch_1"}))
    assert status == 200
    assert answer["said"] == "charge.refunded: nothing to do"


def test_a_checkout_that_is_not_a_subscription_makes_nothing(asked: Asked) -> None:
    once = {**CHECKOUT, "mode": "payment", "subscription": None}
    assert (
        stripe(asked, event("checkout.session.completed", once))[1]["said"]
        == "checkout: not a subscription"
    )
    assert asked.service.store.licences() == []
