"""Cut the raw clips into the demo on the *How it works* page.

    uv run python scripts/demo_cut.py                 # assets/demo/works.yaml
    uv run python scripts/demo_cut.py --skip-missing  # with the clips there are

Reads a cut list -- which clip, from when to when, what the caption says,
how much faster than life, which part of the frame -- and has ffmpeg make
one video of it: each cut cropped and fitted to the frame, its caption laid
along the foot, a short fade either side, the cuts joined; then the poster,
one frame of the result. The list is the edit, in a file, so the demo is
cut again by running this when a clip is re-recorded, and a change to the
edit is a diff anybody can read.

The clips come from two places (docs/website.md): the window's, from
``scripts/demo_capture_window.py``, on any machine; Archicad's, from
``scripts/demo_capture_archicad.py``, on a workstation with Archicad and
the add-on. A clip that is not there stops the cut and says which script
makes it, unless ``--skip-missing`` asks for the demo of what there is.

Captions are drawn with Pillow, in Inter where the machine has it, and laid
over the picture by ffmpeg: ffmpeg's own text wants a font file named at
the command line, which differs by machine, and the site's face is in
``site/fonts`` as WOFF2, which it cannot read. Standard library, Pillow and
PyYAML, which the project has; ffmpeg on the path.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "assets" / "demo" / "works.yaml"

#: Seconds of fade at each end of a cut.
FADE = 0.3
#: The caption band: its height, and the type in it.
BAND = 92
TYPE_PX = 24
INK = (31, 31, 29, 255)
PAPER = (255, 255, 255, 236)
RULE = (191, 196, 187, 255)


@dataclass(frozen=True)
class Cut:
    clip: Path
    start: float
    end: float
    caption: str = ""
    speed: float = 1.0
    """How much faster than life: 2.0 shows a minute in thirty seconds."""
    crop: tuple[int, int, int, int] | None = None
    """``(x, y, width, height)`` of the clip to fill the frame with."""

    @property
    def seconds(self) -> float:
        """How long the cut is on screen."""
        return (self.end - self.start) / self.speed


@dataclass(frozen=True)
class CutList:
    out: Path
    poster: Path
    poster_at: float
    width: int
    height: int
    fps: int
    cuts: tuple[Cut, ...] = field(default_factory=tuple)

    @property
    def seconds(self) -> float:
        return sum(cut.seconds for cut in self.cuts)


class CutListError(Exception):
    """The list does not say enough, or says it wrongly."""


def _number(entry: dict[str, Any], key: str, index: int, default: float | None = None) -> float:
    value = entry.get(key, default)
    if value is None:
        raise CutListError(f"cut {index} has no {key!r}")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise CutListError(f"cut {index}: {key!r} is {value!r}, not a number") from error


def read(path: Path) -> CutList:
    """The cut list, checked: every cut has a clip and a span, the spans
    run forwards, and nothing is left to a default nobody wrote down."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CutListError(f"cannot read {path}: {error}") from error
    if not isinstance(document, dict):
        raise CutListError(f"{path} is not a mapping")

    size = document.get("size", [1280, 720])
    if not (isinstance(size, list) and len(size) == 2):
        raise CutListError("size must be [width, height]")
    raw = document.get("cuts")
    if not isinstance(raw, list) or not raw:
        raise CutListError("the list has no cuts")

    cuts: list[Cut] = []
    for index, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict) or "clip" not in entry:
            raise CutListError(f"cut {index} names no clip")
        start = _number(entry, "from", index, 0.0)
        end = _number(entry, "to", index)
        speed = _number(entry, "speed", index, 1.0)
        if end <= start:
            raise CutListError(f"cut {index}: 'to' ({end:g}) is not after 'from' ({start:g})")
        if speed <= 0:
            raise CutListError(f"cut {index}: speed must be positive")
        crop = entry.get("crop")
        if crop is not None:
            if not (isinstance(crop, list) and len(crop) == 4):
                raise CutListError(f"cut {index}: crop must be [x, y, width, height]")
            crop = tuple(int(value) for value in crop)
        clip = Path(str(entry["clip"]))
        cuts.append(
            Cut(
                clip=clip if clip.is_absolute() else ROOT / clip,
                start=start,
                end=end,
                caption=str(entry.get("caption", "")).strip(),
                speed=speed,
                crop=crop,
            )
        )

    def where(key: str, default: str) -> Path:
        named = Path(str(document.get(key, default)))
        return named if named.is_absolute() else ROOT / named

    return CutList(
        out=where("out", "site/demo.mp4"),
        poster=where("poster", "site/demo-poster.png"),
        poster_at=float(document.get("poster_at", 1.0)),
        width=int(size[0]),
        height=int(size[1]),
        fps=int(document.get("fps", 30)),
        cuts=tuple(cuts),
    )


def missing(cut_list: CutList) -> list[Cut]:
    return [cut for cut in cut_list.cuts if not cut.clip.is_file()]


