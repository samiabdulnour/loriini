"""The window's icons: a small picture beside every label.

Why the window has icons at all
-------------------------------

The window asks about sixty things across seven tabs, and the printer driver
it borrows from is the one settings dialog nobody enjoys and everybody
finishes. It works because each control carries a small picture of the thing
it changes -- a tray, a stapled corner, a folded sheet -- so the eye finds the
row before it reads the label. Four fields here begin with the word
"Communal" and are otherwise unrelated; a zone, a threshold, a height and a
grid tell them apart at a glance in a way the second word never will.

How a row gets its icon
-----------------------

By its own label, looked up in ``BY_LABEL`` below. The field helpers in
``window`` pass the label they were already given, so adding an icon to a
field is one line here and nothing at the call site -- and a field that moves
from one tab to another keeps its picture, because the picture belongs to the
thing and not to the tab.

A label with no entry gets no icon and reads exactly as it did before. That is
the intended behaviour for the rows where a drawing would be a lie: a layer
name is free text out of the project and there is nothing to draw.

Nothing here ever raises
------------------------

An icon is decoration. A missing PNG, a settings folder on a locked profile, a
Tk build that will not read the file -- none of those are worth refusing to
open the window for, so every failure answers ``None`` and the label renders
bare. This mirrors ``preferences``, where a settings file hand-edited into
nonsense costs one setting rather than the whole window.

The PNGs are drawn by ``scripts/make_icons.py`` and committed: Tk reads PNG
by itself, so the window needs only the finished files and never draws one.
Pillow is in the bundle since D121, for the reference image; nothing here
uses it.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from typing import Any

#: The size asked for when a caller does not say. Tab strips and row labels
#: both sit at 20: big enough that the sheet reads, small enough that a tab
#: does not grow to accommodate it.
DEFAULT_SIZE = 20

#: Sizes ``make_icons.py`` writes. Asking for anything else answers ``None``
#: rather than scaling a bitmap, which at these sizes looks broken. 40 is the
#: launcher card; 20 a row label; 16 a button.
SIZES = (16, 20, 24, 32, 40, 48)

#: Loaded images, by name and size.
#:
#: Tk does not own the images it is handed: a ``PhotoImage`` that Python
#: garbage-collects is a widget that silently loses its picture, which is the
#: oldest bug in Tkinter. Holding them here for the life of the process is
#: both the fix and the cache.
#:
#: An image belongs to the Tk interpreter that made it, and this cache outlives
#: any one of them, so an entry can go stale -- a second root, or a window
#: rebuilt after the first was destroyed, and the image is a name Tk no longer
#: knows. ``named`` checks an entry before handing it back rather than trusting
#: the dictionary, because the failure is a ``TclError`` at the moment a widget
#: is constructed, which is nowhere near where it would be understood.
_loaded: dict[tuple[str, int], tk.PhotoImage] = {}


def folder() -> Path:
    """Where the PNGs are.

    Two places, because the app runs two ways. Frozen, PyInstaller unpacks the
    data it was given into a temporary folder and names it on ``sys._MEIPASS``;
    from a checkout, the files sit in ``assets/icons`` at the top of the
    repository, four levels up from this module.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled is not None:
        return Path(bundled) / "assets" / "icons"
    return Path(__file__).resolve().parents[3] / "assets" / "icons"


#: How many times a picture is asked for when Tk refuses it without a reason.
#: Twice has always been enough -- see ``_read`` -- and the third is there
#: because being wrong about that is a test that fails one run in a thousand,
#: which is the most expensive kind there is.
ASKS = 3


def _read(path: Path) -> tk.PhotoImage | None:
    """One PNG off disk, or ``None`` if it cannot be had.

    Asked again when Tk refuses *without saying why*. A file that is missing
    or will not parse fails with a sentence, and asking again would change
    nothing. But ``image create photo -file`` can also fail with an empty
    message and an ``errorCode`` of ``NONE`` on a file there is nothing wrong
    with, and the same call a moment later works.

    What was measured, on Tk 9.0.4 and Windows, 18 September 2026. Under
    pytest with the standard file descriptors redirected -- ``--capture=fd``,
    which is its default and what CI runs -- about one run of
    ``test_theme.py`` in two loses an image this way: usually the first one
    made after a ``Tk()``, sometimes the third, now and then the twentieth.
    With ``--capture=sys`` or ``-s``, none in forty runs. In a plain script,
    none in twelve thousand loads over a thousand interpreters, so the window
    itself has never been seen to do it. The collector and the fault handler
    make no difference. Asked again it loaded 223 times out of 223. *Why* is
    not established: it has the look of Tcl's file channels meeting standard
    handles that were re-pointed behind its back, and that is a guess.

    It is caught here because this is where it turns silent. Every caller
    takes ``None`` to mean "no icon" and carries on: a lost ``tick_off`` is a
    window whose ticks are crosses, a lost ``face_up`` is a window with square
    corners, and what it cost was a theme test failing one run in twenty-five
    with nothing anywhere to say why.
    """
    for _ in range(ASKS):
        try:
            return tk.PhotoImage(file=str(path))
        except tk.TclError as error:
            if str(error):
                return None
        except (RuntimeError, OSError):
            # RuntimeError is a PhotoImage built before there is a Tk root to
            # own it, which is a programming error here but not one worth a
            # blank window.
            return None
    return None


