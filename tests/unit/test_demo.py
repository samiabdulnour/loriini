"""The demo videos' scripts: the cut list says what the cut does, and the
fixture's export carries what the animation draws (docs/website.md).

ffmpeg and a browser are not asked for here. What is tested is what can be
wrong silently: a cut list read as something other than it says, a filter
graph that forgets the caption band or the pace, an export whose cells and
bits have come apart.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


@pytest.fixture
def demo_cut() -> Any:
    """The script, imported the way it is run: from its folder."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("demo_cut")
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.fixture
def cut_list(tmp_path: Path) -> Path:
    path = tmp_path / "works.yaml"
    path.write_text(
        """
out: site/demo.mp4
poster: site/demo-poster.png
poster_at: 4
size: [1280, 720]
fps: 30
cuts:
  - clip: assets/demo/captures/window.mp4
    from: 1.0
    to: 14.5
    caption: "An address, four ticks, Run."
  - clip: assets/demo/captures/archicad-site.mp4
    to: 60
    speed: 4
    crop: [0, 0, 1920, 1080]
    caption: ""
""",
        encoding="utf-8",
    )
    return path


# -- the cut list ------------------------------------------------------------
def test_the_list_is_read_as_it_says(demo_cut: Any, cut_list: Path) -> None:
    read = demo_cut.read(cut_list)
    assert read.out == ROOT / "site" / "demo.mp4"
    assert (read.width, read.height, read.fps) == (1280, 720, 30)
    first, second = read.cuts
    assert (first.start, first.end, first.speed, first.crop) == (1.0, 14.5, 1.0, None)
    assert first.caption == "An address, four ticks, Run."
    assert first.clip == ROOT / "assets" / "demo" / "captures" / "window.mp4"
    assert (second.start, second.end, second.speed) == (0.0, 60.0, 4.0)
    assert second.crop == (0, 0, 1920, 1080)
    assert second.seconds == pytest.approx(15.0), "a minute at four times is fifteen seconds"
    assert read.seconds == pytest.approx(13.5 + 15.0)


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ("cuts: []", "no cuts"),
        ("cuts:\n  - from: 1\n    to: 2", "names no clip"),
        ("cuts:\n  - clip: a.mp4\n    from: 5\n    to: 2", "not after"),
        ("cuts:\n  - clip: a.mp4\n    to: 2\n    speed: 0", "speed must be positive"),
        ("cuts:\n  - clip: a.mp4\n    to: 2\n    crop: [1, 2]", "crop must be"),
        ("cuts:\n  - clip: a.mp4", "has no 'to'"),
    ],
)
def test_a_list_that_says_too_little_is_refused(
    demo_cut: Any, tmp_path: Path, body: str, complaint: str
) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(demo_cut.CutListError, match=complaint):
        demo_cut.read(path)


def test_a_missing_clip_names_the_script_that_records_it(demo_cut: Any, cut_list: Path) -> None:
    read = demo_cut.read(cut_list)
    absent = demo_cut.missing(read)
    names = {cut.clip.name for cut in absent}
    assert "archicad-site.mp4" in names
    assert "demo_capture_archicad" in demo_cut.how_to_make(ROOT / "archicad-site.mp4")
    assert "demo_capture_window" in demo_cut.how_to_make(ROOT / "window.mp4")


def test_the_filter_graph_paces_crops_and_captions(demo_cut: Any, cut_list: Path) -> None:
    read = demo_cut.read(cut_list)
    captioned, paced = read.cuts
    graph = demo_cut.filters(captioned, read)
    # The picture sits above the band, so the foot of the window stays seen.
    assert f"scale=1280:{720 - demo_cut.BAND}" in graph
    assert "pad=1280:720:(ow-iw)/2:0:white" in graph
    assert "overlay=0:0" in graph and "fade=t=in" in graph and "fade=t=out" in graph
    assert "setpts" not in graph, "life speed needs no pacing"
    graph = demo_cut.filters(paced, read)
    assert "crop=1920:1080:0:0" in graph
    assert "setpts=PTS/4" in graph
    assert "scale=1280:720:" in graph, "no caption, the whole frame"
    assert f"fade=t=out:st={15.0 - demo_cut.FADE:.3f}" in graph


