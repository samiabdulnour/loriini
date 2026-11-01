"""scripts/site_download.py: the download page says what the zips say."""

from __future__ import annotations

import importlib
import zipfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

NOTE = """Loriini 0.0.1 for Archicad 26 to 30

Everything a workstation needs.

To update, close Archicad and replace both files.

Built on 27 October 2026 from windows at commit 3e814a3.
"""

MAC_NOTE = """Loriini 0.0.1 for Archicad 26 to 30 on a Mac

Everything a Mac needs.

Loriini.app needs an Apple silicon Mac on macOS 11.0 or later. The
add-on runs in Archicad on Apple silicon and Intel alike.

Built on 31 October 2026 from windows at commit 1ae5de7.
"""


@pytest.fixture
def site_download() -> Any:
    """The script, imported the way it is run: from its folder."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        return importlib.import_module("site_download")
    finally:
        sys.path.remove(str(ROOT / "scripts"))


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A Loriini_Win artifact as GitHub serves it, in little."""
    path = tmp_path / "Loriini_Win.zip"
    with zipfile.ZipFile(path, "w") as made:
        made.writestr("How to install.txt", NOTE)
        made.writestr("LICENSE.txt", "the terms")
        made.writestr("Loriini.exe", b"MZ" + bytes(2_000_000))
        for version in (26, 27, 30):
            made.writestr(f"LoriiniAddOn_AC{version}_Win.apx", bytes(1000))
    return path


@pytest.fixture
def mac_folder(tmp_path: Path) -> Path:
    """A Loriini_Mac folder as ditto zips it, in little: under a folder of
    its own name, the program and each add-on a folder of files."""
    path = tmp_path / "Loriini_Mac.zip"
    with zipfile.ZipFile(path, "w") as made:
        made.writestr("Loriini_Mac/How to install.txt", MAC_NOTE)
        made.writestr("Loriini_Mac/LICENSE.txt", "the terms")
        made.writestr("Loriini_Mac/Loriini.app/Contents/Info.plist", "<plist/>")
        made.writestr("Loriini_Mac/Loriini.app/Contents/MacOS/Loriini", bytes(3_000_000))
        for version in (26, 27, 30):
            bundle = f"Loriini_Mac/LoriiniAddOn_AC{version}_Mac.bundle/Contents"
            made.writestr(f"{bundle}/Info.plist", "<plist/>")
            made.writestr(f"{bundle}/MacOS/LoriiniAddOn_AC{version}_Mac", bytes(1000))
    return path


def _box(page: str, box: str) -> str:
    """One platform's box under *Download*, as the script finds it."""
    start = page.index(f'<div class="download-box" id="{box}">')
    return page[start : page.index("</div>", start)]


def test_the_zip_describes_itself(site_download: Any, folder: Path) -> None:
    build = site_download.describe(folder)
    assert build.platform is site_download.WINDOWS
    assert build.version == "0.0.1"
    assert build.built == "27 October 2026"
    assert (build.first, build.last) == (26, 30)
    assert build.versions == "26 to 30"
    assert build.size == folder.stat().st_size
    assert len(build.sha256) == 64
    assert build.contents == (
        "Loriini.exe, one add-on per Archicad version "
        "(LoriiniAddOn_AC26_Win.apx to LoriiniAddOn_AC30_Win.apx), How to install.txt, LICENSE.txt"
    )
    assert build.runs_on == "", "the Windows note names no Windows"


def test_a_mac_zip_describes_itself(site_download: Any, mac_folder: Path) -> None:
    """Read through the folder ditto puts everything under, with a program
    and add-ons that are folders themselves counted once each."""
    build = site_download.describe(mac_folder)
    assert build.platform is site_download.MACOS
    assert build.version == "0.0.1"
    assert build.built == "31 October 2026"
    assert (build.first, build.last) == (26, 30)
    assert build.runs_on == "An Apple silicon Mac on macOS 11 or later"
    assert build.contents == (
        "Loriini.app, one add-on per Archicad version "
        "(LoriiniAddOn_AC26_Mac.bundle to LoriiniAddOn_AC30_Mac.bundle), How to install.txt, LICENSE.txt"
    )
    assert build.size == mac_folder.stat().st_size


def test_a_zip_without_the_note_is_refused(site_download: Any, tmp_path: Path) -> None:
    path = tmp_path / "other.zip"
    with zipfile.ZipFile(path, "w") as made:
        made.writestr("readme.txt", "not a build")
    with pytest.raises(SystemExit, match=r"How to install\.txt"):
        site_download.describe(path)


def test_a_zip_without_a_program_is_refused(site_download: Any, tmp_path: Path) -> None:
    path = tmp_path / "other.zip"
    with zipfile.ZipFile(path, "w") as made:
        made.writestr("How to install.txt", NOTE)
    with pytest.raises(SystemExit, match=r"neither Loriini\.exe nor Loriini\.app"):
        site_download.describe(path)


def test_the_page_takes_the_facts(site_download: Any, folder: Path) -> None:
    """The committed page itself is rewritten, so the script's patterns and
    the page cannot drift apart; every figure in the box is the zip's; and
    the other platform's box is not touched."""
    build = site_download.describe(folder)
    page = (ROOT / "site" / "download.html").read_text(encoding="utf-8")
    written = site_download.rewrite(page, build)
    windows = _box(written, "windows")
    assert "<dt>Version</dt><dd>0.0.1, built 27 October 2026</dd>" in windows
    assert f"<dt>SHA-256</dt><dd>{build.sha256}</dd>" in windows
    assert "<dt>Size</dt><dd>2 MB</dd>" in windows
    assert "<dt>Runs on</dt><dd>Windows 10 or 11</dd>" in windows, "the page's own words, kept"
    assert "Download Loriini for Windows, Archicad 26 to 30</a>" in windows
    assert "for Windows or macOS, with Archicad 26 to 30." in written
    assert _box(written, "macos") == _box(page, "macos")
    # Written twice, it says the same thing: nothing accumulates.
    assert site_download.rewrite(written, build) == written


def test_a_mac_build_fills_its_own_box(site_download: Any, mac_folder: Path) -> None:
    build = site_download.describe(mac_folder)
    page = (ROOT / "site" / "download.html").read_text(encoding="utf-8")
    written = site_download.rewrite(page, build)
    macos = _box(written, "macos")
    assert "<dt>Version</dt><dd>0.0.1, built 31 October 2026</dd>" in macos
    assert "<dt>Runs on</dt><dd>An Apple silicon Mac on macOS 11 or later</dd>" in macos
    assert f"<dt>SHA-256</dt><dd>{build.sha256}</dd>" in macos
    assert "<dt>Size</dt><dd>3 MB</dd>" in macos
    assert "Download Loriini for macOS, Archicad 26 to 30</a>" in macos
    assert _box(written, "windows") == _box(page, "windows")
    assert site_download.rewrite(written, build) == written


def test_the_sizes_are_whole_megabytes(site_download: Any) -> None:
    build = site_download.Build(
        site_download.WINDOWS,
        "0.0.1",
        "1 May 2026",
        26,
        26,
        ("Loriini.exe",),
        82_871_823,
        "0" * 64,
    )
    assert build.megabytes == "83 MB"
    assert build.versions == "26"