def named(name: str, size: int = DEFAULT_SIZE) -> tk.PhotoImage | None:
    """One icon by its own name, or ``None`` if it cannot be had.

    ``None`` is a normal answer and every caller treats it as "no icon".
    """
    if size not in SIZES:
        return None

    key = (name, size)
    cached = _loaded.get(key)
    if cached is not None:
        try:
            # Touches the interpreter that owns it. A live image answers its
            # width; one whose root has gone raises, and is dropped and redrawn
            # against the root that is asking now.
            cached.width()
        except tk.TclError:
            del _loaded[key]
        else:
            return cached

    image = _read(folder() / f"{name}-{size}.png")
    if image is not None:
        _loaded[key] = image
    return image


def face(name: str) -> tk.PhotoImage | None:
    """One of the faces ttk wears, or ``None`` if it cannot be had.

    Not an icon: a nine-slice picture of a button, a field, a tab or a panel,
    which ``theme`` hands to ``style.element_create`` so that Tk stretches the
    middle and leaves the rounded corners alone. A face has one size -- the
    stretching is the point -- so there is none in its file name, which is
    also how the two kinds are told apart in the folder.

    Cached and checked exactly as ``named`` does it, for exactly the same
    reason: an image belongs to the interpreter that made it.
    """
    key = (name, 0)
    cached = _loaded.get(key)
    if cached is not None:
        try:
            cached.width()
        except tk.TclError:
            del _loaded[key]
        else:
            return cached
    image = _read(folder() / f"{name}.png")
    if image is not None:
        _loaded[key] = image
    return image


def for_label(label: str, size: int = DEFAULT_SIZE) -> tk.PhotoImage | None:
    """The icon for a field, looked up by the label it already carries."""
    name = BY_LABEL.get(label)
    return named(name, size) if name else None


def options(label: str, size: int = DEFAULT_SIZE) -> dict[str, Any]:
    """Widget options that put this label's icon to the left of its text.

    Returned as a mapping to be splatted into the widget, so a label with no
    icon is constructed exactly as it was before rather than with an
    ``image=""`` that Tk has to be told to ignore.
    """
    image = for_label(label, size)
    if image is None:
        return {}
    return {"image": image, "compound": "left", "padding": (0, 0, 6, 0)}


def section_options(title: str, size: int = DEFAULT_SIZE) -> dict[str, Any]:
    """The same, for a section named in a line of text.

    Keyed on the section's title rather than on its position, so inserting a
    section cannot shift every icon along by one.
    """
    name = BY_SECTION.get(title)
    if name is None:
        return {}
    image = named(name, size)
    return {} if image is None else {"image": image, "compound": "left"}


def tab_options(title: str, size: int = 32) -> dict[str, Any]:
    """The same, for a tab in the strip, where the drawing sits *above* the
    name rather than beside it.

    Beside the name, an icon can only be as tall as one line of text -- which
    is how the 20 px tab strip got drawings nobody could read, six pictures
    reduced to six smudges. Above it, the tab is as wide as its name either
    way and the drawing gets the width to itself, so 32 px costs nothing but
    the height of one row.
    """
    name = BY_SECTION.get(title)
    if name is None:
        return {}
    image = named(name, size)
    return {} if image is None else {"image": image, "compound": "top"}


def button_options(name: str, size: int = 16) -> dict[str, Any]:
    """The same, for a button, which wants the smaller drawing.

    Run and Stop are the two icons in the set that are not pictures of
    anything -- a play triangle and a red square. They are verbs, and dressing
    a verb up as a drawing would claim it was a thing.
    """
    image = named(name, size)
    return {} if image is None else {"image": image, "compound": "left"}


def state_options(name: str, size: int = 16) -> dict[str, Any]:
    """Options for a label whose picture changes with what it is saying.

    The project line at the top of the window says one of five things -- no
    Archicad, reading, Tapir missing, unreadable, or the project's own tally --
    and the plug in front of it is seated or struck out to match.

    Both keys are always named, including when there is no icon: ``config``
    leaves alone what it is not given, so a label that had a plug and should
    not any more has to be told to drop it.
    """
    image = named(name, size) if name else None
    if image is None:
        return {"image": "", "compound": "none"}
    return {"image": image, "compound": "left"}


