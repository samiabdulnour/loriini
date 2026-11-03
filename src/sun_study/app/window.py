"""The window itself.

Shaped by one rule: a colleague should have to decide only what is genuinely a
decision. Everything that is a property of the *project* -- which layer carries
the apartments, which masters exist, which Layout Book subsets the practice
files this kind of drawing under -- is read from the open Archicad and offered
as a list, because the project already knows and a person mistyping it is the
commonest way a run measures the wrong thing.

Grouped by what comes out of it
-------------------------------
Seven tabs in two kinds. Two of them set the job up -- what the sheets are
drawn on, and what geometry leaves Archicad -- and five of them each draw one
thing: the site analysis, the solar analysis, the shadow diagram, the sun
views, the area calculation. That is how the work is asked for: a job wants
the shadow diagrams for Tuesday, and the person setting one up should be able
to read the whole of that study and none of the rest.

The two kinds are drawn as two groups in the strip, because that split is the
only thing that makes seven tabs a list rather than a bag: only the five can
be ticked, and so only the five can ever carry the queued mark.

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
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from sun_study import ADDON_FILE, PRODUCT, WEBSITE, licence
from sun_study.app import (
    claude_mcp,
    icons,
    licence_box,
    motion,
    overlay,
    preferences,
    probe,
    run_log,
    theme,
)
from sun_study.app.runner import Run
from sun_study.archicad import naming
from sun_study.archicad.shadows import LEGEND as SHADOW_LEGEND
from sun_study.archicad.sheeting import cells_for, parse_sheet_mode, sheet_chunks, sheet_title
from sun_study.cli import DEFAULT_SHADOW_HOURS
from sun_study.core.solar import UnknownTimezoneError, resolve_timezone, solar_position
from sun_study.licence import credential
from sun_study.rules.days import ASSESSMENT_DAYS, day_name, parse_day
from sun_study.site import theme as site_theme
from sun_study.site.pipeline import SITE_SCALES

if TYPE_CHECKING:
    from PIL import ImageTk

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

#: The site page's words for where the project origin goes on the site, and
#: the keyword the command takes for each; the first is the default.
ORIGIN_WORDS: dict[str, str] = {
    "Site centre": "centre",
    "Bottom-left corner": "bottom-left",
    "Bottom-right corner": "bottom-right",
    "Top-left corner": "top-left",
    "Top-right corner": "top-right",
}

#: The first choice of a site panel's Origin: the site where the project's
#: own location says it is (``--anchor location``). The others are
#: ``ORIGIN_WORDS``, each a point of the site put at the project origin.
PROJECT_LOCATION = "Project location"

#: The context sheet's scales, picked from rather than typed (D158): the
#: A1 map field at each, from a tight urban block to a station a long way
#: off. 1:3000 is the default.
CONTEXT_SCALES = ("1:1000", "1:1500", "1:2000", "1:2500", "1:3000", "1:4000", "1:5000")
#: And the site sheet's: fitted to the site, the default, or one of the
#: scales the run fits it from, held whatever the site's size.
FIT_THE_SITE = "Fit the site"
SITE_SHEET_SCALES = (FIT_THE_SITE, *(f"1:{scale}" for scale in SITE_SCALES))

#: Whether the site is turned so its long boundary runs level; the first is
#: the default.
TURN_WORDS: dict[str, bool] = {
    "To the project's north": False,
    "Long boundary level": True,
}

#: The house styles the sheets are drawn in, named as site-analyst.com's
#: STYLE row names them -- Flamingo, Kingfisher, Heron, Canary, a bird each,
#: the site sheet's in the context sheet's order, and only those four (D152);
#: and the ``--theme`` / ``--site-theme`` each sends. What each one looks like
#: is the row's tooltip.
CONTEXT_STYLES: dict[str, str] = {t.label: t.id for t in site_theme.THEMES}
SITE_STYLES: dict[str, str] = {
    site_theme.site_theme(t.id).label: t.id
    for t in site_theme.THEMES
    if site_theme.is_site_theme(t.id)
}


def _style_id(label: str, *, site: bool) -> str:
    """The theme a style row names, by its label or by a name it had before:
    a preset saved when Canary was Conure still says "Conure". A style that
    is gone, FUSE (D152), names nothing, and the sheet is drawn in the
    default."""
    styles = SITE_STYLES if site else CONTEXT_STYLES
    if label in styles:
        return styles[label]
    known = site_theme.is_site_theme(label) if site else site_theme.is_theme(label)
    if not known:
        return ""
    return site_theme.site_theme(label).id if site else site_theme.theme(label).id


#: Which of the Yield page's rows each answer to its Slabs question shows
#: (D140): the option's name unless each layer is an option, the layers the
#: answer reads, and the levels wherever the use is told by level.
YIELD_ROWS: dict[str, frozenset[str]] = {
    "Every slab showing": frozenset({"option", "levels"}),
    "Slabs on chosen layers": frozenset({"option", "layers", "levels"}),
    "A layer per use": frozenset({"option", "per_use"}),
    "A layer per option": frozenset({"option_layers", "levels"}),
}

#: The Renovation answers read off each slab, and what the run is told.
RENOVATION_STATUS_FLAGS: dict[str, str] = {
    "New only": "new",
    "Existing and new": "existing-and-new",
}


#: What RL project zero stands for when the 3D context is placed, and the
#: ``--datum`` each sends; the first is the default. Anything else typed in
#: the box is taken as that RL in metres.
LEVEL_WORDS: dict[str, str] = {
    "Project zero is the site's ground": "project",
    "Project zero is sea level (AHD)": "sea",
}

#: The timezone every study runs in. Named once here rather than five
#: times down in ``jobs``, because the sheets panel has to work out the
#: sun for the same instants the run will use, and two spellings of
#: "Australia/Sydney" is two answers to what noon means.
TIMEZONE = "Australia/Sydney"
#: Where the sheets panel puts the sun before a project says where it is:
#: Sydney, Archicad's own preset, as latitude and longitude.
STAND_IN_PLACE = (-33.8688, 151.2093)
#: How long a run waits on one Archicad command, in minutes. Not on the page
#: any more (D156): the field was for the IFC export, which on a big project
#: ran to minutes, and the studies no longer export that way. An hour is
#: still sent, so a genuinely slow command is waited on and a stuck
#: Archicad is not waited on for ever.
ARCHICAD_WAIT_MIN = 60


#: Short month names, for the date on a sheet.
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

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

#: The communal schedule's "no": the drawn table, as before. A word rather
#: than a blank, so choosing it is a choice a Refresh keeps -- a blank reads as
#: "never asked", and the office's schedule would be picked over it again.
NO_SCHEDULE = "None — the drawn table"
COMMUNAL_AREAS = "Communal areas"
#: The two outputs of the site study that are not sheets: geometry on its
#: own layers, drawn in the panel as geometry.
CONTEXT_MODEL = "Context model"
FUTURE_MODEL = "Future model"
#: And the facade study's output, which is the model coloured in bands of
#: sun hours -- a skin of 3D elements, not a sheet.
FACADE_MODEL = "Facade model"
#: The apartments' second whole-day sheet: the floor inside each flat banded
#: cell by cell, beside the sheet that gives each flat its one ADG figure.
APARTMENT_HEAT_MAP = "Apartments, floor heat map"
COMMUNAL_JOB = "solar analysis: communal open space"
#: The shadow diagram: the hours as 3D Documents from overhead, Archicad
#: casting the shadows, every legend row of an hour stacked in one drawing
#: (roadmap R1, D144). The ``shadow-plans`` command.
SHADOW_JOB = "shadow diagram"
#: Loriini's own caster, kept for the one drawing the documents cannot make:
#: the design's shadow at every hour, imported as fills into one drawing
#: (D144, D160). The ``shadows`` command, every hour and nothing else.
SHADOW_HOURS_JOB = "shadow diagram: every hour"
#: The every-hour drawing's two colours, the office's (D147); the first is
#: the command's own default.
SHADOW_HOURS_COLOURS = ("red", "blue")
SUN_EYE_JOB = "sun views"
#: The site analysis's four outputs, each a study of its own with its own
#: panel and its own run (D157): the two sheets, the controls table, and
#: the 3D context with its future.
SITE_CONTEXT_JOB = "site analysis: context"
SITE_SHEET_JOB = "site analysis: site"
SITE_CONTROLS_JOB = "site analysis: controls"
SITE_MODEL_JOB = "site analysis: 3D context"
SITE_JOBS = (SITE_MODEL_JOB, SITE_CONTEXT_JOB, SITE_SHEET_JOB, SITE_CONTROLS_JOB)
#: The yield analysis (roadmap R3): the office's feasibility sheet from the
#: massing slabs, an option a sheet of its own.
YIELD_JOB = "area and yield"
#: That sheet, as the panel draws it: a table beside the massing.
AREA_SHEET = "Yield Analysis"

#: What a queued study is called on a chip in the run bar and in the summary,
#: and which icon it wears. Keyed on the job name so the chips, the tab ticks
#: and the log all read from the same list -- a study called one thing on a
#: chip and another in the log is a study somebody cannot follow.
CHIPS: dict[str, tuple[str, str]] = {
    FACADE_JOB: ("Facade", "facade"),
    PLANS_JOB: ("Apartments", "apartments"),
    COMMUNAL_JOB: ("Communal", "communal"),
    SHADOW_JOB: ("Shadow diagram", "shadow"),
    SHADOW_HOURS_JOB: ("Every hour", "shadow"),
    SUN_EYE_JOB: ("Sun views", "views"),
    SITE_CONTEXT_JOB: ("Context", "site_analysis"),
    SITE_SHEET_JOB: ("Site", "site_analysis"),
    SITE_CONTROLS_JOB: ("Controls", "subset"),
    SITE_MODEL_JOB: ("3D context", "model"),
    YIELD_JOB: ("Yield", "yield"),
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
        frame_style = {theme.SIDEBAR: "Dock.TFrame", theme.PAGE: "Page.TFrame"}.get(
            ground, "TFrame"
        )
        bar_style = {
            theme.SIDEBAR: "Dock.Vertical.TScrollbar",
            theme.PAGE: "Page.Vertical.TScrollbar",
        }.get(ground, "Vertical.TScrollbar")
        super().__init__(parent, style=frame_style)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=ground)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.bar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style=bar_style,
        )
        self.bar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.content = ttk.Frame(self.canvas, style=frame_style)
        self._item = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._measured)
        self.canvas.bind("<Configure>", self._widened)
        #: The page settling into place as it opens (D134), while it is.
        self.sliding: motion.Slide | None = None

    def _measured(self, _event: object = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._show_bar_if_needed()

    def arrive(self, from_below: bool) -> None:
        """Open with the page settling in from a few pixels below, or
        above: which way the person went down the sidebar. Nothing is laid
        out again -- the page is one canvas item, and the item is moved --
        and the scroll region is re-measured once it has stopped, since it
        was measured with the page off its mark."""
        self.settle()
        offset = motion.DISTANCE if from_below else -motion.DISTANCE
        self.sliding = motion.Slide(self.canvas, self._item, offset, done=self._settled)

    def _settled(self) -> None:
        self.sliding = None
        self._measured()

    def settle(self) -> None:
        """Put the page where it belongs, now, if it was still arriving."""
        if self.sliding is not None:
            self.sliding.cancel()

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

    def glide(self, pixels: float) -> None:
        """A trackpad's two fingers, by the pixel rather than by the line, so
        the page follows the fingers the way every other Mac window does.
        Held inside the scroll region, for the same reason as ``spin``."""
        if pixels == 0 or not self.scrollable:
            return
        region = self.canvas.cget("scrollregion").split()
        tall = float(region[3]) - float(region[1]) if len(region) == 4 else 0.0
        if tall <= 0:
            return
        first, last = self.canvas.yview()
        shown = last - first
        self.canvas.yview_moveto(min(max(first - pixels / tall, 0.0), 1.0 - shown))


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

    # Tk 9 on a Mac sends a trackpad's two-finger scroll as an event of its
    # own, not as the wheel: bound to the wheel alone, the page scrolled for
    # a mouse and stood still under a trackpad. The deltas come packed into
    # one number, and Tk's own helper unpacks them.
    def glide(event: tk.Event[tk.Misc]) -> None:
        try:
            under = root.winfo_containing(event.x_root, event.y_root)
            _across, down = (
                float(part)
                for part in root.tk.splitlist(root.tk.call("tk::PreciseScrollDeltas", event.delta))
            )
        except (KeyError, tk.TclError, ValueError):
            return
        while under is not None:
            if isinstance(under, Scroller):
                under.glide(down)
                return
            under = getattr(under, "master", None)

    try:
        root.bind_all("<TouchpadScroll>", glide)
    except tk.TclError:
        # A Tk before 8.7 has no such event, and its trackpad is the wheel.
        pass


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
        typed: bool = False,
        empty: str = "",
    ) -> None:
        """``describe`` is what a row *reads* as, where the name alone does not
        say enough -- a zone name means little without its size, and ``BY``
        beside ``12 zones, 11 m2`` is a balcony to anybody. The value ticked is
        still the name, so what the caller gets back is what the study takes.

        ``typed`` adds a box for a name the list does not hold. Zone names
        only: a layer typed wrongly is a study that measures nothing, which
        is why layers are ticked, but a zone name is exactly what somebody
        reads off the plan, and a project read that found no Zones on the
        layer -- a hidden storey, a read that timed out, zones drawn since --
        otherwise leaves the Add button with nothing to offer and nothing to
        do. It also keeps names already chosen that the list lacks, rather
        than dropping them on the way out: a saved zone name the read did not
        see is still what the office meant.

        ``empty`` is what the list says when there is nothing in it, so the
        dialog explains itself instead of opening onto a blank pane.
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
        if typed:
            for name in chosen:
                if name not in self._available:
                    self._available.append(name)
        self._describe = dict(describe or {})
        self._empty = empty
        #: Ticked, kept as a set across filtering: narrowing the list must not
        #: quietly untick what has scrolled out of sight.
        self._ticked: set[str] = {name for name in chosen if name in set(self._available)}
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

        #: The box for a name the list does not hold; ``None`` for layers.
        self.typed: ttk.Entry | None = None
        if typed:
            own = ttk.Frame(outer)
            own.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            own.columnconfigure(1, weight=1)
            ttk.Label(own, text="Not listed").grid(row=0, column=0, padx=(0, 6))
            self.typed = ttk.Entry(own)
            self.typed.grid(row=0, column=1, sticky="ew")
            self.typed.bind("<Return>", lambda _event: self._add_typed())
            ttk.Button(own, text="Add name", command=self._add_typed).grid(
                row=0, column=2, padx=(6, 0)
            )

        buttons = ttk.Frame(outer)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        buttons.columnconfigure(0, weight=1)
        ttk.Button(buttons, text="Clear all", command=self._clear).grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Cancel", command=self._close).grid(row=0, column=1, padx=6)
        ttk.Button(buttons, text="Use these", command=self._accept).grid(row=0, column=2)

        self._repaint()
        # Straight to the box that can do something: with nothing listed the
        # search has nothing to search.
        (self.typed if self.typed is not None and not self._available else self.query).focus_set()
        self.bind("<Escape>", lambda _e: self._close())
        # The window manager's own X, which goes nowhere near the buttons.
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()

    def _repaint(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        self._boxes.clear()
        if not self._available and self._empty:
            ttk.Label(self._list, text=self._empty, foreground=HINT, wraplength=460).grid(
                row=0, column=0, sticky="w"
            )
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

    def _add_typed(self) -> None:
        """Put a typed name in the list, ticked. Spacing tidied, case kept:
        the study matches zone names without regard to case, and the chip
        should read the way it was typed."""
        if self.typed is None:
            return
        name = " ".join(self.typed.get().split())
        if not name:
            return
        known = {entry.casefold(): entry for entry in self._available}
        name = known.get(name.casefold(), name)
        if name not in self._available:
            self._available.append(name)
        self._ticked.add(name)
        self.typed.delete(0, "end")
        self.query.delete(0, "end")
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
AREA_TABLE = "Preliminary Yield Analysis.xlsx"

#: The levels the Yield page offers to tick: as the run names them, counted
#: from the ground, six basements down and forty floors up.
LEVEL_CHOICES: tuple[str, ...] = (
    *(f"B {n:02d}" for n in range(6, 0, -1)),
    "Ground",
    *(f"Level {n:02d}" for n in range(1, 41)),
)


def _level_meaning(level: str) -> str:
    if level == "Ground":
        return "The level nearest the project's ground storey; the lowest, with none named so."
    if level.startswith("B "):
        return f"{int(level[2:])} below the ground."
    return f"{int(level[6:])} above the ground."


#: The unit types the Yield page offers, with the share of the units and the
#: net lettable area each opens with: the office's feasibility sheet's five,
#: two of them at nothing, an average NLA of 72.5 m².
MIX_ROWS: tuple[tuple[str, str, str], ...] = (
    ("Studio", "0", "35"),
    ("1-bed", "20", "50"),
    ("2-bed", "70", "75"),
    ("3-bed", "10", "100"),
    ("4-bed", "0", "120"),
)

#: The shadow diagram's legend, one row each: the short name the run is given
#: (and matches to the legend's colour in ``archicad.shadows.LEGEND``),
#: whether it accumulates or is compared, and the row's label, hint and
#: explanation on the page. Listed as a person reads them, Proposed first;
#: sent in the legend's order, which is the order drawn, back to front, so
#: Proposed goes last and lies on top (``_legend_args``).
#:
#: The compared rows are named for no one control (D178): an office tests a
#: TOD envelope on one job, a SEARs massing or an ADG envelope on the next,
#: and Proposed 2 and 3 hold whichever this project compares.
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
        "PROPOSED",
        "scenario",
        "Proposed",
        "Proposed building envelope.",
        "The strongest blue, drawn last so it is on top: this is the one being applied for.",
    ),
    (
        "PROPOSED 2",
        "scenario",
        "Proposed 2",
        "A second envelope to compare, if there is one.",
        "The middle blue. A scenario: cast against every grey row and against "
        "no other blue one, so the proposals overlap on the sheet — which is "
        "the comparison. Drawn under Proposed and Proposed 3. Left empty, the "
        "row is left off the sheet.",
    ),
    (
        "PROPOSED 3",
        "scenario",
        "Proposed 3",
        "A third envelope to compare, if there is one.",
        "A lilac, drawn just under Proposed, so what shows of it is the fringe "
        "it adds beyond the proposal. Compared, not accumulated: putting this "
        "under a grey row instead tests it against itself and reads as a much "
        "smaller shadow. Left empty, the row is left off the sheet.",
    ),
)

#: A preset's rows from before the names were universal, and the rows they
#: are read into, in order: the first two filled take Proposed 2 and 3.
OLDER_SHADOW_ROWS: tuple[str, ...] = ("TOD", "SEARS", "ADG ENVELOPE")


def _wrap(row: tk.Misc, room: int) -> None:
    """Lay a row of buttons out in as many lines as ``room`` takes.

    The row's children are taken in the order they were laid out in, once,
    and dealt into lines left to right. Gridded, not placed, so the second
    line's buttons sit under the first's, which on a row of hours keeps the
    hours in columns. Nothing moves when the lines are the lines already.
    """
    kept: list[tuple[tk.Widget, int]] | None = getattr(row, "_flow_items", None)
    if kept is None:
        laid = [child for child in row.grid_slaves() if int(child.grid_info()["row"]) == 0]
        laid.sort(key=lambda child: int(child.grid_info()["column"]))
        kept = []
        for child in laid:
            padx = child.grid_info()["padx"]
            given = padx if isinstance(padx, (tuple, list)) else row.tk.splitlist(str(padx))
            pads = [int(float(pad)) for pad in given]
            kept.append((child, sum(pads) * (2 if len(pads) == 1 else 1)))
        row._flow_items = kept  # type: ignore[attr-defined]
    lines: list[tuple[int, int]] = []
    x = line = column = 0
    for child, pad in kept:
        need = child.winfo_reqwidth() + pad
        if column and x + need > room:
            line, column, x = line + 1, 0, 0
        lines.append((line, column))
        x += need
        column += 1
    if getattr(row, "_flow_lines", None) == lines:
        return
    row._flow_lines = lines  # type: ignore[attr-defined]
    for (child, _pad), (line, column) in zip(kept, lines, strict=True):
        child.grid_configure(row=line, column=column, pady=(2 if line else 0, 0))


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
        words: Mapping[str, str] | None = None,
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
            # A word on the face as well as the drawing. A row of three
            # pictures was only learnable by hovering each one, and the
            # window's rule is that every control says what it is without
            # being asked; the tooltip keeps the longer sentence.
            # A tile with a word is a segment of a segmented control: the word
            # alone, the way Archicad's own choice rows read. Only a tile with
            # no word keeps its drawing, since then the drawing is all it has.
            word = (words or {}).get(value, "")
            drawing = {} if word else icons.button_options(icon, 16)
            button = ttk.Button(
                self,
                text=word,
                style="Tile.TButton",
                command=partial(self._pick, value),
                padding=(12, 1) if word else (4, 1),
                **drawing,
            )
            button.grid(row=0, column=column, padx=(0, 2))
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
        # Words only, like a tile row: the day's name is the whole of what the
        # button has to say, and a drawing on a blue face is a smudge.
        button = ttk.Button(
            self,
            text=label,
            style="Tile.TButton",
            takefocus=False,
            command=partial(self._flip, variable),
            padding=(12, 1),
        )
        button.grid(row=0, column=len(self._items), padx=(0, 2))
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
        # As wide as its words: the theme's least button width made it a bar.
        more = ttk.Button(self, text="+ Add", style="Add.TButton", width=0, command=self._add)
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
    """The card at the foot of the sidebar that explains what you are on.

    It replaces two things. The grey line printed under every control, forty
    of which at once is a wall nobody reads; and the ``Tooltip`` Toplevel,
    which opened over the window 450 ms after the pointer stopped, covered the
    thing you were pointing at, went away while you were still reading it, and
    could not be reached from the keyboard at all.

    It was a strip across the foot of the window, three lines high and the
    window wide, which cost every page that much height on a laptop. The
    sidebar has room to spare under its list of pages, and a card there is
    always in the same place, never covers a field, and answers Tab as well
    as the pointer -- so it lives there, and the page gets the height back.
    It only grows up into the sidebar's empty space, so nothing on the page
    moves as the pointer crosses it.
    """

    #: How wide the words run: the sidebar, less its gutter and the card's.
    WRAP = 180
    #: The most a detail is allowed to say before it is cut at a sentence. A
    #: card taller than the sidebar's spare room would push the pages up.
    LONGEST = 420

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Help.TFrame", padding=(12, 10, 12, 12))
        self.columnconfigure(1, weight=1)

        self.drawing = ttk.Label(self, style="Help.TLabel")
        self.drawing.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.title = ttk.Label(self, text="", style="HelpTitle.TLabel")
        self.title.grid(row=0, column=1, sticky="w")
        #: What the thing under the pointer is set to, at the right of the
        #: heading. Not called ``state``: that is ttk's own method on every
        #: widget, and a label by that name shadows it.
        self.aside = ttk.Label(self, text="", style="HelpState.TLabel")
        self.aside.grid(row=0, column=2, sticky="e", padx=(6, 0))
        self.short = ttk.Label(
            self, text="", style="Help.TLabel", justify="left", wraplength=self.WRAP
        )
        self.short.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.detail = ttk.Label(
            self, text="", style="HelpHint.TLabel", justify="left", wraplength=self.WRAP
        )
        self.detail.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        #: What it says when the pointer is on nothing. Never empty: a card
        #: that blanks itself is dead space, which is exactly what the log was.
        self._resting: tuple[str, str, str, str] = ("", "", "", "")

    @classmethod
    def _cut(cls, text: str) -> str:
        """At most ``LONGEST`` characters, cut at the end of a sentence."""
        if len(text) <= cls.LONGEST:
            return text
        kept = text[: cls.LONGEST]
        stop = kept.rfind(". ")
        return kept[: stop + 1] if stop > 0 else kept.rstrip() + "…"

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
        self.drawing.config(**icons.state_options(glyph, 16))
        self.title.config(text=title, style="HelpIdle.TLabel" if idle else "HelpTitle.TLabel")
        self.aside.config(text=state)
        if state:
            self.aside.grid()
        else:
            self.aside.grid_remove()
        self.short.config(text=short)
        self.detail.config(text=self._cut(detail))
        if detail:
            self.detail.grid()
        else:
            self.detail.grid_remove()

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
    SHEET_W = 288
    #: A4 landscape, 297 x 210.
    SHEET_H = 204
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
        #: The sheets and filing line last drawn, so a refill that would draw
        #: the same panel again does nothing.
        self._shown: tuple[tuple[Sheet, ...], str] | None = None
        self.folded = False

        # -- open -----------------------------------------------------------
        self.open_view = ttk.Frame(self, style="Dock.TFrame")
        head = ttk.Frame(self.open_view, style="Dock.TFrame", padding=(16, 12, 8, 4))
        head.pack(side="top", fill="x")
        ttk.Label(head, text="Sheets", style="DockTitle.TLabel").pack(side="left")
        self.tally = ttk.Label(head, text="0", style="Badge.TLabel")
        self.tally.pack(side="left", padx=(8, 0))
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
        # Where the sheets are filed, said only when the Layout Book has a
        # subset to file them in: an empty line here read as a gap under the
        # header, before the first study.
        self.filed = ttk.Label(self.open_view, text="", style="DockHint.TLabel")
        self.pane = Scroller(self.open_view, ground=theme.SIDEBAR)
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
        # The spine says what is behind it in words, not as a bare figure: a
        # lone "0" over a sideways "Sheets" read as a counter of something
        # nobody could name. And all of it opens the panel, not only the
        # chevron -- the strip is thirty pixels wide and the chevron eleven.
        self.spine = tk.Canvas(
            self.shut_view,
            width=self.FOLDED - 6,
            height=self.SPINE_TALL,
            background=theme.SIDEBAR,
            highlightthickness=0,
            cursor="hand2",
        )
        self._spine_text = self.spine.create_text(
            (self.FOLDED - 6) // 2,
            self.SPINE_TALL // 2,
            text=self._spell(0),
            angle=90,
            fill=theme.BODY,
            font=(theme.FACE, theme.points(9)),
        )
        self.spine.pack(side="top", pady=(6, 0))
        for widget in (self.shut_view, self.spine):
            widget.bind("<Button-1>", lambda _event: self.fold(False))
        self.spine.bind("<Enter>", lambda _event: self._light(True))
        self.spine.bind("<Leave>", lambda _event: self._light(False))
        Tooltip(
            self.spine,
            "Brings the panel back: every sheet the ticked studies will make, "
            "drawn at the hour and the day it is for.",
            title="Show the sheets",
        )

        self.open_view.pack(fill="both", expand=True)

    #: How tall the folded spine is: room for "No sheets yet" set sideways.
    SPINE_TALL = 140

    @staticmethod
    def _spell(papers: int) -> str:
        """What the folded spine says about the sheets behind it."""
        if not papers:
            return "No sheets yet"
        return "1 sheet" if papers == 1 else f"{papers} sheets"

    def _light(self, on: bool) -> None:
        """Tint the spine's words under the pointer, as a link is."""
        self.spine.itemconfigure(self._spine_text, fill=theme.ON_ACCENT if on else theme.BODY)

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
        # Asked on every tick and keystroke, and most of those change nothing
        # the panel shows. Redrawing it anyway cost a sync about 70 ms of
        # destroying and drawing a dozen canvases on Windows, which is the lag
        # felt typing into a field. The miniatures read nothing but the sheets
        # and the filing line, so those two say whether it is the same panel.
        shown = (tuple(sheets), filed)
        if shown == self._shown:
            return
        self._shown = shown
        for old in self._drawn:
            old.destroy()
        self._drawn = []
        # The count is of sheets. A model in the panel is drawn there because
        # the run makes it, and not counted here because it is not one.
        papers = sum(1 for sheet in sheets if sheet.paper)
        self.tally.config(text=str(papers))
        self.spine.itemconfigure(self._spine_text, text=self._spell(papers))
        self.filed.config(text=filed)
        if filed:
            self.filed.pack(side="top", fill="x", padx=16, pady=(0, 6), before=self.pane)
        else:
            self.filed.pack_forget()

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
                # A hairline over each study, then its name and its count:
                # the groups of the panel, the way the sidebar groups pages.
                rule = ttk.Frame(self.pane.content, style="Rule.TFrame", height=1)
                rule.pack(side="top", fill="x", padx=16, pady=(10, 0))
                self._drawn.append(rule)
                head = ttk.Frame(self.pane.content, style="Dock.TFrame")
                head.pack(side="top", fill="x", padx=16, pady=(8, 2))
                ttk.Label(head, text=sheet.study, style="DockStudy.TLabel").pack(side="left")
                ttk.Label(
                    head,
                    text=str(sum(1 for other in sheets if other.study == sheet.study)),
                    style="DockCount.TLabel",
                ).pack(side="right")
                self._drawn.append(head)
            if sheet.day and sheet.day != day:
                day = sheet.day
                line = ttk.Label(self.pane.content, text=day, style="DockDay.TLabel")
                line.pack(side="top", anchor="w", padx=16, pady=(0, 6))
                self._drawn.append(line)
            self._drawn.append(self._draw(sheet))

    #: How far the paper sits in from the canvas edge: room for the pixel of
    #: lift under it and the rim's antialiasing round it.
    LIFT = 2
    #: The lift: ink at a tenth over the panel's chrome, the figure the
    #: button faces were lifted by before D132 flattened them.
    LIFT_GREY = "#DADADA"

    def _draw(self, sheet: Sheet) -> tk.Canvas:
        """One sheet, at the master's proportions with its title block.

        Drawn in millimetres and scaled, so the geometry sits where it will
        sit on the paper and the title block really is the 40 mm the General
        tab is set to. The sheet number, the scale and the drawing title are
        drawn larger than they will print: a label nobody can read identifies
        nothing, and a thumbnail is not a print preview.

        The paper is rounded, since D133: the button's eight pixels, the
        button's edge, and one pixel of lift under it, so a sheet in the
        panel is a thing of the window like the controls beside it. It was
        square until then, on the grounds that paper has corners; put beside
        the rounded window of D132 the square read as a hole in it.
        """
        lift = self.LIFT
        paper = tk.Canvas(
            self.pane.content,
            width=self.SHEET_W + lift * 2,
            height=self.SHEET_H + lift * 2,
            background=theme.SIDEBAR,
            highlightthickness=0,
        )
        paper.pack(side="top", padx=16 - lift, pady=(0, 10 - lift))
        # A model is not a sheet, so it is not drawn as one: the geometry
        # alone, with no paper and no shadow under it.
        (draw_sheet if sheet.paper else draw_model)(paper, sheet, self.SHEET_W, self.SHEET_H)
        paper.move("all", lift, lift)
        # The lift: the same shape a pixel lower, under everything else, as
        # the button faces had it. One pixel, because the panel's chrome is
        # light and a sheet is not meant to float off it.
        if sheet.paper:
            under = _rounded(
                paper,
                lift,
                lift + 1,
                lift + self.SHEET_W - 1,
                lift + self.SHEET_H,
                SHEET_RADIUS,
                fill=self.LIFT_GREY,
                outline="",
            )
            paper.tag_lower(under)

        def lit(on: bool) -> None:
            # The sheet under the pointer takes the lemon edge every button
            # takes, which is what says the figures in the band below belong
            # to *this* one.
            resting = theme.FACE_EDGE if sheet.paper else ""
            paper.itemconfigure(
                "edge", outline=theme.ACCENT_EDGE if on else resting, width=1.5 if on else 1
            )
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
#: The block and the plate of flats sit in the middle of the site: a plan
#: pushed to one side of its boundary read as a drawing laid out wrong.
BLOCK_MM = (101.0, 84.0, 161.0, 124.0)
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
#: Six flats to a plate, for the apartment sheets, centred on the site.
FLATS_MM = tuple(
    (83.0 + across * 32.0, 71.0 + down * 33.0, 115.0 + across * 32.0, 104.0 + down * 33.0)
    for down in range(2)
    for across in range(3)
)
SHADOW_GREY = "#8E8E8E"
#: The office yield sheet's legend: the podium lilac, the tower yellow.
PODIUM = "#DCCBF7"
TOWER = "#FFF4A8"


def _hours_in(text: str) -> list[str]:
    """The hours in a comma list, each spelled the way a sheet is named."""
    return [_clock_text(part) for part in text.split(",") if part.strip()]


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
#: The site and its neighbours, with a margin: what a drawing is fitted to.
SITE_FIT_MM = (62.0, 36.0, 200.0, 172.0)


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


