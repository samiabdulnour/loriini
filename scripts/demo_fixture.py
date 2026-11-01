"""Run the engine on the sample building and write what the demo animates.

    uv run python scripts/demo_fixture.py

The front of the shop wants a picture of what the program does, and the
honest picture is the program's own answer on the one building the
repository is allowed to show: ``tests/fixtures/sample_building.ifc``, two
storeys, four apartments, a context block to the true north that shades the
lower floor. This runs the massing study and the apartment study on it,
exactly as ``sun-study massing`` and ``sun-study run`` would, and writes
``assets/demo/fixture.js``: the geometry; the skin of cells the model bands
are drawn with, gridded face by face as ``report_model_bands`` grids it,
each cell with whether it saw the sun at each of the 37 instants; the
ground grid the massing study cast rays from, the same way; the sun's
direction at each instant; each apartment's share of lit glazing instant by
instant; the bands; and the ADG verdict. A script rather than JSON because
a page opened from disk may load a script and may not fetch a file.
``assets/demo/makes.html`` draws that file as a short animation and
``scripts/demo_render.py`` turns the animation into the video on the *What
it makes* page (docs/website.md).

Nothing in the picture is drawn by hand: the shadow is the ground grid the
engine cast rays from, the colours are its bands, the table is its
assessment. Run this when the fixture or the engine changes; the file is
committed, like the lorikeet sheet, so the site can be deployed from a
checkout without running the engine.

The skin's cells and the massing study's facade figure come from two
griddings of the same faces -- per planar face for a picture, per triangle
for a measurement -- and differ a little, as ``report_model_bands`` says of
its own drawing. The number the page quotes is the measured one.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np

from sun_study.core.analysis import cumulative_minutes, instant_weights, sunlit_matrix
from sun_study.core.facade import face_panels
from sun_study.core.occlusion import Occluder
from sun_study.core.orientation import enu_to_model_matrix
from sun_study.core.sampling import SamplePoints
from sun_study.ingest.scene import MassingConfig, massing_subject
from sun_study.pipeline import WEIGHTING_BY_RULESET, run_assessment, run_massing

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "sample_building.ifc"
OUT = ROOT / "assets" / "demo" / "fixture.js"

TIMEZONE = "Australia/Sydney"
AREA = "sydney_metro"
#: A metre: coarse enough to read as cells on a 20 m facade, and the spacing
#: a massing study is usually run at.
SPACING_M = 1.0
#: Decimal places kept on a coordinate. Millimetres are more than a picture
#: a few hundred pixels across can show.
PLACES = 3


def _round(values: Any) -> Any:
    """Floats rounded to ``PLACES``, nested lists included, so the JSON stays
    readable and a diff of it says something."""
    if isinstance(values, (float, np.floating)):
        return round(float(values), PLACES)
    if isinstance(values, np.ndarray):
        return _round(values.tolist())
    if isinstance(values, (list, tuple)):
        return [_round(value) for value in values]
    return values


def _rounded_rows(values: Any) -> list[list[float]]:
    rows: list[list[float]] = _round(values)
    return rows


def _bits(sunlit: np.ndarray) -> list[str]:
    """One string per instant, one character per cell: ``1`` lit, ``0`` not.

    ``sunlit`` is ``(cells, instants)`` as ``sunlit_matrix`` returns it. A
    string of digits is a third the size of a list of booleans in JSON and
    is read back with one ``charAt``.
    """
    return ["".join("1" if lit else "0" for lit in column) for column in sunlit.T]


def _ground_cells(points: SamplePoints) -> list[list[float]]:
    """Each ground sample as the centre of a flat square of ``SPACING_M``.

    Two numbers a cell: the page builds the corners, so the file does not
    carry eight."""
    return _rounded_rows(points.positions[:, :2])


def main() -> None:
    assessment = run_assessment(FIXTURE, timezone=TIMEZONE, area=AREA)
    config = MassingConfig(
        timezone=TIMEZONE, facade_spacing_m=SPACING_M, ground_spacing_m=SPACING_M
    )
    massing = run_massing(FIXTURE, timezone=TIMEZONE, area=AREA, massing_config=config)
    series = assessment.instants
    assert series is not None and series.sun_vectors is not None
    if massing.facade is None or massing.ground is None:
        raise SystemExit("the massing run measured neither surface; nothing to draw")

    # The same rays the massing study cast, kept instant by instant rather
    # than summed, so the animation can show the shadow move and the cells
    # fill. Same occluders, same sun, same weights: the minutes agree with
    # the bands to the digit.
    scene = massing.scene
    occluder = Occluder(scene.occluders)
    rules = massing.ruleset.assessment
    weights = instant_weights(
        len(massing.times), float(rules.timestep_minutes), WEIGHTING_BY_RULESET[rules.weighting]
    )
    # The skin: every planar face of the subject gridded in its own plane,
    # both sides, upright and flat, exactly as the model bands are drawn
    # onto the model (``cli.report_model_bands``). The page hides the sides
    # that face away from it.
    subject = massing_subject(massing.model, config).subject
    panels = [
        (element, panel)
        for element in subject
        if element.mesh.triangle_count
        for panel in face_panels(
            element.mesh,
            element.global_id,
            spacing_m=SPACING_M,
            surface_offset_m=config.surface_offset_m,
            vertical_tolerance_deg=config.vertical_tolerance_deg,
        )
    ]
    skin = SamplePoints.concatenate([panel.samples for _element, panel in panels])
    skin_lit = sunlit_matrix(skin, occluder, series.sun_vectors)
    ground_lit = sunlit_matrix(scene.ground_samples, occluder, series.sun_vectors)

    living_by_id = dict(zip(series.apartment_ids, series.living_share, strict=True))
    open_by_id = dict(zip(series.open_space_ids, series.open_space_share, strict=True))

    elements = [
        {
            "name": element.name,
            "ifc_class": element.ifc_class,
            "storey": element.storey,
            "context": element.name.startswith(tuple(config.context_name_prefixes)),
            "triangles": _round(element.mesh.triangles()),
        }
        for element in massing.model.elements
    ]

    north = (
        np.asarray([0.0, 1.0, 0.0])
        @ enu_to_model_matrix(scene.orientation.true_north_bearing_deg).T
    )

    document: dict[str, Any] = {
        "made_from": FIXTURE.relative_to(ROOT).as_posix(),
        "made_on": dt.date.today().isoformat(),
        "site": {
            "latitude_deg": scene.orientation.latitude_deg,
            "longitude_deg": scene.orientation.longitude_deg,
            "timezone": TIMEZONE,
            "true_north_bearing_deg": scene.orientation.true_north_bearing_deg,
            "north_in_model": _round(north),
        },
        "day": massing.assessment_date.isoformat(),
        "times": [moment.strftime("%H:%M") for moment in massing.times],
        "sun": _round(series.sun_vectors),
        "elements": elements,
        "skin": {
            "spacing_m": SPACING_M,
            "offset_m": config.surface_offset_m,
            # Each panel: its frame, and its cells in that frame. The cells
            # of every panel, in this order, index ``minutes`` and ``lit``.
            # A panel on a window or a balcony deck says so, because those
            # are the surfaces the apartment study measures and the page
            # outlines them.
            "panels": [
                {
                    "origin": _round(panel.origin),
                    "u": _round(panel.axis_u),
                    "v": _round(panel.axis_v),
                    "normal": _round(panel.normal),
                    "measured": (
                        "glazing"
                        if element.ifc_class == "IfcWindow"
                        else "open space"
                        if element.name.startswith("Balcony") and float(panel.normal[2]) > 0.5
                        else ""
                    ),
                    "cells": _round(panel.cell_uv),
                }
                for element, panel in panels
            ],
            "minutes": _round(cumulative_minutes(skin_lit, weights)),
            "lit": _bits(skin_lit),
        },
        "ground": {
            "spacing_m": SPACING_M,
            "level_m": _round(float(scene.ground_samples.positions[:, 2].min()))
            if len(scene.ground_samples)
            else 0.0,
            "cells": _ground_cells(scene.ground_samples),
            "minutes": _round(cumulative_minutes(ground_lit, weights)),
            "lit": _bits(ground_lit),
        },
        "bands": {
            "threshold_minutes": massing.threshold_minutes,
            "facade": [
                {
                    "label": band.label,
                    "lower_minutes": band.lower_minutes,
                    "upper_minutes": band.upper_minutes,
                    "area_m2": _round(band.area_m2),
                    "share": _round(band.share),
                }
                for band in massing.facade.bands
            ],
            "facade_total_m2": _round(massing.facade.total_area_m2),
            "facade_at_or_above_share": _round(massing.facade.at_or_above_threshold_share),
            "ground_at_or_above_share": _round(massing.ground.at_or_above_threshold_share),
        },
        "apartments": [
            {
                "name": apartment.apartment_name,
                "living_minutes": _round(apartment.living_room_minutes),
                "open_space_minutes": _round(apartment.open_space_minutes),
                "governing_minutes": _round(apartment.governing_minutes),
                "meets_minimum": apartment.meets_minimum,
                "living_share": _round(living_by_id.get(apartment.apartment_id, [])),
                "open_space_share": _round(open_by_id.get(apartment.apartment_id, [])),
            }
            for apartment in assessment.assessment.apartments
        ],
        "summary": {
            "complies": assessment.assessment.complies,
            "counted": assessment.assessment.counted_total,
            "meeting_minimum": assessment.assessment.meeting_minimum,
            "compliant_share": _round(assessment.assessment.compliant_share),
            "required_share": assessment.assessment.required_share,
            "minimum_minutes": assessment.assessment.minimum_minutes,
            "text": assessment.assessment.summary(),
            "ruleset": massing.ruleset.describe(AREA).splitlines()[0],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "// Written by scripts/demo_fixture.py from "
        f"{document['made_from']}; do not edit.\n"
        "var FIXTURE = " + json.dumps(document, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(elements)} elements, "
        f"{len(panels)} faces with {len(skin)} skin cells, "
        f"{len(scene.ground_samples)} ground cells, "
        f"{len(massing.times)} instants, {len(document['apartments'])} apartments; "
        f"{OUT.stat().st_size / 1000:.0f} kB"
    )


if __name__ == "__main__":
    main()
