"""How the window looks: the palette, the type, and the ttk styles.

Why this file exists
--------------------

The window used Windows' own ``vista`` theme, which draws its widgets through
the operating system. That is the right default for a tool nobody has designed,
and the wrong one here: the icons brought a palette with them -- blue is the
interface, ochre is the sun, grey is what is built -- and a native theme cannot
be told about any of it. A selected tab stays Windows blue, a Run button stays
Windows grey, and the drawing beside the label is the only thing in the window
that knows what the tool is about.

So the theme is ``clam``, which is the one ttk theme drawn by Tk rather than by
the OS and therefore the only one that can be restyled. Everything below is the
same palette the icons are drawn from and the same measurements the design
boards use.

What it is careful about
------------------------

**Contrast.** Every text colour here clears 4.5:1 on the surface it sits on.
The hint grey is the one that wants watching: the old ``#5a5a5a`` was fine on
white and this keeps that standard rather than drifting paler for looks.

**Failing soft.** A machine without ``clam``, or without Segoe UI, must still
open the window. Every step is guarded and the worst case is the plain ttk
default, which is ugly and entirely usable -- the same rule ``preferences`` and
``icons`` follow.

The principles
--------------
Settled 21 September 2026 (D109), after a review of the window as built. The
brief in Sami's words: *airy; Archicad's light grey and light blue; Apple kind
of style; thin contour.* Everything below is one of these, and a change that
is none of them is a change to argue about first.

Refreshed 23 October 2026 (D132), to the brief *fresher: rounder, lighter, a
pale accent*. The structure is D109's; what changed is the ground, the
corners, the face, and above all the accent: a pale lemon under dark text
where a dark blue carried white. Where a principle below says what the
window does today, the D132 reading is the one that holds.

1. **Three surfaces, and nothing else is a colour.** The ground is a warm
   off-white: ``CHROME`` for the window's surround, the sidebar and the
   dock, ``PAGE`` -- a shade lighter -- for the page a section is laid out
   on. Anything you edit or anything the run makes is a white card on that
   ground. The accent means chosen or switched on, and it is pale, so what
   is chosen carries ink, never white. Ochre is the sun and red is a
   warning, and neither is ever decoration. The icons and the thumbnails
   keep their blue: they are drawings of the interface, not the interface.
2. **Thin contours, everywhere a region ends.** A card has a one-pixel edge in
   ``LINE``; a field has one in ``EDGE`` because you can type in it. A
   one-pixel rule in ``LINE`` parts the page from the dock, the body from the
   info band, and the band from the run bar. Nothing is ever framed twice, and
   nothing heavier than a pixel is drawn. No face is lifted: flat, with its
   edge, and nothing under it.
3. **One radius scale.** Eight pixels on a control, twelve on a card -- and
   a tab is a card, as is the page it sits a gap above; the open sidebar row
   is ten, a chip or a pill is its own half-height. Zero on paper and on
   anything drawn: a sheet has corners, and so does a model.
4. **Air.** Cards sit sixteen pixels in from the page and eight apart; rows
   step six pixels; the run bar keeps its two kinds of button a clear gap
   apart. Empty page is page, not an unfinished panel.
5. **Every control lives in a card**, under a header that says what the card
   is for. A study's card is headed by its own tick; a settings card by a
   title. No row floats on the page by itself.
6. **One mark per state, on its own axis.** Open is the white tab under a
   blue cap; queued is the blue name with its dot; on is the tinted tile or
   the tinted header. No focus ring is drawn on a tab or a tile, because it
   read as a second mark. The count on a card's header is what its tick is
   worth, and the dock draws the same.
7. **Type is Inter, at the body size the operating system uses.** The face
   the web site is set in, carried with the program (``assets/fonts``) and
   registered for this process alone when the window opens, so nothing is
   installed; a machine where that fails falls back to Segoe UI. Titles are
   bold, hints are ``HINT`` grey and clear 4.5:1, group captions are small
   capitals. Nothing on a thumbnail carries anything a person must read. On a
   Mac it is the Mac's own face at the same size on screen -- see ``points``.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

# -- the palette, the same one the icons are drawn from --------------------

#: The window's surround, the sidebar and the dock: the warm off-white the
#: web site's ground is lightened to. It was Archicad's own neutral #F0F0F0
#: from D109 to D132, sampled so the window would not look like a different
#: program parked on top of Archicad; the warmth is slight enough that the
#: window still sits beside Archicad's grey, and it is the one thing that
#: says the window and the site are the same product.
CHROME = "#F1F0E6"

#: Where the settings are. White, because the icons are drawn on white and a
#: sheet of paper on grey is not a sheet of paper. Archicad's panels agree.
SURFACE = "#FFFFFF"

#: The page a section is laid out on: a shade *lighter* than the surround
#: now, a rounded panel the cards sit on, so the page reads as the lit
#: thing and the surround as what holds it.
PAGE = "#F8F7F0"

#: The sidebar of pages down the left, and the sheets panel down the right.
#: The surround's own colour: neither is a panel of its own any more, the
#: rows and the cards on them are the things with edges.
SIDEBAR = CHROME
#: The card at the foot of the sidebar that explains what is under the
#: pointer. A white card like the others.
HELP = "#FFFFFF"
#: A panel's edge when its study is off, or it has no study.
PANEL_EDGE = "#E3E2D8"
#: The grey of a sidebar group's caption -- SET UP, STUDIES, TOOLS. Darker
#: than ``HINT`` because it sits on the surround, not on white.
CAPTION = "#5B5A52"

#: A control nobody has chosen, and the trough of the progress bar.
MUTED = "#ECEBE2"

INK = "#1F1F1D"
BODY = "#3C3C3A"
#: The line under a control. 5.3:1 on white, which is the point of it.
HINT = "#6B6A63"
#: A divider. Lighter than a field's edge, and warm -- LINE separates, EDGE
#: encloses something you can type in, and clears 3:1 on white because a
#: control's boundary owes the eye that much.
LINE = "#E3E2D8"
EDGE = "#8A8980"

#: The accent: what is chosen, switched on, or the action a page leads to.
#: Pale lemon, after the web site's lemon board (D132), and pale on purpose:
#: it carries ink, never white, so the open row, the chosen day and the Run
#: button are light shapes on a light window rather than dark blocks.
ACCENT = "#FFF07A"
#: The accent's tint, for a chosen card's header and a chip; its edge, for
#: a hover and the rule under a chosen header; and what sits on it.
ACCENT_TINT = "#FFF9CF"
ACCENT_EDGE = "#E6D65A"
ON_ACCENT = INK

#: The drawings' blue. The icons (``scripts/make_icons.py``) and the sheet
#: thumbnails are pictures of the interface drawn in Archicad's blue, and
#: they keep it: a picture of a chosen thing is not the chosen thing. No
#: control is this colour since D132.
BLUE = "#1E63C8"
BLUE_TINT = "#E8F0FC"
BLUE_EDGE = "#9DBDEB"
BLUE_DEEP = "#14417F"

SUN = "#D98A1E"
RED = "#C0392B"

#: The gap everything is spaced by, and the one the old layout already used.
PAD = 8

#: Type. Segoe UI because this is a Windows tool and it is the face the rest of
#: the operating system is set in; the log stays monospaced because it prints
#: layer names and numbers that have to line up.
#: How many pixels of a face are corner rather than stretch: one more than
#: the radius, so the curve is never in the part that is tiled. Controls
#: are drawn with an 8 px radius, so 9; a card with 12, so 13.
FACE_SLICE = 9
PANEL_SLICE = 13

#: How tall a panel's header is. ``scripts/make_icons.py`` holds the same
#: number, and has to: the header's tint and the rule under it are drawn into
#: the top slice of the panel's face, so the window must place the header at
#: exactly the height the picture was drawn for. A test holds the two together.
PANEL_HEAD = 32

#: The tint behind a study's header, on and off. Drawn into the panel faces
#: and worn by the tick that sits on them, so they have to match to the digit.
HEAD_ON = ACCENT_TINT
HEAD_OFF = SURFACE

#: Every button style this theme defines, and which face it wears.
#:
#: Declared, and not worked out at the point of use, because of the trap: ttk
#: hands a derived style its parent's *layout*, so changing ``TButton`` changes
#: every ``*.TButton`` that has not been given one of its own. That is how a
#: rounded button face ended up behind all six tabs the first time this was
#: written. Listing them is the decision; the test that reads this dictionary
#: back against the module is what stops the next style being added without
#: one, which is the part that makes it stop being a trap.
#:
#: ``"flat"`` means the style is painted by its own ``background`` and keeps
#: clam's drawn border. Everything else names an element made in ``_rounded``.
#: Buttons drawn without Tk's dotted focus ring: their face already says
#: which one is chosen, and the ring stayed on whichever was clicked last.
NO_RING = frozenset({"Side.TButton", "SideOpen.TButton"})

WEARS: dict[str, str] = {
    "TButton": "button",
    "Chrome.TButton": "button",
    "Run.TButton": "run",
    "Add.TButton": "add",
    "Tile.TButton": "tile",
    "TileOn.TButton": "tileon",
    # A page in the sidebar: its name, on the row's own ground. The row is
    # the faced thing -- a rounded blue bar when it is the open page -- so the
    # name on it is a flat button that takes the row's colour.
    "Side.TButton": "flat",
    "SideOpen.TButton": "flat",
    # The triangle that folds a panel, on its header, the way Archicad folds
    # the panels of a settings dialog.
    "Disclose.TButton": "flat",
    "DiscloseOn.TButton": "flat",
    # The cross on a chip is inside a rounded box already, and a second one
    # around a 13 px glyph is a box around a box.
    "ChipDrop.TButton": "flat",
    # The chevron that folds the sheets panel away: a mark, not a button face.
    "Fold.TButton": "flat",
    # A tool in the project bar that is not about the project: the reference
    # image, Claude, About. Words and a drawing on the chrome, tinted under
    # the pointer, so Refresh beside the picker is the one button up there.
    "Tool.TButton": "flat",
}

#: What each faced style stands on, which is the colour its corners take.
#:
#: The third trap. A face is a rounded shape in a square widget, and what
#: shows through the four corners is the *style's* background, not whatever
#: the widget has been put on. So a button that lives on the grey run bar is
#: a different style from the same button on the white page, and the only
#: difference between them is this.
STANDS_ON: dict[str, str] = {
    "TButton": SURFACE,
    "Chrome.TButton": CHROME,
    "Run.TButton": CHROME,
    "Add.TButton": SURFACE,
    "Tile.TButton": SURFACE,
    "TileOn.TButton": SURFACE,
    # The sidebar's open row, its count pills, and the card at its foot all
    # stand on the sidebar's grey.
    "SideRowOpen.TFrame": SIDEBAR,
    "Badge.TLabel": SIDEBAR,
    "BadgeOpen.TLabel": ACCENT,
    "Help.TFrame": SIDEBAR,
    "TEntry": SURFACE,
    "TCombobox": SURFACE,
    "Chrome.TCombobox": CHROME,
    "Chip.TFrame": SURFACE,
    # A card stands on the page, not on white: its rounded corners would
    # otherwise show four white nicks on the grey.
    "Box.TFrame": PAGE,
    "BoxOff.TFrame": PAGE,
    # The progress bar is a pill, and a pill is nearly all corner. It used to
    # carry ``background=BLUE`` from the days clam drew it, and the first
    # rounded build showed the trough outlined in blue: not a border, but this
    # trap, bleeding through every antialiased pixel of the pill's edge.
    "Horizontal.TProgressbar": CHROME,
}

#: What sits *inside* a faced frame stands on the face's fill, not on the
#: colour the frame's corners show. A card's style background is the page,
#: for its corners; the fields on the card are on its white. The window's
#: stands-on test reads this before it reads a parent's style.
INSIDE: dict[str, str] = {
    "Box.TFrame": SURFACE,
    "BoxOff.TFrame": SURFACE,
    "SideRowOpen.TFrame": ACCENT,
    "Help.TFrame": HELP,
}


#: Whether this is the Mac build. Asked once, here, and read by everything in
#: the window that has to look different there -- which is the type and the
#: Dock's icon, and nothing else.
MACOS = sys.platform == "darwin"
#: And the Windows build, where the bundled face can be registered.
WINDOWS = sys.platform == "win32"

#: The face and the log's face. On Windows, Inter -- the web site's face,
#: carried in ``assets/fonts`` and registered for this process by
#: ``_load_fonts`` when the theme is applied; ``FACE`` is settled then, and
#: falls back to Segoe UI, the face the rest of the operating system is set
#: in, on a machine where the registering fails. On a Mac, the system's own:
#: Tk gives its default font the family ``.AppleSystemUIFont``, which is San
#: Francisco, and a family Tk cannot find falls back to that same font rather
#: than failing, so this cannot leave a Mac without type. Menlo has been the
#: Mac's monospace since 10.6 and lines up the log the way Consolas does.
FACE = ".AppleSystemUIFont" if MACOS else "Segoe UI"
MONO = "Menlo" if MACOS else "Consolas"

#: The face the program carries, and what it falls back to without it.
BUNDLED_FACE = "Inter"
FALLBACK_FACE = "Segoe UI"


def fonts_folder() -> Path:
    """Where the bundled font files are: beside the icons, in the checkout
    and in the frozen program alike (``icons.folder`` has the two places)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled is not None:
        return Path(bundled) / "assets" / "fonts"
    return Path(__file__).resolve().parents[3] / "assets" / "fonts"


