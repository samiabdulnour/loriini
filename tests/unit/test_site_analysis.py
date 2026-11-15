"""The site sheets as elements, and the calls that put them in a worksheet.

The frame is checked against the Kogarah project's north, the same figure
``test_sun_eyes`` uses, so the two halves of the tool agree on which way is
north. The drawings are built from tiny hand-made bundles and counted; the
Archicad side is exercised through the fake transport, which records every
request so the shape of each is asserted rather than assumed.
"""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadError
from sun_study.archicad.read import GeoLocation
from sun_study.archicad.site_analysis import (
    CONTEXT_WORD,
    context_drawing,
    draw_context,
    draw_summary,
    frame_for,
    site_drawing,
    summary_drawing,
    summary_rows,
)
from sun_study.site import nsw, osm, transport
from sun_study.site import theme as themes
from sun_study.site.arcgis import rings_of
from sun_study.site.geo import (
    Extent,
    convex_hull,
    extent_for,
    lonlat_to_mercator,
    lonlat_to_mga,
)
from sun_study.site.pipeline import (
    ContextBundle,
    Institution,
    SiteBundle,
    SummaryBundle,
    describe_lots,
    load_context,
    load_site,
    lots_area_m2,
    save,
)
from sun_study.site.trees import Tree
from tests.unit.test_archicad_adapter import Sequential, connect

KOGARAH = GeoLocation(
    latitude_deg=-33.96,
    longitude_deg=151.13,
    altitude_m=0.0,
    north_radians=math.radians(49.052),
)
SS = naming.prefix()
CONTEXT_LAYER = naming.context_layer()
#: The three layers the context model stands on, buildings last so the
#: buildings keep index 9, which the tests below read slabs back from.
CONTEXT_LAYERS = (naming.terrain_layer(), naming.roads_layer(), naming.buildings_layer())


def _layer_attributes() -> list[dict[str, Any]]:
    """The context layers as ``GetAttributesByType`` lists them."""
    return [
        {"name": name, "index": 7 + i, "attributeId": {"guid": f"L{7 + i}"}}
        for i, name in enumerate(CONTEXT_LAYERS)
    ]


def _layer_states() -> list[dict[str, Any]]:
    """And as ``GetLayers`` does."""
    return [
        {"layerAttribute": {"name": name, "isHidden": False, "isLocked": False}}
        for name in CONTEXT_LAYERS
    ]


FUTURE_LAYER = naming.future_layer()

# A square site about 20 m across, a little east of the project location.
LON, LAT = 151.1312, -33.9601


def square(lon: float, lat: float, metres: float) -> list[tuple[float, float]]:
    dlon = metres / (111_320.0 * math.cos(math.radians(lat)))
    dlat = metres / 111_320.0
    return [
        (lon - dlon / 2, lat - dlat / 2),
        (lon + dlon / 2, lat - dlat / 2),
        (lon + dlon / 2, lat + dlat / 2),
        (lon - dlon / 2, lat + dlat / 2),
        (lon - dlon / 2, lat - dlat / 2),
    ]


def polygon(ring: list[tuple[float, float]], **properties: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in ring]]},
        "properties": properties,
    }


def collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def context_bundle() -> ContextBundle:
    centre = lonlat_to_mercator(LON, LAT)
    return ContextBundle(
        address="1 Test St, Kogarah NSW",
        matched=("1 TEST STREET KOGARAH",),
        centre=centre,
        extent=extent_for(centre, 690.0, 594.0, 3000.0),
        scale=3000.0,
        site_lots=collection(polygon(square(LON, LAT, 20.0), lotidstring="1//DP1")),
        all_lots=collection(polygon(square(LON + 0.001, LAT, 20.0))),
        zoning=collection(
            polygon(square(LON, LAT, 400.0), SYM_CODE="R3"),
            polygon(square(LON + 0.005, LAT, 400.0), SYM_CODE="DM"),
        ),
        heritage=collection(polygon(square(LON - 0.002, LAT, 30.0), LAY_CLASS="Item - General")),
        roads=(
            nsw.Road("Test Street", 5, 2, tuple(square(LON, LAT + 0.001, 300.0)[:2])),
            nsw.Road("Back Lane", 7, 1, tuple(square(LON, LAT - 0.001, 300.0)[:2])),
        ),
        stations=(nsw.NamedPoint("KOGARAH", LON + 0.004, LAT + 0.002),),
        park_areas=(nsw.NamedArea("JUBILEE OVAL", LON - 0.004, LAT + 0.002, 20_000.0),),
        complexes=(nsw.NamedPoint("St George Hospital", LON, LAT + 0.003, "medical"),),
        institutions=(
            Institution("medical", "St George Hospital", (tuple(square(LON, LAT + 0.003, 100.0)),)),
        ),
        bus=osm.BusData(
            stops=(osm.Stop(LON + 0.001, LAT + 0.001, "Test St"),),
            routes=(tuple(square(LON, LAT, 500.0)[:3]),),
        ),
        isochrones=(transport.Isochrone(5, (tuple(square(LON, LAT, 600.0)),)),),
    )


def test_the_frame_turns_true_north_the_way_the_sun_eye_views_do() -> None:
    """Project +Y sits at true bearing 319.052 on the Kogarah project, so a
    point due north of the origin lands up and to the right of it, 41 degrees
    off +Y -- the same 41 the sun eye bearings turn by."""
    frame = frame_for(KOGARAH, site_centre=(KOGARAH.longitude_deg, KOGARAH.latitude_deg))
    assert frame.zone == 56
    origin = frame.project(KOGARAH.longitude_deg, KOGARAH.latitude_deg)
    assert origin == pytest.approx((0.0, 0.0), abs=1e-6)

    phi = math.radians(KOGARAH.latitude_deg)
    metres_per_degree = 111132.954 - 559.822 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    north = frame.project(KOGARAH.longitude_deg, KOGARAH.latitude_deg + 100.0 / metres_per_degree)
    distance = math.hypot(*north)
    assert distance == pytest.approx(100.0, rel=1e-3)
    angle_from_plus_y = math.degrees(math.atan2(north[0], north[1]))
    assert angle_from_plus_y == pytest.approx(360.0 - 319.052, abs=0.05)
    assert frame.direction(0.0) == pytest.approx(
        (north[0] / distance, north[1] / distance), abs=1e-3
    )


def test_anchoring_at_the_site_puts_its_centre_at_the_origin_and_keeps_north() -> None:
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    assert frame.project(LON, LAT) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert frame.plus_y_bearing_deg == pytest.approx(319.052)
    without = frame_for(None, site_centre=(LON, LAT), anchor="site")
    assert without.plus_y_bearing_deg == 0.0
    with pytest.raises(ValueError, match="geolocation"):
        frame_for(None, site_centre=(LON, LAT), anchor="location")


def test_the_site_can_be_squared_to_its_long_boundary_and_set_on_a_corner() -> None:
    """Asked for on 8 October 2026: the model is set out with its long
    frontage level and its origin on a corner of the lot, and the context
    should come in to match. Squared, the site's longest boundary runs along
    +X and the frame's +Y bearing has turned with it, which is the north to
    write; cornered, the corner named is (0, 0)."""
    from sun_study.archicad import site_analysis as sd

    rings = site_bundle().site_rings
    base = frame_for(None, site_centre=(LON, LAT), anchor="site")
    assert sd.placed_frame(base, rings) == base, "centre and unsquared is the frame as it was"

    squared = sd.placed_frame(base, rings, square=True)
    hull = convex_hull(p for ring in rings for p in squared.ring(ring))
    angle = sd._edge_bearing(hull)
    assert min(angle, 180.0 - angle) == pytest.approx(0.0, abs=1e-6), "the long side is level"
    turn = (squared.plus_y_bearing_deg - base.plus_y_bearing_deg + 180.0) % 360.0 - 180.0
    assert turn != 0.0 and abs(turn) <= 90.0, "turned the short way, and north went with it"

    cornered = sd.placed_frame(base, rings, square=True, origin_at="bottom-left")
    hull = convex_hull(p for ring in rings for p in cornered.ring(ring))
    corner = min(hull, key=lambda p: p[0] + p[1])
    assert corner == pytest.approx((0.0, 0.0), abs=1e-6)
    assert cornered.plus_y_bearing_deg == pytest.approx(squared.plus_y_bearing_deg)
    top_right = sd.placed_frame(base, rings, origin_at="top-right")
    hull = convex_hull(p for ring in rings for p in top_right.ring(ring))
    assert max(hull, key=lambda p: p[0] + p[1]) == pytest.approx((0.0, 0.0), abs=1e-6)

    with pytest.raises(ValueError, match="origin_at"):
        sd.placed_frame(base, rings, origin_at="middle")


def test_the_context_drawing_carries_the_legends_colours_and_the_site_on_top() -> None:
    bundle = context_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    # Heron, the office sheet over the aerial: the colours below are read off
    # its own palette. The other three are checked in test_site_theme.
    heron = themes.theme("heron")
    drawing = context_drawing(bundle, frame, theme="heron")

    zoning = [f for f in drawing.fills if "(R3)" in f.element_id or "(DM)" in f.element_id]
    assert [f.colour for f in zoning] == [heron.category("r3").fill], (
        "R3 is drawn in the theme's R3; DM is not a category"
    )
    assert zoning[0].element_id == "SA R3 MEDIUM DENSITY RESIDENTIAL (R3)"
    assert all(f.element_id for f in drawing.fills), "every fill says what it is"
    institutions = [f for f in drawing.fills if f.element_id.startswith("SA MEDICAL")]
    medical = heron.category("medical")
    assert institutions[0].colour == medical.fill and institutions[0].contour == medical.stroke
    assert any(f.element_id == "SA GENERAL HERITAGE SITE" for f in drawing.fills)

    site_lines = [line for line in drawing.lines if line.dashed and line.weight_mm == 0.9]
    assert site_lines and site_lines[0].dashed and site_lines[0].colour == heron.site
    # The site is 20 m a side in the project frame, whatever the turn.
    sides = [math.dist(a, b) for a, b in pairwise(site_lines[0].points)]
    assert sides == pytest.approx([20.0] * 4, rel=0.01)

    labels = {t.text for t in drawing.texts if not t.layer.endswith(".Sheet")}
    # The streets named plain, the places numbered on the map and named in
    # the legend's key, as site-analyst.com draws them.
    assert {"TEST ST", "BACK LN", "1", "2", "B", "T"} <= labels
    assert "SITE" not in labels, "the legend says what red is"
    assert any(t.text.startswith("400m") for t in drawing.texts)
    assert not any(f.element_id == "SA STREET NAME BAND" for f in drawing.fills), "plain names"
    # The stop's letter sits on the roundel's centre, white on the solid disc.
    letter = next(t for t in drawing.texts if t.text == "B")
    roundel = next(f for f in drawing.fills if f.element_id == "SA BUS STOP")
    centre = (sum(x for x, _ in roundel.rings[0]) / 24, sum(y for _, y in roundel.rings[0]) / 24)
    assert letter.at == pytest.approx(centre, abs=1e-6) and letter.colour == "#ffffff"
    assert any(f.hatch for f in drawing.fills if f.element_id == "SA GENERAL HERITAGE SITE")
    assert len(drawing.layers) <= 5, drawing.layers
    assert any(f.wash for f in drawing.fills if f.element_id == "SA SITE")
    # Legend rows only for what is on the map.
    legend = [t.text for t in drawing.texts if t.layer.endswith(".Sheet")]
    assert "R3 MEDIUM DENSITY RESIDENTIAL" in legend and "MEDICAL" in legend
    assert "R2 LOW DENSITY RESIDENTIAL" not in legend
    assert {"ST GEORGE HOSPITAL", "JUBILEE OVAL", "KOGARAH"} <= set(legend), "the key"
    assert drawing.mm(4.0) == pytest.approx(12.0), "4 mm on paper is 12 m at 1:3000"


def site_bundle() -> SiteBundle:
    centre = lonlat_to_mercator(LON, LAT)
    ring = square(LON, LAT, 20.0)
    east = LON + 0.0003
    return SiteBundle(
        address="1 Test St, Kogarah NSW",
        matched=("1 TEST STREET KOGARAH",),
        centre=centre,
        extent=extent_for(centre, 690.0, 594.0, 200.0),
        scale=200.0,
        site_lots=collection(polygon(ring, lotidstring="1//DP1")),
        site_rings=(tuple(ring[:-1]),),
        roads=(
            nsw.Road(
                "Test Street", 4, 2, ((LON - 0.001, LAT + 0.0003), (LON + 0.001, LAT + 0.0003))
            ),
        ),
        zoning=collection(polygon(square(LON, LAT, 400.0), SYM_CODE="R3")),
        contours=(
            # Just outside the west and east boundaries, four metres apart in
            # level, so the corners read about 24.2 and 27.8 and the fall shows.
            nsw.Contour(24.0, ((LON - 0.00012, LAT - 0.0004), (LON - 0.00012, LAT + 0.0004))),
            nsw.Contour(28.0, ((LON + 0.00012, LAT - 0.0004), (LON + 0.00012, LAT + 0.0004))),
        ),
        neighbours=(nsw.Neighbour("3", east, LAT),),
        furniture=osm.Furniture(
            trees=(Tree(LON, LAT + 0.0002),),
            buildings=(osm.Building(east, LAT, tuple(square(east, LAT, 10.0)), levels=2),),
            driveways=(((LON, LAT), (LON, LAT + 0.0003)),),
        ),
    )


