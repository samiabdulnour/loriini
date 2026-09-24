"""Fetch an Archicad API Development Kit and unpack it.

Only ever run by CI. The kit is a 200 MB licensed download from Graphisoft
that has no business in a public repository, and Graphisoft publish it as a
GitHub release asset, so the build fetches the exact version it needs and
throws it away afterwards.

Deliberately plain: the standard library only, no third-party HTTP client, so
it runs on a fresh runner before anything has been installed.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

#: The zip's record of the system that made a member. 3 is Unix, which is
#: what a zip made on a Mac says, and the only kind whose mode bits mean
#: anything to unpack.
MADE_ON_UNIX = 3

#: Finder's shadow copies of each file's extended attributes, one ``._name``
#: per file. The Mac kit carries a folder of them; nothing builds from them.
MAC_METADATA = "__MACOSX/"


def download_and_unzip(url: str, into: Path) -> None:
    """Put the contents of the zip at ``url`` inside ``into``.

    An existing folder is removed first. A half-unpacked kit from an
    interrupted run is the kind of thing that fails much later, in a linker
    error naming a module nobody has heard of.
    """
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)

    with TemporaryDirectory() as scratch:
        archive = Path(scratch) / "devkit.zip"
        print(f"Downloading {url}")
        urllib.request.urlretrieve(url, archive)
        print(f"Unpacking into {into}")
        with zipfile.ZipFile(archive) as bundle:
            if os.name == "nt":
                bundle.extractall(into)
            else:
                unpack(bundle, into)

    # The layout is checked here rather than trusted, because everything
    # downstream depends on it and the failure otherwise surfaces as a cmake
    # error about a path that means nothing to a reader.
    marker = into / "Support" / "Inc" / "ACAPinc.h"
    if not marker.exists():
        raise SystemExit(f"{marker} is missing, so this does not look like an API Development Kit.")
    print(f"Ready: {marker}")


def unpack(bundle: zipfile.ZipFile, into: Path) -> None:
    """Unpack every member as what it was: a link as a link, a tool as a tool.

    ``ZipFile.extractall`` writes a symbolic link out as a small file holding
    the path it pointed at, and drops every permission bit. The Windows kit
    has neither and never noticed. The Mac kit has both and needs both: 423
    links inside its frameworks -- ``GSRoot.framework/GSRoot`` is one, and
    the linker follows it to the library -- and ``Tools/OSX/ResConv``, the
    resource compiler, which does nothing without its execute bit. Tapir's
    own build gets the same result by calling ``unzip``; this keeps it in the
    standard library, and so testable anywhere.
    """
    root = into.resolve()
    for member in bundle.infolist():
        if member.filename.startswith(MAC_METADATA):
            continue
        target = into / member.filename
        _inside(root, target, member.filename)
        mode = member.external_attr >> 16 if member.create_system == MADE_ON_UNIX else 0
        if stat.S_ISLNK(mode):
            pointed = bundle.read(member).decode("utf-8")
            _inside(root, target.parent / pointed, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(pointed)
            continue
        written = Path(bundle.extract(member, into))
        if mode & 0o777 and not member.is_dir():
            written.chmod(mode & 0o777)


def _inside(root: Path, path: Path, name: str) -> None:
    """Refuse a member, or a link, that would land outside the kit's folder.

    The kit is Graphisoft's own release, so this is not expected to fire. It
    is here because a link is written where the member says and points where
    it says, and nothing else in the standard library checks either.
    """
    if not path.resolve().is_relative_to(root):
        raise SystemExit(f"{name} in the zip points outside {root}; refusing to unpack it.")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: download_and_unzip.py <url> <target folder>", file=sys.stderr)
        return 2
    download_and_unzip(argv[1], Path(argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
