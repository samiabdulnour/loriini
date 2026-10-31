"""Build the front page's sheet of lorikeet poses from the artwork.

    uv run python scripts/make_lorikeet_sheet.py

Reads ``assets/lorikeet/``: ``perched.png``, the bird on its feet, drawn at
ten screen pixels a pixel; ``take-off.gif`` and ``landing.gif``, the two
animations, drawn at four screen pixels a pixel on one canvas, the perched
bird in the same place in both. Writes ``site/lorikeet-sheet.png``: every
pose as a cell at the bird's own pixels, side by side -- the perched bird,
then the six frames of the take-off from the crouch to the climb, then the
seven of the landing from the approach to the fold -- and rewrites the
``CELL`` table in ``site/index.html`` to say where each cell is, where the
artist placed it relative to the perched bird, and how long it holds.

The page shows the cells at two picture units a pixel and moves the bird
from pose to pose (docs/website.md, D166). Run this when the artwork
changes; nothing else reads the artwork.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "assets" / "lorikeet"
SHEET = ROOT / "site" / "lorikeet-sheet.png"
PAGE = ROOT / "site" / "index.html"

#: The perched drawing's pixel pitch, and where its drawing begins.
PERCHED_PITCH, PERCHED_ORIGIN = 10, (120, 120)
#: The animations' pixel pitch, canvas in pixels, and the perched bird's top
#: left on that canvas, in pixels.
PITCH, CANVAS, PERCH = 4, (160, 152), (65, 78)
#: The frames used: the take-off from the crouch to the climb, before the
#: bird leaves the canvas; the landing from the approach, once the bird is
#: wholly on the canvas, to the fold, before the perched frame that repeats
#: the drawing.
TAKE_OFF = range(1, 7)
LANDING = range(5, 12)


def _drawn(value: tuple[int, ...]) -> tuple[int, int, int, int] | None:
    """A drawn pixel, or ``None`` for the clear or white ground."""
    if len(value) > 3 and value[3] == 0:
        return None
    if value[0] > 245 and value[1] > 245 and value[2] > 245:
        return None
    return (value[0], value[1], value[2], 255)


def at_pitch(
    image: Image.Image, pitch: int, origin: tuple[int, int], size: tuple[int, int]
) -> Image.Image:
    """The drawing at its own pixels: the centre of each cell of ``pitch``."""
    source = image.convert("RGBA")
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for j in range(size[1]):
        for i in range(size[0]):
            x, y = origin[0] + i * pitch + pitch // 2, origin[1] + j * pitch + pitch // 2
            if x < source.width and y < source.height:
                pixel = _drawn(source.getpixel((x, y)))  # type: ignore[arg-type]
                if pixel is not None:
                    out.putpixel((i, j), pixel)
    return out


def frames(path: Path, keep: range) -> list[tuple[Image.Image, int]]:
    """The kept frames of an animation at their own pixels, with their times."""
    out = []
    with Image.open(path) as animation:
        for index, frame in enumerate(ImageSequence.Iterator(animation)):
            if index in keep:
                held = int(frame.info.get("duration", 0))
                out.append((at_pitch(frame, PITCH, (0, 0), CANVAS), held))
    return out


def main() -> int:
    with Image.open(ART / "perched.png") as source:
        wide = (source.width - PERCHED_ORIGIN[0]) // PERCHED_PITCH
        high = (source.height - PERCHED_ORIGIN[1]) // PERCHED_PITCH
        perched = at_pitch(source, PERCHED_PITCH, PERCHED_ORIGIN, (wide, high))
    box = perched.getbbox()
    if box is None:
        raise SystemExit("perched.png has nothing drawn in it")
    cells: list[tuple[str, Image.Image, int, int, int]] = [("perched", perched.crop(box), 0, 0, 0)]
    animations = (("up", ART / "take-off.gif", TAKE_OFF), ("down", ART / "landing.gif", LANDING))
    for name, path, keep in animations:
        for index, (frame, held) in zip(keep, frames(path, keep), strict=True):
            box = frame.getbbox()
            if box is None:
                raise SystemExit(f"{path.name} frame {index} has nothing drawn in it")
            cells.append(
                (f"{name}{index}", frame.crop(box), box[0] - PERCH[0], box[1] - PERCH[1], held)
            )

    wide = sum(cell[1].width + 1 for cell in cells) - 1
    high = max(cell[1].height for cell in cells)
    sheet = Image.new("RGBA", (wide, high), (0, 0, 0, 0))
    rows, x = [], 0
    for name, image, dx, dy, held in cells:
        sheet.alpha_composite(image, (x, 0))
        rows.append(f"    {name}: [{x}, 0, {image.width}, {image.height}, {dx}, {dy}, {held}]")
        x += image.width + 1
    sheet.save(SHEET, optimize=True)
    weight = SHEET.stat().st_size / 1024
    print(f"wrote {SHEET}  ({wide} x {high}, {len(cells)} cells, {weight:.1f} kB)")

    page = PAGE.read_text(encoding="utf-8")
    table = "  var CELL = {\n" + ",\n".join(rows) + "\n  };"
    page, found = re.subn(
        r"  var CELL = \{\n.*?\n  \};", lambda _match: table, page, flags=re.DOTALL
    )
    if found != 1:
        raise SystemExit("site/index.html has no CELL table to rewrite")
    size = f'<image href="lorikeet-sheet.png" width="{wide}" height="{high}"/>'
    page, found = re.subn(
        r'<image href="lorikeet-sheet\.png" width="\d+" height="\d+"/>', lambda _match: size, page
    )
    PAGE.write_text(page, encoding="utf-8")
    print(f"rewrote the CELL table and {found} sheet size(s) in {PAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
