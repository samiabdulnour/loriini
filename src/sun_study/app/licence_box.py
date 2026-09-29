"""The box a licence key is pasted into (roadmap R5, D124).

A build that takes licence keys opens this before the window, the first time
it is started and any time after that the key held cannot be used -- none
yet, one past its last day, one damaged -- and the info box opens it again to
change the key. It is the whole of what a buyer does with the email: paste,
read the line underneath, press the button.

The line underneath is the point of it. It reads the key as it is pasted, so
the buyer sees before pressing anything whether it is whole and whose it is:
*licence 0042, Fuse Architects, 12 seats, until 28 September 2027* -- or, in
red, the sentence that says what to do instead. A key cut short by a mail
client says "copy it again", not "invalid", which is the difference between a
second paste and a phone call (``licence_key``).
"""

from __future__ import annotations

import datetime as dt
import tkinter as tk
from tkinter import ttk

from sun_study import AUTHOR, PRODUCT, licence
from sun_study.app import theme
from sun_study.licence_key import KeyRefusedError, LicenceKey, read

__all__ = ["LicenceBox", "ask"]

PAD = theme.PAD

#: What the line under the key says before anything is pasted.
WAITING = "Paste the key from your licence email: all of it, from LORIINI to the last group."


class LicenceBox(tk.Toplevel):
    """Paste a key, see what it is, keep it."""

    def __init__(self, parent: tk.Misc, *, first: bool) -> None:
        super().__init__(parent)
        self.title(f"{PRODUCT} licence")
        self.configure(background=theme.SURFACE)
        self.resizable(False, False)
        if parent.winfo_viewable():
            self.transient(parent.winfo_toplevel())
        #: The key kept, once one is.
        self.result: LicenceKey | None = None

        outer = ttk.Frame(self, padding=(PAD, PAD, PAD, PAD))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text="Enter your licence key", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        found = licence.standing()
        opening = (
            f"{PRODUCT} needs a licence key to open a project. Keys come by email with "
            f"the subscription, a new one each time it renews; {AUTHOR} can send one again."
            if first
            else found.describe()
        )
        if first and found.problem and found.problem != licence.NO_KEY:
            opening = found.problem
        ttk.Label(outer, text=opening, wraplength=520, justify="left").grid(
            row=1, column=0, sticky="w", pady=(4, 10)
        )

        face, size = theme.log_font()
        self.text = tk.Text(
            outer, width=64, height=6, wrap="char", font=(face, size), undo=True, padx=8, pady=6
        )
        self.text.grid(row=2, column=0, sticky="ew")
        self.text.bind("<<Modified>>", self._changed)

        self.says = ttk.Label(
            outer, text=WAITING, wraplength=520, justify="left", style="Hint.TLabel"
        )
        self.says.grid(row=3, column=0, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.grid(row=4, column=0, sticky="e", pady=(PAD, 0))
        self.use = ttk.Button(buttons, text="Use this key", command=self._use, state="disabled")
        self.use.grid(row=0, column=0, padx=(0, 6))
        ttk.Button(
            buttons, text="Quit" if first else "Cancel", command=self.destroy, width=10
        ).grid(row=0, column=1)

        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.text.focus_set()

    def _pasted(self) -> str:
        return self.text.get("1.0", "end").strip()

    def _changed(self, _event: object = None) -> None:
        """Read the key as it stands, and say what it is."""
        self.text.edit_modified(False)
        self.says.configure(text=self.verdict(), style=self._style)
        self.use.configure(state="normal" if self._ready else "disabled")

    #: Set by ``verdict``: whether the key would be kept, and how to say so.
    _ready = False
    _style = "Hint.TLabel"

    def verdict(self) -> str:
        """What the key pasted so far is, in a sentence."""
        pasted = self._pasted()
        self._ready, self._style = False, "Hint.TLabel"
        if not pasted:
            return WAITING
        public = licence.public_key()
        if public is None:  # pragma: no cover - the box is only opened by a keyed build
            return "This build takes no licence keys."
        try:
            key = read(pasted, public)
        except KeyRefusedError as refused:
            self._style = "Refused.TLabel"
            return str(refused)
        if not key.good_on(dt.date.today()):
            self._style = "Refused.TLabel"
            return f"This key ended on {key.expires.day} {key.expires:%B %Y}: {key.describe()}."
        self._ready = True
        return f"This is {key.describe()}."

    def _use(self) -> None:
        try:
            self.result = licence.install(self._pasted())
        except KeyRefusedError as refused:
            self.says.configure(text=str(refused), style="Refused.TLabel")
            return
        self.destroy()


def ask(parent: tk.Misc, *, first: bool = False) -> LicenceKey | None:
    """Open the box and wait for it. The key kept, or ``None`` if it was closed
    without one."""
    theme.apply(parent)
    box = LicenceBox(parent, first=first)
    box.grab_set()
    parent.wait_window(box)
    return box.result
