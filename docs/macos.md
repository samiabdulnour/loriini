# Loriini on a Mac

The macOS version of the program and of the Archicad add-on: the same study,
built for a Mac, on the `macos` branch. It started from `windows` at
`aa30131`, the newest work at the time: the redesigned window, Tapir built
into the add-on, and the handover folder built on GitHub.

Nothing in the analysis changed. `core`, `rules`, `ingest`, `report`, `site`
and the Archicad adapter never knew which platform they were on: Archicad's
JSON API is HTTP on the same port on both, and every path the tool hands
Archicad is built with `pathlib` on the machine it runs on. What differs is the
shell around the study: how the add-on is compiled and started, how the
program is packaged, and three things about the window.

> **Not yet run inside Archicad on a Mac.** Everything below that says
> *checked* was checked on a Linux machine or on a GitHub macOS runner, and
> none of those has Archicad. The first run on a Mac with Archicad 26 is the
> [checklist](#the-first-run-on-a-mac) at the end.

## Installing it

The `Archicad add-on (macOS)` workflow makes the folder: `Loriini.app` beside
one add-on per Archicad version, `LoriiniAddOn_AC26_Mac.bundle` to
`LoriiniAddOn_AC30_Mac.bundle`, with `How to install.txt` and the licence
terms (`site/terms.html` as text, as in the PC's folder). It is the
`Loriini_Mac` artifact on the run's page, under the Actions tab, and the
*Website* workflow serves the newest one from the site's download page
beside the Windows folder (website.md, D175). From the run's page the
download is a zip holding `Loriini_Mac.zip`: open both; from the site it is
`Loriini_Mac.zip` itself. An artifact flattens the links inside an
application and drops its execute bit, so the folder travels zipped by
`ditto`, which keeps them.

Then, as the install note says:

1. Copy `Loriini.app` and `LoriiniAddOn_AC26_Mac.bundle` into one folder of
   your own, for example `~/Documents/Loriini/Add-Ons`. Keep them together:
   the Loriini menu starts the `Loriini.app` it finds beside the add-on.
2. Take the quarantine off, once:

       xattr -dr com.apple.quarantine ~/Documents/Loriini/Add-Ons

   Neither half is signed with a Developer ID, because there is none to sign
   with. Both are signed ad hoc, which is what Apple silicon needs to run code
   at all, and the Mac still holds back anything downloaded that is not from
   an identified developer: it stops Archicad loading the add-on, and opens
   the program only by Control-click > Open.
3. In Archicad 26, **Options > Add-On Manager**, add that folder, restart.
4. Start Loriini from its menu in Archicad, or double-click `Loriini.app`.

Tapir is built in, as on Windows, so a separate Tapir add-on is not needed.

**Which Macs.** The add-on carries an Intel and an Apple silicon half, like the
kit it is built from, so it loads in Archicad 26 on either. `Loriini.app` is
for Apple silicon, macOS 11 or later: numpy and ifcopenshell publish one wheel
per processor, so a program is built for the processor it is built on, and
the workflow's runner is Apple silicon. An Intel Mac can build its own with
the script below.

## Building it

**The add-on** needs the Mac kit and Xcode, which a runner has, so it is built
by the workflow on every push that changes `archicad-addon/`. On a Mac that
has Xcode, the same build by hand:

    python3 archicad-addon/Tools/download_and_unzip.py \
        https://github.com/GRAPHISOFT/archicad-api-devkit/releases/download/26.3000/API.Development.Kit.MAC.26.3000.zip \
        archicad-addon/Build/DevKit
    cmake -B archicad-addon/Build -G Xcode -DAC_API_DEVKIT_DIR=archicad-addon/Build/DevKit archicad-addon
    cmake --build archicad-addon/Build --config RelWithDebInfo

Build one configuration per build folder: on a Mac the resources are written
into the bundle of the configuration being built, and the step that writes
them is not repeated for a second one.

**The program**, on a Mac with a checkout:

    uv sync
    uv run python scripts/build_app_macos.py

`scripts/build_app.py` hands over to it on a Mac, so either name works. It
leaves the same folder the workflow does in `dist/`, taking the add-on from
`--addon` (a `.bundle`, or the workflow's zip), a local build, or the newest
workflow run of the branch through `gh`, in that order.

The program says in its `Info.plist` which macOS it needs, and the build reads
that off the binaries inside it rather than assuming it. On a Mac running
macOS 14 or later, uv installs numpy's macOS 14 wheel, so a program built there
says it needs macOS 14 -- right for that Mac and its neighbours, wrong for an
older one. The workflow installs the macOS 11 wheels instead; to do the same
by hand:

    uv sync
    uv export --no-dev --no-hashes --no-emit-project > runtime.txt
    MACOSX_DEPLOYMENT_TARGET=11.0 uv pip install --reinstall \
        --python-platform aarch64-apple-darwin -r runtime.txt
    uv run --no-sync python scripts/build_app_macos.py

## What is different on a Mac, and why

### The add-on

- **`CMakeLists.txt` builds a bundle as well as an .apx.** Its Windows half is
  unchanged. The Mac half is the dev kit's own `AddOnCommandTest` example put
  back -- the Mac kit ships it with its macOS branches intact: a loadable
  bundle, the kit's `libACAP_STAT.a`, `macintosh` defined for the headers,
  resources compiled by the kit's script into the bundle, and PkgInfo copied
  in. Where the example and Tapir differ, Tapir wins, because Tapir's commands
  are most of this add-on and its Mac build is the one proven with them:
  both architectures by name, the warning list Tapir compiles with, the kit's
  headers as system headers so `-Werror` is about this add-on's own code, and
  every framework in the kit linked rather than one per module folder.
- **Header maps are off.** An Xcode header map resolves a quoted include by
  file name across the whole target, and Loriini and Tapir each have a
  `ProjectCommands.hpp`, an `APIEnvir.h` and a `ResourceIds.hpp`. The Tapir
  note in `CMakeLists.txt` relies on an include finding the file beside it.
- **The `Info.plist`** is written from `RFIX.mac/Info.plist.in` the way Tapir
  writes its own, with the version and the oldest macOS read out of the kit.
  `.APX` and `GSAP` are what make the folder an add-on.
- **The kit is unpacked as what it is.** `Tools/download_and_unzip.py` used
  `ZipFile.extractall`, which writes each symbolic link as a small file and
  drops every permission bit. The Windows kit never noticed; the Mac kit has
  423 links inside its frameworks, which the linker follows, and a resource
  compiler that has to be executable. Checked against the real 26.3000 kit:
  the unpacked tree is identical to `unzip`'s, entry for entry.
- **`ExportModel` opens its file portably.** It used `fopen_s`, which is from
  C11's optional Annex K: Microsoft's library has it and Apple's does not. On a
  Mac the path goes to `fopen` in UTF-8, which is how a Mac spells every path.
- **The menu and the palette start `Loriini.app`** from beside the bundle,
  through `open -n -a`: LaunchServices brings the window to the front with its
  own Dock icon and starts it outside Archicad's environment, and `-n` makes
  each press start one, as `ShellExecute` does on Windows -- without it a
  palette button pressed while the window is open would be dropped.

What the workflow checks before uploading, each a way a bundle can build and
still not load: both architectures are in it; `.APX` and `GSAP` are in the
`Info.plist` and in PkgInfo; and the MDID is exact. On a Mac it is a file of
its own, `Resources/English.lproj/MDID_32500.rsrd`, eight bytes, the developer
id and the add-on's own id, most significant byte first -- read out of Tapir's
shipped `TapirAddOn_AC26_Mac.bundle`. Then it signs the bundle ad hoc and
verifies the signature the way macOS will.

### The program

- **`Loriini-macOS.spec`** runs `Loriini.spec` up to the line where the PC's
  executable is made, and makes a `.app` from the same collection. So a data
  file or an exclusion added for the PC reaches the Mac in the same commit,
  and a test fails if that line ever moves. A folder rather than one file,
  because a single-file `.app` is deprecated by PyInstaller and pointless:
  the bundle already is the one thing a person copies.
- **`assets/loriini.icns`**, made by `scripts/make_icon.py` beside the `.ico`.
  The `.ico` is the tile to its edges, as Windows draws icons; the `.icns`
  puts it on Apple's grid, 824 of 1024 with a shadow beneath, so it stands
  the same size as every other icon in the Dock.
- **The Mac's light appearance** is asked for (`NSRequiresAquaSystemAppearance`):
  the window is drawn in its own light palette, and in dark mode a Mac would
  darken the dialogs Tk leaves to it around a window that stays light.

The workflow starts the packaged program once, the way the window starts a
study, and requires it to list the rulesets; then checks its signature and
that it claims macOS 11.

### The window

- **Type.** Tk sizes type in points and turns points into pixels at the
  screen's rate. Windows counts 96 pixels to the inch, so the 9 points the
  window is set in are 12 pixels there, and every row, card and thumbnail was
  measured against those 12. A Mac's Tk counts a point as one pixel, so the
  same 9 came out a quarter smaller. `theme.points` asks a Mac for four thirds
  of every size, and every size in the window goes through it -- the styles,
  the log, and the lettering on the thumbnails, which is measured at the size
  it is drawn. The face is the Mac's own, San Francisco, as Tk names it
  (`.AppleSystemUIFont`); the log is set in Menlo.
- **Settings, the licence key and the run logs** live in
  `~/Library/Application Support/Loriini`, where a Mac keeps every program's
  and where a migrated account takes them. `sun_study.user_folder` says so for
  all of them. `APPDATA` is still asked first, because it is how the tests
  point the folder somewhere disposable, on every platform.
- **The Dock's icon.** The packaged program's comes from its bundle. A window
  started from a checkout is Python's, so it is given `loriini-icon-256.png`.
- **Advice names the Mac's add-on.** `sun_study.ADDON_FILE` is
  `LoriiniAddOn_AC26_Mac.bundle` on a Mac, and every message that tells
  somebody to install the add-on says it.

## Keeping this branch in step with the Windows one

It is meant to take the Windows line's work by merging `windows` in, so almost
everything here is a new file: `Loriini-macOS.spec`,
`scripts/build_app_macos.py`, `archicad-addon/RFIX.mac/`, the two `*-macos.yml`
workflows, `tests/unit/test_macos*.py` and this page. `ci.yml` and
`archicad-addon.yml` are untouched. The shared files it changes do so in
platform branches that leave Windows as it was:

| File | What changed |
|---|---|
| `archicad-addon/CMakeLists.txt` | Mac branches beside the Windows ones |
| `archicad-addon/Src/APIEnvir.h`, `Launch.cpp`, `Launch.hpp` | the Mac launch |
| `archicad-addon/Src/ModelCommands.cpp` | `fopen_s` on Windows only |
| `archicad-addon/Tools/download_and_unzip.py` | links and permissions kept off Windows |
| `scripts/build_app.py` | hands over to the Mac script on a Mac |
| `scripts/make_icon.py` | writes the `.icns` too |
| `src/sun_study/__init__.py` | `ADDON_FILE`; `user_folder` on a Mac |
| `src/sun_study/app/theme.py`, `window.py`, `preferences.py` | type, Dock icon, settings folder |
| `src/sun_study/archicad/connection.py` | advice names `ADDON_FILE` |
| `tests/unit/test_app.py` | the PC icon test pins the PC branch |

`tests/unit/test_macos.py` holds the Mac spec to `Loriini.spec`, so a merge that
moves the line it reads up to fails in CI rather than on a Mac.

## What it costs to run

The repository is private, and GitHub bills a Mac minute as ten. So the Mac
workflows run less than the Windows ones: `CI (macOS)` runs the suite and mypy
on one Python, for a push that changes the program or its tests; `Archicad add-on (macOS)`
builds the bundle and the folder for a push that changes the add-on or how the
folder is made. Neither runs for a pull request, whose push has already run
them, and each is capped well short of GitHub's six-hour limit. Anything else
is **Run workflow** on the Actions tab.

## The first run on a Mac

What a Mac with Archicad 26 settles, in order:

1. Archicad lists **Loriini** in the Add-On Manager as loaded, not as
   *missing* or *not an add-on*, and the **Loriini** menu shows its two items.
2. **Solar Analysis...** starts `Loriini.app`, in front, and the palette shows
   its seven buttons with their drawings.
3. A palette button starts the window with its study ticked, including while
   a window is already open.
4. The window: the type is the size of Archicad's own, nothing is clipped, the
   thumbnails' lettering fits its boxes, and the page scrolls with a trackpad.
5. **Refresh** finds the running Archicad and the project, and the add-on
   answers: the probe reads layers, zones and layouts.
6. A study runs end to end: the facade bands on a small model, with its
   export written to the Mac's temporary folder and read back.
7. The settings saved as defaults are in
   `~/Library/Application Support/Loriini/settings.json`.

If step 1 fails, the Add-On Manager says why it did not load the bundle, and
if step 2 fails the add-on says so in Archicad's Report window. The commonest
cause of either is a quarantine left on the folder -- step 2 of installing.
