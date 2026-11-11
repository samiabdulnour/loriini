"""Movement in the window: a page settling in as it opens, and none of it
where the system has been asked for none."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter", reason="this machine has no tkinter")

from sun_study.app import motion


def _root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - a machine with no display
        pytest.skip("no display for Tk")
    root.withdraw()
    return root


def test_a_page_arrives_fast_and_stops_gently() -> None:
    """Cubic ease-out: all the way at the end, nowhere at the start, past
    halfway well before half the time, and never going back."""
    assert motion.ease_out(0.0) == 0.0
    assert motion.ease_out(1.0) == 1.0
    assert motion.ease_out(0.25) > 0.5, "most of the way early"
    steps = [motion.ease_out(step / 20) for step in range(21)]
    assert steps == sorted(steps), "never back"
    assert motion.ease_out(-1.0) == 0.0 and motion.ease_out(2.0) == 1.0, "held to 0..1"


def test_the_whole_movement_is_small_and_quick() -> None:
    """Twelve pixels and under a fifth of a second: seen as movement, never
    waited for. A test so a tidy-minded tweak cannot make the window bounce."""
    assert motion.DISTANCE <= 16
    assert motion.DURATION_MS <= 200


def test_a_slide_starts_off_its_mark_and_ends_on_it() -> None:
    root = _root()
    try:
        canvas = tk.Canvas(root)
        frame = tk.Frame(canvas)
        item = canvas.create_window((0, 0), window=frame, anchor="nw")
        ended: list[bool] = []
        slide = motion.Slide(canvas, item, 12, done=lambda: ended.append(True), duration_ms=40)
        assert canvas.coords(item) == [0.0, 12.0], "off its mark at once"
        deadline = root.tk.call("clock", "milliseconds") + 1000
        while not slide.finished and root.tk.call("clock", "milliseconds") < deadline:
            root.update()
        assert slide.finished and canvas.coords(item) == [0.0, 0.0]
        assert ended == [True], "told once"
    finally:
        root.destroy()


def test_a_frame_that_came_late_does_not_swallow_the_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page is painted for the first time just after it opens, and that one
    paint used to take a third of the slide with it: the page was seen at 12
    px, at 9, and next at 3. A late frame is charged two beats and no more."""
    root = _root()
    try:
        canvas = tk.Canvas(root)
        frame = tk.Frame(canvas)
        item = canvas.create_window((0, 0), window=frame, anchor="nw")
        clock = [100.0]
        monkeypatch.setattr("time.monotonic", lambda: clock[0])
        slide = motion.Slide(canvas, item, 12)
        clock[0] += 0.150  # the paint: most of the slide's 180 ms
        slide._frame()
        along = motion.HITCH_MS / motion.DURATION_MS
        assert canvas.coords(item) == [0.0, round(12 * (1.0 - motion.ease_out(along)))]
        assert not slide.finished
        slide.cancel()
    finally:
        root.destroy()


def test_a_cancelled_slide_is_put_in_its_place_at_once() -> None:
    """A second page opened before the first has settled finds the first
    exactly where it belongs, and the end is told once by either road."""
    root = _root()
    try:
        canvas = tk.Canvas(root)
        frame = tk.Frame(canvas)
        item = canvas.create_window((0, 0), window=frame, anchor="nw")
        ended: list[bool] = []
        slide = motion.Slide(canvas, item, -12, done=lambda: ended.append(True))
        assert canvas.coords(item) == [0.0, -12.0]
        slide.cancel()
        assert canvas.coords(item) == [0.0, 0.0] and slide.finished
        slide.cancel()
        root.update()
        assert ended == [True], "once, and the pending frame did nothing"
    finally:
        root.destroy()


def test_reduce_motion_is_read_from_the_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    """``defaults`` prints 1 when it is on, and complains when the key was
    never set, which is off. Anything else -- no such tool, a hang -- is off:
    movement is the default, and the setting is a request for less of it."""
    monkeypatch.setattr(motion, "_PLATFORM", "darwin")

    def says(stdout: str, code: int) -> Any:
        def run(*_args: Any, **_kwargs: Any) -> Any:
            return subprocess.CompletedProcess(_args, code, stdout=stdout, stderr="")

        return run

    monkeypatch.setattr(subprocess, "run", says("1\n", 0))
    assert motion._asked_for_none() is True
    monkeypatch.setattr(subprocess, "run", says("0\n", 0))
    assert motion._asked_for_none() is False
    monkeypatch.setattr(subprocess, "run", says("", 1))
    assert motion._asked_for_none() is False

    def hangs(*_args: Any, **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("defaults", 2)

    monkeypatch.setattr(subprocess, "run", hangs)
    assert motion._asked_for_none() is False


def test_the_setting_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[int] = []

    def once() -> bool:
        asked.append(1)
        return True

    monkeypatch.setattr(motion, "_asked_for_none", once)
    motion.reduced.cache_clear()
    try:
        assert motion.reduced() is True
        assert motion.reduced() is True
        assert len(asked) == 1
    finally:
        motion.reduced.cache_clear()
