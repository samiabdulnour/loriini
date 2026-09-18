"""The four ways the rounded theme goes wrong quietly.

Every one of these bit while the corners were being rounded, and none of them
raised anything: ttk accepts each of these mistakes and the window opens
looking subtly wrong -- or, in the last case, opens twenty-six seconds late.
Which is the definition of a trap, and the reason they are pinned here rather
than remembered.
"""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

from sun_study.app import icons, theme

THEME_SOURCE = Path(theme.__file__).read_text(encoding="utf-8")


@pytest.fixture
def styled() -> object:
    """A dressed interpreter, thrown away afterwards."""
    root = tk.Tk()
    root.withdraw()
    try:
        yield theme.apply(root)
    finally:
        root.destroy()


# -- the first trap: a style inherits its parent's layout -------------------
#
# Change ``TButton`` and every ``*.TButton`` that has not been given a layout
# of its own changes with it. The first version of the rounded theme put a
# button face behind all six tabs that way, silently.


def test_every_button_style_says_what_it_wears(styled: object) -> None:
    """A new ``*.TButton`` that nobody classified would come out rounded.

    So the classification is a declaration, and this is what makes leaving a
    style out of it a failing test rather than a tab that looks like a button.
    """
    defined = set(re.findall(r'style\.configure\(\s*"((?:\w+\.)?TButton)"', THEME_SOURCE))
    defined |= set(re.findall(r'\(\s*"((?:\w+\.)?TButton)",\s*\w+,', THEME_SOURCE))

    assert defined, "no button styles found -- has this module been renamed?"
    unclassified = sorted(defined - set(theme.WEARS))
    assert not unclassified, (
        f"these button styles are not in theme.WEARS, so they inherit whatever "
        f"TButton wears: {unclassified}"
    )


def test_what_each_style_says_it_wears_is_what_it_wears(styled: object) -> None:
    """The declaration and the interpreter agree.

    A layout swap that silently did not happen leaves a square control that
    nobody notices until it is beside a round one.
    """
    wrong: list[str] = []
    for name, worn in theme.WEARS.items():
        root = styled.layout(name)[0][0]  # type: ignore[attr-defined]
        want = "Button.border" if worn == "flat" else f"Loriini.{worn}"
        if root != want:
            wrong.append(f"{name} says {worn!r} and wears {root!r}")
    assert not wrong, wrong


def test_a_tab_wears_a_tab_and_never_a_button(styled: object) -> None:
    """Named on its own, because this is the one that actually happened.

    The first rounded build changed ``TButton`` and the six tabs, being
    ``*.TButton``, came out as six rounded buttons. A tab has a face of its
    own now -- chrome at rest, white under a blue cap when open -- and what it
    must never do again is inherit the button's.
    """
    for name in ("Tab.TButton", "TabOpen.TButton", "TabQueued.TButton", "TabOpenQueued.TButton"):
        assert theme.WEARS[name] in {"tab", "tabopen"}
        assert styled.layout(name)[0][0] != "Loriini.button"  # type: ignore[attr-defined]
    # Open and queued are two marks on two axes. The cap is the open mark, so
    # it goes with open-ness and not with being queued.
    assert theme.WEARS["TabOpen.TButton"] == theme.WEARS["TabOpenQueued.TButton"] == "tabopen"
    assert theme.WEARS["Tab.TButton"] == theme.WEARS["TabQueued.TButton"] == "tab"


# -- the second trap: an image element ignores ``background`` ---------------
#
# Anything wearing a face has to say what state it is in with a different
# picture. A style that kept using ``background`` for that lost the state and
# said nothing about it.


def test_a_chosen_tile_is_a_different_picture_and_not_a_colour(styled: object) -> None:
    """The tiles used to say "chosen" with a blue background, which the image
    element threw away. Two faces, or the choice is invisible."""
    assert theme.WEARS["Tile.TButton"] != theme.WEARS["TileOn.TButton"], (
        "the chosen tile and the unchosen one wear the same face, so nothing "
        "on screen says which is chosen"
    )


def test_nothing_wearing_a_face_still_leans_on_its_background(styled: object) -> None:
    """Every style that wears a face must say its states in *faces*.

    ``style.map(..., background=...)`` on one of these is dead code that reads
    like a working hover: ttk accepts it, stores it, hands it back when asked,
    and draws the picture anyway. Four styles were still carrying one when
    this test was written, which is exactly why it exists.

    Compared against stock clam rather than against nothing, because clam sets
    a background map on ``TButton`` itself. That one is not ours and cannot be
    removed; what matters is that this module has not added any.
    """
    stock = tk.Tk()
    stock.withdraw()
    try:
        bare = ttk.Style(stock)
        bare.theme_use("clam")
        leaning = []
        for name, worn in theme.WEARS.items():
            if worn == "flat":
                continue
            ours = styled.map(name, "background")  # type: ignore[attr-defined]
            if ours and ours != bare.map(name, "background"):
                leaning.append(name)
    finally:
        stock.destroy()

    assert not leaning, (
        f"these wear an image and map a background for a state the picture "
        f"already carries: {leaning}"
    )


