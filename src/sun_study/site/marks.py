"""The office's climate marks, as geometry a drawing can place.

The suns, winds and views the office draws on its site sheets, taken as
drawn from its symbol sheet (the generator's ``climateSymbols.ts``): one set
for Flamingo, where each mark is a flat shape filled and outlined, and one
for Kingfisher, where the marks are small and solid and ride on bands of
colour. And the marks the generator draws itself: the crown sun of Heron,
the crescent bands of Kingfisher, the hand-drawn arrow strands of Heron's
winds, the plain rayed sun of Canary's climate circle.

Every path is in its own units: a sun is centred on 0,0 with its rays
reaching a radius of 1; a wind or an arrow is centred on 0,0, points along
+x and runs from x = -1 to 1. An SVG path has its y axis pointing down, so
``polygons`` turns it over as it places it, which keeps a wind blowing the
way the office drew it.

Archicad has no curves on a fill, so each path is flattened: a cubic is
walked in a few straight steps, and a subpath lying inside another becomes
a hole in it (the eye's pupil), which is the nonzero rule the paths were
drawn under for the shapes they actually hold.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence

from sun_study.site.geo import Point, point_in_ring, ring_area

__all__ = [
    "ARROW",
    "EYE",
    "RAY_SUN",
    "SUN",
    "VIEW",
    "WIND",
    "crescent",
    "crown_sun",
    "placed",
    "plain_sun",
    "polygons",
    "sketch_arrow",
]

Polygon = tuple[list[Point], list[list[Point]]]
"""An outer ring and its holes."""

#: Flamingo's sun: eight tapered rays round a disc.
SUN = (
    "M0.226,1.000L-0.193,1.000L-0.096,0.463L0.096,0.463L0.226,1.000M-0.567,0.847L-0.867,0.548"
    "L-0.395,0.259L-0.259,0.395L-0.567,0.847M0.571,0.844L0.259,0.395L0.395,0.259L0.867,0.548"
    "L0.571,0.844M0.002,0.301C-0.015,0.301 -0.031,0.300 -0.048,0.297C-0.174,0.277 -0.277,0.174 "
    "-0.297,0.048C-0.326,-0.140 -0.184,-0.301 0.002,-0.301C0.005,-0.301 0.009,-0.301 0.012,-0.301"
    "C0.166,-0.295 0.295,-0.166 0.301,-0.012C0.306,0.162 0.171,0.301 0.002,0.301M1.000,0.197"
    "L0.463,0.096L0.463,-0.096L1.000,-0.226L1.000,0.197M-1.000,0.197L-1.000,-0.226L-0.463,-0.096"
    "L-0.463,0.096L-1.000,0.197M0.395,-0.259L0.259,-0.395L0.548,-0.867L0.847,-0.567L0.395,-0.259"
    "M-0.395,-0.259L-0.844,-0.571L-0.548,-0.867L-0.259,-0.395L-0.395,-0.259M0.096,-0.463"
    "L-0.096,-0.463L-0.193,-1.000L0.226,-1.000ZM0.096,-0.463"
)

#: Flamingo's wind: two curled arrowheads, one behind the other.
WIND = (
    "M-0.010,0.015C-0.010,0.014 -0.010,0.012 -0.010,0.011C-0.008,-0.148 0.142,-0.264 0.297,-0.318"
    "C0.144,-0.376 -0.001,-0.495 -0.001,-0.652C-0.001,-0.653 -0.001,-0.654 -0.001,-0.655"
    "C0.002,-0.942 0.378,-0.919 0.378,-0.694C0.378,-0.673 0.375,-0.651 0.368,-0.627L0.273,-0.628"
    "C0.275,-0.635 0.275,-0.641 0.275,-0.647C0.275,-0.733 0.146,-0.743 0.144,-0.638C0.144,-0.638 "
    "0.144,-0.637 0.144,-0.637C0.144,-0.485 0.438,-0.349 0.618,-0.346L0.617,-0.282C0.436,-0.284 "
    "0.138,-0.155 0.136,-0.002C0.136,-0.002 0.136,-0.001 0.136,-0.001C0.136,0.051 0.168,0.075 "
    "0.201,0.075C0.234,0.075 0.266,0.051 0.266,0.008C0.266,0.002 0.266,-0.003 0.265,-0.009"
    "L0.359,-0.008C0.365,0.014 0.368,0.035 0.368,0.054C0.368,0.169 0.273,0.230 0.179,0.227"
    "C0.084,0.224 -0.010,0.158 -0.010,0.015M0.539,0.035C0.542,-0.149 0.735,-0.295 0.815,-0.311"
    "C0.736,-0.329 0.549,-0.478 0.549,-0.662C0.549,-0.663 0.549,-0.664 0.549,-0.665L0.725,-0.663"
    "C0.725,-0.661 0.725,-0.659 0.725,-0.658C0.725,-0.461 0.881,-0.375 1.000,-0.341L0.999,-0.277"
    "C0.878,-0.246 0.718,-0.162 0.716,0.038ZM0.539,0.035M-1.000,0.728C-1.000,0.726 -1.000,0.725 "
    "-1.000,0.723C-0.998,0.564 -0.848,0.448 -0.693,0.394C-0.845,0.337 -0.991,0.218 -0.991,0.061"
    "C-0.991,0.059 -0.991,0.058 -0.991,0.057C-0.987,-0.230 -0.611,-0.206 -0.611,0.018"
    "C-0.611,0.039 -0.615,0.062 -0.622,0.086L-0.716,0.085C-0.715,0.078 -0.714,0.071 -0.714,0.065"
    "C-0.714,-0.020 -0.844,-0.030 -0.845,0.074C-0.845,0.075 -0.845,0.075 -0.845,0.076"
    "C-0.845,0.228 -0.552,0.364 -0.372,0.366L-0.373,0.431C-0.553,0.428 -0.852,0.558 -0.854,0.710"
    "C-0.854,0.711 -0.854,0.711 -0.854,0.712C-0.854,0.764 -0.821,0.788 -0.788,0.788"
    "C-0.756,0.788 -0.723,0.764 -0.723,0.720C-0.723,0.715 -0.724,0.709 -0.725,0.703L-0.630,0.705"
    "C-0.624,0.727 -0.622,0.748 -0.622,0.767C-0.622,0.881 -0.716,0.942 -0.811,0.940"
    "C-0.905,0.937 -1.000,0.870 -1.000,0.728M-0.450,0.748C-0.448,0.563 -0.254,0.417 -0.175,0.401"
    "C-0.253,0.383 -0.441,0.234 -0.441,0.051C-0.441,0.050 -0.441,0.049 -0.441,0.047L-0.265,0.050"
    "C-0.265,0.051 -0.265,0.053 -0.265,0.055C-0.265,0.251 -0.108,0.338 0.010,0.372L0.010,0.436"
    "C-0.111,0.467 -0.271,0.550 -0.274,0.750ZM-0.450,0.748"
)

#: Flamingo's view: a small wedge pointing back at the site, then the eye in a widening triangle.
VIEW = (
    "M1.000,0.562L0.396,0.251L0.395,-0.202L0.996,-0.518L1.000,0.562M0.703,-0.182C0.703,-0.182 "
    "0.702,-0.182 0.702,-0.182C0.589,-0.182 0.499,-0.090 0.499,0.022C0.499,0.135 0.591,0.225 "
    "0.703,0.225C0.703,0.225 0.703,0.225 0.704,0.225C0.816,0.225 0.907,0.133 0.907,0.021"
    "C0.906,-0.091 0.815,-0.182 0.703,-0.182M0.284,0.194L0.049,0.073C0.025,0.061 0.000,0.052 "
    "0.000,0.024C0.000,0.000 0.024,-0.009 0.049,-0.021L0.282,-0.144L0.284,0.194M0.697,0.122"
    "C0.645,0.122 0.603,0.080 0.602,0.022C0.602,-0.033 0.645,-0.075 0.696,-0.076C0.696,-0.076 "
    "0.697,-0.076 0.697,-0.076C0.754,-0.076 0.797,-0.033 0.797,0.021C0.797,0.079 0.755,0.122 "
    "0.697,0.122C0.697,0.122 0.697,0.122 0.697,0.122"
)

#: Kingfisher's sun: a disc with eight bar rays.
RAY_SUN = (
    "M0.207,0.227C0.354,0.084 0.324,-0.174 0.143,-0.269C-0.007,-0.348 -0.187,-0.294 -0.267,-0.148"
    "C-0.444,0.176 -0.018,0.446 0.207,0.227M0.399,-0.931L0.143,-0.464C0.141,-0.461 0.142,-0.458 "
    "0.145,-0.456L0.306,-0.368C0.309,-0.367 0.312,-0.368 0.313,-0.370L0.569,-0.838C0.571,-0.841 "
    "0.570,-0.844 0.567,-0.845L0.406,-0.933C0.403,-0.935 0.400,-0.934 0.399,-0.931M-0.313,0.370"
    "L-0.569,0.838C-0.571,0.841 -0.570,0.844 -0.567,0.845L-0.406,0.933C-0.403,0.935 -0.400,0.934 "
    "-0.399,0.931L-0.143,0.464C-0.141,0.461 -0.142,0.458 -0.145,0.456L-0.306,0.368C-0.309,0.367 "
    "-0.312,0.368 -0.313,0.370M-0.931,-0.398L-0.464,-0.143C-0.461,-0.141 -0.458,-0.142 "
    "-0.456,-0.145"
    "L-0.368,-0.306C-0.367,-0.309 -0.368,-0.312 -0.370,-0.313L-0.838,-0.569C-0.841,-0.571 "
    "-0.844,-0.570 -0.845,-0.567L-0.933,-0.406C-0.935,-0.403 -0.934,-0.400 -0.931,-0.398"
    "M0.370,0.313L0.838,0.569C0.841,0.571 0.844,0.570 0.845,0.567L0.933,0.406C0.935,0.403 "
    "0.934,0.400 0.931,0.398L0.464,0.143C0.461,0.141 0.458,0.142 0.456,0.145L0.368,0.306"
    "C0.367,0.309 0.368,0.312 0.370,0.313M-0.377,-0.940L-0.227,-0.427C-0.226,-0.425 -0.223,-0.423 "
    "-0.220,-0.424L-0.043,-0.476C-0.040,-0.476 -0.038,-0.480 -0.039,-0.482L-0.189,-0.995"
    "C-0.190,-0.998 -0.193,-1.000 -0.196,-0.999L-0.374,-0.947C-0.377,-0.946 -0.378,-0.943 "
    "-0.377,-0.940M0.039,0.482L0.189,0.995C0.190,0.998 0.193,1.000 0.196,0.999L0.374,0.947"
    "C0.377,0.946 0.378,0.943 0.377,0.940L0.227,0.427C0.226,0.425 0.223,0.423 0.220,0.424"
    "L0.043,0.476C0.040,0.476 0.038,0.480 0.039,0.482M-0.940,0.377L-0.428,0.227C-0.425,0.226 "
    "-0.423,0.223 -0.424,0.220L-0.476,0.043C-0.476,0.040 -0.480,0.038 -0.482,0.039L-0.995,0.189"
    "C-0.998,0.190 -1.000,0.193 -0.999,0.196L-0.947,0.374C-0.946,0.377 -0.943,0.378 -0.940,0.377"
    "M0.482,-0.039L0.995,-0.189C0.998,-0.190 1.000,-0.193 0.999,-0.196L0.947,-0.374"
    "C0.946,-0.377 0.943,-0.378 0.940,-0.377L0.428,-0.227C0.425,-0.226 0.423,-0.223 0.424,-0.220"
    "L0.476,-0.043C0.476,-0.040 0.480,-0.038 0.482,-0.039"
)

#: Kingfisher's wind: an open arrowhead on a broken shaft.
ARROW = (
    "M0.316,-0.101L-0.248,-0.101L-0.248,0.101L0.316,0.101ZM0.740,-0.016C0.477,-0.118 0.248,-0.337 "
    "0.053,-0.644L0.230,-0.757C0.453,-0.436 0.709,-0.217 1.000,-0.101L1.000,0.101C0.709,0.217 "
    "0.453,0.436 0.231,0.757L0.053,0.644C0.248,0.337 0.477,0.118 0.740,0.015ZM-0.436,-0.101"
    "L-1.000,-0.100L-1.000,0.101L-0.436,0.101ZM-0.436,-0.101"
)

#: Kingfisher's view: the eye alone, set white in its triangle.
EYE = (
    "M0.006,0.491C0.236,0.496 0.426,0.316 0.431,0.081C0.436,-0.149 0.256,-0.338 0.026,-0.344"
    "C-0.209,-0.349 -0.398,-0.168 -0.404,0.062C-0.409,0.296 -0.228,0.486 0.006,0.491M0.056,0.271"
    "C-0.029,0.269 -0.091,0.204 -0.089,0.119C-0.087,0.042 -0.022,-0.020 0.063,-0.018"
    "C0.144,-0.016 0.206,0.049 0.204,0.126C0.202,0.211 0.138,0.273 0.056,0.271M-0.734,0.289"
    "C-0.727,0.013 -0.406,-0.227 0.005,-0.218C0.415,-0.208 0.730,0.048 0.723,0.323L0.989,0.329"
    "C1.000,-0.117 0.548,-0.471 0.011,-0.484C-0.526,-0.496 -0.990,-0.164 -1.000,0.282ZM-0.734,0.289"
)

_TOKEN = re.compile(r"[MLCZ]|-?(?:\d+\.?\d*|\.\d+)")


def _subpaths(path: str, steps: int = 6) -> list[list[Point]]:
    """The closed rings of an SVG path of M, L, C and Z, each cubic walked in ``steps``."""
    tokens = _TOKEN.findall(path)
    rings: list[list[Point]] = []
    current: list[Point] = []
    i = 0

    def number() -> float:
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    def flush() -> None:
        nonlocal current
        if len(current) >= 3:
            rings.append(current)
        current = []

    command = ""
    while i < len(tokens):
        token = tokens[i]
        if token in "MLCZ":
            command = token
            i += 1
            if command == "Z":
                flush()
            continue
        if command == "M":
            flush()
            current = [(number(), number())]
            command = "L"
        elif command == "L":
            current.append((number(), number()))
        elif command == "C":
            (x0, y0) = current[-1] if current else (0.0, 0.0)
            x1, y1, x2, y2, x3, y3 = (number() for _ in range(6))
            for k in range(1, steps + 1):
                t = k / steps
                u = 1 - t
                current.append(
                    (
                        u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3,
                        u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3,
                    )
                )
        else:
            i += 1
    flush()
    return rings


def _nested(rings: Sequence[list[Point]]) -> list[Polygon]:
    """Rings as polygons: a ring lying inside a larger one is that one's hole."""
    ordered = sorted(rings, key=lambda ring: -abs(ring_area(ring)))
    out: list[Polygon] = []
    for ring in ordered:
        x, y = ring[0]
        for outer, holes in out:
            if point_in_ring(x, y, outer):
                holes.append(ring)
                break
        else:
            out.append((ring, []))
    return out


