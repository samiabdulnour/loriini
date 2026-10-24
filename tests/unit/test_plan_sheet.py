"""The combined shadow-plan sheet (D138): the fitted scale, the window of the
plan, the stack's own pen set, and the legend and site outline on the sheet."""

from __future__ import annotations

from typing import Any

import pytest

from sun_study.archicad import plan_sheet
from sun_study.archicad.connection import ArchicadConnection
from sun_study.archicad.draw import Pen
from sun_study.archicad.layout import LayoutSheet
from sun_study.archicad.plan_sheet import (
    PlanWindow,
    draw_legend_and_outline,
    fitted_scale,
    legend_pen_set,
    nearest_pen,
    plan_window,
)


class Project:
    """An Archicad that answers from a script, add-on and official commands alike."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = {"GetAddOnVersion": {"version": "1.5.8"}, **answers}
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["command"] == "API.ExecuteAddOnCommand":
            name = payload["parameters"]["addOnCommandId"]["commandName"]
            given = payload["parameters"].get("addOnCommandParameters") or {}
            self.sent.append((name, given))
            answer = self.answers[name]
            answer = answer(given) if callable(answer) else answer
            return {"succeeded": True, "result": {"addOnCommandResponse": answer}}
        name = payload["command"]
        given = payload.get("parameters") or {}
        self.sent.append((name, given))
        answer = self.answers[name]
        return {"succeeded": True, "result": answer(given) if callable(answer) else answer}

    def asked(self, name: str) -> list[dict[str, Any]]:
        return [given for command, given in self.sent if command == name]


def test_the_scale_is_the_largest_standard_one_the_window_fits_a_cell_at() -> None:
    """The sample project: 421 m in a 230 x 540 mm cell needs 1:1990, so 1:2000;
    the same site in a cell twice as wide fits at 1:1000."""
    site = PlanWindow(-183.0, -187.0, 238.0, 234.0)
    assert fitted_scale(site, (230.0, 540.0)) == 2000
    assert fitted_scale(site, (460.0, 540.0)) == 1000
    assert fitted_scale(PlanWindow(0.0, 0.0, 40.0, 30.0), (230.0, 540.0)) == 200
    assert fitted_scale(PlanWindow(0.0, 0.0, 30000.0, 10.0), (230.0, 540.0)) == 142000


def test_the_window_is_the_model_on_the_layers_the_combinations_show() -> None:
    """Read-only, by layer: a wall on a shown layer counts, one on a hidden
    layer does not, and a dimension on a shown layer does not either, since
    a document draws no annotation."""
    project = Project(
        {
            "GetAttributesByType": lambda given: {
                "attributes": [
                    {"attributeId": {"guid": "L-SHOWN"}, "index": 5, "name": "Shown"},
                    {"attributeId": {"guid": "L-HIDDEN"}, "index": 6, "name": "Hidden"},
                ]
                if given["attributeType"] == "Layer"
                else [{"attributeId": {"guid": "C1"}, "name": "15 | Shadow Plans EXISTING"}]
            },
            "GetLayerCombinations": {
                "layerCombinations": [
                    {
                        "layerCombination": {
                            "layers": [
                                {"attributeId": {"guid": "L-SHOWN"}, "isHidden": False},
                                {"attributeId": {"guid": "L-HIDDEN"}, "isHidden": True},
                            ]
                        }
                    }
                ]
            },
            "API.GetAllElements": {
                "elements": [{"elementId": {"guid": g}} for g in ("W1", "W2", "D1")]
            },
            "GetDetailsOfElements": {
                "detailsOfElements": [
                    {"type": "Wall", "layerIndex": 5},
                    {"type": "Wall", "layerIndex": 6},
                    {"type": "Dimension", "layerIndex": 5},
                ]
            },
            "API.Get2DBoundingBoxes": lambda given: {
                "boundingBoxes2D": [
                    {"boundingBox2D": {"xMin": -10.0, "yMin": 0.0, "xMax": 30.0, "yMax": 20.0}}
                    for _ in given["elements"]
                ]
            },
        }
    )
    window = plan_window(ArchicadConnection(project), ["15 | Shadow Plans EXISTING"])
    assert window == PlanWindow(-10.0, 0.0, 30.0, 20.0)
    (boxes,) = project.asked("API.Get2DBoundingBoxes")
    assert boxes["elements"] == [{"elementId": {"guid": "W1"}}], "only the shown wall"
    assert window.centre == (10.0, 10.0)


def test_the_pen_set_is_a_copy_of_the_source_with_the_legend_colours() -> None:
    project = Project(
        {
            "CreatePenTables": {"attributeIds": [{"attributeId": {"guid": "NEW"}}]},
            "GetAttributesByType": {
                "attributes": [{"attributeId": {"guid": "NEW"}, "index": 17, "name": "x"}]
            },
        }
    )
    index = legend_pen_set(
        ArchicadConnection(project), "15 | Shadow Plans", "SRC", {236: (235, 235, 235)}
    )
    assert index == 17
    (asked,) = project.asked("CreatePenTables")
    assert asked["overwriteExisting"] is True
    (table,) = asked["penTableDataArray"]
    assert table["name"] == "15 | Shadow Plans"
    assert table["sourceAttributeId"] == {"attributeId": {"guid": "SRC"}}
    assert table["pens"] == [
        {"index": 236, "color": {"red": 235 / 255, "green": 235 / 255, "blue": 235 / 255}}
    ]


def test_an_archicad_without_create_pen_tables_keeps_the_nearest_pens() -> None:
    project = Project({"CreatePenTables": {"error": {"code": 4010, "message": "not registered"}}})
    assert legend_pen_set(ArchicadConnection(project), "x", "SRC", {1: (0, 0, 0)}) is None


def test_the_nearest_pen_to_the_boundary_red() -> None:
    pens = [Pen(1, (0, 0, 0)), Pen(20, (230, 20, 20)), Pen(30, (20, 20, 230))]
    assert nearest_pen(pens, (220, 30, 30)) == 20
    assert nearest_pen([], (220, 30, 30)) is None


def test_the_legend_and_the_outline_go_on_the_sheet_where_the_drawings_are(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A swatch per row in its exact colour and the legend's words beside it,
    in the column left of the title block; and the site ring drawn in every
    cell where the drawing puts it -- the window's centre at the cell's centre,
    at the scale -- in the outline pen with the empty fill."""
    project = Project({"CreateFills": lambda given: {"elements": given["fills"]}})
    texts: list[dict[str, Any]] = []
    monkeypatch.setattr(plan_sheet, "enter_layout", lambda *_a: None)
    monkeypatch.setattr(plan_sheet, "_clear", lambda *_a: None)
    monkeypatch.setattr(plan_sheet, "_to_the_top", lambda *_a: None)
    monkeypatch.setattr(
        plan_sheet, "layout_sheet", lambda *_a: (LayoutSheet(841.0, 594.0, 10, 10, 10, 10), False)
    )
    monkeypatch.setattr(
        plan_sheet,
        "attribute_index",
        lambda _c, _kind, names: 9 if "Empty Fill" in names else 65,
    )

    def write(_c: object, given: Any, **kwargs: Any) -> tuple[list[Any], bool]:
        texts.extend(given)
        assert kwargs["layer_index"] == plan_sheet.ARCHICAD_LAYER_INDEX
        return [], True

    monkeypatch.setattr(plan_sheet, "create_texts", write)
    rows = [
        ("EXISTING NEIGHBOURING BUILDINGS", (235, 235, 235)),
        ("PROPOSED BUILDING ENVELOPE", (156, 172, 191)),
    ]
    cells = [(0.10, 0.10, 0.30, 0.50), (0.32, 0.10, 0.52, 0.50)]

    shown = draw_legend_and_outline(
        ArchicadConnection(project),
        "LAYOUT",
        title="SHADOW LEGEND",
        rows=rows,
        cells=cells,
        window=PlanWindow(-100.0, -100.0, 100.0, 100.0),
        scale=2000.0,
        rings=[[(0.0, 0.0), (20.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 0.0)]],
        outline_pen=20,
        title_block_mm=100.0,
    )

    assert shown == (2, 2)
    (asked,) = project.asked("CreateFills")
    swatches, outlines = asked["fills"][:2], asked["fills"][2:]
    assert [s["foregroundColour"]["red"] for s in swatches] == [235 / 255, 156 / 255]
    assert all(s["contourPen"] == 0 and s["fillIndex"] == 65 for s in swatches)
    assert all(s["layerIndex"] == plan_sheet.ARCHICAD_LAYER_INDEX for s in swatches)
    first = outlines[0]["contours"][0]["points"]
    assert first[0] == {"x": 0.20, "y": 0.30}, "the model origin at the window centre"
    assert first[1]["x"] == pytest.approx(0.21), "20 m at 1:2000 is 10 mm"
    assert len(first) == 3 and first[-1] != first[0], "left open; the add-on closes it"
    assert all(len(s["contours"][0]["points"]) == 4 for s in swatches), "four corners, open"
    assert outlines[1]["contours"][0]["points"][0]["x"] == pytest.approx(0.42)
    assert all(o["fillIndex"] == 9 and o["contourPen"] == 20 for o in outlines)
    assert all(o["backgroundPen"] == 0 for o in outlines)
    assert [t["text"] for t in texts] == ["SHADOW LEGEND", *(words for words, _ in rows)]
    assert texts[0]["coordinate"]["x"] == pytest.approx(texts[1]["coordinate"]["x"] - 0.016)


