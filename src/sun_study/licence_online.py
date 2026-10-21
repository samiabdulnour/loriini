"""Talking to the licence service from Loriini: who this computer is, the lease
it holds, and the two requests it makes.

Roadmap R5's second half (D125). ``licence`` decides when to ask; this module
is how. It decides nothing itself, and the only thing it raises is
``ServiceError``, for any trouble on the way -- the network down, a proxy in
the way, the service answering something that is not a lease -- because to a
start all of those are the same thing: the lease already held is what counts.

Who this computer is
--------------------
A seat is a person on a computer (docs/licence-model.md §2), so the name the
service counts is a one-way hash of Windows' own machine GUID and the user's
name, with the product's name mixed in so that the hash means nothing anywhere
else. The raw values never leave the computer. Where there is no machine GUID
-- a developer's Linux box, a registry that will not say -- a random
identifier is made once and kept in the user's folder instead. With the hash
goes the name the practice would use (``jsmith on FUSE-PC-07``), so that a
list of seats can be read, and the right one freed.

What is sent
------------
The licence key, the hash, that name and this version of Loriini: nothing about
any project. docs/licensing.md says the same to the subscriber.

The lease file
--------------
``licence.lease`` beside the key: the lease exactly as the service signed it,
and the day -- this computer's own -- it was fetched, which is how a start
knows it has already asked today. The day is not signed and needs not be:
changing it only changes when the next renewal is asked for, never how long
the lease runs.
"""

from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import json
import os
import platform
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sun_study import PRODUCT, __version__, licence_public_key, user_folder
from sun_study.licence_lease import MACHINE_BYTES

__all__ = [
    "FALLBACK_SERVICES",
    "LEASE_FILE",
    "SERVICE_VAR",
    "Kept",
    "ServiceError",
    "UnreachableError",
    "addresses",
    "ask_for_lease",
    "forget_lease",
    "keep_lease",
    "kept_lease",
    "lease_path",
    "machine",
    "machine_name",
    "release",
    "service",
]

#: An environment variable naming another licence service than the build's
#: own: for a test, or a service being tried out. It cannot make a lease
#: believable -- only the vendor's signature does that -- so it grants nothing.
SERVICE_VAR = "LORIINI_LICENCE_SERVICE"

#: The lease, beside the key in the user's folder.
LEASE_FILE = "licence.lease"

#: Where a computer with no machine GUID keeps the identifier made for it.
IDENTIFIER_FILE = "computer.id"

#: Seconds to wait for the service: long enough for a slow office link, short
#: enough that a start with no network gives up before anyone wonders.
TIMEOUT = 15.0

#: For freeing a seat when a key is removed, which nobody should wait on.
QUICK_TIMEOUT = 5.0

#: The longest answer read from the service. A lease is a few hundred bytes.
_LONGEST_ANSWER = 64 * 1024

#: Where the same service also answers, asked in turn when the build's own
#: address cannot be reached at all. A practice's firewall can refuse a domain
#: too young to have a reputation: loriini.app was registered on 8 October
#: 2026, and an office that blocks new domains reset every connection to it,
#: while the fly.dev address the service stands on went straight through.
#: Only an address that cannot be reached is passed over -- an answer, even a
#: refusal, is the service's word -- and a lease from here is believed no more
#: than one from anywhere else: only the vendor's signature does that.
FALLBACK_SERVICES: tuple[str, ...] = ("https://loriini-licences.fly.dev",)


class ServiceError(Exception):
    """The licence service could not be asked, or did not answer with a lease.
    The message says which, in a sentence."""


class UnreachableError(ServiceError):
    """Nothing answered at the address asked: the network, a proxy, a firewall."""


def service() -> str | None:
    """Where the licence service is: the environment's word first, then the
    build's own (``licence_public_key.SERVICE``). ``None`` when neither says."""
    return os.environ.get(SERVICE_VAR) or licence_public_key.SERVICE or None


def addresses(first: str) -> list[str]:
    """``first``, then the fallbacks -- but only when ``first`` is the build's
    own address. One named in the environment is somebody's deliberate choice,
    for a test or a service being tried out, and is not second-guessed."""
    own = (licence_public_key.SERVICE or "").rstrip("/")
    if os.environ.get(SERVICE_VAR) or first.rstrip("/") != own:
        return [first]
    return [first, *(other for other in FALLBACK_SERVICES if other.rstrip("/") != own)]


# -- who this computer is ----------------------------------------------------------


def machine() -> bytes:
    """This computer and this user, as the service counts a seat."""
    seed = _machine_guid() or _kept_identifier()
    digest = hashlib.sha256(
        b"Loriini computer\x00"
        + seed.encode("utf-8")
        + b"\x00"
        + _user().casefold().encode("utf-8")
    ).digest()
    return digest[:MACHINE_BYTES]


