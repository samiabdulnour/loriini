"""Whether a newer Loriini is out, and when to say so (D198).

The website is the update server. Each time the site is put up, the
*Website* workflow writes ``latest.json`` beside its pages from the two
builds it serves (``scripts/site_download.py``): which version the Windows
folder is and which the Mac folder is. The program asks for that file once
a day, in the background, keeps the answer in the user's folder, and the
window mentions it in two places only:

- when the window is closed: once for a new version, and after that at most
  once a week, a question whose Yes opens the download page;
- in the menu: an entry that opens the download page, named for the new
  version when there is one.

Nothing is downloaded or installed here. The download page is where a build
comes from, as it was before. Nothing is waited on either: with no network,
behind a firewall that refuses the site, on a slow link, the window never
knows, and the next day it asks again. Only a higher version number counts as
new, so the builds made between two releases, which all carry the same
number, are never announced.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sun_study import PRODUCT, WEBSITE, __version__, user_folder

__all__ = [
    "DOWNLOAD_PAGE",
    "REMIND_AGAIN",
    "SOURCES",
    "Known",
    "check",
    "check_in_background",
    "is_newer",
    "known",
    "newer",
    "read_latest",
    "reminded",
    "reminder_due",
]

#: Where the site says which builds it serves, asked in turn. The fly.dev
#: address is the same site, for an office whose firewall refuses a domain as
#: young as loriini.app (``licence_online.FALLBACK_SERVICES`` says how that was
#: found out).
SOURCES: tuple[str, ...] = (
    f"{WEBSITE}/latest.json",
    "https://loriini-site.fly.dev/latest.json",
)

#: Where a new build is fetched from: the page every Yes and every menu entry opens.
DOWNLOAD_PAGE = f"{WEBSITE}/download"

#: What was learnt, beside the settings in the user's folder.
STATE_FILE = "updates.json"

#: Seconds to wait for the site. Nobody waits on it, but a thread left hanging
#: on a dead connection is a thread nobody needs.
TIMEOUT = 5.0

#: The longest answer read. The file is a few hundred bytes.
_LONGEST_ANSWER = 16 * 1024

#: After a reminder, how long before the same version is mentioned again.
REMIND_AGAIN = dt.timedelta(days=7)

#: What a version looks like: numbers and dots, as ``__version__`` is written.
_VERSION = re.compile(r"^\d+(?:\.\d+){0,3}$")

#: One check at a time, and no write of the kept state crossing another.
_lock = threading.Lock()


def platform_key() -> str:
    """Which build this program is, as ``latest.json`` names it."""
    return "macos" if sys.platform == "darwin" else "windows"


def _numbers(version: str) -> tuple[int, ...]:
    """``"1.2.10"`` as ``(1, 2, 10)`` with trailing zeros dropped, so 1.0 and
    1.0.0 are the same version and 1.10 comes after 1.9."""
    numbers = [int(part) for part in version.split(".")]
    while numbers and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def is_newer(candidate: str, than: str = __version__) -> bool:
    """Whether ``candidate`` is a later version than ``than``. Anything that
    is not a version is never newer."""
    if not _VERSION.match(candidate) or not _VERSION.match(than):
        return False
    return _numbers(candidate) > _numbers(than)


@dataclass(frozen=True)
class Known:
    """What the program has learnt about newer versions, kept between starts."""

    checked: dt.date | None = None
    """The day the site last answered."""
    latest: str = ""
    """The version of this platform's build the site serves, as it last said."""
    reminded: dt.date | None = None
    """The day the closing question was last asked."""
    reminded_of: str = ""
    """The version it was asked about."""


def _path() -> Path:
    return user_folder() / STATE_FILE