def test_the_site_drawing_fills_the_neighbouring_buildings() -> None:
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    # Kingfisher draws every neighbour as a fill in its zone's colour.
    drawing = site_drawing(site_bundle(), frame, theme="kingfisher")
    masses = [
        f for f in drawing.fills if f.layer.endswith(".Context") and f.element_id == "SA BUILDINGS"
    ]
    assert len(masses) == 1, "one neighbour, one solid footprint on the Context layer"
    assert masses[0].wash is False and masses[0].contour is not None
    footprint = masses[0].rings[0]
    assert not any(
        line.points[0] == footprint[0] and line.points[-1] == footprint[0] for line in drawing.lines
    ), "the footprint is a fill, not a closed outline"
    trees = [f for f in drawing.fills if f.element_id.startswith("SA TREE")]
    assert drawing.fills.index(masses[0]) < drawing.fills.index(trees[0]), (
        "canopies over the masses"
    )


def test_the_site_drawing_dimensions_levels_and_orients_the_site() -> None:
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    drawing = site_drawing(site_bundle(), frame, theme="heron")
    texts = [t.text for t in drawing.texts]

    dimensions = [
        t.text for t in drawing.texts if t.layer.endswith(".Site") and t.text.startswith("SB ")
    ]
    assert len(dimensions) == 4
    assert all(abs(float(t.split()[1]) - 20.0) < 0.2 for t in dimensions)
    levels = [
        t.text for t in drawing.texts if t.layer.endswith(".Site") and t.text.startswith("RL ")
    ]
    assert len(levels) == 4
    info = next(
        t.text for t in drawing.texts if t.layer.endswith(".Site") and t.text.startswith("FALL")
    )
    assert "AREA 400" in info or "AREA 399" in info or "AREA 401" in info
    assert "3\n2 STOREY" in texts
    assert any(f.element_id == "SA ACCESS" for f in drawing.fills), "a driveway becomes a triangle"
    assert any(f.element_id == "SA NOISE" for f in drawing.fills), (
        "a hierarchy-4 road is a noise source"
    )
    assert len(drawing.layers) <= 5, drawing.layers

    # The north disc sits along true north from the site.
    north = next(t for t in drawing.texts if t.text == "N" and t.layer.endswith(".Sheet"))
    direction = frame.direction(0.0)
    assert math.atan2(north.at[1], north.at[0]) == pytest.approx(
        math.atan2(direction[1], direction[0]), abs=0.01
    )


def test_the_summary_table_fills_what_is_published_and_rules_up_the_rest() -> None:
    bundle = SummaryBundle(
        address="1 Test St",
        site_address="1 TEST STREET KOGARAH",
        lot_description="LOT 1 - DP 1",
        site_area_m2=1000.0,
        controls=nsw.SiteControls(
            epi_name="Georges River Local Environmental Plan 2021",
            lga_name="GEORGES RIVER",
            zone_code="R3",
            zone_purpose="Medium Density Residential",
            max_height_m=12.0,
            fsr=0.55,
            heritage=(("Cottage", "Local"),),
        ),
    )
    rows = summary_rows(bundle)
    by_label = {label: controls for kind, label, controls in rows if kind == "row"}
    assert by_label["LAND USE"] == ["R3 - Medium Density Residential"]
    assert by_label["FLOOR SPACE RATIO"] == ["0.55:1"]
    assert by_label["GROSS FLOOR AREA (sqm)"][0] == "550.0 sqm"
    assert by_label["HERITAGE"] == ["Cottage (Local)"]
    assert by_label["MIN. LOT SIZE (sqm)"] == ["No minimum lot size mapped"]
    assert by_label["SETBACK"] == [], "DCP rows are ruled up, not guessed"
    assert by_label["3D. COMMUNAL OPEN SPACE"][-1] == "= 250.0 sqm"
    assert any(label == "GEORGES RIVER LEP 2021" for kind, label, _ in rows if kind == "section")

    drawing = summary_drawing(bundle)
    assert "SUMMARY OF CONTROLS" in [t.text for t in drawing.texts]
    assert len(drawing.lines) == len(rows) + 1, "a rule under every row and one above"


def test_a_long_label_wraps_inside_its_column_rather_than_over_the_controls() -> None:
    """The Redfern sheet, 7 October 2026: "3F. VISUAL PRIVACY / BUILDING
    SEPARATION" ran across the controls column. Labels now wrap at a word to
    the column's width, the row grows with them, and nothing in the label
    column starts where the controls do."""
    from sun_study.archicad.site_analysis import (
        SUMMARY_LABEL_CHARS,
        SUMMARY_LABEL_MM,
        summary_label_lines,
    )

    assert summary_label_lines("3F. VISUAL PRIVACY / BUILDING SEPARATION") == [
        "3F. VISUAL PRIVACY /",
        "BUILDING SEPARATION",
    ]
    assert summary_label_lines("4A. SOLAR AND DAYLIGHT ACCESS") == [
        "4A. SOLAR AND DAYLIGHT",
        "ACCESS",
    ]
    assert summary_label_lines("GROSS FLOOR AREA (sqm)") == ["GROSS FLOOR AREA (sqm)"]
    assert summary_label_lines("") == [""]

    bundle = SummaryBundle(
        address="1 Test St",
        site_address="1 TEST STREET KOGARAH",
        lot_description="LOT 1 - DP 1",
        site_area_m2=1000.0,
        controls=nsw.SiteControls(
            epi_name="Georges River Local Environmental Plan 2021",
            lga_name="GEORGES RIVER",
            zone_code="R3",
            zone_purpose="Medium Density Residential",
            max_height_m=12.0,
            fsr=0.55,
            heritage=(("Cottage", "Local"),),
        ),
    )
    drawing = summary_drawing(bundle)
    controls_x = drawing.mm(SUMMARY_LABEL_MM)
    by_text = {t.text: t for t in drawing.texts}
    for kind, label, _ in summary_rows(bundle):
        if kind != "row":
            continue
        for line in summary_label_lines(label):
            assert len(line) <= SUMMARY_LABEL_CHARS or " " not in line, line
            assert by_text[line].at[0] < controls_x, f"{line!r} sits in the controls column"
    # The wrapped label's second line sits one lead under its first.
    first, second = by_text["3F. VISUAL PRIVACY /"], by_text["BUILDING SEPARATION"]
    assert first.at[0] == second.at[0]
    assert first.at[1] - second.at[1] == pytest.approx(drawing.mm(5.2))


def test_the_bundles_survive_a_round_trip_through_json(tmp_path: Path) -> None:
    context = context_bundle()
    path = save(context, tmp_path / "data" / "context.json")
    back = load_context(path)
    assert back.matched == context.matched
    assert back.extent == context.extent
    assert back.roads == context.roads
    assert back.institutions == context.institutions
    assert back.bus == context.bus
    assert back.isochrones == context.isochrones

    site = site_bundle()
    again = load_site(save(site, tmp_path / "data" / "site.json"))
    assert again.site_rings == site.site_rings
    assert again.furniture == site.furniture
    assert again.contours == site.contours
    with pytest.raises(ValueError, match="not a saved site"):
        load_site(path)


def test_lot_descriptions_and_areas_follow_the_register() -> None:
    lots = collection(
        polygon(square(LON, LAT, 20.0), lotidstring="1//DP212120"),
        polygon(square(LON + 0.001, LAT, 20.0), lotidstring="2//DP212120"),
    )
    assert describe_lots(lots) == "LOT 1&2 - DP 212120"
    assert lots_area_m2(lots, 56) == pytest.approx(800.0, rel=0.01)
    assert lonlat_to_mga(LON, LAT, 56)[0] > 300_000


def navigator_tree(*worksheets: tuple[str, str]) -> dict[str, Any]:
    return {
        "navigatorItemTree": {
            "rootItem": {
                "name": "root",
                "children": [
                    {
                        "navigatorItem": {
                            "type": "WorksheetDrawingItem",
                            "name": name,
                            "navigatorItemId": {"guid": guid},
                            "children": [],
                        }
                    }
                    for name, guid in worksheets
                ],
            }
        }
    }


def test_drawing_makes_the_worksheet_through_the_add_on_and_fills_in_colour() -> None:
    """The order that makes it drawable: the add-on's CreateWorksheet, then
    the fills through CreateFills with an RGB each, then Tapir's polylines
    and texts, and the texts moved onto the study's layer."""
    connection, transport_ = connect(
        {
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetNavigatorItemTree": navigator_tree(),
            "CreateWorksheet": {"success": True, "databaseId": {"guid": "WS"}, "isCurrent": True},
            # One list answers every attribute kind: the fill and line type by
            # name, and every layer the context sheet draws on, as if a run
            # had made them already.
            "GetAttributesByType": {
                "attributes": [
                    {"name": "Solid Fill", "index": 1, "attributeId": {"guid": "F1"}},
                    {"name": "Dashed", "index": 2, "attributeId": {"guid": "L2"}},
                    *(
                        {"name": name, "index": 10 + i, "attributeId": {"guid": f"LAYER{i}"}}
                        for i, name in enumerate(
                            context_drawing(
                                context_bundle(),
                                frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site"),
                                theme="heron",
                            ).layers
                        )
                    ),
                ]
            },
            "GetLayers": {
                "layers": [{"layerAttribute": {"name": "x", "isHidden": False, "isLocked": False}}]
            },
            "GetPenTables": Sequential(
                {
                    "penTables": [
                        {
                            "penTableAttribute": {
                                "isActiveForModel": True,
                                "attributeId": {"guid": "F1"},
                            }
                        }
                    ]
                },
                {
                    "penTables": [
                        {
                            "penTableAttribute": {
                                "pens": [
                                    {
                                        "index": 5,
                                        "color": {"red": 0.9, "green": 0.05, "blue": 0.05},
                                    },
                                    {"index": 7, "color": {"red": 0.5, "green": 0.5, "blue": 0.5}},
                                ]
                            }
                        }
                    ]
                },
            ),
            "CreateLayers": {"success": True},
            "CreatePenTables": {"attributeIds": [{"attributeId": {"guid": "PENS"}}]},
            "CreateFills": {"success": True, "elements": [{"guid": "H"}]},
            "CreatePolylines": {"elements": [{"elementId": {"guid": "P"}}]},
            "CreateTexts": {"success": True, "elements": [{"guid": "T"}]},
            "CreateLayerCombinations": {"executionResults": [{"success": True}]},
            "CreateViewsInViewMap": {"navigatorItems": [{"navigatorItemId": {"guid": "V"}}]},
            "SetViewSettings": {"executionResults": [{"success": True}]},
            "CreateViewMapFolder": {"navigatorItemId": {"guid": "FOLDER"}},
        }
    )
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    report = draw_context(connection, context_bundle(), frame, view=False, theme="heron")

    commands = transport_.commands()
    assert (
        commands.index("CreateWorksheet")
        < commands.index("CreateFills")
        < commands.index("CreatePolylines")
    )
    assert transport_.parameters_for("CreateWorksheet") == {
        "name": f"{SS} {CONTEXT_WORD}",
        "makeCurrent": True,
    }

    fills = [f for call in transport_.all_parameters_for("CreateFills") for f in call["fills"]]
    zone = next(f for f in fills if f.get("elementId") == "SA R3 MEDIUM DENSITY RESIDENTIAL (R3)")
    assert zone["determination"] == "drafting" and zone["showArea"] is False
    assert zone["foregroundColour"] == pytest.approx(
        {"red": 0xEC / 255, "green": 0xCB / 255, "blue": 0xB2 / 255}
    ), "Heron's R3"
    assert zone["fillIndex"] == 1
    assert len(zone["contours"]) == 1 and len(zone["contours"][0]["points"]) == 4, (
        "no closing point"
    )

    lines = [
        line
        for call in transport_.all_parameters_for("CreatePolylines")
        for line in call["polylinesData"]
    ]
    assert any(line.get("lineTypeIndex") == 2 for line in lines), "the site outline is dashed"
    site_line = next(line for line in lines if line.get("penWeightMm") == 0.9)
    # The sheet's own pen table carries the site's red exactly, in a pen of
    # its own: not the nearest pen of the office's table (D139).
    (table,) = transport_.parameters_for("CreatePenTables")["penTableDataArray"]
    assert table["name"] == f"{SS} {CONTEXT_WORD}" and table["sourceAttributeId"]
    pens = {pen["index"]: pen for pen in table["pens"]}
    assert site_line["linePenIndex"] in pens and site_line["linePenIndex"] >= 136
    assert pens[site_line["linePenIndex"]]["color"] == pytest.approx(
        {"red": 0xCF / 255, "green": 0x4A / 255, "blue": 0x2E / 255}
    ), "Heron's red"
    assert "isActiveForModel" not in table, "never made the model's table"
    texts = [t for call in transport_.all_parameters_for("CreateTexts") for t in call["texts"]]
    site_text = next(t for t in texts if t["text"] == "TEST ST")
    assert site_text["justification"] == "Center" and site_text["anchor"] == "MiddleMiddle"
    assert all("layerIndex" in t for t in texts), "the add-on's texts take their layer at creation"
    assert "SetDetailsOfElements" not in commands, "so nothing has to be moved afterwards"

    assert report.reused is False and report.fills == len(fills) and report.lines == len(lines)
    assert report.texts == len(texts)
    assert not any("pen table" in note for note in report.notes)