def _untimed_note(sheet: Sheet) -> str:
    """What a sheet with no hour on it is instead: the sentence the band says
    when the pointer is on it."""
    if sheet.study == "Site analysis":
        return (
            "Drawn from the address in Site analysis and NSW open data, so it has "
            "no hour and no sun on it."
        )
    if sheet.kind == COMMUNAL_AREAS:
        return (
            "The measured area of every communal space, tabled on a sheet of its "
            "own, so it has no hour and no sun on it."
        )
    if sheet.kind == AREA_SHEET:
        return (
            "Worked from the massing slabs' areas, so it has no hour and no sun on "
            "it: the table on a layout of its own, and the view named on the page "
            "beside it."
        )
    return (
        "The whole assessment window on one plan, banded by hours of sun, so it "
        "is not at any one hour and the Sheets row does not deal it."
    )


#: The one size every word on a sheet miniature is set in. One size, one
#: weight, one ink: the sheet's name, its hours, its scale and its number are
#: read at a glance across the panel, and three sizes in three greys at 300
#: px read as clutter, not as a hierarchy.
SHEET_TEXT = 8
#: Pixels between a cell's hour and the drawing over it.
LABEL_GAP = 3
#: Pixels either side of a sheet number inside its chip.
CHIP_PAD = 5


