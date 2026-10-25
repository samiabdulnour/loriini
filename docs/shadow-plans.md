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

A document shows one scenario's whole shadow. A stack of documents shows the
split, one per row of the shadow legend -- the same rows as the fills', from
the same words -- and every row of an hour laid in one cell of one sheet.
Archicad casts every shadow; nothing is measured or traced.

```
sun-study shadow-plans --layer-combination "04 | Shadow Diagrams" ^
  --shadow-source "EXISTING=03 | Site Context.Buildings" ^
  --shadow-source "FUTURE=03 | Site Context.Future" ^
  --shadow-scenario "TOD=20 | Massing.TOD" ^
  --shadow-scenario "PROPOSED=20 | Massing.Envelope,20 | Massing.Podium"
```

`--shadow-source` is a row that stands -- existing neighbours, future
neighbours, existing structures on the site -- and these **accumulate**: each
is drawn only where the ones named before it cast nothing. `--shadow-scenario`
is a row that might be built -- the TOD envelope, the SEARs height, the
proposal -- **compared**: each is cast against every source and against no
other scenario, so two scenarios overlap, the last named on top. The words
before `=` are the legend's (`EXISTING`, `FUTURE`, `EXISTING ON SITE`, `TOD`,
`SEARS`, `ADG ENVELOPE`, `PROPOSED`, or the sheet's longer words), which is
what picks each row's colour; any other word takes the next grey for a source
or the next blue for a scenario. The layers after it are comma separated.

The short way for one row that stands and the proposals still works:
`--existing` names what stands, `--proposed` one proposal's layers and is
repeated per proposal (**Existing**, **Proposed 1**, **Proposed 2**), with
`--existing-pen` and `--proposed-pen`. The two ways do not mix. Any `--label`
is set aside.

From the window, the rows are the **Shadow diagram** page's own legend rows:
choose layers for them once and the **Shadow plans** box stacks them, so the
fills and the documents of one project are drawn from one legend.

A run then makes, from the base combination:

- **a layer combination per row**, `15 | Shadow Plans EXISTING`: a source
  shows its own layers and every earlier source's, a scenario every source's
  and its own, and each hides the other rows' layers. The ground and the rest
  keep the state the base gives them, and the site context the plain mode
  switches on is switched on here the same way;
- **a document per row and hour**, `15 | Shadow Plan EXISTING 21 Jun 09:00`,
  its shadows solid in the row's pen (`Solid Fill` when the project has it,
  `--shadow-fill` otherwise), and its **uncut surfaces filled in the
  transparent pen**: filled, because Archicad draws a document's shadows on
  filled surfaces and on nothing else ([D141](decisions.md)), and in pen 0,
  so the surfaces themselves draw nothing and the documents beneath show
  ([D142](decisions.md)). Every document, the lowest too: filled with the
  materials' own colours, Archicad draws a shadow as the material shaded
  darker and ignores the shadow's pen. The pens are matched by colour
  against the project's pen table, as the fills' rows are;
