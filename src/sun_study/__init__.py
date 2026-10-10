"""sun-study: direct sunlight hours from an Archicad model.

Layering, enforced by ``tests/unit/test_architecture.py``:

    archicad -> report -> ingest -> rules -> core

``core`` is pure geometry and astronomy: no I/O, no Archicad, no IFC, and
therefore fully testable without an Archicad licence. Everything that talks to
Archicad lives in the ``archicad`` package and nowhere else.
"""

import os
import sys
from pathlib import Path

from sun_study.disclaimer import DISCLAIMER, STATUS

__all__ = [
    "ADDON_FILE",
    "AUTHOR",
    "COPYRIGHT",
    "DISCLAIMER",
    "PRODUCT",
    "STATUS",
    "STOP_FILE_VAR",
    "__version__",
    "user_folder",
]
__version__ = "0.0.1"

#: Who wrote it. Carried into the window, the packaged executable's file
#: properties and every sheet the tool draws, from here, so the three cannot
#: drift apart -- the same reason the disclaimer has a module of its own.
AUTHOR = "Sami Abdulnour"
PRODUCT = "Loriini"

#: Where a licence key comes from, and where to write for another: the
#: mailbox the licence service sends from, on the product's own domain.
SUPPORT_EMAIL = "sami@loriini.app"

#: The copyright line, kept beside the author for the same reason: the window,
#: the executable's file properties and every sheet must say the same thing.
#: Clause 2(e) of the licence requires that it not be removed from either the
#: software or its output.
COPYRIGHT = "Copyright (c) 2026 Sami Abdulnour. All rights reserved."

#: Where a run is told to look for its stop request. The window writes the
#: file; the run watches for it and raises, so its ``finally`` blocks put the
#: project's layer state back.
#:
#: A file rather than a signal because the packaged app has no console, and a
#: console control event -- the only thing a Windows process can be *asked* to
#: stop with -- cannot be sent by a process that has none. The alternative is
#: ``TerminateProcess``, which runs nothing and leaves somebody's project
#: showing the export's layers. It lives here because the two halves that need
#: the name must not import each other: the window would pull in the whole
#: command line, numpy and all, to start up.
STOP_FILE_VAR = "SUN_STUDY_STOP_FILE"

#: The add-on this machine installs, by the file name the ``Archicad add-on``
#: workflow gives it: an .apx on Windows, a .bundle on a Mac. Every message
#: that tells somebody to install it names this, so the advice is about the
#: file on their own screen. Here for the same reason as ``STOP_FILE_VAR``:
#: the window and the Archicad adapter both say it and must not import each
#: other to do so.
ADDON_FILE = (
    "LoriiniAddOn_AC26_Mac.bundle" if sys.platform == "darwin" else "LoriiniAddOn_AC26_Win.apx"
)


def user_folder() -> Path:
    """This user's own folder for Loriini: the settings, the run logs, the
    licence key.

    ``%APPDATA%\\Loriini`` on Windows, because that is where Windows keeps a
    person's application settings and it follows a roaming profile from one
    machine to the next. A Mac keeps the same thing in
    ``~/Library/Application Support``, which a migrated or restored account
    carries across the same way. ``~/.loriini`` elsewhere, for a developer.
    Here rather than in the window's own settings module because the licence
    is read before any window exists, by the command line as well.

    ``APPDATA`` is asked first everywhere, a Mac included, although nothing
    there sets it: it is how the tests point the folder somewhere disposable,
    and they run on all three.
    """
    roaming = os.environ.get("APPDATA")
    if roaming:
        return Path(roaming) / PRODUCT
    # An else, not a fall-through: mypy reads the platform, and on a Mac a
    # line after this branch's return would be code it can never reach.
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / PRODUCT
    else:
        return Path.home() / f".{PRODUCT.casefold()}"