def test_the_summary_of_controls_is_drawn_straight_onto_a_layout_of_its_own() -> None:
    layout_book = {
        "navigatorItemTree": {
            "navigatorItemId": {"guid": "ROOT"},
            "name": "root",
            "children": [
                {
                    "navigatorItem": {
                        "type": "MasterLayoutItem",
                        "name": "A1 - VERTICAL NO SCALE",
                        "navigatorItemId": {"guid": "M1"},
                        "children": [],
                    }
                },
                {
                    "navigatorItem": {
                        "type": "LayoutItem",
                        "name": f"{SS} Summary of Controls",
                        "navigatorItemId": {"guid": "OLD"},
                        "children": [],
                    }
                },
            ],
        }
    }
    connection, transport_ = connect(
        {
            "GetNavigatorItemTree": layout_book,
            "DeleteNavigatorItems": {"success": True},
            "CreateLayout": {"databases": [{"databaseId": {"guid": "LAY"}}]},
            "GetLayoutSettings": {
                "layoutSettings": [
                    {
                        "horizontalSize": 841.0,
                        "verticalSize": 594.0,
                        "leftMargin": 10.0,
                        "topMargin": 10.0,
                        "rightMargin": 10.0,
                        "bottomMargin": 10.0,
                    }
                ]
            },
            "SetCurrentDatabase": {"success": True},
            "GetCurrentDatabase": {"databaseId": {"guid": "LAY"}, "windowType": "Layout"},
            "GetAttributesByType": {"attributes": _layer_attributes()},
            "GetLayers": {"layers": _layer_states()},
            "CreateLayers": {"success": True},
            "GetPenTables": {"penTables": []},
            "CreatePolylines": {"elements": [{"elementId": {"guid": "P"}}]},
            "CreateTexts": {"success": True, "elements": [{"guid": "T"}]},
        }
    )
    bundle = SummaryBundle("1 Test St", "1 TEST STREET", "LOT 1 - DP 1", None, nsw.SiteControls())
    report = draw_summary(connection, bundle, master_layout="A1 no scale")
    assert report.master == "A1 - VERTICAL NO SCALE" and report.database_id == "LAY"
    assert report.lines > 5 and report.texts > 5
    assert "drawn on the sheet itself" in report.describe()
    commands = transport_.commands()
    # The stale sheet goes, the new one is made on the master, entered, drawn.
    assert commands.index("DeleteNavigatorItems") < commands.index("CreateLayout")
    assert commands.index("CreateLayout") < commands.index("SetCurrentDatabase")
    assert commands.index("SetCurrentDatabase") < commands.index("CreateTexts")
    assert transport_.parameters_for("SetCurrentDatabase") == {
        "databaseId": {"guid": "LAY"},
        "windowType": "Layout",
    }
    # Paper metres, hanging from the usable top-left corner 15 mm in: the
    # title sits near x = 0.026 m, y just under 0.569 m, on an A1 landscape.
    texts = transport_.parameters_for("CreateTexts")["texts"]
    title = next(t for t in texts if t["text"] == "SUMMARY OF CONTROLS")
    assert 0.02 < title["coordinate"]["x"] < 0.03
    assert 0.55 < title["coordinate"]["y"] < 0.58
    assert title["height"] == pytest.approx(8.2), "paper millimetres, as on the worksheet"
    assert all(0.0 < t["coordinate"]["y"] < 0.58 for t in texts), "everything on the sheet"
    assert "elementId" not in title, "a layout element takes no ID"


def test_a_context_extent_is_the_sheet_at_its_scale() -> None:
    bundle = context_bundle()
    assert isinstance(bundle.extent, Extent)
    assert bundle.extent.width == pytest.approx(2070.0 / math.cos(math.radians(LAT)), rel=1e-6)


def test_a_refused_creation_falls_back_to_tapir_and_a_refused_entry_says_what_to_do() -> None:
    """Measured on the Kogarah solar study: the add-on's CreateWorksheet is
    refused from its undo scope, Tapir's CreateWorksheets makes the sheet,
    and neither route can enter a worksheet made in this session. The
    worksheet is then there, and the error says to open it and rerun."""
    from sun_study.archicad.site_analysis import WorksheetNotEnteredError, ensure_worksheet

    connection, transport_ = connect(
        {
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetNavigatorItemTree": navigator_tree(),
            "CreateWorksheet": {"error": {"code": -2130312312, "message": "Failed to create"}},
            "CreateWorksheets": {"databases": [{"databaseId": {"guid": "NEW"}}]},
            "SetCurrentDatabase": {"error": {"code": -2130313110, "message": "refused to move"}},
        }
    )
    with pytest.raises(WorksheetNotEnteredError, match="double-click"):
        ensure_worksheet(connection, f"{SS} Context Analysis", wait_s=0.0)
    assert transport_.parameters_for("CreateWorksheets") == {
        "worksheetsData": [
            {"name": f"{SS} Context Analysis", "referenceId": f"{SS} Context Analysis"}
        ]
    }
    assert transport_.all_parameters_for("SetCurrentDatabase")[0]["databaseId"] == {"guid": "NEW"}
    # The plain move, then the move with the window opened first, before any
    # waiting: the second is the route D95 left unread, and an add-on that
    # refuses both leaves the person to open it as before.
    tried = [p.get("open") for p in transport_.all_parameters_for("SetCurrentDatabase")]
    assert tried[:2] == [None, True]


def test_a_fresh_worksheet_entered_by_opening_its_window_needs_nobody() -> None:
    """The add-on's ``open`` -- the call a double-click makes -- taken where
    the plain move is refused. The worksheet is read back as current, so the
    run draws at once and never asks for the Project Map."""
    from sun_study.archicad.site_analysis import ensure_worksheet

    connection, transport_ = connect(
        {
            # Standing on the plan before the move, on the worksheet after.
            "GetCurrentDatabase": Sequential(
                {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
                {"databaseId": {"guid": "NEW"}, "windowType": "Worksheet"},
            ),
            "GetNavigatorItemTree": navigator_tree(),
            "CreateWorksheet": {"error": {"code": -2130312312, "message": "Failed to create"}},
            "CreateWorksheets": {"databases": [{"databaseId": {"guid": "NEW"}}]},
            "SetCurrentDatabase": Sequential(
                {"error": {"code": -2130313110, "message": "refused to move"}},
                {"success": True, "opened": True},
            ),
        }
    )
    database_id, _, reused = ensure_worksheet(connection, f"{SS} Context Analysis", wait_s=0.0)
    assert database_id == "NEW"
    assert not reused
    assert [p.get("open") for p in transport_.all_parameters_for("SetCurrentDatabase")] == [
        None,
        True,
    ]


def test_a_worksheet_the_refused_creation_left_behind_is_found_rather_than_made_twice() -> None:
    """The bug measured live at Bondi on 14 September 2026, and the reason
    every site sheet ended up with two worksheets of one name in the Project
    Map. ``CreateWorksheet`` makes the worksheet and *then* enters it, so a
    refusal at the entering step fails the call with the worksheet already
    made. The run saw only the refusal, believed nothing existed, and let
    Tapir's fallback make a second one.

    The first look finds nothing, because at that point there is nothing. The
    second look -- after the refusal -- is the whole fix: it finds what the
    refused call left, reports it as reused, and never reaches
    ``CreateWorksheets``.
    """
    from sun_study.archicad.site_analysis import ensure_worksheet

    connection, transport_ = connect(
        {
            # Standing in the worksheet the refused call left. The second
            # answer is only reached by the old behaviour, which makes a
            # second worksheet and then enters that instead -- scripted so
            # the regression fails on the assertion below rather than on an
            # unscripted command, which says nothing about what went wrong.
            "GetCurrentDatabase": Sequential(
                {"databaseId": {"guid": "WS"}, "windowType": "Worksheet"},
                {"databaseId": {"guid": "SECOND"}, "windowType": "Worksheet"},
            ),
            # Empty when the run first looks, holding the worksheet once the
            # refused creation has quietly made it.
            "GetNavigatorItemTree": Sequential(
                navigator_tree(),
                navigator_tree((f"{SS} Site Analysis", "NAV")),
            ),
            "CreateWorksheet": {"error": {"code": -2130313110, "message": "refused to move"}},
            "GetDatabaseIdFromNavigatorItemId": {"databases": [{"databaseId": {"guid": "WS"}}]},
            "CreateWorksheets": {"databases": [{"databaseId": {"guid": "SECOND"}}]},
            "SetCurrentDatabase": {"success": True},
        }
    )

    assert ensure_worksheet(connection, f"{SS} Site Analysis", wait_s=0.0) == ("WS", "NAV", True)
    assert "CreateWorksheets" not in transport_.commands(), (
        "a second worksheet was made over the one the refused creation left behind"
    )


def test_a_worksheet_already_in_front_is_drawn_into_without_a_move() -> None:
    """The way through the refusal: a person opens the worksheet, and the run
    finds itself standing in it."""
    from sun_study.archicad.site_analysis import ensure_worksheet

    connection, transport_ = connect(
        {
            "GetCurrentDatabase": {"databaseId": {"guid": "WS"}, "windowType": "Worksheet"},
            "GetNavigatorItemTree": navigator_tree((f"{SS} Context Analysis", "NAV")),
            "GetDatabaseIdFromNavigatorItemId": {"databases": [{"databaseId": {"guid": "WS"}}]},
        }
    )
    assert ensure_worksheet(connection, f"{SS} Context Analysis") == ("WS", "NAV", True)
    assert "SetCurrentDatabase" not in transport_.commands()


def test_the_run_waits_for_a_person_to_open_the_worksheet() -> None:
    """Refused twice, then in front: the third look finds it and drawing goes on."""
    from sun_study.archicad.site_analysis import ensure_worksheet

    connection, transport_ = connect(
        {
            "GetCurrentDatabase": Sequential(
                {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
                {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
                {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
                {"databaseId": {"guid": "NEW"}, "windowType": "Worksheet"},
            ),
            "GetNavigatorItemTree": navigator_tree((f"{SS} Site Analysis", "NAV")),
            "GetDatabaseIdFromNavigatorItemId": {"databases": [{"databaseId": {"guid": "NEW"}}]},
            "SetCurrentDatabase": {"error": {"code": -2130313110, "message": "refused"}},
        }
    )
    said: list[str] = []
    assert ensure_worksheet(connection, f"{SS} Site Analysis", wait_s=30.0, say=said.append) == (
        "NEW",
        "NAV",
        True,
    )
    assert said and "double-click" in said[0]
    assert transport_.commands().count("GetCurrentDatabase") == 4


def test_texts_fall_back_to_tapir_and_a_move_when_the_add_on_is_older() -> None:
    """An add-on without CreateTexts answers 'not registered'; the texts then
    go through Tapir on the Text tool's layer and are moved onto the study's."""
    from sun_study.archicad.site_analysis import Text, _Attributes, _texts

    connection, transport_ = connect(
        {
            "CreateTexts": Sequential(
                {"error": {"code": 4010, "message": "does not have the registered Add-On command"}},
                {"elements": [{"elementId": {"guid": "T"}}]},
            ),
            "GetDetailsOfElements": Sequential(
                {"detailsOfElements": [{"layerIndex": 3}]},
                {"detailsOfElements": [{"layerIndex": 7}]},
            ),
            "GetAttributesByType": {"attributes": []},
            "SetDetailsOfElements": {"success": True},
        }
    )
    texts = [Text(layer="L", text="SITE", at=(1.0, 2.0), height_mm=4.0)]
    moved = _texts(connection, texts, {"L": 7}, _Attributes(None, None, ()))
    assert moved == 1
    calls = transport_.all_parameters_for("CreateTexts")
    assert "texts" in calls[0] and "textsData" in calls[1]
    assert calls[1]["textsData"][0]["coordinate"] == {"x": 1.0, "y": 2.0, "z": 0.0}


def test_a_multipolygon_becomes_one_fill_per_part_with_its_own_holes() -> None:
    """Esri hands every ring of a feature in one list. Two parts and a hole
    in the first must not become one fill with two 'holes', which Archicad
    refuses; the closing point is dropped, since the add-on adds its own."""
    from sun_study.archicad.site_analysis import Drawing, _polygons

    big = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0)]
    hole = [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0), (40.0, 40.0)]
    other = [(200.0, 0.0), (250.0, 0.0), (250.0, 50.0), (200.0, 50.0), (200.0, 0.0)]
    island = [(48.0, 48.0), (52.0, 48.0), (52.0, 52.0), (48.0, 52.0), (48.0, 48.0)]
    polygons = _polygons([hole, other, big, island])
    assert [(len(outer), len(holes)) for outer, holes in polygons] == [(4, 1), (4, 0), (4, 0)]
    assert polygons[0][1][0][0] == (40.0, 40.0)

    drawing = Drawing(3000.0, "Context Analysis")
    drawing.fill("Zoning", [big, hole, other], "#f7c1bd")
    assert len(drawing.fills) == 2
    assert drawing.fills[0].rings[0][-1] != drawing.fills[0].rings[0][0]


def test_the_aerial_lands_under_the_cadastre_as_a_turned_figure(tmp_path: Path) -> None:
    """A tile is north-up in mercator; in the project frame it is turned by
    the frame's angle and sized by its corners on the ground, and it goes
    over the wire as base64 with its box in metres."""
    from sun_study.archicad.site_analysis import Drawing, _aerial, _figures
    from sun_study.site.imagery import Aerial, Tile

    (tmp_path / "aerial_0_0.jpg").write_bytes(bytes([0xFF, 0xD8]) + b" not really a jpeg")
    bundle = context_bundle()
    bundle.aerial = Aerial((Tile("aerial_0_0.jpg", 0.0, 0.0, 1.0, 1.0),), 3200, 2755, str(tmp_path))
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    drawing = Drawing(bundle.scale, "Context Analysis")
    assert _aerial(drawing, bundle, frame)
    (figure,) = drawing.figures
    # 690 mm at 1:3000 is 2070 m of ground, whatever the mercator stretch.
    assert figure.width_m == pytest.approx(2070.0, rel=0.01)
    assert figure.height_m == pytest.approx(1782.0, rel=0.01)
    # The tile's east edge: true east, which in a frame whose +Y is at bearing B sits at angle B.
    turn = math.degrees(figure.angle_rad) % 360.0
    assert turn == pytest.approx(319.052, abs=0.2), "true east is the +Y bearing, as an angle"

    connection, transport_ = connect(
        {"PlaceFigures": {"success": True, "elements": [{"guid": "PIC"}]}}
    )
    assert _figures(connection, drawing.figures, {figure.layer: 5}) == 1
    (request,) = transport_.parameters_for("PlaceFigures")["figures"]
    assert (
        request["format"] == "jpg"
        and request["anchor"] == "LeftBottom"
        and request["layerIndex"] == 5
    )
    assert request["box"]["xMax"] - request["box"]["xMin"] == pytest.approx(2070.0, rel=0.01)
    assert request["data"].startswith("/9g")


def test_place_names_wrap_the_way_the_office_sets_them() -> None:
    from sun_study.archicad.site_analysis import _wrapped

    assert _wrapped("ST GEORGE HOSPITAL") == "ST GEORGE\nHOSPITAL"
    assert _wrapped("KOGARAH") == "KOGARAH"
    assert _wrapped("GREEK ORTHODOX PARISH AND COMMUNITY OF KOGARAH") == (
        "GREEK ORTHODOX\nPARISH AND\nCOMMUNITY OF\nKOGARAH"
    )


def test_one_roundel_per_stop_not_one_per_kerb() -> None:
    from sun_study.site.osm import Stop, cluster_stops

    here = Stop(151.13, -33.96, "Princes Hwy")
    across = Stop(151.13 + 12.0 / (111_320.0 * 0.83), -33.96, "Princes Hwy")
    far = Stop(151.13 + 200.0 / (111_320.0 * 0.83), -33.96, "Next stop")
    merged = cluster_stops([here, across, far])
    assert len(merged) == 2 and merged[0].name == "Princes Hwy"


def test_the_map_field_is_centred_beside_the_title_block() -> None:
    from sun_study.archicad.layout import LayoutSheet
    from sun_study.archicad.site_analysis import _sheet_frame

    sheet = LayoutSheet(
        width_mm=841.0, height_mm=594.0, left_mm=10.0, top_mm=10.0, right_mm=10.0, bottom_mm=10.0
    )
    x0, y0, x1, y1 = _sheet_frame(sheet, width_mm=690.0, height_mm=594.0, title_block_mm=100.0)
    assert (x1 - x0) * 1000 == pytest.approx(690.0), "the field fits, so it keeps its size"
    assert (y1 - y0) * 1000 == pytest.approx(574.0), "the page is shorter than the field"
    assert (x0 + x1) / 2 * 1000 == pytest.approx(10.0 + (821.0 - 100.0) / 2)


def test_the_hatch_is_drawn_as_lines_clipped_to_the_polygon() -> None:
    from sun_study.archicad.site_analysis import _hatch_segments

    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]
    segments = _hatch_segments([square, hole], 1.0)
    assert segments, "a 10 m square at 1 m spacing has lines"
    for a, b in segments:
        assert abs((b[1] - a[1]) - (b[0] - a[0])) < 1e-6, "45 degrees"
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert 0 <= mid[0] <= 10 and 0 <= mid[1] <= 10
        assert not (4 < mid[0] < 6 and 4 < mid[1] < 6), "not across the hole"


