"""A reference image over Archicad's 3D window.

Sometimes a view has to be set up from the angle of a photograph or an
earlier rendering -- the same corner of the same street, so that a proposal
can be dropped into the picture the council already has -- and Archicad
cannot show a picture in its 3D window. Trace Reference works on the plan
and the elevations, and the API draws nothing into the 3D window at all.

What can be put over the 3D window is a window of Loriini's own: a
borderless one that stays on top, shows the picture, and is as see-through
as its slider says. On Windows it also lets the mouse fall through it to
whatever is under it, so the person orbits the model in Archicad *through*
the picture until the two line up. Nothing about it touches the project or
the add-on, and it works over any version of Archicad -- or over anything
else. Roadmap item R4; D121 records how it is built.

A palette and a picture, each where it is put
---------------------------------------------

Two windows, each moved and sized on its own. The palette is the controls
-- the opacity slider, the fit, the lock and the hide -- and stays wherever
it is dragged, out of the way. The picture is a borderless frame of its
own: drag it to move it, drag its blue corner to size it from its top-left
corner, which stays put. *Over Archicad* lays the picture over the 3D
window and leaves the palette alone.

They used to be glued, the palette's foot on the picture's top edge, so
that the pair moved as one -- which put the controls over the model
wherever the picture went, and made a picture as narrow as the strip
impossible. A picture is lined up with the model; the controls are not.

Locked, the picture is a thing to look through: the corner goes and the
mouse goes through it to the model. A window the mouse goes through cannot
hold a slider, which is why the controls were always a window of their own.

Fit and stretch
---------------

*Fit* keeps the picture's shape inside the frame, in the frame's top-left
corner, and the frame's spare margins -- to the right or below -- are
see-through: they are painted in one colour, ``KEY``, that Windows is told
to leave out of the window entirely. So a frame laid
over the whole 3D window with a squarer photograph in it shows the
photograph and nothing else. *Stretch* pulls the picture to the frame's
shape, for a picture already cropped to the 3D window's own.

Where the picture comes from
----------------------------

Pillow reads it. A reference is nearly always a JPEG photograph, which Tk
cannot read on its own (it reads PNG and GIF), and a phone's photograph
carries its orientation in EXIF rather than in its pixels; Pillow turns it
the right way up, resizes it cleanly at any size, and hands it to Tk. It is
the reason Pillow is in the bundle -- see D121.

Off Windows
-----------

The window, the picture, the slider and the fit work anywhere Tk does.
Finding the Archicad window and the click-through are Win32 calls made
through ``ctypes``; elsewhere they answer "nothing found" and "not
possible", the palette says so, and the picture is placed by hand and
hidden to reach what is under it.
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Final, Literal

from PIL import Image, ImageOps, ImageTk

from sun_study.app import icons, theme

__all__ = [
    "FIT",
    "STRETCH",
    "Found",
    "Overlay",
    "Palette",
    "Placement",
    "archicad_windows",
    "click_through",
    "fitted",
    "pick",
    "show",
    "stretched",
]

PAD = theme.PAD

#: The colour Windows is told to leave out of the window: the frame's spare
#: margins in *fit* mode, and whatever a picture's own transparency shows.
#: Nearly black rather than black, so that a photograph's shadows -- which
#: are full of pure black -- do not open holes in it.
KEY = "#010203"

#: What the margins are painted in where there is no colour key: a dark
#: grey, so that a picture with room round it reads as a picture in a mat
#: rather than a picture with holes.
GROUND = "#2B2B2B"

#: The two ways a picture sits in its frame.
FIT: Final = "fit"
STRETCH: Final = "stretch"
Mode = Literal["fit", "stretch"]

#: How see-through the picture opens as, and the least it can be made.
#: Halfway is where a photograph and a model can both be read at once; at
#: less than a twentieth the picture is gone and only the slider says so.
DEFAULT_OPACITY = 0.5
LEAST_OPACITY = 0.05

#: The corner that sizes the frame, and the smallest frame it can size to.
HANDLE = 14
LEAST_SIDE = 80

#: The longest side a picture is kept at once read. A 48-megapixel
#: photograph resized for every drag of the corner is a second's wait each
#: time; at 4096 it is unnoticeable, and no screen shows more.
LONGEST_SIDE = 4096

#: How long the frame waits after its size last changed before redrawing
#: the picture at the new size, so a drag of the corner redraws when the
#: hand pauses rather than at every pixel.
SETTLE_MS = 60

#: What the file dialog offers. Everything Pillow reads that a person is
#: likely to have: a phone's JPEG, a render's PNG or TIFF, a screenshot.
FILE_TYPES: tuple[tuple[str, str], ...] = (
    ("Pictures", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp"),
    ("Any file", "*.*"),
)

#: The word an Archicad window's title carries, whatever else it says: the
#: project's name and the version before it, in any spelling of the
#: product's name since it stopped being written in capitals.
ARCHICAD = "archicad"

#: What the palette says when nothing is being pointed at.
STANDING_HINT = (
    "Drag the palette or the picture to move them, and the blue corner to size "
    "the picture. Lock it, then orbit the model under it until the two line up."
)

#: Win32, for ``click_through``: the slot the extended style is kept in, the
#: two bits of it that matter, and the flags that make a restyled window
#: redraw its frame without moving, sizing, raising or activating it.
_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000
_SWP_REDRAW_FRAME = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020


# -- geometry, with nothing on screen ----------------------------------------


@dataclass(frozen=True)
class Placement:
    """Where a rectangle is on the screen: its top-left corner and its size.

    Pixels, in the same space Tk's ``geometry`` speaks -- which on Windows
    is the space the Win32 calls answer in too, whatever the display's
    scaling, because both are asked by the same process.
    """

    x: int
    y: int
    width: int
    height: int

    @property
    def geometry(self) -> str:
        """The placement as Tk spells it: ``640x400+120+120``."""
        return f"{self.width}x{self.height}{self.x:+d}{self.y:+d}"

    @classmethod
    def parse(cls, geometry: str) -> Placement:
        """A placement from Tk's spelling of one. Raises ``ValueError`` for
        anything else."""
        found = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", geometry.strip())
        if found is None:
            raise ValueError(f"not a geometry: {geometry!r}")
        width, height, x, y = found.groups()
        return cls(int(x), int(y), int(width), int(height))

    @property
    def area(self) -> int:
        return self.width * self.height


def fitted(picture: tuple[int, int], frame: tuple[int, int]) -> Placement:
    """The largest the picture can be inside the frame with its shape kept,
    in the frame's top-left corner: its offset within the frame and its size.

    Top-left rather than centred so that sizing the frame by its bottom-right
    corner leaves the picture's top-left corner where it was: what has been
    lined up on the model stays lined up while the rest is pulled out.

    A frame or a picture with no size answers an empty placement rather
    than dividing by nothing.
    """
    wide, tall = picture
    room_wide, room_tall = frame
    if wide <= 0 or tall <= 0 or room_wide <= 0 or room_tall <= 0:
        return Placement(0, 0, 0, 0)
    scale = min(room_wide / wide, room_tall / tall)
    width = max(1, round(wide * scale))
    height = max(1, round(tall * scale))
    return Placement(0, 0, width, height)


def stretched(picture: tuple[int, int], frame: tuple[int, int]) -> Placement:
    """The picture pulled to the frame's own shape: the whole frame."""
    del picture
    room_wide, room_tall = frame
    if room_wide <= 0 or room_tall <= 0:
        return Placement(0, 0, 0, 0)
    return Placement(0, 0, room_wide, room_tall)


