"""Which commit this program was built from.

The version number does not tell builds apart: every prototype build says
0.0.1, so a run log from a machine with last week's Loriini.app reads
exactly like one from today's. That is how an October run failed on a
certificate problem the source had fixed six days earlier, and nothing in
the log said the build predated the fix -- the diagnosis came down to
matching traceback line numbers against old commits. The commit hash is the
one short line that settles it at a glance.

A packaged program has no repository to ask, so Loriini.spec asks git at
build time and carries the answer into the bundle as ``build_stamp.txt``;
a checkout asks git directly. Either way there may be no answer -- a build
made outside a checkout, a source tree downloaded without git -- and that
is not an error: the run log then opens with the version alone.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__ = ["STAMP", "commit"]

#: The file Loriini.spec writes the hash into, at the root of the bundle --
#: beside the LICENSE, found the same way (``sun_study.licence.file``).
STAMP = "build_stamp.txt"


def commit() -> str | None:
    """The short hash of the commit this is running from, or ``None``."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled is not None:
        try:
            line = (Path(bundled) / STAMP).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return line or None
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        # Installed as a package rather than run from a checkout. Asking git
        # here would answer for whatever repository happens to enclose
        # site-packages, which is nobody's build.
        return None
    try:
        asked = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # pragma: no cover - a checkout on a machine without git
        return None
    line = asked.stdout.strip()
    return line if asked.returncode == 0 and line else None