def test_one_institution_parcel_is_drawn_once() -> None:
    bundle = context_bundle()
    same = bundle.institutions[0]
    bundle.institutions = (same, Institution("education", "St George Hospital School", same.rings))
    drawing = context_drawing(bundle, frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site"))
    parcels = [f for f in drawing.fills if f.element_id.startswith(("SA MEDICAL", "SA EDUCATION"))]
    assert len(parcels) == 1


def test_storeys_come_from_osm_then_the_lep_then_a_stated_default() -> None:
    from sun_study.archicad.context_model import storeys_of

    assert storeys_of(3, None, None) == (3, False)
    assert storeys_of(None, 9.5, None) == (3, False)
    assert storeys_of(None, None, 9.0) == (2, True)
    assert storeys_of(None, None, None) == (2, True)


def test_the_fetched_lot_is_turned_and_moved_onto_the_boundary_drawn_in_the_file() -> None:
    from sun_study.archicad.site_analysis import fit_frame

    bundle = site_bundle()
    base = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    ours = [base.ring(ring) for ring in bundle.site_rings]
    # The office drew the same lot 1.04 degrees straighter and 35 m away.
    turn, shift = math.radians(1.04), (35.5, 19.7)
    drawn = [
        (
            x * math.cos(turn) - y * math.sin(turn) + shift[0],
            x * math.sin(turn) + y * math.cos(turn) + shift[1],
        )
        for ring in ours
        for x, y in ring
    ]
    fit = fit_frame(base, bundle.site_rings, drawn)
    assert fit.turn_deg == pytest.approx(1.04, abs=0.01)
    assert fit.shift[0] == pytest.approx(35.5, abs=0.05)
    assert fit.shift[1] == pytest.approx(19.7, abs=0.05)
    assert fit.residual_m < 0.01
    # The fitted frame puts the lot where it was drawn, and inverts.
    landed = [fit.frame.project(lon, lat) for ring in bundle.site_rings for lon, lat in ring]
    assert all(
        math.hypot(a[0] - b[0], a[1] - b[1]) < 0.01 for a, b in zip(landed, drawn, strict=True)
    )
    lon, lat = fit.frame.unproject(*landed[0])
    assert (lon, lat) == pytest.approx(bundle.site_rings[0][0], abs=1e-8)
    assert "turned +1.04 deg" in fit.describe()
    again = type(fit).from_dict(fit.as_dict())
    assert again.frame == fit.frame

    grid = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site", north="grid")
    assert grid.convergence_deg == 0.0 and base.convergence_deg != 0.0


def test_a_drawn_boundary_that_turns_the_context_off_the_north_is_said() -> None:
    """The fit takes the drawing's turn over the project's north. A degree
    is a hand-traced boundary and passes quietly; a survey placed north up
    in a project whose north is 105 turns the context back by 15, which
    read as the north being ignored until the run said so."""
    from sun_study.archicad.site_analysis import fit_frame

    bundle = site_bundle()
    base = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    ours = [p for ring in bundle.site_rings for p in base.ring(ring)]

    def drawn_turned(degrees: float) -> list[tuple[float, float]]:
        turn = math.radians(degrees)
        return [
            (x * math.cos(turn) - y * math.sin(turn), x * math.sin(turn) + y * math.cos(turn))
            for x, y in ours
        ]

    assert fit_frame(base, bundle.site_rings, drawn_turned(1.04)).turned_from_north("x") is None
    note = fit_frame(base, bundle.site_rings, drawn_turned(-15.0)).turned_from_north(
        "on 'Site Boundary'"
    )
    assert note is not None
    assert "on 'Site Boundary' turns the context -15.0 deg" in note
    assert "--fit-layer none" in note


def test_the_blocks_are_the_lots_dissolved_without_the_site_and_clipped_to_the_extent() -> None:
    from sun_study.archicad.context_model import _blocks

    bundle = site_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    site_ring = list(rings_of(bundle.site_lots["features"][0]["geometry"])[0])
    # Two lots east of the site, touching along a shared side, and one far
    # outside the extent; the site's own lot is in the cadastre too.
    d = 0.0004
    lot_a = [
        (LON + d, LAT),
        (LON + 2 * d, LAT),
        (LON + 2 * d, LAT + d),
        (LON + d, LAT + d),
        (LON + d, LAT),
    ]
    lot_b = [
        (LON + 2 * d, LAT),
        (LON + 3 * d, LAT),
        (LON + 3 * d, LAT + d),
        (LON + 2 * d, LAT + d),
        (LON + 2 * d, LAT),
    ]
    far = [(LON + 1, LAT), (LON + 1.001, LAT), (LON + 1.001, LAT + 0.001), (LON + 1, LAT)]
    cadastre = collection(
        polygon(site_ring, lotidstring="1//DP1"),
        polygon(lot_a, lotidstring="2//DP1"),
        polygon(lot_b, lotidstring="3//DP1"),
        polygon(far, lotidstring="4//DP1"),
    )
    with_lots = replace(bundle, all_lots=cadastre)
    blocks, fell_back = _blocks(with_lots, frame)
    assert fell_back == 0
    assert len(blocks) == 1, "the two lots make one block; the site and the far lot are out"
    assert len(blocks[0]) == 4, "the shared side is gone"


def test_the_roads_and_the_blocks_stand_in_surfaces_of_their_own() -> None:
    """The terrain is what shows between the blocks, which is the roads. In
    the Mesh tool's default both were one green, and a road could not be told
    from a lot (asked on the Campsie sample, 11 November 2026)."""
    from sun_study.archicad.context_model import model_context

    bundle = site_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    d = 0.0004
    lot = [(LON + d, LAT), (LON + 2 * d, LAT), (LON + 2 * d, LAT + d), (LON + d, LAT + d)]
    with_lots = replace(bundle, all_lots=collection(polygon([*lot, lot[0]], lotidstring="2//DP1")))
    connection, transport_ = connect(
        {
            "GetAttributesByType": {"attributes": _layer_attributes()},
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetLayers": {"layers": _layer_states()},
            "CreateLayers": {"success": True},
            "CreateMesh": {"success": True, "guid": "MESH"},
            "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
            "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
            "GetElementsByType": {"elements": []},
            "GetStories": {"stories": [{"index": 0, "level": 0.0}]},
            "GetGeoLocation": {
                "projectLocation": {
                    "latitude": LAT,
                    "longitude": LON,
                    "altitude": 0.0,
                    "north": 0.0,
                }
            },
            "SetPropertyValuesOfElements": {"executionResults": [{"success": True}]},
            "GetAllProperties": {"properties": []},
            "GetPropertyValuesOfElements": {"propertyValuesForElements": []},
        }
    )
    report = model_context(connection, with_lots, frame)

    assert report.blocks == 1
    meshes = {m["elementId"]: m["surface"] for m in transport_.all_parameters_for("CreateMesh")}
    assert meshes["SA TERRAIN"]["name"] == "LORIINI ROAD"
    assert meshes["SA BLOCK 1"]["name"] == "LORIINI GROUND"
    road, ground = meshes["SA TERRAIN"]["colour"], meshes["SA BLOCK 1"]["colour"]
    assert abs(road["red"] - road["green"]) < 0.05, "a grey"
    assert ground["green"] > ground["red"] and ground["green"] > ground["blue"], "a green"


def test_an_add_on_that_takes_no_mesh_surface_still_gets_its_terrain() -> None:
    """The command's schema refuses a field it does not know, so an add-on
    built before meshes took a surface answers the whole request with an
    error. A terrain in one colour is better than none: it is asked again
    without, and the report says why the roads are not grey."""
    from sun_study.archicad.context_model import model_context
    from tests.unit.test_archicad_adapter import FakeTransport

    class OlderAddOn(FakeTransport):
        def send(self, payload: dict[str, Any]) -> dict[str, Any]:
            asked = payload.get("parameters", {})
            inner = asked.get("addOnCommandId", {}).get("commandName")
            if inner == "CreateMesh" and "surface" in asked.get("addOnCommandParameters", {}):
                self.sent.append(payload)
                refusal = {"error": {"code": 4002, "message": "surface is not expected"}}
                return {"succeeded": True, "result": {"addOnCommandResponse": refusal}}
            return super().send(payload)

    bundle = site_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    connection, transport_ = connect(
        {
            "GetAttributesByType": {"attributes": _layer_attributes()},
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetLayers": {"layers": _layer_states()},
            "CreateMesh": {"success": True, "guid": "MESH"},
            "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
            "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
            "GetElementsByType": {"elements": []},
            "GetStories": {"stories": [{"index": 0, "level": 0.0}]},
            "GetGeoLocation": {
                "projectLocation": {
                    "latitude": LAT,
                    "longitude": LON,
                    "altitude": 0.0,
                    "north": 0.0,
                }
            },
            "SetPropertyValuesOfElements": {"executionResults": [{"success": True}]},
            "GetAllProperties": {"properties": []},
            "GetPropertyValuesOfElements": {"propertyValuesForElements": []},
        }
    )
    older = OlderAddOn(transport_.responses)
    connection._transport = older
    report = model_context(connection, bundle, frame)

    asked = older.all_parameters_for("CreateMesh")
    assert ["surface" in one for one in asked] == [True, False], "once with, then without"
    assert report.terrain
    said = [note for note in report.notes if "takes no surface on a mesh" in note]
    assert len(said) == 1, report.notes


def test_the_neighbours_stand_on_the_ground_and_the_sites_own_are_left_out() -> None:
    from sun_study.archicad.context_model import model_context

    bundle = site_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    connection, transport_ = connect(
        {
            "GetAttributesByType": {"attributes": _layer_attributes()},
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetLayers": {"layers": _layer_states()},
            "CreateMesh": {"success": True, "guid": "MESH"},
            "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
            "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
            "GetElementsByType": {"elements": []},
            "GetStories": {"stories": [{"index": 0, "level": 0.0}, {"index": 5, "level": 4.6}]},
            # Project zero is sea level here, so the datum takes nothing off
            # and the levels below are the contours' own.
            "GetGeoLocation": {
                "projectLocation": {
                    "latitude": LAT,
                    "longitude": LON,
                    "altitude": 0.0,
                    "north": 0.0,
                }
            },
            "SetPropertyValuesOfElements": {"executionResults": [{"success": True}]},
            "GetAllProperties": {"properties": []},
            "GetPropertyValuesOfElements": {"propertyValuesForElements": []},
        }
    )
    report = model_context(connection, bundle, frame)
    assert report.terrain and report.contours == 2
    mesh = transport_.parameters_for("CreateMesh")
    assert len(mesh["outline"]) == 4 and mesh["skirt"] == "solid"
    assert all("z" in p for p in mesh["outline"])
    # The ground on the terrain layer (7), the buildings on theirs (9): a view
    # can show the neighbours without the mesh, or the mesh without them.
    assert mesh["layerIndex"] == 7 and mesh["elementId"] == "SA TERRAIN"
    # In a surface of its own: what shows between the blocks is the roads, and
    # in the Mesh tool's default they were the same green as the lots.
    assert mesh["surface"]["name"] == "LORIINI ROAD"
    assert set(mesh["surface"]["colour"]) == {"red", "green", "blue"}
    assert not any("takes no surface" in note for note in report.notes)
    assert len(mesh["levelLines"]) == 2, "both contours lie inside the extent"
    assert mesh["floorIndex"] == 0, "homed on the storey at level zero"
    slabs = transport_.parameters_for("CreateSlabs")["slabs"]
    # The one footprint in the fixture sits 30 m east of the site, two storeys
    # by OSM, standing on the ground the contours give -- through the add-on's
    # own command, with its layer, storey and ID in the one call.
    assert len(slabs) == 1 and report.on_site == 0
    assert slabs[0]["thickness"] == pytest.approx(2 * 3.1)
    assert slabs[0]["referencePlane"] == "bottom"
    # It stands 17 m east of the 28 m contour, the last on a slope rising 4 m
    # in 22: the slope carries on past it, one contour interval at most --
    # the state's 2 m, since the fixture's contours are the state's.
    assert slabs[0]["level"] == pytest.approx(30.0)
    assert slabs[0]["layerIndex"] == 9 and slabs[0]["floorIndex"] == 0
    assert slabs[0]["elementId"] == "SA NEIGHBOUR 2 STOREY (OSM)"
    assert len(slabs[0]["contours"][0]["points"]) >= 3
    assert report.blocks == 0, "no cadastre in the site bundle, so no blocks"
    assert "blocks: 0 meshes" in report.describe()


def test_a_neighbour_on_a_heritage_item_stands_in_its_own_surface() -> None:
    """The item's building reads as the item: its three faces in the heritage
    surface, named and coloured in the request so the add-on can make it,
    and HERITAGE on its ID. A conservation area is not an item."""
    from sun_study.archicad.context_model import HERITAGE_SURFACE, model_context

    east = LON + 0.00035
    west = LON - 0.00035
    bundle = replace(
        site_bundle(),
        heritage=collection(
            polygon(square(east, LAT, 14.0), LAY_CLASS="Item - General", H_NAME="Terrace"),
            polygon(square(west, LAT, 14.0), LAY_CLASS="Conservation Area"),
        ),
        furniture=osm.Furniture(
            buildings=(
                osm.Building(east, LAT, tuple(square(east, LAT, 10.0)), levels=2),
                osm.Building(west, LAT, tuple(square(west, LAT, 10.0)), levels=2),
            )
        ),
    )
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    connection, transport_ = connect(
        {
            "GetAttributesByType": {"attributes": _layer_attributes()},
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetLayers": {"layers": _layer_states()},
            "CreateMesh": {"success": True, "guid": "MESH"},
            "CreateSlabs": {
                "elements": [{"elementId": {"guid": "SLAB1"}}, {"elementId": {"guid": "SLAB2"}}]
            },
            "CreateGroups": {"groupGuids": [{"guid": "GROUP"}]},
            "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
            "GetElementsByType": {"elements": []},
            "GetStories": {"stories": [{"index": 0, "level": 0.0}]},
            "GetGeoLocation": {
                "projectLocation": {
                    "latitude": LAT,
                    "longitude": LON,
                    "altitude": 0.0,
                    "north": 0.0,
                }
            },
            "SetPropertyValuesOfElements": {"executionResults": [{"success": True}]},
            "GetAllProperties": {"properties": []},
            "GetPropertyValuesOfElements": {"propertyValuesForElements": []},
        }
    )
    report = model_context(connection, bundle, frame)
    slabs = transport_.parameters_for("CreateSlabs")["slabs"]
    assert len(slabs) == 2 and report.heritage == 1
    listed, plain = slabs
    assert listed["elementId"] == "SA NEIGHBOUR 2 STOREY (OSM) HERITAGE"
    assert listed["surface"]["name"] == HERITAGE_SURFACE
    colour = listed["surface"]["colour"]
    assert set(colour) == {"red", "green", "blue"}
    assert all(0.0 <= v <= 1.0 for v in colour.values()), "the add-on takes 0 to 1"
    assert plain["elementId"] == "SA NEIGHBOUR 2 STOREY (OSM)" and "surface" not in plain
    assert "1 on heritage items in the 'LORIINI HERITAGE' surface" in report.describe()


def test_the_location_is_the_site_on_the_grid_with_north_kept() -> None:
    from sun_study.archicad.context_model import set_project_location

    connection, transport_ = connect({"SetGeoLocation": {"success": True}})
    geo = set_project_location(connection, KOGARAH, (LON, LAT), ground_m=26.0)
    sent = transport_.parameters_for("SetGeoLocation")
    assert sent["projectLocation"]["latitude"] == LAT
    assert sent["projectLocation"]["north"] == pytest.approx(KOGARAH.north_radians)
    assert sent["surveyPoint"]["geoReferencingParameters"]["crsName"] == "EPSG:7856"
    assert 300_000 < sent["surveyPoint"]["position"]["eastings"] < 400_000
    assert geo.altitude_m == 26.0 and geo.project_north_bearing_deg == pytest.approx(319.052)


def test_the_models_ground_reads_across_the_slope_and_zero_where_there_is_none() -> None:
    from sun_study.archicad.context_model import _Ground

    contours = [
        (24.0, [(0.0, float(y)) for y in range(0, 100, 5)]),
        (26.0, [(20.0, float(y)) for y in range(0, 100, 5)]),
    ]
    ground = _Ground(contours)
    assert ground.at((10.0, 50.0)) == pytest.approx(25.0, abs=0.01), "halfway is halfway"
    assert ground.at((0.0, 50.0)) == pytest.approx(24.0)
    # Past the last contour the slope carries on, and never further than one
    # interval -- here read off the lines, 2 m -- and beyond the walk's reach
    # it is the nearest contour's level.
    assert ground.at((30.0, 50.0)) == pytest.approx(27.0)
    assert ground.at((100.0, 50.0)) == pytest.approx(28.0)
    assert ground.at((400.0, 50.0)) == pytest.approx(26.0)
    assert _Ground([]).at((0.0, 0.0)) == 0.0


def test_the_terrain_mesh_is_cut_to_the_model_and_read_at_the_bundles_interval() -> None:
    """``level_lines`` is the model's side of ``site.ground.mesh_lines``: the
    site's rings are what the detail is kept around, the model's square what
    the lines are cut to, and the interval is whoever drew the contours'."""
    from sun_study.archicad.context_model import level_lines
    from sun_study.archicad.site_analysis import _distance_to_ring, _map_rectangle
    from sun_study.site.geo import point_in_ring

    bundle = site_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    field = _map_rectangle(bundle, frame)
    contours = [
        (float(level), [(float(x), float(level) + 0.3 * (x % 2)) for x in range(-300, 300)])
        for level in range(-80, 80, 2)
    ]
    lines = level_lines(bundle, frame, contours)
    assert lines.interval_m == 2.0, "the fixture's contours are the state's"
    assert lines.lines and all(
        point_in_ring(x, y, field) for _, points in lines.lines for x, y in points
    ), "every level line is inside the model's square, never on its edge"
    # And each is carried to within a few centimetres of the edge it leaves by.
    ends = [points[i] for _, points in lines.lines for i in (0, -1)]
    assert any(_distance_to_ring(end, field) < 0.06 for end in ends)
    assert lines.vertices <= 12_000


# -- the future context -------------------------------------------------------------


def future_bundle() -> SiteBundle:
    """The site bundle with a cadastre and the controls a future context
    reads: the site's lot, an R4 lot east of it under a 25 m control at
    1.5:1, and an R2 lot west of it that keeps its house."""
    east, west = LON + 0.0004, LON - 0.0004
    site_ring = square(LON, LAT, 20.0)
    cadastre = collection(
        polygon(site_ring, lotidstring="1//DP1"),
        polygon(square(east, LAT, 30.0), lotidstring="2//DP1"),
        polygon(square(west, LAT, 30.0), lotidstring="3//DP1"),
    )
    buildings = (
        # On the site: what the proposal replaces, never a future neighbour.
        osm.Building(LON, LAT, tuple(square(LON, LAT, 8.0)), levels=1),
        # On the R4 lot under the 25 m control, two storeys today: raised.
        osm.Building(east, LAT, tuple(square(east, LAT, 10.0)), levels=2),
        # The same lot, already nine storeys -- over the control: left alone.
        osm.Building(east, LAT + 0.0001, tuple(square(east, LAT + 0.0001, 6.0)), levels=9),
        # On the R2 lot: a house whose future is a house.
        osm.Building(west, LAT, tuple(square(west, LAT, 10.0)), levels=1),
        # Three hundred metres off: beyond the reach.
        osm.Building(LON + 0.003, LAT, tuple(square(LON + 0.003, LAT, 10.0)), levels=1),
    )
    return replace(
        site_bundle(),
        furniture=osm.Furniture(buildings=buildings),
        all_lots=cadastre,
        zoning=collection(
            polygon(square(LON + 0.0002, LAT, 100.0), SYM_CODE="R4"),
            polygon(square(west, LAT, 40.0), SYM_CODE="R2"),
        ),
        height_of_building=collection(polygon(square(LON, LAT, 400.0), MAX_B_H=25.0)),
        floor_space_ratio=collection(polygon(square(LON, LAT, 400.0), FSR=1.5)),
    )


def test_each_neighbour_is_raised_to_its_height_control_on_its_own_footprint() -> None:
    from sun_study.archicad.future_context import FutureOptions, future_envelopes, lots_of

    bundle = future_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    lots = {lot.identifier: lot for lot in lots_of(bundle, frame)}
    assert set(lots) == {"1//DP1", "2//DP1", "3//DP1"}
    assert lots["2//DP1"].zone == "R4" and lots["2//DP1"].height_m == 25.0
    assert lots["2//DP1"].fsr == 1.5 and lots["3//DP1"].zone == "R2"
    assert lots["2//DP1"].area_m2 == pytest.approx(900.0, rel=0.01)

    report = future_envelopes(bundle, frame, FutureOptions(reach_m=60.0))
    assert [e.lot.identifier for e in report.envelopes] == ["2//DP1"], "named by its lot"
    assert report.on_site == 1, "the site's own building"
    assert report.at_limit == 1, "the nine-storey one is already over its control"
    assert report.other_zones == 1, "the house on land zoned for houses"
    assert report.beyond_reach == 1
    (raised,) = report.envelopes
    # The building that is there, on its own footprint, raised to the last
    # whole storey under 25 m: eight of 3.1 m. Not set back, not stepped.
    assert raised.storeys == 8 and raised.height_m == pytest.approx(24.8)
    assert raised.binding == "height" and len(raised.tiers) == 1
    assert raised.tiers[0].area_m2 == pytest.approx(100.0, rel=0.02), "its own 10 m footprint"
    assert "1 buildings raised to their height control" in report.describe()


def test_the_site_sheet_draws_the_envelope_dashed_with_its_storeys_written_in() -> None:
    from sun_study.archicad.future_context import FutureOptions, future_envelopes

    bundle = future_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    report = future_envelopes(bundle, frame, FutureOptions(reach_m=60.0))
    drawing = site_drawing(bundle, frame, future=report.envelopes)

    outlines = [
        line
        for line in drawing.lines
        if line.colour == "#c2189a" and line.dashed and line.layer.endswith(".Context")
    ]
    assert len(outlines) == 1, "one raised building, one outline"
    caption = next(t for t in drawing.texts if t.text.startswith("FUTURE"))
    # No ratio on it: nothing applied one, and a caption quoting it would say so.
    assert caption.text == "FUTURE 8 STOREY\n24.8 m"
    assert any("FUTURE CONTEXT" in t.text for t in drawing.texts), "the legend says what it is"
    assert len(drawing.layers) <= 5, drawing.layers

    plain = site_drawing(bundle, frame)
    assert not any(t.text.startswith("FUTURE") for t in plain.texts)
    assert not any("FUTURE CONTEXT" in t.text for t in plain.texts)


def test_the_envelopes_stand_as_slabs_on_their_own_layer_and_a_rerun_replaces_them() -> None:
    from sun_study.archicad.future_context import FutureOptions, model_future

    bundle = future_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    connection, transport_ = connect(
        {
            "GetAttributesByType": {
                "attributes": [
                    {"name": CONTEXT_LAYER, "index": 9, "attributeId": {"guid": "L9"}},
                    {"name": FUTURE_LAYER, "index": 10, "attributeId": {"guid": "L10"}},
                ]
            },
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetLayers": {
                "layers": [
                    {
                        "layerAttribute": {
                            "name": FUTURE_LAYER,
                            "isHidden": False,
                            "isLocked": False,
                        }
                    },
                ]
            },
            "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
            "GetDetailsOfElements": {
                "detailsOfElements": [
                    {"id": "SA FUTURE 9//DP9 2 STOREY 0-6.2 m", "layerIndex": 10},
                    {"id": "SA NEIGHBOUR 2 STOREY (OSM)", "layerIndex": 9},
                ]
            },
            "GetElementsByType": {
                "elements": [{"elementId": {"guid": "OLD"}}, {"elementId": {"guid": "KEEP"}}]
            },
            "DeleteElements": {"success": True},
            "GetStories": {"stories": [{"index": 0, "level": 0.0}, {"index": 5, "level": 4.6}]},
            # Project zero is sea level here, so the datum takes nothing off
            # and the levels below are the contours' own.
            "GetGeoLocation": {
                "projectLocation": {
                    "latitude": LAT,
                    "longitude": LON,
                    "altitude": 0.0,
                    "north": 0.0,
                }
            },
            "SetPropertyValuesOfElements": {"executionResults": [{"success": True}]},
            "GetAllProperties": {"properties": []},
            "GetPropertyValuesOfElements": {"propertyValuesForElements": []},
        }
    )
    report = model_future(connection, bundle, frame, options=FutureOptions(reach_m=60.0))

    assert report.layer == FUTURE_LAYER and report.slabs == 1
    assert len(report.future.envelopes) == 1
    # Only the last run's future slabs go; the context model's neighbour stays.
    doomed = transport_.parameters_for("DeleteElements")["elements"]
    assert [e["elementId"]["guid"] for e in doomed] == ["OLD", "OLD"], doomed
    slabs = transport_.parameters_for("CreateSlabs")["slabs"]
    # Eight storeys under a 25 m control: the building's own footprint, 0 to
    # 24.8 m, standing on the ground.
    assert len(slabs) == 1
    assert slabs[0]["layerIndex"] == 10 and slabs[0]["floorIndex"] == 0
    assert slabs[0]["thickness"] == pytest.approx(24.8)
    # Past the 28 m contour: the slope carries on, a 2 m interval at most.
    assert slabs[0]["level"] == pytest.approx(30.0), "on the ground the contours give"
    assert slabs[0]["elementId"] == "SA FUTURE 2//DP1 8 STOREY 0-24.8 m"
    assert "1 buildings raised to their height control" in report.describe()


