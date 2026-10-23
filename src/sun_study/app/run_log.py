"""Every run's transcript, kept on disk as it is written.

The window shows one line of a run -- the newest -- and used to keep the rest
in memory until the next run cleared it. A study that failed forty minutes in
on a larger model then had its whole story in a list nobody could open, and
the one line left on screen said ``[the study stopped, exit code 1]``. Reading
that failure is the first step of roadmap R1, and the transcript is what makes
it readable -- in an assisted session, or afterwards, sent by a colleague.

So each run is written to a file line by line and flushed as it goes, and a
run that takes the process down with it still leaves everything up to the
moment it went. The files are in the per-user folder beside the settings,
``Logs``, named for when the run started and what it ran; the newest
``KEEP`` are kept and older ones deleted, so the folder is a recent history
rather than a landfill.

Nothing here may stop a run. A folder that will not take a file, a disk that
fills mid-run: the log goes quiet and the study carries on, because a missing
transcript costs a diagnosis and a refused run costs the afternoon.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from sun_study import __version__, stamp
from sun_study.app import preferences
from sun_study.core.resources import physical_memory_bytes, size_text

__all__ = ["KEEP", "LOG_SUFFIX", "RunLog", "logs_folder", "open_file", "prune"]

#: How many transcripts are kept. A month of a busy desk's runs.
KEEP = 60

LOG_SUFFIX = ".log"


def logs_folder() -> Path:
    """Where the transcripts go: ``Logs`` beside the settings file."""
    return preferences.folder() / "Logs"


def _file_name(started: dt.datetime, studies: Sequence[str]) -> str:
    """``2026-09-29 1432 shadow diagram, sun views.log``: sortable by name,
    and saying what ran without being opened."""
    what = ", ".join(studies) or "run"
    tidy = re.sub(r"[^\w ,.-]+", "", what).strip()[:80] or "run"
    return f"{started:%Y-%m-%d %H%M%S} {tidy}{LOG_SUFFIX}"


class RunLog:
    """One run's transcript, open for writing."""

    def __init__(self, path: Path, handle: TextIO) -> None:
        self.path = path
        self._handle: TextIO | None = handle

    @classmethod
    def start(
        cls,
        studies: Sequence[str],
        *,
        folder: Path | None = None,
        now: dt.datetime | None = None,
    ) -> RunLog | None:
        """A new transcript with its head written, or ``None`` if the folder
        will not take one. Older transcripts past ``KEEP`` are pruned."""
        started = now or dt.datetime.now()
        home = folder or logs_folder()
        try:
            home.mkdir(parents=True, exist_ok=True)
            path = home / _file_name(started, studies)
            handle = path.open("w", encoding="utf-8", newline="\n")
        except OSError:
            return None
        log = cls(path, handle)
        for line in _head(started, studies):
            log.write(line)
        prune(home, keep=KEEP, besides=path)
        return log

    @property
    def open(self) -> bool:
        return self._handle is not None

    def write(self, line: str) -> None:
        """Append one line and flush it, so a crash loses nothing written."""
        if self._handle is None:
            return
        try:
            self._handle.write(line.rstrip("\n") + "\n")
            self._handle.flush()
        except OSError:
            self.close()

    def close(self) -> None:
        if self._handle is None:
            return
        try:
            self._handle.close()
        except OSError:
            pass
        self._handle = None


def _head(started: dt.datetime, studies: Sequence[str]) -> list[str]:
    """What the transcript opens with: which build, on what, when, and what
    was asked for. The questions every diagnosis starts by asking.

    Which build means the commit, not just the version: every prototype
    build says 0.0.1, and the first question a failure in a packaged run
    raises is whether the fix for it is already in the source. Without the
    hash that was once answered by matching traceback line numbers against
    old commits."""
    frozen = "packaged" if getattr(sys, "frozen", False) else "from source"
    built = stamp.commit()
    build = f"{frozen}, commit {built}" if built else frozen
    memory = physical_memory_bytes()
    return [
        f"Loriini {__version__} ({build}), Python {platform.python_version()}, "
        f"{platform.platform()}",
        f"memory: {size_text(memory)} on this machine" if memory else "memory: not reported",
        f"started {started:%Y-%m-%d %H:%M:%S}: {', '.join(studies) or 'nothing'}",
        "",
    ]


def prune(folder: Path, *, keep: int = KEEP, besides: Path | None = None) -> int:
    """Delete all but the newest ``keep`` transcripts. Returns how many went.

    Newest by name, which starts with the time the run started; ``besides``
    is the one being written, never deleted whatever its name sorts as.
    """
    try:
        found = sorted(
            (p for p in folder.glob(f"*{LOG_SUFFIX}") if p.is_file() and p != besides),
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return 0
    gone = 0
    for old in found[max(keep - (1 if besides else 0), 0) :]:
        try:
            old.unlink()
            gone += 1
        except OSError:
            pass
    return gone


def open_file(path: Path) -> bool:
    """Open a file the way double-clicking it would. False if it would not."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        return False
    return True