- **one combined sheet set**, `15 | Shadow Plans Combined - JUNE 21`, dealt
  as a labelled set's is, with **every row's drawing in each cell**, their
  origins at the cell's centre and clipped to it, laid bottom to top as the
  scenarios in the order named and then the sources from the last to the
  first. The add-on brings them to the front in that order, gives every
  drawing above the lowest a transparent background (`ArrangeDrawings`), and
  every drawing is then redrawn (Tapir's `UpdateDrawings`), since a drawing
  of a 3D Document keeps showing what its document was until it is;
- **one title per cell** ([D148](decisions.md)): the top drawing is named
  for the hour alone (`JUNE 21 -9AM`) and keeps its title; the ones under it
  are named for the hour and the row (`JUNE 21 -9AM TOD`), since a sheet
  finds its drawings by name, and are given no title and left out of the
  sheet's drawing numbering, so the titles that remain count 1, 2, 3;
- **the whole site in every cell** ([D143](decisions.md)): the run measures
  the plan extent of the model elements the rows' combinations show and puts
  each drawing's origin where that window's centre lands in the middle of
  its cell. With no `--scale`, the plans are drawn at the largest standard
  scale at which the window fits a cell of the master, and the cells are
  dealt by the window's shape -- three hours of a square site are two by two,
  not three tall strips. On the sample project, 421 m square on an A1: 1:2000;
- **the legend's colours, exactly**: the run makes its own pen set, `15 |
  Shadow Plans`, a copy of the one the drawings print in (the model's active
  table, or `--pen-set`) with each row's pen -- the nearest it has -- set to
  the legend's colour, and every drawing on the sheet prints in it. A drawing
  of a 3D Document prints in the model's active pen table, not in the pen set
  its view pins, so it is the drawing that is told. A pen given with
  `--existing-pen` or `--proposed-pen` keeps its own colour. Archicad before
  27 cannot make a pen set, and the rows keep the nearest pens, as the run
  says;
- **the legend and the site on the sheet**: in the column left of the title
  block, which the cells keep clear of, *SHADOW LEGEND* and a swatch per row
  in the colour the drawings print it in, with the legend's words; and the
  boundary layer's outlines (a layer whose name mentions a boundary: its
  slabs, fills or polylines) drawn in red over every plan. They go on
  Archicad's own layer, which nothing hides, are raised to the top display
  level so the outline lies over the plans, and are cleared and redrawn on
  every run -- the combined sheet's texts and fills are the run's own.

Why that order makes the split: a document draws the whole shadow of what it
shows, and on the sheet a drawing is seen only where everything above it
casts nothing. The first source is on top, so its whole shadow is in its
colour; the second source's document is seen only where the first casts
nothing -- what it adds; the scenarios lie under every source, so what is
seen of each is the ground it shades that no source does, the last named
over the earlier where two overlap. That is the fills' legend, with the
subtraction done by the order on the sheet.

**Five rows, 25 October 2026** ([D144](decisions.md)), the same project:
`EXISTING` the neighbours and `FUTURE` the layer `SHADOW 2` as sources,
`TOD` (`SHADOW 3`), `SEARS` (`SHADOW 4`) and `PROPOSED` the tower as
scenarios -- fifteen documents and one A1 at 1:2000 in 49 s, each row in
the legend's own colour through the run's pen set, stacked TOD < SEARS <
PROPOSED < FUTURE < EXISTING. This is the main route for any diagram that
involves the neighbours; the fills route is kept for the design's own
every-hour drawing (`sun-study shadows --shadow-all-hours-only`).

**Run live on 24 October 2026** on the Graphisoft sample project in
Archicad 30 ([D142](decisions.md)): the existing neighbours as a source, the
tower as the proposal, 21 June at 9, 12 and 3 on one A1 sheet. Six documents
and the sheet in 18 s, a rerun in 12 s; the neighbours' shadow in its pen
everywhere, and only the ground the tower adds in the proposal's -- to the
south-west at 9, south at noon, south-east at 3.

From the agent, `shadow_plans` takes `sources` and `scenarios` as
`shadow_diagrams` does, or `existing`, `proposals`, `existing_pen` and
`proposed_pens`.

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
choose the layer combination and a pen set, and press Run. With layers chosen
for the page's legend rows it makes the stack and the combined sheets; with
none, one set, which a set name and a shadow pen can be given. A floor plan
tab must be in front in Archicad when it runs.

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
Mac (24 October, [D135](decisions.md), [D142](decisions.md)). Of the list
below, 1 and 2 hold on both; 3 found the hour out by the project's time zone
on the sample project, which `GetPlace` and the clock line in the run's
output now answer; 6 and 7 hold on the sample project's combined sheet; 4
and 5 are still to be read. In order:

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
6. **The stack shows through.** On a combined sheet, every row's colour must
   show where it adds and nowhere else. If an upper drawing blanks the page
   under it, its document's uncut surfaces are not in the transparent pen --
   open the document's settings, Model Display, *Uncut Surfaces*: filled,
   uniform pen colour, pen 0; the add-on answers what it read back as
   `uncutSurfaces`. If a row's shadow is a darker shade of grey rather than
   its pen, the document is on the materials' colours. If one row's pen
   shows *through* another's shadow, the shadow fill is a hatch: name a
   solid with `--shadow-fill`.
7. **The order.** Bottom to top, scenarios then sources from the last to the
   first. If the sheet shows a scenario's pen everywhere, the add-on's
   bring-to-front did not take; select the source drawings and *Bring to
   Front* by hand, and note the `failures` the run printed from
   `ArrangeDrawings`.

## What is not here yet

- **A legend on the plain set's sheets.** The combined sheets carry one; a
  plain set, one colour, does not, though its sheets are fitted the same way.
- **Shadows on a single level.** The 3D window's style can cast vectorial
  shadows onto one level instead of onto every surface; a document's settings
  expose no such choice through the kit, so the plans need the ground in the
  model.