@dataclass(frozen=True)
class Found:
    """A window on the screen with Archicad in its title, and where the area
    inside its frame is."""

    title: str
    client: Placement


def pick(windows: Sequence[Found], project: str = "") -> Found | None:
    """Which Archicad window to lay the picture over.

    The one whose title names the chosen project, when one does -- two
    projects open is the ordinary case in an office, and the picker above
    the tabs already says which one the person means. Otherwise the largest,
    which is the one they are working in rather than a palette or a dialog
    that happens to carry the name. Nothing found is ``None``.
    """
    wanted = project.casefold().strip()
    if wanted:
        named = [window for window in windows if wanted in window.title.casefold()]
        if named:
            return max(named, key=lambda window: window.client.area)
    return max(windows, key=lambda window: window.client.area, default=None)


# -- the two Win32 calls -----------------------------------------------------


def archicad_windows() -> list[Found]:
    """Every visible top-level window with Archicad in its title, with the
    area inside its frame in screen pixels. Nothing, off Windows.

    The area inside the frame rather than the frame: the title bar and the
    borders are not where the model is. The 3D window itself is a tab
    inside it, under the toolbars and beside the palettes, and no call names
    where; so this is where the picture starts, and the corner is dragged
    in from there.
    """
    found: list[Found] = []
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        def each(handle: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(handle) or user32.IsIconic(handle):
                return True
            length = user32.GetWindowTextLengthW(handle)
            if length <= 0:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, title, length + 1)
            if ARCHICAD not in title.value.casefold():
                return True
            inside = wintypes.RECT()
            corner = wintypes.POINT(0, 0)
            if not user32.GetClientRect(handle, ctypes.byref(inside)):
                return True
            if not user32.ClientToScreen(handle, ctypes.byref(corner)):
                return True
            if inside.right <= 0 or inside.bottom <= 0:
                return True
            where = Placement(corner.x, corner.y, inside.right, inside.bottom)
            found.append(Found(title.value, where))
            return True

        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(callback(each), 0)
    return found