#: Whether the bundled face has been registered with this process. Asked
#: once; ``AddFontResourceEx`` is idempotent but there is no need to ask twice.
_FONTS_LOADED: bool | None = None


def _load_fonts() -> bool:
    """Register the bundled face with Windows, for this process alone.

    ``AddFontResourceExW`` with ``FR_PRIVATE`` makes a font file available to
    the calling process without installing it: nothing is written to the
    system, no administrator is asked, and it is gone when the program
    exits. GDI is what Tk enumerates fonts through on Windows, so a face
    registered this way is a face Tk can be given.

    True when every file registered. False anywhere it cannot be done -- not
    Windows, no files, a GDI that refuses -- and the window is set in the
    fallback face, which is the one it was set in before D132.
    """
    global _FONTS_LOADED
    if _FONTS_LOADED is not None:
        return _FONTS_LOADED
    _FONTS_LOADED = False
    if not WINDOWS:
        return False
    try:
        import ctypes

        # ``getattr`` rather than ``ctypes.windll``: mypy knows the attribute
        # on Windows and not elsewhere, and this file is checked on both.
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        add = windll.gdi32.AddFontResourceExW
        files = sorted(fonts_folder().glob("*.ttf"))
        if not files:
            return False
        fr_private = 0x10
        _FONTS_LOADED = all(add(str(path), fr_private, 0) > 0 for path in files)
    except (OSError, AttributeError):
        return False
    return _FONTS_LOADED