def study_options(label: str, size: int = DEFAULT_SIZE) -> dict[str, Any]:
    """The same, for a study's own tick.

    A ``ttk.Checkbutton`` draws its indicator to the left of everything, so
    the icon lands between the box and the words -- which is where the printer
    driver puts it too.
    """
    name = BY_STUDY.get(label)
    if name is None:
        return {}
    image = named(name, size)
    return {} if image is None else {"image": image, "compound": "left"}


#: The sections, in tab order. Keyed on the titles ``window`` defines, so a
#: renamed tab is a failed lookup and a bare tab rather than a wrong picture.
#:
#: "Solar tools" is gone from here because it is gone from the window: it was
#: a container and never a page, and a drawing of one is a picture of a menu.
BY_SECTION: dict[str, str] = {
    "General": "general",
    "Model": "model",
    "Site analysis": "site",
    "Solar analysis": "analysis",
    "Shadow diagram": "shadow",
    "Sun views": "views",
    "Yield": "yield",
}

#: The six studies, by the label on their own tick.
BY_STUDY: dict[str, str] = {
    "Facade (massing stage)": "facade",
    "Apartments": "apartments",
    "Communal open space": "communal",
    "Shadow diagram": "shadow",
    "Sun views": "views",
    "Site analysis": "site",
    "Area and yield": "yield",
}

#: Every field that has a picture worth drawing, by its own label.
#:
#: Shared entries are deliberate. The four prefixes are one question asked
#: four times and differ only in which study they file, so they wear one tag;
#: giving each a colour would cost the palette its meaning, where blue is the
#: interface and ochre is the sun and nothing else is either. The subsets are
#: the same folder four times over for the same reason.
BY_LABEL: dict[str, str] = {
    # General -- the project's own setup
    "Master layout": "general",
    "Title block width (mm)": "title_block_width",
    "Sheets": "sheets",
    "Layer prefix — solar analysis": "prefix",
    "Layer prefix — shadow diagram": "prefix",
    "Layer prefix — sun views": "prefix",
    "Layer prefix — site analysis": "prefix",
    "Layer group — context model": "group",
    "Archicad wait (min)": "wait",
    "Tables": "table",
    "Measure from storey": "storey_datum",
    "...to storey": "storey_datum",
    "Custom day": "custom_day",
    "Year": "year",
    # Model -- what leaves Archicad
    "Layer combination": "combination",
    "Plan combination": "combination",
    "Layers forced visible": "also_export",
    "Neighbouring buildings": "neighbours",
    "Layers hidden on sheets": "keep_off",
    # Solar analysis -- facade, apartments, communal
    "Facade layers": "facade_layers",
    "Skin cell": "skin_cell",
    "Apartment zones": "zones",
    "Balcony zones": "balcony",
    "Living-room glazing": "glazing",
    "Plan times": "plan_times",
    "Subset — time-of-day sheets": "subset",
    "Subset — ADG sheets": "subset",
    "Communal zones": "communal",
    "Communal window": "communal_window",
    "Communal threshold": "threshold",
    "Communal height": "height",
    "Communal grid": "grid",
    # Shadow diagram
    "Existing": "always_there",
    "Future": "always_there",
    "Existing on site": "always_there",
    "TOD": "being_tested",
    "SEARs": "being_tested",
    "ADG envelope": "being_tested",
    "Proposed": "being_tested",
    "Ground it lands on": "ground_plane",
    "Ignore ground below": "ground_cut",
    "Hours": "plan_times",
    "Draw on storey": "storey_draw",
    "Subset — shadow sheets": "subset",
    # Sun views
    "Pen set": "pen_set",
    "Graphic override": "override",
    "Layers, from": "layers_from",
    "Scale": "scale",
    # Site tools
    "Address": "address",
    # The two rows of site outputs: the drawings, and what goes into the
    # project itself.
    "Project": "model",
    "Context scale": "scale",
    "Site lands at": "site",
    "Model radius (m)": "radius",
    "Future reach (m)": "radius",
    "Run folder": "run_folder",
}

#: The site page's six outputs, by the short word on each button. They were
#: six ticks with a sentence each, keyed above by the sentence; the buttons
#: say one or two words and keep the drawing the sentence had.
BY_OUTPUT: dict[str, str] = {
    "Context": "site_analysis",
    "Site": "site_analysis",
    "Controls": "subset",
    "Future context": "being_tested",
    "3D context": "model",
    "Location": "address",
}