def draw_sheet(
    paper: tk.Canvas, sheet: Sheet, width: int, height: int, *, block_mm: float = 48.0
) -> None:
    """One layout, drawn on a canvas at the size the panel has room for.

    Laid out the way the run lays the sheet out: the drawings in the field,
    and the title block down the right at the width General sets. Since
    D136 the block is drawn as a title block is printed -- its lines of text
    as bars too small to read, which is what they are at this size -- and at
    its foot the scale and the sheet number, the number in the chip the
    sidebar wears. Under the field, level with them, the sheet's name and
    then its hour and which of a pair it is. No north: the master carries
    one. Everything is set in one size; the second line and the scale are
    the hint grey, the way a card's caption is.
    """
    scale = width / SHEET_MM_W

    def x(value: float) -> float:
        return value * scale

    face = tkfont.Font(root=paper, font=_face(SHEET_TEXT, False))

    def words(
        mm_x: float,
        mm_y: float,
        text: str,
        *,
        room: float = 0,
        anchor: Literal["sw", "s"] = "sw",
        fill: str = theme.INK,
    ) -> int:
        # One line, always: a line wrapped on a baseline grows *up*, over
        # whatever is drawn above it. Too long for its room, it is cut short.
        if room and face.measure(text) > x(room):
            while text and face.measure(text + "…") > x(room):
                text = text[:-1]
            text = text.rstrip(" ,") + "…"
        return int(
            paper.create_text(
                x(mm_x),
                x(mm_y),
                text=text,
                anchor=anchor,
                fill=fill,
                font=_face(SHEET_TEXT, False),
            )
        )

    def bar(mm_x: float, mm_y: float, long: float, tint: str = theme.LINE) -> None:
        """A line of the block's text, as the bar it is at this size."""
        _rounded(
            paper, x(mm_x), x(mm_y), x(mm_x + long), x(mm_y + 1.6), x(0.8), fill=tint, outline=""
        )

    # -- the paper, and the block's rule down it -----------------------------
    # Drawn, not left to the canvas: the canvas is the panel's grey, so the
    # sheet can lift off it. Rounded at the button's radius (D133), and so
    # without the ink frame a sheet is printed with: the paper's own edge is
    # the frame, and a second line a few pixels inside a curve reads as a
    # misregistration. The block's rule is the divider grey, not ink, for
    # the same reason the cards' rules are. The edge is an item of its own,
    # the last one drawn, so the panel can turn it lemon under the pointer
    # and nothing on the sheet lies over the lemon.
    _rounded(paper, 0, 0, width - 1, height - 1, SHEET_RADIUS, fill=theme.SURFACE, outline="")
    inset = 5.0
    left = SHEET_MM_W - inset - block_mm
    paper.create_line(x(left), 0, x(left), height, fill=theme.LINE)

    # -- the drawings ----------------------------------------------------
    #
    # One drawing takes the field. Several are dealt onto the grid the run
    # will use, each with its hour under it -- and a cell the run leaves
    # empty is a faint dashed frame, because the short second sheet of a pair
    # really does have a hole in it.
    field = (10.0, 10.0, left - 5.0, 166.0)
    # The room under a cell for its hour: the hour's own line and a gap,
    # measured, and not a figure in millimetres. The sheet scales with the
    # panel and the type does not, and on Windows, where eight points are
    # eleven pixels, the 13 mm this was left the hour touching the drawing.
    under_mm = max(13.0, (face.metrics("linespace") + LABEL_GAP) / scale)
    if sheet.cells <= 1:
        frames = [field]
    else:
        frames = _grid(sheet.cells, field, gap=2.5)
    for index, frame_mm in enumerate(frames):
        if index >= len(sheet.drawings):
            paper.create_rectangle(
                x(frame_mm[0]),
                x(frame_mm[1]),
                x(frame_mm[2]),
                x(frame_mm[3]),
                outline=theme.LINE,
                dash=(3, 3),
            )
            continue
        drawing = sheet.drawings[index]
        if len(frames) > 1:
            # The hour centred under its own cell, in the hint grey: under
            # the cell, it sat on the drawing below.
            words(
                (frame_mm[0] + frame_mm[2]) / 2,
                frame_mm[3],
                drawing.time,
                room=frame_mm[2] - frame_mm[0],
                anchor="s",
                fill=theme.HINT,
            )
            frame_mm = (frame_mm[0], frame_mm[1], frame_mm[2], frame_mm[3] - under_mm)
        frame = (x(frame_mm[0]), x(frame_mm[1]), x(frame_mm[2]), x(frame_mm[3]))
        _draw_drawing(paper, sheet.study, drawing, frame)

    # -- what this sheet is, on the two bottom baselines -------------------
    # The name, and under it what tells this sheet from the next of its
    # study: the hour, and which of a pair it is. Not the day, which the
    # panel prints once over the sheets of that day; not what the sun is
    # doing, which the card in the sidebar says while the pointer is on it.
    saying = [sheet.time] if sheet.time else []
    if sheet.parts > 1:
        saying.append(f"({sheet.part} of {sheet.parts})")
    first, second = 183.0, 200.0
    words(12, first, sheet.kind, room=left - 18)
    if saying:
        words(12, second, "   ".join(saying), room=left - 18, fill=theme.HINT)

    # -- the title block -------------------------------------------------
    # Four lines of text at its head and two lower down, as the master
    # prints them, then a rule that boxes its two fields at the foot: the
    # scale in the hint grey and the sheet number in the chip, level with the
    # two lines beside them. The chip is the sidebar's -- lemon-tinted, a
    # hairline edge, ink on it -- and turns lemon under the pointer with the
    # sheet's edge, which is why it carries a tag. The chip is centred on
    # the number's capitals, not on the line Tk gives it: that line keeps
    # room under the baseline the figures never use, and the number sat at
    # the top of its chip.
    middle = (left + SHEET_MM_W - inset) / 2
    for row in range(4):
        bar(left + 7, 14 + row * 5, 34 - (row % 2) * 10)
    bar(left + 7, 118, 34, theme.FACE_EDGE)
    bar(left + 7, 124, 22)
    paper.create_line(x(left), x(166), x(SHEET_MM_W - inset), x(166), fill=theme.LINE)
    # "NTS", as a drawing set says it, for a sheet that has no scale.
    words(middle, first, sheet.scale or "NTS", anchor="s", fill=theme.HINT)
    caps = x(second) - _cap_drop(face)
    # As wide as the number and its padding, within the block: a fixed 34 mm
    # was narrower than "SD.01" on Windows, and the number ran into its edges.
    reach = min(face.measure(sheet.number) / 2 + CHIP_PAD, x(block_mm / 2) - 2)
    reach = max(x(17), reach)
    _rounded(
        paper,
        x(middle) - reach,
        caps - x(7.5),
        x(middle) + reach,
        caps + x(7.5),
        x(5),
        fill=theme.ACCENT_TINT,
        outline=theme.ACCENT_EDGE,
        tags="chip",
    )
    words(middle, second, sheet.number, anchor="s")

    # -- the edge, last ------------------------------------------------
    # Over everything, and hollow: lit lemon under the pointer, it rims the
    # whole sheet. The button's edge at rest, as every face has.
    _rounded(
        paper,
        0,
        0,
        width - 1,
        height - 1,
        SHEET_RADIUS,
        fill="",
        outline=theme.FACE_EDGE,
        tags="edge",
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

    Since D136 the ground carries what the model carries: the terrain's
    contours, the streets between the blocks and the trees on their verges,
    one block in the ochre the run colours a heritage item, and our building
    in the boundary's red so it is told from the neighbours at a glance. The
    radius the data is fetched for is a grey ring on the ground.

    The future model is the same neighbourhood with the envelopes the
    controls allow drawn over the lots within reach, taller and hollow, so
    the eye reads "what could stand here" rather than "what does". The
    facade model's skin is banded by storey on the heat maps' own ramp, the
    top floors in the most sun and the foot in the neighbours' shade.
    """
    future = sheet.kind == FUTURE_MODEL
    facade = sheet.kind == FACADE_MODEL
    mid_x, mid_y, k = width * 0.5, height * 0.40, width / 34.0

    def at(x: float, y: float, z: float) -> tuple[float, float]:
        return (mid_x + (x - y) * 0.866 * k, mid_y + (x + y) * 0.5 * k - z * k)

    def face(
        points: Sequence[tuple[float, float, float]],
        fill: str,
        outline: str,
        dash: tuple[int, ...] = (),
        width: float = 1.0,
    ) -> None:
        flat: list[float] = []
        for x, y, z in points:
            flat += at(x, y, z)
        paper.create_polygon(flat, fill=fill, outline=outline, dash=dash, width=width)

    def block(
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        tall: float,
        tints: tuple[str, str, str],
        outline: str,
        dash: tuple[int, ...] = (),
        width: float = 1.0,
    ) -> None:
        # The two faces towards the viewer, then the top over them.
        face(
            ((x0, y1, 0), (x1, y1, 0), (x1, y1, tall), (x0, y1, tall)),
            tints[1],
            outline,
            dash,
            width,
        )
        face(
            ((x1, y0, 0), (x1, y1, 0), (x1, y1, tall), (x1, y0, tall)),
            tints[2],
            outline,
            dash,
            width,
        )
        face(
            ((x0, y0, tall), (x1, y0, tall), (x1, y1, tall), (x0, y1, tall)),
            tints[0],
            outline,
            dash,
            width,
        )

    # -- the ground, with its contours and streets ------------------------
    reach = 11.5
    face(
        ((-reach, -reach, 0), (reach, -reach, 0), (reach, reach, 0), (-reach, reach, 0)),
        "#EEEEEE",
        SHADOW_GREY,
    )
    for level, wobble in ((-7.0, 1.2), (-3.5, 0.6), (4.0, -0.8), (8.0, 0.4)):
        points: list[float] = []
        for step in range(0, 13):
            x = -reach + step * (2 * reach / 12)
            y = level + wobble * math.sin(step * 0.9) - 0.15 * x
            points += at(x, y, 0)
        paper.create_line(points, fill=CONTOUR, smooth=True)
    for near, far in ((-4.4, -3.6), (3.6, 4.4)):
        face(((-reach, near, 0), (reach, near, 0), (reach, far, 0), (-reach, far, 0)), ROAD, "")
        face(((near, -reach, 0), (far, -reach, 0), (far, reach, 0), (near, reach, 0)), ROAD, "")
    # The radius the data is fetched for, drawn on the ground.
    ring: list[float] = []
    for step in range(48):
        angle = math.tau * step / 48
        ring += at(math.cos(angle) * reach * 0.92, math.sin(angle) * reach * 0.92, 0)
    paper.create_polygon(ring, fill="", outline=RING, dash=(4, 3), smooth=True)

    # -- the blocks, far to near ---------------------------------------
    grey = ("#F3F3F3", "#C5C5C5", "#DDDDDD")
    # Painter's order: what is further from the viewer -- smaller x + y --
    # is drawn first, and the site takes its turn among the blocks. The
    # fifth block is the heritage item; the site is ours, in red.
    standing = [
        (*block_, HERITAGE if index == 4 else grey, theme.INK, False)
        for index, block_ in enumerate(MODEL_BLOCKS)
    ] + [(*MODEL_SITE, SITE_BLOCK, BOUNDARY, True)]
    for x0, y0, x1, y1, tall, tints, edge, ours in sorted(standing, key=lambda b: b[0] + b[1]):
        if facade and ours:
            # The building itself, its two visible faces banded by storey on
            # the heat maps' ramp -- the top in the most sun, the foot in the
            # neighbours' shade -- which is the skin the study builds, and
            # the sun over it, because the bands are about the sun.
            steps = 6
            for step in range(steps):
                z0, z1 = tall * step / steps, tall * (step + 1) / steps
                face(
                    ((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)),
                    HOURS_RAMP[min(6, step + 1)],
                    "",
                )
                face(
                    ((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)),
                    HOURS_RAMP[min(6, step)],
                    "",
                )
            block(x0, y0, x1, y1, tall, (HOURS_RAMP[6], "", ""), theme.INK)
            sun_x, sun_y = at(x1 + 2.5, y0 - 4.0, tall + 2.5)
            for ray in range(8):
                angle = ray * math.pi / 4
                paper.create_line(
                    sun_x + math.cos(angle) * 9,
                    sun_y + math.sin(angle) * 9,
                    sun_x + math.cos(angle) * 13,
                    sun_y + math.sin(angle) * 13,
                    fill=theme.SUN,
                    capstyle="round",
                )
            paper.create_oval(
                sun_x - 6.5, sun_y - 6.5, sun_x + 6.5, sun_y + 6.5, fill=LIT, outline=theme.SUN
            )
            continue
        block(x0, y0, x1, y1, tall, tints, edge, width=1.5 if ours else 1.0)
        if future and not ours and max(abs(x0 + x1), abs(y0 + y1)) / 2 < 8.0:
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
    if not facade:
        # Street trees on the verges, as the model carries them from the
        # register.
        for tree_x, tree_y in (
            (-6.5, -5.2),
            (1.5, -5.4),
            (7.0, -5.0),
            (-6.0, 5.3),
            (0.5, 5.2),
            (6.5, 5.5),
        ):
            tx, ty = at(tree_x, tree_y, 0.35)
            paper.create_oval(tx - 3.2, ty - 3.2, tx + 3.2, ty + 3.2, fill=CANOPY, outline="")

    # -- what it is ----------------------------------------------------
    #
    # Named first, like a sheet; then the day or the reach, and what the
    # geometry is, in a line -- not what it is not.
    # In the sheets' one style and on their two baselines, so a model in the
    # panel reads as one more item in the same set.
    mm = width / SHEET_MM_W
    paper.create_text(
        12 * mm,
        183 * mm,
        text=sheet.kind,
        anchor="sw",
        fill=theme.INK,
        font=_face(SHEET_TEXT, False),
    )
    # Short enough for one line at the panel's width: a second line would
    # grow up into the name over it.
    if facade:
        what = "skin banded by hours of sun"
    elif future:
        what = "envelopes the controls allow"
    else:
        what = "terrain and neighbours in 3D"
    line = f"{sheet.day} · {what}" if sheet.day else what
    paper.create_text(
        12 * mm,
        198 * mm,
        text=line,
        anchor="sw",
        fill=theme.HINT,
        font=_face(SHEET_TEXT, False),
    )
    # The hover edge, invisible at rest: the item the panel turns lemon, drawn
    # last so that it lies over the model.
    _rounded(paper, 0, 0, width - 1, height - 1, SHEET_RADIUS, fill="", outline="", tags="edge")


#: The drawing set's palette on a miniature, the same one the design review
#: drew them in: the site boundary red and dash-dotted, the massing grey in a
#: heavy line, the neighbours light, sun amber, and shade and shadow hatched.
#: The greys are the window's own, neutral since D153 as the window's are
#: (they were warm from D133). The boundary's red and the pin's blue
#: are a drawing set's conventions, not the interface's colours, and stay.
BOUNDARY = "#C0392B"
BOUNDARY_DASH = (6, 2, 1, 2)
MASSING = "#E4E4E4"
NEIGHBOUR = "#F2F2F2"
NEIGHBOUR_EDGE = "#A1A1A1"
ROAD = "#D8D8D8"
RING = "#B3B3B3"
LIT = "#F2C86B"
HATCH = "#5A5A5A"
#: What the drawings add since D136, each the colour of a thing the run
#: draws and never decoration: the LEP wash on the context sheet, the
#: aerial's lots and the canopies and contours over them on the site sheet,
#: the shadow diagram's two shadows -- the town's own, and the proposal's
#: extra one in the blue the diagram tells it apart with -- the glazing the
#: sun views light, the tinted heading row of a schedule, and the pale amber
#: of the sun's light on the plans, pre-blended because a Tk canvas has no
#: alpha. The ground a courtyard's samples are drawn on, and the yield
#: workbook's green heading row, are the two colours of those two sheets.
ZONING = "#FBE1C6"
ZONING_EDGE = "#E9A96B"
LOT = "#EAEAEA"
TERRACE = "#DFDFDF"
CANOPY = "#B5CFAA"
CONTOUR = "#E2C98C"
PARK = "#DCE7D2"
SHADOW_CAST = "#CDCDCD"
SHADOW_EXTRA = "#B9CDEF"
GLAZING = "#F4D35E"
BEAM = "#FBEFD6"
COURT_GROUND = "#EEEEEE"
YIELD_HEAD = "#CFE3C4"
HERITAGE = ("#F3E3C4", "#D9B97E", "#E8D0A0")
SITE_BLOCK = ("#F6DAD5", "#C9776C", "#E2A69D")
#: A schedule's words, as the design review drew them: the heading in ink
#: at four fifths over its tint, the labels in the caption grey at a bit
#: over half, the figures in the hint grey at under half -- pre-blended,
#: since a Tk canvas has no alpha.
TABLE_HEAD_WORDS = site_theme.blend(theme.INK, theme.ACCENT_TINT, 0.8)
TABLE_LABEL = site_theme.blend(theme.CAPTION, theme.SURFACE, 0.55)
TABLE_FIGURE = site_theme.blend(theme.HINT, theme.SURFACE, 0.45)
#: The context sheet's town: the three lots along a block's street, as
#: shares of its length -- a wide house, a narrow one, a middling one --
#: dealt to the columns of blocks in turn; the site's column takes the one
#: that is even about its middle, so the site, its middle lot, is centred.
#: And the site in Flamingo's coral, the one accent.
CONTEXT_STREETS = (
    (1.35, 0.8, 0.95),
    (0.85, 1.3, 0.85),
    (0.9, 0.85, 1.35),
    (1.15, 1.15, 0.8),
)
CONTEXT_SITE_STREET, CONTEXT_SITE_LOT = 1, 1
CONTEXT_SITE = site_theme.blend(site_theme.CORAL, theme.SURFACE, 0.6)
#: A sheet's corner, and a drawn block's: the button's radius on the paper,
#: and two pixels on every block and boundary in the drawing, so the drawing
#: is as rounded as the paper it is on and no more.
SHEET_RADIUS = 8
BLOCK_RADIUS = 2
#: Hours of sun, none to five and more: the communal legend's seven steps,
#: from the blue of no sun through green and yellow to the orange of a full
#: day. The two heat maps and the facade's skin are banded on the one ramp,
#: so the panel has one way of saying hours of sun.
HOURS_RAMP = ("#6B8ED6", "#9BB8E3", "#B5CFAA", "#EFE39A", "#F2C86B", "#E6A04E", "#D4702E")
#: The two answers to the ADG's two hours: the sun's amber for a flat that
#: reaches them, the grey of no sun for one that falls short. Not blue:
#: on these sheets blue is the pin and the rail line, never an answer.
MEETS, FALLS_SHORT = LIT, "#E6E6E6"


def _rounded(
    paper: tk.Canvas, x0: float, y0: float, x1: float, y1: float, radius: float, **how: Any
) -> int:
    """A rectangle with rounded corners -- canvas pixels -- as one item.

    Tk's canvas rounds nothing by itself, so each corner is walked as a
    quarter circle in straight steps, a step to every pixel and a half of
    the arc, and the whole is one plain polygon. It was a ``smooth``
    polygon with each corner's cuts given twice until the panel's chips
    showed what that costs: the doubled points are sides of no length, and
    the outline's joins at them leave a notch where a curve meets its side.
    Hollow if ``fill`` is empty, dashed if asked, like a rectangle.
    """
    radius = max(0.0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    steps = max(1, math.ceil(radius * math.pi / 2 / 1.5))
    flat: list[float] = []
    # Clockwise from the top right, each corner from the side before it
    # to the side after.
    for centre_x, centre_y, start in (
        (x1 - radius, y0 + radius, -90.0),
        (x1 - radius, y1 - radius, 0.0),
        (x0 + radius, y1 - radius, 90.0),
        (x0 + radius, y0 + radius, 180.0),
    ):
        for step in range(steps + 1 if radius else 1):
            angle = math.radians(start + 90.0 * step / steps)
            flat += [centre_x + radius * math.cos(angle), centre_y + radius * math.sin(angle)]
    return int(paper.create_polygon(flat, **how))


def _cap_drop(font: tkfont.Font) -> float:
    """How far the foot of a line of text -- its ``s`` anchor -- lies below
    the middle of its capitals and figures, in pixels.

    Tk centres a line by its whole height, which counts the room under the
    baseline that a descender would take: a sheet number or a station's
    letter has none, so centred that way it rides high in its chip or its
    roundel. Inter's capitals are three quarters of its ascent.
    """
    return float(font.metrics("ascent")) * 0.75 / 2 + font.metrics("descent")


def _hatch(
    paper: tk.Canvas, points: Sequence[tuple[float, float]], *, spacing: float = 3.0
) -> None:
    """Hatch a convex outline -- canvas pixels -- with lines at 45 degrees.

    Tk on a Mac draws no stipple, so a shadow is hatched by hand: each line
    ``y = x + c`` is cut where it crosses the outline's edges. The outlines
    are convex (a hull, or a rectangle), so each line crosses twice.
    """
    if len(points) < 3:
        return
    offsets = [py - px for px, py in points]
    step = spacing * math.sqrt(2)
    c = min(offsets) + step / 2
    edges = list(zip(points, [*points[1:], points[0]], strict=True))
    while c < max(offsets):
        hits: list[tuple[float, float]] = []
        for (x0, y0), (x1, y1) in edges:
            denominator = (y1 - y0) - (x1 - x0)
            if abs(denominator) < 1e-9:
                continue
            along = (c - (y0 - x0)) / denominator
            if 0.0 <= along <= 1.0:
                hits.append((x0 + along * (x1 - x0), y0 + along * (y1 - y0)))
        if len(hits) >= 2:
            first, last = min(hits), max(hits)
            paper.create_line(*first, *last, fill=HATCH)
        c += step


def _clip_to(
    points: Sequence[tuple[float, float]], area: tuple[float, float, float, float]
) -> list[tuple[float, float]]:
    """A convex polygon cut to a rectangle, one edge at a time
    (Sutherland-Hodgman): what is left of it inside ``area``."""
    left, top, right, foot = area
    edges: tuple[tuple[Callable[[tuple[float, float]], bool], int, float], ...] = (
        (lambda point: point[0] >= left, 0, left),
        (lambda point: point[0] <= right, 0, right),
        (lambda point: point[1] >= top, 1, top),
        (lambda point: point[1] <= foot, 1, foot),
    )
    shape = list(points)
    for inside, axis, at in edges:
        if not shape:
            break
        kept: list[tuple[float, float]] = []
        for index, here in enumerate(shape):
            before = shape[index - 1]
            if inside(here) != inside(before):
                share = (at - before[axis]) / (here[axis] - before[axis])
                kept.append(
                    (
                        before[0] + (here[0] - before[0]) * share,
                        before[1] + (here[1] - before[1]) * share,
                    )
                )
            if inside(here):
                kept.append(here)
        shape = kept
    return shape


#: The ring the communal study's stand-in building makes round its
#: courtyard, and the courtyard itself, in the sheet's millimetres: a
#: courtyard building, because that is the shape a reader knows a communal
#: open space by.
RING_MM = (74.0, 68.0, 188.0, 160.0)
COURT_MM = (90.0, 84.0, 172.0, 142.0)
#: Where the sun is held on a plan: inside the site boundary with room for
#: its rays, on the side it stands.
SUN_BOX_MM = (78.0, 50.0, 184.0, 158.0)


def _sun_spot(azimuth: float) -> tuple[float, float]:
    """Where the sun is drawn for an azimuth: on the site's margin, the way
    it stands from the middle of the plate, north up."""
    mid_x, mid_y = (SITE_MM[0] + SITE_MM[2]) / 2, (SITE_MM[1] + SITE_MM[3]) / 2
    dx, dy = math.sin(math.radians(azimuth)), -math.cos(math.radians(azimuth))
    reach = math.inf
    if abs(dx) > 1e-9:
        reach = min(reach, ((SUN_BOX_MM[2] if dx > 0 else SUN_BOX_MM[0]) - mid_x) / dx)
    if abs(dy) > 1e-9:
        reach = min(reach, ((SUN_BOX_MM[3] if dy > 0 else SUN_BOX_MM[1]) - mid_y) / dy)
    if not math.isfinite(reach):
        reach = 0.0
    return (mid_x + dx * reach, mid_y + dy * reach)


def _sun_side(azimuth: float) -> Literal["east", "north", "west"]:
    """Which wall of a flat the sun comes in by, north up."""
    across = math.sin(math.radians(azimuth))
    if across > 0.35:
        return "east"
    if across < -0.35:
        return "west"
    return "north"


def _draw_drawing(
    paper: tk.Canvas, study: str, drawing: Drawing, frame: tuple[float, float, float, float]
) -> None:
    """One drawing, fitted into ``frame`` -- canvas pixels -- the way
    ``FRAME_MM`` sits on a full sheet.

    Each study puts a different thing on its sheets, so each is drawn as
    that thing, and since D136 in that thing's own colours: the sun in amber
    on the plans, the communal courtyard banded by hours, the shadow
    diagram's two shadows, the white town of a sun view. A shadow under a
    site-analysis sheet, or under a view taken from the sun -- where by
    construction there are no shadows to see -- is a miniature of something
    the run will not make.
    """
    kind = drawing.kind
    # The two site sheets fill their frame: the map and the aerial run to
    # the sheet's margin on paper, so they run to the field's edge here.
    if kind == "Context Analysis":
        _draw_context(paper, frame)
        return
    if kind == "Site Analysis":
        _draw_site(paper, frame)
        return

    fx0, fy0, fx1, fy1 = frame
    # Fitted to the site and what stands round it, not to the whole square
    # the drawing sits in on a sheet: in a cell of four that margin was a
    # third of the cell, and the plan a postage stamp in the middle of it.
    # The schedules and the office's sheet keep the square.
    fit = FRAME_MM if kind in (AREA_SHEET, COMMUNAL_AREAS, "Summary of Controls") else SITE_FIT_MM
    frame_w, frame_h = fit[2] - fit[0], fit[3] - fit[1]
    k = min((fx1 - fx0) / frame_w, (fy1 - fy0) / frame_h)
    ox = fx0 + ((fx1 - fx0) - frame_w * k) / 2 - fit[0] * k
    oy = fy0 + ((fy1 - fy0) - frame_h * k) / 2 - fit[1] * k

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
        radius: float = BLOCK_RADIUS,
    ) -> None:
        """A block, rounded by two pixels (D133); ``radius=0`` for a band
        that has to meet the next band without a notch."""
        _rounded(
            paper,
            px(mm[0]),
            py(mm[1]),
            px(mm[2]),
            py(mm[3]),
            radius,
            fill=fill,
            outline=outline,
            dash=dash,
            width=width,
        )

    def poly(
        points: Sequence[tuple[float, float]], *, fill: str, outline: str = "", width: float = 1.0
    ) -> None:
        flat: list[float] = []
        for point_x, point_y in points:
            flat += [px(point_x), py(point_y)]
        paper.create_polygon(flat, fill=fill, outline=outline, width=width)

    def line(x0: float, y0: float, x1: float, y1: float, fill: str, width: float = 1.0) -> None:
        paper.create_line(px(x0), py(y0), px(x1), py(y1), fill=fill, width=width, capstyle="round")

    def disc(mm_x: float, mm_y: float, radius: float, fill: str, outline: str = "") -> None:
        paper.create_oval(
            px(mm_x - radius),
            py(mm_y - radius),
            px(mm_x + radius),
            py(mm_y + radius),
            fill=fill,
            outline=outline,
        )

    def sun(mm_x: float, mm_y: float, radius: float) -> None:
        """The sun with its rays, in the window's amber: the one playful
        mark on a sheet."""
        for ray in range(8):
            angle = ray * math.pi / 4
            line(
                mm_x + math.cos(angle) * radius * 1.45,
                mm_y + math.sin(angle) * radius * 1.45,
                mm_x + math.cos(angle) * radius * 2.1,
                mm_y + math.sin(angle) * radius * 2.1,
                theme.SUN,
            )
        disc(mm_x, mm_y, radius, LIT, theme.SUN)

    def boundary() -> None:
        """The site's boundary, red and dash-dotted as a drawing set draws it."""
        box(SITE_MM, outline=BOUNDARY, dash=BOUNDARY_DASH, radius=BLOCK_RADIUS + 1)

    def massing() -> None:
        """The building: grey, in the heaviest line on the drawing."""
        box(BLOCK_MM, fill=MASSING, outline=theme.INK, width=1.5)

    def plate(
        tints: Sequence[str],
        inside: Callable[[int, tuple[float, float, float, float]], None] | None = None,
    ) -> None:
        """The flats of a plate as one block of cells, edge to edge, in the
        building's heavy outline; ``inside`` draws what is in each flat."""
        left = min(flat[0] for flat in FLATS_MM)
        top = min(flat[1] for flat in FLATS_MM)
        right = max(flat[2] for flat in FLATS_MM)
        foot = max(flat[3] for flat in FLATS_MM)
        wide, tall = (right - left) / 3, (foot - top) / 2
        for index, tint in enumerate(tints):
            cell = (
                left + (index % 3) * wide,
                top + (index // 3) * tall,
                left + (index % 3 + 1) * wide,
                top + (index // 3 + 1) * tall,
            )
            box(cell, fill=tint, outline=theme.INK, width=0.6, radius=0)
            if inside is not None:
                inside(index, cell)
        box((left, top, right, foot), outline=theme.INK, width=1.5)

    def shifted(
        rect: tuple[float, float, float, float], far: float, bearing: float
    ) -> list[tuple[float, float]]:
        """The shadow a block throws at this sun, as the hull of the block
        and its shifted copy. Exact for the sun even though the block is
        schematic."""
        shift = (math.sin(math.radians(bearing)) * far, -math.cos(math.radians(bearing)) * far)
        corners = [
            (corner_x + dx, corner_y + dy)
            for corner_x in (rect[0], rect[2])
            for corner_y in (rect[1], rect[3])
            for dx, dy in ((0.0, 0.0), shift)
        ]
        return _hull(corners)

    def town(skip: tuple[float, float, float, float] | None) -> None:
        """The lots round the site, each with its roof's ridge."""
        for lot in TOWN_MM:
            if skip is not None and not (
                lot[2] < skip[0] or lot[0] > skip[2] or lot[3] < skip[1] or lot[1] > skip[3]
            ):
                continue
            box(lot, fill=NEIGHBOUR, outline=NEIGHBOUR_EDGE, width=0.8)
            line(
                lot[0] + 3,
                (lot[1] + lot[3]) / 2,
                lot[2] - 3,
                (lot[1] + lot[3]) / 2,
                NEIGHBOUR_EDGE,
                0.6,
            )

    def ring() -> None:
        """The courtyard building, in the massing grey and its heavy line."""
        box(RING_MM, fill=MASSING, outline=theme.INK, width=1.4, radius=0)

    def court_edge() -> None:
        box(COURT_MM, outline=theme.INK, width=1.1, radius=0)

    def court_trees() -> None:
        for tree_x, tree_y, radius in (
            (104.0, 130.0, 7.0),
            (158.0, 98.0, 6.0),
            (146.0, 133.0, 5.0),
        ):
            disc(tree_x, tree_y, radius, CANOPY)

    def court_cells(threshold: bool) -> None:
        """The courtyard gridded the way the study samples it, each cell in
        the band of its hours: most sun towards the open south side, least
        under the north wing."""
        cols, rows, gap = 8, 6, 0.7
        cell_w = (COURT_MM[2] - COURT_MM[0]) / cols
        cell_h = (COURT_MM[3] - COURT_MM[1]) / rows
        box(COURT_MM, fill=COURT_GROUND, radius=0)
        for gx in range(cols):
            for gy in range(rows):
                off = abs(gx - (cols - 1) / 2)
                value = round(0.8 + gy * 1.05 - off * 0.7 + ((gx * 3 + gy * 5) % 3) * 0.45)
                value = max(0, min(6, value))
                tint = (MEETS if value >= 3 else FALLS_SHORT) if threshold else HOURS_RAMP[value]
                box(
                    (
                        COURT_MM[0] + gx * cell_w + gap / 2,
                        COURT_MM[1] + gy * cell_h + gap / 2,
                        COURT_MM[0] + (gx + 1) * cell_w - gap / 2,
                        COURT_MM[1] + (gy + 1) * cell_h - gap / 2,
                    ),
                    fill=tint,
                    radius=0.4,
                )

    def words_bar(x0: float, y: float, x1: float, fill: str, thick: float = 3.0) -> None:
        """A word too small to read, as the rounded bar it is at this size:
        a line with round ends, which Tk draws cleaner than a polygon three
        pixels high."""
        paper.create_line(
            px(x0 + thick / 2),
            py(y),
            px(x1 - thick / 2),
            py(y),
            fill=fill,
            width=thick * k,
            capstyle="round",
        )

    def table(cols: int, rows: int, head: str) -> None:
        """A schedule: a tinted heading row, then a row per space or per
        control, each label and figure held inside its own column.

        Rounded at twice a block's radius, as a card is, and its words in
        the lighter greys the design review drew them in: in the heavier
        ones, seven rows of dark bars read as a barcode. The edge is drawn
        last, so the heading's tint does not cover it."""
        t = (78.0, 54.0, 184.0, 154.0)
        corner = BLOCK_RADIUS * 2
        box(t, fill=theme.SURFACE, radius=corner)
        box((t[0], t[1], t[2], t[1] + 13), fill=head, radius=corner)
        box((t[0], t[1] + 8, t[2], t[1] + 13), fill=head, radius=0)
        line(t[0], t[1] + 13, t[2], t[1] + 13, theme.LINE)
        words_bar(t[0] + 6, t[1] + 6.5, t[0] + 46, TABLE_HEAD_WORDS, 4.0)
        step = (t[3] - t[1] - 13) / rows
        col_w = (t[2] - t[0]) / cols
        for row in range(1, rows + 1):
            y = t[1] + 13 + step * row
            if row < rows:
                line(t[0] + 4, y, t[2] - 4, y, theme.LINE)
            label = min(col_w - 10, 22 + (row % 3) * 5)
            words_bar(t[0] + 5, y - step / 2, t[0] + 5 + label, TABLE_LABEL)
            figure = min(12.0, col_w - 10)
            for col in range(1, cols):
                right = t[0] + (col + 1) * col_w - 5
                words_bar(right - figure, y - step / 2, right, TABLE_FIGURE)
        for col in range(1, cols):
            line(t[0] + col * col_w, t[1] + 13, t[0] + col * col_w, t[3], theme.LINE)
        box(t, outline=theme.FACE_EDGE, radius=corner)

    if kind.startswith("Apartments") and "total" in kind.lower():
        # Each flat against the two hours: the share that meets it in the
        # sun's amber, the share that falls short in the grey of no sun.
        boundary()
        plate((MEETS, MEETS, FALLS_SHORT, MEETS, FALLS_SHORT, MEETS))
        sun(131, 54, 4.5)
    elif kind.startswith("Apartments") and drawing.azimuth is None:
        # The whole day: the floor of each flat gridded and banded cell by
        # cell on the legend's ramp.
        seeds = (6, 5, 3, 4, 1, 6)

        def pixels(index: int, flat: tuple[float, float, float, float]) -> None:
            cell_w, cell_h = (flat[2] - flat[0]) / 4, (flat[3] - flat[1]) / 3
            for gx in range(4):
                for gy in range(3):
                    value = (
                        seeds[index]
                        - abs(gx - 1.5) * 0.9
                        - gy * 0.8
                        + ((gx + gy + index) % 2) * 0.6
                    )
                    box(
                        (
                            flat[0] + gx * cell_w,
                            flat[1] + gy * cell_h,
                            flat[0] + (gx + 1) * cell_w,
                            flat[1] + (gy + 1) * cell_h,
                        ),
                        fill=HOURS_RAMP[max(0, min(6, round(value)))],
                        radius=0,
                    )

        boundary()
        plate([theme.SURFACE] * len(FLATS_MM), pixels)
    elif kind.startswith("Apartments"):
        # One hour: the sun with its rays where it stands, its light reaching
        # the window wall of every flat it is in, and inside each lit flat
        # the amber wedge where the plans show it falling across the floor.
        azimuth = drawing.azimuth
        assert azimuth is not None
        boundary()
        lit = _lit_flats(azimuth)
        side = _sun_side(azimuth)
        sun_x, sun_y = _sun_spot(azimuth)
        for index in sorted(lit):
            f = FLATS_MM[index]
            if side == "east":
                wall = ((f[2], f[1]), (f[2], f[3]))
            elif side == "west":
                wall = ((f[0], f[1]), (f[0], f[3]))
            else:
                wall = ((f[0], f[1]), (f[2], f[1]))
            poly([(sun_x, sun_y), wall[0], wall[1]], fill=BEAM)

        def wedge(index: int, flat: tuple[float, float, float, float]) -> None:
            if index not in lit:
                return
            f = flat
            mid = (f[0] + f[2]) / 2
            if side == "east":
                points = [
                    (f[2], f[1] + 2),
                    (f[2], f[3] - 2),
                    (f[0] + 6, f[3] - 6),
                    (f[0] + 10, f[1] + 8),
                ]
            elif side == "west":
                points = [
                    (f[0], f[1] + 2),
                    (f[0], f[3] - 2),
                    (f[2] - 6, f[3] - 6),
                    (f[2] - 10, f[1] + 8),
                ]
            else:
                points = [
                    (f[0] + 2, f[1]),
                    (f[2] - 2, f[1]),
                    (mid + 8, f[3] - 6),
                    (mid - 8, f[3] - 6),
                ]
            poly(points, fill=LIT)

        plate([theme.SURFACE] * len(FLATS_MM), wedge)
        sun(sun_x, sun_y, 5)
    elif kind == COMMUNAL_HOURLY:
        # The courtyard at one hour: in sun, with the shadow the building
        # throws across it -- which is what the hourly plan measures.
        boundary()
        ring()
        box(COURT_MM, fill=HOURS_RAMP[4], radius=0)
        reach, bearing, azimuth = drawing.reach, drawing.bearing, drawing.azimuth
        if reach is not None and bearing is not None and azimuth is not None:
            wings = [(RING_MM[0], RING_MM[1], RING_MM[2], COURT_MM[1])]
            if _sun_side(azimuth) == "east":
                wings.append((COURT_MM[2], COURT_MM[1], RING_MM[2], COURT_MM[3]))
            elif _sun_side(azimuth) == "west":
                wings.append((RING_MM[0], COURT_MM[1], COURT_MM[0], COURT_MM[3]))
            for wing in wings:
                held = _clip_to(shifted(wing, min(reach, 3.0) * 7.0, bearing), COURT_MM)
                if len(held) >= 3:
                    poly(held, fill=HOURS_RAMP[0])
        court_edge()
        court_trees()
        if azimuth is not None:
            sun(131 + math.sin(math.radians(azimuth)) * 50, 54, 3.5)
    elif kind in (COMMUNAL_AREAS, "Summary of Controls"):
        table(
            4 if kind == COMMUNAL_AREAS else 2,
            6 if kind == COMMUNAL_AREAS else 7,
            theme.ACCENT_TINT,
        )
    elif kind.startswith("Communal open space"):
        # The courtyard over the whole day, banded by hours -- or, on the
        # sheet for the threshold, in the two answers.
        boundary()
        ring()
        court_cells(threshold="or more" in kind)
        court_edge()
        court_trees()
        sun(178, 54, 4.5)
    elif kind == AREA_SHEET:
        # The office's workbook: the building in section, floor on floor --
        # the podium in the legend's lilac, the tower in its yellow -- and
        # beside it the green-headed table, a bar per floor as long as its
        # area, so the schedule reads as the building it adds up.
        storey, floors, podium = 8.5, 13, 2
        ground = FRAME_MM[3] - 18
        for floor in range(floors):
            low, high = ground - storey * floor, ground - storey * (floor + 1)
            under = floor < podium
            left, right = (66.0, 114.0) if under else (74.0, 106.0)
            box(
                (left, high, right, low),
                fill=PODIUM if under else TOWER,
                outline=theme.INK,
                width=0.6,
                radius=0,
            )
        line(60, ground, 122, ground, theme.INK)
        t = (130.0, 50.0, 200.0, 160.0)
        box(t, fill=theme.SURFACE, outline=theme.FACE_EDGE)
        box((t[0], t[1], t[2], t[1] + 10), fill=YIELD_HEAD)
        box((t[0], t[1] + 6, t[2], t[1] + 10), fill=YIELD_HEAD, radius=0)
        for row in range(13):
            y = t[1] + 10 + (t[3] - t[1] - 10) * (row + 0.5) / 13
            under = row >= 11
            box((t[0] + 4, y - 1.5, t[0] + 14, y + 1.5), fill=theme.HINT, radius=1)
            long = 36.0 if under else 26.0 - max(0, row - 7) * 1.5
            box(
                (t[0] + 18, y - 2.2, t[0] + 18 + long, y + 2.2),
                fill=PODIUM if under else TOWER,
                outline=theme.INK,
                width=0.4,
                radius=0,
            )
    elif kind == "Facade bands":
        # The skin in its bands of sun hours, most at the top.
        steps = 6
        tall = (BLOCK_MM[3] - BLOCK_MM[1]) / steps
        for step in range(steps):
            box(
                (
                    BLOCK_MM[0],
                    BLOCK_MM[1] + tall * step,
                    BLOCK_MM[2],
                    BLOCK_MM[1] + tall * (step + 1),
                ),
                fill=HOURS_RAMP[6 - step],
                radius=0,
            )
        box(BLOCK_MM, outline=theme.INK)
    elif kind == "Sun view":
        # The town as the sun sees it: white blocks, the proposal a storey
        # taller in the heavier line with its glazing lit on the face the
        # sun reaches, and the sun over it. No shadow, because from where
        # the light comes from there is none to see.
        mid_x, mid_y, unit = 131.0, 104.0, 6.5
        morning = drawing.azimuth is None or math.sin(math.radians(drawing.azimuth)) > 0

        def at(x: float, y: float, z: float) -> tuple[float, float]:
            return (mid_x + (x - y) * 0.866 * unit, mid_y + (x + y) * 0.5 * unit - z * unit)

        poly(
            [at(-9, -9, 0), at(9, -9, 0), at(9, 9, 0), at(-9, 9, 0)],
            fill=theme.PAGE,
            outline=ROAD,
            width=0.6,
        )
        houses = [
            (*house, ("#F6F6F6", "#DBDBDB", "#EBEBEB"), NEIGHBOUR_EDGE, 0.7) for house in TOWN_ISO
        ] + [(-2.2, -2.2, 2.2, 2.2, 3.2, ("#F2F2F2", "#CDCDCD", "#E1E1E1"), theme.INK, 1.0)]
        for x0, y0, x1, y1, tall, tints, edge, weight in sorted(houses, key=lambda h: h[0] + h[1]):
            poly(
                [at(x0, y1, 0), at(x1, y1, 0), at(x1, y1, tall), at(x0, y1, tall)],
                fill=tints[1],
                outline=edge,
                width=weight,
            )
            poly(
                [at(x1, y0, 0), at(x1, y1, 0), at(x1, y1, tall), at(x1, y0, tall)],
                fill=tints[2],
                outline=edge,
                width=weight,
            )
            poly(
                [at(x0, y0, tall), at(x1, y0, tall), at(x1, y1, tall), at(x0, y1, tall)],
                fill=tints[0],
                outline=edge,
                width=weight,
            )
        # The glazing the sun reaches, on the proposal's face towards it.
        z = 0.4
        while z < 3.0:
            w = -1.8
            while w < 2.0:
                if morning:
                    corners = [
                        at(2.2, w, z),
                        at(2.2, w, z + 0.35),
                        at(2.2, w + 0.5, z + 0.35),
                        at(2.2, w + 0.5, z),
                    ]
                else:
                    corners = [
                        at(w, 2.2, z),
                        at(w, 2.2, z + 0.35),
                        at(w + 0.5, 2.2, z + 0.35),
                        at(w + 0.5, 2.2, z),
                    ]
                poly(corners, fill=GLAZING)
                w += 0.9
            z += 0.7
        sun_x, sun_y = at(7, -2, 5.5) if morning else at(-2, -7, 5.5)
        sun(sun_x, sun_y, 3.4)
    elif study == "Site analysis":
        # The site itself, outlined, with the address dropped on it.
        box(BLOCK_MM, fill="", outline=BOUNDARY, dash=BOUNDARY_DASH)
        _pin(paper, px((BLOCK_MM[0] + BLOCK_MM[2]) / 2), py(BLOCK_MM[1] + 12), k)
    else:
        # A shadow diagram: the town's own shadows in grey, the proposal's
        # extra shadow in the blue the diagram tells it apart with, the lots
        # over them and the site boundary over those.
        reach, bearing = drawing.reach, drawing.bearing
        site = (BLOCK_MM[0] - 8, BLOCK_MM[1] - 8, BLOCK_MM[2] + 8, BLOCK_MM[3] + 8)
        if reach is not None and bearing is not None:
            for lot in TOWN_MM:
                if not (
                    lot[2] < site[0] or lot[0] > site[2] or lot[3] < site[1] or lot[1] > site[3]
                ):
                    continue
                held = _clip_to(shifted(lot, min(reach, 3.0) * 9.0, bearing), SITE_FIT_MM)
                if len(held) >= 3:
                    poly(held, fill=SHADOW_CAST)
            held = _clip_to(
                shifted(BLOCK_MM, min(reach, 3.0) * BLOCK_HEIGHT_M, bearing), SITE_FIT_MM
            )
            if len(held) >= 3:
                poly(held, fill=SHADOW_EXTRA)
        town(site)
        box(site, outline=BOUNDARY, dash=BOUNDARY_DASH, width=1.2, radius=BLOCK_RADIUS + 1)
        massing()


#: The lots round the site on a shadow diagram, in the sheet's millimetres,
#: and the houses of the white town a sun view looks down on, in the view's
#: own units about the proposal.
TOWN_MM = (
    (70.0, 44.0, 96.0, 66.0),
    (100.0, 44.0, 130.0, 62.0),
    (136.0, 44.0, 158.0, 64.0),
    (164.0, 46.0, 190.0, 68.0),
    (70.0, 76.0, 94.0, 106.0),
    (174.0, 78.0, 192.0, 110.0),
    (70.0, 132.0, 98.0, 162.0),
    (106.0, 136.0, 136.0, 162.0),
    (144.0, 136.0, 164.0, 162.0),
    (170.0, 128.0, 192.0, 162.0),
)
TOWN_ISO = (
    (-8.0, -8.0, -5.0, -4.0, 1.0),
    (-3.0, -8.5, 1.0, -6.0, 0.8),
    (3.0, -8.0, 7.5, -5.0, 1.2),
    (-8.5, -2.0, -5.5, 2.0, 0.9),
    (5.0, -2.0, 8.5, 2.5, 1.1),
    (-8.0, 4.0, -4.5, 8.0, 0.8),
    (-2.0, 5.0, 2.0, 8.5, 1.0),
    (4.0, 4.5, 8.0, 8.0, 0.7),
)


def _pin(paper: tk.Canvas, x: float, y: float, k: float) -> None:
    """The address pin, in the interface's blue, at canvas ``(x, y)`` with
    its point there; ``k`` is the pixels per millimetre it is drawn at."""
    paper.create_polygon(
        x - 5 * k, y - 7 * k, x + 5 * k, y - 7 * k, x, y + 6 * k, fill=theme.BLUE, outline=""
    )
    paper.create_oval(x - 6 * k, y - 15 * k, x + 6 * k, y - 3 * k, fill=theme.BLUE, outline="")
    paper.create_oval(
        x - 2.2 * k, y - 11.2 * k, x + 2.2 * k, y - 6.8 * k, fill=theme.SURFACE, outline=""
    )


def _footprint(
    paper: tk.Canvas, x0: float, y0: float, x1: float, y1: float, ink: str, *, width: float = 0.8
) -> None:
    """A neighbour's building in plan: white, in a fine line of its zone's
    ink, as Flamingo draws every building."""
    _rounded(paper, x0, y0, x1, y1, 1.0, fill=theme.SURFACE, outline=ink, width=width)


def _roundel(paper: tk.Canvas, x: float, y: float, radius: float) -> None:
    """A station's roundel as Flamingo draws it: a solid disc in the rail's
    blue, a white T on it.

    The T is drawn, a bar and a stem, not set in type: Tk puts text on
    whole pixels, and on a disc a dozen pixels across a letter a pixel off
    the middle reads as off -- which is how it read, set even on its
    capital. Drawn, its box is centred on the disc exactly.
    """
    paper.create_oval(
        x - radius, y - radius, x + radius, y + radius, fill=theme.BLUE, outline=theme.SURFACE
    )
    arm, stroke = radius * 0.5, radius * 0.3
    top, foot = y - radius * 0.5, y + radius * 0.5
    paper.create_line(
        x - arm, top + stroke / 2, x + arm, top + stroke / 2, fill=theme.SURFACE, width=stroke
    )
    paper.create_line(x, top + stroke, x, foot, fill=theme.SURFACE, width=stroke)


def _draw_context(paper: tk.Canvas, frame: tuple[float, float, float, float]) -> None:
    """The context sheet, drawn to the edges of its frame as Flamingo draws
    it, and centred as the run centres it, on the site.

    The site in the middle of the field and the street grid laid out from
    it, the blocks at the edges cut where the frame cuts them; each block
    washed in its zone -- Flamingo's warm orange, or the grey of no zone --
    and built along both its streets, the buildings white in a fine line of
    the zone's ink, near alike, with the yards open behind them;
    a park; the railway along the street north of the site, its station's
    roundel on it; the five-minute walk round the site -- the catchment
    is the site's, not the station's -- and the site itself, the middle lot
    of its block on the rail street, in the site's coral. Everything
    is laid out inside the frame by construction, because a Tk canvas clips
    nothing.

    Until 24 October the rail ran corner to corner across every block, the
    site was a box set down across the lots of its block rather than lots
    of it, and a building was a lot with a line through it. Then the grid
    was laid from the corner, which put the site off to one side and the
    walk round the station. "Our site needs to be in the middle. The circle
    should be around our site, not around the train station." Then each
    block had its own count of lots and each building its own depth, in a
    lilac wash: "set the building into block more equally, more unified
    and clean ... use some orange instead of pink."
    """
    fx0, fy0, fx1, fy1 = frame
    w, h = fx1 - fx0, fy1 - fy0
    u = w / 229.0  # the field's width on a full sheet, in millimetres
    street = 5 * u
    block_w, block_h = 56 * u, 48 * u
    # Every block is laid out by one rule: three lots along each of its two
    # streets, one gap between every two houses, every house on the line
    # of its street and as wide as its lot, the back row the front's
    # mirror. The lots are not equal -- a wide house, a narrow one -- and a
    # wider house is a little deeper, so the houses differ in size while
    # the rows stay rows. A fixed scatter of sizes read as houses dropped
    # anywhere ("not be placed everywhere randomly").
    inset, gap = 2 * u, 2.5 * u
    deep = block_h * 0.34
    mid_x, mid_y = (fx0 + fx1) / 2, (fy0 + fy1) / 2
    site_block, park_block = (0, 0), (1, 1)

    def street_of(col: int) -> tuple[float, ...]:
        # Dealt by column, so the lot lines run on down the column from block
        # to block, and the site's column takes the pattern even about its
        # middle.
        return CONTEXT_STREETS[(CONTEXT_SITE_STREET + col) % len(CONTEXT_STREETS)]

    def lots_along(left: float, shares: Sequence[float]) -> list[tuple[float, float, float]]:
        """Each lot along a street from ``left``: where it starts and ends,
        and its share."""
        room = block_w - 2 * inset - (len(shares) - 1) * gap
        out: list[tuple[float, float, float]] = []
        x = left + inset
        for share in shares:
            wide = room * share / sum(shares)
            out.append((x, x + wide, share))
            x += wide + gap
        return out

    # The site's block is placed so the site, its front half, is centred.
    top = mid_y - (inset + block_h / 2) / 2

    def held(
        x0: float, y0: float, x1: float, y1: float, least: float = 3.0
    ) -> tuple[float, float, float, float] | None:
        """A rectangle cut to the frame, or nothing when less than
        ``least`` millimetres of it is left either way to read."""
        x0, y0, x1, y1 = max(x0, fx0), max(y0, fy0), min(x1, fx1), min(y1, fy1)
        return (x0, y0, x1, y1) if min(x1 - x0, y1 - y0) > least * u else None

    across = math.ceil(w / 2 / (block_w + street))
    down = math.ceil(h / 2 / (block_h + street)) + 1
    for col in range(-across, across + 1):
        for row in range(-down, down + 1):
            bx = mid_x + col * (block_w + street) - block_w / 2
            by = top + row * (block_h + street)
            block = held(bx, by, bx + block_w, by + block_h)
            if block is None:
                continue
            if (col, row) == park_block:
                # A park on one block, its trees in canopy.
                _rounded(paper, *block, 2, fill=PARK, outline="")
                px0, py0, px1, py1 = block
                for tx, ty, tr in ((0.3, 0.3, 6), (0.68, 0.55, 7.5), (0.3, 0.75, 4.5)):
                    r = tr * u
                    cx = min(max(px0 + (px1 - px0) * tx, px0 + r), px1 - r)
                    cy = min(max(py0 + (py1 - py0) * ty, py0 + r), py1 - r)
                    paper.create_oval(cx - r, cy - r, cx + r, cy + r, fill=CANOPY, outline="")
                continue
            zoned = ((col * 7 + row * 3 + 1) % 3) != 0
            ground, ink = (ZONING, ZONING_EDGE) if zoned else (LOT, NEIGHBOUR_EDGE)
            _rounded(paper, *block, 2, fill=ground, outline="")
            shares = street_of(col)
            for back in (False, True):
                for part, (x0, x1, share) in enumerate(
                    lots_along(bx, shares[::-1] if back else shares)
                ):
                    if (col, row) == site_block and not back and part == CONTEXT_SITE_LOT:
                        continue
                    depth = deep * min(1.0, 0.55 + 0.33 * share)
                    y0 = by + block_h - inset - depth if back else by + inset
                    house = held(x0, y0, x1, y0 + depth, depth / u * 0.6)
                    if house is not None:
                        _footprint(paper, *house, ink)
    # The railway along the street north of the site's block, the station
    # on it at the corner, and the five-minute walk round the site.
    rail_y = top - street / 2
    paper.create_line(fx0, rail_y, fx1, rail_y, fill=theme.BLUE, width=1.5, dash=(6, 2))
    walk = 64 * u
    paper.create_oval(
        mid_x - walk, mid_y - walk, mid_x + walk, mid_y + walk, outline=RING, dash=(4, 3)
    )
    # The site: the middle lot of its block, front to the rail street and
    # back to the middle of the block, as the cadastre has them.
    left, right, _share = lots_along(mid_x - block_w / 2, street_of(site_block[0]))[
        CONTEXT_SITE_LOT
    ]
    _rounded(
        paper,
        left,
        top + inset,
        right,
        top + block_h / 2,
        1.5,
        fill=CONTEXT_SITE,
        outline=BOUNDARY,
        width=1.4,
    )
    _roundel(paper, mid_x - block_w / 2 - street / 2, rail_y, 6.5 * u)


def _draw_site(paper: tk.Canvas, frame: tuple[float, float, float, float]) -> None:
    """The site sheet, drawn to the edges of its frame: the street the site
    fronts, its street trees, and the lots along both sides of it as the
    cadastre has them -- a fine grey line between them -- each neighbour's
    building on its lot as a footprint, set back from the street, its yard
    behind; the contours across the slope in ochre; the site in red, a
    circle at each survey corner, its frontage dimensioned in the street,
    the pin on it; and the sun in the corner. Laid out inside the frame by
    construction.

    Until 24 October the neighbours were terraces drawn as ruled lines with
    a stub of a house at each, and a dashed box stood in the site for the
    building -- which the site sheet does not draw: it is the site as it is.
    """
    fx0, fy0, fx1, fy1 = frame
    w, h = fx1 - fx0, fy1 - fy0
    u = w / 229.0

    def at(x_mm: float) -> float:
        return fx0 + x_mm * u

    _rounded(paper, fx0, fy0, fx1, fy1, 3, fill=LOT, outline="")
    # Contours under everything built, read across the slope.
    for start, end in ((0.82, 0.42), (0.5, 0.12)):
        points: list[float] = []
        for step in range(0, 9):
            share = step / 8
            y = fy0 + h * (start + (end - start) * (share * share * (3 - 2 * share)))
            points += [fx0 + w * share, min(max(y, fy0 + u), fy1 - u)]
        paper.create_line(points, fill=CONTOUR, smooth=True)
    # The street, across the foot of the sheet.
    kerb, far_kerb = fy0 + 0.7 * h, fy0 + 0.7 * h + 15 * u
    paper.create_rectangle(fx0, kerb, fx1, far_kerb, fill=ROAD, outline="")
    rear = fy0 + 0.33 * h
    paper.create_line(fx0, rear, fx1, rear, fill=NEIGHBOUR_EDGE, width=0.6)
    # The lots in their three rows, behind, beside and over the road from
    # the site; the site is the front row's third, 78 to 150.
    site = (at(78), rear, at(150), kerb)
    rows = (
        ((0, 40, 92, 130, 176, 229), fy0, rear),
        ((0, 26, 78, 150, 196, 229), rear, kerb),
        ((0, 54, 110, 168, 229), far_kerb, fy1),
    )
    for row_index, (cuts, top, bottom) in enumerate(rows):
        for cut in cuts[1:-1]:
            paper.create_line(at(cut), top, at(cut), bottom, fill=NEIGHBOUR_EDGE, width=0.6)
        for left, right in pairwise(cuts):
            if row_index == 1 and (left, right) == (78, 150):
                continue
            # Each house a little different, set in from its side lines.
            side = 3 + (left % 3)
            x0, x1 = at(left + side), at(right - side - 1)
            if row_index == 0 and right == 229:
                x1 = min(x1, at(198))  # the sun's corner kept clear
            if row_index == 0:
                y0, y1 = top + 6 * u, bottom - (12 + left % 5) * u
            elif row_index == 1:
                y1 = bottom - (7 + left % 3) * u
                y0 = y1 - (28 + left % 7) * u
            else:
                y0, y1 = top + 7 * u, min(bottom - 3 * u, top + 30 * u)
            if x1 - x0 > 4 * u and y1 - y0 > 4 * u:
                _footprint(paper, x0, y0, x1, y1, NEIGHBOUR_EDGE)
    # The street trees, on the kerbs and clear of the site's frontage.
    for tx, ty, tr in (
        (30, kerb, 6),
        (172, kerb, 5.5),
        (214, kerb, 6),
        (62, far_kerb, 5.5),
        (138, far_kerb, 6.5),
        (200, far_kerb, 5),
    ):
        paper.create_oval(
            at(tx) - tr * u, ty - tr * u, at(tx) + tr * u, ty + tr * u, fill=CANOPY, outline=""
        )
    # The site: its lot in colour, the boundary, a circle at each survey
    # corner, the frontage dimensioned in the street, the pin.
    paper.create_rectangle(*site, fill=SITE_BLOCK[0], outline=BOUNDARY, width=1.5)
    for cx in (site[0], site[2]):
        for cy in (site[1], site[3]):
            paper.create_oval(
                cx - 2.4 * u,
                cy - 2.4 * u,
                cx + 2.4 * u,
                cy + 2.4 * u,
                fill=theme.SURFACE,
                outline=BOUNDARY,
            )
    dim = (kerb + far_kerb) / 2
    paper.create_line(site[0], dim, site[2], dim, fill=theme.INK, width=0.8)
    for tick_x in (site[0], site[2]):
        paper.create_line(tick_x, dim - 3 * u, tick_x, dim + 3 * u, fill=theme.INK, width=0.8)
    _pin(paper, (site[0] + site[2]) / 2, (site[1] + site[3]) / 2 + 5 * u, u)
    # The sun, in the corner the north side leaves free.
    sx, sy, sr = fx1 - 16 * u, fy0 + 14 * u, 4.5 * u
    for ray in range(8):
        angle = ray * math.pi / 4
        paper.create_line(
            sx + math.cos(angle) * sr * 1.45,
            sy + math.sin(angle) * sr * 1.45,
            sx + math.cos(angle) * sr * 2.1,
            sy + math.sin(angle) * sr * 2.1,
            fill=theme.SUN,
            capstyle="round",
        )
    paper.create_oval(sx - sr, sy - sr, sx + sr, sy + sr, fill=LIT, outline=theme.SUN)


def _face(size: int, bold: bool) -> tuple[str, int] | tuple[str, int, str]:
    """The window's typeface at that size, as Tk takes a font on a canvas."""
    scaled = theme.points(size)
    return (theme.FACE, scaled, "bold") if bold else (theme.FACE, scaled)


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


class MasterChooser(tk.Toplevel):
    """Which master layout the sheets go on: one, from the project's own.

    ``result`` is the name chosen, or ``None`` when the window was closed
    without one.
    """

    def __init__(self, parent: tk.Misc, masters: Sequence[str]) -> None:
        super().__init__(parent)
        self.title("Master layout")
        self.transient(parent)  # type: ignore[call-overload]
        self.result: str | None = None
        ttk.Label(
            self,
            text="Which master layout should the sheets go on?",
            padding=(16, 14, 16, 6),
        ).pack(anchor="w")
        self.names = tk.Listbox(self, height=min(14, len(masters)), width=48, exportselection=False)
        for name in masters:
            self.names.insert("end", name)
        self.names.pack(fill="both", expand=True, padx=16)
        self.names.bind("<Double-Button-1>", lambda _event: self._done())
        buttons = ttk.Frame(self, padding=(16, 10, 16, 14))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Use this one", command=self._done).pack(side="right", padx=8)
        self.bind("<Return>", lambda _event: self._done())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.grab_set()
        self.names.focus_set()

    def _done(self) -> None:
        picked = self.names.curselection()  # type: ignore[no-untyped-call]
        if not picked:
            return
        self.result = str(self.names.get(picked[0]))
        self.destroy()


class Window:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        #: The assessment days the solar analysis runs on, by short name,
        #: ticked or not. Built before the sections are, because the Solar
        #: analysis tab fills it as it is drawn.
        self.days: dict[str, tk.BooleanVar] = {}
        #: The same question asked of the sun views, on their own tab and
        #: with their own answer. One set of ticks used to serve both, which
        #: put the days on the Model tab -- a page about geometry -- where
        #: nobody drawing either study thought to look for them.
        self.eye_days: dict[str, tk.BooleanVar] = {}
        #: And of the shadow diagram, which had its own row of four dates
        #: spelled differently from the other two pages' days.
        self.shadow_day_ticks: dict[str, tk.BooleanVar] = {}
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
        self.root.geometry(self._on_the_screen(self.OPENING_WIDTH, self.OPENING_HEIGHT))

        #: Lines from the worker thread. Tkinter is not thread-safe, so nothing
        #: touches a widget from the runner's thread: lines go through here and
        #: the UI thread drains them on a timer.
        self.incoming: queue.Queue[tuple[str, object]] = queue.Queue()

        self.options = probe.ProjectOptions()
        self.ports: list[int] = []
        self.run: Run | None = None
        self.queued: list[Job] = []
        #: Whether a run is under way, and whether the open Archicad lacks the
        #: add-on. The two things besides an empty queue that switch Run off;
        #: ``_paint_run`` weighs all three in one place.
        self._running = False
        self._tapir_missing = False
        #: Everything a run has said, in order. The window shows the newest
        #: line of it and no more, but a failure has to be readable after the
        #: fact, so the transcript is kept rather than drawn.
        self.lines: list[str] = []
        #: And written to disk as it comes, so it outlives the window and the
        #: next run: the file of the run in progress, then of the last one.
        #: ``None`` before the first run, or where the folder refused a file.
        self.log: run_log.RunLog | None = None
        self.last_log: Path | None = None

        #: The width under which the sheets panel folds away. At least
        #: ``FOLD_BELOW``, and measured once the tabs exist: see below.
        self.fold_below = self.FOLD_BELOW
        #: Every card, so the label column can be set once for all of them.
        self.boxes: list[ttk.Frame] = []
        #: Each panel's fold: its triangle, whether it is folded, and the rows
        #: it took off the grid to fold, so opening it puts back only those.
        self.folders: dict[str, ttk.Button] = {}
        self.folded: dict[str, bool] = {}
        self._kept_rows: dict[str, list[tk.Widget]] = {}
        self._spacers: dict[str, ttk.Frame] = {}
        #: Each study's name on its panel's header, restyled as it is
        #: switched on and off.
        self.study_titles: dict[str, ttk.Label] = {}
        #: The page's own rearranging: whether it is narrow, the rows that
        #: wrap (found once the pages are built), and a pending pass.
        self._narrow_page = False
        self._flows: list[tk.Misc] | None = None
        self._responding: str | None = None
        #: Whether each study was on at the last ``_sync``, so a study is
        #: opened the moment it is switched on and not on every sync after.
        self._was_on: dict[str, bool] = {}
        self._build()
        self._line_up_labels()
        # Wide enough for every tab beside the sheets panel, measured rather
        # than assumed. Seven tabs need more than the 728 the page was sized
        # for, and a font wider than Segoe UI -- the one a machine without it
        # falls back to -- needs more again; a tab past the edge of the
        # window is a page nobody can open. So the strip says what it needs,
        # the panel folds below that, and the window opens at least that wide.
        self.root.update_idletasks()
        self.fold_below = max(
            self.FOLD_BELOW, self.strip.winfo_reqwidth() + self.PAGE_LEAST + Dock.WIDTH + 2
        )
        if self.fold_below > self.OPENING_WIDTH:
            self.root.geometry(self._on_the_screen(self.fold_below, self.OPENING_HEIGHT))
        #: What the window opens with when nothing has been saved. Taken
        #: before any saved settings land on top of it, so Forget has
        #: something to go back to that is not "whatever was on screen".
        self.factory = self.settings()
        self._restore()
        # A study nobody has switched on starts folded to its header: the page
        # opens on what will run, and on the one line of each study that won't.
        for name, tick, _where in self._studies():
            if name in self.study_boxes and not tick.get():
                self._fold(self.study_boxes[name][0], True)
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
        if theme.MACOS:
            # A Mac is most often a laptop, and a window that opens across the
            # whole of one is a window in the way of Archicad, which is the
            # program this one works beside. Three quarters of the screen at
            # most; below the width the sheets panel needs, the panel starts
            # folded at its edge and the page has the room.
            wide = min(wide, round(self.root.winfo_screenwidth() * self.MAC_SHARE))
            tall = min(tall, round(self.root.winfo_screenheight() * self.MAC_SHARE))
        return f"{max(wide, 880)}x{max(tall, 620)}"

    #: The most of a Mac's screen the window opens across, either way.
    MAC_SHARE = 0.75

    # -- layout ------------------------------------------------------------
    #: The seven pages, and the two kinds they come in. That split is the
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
    YIELD = "Yield"
    #: Not an output and not set-up: a tool used on the open project, which
    #: is why it is a third group of its own.
    REFERENCE = "Reference image"

    #: The three kinds, in sidebar order, under the word that names each.
    #: Pages that set the job up, pages that each draw something and can be
    #: queued, and tools that act on Archicad there and then.
    SET_UP = "SET UP"
    DRAWS = "STUDIES"
    TOOLS = "TOOLS"
    GROUPS: ClassVar[tuple[tuple[str, tuple[str, ...]], ...]] = (
        (SET_UP, (GENERAL, MODEL)),
        (DRAWS, (SITE, DIAGRAMS, SHADOWS, EYE, YIELD)),
        (TOOLS, (REFERENCE,)),
    )
    #: The study a page's switch in the sidebar turns on, on a page that has
    #: more than one. The apartments are what Solar analysis is opened for,
    #: and the 3D Documents are what Shadow diagram is (D144).
    LEADS: ClassVar[dict[str, str]] = {
        DIAGRAMS: PLANS_JOB,
        SHADOWS: SHADOW_JOB,
        SITE: SITE_CONTEXT_JOB,
    }
    #: How wide the sidebar is.
    SIDE_WIDTH = 236
    #: The project picker's width in characters: never narrower than this,
    #: and never wider than the most, however long a project's name.
    PICKER_LEAST = 34
    PICKER_MOST = 72
    #: The least the page between the sidebar and the sheets panel is allowed
    #: before the sheets panel folds away to give it room. Below
    #: ``FIELD_LEAST`` beside its labels the page rearranges itself to fit (``_rearrange``);
    #: below this there is too little left even for that.
    PAGE_LEAST = 520

    #: What each tab says when hovered. The tab carries a drawing at 32 px and
    #: a name, and nothing else -- so the sentence that would otherwise sit
    #: under the label lives here, where it costs no room at all.
    SECTION_BLURB: ClassVar[dict[str, str]] = {
        GENERAL: (
            "The sheet every output lands on: the master and its title block, "
            "the layer prefixes that file the results, and where the tables go."
        ),
        SITE: (
            "An address in; the Context and Site Analysis sheets, the Summary of "
            "Controls, and a 500 m context model of terrain, blocks and "
            "neighbours out."
        ),
        MODEL: (
            "What geometry leaves Archicad: the storeys it is measured between, "
            "the layer combination it starts from, what is forced in, what the "
            "neighbours are, and what is kept off the drawings."
        ),
        DIAGRAMS: (
            "Hours of direct sun, on the days lit here. Three studies: the facade "
            "in bands at massing stage, the apartments assessed against the ADG, "
            "and communal open space."
        ),
        SHADOWS: (
            "3D Documents from overhead with Archicad's own shadows, each massing "
            "stacked in its legend colour, hour by hour — and the design's every "
            "hour on one drawing."
        ),
        EYE: (
            "3D documents aimed straight down the sun on the days lit here, and "
            "the sheets they are dealt onto."
        ),
        YIELD: (
            "The office's feasibility sheet from the massing slabs: BEA, GFA, NLA and "
            "FSR by use, the units, the parking -- a sheet an option, and a live workbook."
        ),
        REFERENCE: (
            "A photograph or a rendering laid over Archicad's 3D window, as "
            "see-through as you like, so the model can be orbited under it "
            "until the two line up. Nothing is written into the project."
        ),
    }
    #: The one line under a page's name, at the top of the page. The blurb
    #: above is the longer sentence, for the card in the sidebar.
    SECTION_SHORT: ClassVar[dict[str, str]] = {
        GENERAL: "The sheet every output lands on, and where the results are filed.",
        MODEL: "What geometry leaves Archicad, and what is kept off the drawings.",
        SITE: "The context and site sheets, and a context model, from an address.",
        DIAGRAMS: "Hours of direct sun on the days below.",
        SHADOWS: "Archicad's own shadows of each massing, hour by hour, stacked.",
        EYE: "3D documents aimed down the sun, dealt onto sheets.",
        YIELD: "The feasibility sheet from the massing slabs, and a live workbook.",
        REFERENCE: "A picture laid over Archicad, to trace or check against.",
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
        # so it stays put while the page above it changes and scrolls. Run
        # has to be findable without hunting through pages, and the one line
        # a run has to say about itself has to stay where it was put.
        base = ttk.Frame(self.root, style="Chrome.TFrame", padding=(PAD * 2, 8, PAD * 2, 8))
        base.pack(side="bottom", fill="x")
        base.columnconfigure(0, weight=1)
        ttk.Frame(self.root, style="Rule.TFrame", height=1).pack(side="bottom", fill="x")

        self._project_picker()
        if theme.MACOS:
            self._mac_menus()

        # Three columns: the pages down the left, the open page, and every
        # sheet the run will make down the right -- which belongs to the run
        # and not to a page, so it stays put while the pages change.
        middle = ttk.Frame(self.root, style="Page.TFrame")
        middle.pack(side="top", fill="both", expand=True)
        self.side = ttk.Frame(
            middle, style="Side.TFrame", width=self.SIDE_WIDTH, padding=(10, 12, 10, 12)
        )
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        #: Kept by its old name: what the window measures to know how wide it
        #: has to be before the sheets panel can stay open beside the page.
        self.strip = self.side
        ttk.Frame(middle, style="Rule.TFrame", width=1).pack(side="left", fill="y")
        # At the foot of the sidebar, the card that explains whatever is under
        # the pointer. Made here, packed by ``_strip`` *after* the pages: the
        # packer gives room in packing order, and a card packed first kept
        # its whole height on a short screen while the last page's row was
        # the thing that went unmapped. Packed last it still keeps the
        # bottom, and is the thing cut when the sidebar is short.
        self.info = InfoBand(self.side)
        Tooltip.band = self.info

        self.dock = Dock(middle, on_pick=self._sheet_under, on_fold=self._dock_folded)
        #: Whether the window is too narrow to hold both panes. Crossing the
        #: line folds the panel or brings it back; in between, the chevron
        #: is the user's and is left alone.
        self._narrow = False
        #: Whether nothing is ticked, so the panel has no sheet to show, and
        #: whether somebody opened it by hand anyway. An empty panel was a
        #: third of the window saying "Nothing ticked" on every page; it now
        #: waits at its edge until there is a sheet to draw.
        self._dock_empty = False
        self._dock_opened_empty = False
        self.root.bind("<Configure>", self._fit, add="+")
        self.dock.pack(side="right", fill="y")
        # The contour between the page and the dock: one pixel, and thin.
        ttk.Frame(middle, style="Rule.TFrame", width=1).pack(side="right", fill="y")
        self.pane = ttk.Frame(middle, style="Page.TFrame")
        self.pane.pack(side="left", fill="both", expand=True)
        self.pane.bind("<Configure>", self._respond, add="+")

        self._sections()
        self._controls(base)
        # What is typed changes what a run will make as surely as what is
        # ticked, so the panel of sheets hears about keystrokes too.
        for typed in (self.communal_hours, self.year, self.custom_day, self.eye_custom_day):
            typed.bind("<KeyRelease>", lambda _event: self._sync(), add="+")
        for chosen in (self.adg_subset, self.shadow_subset):
            chosen.bind("<<ComboboxSelected>>", lambda _event: self._sync(), add="+")
        self._sync()

    def _project_picker(self) -> None:
        """The tool bar: the program, which Archicad, and the menu.

        Which Archicad belongs to no page. Every list in every section is read
        out of the chosen project and every study runs against it, so it is
        not a setting of one output, and it has to stay in view while a page
        is being filled in.

        Nothing else sits up here. The reference image is a tool, so it is a
        page under Tools in the sidebar; Connect Claude is set up once and
        then forgotten, so it is in the menu with the other things that act
        on the program rather than on the project. What was a row of five
        buttons of three different kinds is a name, a picker and a menu.
        """
        top = ttk.Frame(self.root, style="Chrome.TFrame", padding=(PAD * 2, 8, PAD * 2, 8))
        top.pack(side="top", fill="x")

        brand = ttk.Frame(top, style="Chrome.TFrame")
        brand.pack(side="left", padx=(0, PAD * 2))
        # The program's name, written: the wordmark, as tall as a line of the
        # heading face the name was set in, so it stands where the name stood
        # (D165). The name in that face when the picture cannot be had.
        wordmark = brand_wordmark(self.root, brand_height(self.root))
        if wordmark is not None:
            self._wordmark = wordmark  # Tk forgets a picture nothing in Python holds
            ttk.Label(brand, image=wordmark, style="Brand.TLabel").pack(side="left")
        else:
            ttk.Label(brand, text=PRODUCT, style="Brand.TLabel").pack(side="left")

        # Listed, never assumed: each instance gets its own port, so the
        # default is right only for whichever started first, and two projects
        # open is the ordinary case in an office. As wide as a project's name,
        # not as wide as the window: the picker used to stretch across most
        # of the bar for a name a third that long.
        self.instance = ttk.Combobox(
            top, state="readonly", values=[], style="Chrome.TCombobox", width=self.PICKER_LEAST
        )
        self.instance.pack(side="left")
        self.instance.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        Tooltip(
            self.instance,
            "Archicad gives every open instance its own port, so there is no "
            "single right one to guess at. The study reads and draws in "
            "whichever project is chosen here — pick the wrong one and it "
            "measures the wrong building and says nothing. Press Refresh "
            "after opening or closing a project.",
            title="Archicad",
        )
        rescan = ttk.Button(
            top,
            style="Chrome.TButton",
            command=self.refresh,
            padding=(6, 0),
            width=0,
            **icons.button_options("refresh"),
        )
        rescan.pack(side="left", padx=(6, 0))
        Tooltip(
            rescan,
            "Looks again for running Archicads and re-reads the chosen "
            "project. Press it after opening a project, or after adding a "
            "layer or a Layout Book subset that should appear in the lists "
            "in the sections below.",
            title="Refresh",
        )

        # The things that act on the program rather than on the project, in
        # one menu at the end of the bar. They were four buttons as big as
        # Run on the run bar and two more up here. "Save as default" is for
        # what belongs to the practice; a preset is for what belongs to a job
        # or a colleague -- the Silverwater setup, the shadow set the council
        # asked for -- and goes wherever a job's files go.
        self.settings_menu = tk.Menu(self.root, tearoff=False)
        # Loriini as an MCP server in the Claude a person already has.
        # "Connect Claude" rather than "Add to Claude": what it does to the
        # Claude a person already has, in the words of somebody who has not
        # read what an MCP server is. ``claude_mcp`` is the whole of it.
        self.settings_menu.add_command(label="Connect Claude…", command=self._add_to_claude)
        self.settings_menu.add_separator()
        self.settings_menu.add_command(label="Save as default", command=self._remember)
        self.settings_menu.add_command(label="Save preset…", command=self._save_preset)
        self.settings_menu.add_command(label="Load preset…", command=self._load_preset)
        self.settings_menu.add_separator()
        self.settings_menu.add_command(label="Forget saved settings", command=self._forget)
        # About here as well as in a Mac's program menu: this is where people
        # look for it once the menu is the one place the program's own things
        # are, and the web site beside it.
        self.settings_menu.add_separator()
        self.settings_menu.add_command(label=f"About {PRODUCT}", command=self._about)
        self.settings_menu.add_command(
            label=f"{WEBSITE.removeprefix('https://')} ↗", command=self._website
        )
        glyph = theme.menu_glyph(self.root)
        menu = ttk.Button(
            top,
            style="Chrome.TButton",
            padding=(6, 0),
            width=0,
            command=lambda: self._post(self.settings_menu, menu),
            **({"image": glyph} if glyph is not None else {"text": "Menu"}),
        )
        menu.pack(side="right")
        self.menu_button = menu
        Tooltip(
            menu,
            "Connect Claude registers this program as an MCP server with Claude "
            "Desktop and Claude Code, so an agent can run the studies into the "
            "open project. Save as default remembers every page -- the ticks, "
            "the fields and which page was open -- and fills the window in "
            "with it next time. A preset is the same written to a file you "
            "name. Forget throws the saved settings away. About says which "
            "version this is and whose licence it runs on.",
            title="Menu",
        )
        # The contour under the tool bar.
        ttk.Frame(self.root, style="Rule.TFrame", height=1).pack(side="top", fill="x")

    def _mac_menus(self) -> None:
        """The Mac's menu bar: About where every Mac program keeps it.

        Tk gives a window with no menu of its own a bare File, Edit, Window
        and Help, none of which did anything here, while About sat as a button
        in the project bar. On a Mac the program's own menu is where somebody
        looks for it, so it goes there and the bar is left to the project.
        Windows keeps the button: a Windows tool has no program menu to put
        it in.
        """
        bar = tk.Menu(self.root)
        # Named ``apple``: Tk makes that menu the program's own, the bold one
        # after the Apple logo.
        own = tk.Menu(bar, name="apple", tearoff=False)
        own.add_command(label=f"About {PRODUCT}", command=self._about)
        own.add_separator()
        bar.add_cascade(menu=own)
        # Named ``window`` and ``help``: Tk fills the first with the Mac's own
        # window list, and gives the second the system's search field.
        bar.add_cascade(label="Window", menu=tk.Menu(bar, name="window", tearoff=False))
        helping = tk.Menu(bar, name="help", tearoff=False)
        helping.add_command(label=f"About {PRODUCT}", command=self._about)
        helping.add_command(
            label="Where the site data comes from", command=lambda: self._about("sources")
        )
        helping.add_separator()
        helping.add_command(label="Open the last run's log", command=self._open_log)
        bar.add_cascade(label="Help", menu=helping)
        self.root.configure(menu=bar)
        self.menu_bar = bar

    def _add_to_claude(self) -> None:
        """Register the program with Claude Desktop and Claude Code, and say
        what happened where."""
        added = claude_mcp.add_to_claude()
        self._tell("Connect Claude", added.describe())

    def _reference(self) -> None:
        """Open the reference image's page, under Tools."""
        self._show_section(self.REFERENCE)

    def _reference_page(self, frame: ttk.Frame) -> None:
        """The reference image: a picture laid over Archicad's 3D window.

        Two panels, what the picture is and where it is, built by ``overlay``
        into this window's own panels so they line up with every other page.
        It is told which project is chosen up here, as a question rather
        than a name, so that the Archicad window it looks for is the one
        chosen at the moment the button is pressed.
        """
        picture = self._panel(frame, 0, title="Picture")
        placing = self._panel(frame, 1, title="Over Archicad")
        self.palette = overlay.Palette(
            picture,
            placing,
            project=lambda: self.options.project,
            explain=self._explain,
            on_change=self._paint_tabs,
        )

    @staticmethod
    def _explain(widget: tk.Widget, title: str, text: str) -> None:
        """Explain a control in the sidebar's card, under that name."""
        Tooltip(widget, text, title=title)

    def _picture_open(self) -> bool:
        """Whether the reference picture is on the screen."""
        palette = getattr(self, "palette", None)
        return palette is not None and palette.showing

    @staticmethod
    def _website() -> None:
        """The product's site, in the browser."""
        import webbrowser

        webbrowser.open(WEBSITE)

    @staticmethod
    def _styles_home() -> None:
        """site-analyst.com, where the sheets' four styles come from."""
        import webbrowser

        webbrowser.open(site_theme.SITE_ANALYST)

    def _about(self, at: str = "") -> None:
        """Open the info box, at the top or at the data sources.

        Imported here rather than at the top of the module: ``about`` reads
        ``Scroller`` out of this one, so a module-level import either way
        round is a cycle, and this is the side where the cost is a dictionary
        lookup the first time somebody presses a button.
        """
        from sun_study.app import about

        about.show(self.root, at=at)

    def _sections(self) -> None:
        """One page per output, reached from a list of pages down the left.

        A sidebar rather than the strip of tabs that was here, for three
        reasons. The strip's drawings and names took 140 px of height off
        every page, which on a laptop was a fifth of the window. Its one
        mark for *queued* was a blue name and a dot, on the smallest thing in
        it. And it had no room to say how much a page would make.

        A row in the sidebar says all three without being opened. The open
        page is the blue bar; a page that draws something has a switch that
        queues it, and a pill with the sheets it will make; and the three
        kinds of page -- set-up, studies, tools -- are three groups under
        their own captions, the way Archicad lists the pages of a settings
        dialog. The card that explains what is under the pointer sits in the
        room left at the foot.
        """
        #: The sections, in sidebar order, the groups flattened into one list.
        #: The groups are drawn by ``_strip``; everything else -- the
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
        #: The pages' names in the sidebar, by title: the button that opens
        #: each. Which one is open is in the style it wears.
        self.tabs: dict[str, ttk.Button] = {}
        #: And the rest of each row: the row itself, its pill, and its switch
        #: with the variable the switch shows -- for a page that has a study.
        self.side_rows: dict[
            str, tuple[ttk.Frame, ttk.Label, ttk.Checkbutton | None, tk.BooleanVar]
        ] = {}
        #: Which section is showing. Never empty: there is no state of this
        #: window with no page open.
        self.showing = self.GENERAL

        self._strip()

        self.stack = ttk.Frame(self.pane, style="Page.TFrame")
        self.stack.pack(side="top", fill="both", expand=True)

        builders = {
            self.GENERAL: self._general,
            self.SITE: self._site,
            self.MODEL: self._model,
            self.DIAGRAMS: self._diagrams,
            self.SHADOWS: self._shadows,
            self.EYE: self._sun_eyes,
            self.YIELD: self._yield,
            self.REFERENCE: self._reference_page,
        }
        for title in self.titles:
            builders[title](self._section(title))
        self._show_section(self.GENERAL)

    def _strip(self) -> None:
        """The pages, in their three groups, down the sidebar."""
        pages = ttk.Frame(self.side, style="Side.TFrame")
        pages.pack(side="top", fill="x")
        # And only now the help card, so the pages are given their height
        # first and the card takes what is left.
        self.info.pack(side="bottom", fill="x")
        first = True
        for kind, group in self.GROUPS:
            ttk.Label(pages, text=kind, style="Group.TLabel").pack(
                side="top", anchor="w", padx=10, pady=(4 if first else 14, 4)
            )
            first = False
            for title in group:
                self._tab(pages, title, queues=kind == self.DRAWS)

    def _tab(self, pages: ttk.Frame, title: str, *, queues: bool) -> None:
        """One page in the sidebar: its name, what it will make, its switch.

        The whole row opens the page; the switch, on a study's row, queues
        the study without opening anything. The row is a frame so that the
        open one can wear a rounded blue face under all three.
        """
        row = ttk.Frame(pages, style="SideRow.TFrame", padding=(8, 2, 6, 2), height=32)
        row.pack(side="top", fill="x", pady=1)
        row.pack_propagate(False)
        name = ttk.Button(
            row,
            text=title,
            style="Side.TButton",
            command=partial(self._show_section, title),
        )
        lit = tk.BooleanVar(value=False)
        switch: ttk.Checkbutton | None = None
        if queues:
            switch = ttk.Checkbutton(
                row,
                style="Switch.TCheckbutton",
                variable=lit,
                command=partial(self._flip_section, title),
            )
            switch.pack(side="right")
            Tooltip(
                switch,
                "Queues this page's study for the next run, or takes every study "
                "on the page out of it. A page with more than one study turns "
                "its main one on; the others are switched on the page itself.",
                title=f"Run {title.lower()}",
            )
        pill = ttk.Label(row, text="", style="Badge.TLabel")
        name.pack(side="left", fill="both", expand=True)
        row.bind("<Button-1>", lambda _event: self._show_section(title))
        Tooltip(name, self.SECTION_BLURB[title], title=title)
        self.tabs[title] = name
        self.side_rows[title] = (row, pill, switch, lit)

    def _flip_section(self, title: str) -> None:
        """The sidebar switch of one page: every study on it off, if any is
        on; otherwise its lead study on."""
        studies = [(name, tick) for name, tick, where in self._studies() if where == title]
        if any(tick.get() for _name, tick in studies):
            for _name, tick in studies:
                tick.set(False)
        elif studies:
            lead = self.LEADS.get(title, studies[0][0])
            for name, tick in studies:
                if name == lead:
                    tick.set(True)
        self._sync()

    def _paint_tabs(self, sheets: Sequence[Sheet] | None = None) -> None:
        """Say which page is open, which will run, and how much each makes.

        Open is the blue bar. Queued is the switch, and what it is worth is
        the pill beside it -- two marks on two things, so a page that is both
        says both.
        """
        if sheets is None:
            sheets = self.planned()
        where_of = {name: where for name, _tick, where in self._studies()}
        running = {where for _name, tick, where in self._studies() if tick.get()}
        made: dict[str, int] = {}
        for sheet in sheets:
            if sheet.paper and sheet.job in where_of:
                page = where_of[sheet.job]
                made[page] = made.get(page, 0) + 1
        for title, (row, pill, switch, lit) in self.side_rows.items():
            open_here = title == self.showing
            row.configure(style="SideRowOpen.TFrame" if open_here else "SideRow.TFrame")
            self.tabs[title].configure(style="SideOpen.TButton" if open_here else "Side.TButton")
            if switch is not None:
                lit.set(title in running)
                switch.configure(
                    style="SwitchOpen.TCheckbutton" if open_here else "Switch.TCheckbutton"
                )
            words = str(made[title]) if made.get(title) else ""
            if title == self.REFERENCE and self._picture_open():
                words = "open"
            pill.configure(text=words, style="BadgeOpen.TLabel" if open_here else "Badge.TLabel")
            if words and not pill.winfo_manager():
                pill.pack(side="right", padx=(4, 8))
            elif not words and pill.winfo_manager():
                pill.pack_forget()

    def _section(self, title: str) -> ttk.Frame:
        """One page, and the frame its settings are built into.

        Each scrolls on its own rather than all of them inside one scroller,
        because they are not the same length: Solar analysis asks about three
        studies and is three times General. One scroller would size itself to
        the longest and leave every short page with a bar that moves nothing.

        Built now and shown later. Every page exists from the moment the
        window opens, so reading the project fills all of them at once and
        moving between them costs nothing. Headed by its name and one line,
        so the page says where you are without the sidebar.
        """
        pane = Scroller(self.stack, ground=theme.PAGE)
        self.panes.append(pane)
        self.pane_of[title] = pane
        # The page's own width is what it rearranges for, so it is the
        # page's resizing that asks: the frame round it is resized first, and
        # asked from there the page had not yet been told its new width.
        pane.canvas.bind("<Configure>", self._respond, add="+")
        head = ttk.Frame(pane.content, style="Page.TFrame", padding=(PAD * 3, 16, PAD * 3, 4))
        head.pack(side="top", fill="x")
        ttk.Label(head, text=title, style="PageTitle.TLabel").pack(side="left")
        ttk.Label(head, text=self.SECTION_SHORT[title], style="PageBlurb.TLabel").pack(
            side="left", padx=(12, 0), pady=(2, 0)
        )
        frame = ttk.Frame(pane.content, style="Page.TFrame", padding=(PAD * 3, 8, PAD * 3, 16))
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
            "So the output is filed where a reader expects it: 'Solar |' "
            "gives 'Solar | Solar Analysis.Results'. An office that numbers "
            "its layer groups types its own number in. It is also how a rerun "
            "finds its own sheets to replace, so changing it leaves the last "
            "run's behind to be deleted by hand, and it cannot be emptied — an "
            "empty prefix matches every layout in the project."
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
            "Your template's site group, if it keeps the neighbours in one.",
            "Blank, the fetched neighbours and the ground under them go on "
            "'Site Context.Buildings', '.Terrain' and '.Roads'. Give the group "
            "your template files its site in and they go there instead, in "
            "front of the same words; a layer that is already there is used "
            "rather than duplicated. Only the group is yours to choose — the "
            "wording after it is fixed.",
        )
        frame, row = self._panel(outer, 2, title="Tables"), 0
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
        frame, row = self._panel(outer, 1, title="Layers the sun studies see"), 0
        self._caption(
            frame,
            row,
            "What every solar study reads the model under: what shows is what is "
            "measured and what casts shadow. Set once for the project.",
        )
        row += 1
        self.combination, row = self._combo(
            frame,
            row,
            "Layer combination",
            "The layer combination every solar study reads the model under.",
            "Nothing is exported to a file any more, but the layer state still "
            "decides every number: the add-on reads the 3D model Archicad has "
            "built, and that model holds only what is shown. The run sets this "
            "combination, forces on what the study needs over the top, and puts "
            "every layer back afterwards — so the answer does not depend on "
            "what happened to be on screen.",
        )
        self.require, row = self._picker(
            frame,
            row,
            "Layers forced visible",
            "Layers switched on for every solar study, whatever the combination says.",
            "Shared by all three solar studies, which is why it is here rather "
            "than in any one. The zone layers must be in the model or the "
            "drawings cannot be placed on the building — each needs a Zone to "
            "line the model up against, and an office's usual combinations "
            "hide them. Left empty, the facade and communal studies add the "
            "zone layers themselves and the apartments study adds its own.",
        )
        self.context, row = self._picker(
            frame,
            row,
            "Neighbouring buildings",
            "Layers that shade the site without being part of it.",
            "Switched on for every solar study, because a neighbour that is not "
            "in the model shades nothing, and a building measured with nothing "
            "around it can only be given more sunlight than it gets. Named by "
            "layer and not by element name because survey context usually "
            "arrives nameless — on one project all 232 neighbours are unnamed "
            "slabs. The site analysis's own model goes on 'Site "
            "Context.Buildings' and '.Future buildings'; name those here to "
            "study against it. Never measured: the facade study measures its "
            "facade layers and the communal study its Zones.",
        )
        self.hide, row = self._picker(
            frame,
            row,
            "Layers hidden on sheets",
            "Layers switched off on the study drawings and in the model read.",
            "Grids and dimension layers usually: they are the practice's own "
            "annotation and clutter a sun study without adding to it. What "
            "counts as clutter is a decision about the drawing, so it is named "
            "here rather than guessed from layer names.",
        )

    def _days_panel(
        self,
        outer: ttk.Frame,
        row: int,
        days: dict[str, tk.BooleanVar],
        *,
        study: str,
        year: bool,
    ) -> tuple[ttk.Entry, ttk.Entry | None]:
        """The days a study runs on, in a box of its own on that study's page.

        Asked on the Solar analysis tab and again on the Sun views tab, with
        an answer each. One set of ticks used to serve both, and it sat on the
        Model tab -- a page about what geometry leaves Archicad -- where
        nobody planning either study thought to look for it, and where a day
        ticked for the apartments quietly ran the sun views on it too. The
        question belongs with the study it changes, and the two studies are
        not always asked on the same days: the ADG test is midwinter, and a
        set of sun views is often wanted for the equinox beside it.

        Days are pressed and not picked, because a study is usually asked for
        on more than one. A council wants midwinter for the test and the
        equinox beside it to show the year, and choosing one at a time meant
        running the whole tool again and remembering to change the box.
        Every lit day runs the tools once each, and every name a run makes
        carries its day, so the sets stand beside each other in the project
        rather than over each other.

        The year is asked once, with the solar analysis, and read by every
        sun tool: it only shifts the sun positions slightly, and two studies
        of one project are never wanted against different years. Returned
        along with the custom-day entry, so the caller keeps both.
        """
        frame = self._panel(outer, row, title="Days studied")
        row = 0
        ttk.Label(frame, text="Days", anchor="e").grid(
            row=row, column=0, sticky="e", padx=(0, 12), pady=(6, 0)
        )
        toggles = Toggles(frame, on_change=self._sync)
        toggles.grid(row=row, column=1, sticky="w", pady=(6, 0))
        self.toggle_rows.append(toggles)
        for name, (_, title) in ASSESSMENT_DAYS.items():
            state = tk.BooleanVar(value=name == "winter")
            days[name] = state
            # A button with the sun at that day's height, rather than a box.
            box = toggles.add(state, title.split(",")[0], f"day_{name}")
            Tooltip(
                box,
                f"{title}. "
                + (
                    "The shortest day, the worst case the ADG assesses and the only "
                    "day its two-hour test means anything. Left lit unless a "
                    "council asks otherwise."
                    if name == "winter"
                    else "Shows the year beside the midwinter case. A run on this day "
                    "carries it in every layer, view, sheet and property it makes."
                )
                + f" Only the {study} reads this row.",
            )
        row += 1
        custom, row = self._entry(
            frame,
            row,
            "Custom day",
            "",
            "Any other days, as MM-DD, comma separated. Run in addition to the lit days.",
            "For a council that asks for a date the three buttons do not cover "
            "-- the 22nd rather than the 21st, or a day named in a DCP. "
            "Written MM-DD, e.g. 07-15, and several with commas between. It "
            "runs as well as whatever is lit, "
            f"so the usual pair plus one is three runs of the {study} rather "
            f"than a choice between them. Only the {study} reads this box; "
            "the other sun studies have a box of their own.",
        )
        if not year:
            return custom, None
        typed, row = self._entry(
            frame,
            row,
            "Year",
            "2024",
            "Which year's sun positions to use, for every sun study.",
            "The year only shifts the sun positions slightly; it is here so a "
            "study can be repeated against the same day as an earlier report. "
            "Asked once: the sun views and the shadow diagram read it too.",
        )
        return custom, typed

    def _facade(self, frame: ttk.Frame, row: int) -> int:
        """The facade study's rows: the 3D skin, what gets painted, how finely."""
        # Off, like every other study. The basic preset -- what Forget goes
        # back to -- is a window with nothing queued: a study that is ticked
        # before anybody has decided to run it is one that runs because it
        # was not noticed, and the facade study is the long one.
        self.do_facade = tk.BooleanVar(value=False)
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
            "makes over five thousand at 0.5 m, over twenty thousand at 0.25 m "
            "and well over a hundred thousand at 0.1 m. A face narrower than "
            "one cell is not drawn at all, so a coarse setting loses thin "
            "columns.",
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
        # First the days, because they are the first thing a council names;
        # then the two settings all three studies share, in a card of their
        # own: nothing floats on the page by itself.
        outer = frame
        self.custom_day, year = self._days_panel(
            outer, 0, self.days, study="solar analysis", year=True
        )
        assert year is not None
        self.year = year
        frame, row = self._panel(outer, 1, title="Layout Book filing, and what the plans show"), 0
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

        self.plan_combination, row = self._combo(
            frame,
            row,
            "Plan combination",
            "The layer combination the plans are drawn over, under the sunlight.",
            "What a reader expects to see under the colours: the walls, the "
            "doors, the apartment names -- the office's own plan, not the model "
            "the study reads. Used by the apartment plans and the communal "
            "plans alike. Left blank, they are drawn over the Model tab's "
            "combination, which is chosen for measuring and not for looking at. "
            "Without any, each run would start from whatever the last one left "
            "on screen, and over a few runs the sheets drift to showing the "
            "study and nothing under it.",
        )

        self.plan_kinds, row = self._tiles(
            frame,
            row,
            "Plans",
            "What the apartment plans show: the sun at each time, the floor as a "
            "heat map, each apartment's total -- any of the three.",
            "Three plans for three questions. Sun at each time is a plan per "
            "instant showing where the sun actually falls, which is what "
            "somebody standing there at nine in the morning asks about. The "
            "floor heat map grids each apartment and bands every cell by its "
            "hours of sun over the day, which says how far in the sun gets. "
            "The apartment total fills each flat whole in the band of its "
            "hours over the day and writes the figure in, which is what the "
            "ADG and a DCP ask about. The communal space draws the first and "
            "one banded plan for either of the other two. Each tile switches "
            "on and off by itself; the last one lit stays lit, because no "
            "plans at all is not a plan study.",
        )

        self.see_glass, row = self._tiles(
            frame,
            row,
            "Glass",
            "Whether glass balustrades, screens and canopies cast shade.",
            "Solid is how every study measured until there was a choice: a "
            "glass balustrade shades the balcony and the room behind it as if "
            "it were a wall. The other two let the sun through every surface "
            "at least that transparent in Archicad -- all glass, or clear glass "
            "only -- while the rails and posts round a panel still cast "
            "shade. Windows, doors, skylights and curtain walls stay solid "
            "whatever is chosen: they are a building's envelope, and sun let "
            "through them would shine through the building behind. Used by "
            "all three studies.",
        )
        self.see_glass.set("off")

        self.do_plans = tk.BooleanVar(value=False)
        # The study's own box. Everything from here to the end of the block
        # is built inside it, by the simple means of pointing ``frame`` at it:
        # the rows beneath neither know nor care.
        resume = 2
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
        self.floor_grid, row = self._tiles(
            frame,
            row,
            "Floor grid",
            "",
            "How finely each apartment's floor is sampled for the sun patches "
            "and the heat map. It changes the drawings, not the ADG figure: the "
            "hours per apartment are read at the glazing, which is sampled every "
            "0.2 m whatever this says. Finer draws the patch edge more truly and "
            "casts more rays: 0.1 m is over six times the rays of 0.25 m.",
        )
        self.floor_grid.set("0.25")
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
            "Half a metre reads a courtyard properly; 0.25 m is for a narrow "
            "terrace, or an area figure that sits close to the threshold, at "
            "four times the samples, and 0.1 m for a small space measured "
            "closely. This is separate from the ground grid on "
            "purpose: the ground is the whole site, and gridding all of it "
            "this finely costs four times the samples for an answer nobody "
            "asked of it.",
        )
        self.communal_grid.set("0.5")
        self.cos_schedule, row = self._combo(
            frame,
            row,
            "Communal schedule",
            "The project's schedule for the hourly sheets, in place of the drawn table.",
            "The office's COS sheet carries an Archicad schedule rather than a "
            "table -- 'Areas COS solar': a row per hour, its time, the sunlit "
            "area and its share. Picked here, every sunlit fill of each hour "
            "gets that hour's time and share as the IFC properties Time and "
            "Percentage (set 'Solar Analysis'), and the schedule goes on the "
            "sheet beside the plans; Archicad sums the area itself, so the "
            "schedule stays live. Archicad cannot make a schedule through its "
            "API, so the scheme has to be in the project already. Needs the "
            "Times plans, and Archicad 26 to 28 -- 29 and 30 cannot store an IFC "
            "property from an add-on, and the drawn table is used there. None "
            "draws the table as before.",
        )

    def _shadows(self, frame: ttk.Frame) -> None:
        """The shadow page: what casts the shadows, then the two ways to draw them.

        Four panels. The days, as on the other sun pages. *Layers and hours*,
        set up rather than switched on: one row per line of the office's
        legend, each naming the layers that hold that row's massing, picked
        out of the open project, and the hours drawn -- what both drawings
        under it read, so they are chosen once (D160). Then the two drawings,
        each under its own switch with only what is its own:

        - **Shadow diagram**, the route for every diagram that involves the
          neighbours (D144): a 3D Document per legend row and hour, looking
          straight down with the sun at that hour, the rows of an hour
          stacked in one drawing so each shows what it adds to the rows above
          it, in the legend's colours, on a combined sheet per day. Archicad
          casts every shadow. Roadmap R1; ``docs/shadow-plans.md``.
        - **Every hour on one drawing**, Loriini's own caster, kept for the
          one drawing the documents cannot make: the design's massing -- the
          Proposed row -- at every hour on one plan, imported as fills.

        The rows are fixed because the legend is: three that will be there
        whatever is approved, which accumulate, and the rest being compared,
        which overlap. A row left empty is left off the sheet, and the others
        keep their colours -- they are matched by name, not dealt out by
        position. With no row chosen the documents are one set under the
        layer combination, which is what the set name and the shadow pen are
        for.
        """
        outer = frame
        frame, row = self._panel(outer, 1, title="Layers and hours"), 0
        self._caption(
            frame,
            row,
            "What casts the shadows, one legend row to a set of layers, and the hours "
            "drawn. Both drawings below read these; the Proposed row is the design's "
            "massing.",
        )
        row += 1

        #: The legend, row by row: the name the run is given, whether the row
        #: accumulates or is compared, and its layer picker. Read by ``jobs``,
        #: for the documents and for the every-hour drawing, which takes its
        #: design from the rows being compared.
        self.shadow_rows: list[tuple[str, str, Chips]] = []
        for short, role, label, hint, detail in SHADOW_LEGEND_ROWS:
            picker, row = self._picker(frame, row, label, hint, detail)
            self.shadow_rows.append((short, role, picker))
        self.shadow_hours, row = self._ticks_row(
            frame,
            row,
            "Hours",
            "The whole hours drawn, on each of those days.",
            "A document per hour per day in the shadow diagram, and every one of "
            "them on the every-hour drawing. Nine to three is the assessed "
            "window; the long shadows at either end are correct and surprise "
            "people — on 21 June the sun is about 19 degrees up and a shadow "
            "runs nearly three times the height that casts it.",
            _hour_choices(clock=False),
            key=_clock_text,
            initial=DEFAULT_SHADOW_HOURS,
        )
        self.shadow_study_subset, row = self._combo(
            frame,
            row,
            "Subset — shadow sheets",
            "Layout Book subset both drawings' sheets go into.",
            "Same rule as the other two: the subset has to exist already, "
            "because the Layout Book is the office's structure to organise. A "
            "missing one is reported rather than invented, with the sheets "
            "left at the root of the book.",
        )
        # The days, the same three buttons the other two sun studies press,
        # in a box of their own above everything: the day is the first thing
        # a council names, and the same card in the same place on every page
        # is found without looking.
        self.shadow_custom_day, _ = self._days_panel(
            outer, 0, self.shadow_day_ticks, study="shadow diagram", year=False
        )
        self._shadow_documents(outer, 2)
        self._shadow_every_hour(outer, 3)

    def _shadow_documents(self, outer: ttk.Frame, at: int) -> None:
        """The shadow diagram: 3D Documents from overhead, Archicad's own shadows.

        The legend rows and the hours are the panel above's; what is this
        drawing's own is the layer combination the documents show, the pens
        they print in, and the name and pen of a set drawn without the
        legend.
        """
        self.do_shadows = tk.BooleanVar(value=False)
        frame, row = self._panel(outer, at), 0
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
            "The days and hours as 3D Documents looking straight down, each "
            "with Archicad's sun for that hour and its own vectorial sun "
            "shadows, placed on sheets by day. With layers chosen for the "
            "legend rows, a document is made per row and every row of an hour "
            "is stacked in one drawing on a combined sheet, each row's shadow "
            "in its legend colour where it adds to the rows above it. With "
            "none, one set under the layer combination. Needs the current "
            "add-on, and a floor plan tab in front when it runs.",
        )
        row += 1
        self._caption(
            frame,
            row,
            "Every legend row of an hour as 3D Documents from overhead, stacked in one "
            "drawing, each in its colour, with Archicad's own shadows.",
        )
        row += 1
        self.shadow_plan_combination, row = self._combo(
            frame,
            row,
            "Layers",
            "The layer combination the documents show: what casts shadow and what catches it.",
            "Everything showing casts a shadow and catches one, so the ground "
            "has to be in it -- a plan with no terrain or site slab under the "
            "buildings has nothing for the shadows to fall on. With legend rows, "
            "each row's combination is made from this one. Nothing is picked "
            "for you: Run asks when it is blank.",
        )
        self.shadow_plan_pen_set, row = self._combo(
            frame,
            row,
            "Pen set",
            "The project's pen set the documents use. Blank keeps each view's own.",
            "The practice's drawing pens, so the sheet prints the way the other "
            "DA drawings do. With legend rows the run copies it, each row's pen "
            "set to the legend's colour.",
        )
        self.shadow_plan_label, row = self._entry(
            frame,
            row,
            "Set name",
            "",
            "A word in every document and sheet name, for a set without the legend.",
            "Without legend rows the documents are one set under the layer "
            "combination, and a name tells two such sets apart: Existing, "
            "Proposed. With legend rows each set is named for its row, and "
            "this is not used. Blank names neither.",
        )
        self.shadow_plan_pen, row = self._entry(
            frame,
            row,
            "Shadow pen",
            "",
            "The pen the shadows are filled in, for a set without the legend.",
            "A pen number from the project's pen set. With legend rows each row "
            "takes the pen nearest its legend colour and this is not used. "
            "Blank keeps the project's defaults for new 3D Documents.",
        )

    def _shadow_every_hour(self, outer: ttk.Frame, at: int) -> None:
        """The design's shadow at every hour on one drawing: Loriini's fills.

        The one drawing the documents cannot make, since a document is one
        hour (D144): the design's massing at every hour ticked above, each
        hour a fill labelled by its hour, on the floor plan, with its view
        and a sheet per day fitted to the shadows (D149). The massing is the
        Proposed row above, or the last row being compared when Proposed is
        empty, and this panel says which, by name, so nobody has to know the
        rule; the other rows are what it lands on. Loriini casts it with its
        own ray caster and imports the fills into the drawing, so the ground
        it lands on and the storey it is drawn on are asked here and nowhere
        else on the page. ``D160``.
        """
        self.do_shadow_hours = tk.BooleanVar(value=False)
        frame, row = self._panel(outer, at), 0
        box = ttk.Checkbutton(
            frame,
            text="Every hour on one drawing",
            variable=self.do_shadow_hours,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Shadow diagram"),
        )
        self._head(frame, box, SHADOW_HOURS_JOB)
        Tooltip(
            box,
            "The design's massing -- the Proposed row above -- at every hour "
            "ticked above, on one plan: each hour a fill labelled by its hour, "
            "with its own view and a sheet per day. Cast by Loriini and imported "
            "as fills, because a 3D Document is one hour.",
        )
        row += 1
        self._caption(
            frame,
            row,
            "The design's massing at every hour above, imported as fills into one drawing.",
        )
        row += 1
        name = ttk.Label(frame, text="Massing", anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(6, 0))
        #: Which legend row the drawing draws, and its layers: said here, and
        #: chosen in Layers and hours. Rewritten by ``_sync``.
        self.shadow_hours_design = ttk.Label(frame, text="", anchor="w", wraplength=620)
        self.shadow_hours_design.grid(row=row, column=1, sticky="w", pady=(6, 0))
        Tooltip(
            name,
            "The Proposed row in Layers and hours, or the last row being compared "
            "when Proposed is empty. Choose its layers there.",
            title="Massing",
        )
        row += 1
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
            "Ignore ground below (m)",
            "",
            "Metres. Blank keeps all of it.",
            "A survey often runs past the neighbourhood into ground tens of "
            "metres lower, and a shadow reaching that falls the whole way and "
            "runs on for hundreds of metres. Right arithmetically, and not "
            "what the sheet is asking.",
        )
        self.shadow_grid, row = self._tiles(
            frame,
            row,
            "Shadow grid",
            "",
            "How closely the ground is sampled: the same four steps as every "
            "solar grid. The edges are traced to the true shadow line at any "
            "step (D161); a finer grid catches what is narrower than it -- a "
            "gap between two buildings, a thin balcony's shadow -- at four "
            "times the samples each step down. Normal suits a building; Finest "
            "is for a small one, not a whole site.",
        )
        self.shadow_grid.set("0.5")
        self.shadow_storey, row = self._combo(
            frame,
            row,
            "Draw on storey",
            "The project's storey the fills are placed on. Blank is the ground, storey 0.",
            "Where the fills land, not what casts them. Picked from the "
            "project's own storeys once it has been read, because a site "
            "drawing is usually the ground storey and that is not always "
            "storey 0: a project with a survey datum below it numbers the "
            "ground 6, and fills drawn on 0 land in a plan nobody opens and "
            "read as nothing drawn at all. A number typed here is still taken "
            "as the storey's index, which is what older settings files hold.",
        )
        self.shadow_hours_colour, row = self._combo(
            frame,
            row,
            "Colour",
            "Each hour a 25 % drafting fill in the pen nearest it, no outline.",
            "The office's red, its pen 45, or the nearest blue (D147): dots "
            "rather than a solid, so the hours over one another all show.",
        )
        self.shadow_hours_colour.configure(
            values=SHADOW_HOURS_COLOURS, state="readonly", width=self.NUMBER_WIDTH
        )
        self.shadow_hours_colour.set(SHADOW_HOURS_COLOURS[0])

    def _paint_design(self) -> None:
        """Say in the every-hour panel which massing it will draw.

        The row by its label and its layers, or what to do when there is
        none: the drawing's design is chosen in Layers and hours, and a panel
        that only said "the Proposed row" left the person looking for a
        massing picker that is not in it.
        """
        short = self._designed_row()
        for row, _role, box in self.shadow_rows:
            if row == short:
                label = next(words for name, _r, words, _h, _d in SHADOW_LEGEND_ROWS if name == row)
                self.shadow_hours_design.configure(
                    text=f"{label}: {', '.join(self._listed(box))}", foreground=""
                )
                return
        self.shadow_hours_design.configure(
            text="none yet — choose the Proposed row's layers in Layers and hours",
            foreground=HINT,
        )

    def _sun_eyes(self, frame: ttk.Frame) -> None:
        """The sun eye views: the model seen from the sun, one view per hour.

        Everything it can see is in sun and everything hidden is in shade,
        which answers "why is this balcony dark at ten" in one picture. The
        settings here are the ones read off the practice's own diagrams; the
        hours come from the ruleset's assessment window, and the days from
        the views' own box above the study -- a sun eye set at the wrong
        date is a plausible picture of the wrong day, so the day is said
        where the views are asked for.

        Needs the Loriini add-on, and a floor plan tab in front
        when it runs: the projection can only be written with the window and
        the current database agreeing, and the run says so if they do not.
        """
        row = 0
        self.do_sun_eyes = tk.BooleanVar(value=False)
        # The study's own box, in the page's second row: the days box is
        # the first. Everything from here to the days box is built inside
        # it, by the simple means of pointing ``frame`` at it: the rows
        # beneath neither know nor care.
        outer = frame
        frame, row = self._panel(outer, 1), 0
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
            "Seven views along the sun, 9am to 3pm on each day lit above, each exact to the "
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
            "The ruleset's window, 9 to 15, lit to begin with.",
            "Only for a sheet that needs fewer. The assessment window is the "
            "ruleset's and a set drawn at other hours is not the study. Lit "
            "from the start, as the shadow diagram's are, so the row shows "
            "the hours the views will be drawn at rather than leaving none "
            "lit to mean all of them; with none pressed it is still the "
            "ruleset's window.",
            _hour_choices(clock=False),
            key=_clock_text,
            initial=DEFAULT_SHADOW_HOURS,
        )
        # The views' own days, on this page and not on another tab. They
        # used to run on whatever the solar analysis was ticked for. Above
        # the study, where the other two sun pages have theirs.
        self.eye_custom_day, _ = self._days_panel(
            outer, 0, self.eye_days, study="sun views", year=False
        )

    def _site(self, frame: ttk.Frame) -> None:
        """Site and context analysis from an address, in four panels (D157).

        The address and what the outputs share come first: where the data
        comes from, the Summary of Controls, whether the project's location
        is set. Then a panel per
        output, each with its own switch, as the solar analysis has one per
        study: the Context Analysis sheet, the Site Analysis sheet and the 3D
        context with its future. Each is placed and turned in its own panel,
        and each is a run of its own (``_site_jobs``), so a sheet can be
        turned to its long boundary while the model stays on the project's
        north. Nothing here reads the project: everything after the address
        comes from NSW open data.
        """
        outer = frame
        self.do_site_context = tk.BooleanVar(value=False)
        self.do_site_site = tk.BooleanVar(value=False)
        self.do_site_summary = tk.BooleanVar(value=False)
        self.do_site_model = tk.BooleanVar(value=False)
        self.do_site_future = tk.BooleanVar(value=False)
        self.do_site_location = tk.BooleanVar(value=True)
        self.site_buttons: dict[str, ttk.Button] = {}

        # -- the address, and what every output shares -------------------------
        frame, row = self._panel(outer, 0, title="Address"), 0
        self._caption(
            frame,
            row,
            "Type the address, switch on the panels below, press Run. A few minutes: "
            "the public data services are slow.",
        )
        row += 1
        # The only section drawn from data nobody here owns, so it is the only
        # one that carries this. It opens the same box the About button at the
        # top does, scrolled to the registers -- the question ("where did this
        # line come from, and what do I have to put on the sheet") occurs on
        # this page, and an answer two clicks away on another one is an answer
        # nobody finds until a drawing has already gone out without its credit.
        where_from = ttk.Button(
            frame,
            text="Where this data comes from",
            command=partial(self._about, "sources"),
            **icons.button_options("info"),
        )
        # Across both columns: it is not a label, and as wide as it is it
        # would otherwise set this card's label column wider than every other.
        where_from.grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 6))
        Tooltip(
            where_from,
            "The six public registers a site analysis run fetches from, what "
            "each one answers for, the licence it is published under and the "
            "wording it asks to be credited with — and the one line, ready to "
            "copy, that a sheet drawn from them should carry.",
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
        row = self._site_toggles(
            frame,
            row,
            "Outputs",
            "The controls table, and whether the project is told where it is. Lit is done.",
            (
                (
                    self.do_site_summary,
                    "Controls",
                    "Summary of Controls layout",
                    "The planning-controls table, drawn straight onto a layout of "
                    "its own: zone, height of building, FSR and the gross floor area "
                    "it allows, minimum lot size, heritage, and the ADG figures "
                    "worked out for this site area. Council DCP rows are ruled up "
                    "empty; they are not open data.",
                ),
                (
                    self.do_site_location,
                    "Location",
                    "Set the project location from the address",
                    "Puts Options > Project Location at the site, with the survey "
                    "point on the MGA2020 grid, so the sun studies know where the "
                    "project is -- and, where a panel turns its output to the long "
                    "boundary, the project's north to match. Done once, by the "
                    "first panel that runs: the 3D context when it is on, the "
                    "Context Analysis otherwise, then the Site Analysis. The other "
                    "panels keep the location that one leaves. Only when that "
                    "panel places the site at the project origin, or the location "
                    "is still a city preset.",
                ),
            ),
        )

        # -- the Context Analysis sheet -----------------------------------------
        frame, row = self._site_panel(
            outer,
            1,
            self.do_site_context,
            "Context Analysis",
            SITE_CONTEXT_JOB,
            "Land use, transport, walking catchments and names around the site.",
            "Land use wash by LEP zone, schools and hospitals coloured by what "
            "they are, heritage items, rail, bus stops and routes, stations, "
            "5 and 10 minute walking catchments, place and street names, the "
            "neighbours' footprints on the paper styles, and the site -- the DA "
            "003 sheet, at the scale below.",
        )
        self.site_context_origin, self.site_context_north, row = self._site_placement(
            frame, row, "the context sheet"
        )
        # The house style each sheet is drawn in: site-analyst.com's four, and
        # only those (D152), a row in each sheet's panel -- a context sheet on
        # paper beside a site sheet on the photograph is how the office's
        # packages have it.
        self.site_theme, row = self._combo(
            frame,
            row,
            "Style",
            "The context sheet's style, one of site-analyst.com's four. Flamingo by default.",
            "Flamingo sits on plain paper: four tints with textures, every "
            "street white, the buildings white, green street names. Kingfisher "
            "is the masterplan palette, pale zone grounds, a white cadastre and "
            "white buildings. Heron is the office sheet over a grey aerial, "
            "white lots and lettering. Canary is Heron with the zoning in the "
            "NSW ePlanning colours, keyed by zone code. All four are "
            "site-analyst.com's, named as it names them; the link under this "
            "row opens it.",
        )
        self.site_theme.configure(values=list(CONTEXT_STYLES), state="readonly")
        self.site_theme.set(site_theme.theme(site_theme.DEFAULT_THEME).label)
        row = self._styles_link(frame, row)
        self.site_scale, row = self._combo(
            frame,
            row,
            "Scale",
            "The context sheet's scale. 1:3000 by default.",
            "Sets how much neighbourhood is fetched: the A1 map field at this "
            "scale, centred on the site. 1:2000 for a tight urban site, 1:4000 "
            "where the station is a long way off.",
        )
        self.site_scale.configure(values=list(CONTEXT_SCALES), state="readonly")
        self.site_scale.set("1:3000")

        # -- the Site Analysis sheet --------------------------------------------
        frame, row = self._site_panel(
            outer,
            2,
            self.do_site_site,
            "Site Analysis",
            SITE_SHEET_JOB,
            "The boundary, levels, neighbours, trees, sun path and winds.",
            "The boundary with its dimensions and corner levels, the fall, "
            "contours -- the City of Sydney's 1 m ones where its area covers the "
            "sheet, the state's 2 m ones elsewhere -- neighbours with storeys "
            "and zone, trees drawn the size of their canopy (as the council's "
            "inventory records it, inside the City of Sydney), poles, hydrants, "
            "driveways, kerbside parking, one-way streets, noise sources, sun "
            "path and prevailing winds -- the DA 004 sheet. With the future "
            "context on in the 3D context panel, the raised neighbours are drawn "
            "on it dashed, with their storeys.",
        )
        self.site_sheet_origin, self.site_sheet_north, row = self._site_placement(
            frame, row, "the site sheet"
        )
        self.site_site_theme, row = self._combo(
            frame,
            row,
            "Style",
            "The site sheet's style, one of site-analyst.com's four. Heron by default.",
            "Heron is the grey aerial with the zones hatched in its palette, the "
            "site in its red, the sun as an open crown and the winds as "
            "hand-drawn strands. Kingfisher is on paper: the buildings in their "
            "zone's colour, the sun paths as yellow crescents, the winds as "
            "blue ones. Flamingo is on paper with the office's drawn suns and "
            "winds. Canary is the office's classic sheet: one black circle for "
            "the sun and the winds, the zones in the ePlanning colours. All four "
            "are site-analyst.com's; the link under this row opens it.",
        )
        self.site_site_theme.configure(values=list(SITE_STYLES), state="readonly")
        self.site_site_theme.set(site_theme.site_theme(site_theme.DEFAULT_SITE_THEME).label)
        row = self._styles_link(frame, row)
        self.site_sheet_scale, row = self._combo(
            frame,
            row,
            "Scale",
            "The site sheet's scale. 'Fit the site' by default.",
            "'Fit the site' picks whichever of 1:200 to 1:750 the boundary fits "
            "the A1 map field at. A scale holds the sheet at it whatever the "
            "site's size: 1:500 for a set of sheets that should all read alike.",
        )
        self.site_sheet_scale.configure(values=list(SITE_SHEET_SCALES), state="readonly")
        self.site_sheet_scale.set(FIT_THE_SITE)

        # -- the 3D context -----------------------------------------------------
        frame, row = self._site_panel(
            outer,
            3,
            self.do_site_model,
            "3D context",
            SITE_MODEL_JOB,
            "Terrain, street blocks and the neighbours, as a model.",
            "The terrain as one mesh from the contours -- the City of Sydney's "
            "1 m ones inside its area, the state's 2 m outside, every one kept "
            "near the site and fewer towards the edge -- every street block as a "
            "kerbed mesh with the roads left between, and one slab per "
            "neighbouring building as tall as its storeys say -- or as the LEP "
            "height control allows, and said to be assumed. Three layers in the "
            "site group, one per kind -- 'Site Context.Terrain', '.Roads' and "
            "'.Buildings' -- so a view can show any of them without the others. "
            "The site's own buildings are left out.",
        )
        row = self._site_toggles(
            frame,
            row,
            "Future",
            "What the controls allow next door, stood in the model beside it.",
            (
                (
                    self.do_site_future,
                    "Future context",
                    "Future Context (what the controls allow next door)",
                    "Each existing building within the radius below, on land zoned "
                    "for flats, kept on its own footprint and raised to the storeys "
                    "the LEP's height control allows where it stands -- never "
                    "lowered, so one already over its control is left as it is. "
                    "Stood as slabs on 'Site Context.Future buildings' -- a layer of "
                    "its own, so a shadow diagram can be cast with the neighbours as "
                    "they are or as they could be -- and drawn dashed on the Site "
                    "Analysis sheet when that panel is on. The control is the LEP's: "
                    "the register carries it, and a council's DCP is not open data.",
                ),
            ),
        )
        self.site_model_origin, self.site_model_north, row = self._site_placement(
            frame, row, "the model"
        )
        self.site_radius, row = self._entry(
            frame,
            row,
            "Radius (m)",
            "500",
            "How far round the site the model reaches, and the future context with it.",
            "A square of this half-width around the site is fetched for the model: "
            "the contours, every building footprint and the height controls. The "
            "future context reaches as far from the site's boundary. 500 m is a "
            "neighbourhood; the fetch and the slabs both grow with the square of it.",
        )
        self.site_levels, row = self._combo(
            frame,
            row,
            "Model levels",
            "What RL project zero stands for. Type a number for a known RL.",
            "The terrain and the neighbours come in at AHD levels. 'The site's "
            "ground' places them against Project Location's altitude, so the "
            "ground lands near zero: right for a file whose storey 0 is the "
            "ground. 'Sea level' places them at true AHD: right for a file drawn "
            "in RLs. A number is the RL project zero stands for, in metres -- "
            "5.85 puts RL 6.00 at +0.15. When the run sets the project location, "
            "the same number goes into its altitude.",
        )
        self.site_levels.configure(values=list(LEVEL_WORDS))
        self.site_levels.set(next(iter(LEVEL_WORDS)))

    def _site_panel(
        self,
        outer: ttk.Frame,
        at: int,
        tick: tk.BooleanVar,
        name: str,
        job: str,
        caption: str,
        detail: str,
    ) -> tuple[ttk.Frame, int]:
        """One of the site page's output panels, headed by its own switch."""
        frame, row = self._panel(outer, at), 0
        box = ttk.Checkbutton(
            frame,
            text=name,
            variable=tick,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Site analysis"),
        )
        self._head(frame, box, job)
        Tooltip(box, detail)
        row += 1
        self._caption(frame, row, caption)
        return frame, row + 1

    def _site_toggles(
        self,
        frame: ttk.Frame,
        row: int,
        label: str,
        hint: str,
        outputs: Sequence[tuple[tk.BooleanVar, str, str, str]],
    ) -> int:
        """A row of lit-or-not buttons, each with its sentence in the tooltip."""
        name = ttk.Label(frame, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(6, 0))
        buttons = Toggles(frame, on_change=self._sync)
        buttons.grid(row=row, column=1, sticky="w", pady=(6, 0))
        self.toggle_rows.append(buttons)
        Tooltip(name, hint, title=label)
        for variable, short, full, detail in outputs:
            # The button wears the drawing its long label always had.
            button = buttons.add(variable, short, icons.BY_OUTPUT[short])
            Tooltip(button, detail, title=full)
            self.site_buttons[full] = button
        return row + 1

    def _site_placement(
        self, frame: ttk.Frame, row: int, what: str
    ) -> tuple[ttk.Combobox, ttk.Combobox, int]:
        """A panel's origin and north: where its output lands, which way up."""
        origin, row = self._combo(
            frame,
            row,
            "Origin",
            f"Where {what} lands: the project's location, or a point of the site at the origin.",
            "'Project location' trusts Options > Project Preferences > Project "
            "Location: the site is placed where the project's own georeferencing "
            "says it is, so it lines up with a model already there. The others put "
            "that point of the site at the project origin (0, 0) -- the centre, or "
            "a corner as the plan reads it after any turn, the way a model is "
            "usually set out -- for a project with nothing in it yet, or one "
            "still on the Sydney preset.",
        )
        origin.configure(values=[PROJECT_LOCATION, *ORIGIN_WORDS], state="readonly")
        origin.set(PROJECT_LOCATION)
        north, row = self._combo(
            frame,
            row,
            "North",
            f"Which way {what} faces. Turning applies with a point at the origin.",
            "'To the project's north' keeps the project's north angle, north up "
            "on a project that has none. 'Long boundary level' turns the site so "
            "its longest boundary runs across the plan; the panel that sets the "
            "project location writes the project's north to match, so the sun "
            "studies stay right. With 'Project location' the project already says "
            "which way the site faces, and this is not applied.",
        )
        north.configure(values=list(TURN_WORDS), state="readonly")
        north.set(next(iter(TURN_WORDS)))
        return origin, north, row

    def _styles_link(self, frame: ttk.Frame, row: int) -> int:
        """Where the styles come from, as a link under a style row (D152): a
        name in a picker is a word until somebody has seen the sheets it
        stands for, and the site that names them shows them."""
        styles_home = ttk.Label(
            frame, text="The four styles at site-analyst.com", style="Link.TLabel", cursor="hand2"
        )
        styles_home.grid(row=row, column=1, sticky="w", pady=(4, 2))
        styles_home.bind("<Button-1>", lambda _event: self._styles_home())
        Tooltip(
            styles_home,
            "Opens site-analyst.com in the browser: the site the four styles "
            "come from, named as it names them, with each one shown on a sheet.",
            title="site-analyst.com",
        )
        return row + 1

    def _yield(self, frame: ttk.Frame) -> None:
        """The yield analysis: the office's feasibility sheet from the massing.

        Roadmap R3. A massing is modelled in slabs, a floor each, and the
        question is what it comes to: the areas the controls are measured in,
        the units it holds, the parking they need. Which slabs are the massing
        is said by layer -- a layer per use, or one massing layer with the use
        told by level -- and by the renovation filter; or, with no layer
        named, by what is showing.

        Three boxes (D159). The study's own says what is measured and what it
        is called, and where the sheet and the workbook go; the second the
        site and the controls it is measured against; the third the
        efficiencies, the mix and the parking figures, which are set once for
        the practice and kept with Save as default. Two uses: residential
        and commercial, which is the shops as well as the offices. Every one
        of the figures is also an input cell in the workbook the run writes,
        so a what-if is typed into Excel.
        """
        row = 0
        self.do_yield = tk.BooleanVar(value=False)
        # Kept as a value, not drawn: a preset saved when the renovation filter
        # was a checkbox still opens on "Floor plan's filter" (``apply``).
        self.yield_renovation = tk.BooleanVar(value=False)
        outer = frame
        frame, row = self._panel(outer, row), 0
        box = ttk.Checkbutton(
            frame,
            text="Yield analysis",
            variable=self.do_yield,
            command=self._sync,
            style="Study.TCheckbutton",
            **icons.study_options("Area and yield"),
        )
        self._head(frame, box, YIELD_JOB)
        Tooltip(
            box,
            "Measures the massing slabs to their edges -- arcs and holes and "
            "all -- gathers them into levels by height, and works the office's "
            "feasibility sheet from them: BEA, GFA and NLA for each use, the FSR "
            "against the permissible, the units at the mix below, the parking and "
            "the basements. Drawn as the Yield Analysis sheet, and written to the "
            "tables folder as the office's template, one sheet per option, whose "
            "figures recalculate when an input is changed.",
        )
        row += 1
        self.yield_panel = frame
        # Which slabs are the massing, and how each one's use is told, is one
        # question with four answers, and the page shows only the rows the
        # answer needs (D140): a page of seven layer and level rows asked
        # every question at once, most of them for a way of modelling the
        # person was not using.
        self.yield_slabs, row = self._tiles(
            frame,
            row,
            "Slabs",
            "Which slabs are the massing. Everything showing is the usual answer.",
            "Everything showing: every slab on a layer that is showing, its use told by "
            "the level it stands on. Chosen layers: the slabs on the layers you choose, "
            "the use told the same way. Layer per use: a layer of residential slabs and "
            "one of commercial. Layer per option: each layer one whole option, "
            "a sheet and a workbook page each.",
        )
        self.yield_renovation_status, row = self._tiles(
            frame,
            row,
            "Renovation",
            "Which slabs count by their renovation status. Any, unless the massing is New.",
            "Read off each slab's own Renovation Status, so nothing has to be set on the "
            "floor plan first. New only: the proposal over a building that stays. Existing "
            "and new: everything but what is to be demolished. Floor plan's filter: what "
            "the floor plan's renovation filter shows, set there before Run.",
        )
        self.yield_groups: dict[str, list[tk.Misc]] = {}

        def rows_of(key: str, made_from: set[str]) -> None:
            # Only what the rows put on the grid: a control's hint is made and
            # never placed (its sentence goes to the info band), and gridding
            # it to show the row would drop it at the panel's top corner.
            self.yield_groups[key] = [
                child
                for child in frame.winfo_children()
                if str(child) not in made_from and child.winfo_manager() == "grid"
            ]

        before = {str(child) for child in frame.winfo_children()}
        self.yield_option, row = self._entry(
            frame,
            row,
            "Option",
            "Option 01",
            "What this massing is called: its sheet in the workbook and its layout.",
            "A run with the same name replaces that option's sheet in the workbook and "
            "its layout; another name adds an option beside the ones already there.",
        )
        rows_of("option", before)
        before = {str(child) for child in frame.winfo_children()}
        self.yield_option_layers, row = self._picker(
            frame,
            row,
            "Option layers",
            "Each layer chosen is one whole option, named after its OPT number.",
            "One option a layer, a sheet in the workbook and a layout each, named after "
            "the layer's OPT number -- '...3D OPT1' is Option 01 -- with the use of each "
            "slab told by its level. The levels, the site and the efficiencies are shared.",
        )
        rows_of("option_layers", before)
        before = {str(child) for child in frame.winfo_children()}
        self.yield_massing, row = self._picker(
            frame,
            row,
            "Layers",
            "The layers whose slabs are the massing.",
            "Every slab on these layers is counted, its use told by the level it stands "
            "on: the commercial levels below, every other level residential. A "
            "layer cannot be named twice; the run refuses one that is.",
        )
        rows_of("layers", before)
        before = {str(child) for child in frame.winfo_children()}
        self.yield_residential, row = self._picker(
            frame,
            row,
            "Residential layers",
            "The layers whose slabs are residential floor.",
            "Each slab on these layers is a residential floor: its area is residential BEA, "
            "and its GFA is what the units are worked from. A slab on a layer named for "
            "nothing is not counted, and the run says which layers those were.",
        )
        self.yield_commercial, row = self._picker(
            frame,
            row,
            "Commercial layers",
            "The layers whose slabs are commercial floor: shops, offices, a podium.",
            "Counted at the commercial efficiencies, and left out of the units.",
        )
        rows_of("per_use", before)
        before = {str(child) for child in frame.winfo_children()}
        self.yield_commercial_levels, row = self._level_picker(
            frame,
            row,
            "Commercial levels",
            "The levels that are commercial: shops, offices, a podium. Every other level is "
            "residential.",
            "The levels are counted up from the ground -- the level nearest the project's "
            "ground storey -- as the run names them in its log: Ground, Level 01, B 01.",
        )
        rows_of("levels", before)
        self.yield_view, row = self._entry(
            frame,
            row,
            "View beside the table",
            "",
            "A view in the View Map, such as the massing in axonometric. Blank: the table alone.",
            "The office's own 3D view of the massing, coloured by use with its graphic "
            "override, placed on the sheet and framed to the page right of the table. A "
            "name the View Map does not have costs the picture, not the sheet.",
        )

        self.yield_xlsx = tk.BooleanVar(value=True)
        workbook = ttk.Checkbutton(
            frame,
            text="Excel workbook: Preliminary Yield Analysis",
            variable=self.yield_xlsx,
            command=self._sync,
        )
        workbook.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        Tooltip(
            workbook,
            "Writes the office's feasibility template, filled: one sheet per option, the "
            "inputs in red and everything else a live formula. An option already in the "
            "workbook is replaced; the others stay.",
            title="The workbook",
        )
        row += 1
        self.yield_workbook, row = self._file_row(
            frame,
            row,
            "Workbook",
            "Blank writes Preliminary Yield Analysis.xlsx into the tables folder in General.",
            "Choose where the workbook goes, for one kept with the project. An option "
            "already in it is replaced and the others stay; a workbook Loriini did not "
            "write is left alone, and the run says so.",
            kinds=(("Excel workbook", "*.xlsx"),),
            default=AREA_TABLE,
        )

        frame, row = self._panel(outer, 1, title="Site and controls"), 0
        self.yield_site_area, row = self._entry(
            frame,
            row,
            "Site area (m²)",
            "",
            "Blank reads it at the address on the Site analysis page, when one is typed.",
            "The FSR is the GFA over this. From the address it is the cadastral lots' own "
            "area, which is the figure to confirm against the survey.",
        )
        self.yield_fsr_residential, row = self._entry(
            frame,
            row,
            "Permissible FSR, residential",
            "",
            "The sheet splits the permissible FSR by use. Blank everywhere reads the LEP's.",
            "The LEP's one FSR, read at the address, goes on the residential row with a "
            "note; split it here, or in the workbook.",
        )
        self.yield_fsr_commercial, row = self._entry(
            frame,
            row,
            "Permissible FSR, commercial",
            "",
            "",
            "The part of the permissible FSR that is commercial floor.",
        )

        frame, row = self._panel(outer, 2, title="Efficiencies, mix and parking"), 0
        self.yield_gfa_residential, row = self._entry(
            frame,
            row,
            "BEA to GFA, residential",
            "0.725",
            "The share of the residential BEA that is GFA.",
            "What the walls, the cores, the plant and the circulation take out of a "
            "residential floor, as the LEP's definition of GFA does. The sheet's 0.725.",
        )
        self.yield_gfa_commercial, row = self._entry(
            frame,
            row,
            "BEA to GFA, commercial",
            "0.85",
            "The share of the commercial BEA that is GFA.",
            "A shop or office floor loses less to cores and circulation. The sheet's 0.85.",
        )
        self.yield_nla_residential, row = self._entry(
            frame,
            row,
            "GFA to NLA, residential",
            "0.85",
            "The share of the residential GFA that is net lettable.",
            "The units are worked from this: the mix's average NLA over it is the GFA "
            "one unit costs.",
        )
        self.yield_nla_commercial, row = self._entry(
            frame,
            row,
            "GFA to NLA, commercial",
            "0.9",
            "The share of the commercial GFA that is net lettable.",
            "Said on the sheet; nothing else is worked from it.",
        )
        self.yield_affordable_share, row = self._entry(
            frame,
            row,
            "Affordable share (%)",
            "0",
            "The share of the residential GFA that is affordable housing.",
            "The affordable units take the sheet's own mix -- the same shares, a smaller "
            "three-bedroom -- and their own parking rates; both are inputs in the workbook.",
        )
        self.yield_mix: dict[str, tuple[ttk.Entry, ttk.Entry]] = {}
        for name, share, size in MIX_ROWS:
            share_box, size_box, row = self._mix_row(frame, row, name, share, size)
            self.yield_mix[name] = (share_box, size_box)
        self.yield_sqm_per_space, row = self._entry(
            frame,
            row,
            "m² per parking space",
            "40",
            "Basement floor a space takes, with its aisle.",
            "The parking the sheet counts, at this, is so much basement; over the share of "
            "the site below, so many basement levels.",
        )
        self.yield_basement_ratio, row = self._entry(
            frame,
            row,
            "Basement site ratio",
            "0.4",
            "The share of the site a basement level may take, 0.4 for forty per cent.",
            "The rates per unit type and per m² of commercial floor are the "
            "sheet's, and are inputs in the workbook.",
        )

    def _level_picker(
        self, parent: ttk.Frame, row: int, label: str, hint: str, detail: str
    ) -> tuple[Chips, int]:
        """A list of levels, ticked out of the ones a massing can have, shown
        as chips: the same control as a layer list, over the levels the run
        names rather than the project's storeys, which a massing homed on
        the ground storey and offset up does not follow."""
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="ne", padx=(0, 12), pady=(6, 0))
        box = Chips(
            parent,
            add=lambda: self._choose(
                box,
                label,
                hint,
                LEVEL_CHOICES,
                {level: _level_meaning(level) for level in LEVEL_CHOICES},
                typed=True,
            ),
            on_change=self._sync,
            empty="no levels chosen",
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

    def _mix_row(
        self, parent: ttk.Frame, row: int, name: str, share: str, size: str
    ) -> tuple[ttk.Entry, ttk.Entry, int]:
        """One type in the mix: its share of the units and its size, side by side."""
        label = ttk.Label(parent, text=name, anchor="e")
        label.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(6, 0))
        cells = ttk.Frame(parent)
        cells.flows = True  # type: ignore[attr-defined]
        cells.grid(row=row, column=1, sticky="w", pady=(6, 0))
        share_box = ttk.Entry(cells, width=6)
        share_box.insert(0, share)
        share_box.grid(row=0, column=0)
        ttk.Label(cells, text="% of the units, at", foreground=HINT).grid(
            row=0, column=1, padx=(6, 8)
        )
        size_box = ttk.Entry(cells, width=6)
        size_box.insert(0, size)
        size_box.grid(row=0, column=2)
        ttk.Label(cells, text="m² NLA each", foreground=HINT).grid(row=0, column=3, padx=(6, 0))
        for target in (label, share_box, size_box):
            Tooltip(
                target,
                f"How many of the units are {name.lower()} apartments, as a share of them "
                "all, and the net lettable area of one. The shares come to 100; a type at "
                "nothing keeps its row on the sheet. "
                "The units are the residential GFA over the average GFA these make, "
                "shared into the mix; the sheet does not round, and nor does the run.",
                title=f"{name} in the mix",
            )
        return share_box, size_box, row + 1

    def _folder_row(
        self, parent: ttk.Frame, row: int, label: str, hint: str, detail: str
    ) -> tuple[ttk.Entry, int]:
        """A path, typeable, with a Browse beside it.

        One of the text boxes that stays a text box: a path on a network drive
        is genuinely typed, or pasted, and the entry is the honest record of
        what gets passed. The button is what makes it bearable.
        """
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(3, 0))
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

    def _file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        hint: str,
        detail: str,
        *,
        kinds: Sequence[tuple[str, str]],
        default: str,
    ) -> tuple[ttk.Entry, int]:
        """A file to write, chosen with a Save dialog, with a Choose beside it.

        The same row as a folder's, for a path that is a file: the workbook
        the yield analysis writes. The box shows what was chosen and can be
        cleared, which is the one edit it is for -- blank is the tables
        folder's own file.
        """
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(3, 0))
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", pady=(3, 0))
        holder.columnconfigure(0, weight=1)
        box = ttk.Entry(holder)
        box.grid(row=0, column=0, sticky="ew")
        button = ttk.Button(
            holder,
            text="Choose…",
            width=11,
            command=lambda: self._browse_file(box, label, kinds, default),
            **icons.button_options("folder"),
        )
        button.grid(row=0, column=1, padx=(6, 0))
        line = self._hint(parent, row + 1, hint)
        for target in (name, box, button):
            Tooltip(target, detail, title=label, short=self._saying(line))
        return box, row + 1

    def _browse_file(
        self, box: ttk.Entry, label: str, kinds: Sequence[tuple[str, str]], default: str
    ) -> None:
        """Pick a file to write. Leaves the entry alone if the dialog was
        cancelled. Opens where the box points, or in the tables folder."""
        current = Path(box.get().strip()) if box.get().strip() else None
        tables = self._tables_folder()
        start = current.parent if current else tables
        chosen = filedialog.asksaveasfilename(
            parent=self.root,
            title=label,
            filetypes=list(kinds),
            defaultextension=kinds[0][1].lstrip("*") if kinds else "",
            initialdir=str(start) if start else "",
            initialfile=current.name if current else default,
            confirmoverwrite=False,
        )
        if not chosen:
            return
        box.delete(0, "end")
        box.insert(0, chosen)
        self._sync()

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
        """The run bar: what the project is, what is queued, and Run.

        One line, the way the design has it. At the left, which project is
        read and what came out of it -- the line that sat under the picker.
        Then what Run will make, by study. At the right, the build, and Run,
        which is the one filled button in the window and says in sheets what
        pressing it does. Stop is there only while there is something to
        stop. While a run is going the bar gets a second line above it, the
        progress; after one, a third under it, the run's last line and the
        way to the whole log.
        """
        # Above the bar, while a run is under way and not otherwise: an empty
        # trough between runs was a strip of nothing at the foot of every page.
        progress_row = ttk.Frame(base, style="Chrome.TFrame")
        progress_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        progress_row.columnconfigure(0, weight=1)
        self.progress_row = progress_row
        progress_row.grid_remove()
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        #: What the bar is actually at, in words. An indeterminate bar says
        #: only that something is happening, and "3 of 7" is the thing a
        #: colleague wants while a shadow diagram grinds through its sheets.
        self.progress_count = ttk.Label(progress_row, text="", style="ChromeHint.TLabel")
        self.progress_count.grid(row=0, column=1, sticky="e", padx=(8, 0))

        bar = ttk.Frame(base, style="Chrome.TFrame")
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)
        #: What the chosen project is, or why there is none: the line that
        #: says what was read, with the plug in front of it seated or struck.
        self.status = ttk.Label(bar, text="", style="Chrome.TLabel")
        self.status.grid(row=0, column=0, sticky="w")
        #: What Run will make, by study, in words: the panel down the right
        #: draws it, and this says it for a window whose panel is folded.
        self.queue_line = ttk.Label(bar, text="", style="ChromeHint.TLabel")
        self.queue_line.grid(row=0, column=1, sticky="w", padx=(PAD * 2, 0))
        # Whose build this is, and until when. The prototype disclaimer is
        # still on every sheet and in every export, where the numbers are.
        ttk.Label(bar, text=credential(), style="ChromeHint.TLabel").grid(
            row=0, column=2, sticky="e", padx=(PAD, PAD * 2)
        )
        self.cancel = ttk.Button(
            bar,
            text="Stop",
            style="Chrome.TButton",
            command=self._stop,
            state="disabled",
            **icons.button_options("stop"),
        )
        self.cancel.grid(row=0, column=3, padx=(0, 6))
        self.cancel.grid_remove()
        Tooltip(
            self.cancel,
            "Asks the run to stop and lets it put the project's layer state "
            "back on the way out. It can take a few seconds to come to a halt.",
        )
        # Filled, and the white disc on it; off, the grey face and the blue
        # disc every other icon in the window wears.
        lit = icons.named("run_on", 16)
        dim = icons.named("run", 16)
        run_image: dict[str, object] = {}
        if lit is not None and dim is not None:
            run_image = {"image": (lit, "disabled", dim), "compound": "left"}
        self.go = ttk.Button(
            bar,
            text="Run study",
            command=self._start,
            style="Run.TButton",
            # Wide enough for "Tick a study to run", so the button does not
            # change size under the pointer as studies are ticked.
            width=20,
            **run_image,  # type: ignore[arg-type]
        )
        self.go.grid(row=0, column=4, sticky="e")
        Tooltip(
            self.go,
            "Runs every queued study in the project chosen above, one after "
            "the other. Minutes rather than seconds: the export alone takes a "
            "couple. Nothing is saved — look at the result in Archicad and "
            "save it yourself if you want to keep it.",
        )

        #: The newest line out of a run, and the only one on screen, under
        #: the bar once there is one. Every line is still kept, in
        #: ``self.lines``, and in a file, so a run that failed can be read
        #: back; it is simply not what the bottom of the window is made of.
        note_row = ttk.Frame(base, style="Chrome.TFrame")
        note_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        note_row.columnconfigure(0, weight=1)
        self.note_row = note_row
        note_row.grid_remove()
        self.note = ttk.Label(note_row, text="", style="Note.TLabel")
        self.note.grid(row=0, column=0, sticky="ew")
        #: The way to the whole transcript, beside the one line of it. Shown
        #: once a run has a file to open, and not before: a link to nothing
        #: is a link somebody clicks once and never trusts again.
        self.log_link = ttk.Label(
            note_row, text="Whole log", style="ChromeLink.TLabel", cursor="hand2"
        )
        self.log_link.bind("<Button-1>", lambda _event: self._open_log())
        Tooltip(
            self.log_link,
            "Opens the whole transcript of the last run -- every line it printed, "
            "with the time each stage took -- which is what to send when a run "
            "goes wrong. Every run is kept, the newest sixty, in the Logs folder "
            "beside the saved settings.",
            title="Whole log",
        )

    def _say(self, line: str) -> None:
        """Put one line of a run under the bar, showing the row if it was not."""
        self.note.config(text=line)
        if line:
            self.note_row.grid()

    @staticmethod
    def _post(menu: tk.Menu, under: tk.Misc) -> None:
        """Drop a menu down from under the button that opened it."""
        x = under.winfo_rootx()
        y = under.winfo_rooty() + under.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    #: How wide the label column is inside a box. Every box has a grid of its
    #: own, so without a number they would each size the column to their own
    #: longest label and no two boxes' fields would line up down the page.
    #: This is "Subset — time-of-day sheets" with its drawing beside it.
    LABEL_COLUMN = 208

    def _line_up_labels(self) -> None:
        """One label column for every card in the window, as wide as the
        widest label in any of them.

        ``LABEL_COLUMN`` is the floor, measured against Segoe UI. A Mac sets
        the same words a third larger, so the longest labels outgrew it and
        each card widened its own column to fit -- and the fields started at a
        different place on every card, and on every page.
        """
        widest = self.LABEL_COLUMN
        for box in self.boxes:
            for child in box.grid_slaves(column=0):
                if child.winfo_class() != "TLabel":
                    continue
                if int(child.grid_info().get("columnspan", 1)) > 1:
                    continue
                widest = max(widest, child.winfo_reqwidth())
        for box in self.boxes:
            box.columnconfigure(0, minsize=widest)
        #: The column as wide as its widest label, for a page with room.
        self._label_wide = widest

    # -- a page narrower than its rows -------------------------------------
    #
    # The page between the sidebar and the sheets panel is as wide as the
    # window leaves it, and on a laptop with the panel open that is about
    # 560 px -- less than a row of fourteen hours, or three choices side by
    # side, beside a 200 px label column. Cut off at the panel's edge, the
    # last buttons of a row could not be reached. So the page rearranges
    # itself instead: the label column narrows and its labels wrap; a row of
    # buttons wraps onto a second line, the way the layer chips always did;
    # and a list of the project's names gives up the width it asked for.

    #: The label column on a narrow page, and how wide its words may run.
    LABEL_NARROW = 132
    #: The least room the fields beside a full-width label column need before
    #: the labels give some of theirs up and wrap. A row of choices wraps on
    #: its own and a list of names narrows to fit, so this is room for an
    #: ordinary field and a row of three tiles -- not for the widest row on
    #: any page. Measured against the page as it is, rather than a fixed page
    #: width: a fixed 720 px wrapped every label on a laptop with the sheets
    #: panel open, beside fields that had a third of the page spare.
    FIELD_LEAST = 280

    def _flowing(self) -> list[tk.Misc]:
        """Every row that wraps: the choice tiles, the toggles, the hours,
        and any frame that asks to by carrying ``flows``."""
        found: list[tk.Misc] = []

        def walk(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                if isinstance(child, (Tiles, Toggles, Ticks)) or getattr(child, "flows", False):
                    found.append(child)
                else:
                    walk(child)

        walk(self.stack)
        return found

    def _box_of(self, widget: tk.Misc) -> ttk.Frame | None:
        """The panel a widget sits in."""
        boxes = {str(box): box for box in self.boxes}
        at: tk.Misc | None = widget
        while at is not None:
            if str(at) in boxes:
                return boxes[str(at)]
            at = at.master
        return None

    def _room_beside(self, box: ttk.Frame, wide: int) -> int:
        """How wide a row beside the label column of ``box`` may run, on a
        page ``wide`` pixels across."""
        column = int(box.grid_columnconfigure(0)["minsize"])
        return wide - PAD * 6 - 28 - column - 12 - 16

    def _room_with_full_labels(self, wide: int) -> int:
        """How wide a row beside a label column at its full width may run,
        on a page ``wide`` pixels across: ``_room_beside`` for the column as
        it is when nothing wraps."""
        column = getattr(self, "_label_wide", self.LABEL_COLUMN)
        return wide - PAD * 6 - 28 - column - 12 - 16

    def _respond(self, _event: object = None) -> None:
        """Rearrange the open page for the width it has now."""
        if self._responding is not None:
            return
        self._responding = self.root.after_idle(self._rearrange)

    def _rearrange(self) -> None:
        self._responding = None
        pane = self.pane_of.get(self.showing)
        if pane is None:
            return
        wide = pane.canvas.winfo_width()
        if wide <= 1:
            return
        narrow = self._room_with_full_labels(wide) < self.FIELD_LEAST
        if narrow != self._narrow_page:
            self._narrow_page = narrow
            labels = [
                child
                for panel in self.boxes
                for child in panel.grid_slaves(column=0)
                if isinstance(child, ttk.Label)
                and not str(child.cget("style"))
                and int(child.grid_info().get("columnspan", 1)) == 1
            ]
            for label in labels:
                label.configure(wraplength=self.LABEL_NARROW - 4 if narrow else 0, justify="right")
            # One column for every panel, as wide as the widest label in it
            # now -- wrapped or not -- so the fields line up down the page.
            column = getattr(self, "_label_wide", 0)
            if narrow:
                # The label and the 12 px it keeps from its field. A wrapped
                # label's words are never wider than its wrap, so this is known
                # before Tk has laid the new lines out. The label is its words
                # and the 4 px the wrap leaves for its own edges: capped at the
                # wrap alone, a wrapped label on Windows -- whose ttk draws
                # those edges, where a Mac's does not -- came out wider than
                # the column allowed for and pushed its fields 2 px right of
                # every other panel's.
                column = max(
                    [
                        self.LABEL_NARROW,
                        *(min(label.winfo_reqwidth(), self.LABEL_NARROW) + 12 for label in labels),
                    ]
                )
            for panel in self.boxes:
                panel.columnconfigure(0, minsize=column)
            # The rows beside the column are measured on the next pass, once
            # Tk has moved them. Asked from here, inside an idle handler, a
            # layout pass ran the window's whole idle queue inside itself.
            self._respond()
            return
        if self._flows is None:
            self._flows = self._flowing()
        # Measured against the page, not against the panel: a panel is as
        # wide as what is in it once that is wider than the page, so a room
        # taken from the panel shrank with every row wrapped to fit it, and
        # the page rearranged itself down to a word a line.
        # Worked out rather than read off the screen: just after the label
        # column changes, Tk has not yet moved the rows beside it, and a row
        # measured from where it was would be given the room it had before.
        # The page's margins, the panel's, the label column and its gap.
        # Every page, not only the one showing: they are all as wide as each
        # other, and a row on a page not yet drawn -- or in a folded panel --
        # is then laid out already when it is opened.
        for row in self._flows:
            holder = self._box_of(row)
            if holder is not None:
                _wrap(row, self._room_beside(holder, wide))
        # A study's one line under its header runs the width of its panel.
        room = max(wide - PAD * 6 - 90, 200)
        for box in self.boxes:
            for child in box.grid_slaves(column=0):
                if (
                    isinstance(child, ttk.Label)
                    and int(child.grid_info().get("columnspan", 1)) > 1
                    and int(str(child.cget("wraplength")) or 0) not in (0, room)
                ):
                    child.configure(wraplength=room)
        # A list of the project's names asked for 36 characters; on a page
        # that has not got them it takes the width there is instead.
        for box in self.boxes:
            for child in box.grid_slaves(column=1):
                if child.winfo_class() != "TCombobox":
                    continue
                room = self._room_beside(box, wide)
                sticky = "ew" if child.winfo_reqwidth() > room else "w"
                if str(child.grid_info().get("sticky")) != sticky:
                    child.grid_configure(sticky=sticky)

    def _panel(self, outer: ttk.Frame, row: int, *, title: str = "") -> ttk.Frame:
        """One panel on a page: a study, or a group of settings that go together.

        A rounded border with its header drawn into the top of it, the way
        Archicad sets out the panels of a settings dialog: a triangle that
        folds the panel to its header, and the panel's name beside it. The
        border and the header's tint are one nine-slice picture
        (``theme._rounded``), so the tint's corners are the panel's corners.

        The rows are built by the code that always built them. The caller
        points its own ``frame`` at what this returns and starts ``row`` again
        at nought, and the helpers beneath it neither know nor care.

        ``title`` heads a panel that has no study to head it -- General and
        Model are set up, not switched on. A study's panel is headed by
        ``_head``, which puts its name and its switch where this puts a title.
        """
        head = theme.PANEL_HEAD
        # A settings panel wears the plain header: it is not switched on, and
        # the tint means switched on. A study's panel is restyled by ``_sync``.
        box = ttk.Frame(
            outer,
            style="BoxOff.TFrame" if title else "Box.TFrame",
            padding=self.OPEN_PANEL,
        )
        box.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        box.columnconfigure(0, minsize=self.LABEL_COLUMN)
        box.columnconfigure(1, weight=1)
        self.boxes.append(box)
        # Placed, not gridded: the padding above keeps the rows clear of the
        # header, and the header itself sits in that padding. Measured from
        # the *outside* of the box, because a ttk frame tells Tk its padding is
        # a border and ``place`` otherwise starts inside it -- which puts the
        # header on top of the first row instead of over it.
        fold = ttk.Button(
            box,
            text="▾",
            style="Disclose.TButton",
            takefocus=False,
            command=lambda: self._fold(box, not self.folded.get(str(box), False)),
        )
        fold.place(bordermode="outside", x=8, y=2, width=20, height=head - 3)
        self.folders[str(box)] = fold
        Tooltip(
            fold,
            "Folds the panel to its header, or opens it again. Folding changes "
            "nothing about what runs: a study runs by its switch, open or folded.",
            title=title or "Fold",
        )
        if title:
            ttk.Label(box, text=title, style="BoxTitle.TLabel").place(
                bordermode="outside", x=30, y=2, height=head - 3, relwidth=1.0, width=-44
            )
        return box

    #: A panel's padding open, and folded to its header.
    OPEN_PANEL = (14, theme.PANEL_HEAD + 10, 14, 12)
    FOLDED_PANEL = (14, theme.PANEL_HEAD, 14, 6)

    def _fold(self, box: ttk.Frame, shut: bool) -> None:
        """Fold a panel to its header, or open it again.

        Its rows are taken off the grid and put back where they were, which
        ``grid_remove`` remembers; the header is placed, so it stays.
        """
        if self.folded.get(str(box), False) == shut:
            return
        self.folded[str(box)] = shut
        if shut:
            rows = box.grid_slaves()
            self._kept_rows[str(box)] = rows
            for child in rows:
                child.grid_remove()
            # Grid leaves a frame at its last size when its last row goes, so
            # one empty row stays to let the panel shrink to its header.
            spacer = ttk.Frame(box, height=1)
            spacer.grid(row=0, column=0)
            self._spacers[str(box)] = spacer
        else:
            if str(box) in self._spacers:
                self._spacers.pop(str(box)).destroy()
            for child in self._kept_rows.pop(str(box), []):
                child.grid()
        box.configure(padding=self.FOLDED_PANEL if shut else self.OPEN_PANEL)
        self.folders[str(box)].configure(text="▸" if shut else "▾")

    def _head(self, box: ttk.Frame, tick: ttk.Checkbutton, job: str) -> None:
        """Put a study's name and its switch at the head of its panel.

        The tick that was the header -- a 12 px box beside the study's name
        -- is a switch now, at the right of the header, where a pointer finds
        it without looking. The name is a label beside the fold's triangle,
        and between them, what the switch is worth in sheets: the figure the
        panel down the side of the window draws, said where the decision is.
        """
        head = theme.PANEL_HEAD
        name = str(tick.cget("text"))
        tick.configure(text="", image="", style="SwitchHeadOff.TCheckbutton")
        tick.place(bordermode="outside", relx=1.0, x=-12, y=2, height=head - 3, anchor="ne")
        says = ttk.Label(box, text="", style="PanelSaysOff.TLabel")
        says.place(bordermode="outside", relx=1.0, x=-50, y=2, height=head - 3, anchor="ne")
        title = ttk.Label(box, text=name, style="StudyTitleOff.TLabel")
        title.place(bordermode="outside", x=30, y=2, height=head - 3)
        self.study_bars[job] = tick
        self.study_boxes[job] = (box, says)
        self.study_titles[job] = title

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
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(3, 0))
        # As wide as a long Archicad name, not as wide as the card: a list of
        # layouts or combinations a metre across is mostly empty box.
        box = ttk.Combobox(parent, values=[], width=self.NAME_WIDTH)
        box.grid(row=row, column=1, sticky="w", pady=(3, 0))
        line = self._hint(parent, row + 1, hint)
        for target in (name, box):
            Tooltip(target, detail, title=label, short=self._saying(line))
        return box, row + 1

    #: The typed fields that hold words, and so run the width of their card.
    #: Every other ``_entry`` holds a number or a short prefix -- a scale, a
    #: ratio, ``14 |`` -- and a three-character value in a box the width of
    #: the window reads as a sentence nobody has written yet.
    TEXT_FIELDS = frozenset(
        {
            "Address",
            "Custom day",
            "Option",
            "Set name",
            "View beside the table",
        }
    )
    #: How many characters wide a number's field is: room for ``1:3000`` or
    #: ``0.725`` with a margin, and the same on every page.
    NUMBER_WIDTH = 12
    #: And a list of the project's own names: a layout, a combination, a
    #: storey, a pen set.
    NAME_WIDTH = 36

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
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(6, 0))
        wide = label in self.TEXT_FIELDS
        box = ttk.Entry(parent) if wide else ttk.Entry(parent, width=self.NUMBER_WIDTH)
        box.insert(0, initial)
        box.grid(row=row, column=1, sticky="ew" if wide else "w", pady=(6, 0))
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
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="ne", padx=(0, 12), pady=(6, 0))
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", pady=(6, 0))
        holder.columnconfigure(1, weight=1)

        layer = ttk.Combobox(holder, values=[], width=22)
        layer.grid(row=0, column=0, sticky="nw")
        names = Chips(
            holder,
            add=lambda: self._choose_zone_names(names, layer, label),
            on_change=self._sync,
            empty="no names chosen",
            label=label,
        )
        # Under the layer, not beside it: beside it the names and their Add
        # had the narrow end of the row, and wrapped into a column of their
        # own with the button stretched under them.
        names.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
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
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(6, 0))
        made = Tiles(
            parent,
            self.TILE_CHOICES[label],
            on_change=self._sync,
            multi=label in self.TILE_MULTI,
            aliases=self.TILE_ALIASES.get(label),
            words=self.TILE_WORDS.get(label),
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
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="e", padx=(0, 12), pady=(6, 0))
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
        name = ttk.Label(parent, text=label, anchor="e")
        name.grid(row=row, column=0, sticky="ne", padx=(0, 12), pady=(6, 0))
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

    def _choose_zone_names(self, box: Chips, layer: ttk.Combobox, label: str) -> None:
        """The zone row's Add: the names the project read found on the layer.

        It always opens now. It used to open only when the read had found
        Zones on the chosen layer, and otherwise wrote one line into the note
        at the foot of the window and did nothing else -- which, from where
        the button is, is a button that does not work. A layer can hold no
        Zones the read saw for several good reasons: they are on a storey the
        read skipped, the read timed out on a big project, they were drawn
        after the window read the project. So the dialog opens either way,
        says which of those it looks like, and takes a typed name.
        """
        chosen = layer.get().strip()
        if not chosen:
            self._tell(
                f"{label}: no layer",
                "Choose the layer the Zones are on first, in the box to the left "
                "of Add. The names offered are the ones on that layer.",
            )
            return
        kinds = self._kinds_on(chosen)
        empty = ""
        if not kinds:
            failed = [line for line in self.options.problems if line.startswith("zones:")]
            empty = (
                f"The project read found no Zones on {chosen}. "
                + (
                    f"Reading the Zones failed ({failed[0][len('zones:') :].strip()}), "
                    "so press Refresh to try again, "
                    if failed
                    else "If they were drawn since, press Refresh; "
                )
                + "or type the names below as they are written on the plan."
            )
        self._choose(
            box,
            f"{label}: which names",
            "Zones on the chosen layer. The size beside each name is what says "
            "what it is: a dwelling is tens of square metres, a balcony is a "
            "few, a storage cupboard is less.",
            [kind.label for kind in kinds],
            {kind.label: kind.described() for kind in kinds},
            typed=True,
            empty=empty,
        )

    def _have_master(self) -> bool:
        """A master layout to put the sheets on, asked for now if it is blank.

        Asked rather than guessed, and before the run rather than in the
        middle of it, where the command has nobody to ask. False when there
        is nothing to ask from, or nobody answered.
        """
        if self.master.get().strip():
            return True
        masters = tuple(self.master.cget("values") or ())
        if not masters:
            # Nothing read yet, or a project with no masters: the command
            # says which, with the list, if it comes to make a sheet.
            return True
        dialog = MasterChooser(self.root, masters)
        self.root.wait_window(dialog)
        if dialog.result is None:
            self._write("No master layout chosen, so nothing was run.")
            return False
        self.master.set(dialog.result)
        return True

    def _tell(self, title: str, message: str) -> None:
        """A sentence somebody has to read before anything else happens.

        A box rather than the note at the foot of the window: the note is
        where a run reports, and a reason a button did nothing has to be
        where the button is, or the button looks broken.
        """
        from tkinter import messagebox

        self._write(message)
        messagebox.showinfo(title, message, parent=self.root)

    def _choose(
        self,
        box: ttk.Entry | Chips,
        label: str,
        hint: str,
        available: Sequence[str] | None = None,
        describe: Mapping[str, str] | None = None,
        *,
        typed: bool = False,
        empty: str = "",
    ) -> None:
        """Tick names into an entry. Leaves it alone if nothing was chosen.

        ``available`` defaults to the project's layers, which is what most of
        these are; a zone row passes the names its layer carries instead,
        and ``typed`` so a name the read did not find can still be given.
        """
        offered = list(available) if available is not None else pickable(self.options.layers)
        if not offered and not typed:
            self._tell(
                label,
                f"Nothing to choose from for {label}: no project has been read. "
                "Pick the Archicad at the top of the window and press Refresh.",
            )
            return
        dialog = LayerChooser(
            self.root,
            title=label,
            hint=hint,
            available=offered,
            chosen=self._listed(box),
            describe=describe,
            typed=typed,
            empty=empty,
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
            (SHADOW_HOURS_JOB, self.do_shadow_hours, self.SHADOWS),
            (SUN_EYE_JOB, self.do_sun_eyes, self.EYE),
            (SITE_CONTEXT_JOB, self.do_site_context, self.SITE),
            (SITE_SHEET_JOB, self.do_site_site, self.SITE),
            (SITE_MODEL_JOB, self.do_site_model, self.SITE),
            (SITE_CONTROLS_JOB, self.do_site_summary, self.SITE),
            (YIELD_JOB, self.do_yield, self.YIELD),
        ]

    def _open_section(self) -> str:
        """Which page is showing, by title.

        By title and not by number so that inserting a section, or dropping
        one, cannot reopen somebody on a different page than the one they
        left. Never empty: a tab strip has no state with nothing open, which
        is the one thing the launcher could be and this cannot.
        """
        return self.showing

    def _on_screen(self) -> bool:
        """Whether the window is where anybody can see it."""
        try:
            return bool(self.root.winfo_viewable())
        except tk.TclError:  # pragma: no cover - the window is gone
            return False

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
        leaving = self.showing
        for pane in self.panes:
            pane.settle()
            pane.pack_forget()
        self.pane_of[title].pack(side="top", fill="both", expand=True)
        self.showing = title
        # The page settles in from the side you came from (D134): a few
        # pixels, under a fifth of a second, and only on a screen -- a window
        # nobody can see has nothing to show arriving -- and only where the
        # system has not been asked for less movement. The page is in place
        # from this line on either way; the movement is the item in its
        # canvas, not the page in the window, so nothing waits on it.
        if (
            leaving != title
            and leaving in self.titles
            and self._on_screen()
            and not motion.reduced()
        ):
            self.pane_of[title].arrive(self.titles.index(title) > self.titles.index(leaving))
        if hasattr(self, "_responding"):
            self._respond()
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
        asked = study.strip().casefold()
        if asked == "reference":
            # Not a study: the palette's last button opens the reference
            # image over the 3D window, so the next click is "Open picture".
            self._reference()
            return True
        wanted = {
            "facade": (self.do_facade, self.FACADE),
            "apartments": (self.do_plans, self.DIAGRAMS),
            "communal": (self.do_communal, self.DIAGRAMS),
            "shadow": (self.do_shadows, self.SHADOWS),
            # The documents' older name: they are the shadow diagram now.
            "shadow plans": (self.do_shadows, self.SHADOWS),
            "every hour": (self.do_shadow_hours, self.SHADOWS),
            "views": (self.do_sun_eyes, self.EYE),
            "site": (self.do_site_context, self.SITE),
        }
        found = wanted.get(asked)
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

        # A page whose study will run says so, without anybody opening it.
        sheets = self.planned()
        self._paint_tabs(sheets)
        for toggles in self.toggle_rows:
            toggles.paint()
        for name, tick, _where in self._studies():
            on = tick.get()
            bar = self.study_bars.get(name)
            if bar is not None:
                bar.configure(
                    style="SwitchHead.TCheckbutton" if on else "SwitchHeadOff.TCheckbutton"
                )
            title = self.study_titles.get(name)
            if title is not None:
                title.configure(style="StudyTitle.TLabel" if on else "StudyTitleOff.TLabel")
            if name in self.study_boxes:
                box, says = self.study_boxes[name]
                box.configure(style="Box.TFrame" if on else "BoxOff.TFrame")
                self.folders[str(box)].configure(
                    style="DiscloseOn.TButton" if on else "Disclose.TButton"
                )
                # A study switched on opens to show what it will be run with;
                # one switched off is left as it was, open or folded.
                if on and not self._was_on.get(name, False):
                    self._fold(box, False)
                self._was_on[name] = on
                made = sum(1 for sheet in sheets if sheet.job == name and sheet.paper)
                models = sum(1 for sheet in sheets if sheet.job == name and not sheet.paper)
                # A panel that makes only models -- the 3D context -- says
                # so, rather than "0 sheets" in front of them.
                parts: list[str] = []
                if made or not models:
                    parts.append(f"{made} sheet" + ("" if made == 1 else "s"))
                if models:
                    parts.append(f"{models} model" + ("" if models == 1 else "s"))
                worth = ", ".join(parts)
                says.configure(
                    text=worth if on else "off",
                    style="PanelSays.TLabel" if on else "PanelSaysOff.TLabel",
                )
        self._yield_rows()
        self._paint_design()
        self._refill_dock(sheets)
        self._paint_run(sheets)

    def _paint_run(self, sheets: Sequence[Sheet] | None = None) -> None:
        """Say on the Run button what pressing it will do, and switch it off
        when the answer is nothing.

        A Run button that looked ready with nothing switched on answered a
        press with a line at the foot of the window and nothing else. So it
        counts what the run will make and says so -- "Run 6 sheets", the same
        number the sheets panel draws -- and is off, and says why, while there
        is nothing to run; while a run is going; and while the open Archicad
        lacks the add-on, which ``_offer`` says in the status line. The line
        beside it says the same by study, for a window whose panel is folded.
        """
        if not hasattr(self, "go"):  # pragma: no cover - a tick before the bar is built
            return
        if sheets is None:
            sheets = self.planned()
        queued = [name for name, tick, _where in self._studies() if tick.get()]
        paper = sum(1 for sheet in sheets if sheet.paper)
        if not queued:
            text = "Switch on a study"
        elif paper:
            text = f"Run {paper} sheet" + ("" if paper == 1 else "s")
        elif len(queued) == 1:
            text = "Run study"
        else:
            text = f"Run {len(queued)} studies"
        off = self._running or self._tapir_missing or not queued
        self.go.config(text=text, state="disabled" if off else "normal")

        said = []
        for name in queued:
            made = sum(1 for sheet in sheets if sheet.job == name and sheet.paper)
            # The study's own name, without the page it is filed under:
            # "solar analysis: apartments" reads as "Apartments".
            short = name.split(": ", 1)[-1]
            short = short[:1].upper() + short[1:]
            said.append(f"{short} ({made})" if made else short)
        line = f"Queued: {' · '.join(said)}" if said else ""
        if len(line) > self.QUEUE_LONGEST:
            # Past this it runs into the build's line; the sidebar and the
            # panel say which, so the bar says how many.
            line = f"Queued: {len(said)} studies, {paper} sheets"
        self.queue_line.config(text=line)

    #: The longest the run bar's line of queued studies is let run.
    QUEUE_LONGEST = 64

    #: Under this many pixels the window cannot hold the page and the sheets
    #: panel side by side: the page is left with less than a chip row needs.
    #: The least of it: ``fold_below`` is the one in force, which is more when
    #: the tab strip needs more room than this leaves it.
    FOLD_BELOW = 1056
    #: The size the window opens at on a screen with room for it: see
    #: ``__init__`` for where the numbers come from. The sidebar, a page and
    #: the sheets panel side by side.
    OPENING_WIDTH = 1240
    OPENING_HEIGHT = 856

    def _fit(self, event: tk.Event[tk.Misc]) -> None:
        """Fold the sheets panel when the window is dragged too narrow for both.

        Only on *crossing* the line. In between, the chevron is the user's:
        somebody who opened the panel in a narrow window meant to, and having
        it snap shut again on the next pixel of a resize would be the window
        arguing with them.
        """
        if event.widget is not self.root:
            return
        narrow = event.width < self.fold_below
        if narrow == self._narrow:
            return
        self._narrow = narrow
        self.dock.fold(narrow or (self._dock_empty and not self._dock_opened_empty), by_hand=False)

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
        empty = not sheets
        if empty == self._dock_empty:
            return
        self._dock_empty = empty
        if empty:
            # The last tick went: the panel goes to its edge, unless it was
            # opened by hand on an empty page, which is somebody looking.
            if not self._dock_opened_empty:
                self.dock.fold(True, by_hand=False)
        else:
            # The first tick: the sheets come out, unless the window is too
            # narrow to hold them, which is the other reason it folds.
            self._dock_opened_empty = False
            # Asked of the window as it is, not of the last crossing: the
            # first <Configure> comes before the window has its size, and
            # would otherwise leave the panel folded on a window wide enough.
            if self.root.winfo_ismapped():
                self._narrow = self.root.winfo_width() < self.fold_below
            if not self._narrow:
                self.dock.fold(False, by_hand=False)

    def _dock_folded(self, shut: bool) -> None:
        """The chevron, pressed by hand. Opening an empty panel is a person
        asking to see it, and it stays open until a tick comes and goes."""
        self._dock_opened_empty = not shut and self._dock_empty

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
            "sun_view_custom_day": self.eye_custom_day,
            "communal_grid": self.communal_grid,
            "communal_schedule": self.cos_schedule,
            "tables_folder": self.tables,
            "master_layout": self.master,
            "storey_from": self.storey_from,
            "storey_to": self.storey_to,
            "year": self.year,
            "layer_combination": self.combination,
            "plan_combination": self.plan_combination,
            "subject_layers": self.subject,
            "require_layers": self.require,
            "context_layers": self.context,
            "hide_layers": self.hide,
            "livable_suffix": self.livable,
            "plan_instants": self.instants,
            "plan_kinds": self.plan_kinds,
            "floor_grid": self.floor_grid,
            "see_through_glass": self.see_glass,
            "shadow_subset": self.shadow_subset,
            **{f"shadow_layers_{short.lower()}": box for short, _role, box in self.shadow_rows},
            "shadow_terrain_layers": self.terrain_layers,
            "shadow_terrain_floor": self.terrain_floor,
            # The key a file saved by the old row of four dates used; it
            # restores into the custom-day field, which reads a comma list.
            "shadow_dates": self.shadow_custom_day,
            "shadow_hours": self.shadow_hours,
            "shadow_storey": self.shadow_storey,
            "shadow_study_subset": self.shadow_study_subset,
            "shadow_plan_combination": self.shadow_plan_combination,
            "shadow_plan_label": self.shadow_plan_label,
            "shadow_plan_pen_set": self.shadow_plan_pen_set,
            "shadow_plan_pen": self.shadow_plan_pen,
            "shadow_hours_colour": self.shadow_hours_colour,
            "shadow_grid": self.shadow_grid,
            "eye_pen_set": self.eye_pen_set,
            "eye_override": self.eye_override,
            "eye_base_combination": self.eye_base_combination,
            "eye_scale": self.eye_scale,
            "sheets": self.sheets,
            "eye_title_block": self.eye_title_block,
            "eye_hours": self.eye_hours,
            "site_address": self.site_address,
            "site_scale": self.site_scale,
            "site_theme": self.site_theme,
            "site_site_theme": self.site_site_theme,
            "site_context_origin": self.site_context_origin,
            "site_context_north": self.site_context_north,
            "site_sheet_origin": self.site_sheet_origin,
            "site_sheet_north": self.site_sheet_north,
            "site_sheet_scale": self.site_sheet_scale,
            "site_model_origin": self.site_model_origin,
            "site_model_north": self.site_model_north,
            "site_levels": self.site_levels,
            "site_radius": self.site_radius,
            "adg_subset": self.adg_subset,
            "layer_prefix": self.prefix_solar,
            "shadow_layer_prefix": self.prefix_shadow,
            "sun_view_layer_prefix": self.prefix_sun,
            "site_layer_prefix": self.prefix_site,
            "context_site_group": self.prefix_context,
            "skin_grid": self.grid_m,
            "yield_option": self.yield_option,
            "yield_slabs": self.yield_slabs,
            "yield_renovation_status": self.yield_renovation_status,
            "yield_option_layers": self.yield_option_layers,
            "yield_workbook": self.yield_workbook,
            "yield_residential_layers": self.yield_residential,
            "yield_commercial_layers": self.yield_commercial,
            "yield_massing_layers": self.yield_massing,
            "yield_commercial_levels": self.yield_commercial_levels,
            "yield_site_area": self.yield_site_area,
            "yield_fsr_residential": self.yield_fsr_residential,
            "yield_fsr_commercial": self.yield_fsr_commercial,
            "yield_view": self.yield_view,
            "yield_gfa_residential": self.yield_gfa_residential,
            "yield_gfa_commercial": self.yield_gfa_commercial,
            "yield_nla_residential": self.yield_nla_residential,
            "yield_nla_commercial": self.yield_nla_commercial,
            "yield_affordable_share": self.yield_affordable_share,
            "yield_sqm_per_space": self.yield_sqm_per_space,
            "yield_basement_ratio": self.yield_basement_ratio,
            **{
                f"yield_mix_{name.lower().replace(' ', '_')}_{part}": box
                for name, (share, size) in self.yield_mix.items()
                for part, box in (("share", share), ("size", size))
            },
        }

    def _ticks(self) -> dict[str, tk.BooleanVar]:
        """The boxes, by the same rule."""
        return {
            "study_facade": self.do_facade,
            "study_floors": self.do_floors,
            "study_plans": self.do_plans,
            "study_communal": self.do_communal,
            "study_shadows": self.do_shadows,
            "study_shadow_hours": self.do_shadow_hours,
            "study_sun_eyes": self.do_sun_eyes,
            "site_context": self.do_site_context,
            "site_site": self.do_site_site,
            "site_summary": self.do_site_summary,
            "site_model": self.do_site_model,
            "site_future": self.do_site_future,
            "site_location": self.do_site_location,
            "study_yield": self.do_yield,
            "yield_renovation": self.yield_renovation,
            "yield_xlsx": self.yield_xlsx,
            # The three boxes of days, one key per button, so a preset that
            # studies the equinox beside midwinter opens the same way.
            **{f"day_{name}": state for name, state in self.days.items()},
            **{f"sun_view_day_{name}": state for name, state in self.eye_days.items()},
            **{f"shadow_day_{name}": state for name, state in self.shadow_day_ticks.items()},
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
            if not isinstance(value, str):
                continue
            if isinstance(box, ttk.Combobox) and str(box.cget("state")) == "readonly":
                # A read-only list ignores delete and insert, so every saved
                # style, origin and scale was dropped on the floor. It is set,
                # and only to a value it offers.
                if value in tuple(box.cget("values") or ()):
                    box.set(value)
                continue
            box.delete(0, "end")
            box.insert(0, value)
        for name, state in self._ticks().items():
            ticked = saved.get(name)
            if isinstance(ticked, bool):
                state.set(ticked)
        self._yield_from_older(saved)
        self._shadows_from_older(saved)
        self._proposals_from_older(saved)
        opened = saved.get(self.OPEN_SECTION)
        if isinstance(opened, str):
            # A title this version does not have -- a file saved before the
            # sections existed, or after one was renamed -- leaves the
            # notebook where it is, which is General. Losing which tab was
            # open is the cheapest thing in the file to lose.
            self._show_section(opened)
        self._sync()

    def _shadows_from_older(self, saved: Mapping[str, str | bool]) -> None:
        """A preset saved while the fills were the shadow diagram, read as
        what it meant (D160).

        Its ``study_shadows`` asked for the shadow diagram, which is the
        documents now, and is taken as it stands. Its shadow plans were the
        documents under their older name, so they switch the diagram on too;
        and its every-hour tick, which only ran beside the fills' diagram,
        is the every-hour drawing's own switch. A preset that knows the
        every-hour switch is this version's, and is left alone.
        """
        if "study_shadow_hours" in saved:
            return
        if saved.get("study_shadow_plans") is True:
            self.do_shadows.set(True)
        if saved.get("study_shadows") is True and saved.get("shadow_all_hours") is True:
            self.do_shadow_hours.set(True)

    def _proposals_from_older(self, saved: Mapping[str, str | bool]) -> None:
        """A preset saved while the compared rows were the TOD, SEARs and ADG
        envelopes, read as what it meant (D178).

        Their layers move into Proposed 2 and Proposed 3, the first two
        filled in the order the rows stood; Proposed kept its name and is
        restored as it was. A third filled row has nowhere to go, and the log
        names its layers rather than dropping them unseen. A preset that knows
        the new rows is this version's, and is left alone.
        """
        if any(f"shadow_layers_{short.lower()}" in saved for short in ("PROPOSED 2", "PROPOSED 3")):
            return
        older = [
            (short, value.strip())
            for short in OLDER_SHADOW_ROWS
            if isinstance(value := saved.get(f"shadow_layers_{short.lower()}"), str)
            and value.strip()
        ]
        boxes = {short: box for short, _role, box in self.shadow_rows}
        for (_short, layers), target in zip(older, ("PROPOSED 2", "PROPOSED 3"), strict=False):
            boxes[target].delete(0, "end")
            boxes[target].insert(0, layers)
        for short, layers in older[2:]:
            self._write(
                f"The preset's {short} row ({layers}) has no row now: Proposed 2 and "
                "Proposed 3 hold its first two. Choose its layers again to draw it."
            )

    def _yield_from_older(self, saved: Mapping[str, str | bool]) -> None:
        """A preset saved before the Slabs and Renovation rows, read as what
        it meant: the way of choosing slabs its filled layer rows imply, and
        the renovation checkbox as the floor plan's filter."""
        if "yield_slabs" not in saved:

            def filled(key: str) -> bool:
                value = saved.get(key)
                return isinstance(value, str) and bool(value.strip())

            if filled("yield_option_layers"):
                self.yield_slabs.set("A layer per option")
            elif any(
                filled(key)
                for key in (
                    "yield_residential_layers",
                    "yield_commercial_layers",
                    "yield_retail_layers",
                )
            ):
                self.yield_slabs.set("A layer per use")
            elif filled("yield_massing_layers"):
                self.yield_slabs.set("Slabs on chosen layers")
        # Retail is commercial now (D159): an older file's retail layers and
        # levels join the commercial ones rather than being dropped.
        for retail, box in (
            ("yield_retail_layers", self.yield_commercial),
            ("yield_retail_levels", self.yield_commercial_levels),
        ):
            value = saved.get(retail)
            if isinstance(value, str) and value.strip():
                joined = [*self._listed(box), *(v.strip() for v in value.split(",") if v.strip())]
                box.delete(0, "end")
                box.insert(0, ", ".join(dict.fromkeys(joined)))
        if "yield_renovation_status" not in saved and saved.get("yield_renovation") is True:
            self.yield_renovation_status.set("As the floor plan's filter")

    def _yield_rows(self) -> None:
        """Show the Yield page's rows the Slabs answer needs, and no others.

        A folded panel keeps the rows it will put back when it opens; while
        folded, that list is what changes, so nothing appears inside it.
        """
        groups = getattr(self, "yield_groups", None)
        if not groups:
            return
        shown = YIELD_ROWS.get(self.yield_slabs.get(), YIELD_ROWS["Every slab showing"])
        panel = str(self.yield_panel)
        kept = self._kept_rows.get(panel) if self.folded.get(panel, False) else None
        for key, widgets in groups.items():
            for widget in widgets:
                if kept is not None:
                    if key in shown and widget not in kept:
                        kept.append(widget)
                    elif key not in shown and widget in kept:
                        kept.remove(widget)
                elif key in shown:
                    widget.grid()
                else:
                    widget.grid_remove()

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
    def _picked(self) -> int:
        """Which Archicad in the list is chosen, or -1 for none.

        Tk 9 answers ``current`` with an empty string rather than -1 when the
        box holds nothing from its list, and ``Combobox.current`` hands that
        straight to ``getint`` -- so on a Mac's Tk the first Refresh that
        found an Archicad raised instead of choosing it.
        """
        try:
            return self.instance.current()
        except tk.TclError:
            return -1

    def refresh(self) -> None:
        found = probe.running()
        self.ports = [instance.port for instance in found]
        names = [f"{instance.project}  ·  port {instance.port}" for instance in found]
        # As wide as the longest name it holds, within reason: an office's
        # project files are named for the job and the street, and 34
        # characters cut most of them off before the port.
        longest = max((len(name) for name in names), default=0)
        self.instance.config(
            values=names,
            width=min(max(self.PICKER_LEAST, longest + 2), self.PICKER_MOST),
        )
        if not found:
            # Where every session starts, not a fault: the plug drained but
            # not struck through, and the next step in plain words. The red
            # mark is kept for the project that answered and then could not
            # be read, which is something actually wrong.
            self.instance.set("No Archicad open")
            self.status.config(
                text="Open a project in Archicad, then press Refresh.",
                **icons.state_options("waiting"),
            )
            self.options = probe.ProjectOptions()
            return
        if self._picked() < 0:
            self.instance.current(0)

        self.status.config(text="reading the project ...", **icons.state_options("connected"))
        self.root.update_idletasks()
        self.options = probe.options(self.ports[max(self._picked(), 0)])
        self._offer()

    def _offer(self) -> None:
        found = self.options
        # Nothing here works without the add-on: most of the tool's Archicad
        # calls are Tapir's commands, which the Loriini add-on carries built
        # in. So it is said plainly, and Run is switched off rather than left
        # to fail several steps later.
        self._tapir_missing = found.tapir_missing
        self._paint_run()
        if found.tapir_missing:
            self.status.config(
                text=(
                    "Archicad is running but the Loriini add-on is not installed, "
                    "or is too old to carry Tapir's commands, and nothing here works "
                    f"without it. Install the current {ADDON_FILE} for your Archicad version, "
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
                f"{len(found.zone_layers)} zone layers · {len(found.masters)} masters · "
                f"{len(found.subsets)} subsets"
            ),
            **icons.state_options("connected"),
        )
        self._only_what_this_project_has()
        choices = self._zone_layer_choices()
        # Picked by what is on a layer, never by what it is called (D156):
        # the layer carrying apartment-sized zones, as the zone names below
        # are picked by their size.
        self._fill(
            self.apartments,
            choices,
            tuple(kind.layer for kind in found.zone_kinds if kind.dwelling),
        )
        # The balconies are usually on the apartments' own layer -- one
        # project keeps 15 units, 20 balconies and the storage on
        # "06 | Zone.Units" -- so that is the first candidate, and a layer
        # carrying open-space-sized zones is the next.
        self._fill(
            self.balconies,
            choices,
            (self.apartments.get(), *(kind.layer for kind in found.zone_kinds if kind.open_space)),
        )
        self._fill(self.communal, choices, ())
        self._offer_zone_names()
        # Offered, never picked: which title block a study is issued on is the
        # person's to say, and Run asks when it is blank (asked 17 October
        # 2026). A name chosen once stays chosen across a Refresh.
        self._fill(self.master, found.masters, (), guess=False)
        # A project never located has nothing for a site to line up with, so
        # the site goes on its origin, at a corner of the lot. A located one
        # keeps whatever the page says.
        if not found.located:
            for origin in (
                self.site_context_origin,
                self.site_sheet_origin,
                self.site_model_origin,
            ):
                origin.set("Bottom-left corner")
        # The project's lists, and no names picked out of them by an office's
        # words (D156): a blank is the person's to fill, and the commands
        # treat a blank as "none" -- the sheets at the root of the book, the
        # drawn table rather than a schedule.
        self._fill(self.combination, found.combinations, ())
        self._offer_plan_combination(found.combinations)
        self._fill(self.shadow_subset, found.subsets, ())
        self._fill(self.adg_subset, found.subsets, ())
        self._fill(self.cos_schedule, (NO_SCHEDULE, *found.schedules), (NO_SCHEDULE,))
        # Blank first, and no preference: a blank keeps each view's own pen
        # set, which is what the command does, and the office's set is a
        # choice rather than a guess.
        self._fill(self.eye_pen_set, ("", *found.pen_sets), ())
        # Blank first for the override too: a blank sends nothing and the
        # command's own default holds, where the first name in the list would
        # be a guess -- and a view given the wrong override shows plain glass.
        if found.overrides:
            self._fill(self.eye_override, ("", *found.overrides), ())
        self._fill(self.eye_base_combination, ("", *found.combinations), ())
        self._fill(self.shadow_plan_combination, found.combinations, ())
        self._fill(self.shadow_plan_pen_set, ("", *found.pen_sets), ())
        self._fill(self.shadow_study_subset, found.subsets, ())
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
        # The shadow page's storey too: the same list, for the same reason.
        for box in (self.storey_from, self.storey_to, self.shadow_storey):
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

    def _offer_plan_combination(self, combinations: Sequence[str]) -> None:
        """The plan combination: a plan-like one picked, or none rather than a guess.

        Not ``_fill``, for two reasons. Its fallback is the first name in the
        list, and a plan drawn over an arbitrary combination is worse than one
        drawn over the model's, which is what blank means. And never one of
        this tool's own: it regenerates those every run, and a base that is its
        own output is the drift a base exists to stop.
        """
        own = f"{self.prefix_solar.get().strip() or naming.DEFAULT_PREFIX} "
        values = [name for name in combinations if not name.startswith(own)]
        self.plan_combination.config(values=["", *values])
        if self.plan_combination.get() not in values:
            self.plan_combination.set("")

    def _fill(
        self,
        box: ttk.Combobox,
        values: tuple[str, ...],
        prefer: tuple[str, ...],
        *,
        guess: bool = True,
    ) -> None:
        """Offer these, and pick one only on evidence -- without overriding a choice.

        ``prefer`` is what the project itself points to, read off its content
        (the layer its apartment-sized zones are on), as ordered fragments.
        Nothing matching, nothing is picked: the first name in the list was a
        guess, and an office's words were another (D156). ``guess=False``
        offers them and picks nothing even then.
        """
        box.config(values=list(values))
        if not values or box.get() in values:
            return
        if guess:
            for want in prefer:
                match = next((v for v in values if want.casefold() in v.casefold()), None)
                if match is not None:
                    box.set(match)
                    return
        box.set("")

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
        """Zone layers worth forcing into the export: every layer the project
        carries Zones on. Narrowing them to the ones named for zones read an
        office's naming into the project (D156).
        """
        return list(self.options.zone_layers)

    #: What each choice row draws, keyed on the label it sits beside: the
    #: value the field holds, the icon on the tile, and what the tile says on
    #: hover. The values must match what the rest of the window expects to
    #: read back -- ``SHEET_CHOICES`` below is where the sheet titles are
    #: turned into the word the command line wants.
    #: The choice rows whose tiles are switches of their own rather than one
    #: of a set, and the older spellings each reads as the tiles they mean.
    #: "Bands and times" was the Plans row's third tile until both could be lit.
    TILE_MULTI: ClassVar[frozenset[str]] = frozenset({"Plans"})
    #: Older spellings of the Plans row, read as the tiles they now mean:
    #: "Bands and times" was a tile of its own, and "Bands by hour" was the
    #: heat map and the apartment total together before they were two.
    TILE_ALIASES: ClassVar[dict[str, dict[str, tuple[str, ...]]]] = {
        "Plans": {
            "Bands and times": ("Sun at each time", "Floor heat map", "Apartment total"),
            "Bands by hour": ("Floor heat map", "Apartment total"),
        },
    }

    #: The four grid steps, worded once for every solar grid row.
    GRID_WORDS: ClassVar[dict[str, str]] = {
        "1.0": "Rough",
        "0.5": "Normal",
        "0.25": "Detailed",
        "0.1": "Finest",
    }

    #: The word on each tile's face, by row and then by value: short enough
    #: that a row of three still fits beside its label, and the same words
    #: the tooltip opens with so the two never disagree.
    TILE_WORDS: ClassVar[dict[str, dict[str, str]]] = {
        "Slabs": {
            "Every slab showing": "Everything showing",
            "Slabs on chosen layers": "Chosen layers",
            "A layer per use": "Layer per use",
            "A layer per option": "Layer per option",
        },
        "Renovation": {
            "Any status": "Any",
            "New only": "New only",
            "Existing and new": "Existing + new",
            "As the floor plan's filter": "Floor plan's filter",
        },
        "Plans": {
            "Sun at each time": "Sun at each time",
            "Floor heat map": "Floor heat map",
            "Apartment total": "Apartment total",
        },
        "Sheets": {
            "One layout, all drawings": "One layout",
            "Two layouts, half each": "Two layouts",
            "A layout per drawing": "One per drawing",
        },
        "Skin cell": GRID_WORDS,
        "Communal grid": GRID_WORDS,
        "Shadow grid": GRID_WORDS,
        "Floor grid": GRID_WORDS,
        "Glass": {"off": "Solid", "30": "All glass", "80": "Clear only"},
        "Site lands at": {
            "Project location": "Project location",
            "Project origin": "Project origin",
        },
    }

    TILE_CHOICES: ClassVar[dict[str, tuple[tuple[str, str, str], ...]]] = {
        "Plans": (
            (
                "Sun at each time",
                "plans_times",
                "Sun at each time: a plan per time of day, showing where the "
                "sun actually falls at that moment.",
            ),
            (
                "Floor heat map",
                "plans_bands",
                "Floor heat map: the floor of every apartment gridded and banded "
                "by its own hours of sun over the day -- how far in the sun gets.",
            ),
            (
                "Apartment total",
                "plans_total",
                "Apartment total: each apartment filled whole, in the band of its "
                "hours of sun over the day, with the figure written in.",
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
        # coarseness, and four drawings say which way is finer without a word.
        # The same four steps on every solar grid -- 1, 0.5, 0.25 and 0.1 m --
        # so Detailed means one thing whichever study it is chosen in.
        "Skin cell": (
            ("1.0", "grid_rough", "Rough — 1 m cells. Fast, and it loses anything narrower."),
            (
                "0.5",
                "grid_normal",
                "Normal — 0.5 m cells. Four times the elements of 1 m; over five "
                "thousand on a project this size.",
            ),
            (
                "0.25",
                "grid_fine",
                "Detailed — 0.25 m cells. Four times the elements of 0.5 m, so over "
                "twenty thousand on a project this size, and Archicad slows with them.",
            ),
            (
                "0.1",
                "grid_finest",
                "Finest — 0.1 m cells. Over six times the elements of 0.25 m: well "
                "over a hundred thousand on a project this size. For one small "
                "building, not a whole site.",
            ),
        ),
        "Communal grid": (
            ("1.0", "grid_rough", "Rough — samples every 1 m."),
            (
                "0.5",
                "grid_normal",
                "Normal — samples every 0.5 m, which is what reads a courtyard properly.",
            ),
            (
                "0.25",
                "grid_fine",
                "Detailed — samples every 0.25 m. Four times the samples of 0.5 m, "
                "for a narrow terrace or an area figure that sits on a threshold.",
            ),
            (
                "0.1",
                "grid_finest",
                "Finest — samples every 0.1 m. Over six times the samples of 0.25 m, "
                "and a run to match.",
            ),
        ),
        # The every-hour drawing's ground (D161). The same four again; the
        # command's own is 1 m, and Normal is what the window starts on.
        "Shadow grid": (
            ("1.0", "grid_rough", "Rough — samples every 1 m. Quick; misses anything narrower."),
            ("0.5", "grid_normal", "Normal — samples every 0.5 m."),
            (
                "0.25",
                "grid_fine",
                "Detailed — samples every 0.25 m. Four times the samples of 0.5 m.",
            ),
            (
                "0.1",
                "grid_finest",
                "Finest — samples every 0.1 m. Over six times the samples of 0.25 m, "
                "and a run to match: for a small building, not a whole site.",
            ),
        ),
        # The apartments' floor: the sun patches and the heat map. The same
        # four as the other rows; the study has always gridded it at 0.25 m,
        # which is Detailed, and Rough draws a flat's sun patch in blocks.
        "Floor grid": (
            (
                "1.0",
                "grid_rough",
                "Rough — samples every 1 m. Quick, and the sun patches come out in metre blocks.",
            ),
            ("0.5", "grid_normal", "Normal — samples every 0.5 m."),
            (
                "0.25",
                "grid_fine",
                "Detailed — samples every 0.25 m, the study's own grid until now.",
            ),
            (
                "0.1",
                "grid_finest",
                "Finest — samples every 0.1 m. Over six times the samples of 0.25 m, "
                "so a much slower run for a truer patch edge.",
            ),
        ),
        # The percentages are Archicad's own surface transparency. On Tweed
        # Heads clear glass is 88-90%, tinted and frosted 40-49%, generic
        # translucent 35% and polycarbonate 15%: 30 takes every glass and
        # leaves polycarbonate solid, 80 the clear glass alone.
        "Glass": (
            ("off", "glass_solid", "Solid — glass casts shade like any other surface."),
            (
                "30",
                "glass_all",
                "All glass — every surface at least 30% transparent lets the sun "
                "through: clear, tinted and frosted glass. Polycarbonate stays solid.",
            ),
            (
                "80",
                "glass_clear",
                "Clear only — surfaces at least 80% transparent let the sun through; "
                "tinted and frosted glass still cast shade.",
            ),
        ),
        "Slabs": (
            (
                "Every slab showing",
                "site",
                "Everything showing: every slab on a layer that is showing, its use "
                "told by its level.",
            ),
            (
                "Slabs on chosen layers",
                "site",
                "Chosen layers: the slabs on the layers you choose, the use told by level.",
            ),
            (
                "A layer per use",
                "site",
                "Layer per use: a layer of residential slabs and one of commercial.",
            ),
            (
                "A layer per option",
                "site",
                "Layer per option: each layer one whole option, a sheet and a workbook page each.",
            ),
        ),
        "Renovation": (
            ("Any status", "site", "Any: every slab, whatever its renovation status."),
            ("New only", "site", "New only: the slabs whose renovation status is New."),
            (
                "Existing and new",
                "site",
                "Existing and new: every slab but those To Be Demolished.",
            ),
            (
                "As the floor plan's filter",
                "site",
                "Floor plan's filter: what the floor plan's renovation filter shows; set it "
                "there before Run.",
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
    PLAN_TIMES = "Sun at each time"
    PLAN_HEAT = "Floor heat map"
    PLAN_TOTAL = "Apartment total"

    def _plan_kinds(self) -> tuple[bool, bool, bool]:
        """``(times, heat, total)``: which of the three kinds of plan the
        Plans row asks for. Three because they answer three questions: where
        the sun is at nine, how far into each room it reaches over the day,
        and whether each flat passes. A value naming none of them -- a
        hand-edited file -- is all three, and an older spelling is read
        through the row's aliases."""
        chosen: set[str] = set()
        for part in (piece.strip() for piece in self.plan_kinds.get().split(",")):
            chosen.update(self.TILE_ALIASES["Plans"].get(part, (part,)))
        if not chosen & {self.PLAN_TIMES, self.PLAN_HEAT, self.PLAN_TOTAL}:
            return True, True, True
        return self.PLAN_TIMES in chosen, self.PLAN_HEAT in chosen, self.PLAN_TOTAL in chosen

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

    def _glass_args(self) -> list[str]:
        """``--see-through-glass`` with the tile's percentage, or nothing for
        solid -- which is the command's own default."""
        chosen = self.see_glass.get().strip()
        return ["--see-through-glass", chosen] if chosen.isdigit() else []

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
        return self._chosen(self.days, self.custom_day)

    def chosen_view_days(self) -> list[str]:
        """The same, for the sun views, which have their own row of days."""
        return self._chosen(self.eye_days, self.eye_custom_day)

    @staticmethod
    def _chosen(ticks: dict[str, tk.BooleanVar], custom: ttk.Entry) -> list[str]:
        """The lit days by name, then the typed ones -- several, comma
        separated, so a settings file that held a list of dates restores."""
        days = [name for name in ASSESSMENT_DAYS if name in ticks and ticks[name].get()]
        for typed in (part.strip() for part in custom.get().split(",")):
            if not typed:
                continue
            try:
                mmdd = parse_day(typed)
            except ValueError:
                if typed not in days:
                    days.append(typed)
            else:
                named = day_name(mmdd)
                if named not in days:
                    days.append(named)
        return days or ["winter"]

    def _day_label(self, day: str, among: list[str] | None = None) -> str:
        """How a day reads on a queued job, or "" for the only day there is.

        Silent when one day is studied, because the label is then the tool's
        own name and has always been; a suffix on every job would be noise on
        the ordinary run. With several, the day is what tells two otherwise
        identical jobs apart while they wait. ``among`` is the row the day
        came from; the solar analysis's own when not said.
        """
        if len(self.chosen_days() if among is None else among) < 2:
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
        """The Archicad wait, ``ARCHICAD_WAIT_MIN``, in the seconds
        ``--timeout`` takes."""
        return f"{ARCHICAD_WAIT_MIN * 60.0:g}"

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
        context_scale = self.site_scale.get() or "1:3000"
        eye_scale = f"1:{self.eye_scale.get().strip() or '500'}"
        plan_scale, communal_scale, shadow_scale = "1:200", "1:300", "1:1000"

        # Not at an hour of any day: these are drawn from the address. The
        # context sheet is at the scale its panel says; the site sheet at its
        # own, or fitted to the site from a list of scales the run chooses
        # from, which nothing here can know; the summary is a table.
        sheet_scale = self.site_sheet_scale.get()
        for job, which, scale in (
            (SITE_CONTEXT_JOB, "Context Analysis", context_scale),
            (
                SITE_SHEET_JOB,
                "Site Analysis",
                "to fit" if sheet_scale in ("", FIT_THE_SITE) else sheet_scale,
            ),
            (SITE_CONTROLS_JOB, "Summary of Controls", ""),
        ):
            if job in queued:
                deal(job, "Site analysis", "site", "ST", which, "", [""], scale=scale)
        if SITE_MODEL_JOB in queued:
            # The models are not sheets and are not numbered as sheets: they
            # are geometry on their own layers, and the panel draws them as
            # that. One radius, which the future context reaches too.
            radius = self.site_radius.get().strip() or "500"
            for kind, on, extent in (
                (CONTEXT_MODEL, True, f"{radius} m"),
                (FUTURE_MODEL, self.do_site_future.get(), f"{radius} m reach"),
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
                            job=SITE_MODEL_JOB,
                            paper=False,
                        )
                    )

        if YIELD_JOB in queued:
            # One sheet, at no hour: the table, and the massing beside it.
            deal(YIELD_JOB, "Yield", "yield", "AC", AREA_SHEET, "", [""])

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
        times, heat, total = self._plan_kinds()
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
                if total:
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
                if heat:
                    # The floor inside each flat, banded cell by cell. Placed
                    # coarser than the plans because its legend carries the
                    # areas beside it -- the command's own 1:300.
                    deal(
                        PLANS_JOB,
                        "Solar analysis",
                        "analysis",
                        "SA",
                        APARTMENT_HEAT_MAP,
                        day,
                        [""],
                        scale=communal_scale,
                    )
        if COMMUNAL_JOB in queued:
            for day in days:
                threshold = self.communal_hours.get().strip()
                if heat or total:
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
                if (heat or total) and threshold:
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
            # The documents, dealt by day. A stack of legend rows is fitted
            # to the whole site (D143); a plain set is at the plans' 1:1000.
            hours = self._clocks(self.shadow_hours, DEFAULT_SHADOW_HOURS.split(","))
            stacked = "to fit" if self._legend_args() else shadow_scale
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
                    scale=stacked,
                )

        if SHADOW_HOURS_JOB in queued:
            # One drawing a day, every hour in it, on a sheet of its own
            # fitted to its shadows (D149).
            for day in self._shadow_days():
                deal(
                    SHADOW_HOURS_JOB,
                    "Every hour",
                    "shadow",
                    "SH",
                    "Every hour",
                    day,
                    [""],
                    scale="to fit",
                )

        if SUN_EYE_JOB in queued:
            hours = self._clocks(self.eye_hours, [f"{hour:02d}:00" for hour in range(9, 16)])
            for day in self.chosen_view_days():
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
        """The days the shadow study draws, as ``MM-DD`` -- which is how the
        command takes them -- from the diagram's own box of days. The same
        three buttons the solar analysis and the sun views press, and its
        own answer: winter unless something else is lit or typed."""
        dates: list[str] = []
        for day in self._chosen(self.shadow_day_ticks, self.shadow_custom_day):
            try:
                mmdd = parse_day(day)
            except ValueError:
                mmdd = day
            if mmdd not in dates:
                dates.append(mmdd)
        return dates

    def _shadow_storey_index(self) -> str:
        """What ``--shadow-storey`` is sent: the index of the storey picked by
        name, a number as typed, or nothing for a blank field.

        The command takes an index, because that is what Archicad places a
        fill by. The window offers names, because an index is a fact about
        the storey settings dialog and a name is a fact about the building.
        A name the project does not have -- a preset from another project --
        is sent as typed, and the command says what it makes of it.
        """
        chosen = self.shadow_storey.get().strip()
        if not chosen:
            return ""
        for name, index in self.options.storey_indices:
            if name == chosen:
                return str(index)
        return chosen

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

        Before a project says where it is, the sun is put over Sydney --
        Archicad's own preset, and where these studies are made -- so a
        shadow diagram shows shadows rather than an empty plan. The card says
        so while the pointer is on the sheet: a miniature is a picture of
        what the run will make, and the run itself will not start without the
        project's real location.

        The timezone is the one the run itself passes, so the panel and the
        study cannot disagree about what 12:00 means. It matters: in December
        that is daylight saving, solar noon is nearer one o'clock, and a
        summer study set to noon is not a midday study.
        """
        latitude, longitude = self.options.latitude, self.options.longitude
        if latitude is None or longitude is None:
            latitude, longitude = STAND_IN_PLACE
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
            found = solar_position([when], latitude, longitude)
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
            detail = _untimed_note(sheet)
        elif sheet.elevation is None:
            detail = "No sun can be put on it: the day or the hour is not one."
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
        if sheet.time and self.options.latitude is None:
            # First, so the card's length limit never cuts it off.
            detail = (
                "Drawn with Sydney's sun until the project has a location: set one in "
                "Options > Project Preferences > Project Location, then press Refresh. " + detail
            )
        if sheet.time:
            short = f"{sheet.kind}, {sheet.day} at {sheet.time}."
        elif sheet.day:
            short = f"{sheet.kind}, {sheet.day}."
        else:
            short = f"{sheet.kind}."
        self.info.show(sheet.glyph, sheet.number, short, detail, state="not drawn yet")

    def _legend_args(self) -> list[str]:
        """The shadow legend's rows as flags, one per filled row.

        ``NAME=layer,layer``: the name is the row's short name, which the
        drawing matches to the legend's colour, and the layers are what find
        its geometry. A row that accumulates is a ``--shadow-source`` and one
        that is compared a ``--shadow-scenario``. An empty row is left off
        the sheet. The shadow diagram and the shadow plans take the same rows,
        so one legend is chosen once for both.
        """
        args: list[str] = []
        drawn = [short for short, _words, _role, _rgb in SHADOW_LEGEND]
        for short, role, box in sorted(
            self.shadow_rows,
            key=lambda row: drawn.index(row[0]) if row[0] in drawn else len(drawn),
        ):
            layers = self._listed(box)
            if layers:
                flag = "--shadow-source" if role == "baseline" else "--shadow-scenario"
                args += [flag, f"{short}={','.join(layers)}"]
        return args

    def _designed_row(self) -> str:
        """The legend row the every-hour drawing outlines, by its short name,
        or nothing when no row being compared has layers.

        The command's own rule (``designed_source``): the Proposed row, or
        the last row being compared when Proposed is empty.
        """
        compared = [
            short
            for short, role, box in self.shadow_rows
            if role != "baseline" and self._listed(box)
        ]
        if "PROPOSED" in compared:
            return "PROPOSED"
        return compared[-1] if compared else ""

    def jobs(self) -> list[Job]:
        """The command lines the ticked boxes mean. Public, and pure, because
        this is the part worth testing without a window on screen."""
        port = str(self.ports[max(self._picked(), 0)]) if self.ports else ""
        common = ["--port", port, "--timeout", self._wait_seconds()]
        made: list[Job] = []

        if self.do_facade.get():
            args = [
                "massing",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_solar),
                "--export",
                "native",
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
            # The neighbours into the model, so they shade the facade. Not as
            # --context-layer: the facade is measured on its own layers, so
            # they add nothing to its area, and naming both sides would narrow
            # the model to them and drop whatever else the scheme casts.
            for name in self._listed(self.context):
                args += ["--require-layer", name]
            args += self._band_args() + self._glass_args()
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
            times, heat, total = self._plan_kinds()
            args = [
                "archicad-run",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_solar),
                # --draw is the whole-day sheet, each apartment filled whole
                # in the band of its hours of sun; --sheet makes the layouts
                # for every kind, and without --draw it makes the other two
                # alone.
                "--draw" if total else "--no-draw",
                "--sheet",
                # The native model and never an IFC: a missing ExportModel
                # stops the run with a sentence instead of quietly exporting
                # six hundred megabytes of properties nothing here reads.
                "--export",
                "native",
            ]
            if heat:
                # The heat map, its own tile now: the floor of every apartment
                # gridded and banded by its own hours of sun, which is the
                # sheet that shows how far into the room the sun gets.
                # --draw says whether a flat passes; this says where.
                args += ["--plan-bands"]
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
            # What the Model tab says every solar study sees. This study was
            # the one that got neither: a neighbour the combination hides was
            # not in its model, and the apartments were measured with nothing
            # next door -- more sun than they get, and nothing to say so.
            for name in [*self._listed(self.require), *self._listed(self.context)]:
                args += ["--require-layer", name]
            if self.plan_combination.get():
                args += ["--plan-combination", self.plan_combination.get()]
            for stamp in self._listed(self.instants) if times else []:
                args += ["--plan-instant", stamp]
            # The floor grid only where a plan reads the floor. Named with the
            # total alone, it would switch on a second ray cast for nothing.
            if times or heat:
                args += ["--patch-grid", self.floor_grid.get().strip() or "0.25"]
            args += self._band_args() + self._glass_args()
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
                "--export",
                "native",
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
            args += self._band_args() + self._glass_args()
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            if self.adg_subset.get():
                args += ["--zone-subset", self.adg_subset.get()]
            if self.plan_combination.get():
                args += ["--zone-view-combination", self.plan_combination.get()]
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
            # The communal plan has two kinds, not three: the open space is
            # banded as one heat map, so either whole-day tile asks for it.
            times, heat, total = self._plan_kinds()
            if times:
                args += ["--zone-hourly"]
                schedule = self.cos_schedule.get().strip()
                if schedule and schedule != NO_SCHEDULE:
                    args += ["--zone-schedule", schedule]
            if not (heat or total):
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
            # The shadow diagram: the documents, on the diagram's own days
            # and hours (D144).
            args = [
                "shadow-plans",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_shadow),
                "--shadow-date",
                ",".join(self._shadow_days()),
            ]
            # The legend rows, when any is filled: a document per row, and
            # every row of an hour stacked in one drawing, each in its legend
            # colour (D142). The set name and the shadow pen are for the
            # plain set and are not sent with them.
            legend = self._legend_args()
            args += legend
            plain_only = ("--label", "--shadow-pen")
            for flag, field in (
                ("--shadow-hour", self.shadow_hours),
                ("--layer-combination", self.shadow_plan_combination),
                ("--label", self.shadow_plan_label),
                ("--pen-set", self.shadow_plan_pen_set),
                ("--shadow-pen", self.shadow_plan_pen),
                ("--subset", self.shadow_study_subset),
                ("--master-layout", self.master),
            ):
                if field.get().strip() and not (legend and flag in plain_only):
                    args += [flag, field.get().strip()]
            args += ["--year", self.year.get().strip() or "2024"]
            args += self._sheet_args()
            made.append(Job(SHADOW_JOB, args))

        if self.do_shadow_hours.get():
            # The design's every hour on one drawing, cast by Loriini and
            # drawn as fills, and nothing else: no fill, view or sheet per
            # hour, which the documents above draw (D144, D160). The same
            # legend, which says what the design is and what it lands on.
            args = [
                "shadows",
                "--timezone",
                TIMEZONE,
                *common,
                *self._prefix_flag(self.prefix_shadow),
            ]
            args += self._legend_args()
            for name in self._listed(self.terrain_layers):
                args += ["--shadow-terrain", name]
            # Drawn and put on its sheet. Without these the command measures
            # the hours, prints the areas and draws nothing, which is what
            # the window's fills job had always sent it.
            args += ["--export", "native", "--shadow-all-hours-only", "--draw", "--sheet"]
            if self.shadow_grid.get().strip():
                args += ["--shadow-grid", self.shadow_grid.get().strip()]
            if self.shadow_hours_colour.get():
                args += ["--shadow-all-hours-colour", self.shadow_hours_colour.get()]
            if self.terrain_floor.get().strip():
                args += ["--shadow-terrain-floor", self.terrain_floor.get().strip()]
            args += ["--shadow-date", ",".join(self._shadow_days())]
            if self.shadow_hours.get().strip():
                args += ["--shadow-hour", self.shadow_hours.get().strip()]
            if self._shadow_storey_index():
                args += ["--shadow-storey", self._shadow_storey_index()]
            args += self._band_args()
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            if self.shadow_study_subset.get():
                args += ["--shadow-subset", self.shadow_study_subset.get()]
            args += ["--year", self.year.get().strip() or "2024"]
            args += self._sheet_args()
            made.append(Job(SHADOW_HOURS_JOB, args))

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
            ):
                if field.get().strip():
                    args += [flag, field.get().strip()]
            # The hours open lit at the ruleset's window, so the row shows
            # what will be drawn. Lit exactly so, nothing is sent: the
            # ruleset's own window stands, and follows it if it ever moves.
            hours = self.eye_hours.get().strip()
            if hours and _hours_in(hours) != _hours_in(DEFAULT_SHADOW_HOURS):
                args += ["--hour", hours]
            if self.master.get():
                args += ["--master-layout", self.master.get()]
            args += ["--year", self.year.get().strip() or "2024"]
            # One run per day lit on the views' own row. Each carries its own
            # date, and a command names everything it makes after the day it
            # studied, so the sets stand beside each other in the project
            # instead of the second quietly replacing the first.
            view_days = self.chosen_view_days()
            for day in view_days:
                made.append(
                    Job(
                        SUN_EYE_JOB + self._day_label(day, view_days),
                        [*args, *self._day_args(day), *self._sheet_args()],
                    )
                )

        made += self._site_jobs(common)

        if self.do_yield.get():
            made.append(Job(YIELD_JOB, self._yield_args(common)))

        return made

    def _site_jobs(self, common: list[str]) -> list[Job]:
        """The site page's runs: one per lit panel, each placed as it says.

        Each panel is a run of its own (D157), so each can put its output at
        its own origin and turn it its own way. The project has one location
        and one north, though, so only one run may write them: the first,
        which is the 3D context when it is on -- the model has to line up
        with the building -- then the Context Analysis, then the Site
        Analysis. It runs first so that a later panel placed by the
        project's location finds the one it wrote; every other run is told
        ``--keep-location``. The future slabs are stood by the 3D context's
        run alone: the site sheet's draws their outlines and leaves the model
        to it (``--no-future-slabs``).
        """
        address = self.site_address.get().strip()
        if not address:
            return []
        shared = [
            "site",
            address,
            *common,
            *self._prefix_flag(self.prefix_site),
            *self._flag("--context-prefix", self.prefix_context),
        ]
        # Placed by each panel's Origin and North and by nothing else
        # (D158): the fit to a boundary drawn in the file overrode both
        # unseen, which on the page read as the panels not working.
        shared += ["--fit-layer", "none"]
        # Its sheets go on the master the others' do. Without it the
        # command, having nobody to ask, stops at the first sheet.
        if self.master.get():
            shared += ["--master-layout", self.master.get()]

        def only(output: str) -> list[str]:
            """The one sheet this run makes, and the others switched off."""
            return [
                f"--{name}" if name == output else f"--no-{name}"
                for name in ("context", "site", "summary")
            ]

        def placed(origin: ttk.Combobox, north: ttk.Combobox) -> list[str]:
            """The combobox says it in words; the command takes keywords."""
            corner = ORIGIN_WORDS.get(origin.get())
            if corner is None:
                return ["--anchor", "location"]
            args = ["--anchor", "site"]
            if corner != "centre":
                args += ["--origin-at", corner]
            if TURN_WORDS.get(north.get(), False):
                args += ["--square-to-site"]
            return args

        # Blank is the 500 m the sheets panel shows, sent rather than left to
        # the command: its own defaults are a 500 m model and a 100 m reach,
        # and one radius is what the panel promises for both.
        radius = self.site_radius.get().strip() or "500"
        reach = ["--model-radius", radius, "--future-reach", radius]
        future = self.do_site_model.get() and self.do_site_future.get()
        runs: list[tuple[str, list[str]]] = []
        if self.do_site_model.get():
            args = [*only(""), "--model", "--model-radius", radius]
            if future:
                args += ["--future", "--future-reach", radius]
            levels = self.site_levels.get().strip()
            datum = LEVEL_WORDS.get(levels, levels.removesuffix("m").strip())
            if datum and datum != "project":
                args += ["--datum", datum]
            runs.append(
                (SITE_MODEL_JOB, args + placed(self.site_model_origin, self.site_model_north))
            )
        if self.do_site_context.get():
            args = only("context")
            if self.site_scale.get():
                args += ["--scale", self.site_scale.get().removeprefix("1:")]
            style = _style_id(self.site_theme.get(), site=False)
            if style not in ("", site_theme.DEFAULT_THEME):
                args += ["--theme", style]
            runs.append(
                (SITE_CONTEXT_JOB, args + placed(self.site_context_origin, self.site_context_north))
            )
        if self.do_site_site.get():
            args = only("site")
            if self.site_sheet_scale.get() not in ("", FIT_THE_SITE):
                args += ["--site-scale", self.site_sheet_scale.get().removeprefix("1:")]
            style = _style_id(self.site_site_theme.get(), site=True)
            if style not in ("", site_theme.DEFAULT_SITE_THEME):
                args += ["--site-theme", style]
            if future:
                args += ["--future", "--no-future-slabs", *reach]
            runs.append(
                (SITE_SHEET_JOB, args + placed(self.site_sheet_origin, self.site_sheet_north))
            )
        if self.do_site_summary.get():
            runs.append((SITE_CONTROLS_JOB, only("summary")))

        made: list[Job] = []
        for index, (job, args) in enumerate(runs):
            sets = index == 0 and job != SITE_CONTROLS_JOB and self.do_site_location.get()
            made.append(Job(job, [*shared, *args, *([] if sets else ["--keep-location"])]))
        return made

    def _yield_args(self, common: list[str]) -> list[str]:
        """The yield analysis's command line, from the Yield page."""
        args = ["yield", *common]
        # Only the rows the Slabs answer shows: a layer left in a row that is
        # hidden must not quietly change what is counted.
        shown = YIELD_ROWS.get(self.yield_slabs.get(), YIELD_ROWS["Every slab showing"])
        pickers: list[tuple[str, Any, str]] = [
            ("--residential-layer", self.yield_residential, "per_use"),
            ("--commercial-layer", self.yield_commercial, "per_use"),
            ("--massing-layer", self.yield_massing, "layers"),
            ("--option-layer", self.yield_option_layers, "option_layers"),
            ("--commercial-level", self.yield_commercial_levels, "levels"),
        ]
        for flag, box, group in pickers:
            if group in shown:
                for name in self._listed(box):
                    args += [flag, name]
        status = self.yield_renovation_status.get()
        if status == "As the floor plan's filter":
            args.append("--renovation-filter")
        elif status in RENOVATION_STATUS_FLAGS:
            args += ["--renovation-status", RENOVATION_STATUS_FLAGS[status]]
        if "option" in shown:
            args += self._flag("--option", self.yield_option)
        for flag, control in (
            ("--gfa-residential", self.yield_gfa_residential),
            ("--gfa-commercial", self.yield_gfa_commercial),
            ("--nla-residential", self.yield_nla_residential),
            ("--nla-commercial", self.yield_nla_commercial),
            ("--affordable-share", self.yield_affordable_share),
            ("--sqm-per-space", self.yield_sqm_per_space),
            ("--basement-site-ratio", self.yield_basement_ratio),
            ("--site-area", self.yield_site_area),
            ("--fsr-residential", self.yield_fsr_residential),
            ("--fsr-commercial", self.yield_fsr_commercial),
        ):
            args += self._flag(flag, control)
        # Whatever the page does not say about the site is read at the
        # address the Site analysis page has, when it has one.
        address = self.site_address.get().strip()
        permissible = any(
            box.get().strip()
            for box in (
                self.yield_fsr_residential,
                self.yield_fsr_commercial,
            )
        )
        if address and not (self.yield_site_area.get().strip() and permissible):
            args += ["--address", address]
        # Every type goes, a share of nothing included: the sheet shows the
        # type on its own row either way.
        defaults = {name: size for name, _share, size in MIX_ROWS}
        for name, (share_box, size_box) in self.yield_mix.items():
            share = share_box.get().strip().rstrip("%").strip() or "0"
            size = size_box.get().strip() or defaults.get(name, "")
            args += ["--unit", f"{name}={share},{size}"]
        if self.yield_view.get().strip():
            args += ["--view", self.yield_view.get().strip()]
        if self.master.get():
            args += ["--master-layout", self.master.get()]
        if self.yield_xlsx.get():
            wanted = self.yield_workbook.get().strip()
            tables = self._tables_folder()
            if wanted:
                args += ["--xlsx", wanted]
            elif tables is not None:
                args += ["--xlsx", str(tables / AREA_TABLE)]
        return args

    def _start(self) -> None:
        if self.run is not None and self.run.running:
            return
        if not self.ports:
            self._write("No Archicad to run against. Open a project, then Refresh.")
            return
        if self.options.tapir_missing:
            self._write("The Loriini add-on is not installed in this Archicad.")
            return
        site_on = any(
            tick.get()
            for tick in (
                self.do_site_context,
                self.do_site_site,
                self.do_site_model,
                self.do_site_summary,
            )
        )
        if site_on and not self.site_address.get().strip():
            self._write("Site analysis is ticked but has no address. Type one in its section.")
            return
        if any(tick.get() for _name, tick, _section in self._studies()) and not self._have_master():
            return
        if self.do_shadows.get() and not self.shadow_plan_combination.get().strip():
            # No office combination to fall back on (D156): the documents are
            # pinned to this one, so it is asked for rather than guessed.
            self._write(
                "The shadow diagram needs a layer combination: pick the one with "
                "the buildings and the ground under them, in its Layers row."
            )
            return
        if self.do_shadow_hours.get() and not self._designed_row():
            # The command would otherwise fall back to a fill per hour, the
            # diagram the documents draw now (D160).
            self._write(
                "Every hour on one drawing needs the design: choose its layers "
                "for the Proposed row, or another row being compared, in the "
                "Shadow diagram panel."
            )
            return
        queued = self.jobs()
        if not queued:
            self._write("Nothing selected. Tick a study first.")
            return

        self.lines.clear()
        self._start_log([job.label for job in queued])
        self.queued = queued
        self._running = True
        self._paint_run()
        self.cancel.config(state="normal")
        self.cancel.grid()
        self.progress_row.grid()
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
        self.progress_row.grid_remove()
        self._running = False
        self._paint_run()
        self.cancel.config(state="disabled")
        self.cancel.grid_remove()
        if self.log is not None:
            self.log.close()
            self.log = None

    def _start_log(self, studies: Sequence[str]) -> None:
        """A transcript file for the run about to start, and the link to it."""
        if self.log is not None:
            self.log.close()
        self.log = run_log.RunLog.start(studies)
        if self.log is None:
            return
        self.last_log = self.log.path
        self.log_link.grid(row=0, column=1, sticky="e", padx=(8, 0))

    def _open_log(self) -> None:
        """Open the last run's transcript, or say why it cannot be."""
        if self.last_log is None or not self.last_log.is_file():
            self._say("No log to open yet: the transcript is written from a run.")
            return
        if not run_log.open_file(self.last_log):
            self._say(f"The log is {self.last_log}")

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
                    if self.log is not None:
                        # Said on screen as well as filed: the one line left
                        # showing is the one that says where the rest is.
                        self._write(f"The whole run is in {self.log.path}")
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
        if self.log is not None:
            self.log.write(line)
        if line.strip(" ─"):
            self._say(line)


#: The artwork a Mac window started from a checkout wears in the Dock. A
#: PNG, because a Mac does nothing with an .ico.
MAC_DOCK_ICON = "loriini-icon-256.png"

#: The wordmark the tool bar and the About box show: the name written, black
#: on nothing (D165). One file, at a size no screen reaches, fitted to the
#: heading face's line by ``brand_wordmark`` with a proper filter: Tk can
#: only shrink a picture by dropping pixels, which leaves letters in pieces.
BRAND_WORDMARK = "loriini-wordmark.png"


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


#: The wordmark's height as a share of a line of the heading face: the
#: proportion of the artwork's own mock-up, where the word's x-height is near
#: twice the picker's capitals, so it reads as a mark and not as one more
#: label in the bar.
WORDMARK_LINES = 1.4


def brand_height(window: tk.Misc) -> int:
    """How tall the wordmark is shown: ``WORDMARK_LINES`` lines of the heading
    face the name was set in before it, so it grows with the type on a
    scaled screen rather than being one size on every one."""
    try:
        spec = ttk.Style(window).lookup("Brand.TLabel", "font") or "TkDefaultFont"
        line = int(tkfont.Font(root=window, font=spec).metrics("linespace"))
        return max(1, round(line * WORDMARK_LINES))
    except (tk.TclError, RuntimeError, ValueError):
        return 24


def brand_wordmark(window: tk.Misc, tall: int) -> ImageTk.PhotoImage | None:
    """The wordmark ``tall`` pixels high, or ``None`` without it.

    Fitted by Pillow rather than Tk: ``PhotoImage`` shrinks only by dropping
    whole rows and columns, and the file is a dozen times taller than the
    bar. ``None`` is an ordinary answer, as it is for every icon: the bar
    then shows the name in the heading face, as it did before the wordmark.
    """
    packaged = getattr(sys, "_MEIPASS", None)
    root = Path(packaged) if packaged else Path(__file__).resolve().parents[3]
    found = root / "assets" / BRAND_WORDMARK
    if not found.is_file() or tall < 1:
        return None
    try:
        from PIL import Image, ImageTk

        with Image.open(found) as source:
            picture = source.convert("RGBA")
        wide = max(1, round(picture.width * tall / picture.height))
        fitted = picture.resize((wide, tall), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(fitted, master=window)
    except (ImportError, OSError, ValueError, tk.TclError, RuntimeError):
        return None


def wear_the_icon(window: tk.Tk) -> None:
    """Put the application icon on the window and everything it opens.

    ``--icon`` at build time carves the icon into the .exe as a Windows
    resource, which is what Explorer and the task bar read -- and Tk never
    looks at it. Without this the executable has the right icon in the folder
    and the window it opens wears the Tk feather, which is the sort of half a
    job somebody notices immediately.

    ``default=`` rather than a plain call, so the message boxes and dialogs
    raised later inherit it instead of each needing to be found and dressed.

    A Mac is the other way round, and ``wear_the_mac_icon`` says how.
    """
    if theme.MACOS:
        wear_the_mac_icon(window)
        return
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


def wear_the_mac_icon(window: tk.Tk) -> None:
    """The Dock's icon, for the one Mac window that would not have it.

    A Mac reads an application's icon out of its bundle: Loriini.app carries
    ``loriini.icns`` and the Dock shows it without Tk being asked anything, so
    the packaged program is left alone -- dressing it again would swap the
    bundle's full set of sizes for one smaller picture. A window started from
    a checkout is Python's, and wears Python's rocket. ``iconphoto`` is how Tk
    changes the Dock's picture, so that is the one place it is used.
    """
    if getattr(sys, "frozen", False):
        return
    found = Path(__file__).resolve().parents[3] / "assets" / MAC_DOCK_ICON
    if not found.is_file():
        return
    try:
        # Tk copies the picture as it is set, so it need not be kept.
        window.iconphoto(True, tk.PhotoImage(master=window, file=str(found)))
    except tk.TclError:
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
    # A build that takes licence keys asks for one before anything else, the
    # first time and whenever the key held cannot be used; closed without
    # one, nothing opens (roadmap R5). An online key whose lease is in force
    # is renewed in the background, once a day, and never waited on (D125).
    found = licence.standing()
    if found.usable:
        licence.refresh(found)
    else:
        root.withdraw()
        if licence_box.ask(root, first=True) is None:
            root.destroy()
            return
        root.deiconify()
    window = Window(root)
    if study:
        window.ask_for(study)
    root.mainloop()