def click_through(window: tk.Toplevel, on: bool) -> bool:
    """Let the mouse fall through the window to whatever is under it, or
    take it back. True if the window now does as asked; False off Windows,
    where nothing can be done and the caller says so.

    Two bits of the window's extended style: ``WS_EX_TRANSPARENT`` is the
    click-through, and it takes effect only on a ``WS_EX_LAYERED`` window,
    which Tk has already made this one to give it its ``-alpha``. The
    window Windows knows is not the one ``winfo_id`` names -- Tk wraps every
    toplevel in a window of its own -- so it is the parent that is styled.
    """
    done = False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        handle = user32.GetParent(window.winfo_id()) or window.winfo_id()
        if not handle:
            return False

        # The Ptr forms are what a 64-bit user32 exports; the plain ones are
        # the same call on a 32-bit build, which has no Ptr forms to export.
        read = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        write = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        read.restype = ctypes.c_ssize_t
        read.argtypes = [wintypes.HWND, ctypes.c_int]
        write.restype = ctypes.c_ssize_t
        write.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

        style = int(read(handle, _GWL_EXSTYLE))
        if on:
            wanted = style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT
        else:
            wanted = style & ~_WS_EX_TRANSPARENT
        if wanted != style:
            write(handle, _GWL_EXSTYLE, wanted)
            user32.SetWindowPos(handle, 0, 0, 0, 0, 0, _SWP_REDRAW_FRAME)
        done = True
    return done


# -- the picture ---------------------------------------------------------------


