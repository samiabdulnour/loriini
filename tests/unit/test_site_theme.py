"""The house styles the context and site sheets are drawn in.

Each theme is checked by what it changes on the drawing -- which colours
the zoning takes, whether the streets are white strips or centre lines,
which marks stand for the sun -- against the same tiny bundles the drawing
tests use, so the content is known to be the same and only the hand differs.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import cast

import pytest

from sun_study.archicad.site_analysis import (
    CREDIT_MM,
    Drawing,
    Frame,
    _aerial,
    _buffered,
    _clipped,
    _loops,
    _strips,
    context_drawing,
    frame_for,
    site_drawing,
)
from sun_study.site import curate, marks, theme
from sun_study.site.geo import ring_area
from sun_study.site.imagery import Aerial, Tile, toned
from tests.unit.test_site_analysis import (
    KOGARAH,
    LAT,
    LON,
    context_bundle,
    site_bundle,
)


def frame() -> Frame:
    return frame_for(KOGARAH, site_centre=(LON, LAT), anchor="site")


def pixel(path: str, xy: tuple[int, int]) -> tuple[int, int, int]:
    from PIL import Image

    with Image.open(path) as opened:
        return cast(tuple[int, int, int], opened.convert("RGB").getpixel(xy))


# -- the data ----------------------------------------------------------------------


def test_every_theme_has_the_whole_legend_in_colours_the_add_on_can_take() -> None:
    ids = {c.id for c in curate.CATEGORIES}
    for t in theme.THEMES:
        assert {c.id for c in t.categories} == ids, t.id
        for cat in t.categories:
            for colour in (cat.fill, cat.stroke, cat.texture_colour, cat.figure):
                if colour is not None:
                    assert len(colour) == 7 and colour.startswith("#"), (t.id, cat.id, colour)
            assert 0.0 < cat.opacity <= 1.0
        for ink in (t.ink, t.street_ink, t.site, t.road, t.rail, t.walk5, t.walk10, t.heritage):
            curate.rgb(ink)


def test_oatley_is_the_office_legend_the_sheets_were_first_drawn_in() -> None:
    oatley = theme.theme("oatley")
    assert [(c.id, c.fill, c.stroke) for c in oatley.categories] == [
        (c.id, c.fill, c.stroke) for c in curate.CATEGORIES
    ]
    assert oatley.ground == "aerial" and oatley.streets == "lines" and oatley.roundel == "ring"
    assert theme.site_theme("oatley").look.sun == "discs"


def test_themes_resolve_by_id_and_by_their_former_names() -> None:
    assert theme.theme("Kingfisher").id == "kingfisher"
    assert theme.theme("conure").id == "canary"
    assert theme.theme("flamingo-2").id == "kingfisher"
    assert theme.theme("office").id == "oatley"
    assert theme.theme(None).id == theme.DEFAULT_THEME == "flamingo"
    assert theme.theme("no such bird").id == "flamingo"
    assert theme.site_theme("dove").id == "heron"
    assert theme.site_theme("kookaburra").id == "kingfisher"
    assert theme.site_theme(None).id == theme.DEFAULT_SITE_THEME == "heron"
    assert theme.theme_ids() == ("flamingo", "kingfisher", "heron", "canary", "oatley")
    assert theme.site_theme_ids() == ("heron", "kingfisher", "flamingo", "canary", "oatley")


def test_a_tint_on_paper_is_the_colour_laid_over_white() -> None:
    assert theme.blend("#000000", "#ffffff", 0.5) == "#808080"
    assert theme.blend("#e8705a", "#ffffff", 1.0) == "#e8705a"
    r2 = theme.theme("flamingo").category("r2")
    assert r2.opacity == pytest.approx(0.22) and r2.on_paper() == "#fcefeb"
    assert theme.theme("kingfisher").category("r2").on_paper() == "#fbf4c9", "opacity 1 is itself"


def test_the_lep_colours_are_keyed_by_zone_code() -> None:
    assert theme.zone_fill("R3") == "#ff776e"
    assert theme.zone_fill("r3 medium density") == "#ff776e"
    assert theme.zone_fill("ZZ9") == "#d9d9d9", "an unknown code still shows"


def test_each_site_theme_draws_on_a_context_theme() -> None:
    for st in theme.SITE_THEMES:
        assert theme.theme(st.base).id == st.base, st.id


# -- the context sheet ----------------------------------------------------------


def test_flamingo_sits_on_paper_with_white_streets_and_textured_tints() -> None:
    drawing = context_drawing(context_bundle(), frame(), theme="flamingo")
    assert not drawing.figures, "no photograph under a paper theme"
    r3 = next(f for f in drawing.fills if f.element_id.endswith("(R3)"))
    assert r3.colour == theme.theme("flamingo").category("r3").on_paper() and not r3.wash
    streets = [f for f in drawing.fills if f.element_id == "SA STREET"]
    assert streets and all(f.colour == "#ffffff" for f in streets)
    assert not any(
        line.layer.endswith(".Lines") and line.colour == "#8a8a8a" and len(line.points) == 2
        for line in drawing.lines
        if line.weight_mm == 0.18
    ), "no grey centre lines"
    # The hospital is education's teal with white hatch lines over it.
    medical = next(f for f in drawing.fills if f.element_id.startswith("SA MEDICAL"))
    assert medical.contour == "#3f7f6d"
    hatch = [line for line in drawing.lines if line.weight_mm == 0.13]
    assert hatch, "a textured category is hatched with the drawing's own lines"
    # Solid roundels with a white letter; a plain street name, no band.
    roundel = next(f for f in drawing.fills if f.element_id == "SA BUS STOP")
    assert roundel.colour == "#3b4f8a"
    assert next(t for t in drawing.texts if t.text == "B").colour == "#ffffff"
    assert not any(f.element_id == "SA STREET NAME BAND" for f in drawing.fills)
    assert next(t for t in drawing.texts if t.text == "TEST ST").colour == "#5f9a58"
    # Dotted catchments, labelled with their minutes along the line.
    catchment = [line for line in drawing.lines if line.dotted and line.weight_mm == 0.6]
    assert catchment and any(t.text == "5 MIN" for t in drawing.texts)
    assert any(line.dotted and line.colour == "#7a8bb0" for line in drawing.lines), (
        "dotted bus route"
    )


def test_kingfisher_draws_the_cadastre_white_and_the_site_magenta() -> None:
    drawing = context_drawing(context_bundle(), frame(), theme="kingfisher")
    lots = [
        line for line in drawing.lines if line.layer.endswith(".Lines") and line.weight_mm == 0.45
    ]
    assert lots and all(line.colour == "#ffffff" for line in lots)
    site = next(f for f in drawing.fills if f.element_id == "SA SITE")
    assert site.contour == "#c2367c" and not site.wash


def test_heron_tones_the_aerial_grey_and_letters_in_white(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    Image.new("RGB", (40, 32), (200, 60, 60)).save(tmp_path / "aerial_0_0.jpg", "JPEG")
    bundle = context_bundle()
    bundle.aerial = Aerial((Tile("aerial_0_0.jpg", 0.0, 0.0, 1.0, 1.0),), 40, 32, str(tmp_path))
    drawing = context_drawing(bundle, frame(), theme="heron")
    (figure,) = drawing.figures
    assert figure.path.endswith("aerial_0_0-grey36.jpg"), "a toned copy beside the tile"
    r, g, b = pixel(figure.path, (20, 16))
    assert abs(r - g) < 8 and abs(g - b) < 8, "grey"
    assert r > 120, "and veiled toward white"
    assert not any(f.element_id == "SA AERIAL WASH" for f in drawing.fills), "the veil is baked in"
    assert next(t for t in drawing.texts if t.text == "TEST ST").colour == "#ffffff"
    assert not any(line.colour == "#7d7d7d" for line in drawing.lines), (
        "the photo shows the streets"
    )
    walkers = [f for f in drawing.fills if f.element_id == "SA WALKER"]
    assert len(walkers) == 4, "walker discs along the catchment"


def test_heron_without_a_photograph_falls_back_to_centre_lines() -> None:
    drawing = context_drawing(context_bundle(), frame(), theme="heron")
    assert not drawing.figures
    assert any(line.weight_mm == 0.18 and line.colour == "#7d7d7d" for line in drawing.lines)


def test_canary_keys_the_zoning_by_code_in_the_eplanning_colours() -> None:
    drawing = context_drawing(context_bundle(), frame(), theme="canary")
    r3 = next(f for f in drawing.fills if f.element_id.startswith("SA R3"))
    assert r3.colour == "#ff776e"
    assert not any(f.element_id.startswith("SA MEDICAL") for f in drawing.fills), (
        "no institution tint over the statutory colours"
    )
    legend = [t.text for t in drawing.texts if t.layer.endswith(".Sheet")]
    assert "R3 MEDIUM DENSITY RESIDENTIAL" in legend
    assert any(t.text == "5 MIN · 400M" for t in drawing.texts), "labelled catchments"


def test_the_sheets_own_words_keep_their_size_whatever_the_theme() -> None:
    for name in ("flamingo", "heron"):
        drawing = context_drawing(context_bundle(), frame(), theme=name)
        assert any(t.height_mm == CREDIT_MM for t in drawing.texts), name
        street = next(t for t in drawing.texts if t.text == "TEST ST")
        assert street.height_mm == pytest.approx(3.0 * 0.96), name


def test_the_legend_names_what_is_on_the_map_in_every_theme() -> None:
    for t in theme.THEMES:
        drawing = context_drawing(context_bundle(), frame(), theme=t)
        legend = [x.text for x in drawing.texts if x.layer.endswith(".Sheet")]
        assert "SITE" in legend and "TRAIN STATION" in legend, t.id
        assert "R2 LOW DENSITY RESIDENTIAL" not in legend, t.id
        assert len(drawing.layers) <= 5, (t.id, drawing.layers)


def test_a_street_strip_is_the_road_widened_with_round_ends() -> None:
    strip = _buffered([(0.0, 0.0), (100.0, 0.0)], 5.0)
    xs = [x for x, _ in strip]
    ys = [y for _, y in strip]
    assert min(xs) == pytest.approx(-5.0) and max(xs) == pytest.approx(105.0)
    assert min(ys) == pytest.approx(-5.0) and max(ys) == pytest.approx(5.0)
    bent = _buffered([(0.0, 0.0), (50.0, 0.0), (50.0, 50.0)], 5.0)
    assert len(bent) > len(strip), "a bend keeps both offsets"
    assert _buffered([(0.0, 0.0)], 5.0) == []


# -- the site sheet -------------------------------------------------------------


def test_heron_draws_crown_suns_strand_winds_and_white_outlines() -> None:
    drawing = site_drawing(site_bundle(), frame(), theme="heron")
    suns = [f for f in drawing.fills if f.element_id == "SA SUN"]
    assert len(suns) == 8, "four crowns, each with its inner circle"
    assert all(f.contour == "#6f7377" for f in suns)
    winds = [f for f in drawing.fills if f.element_id == "SA WIND"]
    assert len(winds) == 9, "three strands for each of three winds"
    names = {t.text for t in drawing.texts}
    assert {"WINTER\nSUNRISE", "SUMMER\nSUNSET", "NE SUMMER\nSEA BREEZE"} <= names
    assert any(t.text == "12PM" for t in drawing.texts), "the solar hours along the arcs"
    outline = [line for line in drawing.lines if line.colour == "#ffffff" and line.weight_mm == 0.3]
    assert outline, "the neighbour as a white outline, not a grey mass"
    assert not any(f.element_id == "SA BUILDINGS" for f in drawing.fills)
    levels = [t for t in drawing.texts if t.text.startswith("RL ") and t.layer.endswith(".Site")]
    assert levels and all(t.colour == "#cf4a2e" for t in levels), "levels in Heron's red"
    assert "3\n2 STOREY" in names and not any("RESIDENTIAL" in t for t in names if "\n" in t)
    zone = next(f for f in drawing.fills if f.element_id.endswith("(R3)"))
    assert zone.wash and zone.colour == "#eccbb2"
    neighbour = next(t for t in drawing.texts if t.text == "3\n2 STOREY")
    assert neighbour.height_mm == pytest.approx(3.0 * 1.2), "a fifth larger"


def test_kingfisher_fills_the_lots_by_zone_and_bands_the_climate() -> None:
    bundle = site_bundle()
    bundle.all_lots = bundle.site_lots
    drawing = site_drawing(bundle, frame(), theme="kingfisher")
    assert not drawing.figures
    lot = next(f for f in drawing.fills if f.element_id == "SA R3 MEDIUM DENSITY RESIDENTIAL")
    assert lot.colour == "#f9e3f1" and lot.contour == "#ffffff"
    building = next(f for f in drawing.fills if f.element_id == "SA BUILDINGS")
    assert building.colour == "#f8cee8" and building.contour == "#ffffff", "R3's pink, white edge"
    paths = [f for f in drawing.fills if f.element_id == "SA SUN PATH"]
    assert len(paths) == 2, "a crescent per solstice"
    arrows = [f for f in drawing.fills if f.element_id == "SA WIND ARROW"]
    assert len(arrows) == 27, "three arrows on each of three winds, each of three pieces"
    site = next(f for f in drawing.fills if f.element_id == "SA SITE")
    assert site.contour == "#c2367c"


def test_flamingo_draws_white_hatched_buildings_and_the_office_marks() -> None:
    drawing = site_drawing(site_bundle(), frame(), theme="flamingo")
    building = next(f for f in drawing.fills if f.element_id == "SA BUILDINGS")
    assert building.colour == "#ffffff" and building.contour == "#d48b75"
    hatch = [line for line in drawing.lines if line.colour == "#d48b75" and line.weight_mm == 0.13]
    assert hatch, "finely hatched in the family's ink"
    suns = [f for f in drawing.fills if f.element_id == "SA SUN"]
    assert len(suns) >= 4 * 9 and all(f.colour == "#d48f00" for f in suns)
    winds = [f for f in drawing.fills if f.element_id == "SA WIND"]
    assert winds and all(f.colour == "#3d8fd1" for f in winds)
    assert any(line.dotted for line in drawing.lines), "the winter arc dotted"


def test_canary_draws_one_climate_circle_and_the_statutory_colours() -> None:
    bundle = site_bundle()
    drawing = site_drawing(bundle, frame(), theme="canary")
    zone = next(f for f in drawing.fills if f.element_id.startswith("SA R3"))
    assert zone.colour == "#ff776e" and zone.wash
    circle = [
        line for line in drawing.lines if line.layer.endswith(".Sheet") and len(line.points) == 73
    ]
    assert circle and circle[0].dashed, "one dashed ring about the site"
    suns = [f for f in drawing.fills if f.element_id == "SA SUN"]
    assert len(suns) == 4 and all(f.colour == "#ffffff" for f in suns)
    quarters = [f for f in drawing.fills if f.element_id == "SA WIND"]
    assert len(quarters) == 3 and all(f.hatch for f in quarters)
    assert any(f.element_id == "SA NORTH" for f in drawing.fills)
    assert not any(line.colour == "#3f9a5c" for line in drawing.lines), "no contours"
    names = {t.text for t in drawing.texts}
    assert "NE SUMMER SEA BREEZE" in names and "WINTER\nSUNRISE" in names
    assert not any("STOREY\n" in t for t in names), "number and storeys, no zone"


def test_heritage_is_hatched_in_the_eplanning_inks_where_a_theme_asks() -> None:
    from tests.unit.test_site_analysis import collection, polygon, square

    bundle = site_bundle()
    bundle.heritage = collection(
        polygon(square(LON + 0.0005, LAT, 10.0), LAY_CLASS="Item - General"),
        polygon(square(LON - 0.0005, LAT, 30.0), LAY_CLASS="Conservation Area - General"),
    )
    drawing = site_drawing(bundle, frame(), theme="canary")
    items = [f for f in drawing.fills if f.element_id == "SA HERITAGE ITEM"]
    areas = [f for f in drawing.fills if f.element_id == "SA HERITAGE CONSERVATION AREA"]
    assert items and items[0].colour == "#dbbb7b" and items[0].hatch
    assert areas and areas[0].colour == "#ff0000"
    plain = site_drawing(bundle, frame(), theme="heron")
    assert not any(f.element_id.startswith("SA HERITAGE") for f in plain.fills)


def test_the_site_keeps_its_colours_on_a_toned_photograph(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    Image.new("RGB", (100, 86), (200, 60, 60)).save(tmp_path / "aerial_0_0.jpg", "JPEG")
    bundle = site_bundle()
    bundle.aerial = Aerial((Tile("aerial_0_0.jpg", 0.0, 0.0, 1.0, 1.0),), 100, 86, str(tmp_path))
    drawing = site_drawing(bundle, frame(), theme="heron")
    (figure,) = drawing.figures
    centre = pixel(figure.path, (50, 43))
    corner = pixel(figure.path, (3, 3))
    assert centre[0] - centre[1] > 80, "the site, in the middle, keeps its red"
    assert abs(corner[0] - corner[1]) < 8, "the rest is grey"


def test_a_toned_tile_is_reused_and_a_bad_one_left_alone(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    source = tmp_path / "t.jpg"
    Image.new("RGB", (8, 8), (10, 200, 10)).save(source, "JPEG")
    first = toned(source, grey=True, veil=0.5)
    assert first != source and first.is_file()
    stamp = first.stat().st_mtime
    assert toned(source, grey=True, veil=0.5) == first and first.stat().st_mtime == stamp
    assert toned(source, grey=False, veil=0.0) == source, "nothing to do"
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a picture")
    assert toned(bad, grey=True, veil=0.5) == bad, "a tile Pillow cannot read keeps its photo"


# -- the marks ---------------------------------------------------------------------


def test_the_office_symbols_flatten_to_polygons_with_their_holes() -> None:
    eye = marks.polygons(marks.EYE, 10.0, (0.0, 0.0))
    assert len(eye) == 2 and sum(len(holes) for _, holes in eye) == 1, "the pupil is a hole"
    sun = marks.polygons(marks.SUN, 10.0, (5.0, 5.0))
    assert len(sun) == 9, "eight rays and a disc"
    xs = [x for outer, _ in sun for x, _ in outer]
    assert max(xs) == pytest.approx(15.0, abs=0.05) and min(xs) == pytest.approx(-5.0, abs=0.05)
    turned = marks.polygons(marks.ARROW, 10.0, (0.0, 0.0), math.pi / 2)
    ys = [y for outer, _ in turned for _, y in outer]
    assert max(ys) == pytest.approx(10.0, abs=0.05), "turned to point along +y"


def test_the_crown_and_the_crescent_are_sized_in_the_sheets_millimetre() -> None:
    ring, inner = marks.crown_sun((0.0, 0.0), 2.0, seed=3)
    assert inner == pytest.approx(19.2)
    reach = max(math.hypot(x, y) for x, y in ring)
    assert 36.0 <= reach <= 46.0, "teeth to about 18-22 mm, at 2 m a millimetre"
    other, _ = marks.crown_sun((0.0, 0.0), 2.0, seed=4)
    assert other != ring, "each sun from its own seed"
    crescent = marks.crescent((0.0, 0.0), 100.0, 0.0, math.pi, 10.0)
    radii = [math.hypot(x, y) for x, y in crescent]
    assert max(radii) == pytest.approx(100.0) and min(radii) == pytest.approx(90.0, abs=0.5)


def test_a_sketched_arrow_widens_toward_its_head() -> None:
    arrow = marks.sketch_arrow((0.0, 0.0), (1.0, 0.0), 50.0, bow=0.0)
    xs = [x for x, _ in arrow]
    assert max(xs) == pytest.approx(50.0)
    ys = [abs(y) for _, y in arrow]
    assert max(ys) == pytest.approx(8.8), "the head's wings, twice the strip's end width"


def test_a_drawing_scales_its_map_words_and_not_the_sheets() -> None:
    drawing = Drawing(1000.0, "Site Analysis", text_scale=1.5)
    drawing.text("Neighbours", "12", (0.0, 0.0), height_mm=3.0)
    drawing.text("Legend", "SITE", (0.0, 0.0), height_mm=3.0)
    heights = {t.text: t.height_mm for t in drawing.texts}
    assert heights == {"12": 4.5, "SITE": 3.0}


def test_an_aerial_on_paper_is_never_asked_for() -> None:
    drawing = Drawing(3000.0, "Context Analysis")
    bundle = context_bundle()
    assert not _aerial(drawing, bundle, frame()), "no tiles, nothing placed"


def test_a_zone_is_cut_to_the_map_field_and_one_outside_it_dropped() -> None:
    window = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]
    big = [(-500.0, -500.0), (500.0, -500.0), (500.0, 500.0), (-500.0, 500.0)]
    (cut,) = _clipped([big], window)
    assert sorted(cut) == sorted(window), "a zone round the whole sheet becomes the sheet"
    half = [(50.0, -10.0), (200.0, -10.0), (200.0, 60.0), (50.0, 60.0)]
    (cut,) = _clipped([half], window)
    assert min(x for x, _ in cut) == pytest.approx(50.0) and max(x for x, _ in cut) == 100.0
    assert _clipped([[(300.0, 300.0), (400.0, 300.0), (400.0, 400.0)]], window) == []
    turned = [(0.0, 0.0), (70.7, 70.7), (0.0, 141.4), (-70.7, 70.7)]
    (cut,) = _clipped([big], turned)
    assert abs(ring_area(cut)) == pytest.approx(abs(ring_area(turned)), rel=1e-3), (
        "any convex window"
    )


def test_the_site_is_a_hole_in_the_zone_wash_it_lies_in() -> None:
    drawing = site_drawing(site_bundle(), frame(), theme="canary")
    zone = next(f for f in drawing.fills if f.element_id.startswith("SA R3"))
    assert len(zone.rings) == 2, "the outer ring, and the site cut out of it"


def test_a_hole_that_reaches_the_sheets_edge_is_kept_just_inside_it() -> None:
    from sun_study.site.geo import point_in_ring

    window = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]
    outer = [(-500.0, -500.0), (500.0, -500.0), (500.0, 500.0), (-500.0, 500.0)]
    hole = [(40.0, 20.0), (60.0, 20.0), (60.0, 80.0), (40.0, 80.0)]
    cut_outer, cut_hole = _clipped([outer, hole], window)
    assert all(point_in_ring(x, y, cut_outer) for x, y in cut_hole), "strictly inside"
    assert max(y for _, y in cut_hole) < 50.0


def test_a_pinched_ring_is_split_into_its_loops() -> None:
    pinched = [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 10.0),
        (5.0, 5.0),
        (0.0, 10.0),
        (0.0, 7.0),
        (5.0, 5.0),
    ]
    loops = _loops(pinched)
    assert len(loops) == 2 and all(len(loop) >= 3 for loop in loops)
    assert _loops([(0.0, 0.0), (10.0, 0.0), (7.0, 3.0), (10.0, 0.0), (10.0, 10.0)]) == [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    ], "a spike out and back has no area and goes"
    assert _loops([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]) == [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    ]


def test_a_hairpin_road_becomes_rectangles_and_discs_rather_than_a_crossed_strip() -> None:
    straight = _strips([(0.0, 0.0), (100.0, 0.0)], 5.0)
    assert len(straight) == 1
    hairpin = _strips([(0.0, 0.0), (100.0, 0.0), (0.0, 1.0)], 5.0)
    assert len(hairpin) == 2 + 3, "a rectangle per segment and a disc per joint"


def test_loops_split_at_a_pinch_no_longer_share_the_vertex() -> None:
    pinched = [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 10.0),
        (5.0, 5.0),
        (0.0, 10.0),
        (0.0, 7.0),
        (5.0, 5.0),
    ]
    big, small = sorted(_loops(pinched), key=lambda loop: -abs(ring_area(loop)))
    assert (5.0, 5.0) in big and (5.0, 5.0) not in small
    moved = next(pt for pt in small if math.dist(pt, (5.0, 5.0)) < 0.1)
    assert 0.0 < math.dist(moved, (5.0, 5.0)) <= 0.051


def test_a_ring_that_nearly_touches_itself_is_split_as_if_it_did() -> None:
    # A square with a bay cut in from the top that comes within a centimetre
    # of the bottom edge: two loops once the bay's tip is snapped onto it.
    ring = [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 10.0),
        (6.0, 10.0),
        (6.0, 0.01),
        (4.0, 0.01),
        (4.0, 10.0),
        (0.0, 10.0),
    ]
    loops = _loops(ring)
    assert len(loops) == 2, [len(loop) for loop in loops]


# -- numbered places and the legend on the layout (D138) ---------------------------


def test_the_site_analyst_themes_number_the_places_and_key_them() -> None:
    drawing = context_drawing(context_bundle(), frame(), theme="flamingo")
    discs = [f for f in drawing.fills if f.element_id.startswith("SA PLACE ")]
    assert [f.element_id for f in discs] == [
        "SA PLACE 1: ST GEORGE HOSPITAL",
        "SA PLACE 2: JUBILEE OVAL",
    ], "institutions in legend order, then the open spaces, each name once"
    assert discs[0].colour == "#c49a52" and discs[1].colour == "#5f9a58", "disc inks"
    on_map = {t.text for t in drawing.texts if not t.layer.endswith(".Sheet")}
    assert {"1", "2", "T", "TEST ST"} <= on_map
    assert not {"ST GEORGE\nHOSPITAL", "JUBILEE OVAL", "KOGARAH"} & on_map, (
        "the only words on the map are the street names"
    )
    legend = [t.text for t in drawing.texts if t.layer.endswith(".Sheet")]
    assert "KEY" in legend
    assert {"ST GEORGE HOSPITAL", "JUBILEE OVAL", "KOGARAH"} <= set(legend)
    assert drawing.legend is not None
    keyed = [row for row in drawing.legend[1] if row.key]
    assert [(row.mark, row.label) for row in keyed] == [
        ("1", "ST GEORGE HOSPITAL"),
        ("2", "JUBILEE OVAL"),
        ("T", "KOGARAH"),
    ]


def test_oatley_keeps_the_names_on_the_map() -> None:
    drawing = context_drawing(context_bundle(), frame(), theme="oatley")
    on_map = {t.text for t in drawing.texts if not t.layer.endswith(".Sheet")}
    assert {"ST GEORGE\nHOSPITAL", "JUBILEE OVAL", "KOGARAH"} <= on_map
    assert not any(f.element_id.startswith("SA PLACE ") for f in drawing.fills)


def test_more_than_one_station_is_numbered_nearest_the_site_first() -> None:
    from sun_study.site import nsw

    bundle = context_bundle()
    bundle.stations = (
        nsw.NamedPoint("ALLAWAH", LON - 0.006, LAT),
        nsw.NamedPoint("KOGARAH", LON + 0.002, LAT),
        nsw.NamedPoint("KOGARAH LIGHT RAIL", LON, LAT - 0.002),
    )
    drawing = context_drawing(bundle, frame(), theme="heron")
    assert drawing.legend is not None
    keyed = {row.label: row.mark for row in drawing.legend[1] if row.key and row.mark}
    assert keyed["KOGARAH"] == "T1" and keyed["ALLAWAH"] == "T2"
    assert keyed["KOGARAH LIGHT RAIL"] == "L", "one light rail stop needs no number"
    on_map = {t.text for t in drawing.texts if not t.layer.endswith(".Sheet")}
    assert {"T1", "T2", "L"} <= on_map


def test_a_key_too_long_for_the_column_keeps_the_places_nearest_the_site() -> None:
    from sun_study.archicad.site_analysis import Place, Row, _within_the_column

    places = [Place(i + 1, f"PLACE {i + 1}", "medical", (float(i) * 10.0, 0.0)) for i in range(80)]
    legend = [Row("fill", "#ffffff", None, f"ROW {i}") for i in range(20)]
    kept = _within_the_column(places, legend, [], (0.0, 0.0))
    assert 20 < len(kept) < 80
    assert [p.number for p in kept] == list(range(1, len(kept) + 1)), "numbered again"
    assert kept[-1].name == f"PLACE {len(kept)}", "the nearest are the ones kept"
    few = places[:5]
    assert _within_the_column(few, legend, [], (0.0, 0.0)) == few


def test_a_legend_drawn_on_paper_breaks_its_labels_to_the_column() -> None:
    from sun_study.archicad.site_analysis import Row, _legend

    rows = [
        Row("fill", "#ffffff", None, "MIXED USE CLUSTER RESIDENTIAL/COMMERCIAL AND MORE WORDS"),
        Row("disc", "#000000", None, "A PLACE", mark="1", key=True),
    ]
    paper = Drawing(1.0, "Context Analysis")
    _legend(paper, rows, (0.7, 0.5), title="CONTEXT ANALYSIS", width_mm=60.0)
    labels = [t.text for t in paper.texts]
    assert any("\n" in label for label in labels), "a long label goes onto a second line"
    assert "KEY" in labels and "1" in labels
    sheet = Drawing(3000.0, "Context Analysis")
    _legend(sheet, rows, (0.0, 0.0), title="CONTEXT ANALYSIS")
    assert not any("\n" in t.text for t in sheet.texts), "the worksheet's has room to spare"


def test_the_legend_comes_off_a_drawing_and_keeps_its_rows() -> None:
    drawing = context_drawing(context_bundle(), frame(), theme="kingfisher")
    bare = drawing.without(frozenset({"Legend"}))
    assert not any(t.part == "Legend" for t in bare.texts)
    assert not any(f.part == "Legend" for f in bare.fills)
    assert bare.legend == drawing.legend, "the rows go with it, for the layout to draw"
    assert any(t.text == "TEST ST" for t in bare.texts), "the map stays"


def test_the_map_field_is_centred_from_the_bottom_margin() -> None:
    from sun_study.archicad.layout import LayoutSheet
    from sun_study.archicad.site_analysis import _sheet_frame

    sheet = LayoutSheet(
        width_mm=841.0, height_mm=594.0, left_mm=10.0, top_mm=40.0, right_mm=10.0, bottom_mm=10.0
    )
    _x0, y0, _x1, y1 = _sheet_frame(sheet, width_mm=690.0, height_mm=500.0, title_block_mm=100.0)
    assert (y0 + y1) / 2 * 1000 == pytest.approx(10.0 + (594.0 - 50.0) / 2), (
        "midway between the bottom and top margins, layout y running upward"
    )
