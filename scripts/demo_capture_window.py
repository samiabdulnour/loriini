"""Record the window going through a study, with no Archicad and no screen.

    UV_PROJECT_ENVIRONMENT=.venv-tk uv run --python 3.12 python scripts/demo_capture_window.py

The clip of the window on the *How it works* page has to show the program
as it is, and the program as it is cannot run without an Archicad to read a
project from. So this opens the real ``Window`` over a fake project -- the
same lists the window's tests feed it: a project with its layers, masters
and subsets -- and over a fake run that says what a run says, a line at a
time, while the progress bar goes. Then it does what a colleague does:
opens Site analysis, types an address, switches the panels on, presses Run,
and waits for Done. ffmpeg records the window the whole time, to
``assets/demo/captures/window.mp4``, a raw clip for ``scripts/demo_cut.py``.

On Linux, with no display, it starts an Xvfb of its own and records that,
so the clip can be made on a runner. The window is then set in Inter, the
face the Mac build carries in ``assets/fonts``, served to that X server as
a core font -- the Tk a ``uv``-managed Python brings has no Xft, so it
sees no other kind, and draws it unsmoothed. On Windows it records the
window off the screen it opens on, which is the window exactly as the
office sees it, Segoe UI smoothed and all; that is the clip to publish.
Nothing it does reaches Archicad, the settings or the logs: it points the
user folder somewhere disposable.

Needs a Python with tkinter (the Linux one the project syncs has none; see
``.gitignore`` on ``.venv*``) and ffmpeg on the path.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "demo" / "captures" / "window.mp4"
FPS = 30
DISPLAY = ":99"
#: Where the window stands on the virtual screen, and the screen itself:
#: room for the window at its opening size with a margin the capture leaves.
AT = (20, 20)
SCREEN = "1400x1000x24"

ADDRESS = "26-30 Campsie St, Campsie NSW 2194"
#: Milliseconds a typed character takes, and the pauses between the steps.
KEY_MS = 55
PAUSE_MS = 700


def fake_project() -> None:
    """A project the window can read without an Archicad: the tests' own."""
    from sun_study.app import probe
    from sun_study.archicad.connection import Instance

    probe.running = lambda: [Instance(port=19723, project="26-30 Campsie St")]
    probe.options = lambda port: probe.ProjectOptions(
        project="26-30 Campsie St",
        tapir="1.5.8",
        layers=(
            "01 | Wall.External",
            "01 | Floor.Structural",
            "01 | Floor Overhang.Shadow Calcs",
            "03 | Site Contexts.3D",
            "05 | Dims/Notes.DA",
            "06 | Zone.SEPP 65",
            "06 | Zone.Balcony",
            "06 | Zone.Units",
        ),
        zone_layers=(
            "05 | Dims/Notes.DA",
            "06 | Zone.Balcony",
            "06 | Zone.SEPP 65",
            "06 | Zone.Units",
        ),
        zone_kinds=(
            probe.ZoneKind(layer="06 | Zone.SEPP 65", label="Unit", count=24, area_m2=78.0),
            probe.ZoneKind(layer="06 | Zone.Balcony", label="Balcony", count=24, area_m2=11.5),
            probe.ZoneKind(layer="06 | Zone.Units", label="SC", count=6, area_m2=2.5),
            probe.ZoneKind(layer="05 | Dims/Notes.DA", label="GFA", count=37, area_m2=310.0),
        ),
        combinations=("01 | Plans - DA", "06 | SEPP 65 Export", "12 | IFC ARCH. EXPORT"),
        masters=("A4", "DA A1 - VERTICAL COVER/NO SCALE", "DA A1 - VERTICAL - No Scale"),
        subsets=("ADG DIAGRAMS", "PLANS", "SHADOW DIAGRAMS", "SITE ANALYSIS"),
        overrides=("Clean", "Sun Eye Views", "Zone Colours"),
    )


