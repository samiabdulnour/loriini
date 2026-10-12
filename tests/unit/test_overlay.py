"""The reference image, tested without Archicad and mostly without a screen.

Two things are worth testing. The geometry -- where a picture sits in its
frame, and which window it is laid over -- because a picture fitted to the
wrong shape is a view set up from the wrong angle, quietly. And the
controls' promises: that a file which is not a picture is said and not
raised, that the lock says whether the mouse goes through, that hiding and
closing do what they say. The Win32 calls themselves are not tested here;
off Windows they answer "nothing" and "no", and the tests say that much.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from PIL import Image

# Skipped, not collected into an error, where Tk cannot be had: the Linux
# runners ship no tkinter. It has to come before the import underneath,
# which imports tkinter itself.
if TYPE_CHECKING:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter", reason="this machine has no tkinter")
from tkinter import ttk

from sun_study.app import overlay
from sun_study.app.overlay import (
    FIT,
    GROUND,
    LEAST_OPACITY,
    SETTLE_MS,
    STANDING_HINT,
    STRETCH,
    Found,
    Placement,
    archicad_windows,
    click_through,
    fitted,
    pick,
    stretched,
)

# -- geometry, with nothing on screen ----------------------------------------


def test_a_picture_fits_inside_the_frame_with_its_shape_kept() -> None:
    """A wide picture in a square frame leaves the room below it; a tall
    one leaves it to the right. Either way it sits in the frame's top-left
    corner -- so that sizing the frame by its bottom-right corner leaves what
    was lined up where it was -- and its shape is the picture's."""
    wide = fitted((1600, 900), (800, 800))
    assert (wide.width, wide.height) == (800, 450)
    assert (wide.x, wide.y) == (0, 0)
    tall = fitted((900, 1600), (800, 800))
    assert (tall.width, tall.height) == (450, 800)
    assert (tall.x, tall.y) == (0, 0)


def test_a_frame_of_the_pictures_own_shape_is_filled_exactly() -> None:
    assert fitted((1600, 900), (640, 360)) == Placement(0, 0, 640, 360)


def test_stretched_is_the_frame_itself_whatever_the_picture() -> None:
    assert stretched((1600, 900), (500, 500)) == Placement(0, 0, 500, 500)


def test_nothing_to_fit_is_an_empty_placement_not_a_division_by_nothing() -> None:
    assert fitted((0, 900), (800, 800)).area == 0
    assert fitted((1600, 900), (800, 0)).area == 0
    assert stretched((1600, 900), (0, 0)).area == 0


def test_a_placement_reads_and_writes_tks_spelling() -> None:
    assert Placement.parse("640x400+120+120") == Placement(120, 120, 640, 400)
    assert Placement(120, 120, 640, 400).geometry == "640x400+120+120"
    # A second screen to the left has negative coordinates.
    assert Placement.parse("640x400-1200+20").x == -1200
    assert Placement(-1200, 20, 640, 400).geometry == "640x400-1200+20"
    with pytest.raises(ValueError, match="not a geometry"):
        Placement.parse("wide and tall")


BIG = Found("Other.pln - Archicad 26", Placement(0, 0, 1900, 1000))
SMALL = Found("Kogarah.pln - Archicad 26", Placement(100, 100, 1200, 800))
PALETTE = Found("Kogarah.pln - Archicad 26 - Navigator", Placement(0, 0, 300, 600))


def test_the_window_naming_the_project_is_picked_over_a_bigger_one() -> None:
    """Two projects open is the ordinary case, and the picker above the tabs
    already says which one is meant."""
    assert pick([BIG, SMALL], "Kogarah") is SMALL
    assert pick([BIG, SMALL], "kogarah") is SMALL


def test_without_a_project_or_with_one_nobody_has_open_the_largest_is_picked() -> None:
    assert pick([SMALL, BIG]) is BIG
    assert pick([SMALL, BIG], "Silverwater") is BIG


def test_among_the_windows_naming_the_project_the_largest_is_the_one() -> None:
    """A palette carries the project's name too; the one being worked in is
    the big one."""
    assert pick([PALETTE, SMALL], "Kogarah") is SMALL