def test_the_combobox_arrow_is_inside_the_field(styled: object) -> None:
    """Clam has the arrow as a sibling of the field, which was fine while the
    field was a square box drawn to the same height. Against a rounded face it
    reads as a second little button parked beside it."""
    layout = styled.layout("TCombobox")  # type: ignore[attr-defined]

    assert len(layout) == 1, f"the arrow is still beside the field: {[n for n, _ in layout]}"
    root, spec = layout[0]
    assert root == "Loriini.field"
    inside = [name for name, _ in spec["children"]]
    assert "Combobox.downarrow" in inside, inside


# -- the third trap: the corners take the style's colour, not the parent's ---
#
# The walk over the real window is in ``test_app`` because it needs one. What
# can be said without a window is that the declaration is complete, and that
# nothing configured after it has undone it.


def test_everything_that_wears_a_face_says_what_it_stands_on(styled: object) -> None:
    """A face is a rounded shape in a square widget, and what shows through
    its corners is the *style's* background. So every faced style declares the
    ground it stands on, and the interpreter has to agree -- which it did not
    for the progress bar, whose old ``background=BLUE`` was configured after
    the rounding ran and showed through the pill as a blue outline."""
    faced = {name for name, worn in theme.WEARS.items() if worn != "flat"}
    undeclared = sorted(faced - set(theme.STANDS_ON))
    assert not undeclared, f"faced, with no ground declared: {undeclared}"

    wrong = [
        f"{name}: declared {ground}, is {styled.lookup(name, 'background')}"  # type: ignore[attr-defined]
        for name, ground in theme.STANDS_ON.items()
        if str(styled.lookup(name, "background")).upper() != ground.upper()  # type: ignore[attr-defined]
    ]
    assert not wrong, wrong


