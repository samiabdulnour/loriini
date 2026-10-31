"""Put a build on the website's download page.

    python3 scripts/site_download.py site/download/Loriini_Win.zip

Reads the zip the *Archicad add-on* workflow uploads as ``Loriini_Win`` --
``Loriini.exe``, one add-on per Archicad version, ``How to install.txt``
and ``LICENSE.txt`` -- and writes what it finds under *Download* on
``site/download.html``: the version and the day it was built, from the
install note inside; which Archicad versions, from the add-ons' names; the
size; and the SHA-256 of the file as it will be served. Nothing is typed by
hand, so the page cannot say one thing about the file and the file another.

The *Website* workflow runs this before every deploy (docs/website.md);
by hand it is the step between downloading the artifact and ``fly deploy``.
Standard library only, so it runs on a bare runner.
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
ADDON = re.compile(r"LoriiniAddOn_AC(\d+)_Win\.apx$")


@dataclass(frozen=True)
class Build:
    """What a download folder says about itself."""

    version: str
    built: str
    """The day, as the install note writes it: ``27 October 2026``."""
    first: int
    last: int
    """The Archicad versions the add-ons cover."""
    files: tuple[str, ...]
    size: int
    sha256: str

    @property
    def megabytes(self) -> str:
        return f"{round(self.size / 1_000_000)} MB"

    @property
    def versions(self) -> str:
        return f"{self.first} to {self.last}" if self.first != self.last else str(self.first)

    @property
    def contents(self) -> str:
        addons = sorted(name for name in self.files if ADDON.search(name))
        others = [name for name in self.files if name not in addons and name != "Loriini.exe"]
        if len(addons) > 1:
            found = f"one add-on per Archicad version ({addons[0]} to {addons[-1]})"
        else:
            found = ", ".join(addons)
        return ", ".join(["Loriini.exe", found, *sorted(others)])


def describe(path: Path) -> Build:
    """Read the folder's own account of itself out of the zip."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    with zipfile.ZipFile(path) as folder:
        names = tuple(sorted(info.filename for info in folder.infolist() if not info.is_dir()))
        if NOTE not in names:
            raise SystemExit(f"{path} carries no {NOTE}; is it the Loriini_Win artifact?")
        note = folder.read(NOTE).decode("utf-8")
    heading = re.match(r"Loriini (\S+) for Archicad", note)
    built = re.search(r"^Built on (\d+ \w+ \d{4})", note, re.MULTILINE)
    if heading is None or built is None:
        raise SystemExit(f"{NOTE} in {path} does not say which build it is.")
    numbers = sorted(int(ADDON.search(name).group(1)) for name in names if ADDON.search(name))  # type: ignore[union-attr]
    if not numbers:
        raise SystemExit(f"{path} carries no add-on.")
    return Build(
        version=heading.group(1),
        built=built.group(1),
        first=numbers[0],
        last=numbers[-1],
        files=names,
        size=path.stat().st_size,
        sha256=digest.hexdigest(),
    )


def rewrite(page: str, build: Build) -> str:
    """The page with the build's facts under *Download*."""
    fields = {
        "Version": f"{build.version}, built {build.built}",
        "Contents": build.contents,
        "Size": build.megabytes,
        "SHA-256": build.sha256,
    }
    for name, value in fields.items():
        page, found = re.subn(
            rf"(<dt>{re.escape(name)}</dt><dd>)[^<]*(</dd>)", rf"\g<1>{value}\g<2>", page, count=1
        )
        if found != 1:
            raise SystemExit(f"The page has no {name} line under Download.")
    page, found = re.subn(
        r"(Download Loriini for Windows, Archicad )[^<]*(</a>)",
        rf"\g<1>{build.versions}\g<2>",
        page,
        count=1,
    )
    if found != 1:
        raise SystemExit("The page has no Download button.")
    page, found = re.subn(
        r"(Download the current build of Loriini for Windows and Archicad )[^.\"]*",
        rf"\g<1>{build.versions}",
        page,
        count=1,
    )
    if found != 1:
        raise SystemExit("The page has no description.")
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("zip", type=Path, help="the Loriini_Win artifact, as GitHub serves it")
    parser.add_argument(
        "--page", type=Path, default=PAGE, help="the page to write; the site's download page"
    )
    arguments = parser.parse_args(argv)
    build = describe(arguments.zip)
    arguments.page.write_text(
        rewrite(arguments.page.read_text(encoding="utf-8"), build), encoding="utf-8"
    )
    facts = f"Loriini {build.version}, built {build.built}, Archicad {build.versions}"
    print(f"{arguments.page}: {facts}, {build.megabytes}, sha256 {build.sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