def test_no_windows_is_nothing_to_cover() -> None:
    assert pick([]) is None
    assert pick([], "Kogarah") is None


# -- the picture and its controls, on a screen nobody sees ------------------


@pytest.fixture
def root() -> Any:
    try:
        made = tk.Tk()
    except tk.TclError:  # pragma: no cover - a machine with no display
        pytest.skip("no display for Tk")
    made.withdraw()
    from sun_study.app import theme

    theme.apply(made)
    yield made
    made.destroy()


@pytest.fixture
def palette(root: Any) -> Any:
    """The controls, built into two panels of a page the way the window
    builds them, with what each control says kept where a test can read it."""
    picture, placing = ttk.Frame(root), ttk.Frame(root)
    picture.pack()
    placing.pack()
    explained: dict[str, str] = {}
    made = overlay.Palette(
        picture,
        placing,
        project=lambda: "Kogarah",
        explain=lambda widget, _title, text: explained.__setitem__(str(widget), text),
    )
    made.explained = explained  # type: ignore[attr-defined]
    yield made
    made.close()


@pytest.fixture
def photograph(tmp_path: Path) -> Path:
    """A landscape picture, 1600 by 900, as a JPEG -- the shape and the kind
    a photograph of a site is."""
    where = tmp_path / "corner.jpg"
    Image.new("RGB", (1600, 900), "#B0C4DE").save(where, quality=80)
    return where


def settled(root: Any) -> None:
    """Let the frame hear its new size, then let its redraw timer fire."""
    root.update()
    time.sleep(SETTLE_MS / 1000 + 0.05)
    root.update()


def test_a_picture_is_read_named_and_shown(palette: Any, root: Any, photograph: Path) -> None:
    assert palette.take(photograph) == ""
    assert palette.overlay.picture is not None
    assert palette.overlay.picture.size == (1600, 900)
    assert palette.named.cget("text").startswith("corner.jpg")
    assert "1600" in palette.named.cget("text")
    root.update()
    assert palette.overlay.shown


def test_the_picture_sits_fitted_in_its_frame_and_then_stretched_to_it(
    palette: Any, root: Any, photograph: Path
) -> None:
    """The frame is square; the wide picture sits at the top of it with the
    room below, and Stretch pulls it to the whole frame. 802 is 800 inside
    the one-pixel blue edge an unlocked frame wears."""
    palette.take(photograph)
    palette.overlay.place_at(Placement(0, 0, 802, 802))
    settled(root)
    face = palette.overlay.face
    assert (face.winfo_width(), face.winfo_height()) == (800, 450)
    assert (face.winfo_x(), face.winfo_y()) == (1, 1)
    palette._mode(STRETCH)
    root.update()
    assert (face.winfo_width(), face.winfo_height()) == (800, 800)
    assert (face.winfo_x(), face.winfo_y()) == (1, 1)
    # Locked, the edge goes and the picture takes its two pixels.
    palette.locked.set(True)
    palette._lock()
    root.update()
    assert (face.winfo_width(), face.winfo_height()) == (802, 802)
    assert (face.winfo_x(), face.winfo_y()) == (0, 0)
    palette.locked.set(False)
    palette._lock()
    assert str(palette.stretch.cget("style")) == "TileOn.TButton"
    assert str(palette.fit.cget("style")) == "Tile.TButton"
    palette._mode(FIT)
    root.update()
    assert face.winfo_height() == 450


