"""The window on a Mac: its type and its Dock icon.

The two things the window does differently there, each tested by telling the
theme it is on a Mac, and then -- where there is a display -- against the Tk
the suite is running on, so ci-macos.yml checks them on a real one.

The Tk-free half of the Mac version is test_macos.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

# Skipped, not collected into an error, where Tk cannot be had -- the guard
# test_app and test_theme use, and for the same reason.
if TYPE_CHECKING:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
else:
    tk = pytest.importorskip("tkinter", reason="this machine has no tkinter")
    from tkinter import font as tkfont
    from tkinter import ttk

from sun_study.app import theme, window


def _root() -> tk.Tk:
    """A hidden interpreter, or a skip where there is no display for one."""
    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - a machine with no display
        pytest.skip("no display for Tk")
    root.withdraw()
    return root


# -- the type -----------------------------------------------------------------


def test_a_mac_asks_for_four_thirds_of_each_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same pixels as Windows: 9 points are 12 pixels there, and an older
    Mac Tk counts a point as a pixel. Off a Mac, nothing changes at all."""
    monkeypatch.setattr(theme, "MACOS", True)
    monkeypatch.setattr(theme, "MAC_POINTS", 4 / 3)
    assert [theme.points(size) for size in (5, 7, 8, 9, 10)] == [7, 9, 11, 12, 13]

    monkeypatch.setattr(theme, "MACOS", False)
    assert [theme.points(size) for size in range(4, 16)] == list(range(4, 16))


class _Scaled:
    """Stands in for a root: answers ``tk scaling`` and nothing else."""

    def __init__(self, scaling: float) -> None:
        self.tk = self
        self.scaling = scaling

    def call(self, *_args: object) -> float:
        return self.scaling


@pytest.mark.parametrize(("scaling", "nine"), [(1.0, 12), (96 / 72, 9), (2.0, 6)])
def test_a_mac_point_is_fitted_to_what_its_tk_makes_of_one(
    monkeypatch: pytest.MonkeyPatch, scaling: float, nine: int
) -> None:
    """Tk 9 already counts 1.33 pixels to a Mac point, and four thirds on top
    of that set every word a third too big. The factor comes from the Tk, so
    9 points are 12 pixels whichever Tk it is."""
    monkeypatch.setattr(theme, "MACOS", True)
    monkeypatch.setattr(theme, "MAC_POINTS", 4 / 3)
    theme._fit_points(_Scaled(scaling))  # type: ignore[arg-type]
    assert theme.points(9) == nine
    assert round(theme.points(9) * scaling) == 12


def test_the_window_is_set_at_the_size_its_platform_asks_for() -> None:
    """Through the theme, on the Tk this is running on: 9 everywhere but a Mac,
    12 there -- and the face Tk resolves is a real one either way, which on a
    Mac is the system's own."""
    root = _root()
    try:
        theme.apply(root)
        body = tkfont.Font(root=root, font=ttk.Style(root).lookup(".", "font"))
        assert body.actual("size") == theme.points(9)
        assert body.actual("family")
        log = tkfont.Font(root=root, font=theme.log_font())
        assert log.actual("size") == theme.points(9)
    finally:
        root.destroy()


def test_the_lettering_on_a_thumbnail_is_scaled_like_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sheet's words are set at the window's own scale, so on a Mac they
    grow by the same factor as every other word on the screen."""
    monkeypatch.setattr(theme, "MACOS", True)
    monkeypatch.setattr(theme, "MAC_POINTS", 4 / 3)
    drawn = window._face(9, True)
    assert drawn[1] == 12


# -- the Dock's icon ----------------------------------------------------------


def window_icon() -> Path:
    """Where the window looks for the Dock's picture in a checkout."""
    return Path(window.__file__).resolve().parents[3] / "assets" / window.MAC_DOCK_ICON


class _Dock:
    """Stands in for the root: records what the Dock is given."""

    def __init__(self) -> None:
        self.given: list[tuple[bool, tuple[Any, ...]]] = []

    def iconphoto(self, default: bool, *images: Any) -> None:
        self.given.append((default, images))

    def iconbitmap(self, **kwargs: Any) -> None:  # pragma: no cover - the PC's call
        raise AssertionError("a Mac was given the PC's .ico")


def test_a_mac_window_started_from_a_checkout_wears_the_png_in_the_dock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Started from a checkout the window is Python's and would wear Python's
    rocket. The PNG goes to the Dock, for every window it will open."""
    monkeypatch.setattr(theme, "MACOS", True)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(tk, "PhotoImage", lambda **kwargs: ("picture", kwargs["file"]))
    dock = _Dock()

    window.wear_the_icon(dock)  # type: ignore[arg-type]

    assert len(dock.given) == 1
    default, images = dock.given[0]
    assert default, "the dialogs opened later should wear it too"
    assert images == (("picture", str(window_icon())),)


def test_the_dock_icon_is_in_the_checkout() -> None:
    assert window_icon().is_file(), "the Mac window's Dock icon must be in the checkout"
    assert window_icon().read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_packaged_mac_program_keeps_the_icon_its_bundle_gives_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loriini.app carries its icon in the bundle, in every size the Dock
    asks for; one PNG set over it would only be worse."""
    monkeypatch.setattr(theme, "MACOS", True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    dock = _Dock()

    window.wear_the_icon(dock)  # type: ignore[arg-type]

    assert dock.given == []


def test_a_mac_checkout_without_the_picture_still_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    """How the window looks, not whether it opens -- the rule the PC's icon
    follows too."""
    monkeypatch.setattr(theme, "MACOS", True)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(window, "MAC_DOCK_ICON", "not-there.png")
    dock = _Dock()

    window.wear_the_icon(dock)  # type: ignore[arg-type]

    assert dock.given == []


def test_a_real_mac_window_takes_the_dock_icon(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same call against Tk itself, which is where a Mac runner proves the
    picture loads and the Dock accepts it; elsewhere it proves the call is at
    least one Tk takes."""
    monkeypatch.setattr(theme, "MACOS", True)
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = _root()
    try:
        window.wear_the_icon(root)
    finally:
        root.destroy()