def shown(path: Path) -> str:
    """A path as it is said: from the repository's root when under it."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def how_to_make(clip: Path) -> str:
    """Which script records that clip."""
    if clip.name.startswith("window"):
        return "scripts/demo_capture_window.py, on any machine"
    return "scripts/demo_capture_archicad.py, on a workstation with Archicad open"


# -- captions --------------------------------------------------------------
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Inter if the machine has it, else the system's face, else Pillow's."""
    candidates = ["Inter-Medium.ttf", "Inter-Regular.ttf", "Inter.ttf"]
    if shutil.which("fc-match"):
        # fontconfig answers with the nearest face it has, so the answer is
        # only taken when it is the face asked for.
        found = subprocess.run(
            ["fc-match", "-f", "%{family}|%{file}", "Inter:medium"], capture_output=True, text=True
        ).stdout.strip()
        family, _, file = found.partition("|")
        if file and "inter" in family.lower():
            candidates.insert(0, file)
    if sys.platform == "win32":
        candidates += ["segoeui.ttf"]
    elif sys.platform == "darwin":
        candidates += ["/System/Library/Fonts/Helvetica.ttc"]
    else:
        candidates += ["DejaVuSans.ttf"]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def caption_image(text: str, width: int, height: int) -> Image.Image:
    """The caption band on a clear frame, to lay over the picture."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text:
        return image
    draw = ImageDraw.Draw(image)
    top = height - BAND
    draw.rectangle((0, top, width, height), fill=PAPER)
    draw.line((0, top, width, top), fill=RULE, width=1)
    font = _font(TYPE_PX)
    # Wrapped to the band's width, two lines at most.
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width - 96:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    lines = lines[:2]
    y = top + (BAND - len(lines) * (TYPE_PX + 6)) / 2
    for text_line in lines:
        draw.text((48, y), text_line, font=font, fill=INK)
        y += TYPE_PX + 6
    return image


# -- ffmpeg ------------------------------------------------------------------
def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SystemExit("ffmpeg is not on the path; install it, or point PATH at it.")
    return found


def filters(cut: Cut, cut_list: CutList) -> str:
    """The filter graph for one cut: crop, fit, pad, pace, caption, fades."""
    steps = []
    if cut.crop is not None:
        x, y, w, h = cut.crop
        steps.append(f"crop={w}:{h}:{x}:{y}")
    # With a caption the picture is fitted above the band, not under it:
    # the foot of a window is where the run bar and its line are.
    room = cut_list.height - (BAND if cut.caption else 0)
    steps.append(
        f"scale={cut_list.width}:{room}:force_original_aspect_ratio=decrease:flags=lanczos"
    )
    steps.append(
        f"pad={cut_list.width}:{cut_list.height}:(ow-iw)/2:"
        + ("0" if cut.caption else "(oh-ih)/2")
        + ":white"
    )
    if cut.speed != 1.0:
        steps.append(f"setpts=PTS/{cut.speed:g}")
    steps.append(f"fps={cut_list.fps}")
    picture = ",".join(steps)
    seconds = cut.seconds
    return (
        f"[0:v]{picture}[p];[p][1:v]overlay=0:0,"
        f"fade=t=in:st=0:d={FADE:g},fade=t=out:st={max(0.0, seconds - FADE):.3f}:d={FADE:g},"
        f"format=yuv420p[v]"
    )


def part_command(cut: Cut, cut_list: CutList, caption: Path, out: Path) -> list[str]:
    return [
        ffmpeg(),
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{cut.start:.3f}",
        "-to",
        f"{cut.end:.3f}",
        "-i",
        str(cut.clip),
        "-i",
        str(caption),
        "-filter_complex",
        filters(cut, cut_list),
        "-map",
        "[v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        str(out),
    ]


def join_command(parts: list[Path], listing: Path, out: Path) -> list[str]:
    listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
    return [
        ffmpeg(),
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(out),
    ]


def poster_command(cut_list: CutList) -> list[str]:
    at = min(cut_list.poster_at, max(0.0, cut_list.seconds - 0.5))
    return [
        ffmpeg(),
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{at:.3f}",
        "-i",
        str(cut_list.out),
        "-frames:v",
        "1",
        str(cut_list.poster),
    ]


def cut(cut_list: CutList, *, skip_missing: bool = False) -> None:
    absent = missing(cut_list)
    if absent and not skip_missing:
        lines = [f"  {shown(c.clip)}  --  {how_to_make(c.clip)}" for c in absent]
        raise SystemExit(
            "These clips are not there; record them first, or pass --skip-missing:\n"
            + "\n".join(lines)
        )
    cuts = [c for c in cut_list.cuts if c.clip.is_file()]
    if not cuts:
        raise SystemExit("No clips at all; nothing to cut.")

    with tempfile.TemporaryDirectory(prefix="loriini-cut-") as scratch:
        folder = Path(scratch)
        parts: list[Path] = []
        for index, one in enumerate(cuts, start=1):
            caption = folder / f"caption{index}.png"
            caption_image(one.caption, cut_list.width, cut_list.height).save(caption)
            part = folder / f"part{index:02d}.mp4"
            subprocess.run(part_command(one, cut_list, caption, part), check=True)
            parts.append(part)
            pace = f" at {one.speed:g}x" if one.speed != 1 else ""
            print(
                f"  cut {index}: {one.clip.name} {one.start:g}-{one.end:g} s{pace}, "
                f"{one.seconds:.1f} s on screen"
            )
        cut_list.out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(join_command(parts, folder / "parts.txt", cut_list.out), check=True)
    subprocess.run(poster_command(cut_list), check=True)
    total = sum(c.seconds for c in cuts)
    print(
        f"wrote {shown(cut_list.out)}: {len(cuts)} cuts, {total:.1f} s, "
        f"{cut_list.out.stat().st_size / 1_000_000:.1f} MB; poster {shown(cut_list.poster)}"
        + (f"; {len(absent)} clip(s) skipped" if absent else "")
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("list", nargs="?", type=Path, default=LIST, help="The cut list (YAML).")
    parser.add_argument("--skip-missing", action="store_true", help="Cut what there is.")
    args = parser.parse_args(argv)
    try:
        cut_list = read(args.list)
    except CutListError as error:
        raise SystemExit(f"{args.list}: {error}") from error
    cut(cut_list, skip_missing=args.skip_missing)


if __name__ == "__main__":
    main()
