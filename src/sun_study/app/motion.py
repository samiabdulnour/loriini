"""Movement in the window, which is to say very little of it.

One thing moves: a page, as it opens, settles into place from a few pixels
off (D134). It is there to say which way you went -- down the sidebar, and
the page rises; up it, and the page drops -- and to make a switch read as
one page giving way to the next rather than the screen being repainted.
That is the whole of it: nothing bounces, nothing fades, nothing takes
longer than a glance.

Tk has no animation of its own. What it has is ``after`` and a canvas item
that can be moved, and that is enough: every page sits in a canvas (the
``Scroller``), so sliding the page is moving one item, which Tk does
without laying anything out again. The frames are paced by the clock, not
counted -- but a single frame is charged for no more than ``HITCH_MS`` of
it. A page is painted for the first time just after it opens, and on
Windows that one paint took 30 to 60 ms of a 180 ms slide: measured, the
page was seen at 12 px, at 9, and next at 3, which is a jerk and not a
movement. With the charge capped, the paint costs the slide a frame and
the page still travels the whole way.

And none of it where the person has asked for none: macOS's Reduce Motion
and Windows' client-area animation setting are read once, and a page then
opens where it belongs with no movement at all. Any doubt about what the
system said is taken as that answer too.
"""

from __future__ import annotations

import subprocess
import sys
import time
import tkinter as tk
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import cache
from typing import Any

#: How long a page takes to settle, and how far off it starts. Both small:
#: long enough to be seen as movement and not as a flicker, short enough
#: that nobody waits for it. Twelve pixels is under the height of a line of
#: text, so the page is never seen to be somewhere else, only arriving.
DURATION_MS = 180
DISTANCE = 12
#: A frame. Sixteen milliseconds is a screen's own beat; Tk may deliver
#: fewer, and the clock, not the count, says where the page is.
FRAME_MS = 16
#: The most of the slide's time one frame may use up, however long it took
#: to arrive: two beats. What a slow paint costs the movement.
HITCH_MS = 32
#: Held as a plain string, so the branch for the other system is read as
#: code and not, by a type checker on this one, as unreachable.
_PLATFORM: str = sys.platform


def ease_out(along: float) -> float:
    """Where the page is, ``along`` the way through its time, in 0..1.

    Cubic ease-out: fast away from where it started and slowing to a stop,
    which is how a thing that has been put down arrives. Linear motion
    reads as mechanical, and an ease-in -- slow to start -- reads as the
    window hesitating.
    """
    along = min(max(along, 0.0), 1.0)
    return 1.0 - (1.0 - along) ** 3


