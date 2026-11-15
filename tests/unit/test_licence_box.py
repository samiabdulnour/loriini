"""The licence box, and the window asking for a key before it opens.

Roadmap R5 (D124). The keys are signed with the test pair the other licence
tests use; the build is told to trust it for each test, and the user's folder
is a temporary one, so nothing here reads or writes a real licence.
"""

from __future__ import annotations

import datetime as dt
import gc
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

# Skipped, not collected into an error, where Tk cannot be had.
if TYPE_CHECKING:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter", reason="this machine has no tkinter")

from sun_study import licence, licence_key, licence_public_key, signing
from sun_study.app import licence_box
from sun_study.licence_key import LicenceKey

SEED = bytes(range(32))
PUBLIC = signing.public_key(SEED)


def _key(
    expires: dt.date = dt.date(2100, 1, 1),
    seed: bytes = SEED,
    issued: dt.date = dt.date(2026, 9, 29),
) -> str:
    return licence_key.make(
        LicenceKey(42, "office@fuse.example", "Fuse Architects", 12, issued, expires), seed
    )


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(licence_public_key, "PUBLIC_KEY", PUBLIC.hex())
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path / "Loriini" / licence.KEY_FILE


@pytest.fixture
def root() -> Any:
    try:
        window = tk.Tk()
    except tk.TclError:  # pragma: no cover - a machine with no display
        pytest.skip("no display for Tk")
    window.withdraw()
    yield window
    window.destroy()
    # Finalised here, on the thread that made it: Tcl aborts the process if an
    # interpreter is deleted from another thread, and the tests below run a
    # licence service on one -- whose garbage collection would otherwise be
    # the one that reaches this root.
    del window
    gc.collect()


def _paste(box: licence_box.LicenceBox, text: str) -> None:
    box.text.delete("1.0", "end")
    box.text.insert("1.0", text)
    box._changed()


def test_the_line_under_the_key_says_what_it_is_as_it_is_pasted(keyed: Path, root: Any) -> None:
    box = licence_box.LicenceBox(root, first=True)
    try:
        assert box.says.cget("text") == licence_box.WAITING
        assert str(box.use.cget("state")) == "disabled"

        _paste(box, "\n".join(licence_key.lines(_key())))
        assert box.says.cget("text").startswith("This is licence 0042, Fuse Architects")
        assert str(box.use.cget("state")) == "normal"

        _paste(box, _key()[:-6])
        assert "not the whole key" in box.says.cget("text")
        assert str(box.says.cget("style")) == "Refused.TLabel"
        assert str(box.use.cget("state")) == "disabled"

        _paste(box, _key(seed=bytes(range(1, 33))))
        assert "not a licence key for this Loriini" in box.says.cget("text")

        _paste(box, _key(expires=dt.date(2025, 1, 31), issued=dt.date(2025, 1, 1)))
        assert "ended on 31 January 2025" in box.says.cget("text")
        assert str(box.use.cget("state")) == "disabled"
    finally:
        box.destroy()


def test_using_a_key_keeps_it_and_answers_it(keyed: Path, root: Any) -> None:
    box = licence_box.LicenceBox(root, first=False)
    _paste(box, _key())
    box._use()

    assert box.result is not None and box.result.serial == 42
    assert keyed.read_text(encoding="utf-8").strip() == _key()
    assert licence.standing().usable


