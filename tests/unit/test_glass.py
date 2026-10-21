"""Glass the sun is let through: a balustrade's panels, and nothing else.

``IfcModel.without_glass`` takes out every face at least so transparent,
which is what a glass balustrade is to a solar study. What it must not touch
is as much the test as what it does: the rail a panel hangs on, a Zone drawn
in a see-through surface, and a model that cannot say -- which has to read as
"could not tell", never as "there was no glass".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sun_study.archicad.connection import ArchicadConnection
from sun_study.archicad.read import export_model
from sun_study.core.geometry import TriangleMesh
from sun_study.ingest.ifc import IfcElement, IfcModel
from sun_study.ingest.scene import MassingConfig, SceneConfig, massing_subject


def _element(
    global_id: str, ifc_class: str, transparency: list[int] | None, triangles: int = 2
) -> IfcElement:
    """``triangles`` flat triangles side by side, each a metre long."""
    corners = []
    for k in range(triangles):
        corners += [[k, 0.0, 1.0], [k + 1.0, 0.0, 1.0], [k + 1.0, 1.0, 1.0]]
    return IfcElement(
        global_id=global_id,
        ifc_class=ifc_class,
        name=global_id,
        long_name="",
        predefined_type="",
        storey=None,
        mesh=TriangleMesh(
            np.asarray(corners, dtype=np.float64),
            np.arange(triangles * 3, dtype=np.int64).reshape(-1, 3),
        ),
        transparency=None if transparency is None else np.asarray(transparency, dtype=np.uint8),
    )


def _model(*elements: IfcElement) -> IfcModel:
    return IfcModel(
        path=Path("model.loriini"),
        schema="LORIINI",
        latitude_deg=-33.84,
        longitude_deg=151.04,
        true_north_bearing_deg=0.0,
        site_elevation_m=0.0,
        length_unit_scale=1.0,
        elements=elements,
    )


def test_a_panels_glass_goes_and_its_rail_stays() -> None:
    """A railing arrives as one element per part, and a part may be glass on
    one face and steel on another: only the glass is let through."""
    rail = _element("RAIL", "IfcBuildingElementProxy", [88, 0])
    wall = _element("WALL", "IfcWall", [0, 0])

    model, report = _model(rail, wall).without_glass(30)

    by_id = {element.global_id: element for element in model.elements}
    assert by_id["RAIL"].mesh.triangle_count == 1
    assert by_id["RAIL"].transparency is not None
    assert by_id["RAIL"].transparency.tolist() == [0]
    assert by_id["WALL"].mesh.triangle_count == 2
    assert (report.faces, report.elements, report.removed) == (1, 1, 0)


def test_a_panel_that_is_all_glass_goes_altogether() -> None:
    model, report = _model(_element("PANEL", "IfcBuildingElementProxy", [90, 90])).without_glass(30)
    assert model.elements == ()
    assert report.removed == 1
    assert "all glass" in report.describe()


def test_the_threshold_keeps_tinted_glass_solid_when_only_clear_is_let_through() -> None:
    """Tweed Heads' own surfaces: clear glass 90%, tinted 40%, polycarbonate 15%."""
    panels = _element("PANELS", "IfcBuildingElementProxy", [90, 40, 15], triangles=3)

    clear, _ = _model(panels).without_glass(80)
    every, _ = _model(panels).without_glass(30)

    assert clear.elements[0].mesh.triangle_count == 2, "tinted and polycarbonate stay"
    assert every.elements[0].mesh.triangle_count == 1, "only the polycarbonate stays"


def test_a_zone_in_a_see_through_surface_is_never_taken() -> None:
    """Zones are drawn 78% transparent on Tweed Heads, and they are what is
    measured: taking their faces would take the communal open space."""
    zone = _element("COS", "IfcSpace", [78, 78])
    model, report = _model(zone).without_glass(30)
    assert model.elements[0].mesh.triangle_count == 2
    assert report.carried and report.faces == 0


def test_a_model_that_cannot_say_reads_as_could_not_tell() -> None:
    """An IFC, or an add-on's file from before transparency was written."""
    model, report = _model(_element("WALL", "IfcWall", None)).without_glass(30)
    assert model.elements[0].mesh.triangle_count == 2
    assert not report.carried
    assert "does not say how transparent" in report.describe()


def test_the_massing_studies_see_the_building_without_its_glass() -> None:
    """COS and the facade both reduce the model through ``massing_subject``,
    so the measuring and the drawing see the same balustrade -- or none."""
    model = _model(
        _element("PANEL", "IfcBuildingElementProxy", [88, 0]),
        _element("WALL", "IfcWall", [0, 0]),
    )

    solid = massing_subject(model, MassingConfig(timezone="Australia/Sydney"))
    glass = massing_subject(
        model, MassingConfig(timezone="Australia/Sydney", see_through_glass_pct=30)
    )

    assert sum(e.mesh.triangle_count for e in solid.solids) == 4
    assert sum(e.mesh.triangle_count for e in glass.solids) == 3
    assert solid.glass == ""
    assert "glass lets sun through: 1 face on 1 element" in glass.glass


def test_both_settings_lines_say_when_glass_lets_sun_through() -> None:
    assert "glass from 30% transparent lets sun through" in (
        SceneConfig(timezone="Australia/Sydney", see_through_glass_pct=30).describe()
    )
    assert "glass" not in MassingConfig(timezone="Australia/Sydney").describe()


class _Exporting:
    """The add-on's ExportModel, writing the file it was asked for; ``old``
    refuses the transparency field the way an add-on from before it does."""

    def __init__(self, *, old: bool) -> None:
        self.old = old
        self.asked: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        parameters = payload["parameters"]["addOnCommandParameters"]
        self.asked.append(dict(parameters))
        if self.old and "transparency" in parameters:
            return {
                "succeeded": False,
                "error": {
                    "code": 4002,
                    "message": "Invalid command parameters (Validation failed on schema "
                    "rule 'additionalProperties' while trying to validate field on path "
                    "'#/transparency'.)",
                },
            }
        Path(parameters["path"]).write_bytes(b"LORIINIM")
        return {"succeeded": True, "result": {"addOnCommandResponse": {"success": True}}}


@pytest.mark.parametrize("old", [False, True])
def test_the_export_asks_for_transparency_and_an_old_add_on_is_asked_again_without(
    tmp_path: Path, old: bool
) -> None:
    transport = _Exporting(old=old)
    written = export_model(ArchicadConnection(transport), tmp_path / "model.loriini")

    assert written is not None and written.is_file()
    assert transport.asked[0]["transparency"] is True
    if old:
        assert len(transport.asked) == 2
        assert "transparency" not in transport.asked[1]
    else:
        assert len(transport.asked) == 1
