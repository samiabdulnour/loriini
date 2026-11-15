"""Turn the animation page into the video on the *What it makes* page.

    uv run --group demo python scripts/demo_render.py
    uv run --group demo python scripts/demo_render.py --still 8.5 out.png

Opens ``assets/demo/makes.html`` in a headless Chromium, asks it for one
moment after another -- ``demo.seek(t)``, a frame at a time, so the clip is
the same whatever the machine's speed -- and photographs each, then has
ffmpeg join the frames into ``site/demo-makes.mp4``: H.264, the page's own
1280 x 720, a few megabytes, playable in every browser. The poster,
``site/demo-makes.png``, is the frame the page rests on, so a reader with
motion switched off, or the video not yet loaded, sees the verdict.

Needs the ``demo`` dependency group (Playwright) and a Chromium for it:
``uv run --group demo playwright install chromium`` once, or ``--chromium``
pointing at one already on the machine. And ffmpeg on the path. Run it when
the page, the fixture or the engine changes; the video is committed, like
the lorikeet sheet, so the site deploys from a checkout.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "assets" / "demo" / "makes.html"
VIDEO = ROOT / "site" / "demo-makes.mp4"
POSTER = ROOT / "site" / "demo-makes.png"

WIDTH, HEIGHT = 1280, 720
FPS = 30
#: Where the poster is taken: on the verdict, every mark and the summary
#: showing, before the closing caption.
POSTER_AT = 12.4

#: A Chromium the machine already has, named in the environment, so the
#: build need not download one: the cloud session that made this had
#: Playwright's browser at this path and was asked not to fetch another.
CHROMIUM_VAR = "LORIINI_CHROMIUM"


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SystemExit("ffmpeg is not on the path; install it, or point PATH at it.")
    return found


def render(
    *, fps: int, video: Path, poster: Path, chromium: str | None, only_still: float | None
) -> None:
    from playwright.sync_api import sync_playwright

    launch: dict[str, object] = {"args": ["--no-sandbox"]}
    if chromium:
        launch["executable_path"] = chromium

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch)  # type: ignore[arg-type]
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page.goto(PAGE.resolve().as_uri() + "?render")
        page.wait_for_function("window.demo && window.demo.duration > 0")
        # Fonts arrive after the page does; a frame photographed before them
        # is set in the fallback face and the clip flickers at its start.
        page.evaluate("document.fonts.ready")
        duration = float(page.evaluate("window.demo.duration"))

        if only_still is not None:
            page.evaluate(f"window.demo.seek({only_still})")
            page.screenshot(path=str(poster))
            print(f"wrote {poster} at {only_still:.2f} s")
            browser.close()
            return

        frames = round(duration * fps)
        with tempfile.TemporaryDirectory(prefix="loriini-demo-") as scratch:
            folder = Path(scratch)
            for index in range(frames):
                page.evaluate(f"window.demo.seek({index / fps})")
                page.screenshot(path=str(folder / f"f{index:05d}.png"))
                if index % fps == 0:
                    print(f"  {index / fps:4.1f} s of {duration:.1f}", file=sys.stderr)
            page.evaluate(f"window.demo.seek({POSTER_AT})")
            page.screenshot(path=str(poster))
            browser.close()

            video.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    ffmpeg(),
                    "-y",
                    "-loglevel",
                    "error",
                    "-framerate",
                    str(fps),
                    "-i",
                    str(folder / "f%05d.png"),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "22",
                    # Flat colour and hard edges: keep the chroma from
                    # smearing across the cells' grid lines.
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(video),
                ],
                check=True,
            )
        print(
            f"wrote {video.relative_to(ROOT)}: {frames} frames at {fps} fps, "
            f"{duration:.1f} s, {video.stat().st_size / 1_000_000:.1f} MB; "
            f"poster {poster.relative_to(ROOT)} at {POSTER_AT} s"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--video", type=Path, default=VIDEO)
    parser.add_argument("--poster", type=Path, default=POSTER)
    parser.add_argument(
        "--chromium",
        default=os.environ.get(CHROMIUM_VAR) or None,
        help=f"A Chromium to use instead of Playwright's own; ${CHROMIUM_VAR} by default.",
    )
    parser.add_argument(
        "--still",
        nargs=2,
        metavar=("SECONDS", "PNG"),
        help="Write one frame at that moment to that file and stop.",
    )
    args = parser.parse_args(argv)
    if args.still:
        render(
            fps=args.fps,
            video=args.video,
            poster=Path(args.still[1]),
            chromium=args.chromium,
            only_still=float(args.still[0]),
        )
        return
    render(
        fps=args.fps,
        video=args.video,
        poster=args.poster,
        chromium=args.chromium,
        only_still=None,
    )


if __name__ == "__main__":
    main()
