"""The licence service's web side: the requests it answers, and how it runs.

Four doors, and a fifth for whatever watches it:

- ``POST /v1/lease`` -- Loriini asking for a lease (``licence_online``).
- ``POST /v1/release`` -- Loriini freeing its seat as its key is removed.
- ``POST /v1/stripe`` -- Stripe telling of a payment (``stripe_events``).
- ``/v1/admin/...`` -- the vendor's script, with the admin token: issue a key,
  look a licence up, change it, withdraw it, recall a version, back up.
- ``GET /v1/health`` -- up or not.

Everything is JSON except the backup, which is the SQLite file itself. A
request body is refused unread past ``LONGEST_BODY``, and an error's answer is
a sentence (``{"error": ...}``) for whoever asked to show: Loriini shows it,
and so does the script.

A key is its own proof of possession: a lease or a release is asked for with
the key's text, and the service reads it with the same public key a build
carries, so it answers only for keys it signed. A key it has never seen but
did sign -- one issued before the service ran, or one whose record was lost
with a database -- is taken in on first use, from what the key says.

Settings come from the environment (``Settings.from_environment``), which is
where a container host keeps secrets: the signing key, the admin token,
Stripe's webhook secret, the mail server. The service keeps nothing else
outside its database.
"""

from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import smtplib
import socketserver
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from http import HTTPStatus
from pathlib import Path
from typing import Any
from wsgiref import simple_server

from sun_study import licence_issue, signing
from sun_study.licence_key import KeyRefusedError, LicenceKey, read, tidy
from sun_study.licence_lease import MACHINE_BYTES
from sun_study.licence_lease import make as make_lease
from sun_study.licence_service import stripe_events
from sun_study.licence_service.decide import LEASE_DAYS, Terms, decide
from sun_study.licence_service.store import Licence, Store

__all__ = ["LONGEST_BODY", "SETTABLE", "Service", "Settings", "serve"]

#: The largest request body read. A lease request is a few hundred bytes, and
#: Stripe's events are a few kilobytes.
LONGEST_BODY = 256 * 1024

#: What the vendor can set for every lease (``Terms``), and the floor under
#: licence numbers when the service takes over from a ledger.
SETTABLE = ("minimum_build", "recall_reason", "download", "portal", "notice", "serial_floor")

#: Days of grace past a paid-to date: Stripe's retries of a failed card run
#: up to two weeks (docs/licence-model.md §5).
GRACE_DAYS = 14

_Answer = tuple[int, list[tuple[str, str]], bytes]


class _RefusedError(Exception):
    """A request answered with an error: its status, and the sentence."""

    def __init__(self, status: int, sentence: str) -> None:
        super().__init__(sentence)
        self.status = status
        self.sentence = sentence