def test_without_a_window_or_a_ring_the_legend_is_drawn_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project({"CreateFills": lambda given: {"elements": given["fills"]}})
    monkeypatch.setattr(plan_sheet, "enter_layout", lambda *_a: None)
    monkeypatch.setattr(plan_sheet, "_clear", lambda *_a: None)
    monkeypatch.setattr(plan_sheet, "_to_the_top", lambda *_a: None)
    monkeypatch.setattr(plan_sheet, "layout_sheet", lambda *_a: (LayoutSheet(841.0, 594.0), False))
    monkeypatch.setattr(plan_sheet, "attribute_index", lambda *_a: None)
    monkeypatch.setattr(plan_sheet, "create_texts", lambda *_a, **_k: ([], True))
    shown = draw_legend_and_outline(
        ArchicadConnection(project),
        "LAYOUT",
        title="SHADOW LEGEND",
        rows=[("EXISTING", (235, 235, 235))],
        cells=[(0.1, 0.1, 0.3, 0.5)],
        window=None,
        scale=1000.0,
        rings=[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]],
        outline_pen=20,
        title_block_mm=100.0,
    )
    assert shown == (1, 0)
    (asked,) = project.asked("CreateFills")
    assert len(asked["fills"]) == 1 and "fillIndex" not in asked["fills"][0]