class Overlay(tk.Toplevel):
    """The picture itself: a borderless window on top of everything, as
    see-through as it is told, that the mouse can be sent through.

    Built withdrawn. ``show`` puts it on screen, once there is a picture to
    put there; until then there is nothing to see and nothing to move. It
    moves and sizes itself, and nothing else moves with it.
    """

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        #: Whether the margins are see-through. Only Windows has a colour
        #: key; anywhere else they are a dark mat.
        self.keyed = False
        ground = GROUND
        if sys.platform == "win32":
            try:
                self.attributes("-transparentcolor", KEY)
            except tk.TclError:  # pragma: no cover - a Tk without the option
                pass
            else:
                self.keyed = True
                ground = KEY
        self.configure(background=ground, highlightthickness=1, highlightbackground=theme.BLUE)

        #: The picture, read once and the right way up, at most ``LONGEST_SIDE``
        #: on its longer side; ``None`` until one has been read.
        self.picture: Image.Image | None = None
        #: The name of the file it came from, for the palette to say.
        self.name = ""
        self.mode: Mode = FIT
        self.opacity = DEFAULT_OPACITY
        self.locked = False
        #: Whether the mouse goes through the window when it is locked --
        #: what ``click_through`` answered the last time it was asked.
        self.passes = False
        #: Whether ``show`` has ever been called: the palette places the
        #: frame the first time and leaves it where the person put it after.
        self.placed = False

        self._photo: ImageTk.PhotoImage | None = None
        self._drawn: tuple[int, int, Mode] | None = None
        self._settle: str | None = None
        self._grab_at = (0, 0)
        self._corner_at = (0, 0, 0, 0)

        self.face = tk.Label(self, bd=0, highlightthickness=0, background=ground)
        self.face.place(x=0, y=0)
        self.grip = tk.Frame(self, width=HANDLE, height=HANDLE, background=theme.BLUE)
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        # X11's names for the cursors; Tk on Windows maps them to its own.
        for widget, cursor in ((self.face, "fleur"), (self.grip, "bottom_right_corner")):
            try:
                widget.configure(cursor=cursor)
            except tk.TclError:  # pragma: no cover - a Tk without the cursor
                pass

        for movable in (self, self.face):
            movable.bind("<ButtonPress-1>", self._grab)
            movable.bind("<B1-Motion>", self._drag)
        self.grip.bind("<ButtonPress-1>", self._grab_corner)
        self.grip.bind("<B1-Motion>", self._resize)
        self.bind("<Configure>", self._configured)
        # Tk makes the window Windows knows when it maps this one, and makes
        # it again after some changes, so the click-through is put back at
        # every mapping rather than trusted to stay.
        self.bind("<Map>", lambda _event: self._apply_lock())
        self.bind("<Destroy>", self._destroyed)
        self.set_opacity(DEFAULT_OPACITY)
        self.geometry(Placement(120, 120, 640, 400).geometry)

    # -- what the palette asks for ------------------------------------------

    def load(self, path: Path) -> str:
        """Read this picture and show it. Answers a sentence if the file
        cannot be read, and keeps whatever picture it had."""
        try:
            with Image.open(path) as opened:
                turned = ImageOps.exif_transpose(opened)
                turned.thumbnail((LONGEST_SIDE, LONGEST_SIDE))
                picture = self._flat(turned)
        except (OSError, ValueError, MemoryError, Image.DecompressionBombError) as refused:
            # A file that is not a picture and a truncated one are OSErrors;
            # a mode Pillow cannot convert is a ValueError; a picture too big
            # to be safe to open is its own kind.
            why = str(refused).strip() or "it is not a picture"
            return f"Could not read {path.name}: {why}"
        self.picture = picture
        self.name = path.name
        self._drawn = None
        self._redraw()
        return ""

    def set_opacity(self, value: float) -> None:
        """How much of the picture shows, from ``LEAST_OPACITY`` to 1."""
        self.opacity = min(1.0, max(LEAST_OPACITY, value))
        try:
            self.attributes("-alpha", self.opacity)
        except tk.TclError:  # pragma: no cover - a Tk without alpha
            pass

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode
        self._redraw()

    def lock(self, on: bool) -> bool:
        """Locked, the corner goes and the mouse goes through the picture;
        unlocked, the picture can be moved and sized again. Answers whether
        the mouse does go through, which off Windows it cannot."""
        self.locked = on
        if on:
            self.grip.place_forget()
        else:
            self.grip.place(relx=1.0, rely=1.0, anchor="se")
            self.grip.lift()
        # The blue edge goes with the corner, and the picture takes the pixel
        # it stood on: the frame's size has not changed, so nothing else
        # would redraw it.
        self.configure(highlightthickness=0 if on else 1)
        self._apply_lock()
        self._redraw()
        return self.passes

    def place_at(self, placement: Placement) -> None:
        self.geometry(placement.geometry)
        self.placed = True

    @property
    def placement(self) -> Placement:
        """Where the frame is now."""
        self.update_idletasks()
        return Placement(self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height())

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.update_idletasks()
        self._apply_lock()
        self._redraw()

    def hide(self) -> None:
        self.withdraw()

    @property
    def shown(self) -> bool:
        return self.winfo_viewable() == 1

    # -- moving and sizing by hand --------------------------------------------

    def _grab(self, event: tk.Event[tk.Misc]) -> None:
        self._grab_at = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag(self, event: tk.Event[tk.Misc]) -> None:
        if self.locked:
            return
        dx, dy = self._grab_at
        self.geometry(f"{event.x_root - dx:+d}{event.y_root - dy:+d}")

    def _grab_corner(self, event: tk.Event[tk.Misc]) -> None:
        self._corner_at = (event.x_root, event.y_root, self.winfo_width(), self.winfo_height())

    def _resize(self, event: tk.Event[tk.Misc]) -> None:
        """The corner sizes the frame from its top-left, which stays where it
        is: only the width and the height change."""
        if self.locked:
            return
        x0, y0, wide, tall = self._corner_at
        width = max(LEAST_SIDE, wide + event.x_root - x0)
        height = max(LEAST_SIDE, tall + event.y_root - y0)
        self.geometry(f"{width}x{height}")

    # -- drawing ----------------------------------------------------------------

    def _configured(self, event: tk.Event[tk.Misc]) -> None:
        # Every child's <Configure> arrives here too, through the bindtags,
        # and only the frame's own is the picture's business. A move sends
        # one as well; ``_redraw`` finds nothing to do then.
        if event.widget is not self:
            return
        if self._settle is not None:
            self.after_cancel(self._settle)
        self._settle = self.after(SETTLE_MS, self._redraw)

    def _redraw(self) -> None:
        """Draw the picture at the frame's size, in its mode."""
        self._settle = None
        if self.picture is None:
            return
        # Inside the blue edge, while there is one: ``place`` counts from
        # the inside of it, and a picture the frame's whole size would
        # stand a pixel over it on two sides.
        ring = int(self.cget("highlightthickness"))
        width, height = self.winfo_width() - 2 * ring, self.winfo_height() - 2 * ring
        if (width, height, self.mode) == self._drawn:
            return
        box = fitted(self.picture.size, (width, height))
        if self.mode == STRETCH:
            box = stretched(self.picture.size, (width, height))
        if box.area == 0:
            return
        resized = self.picture.resize(
            (box.width, box.height), Image.Resampling.LANCZOS, reducing_gap=3.0
        )
        self._photo = ImageTk.PhotoImage(resized, master=self)
        self.face.configure(image=self._photo)
        self.face.place(x=box.x, y=box.y, width=box.width, height=box.height)
        self.grip.lift()
        self._drawn = (width, height, self.mode)

    def _flat(self, picture: Image.Image) -> Image.Image:
        """The picture as plain RGB, its own transparency laid over the
        ground -- which on Windows is the colour key, so a transparent PNG
        stays transparent over the model."""
        ground = KEY if self.keyed else GROUND
        if picture.mode in ("RGBA", "LA") or (
            picture.mode == "P" and "transparency" in picture.info
        ):
            mat = Image.new("RGBA", picture.size, ground)
            return Image.alpha_composite(mat, picture.convert("RGBA")).convert("RGB")
        return picture.convert("RGB")

    def _apply_lock(self) -> None:
        try:
            self.passes = click_through(self, self.locked)
        except (OSError, tk.TclError):  # pragma: no cover - a window already gone
            self.passes = False

    def _destroyed(self, event: tk.Event[tk.Misc]) -> None:
        # A redraw still waiting when the frame goes would fire on a window
        # Tk no longer has, and say so on stderr. Only the frame's own
        # <Destroy> is the frame going; its children's arrive here too.
        if str(event.widget) != str(self) or self._settle is None:
            return
        try:
            self.after_cancel(self._settle)
        except tk.TclError:  # pragma: no cover - the timer already gone
            pass
        self._settle = None