def test_the_ratio_survives_the_round_trip_and_an_old_bundle_reads_as_none(
    tmp_path: Path,
) -> None:
    bundle = future_bundle()
    again = load_site(save(bundle, tmp_path / "data" / "site.json"))
    assert again.floor_space_ratio == bundle.floor_space_ratio
    old = bundle.as_dict()
    del old["floor_space_ratio"]
    assert SiteBundle.from_dict(old).floor_space_ratio == {
        "type": "FeatureCollection",
        "features": [],
    }


def test_the_summary_of_controls_states_the_separation_the_envelopes_use() -> None:
    bundle = SummaryBundle(
        address="1 Test St",
        site_address="1 TEST STREET",
        lot_description="LOT 1 - DP 1",
        site_area_m2=1000.0,
        controls=nsw.SiteControls(
            epi_name=None,
            lga_name=None,
            zone_code=None,
            zone_purpose=None,
            max_height_m=None,
            fsr=None,
            min_lot_size_m2=None,
            heritage=(),
        ),
    )
    by_label = {label: controls for _, label, controls in summary_rows(bundle)}
    assert by_label["3F. VISUAL PRIVACY / BUILDING SEPARATION"] == [
        "up to 4 storeys: 12 m between habitable rooms, 6 m to a side or rear boundary",
        "5 to 8 storeys: 18 m between habitable rooms, 9 m to a side or rear boundary",
        "9 storeys and over: 24 m between habitable rooms, 12 m to a side or rear boundary",
    ]


