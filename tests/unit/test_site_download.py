"""scripts/site_download.py: the download page says what the zip says."""

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


def test_the_zip_describes_itself(site_download: Any, folder: Path) -> None:
    build = site_download.describe(folder)
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


def test_a_zip_without_the_note_is_refused(site_download: Any, tmp_path: Path) -> None:
    path = tmp_path / "other.zip"
    with zipfile.ZipFile(path, "w") as made:
        made.writestr("readme.txt", "not a build")
    with pytest.raises(SystemExit, match=r"How to install\.txt"):
        site_download.describe(path)


def test_the_page_takes_the_facts(site_download: Any, folder: Path) -> None:
    """The committed page itself is rewritten, so the script's patterns and
    the page cannot drift apart; and every figure on it is the zip's."""
    build = site_download.describe(folder)
    page = (ROOT / "site" / "download.html").read_text(encoding="utf-8")
    written = site_download.rewrite(page, build)
    assert "<dt>Version</dt><dd>0.0.1, built 27 October 2026</dd>" in written
    assert f"<dt>SHA-256</dt><dd>{build.sha256}</dd>" in written
    assert "<dt>Size</dt><dd>2 MB</dd>" in written
    assert "Download Loriini for Windows, Archicad 26 to 30</a>" in written
    assert "for Windows and Archicad 26 to 30." in written
    # Written twice, it says the same thing: nothing accumulates.
    assert site_download.rewrite(written, build) == written


def test_the_sizes_are_whole_megabytes(site_download: Any) -> None:
    build = site_download.Build(
        "0.0.1", "1 May 2026", 26, 26, ("Loriini.exe",), 82_871_823, "0" * 64
    )
    assert build.megabytes == "83 MB"
    assert build.versions == "26"
