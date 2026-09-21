"""Results drawn on the sheet, over the plan, instead of into the plan.

Why this exists
---------------
Every study used to reach paper the same way: fills on a floor-plan layer of
the tool's own, a layer combination showing that layer, a view pinned to the
combination, and the view placed on a layout. It works, and it leaves the
model carrying the study -- a layer per instant, a fill per cell, a legend
beside the building on every storey it touched -- in a file whose floor plans
are other people's working drawings.

A layout can be drawn on directly (fills, polylines and texts, in metres of
paper measured up from the sheet's bottom-left), and a placed Drawing says
where it put the model: ``Loriini.ArrangeDrawings`` anchors a Drawing by its
*own origin*, which for a floor plan is the project origin. So the plan on the
sheet can be the office's own view, untouched, and the study can be laid over
it in paper space.

What this module is
-------------------
Only the arithmetic, and the re-spelling of an element from the floor plan's
terms into the sheet's. ``PaperFrame`` is one placed Drawing's account of
where the model lands; ``onto_paper`` takes an element exactly as the drawers
already build it -- project metres, a layer, a storey -- and answers the same
element in paper metres with the two fields a layout has no use for removed.
The drawers therefore do not change what they compute, only where it goes.

What is given up, said plainly: an element on a layout takes no Element ID
and its area is paper area, so a Schedule totalling the study's fills has
nothing to total. Every figure the tool puts on a sheet comes from the
analysis and never from the fills, so nothing it draws depends on that.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["PaperFrame", "PaperSink", "StudyElements", "onto_paper"]

#: Fields that place an element in the model and mean nothing on a sheet. A
#: layout has no storeys -- a floor index sent there is documented in
#: ``series._hatch`` as silently destroying the element -- and the tool's
#: layers are exactly what drawing on paper is meant to stop creating.
_MODEL_ONLY = ("floorInd", "floorIndex", "layerIndex", "elementId")


@dataclass(frozen=True)
class PaperFrame:
    """Where one placed Drawing puts the model on its sheet.

    ``origin`` is the paper point, in metres up from the sheet's bottom-left,
    where the project origin lands -- what ``ArrangeDrawings`` is given with
    ``anchor: "origin"``. ``scale`` is the view's drawing scale as its
    denominator, 200 for 1:200. ``ratio`` is the Drawing's magnification,
    which is 1 unless a drawing too big for its sheet was shrunk to fit.
    ``angle_rad`` is how far the Drawing stands turned on the sheet,
    anticlockwise; a straightened drawing is zero.
    """

    origin: tuple[float, float]
    scale: float
    ratio: float = 1.0
    angle_rad: float = 0.0

    def __post_init__(self) -> None:
        if not self.scale > 0.0 or not self.ratio > 0.0:
            raise ValueError(
                f"a drawing at scale 1:{self.scale:g} magnified {self.ratio:g} times "
                f"places nothing: both have to be above zero"
            )

    @property
    def metres_of_paper_per_metre(self) -> float:
        return self.ratio / self.scale

    def point(self, x: float, y: float) -> tuple[float, float]:
        """One project point, in metres, as a point on the sheet."""
        k = self.metres_of_paper_per_metre
        cos, sin = math.cos(self.angle_rad), math.sin(self.angle_rad)
        return (
            self.origin[0] + k * (x * cos - y * sin),
            self.origin[1] + k * (x * sin + y * cos),
        )

    def box(self, x_min: float, y_min: float, x_max: float, y_max: float) -> dict[str, float]:
        """A project-space box as the clip frame that shows exactly it.

        Axis-aligned on the sheet whatever the angle, because a frame is: the
        box's four corners are placed and the frame is what holds them.
        """
        corners = [self.point(x, y) for x in (x_min, x_max) for y in (y_min, y_max)]
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        return {"xMin": min(xs), "yMin": min(ys), "xMax": max(xs), "yMax": max(ys)}


def _moved(point: Mapping[str, Any], frame: PaperFrame) -> dict[str, Any]:
    x, y = frame.point(float(point["x"]), float(point["y"]))
    moved: dict[str, Any] = {**point, "x": x, "y": y}
    return moved


#: Closer than this on the sheet and two nodes are one. Twenty microns is
#: under anything a plotter resolves, and well over the point at which
#: Archicad refuses the element: a Zone outline with two nodes 4 mm apart in
#: the model has them 13 microns apart at 1:300, and ``CreatePolylines``
#: answered "Failed to create new PolyLine" for that flat alone among thirteen.
_SAME_POINT_M = 2e-5


def _ring(points: Sequence[Mapping[str, Any]], frame: PaperFrame) -> list[dict[str, Any]]:
    """The points on paper, without the ones that land on their neighbour.

    A closing point that repeats the first is kept -- that is how a polyline
    says it is closed -- so only a node too near the one *before* it goes.
    """
    kept: list[dict[str, Any]] = []
    for point in points:
        moved = _moved(point, frame)
        if (
            kept
            and math.hypot(moved["x"] - kept[-1]["x"], moved["y"] - kept[-1]["y"]) < _SAME_POINT_M
        ):
            continue
        kept.append(moved)
    return kept


def onto_paper(element: Mapping[str, Any], frame: PaperFrame) -> dict[str, Any]:
    """One element as the drawers build it, re-spelled for a layout.

    Handles every shape the 2D drawers emit, recognised by the field that
    carries its geometry:

    - ``coordinates`` -- a Tapir hatch or polyline, a list of ``{x, y}``;
    - ``contours`` -- an add-on fill, each with its own ``points``;
    - ``coordinate`` -- a text, one ``{x, y, z}``.

    A pen weight and a text ``height`` are paper lengths in both places and
    are left alone: the add-on's ``CreateTexts`` reads a height as millimetres
    on paper whichever database is current, and the add-on is the only way
    onto a sheet. (Converting it to metres, as Tapir's command wants on a
    layout, drew the first sheets' labels 0.0025 mm tall -- Archicad showed
    them at its 0.10 mm floor, which is a dot.) An ``angle`` is turned with
    the frame, since a text along a shadow's edge has to stay along it.
    """
    out: dict[str, Any] = {key: value for key, value in element.items() if key not in _MODEL_ONLY}
    if "coordinates" in out:
        out["coordinates"] = _ring(out["coordinates"], frame)
    if "contours" in out:
        out["contours"] = [
            {**contour, "points": _ring(contour.get("points") or (), frame)}
            for contour in out["contours"]
        ]
    if "coordinate" in out:
        out["coordinate"] = _moved(out["coordinate"], frame)
    if "angle" in out and frame.angle_rad:
        out["angle"] = float(out["angle"]) + frame.angle_rad
    return out


def _storey_of(element: Mapping[str, Any]) -> int | None:
    storey = element.get("floorInd", element.get("floorIndex"))
    return int(storey) if storey is not None else None


@dataclass
class StudyElements:
    """What one drawing of the study is made of, still in project metres."""

    fills: list[dict[str, Any]]
    polylines: list[dict[str, Any]]
    texts: list[dict[str, Any]]
    outline: bool = True
    """Whether the fills carry a contour. It decides which command can draw
    them -- see ``penetration._create_fills`` -- so it travels with them."""

    def __len__(self) -> int:
        return len(self.fills) + len(self.polylines) + len(self.texts)


class PaperSink:
    """Where the drawers put their elements when the study goes on the sheet.

    A drawer finishes long before there is a sheet: the layouts are made from
    views, and which cell a storey's plan lands in is not known until they
    are. So the drawers hand their elements here, exactly as they would have
    sent them to the floor plan, and the sheet step collects each drawing's
    share once it knows where that drawing is.

    Keyed by the layer the elements *would* have gone on and the storey they
    name, which is already how the floor-plan route tells one drawing from
    another: a layer per instant, a view per storey.
    """

    def __init__(self) -> None:
        self._held: dict[tuple[str, int | None], StudyElements] = {}

    def _bucket(self, layer_name: str, storey: int | None, outline: bool) -> StudyElements:
        return self._held.setdefault(
            (layer_name, storey), StudyElements([], [], [], outline=outline)
        )

    def add(
        self,
        layer_name: str,
        *,
        fills: Sequence[Mapping[str, Any]] = (),
        polylines: Sequence[Mapping[str, Any]] = (),
        texts: Sequence[Mapping[str, Any]] = (),
        outline: bool = True,
    ) -> None:
        for fill in fills:
            self._bucket(layer_name, _storey_of(fill), outline).fills.append(dict(fill))
        for line in polylines:
            self._bucket(layer_name, _storey_of(line), outline).polylines.append(dict(line))
        for one in texts:
            self._bucket(layer_name, _storey_of(one), outline).texts.append(dict(one))

    def take(self, layer_name: str, storey: int | None) -> StudyElements:
        """One drawing's elements, and whatever named no storey at all."""
        mine = self._held.get((layer_name, storey), StudyElements([], [], []))
        loose = self._held.get((layer_name, None)) if storey is not None else None
        if loose is None:
            return mine
        return StudyElements(
            [*mine.fills, *loose.fills],
            [*mine.polylines, *loose.polylines],
            [*mine.texts, *loose.texts],
            outline=mine.outline if len(mine) else loose.outline,
        )

    def storeys(self, layer_name: str) -> list[int]:
        return sorted({s for (name, s) in self._held if name == layer_name and s is not None})
