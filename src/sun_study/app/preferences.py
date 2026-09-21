"""What a colleague set last time, kept for next time.

Half the fields in the window are a property of the *project* and are read
back out of Archicad every time it opens -- the layer that carries the
apartments, the masters, the subsets. The rest are a property of the
*practice*: the layer prefix that files the output inside the office's own
numbering, the living-room suffix, the Archicad wait a big job needs, which
studies this person ever runs. Those are the same on every project and every
day, and retyping them is both tedious and a way to get one of them subtly
wrong.

So they are written, on request, to one small JSON file beside the user's own
settings -- ``%APPDATA%`` then ``Loriini``, ``settings.json`` -- and read back
when the window opens. On request rather than on every change, because a
saved default nobody chose to save is worse than no saved default at all: the
next run would quietly use a setting typed once for one odd project.

Nothing here ever raises when the window opens. A settings file that has been
hand-edited into nonsense, or sits on a locked profile, or was written by a
later version with fields this one has never heard of, must leave the window
opening on its own defaults -- not refusing to open at all.

The one exception is a *preset*: the same file, written wherever somebody
asked for it and read back on request. A colleague who picked a file and
pressed Load wants to know why it did not load, so ``read`` says so, and the
window prints the reason rather than pretending nothing happened. Presets and
the saved defaults are one format on purpose -- a preset copied over
``settings.json`` is the defaults, and the defaults saved as a preset can be
sent to the next desk.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

#: The folder name under %APPDATA%, and the file in it. Named for the program
#: rather than for the product: everything the tool writes *into a project* is
#: "Sun Study", and this is the application's own state.
FOLDER = "Loriini"
FILE = "settings.json"

#: What a preset is saved as, and how the file dialogs describe it. Plain
#: ``.json`` rather than an extension of the program's own: the file is the
#: settings file, and a name that says so is one somebody can open in an
#: editor when they want to see what a colleague sent them.
PRESET_SUFFIX = ".json"
PRESET_TYPES: tuple[tuple[str, str], ...] = (("Loriini preset", "*.json"), ("Any file", "*.*"))


def folder() -> Path:
    """Where this user's settings live.

    ``%APPDATA%`` because that is where Windows keeps per-user application
    settings and it follows a roaming profile between machines. The home
    directory is the fallback for a developer on anything else, so the module
    can be exercised off Windows.
    """
    roaming = os.environ.get("APPDATA")
    return Path(roaming) / FOLDER if roaming else Path.home() / f".{FOLDER.casefold()}"


def path() -> Path:
    """The settings file itself, whether or not it exists yet."""
    return folder() / FILE


def presets_folder() -> Path:
    """Where the preset dialogs open.

    Not beside the defaults: ``%APPDATA%`` is hidden, and a preset exists to
    be found -- copied to a job folder, sent to the next desk. The user's
    Documents is where a person looks for a file they made, and nothing is
    created there until they save one.
    """
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def read(where: Path) -> dict[str, str | bool]:
    """The settings in one file.

    Raises ``OSError`` for a file that is not there or will not open, and
    ``ValueError`` for one that is not a settings file -- JSON that will not
    parse, text that is not text, or a list where a mapping should be. Both
    carry a sentence the window can print. Values that are neither a field's
    text nor a tick are dropped one by one rather than condemning the whole
    file, so a single bad line costs one setting.
    """
    try:
        found = json.loads(where.read_text(encoding="utf-8"))
    except UnicodeDecodeError as refused:
        raise ValueError("it is not a text file") from refused
    except json.JSONDecodeError as refused:
        raise ValueError(f"it is not a settings file (line {refused.lineno})") from refused
    if not isinstance(found, dict):
        raise ValueError("it is not a settings file (no settings in it)")
    return {str(name): value for name, value in found.items() if isinstance(value, str | bool)}


def write(where: Path, values: Mapping[str, str | bool]) -> Path:
    """Write these settings to one file, making the folder if it is missing.

    Raises ``OSError`` for a folder that will not take the file, which the
    window reports rather than raises: a preset that could not be written is
    a failure to save a convenience, not a failure to run a study.
    """
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(dict(values), indent=2, sort_keys=True), encoding="utf-8")
    return where


def load() -> dict[str, str | bool]:
    """What was saved as the defaults, or nothing at all.

    Every failure answers with an empty mapping, which the window reads as
    "no saved settings" and starts from its own defaults.
    """
    try:
        return read(path())
    except (OSError, ValueError):
        # OSError is the file that is not there or will not open;
        # ValueError is everything ``read`` refuses. Either way the window
        # opens on its own defaults rather than not at all.
        return {}


def save(values: Mapping[str, str | bool]) -> Path:
    """Write these as the defaults, and say where they went.

    The path is returned so the window can print it: a preference somebody
    cannot find is a preference they cannot delete, and "it remembers the
    wrong thing now" is otherwise unanswerable.
    """
    return write(path(), values)


def forget() -> bool:
    """Delete the saved settings. True if the file is now gone.

    A locked profile answers False rather than raising, like everything else
    here: by the time this is called the page has already been put back to its
    defaults, and a file that will not delete is worth reporting but not worth
    stopping for. Whether there was anything to delete is a separate question,
    asked of ``path`` by the caller that wants to say so.
    """
    try:
        path().unlink(missing_ok=True)
    except OSError:
        return False
    return True