#: How many of a Mac's points make one of this window's.
#:
#: Every size in this window was drawn against Windows, where 9 points are 12
#: pixels (96 to the inch against a point's 72). What a Mac's Tk makes of a
#: point depends on the Tk: an older one counts a point as one pixel, so the
#: same 9 came out a quarter smaller and wanted four thirds; Tk 9 already
#: counts 1.33 pixels to the point, and four thirds on top of that set every
#: word a third too big -- a window that filled a laptop's screen. So the
#: factor is worked out from the Tk's own ``scaling`` when the theme is
#: applied (``_fit_points``). Four thirds is the answer for the old Tk, and
#: stands until then.
MAC_POINTS = 4 / 3

#: The pixels a Windows point is, which is the size everything was drawn at.
_DESIGN_PIXELS_PER_POINT = 96 / 72


def _fit_points(root: tk.Misc) -> None:
    """Set ``MAC_POINTS`` so a point here is as many pixels as on Windows."""
    global MAC_POINTS
    if not MACOS:
        return
    try:
        scaling = float(root.tk.call("tk", "scaling"))
    except (tk.TclError, ValueError):
        return
    if scaling > 0:
        MAC_POINTS = _DESIGN_PIXELS_PER_POINT / scaling


def points(size: int) -> int:
    """A type size as this window was designed in it, for the screen it is on.

    Unchanged off a Mac. Every size in the window goes through here -- the
    styles below, the log, and the lettering drawn on the thumbnails -- so the
    words keep their proportion to the boxes they were measured to fit.
    """
    return round(size * MAC_POINTS) if MACOS else size


def _has_face(name: str) -> bool:
    """Whether this machine actually has that typeface."""
    try:
        return name in tkfont.families()
    except tk.TclError:
        return False


