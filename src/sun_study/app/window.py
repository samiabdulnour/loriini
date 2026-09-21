"""The window itself.

Shaped by one rule: a colleague should have to decide only what is genuinely a
decision. Everything that is a property of the *project* -- which layer carries
the apartments, which masters exist, which Layout Book subsets the practice
files this kind of drawing under -- is read from the open Archicad and offered
as a list, because the project already knows and a person mistyping it is the
commonest way a run measures the wrong thing.

Grouped by what comes out of it
-------------------------------
Six tabs in two kinds. Two of them set the job up -- what the sheets are drawn
on, and what geometry leaves Archicad -- and four of them each draw one thing:
the site analysis, the solar analysis, the shadow diagram, the sun views. That
is how the work is asked for: a job wants the shadow diagrams for Tuesday, and
the person setting one up should be able to read the whole of that study and
none of the rest.

The two kinds are drawn as two groups in the strip, because that split is the
only thing that makes six tabs a list rather than a bag: only the four can be
ticked, and so only the four can ever carry the queued mark.

It replaces a single column of thirty settings with an Advanced panel under
them, which was the wrong cut. "Advanced" is not a property of a setting: the
facade layers are not harder than the year, they are simply the facade
study's, and a section that hides half of its own inputs somewhere else is not
a section. What is genuinely shared -- the year, the title block, the layer
state the export starts from, the numbering the results file themselves under
-- is what General now is, and it is shared rather than advanced.

The cost of tabs is that a section nobody opens is a section nobody knows the
state of, and this window's whole subject is the wrong answer nobody noticed.
So it is paid for twice, in ``Window._sync``: a tab whose study will run says
so on its own label -- in blue, with a dot, which is a different mark from the
white-and-blue-rule that means the tab you are on -- and a line above Run names
every study queued whichever tab happens to be showing.

Every field says what it is
---------------------------
A line under each control, and a longer one on hover. Not decoration: most of
these settings fail *quietly*. A facade study with the slab layers missing does
not report an error, it reports the least-lit half of the building; an export
without the zone layers runs for minutes and then cannot place the skin. The
hint says what the setting is; the tooltip says what happens when it is wrong,
because that is the part nobody can infer from a label.

Which makes sections no screen can hold either
----------------------------------------------
Sections shorten the page but do not fix it: Solar analysis alone is three
studies and a dozen questions, each answered with a line of its own, which is
more than a laptop shows -- and a window cannot be dragged taller than the
screen it is on, so anything past the bottom edge is not awkward to reach but
unreachable. So every tab is its own ``Scroller``. Run, the progress bar and
the one line a run has to say about itself sit below the strip and outside it,
so the button stays findable and the line stays put whichever tab is showing.

What is worth remembering between runs
--------------------------------------
Half of these fields are a property of the *project* and are read out of
Archicad every time. The rest are a property of the *practice* -- the layer
prefix that files the output inside the office's own numbering, the
living-room suffix, the wait a big export needs, which studies this person ever
runs, which section they work in -- and those are saved, on request, by
``preferences``. The project always wins afterwards: the lists are refilled
from the open Archicad, so a saved name it does not have is replaced by one it
does.
"""

from __future__ import annotations

import datetime as dt
import math
import queue
import sys
import tkinter as tk
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from itertools import pairwise
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter import font as tkfont
from typing import ClassVar, Literal

from sun_study import PRODUCT
from sun_study.app import icons, preferences, probe, theme
from sun_study.app.runner import Run
from sun_study.archicad import naming
from sun_study.archicad.connection import DEFAULT_TIMEOUT_SECONDS
from sun_study.archicad.sheeting import cells_for, parse_sheet_mode, sheet_chunks, sheet_title
from sun_study.cli import DEFAULT_SHADOW_DATES, DEFAULT_SHADOW_HOURS
from sun_study.core.solar import UnknownTimezoneError, resolve_timezone, solar_position
from sun_study.licence import credential
from sun_study.rules.days import ASSESSMENT_DAYS, day_name, parse_day

PAD = theme.PAD
#: Kept as a name because a dozen widgets still pass it directly. The value
#: is the theme's, so the window and the styles cannot disagree about it.
HINT = theme.HINT

#: How the add-on's palette says which study its button stood for. Read out of
#: the command line by ``app.__main__`` and handed to ``Window.ask_for``.
#:
#: A command-line argument rather than an environment variable, because the
#: add-on would have to set that variable on Archicad's own process -- and it
#: would then be inherited by every other program Archicad started for the
#: rest of the session.
STUDY_FLAG = "--study"

#: The timezone every study runs in. Named once here rather than five
#: times down in ``jobs``, because the sheets panel has to work out the
#: sun for the same instants the run will use, and two spellings of
#: "Australia/Sydney" is two answers to what noon means.
TIMEZONE = "Australia/Sydney"

#: Short month names, for the date on a sheet.
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: Layer name fragments that mark the envelope a facade study measures. A
#: guess, offered rather than applied: the picker is filled with them and the
#: list stays editable, because the next project names its slabs differently.
SKIN_WORDS = ("Wall.External", "Floor.", "Balustrade", "Screens")

#: What each study is called, in the one place all three callers read it
#: from: the line above Run that says what is queued, the ``──`` rule the log
#: prints when that study starts, and the tab that marks itself. A study
#: named one thing before it runs and another while it runs is a study
#: somebody cannot follow.
FACADE_JOB = "solar analysis: facade"
PLANS_JOB = "solar analysis: apartments"
#: The two communal sheets the panel has to tell apart from the banded plan:
#: the hourly set, which the Sheets row deals, and the schedule, which is a
#: table and not a drawing at all.
COMMUNAL_HOURLY = "Communal open space by hour"
COMMUNAL_AREAS = "Communal areas"
#: The two outputs of the site study that are not sheets: geometry on its
#: own layers, drawn in the panel as geometry.
CONTEXT_MODEL = "Context model"
FUTURE_MODEL = "Future model"
#: And the facade study's output, which is the model coloured in bands of
#: sun hours -- a skin of 3D elements, not a sheet.
FACADE_MODEL = "Facade model"
COMMUNAL_JOB = "solar analysis: communal open space"
SHADOW_JOB = "shadow diagram"
SUN_EYE_JOB = "sun views"
SITE_JOB = "site tools"

#: What a queued study is called on a chip in the run bar and in the summary,
#: and which icon it wears. Keyed on the job name so the chips, the tab ticks
#: and the log all read from the same list -- a study called one thing on a
#: chip and another in the log is a study somebody cannot follow.
CHIPS: dict[str, tuple[str, str]] = {
    FACADE_JOB: ("Facade", "facade"),
    PLANS_JOB: ("Apartments", "apartments"),
    COMMUNAL_JOB: ("Communal", "communal"),
    SHADOW_JOB: ("Shadow diagram", "shadow"),
    SUN_EYE_JOB: ("Sun views", "views"),
    SITE_JOB: ("Site analysis", "site_analysis"),
}


class Tooltip:
    """The longer explanation -- in the band at the foot of the window.

    It used to be a ``Toplevel`` that opened over the window 450 ms after the
    pointer stopped. Three things were wrong with that, and none of them was
    the delay. It covered the thing you were pointing at. It went away while
    you were still reading it. And it could not be reached from the keyboard
    at all, so tabbing through this window explained nothing -- which for a
    window whose settings fail *quietly* is not a polish complaint.

    So the sentence goes to ``InfoBand`` instead, one strip that is always
    there and always says something. The class keeps its name and its two
    positional arguments because five dozen call sites use them, and the
    binding it makes is still ``<Enter>``, which is what the test that
    insists every control explains itself looks for.

    The title is the widget's own text where it has one -- a button, a tick, a
    label -- because that is already the name of the thing. The helpers that
    build a labelled row pass it outright, since an Entry has no text of its
    own to take it from.
    """

    #: Where the sentences go. Set once, by the window that owns the band.
    band: ClassVar[InfoBand | None] = None

    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        delay_ms: int = 450,
        *,
        title: str = "",
        short: str | Callable[[], str] = "",
        glyph: str = "",
        state: Callable[[], str] | None = None,
    ) -> None:
        self.widget = widget
        self.text = text
        #: Kept so the signature is the one the call sites were written
        #: against. Nothing waits any more: the band is already on screen, so
        #: there is no flash to stagger and nothing to be patient about.
        self.delay_ms = delay_ms
        self.title = title
        self.short = short
        self.glyph = glyph
        self.state = state
        self.visible = False
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<FocusIn>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")

    def _named(self) -> str:
        if self.title:
            return self.title
        try:
            return str(self.widget.cget("text")) or "—"
        except tk.TclError:
            return "—"

    def _show(self, _event: object = None) -> None:
        self.visible = True
        if Tooltip.band is None:
            return
        name = self._named()
        drawing = self.glyph or icons.BY_LABEL.get(name) or icons.BY_STUDY.get(name) or ""
        said = self.short() if callable(self.short) else self.short
        Tooltip.band.show(
            drawing,
            name,
            said,
            self.text,
            state="" if self.state is None else self.state(),
        )

    def _hide(self, _event: object = None) -> None:
        self.visible = False
        if Tooltip.band is not None:
            Tooltip.band.rest()


