# The area calculation: GBA, GFA and yield from the massing slabs

A massing is modelled in slabs, one per floor, and the first question asked
of it is what it comes to: the areas the planning controls are measured in,
and the number of apartments it holds. Loriini measures the slabs and works
the office's own area calculation from them -- *Area calculation, GFA +
Yield* -- as a sheet in the project, a live workbook, and a table printed in
the run's log. This is roadmap item R3; D122 records how it is built.

## Which slabs count

The slabs that are the massing are chosen the ways the office asked for:

- **By layer.** The slabs on the layers named *residential* are residential
  floor; the slabs on the layers named *non-residential* are any other floor
  (retail, office, a podium). A layer named for both is refused. A slab on a
  layer named for neither is not counted, and the run lists those layers so
  that a forgotten one is seen.
- **By the renovation filter.** With *Only the slabs the renovation filter
  shows* ticked, only what the floor plan's renovation filter shows is
  counted: a massing modelled as *New* over a building that stays counts the
  new floors and not the old. Archicad decides what the filter shows; set it
  on the floor plan before pressing Run.
- **By what is showing.** With no layer named for either use, every slab on
  a layer that is showing counts, as residential: the quick GBA of what is on
  screen. The run says so in yellow, because a structural floor slab on a
  showing layer is counted too.

Loriini's own slabs -- the context model's neighbours and the future
context -- are never counted.

## The arithmetic

Each slab is measured to its edge, the way a massing slab is drawn to the
building's outside face: its outline, less its holes, with every arc counted
as the curve it is, not as the straight line between its ends.

| | Residential | Non-residential |
|---|---|---|
| GBA | the slabs | the slabs |
| GFA | GBA × 0.75 | GBA × 0.9 |
| NSA | GFA × 0.85 | GFA × 0.9 |
| FSR | GFA ÷ site area | GFA ÷ site area |

The four factors are the office's, from its sheet, and every one is a
setting (*Factors and mix* on the Yield page, `--gfa-residential` and the
others on the command line).

The **yield** is the residential NSA over the mix's average unit, rounded
down -- a part of a unit is not a unit -- and split into the mix by the
largest remainder, so that the types always add back up to the total. The
defaults are the office's sheet: 15, 70 and 15 per cent of 1, 2 and 3
bedrooms, at 55, 75 and 95 m² NSA, an average of 75 m². A studio row is on
the page at nothing, for a scheme that has them.

The **site area** and the **target FSR** are typed, or read at the address
on the Site analysis page -- the cadastral lots' area and the LEP's FSR
control -- when they are left blank and an address is there. The target GFA
beside the proposed total is the FSR times the site. The target unit count
is only said beside the yield.

The office's example sheet is reproduced exactly by these defaults, from its
own two GBAs and its site: 112 units, 17, 78 and 17. One thing about that
sheet is worth knowing: its *Non resi.* and *Resi.* rows are the wrong way
round. The rows it labels non-residential were worked with the residential
factors, 0.75 and 0.85, and measure the tower -- the yellow, residential
bulk. Loriini's sheet puts each use's figures on its own row.

## What comes out

**The Area Calculation sheet**, `18 | Area Calculation` in the Layout Book,
on the master chosen in General: the title in two lines, the table of
proposed and target figures, the yield, the notes that say which factors
and sizes the figures were worked with, and a legend. It is remade on every
run.

**The massing beside it.** Name a view in the View Map -- the office's own
3D view of the massing in axonometric, coloured by use with its graphic
override -- in *View beside the table* (`--view`) and it is placed on the
sheet and framed to the page right of the table. A name the View Map does
not have costs the picture and not the sheet; the run says so. The legend's
colours are the office's yellow and lilac, which the override should match.

**The workbook**, `Area calculation.xlsx` in the tables folder (`--xlsx`).
It is live: the site, the targets, the factors and the mix are input cells,
the storeys' measured GBA is the one measured figure, and every other number
is a formula over them. Changing a factor or a share in Excel recalculates
the areas, the FSR and the yield exactly as Loriini would -- the split into
the mix is written out beside it in working columns. This was checked by
LibreOffice Calc recalculating the workbook from nothing (a test does it
wherever Calc is installed).

**The log** prints the slabs counted per layer, what was passed over, the
table and the notes.

## Running it

From the window: the **Yield** tab, tick *Area and yield*, name the layers,
press Run.

From a command line:

```
sun-study yield --residential-layer "05 | Mass.Residential" ^
  --non-residential-layer "05 | Mass.Retail" --renovation-filter ^
  --site-area 1386.78 --target-fsr 8 --target-units 110 ^
  --xlsx "Area calculation.xlsx" --view "Yield Axo"
```

An agent connected to `Loriini.exe mcp` runs the same command through
`run_loriini`.

## What to check first on a workstation

The study has been run against a scripted Archicad and the arithmetic
against the office's sheet, not yet against a live project. The first
things to look at:

1. **A curved slab.** Arcs are counted with Archicad's documented sense --
   an arc angle positive counter-clockwise. Draw a slab with a rounded
   corner (or a circle) and compare the area the run reports with the slab's
   own area in its settings. If they differ by twice the curved part, the
   sense is the other way and it is one sign to change.
2. **The renovation filter.** Tick the box with the floor plan's filter set
   to show the new construction, and check that the slabs counted are the
   new ones.
3. **The view beside the table.** That it is placed, and framed right of the
   table, on the office's own master.
4. **The legend's swatches** are drawn as close lines in the nearest pen to
   the colour; check that they print as the colour on the office's pen set.

## What is not here yet

- **Per building.** The GFA is per use and per storey (the workbook has the
  storeys), not per building; a slab's ID could tell buildings apart.
- **Parking** and any rate-based figure.
- **The external-wall deduction** the LEP's GFA definition implies is inside
  the 0.75 and 0.9 factors, not measured.
- **The Summary of Controls'** PROJECT SUMMARY rows -- residential mix,
  commercial area -- are still left for a person, and could be filled from
  this.
- **Later stages.** When the apartments are Zones, the yield could be
  counted from them rather than worked out from the area.