def apply(root: tk.Misc) -> ttk.Style:
    """Dress the window. Returns the style, already configured.

    Idempotent, and safe to call more than once: ttk styles are settings on
    the interpreter rather than objects, so the second call overwrites the
    first with the same values.
    """
    global FACE
    style = ttk.Style(root)
    _fit_points(root)
    if not MACOS:
        # Before any font is looked up: the face has to be registered before
        # Tk enumerates families, and ``_has_face`` below is that enumeration.
        FACE = BUNDLED_FACE if _load_fonts() and _has_face(BUNDLED_FACE) else FALLBACK_FACE

    # clam is the themeable one. Without it every `configure` below is
    # accepted and then ignored by the platform engine, which is worse than
    # not trying: the window would be half restyled.
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - a Tk built without clam
        return style

    family = FACE if _has_face(FACE) else "TkDefaultFont"
    body = (family, points(9))
    strong = (family, points(9), "bold")
    heading = (family, points(10), "bold")
    #: The caption over a group of tabs, and nothing else. Small enough to be
    #: read after the tabs rather than before them.
    small = (family, points(8))
    #: A clickable address. Underlined rather than merely blue: colour alone
    #: is the one mark a colour-blind reader does not get.
    link = (family, points(9), "underline")

    try:
        root.option_add("*Font", body)
        # But not on a ttk label. A ttk label has a ``-font`` of its own,
        # and the line above filled it in on every one -- which beat the
        # style's font, so every bold title and heading in the window was
        # set in the body face. Empty, the label takes its style's.
        root.option_add("*TLabel.Font", "")
    except tk.TclError:
        pass

    # -- the surfaces -----------------------------------------------------
    #
    # White is the default, not the exception. Nearly everything in this
    # window is a setting, settings sit on the content surface, and there are
    # two hundred labels down there against a dozen in the chrome -- so the
    # default goes to the many and the chrome asks for itself by name.
    style.configure(
        ".",
        background=SURFACE,
        foreground=BODY,
        font=body,
        bordercolor=LINE,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        focuscolor=ON_ACCENT,
    )
    style.configure("TFrame", background=SURFACE)
    style.configure("TLabel", background=SURFACE, foreground=BODY)
    style.configure("TSeparator", background=LINE)
    #: The page under the cards, and the one-pixel rule between regions.
    style.configure("Page.TFrame", background=PAGE)
    style.configure("Rule.TFrame", background=LINE)

    #: The line under a control, on the content surface.
    style.configure("Hint.TLabel", background=SURFACE, foreground=HINT)
    #: The same line when what it has to say went wrong: a file that would
    #: not read, a window that could not be found. Red, and nothing else
    #: about it changes, so the sentence reads where the last one did.
    style.configure("Refused.TLabel", background=SURFACE, foreground=RED)
    #: A study's own name, above the fields it needs.
    style.configure("Heading.TLabel", background=SURFACE, foreground=INK, font=heading)
    style.configure("Strong.TLabel", background=SURFACE, foreground=INK, font=strong)
    #: An address on somebody else's site, in the info box and nowhere else.
    #: Blue and underlined, because a label that opens a browser when clicked
    #: has to look unlike the two hundred labels that do nothing -- and blue
    #: is already the colour of the interface here, so it costs the palette
    #: nothing to say "this one answers".
    style.configure("Link.TLabel", background=SURFACE, foreground=INK, font=link)
    #: The same, on the window's surround: the way from the run's one line to
    #: its whole transcript.
    style.configure("ChromeLink.TLabel", background=CHROME, foreground=INK, font=link)

    #: The window's surround: the project strip at the top, the run bar at the
    #: bottom, the summary down the left.
    style.configure("Chrome.TFrame", background=CHROME)
    style.configure("Chrome.TLabel", background=CHROME, foreground=BODY)
    style.configure("ChromeHint.TLabel", background=CHROME, foreground=HINT)
    style.configure("ChromeStrong.TLabel", background=CHROME, foreground=INK, font=strong)
    style.configure(
        "Chip.TLabel",
        background=SURFACE,
        foreground=BODY,
        bordercolor=LINE,
        relief="solid",
        borderwidth=1,
        padding=(6, 2),
    )

    # A ``ttk.Notebook`` used to be here and its styles with it. The strip is
    # built out of buttons now -- see ``Tab.TButton`` below -- because a
    # notebook tab cannot carry a drawing above its label, cannot be given a
    # coloured edge of its own, and has one selected state where this window
    # needs two marks on two axes.

    # -- fields -----------------------------------------------------------
    for kind in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(
            kind,
            fieldbackground=SURFACE,
            background=SURFACE,
            foreground=INK,
            bordercolor=EDGE,
            lightcolor=SURFACE,
            darkcolor=SURFACE,
            insertcolor=INK,
            arrowcolor=BODY,
            padding=(5, 2),
        )
        style.map(
            kind,
            bordercolor=[("focus", ON_ACCENT), ("hover", ACCENT_EDGE)],
            fieldbackground=[("disabled", MUTED), ("readonly", SURFACE)],
            foreground=[("disabled", HINT)],
        )

    # clam calls these `indicatorbackground` and `indicatorforeground`, not
    # `indicatorcolor` -- which every ttk guide says and which this file said
    # first. ttk accepts an option it does not have and silently ignores it,
    # so the wrong name is not an error, it is a tick that stays white with a
    # black mark on it. Checked with `Style.element_options` rather than
    # guessed at a second time.
    #
    # Unticked, the mark is white on white and so invisible; ticked, the box
    # fills blue and the mark is knocked out of it -- which is rule six of the
    # icon set, applied to the one control the set does not draw.
    style.configure(
        "TCheckbutton",
        background=SURFACE,
        foreground=INK,
        indicatorbackground=SURFACE,
        indicatorforeground=SURFACE,
        indicatormargin=(1, 1, 6, 1),
        bordercolor=LINE,
        padding=(0, 3),
    )
    style.map(
        "TCheckbutton",
        indicatorbackground=[("selected", ACCENT), ("disabled", MUTED), ("active", ACCENT_TINT)],
        indicatorforeground=[("selected", INK)],
        bordercolor=[("selected", ON_ACCENT), ("active", ACCENT_EDGE)],
        foreground=[("disabled", HINT)],
        background=[("active", SURFACE)],
    )

    # -- buttons ----------------------------------------------------------
    #
    # These five wear a rounded face (``_rounded`` below), and an image
    # element ignores background, bordercolor and relief entirely. So none
    # of them is set here: the fill, the edge and the pressed and hover
    # states are all in the picture. What is left is what a picture cannot
    # draw -- the words on it, and the room around them.
    # Compact, at the height of a field: Archicad's own dialogs set a button
    # no taller than the list beside it, and so does this.
    style.configure(
        "TButton",
        foreground=INK,
        padding=(10, 0),
        font=body,
    )
    style.map(
        "TButton",
        foreground=[("disabled", HINT)],
    )

    #: The same button, standing on the chrome: the project strip and the run
    #: bar. Its only difference from ``TButton`` is the colour its corners
    #: take, which ``STANDS_ON`` sets -- see the third trap in ``_rounded``.
    style.configure("Chrome.TButton", foreground=INK, padding=(10, 0), font=body)
    style.map("Chrome.TButton", foreground=[("disabled", HINT)])
    style.configure("Chrome.TCombobox", foreground=INK)

    #: The chevron that folds the sheets panel to its edge and back. A mark
    #: on the chrome rather than a button face: it is the smallest control in
    #: the window and the one used least.
    style.configure(
        "Fold.TButton",
        background=SIDEBAR,
        foreground=BODY,
        bordercolor=SIDEBAR,
        lightcolor=SIDEBAR,
        darkcolor=SIDEBAR,
        relief="flat",
        padding=(5, 0),
        font=strong,
    )
    style.map("Fold.TButton", foreground=[("active", ON_ACCENT)], background=[("active", SIDEBAR)])

    #: A tool on the project bar: no face until the pointer is on it.
    style.configure(
        "Tool.TButton",
        background=CHROME,
        foreground=BODY,
        bordercolor=CHROME,
        lightcolor=CHROME,
        darkcolor=CHROME,
        relief="flat",
        padding=(8, 2),
        font=body,
    )
    style.map(
        "Tool.TButton",
        background=[("pressed", ACCENT_EDGE), ("active", ACCENT_TINT)],
        bordercolor=[("active", ACCENT_TINT)],
        lightcolor=[("active", ACCENT_TINT)],
        darkcolor=[("active", ACCENT_TINT)],
        foreground=[("active", ON_ACCENT)],
    )

    #: Run. The one filled control in the window: the accent, with ink on
    #: it. It was tinted once, on the grounds that a solid colour beside grey
    #: reads as a warning; in use the tint read as one more of the six
    #: buttons on the bar, and the action every page leads to was the hardest
    #: thing on it to find. Off, it wears the grey face every button does,
    #: and its words say why.
    style.configure(
        "Run.TButton",
        foreground=INK,
        padding=(12, 0),
        font=strong,
    )
    style.map(
        "Run.TButton",
        foreground=[("disabled", HINT), ("!disabled", INK)],
    )

    # -- the sidebar ------------------------------------------------------
    #
    # The pages down the left, in three groups under small capitals, the way
    # Archicad lists the pages of a settings dialog. A row is a frame -- the
    # open one wears a rounded face in the accent -- holding the page's name,
    # what it will make, and the switch that queues it; each of those takes
    # the row's colour, so there are two of every style: on the surround, and
    # on the accent.
    caption = (family, points(8), "bold")
    style.configure("Side.TFrame", background=SIDEBAR)
    style.configure("SideRow.TFrame", background=SIDEBAR)
    style.configure("SideRowOpen.TFrame", background=SIDEBAR)
    style.configure("Group.TLabel", background=SIDEBAR, foreground=CAPTION, font=caption)
    for name, ground, text, face in (
        ("Side.TButton", SIDEBAR, INK, body),
        ("SideOpen.TButton", ACCENT, INK, strong),
    ):
        style.configure(
            name,
            background=ground,
            foreground=text,
            bordercolor=ground,
            lightcolor=ground,
            darkcolor=ground,
            relief="flat",
            padding=(2, 4),
            anchor="w",
            font=face,
            width=0,
            focuscolor=text,
        )
        style.map(name, background=[("active", ground)], foreground=[("active", text)])
    #: What a page will make, as a pill beside its name: the tinted pill on
    #: the surround, a white one on the open row.
    style.configure("Badge.TLabel", background=SIDEBAR, foreground=ON_ACCENT, font=small)
    style.configure("BadgeOpen.TLabel", background=ACCENT, foreground=INK, font=small)

    #: The card at the foot of the sidebar: whatever is under the pointer,
    #: what it is, and what happens when it is wrong.
    style.configure("Help.TFrame", background=SIDEBAR)
    style.configure("HelpTitle.TLabel", background=HELP, foreground=INK, font=strong)
    style.configure("HelpIdle.TLabel", background=HELP, foreground=CAPTION, font=strong)
    style.configure("Help.TLabel", background=HELP, foreground=INK)
    style.configure("HelpHint.TLabel", background=HELP, foreground="#4A4A4A", font=small)
    style.configure(
        "HelpState.TLabel", background=ACCENT_TINT, foreground=ON_ACCENT, font=small, padding=(6, 0)
    )

    #: The page's own name over its panels, and the one line under it.
    style.configure("PageTitle.TLabel", background=PAGE, foreground=INK, font=heading)
    style.configure("PageBlurb.TLabel", background=PAGE, foreground=CAPTION)

    #: The tool bar's name of the program.
    style.configure("Brand.TLabel", background=CHROME, foreground=INK, font=heading)

    #: The triangle on a panel's header that folds it.
    for name, ground in (("Disclose.TButton", HEAD_OFF), ("DiscloseOn.TButton", HEAD_ON)):
        style.configure(
            name,
            background=ground,
            foreground=BODY,
            bordercolor=ground,
            lightcolor=ground,
            darkcolor=ground,
            relief="flat",
            padding=(0, 0),
            width=0,
            font=body,
        )
        style.map(name, background=[("active", ground)], foreground=[("active", ON_ACCENT)])

    #: The newest line out of a run, and the only one shown. Monospaced
    #: because it prints layer names and tallies that want to line up.
    style.configure("Note.TLabel", background=CHROME, foreground=BODY, font=log_font(), anchor="w")

    #: A tile in a choice row: its drawing, and the word that names it where
    #: it has one (``window.Tiles`` widens those itself). The hour chips wear
    #: this too, and fourteen of them have to fit a card's row.
    style.configure(
        "Tile.TButton",
        padding=(4, 1),
    )
    #: The chosen tile. Filled blue, and the drawing inside it is the white
    #: one -- the same move the printer driver makes.
    #: The chosen tile. Tinted and edged in blue rather than filled with it:
    #: these tiles keep their drawing, and a white-on-blue sun is not a sun.
    #: The icon-only tiles on the design boards invert; these carry a picture
    #: that has to stay readable, so they take the named-card treatment.
    style.configure(
        "TileOn.TButton",
        padding=(4, 1),
        foreground=INK,
    )
    style.map("TileOn.TButton", foreground=[("disabled", HINT), ("!disabled", INK)])

    # -- chips: a chosen name, and the button that drops it ----------------
    #
    # What a list of layers looks like now that it is not a comma-joined
    # string in a text box. The cross is a real button with its own focus, so
    # a name can be dropped from the keyboard as well as the pointer.
    style.configure(
        "Chip.TFrame",
        background=ACCENT_TINT,
        bordercolor=ACCENT_EDGE,
        lightcolor=ACCENT_TINT,
        darkcolor=ACCENT_TINT,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Chip.TLabel", background=ACCENT_TINT, foreground=ON_ACCENT, padding=(7, 2, 3, 2)
    )
    style.configure(
        "ChipDrop.TButton",
        background=ACCENT_TINT,
        foreground=ON_ACCENT,
        bordercolor=ACCENT_TINT,
        lightcolor=ACCENT_TINT,
        darkcolor=ACCENT_TINT,
        relief="flat",
        padding=(0, 0),
        font=body,
    )
    style.map(
        "ChipDrop.TButton",
        background=[("active", ACCENT_EDGE), ("pressed", ACCENT_EDGE)],
        foreground=[("active", ON_ACCENT)],
    )
    #: The button that opens the project's own list. Dashed, because it is an
    #: invitation rather than a value -- the chips beside it are the values.
    style.configure(
        "Add.TButton",
        foreground=BODY,
        padding=(7, 1),
        font=body,
    )
    style.map(
        "Add.TButton",
        foreground=[("active", ON_ACCENT)],
    )

    # -- the info band -----------------------------------------------------
    style.configure("Info.TFrame", background=CHROME)
    style.configure("Info.TLabel", background=CHROME, foreground=INK)
    style.configure("InfoTitle.TLabel", background=CHROME, foreground=INK, font=strong)
    style.configure("InfoIdle.TLabel", background=CHROME, foreground=HINT, font=strong)
    style.configure("InfoState.TLabel", background=CHROME, foreground=ON_ACCENT)
    style.configure("InfoHint.TLabel", background=CHROME, foreground=HINT)

    # -- the sheets dock ---------------------------------------------------
    #
    # Its own grey, so the white sheets sit on it the way pages sit in
    # InDesign's panel rather than reading as part of the page beside it.
    style.configure("Dock.TFrame", background=SIDEBAR)
    style.configure("DockTitle.TLabel", background=SIDEBAR, foreground=INK, font=strong)
    style.configure("DockCount.TLabel", background=SIDEBAR, foreground=ON_ACCENT, font=strong)
    style.configure("DockHint.TLabel", background=SIDEBAR, foreground=CAPTION, font=small)
    style.configure("DockStudy.TLabel", background=SIDEBAR, foreground=INK, font=strong)
    style.configure("DockDay.TLabel", background=SIDEBAR, foreground=CAPTION, font=small)

    #: A study's block on a settings page: its tick, its name, and what it
    #: will make, on a tinted bar with a rule under it. Not a box with a
    #: border, because ttk draws borders square and six of them down a page
    #: reads as six boxes; a bar and a rule group the same rows for less.
    #: A study's tick, which is also the header of its block: the name in the
    #: heading face on a tinted bar across the page. Switched off, the bar
    #: goes grey -- a study nobody has turned on should not look like a live
    #: form with a cleared box somewhere above it.
    # The header is placed at a fixed height (``PANEL_HEAD``, which the panel
    # faces are drawn to), so the tick has to fit it rather than ask for more.
    # At a Mac's four-thirds type the heading face is 20 px a line, and with
    # six above and below it wanted 34 of the 29 it is given: the descenders
    # were cut off every study's name. Placed, the content is centred anyway,
    # so a Mac simply goes without the padding.
    study_pad = (7, 0) if MACOS else (7, 6)
    style.configure(
        "Study.TCheckbutton",
        background=ACCENT_TINT,
        foreground=INK,
        font=heading,
        padding=study_pad,
    )
    style.map("Study.TCheckbutton", background=[("active", ACCENT_TINT)])
    style.configure(
        "StudyOff.TCheckbutton",
        background=HEAD_OFF,
        foreground=BODY,
        font=heading,
        padding=study_pad,
    )
    style.map("StudyOff.TCheckbutton", background=[("active", HEAD_OFF)])

    #: A study's box: a rounded border with the header's tint drawn into its
    #: top slice (``_rounded``). Off, the border and the header go grey.
    style.configure("Box.TFrame", background=SURFACE)
    style.configure("BoxOff.TFrame", background=SURFACE)
    #: The title of a box that is not a study and so has no tick to head it.
    #: A settings card's title, on the grey band: it is not switched on, so
    #: it does not wear the tint. Set the way Archicad heads a section.
    style.configure("BoxTitle.TLabel", background=HEAD_OFF, foreground=INK, font=strong)
    #: A study's name on its panel's header, on the tint and off it.
    style.configure("StudyTitle.TLabel", background=HEAD_ON, foreground=INK, font=strong)
    style.configure("StudyTitleOff.TLabel", background=HEAD_OFF, foreground=INK, font=strong)
    #: What the box will make, at the right of its header.
    style.configure("PanelSays.TLabel", background=HEAD_ON, foreground=ON_ACCENT)
    style.configure("PanelSaysOff.TLabel", background=HEAD_OFF, foreground=HINT)

    _own_tick(style)
    _switches(style)

    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=SURFACE,
        bordercolor=LINE,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        thickness=10,
    )
    #: The one slider in the program: the reference image's opacity. A white
    #: knob with the field edge on the field's own grey trough, so it reads
    #: as a control beside the fields it sits among rather than as clam's
    #: raised grey bar.
    style.configure(
        "Horizontal.TScale",
        background=SURFACE,
        troughcolor=MUTED,
        bordercolor=EDGE,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        sliderlength=18,
    )
    style.map(
        "Horizontal.TScale",
        background=[("active", ACCENT_TINT)],
        bordercolor=[("active", ON_ACCENT), ("focus", ON_ACCENT)],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=MUTED,
        troughcolor=SURFACE,
        bordercolor=SURFACE,
        arrowcolor=BODY,
        lightcolor=MUTED,
        darkcolor=MUTED,
    )
    style.map("Vertical.TScrollbar", background=[("active", "#CFCCC2")])
    #: The same bar in the sheets panel, whose gutter is the panel's grey.
    style.configure("Dock.Vertical.TScrollbar", troughcolor=SIDEBAR, bordercolor=SIDEBAR)
    #: And on a page, whose gutter is the page's grey.
    style.configure("Page.Vertical.TScrollbar", troughcolor=PAGE, bordercolor=PAGE)

    # Last, and it has to be. It sets the background of everything that wears
    # a face to the colour that thing stands on, and any ``configure`` after
    # it that names a background undoes that -- which is how the progress bar
    # kept its blue the first time, and showed it through the pill's corners.
    _rounded(style)

    return style


