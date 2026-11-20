"""What a run adds, from Archicad, when the Zones it was told to measure are
not in the model it exported.

Penrith, 16 November 2026: the window offered COS on ``01 | Floor.Finish``,
read off the plan, and the run said no Zone matched. The Zone was 20 mm tall
on LEVEL 02, inside the floor, and had no 3D body to export.
"""

from __future__ import annotations

from typing import Any

from sun_study.cli import _zones_the_export_lacks
from sun_study.ingest.scene import MassingConfig
from tests.unit.test_archicad_adapter import connect

FLOOR_FINISH = 7


def _project(*zones: dict[str, Any]) -> dict[str, Any]:
    """A project holding these Zones, on the Penrith layers and storeys."""
    return {
        "GetElementsByType": {
            "elements": [{"elementId": {"guid": f"zone-{n}"}} for n in range(len(zones))]
        },
        "GetDetailsOfElements": {"detailsOfElements": list(zones)},
        "GetAttributesByType": {
            "attributes": [
                {"index": FLOOR_FINISH, "name": "01 | Floor.Finish"},
                {"index": 12, "name": "06 | Zone.SEPP 65"},
            ]
        },
        "GetStories": {
            "stories": [
                {"index": 0, "name": "AHD", "level": 0.0},
                {"index": 2, "name": "LEVEL 02", "level": 6.4},
            ]
        },
    }


def _zone(
    name: str, number: str = "", *, layer: int = FLOOR_FINISH, floor: int = 2
) -> dict[str, Any]:
    return {
        "type": "Zone",
        "floorIndex": floor,
        "layerIndex": layer,
        "details": {"name": name, "numberStr": number},
    }


COS = MassingConfig(
    timezone="Australia/Sydney", zone_layers=("01 | Floor.Finish",), zone_names=("COS",)
)


def test_a_zone_the_project_has_and_the_export_lacks_is_named_with_its_storey() -> None:
    connection, _ = connect(_project(_zone("COS")))
    said = _zones_the_export_lacks(connection, COS, native=True)
    assert "Archicad has 1 Zone named 'COS' on '01 | Floor.Finish' (LEVEL 02)" in said
    assert "carries no body for it" in said
    assert "height in the Info Box" in said


def test_the_3d_window_is_named_before_the_zone_height() -> None:
    """Penrith: the Zone was raised and still missing, because a 3D view of
    the tower alone was open and the export is read off the 3D window. The
    likelier cause is said first."""
    connection, _ = connect(_project(_zone("COS")))
    said = _zones_the_export_lacks(connection, COS, native=True)
    assert "Check the 3D window first" in said
    assert "a storey range, a marquee, or Show Selection in 3D" in said
    assert said.index("Check the 3D window first") < said.index("height in the Info Box")


def test_a_zone_on_another_layer_or_name_is_not_claimed() -> None:
    """Nothing to add when Archicad has no such Zone either: the scene's own
    message has already said what the export holds."""
    connection, _ = connect(_project(_zone("COS", layer=12), _zone("LOBBY")))
    assert _zones_the_export_lacks(connection, COS, native=True) == ""


def test_a_name_taken_from_the_zone_number_is_explained_on_the_native_route() -> None:
    """The window offers a Zone's number as well as its name; the add-on's own
    export carries the name and the element ID, not the number."""
    connection, _ = connect(_project(_zone("COMMUNAL", "COS")))
    said = _zones_the_export_lacks(connection, COS, native=True)
    assert "Archicad has 1 Zone numbered 'COS'" in said
    assert "matches a Zone by its name, not its number" in said


def test_a_numbered_zone_missing_from_an_ifc_lacks_a_body_like_any_other() -> None:
    """An IFC carries the number as Name, so there the number is no excuse."""
    connection, _ = connect(_project(_zone("COMMUNAL", "COS")))
    said = _zones_the_export_lacks(connection, COS, native=False)
    assert "Archicad has 1 Zone named 'COS'" in said
    assert "carries no body for it" in said
