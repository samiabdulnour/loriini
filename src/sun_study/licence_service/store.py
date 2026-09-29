"""What the licence service keeps: the licences, the computers using them, a log.

One SQLite file, so that the whole of the service's memory is one file to back
up and one file to restore. The licences are the ledger: what
``scripts/licence.py`` kept in ``licences.csv`` beside the signing key before
the service ran lives here once it does, key text and all, so a lost email is
still answered by sending the same key again.

Every write goes through one lock. The service answers a few hundred requests
a day at most, and a lease decision reads a licence's computers and then
writes one of them, which must not interleave with another decision for the
same licence -- the lock is the simplest thing that makes that true.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

__all__ = ["Computer", "Event", "Licence", "Store", "Subscription"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS licences (
    serial INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    holder TEXT NOT NULL DEFAULT '',
    seats INTEGER NOT NULL,
    paid_to TEXT,
    grace_days INTEGER NOT NULL,
    trial INTEGER NOT NULL DEFAULT 0,
    online INTEGER NOT NULL DEFAULT 1,
    withdrawn TEXT,
    subscription TEXT UNIQUE,
    customer TEXT,
    payment_failed TEXT,
    issued TEXT,
    key TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS computers (
    serial INTEGER NOT NULL,
    machine TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    build TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    freed TEXT,
    PRIMARY KEY (serial, machine)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    serial INTEGER,
    what TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stripe_events (
    id TEXT PRIMARY KEY,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    quantity INTEGER,
    paid_to TEXT,
    ended INTEGER NOT NULL DEFAULT 0
);
"""


def _date(text: str | None) -> dt.date | None:
    return dt.date.fromisoformat(text) if text else None


def _iso(when: dt.date | None) -> str | None:
    return when.isoformat() if when is not None else None


@dataclass(frozen=True)
class Licence:
    """One licence, as the service holds it."""

    serial: int
    email: str
    holder: str
    seats: int
    paid_to: dt.date | None
    """The last day paid for; ``None`` for a licence not paid for by the period
    -- complimentary, and never lapsing."""
    grace_days: int
    """Days past ``paid_to`` a lease may still run: the payment provider's
    retries. None for a trial, and none once a subscription is cancelled."""
    trial: bool = False
    online: bool = True
    withdrawn: str | None = None
    """Why the vendor withdrew it, or ``None``."""
    subscription: str | None = None
    """The Stripe subscription it follows."""
    customer: str | None = None
    payment_failed: dt.date | None = None
    """The day a payment failed, while the provider is still retrying it."""
    issued: dt.date | None = None
    key: str = ""
    """The key as issued, to send again."""
    note: str = ""

    @property
    def number(self) -> str:
        return f"{self.serial:04d}"

    @property
    def good_to(self) -> dt.date | None:
        """The last day a lease may reach, or ``None`` for no end."""
        if self.paid_to is None:
            return None
        return self.paid_to + dt.timedelta(days=self.grace_days)

    def summary(self) -> dict[str, Any]:
        return {
            "serial": self.serial,
            "number": self.number,
            "email": self.email,
            "holder": self.holder,
            "seats": self.seats,
            "paid_to": _iso(self.paid_to),
            "grace_days": self.grace_days,
            "good_to": _iso(self.good_to),
            "trial": self.trial,
            "online": self.online,
            "withdrawn": self.withdrawn,
            "subscription": self.subscription,
            "customer": self.customer,
            "payment_failed": _iso(self.payment_failed),
            "issued": _iso(self.issued),
            "note": self.note,
        }


@dataclass(frozen=True)
class Computer:
    """A computer that has used a licence: one seat, while it is in use."""

    serial: int
    machine: str
    """The hash Loriini sends (``licence_online.machine``), in hex."""
    name: str
    build: str
    first_seen: dt.date
    last_seen: dt.date
    freed: dt.date | None = None

    def in_use(self, today: dt.date, lease_days: int) -> bool:
        """Whether its last lease could still be in force: seen in the last
        ``lease_days`` and not freed since."""
        return self.freed is None and self.last_seen + dt.timedelta(days=lease_days) >= today

    def summary(self) -> dict[str, Any]:
        return {
            "machine": self.machine,
            "name": self.name,
            "build": self.build,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "freed": _iso(self.freed),
        }