def _rounded(style: ttk.Style) -> None:
    """Round the corners, by wearing a picture instead of clam's drawn border.

    No amount of ``style.configure`` will round a corner: clam's border is a
    compiled-in element and its shape is square. The way round it is the way
    the checkbutton's tick already goes -- ``style.element_create(..., "image",
    ...)`` -- with one addition. An image element given a ``border`` is a
    NINE-SLICE: Tk holds the four corners at their drawn size and fills what
    is between them from the middle of the picture, so one face with a 4 px
    radius dresses a button of any width and the corner never distorts.

    The faces are drawn by ``scripts/make_icons.py`` and committed beside the
    icons, for the same reason those are: Tk reads PNG by itself, so the
    window never has to draw one.

    Four traps, each of which is silent, and each of which has a test in
    ``tests/unit/test_theme.py`` so that it stays caught.

    **A style inherits its parent's layout.** Changing ``TButton`` changes
    every ``*.TButton`` that has not been given a layout of its own. So what
    each one wears is declared, in ``WEARS``, and nothing is left to inherit.

    **An image element ignores ``background`` for its own drawing.** Anything
    wearing a face says what state it is in with a different picture, never
    a different colour: the chosen tile, the pressed button and the hovered
    tab are faces rather than fills.

    **But the corners it leaves clear are filled with that same background.**
    The face is a rounded shape in a square widget, and what shows through
    the four corners is the *style's* background -- not whatever the widget
    happens to be standing on. A button styled for the white page and placed
    on the grey run bar therefore has four white nicks in its corners, which
    at a 4 px radius is a fault nobody can name and everybody can see. So
    what each faced style stands on is declared too, in ``STANDS_ON``, and a
    test walks the real window comparing every faced widget with its parent.

    **And the middle of a nine-slice is tiled, not stretched.** Tk stamps the
    centre of the picture across the widget as many times as it takes. Drawn
    at 16 px a face has a 6 px middle, so a 700 px field is six hundred image
    blits and a settings box is thirteen thousand: the window's first
    ``update_idletasks`` took twenty-six seconds, and nothing about that shows
    in a picture of the face. So the faces are drawn about as big as the
    biggest thing that wears them (see ``make_icons.py``), and the middle is
    stamped once or twice. A widget smaller than its face shows less middle.

    Leaves the theme alone on any failure. Square corners are worth a great
    deal less than a window that opens.
    """
    from sun_study.app import icons

    def worn(*names: str) -> list[tk.PhotoImage] | None:
        """Those faces, or nothing if any of them will not load."""
        found = [icons.face(name) for name in names]
        return None if any(face is None for face in found) else found  # type: ignore[return-value]

    def inside(*children: Any) -> Any:
        """One level of a ttk layout. Typed ``Any`` because the stubs spell a
        layout as a recursive alias that a helper building one a level at a
        time cannot be made to satisfy, and the interpreter checks it anyway."""
        return {"sticky": "nswe", "children": list(children)}

    #: A button's innards, which are the same whatever it wears.
    label: Any = (
        "Button.focus",
        inside(("Button.padding", inside(("Button.label", {"sticky": "nswe"})))),
    )
    #: What clam draws a button with, for the styles that stay flat.
    flat: Any = [("Button.border", {"sticky": "nswe", "border": "1", "children": [label]})]

    def element(
        name: str,
        faces: list[tk.PhotoImage],
        states: tuple[str, ...],
        border: int | tuple[int, int, int, int],
        sticky: str = "nsew",
        *,
        wide: int = 0,
        tall: int = 0,
    ) -> None:
        """One nine-slice element out of a default face and its states.

        The minimum size is said outright, as the corners and a pixel of
        middle. Left unsaid, an image element asks for the whole picture --
        and the pictures are drawn big on purpose (the fourth trap), so every
        button would want to be 192 px wide and the last tab would be pushed
        off the end of the strip.

        ``wide`` and ``tall`` are for the two things that are never stretched
        one way: a bar is exactly as tall as its picture and a scrollbar thumb
        exactly as wide. Their border on that side is nought, so the sum of
        the corners would make a bar one pixel high.
        """
        left, top, right, bottom = (border,) * 4 if isinstance(border, int) else border
        try:
            style.element_create(
                name,
                "image",
                faces[0],
                *[(state, face) for state, face in zip(states, faces[1:], strict=True)],
                border=border,
                sticky=sticky,
                width=wide or left + right + 1,
                height=tall or top + bottom + 1,
            )
        except tk.TclError:
            # Already there: `apply` has been called twice on this
            # interpreter, which is allowed and means the element exists.
            pass

    plain = worn("face_up", "face_hover", "face_down", "face_off")
    running = worn("face_run", "face_run_hover", "face_run_down", "face_off")
    fields = worn("field", "field_focus", "field_off")
    if plain is None or running is None or fields is None:
        return
    adding = worn("add", "add_hover", "add_down")
    tiles = worn("face_up", "face_hover", "face_chosen")
    chip = worn("chip")
    side = worn("side_open")
    badges = worn("badge", "badge_open")
    help_card = worn("helpcard")
    bars = worn("bar_trough", "bar_fill")
    thumbs = worn("thumb", "thumb_hover")
    panels = worn("panel_on", "panel_off")

    # The lifted faces are a pixel taller than they are wide: the last row is
    # the shadow, and it belongs to the bottom slice.
    lifted = (FACE_SLICE, FACE_SLICE, FACE_SLICE, FACE_SLICE + 1)
    element("Loriini.button", plain, ("active", "pressed", "disabled"), lifted)
    element("Loriini.run", running, ("active", "pressed", "disabled"), lifted)
    element("Loriini.field", fields, ("focus", "disabled"), FACE_SLICE)
    if adding is not None:
        element("Loriini.add", adding, ("active", "pressed"), FACE_SLICE)
    if tiles is not None:
        element("Loriini.tile", tiles[:2], ("active",), lifted)
        # The chosen tile is a different *picture*, not a different
        # background. Two faces, never one face and a colour.
        element("Loriini.tileon", [tiles[2]], (), lifted)

    #: Which faces actually loaded. A style whose face is missing is left on
    #: clam's border rather than left with no layout at all.
    ready = {
        "button": True,
        "run": True,
        "add": adding is not None,
        "tile": tiles is not None,
        "tileon": tiles is not None,
    }
    #: The same innards without the focus ring. A tab or a tile is pressed
    #: with the mouse and shows its state in its face; the dotted rectangle
    #: Tk draws round a focused button read as a second selection mark.
    quiet: Any = ("Button.padding", inside(("Button.label", {"sticky": "nswe"})))
    #: Flat, and without the ring: a sidebar row is clicked to open its page
    #: and shows that in its blue bar, so the dotted box Tk drew round the
    #: last one clicked stood beside the bar as a second, stale selection.
    flat_quiet: Any = [("Button.border", {"sticky": "nswe", "border": "1", "children": [quiet]})]
    for name, worn_as in WEARS.items():
        if name in NO_RING:
            style.layout(name, flat_quiet)
        elif worn_as == "flat" or not ready.get(worn_as, False):
            style.layout(name, flat)
        elif worn_as in {"tile", "tileon"}:
            style.layout(name, [(f"Loriini.{worn_as}", inside(quiet))])
        else:
            style.layout(name, [(f"Loriini.{worn_as}", inside(label))])

    if chip is not None:
        element("Loriini.chip", chip, (), FACE_SLICE)
        style.layout("Chip.TFrame", [("Loriini.chip", {"sticky": "nswe"})])

    if panels is not None:
        # The header's tint and the rule under it are in the top slice, so
        # that slice is exactly as tall as the header plus its rule.
        box = (PANEL_SLICE, PANEL_HEAD + 1, PANEL_SLICE, PANEL_SLICE)
        element("Loriini.box", [panels[0]], (), box)
        element("Loriini.boxoff", [panels[1]], (), box)
        style.layout("Box.TFrame", [("Loriini.box", {"sticky": "nswe"})])
        style.layout("BoxOff.TFrame", [("Loriini.boxoff", {"sticky": "nswe"})])

    # The sidebar: the open row's blue bar, the count pills, and the card at
    # the foot that explains what is under the pointer.
    if side is not None:
        element("Loriini.sideopen", side, (), 11)
        style.layout("SideRowOpen.TFrame", [("Loriini.sideopen", {"sticky": "nswe"})])
    if badges is not None:
        pill: Any = inside(("Label.padding", inside(("Label.label", {"sticky": "nswe"}))))
        element("Loriini.badge", [badges[0]], (), 8)
        element("Loriini.badgeopen", [badges[1]], (), 8)
        style.layout("Badge.TLabel", [("Loriini.badge", pill)])
        style.layout("BadgeOpen.TLabel", [("Loriini.badgeopen", pill)])
        for name in ("Badge.TLabel", "BadgeOpen.TLabel"):
            style.configure(name, padding=(2, 0), anchor="center")
    if help_card is not None:
        element("Loriini.help", help_card, (), PANEL_SLICE)
        style.layout("Help.TFrame", [("Loriini.help", {"sticky": "nswe"})])

    chevron = _chevron(style)
    for kind in ("TEntry", "TCombobox"):
        part = kind.split("T", 1)[1]
        # The arrow goes *inside* the field element, not beside it. Clam has
        # it as a sibling, which was fine while the field was a square box
        # drawn to the same height; against a rounded face it reads as a
        # second little button parked next to the field.
        children: list[tuple[str, dict[str, object]]] = []
        if kind == "TCombobox":
            arrow = chevron or f"{part}.downarrow"
            children.append((arrow, {"side": "right", "sticky": "ns"}))
        children.append((f"{part}.padding", inside((f"{part}.textarea", {"sticky": "nswe"}))))
        style.layout(kind, [("Loriini.field", inside(*children))])

    if bars is not None:
        # A pill: the one control whose ends mean nothing. Neither picture is
        # ever stretched upward -- the bar is exactly as tall as they are --
        # so the round ends stay round.
        element("Loriini.trough", [bars[0]], (), (5, 0, 5, 0), sticky="ew", tall=10)
        element("Loriini.pbar", [bars[1]], (), (5, 0, 5, 0), sticky="nsew", tall=10)
        style.layout(
            "Horizontal.TProgressbar",
            [
                (
                    "Loriini.trough",
                    {
                        "sticky": "ew",
                        "children": [("Loriini.pbar", {"side": "left", "sticky": "ns"})],
                    },
                )
            ],
        )

    if thumbs is not None:
        # No arrows. Nobody has pressed one since wheels were put on mice,
        # and without them the bar is a slim pill in a quiet gutter -- which
        # is how every panel in Archicad and InDesign scrolls now.
        element("Loriini.thumb", thumbs, ("active",), (0, 5, 0, 5), wide=12)
        style.layout(
            "Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {"sticky": "ns", "children": [("Loriini.thumb", {"sticky": "nswe"})]},
                )
            ],
        )

    # The third trap, closed: every faced style is told what it stands on, so
    # the corners its face leaves clear are that colour and not white.
    for name, ground in STANDS_ON.items():
        if name == "Horizontal.TProgressbar" and bars is None:
            # Still clam's own bar, which is drawn *in* its background colour:
            # the chrome here would be a bar nobody can see filling.
            continue
        style.configure(name, background=ground)