def _day(text: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if isinstance(text, str) and text else None
    except ValueError:
        return None


def known() -> Known:
    """What was kept, or nothing known when there is no file or it cannot be read."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Known()
    if not isinstance(data, dict):
        return Known()
    latest = data.get("latest", "")
    reminded_of = data.get("reminded_of", "")
    return Known(
        checked=_day(data.get("checked")),
        latest=latest if isinstance(latest, str) and _VERSION.match(latest) else "",
        reminded=_day(data.get("reminded")),
        reminded_of=reminded_of if isinstance(reminded_of, str) else "",
    )


def _keep(state: Known) -> None:
    """Write what was learnt. A folder that cannot be written to costs only
    the memory: the site is asked again, and a reminder may come again."""
    data = {
        "checked": state.checked.isoformat() if state.checked else "",
        "latest": state.latest,
        "reminded": state.reminded.isoformat() if state.reminded else "",
        "reminded_of": state.reminded_of,
    }
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def newer(state: Known | None = None, current: str = __version__) -> str:
    """The newer version known of, or ``""`` when this one is the newest."""
    state = known() if state is None else state
    return state.latest if is_newer(state.latest, current) else ""


def reminder_due(today: dt.date | None = None, current: str = __version__) -> str:
    """The version to mention as the window closes, or ``""`` to say nothing.

    A version not yet mentioned is mentioned at once. After that it waits
    ``REMIND_AGAIN``, so the question is a reminder rather than a toll on
    every close.
    """
    today = today or dt.date.today()
    state = known()
    version = newer(state, current)
    if not version:
        return ""
    if state.reminded_of != version or state.reminded is None:
        return version
    return version if today - state.reminded >= REMIND_AGAIN else ""


def reminded(version: str, today: dt.date | None = None) -> None:
    """Note that ``version`` was mentioned today."""
    with _lock:
        _keep(replace(known(), reminded=today or dt.date.today(), reminded_of=version))


def read_latest(answer: bytes, platform: str | None = None) -> str:
    """This platform's version out of ``latest.json``: ``""`` when the file
    names no build for it. ``ValueError`` when it is not that file at all."""
    data = json.loads(answer)
    if not isinstance(data, dict):
        raise ValueError("latest.json is not an object")
    build = data.get(platform or platform_key())
    if not isinstance(build, dict):
        return ""
    version = build.get("version", "")
    return version if isinstance(version, str) and _VERSION.match(version) else ""


def _ask(source: str, timeout: float) -> str:
    """One address's answer, read. Raises on anything short of that."""
    # Imported here: the certificate roots are loaded once, and only by a
    # program that asks the network for something.
    from sun_study.site.http import TRUST

    request = urllib.request.Request(
        source, headers={"User-Agent": f"{PRODUCT}/{__version__} ({platform_key()})"}
    )
    with urllib.request.urlopen(request, timeout=timeout, context=TRUST) as response:
        return read_latest(response.read(_LONGEST_ANSWER))


def fetch_latest(sources: tuple[str, ...] | None = None, timeout: float = TIMEOUT) -> str | None:
    """The version the site serves for this platform, from the first address
    that answers with the file (``SOURCES`` unless told otherwise); ``None``
    when none does."""
    for source in SOURCES if sources is None else sources:
        try:
            return _ask(source, timeout)
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return None


def check(
    today: dt.date | None = None,
    sources: tuple[str, ...] | None = None,
    timeout: float = TIMEOUT,
) -> Known:
    """Ask the site, at most once a day, and keep what it said.

    A day the site cannot be reached leaves everything as it was, so the next
    start asks again and the version learnt last time still stands.
    """
    today = today or dt.date.today()
    if known().checked == today:
        return known()
    found = fetch_latest(sources, timeout)
    with _lock:
        # Read again: a reminder may have been noted while the site was asked.
        state = known()
        if found is None:
            return state
        state = replace(state, checked=today, latest=found)
        _keep(state)
        return state


def check_in_background(today: dt.date | None = None) -> threading.Thread | None:
    """``check`` on a thread of its own, so the window never waits on the
    network. Nothing is started when today's answer is already kept."""
    today = today or dt.date.today()
    if known().checked == today:
        return None
    thread = threading.Thread(
        target=check, kwargs={"today": today}, name="loriini-update-check", daemon=True
    )
    thread.start()
    return thread
