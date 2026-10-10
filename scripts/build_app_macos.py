"""Build the window into Loriini.app, the Mac program a colleague double-clicks.

    uv sync            # once, to install PyInstaller
    uv run python scripts/build_app_macos.py

The Mac half of ``build_app.py``, and run on a Mac. Leaves ``dist/Loriini.app``
and, beside it, the add-on it talks to -- ``dist/LoriiniAddOn_AC26_Mac.bundle``
-- with ``How to install.txt`` and ``LICENSE.txt``: the same handover a PC
gets, in the shapes a Mac takes. The ``Archicad add-on`` workflow makes the
same folder on a Mac runner and uploads it as the ``Loriini_AC26_Mac``
artifact, for anybody without a checkout.

The add-on is not compiled here, for the reason it is not on a PC: it needs
the Archicad kit and Xcode, and the workflow has both. This takes it, in
order, from

    --addon PATH              a .bundle you name, or the .zip the workflow
                              uploads it in
    archicad-addon/Build/...  a local build, where somebody has one
    the workflow's artifact   the newest successful build of this branch,
                              downloaded with the GitHub CLI (``gh``)

and says plainly when it found none, as ``build_app.py`` does.

What is different on a Mac
--------------------------
The program is a folder, ``Loriini.app``, that the Finder shows as one file,
so there is no single-file build unpacking itself on every start: the bundle
already is the one thing handed over. The add-on is a folder too, a .bundle,
and is copied as one.

The oldest macOS the app says it runs on is read off the binaries inside it
after the build, not assumed. A wheel built for a newer macOS than the rest --
numpy has one, for macOS 14, which a Mac on 14 or later installs by default --
raises it, and the Info.plist then says so: a Mac too old is told as much by
the Finder instead of the program failing as it opens. The workflow installs
the macOS 11 wheels, so the program it makes runs on every Apple silicon Mac;
see ``OLDEST_MACOS``.

Neither half is signed with a Developer ID, because there is none to sign
with. PyInstaller signs the app ad hoc, which is what Apple silicon needs to
run it at all, and the Mac still asks once before opening anything
downloaded -- the install note says how to answer.
"""

from __future__ import annotations

import argparse
import datetime as dt
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import build_app as pc

ROOT = pc.ROOT
NAME = pc.NAME
APP = f"{NAME}.app"

#: The recipe, beside the PC's and taking its collection from it.
SPEC = ROOT / "Loriini-macOS.spec"

#: The icon a Mac reads for an application, made with the .ico by
#: scripts/make_icon.py.
ICON = ROOT / "assets" / "loriini.icns"

#: The add-on, as the workflow names its artifact and its bundle.
ADDON = "LoriiniAddOn_AC26_Mac"

#: Where a local build of it lands, for a Mac that has the kit and Xcode.
LOCAL_ADDON = ROOT / "archicad-addon" / "Build" / "RelWithDebInfo" / f"{ADDON}.bundle"

#: What Loriini-macOS.spec claims, and the floor under what this reports:
#: Big Sur, the first macOS on Apple silicon, and so the oldest any Mac this
#: program runs on can have.
OLDEST_MACOS = (11, 0)

#: The first four bytes of a Mach-O file, thin or fat, either byte order.
MACH_O = {
    bytes.fromhex(magic)
    for magic in ("feedface", "feedfacf", "cefaedfe", "cffaedfe", "cafebabe", "bebafeca")
}


def spelt(version: tuple[int, int]) -> str:
    """A macOS version the way Info.plist and people write it."""
    return f"{version[0]}.{version[1]}"


def install_note(oldest: tuple[int, int] = OLDEST_MACOS, today: dt.date | None = None) -> str:
    """What ``How to install.txt`` says on a Mac: the files, the steps, and
    which build this is, like the PC's -- and the one step a PC does not
    have, which is persuading the Mac to open something unsigned."""
    branch, commit = pc._branch(), pc._git("rev-parse", "--short", "HEAD")
    day = today or dt.date.today()
    built = f"Built on {day.day} {day:%B %Y}"
    if branch:
        built += f" from {branch}"
    if commit:
        built += f" at commit {commit}"
    return f"""{pc.PRODUCT} {pc.__version__} for Archicad 26 on a Mac

Everything a Mac needs. None of it needs Python, an installer or
administrator rights.

  {APP}                      the program
  {ADDON}.bundle     the Archicad 26 add-on, with Tapir's
                                   commands built in
  {pc.LICENCE_COPY}                      the licence terms, as at
                                   {pc.TERMS_ADDRESS}

To install

1. Copy {APP} and {ADDON}.bundle into one folder of
   your own, for example
       ~/Documents/Loriini/Add-Ons
   Keep the two together: the Loriini menu in Archicad starts the
   {APP} it finds beside the add-on.
2. Neither is signed by an identified developer, so the Mac holds back
   both until told they are wanted. Once, in Terminal:
       xattr -dr com.apple.quarantine ~/Documents/Loriini/Add-Ons
   Without it the Mac stops Archicad loading the add-on, and {APP}
   opens only by Control-clicking it and choosing Open.
3. In Archicad 26, open Options > Add-On Manager, add that folder, and
   restart Archicad.
4. Start {pc.PRODUCT} from its menu in Archicad, or double-click {APP}.

A separate Tapir add-on is not needed, and can be removed once this one
loads.

To update, quit Archicad and replace both with the ones from a newer
folder, then run the command in step 2 again.

{APP} needs an Apple silicon Mac on macOS {spelt(oldest)} or later. The
add-on runs in Archicad on Apple silicon and Intel alike.

{pc.PRODUCT} is a prototype. Its figures are not validated for a DA submission.

{built}.
"""