def test_the_model_is_placed_against_the_projects_declared_altitude() -> None:
    """The contours are AHD levels and the project's altitude says what RL
    project zero is, so placing at the raw contour level counts the site's
    height above sea level twice. At Bondi that stood the neighbourhood
    75.8 m above the storeys it was meant to sit around."""
    from sun_study.archicad.context_model import model_context

    bundle = site_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    responses: dict[str, Any] = {
        "GetAttributesByType": {"attributes": _layer_attributes()},
        "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
        "GetLayers": {"layers": _layer_states()},
        "CreateMesh": {"success": True, "guid": "MESH"},
        "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
        "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
        "GetElementsByType": {"elements": []},
        "GetStories": {"stories": [{"index": 0, "level": 0.0}]},
        # Project zero stands for RL 20: the ground at 24-28 must land at 4-8.
        "GetGeoLocation": {
            "projectLocation": {
                "latitude": LAT,
                "longitude": LON,
                "altitude": 20.0,
                "north": 0.0,
            }
        },
    }
    connection, transport_ = connect(responses)
    report = model_context(connection, bundle, frame)

    slab = transport_.parameters_for("CreateSlabs")["slabs"][0]
    # The ground under it is 30 AHD -- past the 28 m contour, the slope carried
    # on a 2 m interval -- and project zero is RL 20.
    assert slab["level"] == pytest.approx(10.0), "30 AHD against project zero at RL 20"
    mesh = transport_.parameters_for("CreateMesh")
    # A corner the contours do not reach carries the slope on past the last
    # one they do, an interval at most: 22 to 30 AHD, 2 to 10 above the datum.
    assert all(2.0 - 1e-9 <= point["z"] <= 10.0 + 1e-9 for point in mesh["outline"]), mesh[
        "outline"
    ]
    assert any("datum of 20.00 m" in note for note in report.notes), report.notes


def _context_responses(existing: list[str], then: list[str] | None = None) -> dict[str, Any]:
    """Enough of Archicad for model_context, with `existing` layers in it.

    ``then`` is what the project holds once a layer has been made: ensure_layer
    reads back after creating rather than believing the answer, so a script
    that never changes describes a project where creation silently did nothing.
    """

    def attributes(names: list[str]) -> dict[str, Any]:
        return {
            "attributes": [
                {"name": name, "index": 9, "attributeId": {"guid": "L9"}} for name in names
            ]
        }

    def layers(names: list[str]) -> dict[str, Any]:
        return {
            "layers": [
                {"layerAttribute": {"name": name, "isHidden": False, "isLocked": False}}
                for name in names
            ]
        }

    return {
        "GetAttributesByType": (
            attributes(existing)
            if then is None
            else Sequential(attributes(existing), attributes(then))
        ),
        "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
        "GetLayers": (
            layers(existing) if then is None else Sequential(layers(existing), layers(then))
        ),
        "CreateLayers": {"success": True},
        "CreateMesh": {"success": True, "guid": "MESH"},
        "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
        "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
        "GetElementsByType": {"elements": []},
        "GetStories": {"stories": [{"index": 0, "level": 0.0}]},
        "GetGeoLocation": {
            "projectLocation": {
                "latitude": LAT,
                "longitude": LON,
                "altitude": 0.0,
                "north": 0.0,
            }
        },
    }


def test_the_template_layer_is_used_rather_than_a_second_one_made() -> None:
    """The office keeps its neighbours in its own site group, and the layer is
    already there. Asked for by name, it is found and left alone -- the point
    of filing the fetched context under '03 |' instead of a layer of the
    tool's own is that a colleague finds neighbours where neighbours live,
    which fails if the run adds a second layer beside the template's."""
    from sun_study.archicad.context_model import model_context

    connection, transport_ = connect(_context_responses(existing=list(CONTEXT_LAYERS)))
    model_context(connection, site_bundle(), frame_for(KOGARAH, site_centre=(LON, LAT)))

    assert "CreateLayers" not in transport_.commands(), (
        "the template's own layers were there and a second set was made anyway"
    )


def test_a_site_group_the_project_does_not_have_gets_its_layers_made() -> None:
    """The other half: point it at a group that is not in the template and the
    layers are created there. Same call either way -- find or create -- so
    there is nothing to decide at the call site."""
    from sun_study.archicad.context_model import model_context

    naming.set_context_prefix("50 |")
    try:
        wanted = [
            "50 | Site Context.Terrain",
            "50 | Site Context.Roads",
            "50 | Site Context.Buildings",
        ]
        connection, transport_ = connect(_context_responses(existing=[], then=wanted))
        model_context(connection, site_bundle(), frame_for(KOGARAH, site_centre=(LON, LAT)))

        made = [
            layer["name"]
            for call in transport_.all_parameters_for("CreateLayers")
            for layer in call["layerDataArray"]
        ]
        assert made and made[0] == "50 | Site Context.Terrain"
        assert set(made) <= set(wanted), made
    finally:
        naming.set_context_prefix(naming.CONTEXT_PREFIX)


def test_a_project_that_will_not_say_its_altitude_is_placed_as_before() -> None:
    """The old behaviour, which is right for a project whose zero is sea
    level, and the only safe answer when the location cannot be read."""
    from sun_study.archicad.context_model import project_datum

    connection, _ = connect({"GetGeoLocation": {"surveyPoint": {}}})
    assert project_datum(connection) == 0.0


def test_the_datum_is_a_choice_of_words_or_a_number() -> None:
    from sun_study.archicad.context_model import parse_datum

    assert parse_datum(None) is None, "read it from the project"
    assert parse_datum("project") is None
    assert parse_datum("sea") == 0.0
    assert parse_datum("ahd") == 0.0
    assert parse_datum("12.5") == 12.5
    with pytest.raises(ValueError, match="'project', 'sea', or a number"):
        parse_datum("ground")