def _asked_for_none() -> bool:
    """What the system says, read fresh. False on any doubt."""
    try:
        if _PLATFORM == "darwin":
            # ``defaults`` prints 1 when Reduce Motion is on, and complains
            # (on stderr, with a non-zero exit) when the key has never been
            # set -- which is the common case, and means off.
            said = subprocess.run(
                ["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            return said.returncode == 0 and said.stdout.strip() == "1"
        if _PLATFORM == "win32":
            import ctypes

            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return False
            animate = ctypes.c_int(1)
            # SPI_GETCLIENTAREAANIMATION: whether the system animates the
            # inside of windows. Off is Windows' "show animations" switch.
            if windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(animate), 0):
                return not animate.value
    except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
        return False
    return False


@cache
def reduced() -> bool:
    """Whether the person has asked the system for less movement. Read once:
    it is a setting changed about as often as a font, and asking the system
    on every page would cost more than the movement it decides."""
    return _asked_for_none()


class Slide:
    """One canvas item settling from ``offset`` pixels down (or up, if
    negative) to where it belongs, over ``DURATION_MS``.

    Started on construction; ``cancel`` stops it where it is and puts the
    item in its place, which is what a second page opening before the first
    has settled does to it. ``done`` is called once, at the end, by either
    road.
    """

    def __init__(
        self,
        canvas: tk.Canvas,
        item: int,
        offset: float,
        *,
        done: Callable[[], None] | None = None,
        duration_ms: int = DURATION_MS,
    ) -> None:
        self.canvas = canvas
        self.item = item
        self.offset = offset
        self.duration = max(duration_ms, 1) / 1000.0
        self._done = done
        #: How much of its time the slide has used, and when it was last
        #: asked: the clock, with each frame's share of it capped.
        self._spent = 0.0
        self._last = time.monotonic()
        self._pending: str | None = None
        self.finished = False
        self._place(offset)
        self._pending = canvas.after(FRAME_MS, self._frame)

    def _place(self, down: float) -> None:
        x_now, _y = self.canvas.coords(self.item) or (0.0, 0.0)
        self.canvas.coords(self.item, x_now, round(down))

    def _frame(self) -> None:
        self._pending = None
        if self.finished:
            return
        now = time.monotonic()
        self._spent += min(now - self._last, HITCH_MS / 1000.0)
        self._last = now
        along = self._spent / self.duration
        if along >= 1.0:
            self._finish()
            return
        self._place(self.offset * (1.0 - ease_out(along)))
        self._pending = self.canvas.after(FRAME_MS, self._frame)

    def _finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        if self._pending is not None:
            try:
                self.canvas.after_cancel(self._pending)
            except tk.TclError:  # pragma: no cover - the canvas is gone
                pass
            self._pending = None
        try:
            self._place(0)
        except tk.TclError:  # pragma: no cover - the canvas is gone
            return
        if self._done is not None:
            self._done()

    def cancel(self) -> None:
        """Stop, and put the item where it belongs."""
        self._finish()


class Tween:
    """Something eased from 0 to 1 over ``duration_ms``, paced as ``Slide``
    is: ``step`` is handed how far along it is, eased, on every frame, and
    ``done`` is called once when it gets there. ``stop`` ends it where it is
    and without ``done``; ``cancel`` ends it at 1, with it.
    """

    def __init__(
        self,
        widget: tk.Misc,
        step: Callable[[float], None],
        *,
        done: Callable[[], None] | None = None,
        duration_ms: int = DURATION_MS,
    ) -> None:
        self.widget = widget
        self._step = step
        self._done = done
        self.duration = max(duration_ms, 1) / 1000.0
        self._spent = 0.0
        self._last = time.monotonic()
        self.finished = False
        step(0.0)
        self._pending: str | None = widget.after(FRAME_MS, self._frame)

    def _frame(self) -> None:
        self._pending = None
        if self.finished:
            return
        now = time.monotonic()
        self._spent += min(now - self._last, HITCH_MS / 1000.0)
        self._last = now
        along = self._spent / self.duration
        if along >= 1.0:
            self.cancel()
            return
        self._step(ease_out(along))
        self._pending = self.widget.after(FRAME_MS, self._frame)

    def stop(self) -> None:
        """End it where it is, and do not call ``done``."""
        self.finished = True
        if self._pending is not None:
            try:
                self.widget.after_cancel(self._pending)
            except tk.TclError:  # pragma: no cover - the widget is gone
                pass
            self._pending = None

    def cancel(self) -> None:
        """End it where it was going, and call ``done``."""
        if self.finished:
            return
        self.stop()
        try:
            self._step(1.0)
        except tk.TclError:  # pragma: no cover - the widget is gone
            return
        if self._done is not None:
            self._done()


# -- painting held ------------------------------------------------------------
#
# A window of a few hundred widgets re-laid out to a new width -- the page,
# when the sheets panel opens beside it -- is moved and repainted by Windows
# one native child window at a time, and for a third of a second the screen
# shows every half-moved state in between: labels wrapped at the old width
# over fields at the new one. Recorded, an opening of the panel went through
# twelve distinct screens. Telling the window not to paint while Tk lays it
# out, and to paint everything once it has, leaves two: before and after.

_WM_SETREDRAW = 0x000B
_RDW_INVALIDATE = 0x0001
_RDW_ERASE = 0x0004
_RDW_ALLCHILDREN = 0x0080
_RDW_UPDATENOW = 0x0100


@cache
def _user32() -> Any:
    """Windows' user32, with the two calls typed; ``None`` anywhere else."""
    if _PLATFORM != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        # Looked up, as ``windll`` is above: the name exists only on Windows,
        # and a type checker on the Mac reads this branch too.
        loader = getattr(ctypes, "WinDLL", None)
        if loader is None:
            return None
        user32 = loader("user32")
        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.RedrawWindow.argtypes = [
            wintypes.HWND,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.UINT,
        ]
        user32.RedrawWindow.restype = wintypes.BOOL
        return user32
    except (OSError, AttributeError):
        return None


@contextmanager
def painting_held(widget: tk.Misc) -> Iterator[None]:
    """Lay out what the block changes with the window's painting held, then
    paint the window once. Elsewhere than Windows, or on a window not on
    screen, the block simply runs."""
    user32 = _user32()
    handle = 0
    if user32 is not None:
        try:
            top = widget.winfo_toplevel()
            if top.winfo_viewable():
                handle = int(top.winfo_id())
        except tk.TclError:
            handle = 0
    if not handle:
        yield
        return
    user32.SendMessageW(handle, _WM_SETREDRAW, 0, 0)
    try:
        yield
        widget.update_idletasks()
    finally:
        user32.SendMessageW(handle, _WM_SETREDRAW, 1, 0)
        user32.RedrawWindow(
            handle,
            None,
            None,
            _RDW_INVALIDATE | _RDW_ERASE | _RDW_ALLCHILDREN | _RDW_UPDATENOW,
        )