@dataclass(frozen=True)
class Event:
    at: str
    serial: int | None
    what: str


@dataclass(frozen=True)
class Subscription:
    """What Stripe has said about a subscription before its licence exists:
    its events do not arrive in the order they happened."""

    id: str
    quantity: int | None = None
    paid_to: dt.date | None = None
    ended: bool = False


class Store:
    """The service's SQLite file."""

    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock, self._db:
            self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self.lock:
            self._db.close()

    @contextmanager
    def _writing(self) -> Iterator[sqlite3.Connection]:
        with self.lock, self._db:
            yield self._db

    # -- licences --------------------------------------------------------------------

    def licence(self, serial: int) -> Licence | None:
        with self.lock:
            row = self._db.execute("SELECT * FROM licences WHERE serial = ?", (serial,)).fetchone()
        return _licence(row) if row is not None else None

    def licences(self) -> list[Licence]:
        with self.lock:
            rows = self._db.execute("SELECT * FROM licences ORDER BY serial").fetchall()
        return [_licence(row) for row in rows]

    def by_subscription(self, subscription: str) -> Licence | None:
        with self.lock:
            row = self._db.execute(
                "SELECT * FROM licences WHERE subscription = ?", (subscription,)
            ).fetchone()
        return _licence(row) if row is not None else None

    def save(self, licence: Licence) -> Licence:
        with self._writing() as db:
            db.execute(
                "INSERT OR REPLACE INTO licences (serial, email, holder, seats, paid_to, "
                "grace_days, trial, online, withdrawn, subscription, customer, payment_failed, "
                "issued, key, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    licence.serial,
                    licence.email,
                    licence.holder,
                    licence.seats,
                    _iso(licence.paid_to),
                    licence.grace_days,
                    int(licence.trial),
                    int(licence.online),
                    licence.withdrawn,
                    licence.subscription,
                    licence.customer,
                    _iso(licence.payment_failed),
                    _iso(licence.issued),
                    licence.key,
                    licence.note,
                ),
            )
        return licence

    def next_serial(self) -> int:
        """One more than the highest licence number known, or than the floor
        the vendor set when the service took over from the ledger."""
        with self.lock:
            highest = self._db.execute("SELECT MAX(serial) FROM licences").fetchone()[0]
        floor = int(self.setting("serial_floor") or 0)
        return max(highest or 0, floor) + 1

    # -- computers -------------------------------------------------------------------

    def computers(self, serial: int) -> list[Computer]:
        with self.lock:
            rows = self._db.execute(
                "SELECT * FROM computers WHERE serial = ? ORDER BY last_seen DESC, name",
                (serial,),
            ).fetchall()
        return [
            Computer(
                serial=row["serial"],
                machine=row["machine"],
                name=row["name"],
                build=row["build"],
                first_seen=dt.date.fromisoformat(row["first_seen"]),
                last_seen=dt.date.fromisoformat(row["last_seen"]),
                freed=_date(row["freed"]),
            )
            for row in rows
        ]

    def seen(self, serial: int, machine: str, name: str, build: str, today: dt.date) -> None:
        """A computer given a lease today; its seat taken again if it was freed."""
        with self._writing() as db:
            db.execute(
                "INSERT INTO computers (serial, machine, name, build, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (serial, machine) DO UPDATE SET "
                "name = excluded.name, build = excluded.build, last_seen = excluded.last_seen, "
                "freed = NULL",
                (serial, machine, name, build, today.isoformat(), today.isoformat()),
            )

    def free(self, serial: int, which: str, today: dt.date) -> int:
        """Free the seat of the computer named ``which`` -- its hash, or the
        name its user would give it. How many seats were freed."""
        with self._writing() as db:
            cursor = db.execute(
                "UPDATE computers SET freed = ? WHERE serial = ? AND freed IS NULL "
                "AND (machine = ? OR name = ? COLLATE NOCASE)",
                (today.isoformat(), serial, which, which),
            )
        return cursor.rowcount

    # -- the log, the settings, and Stripe's own bookkeeping -------------------------

    def log(self, what: str, serial: int | None = None) -> None:
        at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        with self._writing() as db:
            db.execute("INSERT INTO events (at, serial, what) VALUES (?, ?, ?)", (at, serial, what))

    def events(self, serial: int | None = None, limit: int = 50) -> list[Event]:
        with self.lock:
            if serial is None:
                rows = self._db.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM events WHERE serial = ? ORDER BY id DESC LIMIT ?",
                    (serial, limit),
                ).fetchall()
        return [Event(at=row["at"], serial=row["serial"], what=row["what"]) for row in rows]

    def setting(self, name: str) -> str | None:
        with self.lock:
            row = self._db.execute("SELECT value FROM settings WHERE name = ?", (name,)).fetchone()
        return row["value"] if row is not None else None

    def settings(self) -> dict[str, str]:
        with self.lock:
            rows = self._db.execute("SELECT name, value FROM settings ORDER BY name").fetchall()
        return {row["name"]: row["value"] for row in rows}

    def set_setting(self, name: str, value: str | None) -> None:
        with self._writing() as db:
            if value is None or value == "":
                db.execute("DELETE FROM settings WHERE name = ?", (name,))
            else:
                db.execute(
                    "INSERT INTO settings (name, value) VALUES (?, ?) "
                    "ON CONFLICT (name) DO UPDATE SET value = excluded.value",
                    (name, value),
                )

    def handled(self, event: str) -> bool:
        """Whether a Stripe event was handled before: Stripe sends one again
        when it is not sure the first arrived."""
        with self.lock:
            row = self._db.execute("SELECT 1 FROM stripe_events WHERE id = ?", (event,)).fetchone()
        return row is not None

    def mark_handled(self, event: str) -> None:
        at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        with self._writing() as db:
            db.execute("INSERT OR IGNORE INTO stripe_events (id, at) VALUES (?, ?)", (event, at))

    def subscription(self, subscription: str) -> Subscription:
        with self.lock:
            row = self._db.execute(
                "SELECT * FROM subscriptions WHERE id = ?", (subscription,)
            ).fetchone()
        if row is None:
            return Subscription(id=subscription)
        return Subscription(
            id=row["id"],
            quantity=row["quantity"],
            paid_to=_date(row["paid_to"]),
            ended=bool(row["ended"]),
        )

    def note_subscription(self, subscription: Subscription) -> None:
        with self._writing() as db:
            db.execute(
                "INSERT OR REPLACE INTO subscriptions (id, quantity, paid_to, ended) "
                "VALUES (?, ?, ?, ?)",
                (
                    subscription.id,
                    subscription.quantity,
                    _iso(subscription.paid_to),
                    int(subscription.ended),
                ),
            )

    def backup(self, target: Path) -> None:
        """A consistent copy of the whole file, taken while the service runs."""
        copy = sqlite3.connect(str(target))
        try:
            with self.lock:
                self._db.backup(copy)
        finally:
            copy.close()


def _licence(row: sqlite3.Row) -> Licence:
    return Licence(
        serial=row["serial"],
        email=row["email"],
        holder=row["holder"],
        seats=row["seats"],
        paid_to=_date(row["paid_to"]),
        grace_days=row["grace_days"],
        trial=bool(row["trial"]),
        online=bool(row["online"]),
        withdrawn=row["withdrawn"],
        subscription=row["subscription"],
        customer=row["customer"],
        payment_failed=_date(row["payment_failed"]),
        issued=_date(row["issued"]),
        key=row["key"],
        note=row["note"],
    )


# ``replace`` is how a licence is changed: re-exported for the other modules.
changed = replace
