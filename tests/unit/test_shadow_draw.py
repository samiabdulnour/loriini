"""Putting the shadows into Archicad: one layer to an hour, and a combination.

What is worth testing here is not that a hatch was sent -- it is the three
things that decide whether the sheets are readable and whether a rerun is
safe: the fills land on the right hour's layer, each hour's combination shows
that layer and hides its siblings while leaving the rest of the project alone,
and a second run replaces its own work instead of stacking on it.

The transport is the same fake the rest of the adapter tests use, so a test
reads as the exchange it expects.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pytest

from sun_study.archicad import naming
from sun_study.archicad.connection import ArchicadConnection, ArchicadError
from sun_study.archicad.shadows import (
    combination_name,
    draw_shadow_series,
    layer_name,
    shared_layer_name,
)
from sun_study.core.geometry import box, prism
from sun_study.core.shadow import (
    ADDITIONAL,
    EXISTING,
    cast_shadows,
    default_sources,
    ground_plane_grid,
)

WEST_45 = np.array([[-1.0, 0.0, 1.0]]) / np.sqrt(2.0)

#: The project's own layers, as ``GetAttributesByType`` reports them: id,
#: index and name, and no visibility. Two of them, one shown and one hidden,
#: because the thing worth proving about a combination is that it leaves both
#: exactly as it found them.
PROJECT_LAYERS = [
    ("wall", "01 | Wall.External", 11, False),
    ("dims", "05 | Dims/Notes.DA", 12, True),
]


class ShadowTransport:
    """A project that already has the tool's layers, answering by parameter.

    Purpose-built rather than scripted by command name, because reading layers
    takes *two* commands and ``GetAttributesByType`` is asked for Layers and
    for LayerCombinations in the same run. A fake that cannot tell those apart
    answers the layer lookup with the combination list and the drawing fails
    several steps later on a layer it was told does not exist -- which is a
    good deal harder to read than this class.
    """

    def __init__(self, labels: list[str], stale: int = 0) -> None:
        rows = list(PROJECT_LAYERS)
        for position, label in enumerate(labels):
            rows.append((f"shadow-{label}", layer_name(label), 100 + position, False))
        rows.append(("legend", shared_layer_name(), 200, False))
        self.layers = rows
        #: Fills left by an earlier run, spread over the tool's own layers so
        #: a rerun has something real to clear.
        self.stale = [
            {"elementId": {"guid": f"old-{index}-{layer}"}, "layerIndex": layer}
            for layer in [100 + n for n in range(len(labels))]
            for index in range(stale)
        ]
        self.sent: list[dict[str, Any]] = []
        #: Every Element ID written, in the order it was written.
        self.stamped: list[dict[str, Any]] = []
        #: Every group asked for, so a test can check what shares one.
        self.groups: list[dict[str, Any]] = []

    # -- the transport contract --------------------------------------------
    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.sent.append(payload)
        command = payload["command"]
        if command != "API.ExecuteAddOnCommand":
            return {"succeeded": True, "result": {}}
        name = payload["parameters"]["addOnCommandId"]["commandName"]
        given = payload["parameters"].get("addOnCommandParameters") or {}
        return {
            "succeeded": True,
            "result": {"addOnCommandResponse": self._answer(name, given)},
        }

    def _answer(self, command: str, given: dict[str, Any]) -> dict[str, Any]:
        if command == "GetAddOnVersion":
            return {"version": "1.5.7"}
        if command == "GetAttributesByType":
            if given.get("attributeType") == "Fill":
                return {
                    "attributes": [
                        {"name": "Solid Fill", "index": 65},
                        {"name": "Empty Fill", "index": 137},
                        {"name": "25 %", "index": 24},
                    ]
                }
            if given.get("attributeType") == "Line":
                return {
                    "attributes": [
                        {"name": "Dense Dotted", "index": 3},
                        {"name": "Solid Line", "index": 1},
                    ]
                }
            if given.get("attributeType") == "Layer":
                return {
                    "attributes": [
                        {"attributeId": {"guid": guid}, "name": name, "index": index}
                        for guid, name, index, _ in self.layers
                    ]
                }
            return {"attributes": []}  # no layer combination of ours exists yet
        if command == "GetLayers":
            asked = [entry["attributeId"]["guid"] for entry in given["attributeIds"]]
            by_guid = {guid: (name, hidden) for guid, name, _, hidden in self.layers}
            return {
                "layers": [
                    {"name": by_guid[guid][0], "isHidden": by_guid[guid][1], "isLocked": False}
                    for guid in asked
                ]
            }
        if command == "GetElementsByType":
            return {"elements": self.stale if given.get("elementType") == "Hatch" else []}
        if command == "GetDetailsOfElements":
            return {
                "detailsOfElements": [
                    {"layerIndex": element["layerIndex"]} for element in given["elements"]
                ]
            }
        if command == "DeleteElements":
            return {"executionResults": [{"success": True} for _ in given["elements"]]}
        if command == "CreateHatches":
            return {"elements": [{"elementId": {"guid": "fill"}} for _ in given["hatchesData"]]}
        if command == "CreatePolylines":
            return {"elements": [{"elementId": {"guid": "line"}} for _ in given["polylinesData"]]}
        if command == "CreateTexts":
            return {"elements": [{"guid": "text"} for _ in given["texts"]]}
        if command == "CreateFills":
            # The add-on's shape, not Tapir's: a bare guid.
            return {"elements": [{"guid": "fill"} for _ in given["fills"]]}
        if command in ("CreateLayers", "CreateLayerCombinations"):
            return {"attributeIds": []}
        if command == "CreateGroups":
            groups = given["elementGroups"]
            self.groups.extend(groups)
            return {"groupGuids": [{"groupId": {"guid": f"group-{n}"}} for n in range(len(groups))]}
        if command == "GetAllProperties":
            # Both of them, because the project really carries both and only
            # one of them can be written to.
            return {
                "properties": [
                    {
                        "propertyId": {"guid": "prop-element-id"},
                        "propertyGroupName": "General Parameters",
                        "propertyName": "Element ID",
                        "propertyIsEditable": True,
                        "propertyValueType": "string",
                    },
                    {
                        "propertyId": {"guid": "prop-hotlink-id"},
                        "propertyGroupName": "General Parameters",
                        "propertyName": "Hotlink and Element ID",
                        "propertyIsEditable": False,
                        "propertyValueType": "string",
                    },
                ]
            }
        if command == "GetFavoritesByType":
            # The project's Fill Favorites. An unknown name is refused rather
            # than drawn with the tool's own settings, so the list matters.
            return {"favorites": ["General_Fill", "LORIINI"]}
        if command == "SetPropertyValuesOfElements":
            self.stamped.extend(given["elementPropertyValues"])
            return {"executionResults": [{"success": True} for _ in given["elementPropertyValues"]]}
        raise AssertionError(f"unscripted command {command!r}")

    # -- reading it back ----------------------------------------------------
    def all_parameters_for(self, command: str) -> list[dict[str, Any]]:
        return [
            dict(payload["parameters"]["addOnCommandParameters"])
            for payload in self.sent
            if payload["command"] == "API.ExecuteAddOnCommand"
            and payload["parameters"]["addOnCommandId"]["commandName"] == command
        ]


def series(labels: list[str] | None = None, envelope: bool = True):  # type: ignore[no-untyped-def]
    labels = labels or ["9AM", "12PM"]
    grid = ground_plane_grid(
        (np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        datum_m=0.0,
        spacing_m=2.0,
        margin_m=40.0,
    )
    return cast_shadows(
        grid,
        sources=default_sources(
            box((-40.0, -5.0, 0.0), (-30.0, 5.0, 10.0)),
            box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
            prism([(0, -5), (10, -5), (10, 5), (0, 5)], 0.0, 9.5) if envelope else None,
        ),
        sun_vectors=np.repeat(WEST_45, len(labels), axis=0),
        moments=[dt.datetime(2024, 6, 21, 9 + i, tzinfo=dt.UTC) for i in range(len(labels))],
        labels=labels,
        spacing_m=2.0,
    )


def connect(labels: list[str], stale: int = 0):  # type: ignore[no-untyped-def]
    transport = ShadowTransport(labels, stale)
    return ArchicadConnection(transport), transport


def hatches(transport: ShadowTransport) -> list[dict[str, Any]]:
    """Every fill drawn, by either route, in Tapir's spelling.

    The add-on's ``CreateFills`` is spelled back so the tests can ask the same
    questions of both: which layer, which storey, which pen.
    """
    out: list[dict[str, Any]] = []
    for call in transport.all_parameters_for("CreateHatches"):
        out.extend(call["hatchesData"])
    back = {
        "layerIndex": "layerIndex",
        "floorIndex": "floorInd",
        "fillPen": "fillPenIndex",
        "backgroundPen": "fillBackgroundPenIndex",
        "contourPen": "contourPenIndex",
        "fillIndex": "fillIndex",
        "showArea": "showArea",
        "foregroundColour": "foregroundColour",
    }
    for call in transport.all_parameters_for("CreateFills"):
        for fill in call["fills"]:
            one: dict[str, Any] = {"coordinates": fill["contours"][0]["points"]}
            one.update({back[key]: value for key, value in fill.items() if key in back})
            out.append(one)
    return out


# -- the fills -------------------------------------------------------------


def test_each_hour_is_drawn_on_its_own_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twenty-one hours on one layer is twenty-one overlapping fills and one
    unreadable plan. The layer is the only thing separating them."""
    connection, transport = connect(["9AM", "12PM"])

    report = draw_shadow_series(connection, series(["9AM", "12PM"]))

    assert report.layers == (layer_name("9AM"), layer_name("12PM"))
    drawn = {hatch["layerIndex"] for hatch in hatches(transport)}
    assert len(drawn) >= 2, "the two hours did not land on different layers"


