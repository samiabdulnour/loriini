# -*- mode: python ; coding: utf-8 -*-
import subprocess
from pathlib import Path, PurePath
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

# Every path is taken from the folder this file is in, so the one recipe
# builds on any machine: a checkout on somebody's PC, or the runner that
# makes the distribution folder (.github/workflows/archicad-addon.yml).
# PyInstaller puts SPECPATH in scope for exactly this. A spec PyInstaller
# writes for itself holds absolute paths, and this one held those of the PC
# it was first built on, which no other machine has.
ROOT = PurePath(SPECPATH)
ICON = str(ROOT / 'assets' / 'loriini.ico')

datas = [(ICON, 'assets')]
# The window's icons. PNGs rather than drawings made at run time: Tk reads
# them itself, and `scripts/make_icons.py` is what draws them. Pillow is in
# the bundle since D121 for the reference image (`sun_study.app.overlay`),
# which reads photographs with it; the icons still never need it.
# `sun_study.app.icons` looks for them at exactly this path under _MEIPASS.
datas += [(str(ROOT / 'assets' / 'icons'), 'assets/icons')]
# The window's face, Inter, with its licence. `sun_study.app.theme` registers
# the files with Windows for the running process alone, so nothing is
# installed; without them the window falls back to Segoe UI.
datas += [(str(ROOT / 'assets' / 'fonts'), 'assets/fonts')]
# The bird at 256 pixels, for the agent's client to show beside the server's
# name (`sun_study.agent.tools.icon` looks for it at `assets` under _MEIPASS),
# and at 32 for the window's tool bar (`sun_study.app.window.brand_mark`).
datas += [(str(ROOT / 'assets' / 'loriini-icon-256.png'), 'assets')]
datas += [(str(ROOT / 'assets' / 'loriini-icon-32.png'), 'assets')]
# The licence itself, at the root of the bundle, where `sun_study.licence.file`
# looks for it. The info box summarises the terms from a constant that is in
# the executable either way; this is what `Read the full licence` shows, and
# without it that button is hidden rather than broken.
datas += [(str(ROOT / 'LICENSE'), '.')]
# The terms a subscriber buys under, at the root of the bundle, where
# `sun_study.terms.page` looks for them. A build that takes licence keys shows
# these under `Read the full terms` in place of the source licence: they are
# the agreement the customer accepted at the checkout.
datas += [(str(ROOT / 'site' / 'terms.html'), '.')]
# Which commit this build is, asked of git here at build time because the
# program handed over has no repository to ask. Every prototype build calls
# itself 0.0.1, so without this a run log cannot show that the app on a
# machine is older than a fix in the source -- which is how a certificate
# failure fixed on the 17th was still being diagnosed from a log on the
# 23rd. The hash rides at the root of the bundle, beside the LICENSE, where
# `sun_study.stamp` reads it for the run log's first line. Built outside a
# checkout there is no answer and no stamp, and the log opens with the
# version alone.
try:
    _asked = subprocess.run(
        ['git', 'rev-parse', '--short', 'HEAD'],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    _commit = _asked.stdout.strip() if _asked.returncode == 0 else ''
except OSError:
    _commit = ''
if _commit:
    _stamp = Path(str(ROOT)) / 'build' / 'build_stamp.txt'
    _stamp.parent.mkdir(parents=True, exist_ok=True)
    _stamp.write_text(_commit + '\n', encoding='utf-8')
    datas += [(str(_stamp), '.')]
binaries = []
hiddenimports = []
datas += collect_data_files('tzdata')
datas += collect_data_files('sun_study')
hiddenimports += collect_submodules('typer')
# The Rhino reader is a dev-only path and drags 6 MB of rhino3dm in. The
# licence issuer and the licence service are the vendor's side
# (scripts/licence.py, deploy/licence-service): Loriini only checks keys and
# leases, and a program that carried the code that makes them would be
# advertising where to look.
hiddenimports += [m for m in collect_submodules('sun_study') if not m.startswith(('sun_study.ingest.rhino', 'sun_study.licence_issue', 'sun_study.licence_service'))]
# ifcopenshell: the package and its wrapper, without the express rules, the
# MVD examples and the schema dumps nothing here imports -- 20 MB of the
# 106 MB it weighs when collected whole.
tmp_ret = collect_all('ifcopenshell')
_unwanted = ('/express/', '/mvd/', '/util/schema/')
datas += [d for d in tmp_ret[0] if not any(u in PurePath(d[0]).as_posix() for u in _unwanted)]
binaries += tmp_ret[1]
hiddenimports += [m for m in tmp_ret[2] if not m.startswith(('ifcopenshell.express', 'ifcopenshell.mvd', 'ifcopenshell.validate'))]


a = Analysis(
    [str(ROOT / 'src' / 'sun_study' / 'app' / '__main__.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['rhino3dm', 'shapely', 'mypy', 'pydantic.v1.mypy', 'pydantic.mypy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Loriini',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(ROOT / 'build' / 'version_info.txt'),
    icon=[ICON],
)