@dataclass(frozen=True)
class Settings:
    """How this service is set up."""

    seed: bytes
    """The vendor's private signing key: the one whose public half builds carry."""
    database: Path
    admin_token: str = ""
    stripe_secret: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    sender: str = ""
    grace_days: int = GRACE_DAYS
    lease_days: int = LEASE_DAYS

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """From ``LORIINI_SIGNING_KEY`` (or ``..._FILE``), ``LORIINI_DATABASE``,
        ``LORIINI_ADMIN_TOKEN``, ``STRIPE_WEBHOOK_SECRET``, ``LORIINI_SMTP_HOST``,
        ``..._PORT``, ``..._USER``, ``..._PASSWORD`` and ``LORIINI_MAIL_FROM``."""
        env = os.environ if environ is None else environ
        written = env.get("LORIINI_SIGNING_KEY", "").strip()
        from_file = env.get("LORIINI_SIGNING_KEY_FILE", "").strip()
        if written:
            try:
                seed = bytes.fromhex(written)
            except ValueError as error:
                raise ValueError("LORIINI_SIGNING_KEY is not a signing key") from error
            if len(seed) != signing.KEY_BYTES:
                raise ValueError("LORIINI_SIGNING_KEY is not a signing key")
        elif from_file:
            seed = licence_issue.read_signing_key(Path(from_file))
        else:
            raise ValueError("Set LORIINI_SIGNING_KEY, or LORIINI_SIGNING_KEY_FILE.")
        return cls(
            seed=seed,
            database=Path(env.get("LORIINI_DATABASE", "/data/licences.sqlite3")),
            admin_token=env.get("LORIINI_ADMIN_TOKEN", ""),
            stripe_secret=env.get("STRIPE_WEBHOOK_SECRET", ""),
            smtp_host=env.get("LORIINI_SMTP_HOST", ""),
            smtp_port=int(env.get("LORIINI_SMTP_PORT", "587")),
            smtp_user=env.get("LORIINI_SMTP_USER", ""),
            smtp_password=env.get("LORIINI_SMTP_PASSWORD", ""),
            sender=env.get("LORIINI_MAIL_FROM", ""),
        )


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Service:
    """The licence service, as a WSGI application."""

    def __init__(
        self,
        settings: Settings,
        store: Store | None = None,
        *,
        clock: Callable[[], dt.datetime] = _utc_now,
        send: Callable[..., None] = licence_issue.send,
    ) -> None:
        self.settings = settings
        self.store = store if store is not None else Store(settings.database)
        self.public = signing.public_key(settings.seed)
        self._clock = clock
        self._send = send

    def today(self) -> dt.date:
        """The service's day: UTC's, whatever the host's zone."""
        return self._clock().astimezone(dt.UTC).date()

    def terms(self) -> Terms:
        kept = self.store.settings()
        return Terms(
            lease_days=self.settings.lease_days,
            minimum_build=kept.get("minimum_build", ""),
            recall_reason=kept.get("recall_reason", ""),
            download=kept.get("download", ""),
            portal=kept.get("portal", ""),
            notice=kept.get("notice", ""),
        )

    # -- WSGI ------------------------------------------------------------------------

    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> Iterable[bytes]:
        try:
            status, headers, body = self._answer(environ)
        except _RefusedError as refused:
            status, headers, body = _json(refused.status, {"error": refused.sentence})
        except Exception:  # a request must never take the service down
            traceback.print_exc(file=sys.stderr)
            status, headers, body = _json(500, {"error": "The licence service had a problem."})
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [body]

    def _answer(self, environ: dict[str, Any]) -> _Answer:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "")).rstrip("/") or "/"
        if path == "/v1/health" and method == "GET":
            return _json(200, {"ok": True})
        if path == "/v1/lease" and method == "POST":
            return _json(200, self.lease(_body(environ)))
        if path == "/v1/release" and method == "POST":
            return _json(200, self.release(_body(environ)))
        if path == "/v1/stripe" and method == "POST":
            return _json(
                200, self.stripe(_raw(environ), str(environ.get("HTTP_STRIPE_SIGNATURE", "")))
            )
        if path.startswith("/v1/admin/"):
            self._authorise(environ)
            return self._admin(method, path.removeprefix("/v1/admin/").split("/"), environ)
        raise _RefusedError(404, "There is nothing here.")

    # -- Loriini's two requests ---------------------------------------------------------

    def _key(self, body: Mapping[str, Any]) -> tuple[LicenceKey, str]:
        text = body.get("key")
        if not isinstance(text, str) or not text.strip():
            raise _RefusedError(400, "The request carries no licence key.")
        try:
            return read(text, self.public), tidy(text)
        except KeyRefusedError as refused:
            raise _RefusedError(
                403, f"The licence service cannot accept that key. {refused}"
            ) from refused

    @staticmethod
    def _machine(body: Mapping[str, Any]) -> bytes:
        try:
            machine = bytes.fromhex(str(body.get("machine", "")))
        except ValueError:
            machine = b""
        if len(machine) != MACHINE_BYTES:
            raise _RefusedError(400, "The request does not say which computer it is for.")
        return machine

    def lease(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """The lease a computer gets: a grant, or a refusal that says why."""
        key, text = self._key(body)
        machine = self._machine(body)
        if not key.online:
            raise _RefusedError(
                400, "That is an offline licence key: Loriini checks it without the service."
            )
        name = str(body.get("name", ""))[:120]
        build = str(body.get("build", ""))[:40]
        today = self.today()
        with self.store.lock:
            licence = self.store.licence(key.serial) or self._first_sight(key, text)
            computers = self.store.computers(key.serial)
            lease = decide(
                licence,
                computers,
                machine=machine,
                build=build,
                today=today,
                terms=self.terms(),
            )
            label = name or machine.hex()
            if lease.granted:
                if not any(c.machine == machine.hex() for c in computers):
                    self.store.log(f"first lease for {label} ({build})", key.serial)
                self.store.seen(key.serial, machine.hex(), name, build, today)
            else:
                self.store.log(f"refused {label}: {lease.reason.name.lower()}", key.serial)
        return {"lease": make_lease(lease, self.settings.seed)}

    def _first_sight(self, key: LicenceKey, text: str) -> Licence:
        """A key the service signed but has no record of: taken in from what it
        says, the first period's end as its paid-to date."""
        licence = Licence(
            serial=key.serial,
            email=key.email,
            holder=key.holder,
            seats=key.seats,
            paid_to=None if key.expires >= licence_issue.NO_END else key.expires,
            grace_days=0 if key.trial else self.settings.grace_days,
            trial=key.trial,
            online=key.online,
            issued=key.issued,
            key=text,
        )
        self.store.save(licence)
        self.store.log("taken in on first use", key.serial)
        return licence

    def release(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Free a computer's seat."""
        key, _text = self._key(body)
        machine = self._machine(body)
        freed = self.store.free(key.serial, machine.hex(), self.today())
        if freed:
            self.store.log(f"seat freed by {machine.hex()}", key.serial)
        return {"released": bool(freed)}

    # -- Stripe ----------------------------------------------------------------------

    def stripe(self, payload: bytes, signature: str) -> dict[str, Any]:
        try:
            event = stripe_events.verify(
                payload, signature, self.settings.stripe_secret, now=time.time()
            )
        except stripe_events.SignatureError as refused:
            raise _RefusedError(400, str(refused)) from refused
        said = stripe_events.handle(
            event,
            self.store,
            today=self.today(),
            grace_days=self.settings.grace_days,
            subscribe=self.subscribe,
        )
        print(f"stripe: {said}", flush=True)
        return {"received": True, "said": said}

    def subscribe(
        self,
        *,
        email: str,
        holder: str,
        seats: int,
        paid_to: dt.date,
        subscription: str,
        customer: str | None,
        ended: bool = False,
    ) -> Licence:
        """A new subscriber: a licence, its online key issued and emailed."""
        today = self.today()
        order = licence_issue.Order(
            email=email,
            holder=holder,
            seats=seats,
            starts=today,
            paid_to=max(paid_to, today),
            online=True,
        )
        licence = self.issue(
            order, subscription=subscription, customer=customer, grace_days=0 if ended else None
        )
        self.send_key(licence)
        return licence

    def issue(
        self,
        order: licence_issue.Order,
        *,
        subscription: str | None = None,
        customer: str | None = None,
        grace_days: int | None = None,
        note: str = "",
    ) -> Licence:
        """Issue a key for ``order`` under the next licence number, and keep it."""
        today = self.today()
        with self.store.lock:
            serial = self.store.next_serial()
            key, text = licence_issue.issue(order, self.settings.seed, serial=serial, today=today)
            complimentary = key.online and key.expires >= licence_issue.NO_END
            if key.trial:
                grace = 0
            elif grace_days is not None:
                grace = grace_days
            else:
                grace = self.settings.grace_days if key.online else 0
            paid_to: dt.date | None
            if complimentary:
                paid_to = None
            elif key.online:
                paid_to = key.expires
            else:
                paid_to = key.expires - dt.timedelta(days=order.grace_days)
            licence = self.store.save(
                Licence(
                    serial=serial,
                    email=key.email,
                    holder=key.holder,
                    seats=key.seats,
                    paid_to=paid_to,
                    grace_days=grace,
                    trial=key.trial,
                    online=key.online,
                    subscription=subscription,
                    customer=customer,
                    issued=key.issued,
                    key=text,
                    note=note,
                )
            )
            kind = "trial" if key.trial else "online" if key.online else "offline"
            self.store.log(f"issued ({kind}) to {key.email}", serial)
        return licence

    def send_key(self, licence: Licence) -> bool:
        """Email a licence its key. False when there is no mail server set, or
        it refused; the log says which."""
        settings = self.settings
        if not (settings.smtp_host and settings.sender):
            self.store.log("key not emailed: no mail server set", licence.serial)
            return False
        key = read(licence.key, self.public)
        message = licence_issue.email(key, licence.key, sender=settings.sender)
        try:
            self._send(
                message,
                host=settings.smtp_host,
                port=settings.smtp_port,
                user=settings.smtp_user or None,
                password=settings.smtp_password or None,
            )
        except (OSError, smtplib.SMTPException) as error:
            self.store.log(f"key not emailed to {licence.email}: {error}", licence.serial)
            return False
        self.store.log(f"key emailed to {licence.email}", licence.serial)
        return True

    # -- the vendor's side -------------------------------------------------------------

    def _authorise(self, environ: Mapping[str, Any]) -> None:
        token = self.settings.admin_token
        if not token:
            raise _RefusedError(403, "This service has no admin token set.")
        given = str(environ.get("HTTP_AUTHORIZATION", ""))
        if not hmac.compare_digest(given.encode("utf-8"), f"Bearer {token}".encode()):
            raise _RefusedError(401, "That is not this service's admin token.")

    def _admin(self, method: str, parts: list[str], environ: dict[str, Any]) -> _Answer:
        if parts == ["licences"] and method == "GET":
            return _json(200, {"licences": [self._summary(lic) for lic in self.store.licences()]})
        if parts == ["licences"] and method == "POST":
            return _json(200, self._issue_asked(_body(environ)))
        if parts == ["register"] and method == "POST":
            return _json(200, self._register(_body(environ)))
        if parts == ["settings"] and method == "GET":
            return _json(200, {"settings": self.store.settings()})
        if parts == ["settings"] and method == "POST":
            return _json(200, self._set(_body(environ)))
        if parts == ["backup"] and method == "GET":
            return self._backup()
        if len(parts) >= 2 and parts[0] == "licences" and parts[1].isdigit():
            licence = self.store.licence(int(parts[1]))
            if licence is None:
                raise _RefusedError(404, f"There is no licence {int(parts[1]):04d}.")
            rest = parts[2:]
            if rest == [] and method == "GET":
                return _json(200, self._detail(licence))
            if rest == [] and method == "POST":
                return _json(200, self._change(licence, _body(environ)))
            if rest == ["free"] and method == "POST":
                return _json(200, self._free(licence, _body(environ)))
            if rest == ["send"] and method == "POST":
                return _json(200, {"sent": self.send_key(licence)})
        raise _RefusedError(404, "There is nothing here.")

    def _summary(self, licence: Licence) -> dict[str, Any]:
        in_use = [
            c
            for c in self.store.computers(licence.serial)
            if c.in_use(self.today(), self.settings.lease_days)
        ]
        return licence.summary() | {"in_use": len(in_use)}

    def _detail(self, licence: Licence) -> dict[str, Any]:
        today = self.today()
        computers = self.store.computers(licence.serial)
        return {
            "licence": self._summary(licence),
            "key": licence.key,
            "computers": [
                c.summary() | {"in_use": c.in_use(today, self.settings.lease_days)}
                for c in computers
            ],
            "events": [
                {"at": event.at, "what": event.what} for event in self.store.events(licence.serial)
            ],
        }

    def _issue_asked(self, body: Mapping[str, Any]) -> dict[str, Any]:
        email = str(body.get("email", "")).strip()
        if "@" not in email:
            raise _RefusedError(400, "An email address is needed for a licence.")
        try:
            order = licence_issue.Order(
                email=email,
                holder=str(body.get("holder", "")),
                seats=int(body.get("seats", 1)),
                months=int(body.get("months", 12)),
                starts=_optional_date(body.get("starts")),
                paid_to=_optional_date(body.get("paid_to")),
                grace_days=int(body.get("grace_days", licence_issue.GRACE_DAYS)),
                online=not body.get("offline", False),
                trial=bool(body.get("trial", False)),
                days=int(body.get("days", licence_issue.TRIAL_DAYS)),
                complimentary=bool(body.get("complimentary", False)),
            )
            licence = self.issue(order, note=str(body.get("note", "")))
        except (TypeError, ValueError) as error:
            raise _RefusedError(400, f"That order cannot be issued: {error}") from error
        sent = self.send_key(licence) if body.get("send") else False
        return {"licence": self._summary(licence), "key": licence.key, "sent": sent}

    def _register(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Take in a key issued before the service ran, from the old ledger."""
        key, text = self._key(body)
        paid_to = _optional_date(body.get("paid_to"))
        with self.store.lock:
            licence = self.store.licence(key.serial)
            if licence is None:
                licence = self._first_sight(key, text)
            if paid_to is not None:
                licence = self.store.save(replace(licence, paid_to=paid_to))
                self.store.log(f"paid to {paid_to.isoformat()} (registered)", key.serial)
        return {"licence": self._summary(licence)}

    def _change(self, licence: Licence, body: Mapping[str, Any]) -> dict[str, Any]:
        """The vendor's changes to one licence, each logged."""
        changed = licence
        said: list[str] = []
        try:
            if "paid_to" in body:
                changed = replace(
                    changed, paid_to=_optional_date(body["paid_to"]), payment_failed=None
                )
                said.append(f"paid to {body['paid_to'] or 'no end'}")
            if "seats" in body:
                seats = int(body["seats"])
                if not 1 <= seats < 2**16:
                    raise ValueError(f"{seats} seats")
                changed = replace(changed, seats=seats)
                said.append(f"{seats} seats")
            if "grace_days" in body:
                changed = replace(changed, grace_days=max(0, int(body["grace_days"])))
                said.append(f"{changed.grace_days} days' grace")
            if "withdraw" in body:
                changed = replace(changed, withdrawn=str(body["withdraw"] or "").strip())
                said.append(f"withdrawn: {changed.withdrawn or 'no reason given'}")
            if body.get("restore"):
                changed = replace(changed, withdrawn=None)
                said.append("restored")
            if "email" in body:
                changed = replace(changed, email=str(body["email"]).strip())
                said.append("email changed")
            if "holder" in body:
                changed = replace(changed, holder=str(body["holder"]).strip())
                said.append("holder changed")
            if "note" in body:
                changed = replace(changed, note=str(body["note"]))
                said.append("note changed")
        except (TypeError, ValueError) as error:
            raise _RefusedError(400, f"That change cannot be made: {error}") from error
        if changed != licence:
            self.store.save(changed)
            self.store.log("; ".join(said) + " (by the vendor)", licence.serial)
        return {"licence": self._summary(changed)}

    def _free(self, licence: Licence, body: Mapping[str, Any]) -> dict[str, Any]:
        which = str(body.get("computer", "")).strip()
        if not which:
            raise _RefusedError(400, "Say which computer: its name, or its hash.")
        freed = self.store.free(licence.serial, which, self.today())
        if freed:
            self.store.log(f"seat of {which} freed (by the vendor)", licence.serial)
        return {"freed": freed}

    def _set(self, body: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(body) - set(SETTABLE))
        if unknown:
            raise _RefusedError(400, f"Nothing called {', '.join(unknown)} can be set.")
        for name in SETTABLE:
            if name in body:
                value = body[name]
                self.store.set_setting(name, None if value is None else str(value))
                self.store.log(f"setting {name}: {value or 'cleared'}")
        return {"settings": self.store.settings()}

    def _backup(self) -> _Answer:
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "licences.sqlite3"
            self.store.backup(copy)
            data = copy.read_bytes()
        stamp = self._clock().strftime("%Y%m%d-%H%M")
        return (
            200,
            [
                ("Content-Type", "application/vnd.sqlite3"),
                ("Content-Length", str(len(data))),
                ("Content-Disposition", f'attachment; filename="licences-{stamp}.sqlite3"'),
                ("Cache-Control", "no-store"),
            ],
            data,
        )


def _optional_date(value: Any) -> dt.date | None:
    if value is None or value == "":
        return None
    return dt.date.fromisoformat(str(value))


def _raw(environ: Mapping[str, Any]) -> bytes:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > LONGEST_BODY:
        raise _RefusedError(413, "That request is larger than any this service answers.")
    stream = environ.get("wsgi.input")
    return stream.read(length) if stream is not None and length > 0 else b""


def _body(environ: Mapping[str, Any]) -> dict[str, Any]:
    raw = _raw(environ)
    try:
        body = json.loads(raw or b"{}")
    except ValueError as error:
        raise _RefusedError(400, "The request is not JSON.") from error
    if not isinstance(body, dict):
        raise _RefusedError(400, "The request is not a JSON object.")
    return body


def _json(status: int, answer: Mapping[str, Any]) -> _Answer:
    data = json.dumps(answer).encode("utf-8")
    return (
        status,
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "no-store"),
        ],
        data,
    )


# -- running it ---------------------------------------------------------------------------


class _Server(socketserver.ThreadingMixIn, simple_server.WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(simple_server.WSGIRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base's name
        print(f"{self.client_address[0]} {format % args}", flush=True)


def serve(service: Service, *, host: str = "0.0.0.0", port: int = 8080) -> None:
    """Answer requests until stopped. Behind the host's TLS: the container
    platform terminates HTTPS and passes plain HTTP on."""
    with simple_server.make_server(
        host, port, service, server_class=_Server, handler_class=_Handler
    ) as server:
        print(f"Licence service answering on {host}:{port}", flush=True)
        server.serve_forever()
