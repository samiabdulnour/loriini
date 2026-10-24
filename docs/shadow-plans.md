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

## The comparison: the stack

A document shows one scenario's whole shadow. Two documents show the split,
stacked. A drawing on a layout is clear wherever it draws nothing, so a
document of what stands laid over a document of what stands plus the
proposal shows the existing shadow in the upper document's pen and, wherever
only the proposal casts, the proposal's pen through the gaps. Archicad casts
both; nothing is measured or traced, which is what the fills route does and
what the office found not precise enough on the model it tried it on.

```
sun-study shadow-plans --layer-combination "04 | Shadow Diagrams" ^
  --existing "03 | Site Context.Buildings" ^
  --proposed "20 | Massing.SEARs" ^
  --proposed "20 | Massing.Envelope,20 | Massing.Podium"
```

`--existing` names the layers of what already stands, the neighbours,
repeatable; `--proposed` names one proposal's layers, comma separated, and is
repeated once per proposal. The proposals are called **Proposed 1, Proposed
2** and on in the order given -- **Proposed** alone when there is one --
whatever the office calls them this week, and the existing set **Existing**.
Any `--label` is set aside.

A run then makes, from the base combination:

- **a layer combination per set**, `15 | Shadow Plans Existing` with the
  existing layers on and every proposal's off, and `15 | Shadow Plans
  Proposed 1` with the existing and its own on and the other proposals' off.
  The ground and the rest keep the state the base gives them, and the site
  context the plain mode switches on is switched on here the same way;
- **a document per set and hour**, `15 | Shadow Plan Existing 21 Jun 09:00`,
  `15 | Shadow Plan Proposed 1 21 Jun 09:00`, each with two things forced:
  its shadows solid in its own pen (`Solid Fill` when the project has it,
  `--shadow-fill` otherwise; a hatch would let the pen beneath show between
  its lines), and its **uncut surfaces unfilled**, so a roof or the terrain is
  an outline and the drawing beneath shows through. The pens are
  `--existing-pen` and one `--proposed-pen` per proposal; left out, they are
  matched by colour against the project's pen table as the fills' legend rows
  are -- the existing shadow in the legend's grey, a single proposal in its
  blue, several up the blue ramp in order;
- **sheets per proposal**, `15 | Shadow Plans Proposed 1 - JUNE 21`, dealt as
  a labelled set's are, with **two drawings in every cell**: the proposal's,
  `JUNE 21 -9AM PROPOSED 1`, and over it the existing set's, `JUNE 21 -9AM
  EXISTING`, both with their origin at the cell's centre and clipped to it.
  The add-on brings them to the front in that order (`ArrangeDrawings`,
  `stack`). The existing documents are made once and lie over every proposal.

The existing document on top rather than under, because that is what makes
the split: where the existing shadow falls its pen covers whatever the
proposal cast there, and what is left of the proposal's pen is exactly the
shadow the proposal adds. The other way up the proposal's pen would cover
everything, since its combination casts the existing shadow too.

From the agent, `shadow_plans` takes `existing`, `proposals` -- a list of
layers per proposal -- `existing_pen` and `proposed_pens`.

### Two sets side by side

The older comparison remains: run the set twice, under two layer
combinations, with a **set name** for each --

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

**Whose clock the hours are in.** Archicad reads a sun date in the project
location's own time zone -- the one set beside the latitude and longitude in
Project Location -- and not in the `--timezone` the hours were asked for. The
add-on reports that zone (`GetPlace`), and the run hands each hour over in
Archicad's clock and prints what it did: on a project keeping UTC+3 with
hours asked for in Asia/Dubai, *09:00 as 08:00*; on an AEST project with
Sydney hours, *handed over as they are*. An add-on built before `GetPlace`
cannot say what the clock is, the hour then goes over as the asked-for
wall-clock, and the run says so; check one document against the altitude
printed beside it ([D135](decisions.md)).

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

Built against the Archicad 26 kit, run live on the Redfern project (8
October, Windows) and on the Graphisoft sample project in Archicad 30 on a
Mac (24 October, [D135](decisions.md)). Of the list below, 1 and 2 hold on
both, and the second run and the stacked run both complete; 3 found the hour
out by the project's time zone on the sample project, which is what
`GetPlace` and the clock line in the run's output now answer; 4 to 7 are
still to be read on a workstation. In order:

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
6. **The stack shows through.** On a stacked sheet, open one cell: the
   proposal's roof and shadow must be visible under the existing document
   wherever the existing shadow does not fall. If the upper drawing blanks
   the page under it, its uncut surfaces are still filled -- open the
   document's settings, Model Display, and check *Uncut Surfaces*; the
   add-on writes `shouldUseUncutSurfaceFill` and answers what it read back
   as `fillUncutSurfaces`. If the proposal's pen shows *through* the
   existing shadow, the shadow fill is a hatch: name a solid with
   `--shadow-fill`.
7. **The order.** The existing drawing lies over the proposal's. If the sheet
   shows the proposal's pen everywhere, the add-on's bring-to-front did not
   take; select the existing drawing and *Bring to Front* by hand, and note
   the `failures` the run printed from `ArrangeDrawings`.

## What is not here yet

- **The legend and the site outline on the sheets.** The drawings carry
  their captions; a legend saying *shadow at the hour shown* and the site
  boundary drawn over each drawing are the next step.
- **Shadows on a single level.** The 3D window's style can cast vectorial
  shadows onto one level instead of onto every surface; a document's settings
  expose no such choice through the kit, so the plans need the ground in the
  model.