def test_a_keyed_build_asks_before_the_window_and_opens_nothing_without_a_key(
    keyed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sun_study.app import window

    asked: list[bool] = []
    built: list[bool] = []

    def refuse(parent: object, *, first: bool = False) -> None:
        asked.append(first)
        return None

    monkeypatch.setattr(licence_box, "ask", refuse)
    monkeypatch.setattr(window, "Window", lambda root: built.append(True))
    try:
        window.launch()
    except tk.TclError:  # pragma: no cover - a machine with no display
        pytest.skip("no display for Tk")

    assert asked == [True], "asked once, as the first start"
    assert not built, "closed without a key, nothing opens"


def test_a_build_holding_a_good_key_opens_straight_away(
    keyed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sun_study.app import window

    licence.install(_key())
    asked: list[bool] = []

    class Opened:
        def __init__(self, root: Any) -> None:
            root.after(10, root.destroy)

    monkeypatch.setattr(licence_box, "ask", lambda *a, **k: asked.append(True))
    monkeypatch.setattr(window, "Window", Opened)
    try:
        window.launch()
    except tk.TclError:  # pragma: no cover - a machine with no display
        pytest.skip("no display for Tk")

    assert not asked


# -- online keys (D125) -------------------------------------------------------------------


def _settle(root: Any, box: Any, seconds: float = 15.0) -> None:
    """Let the box run until it closes, or its check is answered."""
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        if not box.winfo_exists():
            return
        if box.checking is None and box.says.cget("text") != licence_box.CHECKING:
            return
        time.sleep(0.02)


def test_an_online_key_is_checked_with_the_service_before_the_box_closes(
    root: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.unit.licence_service_helpers import online

    with online(monkeypatch, tmp_path) as service:
        issued = service.issue(seats=3)
        box = licence_box.LicenceBox(root, first=True)
        _paste(box, issued.key)
        assert "Loriini checks it with the licence service" in box.says.cget("text")
        box._use()
        assert box.says.cget("text") == licence_box.CHECKING
        _settle(root, box)

        assert not box.winfo_exists(), "granted: the box closed"
        assert box.result is not None and box.result.serial == issued.serial
        assert licence.standing().usable


def test_a_refusal_is_said_in_red_and_can_be_asked_again(
    root: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.unit.licence_service_helpers import online

    with online(monkeypatch, tmp_path) as service:
        issued = service.issue()
        row = service.store.licence(issued.serial)
        service.store.save(type(row)(**{**row.__dict__, "withdrawn": "unpaid"}))
        box = licence_box.LicenceBox(root, first=True)
        try:
            _paste(box, issued.key)
            box._use()
            _settle(root, box)
            assert box.winfo_exists()
            assert "has been withdrawn: unpaid" in box.says.cget("text")
            assert str(box.says.cget("style")) == "Refused.TLabel"
            assert box.again.winfo_ismapped() or box.again.grid_info()

            service.store.save(type(row)(**{**row.__dict__, "withdrawn": None}))
            box.try_again()
            _settle(root, box)
            assert not box.winfo_exists(), "restored: asked again, granted, closed"
        finally:
            if box.winfo_exists():
                box.destroy()


def test_a_start_with_an_online_key_and_no_lease_opens_the_box_already_asking(
    root: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.unit.licence_service_helpers import online

    with online(monkeypatch, tmp_path) as service:
        licence.install(service.issue().key)
        box = licence_box.LicenceBox(root, first=True)
        _settle(root, box)
        assert not box.winfo_exists(), "the lease was fetched without anything pressed"
        assert licence.standing().usable


def test_the_info_box_checks_an_online_licence_on_the_spot(
    root: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import time

    from sun_study.app import about, theme
    from tests.unit.licence_service_helpers import online

    with online(monkeypatch, tmp_path) as service:
        licence.install(service.issue(seats=4).key)
        licence.renew()
        theme.apply(root)
        # Shown, as the window is whenever its About button can be pressed.
        # On a Mac the box opened over a withdrawn root is withdrawn with it,
        # and root.update() then never returns: the macOS suite hung here
        # from 20 October until its 30-minute cancel.
        root.deiconify()
        box = about.show(root)
        try:
            assert box._check.grid_info(), "Check now is there for an online key"
            box._check_now()
            deadline = time.monotonic() + 15
            while box._waiting is not None and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert "1 of 4 seats in use" in box._holder.cget("text")
        finally:
            box._close()


def test_the_info_box_says_whose_licence_in_a_keyed_build(keyed: Path, root: Any) -> None:
    from sun_study.app import about, theme

    licence.install(_key())
    theme.apply(root)
    box = about.show(root)
    try:
        assert box._holder.cget("text").startswith("Licensed: licence 0042, Fuse Architects")
    finally:
        box._close()


# -- logging out --------------------------------------------------------------------------


def _log_out(root: Any, window: Any, monkeypatch: pytest.MonkeyPatch, answer: Any) -> list[str]:
    """Press Log out in the info box over ``window``, say yes, and let it run
    until the box has gone. What the licence box was told, each time it was
    asked; ``answer`` is what it gives back."""
    import time
    from tkinter import messagebox

    from sun_study.app import about, theme

    told: list[str] = []

    def ask(parent: Any, *, first: bool = False, said: str = "") -> Any:
        assert first, "asked as a first start is"
        told.append(said)
        return answer() if callable(answer) else answer

    monkeypatch.setattr(messagebox, "askokcancel", lambda *a, **k: True)
    monkeypatch.setattr(licence_box, "ask", ask)
    theme.apply(root)
    box = about.show(window)
    try:
        assert box._log_out.grid_info(), "Log out is there for a key held"
        box._log_out_asked()
        deadline = time.monotonic() + 15
        while box.winfo_exists() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)
    finally:
        if box.winfo_exists():
            box._close()
    return told


def test_logging_out_frees_the_seat_and_asks_for_a_key_again(
    root: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.unit.licence_service_helpers import online

    with online(monkeypatch, tmp_path) as service:
        issued = service.issue(seats=4)
        licence.install(issued.key)
        licence.renew()
        window = tk.Toplevel(root)
        told = _log_out(root, window, monkeypatch, None)

        [computer] = service.store.computers(issued.serial)
        assert computer.freed is not None, "the seat was freed with the service"
    assert not licence.key_path().exists()
    assert len(told) == 1 and told[0].startswith("Logged out. Removed the licence key")
    assert told[0].endswith("Its seat is free for another computer.")
    assert not window.winfo_exists(), "closed without a key, the window goes with the box"


def test_a_key_given_after_logging_out_brings_the_window_back_and_says_so(
    keyed: Path, root: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    licence.install(_key())
    window = tk.Toplevel(root)
    changed: list[bool] = []
    window.bind(licence_box.LICENCE_CHANGED, lambda _event: changed.append(True))
    another = _key(expires=dt.date(2099, 1, 1))

    try:
        told = _log_out(root, window, monkeypatch, lambda: licence.install(another))

        assert len(told) == 1 and told[0].startswith("Logged out.")
        assert window.winfo_exists() and window.state() == "normal"
        assert changed, "the window was told, so its foot says whose licence now"
        assert keyed.read_text(encoding="utf-8").strip() == another
    finally:
        window.destroy()


def test_a_log_out_called_off_keeps_the_key(
    keyed: Path, root: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tkinter import messagebox

    from sun_study.app import about, theme

    licence.install(_key())
    monkeypatch.setattr(messagebox, "askokcancel", lambda *a, **k: False)
    theme.apply(root)
    box = about.show(root)
    try:
        box._log_out_asked()
        assert box._waiting is None, "nothing started"
        assert keyed.exists()
        assert licence.standing().usable
    finally:
        box._close()