def test_a_shadow_fill_never_prints_its_own_area_across_the_plan() -> None:
    """A Fill inherits the Fill tool's default, and on a real project that
    default has Show Area Text on -- which puts a square-metre figure on every
    rectangle of a tiled shadow, and a shadow with a courtyard in it is
    tiled."""
    connection, transport = connect(["9AM"])

    draw_shadow_series(connection, series(["9AM"]))

    assert all(hatch["showArea"] is False for hatch in hatches(transport))


def test_a_plan_fill_carries_its_storey_and_a_worksheet_fill_does_not() -> None:
    """Tapir's own tracker records a floor index silently destroying elements
    in a database that has no storeys."""
    connection, transport = connect(["9AM"])
    draw_shadow_series(connection, series(["9AM"]), storey_index=2)
    assert all(hatch["floorInd"] == 2 for hatch in hatches(transport))

    connection, transport = connect(["9AM"])
    draw_shadow_series(connection, series(["9AM"]), storey_index=None)
    assert all("floorInd" not in hatch for hatch in hatches(transport))


def test_the_existing_shadow_is_drawn_under_what_the_proposal_adds() -> None:
    """Back to front: the existing shadow is the ground the argument is read
    against, and the proposal's own addition is the thing being looked at."""
    from sun_study.archicad.shadows import drawing_order, styles_for

    drawn = series(["9AM"])
    order = drawing_order(drawn.sources)
    assert order.index(EXISTING) < order.index(ADDITIONAL)

    connection, transport = connect(["9AM"])
    draw_shadow_series(connection, drawn)

    pens = [hatch["fillPenIndex"] for hatch in hatches(transport)]
    styles = styles_for(drawn.sources)
    assert pens.index(styles[EXISTING].fill_pen) < pens.index(styles[ADDITIONAL].fill_pen)