# -- the palette -----------------------------------------------------------------


class Palette(tk.Toplevel):
    """The controls, in a small palette of their own, the way Archicad's float.

    Short on purpose: it sits over Archicad while the model is orbited, and
    every pixel it takes is a pixel of the model it is covering. It has its
    own line of explanation at the foot rather than the window's band,
    because the window is under Archicad while this is in use.

    The picture is ``overlay``, a second toplevel that moves and sizes on
    its own; ``lay`` puts it somewhere, by its frame, which is what the
    Archicad window and the screen are measured in. The palette stays where
    it was put.
    """

    def __init__(self, parent: tk.Misc, *, project: Callable[[], str] = lambda: "") -> None:
        super().__init__(parent)
        self.title("Reference image")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        if sys.platform == "win32":
            # A narrow title bar, and no place on the task bar: it is a
            # palette of the window, not a window of its own.
            try:
                self.attributes("-toolwindow", True)
            except tk.TclError:  # pragma: no cover - a Tk without the option
                pass
        self.configure(background=theme.SURFACE)
        self.project = project
        # On its own: dragged, it moves itself; sized by its corner, it sizes
        # itself, down to ``LEAST_SIDE``. Nothing it does moves the palette.
        self.overlay = Overlay(self)
        #: Where the file dialog opens: where the last picture came from.
        self.folder = Path.home()

        page = ttk.Frame(self, padding=(PAD + 2, PAD, PAD + 2, PAD))
        page.pack(fill="both", expand=True)
        page.columnconfigure(1, weight=1)

        self.open = ttk.Button(
            page,
            text="Open picture…",
            command=self._pick,
            width=15,
            **icons.button_options("reference"),
        )
        self.open.grid(row=0, column=0, sticky="w")
        self.named = ttk.Label(page, text="No picture yet.", style="Hint.TLabel")
        self.named.grid(row=0, column=1, columnspan=2, sticky="w", padx=(PAD, 0))

        ttk.Label(page, text="Opacity").grid(row=1, column=0, sticky="w", pady=(PAD, 0))
        self.level = tk.DoubleVar(value=DEFAULT_OPACITY * 100)
        self.slider = ttk.Scale(
            page,
            from_=LEAST_OPACITY * 100,
            to=100,
            orient="horizontal",
            variable=self.level,
            command=self._slid,
            length=220,
        )
        self.slider.grid(row=1, column=1, sticky="ew", pady=(PAD, 0), padx=(PAD, 0))
        self.percent = ttk.Label(page, text="", width=5, anchor="e")
        self.percent.grid(row=1, column=2, sticky="e", pady=(PAD, 0))

        ways = ttk.Frame(page)
        ways.grid(row=2, column=0, columnspan=2, sticky="w", pady=(PAD, 0))
        self.fit = ttk.Button(ways, text="Fit", takefocus=False, command=lambda: self._mode(FIT))
        self.fit.grid(row=0, column=0, padx=(0, 4))
        self.stretch = ttk.Button(
            ways, text="Stretch", takefocus=False, command=lambda: self._mode(STRETCH)
        )
        self.stretch.grid(row=0, column=1)
        self.cover = ttk.Button(page, text="Over Archicad", command=self._cover, width=14)
        self.cover.grid(row=2, column=2, sticky="e", pady=(PAD, 0), padx=(PAD, 0))

        ticks = ttk.Frame(page)
        ticks.grid(row=3, column=0, columnspan=2, sticky="w", pady=(PAD, 0))
        self.locked = tk.BooleanVar(value=False)
        self.lock = ttk.Checkbutton(ticks, text="Lock", variable=self.locked, command=self._lock)
        self.lock.grid(row=0, column=0, padx=(0, PAD + 4))
        self.hidden = tk.BooleanVar(value=False)
        self.hide = ttk.Checkbutton(ticks, text="Hide", variable=self.hidden, command=self._hide)
        self.hide.grid(row=0, column=1)
        self.shut = ttk.Button(page, text="Close", command=self.close, width=14)
        self.shut.grid(row=3, column=2, sticky="e", pady=(PAD, 0), padx=(PAD, 0))

        self.hint = ttk.Label(
            page, text=STANDING_HINT, style="Hint.TLabel", wraplength=380, justify="left"
        )
        self.hint.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(PAD + 2, 0))

        self._explain(
            self.open,
            "A photograph or a rendering to set the view up from: PNG, JPEG, "
            "TIFF, BMP, GIF or WebP.",
        )
        self._explain(
            self.slider,
            "How much of the picture shows over the model. Halfway is where "
            "both can be read at once.",
        )
        self._explain(
            self.fit,
            "The whole picture inside the frame with its shape kept; the "
            "frame's spare margins are see-through.",
        )
        self._explain(
            self.stretch,
            "The picture pulled to the frame's shape, for a picture already "
            "cropped to the 3D window's own.",
        )
        self._explain(
            self.cover,
            "Lays the frame over the Archicad window showing the chosen project "
            "-- the whole of it, inside its frame -- to start from. Then drag "
            "the blue corner in to the 3D window's edges.",
        )
        self._explain(
            self.lock,
            "The mouse goes through the picture to the model under it, and the "
            "corner goes. Unlock to move the picture or size it again.",
        )
        self._explain(self.hide, "Takes the picture off the screen without closing it.")
        self._explain(self.shut, "Closes the picture and this palette.")

        self._mode(FIT)
        self._slid()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Destroy>", self._destroyed)
        # Top right of the screen, out of the way of a 3D window that is
        # nearly always to the left of the palettes Archicad keeps there.
        self.update_idletasks()
        self.geometry(f"+{max(0, self.winfo_screenwidth() - self.winfo_reqwidth() - 24)}+48")

    def lay(self, frame: Placement) -> None:
        """Put the picture's frame here. The palette is not moved."""
        self.overlay.place_at(frame)

    # -- the controls ---------------------------------------------------------------

    def _pick(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Open a reference picture",
            filetypes=FILE_TYPES,
            initialdir=str(self.folder),
        )
        if not chosen:
            return
        self.take(Path(chosen))

    def take(self, path: Path) -> str:
        """Show this picture, placing the frame the first time. Answers what
        ``Overlay.load`` answers: a sentence if the file could not be read."""
        said = self.overlay.load(path)
        if said:
            self.say(said, refused=True)
            return said
        self.folder = path.parent
        picture = self.overlay.picture
        size = f"{picture.width} \N{MULTIPLICATION SIGN} {picture.height}" if picture else ""
        self.named.configure(text=f"{path.name}   {size}")
        if not self.overlay.placed:
            self._place_first()
        self.hidden.set(False)
        self.overlay.show()
        self.say(STANDING_HINT)
        return ""

    def _place_first(self) -> None:
        """Over the Archicad window if one can be found; otherwise the middle
        of the screen, sized to the picture at three fifths of it."""
        over = pick(archicad_windows(), self.project())
        if over is not None:
            self.lay(over.client)
            return
        picture = self.overlay.picture
        if picture is None:
            return
        wide, tall = self.winfo_screenwidth(), self.winfo_screenheight()
        box = fitted(picture.size, (wide * 3 // 5, tall * 3 // 5))
        self.lay(
            Placement((wide - box.width) // 2, (tall - box.height) // 2, box.width, box.height)
        )

    def _slid(self, _value: str = "") -> None:
        level = self.level.get()
        self.percent.configure(text=f"{round(level)} %")
        self.overlay.set_opacity(level / 100)

    def _mode(self, mode: Mode) -> None:
        self.overlay.set_mode(mode)
        self.fit.configure(style="TileOn.TButton" if mode == FIT else "Tile.TButton")
        self.stretch.configure(style="TileOn.TButton" if mode == STRETCH else "Tile.TButton")

    def _cover(self) -> None:
        found = archicad_windows()
        over = pick(found, self.project())
        if over is None:
            if sys.platform == "win32":
                self.say(
                    "No Archicad window on this screen. Drag the picture into place instead.",
                    refused=True,
                )
            else:
                self.say(
                    "Finding the Archicad window works on Windows. Drag the picture "
                    "into place instead.",
                    refused=True,
                )
            return
        self.lay(over.client)
        if self.overlay.picture is not None and not self.hidden.get():
            self.overlay.show()
        self.say(f"Over “{over.title}”. Drag the blue corner in to the 3D window's edges.")

    def _lock(self) -> None:
        passes = self.overlay.lock(self.locked.get())
        if not self.locked.get():
            self.say(STANDING_HINT)
        elif passes:
            self.say("Locked. The mouse goes through the picture: orbit the model under it.")
        else:
            self.say(
                "Locked. On this machine the mouse does not go through the picture; "
                "hide it to reach the model."
            )

    def _hide(self) -> None:
        if self.hidden.get():
            self.overlay.hide()
        elif self.overlay.picture is not None:
            self.overlay.show()

    def say(self, text: str, *, refused: bool = False) -> None:
        """The line at the foot: what a control does, or what went wrong."""
        self.hint.configure(text=text, style="Refused.TLabel" if refused else "Hint.TLabel")

    def _explain(self, widget: tk.Widget, text: str) -> None:
        widget.bind("<Enter>", lambda _event: self.say(text), add="+")
        widget.bind("<Leave>", lambda _event: self.say(STANDING_HINT), add="+")

    def close(self) -> None:
        self.destroy()

    def _destroyed(self, event: tk.Event[tk.Misc]) -> None:
        # Every child's <Destroy> arrives here too; only the palette's own
        # means the palette is gone.
        global _open
        if _open is self and str(event.widget) == str(self):
            _open = None


#: The one palette, whichever button opened it. A second picture over the
#: first is never what anybody meant, so the open one is raised instead.
_open: Palette | None = None


def show(parent: tk.Misc, *, project: Callable[[], str] = lambda: "") -> Palette:
    """Open the palette, or raise the one already open, and answer with it."""
    global _open
    if _open is not None:
        try:
            _open.deiconify()
            _open.lift()
            _open.focus_set()
        except tk.TclError:  # pragma: no cover - destroyed without telling us
            _open = None
        else:
            return _open
    _open = Palette(parent, project=project)
    return _open