def test_the_first_frame_is_the_middle_of_the_screen_at_the_pictures_shape(
    palette: Any, root: Any, photograph: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no Archicad window to lay it over, the picture opens centred,
    three fifths of the screen wide, its shape kept. No Archicad window is
    *made sure of*: on a workstation with one open, the picture is laid over
    it instead, which is the feature."""
    monkeypatch.setattr(overlay, "archicad_windows", lambda: [])
    root.update()
    palette.take(photograph)
    root.update()
    where = palette.overlay.placement
    wide, tall = root.winfo_screenwidth(), root.winfo_screenheight()
    expected = fitted((1600, 900), (wide * 3 // 5, tall * 3 // 5))
    assert (where.width, where.height) == (expected.width, expected.height)
    assert (where.x, where.y) == ((wide - expected.width) // 2, (tall - expected.height) // 2)
    assert palette.overlay.placed


def pointer(x: int, y: int) -> Any:
    """What a mouse event says about where the pointer is on the screen."""
    return SimpleNamespace(x_root=x, y_root=y)


def test_the_window_is_kept_on_top_while_a_picture_is_open(
    palette: Any, root: Any, photograph: Path
) -> None:
    """The picture is on top of everything, so the window its controls are
    in is too while it is open -- and goes back to an ordinary window when
    the picture is hidden or closed."""
    assert not int(root.attributes("-topmost"))
    palette.take(photograph)
    root.update()
    assert int(root.attributes("-topmost"))
    palette.hidden.set(True)
    palette._hide()
    assert not int(root.attributes("-topmost"))
    palette.hidden.set(False)
    palette._hide()
    assert int(root.attributes("-topmost"))
    palette.close()
    assert not int(root.attributes("-topmost"))


def test_dragging_the_picture_moves_it(palette: Any, root: Any, photograph: Path) -> None:
    palette.take(photograph)
    palette.lay(Placement(300, 300, 600, 400))
    root.update()
    before = palette.overlay.placement
    palette.overlay._grab(pointer(before.x + 40, before.y + 40))
    palette.overlay._drag(pointer(before.x + 90, before.y + 70))
    root.update()
    after = palette.overlay.placement
    assert (after.x, after.y) == (before.x + 50, before.y + 30)


def test_the_corner_sizes_the_picture_from_its_top_left_and_nothing_else(
    palette: Any, root: Any, photograph: Path
) -> None:
    """Pull the corner out and the top-left corner stays put and the picture
    keeps its top-left in the frame. Push it in and the frame stops at
    ``LEAST_SIDE``.

    Sized to fit a 1024 by 768 screen: Windows clamps a window to the
    screen, and a CI runner's is small, so a frame asked to reach past its
    edge comes back narrower than asked."""
    palette.take(photograph)
    palette.lay(Placement(200, 200, 500, 300))
    settled(root)
    before = palette.overlay.placement
    palette.overlay._grab_corner(pointer(before.x + before.width, before.y + before.height))
    palette.overlay._resize(pointer(before.x + before.width + 200, before.y + before.height + 100))
    settled(root)
    after = palette.overlay.placement
    assert (after.x, after.y) == (before.x, before.y)
    assert (after.width, after.height) == (before.width + 200, before.height + 100)
    face = palette.overlay.face
    assert (face.winfo_x(), face.winfo_y()) == (1, 1)
    palette.overlay._resize(pointer(before.x - 1000, before.y - 1000))
    settled(root)
    smallest = palette.overlay.placement
    assert (smallest.width, smallest.height) == (overlay.LEAST_SIDE, overlay.LEAST_SIDE)


def test_pulling_the_corner_by_hand_holds_the_top_left_where_it_was(
    palette: Any, root: Any, photograph: Path
) -> None:
    """The way a window on a PC is sized from its corner: the top-left stays
    put. Sent through Tk's own bindings rather than to the handlers, because
    that is where it went wrong -- a Toplevel's bindings fire for everything
    inside it, so the corner's drag also ran the picture's own move, and the
    picture slid by every pixel the corner was pulled."""
    palette.take(photograph)
    palette.lay(Placement(200, 200, 500, 300))
    settled(root)
    before = palette.overlay.placement
    grip = palette.overlay.grip
    corner_x, corner_y = before.x + before.width - 4, before.y + before.height - 4
    grip.event_generate("<ButtonPress-1>", x=2, y=2, rootx=corner_x, rooty=corner_y)
    for step in (20, 60, 120):
        grip.event_generate(
            "<Motion>",
            x=2 + step,
            y=2 + step // 2,
            rootx=corner_x + step,
            rooty=corner_y + step // 2,
            state=0x100,
        )
        root.update()
        during = palette.overlay.placement
        assert (during.x, during.y) == (before.x, before.y), f"moved after {step} px"
    grip.event_generate("<ButtonRelease-1>", x=122, y=62, rootx=corner_x + 120, rooty=corner_y + 60)
    settled(root)
    after = palette.overlay.placement
    assert (after.x, after.y) == (before.x, before.y)
    assert (after.width, after.height) == (before.width + 120, before.height + 60)


def test_the_slider_sets_how_much_shows_and_says_it_in_percent(palette: Any) -> None:
    palette.level.set(30)
    palette._slid()
    assert palette.overlay.opacity == pytest.approx(0.3)
    assert float(palette.overlay.attributes("-alpha")) == pytest.approx(0.3)
    assert palette.percent.cget("text") == "30 %"
    # It can be faded but never gone: the slider's floor is the frame's.
    palette.overlay.set_opacity(0.0)
    assert palette.overlay.opacity == LEAST_OPACITY
    palette.overlay.set_opacity(3.0)
    assert palette.overlay.opacity == 1.0


def test_locking_takes_the_corner_away_and_says_whether_the_mouse_goes_through(
    palette: Any, root: Any, photograph: Path
) -> None:
    palette.take(photograph)
    root.update()
    assert palette.overlay.grip.winfo_manager() == "place"
    palette.locked.set(True)
    palette._lock()
    assert palette.overlay.locked
    assert palette.overlay.grip.winfo_manager() == ""
    said = palette.hint.cget("text")
    assert said.startswith("Locked.")
    if sys.platform in {"win32", "darwin"}:
        assert palette.overlay.passes
        assert "goes through" in said
    else:
        # Nothing here can send the mouse through a window, and the palette
        # says so rather than promising it.
        assert not palette.overlay.passes
        assert "does not go through" in said
    palette.locked.set(False)
    palette._lock()
    assert palette.overlay.grip.winfo_manager() == "place"
    assert palette.hint.cget("text") == STANDING_HINT


@pytest.mark.skipif(sys.platform != "darwin", reason="the Mac's own click-through")
def test_on_a_mac_a_locked_picture_lets_the_mouse_through_and_unlocked_takes_it_back(
    palette: Any, root: Any, photograph: Path
) -> None:
    palette.take(photograph)
    root.update()
    assert overlay._mac_ignores_mouse(palette.overlay, True)
    assert overlay._mac_ignores_mouse(palette.overlay, False)
    palette.locked.set(True)
    palette._lock()
    assert palette.overlay.passes
    palette.locked.set(False)
    palette._lock()
    assert not palette.overlay.locked


def test_the_window_stays_over_its_picture(palette: Any, root: Any, photograph: Path) -> None:
    """Pressing the picture brings it to the front; the window with the
    controls is put back over it, so the slider that dims the picture is
    never under it."""
    root.deiconify()
    palette.take(photograph)
    palette.lay(Placement(200, 200, 500, 300))
    root.update()
    where = palette.overlay.placement
    palette.overlay.face.event_generate("<ButtonPress-1>", x=10, y=10)
    palette.overlay.face.event_generate("<ButtonRelease-1>", x=10, y=10)
    root.update()
    order = [str(name) for name in root.tk.splitlist(root.tk.call("wm", "stackorder", root))]
    assert order[-1] == str(root), order
    assert palette.overlay.placement == where


def test_hide_takes_the_picture_off_the_screen_and_back(
    palette: Any, root: Any, photograph: Path
) -> None:
    palette.take(photograph)
    root.update()
    assert palette.overlay.shown
    palette.hidden.set(True)
    palette._hide()
    root.update()
    assert not palette.overlay.shown
    palette.hidden.set(False)
    palette._hide()
    root.update()
    assert palette.overlay.shown


def test_a_file_that_is_not_a_picture_is_said_not_raised(
    palette: Any, tmp_path: Path, photograph: Path
) -> None:
    """And the picture it had stays: a mis-click on the wrong file should not
    cost the one already lined up."""
    notes = tmp_path / "notes.txt"
    notes.write_text("not a picture", encoding="utf-8")
    palette.take(photograph)
    said = palette.take(notes)
    assert said.startswith("Could not read notes.txt")
    assert palette.hint.cget("text") == said
    assert str(palette.hint.cget("style")) == "Refused.TLabel"
    assert palette.overlay.name == "corner.jpg"
    missing = palette.take(tmp_path / "gone.png")
    assert missing.startswith("Could not read gone.png")


def test_a_phones_photograph_is_turned_the_right_way_up(palette: Any, tmp_path: Path) -> None:
    """A phone held upright writes a landscape JPEG with an orientation tag
    saying to turn it. Shown as stored it is on its side."""
    where = tmp_path / "upright.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to view
    Image.new("RGB", (1600, 900), "#B0C4DE").save(where, quality=80, exif=exif.tobytes())
    assert palette.take(where) == ""
    assert palette.overlay.picture.size == (900, 1600)


def test_a_pictures_own_transparency_is_laid_on_the_ground(palette: Any, tmp_path: Path) -> None:
    """A transparent PNG -- a render with no sky -- becomes plain RGB over
    the ground, which off Windows is the mat and on Windows the colour key,
    so that there it stays see-through."""
    where = tmp_path / "render.png"
    picture = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    picture.putpixel((0, 0), (255, 0, 0, 255))
    picture.save(where)
    assert palette.take(where) == ""
    flat = palette.overlay.picture
    assert flat.mode == "RGB"
    assert flat.getpixel((0, 0)) == (255, 0, 0)
    ground = overlay.KEY if palette.overlay.keyed else GROUND
    expected = tuple(int(ground[i : i + 2], 16) for i in (1, 3, 5))
    assert flat.getpixel((10, 10)) == expected


def test_a_picture_too_big_to_keep_is_kept_at_the_longest_side(
    palette: Any, tmp_path: Path
) -> None:
    where = tmp_path / "scan.png"
    Image.new("L", (6000, 3000), 128).save(where)
    assert palette.take(where) == ""
    assert palette.overlay.picture.size == (overlay.LONGEST_SIDE, overlay.LONGEST_SIDE // 2)


@pytest.mark.skipif(sys.platform == "win32", reason="the calls are real on Windows")
def test_off_windows_no_archicad_window_is_found_and_the_palette_says_so(
    palette: Any, root: Any
) -> None:
    assert archicad_windows() == []
    # A Mac has a click-through of its own; anything else has none.
    assert click_through(palette.overlay, True) is (sys.platform == "darwin")
    palette._cover()
    assert "works on Windows" in palette.hint.cget("text")
    assert str(palette.hint.cget("style")) == "Refused.TLabel"


def test_every_control_is_explained_where_the_window_explains_things(palette: Any) -> None:
    """The sentence goes to whatever the window hands in -- its card in the
    sidebar -- like every other control's."""
    for control in (palette.open, palette.slider, palette.fit, palette.stretch, palette.cover):
        assert palette.explained.get(str(control)), str(control)
    assert "mouse goes through" in palette.explained[str(palette.lock)]


def test_no_picture_window_is_made_before_there_is_a_picture(palette: Any) -> None:
    """The page is built when the main window opens; the picture's window is
    made the first time there is something to show in it. The slider and
    the fit are kept and given to it then."""
    assert palette._overlay is None
    palette.level.set(40)
    palette._slid()
    palette._mode(STRETCH)
    palette.locked.set(True)
    palette._lock()
    palette._hide()
    assert palette._overlay is None
    assert palette.percent.cget("text") == "40 %"
    assert palette.overlay.opacity == pytest.approx(0.4)
    assert palette.overlay.mode == STRETCH


def test_closing_puts_the_picture_away_and_keeps_the_controls(
    palette: Any, root: Any, photograph: Path
) -> None:
    palette.take(photograph)
    root.update()
    palette.locked.set(True)
    palette._lock()
    palette.close()
    root.update()
    assert not palette.showing
    assert palette.overlay.picture is None
    assert not palette.locked.get() and not palette.overlay.locked
    assert palette.named.cget("text") == "No picture yet."
    assert palette.open.winfo_exists()