#: What a run says, by the study's first word, with the seconds each line
#: takes. In the command line's own voice, a few of its own lines among
#: them, and nothing a number could be quoted from: the clip shows that a
#: run talks, not what it found.
SAID: dict[str, list[tuple[float, str]]] = {
    "site": [
        (0.5, "sun-study 0.0.1  --  PROTOTYPE -- NOT VALIDATED FOR SUBMISSION"),
        (0.4, f"  run folder: Documents\\Loriini\\site-analysis\\{ADDRESS.split(',')[0]}"),
        (0.6, "  project location: lat 33.912S lon 151.103E, true north bearing +Y 0.000 deg"),
        (0.9, "fetching the lot from NSW Spatial Services..."),
        (0.8, "fetching the controls from NSW ePlanning..."),
        (0.9, "fetching the contours and the roads..."),
        (0.7, "fetching the stops from Transport for NSW..."),
        (0.6, "fetching the neighbours from OpenStreetMap..."),
        (0.8, "working out the future context from the controls..."),
    ],
}
#: And the last lines, by what the job draws.
DRAWS: dict[str, list[tuple[float, str]]] = {
    "context": [
        (1.1, "drawing the context analysis in the office's colours..."),
        (0.9, "  fitted to '03 | Site Contexts.3D': 0.012 m residual"),
        (0.8, "  worksheet 'ST-01 Context Analysis': 1:2000, the credit along its foot"),
    ],
    "site": [
        (1.0, "drawing the site analysis..."),
        (0.9, "  worksheet 'ST-02 Site Analysis': 1:500, turned to the long boundary"),
    ],
    "summary": [
        (1.0, "drawing the summary of controls on its layout..."),
        (0.8, "  layout 'ST-03 Summary of Controls' on 'DA A1 - VERTICAL - No Scale'"),
    ],
    "model": [
        (1.2, "modelling the terrain and the neighbours..."),
        (0.9, "  terrain mesh from 184 contours; 212 footprints, storeys from the controls"),
        (0.7, "standing the future context in the model..."),
    ],
}


class FakeRun:
    """``runner.Run`` with nobody at the other end: the lines come from here.

    The same shape -- ``start``, ``stop``, ``running``, the two callbacks --
    because the window does not know the difference and must not.
    """

    def __init__(
        self,
        args: Sequence[str],
        *,
        on_line: Callable[[str], None],
        on_done: Callable[[int], None],
        cwd: Path | None = None,
    ) -> None:
        self.args = list(args)
        self._on_line = on_line
        self._on_done = on_done
        self._thread: threading.Thread | None = None
        self._stopped = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._talk, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped = True

    def _script(self) -> list[tuple[float, str]]:
        command = self.args[0] if self.args else ""
        lines = list(SAID.get(command, SAID["site"]))
        # Which of the site's outputs this job draws, from its own flags:
        # the window runs one job per panel, each asking for one thing.
        flags = " ".join(self.args)
        for key, said in DRAWS.items():
            on = f"--{key}" in flags and f"--no-{key}" not in flags
            if key == "model":
                on = "--model" in flags
            if on:
                lines += said
        return lines

    def _talk(self) -> None:
        for wait, line in self._script():
            time.sleep(wait)
            if self._stopped:
                self._on_done(130)
                return
            self._on_line(line)
        time.sleep(0.4)
        self._on_done(0)


def served_fonts() -> str | None:
    """A font path for the X server with Inter on it, or None.

    Built with ``mkfontscale`` and ``mkfontdir`` from the faces the Mac
    build carries, beside the server's own defaults, so Tk can name Inter
    without Xft. Where the tools are missing the server keeps its defaults
    and the window is set in the X server's Helvetica.
    """
    scale, index = shutil.which("mkfontscale"), shutil.which("mkfontdir")
    faces = sorted((ROOT / "assets" / "fonts").glob("Inter-*.ttf"))
    if scale is None or index is None or not faces:
        return None
    folder = Path(tempfile.mkdtemp(prefix="loriini-xfonts-"))
    for face in faces:
        shutil.copy(face, folder)
    subprocess.run([scale, str(folder)], check=True)
    subprocess.run([index, str(folder)], check=True)
    defaults = [
        path
        for path in ("/usr/share/fonts/X11/misc", "/usr/share/fonts/X11/Type1")
        if Path(path).is_dir()
    ]
    return ",".join([str(folder), *defaults])


