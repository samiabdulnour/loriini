# A reference image over the 3D window

Sometimes a view has to be set up from the angle a photograph was taken
at -- the same corner of the same street, so that the proposal can be shown
in the picture the council already has -- or from an earlier rendering that
has to be matched. Archicad cannot show a picture in its 3D window: Trace
Reference works on the plan, the sections and the elevations, and nothing
in its API draws into the 3D window.

So Loriini puts a window of its own over it: borderless, on top of
everything, showing the picture as see-through as a slider says, and --
on Windows -- letting the mouse fall through it to Archicad. The model is
orbited *through* the picture until the two line up. Nothing is written
into the project; Archicad does not know the picture is there, and it
works over any version of it. This is roadmap item R4; D121 records how it
is built.

## Using it

1. **Press *Reference image***, beside the project picker at the top of
   the window -- or the last button on Loriini's palette in Archicad, which
   starts the window with this already open. A palette opens at the top
   right of the screen and stays on top: a small palette of controls, the
   way Archicad's own palettes float.
2. **Open a picture**: PNG, JPEG, TIFF, BMP, GIF or WebP. A phone's
   photograph is turned the way its orientation tag says. The picture
   appears at half opacity, in a window of its own, over the Archicad
   window that shows the chosen project when one can be found (the whole
   area inside its frame), and otherwise in the middle of the screen at
   three fifths of it. The palette stays where it is.
3. **Place it.** Drag the picture to move it; drag the blue corner at its
   bottom right to size it, and it grows from its top-left corner, which
   stays put. The palette and the picture move on their own: put the
   palette out of the way by its title bar, and the picture stays lined up.
   The palette always stays above the picture, so its controls are never
   covered.
   *Over Archicad* lays the picture over the Archicad window again. Match the frame to the 3D window's
   edges. *Fit* keeps the picture's shape in the frame's top-left corner,
   and the frame's spare margins, to the right or below, are see-through;
   *Stretch* pulls the picture to the frame's shape, for one already
   cropped to the 3D window's own.
4. **Lock it.** The corner and the blue edge go, and the mouse goes through
   the picture to the model -- on Windows and on a Mac alike. Orbit the model in Archicad until it sits in
   the picture, moving the opacity slider as you go: low to see the model,
   high to see the picture. Unlock to move or size the picture again.
5. **Hide** takes the picture off the screen without closing it; **Close**,
   or the palette's own close box, closes both.

## What to know

- **Nothing is written into the project.** The picture is a window of
  Loriini's own, laid over Archicad. Archicad does not see it, and
  neither does a screenshot taken from inside Archicad.
- **It is over everything**, not only over Archicad: alt-tab to another
  program and the picture is still there. Hide it when it is not wanted.
- **One picture at a time.** Pressing the button again raises the palette
  already open. To compare two references, open the second in place of the
  first.
- **The picture is kept at most 4096 pixels on its longer side.** A
  48-megapixel photograph is read and then held at that size, which is
  more than any screen shows and keeps sizing the frame instant.
- **It does not set the camera.** Matching Archicad's projection to a
  photograph by reading the photograph's vanishing lines is the bigger
  thing the roadmap leaves for later; the overlay is the tool for doing
  that by eye, which is most of the value.
- **Off Windows**, the picture, the slider and the fit work wherever Tk
  does, but finding the Archicad window and sending the mouse through the
  picture are Windows calls. The palette says so when asked; the picture
  is placed by hand and hidden to reach what is under it.

## What is not here yet

The overlay has been driven by its tests under a virtual display on
Linux, not yet on a Windows workstation over Archicad. Two things are
done there with Win32 calls made blind, and are the first things to check:

- that a *Fit* frame's spare margins, and a PNG's own transparency, are
  see-through (the colour key Windows is asked to leave out of the
  window);
- that the mouse goes through a locked picture to Archicad (the
  click-through style set on the window Tk wraps every toplevel in).

If the second fails, the lock still takes the corner away, and *Hide*
reaches the model. On a high-DPI display, Tk draws at the scale Windows
gives it and the Archicad window's place is asked and answered in the same
coordinates, so the frame should land where it says; that is the third
thing to check.