def test_the_site_boundary_is_drawn_once_not_once_an_hour() -> None:
    """It is identical at every instant. Twenty-one copies is twenty-one
    things to correct when somebody changes a pen."""
    connection, transport = connect(["9AM", "12PM", "3PM"])

    draw_shadow_series(
        connection,
        series(["9AM", "12PM", "3PM"]),
        boundary=((0.0, -5.0), (10.0, -5.0), (10.0, 5.0), (0.0, 5.0)),
        boundary_pen=7,
    )

    on_seven = [hatch for hatch in hatches(transport) if hatch["fillPenIndex"] == 7]
    assert len(on_seven) == 1


# -- the combinations ------------------------------------------------------


def test_an_hours_combination_shows_that_hour_and_hides_the_others() -> None:
    """What makes a View of the plan a drawing of one hour."""
    labels = ["9AM", "12PM", "3PM"]
    connection, transport = connect(labels)

    draw_shadow_series(connection, series(labels))

    written = transport.all_parameters_for("CreateLayerCombinations")
    assert len(written) == len(labels)
    nine = written[0]["layerCombinationDataArray"][0]
    hidden = {entry["attributeId"]["guid"]: entry["isHidden"] for entry in nine["layers"]}
    assert hidden["shadow-9AM"] is False, "the hour being drawn"
    assert hidden["shadow-12PM"] is True and hidden["shadow-3PM"] is True, "its siblings"
    assert hidden["legend"] is False, "the legend and boundary are shared"


def test_a_combination_leaves_the_rest_of_the_project_as_it_found_it() -> None:
    """What belongs on a site plan is the practice's decision, already recorded
    in whatever combination they draw site plans with. A combination built from
    this tool's opinion of somebody else's drawing would be worse than none."""
    connection, transport = connect(["9AM"])

    draw_shadow_series(connection, series(["9AM"]))

    entry = transport.all_parameters_for("CreateLayerCombinations")[0]
    states = {
        row["attributeId"]["guid"]: row["isHidden"]
        for row in entry["layerCombinationDataArray"][0]["layers"]
    }
    assert states["wall"] is False, "was shown, stays shown"
    assert states["dims"] is True, "was hidden, stays hidden"


def test_the_combinations_are_named_for_the_hour_they_show() -> None:
    connection, _ = connect(["9AM"])

    report = draw_shadow_series(connection, series(["9AM"]))

    assert report.combinations == (combination_name("9AM"),)
    assert naming.prefix() in report.combinations[0]


# -- rerunning -------------------------------------------------------------


def test_a_rerun_clears_its_own_fills_before_drawing_again() -> None:
    """Otherwise the second run stacks a set of fills on the first and every
    shadow quietly doubles in contour weight."""
    connection, _ = connect(["9AM", "12PM"], stale=3)

    report = draw_shadow_series(connection, series(["9AM", "12PM"]))

    assert report.cleared == 6, "three fills off each of the two layers"


# -- what the run says out loud --------------------------------------------