def machine_name() -> str:
    """``jsmith on FUSE-PC-07``: how a practice tells its seats apart."""
    computer = platform.node() or "this computer"
    user = _user()
    return f"{user} on {computer}" if user else computer


def _user() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):  # pragma: no cover - no user at all
        return ""


def _machine_guid() -> str:
    """Windows' own name for this installation, or ``/etc/machine-id``'s
    elsewhere. Empty when there is none to be had."""
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                value, _kind = winreg.QueryValueEx(key, "MachineGuid")
        except OSError:
            return ""
        return str(value)
    else:
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                found = Path(path).read_text(encoding="ascii").strip()
            except (OSError, UnicodeDecodeError):
                continue
            if found:
                return found
        return ""


def _kept_identifier() -> str:
    """An identifier made once for a computer that has no GUID of its own."""
    where = user_folder() / IDENTIFIER_FILE
    try:
        found = where.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        found = ""
    if found:
        return found
    made = uuid.uuid4().hex
    try:
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(made + "\n", encoding="ascii")
    except OSError:  # pragma: no cover - a folder that cannot be written
        pass
    return made


# -- the two requests ----------------------------------------------------------------


def ask_for_lease(
    key: str,
    *,
    service: str,
    machine: bytes,
    name: str,
    build: str = __version__,
    timeout: float = TIMEOUT,
) -> str:
    """The lease the service gives this computer for ``key``, as it signed it:
    a grant, or a refusal that says why. Believing it is the caller's job."""
    answer = _post(
        service,
        "/v1/lease",
        {"key": key, "machine": machine.hex(), "name": name, "build": build},
        timeout,
    )
    lease = answer.get("lease")
    if not isinstance(lease, str) or not lease:
        raise ServiceError("The licence service answered without a lease.")
    return lease


def release(key: str, *, service: str, machine: bytes, timeout: float = QUICK_TIMEOUT) -> bool:
    """Free this computer's seat. Whether the service freed one."""
    answer = _post(service, "/v1/release", {"key": key, "machine": machine.hex()}, timeout)
    return bool(answer.get("released"))


def _post(service: str, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Ask at ``service`` and, if nothing answers there, at each fallback
    (``addresses``). When none answers, the first address's trouble is the one
    said, because that is the address a person would look up."""
    first: UnreachableError | None = None
    for address in addresses(service):
        try:
            return _post_once(address, path, body, timeout)
        except UnreachableError as trouble:
            first = first or trouble
    assert first is not None
    raise first


def _post_once(service: str, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        service.rstrip("/") + path,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"{PRODUCT}/{__version__}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(_LONGEST_ANSWER)
    except urllib.error.HTTPError as error:
        raise ServiceError(_what_the_service_said(error)) from error
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", None) or error
        raise UnreachableError(
            f"Loriini could not reach the licence service ({reason})."
        ) from error
    try:
        answer = json.loads(data)
    except ValueError as error:
        raise ServiceError("The licence service's answer could not be read.") from error
    if not isinstance(answer, dict):
        raise ServiceError("The licence service's answer could not be read.")
    return answer


def _what_the_service_said(error: urllib.error.HTTPError) -> str:
    """The sentence a service error carries, or its status when it carries none."""
    try:
        said = json.loads(error.read(_LONGEST_ANSWER)).get("error")
    except (ValueError, AttributeError, OSError):
        said = None
    if isinstance(said, str) and said:
        return f"The licence service said: {said}"
    return f"The licence service could not answer ({error.code} {error.reason})."


# -- the lease file ----------------------------------------------------------------------


@dataclass(frozen=True)
class Kept:
    """The lease held, as the service signed it, and the day it was fetched."""

    text: str
    fetched: dt.date


def lease_path() -> Path:
    return user_folder() / LEASE_FILE


def kept_lease() -> Kept | None:
    """The lease this user holds, unread. ``None`` for none, or a file that is
    not one -- which is the same thing to a start."""
    try:
        held = json.loads(lease_path().read_text(encoding="utf-8"))
        return Kept(text=str(held["lease"]), fetched=dt.date.fromisoformat(held["fetched"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def keep_lease(text: str, fetched: dt.date) -> bool:
    """Keep a lease, replacing the one held. False when it could not be written
    -- another Loriini reading it at that instant, on Windows -- which only means
    the next start asks again."""
    where = lease_path()
    staged = where.with_name(where.name + ".new")
    try:
        where.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(
            json.dumps({"lease": text, "fetched": fetched.isoformat()}) + "\n", encoding="utf-8"
        )
        staged.replace(where)
    except OSError:
        return False
    return True


def forget_lease() -> None:
    try:
        lease_path().unlink()
    except FileNotFoundError:
        pass