class Scroller(ttk.Frame):
    """A pane whose contents may be taller than the screen.

    The window asks about thirty questions and answers each one with a line of
    its own underneath, which is deliberate -- most of these settings fail
    silently and that line is what stops it -- and which makes a form no
    laptop can show at once. Without somewhere to scroll, the settings below
    the fold are not merely awkward to reach, they are unreachable: Tk clips
    them, and a window cannot be dragged taller than the screen it is on.

    A canvas, because Tk has no scrolling frame. The frame goes inside it as a
    single canvas item, kept as wide as the canvas so the fields still
    stretch, and the item's own size is the scroll region -- so adding a row,
    or opening Advanced, re-measures without anything having to be told.
    """

    def __init__(self, parent: tk.Misc, *, ground: str = theme.SURFACE) -> None:
        """``ground`` is what the pane stands on: the white page, or the grey of
        the sheets panel. It is asked for because three things have to agree
        about it -- the canvas, the frame inside it and the gutter the
        scrollbar runs in -- and a white gutter down a grey panel is what
        forgetting one of them looks like."""
        on_chrome = ground == theme.CHROME
        frame_style = {theme.CHROME: "Dock.TFrame", theme.PAGE: "Page.TFrame"}.get(ground, "TFrame")
        super().__init__(parent, style=frame_style)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=ground)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.bar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style="Dock.Vertical.TScrollbar" if on_chrome else "Vertical.TScrollbar",
        )
        self.bar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.content = ttk.Frame(self.canvas, style=frame_style)
        self._item = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._measured)
        self.canvas.bind("<Configure>", self._widened)

    def _measured(self, _event: object = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._show_bar_if_needed()

    def _widened(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.itemconfigure(self._item, width=event.width)
        self._show_bar_if_needed()

    def _show_bar_if_needed(self) -> None:
        """A bar only when there is something below the fold. A trough that
        moves nothing is a line down the page for no reason."""
        needed = self.content.winfo_reqheight() > self.canvas.winfo_height() > 1
        if needed:
            self.bar.grid()
        else:
            self.bar.grid_remove()

    @property
    def scrollable(self) -> bool:
        """Whether anything is out of sight."""
        first, last = self.canvas.yview()
        return first > 0.0 or last < 1.0

    def spin(self, delta: int) -> None:
        """One turn of the wheel. Ignored when everything already fits.

        The guard is not politeness: a canvas will happily scroll past its own
        scroll region, so a wheel over a form that fits slides the whole form
        off the top of the window and leaves an empty pane behind.

        A mouse sends 120 to the notch and a precision touchpad sends whatever
        the finger did, which is often less. The direction is taken from the
        sign and the distance from the size, so a small gesture is worth one
        line either way -- dividing first would round a gentle push down to
        nothing while a gentle pull up still moved, and a page that scrolls
        one way is worse than one that does not scroll at all.
        """
        if delta == 0 or not self.scrollable:
            return
        lines = max(1, abs(delta) // 120)
        self.canvas.yview_scroll(-lines if delta > 0 else lines, "units")


def wheel_reaches_the_pointer(root: tk.Misc) -> None:
    """Give the wheel to whatever is under the mouse, and to nothing else.

    Two Tk defaults are wrong for a form this tall, and both are undone here
    rather than in six places.

    On Windows the wheel is delivered to the widget with keyboard *focus*, not
    to the one the pointer is over. Bound the ordinary way, the page would
    scroll only while the right thing happened to be focused, which reads as
    broken. So it is bound once across the application and routed by where the
    pointer actually is.

    And a ttk combobox answers the wheel by changing its own value. On a page
    that scrolls, that is not a nuisance but a fault: a colleague rolls past
    "Master layout" on the way down and the sheets are built on a different
    title block, with nothing on screen to say so. The class binding goes, and
    a combobox then scrolls the form under it like everything else.
    """
    root.unbind_class("TCombobox", "<MouseWheel>")

    def spin(event: tk.Event[tk.Misc]) -> None:
        try:
            under = root.winfo_containing(event.x_root, event.y_root)
        except KeyError:
            # Tk made that window itself and never told Python about it --
            # a combobox's own dropdown is one, and the layer lists are long
            # enough to be scrolled. The list scrolls on its own class
            # binding; all this has to do is not raise a traceback over it.
            return
        while under is not None:
            if isinstance(under, Scroller):
                under.spin(event.delta)
                return
            under = getattr(under, "master", None)

    root.bind_all("<MouseWheel>", spin)


def pickable(names: Sequence[str]) -> list[str]:
    """Layers worth offering, without the palette's own dividers.

    A practice organises its layer list with separator layers --
    ``06 ------------------------------ ZONES`` -- which are real layers and
    hold nothing. They matter because they sort to the top: a colleague
    searching "zone" is offered the divider first and it is the likeliest
    thing to tick, which measures nothing.

    Detected by the run of dashes rather than by position, so a project that
    does not use them loses nothing.
    """
    return [name for name in names if "-----" not in name and name.strip()]


def _some(entries: Iterable[str], most: int = 5) -> str:
    """A readable list of what a layer holds, and how much was left out.

    One project's zone layer carries thirteen distinct names. Printed in full
    they wrap to three lines under a field and stop being read, which loses
    the first five as well as the last eight -- and the whole point of the
    line is that somebody glances at it. The full list, with sizes, is one
    click away in the chooser.
    """
    listed = list(entries)
    shown = ", ".join(listed[:most])
    return shown if len(listed) <= most else f"{shown} and {len(listed) - most} more"


def _letters_and_digits(text: str) -> str:
    """A name reduced to what somebody actually types when searching for it.

    Layer names carry punctuation nobody reproduces from memory -- ``01 |
    Core``, ``05 | Dims/Notes.DA``, ``Wall.External`` -- and the spacing round
    it is the practice's, not the searcher's. Somebody looking for the core
    types ``1| core``, or ``01|core``, and gets nothing, because neither
    ``1|`` nor ``01|core`` appears anywhere in ``01 | Core`` as written.

    Dropping every non-alphanumeric character from both sides makes all three
    the same question. It only ever widens what matches -- punctuation removed
    from the query cannot make a name stop matching -- so nothing that used to
    be findable becomes unfindable.
    """
    return "".join(character for character in text.casefold() if character.isalnum())


def matching(names: Sequence[str], query: str) -> list[str]:
    """Layers matching a search box, in the order the project lists them.

    Every word has to appear, in any order and anywhere in the name, so
    "floor str" finds ``01 | Floor.Structural`` without anybody having to
    remember whether the group number or the dot comes first.

    Punctuation and case are both ignored, on both sides. Layer naming is
    nobody's memory test, and the group number, the bar and the dot are the
    part of a name a person is least likely to type the way it was written --
    ``1| core``, ``01|core`` and ``core`` all have to find ``01 | Core`` or
    the picker is slower than scrolling.
    """
    words = [_letters_and_digits(word) for word in query.split()]
    wanted = [word for word in words if word]
    if not wanted:
        return list(names)
    return [name for name in names if all(word in _letters_and_digits(name) for word in wanted)]


#: Where the layer chooser was when it was last closed, as a Tk geometry
#: string. Module level because it belongs to none of the fields that open
#: one: a colleague setting a project up opens the chooser six or seven times
#: in a row -- facade layers, then also-export, then the neighbours -- and a
#: dialog that jumps back to the middle of the screen every time is one they
#: have to drag off the form again every time.
#:
#: Not saved to disk. Where a window sat is a fact about this afternoon and
#: this screen, and restoring last week's position onto a laptop that no
#: longer has the second monitor would put the chooser somewhere unreachable.
_chooser_geometry: str | None = None


class LayerChooser(tk.Toplevel):
    """Tick the names, rather than typing them. Layers, or a layer's zones.

    A project has a hundred and fifty layers whose names carry a group number,
    a dot and a space -- ``05 | Dims/Notes.DA`` -- and a study that silently
    measures nothing is what a typo in one buys. So the names come from the
    project and the only input is a tick.

    Modal, and it answers with ``None`` when cancelled rather than with the
    list it started from, so a caller can tell "unchanged" from "emptied".
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        hint: str,
        available: Sequence[str],
        chosen: Sequence[str],
        describe: Mapping[str, str] | None = None,
    ) -> None:
        """``describe`` is what a row *reads* as, where the name alone does not
        say enough -- a zone name means little without its size, and ``BY``
        beside ``12 zones, 11 m2`` is a balcony to anybody. The value ticked is
        still the name, so what the caller gets back is what the study takes.
        """
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.minsize(520, 460)
        if _chooser_geometry:
            # Size and position both, so a chooser somebody widened to read
            # long layer names opens wide the next time as well.
            self.geometry(_chooser_geometry)
        self.result: list[str] | None = None

        self._available = list(available)
        self._describe = dict(describe or {})
        #: Ticked, kept as a set across filtering: narrowing the list must not
        #: quietly untick what has scrolled out of sight.
        self._ticked: set[str] = {name for name in chosen if name in set(available)}
        self._boxes: dict[str, tk.BooleanVar] = {}

        outer = ttk.Frame(self, padding=PAD)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(outer, text=hint, foreground=HINT, wraplength=470).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        search = ttk.Frame(outer)
        search.grid(row=1, column=0, sticky="ew")
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Find").grid(row=0, column=0, padx=(0, 6))
        self.query = ttk.Entry(search)
        self.query.grid(row=0, column=1, sticky="ew")
        self.query.bind("<KeyRelease>", lambda _event: self._repaint())

        # The same pane the main form scrolls in, so the wheel behaves the
        # same way over both. It also replaces a ``bind_all`` this dialog
        # used to leave behind it: the binding outlived the window, and every
        # turn of the wheel afterwards went to a canvas that no longer existed.
        scroller = Scroller(outer)
        scroller.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=6)
        self._list = scroller.content

        self.count = ttk.Label(outer, text="", foreground=HINT)
        self.count.grid(row=3, column=0, sticky="w")

        buttons = ttk.Frame(outer)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        buttons.columnconfigure(0, weight=1)
        ttk.Button(buttons, text="Clear all", command=self._clear).grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Cancel", command=self._close).grid(row=0, column=1, padx=6)
        ttk.Button(buttons, text="Use these", command=self._accept).grid(row=0, column=2)

        self._repaint()
        self.query.focus_set()
        self.bind("<Escape>", lambda _e: self._close())
        # The window manager's own X, which goes nowhere near the buttons.
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()

    def _repaint(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        self._boxes.clear()
        for index, name in enumerate(matching(self._available, self.query.get())):
            state = tk.BooleanVar(value=name in self._ticked)
            self._boxes[name] = state
            ttk.Checkbutton(
                self._list,
                text=self._describe.get(name, name),
                variable=state,
                command=lambda n=name: self._toggle(n),  # type: ignore[misc]
            ).grid(row=index, column=0, sticky="w")
        self.count.config(text=f"{len(self._ticked)} of {len(self._available)} chosen")

    def _toggle(self, name: str) -> None:
        if self._boxes[name].get():
            self._ticked.add(name)
        else:
            self._ticked.discard(name)
        self.count.config(text=f"{len(self._ticked)} of {len(self._available)} chosen")

    def _clear(self) -> None:
        self._ticked.clear()
        self._repaint()

    def _close(self) -> None:
        """Remember where this was, then go.

        Every route out comes through here -- Cancel, Escape, the window
        manager's X and Use these -- because a dialog that remembers its place
        only when dismissed one particular way is worse than one that never
        does: it looks broken rather than absent.
        """
        global _chooser_geometry
        try:
            # ``wm_geometry`` and not ``winfo_geometry``: the first is what the
            # window manager holds and tracks through a drag, the second is
            # what the widget has been realised at -- and a Toplevel that was
            # never mapped answers that one with 1x1+0+0, which would remember
            # a corner nobody put it in.
            _chooser_geometry = self.wm_geometry()
        except tk.TclError:  # pragma: no cover - already gone
            pass
        self.destroy()

    def _accept(self) -> None:
        # Back in the project's own order, not tick order: a list a person can
        # scan against the layer palette is worth more than one recording the
        # sequence somebody happened to click in.
        self.result = [name for name in self._available if name in self._ticked]
        self._close()


#: What each table is called in the tables folder. The command line puts the
#: day in the name when a run studies another day than the ruleset's own.
APARTMENTS_TABLE = "Apartments.csv"
COS_AREAS_TABLE = "COS areas.csv"
COS_SCHEDULE_TABLE = "COS schedule.xlsx"

#: The shadow diagram's legend, one row each: the short name the run is given
#: (and matches to the legend's colour in ``archicad.shadows.LEGEND``),
#: whether it accumulates or is compared, and the row's label, hint and
#: explanation on the page. The order is the legend's, which is also the order
#: drawn, back to front.
SHADOW_LEGEND_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "EXISTING",
        "baseline",
        "Existing",
        "Existing neighbouring buildings.",
        "The lightest grey. Always there, whatever is approved: each of these "
        "rows is charged only for ground the rows before it had not already "
        "darkened, so their areas add up and their fills abut.",
    ),
    (
        "FUTURE",
        "baseline",
        "Future",
        "Future neighbouring context buildings.",
        "The middle grey. What the controls allow next door, drawn as already "
        "there, because the scheme will stand beside it.",
    ),
    (
        "EXISTING ON SITE",
        "baseline",
        "Existing on site",
        "Existing structures within the site.",
        "The darkest grey. What stands on the site today, so the new shadow "
        "is read against the old one.",
    ),
    (
        "TOD",
        "scenario",
        "TOD",
        "Current LEP 2023 building height limit.",
        "The palest blue. A scenario: cast against every grey row and against "
        "no other blue one, so the blues overlap on the sheet — which is the "
        "comparison.",
    ),
    (
        "SEARS",
        "scenario",
        "SEARs",
        "Canterbury Bankstown LEP building height limit.",
        "The middle blue. Compared, not accumulated: putting this under a grey "
        "row instead tests it against itself and reads as a much smaller "
        "shadow.",
    ),
    (
        "PROPOSED",
        "scenario",
        "Proposed",
        "Proposed building envelope.",
        "The strongest blue, drawn last so it is on top: this is the one being applied for.",
    ),
)


class Tiles(ttk.Frame):
    """A row of drawn choices, in place of a dropdown with three phrasings.

    The printer driver's own move, and the reason the icons exist at all:
    paper source, two-sided printing and pages-per-sheet are rows of little
    pictures, and a person picks the shape they meant instead of reading four
    wordings of it and deciding which one is nearest.

    It answers ``get``, ``delete`` and ``insert`` the way the Combobox it
    replaces does, because that is the interface ``Window.apply`` puts a saved
    settings file back through -- so a file saved by the old window still
    restores into this one, which is the whole reason the interface is copied
    rather than improved.

    ``multi`` makes each tile a switch of its own instead of one of a set:
    any of them can be on, and the value is the lit ones joined by commas in
    the row's order. The last one lit will not switch off, because a row
    that asks for none of its things asks for nothing to be drawn.
    ``aliases`` reads an older spelling as the tiles it now means -- a file
    saved when "both" was a tile of its own.
    """

    def __init__(
        self,
        parent: tk.Misc,
        choices: Sequence[tuple[str, str, str]],
        on_change: Callable[[], None] | None = None,
        *,
        multi: bool = False,
        aliases: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._chosen = choices[0][0]
        self._multi = multi
        self._aliases = dict(aliases or {})
        self._order = [value for value, _icon, _detail in choices]
        self._on: set[str] = set(self._order) if multi else {self._chosen}
        if multi:
            self._chosen = self._spell()
        self._on_change = on_change
        self._buttons: dict[str, ttk.Button] = {}
        for column, (value, icon, detail) in enumerate(choices):
            button = ttk.Button(
                self,
                style="Tile.TButton",
                command=partial(self._pick, value),
                **icons.button_options(icon, 16),
            )
            button.grid(row=0, column=column, padx=(0, 2))
            # Every tile says what it is in words as well. Seven unlabelled
            # drawings are only learnable if something names them, and this is
            # also what the window's own test for explained controls looks for.
            Tooltip(button, detail)
            self._buttons[value] = button
        self._paint()

    def _pick(self, value: str) -> None:
        if self._multi:
            if value in self._on and len(self._on) == 1:
                return
            self._on ^= {value}
            self._chosen = self._spell()
            self._paint()
        else:
            self.set(value)
        if self._on_change is not None:
            self._on_change()

    def _spell(self) -> str:
        """The lit tiles, in the row's order, as the one text ``get`` returns."""
        return ", ".join(value for value in self._order if value in self._on)

    def _paint(self) -> None:
        for value, button in self._buttons.items():
            button.configure(style="TileOn.TButton" if value in self._on else "Tile.TButton")

    def get(self) -> str:
        """The chosen value, spelled exactly as the caller listed it."""
        return self._chosen

    def set(self, value: str) -> None:
        """Choose one, or hold a value nobody offered.

        An unoffered value is kept rather than refused, and no tile lights up.
        These rows replaced typed fields, so a settings file saved before them
        can hold 1.25 where the tiles offer 2, 1 and 0.5 -- and silently
        rounding somebody to the nearest tile would change a study's answer
        without saying so. Held, it goes to the command line as it always did
        and the untinted row says it is not one of the three.

        In a ``multi`` row the value is a comma list, each part a tile or an
        alias for some; a value that names none of them is held the same way.
        """
        self._chosen = value
        if not self._multi:
            self._on = {value}
        else:
            wanted: set[str] = set()
            for part in (piece.strip() for piece in value.split(",")):
                wanted.update(self._aliases.get(part, (part,)))
            self._on = wanted & set(self._order)
            if self._on:
                self._chosen = self._spell()
        self._paint()

    # -- what makes it a drop-in for the Combobox it replaced --------------
    def delete(self, first: object = 0, last: object = None) -> None:
        """Nothing to clear: one of the tiles is always the chosen one."""

    def insert(self, index: object, value: str) -> None:
        """How ``Window.apply`` restores a saved choice."""
        self.set(value)


class Ticks(ttk.Frame):
    """A row of hours, or of days, each a button that is on or off.

    In place of a text box that took ``9,10,11,12,13,14,15`` and
    ``08:00-15:00`` and ``06-21, 12-21`` -- three spellings a person had to
    know and could get wrong. The buttons are the values, and there is
    nothing to spell.

    It answers ``get``, ``delete`` and ``insert`` the way the Entry it
    replaces does, for the reason ``Tiles`` does: ``Window.apply`` puts a
    saved file back through that interface, and the run reads the field's
    text. The text is kept rather than rebuilt from the buttons: a file that
    says ``9, 3pm`` lights nine and three and is sent as ``9, 3pm``, and a
    value no button stands for -- a half hour, a date not offered -- is kept
    as typed, sent as typed, and lights nothing, so a setting is never
    silently rounded to the nearest button.

    ``span`` makes the row a range: what is lit runs from the first ticked
    button to the last, and the text is ``08:00-15:00`` rather than a list,
    which is how the communal window is asked for.
    """

    def __init__(
        self,
        parent: tk.Misc,
        choices: Sequence[tuple[str, str, str]],
        *,
        key: Callable[[str], str],
        span: bool = False,
        joiner: str = ", ",
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._choices = list(choices)
        self._key = key
        self._span = span
        self._joiner = joiner
        self._on_change = on_change
        self._text = ""
        self._on: set[str] = set()
        self._buttons: dict[str, ttk.Button] = {}
        for column, (value, label, detail) in enumerate(choices):
            button = ttk.Button(
                self,
                text=label,
                style="Tile.TButton",
                width=max(2, len(label)),
                command=partial(self._toggle, value),
            )
            button.grid(row=0, column=column, padx=(0, 2))
            Tooltip(button, detail)
            self._buttons[value] = button
        self._paint()

    def _toggle(self, value: str) -> None:
        if value in self._on:
            self._on.discard(value)
        else:
            self._on.add(value)
        self._text = self._spell()
        self._paint()
        if self._on_change is not None:
            self._on_change()

    def _spell(self) -> str:
        """The text the buttons mean, in the row's own order."""
        lit = [value for value, _label, _detail in self._choices if value in self._on]
        if not lit:
            return ""
        if self._span:
            return lit[0] if len(lit) == 1 else f"{lit[0]}-{lit[-1]}"
        return self._joiner.join(lit)

    def _lit(self) -> set[str]:
        """The buttons shown on: in a span, everything between the ends."""
        if not self._span or len(self._on) < 2:
            return set(self._on)
        order = [value for value, _label, _detail in self._choices]
        first = min(order.index(value) for value in self._on)
        last = max(order.index(value) for value in self._on)
        return set(order[first : last + 1])

    def _paint(self) -> None:
        lit = self._lit()
        for value, button in self._buttons.items():
            button.configure(style="TileOn.TButton" if value in lit else "Tile.TButton")

    def get(self) -> str:
        """The field's text, exactly as it would be sent."""
        return self._text

    # -- what makes it a drop-in for the Entry it replaced ------------------
    def delete(self, first: object = 0, last: object = None) -> None:
        self._text = ""
        self._on = set()
        self._paint()

    def insert(self, index: object, value: str) -> None:
        """How ``Window.apply`` restores a saved field, and how a test types."""
        self._text = value
        wanted = {self._key(part) for part in self._parts(value)} - {""}
        self._on = {
            choice for choice, _label, _detail in self._choices if self._key(choice) in wanted
        }
        self._paint()

    def _parts(self, text: str) -> list[str]:
        if self._span:
            halves = [half.strip() for half in text.replace("to", "-").split("-")]
            return [half for half in halves if half]
        return [part.strip() for part in text.split(",") if part.strip()]


class Toggles(ttk.Frame):
    """A row of on-or-off buttons, each with its picture, over a BooleanVar.

    What a row of check boxes becomes when the choices have pictures: the
    three assessment days, each a sun at its own height. The variables are
    the caller's, so everything that read a tick before reads it still; the
    buttons only show and flip them. ``paint`` is called by the window's
    ``_sync`` as well as on a press, because a test or a preset can set the
    variable without pressing anything.
    """

    def __init__(self, parent: tk.Misc, *, on_change: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._items: list[tuple[tk.BooleanVar, ttk.Button]] = []

    def add(self, variable: tk.BooleanVar, label: str, icon: str) -> ttk.Button:
        """One more button, bound to ``variable``. Returned so the caller
        can explain it, as every control in the window is explained."""
        button = ttk.Button(
            self,
            text=label,
            style="Tile.TButton",
            takefocus=False,
            command=partial(self._flip, variable),
            **icons.button_options(icon, 16),
        )
        button.grid(row=0, column=len(self._items), padx=(0, 4))
        self._items.append((variable, button))
        self.paint()
        return button

    def _flip(self, variable: tk.BooleanVar) -> None:
        variable.set(not variable.get())
        self.paint()
        if self._on_change is not None:
            self._on_change()

    def paint(self) -> None:
        for variable, button in self._items:
            button.configure(style="TileOn.TButton" if variable.get() else "Tile.TButton")


class Chips(ttk.Frame):
    """The names chosen for a setting, each with the button that drops it.

    It stands in for the Entry that used to hold a comma-joined list, and it
    keeps that interface exactly -- ``get``, ``delete``, ``insert`` -- because
    the settings file round-trips through those three and a file written by
    the old window still has to restore into this one.

    A text box was the honest record of what gets passed and the worst way to
    show it. Forty of them made the page a form; and the one thing a person
    wants from a layer list, *which layers*, was a comma-joined string
    scrolling out of a field two hundred pixels wide. Chips are the same
    record with a way out of each one, and they wrap, so six layers are six
    things rather than a line that has run off the end.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        add: Callable[[], None],
        on_change: Callable[[], None] | None = None,
        empty: str = "none chosen",
        label: str = "this setting",
    ) -> None:
        super().__init__(parent)
        self._values: list[str] = []
        self._add = add
        #: What the setting is called, so the two buttons a chip row carries
        #: can say what they will do to it. Every control in this window
        #: explains itself, and a bare cross is a control.
        self._label = label
        self._changed = on_change
        self._empty = empty
        self._made: list[tk.Widget] = []
        #: The pane the row has to fit inside. Its own width is no guide: a
        #: frame is given whatever it asks for, and a row that asked for one
        #: long line was given one long line, off the edge of the page.
        self._pane: tk.Canvas | None = None
        node: tk.Misc | None = parent
        while node is not None and not isinstance(node, tk.Canvas):
            node = node.master
        if isinstance(node, tk.Canvas):
            self._pane = node
            node.bind("<Configure>", self._reflow, add="+")
        self.bind("<Configure>", self._reflow)
        self._paint()

    # -- what makes it a drop-in for the Entry it replaced -----------------
    def get(self) -> str:
        """The comma-joined list, spelled the way the command line takes it."""
        return ", ".join(self._values)

    def delete(self, first: object = 0, last: object = None) -> None:
        """Every caller clears the whole thing, so the range is not honoured."""
        self._values.clear()
        self._paint()

    def insert(self, index: object, value: str) -> None:
        for name in str(value).split(","):
            if name.strip():
                self._values.append(name.strip())
        self._paint()

    # -- and what makes it chips -------------------------------------------
    def drop(self, name: str) -> None:
        if name in self._values:
            self._values.remove(name)
            self._paint()
            if self._changed is not None:
                self._changed()

    def _paint(self) -> None:
        for old in self._made:
            old.destroy()
        self._made = []
        for name in self._values:
            chip = ttk.Frame(self, style="Chip.TFrame")
            ttk.Label(chip, text=name, style="Chip.TLabel").pack(side="left")
            cross = ttk.Button(
                chip,
                # The close glyph, spelled as an escape: ruff reads a literal
                # multiplication sign as a typo for the letter x, and here it is
                # neither -- it is the cross every window in Windows shuts with.
                text="×",  # noqa: RUF001 - the close cross, not a letter x
                style="ChipDrop.TButton",
                width=2,
                takefocus=True,
                command=partial(self.drop, name),
            )
            cross.pack(side="left")
            Tooltip(
                cross,
                f"Takes {name} out of {self._label}. Nothing else changes, and "
                "the list it came from is still there to put it back.",
                title=f"Drop {name}",
            )
            self._made.append(chip)
        if not self._values:
            self._made.append(ttk.Label(self, text=self._empty, style="Hint.TLabel"))
        more = ttk.Button(self, text="+ Add", style="Add.TButton", command=self._add)
        Tooltip(
            more,
            "Opens the list the project itself holds, with what is already chosen "
            "ticked. Nothing is typed, so nothing can be misspelt -- which is how a "
            "study ends up measuring a layer that is not there and saying nothing.",
            title=f"Add to {self._label}",
        )
        self._made.append(more)
        self._reflow()
        # Once more when the chips have been measured: a chip made a moment
        # ago has no size yet, and a row laid out from sizes of one pixel
        # is one long line until something resizes the pane.
        self.after_idle(self._reflow)

    def room(self) -> int:
        """How wide a row may be: the pane, less the label column and the
        margin -- or a guess, before anything has been drawn."""
        if self._pane is None or self._pane.winfo_width() <= 1:
            return 420
        return max(
            self._pane.winfo_width() - (self.winfo_rootx() - self._pane.winfo_rootx()) - 14, 120
        )

    def _reflow(self, _event: object = None, *, room: int | None = None) -> None:
        """Lay the chips out in as many rows as it takes.

        Tk has no flow layout, so this is it: measure each chip and start a
        new row when the next one would not fit. Placed, not gridded: a grid
        lines its columns up down the page, so the second row's chips sat
        under the first row's column edges with gaps between them where the
        first row's chips were wider. Called on every resize, because the
        pane changes width when the dock is folded away.
        """
        room = self.room() if room is None else room
        x = y = tall = 0
        for made in self._made:
            need, high = made.winfo_reqwidth(), made.winfo_reqheight()
            if x and x + need > room:
                x, y, tall = 0, y + tall + 3, 0
            made.place(x=x, y=y)
            x += need + 4
            tall = max(tall, high)
        # Placed children do not size their parent, so the row says its own
        # size: as wide as the pane allows, as tall as the rows came to.
        self.configure(width=room, height=y + tall + 2)


class InfoBand(ttk.Frame):
    """One strip at the foot of the window that explains what you are on.

    It replaces two things. The grey line printed under every control, forty
    of which at once is a wall nobody reads; and the ``Tooltip`` Toplevel,
    which opened over the window 450 ms after the pointer stopped, covered the
    thing you were pointing at, went away while you were still reading it, and
    could not be reached from the keyboard at all.

    Fixed height, which matters more than it sounds: a band that grows and
    shrinks as the pointer crosses the page makes the whole window jump, and a
    window that moves under the pointer is worse than no explanation.
    """

    #: Three lines and a heading, and never more. Anything longer is cut
    #: rather than allowed to push the run bar off the bottom of the screen.
    HEIGHT = 78

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Info.TFrame", padding=(12, 7, 12, 7), height=self.HEIGHT)
        # Both latches. The children are gridded, so `grid_propagate` is the
        # one that holds the height -- `pack_propagate` alone let the band
        # collapse to nothing, which is a strip that explains everything by
        # being invisible.
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.columnconfigure(1, weight=1)

        self.drawing = ttk.Label(self, style="Info.TLabel")
        self.drawing.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 9))
        self.title = ttk.Label(self, text="", style="InfoTitle.TLabel")
        self.title.grid(row=0, column=1, sticky="w")
        #: What the thing under the pointer is set to, at the right of the
        #: band. Not called ``state``: that is ttk's own method on every
        #: widget, and a label by that name shadows it.
        self.aside = ttk.Label(self, text="", style="InfoState.TLabel")
        self.aside.grid(row=0, column=2, sticky="e")
        self.short = ttk.Label(self, text="", style="Info.TLabel", justify="left")
        self.short.grid(row=1, column=1, columnspan=2, sticky="w")
        self.detail = ttk.Label(self, text="", style="InfoHint.TLabel", justify="left")
        self.detail.grid(row=2, column=1, columnspan=2, sticky="nw")

        #: What it says when the pointer is on nothing. Never empty: a strip
        #: that blanks itself is dead space at the bottom of the window, which
        #: is exactly what the log was.
        self._resting: tuple[str, str, str, str] = ("", "", "", "")
        self.bind("<Configure>", self._rewrap)

    def _rewrap(self, _event: object = None) -> None:
        room = max(self.winfo_width() - 60, 200)
        self.short.config(wraplength=room)
        self.detail.config(wraplength=room)

    def show(
        self,
        glyph: str,
        title: str,
        short: str,
        detail: str = "",
        *,
        state: str = "",
        idle: bool = False,
    ) -> None:
        self.drawing.config(**icons.state_options(glyph, 20))
        self.title.config(text=title, style="InfoIdle.TLabel" if idle else "InfoTitle.TLabel")
        self.aside.config(text=state)
        self.short.config(text=short)
        self.detail.config(text=detail)

    def resting(self, glyph: str, title: str, short: str, detail: str = "") -> None:
        """Set what "nothing under the pointer" means, and say it now."""
        self._resting = (glyph, title, short, detail)
        self.rest()

    def rest(self) -> None:
        glyph, title, short, detail = self._resting
        self.show(glyph, title, short, detail, idle=True)

    def watch(
        self,
        widget: tk.Misc,
        glyph: str,
        title: str,
        short: str,
        detail: str = "",
        *,
        state: Callable[[], str] | None = None,
    ) -> None:
        """Make that widget explain itself here, on hover and on focus.

        Focus as well as hover, which is the part a popup could never do: a
        colleague tabbing through the window gets the same sentences as one
        pointing at it.
        """

        def enter(_event: object = None) -> None:
            self.show(glyph, title, short, detail, state="" if state is None else state())

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<FocusIn>", enter, add="+")
        widget.bind("<Leave>", lambda _event: self.rest(), add="+")
        widget.bind("<FocusOut>", lambda _event: self.rest(), add="+")


@dataclass(frozen=True)
class Drawing:
    """One drawing on a layout: what it shows, and where the sun is for it.

    A site sheet has no hour and no sun; everything else is one instant of
    one day, and the sun at that instant is what the thumbnail draws.
    """

    kind: str
    day: str
    time: str
    azimuth: float | None = None
    elevation: float | None = None

    @property
    def bearing(self) -> float | None:
        """Which way the shadow falls: away from the sun."""
        return None if self.azimuth is None else (self.azimuth + 180.0) % 360.0

    @property
    def reach(self) -> float | None:
        """How long, as a multiple of the thing casting it."""
        if self.elevation is None or self.elevation <= 0.5:
            return None
        return 1.0 / math.tan(math.radians(self.elevation))


@dataclass(frozen=True)
class Sheet:
    """One layout a run will put in the Layout Book, and the drawings on it.

    Everything here is known before anything runs. The sun is arithmetic on a
    date and a latitude; the rest is the settings on the page. Which is the
    whole reason the panel can be drawn at all.

    How many drawings share a layout is the Sheets choice in General, and it
    is dealt here by the same ``sheet_chunks`` the run deals with -- so the
    panel cannot say four sheets where the run makes two. ``cells`` is the
    grid the layout is laid out on, which for the short second sheet of a
    pair is larger than the number of drawings on it: the run leaves those
    cells empty rather than enlarging the rest, and so does the thumbnail.
    """

    study: str
    glyph: str
    number: str
    kind: str
    day: str
    drawings: tuple[Drawing, ...] = ()
    cells: int = 1
    #: This sheet's place in its set -- ``(2, 2)`` is the second of two --
    #: which is how the run titles a sheet that carries several drawings.
    part: int = 1
    parts: int = 1
    #: The study's own job name, so a box can say how many sheets *its* tick
    #: is worth. The panel groups by ``study``, which three jobs share.
    job: str = ""
    #: The scale the run places the drawings at -- ``1:500`` -- or what it
    #: does instead: a site sheet is fitted, a table has none.
    scale: str = ""
    #: False for the outputs that are not sheets at all -- the context model
    #: and the future model, which are geometry on their own layers. The
    #: panel draws those as the geometry, with no paper under it.
    paper: bool = True

    @property
    def time(self) -> str:
        """What the layout is named for: the one hour, or the range."""
        return sheet_title([drawing.time for drawing in self.drawings if drawing.time])

    @property
    def empty(self) -> int:
        """Cells of the grid with no drawing in them."""
        return max(self.cells - len(self.drawings), 0)

    # The first drawing's sun, which is the sheet's when it carries one --
    # and what the band quotes for a sheet that carries several.
    @property
    def azimuth(self) -> float | None:
        return self.drawings[0].azimuth if self.drawings else None

    @property
    def elevation(self) -> float | None:
        return self.drawings[0].elevation if self.drawings else None

    @property
    def bearing(self) -> float | None:
        return self.drawings[0].bearing if self.drawings else None

    @property
    def reach(self) -> float | None:
        return self.drawings[0].reach if self.drawings else None


class Dock(ttk.Frame):
    """Every sheet the run will make, drawn, down the right of the window.

    Outside the tabs on purpose. It belongs to the *run*, not to a section, so
    somebody filling in Sun views can see the twenty-one shadow sheets waiting
    behind them without leaving the page. It also retires the row of chips
    that used to sit above Run: that line existed because the ticks are spread
    over six sections and nothing on screen answered "what happens if I press
    this", and a panel of the actual sheets answers it better.

    It folds. A palette that cannot be put away is a palette that costs a
    third of the window whether or not anybody is looking at it, and below a
    certain width the page beside it needs the room more. Folded, it is a
    strip with the count on it -- which is still the answer to "how much will
    this make", just not the picture.
    """

    #: One across. Two side by side made a spread out of two unrelated days.
    SHEET_W = 300
    #: A4 landscape, 297 x 210.
    SHEET_H = 212
    #: The sheet, its shadow, its padding and the scrollbar beside it.
    WIDTH = 336
    #: What is left when it is folded: the chevron, the count, and the word.
    FOLDED = 30

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_pick: Callable[[Sheet | None], None],
        on_fold: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(parent, style="Dock.TFrame", width=self.WIDTH)
        self.pack_propagate(False)
        self._on_pick = on_pick
        self._on_fold = on_fold
        self._drawn: list[tk.Misc] = []
        self.folded = False

        # -- open -----------------------------------------------------------
        self.open_view = ttk.Frame(self, style="Dock.TFrame")
        head = ttk.Frame(self.open_view, style="Dock.TFrame", padding=(10, 7, 4, 3))
        head.pack(side="top", fill="x")
        ttk.Label(head, text="Sheets", style="DockTitle.TLabel").pack(side="left")
        self.tally = ttk.Label(head, text="0", style="DockCount.TLabel")
        self.tally.pack(side="left", padx=(7, 0))
        self.fold_button = ttk.Button(
            head,
            text="›",  # noqa: RUF001 - a chevron, not a comparison
            style="Fold.TButton",
            width=2,
            command=lambda: self.fold(True),
        )
        self.fold_button.pack(side="right")
        Tooltip(
            self.fold_button,
            "Folds the panel to its edge, to give the page beside it the room. "
            "The count stays on the strip, and the window folds it by itself "
            "when it is dragged too narrow to hold both.",
            title="Fold the sheets away",
        )
        self.filed = ttk.Label(self.open_view, text="", style="DockHint.TLabel")
        self.filed.pack(side="top", fill="x", padx=10, pady=(0, 5))
        self.pane = Scroller(self.open_view, ground=theme.CHROME)
        self.pane.pack(side="top", fill="both", expand=True)

        # -- folded ---------------------------------------------------------
        self.shut_view = ttk.Frame(self, style="Dock.TFrame", padding=(0, 6, 0, 0))
        self.unfold_button = ttk.Button(
            self.shut_view,
            text="‹",  # noqa: RUF001 - a chevron, not a comparison
            style="Fold.TButton",
            width=2,
            command=lambda: self.fold(False),
        )
        self.unfold_button.pack(side="top")
        Tooltip(
            self.unfold_button,
            "Brings the panel back: every sheet the ticked studies will make, "
            "drawn at the hour and the day it is for.",
            title="Show the sheets",
        )
        self.shut_tally = ttk.Label(self.shut_view, text="0", style="DockCount.TLabel")
        self.shut_tally.pack(side="top", pady=(6, 4))
        # Tk cannot turn a label on its side, and a canvas can turn its text.
        spine = tk.Canvas(
            self.shut_view,
            width=self.FOLDED - 8,
            height=60,
            background=theme.CHROME,
            highlightthickness=0,
        )
        spine.create_text(
            (self.FOLDED - 8) // 2,
            30,
            text="Sheets",
            angle=90,
            fill=theme.HINT,
            font=(theme.FACE, 8),
        )
        spine.pack(side="top")

        self.open_view.pack(fill="both", expand=True)

    def fold(self, shut: bool, *, by_hand: bool = True) -> None:
        """Put the panel away, or bring it back."""
        if shut == self.folded:
            return
        self.folded = shut
        if shut:
            self.open_view.pack_forget()
            self.shut_view.pack(fill="both", expand=True)
        else:
            self.shut_view.pack_forget()
            self.open_view.pack(fill="both", expand=True)
        self.configure(width=self.FOLDED if shut else self.WIDTH)
        if by_hand and self._on_fold is not None:
            self._on_fold(shut)

    def refill(self, sheets: Sequence[Sheet], *, filed: str) -> None:
        """Redraw the panel. Cheap enough to do on every tick and keystroke:
        the drawing is a few dozen canvas items and the geometry is a numpy
        call that never leaves this process."""
        for old in self._drawn:
            old.destroy()
        self._drawn = []
        # The count is of sheets. A model in the panel is drawn there because
        # the run makes it, and not counted here because it is not one.
        papers = sum(1 for sheet in sheets if sheet.paper)
        self.tally.config(text=str(papers))
        self.shut_tally.config(text=str(papers))
        self.filed.config(text=filed)

        if not sheets:
            empty = ttk.Label(
                self.pane.content,
                text=(
                    "Nothing ticked.\n\nThe sheets a run would make appear here as "
                    "you switch studies on."
                ),
                style="DockHint.TLabel",
                justify="center",
                wraplength=self.SHEET_W - 20,
            )
            empty.pack(pady=24, padx=10)
            self._drawn.append(empty)
            return

        study = ""
        day = ""
        for sheet in sheets:
            if sheet.study != study:
                study = sheet.study
                day = ""
                head = ttk.Frame(self.pane.content, style="Dock.TFrame")
                head.pack(side="top", fill="x", padx=10, pady=(9, 3))
                ttk.Label(
                    head,
                    text=sheet.study,
                    style="DockStudy.TLabel",
                    **icons.button_options(sheet.glyph),
                ).pack(side="left")
                ttk.Label(
                    head,
                    text=str(sum(1 for other in sheets if other.study == sheet.study)),
                    style="DockCount.TLabel",
                ).pack(side="right")
                self._drawn.append(head)
            if sheet.day and sheet.day != day:
                day = sheet.day
                line = ttk.Label(self.pane.content, text=day, style="DockDay.TLabel")
                line.pack(side="top", anchor="w", padx=10, pady=(4, 2))
                self._drawn.append(line)
            self._drawn.append(self._draw(sheet))

    #: How far the paper sits in from the canvas edge, which is the room its
    #: shadow falls into.
    LIFT = 3

    def _draw(self, sheet: Sheet) -> tk.Canvas:
        """One sheet, at the master's proportions with its title block.

        Drawn in millimetres and scaled, so the geometry sits where it will
        sit on the paper and the title block really is the 40 mm the General
        tab is set to. The sheet number and the drawing title are the two
        things drawn larger than they will print: a label nobody can read
        identifies nothing, and a thumbnail is not a print preview.

        Paper stays square. Everything you press in this window is rounded
        and the sheets are not, because paper has corners -- and that is the
        line between the interface and the thing it is making. It gets a
        shadow instead, the way a page sits in InDesign's panel.
        """
        lift = self.LIFT
        paper = tk.Canvas(
            self.pane.content,
            width=self.SHEET_W + lift * 2,
            height=self.SHEET_H + lift * 2,
            background=theme.CHROME,
            highlightthickness=0,
        )
        paper.pack(side="top", padx=10 - lift, pady=(0, 9 - lift))
        # A model is not a sheet, so it is not drawn as one: the geometry
        # alone, with no paper and no shadow under it.
        (draw_sheet if sheet.paper else draw_model)(paper, sheet, self.SHEET_W, self.SHEET_H)
        paper.move("all", lift, lift - 1)
        # The shadow: three greys, each a pixel further down and out, under
        # everything else. Tk has no blur, and three steps read as one.
        for step, grey in ((3, "#E9E9E8"), (2, "#E0E0DE"), (1, "#D3D3D0")) if sheet.paper else ():
            under = paper.create_rectangle(
                lift - 1 + step // 2,
                lift - 1 + step,
                lift + self.SHEET_W + step // 2,
                lift - 1 + self.SHEET_H + step,
                fill=grey,
                outline="",
            )
            paper.tag_lower(under)

        def lit(on: bool) -> None:
            # The sheet under the pointer takes the blue edge, which is what
            # says the figures in the band below belong to *this* one.
            resting = theme.EDGE if sheet.paper else ""
            paper.itemconfigure("edge", outline=theme.BLUE if on else resting, width=2 if on else 1)
            self._on_pick(sheet if on else None)

        paper.bind("<Enter>", lambda _event: lit(True), add="+")
        paper.bind("<Leave>", lambda _event: lit(False), add="+")
        return paper


# -- drawing a sheet before it exists --------------------------------------
#
# The panel draws each layout at the proportions of the master it will be made
# from, in millimetres, so the geometry lands where it will land on the paper.
# Nothing here asks Archicad anything: the sun is `core.solar` on a date and a
# latitude, and the rest is the settings on the page.
#
# The site and the block are schematic and say so on the sheet. The real
# footprint is the model export -- 67 MB and minutes -- which is not something
# to fetch on a keystroke. The shadow *around* the block is exact even though
# the block is not, which is the part worth checking before pressing Run.

#: The sheet itself, in millimetres. A4 landscape.
SHEET_MM_W, SHEET_MM_H = 297.0, 210.0
#: The site and what sits on it, at 1:1000, so a metre is a millimetre.
SITE_MM = (66.0, 40.0, 196.0, 168.0)
BLOCK_MM = (104.0, 78.0, 164.0, 118.0)
BLOCK_HEIGHT_M = 21.0
NEIGHBOURS_MM = ((74.0, 48.0, 100.0, 70.0), (170.0, 126.0, 190.0, 160.0))
#: The blocks around the site on the context sheet, which shows a
#: neighbourhood where the others show a site.
CONTEXT_MM = (
    (72.0, 46.0, 96.0, 66.0),
    (108.0, 46.0, 136.0, 62.0),
    (146.0, 46.0, 168.0, 64.0),
    (72.0, 84.0, 94.0, 112.0),
    (182.0, 80.0, 194.0, 110.0),
    (72.0, 128.0, 100.0, 160.0),
    (118.0, 134.0, 150.0, 160.0),
    (166.0, 126.0, 190.0, 160.0),
)
#: Six flats to a plate, for the apartment sheets.
FLATS_MM = tuple(
    (78.0 + across * 40.0, 62.0 + down * 42.0, 114.0 + across * 40.0, 100.0 + down * 42.0)
    for down in range(2)
    for across in range(3)
)
SHADOW_GREY = "#8F8E87"


def _clock_text(text: str) -> str:
    """``9``, ``9am``, ``09:00`` and ``3pm`` as the ``15:00`` a sheet is named for.

    Anything that is not an hour is kept as typed: the run will refuse it,
    and the panel should show the same word the run is going to refuse.
    """
    word = text.strip().lower()
    afternoon = word.endswith("pm")
    word = word.removesuffix("am").removesuffix("pm").strip()
    hour, _, minute = word.partition(":")
    if not hour.isdigit() or (minute and not minute.isdigit()):
        return text.strip()
    hours = int(hour) + (12 if afternoon and int(hour) < 12 else 0)
    return f"{hours:02d}:{int(minute or 0):02d}"


def _hour_choices(clock: bool) -> list[tuple[str, str, str]]:
    """Six in the morning to seven at night, as a row of buttons.

    ``clock`` is the spelling the field sends: ``09:00`` for the fields that
    take a time of day, ``9`` for the ones that take whole hours.
    """
    out: list[tuple[str, str, str]] = []
    for hour in range(6, 20):
        value = f"{hour:02d}:00" if clock else str(hour)
        if hour < 12:
            said = f"{hour} in the morning"
        elif hour == 12:
            said = "midday"
        else:
            said = f"{hour - 12} in the afternoon"
        out.append((value, str(hour), f"{said.capitalize()}. Press to include it."))
    return out


def _day_key(text: str) -> str:
    """A day as ``MM-DD``, however it was written -- or as written, when it
    is not a day at all."""
    try:
        return parse_day(text)
    except ValueError:
        return text.strip()


#: The four days a shadow set is drawn for, as the row offers them.
DAY_CHOICES: tuple[tuple[str, str, str], ...] = (
    ("03-21", "21 Mar", "Autumn equinox, 21 March. Press to include it."),
    (
        "06-21",
        "21 Jun",
        "Winter solstice, 21 June -- the shortest day, when shadows are longest, and "
        "the day that decides things. Press to include it.",
    ),
    ("09-21", "21 Sep", "Spring equinox, 21 September. Press to include it."),
    ("12-21", "21 Dec", "Summer solstice, 21 December. Press to include it."),
)


def _hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Monotone chain. Eight corners in, the shadow's own outline out."""
    points = sorted(set(points))
    if len(points) <= 2:
        return points

    def half(seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for point in seq:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1) > 0:
                    break
                out.pop()
            out.append(point)
        return out[:-1]

    return half(points) + half(points[::-1])


#: The drawing itself, in the sheet's millimetres: a square around the site
#: and what stands on it. A layout carrying one drawing puts it here, which
#: is where it always sat; a layout carrying several fits this square into
#: each cell of its grid, the way the run shrinks its drawings to the cells.
FRAME_MM = (56.0, 28.0, 206.0, 178.0)
#: What the cells are cut from: the page less the title block, a margin and
#: the title line along the bottom.
MARGIN_MM = 8.0
CELLS_BOTTOM_MM = 180.0


def _grid(
    count: int, area: tuple[float, float, float, float], gap: float = 3.0
) -> list[tuple[float, float, float, float]]:
    """``count`` cells across ``area``, laid out as the run lays a sheet out.

    The same rule as ``sun_eyes.sheet_cells_for``, which is what the run
    calls: as many across as wastes the fewest cells and then keeps them
    nearest square, so four drawings are two by two and not three and one.
    The thumbnail has to agree with the sheet about that, or it shows a row
    where the run makes a block.
    """
    if count <= 0:
        return []
    left, top, right, bottom = area
    width, height = right - left, bottom - top

    def cost(columns: int) -> tuple[int, float]:
        rows = -(-count // columns)
        return (columns * rows - count, abs(math.log((width / columns) / (height / rows))))

    columns = min(range(1, count + 1), key=cost)
    rows = -(-count // columns)
    cell_w, cell_h = width / columns, height / rows
    return [
        (
            left + (index % columns) * cell_w + gap,
            top + (index // columns) * cell_h + gap,
            left + (index % columns + 1) * cell_w - gap,
            top + (index // columns + 1) * cell_h - gap,
        )
        for index in range(count)
    ]


def _untimed_note(sheet: Sheet) -> tuple[str, str]:
    """What a sheet with no hour on it is instead: the short line under its
    title, and the sentence the band says when the pointer is on it."""
    if sheet.study == "Site analysis":
        return (
            "Drawn from the address, not from the sun",
            "Drawn from the address in Site analysis and NSW open data, so it has "
            "no hour and no sun on it.",
        )
    if sheet.kind == COMMUNAL_AREAS:
        return (
            "The figures, tabled",
            "The measured area of every communal space, tabled on a sheet of its "
            "own, so it has no hour and no sun on it.",
        )
    return (
        "The whole day, banded by hours of sun",
        "The whole assessment window on one plan, banded by hours of sun, so it "
        "is not at any one hour and the Sheets row does not deal it.",
    )


def draw_sheet(
    paper: tk.Canvas, sheet: Sheet, width: int, height: int, *, block_mm: float = 40.0
) -> None:
    """One layout, drawn on a canvas at the size the panel has room for."""
    scale = width / SHEET_MM_W

    def x(value: float) -> float:
        return value * scale

    def words(
        mm_x: float,
        mm_y: float,
        text: str,
        size: int,
        colour: str,
        *,
        anchor: Literal["w", "center"] = "w",
        bold: bool = False,
    ) -> None:
        paper.create_text(
            x(mm_x), x(mm_y), text=text, anchor=anchor, fill=colour, font=_face(size, bold)
        )

    # -- the paper itself ------------------------------------------------
    # Drawn, not left to the canvas: the canvas is the palette's grey, so the
    # sheet can throw a shadow onto it, and the edge is an item so that the
    # panel can turn it blue under the pointer.
    paper.create_rectangle(
        0, 0, width - 1, height - 1, fill=theme.SURFACE, outline=theme.EDGE, tags="edge"
    )

    draw_r = SHEET_MM_W - block_mm - 7.0

    # -- the drawings ----------------------------------------------------
    #
    # One drawing takes the sheet, as it always did. Several are dealt onto
    # the grid the run will use, each shrunk into its cell with its hour under
    # it -- and a cell the run leaves empty is drawn empty, because the short
    # second sheet of a pair really does have a hole in it.
    if sheet.cells <= 1:
        frames = [FRAME_MM]
    else:
        frames = _grid(sheet.cells, (MARGIN_MM, MARGIN_MM, draw_r - 4.0, CELLS_BOTTOM_MM))
    for index, frame_mm in enumerate(frames):
        frame = (x(frame_mm[0]), x(frame_mm[1]), x(frame_mm[2]), x(frame_mm[3]))
        if index >= len(sheet.drawings):
            paper.create_rectangle(*frame, outline=theme.LINE, dash=(3, 3))
            words(
                (frame_mm[0] + frame_mm[2]) / 2,
                (frame_mm[1] + frame_mm[3]) / 2,
                "empty",
                6,
                theme.HINT,
                anchor="center",
            )
            continue
        drawing = sheet.drawings[index]
        if len(frames) > 1:
            paper.create_rectangle(*frame, outline=theme.LINE)
            words(frame_mm[0] + 1.5, frame_mm[3] - 3.5, drawing.time, 6, theme.HINT)
            frame = (frame[0], frame[1], frame[2], frame[3] - x(7.0))
        _draw_drawing(paper, sheet.study, drawing, frame)

    # -- north, which is up --------------------------------------------
    north_x, north_y = x(draw_r - 14), x(26)
    ring = x(7)
    paper.create_oval(
        north_x - ring,
        north_y - ring,
        north_x + ring,
        north_y + ring,
        fill=theme.SURFACE,
        outline=theme.EDGE,
    )
    paper.create_polygon(
        north_x,
        north_y - x(6),
        north_x + x(2.6),
        north_y + x(2.4),
        north_x,
        north_y + x(0.6),
        north_x - x(2.6),
        north_y + x(2.4),
        fill=theme.INK,
        outline="",
    )
    words(draw_r - 14, 15, "N", 6, theme.INK, anchor="center")

    # -- what this drawing is ------------------------------------------
    #
    # A site sheet is not at an hour of the day, so it is titled by what it
    # is; a whole-day plan by its day; everything else by when, because that
    # is what tells one sheet of a study from the next. A sheet that is one
    # of a pair says so, as the run names it.
    # -- what this drawing is ------------------------------------------
    #
    # The drawing's name first and largest -- "Communal open space by hour",
    # "Shadow diagram" -- because that is what a person is looking for
    # across the panel; the day and the hour under it, and which of a pair
    # it is; and last, small, what the sun is doing.
    timed = bool(sheet.time)
    if timed:
        when = f"{sheet.day} \u00b7 {sheet.time}"
    elif sheet.day:
        when = f"{sheet.day} \u00b7 the whole day"
    else:
        when = ""
    if sheet.parts > 1:
        when += f"   ({sheet.part} of {sheet.parts})"
    words(10, 181, sheet.kind.upper(), 10, theme.INK, bold=True)
    if when:
        words(10, 192, when, 7, theme.BODY)
    if not timed:
        words(10, 201, _untimed_note(sheet)[0], 6, theme.HINT)
    elif sheet.elevation is None:
        words(10, 201, "Project location not set \u2014 no sun to draw", 6, theme.RED)
    elif len(sheet.drawings) == 1:
        cast = (
            f" \u00b7 shadow {sheet.reach:.1f}x the height"
            if sheet.reach is not None and sheet.study == "Shadow diagram"
            else ""
        )
        words(
            10,
            201,
            f"Sun {sheet.elevation:.1f}\u00b0 \u00b7 azimuth {sheet.azimuth:.0f}\u00b0{cast}",
            6,
            theme.HINT,
        )
    else:
        ups = [d.elevation for d in sheet.drawings if d.elevation is not None]
        note = f"{len(sheet.drawings)} drawings"
        if sheet.empty:
            note += f", {sheet.empty} cell{'' if sheet.empty == 1 else 's'} empty"
        if ups:
            note += f" \u00b7 sun {min(ups):.0f}\u00b0 to {max(ups):.0f}\u00b0"
        words(10, 201, note, 6, theme.HINT)

    # -- the title block, at the width General is set to ----------------
    #
    # Forty millimetres is forty pixels here, and nothing in it may run out
    # over the drawing or over the line beneath it. So each line is laid
    # under the one before by asking the canvas how tall that one came out,
    # wrapped to the strip: a long drawing title takes two lines and pushes
    # the date down, rather than printing through it.
    left = SHEET_MM_W - block_mm
    box_edge = (left, 0.5, SHEET_MM_W - 0.5, SHEET_MM_H - 0.5)
    paper.create_rectangle(
        x(box_edge[0]),
        x(box_edge[1]),
        x(box_edge[2]),
        x(box_edge[3]),
        fill="#FBFBF9",
        outline=theme.LINE,
    )
    inner = x(left + 3.5)
    room = x(block_mm - 7.0)

    def stacked(top: float, text: str, size: int, colour: str, *, bold: bool = False) -> float:
        """One line of the block, under the last. Returns where it ended.

        Wrapped to the strip, and set a point smaller if that is what it
        takes for its longest word to fit: Tk breaks a word that will not,
        and "Apartment" over "s" is not a drawing title.
        """
        while size > 4 and max(_wide(paper, word, size, bold) for word in text.split()) > room:
            size -= 1
        item = paper.create_text(
            inner,
            top,
            text=text,
            anchor="nw",
            fill=colour,
            width=room,
            font=_face(size, bold),
        )
        return float(paper.bbox(item)[3])

    def ruled(at: float) -> None:
        paper.create_line(inner, at, inner + room, at, fill=theme.LINE)

    foot = stacked(x(5), PRODUCT.upper(), 5, theme.INK, bold=True)
    ruled(foot + 2)
    foot = stacked(foot + 5, sheet.kind, 5, theme.INK)
    if timed:
        foot = stacked(foot + 1, f"{sheet.day} {sheet.time}", 5, theme.HINT)
    elif sheet.day:
        foot = stacked(foot + 1, sheet.day, 5, theme.HINT)
    # The notes and revisions, which at this size are rules on paper too.
    line = max(foot + 6, x(62))
    step = 0
    while line < x(140):
        paper.create_line(inner, line, inner + room - (step % 3) * x(6), line, fill="#E7E6E2")
        line += x(6)
        step += 1
    ruled(x(146))
    # The scale the run will place the drawings at, not a number from the
    # schematic: a reader checks the block for exactly this.
    stacked(x(149), sheet.scale or "no scale", 5, theme.HINT)
    ruled(x(163))
    paper.create_text(
        inner,
        x(SHEET_MM_H - 9),
        text=sheet.number,
        anchor="sw",
        fill=theme.BLUE_DEEP,
        font=(theme.FACE, 9, "bold"),
    )


#: The blocks around the site in the context model, as ``(x0, y0, x1, y1,
#: height)`` in tens of metres from the site's centre, seen from the
#: south-east so the site's front is the near face.
MODEL_BLOCKS = (
    (-9.0, -9.0, -5.5, -5.0, 1.2),
    (-3.5, -9.5, 1.5, -6.5, 0.9),
    (3.5, -9.0, 8.5, -5.5, 1.6),
    (-9.5, -2.5, -6.0, 2.5, 0.8),
    (5.5, -2.0, 9.5, 3.0, 2.2),
    (-9.0, 4.5, -4.5, 9.0, 1.0),
    (-2.0, 5.5, 2.5, 9.5, 1.4),
    (4.5, 5.0, 9.0, 9.0, 0.7),
)
#: The site itself, and the envelope the future model draws on its neighbours.
MODEL_SITE = (-2.5, -2.5, 2.5, 2.5, 2.4)


def draw_model(paper: tk.Canvas, sheet: Sheet, width: int, height: int) -> None:
    """A model, drawn as the geometry: the ground within the radius, the
    blocks on it, the site among them -- and no paper, because the run makes
    no sheet of this. Isometric, from the south-east, which is the corner
    every icon in the set is seen from.

    The future model is the same neighbourhood with the envelopes the
    controls allow drawn over the lots within reach, taller and hollow, so
    the eye reads "what could stand here" rather than "what does".
    """
    future = sheet.kind == FUTURE_MODEL
    facade = sheet.kind == FACADE_MODEL
    # The hover edge, invisible at rest: the item the panel turns blue.
    paper.create_rectangle(0, 0, width - 1, height - 1, fill="", outline="", tags="edge")
    mid_x, mid_y, k = width * 0.5, height * 0.40, width / 34.0

    def at(x: float, y: float, z: float) -> tuple[float, float]:
        return (mid_x + (x - y) * 0.866 * k, mid_y + (x + y) * 0.5 * k - z * k)

    def face(
        points: Sequence[tuple[float, float, float]],
        fill: str,
        outline: str,
        dash: tuple[int, ...] = (),
    ) -> None:
        flat: list[float] = []
        for x, y, z in points:
            flat += at(x, y, z)
        paper.create_polygon(flat, fill=fill, outline=outline, dash=dash)

    def block(
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        tall: float,
        tints: tuple[str, str, str],
        outline: str,
        dash: tuple[int, ...] = (),
    ) -> None:
        # The two faces towards the viewer, then the top over them.
        face(((x0, y1, 0), (x1, y1, 0), (x1, y1, tall), (x0, y1, tall)), tints[1], outline, dash)
        face(((x1, y0, 0), (x1, y1, 0), (x1, y1, tall), (x1, y0, tall)), tints[2], outline, dash)
        face(
            ((x0, y0, tall), (x1, y0, tall), (x1, y1, tall), (x0, y1, tall)),
            tints[0],
            outline,
            dash,
        )

    # -- the ground, with its contours ----------------------------------
    reach = 11.5
    face(
        ((-reach, -reach, 0), (reach, -reach, 0), (reach, reach, 0), (-reach, reach, 0)),
        "#EEF0E8",
        SHADOW_GREY,
    )
    for level, wobble in ((-7.0, 1.2), (-3.5, 0.6), (4.0, -0.8), (8.0, 0.4)):
        points: list[float] = []
        for step in range(0, 13):
            x = -reach + step * (2 * reach / 12)
            y = level + wobble * math.sin(step * 0.9) - 0.15 * x
            points += at(x, y, 0)
        paper.create_line(points, fill="#CBD0BE", smooth=True)
    # The radius the data is fetched for, drawn on the ground.
    ring: list[float] = []
    for step in range(48):
        angle = math.tau * step / 48
        ring += at(math.cos(angle) * reach * 0.92, math.sin(angle) * reach * 0.92, 0)
    paper.create_polygon(ring, fill="", outline=theme.BLUE, dash=(4, 3), smooth=True)

    # -- the blocks, far to near ---------------------------------------
    grey = ("#F4F3EE", "#C6C5BE", "#DEDDD6")
    blue = (theme.BLUE_TINT, "#9DBDEB", "#C3D7F5")
    # Painter's order: what is further from the viewer -- smaller x + y --
    # is drawn first, and the site takes its turn among the blocks.
    standing = [(*block_, grey, theme.INK) for block_ in MODEL_BLOCKS] + [
        (*MODEL_SITE, blue, theme.BLUE)
    ]
    for x0, y0, x1, y1, tall, tints, edge in sorted(standing, key=lambda b: b[0] + b[1]):
        if facade and edge is theme.BLUE:
            # The building itself, its two visible faces striped by hours of
            # sun from the sunny end to the shaded one -- which is the skin
            # the study builds -- and the sun over it, because the bands
            # are about the sun.
            bands = ("#EBC27C", "#F6E2BE", "#FBF0DA", "#E7E6E2")
            for index, tint in enumerate(bands):
                along = (x1 - x0) / len(bands)
                face(
                    (
                        (x0 + along * index, y1, 0),
                        (x0 + along * (index + 1), y1, 0),
                        (x0 + along * (index + 1), y1, tall),
                        (x0 + along * index, y1, tall),
                    ),
                    tint,
                    "",
                )
                across = (y1 - y0) / len(bands)
                face(
                    (
                        (x1, y0 + across * index, 0),
                        (x1, y0 + across * (index + 1), 0),
                        (x1, y0 + across * (index + 1), tall),
                        (x1, y0 + across * index, tall),
                    ),
                    bands[-1 - index],
                    "",
                )
            block(x0, y0, x1, y1, tall, ("#F6E2BE", "", ""), theme.SUN)
            sun_x, sun_y = at(x1 + 2.5, y0 - 4.0, tall + 2.5)
            paper.create_oval(
                sun_x - 7, sun_y - 7, sun_x + 7, sun_y + 7, fill=theme.SUN, outline=""
            )
            continue
        block(x0, y0, x1, y1, tall, tints, edge)
        if future and edge is theme.INK and max(abs(x0 + x1), abs(y0 + y1)) / 2 < 8.0:
            block(
                x0 + 0.3,
                y0 + 0.3,
                x1 - 0.3,
                y1 - 0.3,
                tall + 1.6,
                ("", "", ""),
                theme.BLUE,
                dash=(3, 2),
            )

    # -- what it is ----------------------------------------------------
    #
    # Named first, like a sheet; then the day or the reach, and what the
    # geometry is, in a line -- not what it is not.
    paper.create_text(
        10,
        height * 0.875,
        text=sheet.kind.upper(),
        anchor="w",
        fill=theme.INK,
        font=_face(10, True),
    )
    if facade:
        what = "the building's skin, banded by hours of sun"
    elif future:
        what = "the envelopes the controls allow around the site"
    else:
        what = "terrain and neighbours, in 3D"
    line = f"{sheet.day} \u00b7 {what}" if sheet.day else what
    paper.create_text(
        10, height * 0.935, text=line, anchor="w", fill=theme.BODY, font=_face(7, False)
    )


def _draw_drawing(
    paper: tk.Canvas, study: str, drawing: Drawing, frame: tuple[float, float, float, float]
) -> None:
    """One drawing, fitted into ``frame`` -- canvas pixels -- the way
    ``FRAME_MM`` sits on a full sheet.

    Each study puts a different thing on its sheets, so each is drawn as
    that thing. A shadow under a site-analysis sheet, or under a view taken
    from the sun -- where by construction there are no shadows to see -- is
    a miniature of something the run will not make.
    """
    fx0, fy0, fx1, fy1 = frame
    frame_w, frame_h = FRAME_MM[2] - FRAME_MM[0], FRAME_MM[3] - FRAME_MM[1]
    k = min((fx1 - fx0) / frame_w, (fy1 - fy0) / frame_h)
    ox = fx0 + ((fx1 - fx0) - frame_w * k) / 2 - FRAME_MM[0] * k
    oy = fy0 + ((fy1 - fy0) - frame_h * k) / 2 - FRAME_MM[1] * k

    def px(mm: float) -> float:
        return ox + mm * k

    def py(mm: float) -> float:
        return oy + mm * k

    def box(
        mm: tuple[float, float, float, float],
        *,
        fill: str = "",
        outline: str = "",
        dash: tuple[int, ...] = (),
        width: float = 1.0,
    ) -> None:
        paper.create_rectangle(
            px(mm[0]),
            py(mm[1]),
            px(mm[2]),
            py(mm[3]),
            fill=fill,
            outline=outline,
            dash=dash,
            width=width,
        )

    def poly(points: Sequence[tuple[float, float]], *, fill: str, outline: str) -> None:
        flat: list[float] = []
        for point_x, point_y in points:
            flat += [px(point_x), py(point_y)]
        paper.create_polygon(flat, fill=fill, outline=outline)

    def line(x0: float, y0: float, x1: float, y1: float, fill: str) -> None:
        paper.create_line(px(x0), py(y0), px(x1), py(y1), fill=fill)

    def shadow() -> None:
        """The block's shadow at this sun, as a hull of the block and its
        shifted copy. Exact for the sun even though the block is schematic."""
        reach, bearing = drawing.reach, drawing.bearing
        if reach is None or bearing is None:
            return
        far = reach * BLOCK_HEIGHT_M
        shift = (
            math.sin(math.radians(bearing)) * far,
            -math.cos(math.radians(bearing)) * far,
        )
        corners = [
            (corner_x + dx, corner_y + dy)
            for corner_x in (BLOCK_MM[0], BLOCK_MM[2])
            for corner_y in (BLOCK_MM[1], BLOCK_MM[3])
            for dx, dy in ((0.0, 0.0), shift)
        ]
        poly(_hull(corners), fill="#C7C6C1", outline="")

    def yard() -> None:
        """The courtyard, gridded the way the study samples it."""
        court = (BLOCK_MM[0] - 14, BLOCK_MM[1] + 4, BLOCK_MM[2] + 14, BLOCK_MM[3] + 16)
        box(court, fill="#F6E2BE", outline=theme.SUN)
        for step in range(1, 6):
            along = court[0] + (court[2] - court[0]) * step / 6
            line(along, court[1], along, court[3], "#E9C98F")
        for step in range(1, 4):
            down = court[1] + (court[3] - court[1]) * step / 4
            line(court[0], down, court[2], down, "#E9C98F")

    box(SITE_MM, fill="#FCFCFA", outline=SHADOW_GREY, dash=(3, 2))
    for neighbour in NEIGHBOURS_MM:
        box(neighbour, fill="#EFEEEA", outline=SHADOW_GREY)

    kind = drawing.kind
    if kind.startswith("Apartments") and drawing.azimuth is None:
        # The whole day: the flats in their bands, most sun to least.
        tints = ("#EBC27C", "#F6E2BE", "#FBF0DA", "#F6E2BE", "#E7E6E2", "#EBC27C")
        for index, flat in enumerate(FLATS_MM):
            box(flat, fill=tints[index], outline=theme.EDGE)
    elif kind.startswith("Apartments"):
        lit = _lit_flats(drawing.azimuth)
        for index, flat in enumerate(FLATS_MM):
            box(
                flat,
                fill="#F6E2BE" if index in lit else theme.SURFACE,
                outline=theme.SUN if index in lit else theme.EDGE,
            )
    elif kind == COMMUNAL_HOURLY:
        # The space at one hour: the yard, and the shadow the block throws
        # across it -- which is what the hourly plan measures.
        yard()
        shadow()
        box(BLOCK_MM, fill=theme.BLUE_TINT, outline=theme.BLUE, width=2)
    elif kind in (COMMUNAL_AREAS, "Summary of Controls"):
        # A schedule: a heading rule, then a row per space or per control.
        table = (SITE_MM[0] + 16, SITE_MM[1] + 18, SITE_MM[2] - 16, SITE_MM[3] - 18)
        box(table, fill=theme.SURFACE, outline=theme.EDGE)
        line(table[0], table[1] + 12, table[2], table[1] + 12, theme.INK)
        row = table[1] + 24
        while row < table[3] - 4:
            line(table[0] + 4, row, table[2] - 4, row, theme.LINE)
            row += 12
        line(
            table[0] + (table[2] - table[0]) * 0.55,
            table[1],
            table[0] + (table[2] - table[0]) * 0.55,
            table[3],
            theme.LINE,
        )
    elif kind == "Context Analysis":
        # The neighbourhood: the site in the middle of the radius the data
        # is fetched for, the blocks around it, and the streets between.
        mid_x, mid_y = (SITE_MM[0] + SITE_MM[2]) / 2, (SITE_MM[1] + SITE_MM[3]) / 2
        paper.create_oval(
            px(mid_x - 62),
            py(mid_y - 62),
            px(mid_x + 62),
            py(mid_y + 62),
            outline=theme.BLUE,
            dash=(4, 3),
        )
        for street in (mid_y - 28, mid_y + 32):
            paper.create_line(
                px(SITE_MM[0] - 12),
                py(street),
                px(SITE_MM[2] + 12),
                py(street),
                fill="#D3D3D0",
                width=3,
            )
        paper.create_line(
            px(mid_x + 44),
            py(SITE_MM[1] - 12),
            px(mid_x + 44),
            py(SITE_MM[3] + 12),
            fill="#D3D3D0",
            width=3,
        )
        for block in CONTEXT_MM:
            box(block, fill="#E4E3DE", outline=SHADOW_GREY)
        box(BLOCK_MM, fill=theme.BLUE_TINT, outline=theme.BLUE, width=2)
    elif kind == "Site Analysis":
        # The site itself: its boundary, the setbacks dashed inside it, the
        # frontage dimensioned, and the pin where the address lands.
        lot = (BLOCK_MM[0] - 22, BLOCK_MM[1] - 16, BLOCK_MM[2] + 22, BLOCK_MM[3] + 16)
        box(lot, fill="#E8F0FC", outline=theme.BLUE, width=2)
        box(BLOCK_MM, fill="", outline=theme.BLUE, dash=(4, 2))
        line(lot[0], lot[1] - 7, lot[2], lot[1] - 7, theme.HINT)
        for end in (lot[0], lot[2]):
            line(end, lot[1] - 10, end, lot[1] - 4, theme.HINT)
        pin_x, pin_y = (BLOCK_MM[0] + BLOCK_MM[2]) / 2, BLOCK_MM[1] + 12
        poly(
            ((pin_x - 5, pin_y - 7), (pin_x + 5, pin_y - 7), (pin_x, pin_y + 6)),
            fill=theme.BLUE,
            outline="",
        )
        paper.create_oval(
            px(pin_x - 6), py(pin_y - 15), px(pin_x + 6), py(pin_y - 3), fill=theme.BLUE, outline=""
        )
        paper.create_oval(
            px(pin_x - 2.2),
            py(pin_y - 11.2),
            px(pin_x + 2.2),
            py(pin_y - 6.8),
            fill=theme.SURFACE,
            outline="",
        )
    elif kind.startswith("Communal open space"):
        yard()
    elif kind == "Facade bands":
        # The skin in its bands of sun hours, least to most.
        bands = ("#E7E6E2", "#FBF0DA", "#F6E2BE", "#EBC27C")
        wide = (BLOCK_MM[2] - BLOCK_MM[0]) / len(bands)
        for index, tint in enumerate(bands):
            box(
                (
                    BLOCK_MM[0] + wide * index,
                    BLOCK_MM[1],
                    BLOCK_MM[0] + wide * (index + 1),
                    BLOCK_MM[3],
                ),
                fill=tint,
                outline="",
            )
        box(BLOCK_MM, fill="", outline=theme.INK)
    elif kind == "Sun view":
        # The massing as the sun sees it: three faces and no shadow, because
        # from where the light comes from there is none to see.
        mid_x, top = (BLOCK_MM[0] + BLOCK_MM[2]) / 2, BLOCK_MM[1] - 12
        half, rise, tall = 34.0, 17.0, 30.0
        waist = top + rise * 2
        for points, tint in (
            (
                (
                    (mid_x, top),
                    (mid_x + half, top + rise),
                    (mid_x, waist),
                    (mid_x - half, top + rise),
                ),
                "#F4F3EE",
            ),
            (
                (
                    (mid_x - half, top + rise),
                    (mid_x, waist),
                    (mid_x, waist + tall),
                    (mid_x - half, top + rise + tall),
                ),
                "#C6C5BE",
            ),
            (
                (
                    (mid_x + half, top + rise),
                    (mid_x, waist),
                    (mid_x, waist + tall),
                    (mid_x + half, top + rise + tall),
                ),
                "#DEDDD6",
            ),
        ):
            poly(points, fill=tint, outline=theme.INK)
    elif study == "Site analysis":
        # The site itself, outlined, with the address dropped on it.
        box(BLOCK_MM, fill="#E8F0FC", outline=theme.BLUE, dash=(4, 2))
        pin_x, pin_y = (BLOCK_MM[0] + BLOCK_MM[2]) / 2, BLOCK_MM[1] + 12
        poly(
            ((pin_x - 5, pin_y - 7), (pin_x + 5, pin_y - 7), (pin_x, pin_y + 6)),
            fill=theme.BLUE,
            outline="",
        )
        paper.create_oval(
            px(pin_x - 6), py(pin_y - 15), px(pin_x + 6), py(pin_y - 3), fill=theme.BLUE, outline=""
        )
        paper.create_oval(
            px(pin_x - 2.2),
            py(pin_y - 11.2),
            px(pin_x + 2.2),
            py(pin_y - 6.8),
            fill=theme.SURFACE,
            outline="",
        )
    else:
        shadow()
        box(BLOCK_MM, fill=theme.BLUE_TINT, outline=theme.BLUE, width=2)


def _face(size: int, bold: bool) -> tuple[str, int] | tuple[str, int, str]:
    """The window's typeface at that size, as Tk takes a font on a canvas."""
    return (theme.FACE, size, "bold") if bold else (theme.FACE, size)


#: How wide a word is, in pixels, by size and weight. Kept because thirty
#: sheets ask about the same five words on every keystroke, and kept as
#: numbers rather than as fonts because a font belongs to the interpreter
#: that made it and this outlives any one of them.
_WIDTHS: dict[tuple[int, bool, str], int] = {}


def _wide(widget: tk.Misc, word: str, size: int, bold: bool) -> int:
    key = (size, bold, word)
    if key not in _WIDTHS:
        face = tkfont.Font(
            root=widget, family=theme.FACE, size=size, weight="bold" if bold else "normal"
        )
        _WIDTHS[key] = int(face.measure(word))
    return _WIDTHS[key]


def _lit_flats(azimuth: float | None) -> set[int]:
    """Which flats the sun is in, by where it is.

    Schematic, and honest about being so: the real answer is what the study
    goes and measures. What it gets right is that three hours of one day are
    three different drawings, because the sun is in three different places.
    """
    if azimuth is None:
        return set()
    middle_x = sum(flat[0] + flat[2] for flat in FLATS_MM) / (2 * len(FLATS_MM))
    middle_y = sum(flat[1] + flat[3] for flat in FLATS_MM) / (2 * len(FLATS_MM))
    reach = 54.0
    towards = (
        middle_x + math.sin(math.radians(azimuth)) * reach,
        middle_y - math.cos(math.radians(azimuth)) * reach,
    )
    order = sorted(
        range(len(FLATS_MM)),
        key=lambda index: math.hypot(
            (FLATS_MM[index][0] + FLATS_MM[index][2]) / 2 - towards[0],
            (FLATS_MM[index][1] + FLATS_MM[index][3]) / 2 - towards[1],
        ),
    )
    return set(order[:3])


@dataclass
class Job:
    """One command to run, and what to call it while it runs."""

    label: str
    args: list[str] = field(default_factory=list)


class Window:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        #: The assessment days, by short name, ticked or not. Built before
        #: the sections are, because the Model tab fills it as it is drawn.
        self.days: dict[str, tk.BooleanVar] = {}
        #: Each study's tick, which is also the header of its block. Kept
        #: so `_sync` can grey the blocks that are switched off: a study
        #: nobody has turned on should not look like a live form.
        self.study_bars: dict[str, ttk.Checkbutton] = {}
        #: And the box each one heads, with the line at the right of its
        #: header that says what the tick is worth.
        self.study_boxes: dict[str, tuple[ttk.Frame, ttk.Label]] = {}
        #: Every row of toggle buttons, so ``_sync`` can repaint them when a
        #: variable is set without a press -- by a preset, or by a test.
        self.toggle_rows: list[Toggles] = []
        self.root.title(PRODUCT)
        # Never taller than the screen. A window opened past the bottom edge
        # cannot be dragged back by its title bar, so everything below the
        # fold -- Run included -- is out of reach, which is the fault this
        # replaces. The minimum height only has to keep the strip and the run
        # bar: the settings between them scroll.
        self.root.minsize(880, 620)
        # Taken off the content rather than guessed. A sheet in the panel is
        # 300 px, which is A4 landscape at a size its title block can still be
        # read at; the dock is that plus its padding and its scrollbar, 336.
        # The pane beside it wants a label column, three chips and the button
        # that adds a fourth, which is 728. So the window is 1072 wide, and
        # 856 tall is the strip, a section, the info band and the run bar.
        self.root.geometry(self._on_the_screen(1072, 856))

        #: Lines from the worker thread. Tkinter is not thread-safe, so nothing
        #: touches a widget from the runner's thread: lines go through here and
        #: the UI thread drains them on a timer.
        self.incoming: queue.Queue[tuple[str, object]] = queue.Queue()

        self.options = probe.ProjectOptions()
        self.ports: list[int] = []
        self.run: Run | None = None
        self.queued: list[Job] = []
        #: Everything a run has said, in order. The window shows the newest
        #: line of it and no more, but a failure has to be readable after the
        #: fact, so the transcript is kept rather than drawn.
        self.lines: list[str] = []

        self._build()
        #: What the window opens with when nothing has been saved. Taken
        #: before any saved settings land on top of it, so Forget has
        #: something to go back to that is not "whatever was on screen".
        self.factory = self.settings()
        self._restore()
        self.refresh()
        self.root.after(80, self._drain)

    def _on_the_screen(self, want_wide: int, want_tall: int) -> str:
        """A size that fits the display this window opened on.

        The margins are for the task bar and the title bar, neither of which
        Tk reports: ``winfo_screenheight`` is the whole panel, borders and
        all.
        """
        wide = min(want_wide, self.root.winfo_screenwidth() - 40)
        tall = min(want_tall, self.root.winfo_screenheight() - 120)
        return f"{max(wide, 880)}x{max(tall, 620)}"

    # -- layout ------------------------------------------------------------
    #: The six pages, and the two kinds they come in. That split is the
    #: taxonomy, and it is what six equal cards had no way of saying: *set up*
    #: is what the job is, answered once and never run; *what it draws* is
    #: what comes out, one page per output, each with a tick that Run obeys.
    #:
    #: Only the second kind can be queued, which is the whole reason the
    #: strip is grouped rather than flat: a colleague looking for the queued
    #: mark now knows the two pages that can never carry one.
    #:
    #: "Solar tools" is not a page here and never was an output -- it was a
    #: container holding four of them, which meant four of the six things
    #: this program does were invisible until somebody opened it.
    GENERAL = "General"
    MODEL = "Model"
    SITE = "Site analysis"
    DIAGRAMS = "Solar analysis"
    SHADOWS = "Shadow diagram"
    EYE = "Sun views"

    #: The two kinds, in strip order, under the word that names each. Two
    #: words of chrome, and they are the only text in the strip that is not
    #: the name of a page.
    SET_UP = "SET UP"
    DRAWS = "WHAT IT DRAWS"
    GROUPS: ClassVar[tuple[tuple[str, tuple[str, ...]], ...]] = (
        (SET_UP, (GENERAL, MODEL)),
        (DRAWS, (SITE, DIAGRAMS, SHADOWS, EYE)),
    )

    #: What each tab says when hovered. The tab carries a drawing at 32 px and
    #: a name, and nothing else -- so the sentence that would otherwise sit
    #: under the label lives here, where it costs no room at all.
    SECTION_BLURB: ClassVar[dict[str, str]] = {
        GENERAL: (
            "The sheet every output lands on: the master and its title block, "
            "the layer prefixes that file the results, the storey everything is "
            "measured from, and which days of the year the sun is put at."
        ),
        SITE: (
            "An address in; the Context and Site Analysis sheets, the Summary of "
            "Controls, and a 500 m context model of terrain, blocks and "
            "neighbours out."
        ),
        MODEL: (
            "What geometry leaves Archicad and by which route: the layer "
            "combination it starts from, what is forced in, what the "
            "neighbours are, and what is kept off the drawings."
        ),
        DIAGRAMS: (
            "Hours of direct sun. Three studies: the facade in bands at massing "
            "stage, the apartments assessed against the ADG, and communal open "
            "space."
        ),
        SHADOWS: (
            "Shadows cast by each massing, hour by hour, drawn from published "
            "views — one sheet per hour per day."
        ),
        EYE: ("3D documents aimed straight down the sun, and the sheets they are dealt onto."),
    }
    #: The facade study lives in the Solar analysis section now; the name
    #: stays for the settings files and tests that knew it as a tab.
    FACADE = DIAGRAMS

    def _build(self) -> None:
        # Before any widget exists: ttk reads a style when a widget is made,
        # so restyling afterwards leaves whatever was built first looking like
        # the old theme.
        theme.apply(self.root)
        self.root.configure(background=theme.CHROME)

        wheel_reaches_the_pointer(self.root)

        # The bottom of the window is built first and packed to the bottom,
        # so it stays put while the settings above it change tab and scroll.
        # Run has to be findable without hunting through sections, and the one
        # line a run has to say about itself has to stay where it was put.
        base = ttk.Frame(self.root, style="Chrome.TFrame", padding=(PAD, 6, PAD, PAD))
        base.pack(side="bottom", fill="x")
        base.columnconfigure(0, weight=1)
        # The contours: a one-pixel rule above the run bar, and another above
        # the band, so the three regions across the bottom read as three.
        ttk.Frame(self.root, style="Rule.TFrame", height=1).pack(side="bottom", fill="x")

        # Above it, the one strip that explains whatever is under the pointer.
        # Packed to the bottom too, so it sits between the settings and Run and
        # cannot be scrolled away from either.
        self.info = InfoBand(self.root)
        self.info.pack(side="bottom", fill="x")
        ttk.Frame(self.root, style="Rule.TFrame", height=1).pack(side="bottom", fill="x")
        Tooltip.band = self.info

        self._project_picker()

        # The working area is two panes. The section you are filling in, and
        # every sheet the run will make -- which belongs to the run and not to
        # a page, so it sits outside the tabs and stays put while they change.
        middle = ttk.Frame(self.root, style="Chrome.TFrame")
        middle.pack(side="top", fill="both", expand=True)
        self.dock = Dock(middle, on_pick=self._sheet_under)
        #: Whether the window is too narrow to hold both panes. Crossing the
        #: line folds the panel or brings it back; in between, the chevron
        #: is the user's and is left alone.
        self._narrow = False
        self.root.bind("<Configure>", self._fit, add="+")
        self.dock.pack(side="right", fill="y")
        # The contour between the page and the dock: one pixel, and thin.
        ttk.Frame(middle, style="Rule.TFrame", width=1).pack(side="right", fill="y")
        self.pane = ttk.Frame(middle, style="Chrome.TFrame")
        self.pane.pack(side="left", fill="both", expand=True)

        self._sections()
        self._controls(base)
        # What is typed changes what a run will make as surely as what is
        # ticked, so the panel of sheets hears about keystrokes too.
        for typed in (self.communal_hours, self.year, self.custom_day):
            typed.bind("<KeyRelease>", lambda _event: self._sync(), add="+")
        for chosen in (self.adg_subset, self.shadow_subset):
            chosen.bind("<<ComboboxSelected>>", lambda _event: self._sync(), add="+")
        self._sync()

    def _project_picker(self) -> None:
        """Which Archicad, above the tabs and belonging to none of them.

        Every list in every section is read out of the chosen project and
        every study runs against it, so it is not a setting of one output. It
        also has to stay visible while a section is being filled in: a
        colleague naming zones for the diagrams should not have to leave the
        page to see which project they are naming them in.
        """
        top = ttk.Frame(self.root, style="Chrome.TFrame", padding=(PAD, PAD, PAD, 2))
        top.pack(side="top", fill="x")
        top.columnconfigure(1, weight=1)
        row = 0

        # Listed, never assumed: each instance gets its own port, so the
        # default is right only for whichever started first, and two projects
        # open is the ordinary case in an office.
        label = ttk.Label(top, text="Archicad", style="Chrome.TLabel")
        label.grid(row=row, column=0, sticky="w")
        picker = ttk.Frame(top, style="Chrome.TFrame")
        picker.grid(row=row, column=1, sticky="ew", pady=2)
        picker.columnconfigure(0, weight=1)
        self.instance = ttk.Combobox(picker, state="readonly", values=[], style="Chrome.TCombobox")
        self.instance.grid(row=0, column=0, sticky="ew")
        self.instance.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        rescan = ttk.Button(
            picker,
            text="Refresh",
            style="Chrome.TButton",
            command=self.refresh,
            width=11,
            **icons.button_options("refresh"),
        )
        rescan.grid(row=0, column=1, padx=(6, 0))
        Tooltip(
            rescan,
            "Looks again for running Archicads and re-reads the chosen "
            "project. Press it after opening a project, or after adding a "
            "layer or a Layout Book subset that should appear in the lists "
            "in the sections below.",
        )
        row += 1
        # No line under this one. What it needs to say -- which project, and
        # check it if two are open -- the hover says at length, and the status
        # line below already reports what was read out of whichever is chosen.
        for target in (label, self.instance):
            Tooltip(
                target,
                "Archicad gives every open instance its own port, so there is no "
                "single right one to guess at. The study reads and draws in "
                "whichever project is chosen here — pick the wrong one and it "
                "measures the wrong building and says nothing. Press Refresh "
                "after opening or closing a project.",
            )

        self.status = ttk.Label(
            top, text="", style="ChromeHint.TLabel", wraplength=620, justify="left"
        )
        self.status.grid(row=row, column=1, sticky="w", pady=(0, 4))
        # The contour under the project bar: which Archicad is one question,
        # asked once, and everything below it is the study.
        ttk.Frame(self.root, style="Rule.TFrame", height=1).pack(side="top", fill="x")

    def _sections(self) -> None:
        """One page per output, reached from a strip of tabs across the top.

        The launcher of cards this replaces was right about one thing and
        wrong about everything else. Right: a drawing big enough to recognise
        beats a 20 px smudge beside a word, and six of them in view beats a
        row of small words. Wrong in three ways that a strip fixes at once.

        It cost a click to reach any page and two to reach the next one,
        because the way from one tool to another ran through the front door.

        It had nowhere to say which page you were on, since the cards were
        gone by the time you were on one -- so the one thing a colleague looks
        for first, *where am I*, had to be read off a breadcrumb that was
        itself the only thing left of the navigation.

        And its single mark, the blue tint, was spent on *queued*, which left
        *chosen* with no mark at all. One colour cannot carry two facts.

        The strip keeps the drawings -- 32 px, over the name rather than
        beside it, which is what makes the size free -- and gets all three
        back. Every page is one click from every other. The open tab is white
        and capped in blue, joined to the page beneath it, and stays on screen
        saying so. Queued is a separate mark on a separate axis: the name goes
        blue and takes a dot. A tab can be open, queued, both or neither, and
        all four read without being read.
        """
        #: The sections, in strip order, the two kinds flattened into one
        #: list. The kinds are drawn by ``_strip``; everything else -- the
        #: settings file, the studies, the wheel, the tests -- wants them flat.
        self.titles: list[str] = [title for _kind, group in self.GROUPS for title in group]
        #: The four that used to live inside Solar tools. Kept because
        #: ``_studies`` names the section a study belongs to and the settings
        #: file remembers one of these strings; nothing navigates by it now.
        self.solar_titles: list[str] = [self.MODEL, self.DIAGRAMS, self.SHADOWS, self.EYE]

        #: Every pane in title order, and the same panes by title. The list is
        #: what the wheel and the tests reach for; the map is what showing one
        #: needs.
        self.panes: list[Scroller] = []
        self.pane_of: dict[str, Scroller] = {}
        #: The tab buttons. Which one is open is in the style each wears: the
        #: open tab's face is the page's white under a blue cap, rounded where
        #: it meets nothing and square where it meets the page.
        self.tabs: dict[str, ttk.Button] = {}
        #: Which section is showing. Never empty: there is no state of this
        #: window with no page open, which is what the launcher was.
        self.showing = self.GENERAL

        # Packed before the stack, so it lands above it.
        self._strip()

        # The page is a card of its own on the chrome -- the lighter grey,
        # one thin edge, rounded -- a gap below the strip. The sections are
        # laid out inside it, inset past its corners.
        self.stack = ttk.Frame(self.pane, style="PageCard.TFrame", padding=6)
        self.stack.pack(side="top", fill="both", expand=True, padx=(PAD, PAD), pady=(6, PAD))

        builders = {
            self.GENERAL: self._general,
            self.SITE: self._site,
            self.MODEL: self._model,
            self.DIAGRAMS: self._diagrams,
            self.SHADOWS: self._shadows,
            self.EYE: self._sun_eyes,
        }
        for title in self.titles:
            builders[title](self._section(title))
        self._show_section(self.GENERAL)

    def _strip(self) -> None:
        """The six tabs, in their two kinds, across the top of the window.

        Grouped rather than flat because the taxonomy is the thing six equal
        cards could not say: two of these pages set the job up and four of
        them draw something, and only the four can be queued. A colleague
        hunting for the queued mark can rule out two tabs without looking.
        """
        strip = ttk.Frame(self.pane, style="Chrome.TFrame", padding=(PAD, 4, PAD, 0))
        strip.pack(side="top", fill="x")

        column = 0
        for _kind, group in self.GROUPS:
            if column:
                # Between the kinds, a rule rather than a wider gap: at this
                # size a gap reads as two tabs that happen to sit apart, and
                # the split is the whole point of the arrangement. The rule
                # says it alone; the words that used to sit over each group
                # were a second way of saying it.
                ttk.Separator(strip, orient="vertical").grid(
                    row=0, column=column, sticky="ns", padx=12, pady=(6, 6)
                )
                column += 1
            for title in group:
                self._tab(strip, title, column)
                column += 1
        # The strip ends where the tabs do; the rest of the row is chrome.
        strip.columnconfigure(column, weight=1)

    def _tab(self, strip: ttk.Frame, title: str, column: int) -> None:
        """One tab: a drawing at 32 px and the page's name under it.

        The mark that means *open* used to be three pixels of blue frame sat
        on top of a square button, because ttk has no way to give one edge of
        a widget its own colour. It is in the tab's face now -- the page's
        white under a blue cap, rounded where it meets nothing and square
        where it meets the page -- which is the same fact drawn as one shape
        instead of two, and still a thing the tint used for *queued* can never
        be confused with.
        """
        tab = ttk.Button(
            strip,
            style="Tab.TButton",
            text=title,
            command=partial(self._show_section, title),
            **icons.tab_options(title, 32),
        )
        tab.grid(row=0, column=column, sticky="nsew", padx=(0, 4))
        Tooltip(tab, self.SECTION_BLURB[title])
        self.tabs[title] = tab

    def _paint_tabs(self) -> None:
        """Say which tab is open and which tabs will run, in two ways that
        cannot be read as each other.

        Open is the white tab under the blue rule. Queued is the blue name and
        the dot after it. Two marks on two axes, so a tab that is both says
        both -- where the launcher had one tint that had to mean both and
        therefore meant neither.
        """
        running = {where for _name, tick, where in self._studies() if tick.get()}
        styles = {
            (False, False): "Tab.TButton",
            (True, False): "TabOpen.TButton",
            (False, True): "TabQueued.TButton",
            (True, True): "TabOpenQueued.TButton",
        }
        for title, tab in self.tabs.items():
            open_here = title == self.showing
            queued_here = title in running
            tab.configure(
                style=styles[(open_here, queued_here)],
                text=f"{title} •" if queued_here else title,
            )

    def _section(self, title: str) -> ttk.Frame:
        """One page, and the frame its settings are built into.

        Each scrolls on its own rather than all of them inside one scroller,
        because they are not the same length: Solar analysis asks about three
        studies and is three times General. One scroller would size itself to
        the longest and leave every short page with a bar that moves nothing.

        Built now and shown later. Every page exists from the moment the
        window opens, so reading the project fills all six at once and moving
        between them costs nothing.
        """
        pane = Scroller(self.stack, ground=theme.PAGE)
        self.panes.append(pane)
        self.pane_of[title] = pane
        # The page: light grey, with the cards sixteen pixels in from its
        # edge on the left and eight on the right, where the bar runs.
        frame = ttk.Frame(pane.content, style="Page.TFrame", padding=(PAD, 10, PAD, 12))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        return frame

    def _general(self, frame: ttk.Frame) -> None:
        """What every tool that makes a sheet needs, asked once.

        The master, the title block, the numbering the results file
        themselves under, the year and how long Archicad is waited on are
        the same for a site sheet as for a shadow sheet. The title-block
        width lived in the sun views' tab and the export settings lived
        here; both are now where every tool that reads them can find them
        -- the export settings under Solar tools, because only the solar
        tools export a model.
        """
        outer = frame
        frame, row = self._panel(outer, 0, title="Layouts and title block"), 0
        self.master, row = self._combo(
            frame,
            row,
            "Master layout",
            "Title block the layouts are built on.",
            "A no-scale master is the right one: the drawings are shrunk to fit "
            "the page, so they are no longer at any stated scale and a title "
            "block claiming 1:200 would be wrong. An existing layout keeps the "
            "master it was made on — nothing in the add-on can change it — so "
            "delete old study sheets before changing this.",
        )
        self.eye_title_block, row = self._entry(
            frame,
            row,
            "Title block width (mm)",
            "100",
            "Millimetres kept clear down the right of every sheet the tools make.",
            "Archicad reports a layout's margins and nothing about its "
            "master, so drawings would otherwise tile under the title block. "
            "About 100 mm on the DA masters. Every tool that places a sheet "
            "keeps this strip clear: the site sheets, the sun views, the "
            "shadow and solar diagrams.",
        )
        self.sheets, row = self._tiles(
            frame,
            row,
            "Sheets",
            "How a tool's drawings are dealt onto layouts.",
            "The same for every solar tool: the shadow diagrams, the sun "
            "views, the apartment plans at their times and the communal "
            "plans by the hour. One layout carries every drawing of a set; "
            "two layouts split them, the first half on one and the rest on "
            "the second laid out on the same grid, so seven is four and "
            "three with one cell empty and nine is five and four; a layout "
            "per drawing gives each its full sheet. A sheet whose name no "
            "longer matches is replaced on the next run.",
        )
        self.sheets.set(self.SHEET_CHOICES[1][0])

        frame, row = self._panel(outer, 1, title="Archicad layers the results are drawn on"), 0

        # One per tool, not one for the lot. The four are four drawings read
        # by different people, and under a single number the layer list ran
        # them together with only the group word to tell them apart.
        shared_detail = (
            "So the output files itself inside the office's own numbering: on "
            "a project whose layer groups run 00 to 13, '14 |' gives "
            "'14 | Solar Analysis.Results' and it sorts where a reader expects. "
            "It is also how a rerun finds its own sheets to replace, so changing "
            "it leaves the last run's behind to be deleted by hand, and it "
            "cannot be emptied — an empty prefix matches every layout in the "
            "project."
        )
        self.prefix_solar, row = self._entry(
            frame,
            row,
            "Layer prefix — solar analysis",
            naming.SOLAR_PREFIX,
            "The apartment results and the facade bands.",
            shared_detail,
        )
        self.prefix_shadow, row = self._entry(
            frame,
            row,
            "Layer prefix — shadow diagram",
            naming.SHADOW_PREFIX,
            "The shadow sheets, which are about the neighbourhood rather than the apartments.",
            shared_detail,
        )
        self.prefix_sun, row = self._entry(
            frame,
            row,
            "Layer prefix — sun views",
            naming.SUN_VIEW_PREFIX,
            "The 3D documents aimed along the sun, and their sheets.",
            shared_detail,
        )
        self.prefix_site, row = self._entry(
            frame,
            row,
            "Layer prefix — site analysis",
            naming.SITE_PREFIX,
            "The site and context worksheets, and the summary of controls.",
            shared_detail,
        )
        self.prefix_context, row = self._entry(
            frame,
            row,
            "Layer group — context model",
            naming.CONTEXT_PREFIX,
            "The office's own group, where the neighbours already live.",
            "Not one of this tool's numbers: the fetched neighbours and the "
            "ground under them are the neighbourhood, not the study, so they "
            "go in the site group the template already has — '03 | Site "
            "Context.3D' on the reference project, under '03 ---- SITE' with "
            "the boundaries and the survey mesh. A layer that is already there "
            "is used rather than duplicated; give a group the project does not "
            "have, '50 |', and the layers are made there instead. Only the "
            "number is yours to choose — the wording after it is the "
            "template's.",
        )
        frame, row = self._panel(outer, 2, title="Archicad connection"), 0
        self.wait_min, row = self._entry(
            frame,
            row,
            "Archicad wait (min)",
            "30",
            "How long to let Archicad think about one command before giving up.",
            "Only the IFC export comes anywhere near it, and on a big project "
            "that export is minutes rather than seconds -- 455 MB on one "
            "mixed-use job. Too short and the run stops partway with 'Archicad "
            "did not answer', having already done the slow part, and leaves "
            "the project holding the study's layer state. Raising it costs "
            "nothing on a run that works; it only decides how long a genuinely "
            "stuck Archicad is waited on.",
        )
        frame, row = self._panel(outer, 3, title="Tables"), 0
        self.tables, row = self._folder_row(
            frame,
            row,
            "Tables",
            "The folder every table is written into. Blank writes none.",
            "One place for all of them: the apartments' results as "
            f"{APARTMENTS_TABLE}, and the communal open space as "
            f"{COS_AREAS_TABLE} and the COS schedules as {COS_SCHEDULE_TABLE}. "
            "Each run that studies another day puts the day in the file's "
            "name, so the days stand side by side. Written before anything is "
            "drawn, so the numbers survive whatever Archicad does next.",
        )

    def _model(self, frame: ttk.Frame) -> None:
        """The model the three solar tools export: what is shown, what is
        forced on, what the neighbours are, what is kept off, and the height
        above which nothing counts. Asked once here rather than in each."""
        outer = frame
        frame, row = self._panel(outer, 0, title="Storeys measured"), 0
        self.storey_from, row = self._combo(
            frame,
            row,
            "Measure from storey",
            "The storey the building starts at. Leave empty for no lower limit.",
            "The height band, as two storeys rather than a figure in metres. "
            "A storey is a sentence about the building -- 'from the datum to "
            "the lift overrun' -- and it carries to the next project; a metre "
            "figure has to be looked up per project and is wrong invisibly "
            "when it is wrong. Measured twice: on one project a cut at 195 m "
            "read as generous and removed nothing at all, because the storey "
            "it meant sits at 49.8 m with a quarter kilometre of parked "
            "hotlink masters above it. Filled from the project when it is "
            "read.",
        )
        self.storey_to, row = self._combo(
            frame,
            row,
            "...to storey",
            "The storey the building ends at. Leave empty for no upper limit.",
            "Everything outside the two storeys is dropped before anything is "
            "measured. That is what keeps hotlinked unit-type masters out of "
            "the result: they are parked away from the building on the same "
            "layers as it, so nothing but position separates them -- above it "
            "on some projects and below the datum on others, which is why "
            "both ends are asked for. An element is kept when any part of it "
            "reaches the band, so a wall crossing either end stays whole.",
        )
        frame, row = self._panel(outer, 1, title="Days studied"), 0

        # The day and the year sit with the solar tools rather than in
        # General, because they are not general: the site drawings do not read
        # them, and a setting shown to somebody drawing a context plan is a
        # setting they have to decide not to care about.
        #
        # Days are ticked and not picked, because a study is usually asked for
        # on more than one. A council wants midwinter for the test and the
        # equinox beside it to show the year, and choosing one at a time meant
        # running the whole tool again and remembering to change the box.
        # Every ticked day runs the tools once each, and every name a run
        # makes carries its day, so the sets stand beside each other in the
        # project rather than over each other.
        days = Toggles(frame, on_change=self._sync)
        days.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.toggle_rows.append(days)
        for name, (_, title) in ASSESSMENT_DAYS.items():
            state = tk.BooleanVar(value=name == "winter")
            self.days[name] = state
            # A button with the sun at that day's height, rather than a box.
            box = days.add(state, title.split(",")[0], f"day_{name}")
            Tooltip(
                box,
                f"{title}. "
                + (
                    "The shortest day, the worst case the ADG assesses and the only "
                    "day its two-hour test means anything. Left ticked unless a "
                    "council asks otherwise."
                    if name == "winter"
                    else "Shows the year beside the midwinter case. A run on this day "
                    "carries it in every layer, view, sheet and property it makes."
                ),
            )
        row += 1
        self.custom_day, row = self._entry(
            frame,
            row,
            "Custom day",
            "",
            "Any other day, as MM-DD. Runs in addition to the ticks.",
            "For a council that asks for a date the three ticks do not cover "
            "-- the 22nd rather than the 21st, or a day named in a DCP. "
            "Written MM-DD, e.g. 07-15. It runs as well as whatever is "
            "ticked, so the usual pair plus one is three runs of each tool "
            "rather than a choice between them. The shadow diagram keeps its "
            "own list of days and does not read this.",
        )
        self.year, row = self._entry(
            frame,
            row,
            "Year",
            "2024",
            "Which year's sun positions to use.",
            "The year only shifts the sun positions slightly; it is here so a "
            "study can be repeated against the same day as an earlier report.",
        )
        frame, row = self._panel(outer, 2, title="Model export: the layers that leave Archicad"), 0
        self._caption(
            frame,
            row,
            "The layer state every solar tool exports from. Set once for the project.",
        )
        row += 1
        self.combination, row = self._combo(
            frame,
            row,
            "Layer combination",
            "The office layer combination the IFC export starts from.",
            "The translator exports what is shown, so the layer state is an "
            "input to every number this tool produces. The run sets it from "
            "this combination, forces on what the study needs over the top, "
            "and puts every layer back afterwards — so the answer does not "
            "depend on what happened to be on screen.",
        )
        self.require, row = self._picker(
            frame,
            row,
            "Layers forced visible",
            "Layers forced into the export whatever the combination says.",
            "Shared by the facade skin and the communal study, which is why "
            "it is here rather than in either. The zone layers must be in the "
            "export or neither drawing can be placed on the building — both "
            "need a Zone to line the IFC up against, and neither of this "
            "project's IFC combinations shows them. Left empty, the zone "
            "layers are added automatically.",
        )
        self.context, row = self._picker(
            frame,
            row,
            "Neighbouring buildings",
            "Layers that shade the site without being part of it.",
            "They have to be in the export or the study measures a building "
            "with nothing around it, which can only overstate its sunlight. "
            "Named by layer and not by element name because survey context "
            "usually arrives nameless — on one project all 232 neighbours are "
            "unnamed slabs. Listing them here both forces them into the export "
            "and keeps them out of the facade area, which is about the scheme "
            "and not the neighbourhood.",
        )
        self.hide, row = self._picker(
            frame,
            row,
            "Layers hidden on sheets",
            "Layers switched off on the study drawings and in the export.",
            "Grids and dimension layers usually: they are the practice's own "
            "annotation and clutter a sun study without adding to it. What "
            "counts as clutter is a decision about the drawing, so it is named "
            "here rather than guessed from layer names.",
        )

    def _facade(self, frame: ttk.Frame, row: int) -> int:
        """The facade study's rows: the 3D skin, what gets painted, how finely."""
        self.do_facade = tk.BooleanVar(value=True)
        self.do_floors = tk.BooleanVar(value=True)

        # The study's own box. Everything from here to the end of the block
        # is built inside it, by the simple means of pointing ``frame`` at it:
        # the rows beneath neither know nor care.
        outer, resume = frame, row
        frame, row = self._panel(outer, resume), 0
        facade_box = ttk.Checkbutton(
            frame,
            text="Facade (massing stage)",
            variable=self.do_facade,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Facade (massing stage)"),
        )
        self._head(frame, facade_box, FACADE_JOB)
        Tooltip(
            facade_box,
            "Paints the outside of the building with one colour per band of "
            "direct sun hours on 21 June, as real 3D elements on the tool's own "
            "layer. Switch that layer off to hide the result; nothing else in "
            "the model is touched. This measures surface area, not apartments, "
            "so it answers a massing question rather than an ADG one.",
        )
        row += 1
        self.floors_box = ttk.Checkbutton(
            frame,
            text="including floors, balcony decks and soffits",
            variable=self.do_floors,
        )
        self.floors_box.grid(row=row, column=0, columnspan=2, sticky="w", padx=(18, 0))
        Tooltip(
            self.floors_box,
            "Horizontal surfaces take far more sun than any wall. Leaving them "
            "out is not a smaller study — it is a study of the least-lit half "
            "of the building, and nothing in the result says so. Needs the slab "
            "layers named in Facade layers below.",
        )
        row += 1
        self._caption(
            frame,
            row,
            "Every surface of the building itself, banded by hours of direct sun. "
            "A massing question rather than an ADG one.",
        )
        row += 1

        self.subject, row = self._picker(
            frame,
            row,
            "Facade layers",
            "The layers that are the building being measured. Comma separated.",
            "Everything else in the model still casts shade but is not counted "
            "in the area. Without this, the facade area on a developed model "
            "includes every internal partition and balustrade. The slab layers "
            "belong here too, or there are no floors to colour.",
        )
        self.grid_m, row = self._tiles(
            frame,
            row,
            "Skin cell",
            "",
            "Finer looks better and makes many more elements — half the cell "
            "size is roughly four times the count, and this project already "
            "makes over five thousand at 0.5 m. A face narrower than one cell "
            "is not drawn at all, so a coarse setting loses thin columns.",
        )
        self.grid_m.set("0.5")
        return resume + 1

    def _diagrams(self, frame: ttk.Frame) -> None:
        """Solar analysis: hours of direct sun, on the apartments, on the
        facade, or over communal open space.

        Three studies in one section because they are one question asked
        of three things, and a job that asks for the solar analysis means
        whichever of them the model can answer -- so where the banded
        sheets are filed is asked once, at the top, for all three.
        """
        # The two settings all three studies share, in a card of their own:
        # nothing floats on the page by itself.
        outer = frame
        frame, row = self._panel(outer, 0, title="Layout Book filing, and what the plans show"), 0
        self.adg_subset, row = self._combo(
            frame,
            row,
            "Subset — ADG sheets",
            "Layout Book subset the banded sheets go into.",
            "So the sheets sit with the practice's own drawings of that kind "
            "instead of at the root of the book. The subset has to exist "
            "already — the run will not create one, because the Layout Book is "
            "the office's structure to organise — and a missing one is "
            "reported rather than invented, with the sheets left at the root.",
        )

        self.plan_kinds, row = self._tiles(
            frame,
            row,
            "Plans",
            "What the solar plans show: the day in bands, the sun at each time -- either or both.",
            "For the apartments and the communal space alike. Bands are the "
            "whole day on one plan, striped by hours of sun, which is what the "
            "ADG and a DCP ask about. Times are a plan per instant showing "
            "where the sun actually falls, which is what somebody standing "
            "there at nine in the morning asks about. Each tile switches on "
            "and off by itself; both lit is both, and a longer run. The last "
            "one lit stays lit, because no plans at all is not a plan study.",
        )

        self.do_plans = tk.BooleanVar(value=False)
        # The study's own box. Everything from here to the end of the block
        # is built inside it, by the simple means of pointing ``frame`` at it:
        # the rows beneath neither know nor care.
        resume = 1
        frame, row = self._panel(outer, resume), 0
        plans_box = ttk.Checkbutton(
            frame,
            text="Apartments",
            variable=self.do_plans,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Apartments"),
        )
        self._head(frame, plans_box, PLANS_JOB)
        Tooltip(
            plans_box,
            "The ADG assessment proper: hours of direct sun per apartment, the "
            "sun patch drawn on each floor plan, and a sheet per time of day. "
            "Needs Zones and windows in the model, so it is off by default — "
            "the facade study works on a massing that has neither.",
        )
        row += 1
        self._caption(frame, row, "Hours of sun per apartment, assessed against the ADG.")
        row += 1

        self.apartments, self.apartment_names, self.apartment_hint, row = self._zone_row(
            frame,
            row,
            "Apartment zones",
            "The layer, then which Zones on it are the dwellings.",
            "Only layers that actually carry Zones are listed, found by asking "
            "the Zones rather than by reading layer names — on this project "
            "three layers are named for zones and hold none, while an "
            "annotation layer holds 37. The names matter as much: one layer "
            "carries 15 apartments, 20 balconies and the storage cupboards, "
            "and a balcony assessed as an apartment is a flat with no living "
            "room, which fails silently and drags the percentage down.",
        )
        self.balconies, self.balcony_names, self.balcony_hint, row = self._zone_row(
            frame,
            row,
            "Balcony zones",
            "The Zones that are private open space. Usually the same layer.",
            "Half of the ADG test. Each apartment is judged on its living room "
            "and on its private open space, and the better of the two governs "
            "— so with no balconies named, every apartment is assessed on its "
            "living room alone and the result is worse than the building is. "
            "Left empty, no Zone is treated as open space at all.",
        )
        self.livable, row = self._entry(
            frame,
            row,
            "Living-room glazing",
            "",
            "Suffix marking the windows and doors of a living room, e.g. _L.",
            "The ADG counts sun into living rooms, not into bedrooms, and a "
            "Zone drawn per apartment cannot say which room is which. Where "
            "the office marks its living-room glazing with a suffix on the "
            "opening ID, that is the better answer and it is used instead of "
            "the room names. Left empty, rooms named 'Living Room' are looked "
            "for — and a project that names none is assessed on every opening, "
            "which reads as a pass it has not earned.",
        )
        self.instants, row = self._ticks_row(
            frame,
            row,
            "Plan times",
            "The times of day to draw the sun's patch on the floor for.",
            "One floor-plan drawing per time. Nine, twelve and three are the "
            "conventional set. Each one adds a set of views, so a long row "
            "makes a long run.",
            _hour_choices(clock=True),
            key=_clock_text,
            initial="09:00, 12:00, 15:00",
        )
        self.shadow_subset, row = self._combo(
            frame,
            row,
            "Subset — time-of-day sheets",
            "Layout Book subset the clock-time sheets go into.",
            "A sheet that is a time of day belongs with the practice's own, "
            "which is usually a different subset from the banded plans. Same "
            "rule as those: it has to exist already. This files the sun-patch "
            "sheets this study draws; the Shadow diagram study files its own "
            "under its own setting, because the two are different drawings "
            "and a practice does not always keep them together.",
        )

        # Out of the apartments' box, and on down the page. The boxes part
        # the studies by themselves, so the rules that used to do it are gone.
        frame, row = outer, resume + 1

        row = self._facade(frame, row)

        self.do_communal = tk.BooleanVar(value=False)
        # The study's own box. Everything from here to the end of the block
        # is built inside it, by the simple means of pointing ``frame`` at it:
        # the rows beneath neither know nor care.
        frame, row = self._panel(frame, row), 0
        communal_box = ttk.Checkbutton(
            frame,
            text="Communal open space",
            variable=self.do_communal,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Communal open space"),
        )
        self._head(frame, communal_box, COMMUNAL_JOB)
        Tooltip(
            communal_box,
            "Hours of direct sun over an outdoor area that belongs to no "
            "dwelling — a playground, a courtyard, a communal terrace — "
            "banded and drawn on the plan with a legend. Needs only a Zone "
            "drawn round the area: no apartment, no windows, no marked "
            "glazing. It reports area and share and offers no verdict, "
            "because the ruleset carries ADG 4A-1 and that is about "
            "apartments.",
        )
        row += 1
        self._caption(frame, row, "Hours of sun over a courtyard, a terrace or a playground.")
        row += 1

        self.communal, self.communal_names, self.communal_hint, row = self._zone_row(
            frame,
            row,
            "Communal zones",
            "The Zones covering communal open space.",
            "Nothing is guessed here. A communal area is not separable from a "
            "dwelling by size -- a courtyard and a big flat are the same "
            "number of square metres -- so this is left for you to name, and "
            "the chooser lists every Zone on the layer with its area. The "
            "Zone outline is the extent measured, and the plane assessed is "
            "one metre above the Zone floor.",
        )
        self.communal_window, row = self._ticks_row(
            frame,
            row,
            "Communal window",
            "The hours assessed for the communal study: press the first and the last.",
            "The ADG measures 09:00 to 15:00, and that is what the apartment "
            "study uses whatever is typed here. A council DCP may ask for a "
            "wider window for communal open space -- 08:00 to 15:00 is "
            "common -- so this moves the communal study alone. Every drawing "
            "and the areas sheet carry the window they were made with, and "
            "the run says in yellow when it is not the ruleset's.",
            _hour_choices(clock=True),
            key=_clock_text,
            span=True,
            initial="08:00-15:00",
        )
        self.communal_hours, row = self._entry(
            frame,
            row,
            "Communal threshold",
            "2",
            "Hours. Draws a second plan: what clears this, and what does not.",
            "Seven bands say how the hours spread across the space. What a "
            "DCP asks is how much of it clears the minimum, and a banded plan "
            "makes a reader do that sum by eye. This draws that split as two "
            "areas on a sheet of its own. Leave it empty for the bands alone.",
        )
        self.communal_height, row = self._entry(
            frame,
            row,
            "Communal height",
            "0",
            "Metres above the ground to assess. 0 is at ground level.",
            "The height a person's sunlight is measured at. 0 means on the "
            "ground itself, which is taken as 50 mm clear of it: the site mesh "
            "shades, and a point exactly on the ground starts every ray inside "
            "the ground and reads as permanent shade. It matters more than it "
            "sounds — on the reference project, moving from one metre to "
            "ground level took the two-hour figure from 45% to 33%, because "
            "the fall and the built form shade the surface far more than they "
            "shade a point a metre above it.",
        )
        self.communal_grid, row = self._tiles(
            frame,
            row,
            "Communal grid",
            "",
            "Half a metre reads a courtyard properly. This is separate from "
            "the ground grid on purpose: the ground is the whole site, and "
            "gridding all of it this finely costs four times the samples for "
            "an answer nobody asked of it.",
        )
        self.communal_grid.set("0.5")

    def _shadows(self, frame: ttk.Frame) -> None:
        """The shadow diagram: what already stands, and what the proposal adds.

        One row per line of the office's legend, each naming the layers that
        hold that row's massing, picked out of the open project. The geometry
        comes from the add-on's own model rather than an IFC, so nothing has
        to be published first, and each row is drawn in the legend's own
        colour with no contour.

        The rows are fixed because the legend is: three that will be there
        whatever is approved, which accumulate, and three that are being
        compared, which overlap. A row left empty is left off the sheet, and
        the others keep their colours -- they are matched by name, not dealt
        out by position.

        This replaced a page of published views (D113). A view can say more
        than a layer combination -- a renovation filter, pinned elements --
        and a project that separates its massings that way has to keep them
        on their own layers for this page to reach them.
        """
        row = 0
        self.do_shadows = tk.BooleanVar(value=False)
        # The study's own box. Everything from here to the end of the block
        # is built inside it, by the simple means of pointing ``frame`` at it:
        # the rows beneath neither know nor care.
        frame, row = self._panel(frame, row), 0
        box = ttk.Checkbutton(
            frame,
            text="Shadow diagram",
            variable=self.do_shadows,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Shadow diagram"),
        )
        self._head(frame, box, SHADOW_JOB)
        Tooltip(
            box,
            "The shadow the site casts across itself and its neighbours at "
            "each hour, drawn as fills on the plan in the legend's colours. "
            "Off by default: it needs a layer chosen for at least one legend "
            "row.",
        )
        row += 1
        self._caption(
            frame,
            row,
            "Shadows cast by each massing, hour by hour, one legend row to a set of layers.",
        )
        row += 1

        #: The legend, row by row: the name the run is given, whether the row
        #: accumulates or is compared, and its layer picker. Read by ``jobs``.
        self.shadow_rows: list[tuple[str, str, Chips]] = []
        for short, role, label, hint, detail in SHADOW_LEGEND_ROWS:
            picker, row = self._picker(frame, row, label, hint, detail)
            self.shadow_rows.append((short, role, picker))
        self.terrain_layers, row = self._picker(
            frame,
            row,
            "Ground it lands on",
            "The terrain layers. They receive shadow, never cast it.",
            "Shadows land on the ground and on whatever is standing, so the "
            "terrain has to be in the run — but as a receiver. Among the "
            "occluders it puts every sample below the hill in permanent shade "
            "and prints a solid grey sheet. Left empty, shadows fall on a "
            "flat plane at the datum instead.",
        )
        self.terrain_floor, row = self._entry(
            frame,
            row,
            "Ignore ground below",
            "",
            "Metres. Blank keeps all of it.",
            "A survey often runs past the neighbourhood into ground tens of "
            "metres lower, and a shadow reaching that falls the whole way and "
            "runs on for hundreds of metres. Right arithmetically, and not "
            "what the sheet is asking.",
        )
        self.shadow_dates, row = self._ticks_row(
            frame,
            row,
            "Days",
            "The days a shadow set is drawn for.",
            "21 June is the one that decides things — the shortest day, when "
            "shadows are longest. The equinoxes and midsummer are drawn "
            "alongside it by convention. Each day adds a full set of sheets.",
            DAY_CHOICES,
            key=_day_key,
            initial=DEFAULT_SHADOW_DATES,
        )
        self.shadow_hours, row = self._ticks_row(
            frame,
            row,
            "Hours",
            "The whole hours drawn, on each of those days.",
            "One drawing per hour per day. Nine to three is the assessed "
            "window; the long shadows at either end are correct and surprise "
            "people — on 21 June the sun is about 19 degrees up and a shadow "
            "runs nearly three times the height that casts it.",
            _hour_choices(clock=False),
            key=_clock_text,
            initial=DEFAULT_SHADOW_HOURS,
        )
        self.do_shadow_all_hours = tk.BooleanVar(value=False)
        tick = ttk.Checkbutton(
            frame,
            text="Every hour on one drawing",
            variable=self.do_shadow_all_hours,
            command=self._sync,
        )
        tick.grid(row=row, column=0, columnspan=2, sticky="w", padx=(18, 0), pady=(6, 0))
        Tooltip(
            tick,
            "Also a drawing per day with the designed building's own shadow at "
            "every hour ticked above, as outlines labelled by hour, with its own "
            "view and sheet. The designed building is the Proposed row, or the "
            "last row being tested when Proposed is empty.",
        )
        row += 1
        self.shadow_storey, row = self._entry(
            frame,
            row,
            "Draw on storey",
            "0",
            "Storey index the fills are placed on.",
            "Where the fills land, not what casts them. A site drawing is "
            "usually the ground storey — which is not always storey 0: a "
            "project with a survey datum below it numbers the ground 6, and "
            "fills drawn on 0 land in a plan nobody opens and read as nothing "
            "drawn at all.",
        )
        self.shadow_study_subset, row = self._combo(
            frame,
            row,
            "Subset — shadow sheets",
            "Layout Book subset the shadow sheets go into.",
            "Same rule as the other two: the subset has to exist already, "
            "because the Layout Book is the office's structure to organise. A "
            "missing one is reported rather than invented, with the sheets "
            "left at the root of the book.",
        )

    def _sun_eyes(self, frame: ttk.Frame) -> None:
        """The sun eye views: the model seen from the sun, one view per hour.

        Everything it can see is in sun and everything hidden is in shade,
        which answers "why is this balcony dark at ten" in one picture. The
        settings here are the ones read off the practice's own diagrams; the
        date and the hours come from the ruleset's assessment window and are
        not offered, because a sun eye set at the wrong date is a plausible
        picture of the wrong day.

        Needs the Loriini add-on, and a floor plan tab in front
        when it runs: the projection can only be written with the window and
        the current database agreeing, and the run says so if they do not.
        """
        row = 0
        self.do_sun_eyes = tk.BooleanVar(value=False)
        # The study's own box. Everything from here to the end of the block
        # is built inside it, by the simple means of pointing ``frame`` at it:
        # the rows beneath neither know nor care.
        frame, row = self._panel(frame, row), 0
        box = ttk.Checkbutton(
            frame,
            text="Sun views",
            variable=self.do_sun_eyes,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Sun views"),
        )
        self._head(frame, box, SUN_EYE_JOB)
        Tooltip(
            box,
            "The model seen from the sun's own position at each hour of the "
            "assessment window, as saved views, 3D Documents and sheets. Off "
            "by default: it needs the Loriini add-on installed, and a floor "
            "plan tab in front in Archicad when it runs.",
        )
        row += 1
        self._caption(
            frame,
            row,
            "Seven views along the sun, 9am to 3pm on 21 June, each exact to the "
            "sun's own bearing; the documents on two sheets.",
        )
        row += 1

        self.eye_pen_set, row = self._combo(
            frame,
            row,
            "Pen set",
            "The project's pen set the views use. Blank keeps each view's own.",
            "The practice's drawing pens, so the sheet prints the way the "
            "other DA drawings do. Read off the office's own sun views on the "
            "reference project as '00 FA Pens'.",
        )
        self.eye_override, row = self._combo(
            frame,
            row,
            "Graphic override",
            "The override combination that paints the glazing.",
            "This is the yellow on the diagram: an override rule, not drawn "
            "geometry. It is a different combination from the shadow "
            "diagrams', and a view given the wrong one shows plain glass.",
        )
        self.eye_base_combination, row = self._combo(
            frame,
            row,
            "Layers, from",
            "The layer combination the views start from. Zones are then hidden.",
            "Every layer that carries a zone is hidden on top of this, "
            "measured from the zones themselves: zones are bodies in 3D and "
            "sit inside the glazing the diagram is meant to show through.",
        )
        # What the command itself defaults to, until the project is read and
        # offers its own; typed values still go through on an older add-on
        # that cannot list overrides.
        self.eye_override.set("Sun Eye Views")
        self.eye_base_combination.set("04 | Shadow Diagrams")
        self.eye_scale, row = self._entry(
            frame,
            row,
            "Scale",
            "500",
            "Denominator of the documents' scale on the sheet.",
            "1:500 shows the street around the building, which is what the "
            "practice's sheets do. The views of the 3D window itself are at "
            "1:1 whatever this says; a document is the drawing.",
        )
        self.eye_hours, row = self._ticks_row(
            frame,
            row,
            "Hours",
            "None pressed is the ruleset's window, 9 to 15.",
            "Only for a sheet that needs fewer. The assessment window is the "
            "ruleset's and a set drawn at other hours is not the study.",
            _hour_choices(clock=False),
            key=_clock_text,
        )

    def _site(self, frame: ttk.Frame) -> None:
        """Site and context analysis from an address, drawn into worksheets.

        The one section that reads nothing off the project: its input is a
        street address, and everything else comes from NSW open data. What it
        offers is which of the three sheets to make and where the site lands
        in the project frame; the scale of the context sheet is the only
        number, because the site sheet chooses its own to fit the site.
        """
        row = 0
        self.do_site = tk.BooleanVar(value=False)
        # The study's own box. Everything from here to the end of the block
        # is built inside it, by the simple means of pointing ``frame`` at it:
        # the rows beneath neither know nor care.
        frame, row = self._panel(frame, row), 0
        box = ttk.Checkbutton(
            frame,
            text="Site analysis",
            variable=self.do_site,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Site analysis"),
        )
        self._head(frame, box, SITE_JOB)
        Tooltip(
            box,
            "Fetches the neighbourhood from NSW open data for the address below "
            "and makes whichever of the four outputs are ticked: the Context "
            "Analysis and Site Analysis sheets, the Summary of Controls on a "
            "layout, and the Context Model in 3D. Needs the Loriini add-on "
            "and an internet connection. NSW addresses only.",
        )
        row += 1
        self._caption(
            frame,
            row,
            "Type the address, tick the outputs, press Run. A few minutes: the "
            "public data services are slow and are asked for everything at once.",
        )
        row += 1
        self.site_address, row = self._entry(
            frame,
            row,
            "Address",
            "",
            'Street address of the site, e.g. "26-30 Campsie St, Campsie NSW 2194".',
            "Looked up in the NSW address register, so the spelling can be "
            "loose but the suburb has to be right: a number that exists in "
            "another suburb is refused rather than drawn. A unit number is "
            "taken as its building; a ranged number as every lot in the range.",
        )

        self.do_site_context = tk.BooleanVar(value=True)
        self.do_site_site = tk.BooleanVar(value=True)
        self.do_site_summary = tk.BooleanVar(value=True)
        for variable, label, detail in (
            (
                self.do_site_context,
                "Context Analysis sheet",
                "Land use wash by LEP zone, schools and hospitals coloured by what "
                "they are, heritage items, rail, bus stops and routes, stations, "
                "5 and 10 minute walking catchments, place and street names, "
                "and the site -- the DA 003 sheet, at the scale below.",
            ),
            (
                self.do_site_site,
                "Site Analysis sheet",
                "The boundary with its dimensions and corner levels, the fall, "
                "contours, neighbours with storeys and zone, trees, poles, "
                "hydrants, driveways, kerbside parking, one-way streets, noise "
                "sources, sun path and prevailing winds -- the DA 004 sheet, "
                "at whichever of 1:200 to 1:750 fits the site.",
            ),
            (
                self.do_site_summary,
                "Summary of Controls layout",
                "The planning-controls table, drawn straight onto a layout of "
                "its own: zone, height of building, FSR and the gross floor area "
                "it allows, minimum lot size, heritage, and the ADG figures "
                "worked out for this site area. Council DCP rows are ruled up "
                "empty; they are not open data.",
            ),
        ):
            tick = ttk.Checkbutton(
                frame,
                text=label,
                variable=variable,
                command=self._sync,
                **icons.options(label, 16),
            )
            tick.grid(row=row, column=0, columnspan=2, sticky="w", padx=(18, 0), pady=(2, 0))
            Tooltip(tick, detail)
            row += 1
        self.do_site_model = tk.BooleanVar(value=False)
        self.do_site_future = tk.BooleanVar(value=False)
        self.do_site_location = tk.BooleanVar(value=True)
        for variable, label, detail in (
            (
                self.do_site_future,
                "Future Context (what the controls allow next door)",
                "Each lot near the site, zoned for flats and under a height "
                "control, set back by the ADG's separation (6, 9 and 12 m by "
                "height band), stepped, and capped by the LEP's height and "
                "floor-space ratio. Drawn dashed in magenta on the Site "
                "Analysis sheet with its storeys written in, and stood as "
                "slabs on the LORIINI FUTURE layer -- a layer of its own, so a "
                "shadow diagram can be cast with the neighbours as they are or "
                "as they could be. The street setback is the council's; 6 m "
                "unless the run folder's settings say otherwise.",
            ),
            (
                self.do_site_model,
                "Context Model in 3D (terrain, blocks, neighbours)",
                "The terrain as one mesh from the contours, every street block "
                "as a kerbed mesh with the roads left between, and one slab per "
                "neighbouring building as tall as its storeys say -- or as the "
                "LEP height control allows, and said to be assumed -- on the "
                "LORIINI layer, for the shadow diagram and the sun views to "
                "cast against. The site's own buildings are left out.",
            ),
            (
                self.do_site_location,
                "Set the project location from the address",
                "Puts Options > Project Location at the site's centre, with the "
                "survey point on the MGA2020 grid, so the sun studies and the "
                "IFC exports know where the project is. Only when the site is "
                "placed at the project origin, and only if the location is still "
                "a city preset; north is kept as it is.",
            ),
        ):
            tick = ttk.Checkbutton(
                frame,
                text=label,
                variable=variable,
                command=self._sync,
                **icons.options(label, 16),
            )
            tick.grid(row=row, column=0, columnspan=2, sticky="w", padx=(18, 0), pady=(2, 0))
            Tooltip(tick, detail)
            row += 1
        self.site_ticks = [
            self.do_site_context,
            self.do_site_site,
            self.do_site_summary,
            self.do_site_future,
            self.do_site_model,
            self.do_site_location,
        ]

        self.site_scale, row = self._entry(
            frame,
            row,
            "Context scale",
            "3000",
            "Denominator of the context sheet's scale. 1:3000 on the office's A1 sheets.",
            "Sets how much neighbourhood is fetched: the A1 map field at this "
            "scale, centred on the site. 1:2000 for a tight urban site, 1:4000 "
            "where the station is a long way off. The site sheet ignores this "
            "and picks the scale its boundary fits at.",
        )
        self.site_anchor, row = self._tiles(
            frame,
            row,
            "Site lands at",
            "Where the site goes in the project's frame.",
            "'Project location' trusts Options > Project Preferences > Project "
            "Location: the site is placed where the project's own georeferencing "
            "says it is, turned to the project's north, so it lines up with a "
            "model that is already there. 'Project origin' puts the site's centre "
            "at (0, 0) -- for a project that has nothing in it yet, or whose "
            "location is still the Sydney preset.",
        )
        self.site_anchor.set("Project location")
        self.site_radius, row = self._entry(
            frame,
            row,
            "Model radius (m)",
            "500",
            "How far each way around the site the 3D model reaches. Blank: the site sheet's.",
            "A square of this half-width around the site is fetched for the model: "
            "the contours, every building footprint and the height controls. "
            "500 m is a neighbourhood; the fetch and the slabs both grow with the "
            "square of it.",
        )
        self.site_future_reach, row = self._entry(
            frame,
            row,
            "Future reach (m)",
            "100",
            "How far from the site's boundary a lot is still its future context.",
            "The lots across the street and the two behind are what cast a "
            "shadow on the site or take one from it; a hundred metres is "
            "those. The envelopes are worked out from the model's square, so "
            "the reach cannot exceed the model radius.",
        )
        self.site_future_setback, row = self._entry(
            frame,
            row,
            "Street setback (m)",
            "6",
            "The council's DCP street setback for a flat building.",
            "The register carries the LEP's height and floor-space ratio but "
            "not the DCP's setbacks. Side and rear setbacks are the ADG's, by "
            "height; the street setback is the council's, and 6 m is the "
            "common figure in a Sydney DCP. Check the DCP.",
        )
        self.site_out, row = self._folder_row(
            frame,
            row,
            "Run folder",
            "Where what was fetched is saved. Blank is Documents\\Loriini\\site-analysis.",
            "Every run writes the data it fetched as JSON here, and the aerial "
            "photo under the sheets as JPEG tiles with world files. A saved "
            "run can be redrawn without the internet: "
            "sun-study site --from <this folder>.",
        )

    def _folder_row(
        self, parent: ttk.Frame, row: int, label: str, hint: str, detail: str
    ) -> tuple[ttk.Entry, int]:
        """A path, typeable, with a Browse beside it.

        One of the text boxes that stays a text box: a path on a network drive
        is genuinely typed, or pasted, and the entry is the honest record of
        what gets passed. The button is what makes it bearable.
        """
        name = ttk.Label(parent, text=label, **icons.options(label))
        name.grid(row=row, column=0, sticky="w", pady=(3, 0))
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", pady=(3, 0))
        holder.columnconfigure(0, weight=1)
        box = ttk.Entry(holder)
        box.grid(row=0, column=0, sticky="ew")
        button = ttk.Button(
            holder,
            text="Browse…",
            width=11,
            command=lambda: self._browse(box, label),
            **icons.button_options("folder"),
        )
        button.grid(row=0, column=1, padx=(6, 0))
        line = self._hint(parent, row + 1, hint)
        for target in (name, box, button):
            Tooltip(target, detail, title=label, short=self._saying(line))
        return box, row + 1

    def _browse(self, box: ttk.Entry, label: str) -> None:
        """Pick a folder. Leaves the entry alone if the dialog was cancelled."""
        chosen = filedialog.askdirectory(parent=self.root, title=label, mustexist=True)
        if not chosen:
            return
        box.delete(0, "end")
        box.insert(0, chosen)
        self._sync()

    def _not_yet(self, frame: ttk.Frame, what: str) -> None:
        """A section for an output this version does not make.

        Said in full rather than greyed out, because a tab that cannot be
        opened cannot explain itself and reads as something broken. There is
        nothing to tick here on purpose: an empty page is honest, and a
        switch that does nothing is not.
        """
        ttk.Label(frame, text=what, foreground=HINT, wraplength=560, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )

    def _controls(self, base: ttk.Frame) -> None:
        """Run, the progress bar and the log, under every section alike."""
        #: What pressing Run will actually do. With the ticks spread across
        #: sections there is otherwise nowhere on screen that answers it: a
        # The row of queued study names that used to sit here is gone. It
        # existed because nothing on screen said what Run would do; the panel
        # of sheets down the right says it in sheets, which is the unit the
        # question is really asked in.
        progress_row = ttk.Frame(base, style="Chrome.TFrame")
        progress_row.grid(row=2, column=0, sticky="ew", pady=(2, 6))
        progress_row.columnconfigure(0, weight=1)

        buttons = ttk.Frame(base, style="Chrome.TFrame")
        buttons.grid(row=1, column=0, sticky="ew", pady=(2, 2))
        buttons.columnconfigure(0, weight=1)
        self.go = ttk.Button(
            buttons,
            text="Run study",
            command=self._start,
            style="Run.TButton",
            **icons.button_options("run"),
        )
        self.go.grid(row=0, column=0, sticky="ew")
        Tooltip(
            self.go,
            "Runs every ticked study in the project chosen above, one after "
            "the other. Minutes rather than seconds: the export alone takes a "
            "couple. Nothing is saved — look at the result in Archicad and "
            "save it yourself if you want to keep it.",
        )
        self.cancel = ttk.Button(
            buttons,
            text="Stop",
            style="Chrome.TButton",
            command=self._stop,
            state="disabled",
            **icons.button_options("stop"),
        )
        self.cancel.grid(row=0, column=1, padx=(6, 0))
        Tooltip(
            self.cancel,
            "Asks the run to stop and lets it put the project's layer state "
            "back on the way out. It can take a few seconds to come to a halt.",
        )
        keep = ttk.Button(
            buttons,
            text="Save as default",
            style="Chrome.TButton",
            command=self._remember,
            width=18,
            **icons.button_options("save_default"),
        )
        # A clear gap between the two kinds of button: Run and Stop act on
        # the project, the four to the right act on this window's settings.
        buttons.columnconfigure(2, minsize=28)
        keep.grid(row=0, column=3, padx=(6, 0))
        Tooltip(
            keep,
            "Remembers every section -- the ticks, the fields and which "
            "section was open -- and fills the window in with it next time. "
            "Meant for what belongs to the practice rather than to one job: "
            "the layer prefix, the living-room suffix, the Archicad wait, "
            "which studies you run. Anything the open project disagrees with "
            "is overruled by the project, so a saved layer name cannot make a "
            "run measure a layer that is not there.",
        )
        drop = ttk.Button(
            buttons,
            text="Forget",
            style="Chrome.TButton",
            command=self._forget,
            width=11,
            **icons.button_options("forget"),
        )
        drop.grid(row=0, column=4, padx=(6, 0))
        Tooltip(
            drop,
            "Throws the saved settings away and puts every section back to "
            "what it opens with on a machine that has never been set up. The "
            "project is then read again, so the lists fill from the open "
            "Archicad as they did the first time.",
        )
        # Presets: the same page, written to a file of the person's choosing
        # and read back from one. "Save as default" is for what belongs to
        # the practice; a preset is for what belongs to a job or a colleague
        # -- the Silverwater setup, the shadow set the council asked for --
        # and it goes wherever a job's files go rather than into a profile.
        keep_as = ttk.Button(
            buttons,
            text="Save preset…",
            style="Chrome.TButton",
            command=self._save_preset,
            width=14,
            **icons.button_options("save_preset"),
        )
        keep_as.grid(row=0, column=5, padx=(6, 0))
        Tooltip(
            keep_as,
            "Writes every section -- the ticks, the fields and which section "
            "is open -- to a file you name, to load again later or on another "
            "machine. The same file as the saved defaults, so one can be "
            "copied over the other. Nothing about which Archicad is open is "
            "in it.",
            title="Save preset",
        )
        take = ttk.Button(
            buttons,
            text="Load preset…",
            style="Chrome.TButton",
            command=self._load_preset,
            width=14,
            **icons.button_options("load_preset"),
        )
        take.grid(row=0, column=6, padx=(6, 0))
        Tooltip(
            take,
            "Fills the window in from a preset file. Only what the file names "
            "changes; the rest stays as it is. Anything the open project "
            "disagrees with is overruled by the project, so a layer saved on "
            "another job cannot make a run measure a layer that is not here. "
            "The saved defaults are not touched -- press Save as default to "
            "keep it.",
            title="Load preset",
        )

        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        #: What the bar is actually at, in words. An indeterminate bar says
        #: only that something is happening, and "3 of 7" is the thing a
        #: colleague wants while a shadow diagram grinds through its sheets.
        self.progress_count = ttk.Label(progress_row, text="", style="ChromeHint.TLabel")
        self.progress_count.grid(row=0, column=1, sticky="e", padx=(8, 0))

        #: The newest line out of a run, and the only one on screen.
        #:
        #: Eight lines of scrolling log used to sit here: a sixth of the
        #: window given to a transcript that, between runs, was eight empty
        #: lines, and during one was read by nobody -- a run is minutes long
        #: and the question the whole time is "where is it up to", which is
        #: one line and a bar, not a page.
        #:
        #: Nothing is thrown away. Every line is still kept, in ``self.lines``,
        #: so a run that failed can be read back; it is simply not what the
        #: bottom of the window is made of.
        self.note = ttk.Label(base, text="", style="Note.TLabel")
        self.note.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # The one line of text down here that is not about this run: whose
        # build this is, and until when. The prototype disclaimer is still on
        # every sheet and in every export, where the numbers are; the foot of
        # the window carries the licence instead of shouting it.
        ttk.Label(base, text=credential(), style="ChromeHint.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )

    #: How wide the label column is inside a box. Every box has a grid of its
    #: own, so without a number they would each size the column to their own
    #: longest label and no two boxes' fields would line up down the page.
    #: This is "Subset — time-of-day sheets" with its drawing beside it.
    LABEL_COLUMN = 208

    def _panel(self, outer: ttk.Frame, row: int, *, title: str = "") -> ttk.Frame:
        """One box on a page: a study, or a group of settings that go together.

        A page was a flat run of rows with a rule between the groups, which is
        what made it read as a form. A box says the same grouping as a shape:
        a rounded border, a tinted header, and the rows that belong to it
        inside. The border and the header's tint are one nine-slice picture
        (``theme._rounded``), so the tint's corners are the box's corners.

        The rows are built by the code that always built them. The caller
        points its own ``frame`` at what this returns and starts ``row`` again
        at nought, and the helpers beneath it neither know nor care.

        ``title`` heads a box that has no tick to head it -- General and Model
        are set up, not switched on. A study's box is headed by ``_head``.
        """
        head = theme.PANEL_HEAD
        # A settings card wears the grey band: it is not switched on, and the
        # tint means switched on. A study's card is restyled by ``_sync``.
        box = ttk.Frame(
            outer,
            style="BoxOff.TFrame" if title else "Box.TFrame",
            padding=(14, head + 12, 14, 14),
        )
        box.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        box.columnconfigure(0, minsize=self.LABEL_COLUMN)
        box.columnconfigure(1, weight=1)
        if title:
            # Placed, not gridded: the padding above keeps the rows clear of
            # the header, and the header itself sits in that padding. Measured
            # from the *outside* of the box, because a ttk frame tells Tk its
            # padding is a border and ``place`` otherwise starts inside it --
            # which puts the header on top of the first row instead of over it.
            # Set in capitals, the way Archicad heads a section of a dialog.
            ttk.Label(box, text=title.upper(), style="BoxTitle.TLabel").place(
                bordermode="outside", x=10, y=2, height=head - 3, relwidth=1.0, width=-20
            )
        return box

    def _head(self, box: ttk.Frame, tick: ttk.Checkbutton, job: str) -> None:
        """Put a study's tick at the head of its box, and remember both.

        The tick *is* the header: the study's name, its drawing and the box
        that switches it on, across the tinted top of its own panel. At the
        right, what the tick is worth in sheets -- which is the figure the
        panel down the side of the window draws, said where the decision is.
        """
        head = theme.PANEL_HEAD
        tick.place(bordermode="outside", x=8, y=2, height=head - 3, relwidth=1.0, width=-16)
        says = ttk.Label(box, text="", style="PanelSays.TLabel")
        says.place(bordermode="outside", relx=1.0, x=-11, y=2, height=head - 3, anchor="ne")
        self.study_bars[job] = tick
        self.study_boxes[job] = (box, says)

    def _hint(self, parent: ttk.Frame, row: int, text: str) -> ttk.Label:
        """The one-line explanation of a control.

        Nothing is drawn. Forty of these printed down a page at once was a
        wall of grey nobody read, so the sentence goes to the info band when
        the pointer or the keyboard reaches the control it belongs to.

        The label is still made and still returned, because three callers
        rewrite it once the project has been read -- what a zone field should
        say is what the project turned out to hold, which is not known until
        Archicad answers -- and the band asks it for its text at the moment
        somebody looks.
        """
        return ttk.Label(parent, text=text, style="Hint.TLabel")

    @staticmethod
    def _saying(line: ttk.Label) -> Callable[[], str]:
        """That label's text, read when it is wanted rather than now."""
        return lambda: str(line.cget("text"))

    def _tally(self, box: ttk.Entry | Chips) -> str:
        """How many of the project's layers a picker has, for the band."""
        chosen = len(self._listed(box))
        offered = len(pickable(self.options.layers))
        return f"{chosen} of {offered} chosen" if offered else f"{chosen} chosen"

    def _caption(self, parent: ttk.Frame, row: int, text: str) -> None:
        """What a whole study is, under the tick that turns it on.

        This one is still drawn. It is not the explanation of a control -- it
        is the sentence that says what the block of controls beneath it is
        for, and a page whose studies are unlabelled until you point at one is
        a page you cannot scan.
        """
        ttk.Label(parent, text=text, foreground=HINT, wraplength=620).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=(18, 0), pady=(0, 6)
        )

    def _combo(
        self, parent: ttk.Frame, row: int, label: str, hint: str, detail: str
    ) -> tuple[ttk.Combobox, int]:
        name = ttk.Label(parent, text=label, **icons.options(label))
        name.grid(row=row, column=0, sticky="w", pady=(3, 0))
        box = ttk.Combobox(parent, values=[])
        box.grid(row=row, column=1, sticky="ew", pady=(3, 0))
        line = self._hint(parent, row + 1, hint)
        for target in (name, box):
            Tooltip(target, detail, title=label, short=self._saying(line))
        return box, row + 1

    def _entry(
        self, parent: ttk.Frame, row: int, label: str, initial: str, hint: str, detail: str
    ) -> tuple[ttk.Entry, int]:
        """A field somebody really does type into.

        The pickers are chips now, because their values come out of the
        project and the only sensible input is a tick. These are the ones
        that do not: an address, a layer prefix, a threshold. A text box is
        the right control for typed text, and there are eleven of them left
        where there were forty.
        """
        name = ttk.Label(parent, text=label, **icons.options(label))
        name.grid(row=row, column=0, sticky="w", pady=(6, 0))
        box = ttk.Entry(parent)
        box.insert(0, initial)
        box.grid(row=row, column=1, sticky="ew", pady=(6, 0))
        line = self._hint(parent, row + 1, hint)
        for target in (name, box):
            Tooltip(target, detail, title=label, short=self._saying(line))
        return box, row + 1

    def _zone_row(
        self, parent: ttk.Frame, row: int, label: str, hint: str, detail: str
    ) -> tuple[ttk.Combobox, Chips, ttk.Label, int]:
        """A layer and, beside it, which of the Zones on it are meant.

        One row for the two halves of one question, because they are not
        separable: a layer says where to look and the names say what is there,
        and a project that keeps its apartments, its balconies and its storage
        on one layer -- which is the ordinary case, not an odd one -- is
        measured wrongly by either half alone.

        The names are chips now. They were a comma-joined string in a box two
        hundred pixels wide, which is the least readable way to show the one
        thing a person checks here.
        """
        name = ttk.Label(parent, text=label, **icons.options(label))
        name.grid(row=row, column=0, sticky="nw", pady=(6, 0))
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", pady=(6, 0))
        holder.columnconfigure(1, weight=1)

        layer = ttk.Combobox(holder, values=[], width=22)
        layer.grid(row=0, column=0, sticky="nw")
        names = Chips(
            holder,
            add=lambda: self._choose(
                names,
                f"{label}: which names",
                "Zones on the chosen layer. The size beside each name is what "
                "says what it is: a dwelling is tens of square metres, a "
                "balcony is a few, a storage cupboard is less.",
                [kind.label for kind in self._kinds_on(layer.get())],
                {kind.label: kind.described() for kind in self._kinds_on(layer.get())},
            ),
            on_change=self._sync,
            empty="no names chosen",
            label=label,
        )
        names.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        line = self._hint(parent, row + 1, hint)
        layer.bind("<<ComboboxSelected>>", lambda _event: self._offer_zone_names())
        for target in (name, layer, names):
            Tooltip(target, detail, title=label, short=self._saying(line))
        return layer, names, line, row + 1

    def _tiles(
        self, parent: ttk.Frame, row: int, label: str, hint: str, detail: str
    ) -> tuple[Tiles, int]:
        """A choice row: the label, then the drawings.

        The same shape as ``_combo`` so a field can move between the two
        without its caller changing, and it is returned as the same kind of
        thing as far as everything that reads it is concerned.
        """
        name = ttk.Label(parent, text=label, **icons.options(label))
        name.grid(row=row, column=0, sticky="w", pady=(6, 0))
        made = Tiles(
            parent,
            self.TILE_CHOICES[label],
            on_change=self._sync,
            multi=label in self.TILE_MULTI,
            aliases=self.TILE_ALIASES.get(label),
        )
        made.grid(row=row, column=1, sticky="w", pady=(6, 0))
        line = self._hint(parent, row + 1, hint)
        Tooltip(name, detail, title=label, short=self._saying(line))
        return made, row + 1

    def _ticks_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        hint: str,
        detail: str,
        choices: Sequence[tuple[str, str, str]],
        *,
        key: Callable[[str], str],
        span: bool = False,
        initial: str = "",
    ) -> tuple[Ticks, int]:
        """A row of hours or days to press, in place of a box to type them in.

        The same shape as ``_entry``, and returned as the same kind of thing
        as far as everything that reads it is concerned, so the fields that
        moved off the keyboard did not have to move anywhere else.
        """
        name = ttk.Label(parent, text=label, **icons.options(label))
        name.grid(row=row, column=0, sticky="w", pady=(6, 0))
        made = Ticks(parent, choices, key=key, span=span, on_change=self._sync)
        made.insert(0, initial)
        made.grid(row=row, column=1, sticky="w", pady=(6, 0))
        line = self._hint(parent, row + 1, hint)
        Tooltip(name, detail, title=label, short=self._saying(line))
        return made, row + 1

    def _picker(
        self, parent: ttk.Frame, row: int, label: str, hint: str, detail: str
    ) -> tuple[Chips, int]:
        """A layer list: ticked out of the project, shown as chips.

        The text box is gone. It was the honest record of what will be passed
        and the worst way to show it -- a hundred and fifty layer names carry
        a group number, a dot and a space, and four of them joined by commas
        run off the end of any field that fits on the page. The chips are the
        same record, with a way out of each one, and they wrap.
        """
        name = ttk.Label(parent, text=label, **icons.options(label))
        name.grid(row=row, column=0, sticky="nw", pady=(6, 0))
        box = Chips(
            parent,
            add=lambda: self._choose(box, label, hint),
            on_change=self._sync,
            empty="no layers chosen",
            label=label,
        )
        box.grid(row=row, column=1, sticky="ew", pady=(6, 0))
        line = self._hint(parent, row + 1, hint)
        for target in (name, box):
            Tooltip(
                target,
                detail,
                title=label,
                short=self._saying(line),
                state=lambda: self._tally(box),
            )
        return box, row + 1

    def _choose(
        self,
        box: ttk.Entry | Chips,
        label: str,
        hint: str,
        available: Sequence[str] | None = None,
        describe: Mapping[str, str] | None = None,
    ) -> None:
        """Tick names into an entry. Leaves it alone if nothing was chosen.

        ``available`` defaults to the project's layers, which is what most of
        these are; a zone row passes the names its layer carries instead.
        """
        offered = list(available) if available is not None else pickable(self.options.layers)
        if not offered:
            self._write(f"Nothing to choose from for {label}. Read a project first.")
            return
        dialog = LayerChooser(
            self.root,
            title=label,
            hint=hint,
            available=offered,
            chosen=self._listed(box),
            describe=describe,
        )
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        box.delete(0, "end")
        box.insert(0, ", ".join(dialog.result))
        # A layer chosen here changes what a run will draw, so the sheets
        # panel and the tab marks are told, exactly as a tick tells them.
        self._sync()

    # -- which studies are on, said in every place it matters ----------------
    def _studies(self) -> list[tuple[str, tk.BooleanVar, str]]:
        """Every study this window runs: its name, its tick, and its section.

        One list because two things have to agree about it and would
        otherwise be written out separately -- the tab that marks itself when
        the study in it will run, and the line above Run that says what is
        queued. The names are the ones ``jobs`` labels the run with, so a
        colleague reads the same words before pressing Run and in the log
        afterwards.
        """
        return [
            (FACADE_JOB, self.do_facade, self.FACADE),
            (PLANS_JOB, self.do_plans, self.DIAGRAMS),
            (COMMUNAL_JOB, self.do_communal, self.DIAGRAMS),
            (SHADOW_JOB, self.do_shadows, self.SHADOWS),
            (SUN_EYE_JOB, self.do_sun_eyes, self.EYE),
            (SITE_JOB, self.do_site, self.SITE),
        ]

    def _open_section(self) -> str:
        """Which page is showing, by title.

        By title and not by number so that inserting a section, or dropping
        one, cannot reopen somebody on a different page than the one they
        left. Never empty: a tab strip has no state with nothing open, which
        is the one thing the launcher could be and this cannot.
        """
        return self.showing

    def _show_section(self, title: str) -> None:
        """Open that page. An empty name opens General.

        A title this version *does* have but under another name leaves the
        page where it is -- a settings file written before the sections were
        regrouped names "Solar tools", which was a container and is not a page
        any more. Losing which page was open is the cheapest thing in that
        file to lose, and moving somebody somewhere they did not ask for is
        dearer than not moving them.

        An empty name is different, and is the one case that does move: it is
        what a file saved by the version with the launcher wrote for "no page
        open", and there is no such place to put anybody now.
        """
        if title not in self.pane_of:
            if title:
                return
            title = self.GENERAL
        for pane in self.panes:
            pane.pack_forget()
        self.pane_of[title].pack(side="top", fill="both", expand=True)
        self.showing = title
        self._paint_tabs()
        # With nothing under the pointer the band says what this page is for.
        # A strip that blanks itself is dead space at the foot of the window,
        # which is exactly what the log was.
        self.info.resting(
            icons.BY_SECTION.get(title, ""),
            title,
            self.SECTION_BLURB[title],
            "Point at anything, or tab to it, for what it is and what happens when it is wrong.",
        )

    def ask_for(self, study: str) -> bool:
        """Tick one study and open the section it lives in. True if it took.

        This is what the add-on's palette buttons reach. Archicad cannot run
        the analysis -- that lives in Python, where it is tested -- so a
        palette button starts this program with ``LORIINI_STUDY`` naming what
        it wants, and the window opens already set up for it. Which is the
        whole of what a button in Archicad can honestly do, and is also the
        printer driver's own logic: choose the output, and the dialog comes up
        arranged around it.

        Anything unrecognised is ignored and answers False. A misspelt
        environment variable must leave the window opening normally rather
        than refusing to start, for the same reason a settings file edited
        into nonsense costs one setting and not the whole page.
        """
        wanted = {
            "facade": (self.do_facade, self.FACADE),
            "apartments": (self.do_plans, self.DIAGRAMS),
            "communal": (self.do_communal, self.DIAGRAMS),
            "shadow": (self.do_shadows, self.SHADOWS),
            "views": (self.do_sun_eyes, self.EYE),
            "site": (self.do_site, self.SITE),
        }
        found = wanted.get(study.strip().casefold())
        if found is None:
            return False
        tick, section = found
        tick.set(True)
        self._show_section(section)
        # The ticks were changed from outside, so the three things that are
        # one fact -- the dependent boxes, the tab labels and the line above
        # Run -- have to be told, exactly as a click would tell them.
        self._sync()
        return True

    def _sync(self) -> None:
        """Keep the window telling the truth about what it will do.

        Three things that are one fact seen from three places, which is why
        they move together.

        A dependent tick is only a question while the study above it is on.

        A tab whose study will run says so on its own label -- in blue, with a
        dot, which is not what the open tab is marked with. That is what tabs
        cost: a section nobody opens is a section nobody knows the state of,
        and a colleague who has never opened Solar analysis should still be
        able to see from the outside that two studies are waiting in it.

        And the panel down the right holds every sheet those ticks will make.
        That is what used to be a row of study names above Run, and it exists
        for the same reason: with the ticks spread over six sections there is
        otherwise nowhere on screen that answers "what happens if I press
        this" -- the one question a run of several minutes had better not get
        wrong. A picture of the sheets answers it better than a list of names.
        """
        self.floors_box.config(state="normal" if self.do_facade.get() else "disabled")

        # A tab whose study will run says so, without anybody opening it.
        self._paint_tabs()
        for toggles in self.toggle_rows:
            toggles.paint()
        sheets = self.planned()
        for name, tick, _where in self._studies():
            on = tick.get()
            bar = self.study_bars.get(name)
            if bar is not None:
                bar.configure(style="Study.TCheckbutton" if on else "StudyOff.TCheckbutton")
            if name in self.study_boxes:
                box, says = self.study_boxes[name]
                box.configure(style="Box.TFrame" if on else "BoxOff.TFrame")
                made = sum(1 for sheet in sheets if sheet.job == name and sheet.paper)
                models = sum(1 for sheet in sheets if sheet.job == name and not sheet.paper)
                worth = f"{made} sheet" + ("" if made == 1 else "s")
                if models:
                    worth += f", {models} model" + ("" if models == 1 else "s")
                says.configure(
                    text=worth if on else "off",
                    style="PanelSays.TLabel" if on else "PanelSaysOff.TLabel",
                )
        self._refill_dock(sheets)

    #: Under this many pixels the window cannot hold the page and the sheets
    #: panel side by side: the page is left with less than a chip row needs.
    FOLD_BELOW = 960

    def _fit(self, event: tk.Event[tk.Misc]) -> None:
        """Fold the sheets panel when the window is dragged too narrow for both.

        Only on *crossing* the line. In between, the chevron is the user's:
        somebody who opened the panel in a narrow window meant to, and having
        it snap shut again on the next pixel of a resize would be the window
        arguing with them.
        """
        if event.widget is not self.root:
            return
        narrow = event.width < self.FOLD_BELOW
        if narrow == self._narrow:
            return
        self._narrow = narrow
        self.dock.fold(narrow, by_hand=False)

    def _refill_dock(self, sheets: Sequence[Sheet]) -> None:
        """Redraw the sheets panel from what is ticked and typed now.

        Cheap enough to do on every tick, every chip and every keystroke: the
        sun is a numpy call that never leaves this process and the drawing is
        a few dozen canvas items apiece.
        """
        filed = ", ".join(
            dict.fromkeys(
                box.get().strip()
                for box in (self.adg_subset, self.shadow_subset)
                if box.get().strip()
            )
        )
        self.dock.refill(sheets, filed=f"Layout Book: {filed}" if filed else "")

    # -- settings that outlive the window ------------------------------------
    def _fields(self) -> dict[str, ttk.Entry | Tiles | Ticks | Chips]:
        """Every typed or chosen setting, under a name that survives a rename.

        Written out here rather than gathered off the widget tree, because the
        name is what a saved file is keyed on: a field moved into Advanced, or
        relabelled, or re-ordered, must not cost somebody the setting they
        saved. A ``Combobox`` is an ``Entry``, so both kinds are read and
        written the same way and belong in one mapping.

        The Archicad picker is deliberately not here. Which instance answered,
        on which port, is a fact about this afternoon rather than a preference,
        and restoring last week's port would point the study at whatever holds
        it today.
        """
        return {
            "apartment_layer": self.apartments,
            "apartment_names": self.apartment_names,
            "balcony_layer": self.balconies,
            "balcony_names": self.balcony_names,
            "communal_layer": self.communal,
            "communal_names": self.communal_names,
            "communal_window": self.communal_window,
            "communal_hours": self.communal_hours,
            "communal_height": self.communal_height,
            "custom_day": self.custom_day,
            "communal_grid": self.communal_grid,
            "tables_folder": self.tables,
            "master_layout": self.master,
            "storey_from": self.storey_from,
            "storey_to": self.storey_to,
            "year": self.year,
            "layer_combination": self.combination,
            "subject_layers": self.subject,
            "require_layers": self.require,
            "context_layers": self.context,
            "hide_layers": self.hide,
            "livable_suffix": self.livable,
            "plan_instants": self.instants,
            "plan_kinds": self.plan_kinds,
            "shadow_subset": self.shadow_subset,
            **{f"shadow_layers_{short.lower()}": box for short, _role, box in self.shadow_rows},
            "shadow_terrain_layers": self.terrain_layers,
            "shadow_terrain_floor": self.terrain_floor,
            "shadow_dates": self.shadow_dates,
            "shadow_hours": self.shadow_hours,
            "shadow_storey": self.shadow_storey,
            "shadow_study_subset": self.shadow_study_subset,
            "eye_pen_set": self.eye_pen_set,
            "eye_override": self.eye_override,
            "eye_base_combination": self.eye_base_combination,
            "eye_scale": self.eye_scale,
            "sheets": self.sheets,
            "eye_title_block": self.eye_title_block,
            "eye_hours": self.eye_hours,
            "site_address": self.site_address,
            "site_scale": self.site_scale,
            "site_anchor": self.site_anchor,
            "site_out": self.site_out,
            "site_radius": self.site_radius,
            "site_future_reach": self.site_future_reach,
            "site_future_setback": self.site_future_setback,
            "adg_subset": self.adg_subset,
            "layer_prefix": self.prefix_solar,
            "shadow_layer_prefix": self.prefix_shadow,
            "sun_view_layer_prefix": self.prefix_sun,
            "site_layer_prefix": self.prefix_site,
            "context_site_group": self.prefix_context,
            "archicad_wait_minutes": self.wait_min,
            "skin_grid": self.grid_m,
        }

    def _ticks(self) -> dict[str, tk.BooleanVar]:
        """The boxes, by the same rule."""
        return {
            "study_facade": self.do_facade,
            "study_floors": self.do_floors,
            "study_plans": self.do_plans,
            "study_communal": self.do_communal,
            "study_shadows": self.do_shadows,
            "shadow_all_hours": self.do_shadow_all_hours,
            "study_sun_eyes": self.do_sun_eyes,
            "study_site": self.do_site,
            "site_context": self.do_site_context,
            "site_site": self.do_site_site,
            "site_summary": self.do_site_summary,
            "site_model": self.do_site_model,
            "site_future": self.do_site_future,
            "site_location": self.do_site_location,
        }

    #: The section that was showing, saved under its own name. It is neither
    #: a field nor a tick, and it is worth keeping for the same reason the
    #: open Advanced panel used to be: somebody who only ever runs the
    #: diagrams should open on the diagrams, not on a page of layer settings
    #: they set up once in March.
    OPEN_SECTION = "open_section"

    def settings(self) -> dict[str, str | bool]:
        """Everything on this page, as it would be saved. Public and pure, so
        the round trip can be tested without a file or a screen."""
        saved: dict[str, str | bool] = {name: box.get() for name, box in self._fields().items()}
        saved.update({name: state.get() for name, state in self._ticks().items()})
        saved[self.OPEN_SECTION] = self._open_section()
        return saved

    def apply(self, saved: Mapping[str, str | bool]) -> None:
        """Put saved settings back on the page, one at a time.

        Each is taken only if it is the kind of thing that field holds, and
        anything unrecognised is ignored: a file written by a later version,
        or edited by hand, should cost the settings it got wrong and no more.
        Nothing here is validated further than that, because every one of
        these is checked against the open project a moment later -- the lists
        are refilled from Archicad and a name the project does not have is
        replaced by one it does.
        """
        for name, box in self._fields().items():
            value = saved.get(name)
            if isinstance(value, str):
                box.delete(0, "end")
                box.insert(0, value)
        for name, state in self._ticks().items():
            ticked = saved.get(name)
            if isinstance(ticked, bool):
                state.set(ticked)
        opened = saved.get(self.OPEN_SECTION)
        if isinstance(opened, str):
            # A title this version does not have -- a file saved before the
            # sections existed, or after one was renamed -- leaves the
            # notebook where it is, which is General. Losing which tab was
            # open is the cheapest thing in the file to lose.
            self._show_section(opened)
        self._sync()

    def _restore(self) -> None:
        """Open with what was saved, if anything was."""
        saved = preferences.load()
        if not saved:
            return
        self.apply(saved)
        self._write(f"Opened with the settings saved in {preferences.path()}.")

    def _remember(self) -> None:
        """Save the page as the defaults, and say where it went.

        The path is printed because a preference nobody can find is one nobody
        can delete, and "it remembers the wrong thing now" is otherwise an
        unanswerable complaint. A profile that will not be written to is
        reported in the log rather than raised: it is a failure to save a
        convenience, not a failure to run a study.
        """
        try:
            where = preferences.save(self.settings())
        except OSError as refused:
            self._write(f"Could not save the settings: {refused}")
            return
        self._write(f"Saved. These settings are what the window will open with: {where}")

    def _forget(self) -> None:
        """Back to how the window opens on a machine nobody has set up."""
        where = preferences.path()
        had = where.is_file()
        gone = preferences.forget()
        self.apply(self.factory)
        if self.options.reachable:
            # Emptied fields are filled from the project again, exactly as
            # they were the first time it was read -- otherwise Forget leaves
            # a page of blanks rather than a page of defaults.
            self._offer()
        if not had:
            self._write("There were no saved settings. The page is back to its defaults.")
        elif gone:
            self._write("Saved settings deleted. The page is back to its defaults.")
        else:
            self._write(f"The page is back to its defaults, but {where} could not be deleted.")

    # -- presets: the same page, in a file of the person's choosing ---------
    def _save_preset(self) -> None:
        """Ask where, then write the page there."""
        where = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save these settings as a preset",
            defaultextension=preferences.PRESET_SUFFIX,
            filetypes=preferences.PRESET_TYPES,
            initialdir=str(preferences.presets_folder()),
            initialfile=f"Loriini preset{preferences.PRESET_SUFFIX}",
        )
        if where:
            self.save_preset(Path(where))

    def save_preset(self, where: Path) -> Path | None:
        """Write the page to ``where``. Public, so the round trip can be
        tested without a dialog. None, and a line in the log, if the folder
        would not take it."""
        try:
            written = preferences.write(where, self.settings())
        except OSError as refused:
            self._write(f"Could not save the preset: {refused}")
            return None
        self._write(f"Preset saved: {written}. Load preset reads it back, here or elsewhere.")
        return written

    def _load_preset(self) -> None:
        """Ask which, then put it on the page."""
        where = filedialog.askopenfilename(
            parent=self.root,
            title="Load a preset",
            filetypes=preferences.PRESET_TYPES,
            initialdir=str(preferences.presets_folder()),
        )
        if where:
            self.load_preset(Path(where))

    def load_preset(self, where: Path) -> bool:
        """Put the settings in ``where`` on the page. True if they landed.

        Only what the file names changes -- ``apply`` leaves the rest alone
        -- and the project then has the last word, exactly as it does over
        the saved defaults: layer names it does not carry are dropped and
        said out loud, and the emptied fields are filled from the project
        again. A file that is not a preset is reported in the log, with the
        reason, rather than raised: the person chose it and wants to know
        why it did not take, and a window that closes over a wrong file is
        the worse answer.
        """
        try:
            saved = preferences.read(where)
        except (OSError, ValueError) as refused:
            self._write(f"Could not load {where.name}: {refused}")
            return False
        self.apply(saved)
        if self.options.reachable:
            self._only_what_this_project_has()
            self._offer()
        self._write(
            f"Loaded the preset {where.name}. The open project overrules anything in "
            "it that this project does not have."
        )
        return True

    # -- reading the project -------------------------------------------------
    def refresh(self) -> None:
        found = probe.running()
        self.ports = [instance.port for instance in found]
        self.instance.config(
            values=[f"{instance.project}  ·  port {instance.port}" for instance in found]
        )
        if not found:
            self.status.config(
                text="no Archicad answering. Open a project, then Refresh.",
                **icons.state_options("disconnected"),
            )
            self.options = probe.ProjectOptions()
            return
        if self.instance.current() < 0:
            self.instance.current(0)

        self.status.config(text="reading the project ...", **icons.state_options("connected"))
        self.root.update_idletasks()
        self.options = probe.options(self.ports[max(self.instance.current(), 0)])
        self._offer()

    def _offer(self) -> None:
        found = self.options
        # Nothing here works without the add-on: most of the tool's Archicad
        # calls are Tapir's commands, which the Loriini add-on carries built
        # in. So it is said plainly, and Run is switched off rather than left
        # to fail several steps later.
        self.go.config(state="disabled" if found.tapir_missing else "normal")
        if found.tapir_missing:
            self.status.config(
                text=(
                    "Archicad is running but the Loriini add-on is not installed, "
                    "or is too old to carry Tapir's commands, and nothing here works "
                    "without it. Install the current LoriiniAddOn_AC26_Win.apx, "
                    "restart Archicad, then press Refresh."
                ),
                foreground="#a33",
                **icons.state_options("disconnected"),
            )
            return
        if not found.reachable:
            self.status.config(
                text="; ".join(found.problems) or "could not read the project",
                foreground="#a33",
                **icons.state_options("disconnected"),
            )
            return
        self.status.config(
            foreground=HINT,
            text=(
                f"Tapir {found.tapir} · {len(found.layers)} layers · "
                f"{len(found.zone_layers)} carry zones · {len(found.masters)} masters · "
                f"{len(found.subsets)} subsets"
            ),
            **icons.state_options("connected"),
        )
        self._only_what_this_project_has()
        choices = self._zone_layer_choices()
        self._fill(self.apartments, choices, ("Zone.Unit", "Zone."))
        # The balconies are usually on the apartments' own layer -- one
        # project keeps 15 units, 20 balconies and the storage on
        # "06 | Zone.Units" -- so that is the first candidate, and a layer
        # carrying open-space-sized zones is the next.
        self._fill(
            self.balconies,
            choices,
            (self.apartments.get(), *(kind.layer for kind in found.zone_kinds if kind.open_space)),
        )
        self._fill(self.communal, choices, ("Zone.", "Calc."))
        self._offer_zone_names()
        # "VERTICAL - No Scale" before "COVER/NO SCALE": both say no scale and
        # one of them is a cover sheet.
        self._fill(
            self.master,
            found.masters,
            ("VERTICAL - No Scale", "VERTICAL NO SCALE", "No Scale", "A1"),
        )
        self._fill(self.combination, found.combinations, ("IFC ARCH", "IFC"))
        self._fill(self.shadow_subset, found.subsets, ("SHADOW",))
        self._fill(self.adg_subset, found.subsets, ("ADG",))
        # Blank first, and no preference: a blank keeps each view's own pen
        # set, which is what the command does, and the office's set is a
        # choice rather than a guess.
        self._fill(self.eye_pen_set, ("", *found.pen_sets), ())
        # Blank first for the override too: a blank sends nothing and the
        # command's own default holds, where the first name in the list would
        # be a guess -- and a view given the wrong override shows plain glass.
        if found.overrides:
            self._fill(self.eye_override, ("", *found.overrides), ("Sun Eye",))
        self._fill(self.eye_base_combination, found.combinations, ("Shadow Diagram", "Shadow"))
        self._fill(self.shadow_study_subset, found.subsets, ("SHADOW",))
        if not self.subject.get():
            skin = [name for name in found.layers if any(w in name for w in SKIN_WORDS)]
            self.subject.insert(0, ", ".join(skin))
        self._offer_height_cut()

    def _offer_height_cut(self) -> None:
        """Fill the band's two pickers from the project's own storeys.

        The lists are the project's, so a band can be chosen from what the
        building actually has rather than typed from memory. Nothing is
        selected on the caller's behalf: a band is a judgement about which
        storeys are the building and which are parked geometry, and this
        cannot tell them apart -- one real project defines 134 storeys running
        to 422.5 m at a regular 3.2 m spacing the whole way, with no gap to
        say where the tower stops and the masters begin.

        Guessing there would be worse than not guessing. A band set too low
        silently removes the top of the building from every percentage, and
        nothing in the drawing shows it. So the choice is offered and left.

        A value already chosen -- typed, or restored from saved settings --
        is kept: it is a decision, and it outranks anything read here.
        """
        names = list(self.options.storey_names)
        for box in (self.storey_from, self.storey_to):
            box["values"] = names
        if not names:
            return
        self._write(
            f"Storeys read from the project: {len(names)}, {names[0]!r} to {names[-1]!r}. "
            f"Pick the band to measure -- everything outside it is dropped, which is how "
            f"parked hotlink masters are kept out of the result."
        )

    @staticmethod
    def _as_the_project_spells_them(
        wanted: Iterable[str], offered: Iterable[str]
    ) -> tuple[list[str], list[str]]:
        """Split names into the ones this project has and the ones it has not.

        Spacing and case are ignored going in, because a name pasted out of a
        report or typed by hand is nobody's memory test; what comes back is
        the project's own spelling, because that is what the command line has
        to be handed.
        """
        by_shape = {" ".join(name.split()).casefold(): name for name in offered}
        kept: list[str] = []
        lost: list[str] = []
        for name in wanted:
            found = by_shape.get(" ".join(name.split()).casefold())
            (lost if found is None else kept).append(name if found is None else found)
        return kept, lost

    def _only_what_this_project_has(self) -> None:
        """Drop layer names the open project does not carry, and correct the rest.

        Saved settings are why this is here. A picker is filled from the
        project only when it is *empty*, so a facade list saved on one job and
        opened on another would sit there unchallenged and produce a study of
        nothing -- no error, no warning, the exact silent wrong answer this
        window exists to prevent. Dropping the names leaves the field empty,
        and an empty field is filled from the project like a first run.

        It also catches a typed name, which is the same fault arriving by a
        different door, and rewrites a name whose spacing does not match.

        Said out loud, never silently: a setting that vanished without a word
        is worse than one that was wrong.
        """
        lost: list[str] = []
        for box in (self.subject, self.require, self.context, self.hide):
            kept, dropped = self._as_the_project_spells_them(self._listed(box), self.options.layers)
            if not dropped and kept == self._listed(box):
                continue
            lost += dropped
            box.delete(0, "end")
            box.insert(0, ", ".join(kept))
        if lost:
            self._write(f"Not layers in this project, so left out: {_some(lost)}")

    def _zone_layer_choices(self) -> tuple[str, ...]:
        """Every layer, with the ones carrying Zones first.

        Offered in full rather than narrowed to what the probe found zones on.
        The narrowing looked like help and was a trap: which layer holds the
        zones is the office's decision, not a fact this can derive, and a
        project that keeps its communal areas on a fills layer, or on one whose
        zones are hidden, or on a layer whose zones sit on a storey the probe
        did not read, then has no way to say so. The picker simply did not
        offer the answer.

        Ordering keeps the help without the limit: a layer the project really
        does keep zones on is at the top, and every other layer is under it.
        """
        carrying = list(self.options.zone_layers)
        seen = {" ".join(name.split()).casefold() for name in carrying}
        rest = [
            name for name in self.options.layers if " ".join(name.split()).casefold() not in seen
        ]
        return tuple(carrying + rest)

    def _fill(self, box: ttk.Combobox, values: tuple[str, ...], prefer: tuple[str, ...]) -> None:
        """Offer these, and pick the likeliest -- without overriding a choice.

        Preferences are ordered fragments rather than exact names, because the
        thing being guessed at is an office's own naming.
        """
        box.config(values=list(values))
        if not values or box.get() in values:
            return
        for want in prefer:
            match = next((v for v in values if want.casefold() in v.casefold()), None)
            if match is not None:
                box.set(match)
                return
        box.set(values[0])

    # -- running ---------------------------------------------------------------
    def _kinds_on(self, layer: str) -> list[probe.ZoneKind]:
        """What the zones on one layer are called, biggest first."""
        wanted = " ".join(layer.split()).casefold()
        return [
            kind
            for kind in self.options.zone_kinds
            if " ".join(kind.layer.split()).casefold() == wanted
        ]

    def _offer_zone_names(self) -> None:
        """Fill in which zones are dwellings and which are open space.

        Guessed from floor area, and *shown* rather than applied quietly: the
        line under each field says what was found and what was taken, and the
        chooser lists every name with its size. A guess nobody can see is the
        thing this window exists to avoid.

        Area because nothing else in the model separates them. The names are
        an office's own codes -- ``G08``, ``BY``, ``SC`` -- and mean nothing
        outside it, while an apartment is tens of square metres and a balcony
        is a few, on every project there has ever been. The cuts are the ADG's
        own figures, in ``probe``.
        """
        for layer_box, names_box, line, wanted, what in (
            (self.apartments, self.apartment_names, self.apartment_hint, "dwelling", "dwellings"),
            (self.balconies, self.balcony_names, self.balcony_hint, "open_space", "open space"),
        ):
            kinds = self._kinds_on(layer_box.get())
            if not kinds:
                line.config(text=f"No Zones read on that layer, so nothing is taken as {what}.")
                continue
            self._only_on_this_layer(names_box, layer_box.get(), kinds)
            fits = [kind for kind in kinds if getattr(kind, wanted)]
            if not self._listed(names_box):
                names_box.delete(0, "end")
                names_box.insert(0, ", ".join(kind.label for kind in fits))
            taken = f" — taken as {what}: {_some(k.label for k in fits)}" if fits else ""
            line.config(text=f"carries {_some(kind.described() for kind in kinds)}{taken}")

        # Communal space gets no guess. Area cannot tell a courtyard from a
        # large flat, so the line reports what is on the layer and stops.
        kinds = self._kinds_on(self.communal.get())
        if kinds:
            self._only_on_this_layer(self.communal_names, self.communal.get(), kinds)
        self.communal_hint.config(
            text=(
                f"carries {_some(kind.described() for kind in kinds)} — name the "
                f"ones that are communal"
                if kinds
                else "No Zones read on that layer."
            )
        )

    def _only_on_this_layer(
        self, names_box: ttk.Entry | Chips, layer: str, kinds: Sequence[probe.ZoneKind]
    ) -> None:
        """Keep only the zone names that layer actually carries.

        The same fault as a stale layer, one level down, and it arrives by two
        doors: a name saved on another project, and a layer changed under
        names that were guessed for the one before it. Either way the study is
        told to measure zones that are not there, which is not an error --
        it is an assessment of nothing, or of half a building.

        Only when the layer gave up its zones at all. A layer that read as
        empty is a failure to read, not a statement that the names are wrong,
        and it must not cost somebody a list they chose.
        """
        wanted = self._listed(names_box)
        kept, dropped = self._as_the_project_spells_them(wanted, (kind.label for kind in kinds))
        if not dropped and kept == wanted:
            return
        names_box.delete(0, "end")
        names_box.insert(0, ", ".join(kept))
        if dropped:
            self._write(f"Not Zones on {layer}, so left out: {_some(dropped)}")

    def _zone_defaults(self) -> list[str]:
        """Zone layers worth forcing into the export, narrowest first.

        A project's zone layers are the ones named for zones. Everything else
        that happens to carry a Zone -- annotation, area calculations -- is
        somebody's schedule, not the building.
        """
        named = [name for name in self.options.zone_layers if "Zone." in name]
        return named or list(self.options.zone_layers)

    #: What each choice row draws, keyed on the label it sits beside: the
    #: value the field holds, the icon on the tile, and what the tile says on
    #: hover. The values must match what the rest of the window expects to
    #: read back -- ``SHEET_CHOICES`` below is where the sheet titles are
    #: turned into the word the command line wants.
    #: The choice rows whose tiles are switches of their own rather than one
    #: of a set, and the older spellings each reads as the tiles they mean.
    #: "Bands and times" was the Plans row's third tile until both could be lit.
    TILE_MULTI: ClassVar[frozenset[str]] = frozenset({"Plans"})
    TILE_ALIASES: ClassVar[dict[str, dict[str, tuple[str, ...]]]] = {
        "Plans": {"Bands and times": ("Bands by hour", "Sun at each time")},
    }

    TILE_CHOICES: ClassVar[dict[str, tuple[tuple[str, str, str], ...]]] = {
        "Plans": (
            (
                "Bands by hour",
                "plans_bands",
                "Bands by hour: only the whole-day plans, banded by hours of sun.",
            ),
            (
                "Sun at each time",
                "plans_times",
                "Sun at each time: only the plans at each time, showing where the "
                "sun actually falls at that moment.",
            ),
        ),
        "Sheets": (
            (
                "One layout, all drawings",
                "sheets",
                "One layout, all drawings: every drawing of a set dealt onto a single layout.",
            ),
            (
                "Two layouts, half each",
                "sheets_two",
                "Two layouts, half each: the first half of the set on one layout "
                "and the rest on a second.",
            ),
            (
                "A layout per drawing",
                "sheets_each",
                "A layout per drawing: one layout each, which is a lot of "
                "layouts and the right answer for a presentation set.",
            ),
        ),
        # Metres, still, on the command line -- the tiles hold the number.
        # Nobody has to know a sample grid is measured in metres to pick a
        # coarseness, and three drawings say which way is finer without a word.
        "Skin cell": (
            ("2.0", "grid_rough", "Rough — 2 m cells. Fast, and it loses anything narrower."),
            ("1.0", "grid_normal", "Normal — 1 m cells."),
            (
                "0.5",
                "grid_fine",
                "Detailed — 0.5 m cells. Four times the elements of 1 m; over five "
                "thousand on a project this size.",
            ),
        ),
        "Communal grid": (
            ("2.0", "grid_rough", "Rough — samples every 2 m."),
            ("1.0", "grid_normal", "Normal — samples every 1 m."),
            (
                "0.5",
                "grid_fine",
                "Detailed — samples every 0.5 m, which is what reads a courtyard properly.",
            ),
        ),
        "Site lands at": (
            (
                "Project location",
                "site",
                "Project location: the site goes where the project's own "
                "georeferencing says it is, turned to the project's north.",
            ),
            (
                "Project origin",
                "origin",
                "Project origin: the site's centre at (0, 0), for a project "
                "with nothing in it yet.",
            ),
        ),
    }

    #: The two Plans tiles, each a switch of its own. Both lit is the default.
    PLAN_BANDS = "Bands by hour"
    PLAN_TIMES = "Sun at each time"

    def _plan_kinds(self) -> tuple[bool, bool]:
        """``(bands, times)``: which of the two kinds of plan the Plans row
        asks for. A value naming neither -- a hand-edited file -- is both."""
        chosen = {part.strip() for part in self.plan_kinds.get().split(",")}
        if "Bands and times" in chosen or not chosen & {self.PLAN_BANDS, self.PLAN_TIMES}:
            return True, True
        return self.PLAN_BANDS in chosen, self.PLAN_TIMES in chosen

    #: What the Sheets row offers, and the word each sends.
    SHEET_CHOICES = (
        ("One layout, all drawings", "one"),
        ("Two layouts, half each", "two"),
        ("A layout per drawing", "each"),
    )

    def _sheet_args(self) -> list[str]:
        """``--sheets`` for the mode chosen in General. A title from the list
        becomes its word; anything else is sent as typed."""
        chosen = self.sheets.get().strip()
        if not chosen:
            return []
        for title, word in self.SHEET_CHOICES:
            if chosen == title:
                return ["--sheets", word]
        return ["--sheets", chosen]

    def _band_args(self) -> list[str]:
        """The height band, as the two storey flags or nothing at all.

        Either end may be left empty, which is that end left open. Empty on
        both is the whole model measured, which is what the field means and
        not a failure to fill it in -- a project with no parked masters needs
        no band, and every project had none before this setting existed.
        """
        args: list[str] = []
        if self.storey_from.get().strip():
            args += ["--exclude-below-storey", self.storey_from.get().strip()]
        if self.storey_to.get().strip():
            args += ["--exclude-above-storey", self.storey_to.get().strip()]
        return args

    def _day_args(self, day: str) -> list[str]:
        """``--date`` for one day, or nothing on the ruleset's own.

        Nothing for midwinter so the command's names stay the ones it has
        always made, and a short name for the rest. Anything unparseable is
        sent as typed and the command line says what it makes of it.
        """
        if not day:
            return []
        if day in ASSESSMENT_DAYS:
            return [] if day == "winter" else ["--date", day]
        try:
            mmdd = parse_day(day)
        except ValueError:
            return ["--date", day]
        return [] if mmdd == ASSESSMENT_DAYS["winter"][0] else ["--date", day_name(mmdd)]

    def chosen_days(self) -> list[str]:
        """Every day the solar tools should run for, in the order they are read.

        The ticks first, in the order the list defines -- the assessment day
        before the ones that illustrate it -- then whatever was typed as a
        custom day. A run with nothing ticked and nothing typed studies the
        ruleset's own day rather than refusing: an empty set is somebody
        clearing the boxes, not somebody asking for no study, and the
        midwinter case is the one the controls turn on.

        Duplicates are dropped, so ticking winter and typing 06-21 is one run
        and not two identical ones over the top of each other.
        """
        days = [name for name in ASSESSMENT_DAYS if name in self.days and self.days[name].get()]
        typed = self.custom_day.get().strip()
        if typed:
            try:
                mmdd = parse_day(typed)
            except ValueError:
                days.append(typed)
            else:
                named = day_name(mmdd)
                if named not in days:
                    days.append(named)
        return days or ["winter"]

    def _day_label(self, day: str) -> str:
        """How a day reads on a queued job, or "" for the only day there is.

        Silent when one day is studied, because the label is then the tool's
        own name and has always been; a suffix on every job would be noise on
        the ordinary run. With several, the day is what tells two otherwise
        identical jobs apart while they wait.
        """
        if len(self.chosen_days()) < 2:
            return ""
        if day in ASSESSMENT_DAYS:
            return f" -- {ASSESSMENT_DAYS[day][1].split(', ')[-1]}"
        return f" -- {day}"

    def _window(self) -> tuple[str, str]:
        """The communal study's assessment window, as start and end.

        One field because it is one thought -- "eight to three" -- and two
        boxes invite a start with no end. Anything unparseable is passed as
        nothing rather than guessed at: the run then uses the ruleset's own
        window and says so, which is the safe way to be wrong.
        """
        typed = self.communal_window.get().strip()
        halves = [half.strip() for half in typed.replace("to", "-").split("-")]
        if len(halves) != 2 or not all(halves):
            return "", ""
        return halves[0], halves[1]

    def _tables_folder(self) -> Path | None:
        """The folder the tables go into, or ``None`` when none is named."""
        typed = self.tables.get().strip()
        return Path(typed) if typed else None

    def _listed(self, entry: ttk.Entry | Ticks | Chips) -> list[str]:
        return [part.strip() for part in entry.get().split(",") if part.strip()]

    def _wait_seconds(self) -> str:
        """The Archicad wait, in the seconds the command line wants.

        Minutes on screen because that is the unit the number is thought about
        in -- an export takes minutes -- and seconds on the command line
        because that is what ``--timeout`` takes. Anything unreadable falls
        back to the command line's own default rather than refusing to run: a
        mistyped wait should not stop a study, and the default is right for
        every project but the largest.
        """
        try:
            minutes = float(self.wait_min.get().strip())
        except ValueError:
            return f"{DEFAULT_TIMEOUT_SECONDS:g}"
        if minutes <= 0:
            return f"{DEFAULT_TIMEOUT_SECONDS:g}"
        return f"{minutes * 60.0:g}"

    def _flag(self, name: str, box: ttk.Entry) -> list[str]:
        """One option and its box, or nothing when the box is empty.

        Empty means the command's own default, which is the honest reading of
        a field nobody has filled in.
        """
        chosen = box.get().strip()
        return [name, chosen] if chosen else []

    def _prefix_flag(self, box: ttk.Entry) -> list[str]:
        """``--layer-prefix`` for one tool, or nothing when its box is empty.

        Empty means "the tool's own number", which is the CLI default, rather
        than an empty prefix -- that is refused there, and rightly, since it
        matches every layout in the project.
        """
        return self._flag("--layer-prefix", box)

    # -- what a run will put in the Layout Book, before it runs --------------
    #
    # Every sheet below is arithmetic over what is already on the page: the
    # days are the ticks, the hours are the fields, and the sun at each is
    # ``core.solar`` on a date and a latitude, which is milliseconds and never
    # touches Archicad. So the panel can be redrawn on every keystroke, and
    # what it shows is what Run will make rather than a picture of it.

    #: How many sheets each study deals per day, and what they are called.
    #: Kept here rather than worked out in the panel, because the panel is a
    #: view of this and the run is the other one -- two places that must
    #: agree, so they read from one list.
    def planned(self) -> list[Sheet]:
        """Every layout a run would make, in the order it would make them.

        Each study's drawings are dealt onto layouts by the same
        ``sheet_chunks`` the run calls, with the mode the Sheets row sends --
        or, when that row is blank and sends nothing, the mode each tool
        falls back to on its own. So the panel and the Layout Book agree
        about how many sheets a tick is worth and about which hours share
        one; and the days and hours come from the fields each study really
        reads, which for the shadow diagrams is their own Days row and not
        the ticks in Model.
        """
        made: list[Sheet] = []
        days = self.chosen_days()
        queued = {name for name, tick, _where in self._studies() if tick.get()}

        def deal(
            job: str,
            study: str,
            glyph: str,
            mark: str,
            kind: str,
            day: str,
            clocks: Sequence[str],
            mode: str | None = None,
            scale: str = "",
        ) -> None:
            """One set of drawings, dealt as ``mode`` says -- or a sheet each
            when the set is not one the Sheets row governs."""
            drawings = tuple(self._drawing(kind, day, clock) for clock in clocks)
            chunks = sheet_chunks(len(drawings), mode or "each")
            cells = cells_for(chunks)
            for part, (start, stop) in enumerate(chunks, start=1):
                nth = sum(1 for s in made if s.number.startswith(mark)) + 1
                made.append(
                    Sheet(
                        study=study,
                        glyph=glyph,
                        number=f"{mark}.{nth:02d}",
                        kind=kind,
                        day=self._day_name(day),
                        drawings=drawings[start:stop],
                        cells=cells,
                        part=part,
                        parts=len(chunks),
                        job=job,
                        scale=scale,
                    )
                )

        # The scales the commands place their drawings at. Read off the same
        # fields the run reads, or the command's own default where the window
        # sends none; the plan sheets and the model sheet are the layout
        # module's default and the communal plans are placed at 1:300.
        context_scale = f"1:{self.site_scale.get().strip() or '3000'}"
        eye_scale = f"1:{self.eye_scale.get().strip() or '500'}"
        plan_scale, communal_scale, shadow_scale = "1:200", "1:300", "1:1000"

        if SITE_JOB in queued:
            # Not at an hour of any day: these are drawn from the address.
            # The context sheet is at the scale the tab says; the site sheet
            # is fitted to the site from a list of scales the run chooses
            # from, which nothing here can know; the summary is a table.
            for which, on, scale in (
                ("Context Analysis", self.do_site_context.get(), context_scale),
                ("Site Analysis", self.do_site_site.get(), "to fit"),
                ("Summary of Controls", self.do_site_summary.get(), ""),
            ):
                if on:
                    deal(SITE_JOB, "Site analysis", "site", "ST", which, "", [""], scale=scale)
            # The models are not sheets and are not numbered as sheets: they
            # are geometry on their own layers, and the panel draws them as
            # that. The radius and the reach are the fields the run reads.
            radius = self.site_radius.get().strip() or "500"
            reach = self.site_future_reach.get().strip() or "100"
            for kind, on, extent in (
                (CONTEXT_MODEL, self.do_site_model.get(), f"{radius} m"),
                (FUTURE_MODEL, self.do_site_future.get(), f"{reach} m reach"),
            ):
                if on:
                    made.append(
                        Sheet(
                            study="Site analysis",
                            glyph="site",
                            number="",
                            kind=kind,
                            day=extent,
                            drawings=(Drawing(kind=kind, day="", time=""),),
                            job=SITE_JOB,
                            paper=False,
                        )
                    )

        if FACADE_JOB in queued:
            for day in days:
                # Not a sheet. The run colours the model itself -- a thin skin
                # of 3D elements over the facade, one colour per band -- and
                # the window does not ask for the views sheet, so what comes
                # out is geometry, and the panel draws it as geometry.
                made.append(
                    Sheet(
                        study="Solar analysis",
                        glyph="analysis",
                        number="",
                        kind=FACADE_MODEL,
                        day=self._day_name(day),
                        drawings=(self._drawing(FACADE_MODEL, day, "12:00"),),
                        job=FACADE_JOB,
                        paper=False,
                    )
                )
        bands, times = self._plan_kinds()
        if PLANS_JOB in queued:
            for day in days:
                if times:
                    deal(
                        PLANS_JOB,
                        "Solar analysis",
                        "analysis",
                        "SA",
                        "Apartments",
                        day,
                        self._clocks(self.instants, ("09:00", "12:00", "15:00")),
                        self._sheet_mode("each"),
                        scale=plan_scale,
                    )
                if bands:
                    deal(
                        PLANS_JOB,
                        "Solar analysis",
                        "analysis",
                        "SA",
                        "Apartments, ADG total",
                        day,
                        [""],
                        scale=plan_scale,
                    )
        if COMMUNAL_JOB in queued:
            for day in days:
                threshold = self.communal_hours.get().strip()
                if bands:
                    deal(
                        COMMUNAL_JOB,
                        "Solar analysis",
                        "analysis",
                        "SA",
                        "Communal open space",
                        day,
                        [""],
                        scale=communal_scale,
                    )
                if bands and threshold:
                    deal(
                        COMMUNAL_JOB,
                        "Solar analysis",
                        "analysis",
                        "SA",
                        f"Communal open space, {threshold} h or more",
                        day,
                        [""],
                        scale=communal_scale,
                    )
                if times:
                    deal(
                        COMMUNAL_JOB,
                        "Solar analysis",
                        "analysis",
                        "SA",
                        COMMUNAL_HOURLY,
                        day,
                        self._window_clocks(),
                        self._sheet_mode("one"),
                        scale=communal_scale,
                    )
                deal(COMMUNAL_JOB, "Solar analysis", "analysis", "SA", COMMUNAL_AREAS, day, [""])

        if SHADOW_JOB in queued:
            hours = self._clocks(self.shadow_hours, DEFAULT_SHADOW_HOURS.split(","))
            for day in self._shadow_days():
                deal(
                    SHADOW_JOB,
                    "Shadow diagram",
                    "shadow",
                    "SD",
                    "Shadow diagram",
                    day,
                    hours,
                    self._sheet_mode("two"),
                    scale=shadow_scale,
                )

        if SUN_EYE_JOB in queued:
            hours = self._clocks(self.eye_hours, [f"{hour:02d}:00" for hour in range(9, 16)])
            for day in days:
                deal(
                    SUN_EYE_JOB,
                    "Sun views",
                    "views",
                    "SV",
                    "Sun view",
                    day,
                    hours,
                    self._sheet_mode("two"),
                    scale=eye_scale,
                )

        return made

    def _drawing(self, kind: str, day: str, clock: str) -> Drawing:
        """One drawing of a set, with the sun where it will be for it."""
        azimuth, elevation = self._sun_at(day, clock) if clock else (None, None)
        return Drawing(
            kind=kind, day=self._day_name(day), time=clock, azimuth=azimuth, elevation=elevation
        )

    def _sheet_mode(self, fallback: str) -> str:
        """The word the Sheets row sends, or the one a tool falls back to when
        the row is blank and sends nothing. A word nobody can parse is sent as
        typed and refused by the run; the panel shows the fallback rather than
        nothing, which is the nearest it can get to a run that will not start."""
        chosen = self.sheets.get().strip()
        if not chosen:
            return fallback
        for title, word in self.SHEET_CHOICES:
            if chosen == title:
                return word
        try:
            return parse_sheet_mode(chosen)
        except ValueError:
            return fallback

    def _shadow_days(self) -> list[str]:
        """The days the shadow study draws: its own row, or the command's
        default when the row is blank -- which is what the run reads."""
        typed = [part.strip() for part in self.shadow_dates.get().split(",") if part.strip()]
        return typed or DEFAULT_SHADOW_DATES.split(",")

    def _window_clocks(self) -> list[str]:
        """Every whole hour of the communal window, which is how many hourly
        plans the run draws: eight to three is eight, nine to three is seven.
        A window nobody can parse is the ruleset's own, nine to three, which
        is what the run falls back to as well."""
        start, end = (_clock_text(half) for half in self._window())
        try:
            first, last = int(start.partition(":")[0]), int(end.partition(":")[0])
        except ValueError:
            first, last = 9, 15
        if not 0 <= first <= last <= 23:
            first, last = 9, 15
        return [f"{hour:02d}:00" for hour in range(first, last + 1)]

    @staticmethod
    def _clocks(box: ttk.Entry | Ticks, fallback: Sequence[str]) -> list[str]:
        """The times in a field, or the ones the study runs without them,
        each spelled the way a sheet is named for it."""
        times = [part.strip() for part in box.get().split(",") if part.strip()]
        return [_clock_text(part) for part in (times or list(fallback))]

    def _day_name(self, day: str) -> str:
        """How a day reads on a sheet: the date, not the season's name.

        A sheet in a Layout Book is filed by what it shows, and nobody files
        a drawing under "winter".
        """
        try:
            mmdd = parse_day(day)
        except ValueError:
            return day
        month, _, number = mmdd.partition("-")
        return f"{int(number)} {MONTHS[int(month) - 1]}"

    def _sun_at(self, day: str, clock: str) -> tuple[float | None, float | None]:
        """Where the sun is, for that day and that hour, at this project.

        ``None`` when nobody has set the project location. The panel then
        draws the sheet and says on it that there is no sun to draw, which is
        the honest answer -- a shadow at a guessed latitude is a drawing that
        looks right and is not.

        The timezone is the one the run itself passes, so the panel and the
        study cannot disagree about what 12:00 means. It matters: in December
        that is daylight saving, solar noon is nearer one o'clock, and a
        summer study set to noon is not a midday study.
        """
        if self.options.latitude is None or self.options.longitude is None:
            return (None, None)
        try:
            month, number = (int(piece) for piece in parse_day(day).split("-"))
            hour, _, minute = clock.partition(":")
            when = dt.datetime(
                int(self.year.get().strip() or "2024"),
                month,
                number,
                int(hour),
                int(minute or 0),
                tzinfo=resolve_timezone(TIMEZONE),
            )
            found = solar_position([when], self.options.latitude, self.options.longitude)
        except (ValueError, KeyError, TypeError, UnknownTimezoneError):
            # A day nobody can parse, a year that is not one, an hour typed as
            # words. None of those is worth refusing to draw the sheet for --
            # the sheet is still going to be made, it simply has no sun on it.
            return (None, None)
        return (float(found.azimuth_deg[0]), float(found.elevation_deg[0]))

    def _sheet_under(self, sheet: Sheet | None) -> None:
        """What the band says while the pointer is over a sheet in the dock.

        The one place the panel can say more than the drawing does: which way
        and how far, in figures, and that it has not been drawn yet. A sheet
        carrying several drawings lists the sun at each, and says which cells
        the run will leave empty.
        """
        if sheet is None:
            self.info.rest()
            return
        if not sheet.paper:
            if sheet.kind == FACADE_MODEL:
                detail = (
                    "A thin skin of 3D elements over every surface of "
                    "the building, one colour per band of sun hours, on its own "
                    "layers -- the massing-stage answer, read in the 3D window."
                )
            elif sheet.kind == FUTURE_MODEL:
                detail = (
                    f"The envelopes the controls allow on the lots within "
                    f"{sheet.day} of the site, at the street setback, as 3D geometry on "
                    "its own layers -- what could stand next door, for the shadow "
                    "diagrams to cast."
                )
            else:
                detail = (
                    f"The terrain and the buildings within {sheet.day} of the "
                    "site, as 3D geometry on its own layers from NSW open data -- the "
                    "context every other study casts against."
                )
            self.info.show(
                sheet.glyph,
                sheet.kind,
                f"{sheet.kind}, {sheet.day}.",
                detail,
                state="3D model",
            )
            return
        if not sheet.time:
            detail = _untimed_note(sheet)[1]
        elif sheet.elevation is None:
            detail = (
                "No project location, so there is no sun to put on it. Set one in "
                "Options > Project Preferences > Project Location, then press Refresh."
            )
        elif len(sheet.drawings) == 1:
            detail = f"Sun {sheet.elevation:.1f} degrees up, at azimuth {sheet.azimuth:.0f}."
            if sheet.reach is not None and sheet.study == "Shadow diagram":
                detail += (
                    f" The shadow falls towards {sheet.bearing:.0f} degrees and runs "
                    f"{sheet.reach:.1f} times the height of what casts it."
                )
        else:
            suns = "; ".join(
                f"{drawing.time} {drawing.elevation:.0f} degrees up at {drawing.azimuth:.0f}"
                for drawing in sheet.drawings
                if drawing.elevation is not None and drawing.azimuth is not None
            )
            detail = f"{len(sheet.drawings)} drawings on this layout, {sheet.part} of {sheet.parts}"
            if sheet.empty:
                detail += f", with {sheet.empty} cell{'' if sheet.empty == 1 else 's'} left empty"
            detail += f". Sun: {suns}."
        if sheet.kind == COMMUNAL_HOURLY:
            detail += " One such set per storey the space spans."
        if sheet.time:
            short = f"{sheet.kind}, {sheet.day} at {sheet.time}."
        elif sheet.day:
            short = f"{sheet.kind}, {sheet.day}."
        else:
            short = f"{sheet.kind}."
        self.info.show(sheet.glyph, sheet.number, short, detail, state="not drawn yet")

    def jobs(self) -> list[Job]:
        """The command lines the ticked boxes mean. Public, and pure, because
        this is the part worth testing without a window on screen."""
        port = str(self.ports[max(self.instance.current(), 0)]) if self.ports else ""
        common = ["--port", port, "--timeout", self._wait_seconds()]
        made: list[Job] = []

        if self.do_facade.get():
            args = [
                "massing",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_solar),
            ]
            for name in self._listed(self.subject):
                args += ["--subject-layer", name]
            # Without an IfcSpace there is nothing to fit the skin onto the
            # building against, and no IFC combination shows the zone layers.
            for name in self._listed(self.require) or self._zone_defaults():
                args += ["--require-layer", name]
            for name in self._listed(self.hide):
                args += ["--hide-layer", name]
            if self.combination.get():
                args += ["--layer-combination", self.combination.get()]
            args += self._band_args()
            args += [
                "--model-bands",
                "--model-flat" if self.do_floors.get() else "--no-model-flat",
                "--model-grid",
                self.grid_m.get().strip() or "0.5",
            ]
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            args += ["--year", self.year.get().strip() or "2024"]
            # One run per day ticked. Each carries its own date, and a
            # command names everything it makes after the day it studied,
            # so the sets stand beside each other in the project instead of
            # the second quietly replacing the first.
            for day in self.chosen_days():
                made.append(
                    Job(
                        FACADE_JOB + self._day_label(day),
                        [*args, *self._day_args(day), *self._sheet_args()],
                    )
                )

        if self.do_plans.get():
            bands, times = self._plan_kinds()
            args = [
                "archicad-run",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_solar),
                # --draw is the whole-day sheet, the apartments banded by their
                # hours of sun; --sheet makes the layouts for both kinds, and
                # without --draw it makes the plans at each time alone.
                "--draw" if bands else "--no-draw",
                "--sheet",
            ]
            if self.apartments.get():
                args += ["--apartment-zone-layer", self.apartments.get()]
            # Without these the layer alone decides, and a layer that mixes
            # dwellings with balconies and storage -- the ordinary case --
            # assesses all three as apartments. Two thirds of them have no
            # living room, so the building fails on zones nobody lives in.
            for name in self._listed(self.apartment_names):
                args += ["--apartment-zone-name", name]
            # The balcony layer is only named when something narrows it. On its
            # own, with the apartments' own layer chosen, it would take every
            # apartment for open space and leave the assessment with no
            # apartments at all.
            balcony_names = self._listed(self.balcony_names)
            if self.balconies.get() and (
                balcony_names or self.balconies.get() != self.apartments.get()
            ):
                args += ["--open-space-zone-layer", self.balconies.get()]
                for name in balcony_names:
                    args += ["--open-space-zone-name", name]
            if self.livable.get().strip():
                args += ["--livable-suffix", self.livable.get().strip()]
            if self.combination.get():
                args += ["--layer-combination", self.combination.get()]
            for name in self._listed(self.hide):
                args += ["--hide-layer", name]
            for stamp in self._listed(self.instants) if times else []:
                args += ["--plan-instant", stamp]
            args += self._band_args()
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            if self.shadow_subset.get():
                args += ["--layout-subset", self.shadow_subset.get()]
            if self.adg_subset.get():
                args += ["--adg-subset", self.adg_subset.get()]
            tables = self._tables_folder()
            if tables is not None:
                args += ["--csv", str(tables / APARTMENTS_TABLE)]
            args += ["--year", self.year.get().strip() or "2024"]
            # One run per day ticked. Each carries its own date, and a
            # command names everything it makes after the day it studied,
            # so the sets stand beside each other in the project instead of
            # the second quietly replacing the first.
            for day in self.chosen_days():
                made.append(
                    Job(
                        PLANS_JOB + self._day_label(day),
                        [*args, *self._day_args(day), *self._sheet_args()],
                    )
                )

        if self.do_communal.get():
            args = [
                "massing",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_solar),
            ]
            if self.communal.get():
                args += ["--zone-layer", self.communal.get()]
            for name in self._listed(self.communal_names):
                args += ["--zone-name", name]
            # The drawing is fitted onto the project from Zones the export
            # carries, and the communal layer alone gives one. A second zone
            # layer is what makes the plan placeable; those Zones are not
            # measured.
            for name in self._listed(self.require) or self._zone_defaults():
                args += ["--require-layer", name]
            if self.combination.get():
                args += ["--layer-combination", self.combination.get()]
            for name in self._listed(self.hide):
                args += ["--hide-layer", name]
            args += self._band_args()
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            if self.adg_subset.get():
                args += ["--zone-subset", self.adg_subset.get()]
            for name in self._listed(self.context):
                # Both: into the export, because a neighbour that is not
                # exported shades nothing, and out of the facade denominator.
                args += ["--require-layer", name, "--context-layer", name]
            if self.communal_height.get().strip():
                args += ["--zone-height", self.communal_height.get().strip()]
            if self.communal_grid.get().strip():
                args += ["--zone-grid", self.communal_grid.get().strip()]
            tables = self._tables_folder()
            if tables is not None:
                args += ["--zone-csv", str(tables / COS_AREAS_TABLE)]
                args += ["--zone-table", str(tables / COS_SCHEDULE_TABLE)]
            start, end = self._window()
            if start:
                args += ["--window-start", start]
            if end:
                args += ["--window-end", end]
            if self.communal_hours.get().strip():
                args += ["--zone-hours", self.communal_hours.get().strip()]
            # The areas always. The plans are what a reader looks at and the
            # areas are what they quote, and a study that draws the one
            # without writing the other invites a figure read off a colour.
            args += ["--zone-sheet", "--zone-stats"]
            bands, times = self._plan_kinds()
            if times:
                args += ["--zone-hourly"]
            if not bands:
                args += ["--no-zone-bands"]
            args += ["--year", self.year.get().strip() or "2024"]
            # One run per day ticked. Each carries its own date, and a
            # command names everything it makes after the day it studied,
            # so the sets stand beside each other in the project instead of
            # the second quietly replacing the first.
            for day in self.chosen_days():
                made.append(
                    Job(
                        COMMUNAL_JOB + self._day_label(day),
                        [*args, *self._day_args(day), *self._sheet_args()],
                    )
                )

        if self.do_shadows.get():
            args = [
                "shadows",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_shadow),
            ]
            # One legend row per flag, "NAME=layer,layer": the name is the
            # row's short name, which the drawing matches to the legend's
            # colour, and the layers are what find its geometry in the
            # add-on's model. An empty row is left off the sheet.
            for short, role, box in self.shadow_rows:
                layers = self._listed(box)
                if layers:
                    flag = "--shadow-source" if role == "baseline" else "--shadow-scenario"
                    args += [flag, f"{short}={','.join(layers)}"]
            for name in self._listed(self.terrain_layers):
                args += ["--shadow-terrain", name]
            args += ["--export", "native"]
            if self.do_shadow_all_hours.get():
                args += ["--shadow-all-hours"]
            if self.terrain_floor.get().strip():
                args += ["--shadow-terrain-floor", self.terrain_floor.get().strip()]
            if self.shadow_dates.get().strip():
                args += ["--shadow-date", self.shadow_dates.get().strip()]
            if self.shadow_hours.get().strip():
                args += ["--shadow-hour", self.shadow_hours.get().strip()]
            if self.shadow_storey.get().strip():
                args += ["--shadow-storey", self.shadow_storey.get().strip()]
            args += self._band_args()
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            if self.shadow_study_subset.get():
                args += ["--shadow-subset", self.shadow_study_subset.get()]
            args += ["--year", self.year.get().strip() or "2024"]
            args += self._sheet_args()
            made.append(Job(SHADOW_JOB, args))

        if self.do_sun_eyes.get():
            args = [
                "sun-views",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_sun),
            ]
            # Only what is filled in is sent, so the command's own defaults
            # -- read off the practice's diagrams -- hold for a blank field,
            # and a blank pen set keeps each view's own rather than naming
            # one the project does not have.
            for flag, field in (
                ("--pen-set", self.eye_pen_set),
                ("--override", self.eye_override),
                ("--base-combination", self.eye_base_combination),
                ("--scale", self.eye_scale),
                ("--title-block-mm", self.eye_title_block),
                ("--hour", self.eye_hours),
            ):
                if field.get().strip():
                    args += [flag, field.get().strip()]
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            args += ["--year", self.year.get().strip() or "2024"]
            # One run per day ticked. Each carries its own date, and a
            # command names everything it makes after the day it studied,
            # so the sets stand beside each other in the project instead of
            # the second quietly replacing the first.
            for day in self.chosen_days():
                made.append(
                    Job(
                        SUN_EYE_JOB + self._day_label(day),
                        [*args, *self._day_args(day), *self._sheet_args()],
                    )
                )

        if self.do_site.get() and self.site_address.get().strip():
            args = [
                "site",
                self.site_address.get().strip(),
                *common,
                *self._prefix_flag(self.prefix_site),
                *self._flag("--context-prefix", self.prefix_context),
            ]
            args += ["--context" if self.do_site_context.get() else "--no-context"]
            args += ["--site" if self.do_site_site.get() else "--no-site"]
            args += ["--summary" if self.do_site_summary.get() else "--no-summary"]
            if self.do_site_model.get():
                args += ["--model"]
                if self.site_radius.get().strip():
                    args += ["--model-radius", self.site_radius.get().strip()]
            if self.do_site_future.get():
                args += ["--future"]
                if not self.do_site_model.get() and self.site_radius.get().strip():
                    args += ["--model-radius", self.site_radius.get().strip()]
                if self.site_future_reach.get().strip():
                    args += ["--future-reach", self.site_future_reach.get().strip()]
                if self.site_future_setback.get().strip():
                    args += ["--future-setback", self.site_future_setback.get().strip()]
            if not self.do_site_location.get():
                args += ["--keep-location"]
            if self.site_scale.get().strip():
                args += ["--scale", self.site_scale.get().strip()]
            # The combobox says it in words; the command takes a keyword.
            args += [
                "--anchor",
                "site" if "origin" in self.site_anchor.get().lower() else "location",
            ]
            if self.site_out.get().strip():
                args += ["--out", self.site_out.get().strip()]
            made.append(Job(SITE_JOB, args))

        return made

    def _start(self) -> None:
        if self.run is not None and self.run.running:
            return
        if not self.ports:
            self._write("No Archicad to run against. Open a project, then Refresh.")
            return
        if self.options.tapir_missing:
            self._write("The Loriini add-on is not installed in this Archicad.")
            return
        if self.do_site.get() and not self.site_address.get().strip():
            self._write("Site analysis is ticked but has no address. Type one in its section.")
            return
        queued = self.jobs()
        if not queued:
            self._write("Nothing selected. Tick a study first.")
            return

        self.lines.clear()
        self.queued = queued
        self.go.config(state="disabled")
        self.cancel.config(state="normal")
        self.progress.config(mode="indeterminate")
        self.progress.start(12)
        self._next()

    def _next(self) -> None:
        if not self.queued:
            self._write("")
            self._write("Done.")
            self._finished()
            return
        job = self.queued.pop(0)
        self._write(f"── {job.label} ──")
        self._write("sun-study " + " ".join(job.args))
        self._write("")
        self.run = Run(
            job.args,
            on_line=lambda line: self.incoming.put(("line", line)),
            on_done=lambda code: self.incoming.put(("done", code)),
        )
        self.run.start()

    def _stop(self) -> None:
        self.queued.clear()
        if self.run is not None:
            self.run.stop()

    def _finished(self) -> None:
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.go.config(state="normal")
        self.cancel.config(state="disabled")

    def _drain(self) -> None:
        """Move the worker's lines into the widget, on the UI thread."""
        try:
            while True:
                kind, payload = self.incoming.get_nowait()
                if kind == "line":
                    self._write(str(payload))
                    continue
                code = int(payload)  # type: ignore[call-overload]
                if code == 0:
                    self._next()
                else:
                    self._write(f"[the study stopped, exit code {code}]")
                    self.queued.clear()
                    self._finished()
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def _write(self, line: str) -> None:
        """Keep the line, and show it if it says anything.

        Every line is kept; only the newest one with words in it is shown. The
        blanks and the ``──`` rules a run prints are there to space a
        transcript out, and a one-line note has nothing to space -- shown,
        they would blank the note at exactly the moments a study changes over,
        which is when it has most to say.
        """
        self.lines.append(line)
        if line.strip(" ─"):
            self.note.config(text=line)


def icon_path() -> Path | None:
    """Where the application icon is, packaged or not.

    A ``--onefile`` build unpacks itself to a temp directory on every start
    and points ``sys._MEIPASS`` at it, so the packaged path is neither beside
    the .exe nor beside this file. From a source checkout it is where it was
    written, at the top of the project.

    ``None`` rather than an exception when it is missing: an icon is how the
    window looks, not whether the study runs, and a checkout that has not been
    given one should still open.
    """
    packaged = getattr(sys, "_MEIPASS", None)
    root = Path(packaged) if packaged else Path(__file__).resolve().parents[3]
    found = root / "assets" / "loriini.ico"
    return found if found.is_file() else None


def wear_the_icon(window: tk.Tk) -> None:
    """Put the application icon on the window and everything it opens.

    ``--icon`` at build time carves the icon into the .exe as a Windows
    resource, which is what Explorer and the task bar read -- and Tk never
    looks at it. Without this the executable has the right icon in the folder
    and the window it opens wears the Tk feather, which is the sort of half a
    job somebody notices immediately.

    ``default=`` rather than a plain call, so the message boxes and dialogs
    raised later inherit it instead of each needing to be found and dressed.
    """
    found = icon_path()
    if found is None:
        return
    try:
        window.iconbitmap(default=str(found))  # type: ignore[no-untyped-call]
    except tk.TclError:
        # .ico is a Windows format and ``default=`` is a Windows option. This
        # is a Windows tool, but a developer on anything else should get a
        # plain window rather than a crash on the way to one.
        pass


def wanted_study(argv: Sequence[str]) -> str:
    """The study a palette button asked for, or nothing at all.

    Read by hand rather than with argparse because there is exactly one
    argument and the frozen executable's other half already owns the command
    line -- see ``app.__main__``. Anything it does not recognise is nothing,
    and ``ask_for`` ignores a name it does not know, so a stray argument
    cannot stop the window opening.
    """
    for before, value in pairwise(argv):
        if before == STUDY_FLAG:
            return value
    return ""


def launch(study: str = "") -> None:
    root = tk.Tk()
    wear_the_icon(root)
    window = Window(root)
    if study:
        window.ask_for(study)
    root.mainloop()
