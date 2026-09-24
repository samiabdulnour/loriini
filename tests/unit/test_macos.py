"""The Mac version's own answers, checked on every platform.

The macOS branch changes a handful of things, each only where a Mac differs:
where the settings live, which add-on file the advice names, how the add-on's
kit is unpacked, and how the Mac program is built and handed over. Each turns
on the platform, so each is exercised here by telling the code it is on a
Mac -- and ci-macos.yml then runs the same file on one.

The window's half, which needs Tk, is test_macos_window.
"""

from __future__ import annotations

import datetime as dt
import importlib
import importlib.util
import os
import stat
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from sun_study import ADDON_FILE
from sun_study.app import preferences
from sun_study.archicad import connection

ROOT = Path(__file__).resolve().parents[2]
KIT_SCRIPT = ROOT / "archicad-addon" / "Tools" / "download_and_unzip.py"


def _home(monkeypatch: pytest.MonkeyPatch, where: Path) -> None:
    """Point the home folder somewhere disposable, on every platform.

    Not by HOME: Windows reads USERPROFILE, and a test that set HOME would pass
    on two platforms and read the real profile on the third.
    """
    monkeypatch.setattr(Path, "home", lambda: where)


# -- where the settings live ------------------------------------------------


def test_a_mac_keeps_the_settings_in_application_support(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Where every Mac program keeps its own, and where a migrated account
    takes them -- not a dot-folder in the home folder, which is the fallback
    for a platform with no convention."""
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    _home(monkeypatch, tmp_path)

    expected = tmp_path / "Library" / "Application Support" / "Loriini"
    assert preferences.folder() == expected
    assert preferences.path() == expected / "settings.json"


def test_appdata_is_still_asked_first_on_a_mac(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Nothing on a Mac sets it, and the tests set it everywhere: it is how the
    window's own tests keep their saved settings out of the developer's."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")

    assert preferences.folder() == tmp_path / "Loriini"


def test_off_both_the_home_folder_is_the_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    _home(monkeypatch, tmp_path)

    assert preferences.folder() == tmp_path / ".loriini"


# -- the add-on the advice names ---------------------------------------------


def test_the_install_advice_names_this_machines_add_on() -> None:
    """A colleague told to install an .apx on a Mac goes looking for a file
    that will never load there."""
    expected = (
        "LoriiniAddOn_AC26_Mac.bundle" if sys.platform == "darwin" else "LoriiniAddOn_AC26_Win.apx"
    )
    assert expected == ADDON_FILE
    assert ADDON_FILE in connection.INSTALL_LORIINI


# -- the Mac kit, unpacked as what it is --------------------------------------


def _kit_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("download_and_unzip", KIT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _member(name: str, mode: int, *, unix: bool = True) -> zipfile.ZipInfo:
    """A zip entry as a Mac's zip records one: made on Unix, mode in the top
    sixteen bits of the external attributes."""
    info = zipfile.ZipInfo(name)
    # Set either way: ZipInfo takes the platform the test runs on as its
    # default, and a member from a PC has to say it came from one.
    info.create_system = 3 if unix else 0
    if unix:
        info.external_attr = mode << 16
    return info


posix_only = pytest.mark.skipif(
    os.name == "nt",
    reason="the Windows kit has no links, and Windows unpacks with extractall",
)


@posix_only
def test_the_mac_kit_unpacks_with_its_links_and_its_tools(tmp_path: Path) -> None:
    """The two things zipfile drops, and a Mac kit cannot build without: a
    framework's links, which the linker follows to the library, and the
    resource compiler's execute bit."""
    archive = tmp_path / "kit.zip"
    library = b"\xcf\xfa\xed\xfe the library itself"
    with zipfile.ZipFile(archive, "w") as kit:
        kit.writestr(_member("Support/Tools/OSX/ResConv", stat.S_IFREG | 0o755), b"tool")
        kit.writestr(
            _member("Support/Frameworks/GSRoot.framework/Versions/A/GSRoot", stat.S_IFREG | 0o644),
            library,
        )
        kit.writestr(
            _member("Support/Frameworks/GSRoot.framework/Versions/Current", stat.S_IFLNK | 0o755),
            "A",
        )
        kit.writestr(
            _member("Support/Frameworks/GSRoot.framework/GSRoot", stat.S_IFLNK | 0o755),
            "Versions/Current/GSRoot",
        )
        kit.writestr(_member("__MACOSX/Support/Tools/OSX/._ResConv", stat.S_IFREG | 0o644), b"")
        kit.writestr(_member("Support/Inc/ACAPinc.h", 0, unix=False), b"// from a PC")

    into = tmp_path / "kit"
    into.mkdir()
    with zipfile.ZipFile(archive) as kit:
        _kit_script().unpack(kit, into)

    link = into / "Support" / "Frameworks" / "GSRoot.framework" / "GSRoot"
    assert link.is_symlink()
    assert link.read_bytes() == library
    resconv = into / "Support" / "Tools" / "OSX" / "ResConv"
    assert resconv.stat().st_mode & 0o111, "the resource compiler lost its execute bit"
    assert not (into / "__MACOSX").exists(), "Finder's metadata is not part of the kit"
    assert (into / "Support" / "Inc" / "ACAPinc.h").read_bytes() == b"// from a PC"


@posix_only
def test_a_link_out_of_the_kit_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "kit.zip"
    with zipfile.ZipFile(archive, "w") as kit:
        kit.writestr(_member("Support/elsewhere", stat.S_IFLNK | 0o755), "../../../outside")

    into = tmp_path / "kit"
    into.mkdir()
    with zipfile.ZipFile(archive) as kit, pytest.raises(SystemExit, match="outside"):
        _kit_script().unpack(kit, into)
    assert not (into / "Support" / "elsewhere").is_symlink()


@posix_only
def test_a_member_out_of_the_kit_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "kit.zip"
    with zipfile.ZipFile(archive, "w") as kit:
        kit.writestr(_member("../escaped.txt", stat.S_IFREG | 0o644), b"no")

    into = tmp_path / "kit"
    into.mkdir()
    with zipfile.ZipFile(archive) as kit, pytest.raises(SystemExit, match="outside"):
        _kit_script().unpack(kit, into)
    assert not (tmp_path / "escaped.txt").exists()


# -- the Mac program's recipe --------------------------------------------------


def test_the_mac_build_takes_its_collection_from_the_pcs() -> None:
    """Loriini-macOS.spec runs Loriini.spec up to the line where the PC's
    executable is built, so what is collected and trimmed is written once.
    That line has to be there, once, for it to find -- and the names the Mac
    spec goes on to use have to be made before it."""
    pc = (ROOT / "Loriini.spec").read_text(encoding="utf-8")
    mac = (ROOT / "Loriini-macOS.spec").read_text(encoding="utf-8")

    marker = "\npyz = PYZ(a.pure)"
    assert pc.count(marker) == 1, "Loriini.spec must build its PYZ exactly once, on its own line"
    assert repr(marker) in mac, "Loriini-macOS.spec no longer looks for the PC spec's PYZ line"

    collection = pc.partition(marker)[0]
    for made in ("ROOT = ", "a = Analysis("):
        assert made in collection, f"Loriini-macOS.spec needs {made!r} from Loriini.spec"


def test_the_mac_icon_is_an_icns() -> None:
    """What the Finder and the Dock read. The .ico beside it means nothing to
    a Mac, and PyInstaller would otherwise quietly fall back to its own."""
    icon = ROOT / "assets" / "loriini.icns"
    assert icon.read_bytes()[:4] == b"icns"


# -- the Mac handover folder ---------------------------------------------------


@pytest.fixture
def mac_build(monkeypatch: pytest.MonkeyPatch) -> Any:
    """scripts/build_app_macos.py, imported the way it is run: from its folder,
    beside the build_app.py it takes the shared pieces from."""
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("build_app_macos")


def test_the_mac_install_note_names_the_mac_files_and_the_mac_step(mac_build: Any) -> None:
    note = mac_build.install_note((11, 0), today=dt.date(2026, 9, 24))

    for named in ("Loriini.app", "LoriiniAddOn_AC26_Mac.bundle", "LICENSE.txt"):
        assert named in note
    assert ".exe" not in note and ".apx" not in note
    # The step a PC does not have: an unsigned program is held back until the
    # quarantine is taken off, and the add-on with it.
    assert "xattr -dr com.apple.quarantine" in note
    assert "macOS 11.0 or later" in note
    assert "Built on 24 September 2026" in note


def test_the_install_note_says_so_when_the_program_needs_a_newer_mac(mac_build: Any) -> None:
    assert "macOS 14.0 or later" in mac_build.install_note((14, 0))


def _bundle(where: Path) -> Path:
    bundle = where / "LoriiniAddOn_AC26_Mac.bundle"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    (bundle / "Contents" / "Info.plist").write_text("<plist/>", encoding="utf-8")
    (bundle / "Contents" / "MacOS" / "LoriiniAddOn_AC26_Mac").write_bytes(b"\xcf\xfa\xed\xfe")
    return bundle


def test_the_add_on_is_found_inside_the_zip_the_workflow_uploads(
    mac_build: Any, tmp_path: Path
) -> None:
    """The artifact carries the bundle zipped, with the bundle's own folder at
    its top, as ditto --keepParent makes it."""
    bundle = _bundle(tmp_path / "built")
    archive = tmp_path / "LoriiniAddOn_AC26_Mac.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in sorted(bundle.rglob("*")):
            zipped.write(path, path.relative_to(bundle.parent))
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    found = mac_build.find_addon(archive, scratch)

    assert found is not None and found.name == "LoriiniAddOn_AC26_Mac.bundle"
    assert (found / "Contents" / "Info.plist").read_text(encoding="utf-8") == "<plist/>"


def test_the_add_on_is_placed_beside_the_program(mac_build: Any, tmp_path: Path) -> None:
    """Copied whole, as the folder it is, and a second run replaces the first
    rather than nesting a bundle inside the old one."""
    bundle = _bundle(tmp_path / "built")
    dist = tmp_path / "dist"

    assert mac_build.add_addon(dist, bundle)
    assert mac_build.add_addon(dist, bundle)

    placed = dist / "LoriiniAddOn_AC26_Mac.bundle"
    assert (placed / "Contents" / "MacOS" / "LoriiniAddOn_AC26_Mac").is_file()
    assert not (placed / "LoriiniAddOn_AC26_Mac.bundle").exists()


def test_a_missing_add_on_is_said_rather_than_shrugged_at(
    mac_build: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not mac_build.add_addon(tmp_path / "dist", tmp_path / "nowhere.bundle")
    assert "NOT IN dist" in capsys.readouterr().out
    assert not (tmp_path / "dist" / "LoriiniAddOn_AC26_Mac.bundle").exists()


def test_the_program_claims_the_macos_its_binaries_need(
    mac_build: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The newest of what every binary inside was built for, and never older
    than Big Sur. One wheel built for a newer Mac -- numpy's, for macOS 14 --
    is enough to raise it, and data that merely sits beside the binaries is
    not read at all."""
    app = tmp_path / "Loriini.app" / "Contents"
    (app / "MacOS").mkdir(parents=True)
    (app / "MacOS" / "Loriini").write_bytes(b"\xcf\xfa\xed\xfe program")
    (app / "Frameworks").mkdir()
    (app / "Frameworks" / "numpy.so").write_bytes(b"\xcf\xfa\xed\xfe numpy")
    (app / "Frameworks" / "rules.yaml").write_text("not a binary", encoding="utf-8")

    built_for = {"Loriini": (10, 13, 0), "numpy.so": (14, 0, 0)}
    read: list[str] = []

    def macosx_version_min(filename: str) -> tuple[int, int, int]:
        read.append(Path(filename).name)
        return built_for[Path(filename).name]

    # PyInstaller's own reader, which needs macholib, and that is installed
    # only on a Mac. Stood in for, so the choosing is tested everywhere
    # PyInstaller is -- which is not the bare install, without the dev tools.
    utils = pytest.importorskip("PyInstaller.utils", reason="PyInstaller is a dev dependency")
    reader = ModuleType("PyInstaller.utils.osx")
    monkeypatch.setattr(reader, "macosx_version_min", macosx_version_min, raising=False)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.osx", reader)
    monkeypatch.setattr(utils, "osx", reader, raising=False)

    assert mac_build.oldest_macos(tmp_path / "Loriini.app") == (14, 0)
    assert sorted(read) == ["Loriini", "numpy.so"]

    del built_for["numpy.so"]
    (app / "Frameworks" / "numpy.so").unlink()
    assert mac_build.oldest_macos(tmp_path / "Loriini.app") == (11, 0)