def test_a_datum_given_outright_beats_the_projects_own_altitude() -> None:
    """So a project whose altitude is wrong, or whose zero means something
    else, can still be modelled without editing Project Location."""
    from sun_study.archicad.context_model import model_context

    bundle = site_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    connection, transport_ = connect(
        {
            "GetAttributesByType": {"attributes": _layer_attributes()},
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetLayers": {"layers": _layer_states()},
            "CreateMesh": {"success": True, "guid": "MESH"},
            "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
            "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
            "GetElementsByType": {"elements": []},
            "GetStories": {"stories": [{"index": 0, "level": 0.0}]},
            # The project says 20; the caller says 26, and the caller wins.
            "GetGeoLocation": {
                "projectLocation": {
                    "latitude": LAT,
                    "longitude": LON,
                    "altitude": 20.0,
                    "north": 0.0,
                }
            },
        }
    )
    model_context(connection, bundle, frame, datum_m=26.0)
    slab = transport_.parameters_for("CreateSlabs")["slabs"][0]
    assert slab["level"] == pytest.approx(4.0), "30 AHD against a datum of 26"

    # And 'sea' puts it back at true AHD, whatever the project says.
    connection, transport_ = connect(
        {
            "GetAttributesByType": {"attributes": _layer_attributes()},
            "GetCurrentDatabase": {"databaseId": {"guid": "PLAN"}, "windowType": "FloorPlan"},
            "GetLayers": {"layers": _layer_states()},
            "CreateMesh": {"success": True, "guid": "MESH"},
            "CreateSlabs": {"elements": [{"elementId": {"guid": "SLAB"}}]},
            "GetDetailsOfElements": {"detailsOfElements": [{"layerIndex": 9}]},
            "GetElementsByType": {"elements": []},
            "GetStories": {"stories": [{"index": 0, "level": 0.0}]},
            "GetGeoLocation": {
                "projectLocation": {
                    "latitude": LAT,
                    "longitude": LON,
                    "altitude": 20.0,
                    "north": 0.0,
                }
            },
        }
    )
    model_context(connection, bundle, frame, datum_m=0.0)
    slab = transport_.parameters_for("CreateSlabs")["slabs"][0]
    assert slab["level"] == pytest.approx(30.0), "true AHD, as it was before the datum existed"


def tmp_jpeg() -> Path:
    """A file on disk for the picture commands to read and base64. The bytes
    are not a real JPEG; nothing here decodes them."""
    import tempfile

    path = Path(tempfile.gettempdir()) / "loriini_test_tile.jpg"
    path.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b" not really a jpeg")
    return path


def test_the_orthophoto_goes_down_as_a_figure_or_as_a_drawing() -> None:
    """Same picture, same box, two commands. A Figure is anchored by a
    corner; a Drawing is positioned by its box and has no anchor."""
    from sun_study.archicad.site_analysis import Drawing, _figures

    picture = tmp_jpeg()
    for wanted, command, key in (
        ("figure", "PlaceFigures", "figures"),
        ("drawing", "PlaceDrawings", "drawings"),
    ):
        drawing = Drawing(200.0, "Site Analysis", pictures_as=wanted)
        drawing.figure("Aerial", str(picture), (1.0, 2.0), 30.0, 20.0, name="aerial")
        connection, transport_ = connect({command: {"elements": [{"guid": "PIC"}]}})
        placed = _figures(connection, drawing.figures, {drawing.layer("Aerial"): 7}, wanted)

        assert placed == 1
        sent = transport_.parameters_for(command)[key][0]
        assert sent["box"] == {"xMin": 1.0, "yMin": 2.0, "xMax": 31.0, "yMax": 22.0}
        assert sent["layerIndex"] == 7 and sent["name"] == "aerial"
        assert sent["format"] == "jpg"
        assert ("anchor" in sent) is (wanted == "figure")


def test_an_add_on_without_the_command_says_which_one_is_missing() -> None:
    from sun_study.archicad.site_analysis import Drawing, _figures

    drawing = Drawing(200.0, "Site Analysis", pictures_as="drawing")
    drawing.figure("Aerial", str(tmp_jpeg()), (0.0, 0.0), 10.0, 10.0)
    connection, _ = connect(
        {"PlaceDrawings": ArchicadError("Archicad does not have the registered command")}
    )
    with pytest.raises(ArchicadError, match="no PlaceDrawings command"):
        _figures(connection, drawing.figures, {drawing.layer("Aerial"): 7}, "drawing")


def test_a_worksheet_the_run_will_have_to_make_is_named_before_the_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal arrives at the end -- after the geocoding, the fetching and
    the drawing -- and by then a person has been waiting four minutes for the
    news. D95 and D96 make it predictable: a worksheet already in the project
    enters without help, one the run creates does not. So the run can say at
    the start which of them it is about to have trouble with."""
    import typer

    from sun_study.cli import _say_which_worksheets_are_missing

    connection, _ = connect({"GetNavigatorItemTree": navigator_tree((f"{SS} Site Analysis", "N"))})
    said: list[str] = []
    monkeypatch.setattr(typer, "secho", lambda message, **kw: said.append(str(message)))

    _say_which_worksheets_are_missing(connection, context=True, site=True)

    spoken = " ".join(said)
    assert f"{SS} Context Analysis" in spoken, "the missing one is named"
    assert f"{SS} Site Analysis" not in spoken, "the one already there is not"
    assert "template" in spoken, "and the fix that ends it for good is named"


def test_nothing_is_said_when_every_worksheet_is_already_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary case on a project set up once. Silence is the point."""
    import typer

    from sun_study.cli import _say_which_worksheets_are_missing

    connection, _ = connect(
        {
            "GetNavigatorItemTree": navigator_tree(
                (f"{SS} Site Analysis", "A"), (f"{SS} Context Analysis", "B")
            )
        }
    )
    said: list[str] = []
    monkeypatch.setattr(typer, "secho", lambda message, **kw: said.append(str(message)))

    _say_which_worksheets_are_missing(connection, context=True, site=True)

    assert said == []


def test_the_terrain_skirt_hangs_below_the_ground_and_not_above_it() -> None:
    """The bug that made the Bondi context a plate with the neighbourhood
    hanging under it. Archicad stores a mesh skirt as a depth below the mesh
    level, positive downward -- send it a level and the solid body is mirrored
    to the other side of the ground.

    Worth a test precisely because nothing in a run says so: the counts, the
    layers and the element IDs are identical either way, and the only symptom
    is the model seen from underneath.
    """
    from sun_study.archicad.context_model import _skirt_depth

    # Ground 51.8 m below project zero, the skirt 2 m under that.
    assert _skirt_depth(-53.818) == pytest.approx(53.818)
    # And a site whose ground is above zero keeps the skirt under it.
    assert _skirt_depth(3.0) == pytest.approx(-3.0)
    # The sign is the whole point: a depth is never the level it came from.
    assert _skirt_depth(-10.0) > 0
    assert _skirt_depth(10.0) < 0


def test_every_mesh_the_context_makes_sends_a_depth_not_a_level() -> None:
    """Three call sites -- the terrain, the road blocks and the fallback --
    and one of them left on the old sign would put that mesh inside out while
    the others looked right."""
    import ast
    from pathlib import Path as _Path

    source = _Path("src/sun_study/archicad/context_model.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    sent = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "skirtLevel":
                sent.append(value)
    assert sent, "no skirtLevel is sent any more -- has the mesh changed?"
    bare = [
        ast.unparse(value)
        for value in sent
        if not (isinstance(value, ast.Call) and getattr(value.func, "id", "") == "_skirt_depth")
    ]
    assert not bare, "these send a level where Archicad wants a depth: " + ", ".join(bare)


def test_asking_to_be_located_is_enough_on_its_own() -> None:
    """--set-location used to need the site anchored at the origin as well, so
    on a project sitting on a city preset -- the one case it is most wanted --
    the flag quietly did nothing. Asking outright is now enough.

    Read off the source rather than run, because the branch sits four minutes
    into a run that fetches a suburb first.
    """
    import ast
    from pathlib import Path as _Path

    source = _Path("src/sun_study/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    guards = [
        ast.unparse(node.test)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and "set_project_location" in ast.unparse(node)
    ]
    assert guards, "the location is never set -- has the branch moved?"
    outer = guards[0]
    assert "set_location" in outer, "asking for the location does not reach it: " + outer


def test_anchoring_the_site_at_the_origin_locates_the_project_by_default() -> None:
    """--anchor site puts the origin on the site and, squared, turns the
    frame: a project that kept its old location would then stand its model in
    the wrong place and light it from the wrong side. Found on Darlinghurst,
    where the squared model went in with the north untouched."""
    import ast
    from pathlib import Path as _Path

    source = _Path("src/sun_study/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    guards = [
        ast.unparse(node.test)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and "set_project_location" in ast.unparse(node)
    ]
    assert len(guards) >= 2, "the location's own guard is gone -- has the branch moved?"
    inner = guards[1]
    assert "at_origin" in inner, "the anchor does not locate the project by default: " + inner


@pytest.mark.parametrize(
    ("asked", "stood"),
    [((), 1), (("--no-future-slabs",), 0)],
    ids=["slabs", "no-slabs"],
)
def test_a_run_told_no_future_slabs_draws_the_envelopes_and_stands_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, asked: tuple[str, ...], stood: int
) -> None:
    """The window's site sheet run works the future context out to draw it
    dashed, and leaves the slabs to the 3D context's run (D157): two runs
    standing them would put the future in the model twice, in two frames.
    --no-future-slabs is how it says so; without it the run stands them as
    it always did. Run through the command, with the fetching, Archicad and
    the drawing faked, since the branch sits after all three."""
    from types import SimpleNamespace

    from typer.testing import CliRunner

    from sun_study import cli
    from sun_study.archicad import future_context
    from sun_study.archicad import site_analysis as sheets
    from sun_study.site import pipeline

    bundle = SimpleNamespace(
        centre_lonlat=(151.13, -33.96), furniture=SimpleNamespace(buildings=("a neighbour",))
    )
    worked_out = SimpleNamespace(envelopes=("an envelope",), describe=lambda: "one envelope")
    drawn: list[Any] = []
    slabs: list[Any] = []

    def draw_site(*_args: Any, future: Any, **_kwargs: Any) -> Any:
        drawn.append(future)
        return SimpleNamespace(describe=lambda: "drawn", notes=())

    def model_future(*_args: Any, found: Any, **_kwargs: Any) -> Any:
        slabs.append(found)
        return SimpleNamespace(describe=lambda: "stood")

    monkeypatch.setattr(cli, "_connect", lambda *a, **k: object())
    monkeypatch.setattr(cli, "_say_which_worksheets_are_missing", lambda *a, **k: None)
    monkeypatch.setattr(cli, "read_geo_location", lambda connection: KOGARAH)
    monkeypatch.setattr(pipeline, "run_site", lambda *a, **k: bundle)
    monkeypatch.setattr(pipeline, "run_model", lambda *a, **k: bundle)
    monkeypatch.setattr(future_context, "future_envelopes", lambda *a, **k: worked_out)
    monkeypatch.setattr(sheets, "draw_site", draw_site)
    monkeypatch.setattr(future_context, "model_future", model_future)
    # The command files its layers under the site's own prefix, which is
    # process-wide: put back, or every later test names its layers "Site |".
    before, context_before = naming.prefix(), naming.context_prefix()
    try:
        result = CliRunner().invoke(
            cli.app,
            [
                "site",
                "1 Test St, Kogarah NSW",
                "--no-context",
                "--site",
                "--no-summary",
                "--future",
                *asked,
                "--model-radius",
                "250",
                "--future-reach",
                "250",
                "--anchor",
                "site",
                "--origin-at",
                "centre",
                "--fit-layer",
                "none",
                "--keep-location",
                "--out",
                str(tmp_path),
            ],
        )
    finally:
        naming.set_prefix(before)
        naming.set_context_prefix(context_before)

    assert result.exit_code == 0, result.output
    assert drawn == [("an envelope",)], "the envelopes reach the site sheet either way"
    assert slabs == [worked_out] * stood, "and stood from the same envelopes, when asked"


def test_locating_a_project_writes_the_grid_and_leaves_north_alone() -> None:
    """The survey point matters as much as the latitude: a project located by
    longitude alone georeferences to nothing an engineer can use. North is not
    the address's business -- turning it would move everything modelled."""
    from sun_study.archicad.context_model import set_project_location

    connection, transport_ = connect({"SetGeoLocation": {"success": True}})
    before = GeoLocation(latitude_deg=-33.8, longitude_deg=151.2, altitude_m=0.0, north_radians=1.5)

    set_project_location(connection, before, (151.2016, -33.8926), ground_m=24.0)

    sent = transport_.parameters_for("SetGeoLocation")
    assert sent["projectLocation"]["longitude"] == pytest.approx(151.2016)
    assert sent["projectLocation"]["altitude"] == pytest.approx(24.0)
    assert sent["projectLocation"]["north"] == pytest.approx(1.5), "north is left as it was"
    survey = sent["surveyPoint"]
    assert survey["position"]["eastings"] > 0 and survey["position"]["northings"] > 0
    assert survey["geoReferencingParameters"]["crsName"].startswith("EPSG:78"), survey
    assert "MGA zone 56" in survey["geoReferencingParameters"]["description"]


# ---------------------------------------------------------------------------
# The credit along the foot of the sheet. A drawing made from somebody's open
# data is a produced work, and a produced work carries their name.
# ---------------------------------------------------------------------------
def _credit_of(drawing: Any) -> str:
    """The credit line as drawn, rejoined if it wrapped."""
    from sun_study.archicad.site_analysis import CREDIT_MM

    return " ".join(t.text for t in drawing.texts if t.height_mm == CREDIT_MM)


