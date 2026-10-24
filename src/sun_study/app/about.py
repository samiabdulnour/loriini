"""The info box: what this is, on what terms, and whose data is on the sheet.

Three questions, one box, because they are asked by the same person at the
same moment and none of them is a setting.

*Whose data is this?* The site analysis draws a neighbourhood nobody in the
office surveyed. Seven public registers answer for it, all but one of them
under a licence that asks for a credit on anything drawn from it, and a DA
set is exactly the sort of thing that gets drawn from it. A colleague sending
a Context Analysis sheet out has to be able to find that credit in the ten
seconds before they send it, and it has to be the publisher's own wording --
Spatial Services and Transport for NSW both state one, and neither is what
anybody would guess. So the box carries the line ready to copy.

*What may I do with the program?* The short form of the licence, because the
question a colleague actually has is "may I give this to the consultant", and
that is one line rather than a page. Which licence depends on the build: one
that takes licence keys was bought, and shows the subscription terms sold at
loriini.app; one that does not is the source, and shows the source licence.
The full text remains the authority and the box says so; the button under it
puts the whole of it on screen for the person who needs it.

*Is this any good yet?* The prototype notice, in the same words as the README,
the run bar and every exported file -- from ``disclaimer``, so the four cannot
drift apart.

What it deliberately does not say
---------------------------------
When this build stops working. ``licence`` is silent about its own term while
the build is inside it, and that silence is not merely a property of
``--help``: a date in an info box is the countdown that module refuses to
give, put somewhere a colleague trips over it a year early. The terms it shows
are the terms; the date is nobody's business until it matters, and then the
tool says it at the door, on its own.

Opened from two places
----------------------
The ⓘ beside the project picker, which belongs to no section and is always
in view, and ``Where this data comes from`` on the Site analysis page, which
is where the question occurs to somebody. The second opens the same box
scrolled to the sources, so the button lands on the answer rather than near
it.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from functools import partial
from tkinter import ttk

from sun_study import AUTHOR, COPYRIGHT, PRODUCT, __version__, licence
from sun_study.app import theme
from sun_study.disclaimer import DISCLAIMER, STATUS
from sun_study.site.sources import SOURCES, credit_line

__all__ = ["About", "show"]

PAD = theme.PAD

#: How wide the prose wraps. Narrower than the box, so the text has a margin
#: on the right rather than running into the scrollbar.
WRAP = 520

#: What ``at`` may be: the top, or the sources. Two entry points, and the
#: names are the buttons' own subjects rather than widget names.
TOP = ""
SOURCES_SECTION = "sources"

#: The heading that section carries, in one place because two things read it:
#: the box that draws it and ``look_at``, which scrolls to it.
SOURCES_TITLE = "Where the site analysis data comes from"

#: The one box, whichever button was pressed. A second copy of an info box is
#: never what anybody meant -- the first is simply behind the window -- so the
#: existing one is raised instead.
_open: About | None = None


def show(parent: tk.Misc, *, at: str = TOP) -> About:
    """Open the box, or raise the one already open, and answer with it."""
    global _open
    if _open is not None:
        try:
            _open.deiconify()
            _open.lift()
            _open.focus_set()
            _open.look_at(at)
        except tk.TclError:  # pragma: no cover - destroyed without telling us
            _open = None
        else:
            return _open
    _open = About(parent, at=at)
    return _open


class About(tk.Toplevel):
    """The box itself. Read-only but for the one line it offers to copy."""

    def __init__(self, parent: tk.Misc, *, at: str = TOP) -> None:
        super().__init__(parent)
        self.title(f"About {PRODUCT}")
        self.transient(parent.winfo_toplevel())
        self.minsize(560, 480)
        # Tall rather than wide: it is a page of prose with a heading every
        # few lines, and prose set 600 px wide is read in a glance while the
        # same words set 900 px wide are read twice.
        self.geometry("620x680")
        # Not modal. The question is asked *about* something on the window
        # behind it -- which address, which sheet -- and a box that will not
        # let a person look at that while reading is a box they close first
        # and reopen after.
        # The window's own anatomy, since D136: a chrome band at the top with
        # the mark and the name, the page under it with a white card per
        # section, and a chrome band at the foot with the buttons -- so the
        # box reads as a page of the window it was opened from, in the
        # window's greys and with its lemon on the one thing that is an
        # action.
        self.configure(background=theme.CHROME)

        self._heading(self)
        ttk.Frame(self, style="Rule.TFrame", height=1).pack(side="top", fill="x")

        buttons = ttk.Frame(self, style="Chrome.TFrame", padding=(PAD * 2, PAD, PAD * 2, PAD))
        buttons.pack(side="bottom", fill="x")
        buttons.columnconfigure(0, weight=1)
        ttk.Frame(self, style="Rule.TFrame", height=1).pack(side="bottom", fill="x")
        self._full = ttk.Button(
            buttons,
            text="Read the full terms" if licence.keys_required() else "Read the full licence",
            command=self._show_the_licence,
            style="Run.TButton",
            width=22,
        )
        self._full.grid(row=0, column=0, sticky="w")
        if licence.full_text() is None:
            # A build whose licence text did not make it in. The summary above
            # is in the executable and stands on its own, so the button goes
            # rather than the box.
            self._full.grid_remove()
        ttk.Button(
            buttons, text="Close", command=self._close, style="Chrome.TButton", width=11
        ).grid(row=0, column=1)

        # Imported here and not at the top of the module: the window is what
        # opens this box, so a module-level import back into it would be a
        # cycle. By the time a button can be pressed, ``window`` is long since
        # imported and this costs a dictionary lookup.
        from sun_study.app.window import Scroller

        scroller = Scroller(self, ground=theme.PAGE)
        scroller.pack(side="top", fill="both", expand=True)
        self._scroller = scroller
        page = scroller.content
        page.columnconfigure(0, weight=1)

        #: Every section's card, by its heading's own words, so ``look_at``
        #: can put one at the top of the pane without counting rows -- a
        #: count would be wrong the first time a clause is added to the
        #: licence summary.
        self._headings: dict[str, ttk.Frame] = {}
        row = 0
        row = self._status(page, row)
        row = self._licence(page, row)
        row = self._sources(page, row)
        row = self._credit(page, row)

        self.bind("<Escape>", lambda _event: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.look_at(at)

    # -- the parts, top to bottom -----------------------------------------

    def _heading(self, parent: tk.Misc) -> None:
        """Whose program this is. The one part that is not scrolled away: the
        window's own top band, with the mark, the name, the version as the
        chip the window uses for a figure, and the two lines under them."""
        from sun_study.app.window import brand_mark

        head = ttk.Frame(
            parent, style="Chrome.TFrame", padding=(PAD * 2, PAD + 4, PAD * 2, PAD + 2)
        )
        head.pack(side="top", fill="x")
        head.columnconfigure(1, weight=1)
        mark = brand_mark(self)
        if mark is not None:
            self._mark = mark  # Tk forgets a picture nothing in Python holds
            ttk.Label(head, image=mark, style="Brand.TLabel").grid(
                row=0, column=0, rowspan=3, sticky="nw", padx=(0, 10)
            )
        name = ttk.Frame(head, style="Chrome.TFrame")
        name.grid(row=0, column=1, sticky="w")
        ttk.Label(name, text=PRODUCT, style="Brand.TLabel").pack(side="left")
        ttk.Label(name, text=__version__, style="Chip.TLabel").pack(side="left", padx=(8, 0))
        ttk.Label(head, text=AUTHOR, style="ChromeHint.TLabel").grid(row=1, column=1, sticky="w")
        # Clause 2(e): this line may not be removed from the software or from
        # what it draws. It is here for the same reason it is on every sheet.
        ttk.Label(head, text=COPYRIGHT, style="ChromeHint.TLabel").grid(row=2, column=1, sticky="w")

    def _status(self, page: ttk.Frame, row: int) -> int:
        """What the numbers are worth. The same words as everywhere else."""
        card = self._title(page, row, "What this is")
        ttk.Label(card, text=STATUS, style="Refused.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        self._paragraph(card, 1, DISCLAIMER)
        return row + 1

    def _licence(self, page: ttk.Frame, row: int) -> int:
        card = self._title(page, row, "Licence")
        page, row = card, 0
        if licence.keys_required():
            # Whose licence this is, and the way to change the key -- only in
            # a build that takes keys, so a build that does not says nothing
            # about them (roadmap R5).
            self._holder = ttk.Label(
                page, text=licence.standing().describe(), wraplength=WRAP, justify="left"
            )
            self._holder.grid(row=row, column=0, sticky="w", pady=(0, 4))
            row += 1
            keys = ttk.Frame(page)
            keys.grid(row=row, column=0, sticky="w", pady=(0, 8))
            ttk.Button(keys, text="Enter licence key…", command=self._enter_key, width=20).grid(
                row=0, column=0
            )
            # An online key can be checked with the licence service on the
            # spot -- after a payment, or a seat freed elsewhere (D125).
            self._check = ttk.Button(keys, text="Check now", command=self._check_now, width=12)
            self._check.grid(row=0, column=1, padx=(6, 0))
            if not licence.standing().online:
                self._check.grid_remove()
            row += 1
        for clause in licence.summary():
            ttk.Label(
                page,
                text=f"•  {clause}",
                wraplength=WRAP,
                justify="left",
            ).grid(row=row, column=0, sticky="w", pady=(0, 3))
            row += 1
        closing = (
            "This is the short form. The terms at loriini.app/terms, also in "
            "LICENSE.txt beside the program, are the agreement, and where the "
            "two differ the terms win."
            if licence.keys_required()
            else "This is the short form. The LICENSE file that came with this "
            "build is the licence, and where the two differ the file wins."
        )
        self._paragraph(page, row, closing, style="Hint.TLabel")
        return int(card.grid_info()["row"]) + 1

    def _sources(self, page: ttk.Frame, row: int) -> int:
        """One block per publisher, and every block ends in its own terms."""
        card = self._title(page, row, SOURCES_TITLE)
        page, row = card, 0
        row = self._paragraph(
            page,
            row,
            "The site analysis fetches the neighbourhood from public "
            "registers rather than from a survey. Nothing here is the "
            "author's, all of it is somebody's to credit, and a sheet drawn "
            "from it should carry the line at the foot of this box.",
        )
        for source in SOURCES:
            block = ttk.Frame(page)
            block.grid(row=row, column=0, sticky="ew", pady=(6, 8))
            block.columnconfigure(0, weight=1)
            row += 1

            inner = 0
            ttk.Label(block, text=source.name, style="Strong.TLabel", wraplength=WRAP).grid(
                row=inner, column=0, sticky="w"
            )
            inner += 1
            ttk.Label(block, text=source.publisher, style="Hint.TLabel", wraplength=WRAP).grid(
                row=inner, column=0, sticky="w"
            )
            inner += 1
            for text in (source.provides, f"Licence: {source.licence}", source.note):
                if not text:
                    continue
                ttk.Label(block, text=text, wraplength=WRAP, justify="left").grid(
                    row=inner, column=0, sticky="w", pady=(3, 0)
                )
                inner += 1
            if source.key_var:
                ttk.Label(
                    block,
                    text=f"Needs a free key in {source.key_var}.",
                    style="Hint.TLabel",
                    wraplength=WRAP,
                ).grid(row=inner, column=0, sticky="w", pady=(3, 0))
                inner += 1
            self._link(block, inner, source.terms)
        return int(card.grid_info()["row"]) + 1

    def _credit(self, page: ttk.Frame, row: int) -> int:
        """The line for a drawing, in a field somebody can take away.

        A selectable field rather than a label, and a Copy button beside it,
        because the whole point of writing the credits down is that the
        wording reaches a title block without being retyped.

        Wrapped over several lines rather than set in an entry box: the line
        is three hundred characters and an entry shows forty of them, so a
        person checking what they are about to paste would be reading it
        through a slot.
        """
        card = self._title(page, row, "The credit for a drawing")
        page, row = card, 0
        row = self._paragraph(
            page,
            row,
            "Every publisher above, each said once, in the wording they ask "
            "for. Put it in the title block or against the sheet's north "
            "point on anything drawn from a site analysis run.",
        )
        line = ttk.Frame(page)
        line.grid(row=row, column=0, sticky="ew", pady=(2, 0))
        line.columnconfigure(0, weight=1)
        row += 1

        self.credit = tk.Text(
            line,
            # Seven lines, which is what the credits come to at this width
            # with every publisher answering, the City of Sydney included. A
            # field a line short of its own text is worse than a scrollbar: it
            # looks complete and is not.
            height=7,
            wrap="word",
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            background=theme.SURFACE,
            foreground=theme.INK,
            padx=6,
            pady=5,
        )
        self.credit.insert("1.0", credit_line())
        # Disabled *after* the insert, or the insert is refused. A disabled
        # Text can still be selected and copied by hand, which is how half the
        # people who open this will take it; what it refuses is the typing.
        self.credit.configure(state="disabled")
        self.credit.grid(row=0, column=0, sticky="ew")
        self._copy_button = ttk.Button(line, text="Copy", command=self._copy, width=9)
        self._copy_button.grid(row=0, column=1, padx=(6, 0), sticky="n")
        return int(card.grid_info()["row"]) + 1

    # -- the small pieces --------------------------------------------------

    def _title(self, page: ttk.Frame, row: int, text: str) -> ttk.Frame:
        """A section's card, headed by its title the way a settings panel on
        a page is: the same rounded white card, sixteen pixels in from the
        page and ten apart, the title on its header band. Answers with the
        card; the section lays its rows inside it from nought."""
        head = theme.PANEL_HEAD
        card = ttk.Frame(page, style="BoxOff.TFrame", padding=(14, head + 10, 14, 12))
        card.grid(row=row, column=0, sticky="ew", padx=16, pady=(10 if row == 0 else 0, 10))
        card.columnconfigure(0, weight=1)
        # Placed in the padding, as the window places a panel's title: a ttk
        # frame tells Tk its padding is a border, and ``place`` otherwise
        # starts inside it.
        ttk.Label(card, text=text, style="BoxTitle.TLabel").place(
            bordermode="outside", x=14, y=2, height=head - 3, relwidth=1.0, width=-28
        )
        self._headings[text] = card
        return card

    def _paragraph(self, page: ttk.Frame, row: int, text: str, style: str = "TLabel") -> int:
        ttk.Label(page, text=text, wraplength=WRAP, justify="left", style=style).grid(
            row=row, column=0, sticky="w", pady=(0, 2)
        )
        return row + 1

    def _link(self, parent: ttk.Frame, row: int, url: str) -> None:
        """The terms, as an address that opens in a browser when clicked.

        The URL is shown rather than hidden behind a phrase: this is the one
        thing in the box somebody may need to pass on to a person who is not
        sitting at this machine, and "the terms" cannot be read down a phone.
        """
        link = ttk.Label(parent, text=url, style="Link.TLabel", cursor="hand2", wraplength=WRAP)
        link.grid(row=row, column=0, sticky="w", pady=(3, 0))
        # ``partial`` rather than a lambda with a default argument: the default
        # is how a lambda in a loop keeps the value it was made with, and it is
        # also what leaves the callback untypeable.
        link.bind("<Button-1>", partial(self._clicked, url))

    def _clicked(self, url: str, _event: object = None) -> None:
        self._open(url)

    def _open(self, url: str) -> None:
        """Hand the address to the browser, and never raise over it.

        A machine with no browser registered, or a locked-down profile, is not
        a reason for an info box to throw a traceback at somebody -- the
        address is on screen and can be read out or typed.
        """
        try:
            webbrowser.open(url)
        except (OSError, webbrowser.Error):  # pragma: no cover - see the docstring
            pass

    def _copy(self) -> None:
        """The credit onto the clipboard, and the button says that it went.

        Tk's clipboard is the X selection on Linux and a real clipboard on
        Windows; on both, a copy with no visible answer is indistinguishable
        from a button that does nothing.
        """
        try:
            self.clipboard_clear()
            self.clipboard_append(credit_line())
        except tk.TclError:  # pragma: no cover - no clipboard to be had
            self._copy_button.configure(text="Cannot")
            return
        self._copy_button.configure(text="Copied")
        self.after(1600, self._copy_said_nothing)

    def _copy_said_nothing(self) -> None:
        try:
            self._copy_button.configure(text="Copy")
        except tk.TclError:  # pragma: no cover - box closed while it waited
            pass

    def look_at(self, at: str) -> None:
        """Scroll to the part the button that opened this was asking about."""
        if at != SOURCES_SECTION:
            self._scroller.canvas.yview_moveto(0.0)
            return
        # Measured rather than guessed: the licence summary is six clauses
        # today and may be five tomorrow, and a hard-coded fraction would
        # then land on the wrong heading.
        self.update_idletasks()
        heading = self._headings.get(SOURCES_TITLE)
        tall = self._scroller.content.winfo_height()
        if heading is None or tall <= 1:  # pragma: no cover - nothing drawn yet
            return
        # A little above the card, so its edge comes with it and the section
        # does not read as having begun off the top of the pane.
        top = max(0.0, heading.winfo_y() - 10.0)
        self._scroller.canvas.yview_moveto(max(0.0, min(1.0, top / tall)))

    def _enter_key(self) -> None:
        """The licence box, to change the key this machine holds."""
        from sun_study.app import licence_box

        if licence_box.ask(self) is not None:
            self._show_standing()

    def _show_standing(self) -> None:
        found = licence.standing()
        self._holder.configure(text=found.describe())
        if found.online:
            self._check.grid()
        else:
            self._check.grid_remove()

    def _check_now(self) -> None:
        """Ask the licence service now, in the background, and say the answer."""
        import threading

        done: list[licence.Standing] = []
        asking = threading.Thread(
            target=lambda: done.append(licence.renew()), name="licence check", daemon=True
        )
        self._holder.configure(text="Checking the licence with the licence service…")
        self._check.configure(state="disabled")
        asking.start()

        def answered() -> None:
            if asking.is_alive():
                self._waiting = self.after(100, answered)
                return
            self._waiting = None
            self._check.configure(state="normal")
            found = done[0] if done else licence.standing()
            self._holder.configure(text=found.describe())

        self._waiting = self.after(100, answered)

    #: The look at a licence check that is due next, while one runs.
    _waiting: str | None = None

    def destroy(self) -> None:
        # Closed while a check runs: it finishes on its own, and keeps what
        # it gets; nothing is left to write into a closed box.
        if self._waiting is not None:
            self.after_cancel(self._waiting)
            self._waiting = None
        super().destroy()

    def _show_the_licence(self) -> None:
        """The whole text, in a window of its own.

        Shown here rather than handed to the operating system: the file has no
        extension, so a Windows machine answers a double-click with the "how
        do you want to open this" dialog, which is not an answer.
        """
        text = licence.full_text()
        if text is None:  # pragma: no cover - the button is hidden without it
            return
        window = tk.Toplevel(self)
        what = "licence terms" if licence.keys_required() else "licence"
        window.title(f"{PRODUCT} — {what}")
        window.transient(self)
        window.geometry("720x620")
        window.configure(background=theme.PAGE)
        frame = ttk.Frame(window, style="Page.TFrame", padding=PAD)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        face, size = theme.log_font()
        body = tk.Text(
            frame,
            wrap="word",
            font=(face, size),
            borderwidth=0,
            highlightthickness=0,
            background=theme.SURFACE,
            foreground=theme.BODY,
            padx=12,
            pady=10,
        )
        body.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(frame, orient="vertical", command=body.yview)
        bar.grid(row=0, column=1, sticky="ns")
        body.configure(yscrollcommand=bar.set)
        body.insert("1.0", text)
        # After the text, or the insert is refused.
        body.configure(state="disabled")
        window.bind("<Escape>", lambda _event: window.destroy())

    def _close(self) -> None:
        global _open
        _open = None
        self.destroy()