def test_an_hour_with_the_sun_down_is_named_rather_than_drawn_black() -> None:
    grid = ground_plane_grid(
        (np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        datum_m=0.0,
        spacing_m=4.0,
        margin_m=20.0,
    )
    night = cast_shadows(
        grid,
        sources=default_sources(
            box((-40.0, -5.0, 0.0), (-30.0, 5.0, 10.0)),
            box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
        ),
        sun_vectors=np.array([[-1.0, 0.0, -0.5]]),
        moments=[dt.datetime(2024, 6, 21, 17, tzinfo=dt.UTC)],
        labels=["5PM"],
        spacing_m=4.0,
    )
    connection, _ = connect(["5PM"])

    report = draw_shadow_series(connection, night)

    assert report.below_horizon == ("5PM",)
    assert "below the horizon" in report.describe()


def test_terrain_in_the_context_is_a_warning_and_not_a_silent_grey_sheet() -> None:
    """It cannot be seen in the drawing: a solid grey sheet is exactly what a
    dense city at 9am looks like to somebody who was not there."""
    grid = ground_plane_grid(
        (np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        datum_m=0.0,
        spacing_m=4.0,
        margin_m=20.0,
    )
    under_a_lid = cast_shadows(
        grid,
        sources=default_sources(
            box((-300.0, -300.0, 5.0), (300.0, 300.0, 6.0)),
            box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
        ),
        sun_vectors=WEST_45,
        moments=[dt.datetime(2024, 6, 21, 12, tzinfo=dt.UTC)],
        labels=["12PM"],
        spacing_m=4.0,
    )
    connection, _ = connect(["12PM"])

    report = draw_shadow_series(connection, under_a_lid)

    assert "WARNING" in report.describe()
    assert "site mesh" in report.describe()


def test_the_areas_are_reported_so_nobody_scales_them_off_the_drawing() -> None:
    connection, _ = connect(["9AM"])

    report = draw_shadow_series(connection, series(["9AM"]))

    assert report.areas_m2["9AM"][EXISTING] > 0.0
    assert report.areas_m2["9AM"][ADDITIONAL] > 0.0
    assert "m2" in report.describe()


# -- the legend a six-row sheet needs -------------------------------------


def test_baselines_are_grey_and_scenarios_are_blue_in_the_sheets_own_colours() -> None:
    """The ramps are sampled out of SSDA 401's legend, so a run reproduces the
    sheet rather than approximating it: what will be there recedes in grey,
    what is being argued about comes forward in blue."""
    from sun_study.archicad.shadows import BASELINE_RAMP, SCENARIO_RAMP, styles_for
    from sun_study.core.shadow import BASELINE, SCENARIO, SourceSpec

    styles = styles_for(
        [
            SourceSpec("existing", "Existing neighbouring buildings", BASELINE),
            SourceSpec("future", "Future neighbouring context buildings", BASELINE),
            SourceSpec("on site", "Existing structures within the site", BASELINE),
            SourceSpec("tod", "TOD", SCENARIO),
            SourceSpec("sears", "SEARs", SCENARIO),
            SourceSpec("proposed", "Proposed building envelope", SCENARIO),
        ]
    )

    assert [styles[key].rgb for key in ("existing", "future", "on site")] == list(BASELINE_RAMP)
    assert [styles[key].rgb for key in ("tod", "sears", "proposed")] == list(SCENARIO_RAMP)
    # The legend row is the sheet's words, upper-cased the way a title block is.
    assert styles["on site"].label == "EXISTING STRUCTURES WITHIN THE SITE"
    # One pen each, so a pen table can be matched row by row.
    assert len({style.fill_pen for style in styles.values()}) == 6


def test_every_baseline_is_drawn_under_every_scenario() -> None:
    """Scenarios genuinely overlap, so this decides what a reader sees and not
    merely which hairline wins on a shared edge."""
    from sun_study.archicad.shadows import drawing_order
    from sun_study.core.shadow import BASELINE, SCENARIO, SourceSpec

    order = drawing_order(
        [
            SourceSpec("tod", "TOD", SCENARIO),
            SourceSpec("existing", "Existing", BASELINE),
            SourceSpec("proposed", "Proposed", SCENARIO),
            SourceSpec("future", "Future", BASELINE),
        ]
    )

    assert order == ("existing", "future", "tod", "proposed")


# -- the frame the fills are drawn in --------------------------------------


def test_every_ring_is_moved_into_the_project_frame() -> None:
    """The bug this exists to end. A shadow is computed where the exporter put
    the geometry and drawn where Archicad keeps it, and with a Survey Point
    export those differ by the site's north angle -- 31.5 degrees on the Crows
    Nest model. Drawn uncorrected, every fill is the right shape in the wrong
    place at the wrong angle, and the sheet looks perfectly plausible."""
    import numpy as np

    from sun_study.core.geometry import PlanTransform, rotation_about_z

    turn = PlanTransform(
        rotation=rotation_about_z(-31.516)[:2, :2],
        offset=np.array([12.0, -5.0]),
        rmse_m=0.0,
    )
    connection, transport = connect(["9AM"])
    drawn = series(["9AM"])
    draw_shadow_series(connection, drawn, transform=turn)
    turned = [h["coordinates"] for h in hatches(transport)]

    connection, transport = connect(["9AM"])
    draw_shadow_series(connection, drawn)
    plain = [h["coordinates"] for h in hatches(transport)]

    assert len(turned) == len(plain) and turned, "the same fills, moved"
    # Every one of them, not merely the first: a half-corrected drawing still
    # tiles and still looks like a shadow while sitting off the model.
    for moved, original in zip(turned, plain, strict=True):
        source = np.array([[p["x"], p["y"]] for p in original])
        assert np.allclose(np.array([[p["x"], p["y"]] for p in moved]), turn.apply(source))


def test_a_native_export_is_checked_by_its_own_guids() -> None:
    """A native export carries Archicad's guids, not IFC GlobalIds, and sits
    in the project's frame already. Nothing is looked up by IFC id, the turn
    is zero, and the boxes confirm the identity rather than being skipped."""
    from sun_study.archicad.shadows import project_frame

    class Boxes:
        def __init__(self) -> None:
            self.asked: list[str] = []

        def send(self, payload: dict[str, Any]) -> dict[str, Any]:
            name = payload["parameters"]["addOnCommandId"]["commandName"]
            self.asked.append(name)
            given = payload["parameters"]["addOnCommandParameters"]
            answer: dict[str, Any] = {"version": "1.5.7"}
            if name == "Get3DBoundingBoxes":
                centres = {"a": (10.0, 20.0), "b": (-30.0, 5.0)}
                answer = {
                    "boundingBoxes3D": [
                        {
                            "boundingBox3D": {
                                "xMin": centres[e["elementId"]["guid"]][0] - 1,
                                "xMax": centres[e["elementId"]["guid"]][0] + 1,
                                "yMin": centres[e["elementId"]["guid"]][1] - 1,
                                "yMax": centres[e["elementId"]["guid"]][1] + 1,
                            }
                        }
                        for e in given["elements"]
                    ]
                }
            return {"succeeded": True, "result": {"addOnCommandResponse": answer}}

    transport = Boxes()
    north = np.radians(58.4)
    frame, note = project_frame(
        ArchicadConnection(transport),
        [("a", 10.0, 20.0), ("b", -30.0, 5.0)],
        north_radians=north,
        export_bearing_deg=(270.0 + 58.4) % 360.0,
        archicad_guids=True,
    )

    assert "GetElementsByIFCIds" not in transport.asked
    assert np.allclose(frame.rotation, np.eye(2))
    assert np.allclose(frame.offset, 0.0)
    assert "checked against 2 elements" in note


def test_every_hour_of_the_design_is_outlined_on_one_layer_of_its_own() -> None:
    """Lines, not fills, on a layer per day, labelled by hour, with a
    combination showing it; and every hour's own combination hides it."""
    from sun_study.archicad.shadows import (
        all_hours_combination_name,
        all_hours_layer_name,
        designed_source,
    )

    labels = ["9AM", "12PM"]
    grid = ground_plane_grid(
        (np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        datum_m=0.0,
        spacing_m=2.0,
        margin_m=40.0,
    )
    sources = default_sources(
        box((-40.0, -5.0, 0.0), (-30.0, 5.0, 10.0)),
        box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
        None,
    )
    key = designed_source([source.spec for source in sources])
    assert key == ADDITIONAL
    drawn_series = cast_shadows(
        grid,
        sources=sources,
        sun_vectors=np.repeat(WEST_45, len(labels), axis=0),
        moments=[dt.datetime(2024, 6, 21, 9 + i, tzinfo=dt.UTC) for i in range(len(labels))],
        labels=labels,
        spacing_m=2.0,
        outline=key,
    )
    assert all(instant.outlines[key] for instant in drawn_series.instants)

    connection, transport = connect(labels)
    day = "JUNE 21"
    transport.layers.append(("all-hours", all_hours_layer_name(day), 300, False))
    report = draw_shadow_series(connection, drawn_series, all_hours=key, all_hours_pen=45)

    assert not transport.all_parameters_for("CreatePolylines"), "fills, not polylines (D145)"
    outlines = [
        fill
        for call in transport.all_parameters_for("CreateFills")
        for fill in call["fills"]
        if fill["layerIndex"] == 300
    ]
    assert outlines
    # D147, the office's own shadow fill: 25 %, drafting, the pen, a
    # transparent background and no outline.
    assert all(fill["fillIndex"] == 24 for fill in outlines), "the 25 % fill"
    assert all(fill["determination"] == "drafting" for fill in outlines)
    assert all(fill["fillPen"] == 45 and fill["backgroundPen"] == 0 for fill in outlines)
    assert all(fill["contourPen"] == 0 for fill in outlines), "no outline"
    assert all(fill["lineTypeIndex"] == 1 for fill in outlines), "continuous, not dense dotted"
    assert all(
        fill["contours"][0]["points"][0] != fill["contours"][0]["points"][-1] for fill in outlines
    ), "left open: the add-on closes it"
    texts = [
        text["text"]
        for call in transport.all_parameters_for("CreateTexts")
        for text in call["texts"]
    ]
    assert sorted(texts) == sorted(labels), "one label per hour"
    assert report.all_hours == (all_hours_combination_name(day),)

    written = transport.all_parameters_for("CreateLayerCombinations")
    by_name = {
        entry["name"]: {row["attributeId"]["guid"]: row["isHidden"] for row in entry["layers"]}
        for call in written
        for entry in call["layerCombinationDataArray"]
    }
    assert by_name[all_hours_combination_name(day)]["all-hours"] is False
    assert by_name[all_hours_combination_name(day)]["shadow-9AM"] is True
    assert by_name[combination_name("9AM")]["all-hours"] is True, "an hour alone hides it"


def test_only_the_every_hour_drawing_draws_no_hour_of_its_own() -> None:
    """D144: the fills are now for the design's every-hour drawing alone. No
    fill and no combination per hour; the every-hour lines, labels and
    combination as before."""
    from sun_study.archicad.shadows import (
        all_hours_combination_name,
        all_hours_layer_name,
        designed_source,
    )

    labels = ["9AM", "12PM"]
    grid = ground_plane_grid(
        (np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        datum_m=0.0,
        spacing_m=2.0,
        margin_m=40.0,
    )
    sources = default_sources(
        box((-40.0, -5.0, 0.0), (-30.0, 5.0, 10.0)),
        box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
        None,
    )
    key = designed_source([source.spec for source in sources])
    drawn_series = cast_shadows(
        grid,
        sources=sources,
        sun_vectors=np.repeat(WEST_45, len(labels), axis=0),
        moments=[dt.datetime(2024, 6, 21, 9 + i, tzinfo=dt.UTC) for i in range(len(labels))],
        labels=labels,
        spacing_m=2.0,
        outline=key,
    )
    connection, transport = connect(labels)
    day = "JUNE 21"
    transport.layers.append(("all-hours", all_hours_layer_name(day), 300, False))

    report = draw_shadow_series(
        connection, drawn_series, all_hours=key, only_all_hours=True, all_hours_pen=45
    )

    assert not [h for h in hatches(transport) if h["layerIndex"] != 300], "no fill for any hour"
    assert report.fills == 0 and report.combinations == ()
    assert report.all_hours == (all_hours_combination_name(day),)
    assert transport.all_parameters_for("CreateFills"), "the every-hour outlines, as fills"
    written = {
        entry["name"]
        for call in transport.all_parameters_for("CreateLayerCombinations")
        for entry in call["layerCombinationDataArray"]
    }
    assert written == {all_hours_combination_name(day)}

    # D149: the extent its sheet is fitted to, every outline and label in it.
    ((extent_day, (x0, y0, x1, y1)),) = report.all_hours_extents
    assert extent_day == day
    points = [
        (point["x"], point["y"])
        for call in transport.all_parameters_for("CreateFills")
        for fill in call["fills"]
        for contour in fill["contours"]
        for point in contour["points"]
    ]
    assert x0 == min(x for x, _ in points) and x1 == max(x for x, _ in points)
    assert y0 == min(y for _, y in points) and y1 == max(y for _, y in points)


def test_the_every_hour_sheet_is_fitted_to_its_shadows_and_centred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D149: the view was zoomed wherever the screen was and the drawing put
    down by a corner, so the shadows were cut off and off the middle. The view
    now covers the shadows and a margin, the scale is the largest standard one
    that fits the sheet, and the shadows' middle is the sheet's."""
    from sun_study.archicad import shadows as module
    from sun_study.archicad.layout import LayoutReport, NavigatorItem
    from sun_study.archicad.views import StoreyView

    viewed: list[dict[str, Any]] = []
    placed: list[tuple[Any, dict[str, Any]]] = []

    def views(_c: object, _storeys: Any, **kwargs: Any) -> list[Any]:
        viewed.append(kwargs)
        return [StoreyView(0, kwargs["suffix"], "VIEW")]

    def place(_c: object, groups: Any, **kwargs: Any) -> list[Any]:
        placed.append((groups, kwargs))
        return [
            LayoutReport(name, 1, (), kwargs["scale"], (), database_id="DB") for name, _ in groups
        ]

    storey = NavigatorItem("STOREY", "Ground Floor", "StoryItem", "0")
    monkeypatch.setattr(module, "storey_items", lambda _c, _i: ({0: storey}, []))
    monkeypatch.setattr(module, "views_for_storeys", views)
    monkeypatch.setattr(module, "place_on_sheets", place)
    monkeypatch.setattr(module, "remove_stale_layouts", lambda *_a: [])
    monkeypatch.setattr(module, "_every_hour_scale", lambda _c, _w, _m: 1500)

    built = module.build_shadow_sheets(
        ArchicadConnection(ShadowTransport(["9AM"], 0)),
        series(["9AM"]),
        only_all_hours=True,
        all_hours_extents={"JUNE 21": (-80.0, -120.0, 130.0, 20.0)},
    )

    ((asked,),) = [viewed]
    assert asked["drawing_scale"] == 1500
    assert asked["zoom"] == (-90.0, -130.0, 140.0, 30.0), "the shadows and 10 m round them"
    ((groups, kwargs),) = placed
    assert groups == [
        (f"{naming.prefix()} Shadow Diagrams - JUNE 21 ALL HOURS", [("VIEW", "JUNE 21 ALL HOURS")])
    ]
    assert kwargs["cells"] == 1 and kwargs["scale"] == 1500
    assert kwargs["offset"] == pytest.approx((-25.0 / 1500, 50.0 / 1500)), "the shadows' middle"
    assert kwargs["aspect"] == pytest.approx(230.0 / 160.0)
    assert any("1:1500" in line for line in built.fitted)

    viewed.clear()
    placed.clear()
    module.build_shadow_sheets(
        ArchicadConnection(ShadowTransport(["9AM"], 0)),
        series(["9AM"]),
        only_all_hours=True,
        all_hours_extents={"JUNE 21": (-80.0, -120.0, 130.0, 20.0)},
        all_hours_scale=500.0,
    )
    assert viewed[0]["drawing_scale"] == 500.0, "a scale asked for is kept"
    assert placed[0][1]["offset"] == pytest.approx((-25.0 / 500, 50.0 / 500))


def test_only_the_every_hour_drawing_needs_a_designed_building() -> None:
    connection, _ = connect(["9AM"])
    with pytest.raises(ArchicadError, match="no designed building"):
        draw_shadow_series(connection, series(["9AM"]), only_all_hours=True)


def test_a_project_without_the_25_percent_fill_is_told_rather_than_drawn_solid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A solid fill per hour would hide every hour but the last; with no 25 %
    fill to draw them in, the run stops and says which fill to add."""
    from sun_study.archicad import shadows as module

    monkeypatch.setattr(
        module, "attribute_index", lambda _c, kind, _n: None if kind == "Fill" else 1
    )
    labels = ["9AM"]
    drawn = series(labels)
    connection, _ = connect(labels)
    with pytest.raises(ArchicadError, match="25 %"):
        draw_shadow_series(connection, drawn, all_hours="PROPOSED")


def test_the_every_hour_drawing_is_red_or_blue_in_the_nearest_pen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D147: red by default, the pen nearest the office's pen-45 red; blue
    when asked; anything else refused."""
    from sun_study.archicad import shadows as module
    from sun_study.archicad.draw import Pen

    monkeypatch.setattr(
        module,
        "pen_table",
        lambda _c: (Pen(1, (0, 0, 0)), Pen(45, (204, 9, 32)), Pen(7, (20, 80, 210))),
    )
    labels = ["9AM"]
    grid = ground_plane_grid(
        (np.array([-40.0, -5.0, 0.0]), np.array([10.0, 5.0, 20.0])),
        datum_m=0.0,
        spacing_m=2.0,
        margin_m=40.0,
    )
    sources = default_sources(
        box((-40.0, -5.0, 0.0), (-30.0, 5.0, 10.0)),
        box((0.0, -5.0, 0.0), (10.0, 5.0, 20.0)),
        None,
    )
    key = module.designed_source([source.spec for source in sources])
    drawn = cast_shadows(
        grid,
        sources=sources,
        sun_vectors=np.repeat(WEST_45, 1, axis=0),
        moments=[dt.datetime(2024, 6, 21, 9, tzinfo=dt.UTC)],
        labels=labels,
        spacing_m=2.0,
        outline=key,
    )
    for colour, pen in (("red", 45), ("blue", 7)):
        connection, transport = connect(labels)
        transport.layers.append(("all-hours", module.all_hours_layer_name("JUNE 21"), 300, False))
        draw_shadow_series(connection, drawn, all_hours=key, all_hours_colour=colour)
        drawn_fills = [
            fill
            for call in transport.all_parameters_for("CreateFills")
            for fill in call["fills"]
            if fill["layerIndex"] == 300
        ]
        assert drawn_fills and all(fill["fillPen"] == pen for fill in drawn_fills), colour
    connection, _ = connect(labels)
    with pytest.raises(ArchicadError, match="red or blue"):
        draw_shadow_series(connection, drawn, all_hours=key, all_hours_colour="green")


def test_the_designed_building_is_proposed_or_else_the_last_scenario() -> None:
    from sun_study.archicad.shadows import designed_source
    from sun_study.core.shadow import BASELINE, SCENARIO, SourceSpec

    assert (
        designed_source(
            [
                SourceSpec("EXISTING", "EXISTING", BASELINE),
                SourceSpec("PROPOSED", "PROPOSED", SCENARIO),
                SourceSpec("TOD", "TOD", SCENARIO),
            ]
        )
        == "PROPOSED"
    )
    assert (
        designed_source(
            [SourceSpec("TOD", "TOD", SCENARIO), SourceSpec("SEARS", "SEARS", SCENARIO)]
        )
        == "SEARS"
    )
    assert designed_source([SourceSpec("EXISTING", "EXISTING", BASELINE)]) is None


def test_no_transform_leaves_the_coordinates_alone() -> None:
    """A project that cannot be joined back to its export loses the correction
    and is told so; it must not lose the drawing, or silently gain a rotation
    nobody fitted."""
    connection, transport = connect(["9AM"])
    draw_shadow_series(connection, series(["9AM"]), transform=None)

    assert hatches(transport), "still drawn"


def test_a_favourite_replaces_the_contour_rather_than_fighting_it() -> None:
    """CreateHatches has a contour pen and no switch to turn the contour off,
    so a contour-less fill can only come from a Favorite. A Favorite's
    settings are applied first and the explicit fields over the top, so naming
    a contour pen alongside it would put back the very thing it exists to
    remove."""
    connection, transport = connect(["9AM"])
    draw_shadow_series(connection, series(["9AM"]), favourite="LORIINI")
    drawn = hatches(transport)

    assert drawn
    assert all(h.get("favoriteName") == "LORIINI" for h in drawn)
    assert all("contourPenIndex" not in h for h in drawn), "the Favorite decides it"
    # And the background, which decides whether the fill is opaque. A shadow
    # diagram is read *through*: the roads, the boundaries and the neighbours
    # are underneath it, and an opaque fill is a grey rectangle over them.
    assert all("fillBackgroundPenIndex" not in h for h in drawn)
    # The pen still does separate one legend row from the next; that is not
    # the Favorite's business.
    assert len({h["fillPenIndex"] for h in drawn}) > 1


def test_without_a_favourite_each_fill_is_its_legend_colour_with_no_contour() -> None:
    """Through the add-on's CreateFills: contour pen 0 is no contour at all,
    and the colour is the legend's own rather than whatever pen 93 is."""
    from sun_study.archicad.shadows import styles_for

    connection, transport = connect(["9AM"])
    drawn_series = series(["9AM"])
    draw_shadow_series(connection, drawn_series)
    drawn = hatches(transport)

    assert drawn
    assert not transport.all_parameters_for("CreateHatches"), "the add-on route only"
    assert all(h["contourPenIndex"] == 0 for h in drawn)
    assert all(h["fillIndex"] == 65 for h in drawn), "the project's solid fill"
    wanted = {
        tuple(round(channel * 255) for channel in (c["red"], c["green"], c["blue"]))
        for c in (h["foregroundColour"] for h in drawn)
    }
    assert wanted <= {style.rgb for style in styles_for(drawn_series.sources).values()}


def test_a_legend_row_keeps_its_colour_when_another_is_left_out() -> None:
    """By name, not by position: a sheet with no future context still draws
    the proposal in the proposal's blue."""
    from sun_study.archicad.shadows import LEGEND, styles_for
    from sun_study.core.shadow import BASELINE, SCENARIO, SourceSpec

    styles = styles_for(
        [
            SourceSpec("existing", "EXISTING", BASELINE),
            SourceSpec("proposed", "PROPOSED", SCENARIO),
        ]
    )
    colours = {short: rgb for short, _words, _role, rgb in LEGEND}

    assert styles["existing"].rgb == colours["EXISTING"] == (235, 235, 235)
    assert styles["proposed"].rgb == colours["PROPOSED"] == (156, 172, 191)


def test_the_fills_are_stamped_even_though_the_add_on_answers_a_bare_guid() -> None:
    """The add-on answers {"guid"} and the stamper reads {"elementId"}; not
    re-shaped, every Element ID would silently go unwritten."""
    connection, transport = connect(["9AM"])
    report = draw_shadow_series(connection, series(["9AM"]))

    assert transport.stamped, "Element IDs written"
    assert report.fills == len(hatches(transport))


def test_a_favourite_the_project_does_not_have_is_refused() -> None:
    """CreateHatches takes an unknown favoriteName and draws the hatch anyway,
    with the tool's own settings and a contour round every cell. That is a
    plan of boxes rather than a shadow, and it reads as a drawing defect
    rather than as a missing Favorite."""
    connection, _ = connect(["9AM"])

    with pytest.raises(ArchicadError, match="No Fill favorite"):
        draw_shadow_series(connection, series(["9AM"]), favourite="Nope")


def test_proposed_3_wears_its_own_colour_and_not_a_fourth_blue() -> None:
    from sun_study.archicad.shadows import LEGEND, PROPOSED_3_RGB, SCENARIO_RAMP, legend_colour

    assert legend_colour("PROPOSED 3") == PROPOSED_3_RGB
    assert legend_colour("proposed 3 building envelope") == PROPOSED_3_RGB
    assert PROPOSED_3_RGB not in SCENARIO_RAMP
    shorts = [short for short, _words, _role, _rgb in LEGEND]
    assert shorts.index("PROPOSED 3") == shorts.index("PROPOSED") - 1


def test_the_compared_rows_are_named_for_no_one_control() -> None:
    """Proposed and Proposed 2 to 5 (D178), each its own colour, and
    Proposed 2 in the colour a second proposal takes by position, so a stack's
    numbered proposals never share one."""
    from sun_study.archicad.shadows import LEGEND, SCENARIO_RAMP, legend_colour
    from sun_study.core.shadow import SCENARIO

    compared = [short for short, _words, role, _rgb in LEGEND if role == SCENARIO]
    assert compared == ["PROPOSED 4", "PROPOSED 5", "PROPOSED 2", "PROPOSED 3", "PROPOSED"]
    colours = [legend_colour(short) for short in compared]
    assert len(set(colours)) == 5
    assert legend_colour("PROPOSED 2") == SCENARIO_RAMP[1]
    assert legend_colour("PROPOSED") == SCENARIO_RAMP[2]
    assert legend_colour("Proposed 1") is None


def test_the_older_names_keep_their_colours() -> None:
    """A run that still names the TOD, SEARs or ADG envelope draws it as before."""
    from sun_study.archicad.shadows import ADG_ENVELOPE_RGB, SCENARIO_RAMP, legend_colour

    assert legend_colour("TOD") == SCENARIO_RAMP[0]
    assert legend_colour("SEARS BUILDING ENVELOPE") == SCENARIO_RAMP[1]
    assert legend_colour("adg building envelope") == ADG_ENVELOPE_RGB


# -- the every-hour drawing's edges and labels (D161) -----------------------------


def _every_hour_cast(edge: float | None) -> Any:
    """The tower's own shadow at 9, noon and 3 on a winter's day: long to the
    south-west and south-east, short to the south at noon."""
    grid = ground_plane_grid(
        (np.array([0.0, 0.0, 0.0]), np.array([10.0, 10.0, 20.0])),
        datum_m=0.0,
        spacing_m=1.0,
        margin_m=40.0,
    )
    sources = default_sources(
        box((-60.0, 40.0, 0.0), (-59.0, 41.0, 1.0)),
        box((0.0, 0.0, 0.0), (10.0, 10.0, 20.0)),
        None,
    )
    # The sun to the north-east, north, and north-west, low: the shadows run
    # south-west, south, and south-east.
    suns = np.array([[1.0, 1.0, 0.9], [0.0, 1.0, 1.6], [-1.0, 1.0, 0.9]])
    suns /= np.linalg.norm(suns, axis=1)[:, None]
    return cast_shadows(
        grid,
        sources=sources,
        sun_vectors=suns,
        moments=[dt.datetime(2024, 6, 21, hour, tzinfo=dt.UTC) for hour in (9, 12, 15)],
        labels=["9AM", "12PM", "3PM"],
        spacing_m=1.0,
        edge_tolerance_m=edge,
        outline=ADDITIONAL,
    )


def test_every_hour_records_which_way_its_shadow_runs() -> None:
    cast = _every_hour_cast(None)
    runs = [instant.shadow_direction for instant in cast.instants]
    assert runs[1] == pytest.approx((0.0, -1.0)), "noon's runs due south"
    assert runs[0] == pytest.approx((-np.sqrt(0.5), -np.sqrt(0.5)))
    assert runs[2] == pytest.approx((np.sqrt(0.5), -np.sqrt(0.5)))


def test_the_every_hour_outline_is_traced_to_the_true_edge() -> None:
    """Along the cells a diagonal shadow is a staircase; traced, its long
    sides run at the sun's angle (D79, D161)."""

    def diagonal_edges(cast: Any) -> int:
        rings = cast.instants[0].outlines[ADDITIONAL]
        count = 0
        for ring in rings:
            points = np.asarray(ring, dtype=np.float64)
            steps = np.diff(points, axis=0)
            long = np.hypot(steps[:, 0], steps[:, 1]) > 3.0
            slanted = (np.abs(steps[:, 0]) > 0.5) & (np.abs(steps[:, 1]) > 0.5)
            count += int((long & slanted).sum())
        return count

    assert diagonal_edges(_every_hour_cast(None)) == 0, "the cells: a staircase"
    assert diagonal_edges(_every_hour_cast(0.001)) >= 2, "both long sides at 45 degrees"


def test_each_hour_is_written_at_the_tip_of_its_own_shadow() -> None:
    """By the way each shadow runs, not by the middle of all of them: with
    the long 9 and 3 o'clock shadows pulling that middle south, noon's label
    went to the tower's north side (D161)."""
    from sun_study.archicad.shadows import _all_hours_elements

    cast = _every_hour_cast(0.001)
    hours = [(i.label, list(i.outlines[ADDITIONAL]), i.shadow_direction) for i in cast.instants]
    _fills, texts = _all_hours_elements(hours, 7, None, 45, 2.5)
    at = {text["text"]: text["coordinate"] for text in texts}

    # The tower stands from 0 to 10 both ways; every tip is south of it.
    assert at["12PM"]["y"] < -5.0, "noon at its southern tip, not on the tower"
    assert 0.0 <= at["12PM"]["x"] <= 10.0, "and in the middle of that edge"
    assert at["9AM"]["x"] < -10.0 and at["9AM"]["y"] < -10.0
    assert at["3PM"]["x"] > 20.0 and at["3PM"]["y"] < -10.0

    undirected = [(label, rings, None) for label, rings, _runs in hours]
    _fills, before = _all_hours_elements(undirected, 7, None, 45, 2.5)
    noon = next(text["coordinate"] for text in before if text["text"] == "12PM")
    assert noon["y"] > at["12PM"]["y"], "the old rule put noon farther north"
