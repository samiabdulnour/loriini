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
from collections.abc import Callable
from functools import cache

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
