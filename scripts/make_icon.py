"""Build every size of the application icon from the artwork.

    uv run python scripts/make_icon.py

Reads ``assets/loriini-icon-1024.png`` -- the lorikeet on its rounded tile,
transparent outside the corners -- and writes, beside it:

* ``loriini.ico``, carrying every size Windows asks for;
* ``loriini.icns``, carrying every size a Mac asks for, on Apple's grid;
* ``loriini-icon-256.png``, the Dock's picture for a window started from a
  checkout and the MCP server's icon;
* ``loriini-icon-32.png``, the mark in the window's tool bar;
* ``loriini-icon-tile-1024.png``, the icon on cream, opaque, for anywhere that
  wants a square with nothing transparent in it;

and the website's copies in ``site``: ``icon-256.png``, ``icon-1024.png`` and a
``favicon.ico`` carrying only the sizes a browser tab uses, a tenth of the
weight of the program's.

Run it when the artwork changes; the build scripts do not, because an icon
changes about once a year and a build happens all day.

Why not hand the .png straight to PyInstaller
---------------------------------------------
It accepts one and converts it itself, with no say over the filter or the
alpha, and the sizes people actually look at are the small ones: Windows asks
for 16 in the title bar and the task bar, 32 and 48 in Explorer, and 256 in
the large-icon view.

The artwork is painted to look like pixel art, but its squares are not on a
regular grid, so no output size lands on whole squares and nearest-neighbour
would keep some and chop others. Every size's colour is a Lanczos reduction
of the 1024, done in premultiplied alpha so the transparent corners do not
bleed a dark rim into the tile's edge. Its transparency is not: Lanczos rings
at a hard edge, up to a twelfth too opaque on one side of the rounded corner
and too clear on the other, so the alpha is the plain share of each pixel the
tile covers.

Windows and a Mac want different framing
----------------------------------------
Windows draws an icon as given, so the .ico is the tile to its edges. A Mac's
icons sit on Apple's grid -- the tile 824 of 1024, centred, with a shadow
beneath -- and one drawn to the edges stands a size larger than everything
else in the Dock and the Finder. Everything a Mac asks for, from 16 at double
density to 1024, is resampled from that framed 1024.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "loriini-icon-1024.png"
TARGET = ASSETS / "loriini.ico"
MAC_TARGET = ASSETS / "loriini.icns"
#: The PNGs the program reads at run time, by size.
PNG_TARGETS = {256: ASSETS / "loriini-icon-256.png", 32: ASSETS / "loriini-icon-32.png"}
TILE_TARGET = ASSETS / "loriini-icon-tile-1024.png"
SITE = ROOT / "site"

#: Every size Windows asks for. 256 is the large-icon view and the Alt-Tab
#: switcher; 16 is the title bar and the task bar.
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: The sizes a browser asks a favicon for: a tab at single and double
#: density, and a bookmark.
SITE_SIZES = (16, 32, 48)

#: Every size a Mac asks for, as pixels: 16 to 512 points, each at single and
#: double density, which is 32 through 1024 once the two coincide. Pillow
#: writes an .icns from these and takes each one as given rather than
#: resizing the largest itself.
MAC_SIZES = (32, 64, 128, 256, 512, 1024)

#: Apple's grid at 1024: the tile's side, and the shadow under it.
MAC_TILE = 824
MAC_SHADOW_DROP = 10
MAC_SHADOW_BLUR = 12
MAC_SHADOW_ALPHA = 0.3

#: The cream behind the opaque tile.
CREAM = (249, 243, 239)


def render(source: Image.Image, size: int) -> Image.Image:
    """One size: Lanczos for the colour, coverage for the alpha."""
    if source.width == size:
        return source.copy()
    premultiplied = source.convert("RGBa")
    sharp = premultiplied.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    # Where Lanczos left a pixel all but clear its colour is noise divided by
    # nearly nothing; the area average is the honest colour there.
    soft = premultiplied.resize((size, size), Image.Resampling.BOX).convert("RGBA")
    trusted = sharp.getchannel("A").point(lambda a: 255 if a >= 32 else 0)
    frame = Image.composite(sharp, soft, trusted)
    frame.putalpha(source.getchannel("A").resize((size, size), Image.Resampling.BOX))
    return frame


def on_mac_grid(source: Image.Image) -> Image.Image:
    """The tile at Apple's size in a 1024 square, with its shadow."""
    side = source.width
    tile = render(source, MAC_TILE * side // 1024)
    at = (side - tile.width) // 2
    drop = MAC_SHADOW_DROP * side // 1024

    shadow = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ink = Image.new("RGBA", tile.size, (0, 0, 0, 255))
    ink.putalpha(tile.getchannel("A").point(lambda a: round(a * MAC_SHADOW_ALPHA)))
    shadow.alpha_composite(ink, (at, at + drop))
    shadow = shadow.filter(ImageFilter.GaussianBlur(MAC_SHADOW_BLUR * side / 1024))

    shadow.alpha_composite(tile, (at, at))
    return shadow


def main() -> int:
    if not SOURCE.is_file():
        print(f"No artwork at {SOURCE}.", file=sys.stderr)
        return 1

    source = Image.open(SOURCE).convert("RGBA")
    if source.size != (1024, 1024):
        print(f"{SOURCE.name} is {source.width}x{source.height}, not 1024x1024.", file=sys.stderr)
        return 1

    frames = [render(source, size) for size in SIZES]
    # Pillow writes the largest as the base and the rest as further entries.
    frames[-1].save(TARGET, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    written = ", ".join(str(size) for size in SIZES)
    print(f"wrote {TARGET}  ({TARGET.stat().st_size / 1024:.1f} kB, sizes {written})")

    framed = on_mac_grid(source)
    mac = [render(framed, size) for size in MAC_SIZES]
    mac[-1].save(MAC_TARGET, format="ICNS", append_images=mac[:-1])
    written = ", ".join(str(size) for size in MAC_SIZES)
    print(f"wrote {MAC_TARGET}  ({MAC_TARGET.stat().st_size / 1024:.1f} kB, sizes {written})")

    for size, target in PNG_TARGETS.items():
        render(source, size).save(target, optimize=True)
        print(f"wrote {target}  ({target.stat().st_size / 1024:.1f} kB)")

    tile = Image.new("RGBA", framed.size, (*CREAM, 255))
    tile.alpha_composite(framed)
    tile.convert("RGB").save(TILE_TARGET, optimize=True)
    print(f"wrote {TILE_TARGET}  ({TILE_TARGET.stat().st_size / 1024:.1f} kB)")

    favicon = SITE / "favicon.ico"
    small = [render(source, size) for size in SITE_SIZES]
    small[-1].save(
        favicon, format="ICO", sizes=[(s, s) for s in SITE_SIZES], append_images=small[:-1]
    )
    render(source, 256).save(SITE / "icon-256.png", optimize=True)
    source.save(SITE / "icon-1024.png", optimize=True)
    print(f"wrote {favicon}  ({favicon.stat().st_size / 1024:.1f} kB), icon-256.png, icon-1024.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
