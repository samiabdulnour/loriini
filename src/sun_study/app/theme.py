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
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

# -- the palette, the same one the icons are drawn from --------------------

#: Archicad's own chrome, sampled off a screenshot of it rather than guessed:
#: its toolbars and palette surrounds are a neutral #F0F0F0, its panels are
#: white, and its field edges are around #8D8D8D. This window sits inside
#: Archicad all day and an earlier warm grey made it look like a different
#: program parked on top of it.
CHROME = "#F0F0F0"

#: Where the settings are. White, because the icons are drawn on white and a
#: sheet of paper on grey is not a sheet of paper. Archicad's panels agree.
SURFACE = "#FFFFFF"

#: A control nobody has chosen, and the trough of the progress bar.
MUTED = "#E4E4E4"

INK = "#1F1F1F"
BODY = "#3C3C3C"
#: The line under a control. 5.5:1 on white, which is the point of it.
HINT = "#6A6A6A"
#: A divider. Archicad's own are lighter than its field edges, and so are
#: these -- LINE separates, EDGE encloses something you can type in.
LINE = "#DCDCDC"
EDGE = "#8D8D8D"

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
#: How many pixels of a face are corner rather than stretch. The faces are
#: 16 px with a 4 px radius, so 5 leaves the middle 6 to be pulled about.
FACE_SLICE = 5

#: How tall a panel's header is. ``scripts/make_icons.py`` holds the same
#: number, and has to: the header's tint and the rule under it are drawn into
#: the top slice of the panel's face, so the window must place the header at
#: exactly the height the picture was drawn for. A test holds the two together.
PANEL_HEAD = 32

#: The tint behind a study's header, on and off. Drawn into the panel faces
#: and worn by the tick that sits on them, so they have to match to the digit.
HEAD_ON = BLUE_TINT
HEAD_OFF = "#F1F1F0"

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
WEARS: dict[str, str] = {
    "TButton": "button",
    "Chrome.TButton": "button",
    "Run.TButton": "run",
    "Add.TButton": "add",
    "Tile.TButton": "tile",
    "TileOn.TButton": "tileon",
    # A tab wears a tab, not a button: chrome at rest, a rounded tint under
    # the pointer, and the page's own white under a blue cap when it is open.
    "Tab.TButton": "tab",
    "TabQueued.TButton": "tab",
    "TabOpen.TButton": "tabopen",
    "TabOpenQueued.TButton": "tabopen",
    # The cross on a chip is inside a rounded box already, and a second one
    # around a 13 px glyph is a box around a box.
    "ChipDrop.TButton": "flat",
    # The chevron that folds the sheets panel away: a mark, not a button face.
    "Fold.TButton": "flat",
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
    "Tab.TButton": CHROME,
    "TabQueued.TButton": CHROME,
    "TabOpen.TButton": CHROME,
    "TabOpenQueued.TButton": CHROME,
    "TEntry": SURFACE,
    "TCombobox": SURFACE,
    "Chrome.TCombobox": CHROME,
    "Chip.TFrame": SURFACE,
    "Box.TFrame": SURFACE,
    "BoxOff.TFrame": SURFACE,
    # The progress bar is a pill, and a pill is nearly all corner. It used to
    # carry ``background=BLUE`` from the days clam drew it, and the first
    # rounded build showed the trough outlined in blue: not a border, but this
    # trap, bleeding through every antialiased pixel of the pill's edge.
    "Horizontal.TProgressbar": CHROME,
}