def recorder(region: tuple[int, int, int, int], out: Path, display: str) -> subprocess.Popen[bytes]:
    """ffmpeg, recording the window's rectangle until told to stop."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is not on the path.")
    x, y, width, height = region
    # An even size: H.264 at 4:2:0 cannot hold an odd one.
    width -= width % 2
    height -= height % 2
    if sys.platform == "win32":
        grab = [
            "-f",
            "gdigrab",
            "-framerate",
            str(FPS),
            "-offset_x",
            str(x),
            "-offset_y",
            str(y),
            "-video_size",
            f"{width}x{height}",
            "-i",
            "desktop",
        ]
    elif sys.platform == "darwin":
        raise SystemExit(
            "On a Mac, record the window with QuickTime: this captures X11 and Windows."
        )
    else:
        grab = [
            "-f",
            "x11grab",
            "-framerate",
            str(FPS),
            "-video_size",
            f"{width}x{height}",
            "-i",
            f"{display}.0+{x},{y}",
        ]
    out.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            *grab,
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
        ],
        stdin=subprocess.PIPE,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--display", default=DISPLAY, help="The X display to make, on Linux.")
    parser.add_argument(
        "--on-screen",
        action="store_true",
        help="Use the display there is instead of starting an Xvfb (Linux).",
    )
    args = parser.parse_args(argv)

    xvfb: subprocess.Popen[bytes] | None = None
    if sys.platform.startswith("linux") and not args.on_screen:
        if shutil.which("Xvfb") is None:
            raise SystemExit("Xvfb is not on the path; install it, or pass --on-screen.")
        fonts = served_fonts()
        xvfb = subprocess.Popen(
            [
                "Xvfb",
                args.display,
                "-screen",
                "0",
                SCREEN,
                "-nolisten",
                "tcp",
                *(["-fp", fonts] if fonts else []),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = args.display
        time.sleep(0.8)

    # The window's settings, logs and key go somewhere disposable.
    scratch = tempfile.mkdtemp(prefix="loriini-demo-")
    os.environ["APPDATA"] = scratch
    try:
        _record(args.out, os.environ.get("DISPLAY", args.display))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if xvfb is not None:
            xvfb.terminate()
            xvfb.wait(timeout=5)


def _record(out: Path, display: str) -> None:
    import tkinter as tk
    from tkinter import font as tkfont

    fake_project()
    from sun_study.app import theme, window

    window.Run = FakeRun  # type: ignore[attr-defined, assignment]

    root = tk.Tk()
    # Off Windows the window would be set in the X server's default face;
    # Inter is what the Mac build carries, and what the web site is set in.
    # A core font is named in lower case, so both spellings are tried.
    if sys.platform != "win32":
        for face in ("Inter", "inter"):
            if face in tkfont.families(root):
                theme.FACE = face
                break
    made = window.Window(root)
    # No pointer: an X server with nobody at it draws its cross in the
    # middle of the screen, and a pointer that never moves is a smudge.
    root.config(cursor="none")
    root.geometry(f"+{AT[0]}+{AT[1]}")
    root.update()
    root.geometry(f"{made.OPENING_WIDTH}x{made.OPENING_HEIGHT}+{AT[0]}+{AT[1]}")
    root.update()
    # The run needs a master layout to put sheets on; a desk has one saved.
    masters = tuple(made.master.cget("values") or ())
    if masters:
        made.master.set(masters[-1])

    region = (root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height())
    ffmpeg = recorder(region, out, display)
    started = time.time()

    def later(ms: int, what: Callable[[], None]) -> None:
        root.after(ms, what)

    def type_address(index: int = 0) -> None:
        if index == 0:
            made.site_address.focus_set()
            made.site_address.delete(0, tk.END)
        if index < len(ADDRESS):
            made.site_address.insert(tk.END, ADDRESS[index])
            later(KEY_MS, lambda: type_address(index + 1))
        else:
            later(PAUSE_MS, lambda: tick(0))

    ticks = [made.do_site_context, made.do_site_site, made.do_site_summary, made.do_site_model]

    def tick(index: int) -> None:
        if index < len(ticks):
            ticks[index].set(True)
            made._sync()
            later(450, lambda: tick(index + 1))
        else:
            later(PAUSE_MS + 300, press_run)

    def press_run() -> None:
        made.go.focus_set()
        made._start()
        later(300, wait_for_done)

    def wait_for_done() -> None:
        if made._running:
            later(200, wait_for_done)
        else:
            later(1800, finish)

    def finish() -> None:
        if ffmpeg.stdin is not None:
            ffmpeg.stdin.write(b"q")
            ffmpeg.stdin.flush()
        ffmpeg.wait(timeout=30)
        root.destroy()

    later(1400, lambda: made._show_section(made.SITE))
    later(1400 + PAUSE_MS + 400, type_address)
    root.mainloop()
    print(
        f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: "
        f"{time.time() - started:.0f} s, {out.stat().st_size / 1_000_000:.1f} MB, "
        f"{region[2]}x{region[3]} at {FPS} fps"
    )


if __name__ == "__main__":
    main()
