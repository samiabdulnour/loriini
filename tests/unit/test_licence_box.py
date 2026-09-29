"""The licence box, and the window asking for a key before it opens.

Roadmap R5 (D124). The keys are signed with the test pair the other licence
tests use; the build is told to trust it for each test, and the user's folder
is a temporary one, so nothing here reads or writes a real licence.
"""

from __future__ import annotations

import datetime as dt
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


def test_the_info_box_says_whose_licence_in_a_keyed_build(keyed: Path, root: Any) -> None:
    from sun_study.app import about, theme

    licence.install(_key())
    theme.apply(root)
    box = about.show(root)
    try:
        assert box._holder.cget("text").startswith("Licensed: licence 0042, Fuse Architects")
    finally:
        box._close()
