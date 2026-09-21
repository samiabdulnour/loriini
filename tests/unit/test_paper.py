"""The arithmetic that lays a study over a plan on the sheet."""

from __future__ import annotations

import math

import pytest

from sun_study.archicad.paper import PaperFrame, PaperSink, onto_paper


def test_the_project_origin_lands_on_the_anchor_and_a_metre_is_five_millimetres() -> None:
    frame = PaperFrame(origin=(0.4, 0.3), scale=200.0)

    assert frame.point(0.0, 0.0) == (0.4, 0.3)
    x, y = frame.point(10.0, -4.0)
    assert x == pytest.approx(0.45) and y == pytest.approx(0.28)


def test_a_drawing_shrunk_to_fit_shrinks_what_is_laid_over_it() -> None:
    frame = PaperFrame(origin=(0.0, 0.0), scale=100.0, ratio=0.5)
    assert frame.point(20.0, 0.0) == pytest.approx((0.1, 0.0))


def test_a_turned_drawing_turns_the_study_with_it() -> None:
    frame = PaperFrame(origin=(1.0, 1.0), scale=1.0, angle_rad=math.pi / 2.0)
    assert frame.point(2.0, 0.0) == pytest.approx((1.0, 3.0))


def test_a_frame_that_places_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="above zero"):
        PaperFrame(origin=(0.0, 0.0), scale=0.0)


def test_a_clip_frame_holds_the_whole_box_even_when_turned() -> None:
    frame = PaperFrame(origin=(0.0, 0.0), scale=1.0, angle_rad=math.pi / 4.0)
    box = frame.box(0.0, 0.0, 1.0, 1.0)
    assert box["xMin"] == pytest.approx(-math.sqrt(0.5))
    assert box["xMax"] == pytest.approx(math.sqrt(0.5))
    assert box["yMin"] == pytest.approx(0.0) and box["yMax"] == pytest.approx(math.sqrt(2.0))


def test_a_hatch_loses_its_storey_and_layer_and_keeps_its_pens() -> None:
    frame = PaperFrame(origin=(0.1, 0.1), scale=100.0)
    hatch = {
        "coordinates": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 10.0, "y": 5.0}],
        "layerIndex": 135,
        "floorInd": 14,
        "fillPenIndex": 83,
        "showArea": False,
    }

    moved = onto_paper(hatch, frame)

    assert "layerIndex" not in moved and "floorInd" not in moved
    assert moved["fillPenIndex"] == 83 and moved["showArea"] is False
    assert moved["coordinates"][1] == pytest.approx({"x": 0.2, "y": 0.1})
    assert hatch["coordinates"][1] == {"x": 10.0, "y": 0.0}, "the original is not touched"


def test_an_add_on_fill_moves_every_contour_holes_included() -> None:
    frame = PaperFrame(origin=(0.0, 0.0), scale=10.0)
    fill = {
        "contours": [
            {"points": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 0.0, "y": 10.0}]},
            {"points": [{"x": 2.0, "y": 2.0}, {"x": 3.0, "y": 2.0}, {"x": 2.0, "y": 3.0}]},
        ],
        "floorIndex": 3,
        "elementId": "SOLAR 2-3hrs",
        "contourPen": 0,
    }

    moved = onto_paper(fill, frame)

    assert "floorIndex" not in moved and "elementId" not in moved
    assert moved["contourPen"] == 0
    assert moved["contours"][1]["points"][0] == pytest.approx({"x": 0.2, "y": 0.2})


def test_a_text_is_as_tall_on_the_sheet_and_turns_with_the_drawing() -> None:
    frame = PaperFrame(origin=(0.5, 0.5), scale=200.0, angle_rad=0.1)
    text = {
        "coordinate": {"x": 0.0, "y": 0.0, "z": 0.0},
        "text": "A.401\n118 min",
        "height": 2.5,
        "angle": 0.2,
        "floorIndex": 14,
    }

    moved = onto_paper(text, frame)

    assert moved["coordinate"] == pytest.approx({"x": 0.5, "y": 0.5, "z": 0.0})
    assert moved["height"] == pytest.approx(0.0025), "a layout measures a height in metres"
    assert moved["angle"] == pytest.approx(0.3)
    assert "floorIndex" not in moved


def test_two_nodes_that_land_on_one_point_of_the_sheet_become_one() -> None:
    """13 microns apart at 1:300, and Archicad refused that polyline alone."""
    frame = PaperFrame(origin=(0.0, 0.0), scale=300.0)
    line = {
        "coordinates": [
            {"x": 0.0, "y": 0.0},
            {"x": 0.004, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 5.0},
            {"x": 0.0, "y": 0.0},
        ]
    }

    moved = onto_paper(line, frame)["coordinates"]

    assert len(moved) == 4
    assert moved[0] == moved[-1], "the closing point is what closes it, and stays"


def test_the_sink_hands_each_drawing_its_own_storey_and_what_named_none() -> None:
    sink = PaperSink()
    sink.add(
        "14 | Results 09:00",
        fills=[{"coordinates": [], "floorInd": 14}, {"coordinates": [], "floorInd": 15}],
        polylines=[{"coordinates": [], "floorInd": 14}],
        texts=[
            {"coordinate": {"x": 0, "y": 0}, "floorIndex": 14},
            {"coordinate": {"x": 1, "y": 1}},
        ],
        outline=False,
    )
    sink.add("14 | Results 12:00", fills=[{"coordinates": [], "floorInd": 14}])

    nine = sink.take("14 | Results 09:00", 14)

    assert (len(nine.fills), len(nine.polylines), len(nine.texts)) == (1, 1, 2)
    assert nine.outline is False
    assert sink.storeys("14 | Results 09:00") == [14, 15]
    assert len(sink.take("14 | Results 12:00", 14)) == 1
    assert len(sink.take("14 | Results 15:00", 14)) == 0, "asked for nothing, handed nothing"