def add_notes(dist: Path, oldest: tuple[int, int] = OLDEST_MACOS) -> None:
    """The install note and the licence terms, beside the program and the
    add-on. The terms as the PC's folder carries them (``build_app.licence_terms``),
    in a Mac's own line endings."""
    dist.mkdir(parents=True, exist_ok=True)
    (dist / pc.INSTALL_NOTE).write_text(install_note(oldest), encoding="utf-8")
    (dist / pc.LICENCE_COPY).write_text(pc.licence_terms(), encoding="utf-8")
    print(f"added  {dist / pc.INSTALL_NOTE}  and  {pc.LICENCE_COPY}")


def unzip(archive: Path, into: Path) -> None:
    """Unpack a zip the way the Finder would.

    ``ditto`` where there is one, which is every Mac: it is what made the
    workflow's zip, and it puts back what ``zipfile`` drops -- permissions,
    and the Finder's own metadata, which it keeps out of the way rather than
    leaving a ``__MACOSX`` folder beside the bundle.
    """
    ditto = shutil.which("ditto")
    if ditto is not None:
        subprocess.run([ditto, "-x", "-k", str(archive), str(into)], check=True)
        return
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(into)


def bundle_in(folder: Path) -> Path | None:
    """The add-on bundle somewhere under ``folder``, unzipping to find it."""
    for archive in sorted(folder.rglob("*.zip")):
        unzip(archive, archive.parent)
    return next(iter(sorted(folder.rglob(f"{ADDON}.bundle"))), None)


