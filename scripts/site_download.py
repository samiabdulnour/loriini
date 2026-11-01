"""Put a build on the website's download page.

    python3 scripts/site_download.py site/download/Loriini_Win.zip
    python3 scripts/site_download.py site/download/Loriini_Mac.zip

Reads a folder one of the add-on workflows uploads -- ``Loriini_Win`` from
*Archicad add-on*: ``Loriini.exe``, one add-on per Archicad version,
``How to install.txt`` and ``LICENSE.txt``, zipped by GitHub as it serves
an artifact; or ``Loriini_Mac`` from *Archicad add-on (macOS)*:
``Loriini.app`` and the ``.bundle`` add-ons beside the same two files,
zipped by ditto under a folder of that name -- and writes what it finds in
that build's box under *Download* on ``site/download.html``: the version
and the day it was built, from the install note inside; which Archicad
versions, from the add-ons' names; on a Mac, which Macs, from the note's
own line; the size; and the SHA-256 of the file as it will be served.
Nothing is typed by hand, so the page cannot say one thing about the file
and the file another. The other platform's box is left as it is.

The *Website* workflow runs this before every deploy, once for each build
(docs/website.md); by hand it is the step between downloading the artifact
and ``fly deploy``. Standard library only, so it runs on a bare runner.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "download.html"
NOTE = "How to install.txt"


@dataclass(frozen=True)
class Platform:
    """One of the two folders, and its box on the page."""

    name: str
    box: str
    """The ``id`` of its box under *Download*."""
    program: str
    addon: re.Pattern[str]
    """An add-on's name, with the Archicad version as its group."""


WINDOWS = Platform(
    "Windows", "windows", "Loriini.exe", re.compile(r"^LoriiniAddOn_AC(\d+)_Win\.apx$")
)
MACOS = Platform("macOS", "macos", "Loriini.app", re.compile(r"^LoriiniAddOn_AC(\d+)_Mac\.bundle$"))
PLATFORMS = (WINDOWS, MACOS)


@dataclass(frozen=True)
class Build:
    """What a download folder says about itself."""

    platform: Platform
    version: str
    built: str
    """The day, as the install note writes it: ``27 October 2026``."""
    first: int
    last: int
    """The Archicad versions the add-ons cover."""
    files: tuple[str, ...]
    """What the folder holds. A program or an add-on that is a folder itself counts once."""
    size: int
    sha256: str
    oldest_macos: str = ""
    """On a Mac, the oldest macOS the note says the program needs; otherwise empty."""

    @property
    def megabytes(self) -> str:
        return f"{round(self.size / 1_000_000)} MB"

    @property
    def versions(self) -> str:
        return f"{self.first} to {self.last}" if self.first != self.last else str(self.first)

    @property
    def contents(self) -> str:
        addons = sorted(name for name in self.files if self.platform.addon.match(name))
        others = [
            name for name in self.files if name not in addons and name != self.platform.program
        ]
        if len(addons) > 1:
            found = f"one add-on per Archicad version ({addons[0]} to {addons[-1]})"
        else:
            found = ", ".join(addons)
        return ", ".join([self.platform.program, found, *sorted(others)])

    @property
    def runs_on(self) -> str:
        """Which computers, where the folder itself says so. A Mac's note
        names the oldest macOS, and the program is built for Apple silicon
        (docs/macos.md). The Windows note names no Windows, so that box's
        line is the page's own words and is left alone."""
        if self.platform is MACOS:
            return f"An Apple silicon Mac on macOS {self.oldest_macos} or later"
        return ""


def _folder(entries: list[str]) -> str:
    """The one folder every entry is in, slash included, or nothing: ditto
    zips a folder under its name, GitHub zips a folder's files."""
    tops = {name.split("/", 1)[0] for name in entries}
    if len(tops) == 1 and all("/" in name for name in entries):
        return f"{tops.pop()}/"
    return ""