#: The chevrons made, one per interpreter, kept because Tk forgets an image
#: nothing in Python holds.
_CHEVRON: list[tk.PhotoImage] = []


def _chevron(style: ttk.Style) -> str | None:
    """A drop-down's mark: a bare chevron, drawn on nothing.

    Clam's arrow is a little bordered box filled with the style's background.
    Inside a rounded field that box read as a second button parked in the
    first, and on the project picker -- whose background is the chrome, for
    its corners -- it was a grey square in a white field. An image element
    paints only its own pixels, so the field's face shows round the mark.

    Returns the element's name, or ``None`` to keep clam's arrow.
    """
    name = "Loriini.chevron"
    if name in style.element_names():
        # This interpreter has it already: ``apply`` was called twice.
        return name
    # Nine wide and five tall, two pixels thick, then six of air on the right
    # so the mark sits inside the field's rounded end rather than on it.
    wide, tall, air = 9, 5, 6
    try:
        image = tk.PhotoImage(width=wide + air, height=tall + 1)
        for x in range(wide):
            y = min(x, wide - 1 - x)
            image.put(BODY, to=(x, y, x + 1, y + 2))
        style.element_create(name, "image", image, sticky="")
    except tk.TclError:
        return None
    _CHEVRON.append(image)
    return name


