"""sun_study.updates: whether a newer Loriini is out, and when to say so (D198)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import http.server
import json
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from sun_study import updates

TODAY = dt.date(2026, 11, 20)


@pytest.fixture(autouse=True)
def own_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """What is learnt is kept somewhere disposable, never in the developer's
    own settings."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


class Site:
    """The site's latest.json, served from a port of its own, counting asks."""

    def __init__(self) -> None:
        self.body = b""
        self.status = 200
        self.asked = 0

    def url(self, port: int) -> str:
        return f"http://127.0.0.1:{port}/latest.json"


@pytest.fixture
def site() -> Iterator[tuple[Site, str]]:
    served = Site()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            served.asked += 1
            self.send_response(served.status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(served.body)

        def log_message(self, *_: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield served, served.url(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


def _nowhere() -> str:
    """An address nothing answers at: a port taken and let go."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}/latest.json"


def _latest(windows: str = "1.1.0", macos: str = "1.1.0") -> bytes:
    return json.dumps(
        {
            "page": "https://loriini.app/download",
            "windows": {"version": windows, "built": "1 December 2026"},
            "macos": {"version": macos, "built": "1 December 2026"},
        }
    ).encode()


# -- which version is newer ---------------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "than", "newer"),
    [
        ("1.0.1", "1.0.0", True),
        ("1.1", "1.0.0", True),
        ("1.10.0", "1.9.0", True),
        ("2.0.0", "1.99.99", True),
        ("1.0.0", "1.0.0", False),
        ("1.0", "1.0.0", False),
        ("0.0.1", "1.0.0", False),
        ("", "1.0.0", False),
        ("1.1.0-beta", "1.0.0", False),
        ("latest", "1.0.0", False),
    ],
)
def test_only_a_higher_number_is_newer(candidate: str, than: str, newer: bool) -> None:
    assert updates.is_newer(candidate, than) is newer


def test_each_platform_reads_its_own_build() -> None:
    answer = _latest(windows="1.2.0", macos="1.1.0")
    assert updates.read_latest(answer, "windows") == "1.2.0"
    assert updates.read_latest(answer, "macos") == "1.1.0"


def test_a_file_naming_no_build_for_this_platform_says_nothing_is_out() -> None:
    answer = json.dumps({"page": "https://loriini.app/download"}).encode()
    assert updates.read_latest(answer, "windows") == ""
    weird = json.dumps({"windows": {"version": "soon"}}).encode()
    assert updates.read_latest(weird, "windows") == ""


def test_a_file_that_is_not_latest_json_is_refused() -> None:
    with pytest.raises(ValueError):
        updates.read_latest(b"<html>a captive portal</html>", "windows")
    with pytest.raises(ValueError):
        updates.read_latest(b"[1, 2]", "windows")


# -- asking the site ----------------------------------------------------------------


def test_the_site_is_asked_and_the_answer_kept(site: tuple[Site, str]) -> None:
    served, url = site
    served.body = _latest()
    state = updates.check(TODAY, sources=(url,))
    assert state.latest == "1.1.0"
    assert state.checked == TODAY
    assert updates.known() == state, "kept for the next start"
    assert updates.newer(current="1.0.0") == "1.1.0"


def test_the_site_is_asked_once_a_day(site: tuple[Site, str]) -> None:
    served, url = site
    served.body = _latest()
    updates.check(TODAY, sources=(url,))
    updates.check(TODAY, sources=(url,))
    assert served.asked == 1
    assert updates.check_in_background(TODAY) is None, "no thread for an answer already kept"
    updates.check(TODAY + dt.timedelta(days=1), sources=(url,))
    assert served.asked == 2


def test_an_address_that_does_not_answer_is_passed_over(site: tuple[Site, str]) -> None:
    """The fly.dev address stands behind loriini.app for an office whose
    firewall refuses the younger domain."""
    served, url = site
    served.body = _latest()
    state = updates.check(TODAY, sources=(_nowhere(), url), timeout=2.0)
    assert state.latest == "1.1.0"


def test_no_network_changes_nothing_and_raises_nothing(site: tuple[Site, str]) -> None:
    served, url = site
    served.body = _latest()
    updates.check(TODAY, sources=(url,))
    tomorrow = TODAY + dt.timedelta(days=1)
    state = updates.check(tomorrow, sources=(_nowhere(),), timeout=2.0)
    assert state.latest == "1.1.0", "what was learnt still stands"
    assert state.checked == TODAY, "so the next start asks again"


def test_an_error_page_is_no_answer(site: tuple[Site, str]) -> None:
    served, url = site
    served.status = 503
    served.body = b"busy"
    state = updates.check(TODAY, sources=(url,))
    assert state == updates.Known()


def test_the_background_check_keeps_its_answer(
    site: tuple[Site, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    served, url = site
    served.body = _latest()
    monkeypatch.setattr(updates, "SOURCES", (url,))
    thread = updates.check_in_background(TODAY)
    assert thread is not None
    thread.join(10)
    assert updates.known().latest == "1.1.0"


# -- when to say so -----------------------------------------------------------------


def _learnt(version: str) -> None:
    updates._keep(updates.Known(checked=TODAY, latest=version))


def test_nothing_is_said_when_this_is_the_newest() -> None:
    _learnt("1.0.0")
    assert updates.reminder_due(TODAY, current="1.0.0") == ""
    _learnt("0.0.1")
    assert updates.reminder_due(TODAY, current="1.0.0") == ""


def test_a_new_version_is_said_once_and_then_weekly() -> None:
    _learnt("1.1.0")
    assert updates.reminder_due(TODAY, current="1.0.0") == "1.1.0"
    updates.reminded("1.1.0", TODAY)
    assert updates.reminder_due(TODAY, current="1.0.0") == "", "not again the same day"
    six = TODAY + dt.timedelta(days=6)
    assert updates.reminder_due(six, current="1.0.0") == "", "nor that week"
    seven = TODAY + dt.timedelta(days=7)
    assert updates.reminder_due(seven, current="1.0.0") == "1.1.0", "a week on, once more"


def test_a_newer_version_still_is_said_at_once() -> None:
    _learnt("1.1.0")
    updates.reminded("1.1.0", TODAY)
    updates._keep(dataclasses.replace(updates.known(), latest="1.2.0"))
    assert updates.reminder_due(TODAY, current="1.0.0") == "1.2.0"


def test_installing_the_new_version_ends_the_reminders() -> None:
    _learnt("1.1.0")
    assert updates.reminder_due(TODAY, current="1.1.0") == ""


def test_a_check_does_not_forget_a_reminder_noted_while_it_asked(
    site: tuple[Site, str],
) -> None:
    served, url = site
    served.body = _latest()
    _learnt("1.1.0")
    updates.reminded("1.1.0", TODAY)
    updates.check(TODAY + dt.timedelta(days=1), sources=(url,))
    kept = updates.known()
    assert kept.reminded == TODAY
    assert kept.reminded_of == "1.1.0"


def test_a_damaged_file_is_nothing_known() -> None:
    where = updates._path()
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text("{not json", encoding="utf-8")
    assert updates.known() == updates.Known()
    assert updates.reminder_due(TODAY) == ""