def describe(path: Path) -> Build:
    """Read the folder's own account of itself out of the zip."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    with zipfile.ZipFile(path) as folder:
        entries = [
            info.filename
            for info in folder.infolist()
            if not info.is_dir() and not info.filename.startswith("__MACOSX/")
        ]
        inside = _folder(entries)
        names = tuple(sorted({name[len(inside) :].split("/", 1)[0] for name in entries}))
        if NOTE not in names:
            raise SystemExit(
                f"{path} carries no {NOTE}; is it a Loriini_Win or Loriini_Mac artifact?"
            )
        note = folder.read(inside + NOTE).decode("utf-8")
    platform = next((each for each in PLATFORMS if each.program in names), None)
    if platform is None:
        raise SystemExit(f"{path} carries neither {WINDOWS.program} nor {MACOS.program}.")
    heading = re.match(r"Loriini (\S+) for Archicad", note)
    built = re.search(r"^Built on (\d+ \w+ \d{4})", note, re.MULTILINE)
    if heading is None or built is None:
        raise SystemExit(f"{NOTE} in {path} does not say which build it is.")
    numbers = sorted(int(found.group(1)) for name in names if (found := platform.addon.match(name)))
    if not numbers:
        raise SystemExit(f"{path} carries no add-on.")
    oldest = ""
    if platform is MACOS:
        macos = re.search(r"needs an Apple silicon Mac on macOS (\d+(?:\.\d+)*) or later", note)
        if macos is None:
            raise SystemExit(f"{NOTE} in {path} does not say which macOS the program needs.")
        oldest = macos.group(1).removesuffix(".0")
    return Build(
        platform=platform,
        version=heading.group(1),
        built=built.group(1),
        first=numbers[0],
        last=numbers[-1],
        files=names,
        size=path.stat().st_size,
        sha256=digest.hexdigest(),
        oldest_macos=oldest,
    )


def rewrite(page: str, build: Build) -> str:
    """The page with the build's facts in its own box under *Download*."""
    opening = f'<div class="download-box" id="{build.platform.box}">'
    start = page.find(opening)
    if start < 0:
        raise SystemExit(f"The page has no {build.platform.name} box under Download.")
    end = page.find("</div>", start)  # nothing inside a box is a div
    box = page[start:end]
    fields = {
        "Version": f"{build.version}, built {build.built}",
        "Contents": build.contents,
        "Size": build.megabytes,
        "SHA-256": build.sha256,
    }
    if build.runs_on:
        fields["Runs on"] = build.runs_on
    for name, value in fields.items():
        box, found = re.subn(
            rf"(<dt>{re.escape(name)}</dt><dd>)[^<]*(</dd>)", rf"\g<1>{value}\g<2>", box, count=1
        )
        if found != 1:
            raise SystemExit(f"The {build.platform.name} box has no {name} line.")
    box, found = re.subn(
        rf"(Download Loriini for {build.platform.name}, Archicad )[^<]*(</a>)",
        rf"\g<1>{build.versions}\g<2>",
        box,
        count=1,
    )
    if found != 1:
        raise SystemExit(f"The {build.platform.name} box has no Download button.")
    page = page[:start] + box + page[end:]
    # Both folders are built from the one list of Archicad versions, so either
    # build's range is the page's.
    page, found = re.subn(
        r"(Download the current build of Loriini for Windows or macOS, with Archicad )[^.\"]*",
        rf"\g<1>{build.versions}",
        page,
        count=1,
    )
    if found != 1:
        raise SystemExit("The page has no description.")
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument(
        "zip", type=Path, help="the Loriini_Win or Loriini_Mac folder, zipped as the site serves it"
    )
    parser.add_argument(
        "--page", type=Path, default=PAGE, help="the page to write; the site's download page"
    )
    arguments = parser.parse_args(argv)
    build = describe(arguments.zip)
    arguments.page.write_text(
        rewrite(arguments.page.read_text(encoding="utf-8"), build), encoding="utf-8"
    )
    facts = (
        f"Loriini {build.version} for {build.platform.name}, built {build.built}, "
        f"Archicad {build.versions}"
    )
    if build.runs_on:
        facts += f", {build.runs_on}"
    print(f"{arguments.page}: {facts}, {build.megabytes}, sha256 {build.sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