def _own_tick(style: ttk.Style) -> None:
    """Replace the checkbutton indicator with a drawn one.

    Tk 9 draws clam's selected indicator as a cross. A cross means no, and the
    control it sits on means yes -- which is not a polish complaint: the study
    ticks are the six most important controls in the window and half the point
    of them is being readable at a glance from the tab strip.

    So the indicator becomes two images from the icon set, which also makes it
    the same blue-and-knocked-out-white as everything else that is chosen.
    Only the element is swapped; clam's own layout around it is kept, so the
    padding, the focus ring and the label are untouched.

    Leaves the theme alone on any failure. An ugly tick is worth a great deal
    less than a window that opens.
    """
    # Imported here rather than at the top: `icons` needs a Tk root to make a
    # PhotoImage, and this is the only thing in the module that needs it.
    from sun_study.app import icons

    off = icons.named("tick_off", 16)
    on = icons.named("tick_on", 16)
    if off is None or on is None:
        return

    element = "Loriini.Checkbutton.indicator"
    try:
        style.element_create(element, "image", off, ("selected", on), sticky="", border=0)
    except tk.TclError:
        # Already created -- `apply` has been called twice on this
        # interpreter, which is allowed and means the element is there.
        pass
    try:
        style.layout(
            "TCheckbutton",
            [
                (
                    "Checkbutton.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            (element, {"side": "left", "sticky": ""}),
                            (
                                "Checkbutton.focus",
                                {
                                    "side": "left",
                                    "sticky": "w",
                                    "children": [("Checkbutton.label", {"sticky": "nswe"})],
                                },
                            ),
                        ],
                    },
                )
            ],
        )
    except tk.TclError:  # pragma: no cover - a Tk that will not take a layout
        return
    # The drawn box carries its own margin, so clam's is no longer wanted.
    style.configure("TCheckbutton", indicatormargin=(0, 0, 6, 0))


