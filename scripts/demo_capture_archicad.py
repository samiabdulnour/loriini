"""Record Archicad while Loriini draws into it: the clips the demo is cut from.

    uv run python scripts/demo_capture_archicad.py "26-30 Campsie St, Campsie NSW 2194"
    uv run python scripts/demo_capture_archicad.py --only solar --port 19724
    uv run python scripts/demo_capture_archicad.py --loriini "C:\\Loriini\\Loriini.exe" ...

The one part of the demo the cloud cannot make: a workstation with Archicad
open on a project and the Loriini add-on loaded. For each study this starts
ffmpeg recording the screen, runs the study exactly as the command line
runs it, waits for it to finish, gives Archicad a moment to redraw, and
stops. One raw clip a study, into ``assets/demo/captures/``, named as
``assets/demo/works.yaml`` expects them: ``archicad-site.mp4``,
``archicad-solar.mp4``, ``archicad-shadows.mp4``. ``scripts/demo_cut.py``
then shows the minutes faster than life and lays the captions on.

Before pressing Enter: Archicad filling the screen, on a view worth
watching -- the 3D window for the solar study, the Layout Book for the
sheets -- a plain desktop behind it, nothing else open, notifications off.
The clip is the whole screen unless ``--region`` names a part of it, at 30
frames a second, as long as the study takes. The first run of each study is
also the manual checklist in docs/archicad.md: if a study stops, the clip
stops with it and says so, and the transcript is on the console.

Windows only, with ffmpeg's screen grabber; ffmpeg is a portable exe, so
no administrator rights are needed, and ``--ffmpeg`` names it when it is
not on the path. The study is run from this checkout with the Python it is
run with, or from a packaged build named with ``--loriini``, which carries
the licence key the command line asks for. On a Mac, record with
QuickTime while running the same commands by hand; they are printed first.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "assets" / "demo" / "captures"
TIMEZONE = "Australia/Sydney"
FPS = 30
#: Seconds of screen before the study starts, and after it ends, so the
#: cut has a still to open on and the result to rest on.
LEAD = 2.0
HOLD = 8.0


@dataclass(frozen=True)
class Study:
    name: str
    clip: str
    args: Callable[[argparse.Namespace], list[str]]
    about: str


def _site(o: argparse.Namespace) -> list[str]:
    return ["site", o.address, "--port", str(o.port), "--context", "--site", "--summary"]


def _solar(o: argparse.Namespace) -> list[str]:
    argv = ["archicad-run", "--timezone", TIMEZONE, "--port", str(o.port), "--write"]
    # The office's conventions (docs/workflow.md): the SEPP 65 zones are the
    # apartments, the balconies their open space, `_L` the living-room glazing.
    argv += ["--apartment-zone-layer", o.apartment_layer]
    argv += ["--open-space-zone-layer", o.balcony_layer]
    argv += ["--livable-suffix", o.livable_suffix]
    return argv


def _shadows(o: argparse.Namespace) -> list[str]:
    return [
        "shadow-plans",
        "--timezone",
        TIMEZONE,
        "--port",
        str(o.port),
        "--shadow-date",
        "06-21",
        "--shadow-hour",
        "9,10,11,12,13,14,15",
    ]


STUDIES: tuple[Study, ...] = (
    Study(
        "site",
        "archicad-site.mp4",
        _site,
        "the context analysis, the site analysis and the summary of controls, from the address",
    ),
    Study(
        "solar", "archicad-solar.mp4", _solar, "solar access by apartment, written onto the Zones"
    ),
    Study(
        "shadows",
        "archicad-shadows.mp4",
        _shadows,
        "the shadow diagram as 3D Documents, one an hour, on sheets by day",
    ),
)


def command_prefix(loriini: str | None) -> list[str]:
    """How to run the command line: a packaged build, or this checkout."""
    if loriini:
        return [loriini]
    return [sys.executable, "-u", "-m", "sun_study.cli"]


def grab(region: tuple[int, int, int, int] | None, out: Path, ffmpeg: str) -> list[str]:
    # Read at run time rather than as ``sys.platform`` itself, which a type
    # checker on a Mac or Linux would take as settled and the rest as dead.
    windows = sys.platform.startswith("win")
    if not windows:
        raise SystemExit(
            "This records a Windows screen. On a Mac, record with QuickTime while running "
            "the commands printed by --dry-run."
        )
    source: list[str] = ["-f", "gdigrab", "-framerate", str(FPS)]
    if region is not None:
        x, y, width, height = region
        source += ["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{width}x{height}"]
    source += ["-i", "desktop"]
    return [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        *source,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]


def record(
    study: Study, argv: Sequence[str], *, grabber: list[str], out: Path, lead: float, hold: float
) -> int:
    """One clip: the screen from before the study starts to after it ends."""
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n== {study.name}: {study.about}")
    print("   " + " ".join(shlex.quote(word) for word in argv))
    recorder = subprocess.Popen(grabber, stdin=subprocess.PIPE)
    try:
        time.sleep(lead)
        code = subprocess.run(argv, check=False).returncode
        if code != 0:
            print(f"   the study stopped with exit code {code}; the clip stops here too.")
        time.sleep(hold if code == 0 else 1.0)
    finally:
        if recorder.stdin is not None:
            recorder.stdin.write(b"q")
            recorder.stdin.flush()
        recorder.wait(timeout=60)
    if out.is_file():
        print(f"   wrote {out.relative_to(ROOT)}: {out.stat().st_size / 1_000_000:.1f} MB")
    return code


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "address",
        nargs="?",
        default="26-30 Campsie St, Campsie NSW 2194",
        help="The site, for the site analysis. NSW only.",
    )
    parser.add_argument("--port", type=int, default=19723, help="Which Archicad to talk to.")
    parser.add_argument(
        "--only",
        action="append",
        choices=[s.name for s in STUDIES],
        help="Record this study only; repeatable.",
    )
    parser.add_argument("--loriini", help="A packaged Loriini.exe to run the studies with.")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"), help="Where ffmpeg is.")
    parser.add_argument(
        "--region", help="x,y,width,height of the screen to record; all of it by default."
    )
    parser.add_argument("--lead", type=float, default=LEAD)
    parser.add_argument("--hold", type=float, default=HOLD)
    parser.add_argument("--apartment-layer", default="06 | Zone.SEPP 65")
    parser.add_argument("--balcony-layer", default="06 | Zone.Balcony")
    parser.add_argument("--livable-suffix", default="_L")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands and stop.")
    args = parser.parse_args(argv)

    region = None
    if args.region:
        parts = [int(value) for value in args.region.split(",")]
        if len(parts) != 4:
            raise SystemExit("--region takes x,y,width,height")
        region = (parts[0], parts[1], parts[2], parts[3])

    wanted = [s for s in STUDIES if not args.only or s.name in args.only]
    prefix = command_prefix(args.loriini)
    if args.dry_run:
        for study in wanted:
            print(
                f"{study.name}: " + " ".join(shlex.quote(w) for w in [*prefix, *study.args(args)])
            )
        return
    if not args.ffmpeg:
        raise SystemExit("ffmpeg is not on the path; name it with --ffmpeg.")

    print(
        "Archicad on the screen, on the project, the add-on loaded? Enter to start, Ctrl-C to stop."
    )
    try:
        input()
    except KeyboardInterrupt:
        return
    failed = 0
    for study in wanted:
        out = CAPTURES / study.clip
        code = record(
            study,
            [*prefix, *study.args(args)],
            grabber=grab(region, out, args.ffmpeg),
            out=out,
            lead=args.lead,
            hold=args.hold,
        )
        failed += code != 0
    print(
        "\nNow: uv run python scripts/demo_cut.py"
        + (f"  ({failed} study(ies) stopped early)" if failed else "")
    )


if __name__ == "__main__":
    main()