def polygons(path: str, size: float, at: Point, angle_rad: float = 0.0) -> list[Polygon]:
    """A symbol's polygons, scaled so a unit is ``size``, turned so its +x
    points along ``angle_rad``, and placed with its origin at ``at``."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    ax, ay = at

    def place(pt: Point) -> Point:
        # The office drew these with y down; the drawing's y is up.
        x, y = pt[0] * size, -pt[1] * size
        return (ax + x * c - y * s, ay + x * s + y * c)

    return _nested([[place(pt) for pt in ring] for ring in _subpaths(path)])


def placed(ring: Sequence[Point], size: float, at: Point, angle_rad: float = 0.0) -> list[Point]:
    """A ring in symbol units, scaled, turned and placed the way ``polygons`` does it."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    ax, ay = at
    return [
        (ax + (x * size) * c - (-y * size) * s, ay + (x * size) * s + (-y * size) * c)
        for x, y in ring
    ]


def crescent(
    centre: Point,
    radius: float,
    from_rad: float,
    to_rad: float,
    depth: float,
    *,
    steps: int | None = None,
) -> list[Point]:
    """A crescent along a circle about ``centre``, between two angles: its
    outer edge on ``radius``, its inner edge swelling in to ``depth`` at the
    middle and closing to a point at each end."""
    n = steps or max(8, math.ceil(abs(math.degrees(to_rad - from_rad)) / 2))
    outer: list[Point] = []
    inner: list[Point] = []
    for i in range(n + 1):
        u = i / n
        a = from_rad + (to_rad - from_rad) * u
        r_in = radius - depth * math.sin(math.pi * u)
        outer.append((centre[0] + radius * math.cos(a), centre[1] + radius * math.sin(a)))
        inner.append((centre[0] + r_in * math.cos(a), centre[1] + r_in * math.sin(a)))
    return outer + inner[::-1]


