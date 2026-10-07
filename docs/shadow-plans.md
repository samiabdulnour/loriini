# Shadow plans: the hours as 3D Documents, with Archicad's own shadows

The shadow diagram Loriini draws itself -- the model exported, the shadows
cast by its own ray caster, and what stands and what the proposal adds drawn
as fills in the legend's colours -- is the argument a DA makes. **Shadow
plans** are the other way to draw the same hours: a 3D Document per hour,
looking straight down, with the sun at that hour and Archicad's own vectorial
sun shadows on. Archicad casts the shadows, from the sun it works out from
the project's location, at any size of model it can display. This is the
second half of roadmap R1; D123 records how it is built.

| | Shadow diagram (fills) | Shadow plans (3D Documents) |
|---|---|---|
| Who casts the shadow | Loriini's ray caster | Archicad |
| What a drawing shows | each legend row in its colour: existing, future, proposed, and the split between them | the whole shadow of what the layer combination shows |
| The areas | measured, in the log and the schedule | none |
| A larger model | limited by the caster's time and memory ([`larger-models.md`](larger-models.md)) | whatever Archicad can display |
| Where it goes | fills on the plan, one layer an hour, views and sheets | documents, views and sheets |

So the two answer different questions, and the office may want both: the
documents as the record, the fills as the argument.

## What a run makes

For every day and hour asked -- the shadow diagram's own days and hours, so
the two routes draw the same instants under the same names:

- **a 3D Document**, `15 | Shadow Plan 21 Jun 09:00`, reference `SP0621-0900`,
  looking straight down with the project's +Y up the page (the add-on snaps a
  straight-down camera to the plan's orientation), its sun set to that date
  and hour so Archicad computes it, and its vectorial sun shadows switched on
  as it is made, in the fill asked for;
- **a view of it** in the View Map folder `15 | Shadow Plans`, pinned to the
  layer combination, the renovation filter (by default the one most of the
  project's views carry, its planned state), the pen set and the scale --
  1:1000, as the fills' sheets are;
- **sheets by day**, `15 | Shadow Plans - JUNE 21`, split as the Sheets row
  in General says, each drawing captioned as the fills' are -- `JUNE 21 -9AM`
  -- with its origin at the centre of its cell and its frame clipped to it.

An hour with the sun below the horizon is said and skipped. The storey
filter is taken off the 3D window before any document is made and off every
document after, since a document keeps the filter it was made under (D98).

**The ground must be in the layer combination.** Everything the plan shows
casts a shadow and catches one; with no terrain mesh or site slab under the
buildings, the shadows have nothing to fall on and the plan shows roofs on a
blank page. The first live run (Redfern, 8 October 2026) showed exactly that:
the office's `04 | Shadow Diagrams` hides the layers the site tools draw the
context on, so the documents held the proposal's slab and nothing else. So
the run looks: when the project has the site tools' context layers --
`03 | Site Context.Terrain`, `.Roads`, `.Buildings`, `.Future buildings` --
and the combination hides any of them, the plans pin a combination of their
own, `15 | Shadow Plans`, which is the named one with those switched on, and
the log says so. `--no-site-context` leaves the combination alone;
`--require-layer` adds any other layer the same way.

**The shadows' fill** is the office's `50 %` when the project has it, which
is what its own hour documents are drawn in; the project's 3D Document
default on the same file was a brick hatch on the mark-up pen, which showed
as no shadow at all. `--shadow-fill` names another, `--shadow-fill none`
keeps the project's default, and `--shadow-pen` and `--shadow-background-pen`
set the pens.

## The comparison: two sets

A document shows one scenario's whole shadow, and layouts do not composite
drawings. The comparison is made the way the office made it by hand: run the
set twice, under two layer combinations, with a **set name** for each --

```
sun-study shadow-plans --layer-combination "04 | Shadow - Existing" --label Existing
sun-study shadow-plans --layer-combination "04 | Shadow - Proposed" --label Proposed
```

-- and the Project Map and the Layout Book hold both, `15 | Shadow Plans
Existing - JUNE 21` beside `15 | Shadow Plans Proposed - JUNE 21`, to be read
against each other.

## Running it

From the window: the **Shadow diagram** tab, the **Shadow plans** box under
the days. It draws the days lit and the hours ticked above it. Tick it,
choose the layer combination, optionally a set name, a pen set and the pen
the shadows are filled in, and press Run. A floor plan tab must be in front
in Archicad when it runs.

From a command line:

```
sun-study shadow-plans --shadow-date 06-21 --shadow-hour 9,10,11,12,13,14,15 ^
  --layer-combination "04 | Shadow Diagrams" --shadow-pen 3 --subset "SHADOW DIAGRAMS"
```

`--shadow-fill "Solid Fill"`, `--shadow-background-pen` and
`--shadow-contours` set the rest of the shadows' look; anything left out
keeps the project's own defaults for new 3D Documents. An agent connected to
`Loriini.exe mcp` has the same as its `shadow_plans` tool.

## A second run

A 3D Document cannot be deleted through the API, so a second run over the
same hours finds the first run's documents by their names. It re-aims them,
sets their sun and fill again, and copies the shadow switch onto them from a
document it has just made with it (`SetDocumentFrom3D`), so a rerun leaves
what a first run would. When every document was already there, there is
nothing fresh to copy the switch from, and the run says so: delete one
document in the Project Map and run again to have it remade. Sheets are
remade every run; an earlier sheet of the set that this run is not remaking
is removed.

## What to check first on a workstation

Built against the Archicad 26 kit and tested against a scripted Archicad,
not yet a live project. In order:

1. **The shadows are on.** Open one document. If it shows the plan with no
   shadows, the defaults switch did not reach it: open the document's
   settings, tick *Vectorial Sun Shadows* by hand, and note the `effects3D`
   the run's log printed for it -- that number, compared with the same
   document's after the tick, is the bit to set.
2. **It is a plan, north up.** The documents should read exactly as the site
   plan does. A document turned, or seen from slightly off vertical, says the
   overhead snap in the add-on needs the *Top* preset rather than a free
   axonometry.
3. **The sun is Archicad's and agrees with the fills.** The run prints this
   tool's sun altitude beside each document; at 9am on 21 June in Sydney a
   shadow runs about three times the height that casts it. Compared with the
   fills for the same hour, the outlines should coincide.
4. **The defaults came back.** Make a 3D Document by hand after a run: it
   should have whatever *Vectorial Sun Shadows* setting the project had
   before, since the run puts the defaults back after each document.
5. **The fill.** With `--shadow-pen` given, the shadows are in that pen.

## What is not here yet

- **The legend and the site outline on the sheets.** The drawings carry
  their captions; a legend saying *shadow at the hour shown* and the site
  boundary drawn over each drawing are the next step.
- **Shadows on a single level.** The 3D window's style can cast vectorial
  shadows onto one level instead of onto every surface; a document's settings
  expose no such choice through the kit, so the plans need the ground in the
  model.