FACE = "Segoe UI"
MONO = "Consolas"


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
    style = ttk.Style(root)

    # clam is the themeable one. Without it every `configure` below is
    # accepted and then ignored by the platform engine, which is worse than
    # not trying: the window would be half restyled.
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - a Tk built without clam
        return style

    body = (FACE, 9) if _has_face(FACE) else ("TkDefaultFont", 9)
    strong = (FACE, 9, "bold") if _has_face(FACE) else ("TkDefaultFont", 9, "bold")
    heading = (FACE, 10, "bold") if _has_face(FACE) else ("TkDefaultFont", 10, "bold")
    #: The caption over a group of tabs, and nothing else. Small enough to be
    #: read after the tabs rather than before them.
    small = (FACE, 8) if _has_face(FACE) else ("TkDefaultFont", 8)

    try:
        root.option_add("*Font", body)
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
        focuscolor=BLUE,
    )
    style.configure("TFrame", background=SURFACE)
    style.configure("TLabel", background=SURFACE, foreground=BODY)
    style.configure("TSeparator", background=LINE)

    #: The line under a control, on the content surface.
    style.configure("Hint.TLabel", background=SURFACE, foreground=HINT)
    #: A study's own name, above the fields it needs.
    style.configure("Heading.TLabel", background=SURFACE, foreground=INK, font=heading)
    style.configure("Strong.TLabel", background=SURFACE, foreground=INK, font=strong)

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
            padding=(5, 4),
        )
        style.map(
            kind,
            bordercolor=[("focus", BLUE), ("hover", BLUE_EDGE)],
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
        indicatorbackground=[("selected", BLUE), ("disabled", MUTED), ("active", BLUE_TINT)],
        indicatorforeground=[("selected", SURFACE)],
        bordercolor=[("selected", BLUE_DEEP), ("active", BLUE_EDGE)],
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
    style.configure(
        "TButton",
        foreground=INK,
        padding=(12, 5),
        font=body,
    )
    style.map(
        "TButton",
        foreground=[("disabled", HINT)],
    )

    #: The same button, standing on the chrome: the project strip and the run
    #: bar. Its only difference from ``TButton`` is the colour its corners
    #: take, which ``STANDS_ON`` sets -- see the third trap in ``_rounded``.
    style.configure("Chrome.TButton", foreground=INK, padding=(12, 5), font=body)
    style.map("Chrome.TButton", foreground=[("disabled", HINT)])
    style.configure("Chrome.TCombobox", foreground=INK)

    #: The chevron that folds the sheets panel to its edge and back. A mark
    #: on the chrome rather than a button face: it is the smallest control in
    #: the window and the one used least.
    style.configure(
        "Fold.TButton",
        background=CHROME,
        foreground=HINT,
        bordercolor=CHROME,
        lightcolor=CHROME,
        darkcolor=CHROME,
        relief="flat",
        padding=(5, 0),
        font=strong,
    )
    style.map("Fold.TButton", foreground=[("active", BLUE_DEEP)], background=[("active", CHROME)])

    #: Run. The one emphasised control in the window, tinted rather than
    #: filled: a solid blue button next to three grey ones reads as a warning.
    style.configure(
        "Run.TButton",
        foreground=BLUE_DEEP,
        padding=(14, 6),
        font=strong,
    )
    style.map(
        "Run.TButton",
        foreground=[("disabled", HINT)],
    )

    #: A tab in the strip: one drawing at 32 px with the section's name under
    #: it. No border and no fill when it is not the open one, because six
    #: outlined boxes in a row read as six boxes rather than as one strip.
    #:
    #: Four styles rather than one style with two maps, because a tab carries
    #: two facts that must never be drawn as the same thing -- which is the
    #: fault this replaces, where a tinted card meant "queued" and there was
    #: nothing at all for "you are here".
    #:
    #: *Open* is the white surface, the same white as the page beneath it, so
    #: the tab and its page read as one sheet; a blue rule over the tab closes
    #: it. *Queued* is the blue label and the dot after the name. A tab can be
    #: both at once, and then it says both.
    # Three more pixels at the top than at the sides: that is where the open
    # tab's blue cap is drawn, and every tab keeps the room so that opening
    # one does not move its drawing down.
    tab_pad = (10, 10, 10, 7)
    for name, text, face in (
        ("Tab.TButton", BODY, body),
        ("TabOpen.TButton", INK, strong),
        ("TabQueued.TButton", BLUE_DEEP, body),
        ("TabOpenQueued.TButton", BLUE_DEEP, strong),
    ):
        # No background and no border here. The tab wears a face (``_rounded``
        # below): chrome at rest, a rounded tint under the pointer, white
        # under a blue cap when open. An open tab has one picture and so does
        # not light up under the pointer -- you are already there.
        style.configure(name, foreground=text, padding=tab_pad, anchor="center", font=face)

    #: The word over a group of tabs -- the only text in the strip that is not
    #: the name of a page. It says which of the two kinds the tabs under it
    #: are, which is the whole taxonomy: two pages set the job up, four draw
    #: something.
    style.configure("Group.TLabel", background=CHROME, foreground=HINT, font=small)

    #: The newest line out of a run, and the only one shown. Monospaced
    #: because it prints layer names and tallies that want to line up.
    style.configure("Note.TLabel", background=CHROME, foreground=BODY, font=log_font(), anchor="w")

    #: A tile in a choice row: icon only, no text, and square.
    style.configure(
        "Tile.TButton",
        padding=2,
    )
    #: The chosen tile. Filled blue, and the drawing inside it is the white
    #: one -- the same move the printer driver makes.
    #: The chosen tile. Tinted and edged in blue rather than filled with it:
    #: these tiles keep their drawing, and a white-on-blue sun is not a sun.
    #: The icon-only tiles on the design boards invert; these carry a picture
    #: that has to stay readable, so they take the named-card treatment.
    style.configure(
        "TileOn.TButton",
        padding=2,
    )

    # -- chips: a chosen name, and the button that drops it ----------------
    #
    # What a list of layers looks like now that it is not a comma-joined
    # string in a text box. The cross is a real button with its own focus, so
    # a name can be dropped from the keyboard as well as the pointer.
    style.configure(
        "Chip.TFrame",
        background=BLUE_TINT,
        bordercolor=BLUE_EDGE,
        lightcolor=BLUE_TINT,
        darkcolor=BLUE_TINT,
        relief="solid",
        borderwidth=1,
    )
    style.configure("Chip.TLabel", background=BLUE_TINT, foreground=BLUE_DEEP, padding=(7, 2, 3, 2))
    style.configure(
        "ChipDrop.TButton",
        background=BLUE_TINT,
        foreground=BLUE_DEEP,
        bordercolor=BLUE_TINT,
        lightcolor=BLUE_TINT,
        darkcolor=BLUE_TINT,
        relief="flat",
        padding=(0, 0),
        font=body,
    )
    style.map(
        "ChipDrop.TButton",
        background=[("active", BLUE_EDGE), ("pressed", BLUE_EDGE)],
        foreground=[("active", BLUE_DEEP)],
    )
    #: The button that opens the project's own list. Dashed, because it is an
    #: invitation rather than a value -- the chips beside it are the values.
    style.configure(
        "Add.TButton",
        foreground=BODY,
        padding=(9, 3),
        font=body,
    )
    style.map(
        "Add.TButton",
        foreground=[("active", BLUE_DEEP)],
    )

    # -- the info band -----------------------------------------------------
    style.configure("Info.TFrame", background=CHROME)
    style.configure("Info.TLabel", background=CHROME, foreground=INK)
    style.configure("InfoTitle.TLabel", background=CHROME, foreground=INK, font=strong)
    style.configure("InfoIdle.TLabel", background=CHROME, foreground=HINT, font=strong)
    style.configure("InfoState.TLabel", background=CHROME, foreground=BLUE_DEEP)
    style.configure("InfoHint.TLabel", background=CHROME, foreground=HINT)

    # -- the sheets dock ---------------------------------------------------
    #
    # Its own grey, so the white sheets sit on it the way pages sit in
    # InDesign's panel rather than reading as part of the page beside it.
    style.configure("Dock.TFrame", background=CHROME)
    style.configure("DockTitle.TLabel", background=CHROME, foreground=INK, font=strong)
    style.configure("DockCount.TLabel", background=CHROME, foreground=BLUE_DEEP)
    style.configure("DockHint.TLabel", background=CHROME, foreground=HINT, font=small)
    style.configure("DockStudy.TLabel", background=CHROME, foreground=INK, font=strong)
    style.configure("DockDay.TLabel", background=CHROME, foreground=HINT, font=small)

    #: A study's block on a settings page: its tick, its name, and what it
    #: will make, on a tinted bar with a rule under it. Not a box with a
    #: border, because ttk draws borders square and six of them down a page
    #: reads as six boxes; a bar and a rule group the same rows for less.
    #: A study's tick, which is also the header of its block: the name in the
    #: heading face on a tinted bar across the page. Switched off, the bar
    #: goes grey -- a study nobody has turned on should not look like a live
    #: form with a cleared box somewhere above it.
    style.configure(
        "Study.TCheckbutton",
        background=BLUE_TINT,
        foreground=INK,
        font=heading,
        padding=(7, 6),
    )
    style.map("Study.TCheckbutton", background=[("active", BLUE_TINT)])
    style.configure(
        "StudyOff.TCheckbutton",
        background=HEAD_OFF,
        foreground=BODY,
        font=heading,
        padding=(7, 6),
    )
    style.map("StudyOff.TCheckbutton", background=[("active", HEAD_OFF)])

    #: A study's box: a rounded border with the header's tint drawn into its
    #: top slice (``_rounded``). Off, the border and the header go grey.
    style.configure("Box.TFrame", background=SURFACE)
    style.configure("BoxOff.TFrame", background=SURFACE)
    #: The title of a box that is not a study and so has no tick to head it.
    style.configure("BoxTitle.TLabel", background=HEAD_ON, foreground=INK, font=heading)
    #: What the box will make, at the right of its header.
    style.configure("PanelSays.TLabel", background=HEAD_ON, foreground=BLUE_DEEP)
    style.configure("PanelSaysOff.TLabel", background=HEAD_OFF, foreground=HINT)

    _own_tick(style)

    style.configure(
        "Horizontal.TProgressbar",
        background=BLUE,
        troughcolor=SURFACE,
        bordercolor=LINE,
        lightcolor=BLUE,
        darkcolor=BLUE,
        thickness=10,
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
    style.configure("Dock.Vertical.TScrollbar", troughcolor=CHROME, bordercolor=CHROME)

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
    icons, for the same reason those are: Tk reads PNG by itself, and Pillow
    is a development dependency that never goes in the bundle.

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
    tiles = worn("face_up", "face_hover", "face_run")
    chip = worn("chip")
    tabs = worn("tab_rest", "tab_hover", "tab_open")
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
    if tabs is not None:
        # Rounded where a tab meets nothing and square where it meets its
        # page, so the bottom slice is a single row.
        foot = (FACE_SLICE, FACE_SLICE, FACE_SLICE, 1)
        element("Loriini.tab", tabs[:2], ("active",), foot)
        element("Loriini.tabopen", [tabs[2]], (), foot)

    #: Which faces actually loaded. A style whose face is missing is left on
    #: clam's border rather than left with no layout at all.
    ready = {
        "button": True,
        "run": True,
        "add": adding is not None,
        "tile": tiles is not None,
        "tileon": tiles is not None,
        "tab": tabs is not None,
        "tabopen": tabs is not None,
    }
    for name, worn_as in WEARS.items():
        if worn_as == "flat" or not ready.get(worn_as, False):
            style.layout(name, flat)
        else:
            style.layout(name, [(f"Loriini.{worn_as}", inside(label))])

    if chip is not None:
        element("Loriini.chip", chip, (), FACE_SLICE)
        style.layout("Chip.TFrame", [("Loriini.chip", {"sticky": "nswe"})])

    if panels is not None:
        # The header's tint and the rule under it are in the top slice, so
        # that slice is exactly as tall as the header plus its rule.
        box = (7, PANEL_HEAD + 1, 7, 7)
        element("Loriini.box", [panels[0]], (), box)
        element("Loriini.boxoff", [panels[1]], (), box)
        style.layout("Box.TFrame", [("Loriini.box", {"sticky": "nswe"})])
        style.layout("BoxOff.TFrame", [("Loriini.boxoff", {"sticky": "nswe"})])

    for kind in ("TEntry", "TCombobox"):
        part = kind.split("T", 1)[1]
        # The arrow goes *inside* the field element, not beside it. Clam has
        # it as a sibling, which was fine while the field was a square box
        # drawn to the same height; against a rounded face it reads as a
        # second little button parked next to the field.
        children: list[tuple[str, dict[str, object]]] = []
        if kind == "TCombobox":
            children.append((f"{part}.downarrow", {"side": "right", "sticky": "ns"}))
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
        if tabs is None and name.startswith("TabOpen"):
            # Still painted by its background, which is what makes it white.
            ground = SURFACE
        style.configure(name, background=ground)


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


def log_font() -> tuple[str, int]:
    """What the log is set in."""
    return (MONO, 9) if _has_face(MONO) else ("TkFixedFont", 9)
