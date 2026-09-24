# -*- mode: python ; coding: utf-8 -*-
#
# Loriini.app: the program for a Mac, from the same collection as the PC's.
#
# Everything up to the executable -- what is gathered, what is trimmed, the
# analysis itself -- is Loriini.spec's. It is read out of that file and run
# here rather than copied, so a data file or an exclusion added for the PC
# reaches the Mac in the same commit instead of in a bug report. Only what is
# made from it differs:
#
#   A folder, not one file. PyInstaller's single-file mode unpacks itself to
#   a temporary folder on every start, which inside a .app is deprecated and
#   will be refused -- and there is no need for it: an application bundle is
#   already the one thing a person copies.
#   No console to hide and no version resource. Both are Windows things; the
#   Finder reads the name and the version out of the Info.plist below.
#   The icon is the .icns, which is what the Finder and the Dock read, made
#   by scripts/make_icon.py from the same artwork as the .ico.
#   No UPX. It saves little on a Mac and breaks the code signature every
#   Apple silicon binary has to carry.
#
# Built by scripts/build_app_macos.py, which runs this from its own folder.

import sys
from pathlib import Path

_PC_SPEC = Path(SPECPATH) / 'Loriini.spec'
# Where the PC's recipe stops collecting and starts building. A test holds
# Loriini.spec to it (tests/unit/test_macos.py), so a change there that moves
# it fails in CI rather than here.
_THE_EXECUTABLE = '\npyz = PYZ(a.pure)'
_collection, _found, _ = _PC_SPEC.read_text(encoding='utf-8').partition(_THE_EXECUTABLE)
if not _found:
    raise SystemExit(f"{_PC_SPEC} has no line '{_THE_EXECUTABLE.strip()}' to take the collection up to.")
exec(compile(_collection, str(_PC_SPEC), 'exec'))

sys.path.insert(0, str(ROOT / 'src'))
from sun_study import AUTHOR, PRODUCT, __version__

ICNS = str(ROOT / 'assets' / 'loriini.icns')

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Loriini',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    # The palette's study arrives as `--args --study facade` through `open`,
    # which is an ordinary command line; there is no Apple event to turn into
    # one.
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Loriini',
)
app = BUNDLE(
    coll,
    name='Loriini.app',
    icon=ICNS,
    bundle_identifier='com.samiabdulnour.loriini',
    version=__version__,
    info_plist={
        'CFBundleName': PRODUCT,
        'CFBundleDisplayName': PRODUCT,
        'CFBundleShortVersionString': __version__,
        'CFBundleVersion': __version__,
        'NSHumanReadableCopyright': f'Created by {AUTHOR}',
        'NSHighResolutionCapable': True,
        # The window is drawn in its own light palette -- see
        # sun_study/app/theme.py -- and a Mac in dark mode would otherwise
        # darken the parts Tk leaves to the system, the dialogs and message
        # boxes, around a window that stays light.
        'NSRequiresAquaSystemAppearance': True,
        # Big Sur, the first macOS on Apple silicon. scripts/build_app_macos.py
        # raises it after the build if a binary inside needs a newer one.
        'LSMinimumSystemVersion': '11.0',
    },
)