def test_a_box_header_is_the_height_and_the_tint_its_face_was_drawn_for(
    styled: object,
) -> None:
    """The header's tint and the rule under it are *in* the box's picture, so
    the window has to place the header at exactly the height the picture was
    drawn for, in exactly its colour -- or the tick shows as a patch on its
    own header. Two files hold those numbers; this holds them together."""
    for name, tint in (("panel_on", theme.HEAD_ON), ("panel_off", theme.HEAD_OFF)):
        face = icons.face(name)
        assert face is not None, name
        red, green, blue = face.get(face.width() // 2, theme.PANEL_HEAD // 2)
        assert f"#{red:02X}{green:02X}{blue:02X}" == tint.upper(), name
        below = face.get(face.width() // 2, theme.PANEL_HEAD + 6)
        assert below == (255, 255, 255), (
            f"{name}: the body starts under a {theme.PANEL_HEAD} px head"
        )


# -- the fourth trap: the middle of a nine-slice is tiled, not stretched ----


def test_no_face_is_drawn_small_enough_to_be_stamped_a_thousand_times() -> None:
    """Tk stamps the centre of a nine-slice across the widget as many times as
    it takes. Drawn at 16 px a face has a 6 px middle: one 700 px field was
    six hundred blits, a settings box thirteen thousand, and the window's
    first ``update_idletasks`` took twenty-six seconds.

    Nothing about that shows in a picture of the face, and a tidy-minded
    redraw at "a sensible size" would bring it straight back. So: every face
    is at least a hundred pixels along any side it is tiled along.
    """
    folder = icons.folder()
    root = tk.Tk()
    root.withdraw()
    try:
        small = []
        for path in sorted(folder.glob("*.png")):
            if re.search(r"-\d+\.png$", path.name):
                continue  # a drawing, which has a size in its name and is never tiled
            # Through the loader and not ``tk.PhotoImage``, which can refuse the
            # first picture in an interpreter for no reason at all -- see
            # ``icons._read`` -- and now and then did, here.
            face = icons.face(path.stem)
            assert face is not None, path.name
            wide, tall = face.width(), face.height()
            # A scrollbar thumb is as wide as its gutter and a bar is as tall
            # as itself: neither is ever tiled along that side.
            tiled_across = not path.stem.startswith("thumb")
            tiled_down = not path.stem.startswith("bar_")
            if (tiled_across and wide < 96) or (tiled_down and tall < 24):
                small.append(f"{path.name} is {wide}x{tall}")
    finally:
        root.destroy()
    assert not small, small


def test_a_big_face_does_not_make_a_big_widget(styled: object) -> None:
    """The other half of the fourth trap. Left to itself an image element asks
    for the whole picture as its minimum size -- and the pictures are drawn
    big on purpose. The first build with big faces had every button wanting
    192 px, "+ Add" as wide as a field, and the last tab pushed off the strip.

    And the two things that are never stretched one way must keep that side:
    a border of nought there made the progress bar one pixel high and the
    scrollbars invisible, which is a window with no way to scroll it.
    """
    root = styled.master  # type: ignore[attr-defined]
    # ``width=2``: clam gives every button a floor of eleven characters of its
    # own, which is 102 px and is not what is being measured here.
    small = ttk.Button(root, text="x", width=2)
    tab = ttk.Button(root, text="x", style="Tab.TButton", width=2)
    field = ttk.Entry(root, width=4)
    bar = ttk.Progressbar(root)
    scroll = ttk.Scrollbar(root, orient="vertical")
    root.update_idletasks()

    assert small.winfo_reqwidth() < 80, small.winfo_reqwidth()
    assert small.winfo_reqheight() < 40, small.winfo_reqheight()
    assert tab.winfo_reqwidth() < 80, tab.winfo_reqwidth()
    assert field.winfo_reqwidth() < 80, field.winfo_reqwidth()
    assert bar.winfo_reqheight() == 10, "the pill is exactly as tall as its picture"
    assert scroll.winfo_reqwidth() == 12, "and the thumb exactly as wide as its gutter"


# -- and the guard that keeps the whole thing optional ----------------------


def test_a_missing_face_leaves_a_working_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Square corners are worth a great deal less than a window that opens.

    The faces are PNGs on disk, so a build that shipped without them, or a Tk
    that will not read one, must fall back rather than raise -- and fall back
    to something usable: clam's own progress bar is drawn *in* its background
    colour, so a fallback that had already greyed that would be a bar nobody
    can see filling.
    """
    monkeypatch.setattr(icons, "face", lambda name: None)
    monkeypatch.setattr(icons, "named", lambda name, size=20: None)
    root = tk.Tk()
    root.withdraw()
    try:
        style = theme.apply(root)
        for name in theme.WEARS:
            assert style.layout(name), f"{name} was left with no layout at all"
        assert str(style.lookup("Horizontal.TProgressbar", "background")).upper() == theme.BLUE
    finally:
        root.destroy()


# -- and one trap that is not ttk's: a picture that will not load, once ------
#
# ``tk.PhotoImage(file=...)`` can fail with an empty ``TclError`` on a file
# with nothing wrong with it, while the standard file descriptors are
# redirected -- which is how pytest runs unless told otherwise. Every caller
# of the loader takes ``None`` to mean "no icon", so what it cost was one run
# of this file in twenty-five failing on a square combobox, and nothing
# anywhere to say why. ``icons._read`` has the measurements.
#
# Neither of these makes a real image: the fault being described is in making
# one, and a test about it that could itself be refused is the same flake
# moved one line down. Which it was, once in eighty runs, before this was so.


def test_a_picture_refused_without_a_reason_is_asked_for_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same call works a moment later, so it is made a moment later."""
    picture = object()
    asked: list[str] = []

    def moody(*, file: str) -> object:
        asked.append(file)
        if len(asked) == 1:
            raise tk.TclError("")
        return picture

    monkeypatch.setattr(icons, "_loaded", {})
    monkeypatch.setattr(tk, "PhotoImage", moody)

    assert icons.face("face_up") is picture
    assert len(asked) == 2


def test_a_picture_is_not_asked_for_for_ever(monkeypatch: pytest.MonkeyPatch) -> None:
    """A window with square corners is still worth more than one that never
    opens because a loop is waiting for Tk to change its mind."""
    asked: list[str] = []

    def never(*, file: str) -> object:
        asked.append(file)
        raise tk.TclError("")

    monkeypatch.setattr(icons, "_loaded", {})
    monkeypatch.setattr(tk, "PhotoImage", never)

    assert icons.face("face_up") is None
    assert len(asked) == icons.ASKS


def test_a_picture_refused_with_a_reason_is_not_asked_for_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing file says so, and asking again changes nothing. ``None`` is
    the ordinary answer for "no icon" and ought to stay a cheap one."""
    asked: list[str] = []

    def absent(*, file: str) -> object:
        asked.append(file)
        raise tk.TclError(f'could not open "{file}": no such file or directory')

    monkeypatch.setattr(icons, "_loaded", {})
    monkeypatch.setattr(tk, "PhotoImage", absent)

    assert icons.face("face_up") is None
    assert icons.named("sun", 20) is None
    assert len(asked) == 2, "asked once each, and not twice"