def test_the_grid_follows_the_shape_of_what_it_holds() -> None:
    """Three cells on an A1, a square site: without the shape, three tall
    strips (no cell wasted); with it, two by two, which holds the site larger."""
    from sun_study.archicad.sun_eyes import sheet_cells_for

    a1 = LayoutSheet(841.0, 594.0, 10.0, 10.0, 10.0, 10.0)
    strips = sheet_cells_for(a1, 3, title_block_mm=195.0)
    square = sheet_cells_for(a1, 3, title_block_mm=195.0, aspect=1.0)
    assert len({round(x0, 3) for x0, _, _, _ in strips}) == 3, "one row of three"
    assert len({round(x0, 3) for x0, _, _, _ in square}) == 2, "two columns"
    side = min(square[0][2] - square[0][0], square[0][3] - square[0][1])
    narrow = min(strips[0][2] - strips[0][0], strips[0][3] - strips[0][1])
    assert side > narrow * 1.4


def test_the_sheets_fills_and_texts_go_to_the_top_level() -> None:
    """D138: drawn after the drawings, a fill still lands at its tool's level
    and the outline was under the plan; every fill and text is moved to 14."""
    project = Project(
        {
            "GetElementsByType": lambda given: {
                "elements": [{"elementId": {"guid": f"{given['elementType']}-1"}}]
            },
            "SetDetailsOfElements": {"executionResults": [{"success": True}] * 2},
        }
    )
    plan_sheet._to_the_top(ArchicadConnection(project))
    (asked,) = project.asked("SetDetailsOfElements")
    assert asked["elementsWithDetails"] == [
        {"elementId": {"guid": "Hatch-1"}, "details": {"drawIndex": 14}},
        {"elementId": {"guid": "Text-1"}, "details": {"drawIndex": 14}},
    ]
