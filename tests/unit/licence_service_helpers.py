"""A licence service on this machine, for the tests that need Loriini to talk to one.

The real thing -- ``licence_service.app.Service`` behind the standard library's
own HTTP server, on a port of its own on 127.0.0.1 -- so that the requests go
over a socket through ``urllib`` exactly as they do from an office, and only
the clock and the mail server are the test's. Keys and leases are signed with
the fixed test pair, never the product's.
"""

from __future__ import annotations

import datetime as dt
import gc
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from wsgiref import simple_server

import pytest

from sun_study import licence_issue, licence_online, licence_public_key, signing
from sun_study.licence_service import app
from sun_study.licence_service.store import Licence

SEED = bytes(range(32))
PUBLIC = signing.public_key(SEED)
TOKEN = "an-admin-token"
STRIPE_SECRET = "whsec_test_secret"


class _Quiet(simple_server.WSGIRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base's name
        pass


@dataclass
class Running:
    """A service answering on ``url``, and what the test can do to it."""

    url: str
    service: app.Service
    sent: list[EmailMessage] = field(default_factory=list)
    now: list[dt.datetime] = field(default_factory=list)

    @property
    def store(self) -> Any:
        return self.service.store

    def set_today(self, day: dt.date) -> None:
        self.now[0] = dt.datetime.combine(day, dt.time(12), dt.UTC)

    def issue(self, **order: Any) -> Licence:
        """A licence issued by the service, as the vendor's script would."""
        order.setdefault("email", "office@fuse.example")
        order.setdefault("holder", "Fuse Architects")
        order.setdefault("online", True)
        return self.service.issue(licence_issue.Order(**order))


@contextmanager
def running(folder: Path, *, today: dt.date | None = None, mail: bool = False) -> Iterator[Running]:
    """The service, on a port of its own, until the ``with`` ends."""
    now = [
        dt.datetime.combine(today, dt.time(12), dt.UTC)
        if today is not None
        else dt.datetime.now(dt.UTC)
    ]
    sent: list[EmailMessage] = []
    settings = app.Settings(
        seed=SEED,
        database=folder / "licences.sqlite3",
        admin_token=TOKEN,
        stripe_secret=STRIPE_SECRET,
        smtp_host="smtp.example.com" if mail else "",
        sender="sami@example.com" if mail else "",
    )
    service = app.Service(
        settings, clock=lambda: now[0], send=lambda message, **_how: sent.append(message)
    )
    server = simple_server.make_server(
        "127.0.0.1", 0, service, server_class=app._Server, handler_class=_Quiet
    )
    # Anything collectable is collected here, on the test's own thread, before
    # the server's thread exists to collect it -- a Tk root among it would
    # abort the process if finalised there (test_licence_box).
    gc.collect()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Running(
            url=f"http://127.0.0.1:{server.server_address[1]}",
            service=service,
            sent=sent,
            now=now,
        )
    finally:
        server.shutdown()
        server.server_close()
        service.store.close()


def trust_the_test_pair(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    """A build that takes keys signed with the test pair, a user folder of its
    own, and no proxy between it and 127.0.0.1."""
    monkeypatch.setattr(licence_public_key, "PUBLIC_KEY", PUBLIC.hex())
    monkeypatch.setattr(licence_public_key, "SERVICE", None)
    monkeypatch.setenv("APPDATA", str(folder / "user"))
    monkeypatch.delenv(licence_online.SERVICE_VAR, raising=False)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")


@contextmanager
def online(monkeypatch: pytest.MonkeyPatch, folder: Path, **how: Any) -> Iterator[Running]:
    """A keyed build pointed at a running service."""
    trust_the_test_pair(monkeypatch, folder)
    with running(folder, **how) as service:
        monkeypatch.setenv(licence_online.SERVICE_VAR, service.url)
        yield service