def fetch_addon(into: Path) -> Path | None:
    """The newest successful Mac add-on build of this branch, from GitHub.

    As ``build_app.fetch_addon``, but for the Mac artifact, which carries the
    bundle zipped: an artifact keeps files and not folders' permissions.
    """
    gh = shutil.which("gh")
    if gh is None:
        print("  no GitHub CLI (gh) on this machine to fetch the add-on with.")
        return None
    listing = [gh, "run", "list", "--workflow", pc.ADDON_WORKFLOW, "--status", "success"]
    branch = pc._branch()
    if branch:
        listing += ["--branch", branch]
    listing += ["--limit", "1", "--json", "databaseId", "--jq", ".[0].databaseId"]
    found = subprocess.run(listing, cwd=ROOT, capture_output=True, text=True, check=False)
    run_id = found.stdout.strip()
    if found.returncode != 0 or not run_id or run_id == "null":
        where = f" of {branch}" if branch else ""
        print(f"  no successful add-on build{where} to fetch. {found.stderr.strip()}".rstrip())
        return None
    print(f"  fetching the add-on from build {run_id}...")
    fetched = subprocess.run(
        [gh, "run", "download", run_id, "--name", ADDON, "--dir", str(into)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if fetched.returncode != 0:
        print(f"  the download failed: {fetched.stderr.strip()}")
        return None
    return bundle_in(into)


def find_addon(named: Path | None, scratch: Path) -> Path | None:
    """Where the add-on is, by the order the module docstring gives."""
    if named is not None:
        if named.is_dir() and named.suffix == ".bundle":
            return named
        if named.is_file() and named.suffix == ".zip":
            shutil.copy2(named, scratch / named.name)
            return bundle_in(scratch)
        print(f"  no add-on bundle, or zip of one, at {named}.")
        return None
    if LOCAL_ADDON.is_dir():
        return LOCAL_ADDON
    return fetch_addon(scratch)


def add_addon(dist: Path, named: Path | None) -> bool:
    """Put the add-on beside the program. True when it is there."""
    with tempfile.TemporaryDirectory() as scratch:
        found = find_addon(named, Path(scratch))
        if found is None:
            print(
                f"\nNOT IN dist: the add-on. Download {ADDON} from the latest "
                "'Archicad add-on' run on GitHub and run this with --addon <file>, "
                "or log in with 'gh auth login' so it can be fetched."
            )
            return False
        placed = dist / f"{ADDON}.bundle"
        if placed.exists():
            shutil.rmtree(placed)
        dist.mkdir(parents=True, exist_ok=True)
        shutil.copytree(found, placed, symlinks=True)
    print(f"added  {placed}  (from {found})")
    return True


def is_mach_o(path: Path) -> bool:
    """Whether a file in the bundle is a program or a library, by its magic."""
    try:
        with path.open("rb") as file:
            return file.read(4) in MACH_O
    except OSError:
        return False


def oldest_macos(app: Path) -> tuple[int, int]:
    """The oldest macOS every binary in the app runs on.

    Each binary records the oldest macOS it was built for, and the app runs
    only where all of them do, so this is the newest of those -- never older
    than ``OLDEST_MACOS``, which is what the spec claims to begin with.
    PyInstaller's own reader, which it uses to sign the same files.
    """
    from PyInstaller.utils import osx

    newest = OLDEST_MACOS
    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file() or not is_mach_o(path):
            continue
        try:
            major, minor, _ = osx.macosx_version_min(str(path))
        except Exception:
            # A Mach-O it cannot read -- an object file, a stub -- claims no
            # version, and so constrains nothing.
            continue
        newest = max(newest, (major, minor))
    return newest


def claim_oldest_macos(app: Path) -> tuple[int, int]:
    """Make the Info.plist say what the binaries need, and sign it again if so."""
    oldest = oldest_macos(app)
    plist = app / "Contents" / "Info.plist"
    info = plistlib.loads(plist.read_bytes())
    if info.get("LSMinimumSystemVersion") == spelt(oldest):
        return oldest
    info["LSMinimumSystemVersion"] = spelt(oldest)
    plist.write_bytes(plistlib.dumps(info))
    # Changing a signed bundle's Info.plist breaks its seal, and a broken
    # seal on Apple silicon is a program that does not start.
    from PyInstaller.utils import osx

    osx.sign_binary(str(app), deep=True)
    print(
        f"  {APP} needs macOS {spelt(oldest)}, because a wheel in it was built for "
        f"that; for older Macs, build with MACOSX_DEPLOYMENT_TARGET={spelt(OLDEST_MACOS)} "
        "wheels, as the workflow does."
    )
    return oldest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Loriini.app and gather the add-on.")
    parser.add_argument(
        "--addon", type=Path, help="the add-on .bundle, or a .zip of it, to put beside the program"
    )
    parser.add_argument(
        "--addon-only",
        action="store_true",
        help="only put the add-on into dist; do not rebuild the program",
    )
    arguments = parser.parse_args(argv)
    dist = ROOT / "dist"
    if arguments.addon_only:
        add_notes(dist)
        return 0 if add_addon(dist, arguments.addon) else 1

    if sys.platform != "darwin":
        # PyInstaller builds for the machine it runs on, and a .app is made
        # only on a Mac.
        print("Loriini.app is built on a Mac. On a PC, run scripts/build_app.py.", file=sys.stderr)
        return 2

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is not installed. It is in the dev dependency group:\n"
            "    uv sync\n"
            "then run this again.",
            file=sys.stderr,
        )
        return 2

    for needed, what in (
        (SPEC, "build recipe"),
        (pc.SPEC, "PC recipe the Mac's reads"),
        (ICON, "icon"),
    ):
        if not needed.is_file():
            # Named rather than shrugged at, for the reasons build_app.py gives.
            print(f"No {what} at {needed}.", file=sys.stderr)
            return 2

    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)]
    print(" ".join(command))
    finished = subprocess.run(command, cwd=ROOT, check=False)
    if finished.returncode != 0:
        return finished.returncode

    built = dist / APP
    if not built.is_dir():
        print(f"PyInstaller finished but there is no {built}.", file=sys.stderr)
        return 1
    # The folder the bundle was assembled from, left beside it. Handed over,
    # it is a second copy of the program that does not open like one.
    shutil.rmtree(dist / NAME, ignore_errors=True)
    oldest = claim_oldest_macos(built)
    size = sum(f.stat().st_size for f in built.rglob("*") if f.is_file() and not f.is_symlink())
    print(f"\nbuilt {built}  ({size / 1e6:.0f} MB, macOS {spelt(oldest)} and later)")
    add_notes(dist, oldest)
    # Last, so that when it is missing the line saying so is the last thing
    # printed.
    return 0 if add_addon(dist, arguments.addon) else 1


if __name__ == "__main__":
    raise SystemExit(main())