def _switches(style: ttk.Style) -> None:
    """The switch a study is turned on with, as a checkbutton's indicator.

    A tick in a 12 px box was the most important control on every page and
    the smallest thing on it. A switch says the same yes or no at a size a
    pointer finds without looking, and reads as *on* from across the room --
    which is what the sidebar needs, where it is the whole of what a row says
    about its study.

    Two pictures each way: the blue switch on the sidebar's grey and on a
    panel's header, and the white one on the open row, which is blue already.
    Leaves the checkbuttons as they are on any failure.
    """
    from sun_study.app import icons

    pictures: dict[str, tk.PhotoImage] = {}
    for name in ("switch_off", "switch_on", "switch_off_light", "switch_on_light"):
        picture = icons.face(name)
        if picture is None:
            return
        pictures[name] = picture
    for element, off, on in (
        ("Loriini.switch", "switch_off", "switch_on"),
        ("Loriini.switchlight", "switch_off_light", "switch_on_light"),
    ):
        try:
            style.element_create(
                element, "image", pictures[off], ("selected", pictures[on]), sticky="", border=0
            )
        except tk.TclError:
            pass  # made already: ``apply`` called twice on this interpreter

    def laid(element: str) -> Any:
        return [
            (
                "Checkbutton.padding",
                {
                    "sticky": "nswe",
                    "children": [
                        # No focus ring: round a switch with no words beside
                        # it, it was a dotted sliver that stayed after a click.
                        (element, {"side": "left", "sticky": ""}),
                        ("Checkbutton.label", {"side": "left", "sticky": "w"}),
                    ],
                },
            )
        ]

    for name, ground, element in (
        ("Switch.TCheckbutton", SIDEBAR, "Loriini.switch"),
        ("SwitchOpen.TCheckbutton", ACCENT, "Loriini.switchlight"),
        ("SwitchHead.TCheckbutton", HEAD_ON, "Loriini.switch"),
        ("SwitchHeadOff.TCheckbutton", HEAD_OFF, "Loriini.switch"),
        ("SwitchPanel.TCheckbutton", SURFACE, "Loriini.switch"),
    ):
        try:
            style.layout(name, laid(element))
        except tk.TclError:  # pragma: no cover - a Tk that will not take a layout
            return
        style.configure(name, background=ground, foreground=BODY, padding=(0, 0), indicatormargin=0)
        style.map(name, background=[("active", ground)], foreground=[("disabled", HINT)])


#: The menu's three lines, one per interpreter, kept because Tk forgets an
#: image nothing in Python holds.
_MENU: dict[str, tk.PhotoImage] = {}


def menu_glyph(root: tk.Misc) -> tk.PhotoImage | None:
    """Three lines, the mark every program puts on the button that opens its
    menu. Drawn here rather than in the icon set because it is three
    rectangles, and fourteen pixels of them."""
    key = str(root.tk)
    made = _MENU.get(key)
    if made is not None:
        return made
    try:
        image = tk.PhotoImage(master=root, width=14, height=12)
        for y in (1, 5, 9):
            image.put(BODY, to=(0, y, 14, y + 2))
    except tk.TclError:
        return None
    _MENU[key] = image
    return image


def log_font() -> tuple[str, int]:
    """What the log is set in."""
    return (MONO, points(9)) if _has_face(MONO) else ("TkFixedFont", points(9))