def test_the_context_sheet_credits_the_registers_it_was_drawn_from() -> None:
    """In the publishers' own wording, and under the map where a credit
    goes."""
    bundle = context_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    drawing = context_drawing(bundle, frame)

    credit = _credit_of(drawing)
    assert "© State of New South Wales (Spatial Services" in credit
    assert "Department of Planning, Housing and Infrastructure" in credit
    assert "© OpenStreetMap contributors" in credit
    assert "Valhalla (FOSSGIS e.V.)" in credit


def test_the_credit_sits_under_the_map_and_not_in_it() -> None:
    from sun_study.archicad.site_analysis import CREDIT_MM

    bundle = context_bundle()
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    drawing = context_drawing(bundle, frame)

    from sun_study.archicad.site_analysis import _sheet_field

    lines = [t for t in drawing.texts if t.height_mm == CREDIT_MM]
    assert lines, "nothing was credited at all"
    corners = _sheet_field(bundle, frame)
    floor = min(y for _, y in corners)
    left = min(x for x, _ in corners)
    assert all(text.at[1] < floor for text in lines), "the credit is inside the map"
    assert all(text.at[0] == pytest.approx(left) for text in lines), "it does not start at the edge"


def test_the_sheet_field_is_square_to_the_page_on_a_turned_project() -> None:
    """The page is the project's, so its field is too. It was the bundle's
    north-up extent, which on a project squared to its site crossed the
    page and left the corners bare (Campsie, 11 November 2026)."""
    from dataclasses import replace

    from sun_study.archicad.site_analysis import _fetched_field, _sheet_field
    from sun_study.site.geo import turned_window
    from sun_study.site.pipeline import MAP_HEIGHT_MM, MAP_WIDTH_MM

    bundle = context_bundle()
    north_up = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    frame = replace(north_up, plus_y_bearing_deg=64.58)

    field = _sheet_field(bundle, frame)
    xs, ys = sorted({round(x, 6) for x, _ in field}), sorted({round(y, 6) for _, y in field})
    assert len(xs) == 2 and len(ys) == 2, "the field is not along the project's axes"
    assert xs[1] - xs[0] == pytest.approx(MAP_WIDTH_MM * bundle.scale / 1000.0)
    assert ys[1] - ys[0] == pytest.approx(MAP_HEIGHT_MM * bundle.scale / 1000.0)

    # Fetched for the north-up field alone, the corners have nothing in them
    # and the data is cut where it ends; fetched for any turn, it is whole.
    assert len(_fetched_field(bundle, frame)) > 4
    bundle.fetched = turned_window(bundle.extent)
    assert _fetched_field(bundle, frame) == field


def test_a_publisher_whose_service_was_down_is_not_credited() -> None:
    """The point of reading it off the bundle. A context sheet with no bus
    routes and no catchments on it has nothing of OpenStreetMap's to credit,
    and saying otherwise is a claim about a line that is not there."""
    bundle = context_bundle()
    bundle.bus = osm.BusData()
    bundle.isochrones = ()

    drawing = context_drawing(bundle, frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site"))

    credit = _credit_of(drawing)
    assert "OpenStreetMap" not in credit
    assert "Valhalla" not in credit
    assert "Spatial Services" in credit, "the cadastre is still theirs"


def test_bus_stops_are_credited_to_whoever_actually_supplied_them() -> None:
    """A Stop does not say where it came from, so the run writes it down:
    the same symbols on the same sheet are Transport for NSW's or
    OpenStreetMap's depending only on whether a key was in the environment."""
    osm_stops = context_bundle()
    assert "Transport for NSW" not in _credit_of(
        context_drawing(osm_stops, frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site"))
    )

    register = context_bundle()
    register.stops_from_tfnsw = True
    credit = _credit_of(
        context_drawing(register, frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site"))
    )
    assert "© Transport for NSW" in credit


def test_which_publishers_a_bundle_used_survives_being_saved(tmp_path: Path) -> None:
    """A sheet redrawn from a saved run must credit what that run fetched,
    not what today's environment would fetch."""
    bundle = context_bundle()
    bundle.stops_from_tfnsw = True

    again = load_context(save(bundle, tmp_path / "data" / "context.json"))

    assert again.sources_used() == bundle.sources_used()
    assert "tfnsw" in again.sources_used()


def test_the_summary_table_credits_the_register_its_figures_came_from() -> None:
    """A table of somebody else's numbers is as much a produced work as a map
    of their lines -- and a table with nothing in its controls column owes
    ePlanning nothing."""
    from sun_study.archicad.site_analysis import summary_drawing

    controls = nsw.SiteControls(epi_name="Georges River LEP 2021", zone_code="R3", fsr=0.9)
    filled = SummaryBundle("1 Test St", "1 TEST ST", "LOT 1 - DP 1", 850.0, controls)
    assert "Department of Planning" in _credit_of(summary_drawing(filled))

    bare = SummaryBundle("1 Test St", "1 TEST ST", "LOT 1 - DP 1", None, nsw.SiteControls())
    credit = _credit_of(summary_drawing(bare))
    assert "Department of Planning" not in credit
    assert "Spatial Services" in credit


# ---------------------------------------------------------------------------
# The City of Sydney's registers: trees at the size of their canopy, the
# council's own contours, and the council credited for both.
# ---------------------------------------------------------------------------
def council_site_bundle() -> SiteBundle:
    """The site bundle with the council's contours, one inventory tree 10 m
    across and one OSM tree nobody measured."""
    from sun_study.site import sources

    bundle = site_bundle()
    return replace(
        bundle,
        contours=tuple(
            nsw.Contour(c.elevation, c.coords, sources.CITY_OF_SYDNEY) for c in bundle.contours
        ),
        furniture=replace(
            bundle.furniture,
            trees=(
                Tree(
                    LON,
                    LAT + 0.0002,
                    10.0,
                    "measured",
                    12.0,
                    45.0,
                    "Platanus x acerifolia",
                    "London Plane",
                    sources.CITY_OF_SYDNEY,
                ),
                Tree(LON + 0.0002, LAT - 0.0002),
            ),
        ),
    )


def test_trees_are_drawn_the_size_of_their_canopy_and_a_guess_is_dashed() -> None:
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    drawing = site_drawing(council_site_bundle(), frame)

    plane = next(f for f in drawing.fills if "London Plane" in f.element_id)
    centre = frame.project(LON, LAT + 0.0002)
    radii = [math.dist(centre, p) for p in plane.rings[0]]
    assert radii == pytest.approx([5.0] * len(radii), abs=1e-6), "10 m across, on the ground"
    assert plane.wash and not plane.dashed
    assert plane.element_id == (
        "SA TREE London Plane (Platanus x acerifolia), canopy 10 m, 12 m high, trunk 45 cm"
    )

    guess = next(f for f in drawing.fills if f.element_id.startswith("SA TREE, canopy not"))
    assert guess.wash and guess.dashed, "a size nobody recorded is drawn dashed"
    radii = [math.dist(frame.project(LON + 0.0002, LAT - 0.0002), p) for p in guess.rings[0]]
    assert radii == pytest.approx([3.0] * len(radii), abs=1e-6)
    assert sum(f.element_id == "SA TREE TRUNK" for f in drawing.fills) == 2

    legend = [t.text for t in drawing.texts if t.layer.endswith(".Sheet")]
    assert "TREE, CANOPY TO SCALE" in legend
    assert "TREE, SIZE NOT RECORDED (6 m SHOWN)" in legend


def test_a_sheet_of_the_councils_contours_says_whose_and_at_what_interval() -> None:
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    council = [t.text for t in site_drawing(council_site_bundle(), frame).texts]
    assert "CONTOURS AT 1 m AHD, CITY OF SYDNEY 2020 SURVEY" in council
    state = [t.text for t in site_drawing(site_bundle(), frame).texts]
    assert "CONTOURS AT 2 m AHD, NSW SPATIAL SERVICES" in state


def test_the_council_is_credited_for_its_contours_and_its_trees_and_only_then() -> None:
    frame = frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")
    assert "© City of Sydney, CC BY 4.0" in _credit_of(site_drawing(council_site_bundle(), frame))
    assert "City of Sydney" not in _credit_of(site_drawing(site_bundle(), frame))


def test_the_councils_trees_are_not_credited_to_openstreetmap() -> None:
    """The trees say whose they are. A sheet whose furniture is the
    council's trees and nothing else -- Overpass down that morning -- owes
    OpenStreetMap nothing."""
    from sun_study.site import sources

    bundle = council_site_bundle()
    only_council = replace(
        bundle,
        furniture=osm.Furniture(
            trees=tuple(t for t in bundle.furniture.trees if t.source == sources.CITY_OF_SYDNEY)
        ),
    )
    used = only_council.sources_used()
    assert sources.CITY_OF_SYDNEY in used and sources.OSM not in used
    assert sources.OSM in bundle.sources_used(), "the nominal tree is OpenStreetMap's"


def _flush_project(drawing: Any, fills: int) -> Any:
    """A project that answers what ``_flush`` asks of it, for ``drawing``."""
    return connect(
        {
            "GetAttributesByType": {
                "attributes": [
                    {"name": name, "index": 10 + i, "attributeId": {"guid": f"L{i}"}}
                    for i, name in enumerate(drawing.layers)
                ]
            },
            "GetLayers": {
                "layers": [{"layerAttribute": {"name": "x", "isHidden": False, "isLocked": False}}]
            },
            "CreateLayers": {"success": True},
            "CreateFills": {"success": True, "elements": [{"guid": f"F{n}"} for n in range(fills)]},
            "CreatePolylines": {"elements": [{"elementId": {"guid": "P"}}] * 3},
        }
    )


def test_a_line_or_a_contour_that_is_not_dashed_is_drawn_solid() -> None:
    """D146: given no line type, an element takes its tool's -- the Polyline
    tool on the sample project was on Dense Dotted. Every plain line and every
    plain fill's contour is sent the continuous line type by name; dashed and
    dotted keep theirs."""
    from sun_study.archicad.site_analysis import Drawing, _Attributes, _flush

    drawing = Drawing(200.0, "Site Analysis")
    drawing.circle("Trees", (0.0, 0.0), 3.0, fill="#7dbb57", wash=True, dashed=True)
    drawing.circle("Trees", (9.0, 0.0), 3.0, fill="#7dbb57", wash=True)
    drawing.line("Site", [(0.0, 0.0), (10.0, 0.0)])
    drawing.line("Site", [(0.0, 5.0), (10.0, 5.0)], dashed=True)
    drawing.line("Site", [(0.0, 9.0), (10.0, 9.0)], dotted=True)
    connection, transport_ = _flush_project(drawing, 2)

    _flush(
        connection,
        drawing,
        _Attributes(solid_fill=1, dashed=2, pens=(), wash_fill=3, dotted=4, solid=7),
    )

    dashed_fill, plain_fill = transport_.parameters_for("CreateFills")["fills"]
    assert dashed_fill["lineTypeIndex"] == 2 and plain_fill["lineTypeIndex"] == 7
    plain, dashed, dotted = transport_.parameters_for("CreatePolylines")["polylinesData"]
    assert (plain["lineTypeIndex"], dashed["lineTypeIndex"], dotted["lineTypeIndex"]) == (7, 2, 4)


def test_the_solid_line_type_is_found_by_its_names() -> None:
    from sun_study.archicad.site_analysis import SOLID_LINES, attribute_index

    connection, _ = connect(
        {
            "GetAttributesByType": {
                "attributes": [
                    {"name": "Dense Dotted", "index": 3},
                    {"name": "Solid Line", "index": 1},
                ]
            }
        }
    )
    assert attribute_index(connection, "Line", SOLID_LINES) == 1


def test_a_dashed_fill_reaches_archicad_with_the_dashed_line_type() -> None:
    from sun_study.archicad.site_analysis import Drawing, _Attributes, _flush

    drawing = Drawing(200.0, "Site Analysis")
    drawing.circle("Trees", (0.0, 0.0), 3.0, fill="#7dbb57", wash=True, dashed=True)
    drawing.circle("Trees", (9.0, 0.0), 3.0, fill="#7dbb57", wash=True)
    connection, transport_ = connect(
        {
            "GetAttributesByType": {
                "attributes": [
                    {"name": name, "index": 10 + i, "attributeId": {"guid": f"L{i}"}}
                    for i, name in enumerate(drawing.layers)
                ]
            },
            "GetLayers": {
                "layers": [{"layerAttribute": {"name": "x", "isHidden": False, "isLocked": False}}]
            },
            "CreateLayers": {"success": True},
            "CreateFills": {"success": True, "elements": [{"guid": "F"}, {"guid": "G"}]},
        }
    )
    _flush(connection, drawing, _Attributes(solid_fill=1, dashed=2, pens=(), wash_fill=3))
    dashed, solid = transport_.parameters_for("CreateFills")["fills"]
    assert dashed["lineTypeIndex"] == 2 and dashed["fillIndex"] == 3
    assert "lineTypeIndex" not in solid
