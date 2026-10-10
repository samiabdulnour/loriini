"""A larger model: bounded memory, a readable log, and one bad fill not fatal.

Roadmap R1. The shadow diagram failed outright on a larger model, and the
three ways it can -- the caster's memory, the grid's size, a fill Archicad
will not take -- are each tested here against what the fix promises: the
same answer in bounded memory, a log that says how big the job was and what
stretched it, and a refused fill left out and named rather than the run lost.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sun_study.app import run_log
from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.shadows import draw_shadow_series
from sun_study.core import analysis
from sun_study.core.analysis import candidate_rays, sunlit_matrix
from sun_study.core.geometry import box
from sun_study.core.occlusion import Occluder
from sun_study.core.resources import Stopwatch, duration_text, peak_memory_bytes, size_text
from sun_study.core.shadow import cast_shadows, default_sources, ground_plane_grid
from sun_study.ingest.ifc import IfcElement
from sun_study.ingest.scene import far_layers
from tests.unit.test_shadow_draw import ShadowTransport, series

WEST_45 = np.array([[-1.0, 0.0, 1.0]]) / np.sqrt(2.0)


def _grid() -> Any:
    return ground_plane_grid(
        (np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        datum_m=0.0,
        spacing_m=2.0,
        margin_m=40.0,
    )


def _suns() -> Any:
    return np.array(
        [
            [-1.0, 0.0, 1.0],
            [0.3, -0.8, 0.5],
            [0.0, 0.0, -1.0],  # below the horizon: nothing cast for it
        ]
    ) / np.array([[np.sqrt(2.0)], [np.sqrt(0.98)], [1.0]])


# -- the caster, a block at a time ---------------------------------------------


def test_casting_in_blocks_gives_the_same_answer_bit_for_bit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grid = _grid()
    occluder = Occluder(box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)))
    whole = sunlit_matrix(grid, occluder, _suns())

    # A block of seven samples: every block boundary falls somewhere odd.
    monkeypatch.setattr(analysis, "SAMPLE_BLOCK", 7)
    told: list[tuple[int, int]] = []
    blocked = sunlit_matrix(
        grid, occluder, _suns(), progress=lambda done, total: told.append((done, total))
    )

    assert blocked.shape == whole.shape
    assert np.array_equal(blocked, whole)
    assert whole[:, 0].any() and not whole[:, 0].all()  # a real shadow, not a blank
    assert not whole[:, 2].any()  # the sun is down: lit nowhere
    # Told after every block, the last time with everything done.
    assert told[-1] == (len(grid), len(grid))
    assert len(told) == -(-len(grid) // 7)
    assert [done for done, _ in told] == sorted(done for done, _ in told)


def test_the_rays_a_cast_will_need_are_counted_before_it_starts() -> None:
    grid = _grid()
    # An upward grid faces both suns that are up, and not the one below.
    assert candidate_rays(grid, _suns()) == 2 * len(grid)


def test_a_cast_says_what_it_is_casting_and_against_what() -> None:
    said: list[str] = []
    cast_shadows(
        _grid(),
        sources=default_sources(
            box((-40.0, -5.0, 0.0), (-30.0, 5.0, 10.0)),
            box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
        ),
        sun_vectors=np.repeat(WEST_45, 2, axis=0),
        moments=[dt.datetime(2024, 6, 21, 9 + i, tzinfo=dt.UTC) for i in range(2)],
        labels=["9AM", "10AM"],
        spacing_m=2.0,
        say=said.append,
    )
    casts = [line for line in said if "casting" in line]
    assert len(casts) == 2  # one per source, never more
    assert all("samples x 2 instants against" in line for line in casts)
    assert all("triangles" in line for line in casts)


# -- what stretches the grid -----------------------------------------------------


def _element(layer: str, low: tuple[float, float, float], high: tuple[float, float, float]) -> Any:
    return IfcElement(
        global_id=layer,
        ifc_class="IfcBuildingElementProxy",
        name="",
        long_name="",
        predefined_type="",
        storey=None,
        mesh=box(low, high),
        layer=layer,
    )


def test_a_solid_far_from_every_legend_row_is_named_with_its_distance() -> None:
    tower = _element("05 | Mass.Proposed", (0, 0, 0), (30, 30, 90))
    neighbour = _element("03 | Site Context.Buildings", (60, 0, 0), (90, 30, 20))
    parked = _element("00 | Temp Delete", (1530, 0, 0), (1540, 10, 10))

    far = far_layers([tower, neighbour, parked], [tower, neighbour])

    assert [layer for layer, _ in far] == ["00 | Temp Delete"]
    assert far[0][1] == pytest.approx(1440.0)
    # Nothing casting, nothing to be far from.
    assert far_layers([tower, parked], []) == ()


# -- a refused fill costs that fill ------------------------------------------------


class RefusingTransport(ShadowTransport):
    """A project where Archicad will not draw certain fills.

    Refuses a whole ``CreateFills`` batch whenever it carries one of them, as
    the add-on does: one undo step, rolled back entire.
    """

    def __init__(self, labels: list[str], refuse: set[str]) -> None:
        super().__init__(labels)
        self.refuse = refuse

    def _answer(self, command: str, given: dict[str, Any]) -> dict[str, Any]:
        if command == "CreateFills" and any(_key(fill) in self.refuse for fill in given["fills"]):
            return {
                "success": False,
                "error": {"code": -2130313112, "message": "Archicad refused to create fill"},
            }
        return super()._answer(command, given)


def _key(fill: dict[str, Any]) -> str:
    """One fill, whole: its outline, layer and colour. Two hours' shadows can
    share an outline; they cannot share a layer."""
    return json.dumps(fill, sort_keys=True)


def _sent_fills(transport: ShadowTransport) -> list[dict[str, Any]]:
    return [fill for call in transport.all_parameters_for("CreateFills") for fill in call["fills"]]


def test_one_fill_archicad_will_not_draw_is_left_out_and_named() -> None:
    drawn = series()
    plain = ShadowTransport(["9AM", "12PM"])
    everything = draw_shadow_series(ArchicadConnection(plain), drawn)
    bad = _key(_sent_fills(plain)[1])

    transport = RefusingTransport(["9AM", "12PM"], {bad})
    report = draw_shadow_series(ArchicadConnection(transport), drawn)

    assert report.fills == everything.fills - 1
    assert len(report.refused) == 1
    assert "corners around" in report.refused[0]
    assert "refused 1 fill" in report.describe()
    # Halved down to it: more than one request, and every other fill drawn.
    assert len(transport.all_parameters_for("CreateFills")) > 1
    # Each stamped ID still belongs to the fill it was drawn for: one fewer.
    assert len(transport.stamped) == len(plain.stamped) - 1


def test_a_refusal_of_every_fill_still_stops_the_run() -> None:
    drawn = series()
    plain = ShadowTransport(["9AM", "12PM"])
    draw_shadow_series(ArchicadConnection(plain), drawn)
    every = {_key(fill) for fill in _sent_fills(plain)}

    transport = RefusingTransport(["9AM", "12PM"], every)
    with pytest.raises(ArchicadError, match="refuses every fill"):
        draw_shadow_series(ArchicadConnection(transport), drawn)


# -- the numbers a log is read by ---------------------------------------------------


def test_durations_and_sizes_read_as_a_person_says_them() -> None:
    assert duration_text(0.42) == "0.4 s"
    assert duration_text(41.2) == "41 s"
    assert duration_text(192.0) == "3 min 12 s"
    assert duration_text(3840.0) == "1 h 04 min"
    assert size_text(245 * 1024**2) == "245 MB"
    assert size_text(2.1 * 1024**3) == "2.1 GB"
    assert size_text(None) == "unknown"


def test_a_stage_says_how_long_it_took_and_the_memory_so_far() -> None:
    clock = Stopwatch()
    line = clock.said("read the model")
    assert line.startswith("  timing: read the model in ")
    assert "memory at most" in line
    peak = peak_memory_bytes()
    assert peak is None or peak > 1024**2  # a Python with numpy is past a megabyte


# -- the transcript on disk ----------------------------------------------------------


def test_a_run_is_written_to_a_file_as_it_goes(tmp_path: Path) -> None:
    started = dt.datetime(2026, 9, 29, 14, 32, 5)
    log = run_log.RunLog.start(["shadow diagram"], folder=tmp_path, now=started)
    assert log is not None
    log.write("── Shadow diagram ──")
    log.write("  timing: exported the model in 3 min 12 s, memory at most 1.2 GB")

    # Readable before it is closed: a run that takes the process with it
    # still leaves everything up to the moment it went.
    text = log.path.read_text(encoding="utf-8")
    assert log.path.name == "2026-09-29 143205 shadow diagram.log"
    assert text.startswith("Loriini ")
    assert "started 2026-09-29 14:32:05: shadow diagram" in text
    assert text.rstrip().endswith("memory at most 1.2 GB")
    log.close()
    log.write("after closing, nothing and no error")
    assert "after closing" not in log.path.read_text(encoding="utf-8")


def test_only_the_newest_transcripts_are_kept(tmp_path: Path) -> None:
    for day in range(1, 9):
        (tmp_path / f"2026-09-0{day} 090000 run.log").write_text("old", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a log", encoding="utf-8")

    gone = run_log.prune(tmp_path, keep=3)

    assert gone == 5
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == [
        "2026-09-06 090000 run.log",
        "2026-09-07 090000 run.log",
        "2026-09-08 090000 run.log",
        "notes.txt",
    ]


def test_a_folder_that_will_not_take_a_log_does_not_stop_the_run(tmp_path: Path) -> None:
    blocked = tmp_path / "a file, not a folder"
    blocked.write_text("", encoding="utf-8")
    assert run_log.RunLog.start(["yield"], folder=blocked) is None


# -- the shadow command's log ------------------------------------------------------


def _scene(far: tuple[tuple[str, float], ...] = ()) -> Any:
    from sun_study.core.orientation import SiteOrientation
    from sun_study.ingest.scene import ShadowScene

    return ShadowScene(
        sources=default_sources(
            box((-40.0, -5.0, 0.0), (-30.0, 5.0, 10.0)),
            box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
        ),
        bounds=(np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        orientation=SiteOrientation(-33.87, 151.21, "Australia/Sydney", 0.0),
        provenance={},
        far=far,
    )


def _report(monkeypatch: pytest.MonkeyPatch, scene: Any, capsys: Any) -> tuple[int, str]:
    """Run the shadow command's measuring half over a scene, drawing nothing."""
    import typer

    from sun_study import cli
    from sun_study.ingest.scene import MassingConfig

    monkeypatch.setattr(cli, "read_model", lambda path: object())
    monkeypatch.setattr(cli, "read_geo_location", lambda connection: None)
    monkeypatch.setattr(cli, "cross_check_georeferencing", lambda geo, model: None)
    monkeypatch.setattr(cli, "build_shadow_scene", lambda model, config: scene)
    code = 0
    try:
        cli._shadow_report(
            object(),  # type: ignore[arg-type]
            Path("model.loriini"),
            config=MassingConfig(timezone="Australia/Sydney"),
            moments=[dt.datetime(2024, 6, 21, 9 + i, tzinfo=dt.UTC) for i in range(2)],
            labels=["9AM", "10AM"],
            shadow_datum=None,
            shadow_grid=2.0,
            shadow_margin=40.0,
            draw=False,
            sheet=False,
            shadow_storey=0,
            shadow_favourite=None,
            terrain_floor=None,
            edge_tolerance=0.0,
            drawing_scale=1000.0,
            master_layout=None,
            shadow_subset=None,
            check_georeferencing=False,
        )
    except typer.Exit as stopped:
        code = int(stopped.exit_code)
    out = capsys.readouterr()
    return code, out.out + out.err


def test_the_shadow_log_says_each_stage_the_grid_and_the_cast(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, said = _report(monkeypatch, _scene(far=(("00 | Temp Delete", 1440.0),)), capsys)

    assert code == 0, said
    assert "grid 130 x 90 m at 2 m, 40 m past everything: about 2,925 samples" in said
    assert "stretched by '00 | Temp Delete', which has a solid 1,440 m clear" in said
    assert "rays a cast, 2 casts" in said
    assert said.count("  casting ") == 2
    assert "timing: read the model and sorted it into the legend in" in said
    assert "timing: cast and traced the shadows in" in said
    assert "timing: the whole run took" in said


def test_running_out_of_memory_is_said_with_the_way_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from sun_study import cli

    def exhausted(*args: Any, **kwargs: Any) -> Any:
        raise MemoryError("Unable to allocate 8.94 GiB for an array")

    monkeypatch.setattr(cli, "cast_shadows", exhausted)
    code, said = _report(monkeypatch, _scene(), capsys)

    assert code == 2
    assert "Out of memory casting" in said
    assert "--shadow-grid" in said and "shadow-plans" in said
    assert "Unable to allocate 8.94 GiB" in said