def test_the_caption_is_drawn_along_the_foot(demo_cut: Any) -> None:
    image = demo_cut.caption_image("An address, four ticks, Run.", 640, 360)
    assert image.size == (640, 360)
    assert image.getpixel((320, 20))[3] == 0, "clear above the band"
    assert image.getpixel((320, 360 - demo_cut.BAND // 2))[3] > 0, "paper in the band"
    assert demo_cut.caption_image("", 640, 360).getpixel((320, 340))[3] == 0, "no caption, no band"


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0
    if __import__("shutil").which("ffmpeg")
    else True,
    reason="needs ffmpeg",
)
def test_two_clips_are_cut_into_one(demo_cut: Any, tmp_path: Path) -> None:
    """End to end on two synthetic clips: the result is as long as the cuts
    say, and the poster is a frame of it."""
    for name, colour in (("a.mp4", "red"), ("b.mp4", "blue")):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={colour}:s=320x240:r=10:d=3",
                "-pix_fmt",
                "yuv420p",
                str(tmp_path / name),
            ],
            check=True,
        )
    listing = tmp_path / "list.yaml"
    listing.write_text(
        f"""
out: {tmp_path / "out.mp4"}
poster: {tmp_path / "poster.png"}
poster_at: 1
size: [320, 180]
fps: 10
cuts:
  - clip: {tmp_path / "a.mp4"}
    to: 2
    caption: "Red."
  - clip: {tmp_path / "b.mp4"}
    from: 1
    to: 3
    speed: 2
""",
        encoding="utf-8",
    )
    read = demo_cut.read(listing)
    demo_cut.cut(read)
    assert (tmp_path / "out.mp4").is_file() and (tmp_path / "poster.png").is_file()
    probed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(tmp_path / "out.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert float(probed) == pytest.approx(3.0, abs=0.25), "two seconds, and two at double speed"


# -- the workstation's screen ------------------------------------------------
@pytest.fixture
def demo_capture_archicad() -> Any:
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("demo_capture_archicad")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_a_windows_screen_is_grabbed_at_its_offset(demo_capture_archicad: Any) -> None:
    grabbed = demo_capture_archicad.grab(
        (10, 20, 1600, 900), Path("clip.mp4"), "ffmpeg", platform="win32"
    )
    assert grabbed[grabbed.index("-f") + 1] == "gdigrab"
    assert grabbed[grabbed.index("-offset_x") + 1] == "10"
    assert grabbed[grabbed.index("-video_size") + 1] == "1600x900"
    assert grabbed[grabbed.index("-i") + 1] == "desktop"
    assert "-vf" not in grabbed


def test_a_mac_screen_is_named_and_its_region_cut_out(demo_capture_archicad: Any) -> None:
    grabbed = demo_capture_archicad.grab(
        (0, 50, 2881, 1601), Path("clip.mp4"), "ffmpeg", platform="darwin"
    )
    assert grabbed[grabbed.index("-f") + 1] == "avfoundation"
    assert grabbed[grabbed.index("-i") + 1] == "Capture screen 0:none", "the screen, no sound"
    picture = grabbed[grabbed.index("-vf") + 1]
    assert picture.startswith("crop=2880:1600:0:50,"), "even sizes, at the region's corner"
    assert "scale='min(1920,iw)':-2" in picture
    whole = demo_capture_archicad.grab(None, Path("c.mp4"), "ffmpeg", platform="darwin", screen="2")
    assert whole[whole.index("-i") + 1] == "2:none"
    assert not whole[whole.index("-vf") + 1].startswith("crop")


def test_no_other_screen_is_pretended(demo_capture_archicad: Any) -> None:
    with pytest.raises(SystemExit, match="Windows or a Mac"):
        demo_capture_archicad.grab(None, Path("c.mp4"), "ffmpeg", platform="linux")


# -- the fixture's export ----------------------------------------------------
@pytest.fixture(scope="module")
def fixture_document() -> dict[str, Any]:
    """The committed export, read back out of its script."""
    text = (ROOT / "assets" / "demo" / "fixture.js").read_text(encoding="utf-8")
    body = text.split("var FIXTURE = ", 1)[1].strip().rstrip(";")
    loaded: dict[str, Any] = json.loads(body)
    return loaded


def test_the_export_is_the_engines_own_answer(fixture_document: dict[str, Any]) -> None:
    """The figures the page quotes are the figures the tests already hold
    the engine to: the golden file's minutes, the fixture's four apartments."""
    golden = json.loads(
        (ROOT / "tests" / "fixtures" / "golden_sample_building.json").read_text(encoding="utf-8")
    )
    by_name = {a["name"]: a for a in fixture_document["apartments"]}
    assert set(by_name) == set(golden["living_room"])
    for name, minutes in golden["living_room"].items():
        assert by_name[name]["living_minutes"] == pytest.approx(minutes, abs=0.01)
    for name, minutes in golden["open_space"].items():
        assert by_name[name]["open_space_minutes"] == pytest.approx(minutes, abs=0.01)
    summary = fixture_document["summary"]
    assert summary["counted"] == 4 and summary["meeting_minimum"] == 3 and summary["complies"]


def test_every_cell_has_its_bits_and_its_minutes(fixture_document: dict[str, Any]) -> None:
    instants = len(fixture_document["times"])
    assert instants == 37 and len(fixture_document["sun"]) == instants
    skin = fixture_document["skin"]
    cells = sum(len(panel["cells"]) for panel in skin["panels"])
    assert len(skin["minutes"]) == cells
    assert len(skin["lit"]) == instants and all(len(row) == cells for row in skin["lit"])
    ground = fixture_document["ground"]
    assert len(ground["minutes"]) == len(ground["cells"])
    assert all(len(row) == len(ground["cells"]) for row in ground["lit"])
    # The bits sum to the minutes, under the ruleset's trapezoidal weights.
    step = 360 / (instants - 1)
    weights = [step / 2 if i in (0, instants - 1) else step for i in range(instants)]
    for index in (0, cells // 2, cells - 1):
        summed = sum(w for w, row in zip(weights, skin["lit"], strict=True) if row[index] == "1")
        assert summed == pytest.approx(skin["minutes"][index], abs=0.01)


def test_the_measured_surfaces_are_marked(fixture_document: dict[str, Any]) -> None:
    marks = {panel["measured"] for panel in fixture_document["skin"]["panels"]}
    assert marks == {"", "glazing", "open space"}