def _flame(a: float, r_base: float, h: float, amp: float) -> Callable[[float], list[Point]]:
    """One side of a flame on the crown at angle ``a``: its centre line
    leaves the crown radially and bends once, its width falling from a
    little over the tooth's base to a point; neighbouring flames bend
    opposite ways (the sign of ``amp``)."""
    length, w0 = 8.5, r_base * math.sin(h) * 1.2
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    steps = 10

    def side(sign: float) -> list[Point]:
        out: list[Point] = []
        for k in range(steps + 1):
            t = k / steps
            off = amp * math.sin(t * math.pi * 1.5)
            w = w0 * (1 - t) ** 0.8 + 0.12
            r = r_base * math.cos(h) + length * t
            out.append((ux * r + nx * (off + sign * w), uy * r + ny * (off + sign * w)))
        return out

    return side


def crown_sun(at: Point, size: float, seed: int = 1) -> tuple[list[Point], float]:
    """Heron's sun: an open jagged crown round a plain circle, twelve teeth of
    uneven length with the four on the diagonals drawn out as short, broad
    flames with one gentle bend, after the manuscript suns. ``size`` is the
    drawing's millimetre; the crown's base is 12.4 of them. Each sun is drawn
    from its own seed so the four differ a little, as if drawn one by one.

    Returns the crown's ring and the inner circle's radius.
    """
    state = seed * 9301 + 49297

    def rnd() -> float:
        nonlocal state
        state = (state * 9301 + 49297) % 233280
        return state / 233280

    n, r_base, flames = 12, 12.4, (1, 4, 7, 10)
    pts: list[Point] = []
    h = (math.pi / n) * 0.85
    for i in range(n):
        a = (i / n) * math.pi * 2
        if i not in flames:
            r0 = r_base + rnd() * 0.8
            pts.append((r0 * math.cos(a - h), r0 * math.sin(a - h)))
            r1, a1 = 18 + rnd() * 4, a + (rnd() - 0.5) * 0.12
            pts.append((r1 * math.cos(a1), r1 * math.sin(a1)))
            continue
        f = flames.index(i)
        flame = _flame(a, r_base, h, 0.5 * (-1 if f % 2 else 1))
        pts.extend(flame(-1))
        pts.extend(flame(1)[::-1])
    ring = [(at[0] + x * size, at[1] + y * size) for x, y in pts]
    return ring, 9.6 * size


