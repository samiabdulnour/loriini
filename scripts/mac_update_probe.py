"""Temporary: which part of the About box keeps Tk's update() from returning on a Mac.

Each case runs in a process of its own with a time limit, so one hang does not
stop the others, and samples every thread's stack while it runs.
"""

from __future__ import annotations

import subprocess
import sys

PRELUDE = """
import faulthandler, sys, tkinter as tk
faulthandler.dump_traceback_later(6, repeat=True, exit=False)
from sun_study.app import about, theme, window
root = tk.Tk()
root.withdraw()
def said(box):
    print("mapped", box.winfo_ismapped(), "state", box.wm_state(),
          "root", root.wm_state(), file=sys.stderr, flush=True)
"""

CASES = {
    "bare root": "root.update()",
    "about, withdrawn root": "theme.apply(root); box = about.show(root); said(box); root.update()",
    "about, idletasks only": (
        "theme.apply(root); box = about.show(root); said(box); root.update_idletasks()"
    ),
    "about, root shown": (
        "root.deiconify(); theme.apply(root); box = about.show(root); said(box); root.update()"
    ),
    "about, no theme": "box = about.show(root); said(box); root.update()",
    "about, scroll bar left alone": (
        "window.Scroller._show_bar_if_needed = lambda self: None; "
        "theme.apply(root); box = about.show(root); said(box); root.update()"
    ),
    "plain toplevel, transient": (
        "top = tk.Toplevel(root); top.transient(root); said(top); root.update()"
    ),
}


def main() -> int:
    for name, body in CASES.items():
        code = PRELUDE + body + "\nprint('returned', flush=True)\n"
        try:
            done = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=25
            )
        except subprocess.TimeoutExpired as hung:
            err = hung.stderr.decode() if isinstance(hung.stderr, bytes) else hung.stderr or ""
            print(f"=== {name}: HUNG")
            print(err[-6000:])
            continue
        verdict = "returned" if "returned" in done.stdout else f"exit {done.returncode}"
        print(f"=== {name}: {verdict}")
        print(done.stderr[-1500:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
