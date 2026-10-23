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

#: Where to write for a licence key, or for another copy of one: the
#: product's contact address, on its own domain.
SUPPORT_EMAIL = "hi@loriini.app"

#: The product's web site, on the same domain.
WEBSITE = "https://loriini.app"

#: The copyright line, kept beside the author for the same reason: the window,
#: the executable's file properties and every sheet must say the same thing.
#: Clause 2(e) of the licence requires that it not be removed from either the
#: software or its output.
COPYRIGHT = "Copyright (c) 2026 Sami Abdulnour and Zofia Kosova. All rights reserved."

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

#: The Archicad versions an add-on is built for. An add-on is compiled against
#: one major version and loads in no other, so the ``Archicad add-on``
#: workflows build one per version and the handover folder carries them all.
#: The program itself talks to any of them the same way.
ARCHICAD_VERSIONS = (26, 27, 28, 29, 30)

#: The add-on's platform half, as the workflow names its files: an .apx on
#: Windows, a .bundle on a Mac.
ADDON_PLATFORM, ADDON_SUFFIX = ("Mac", ".bundle") if sys.platform == "darwin" else ("Win", ".apx")


def addon_name(version: int) -> str:
    """The add-on for one Archicad version, without its suffix:
    ``LoriiniAddOn_AC27_Win``."""
    return f"LoriiniAddOn_AC{version}_{ADDON_PLATFORM}"


#: The add-on this machine installs, as every message that tells somebody to
#: install it names it, so the advice is about a file on their own screen.
#: The version is left for them to fill in: the one matching their Archicad.
#: Here for the same reason as ``STOP_FILE_VAR``: the window and the Archicad
#: adapter both say it and must not import each other to do so.
ADDON_FILE = f"LoriiniAddOn_AC<version>_{ADDON_PLATFORM}{ADDON_SUFFIX}"


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