def plain_sun(at: Point, size: float) -> tuple[list[Point], list[tuple[Point, Point]]]:
    """Canary's sun: an open disc with eight rays. ``size`` is the disc's
    radius; the rays run from 1.6 to 4 of it. Returns the disc and the rays."""
    disc = [
        (at[0] + size * math.cos(math.pi * i / 12), at[1] + size * math.sin(math.pi * i / 12))
        for i in range(24)
    ]
    rays = []
    for k in range(8):
        a = k * math.pi / 4
        rays.append(
            (
                (at[0] + 1.6 * size * math.cos(a), at[1] + 1.6 * size * math.sin(a)),
                (at[0] + 4.0 * size * math.cos(a), at[1] + 4.0 * size * math.sin(a)),
            )
        )
    return disc, rays


def sketch_arrow(
    start: Point,
    direction: tuple[float, float],
    length: float,
    *,
    bow: float = 2.2,
    w0: float = 1.4,
    w1: float = 4.4,
    head: float = 11.0,
) -> list[Point]:
    """The sheet's hand-drawn arrow: a strip that leaves ``start`` along the
    unit ``direction``, bows gently to one side and widens as it goes, ending
    in a broad head. Everything is in the same unit as ``length``; ``bow``
    signs which side it bows to."""
    x, y = start
    ux, uy = direction
    nx, ny = -uy, ux
    n = 24
    body = length - head
    head_w = w1 * 2
    left: list[Point] = []
    right: list[Point] = []
    for i in range(n + 1):
        t = i / n
        off = bow * math.sin(t * math.pi)
        cx, cy = x + ux * body * t + nx * off, y + uy * body * t + ny * off
        w = w0 + (w1 - w0) * t
        left.append((cx + nx * w, cy + ny * w))
        right.append((cx - nx * w, cy - ny * w))
    ex, ey = x + ux * body, y + uy * body
    tip = (ex + ux * head, ey + uy * head)
    return [
        *left,
        (ex + nx * head_w, ey + ny * head_w),
        tip,
        (ex - nx * head_w, ey - ny * head_w),
        *right[::-1],
    ]
