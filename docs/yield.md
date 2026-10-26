# The yield analysis: the office's feasibility sheet from the massing slabs

A massing is modelled in slabs, one per floor, and the first question asked
of it is what it comes to: the areas the planning controls are measured in,
the apartments it holds, the parking they need. Loriini measures the slabs
and works the office's own feasibility sheet from them -- *Preliminary
Yield Analysis*, the *Feasibility template* -- as a sheet in the project, a
live workbook in the template's own cells, and a table printed in the run's
log. One option, one sheet; the workbook holds every option side by side.
This is roadmap item R3; D122 and D127 record how it is built.

## Which slabs count, and what they are

The Yield page asks two questions, and shows only the rows the answers need
(D140).

**Slabs** -- which slabs are the massing, and how each one's use is told:

- **Everything showing** (the usual answer). Every slab on a layer that is
  showing, its use told by the level it stands on: the *Retail levels* are
  retail, the *Commercial levels* commercial, every other level
  residential. The run says so in yellow, because a structural floor slab
  on a showing layer is counted too.
- **Chosen layers.** The slabs on the *Layers* chosen, the use told by level
  the same way. An option modelled on one layer -- a podium with a tower on
  it, `01 | Massing - Main Building.3D OPT1` -- is read this way. The run
  prints which level took which use.
- **Layer per use.** The slabs on the *Residential*, *Commercial* and
  *Retail layers* are that kind of floor, whatever level they stand on. A
  layer named for two things is refused; a slab on a layer named for
  nothing is not counted, and the run lists those layers so a forgotten one
  is seen.
- **Layer per option.** Each of the *Option layers* is one whole option, a
  sheet and a workbook page each, named after its OPT number, the use told
  by level.

A row the answer does not show sends nothing, so a layer left in it cannot
change what is counted. The command line still takes any of these together
(`--massing-layer`, `--residential-layer` and the others).

**Renovation** -- which slabs count by their renovation status:

- **Any** (the default): every slab, whatever its status.
- **New only**: the slabs whose own *Renovation Status* is New -- a massing
  modelled as New over a building that stays counts the new floors only.
- **Existing and new**: every slab but those To Be Demolished.
- **Floor plan's filter**: what the floor plan's renovation filter shows,
  set on the floor plan before pressing Run.

The first three are read off each slab's built-in *Renovation Status*
(`--renovation-status new` or `existing-and-new`), so nothing has to be set
on the floor plan first, and the run counts what it left out under each
status. A status in a language it does not know is reported and left out,
never guessed; English, German and French are known. The last is Archicad's
own filter (`--renovation-filter`).

Loriini's own slabs -- the context model's neighbours and the future
context -- are never counted.

## Levels

The sheet's storey table is by level, and a massing's slabs say where they
are by their height, not by their home storey: a stack of storey-thick
slabs is usually homed on the ground storey and offset up. So each slab's
underside is worked from its reference plane, the offset of its top and its
thickness, and slabs whose undersides are within half a metre of each other
are one level. The levels are named up from the ground -- *Ground Floor*,
*Level 01*, *Level 02*; *B 01* below it -- the ground being the level
nearest the project's storey called *Ground* (or *GF*, or *Level 00*), or
the lowest level when no storey is named so; the run says which. A level's
floor-to-floor is the rise to the level above; the top level's is its own
slab's thickness when the slabs are storey-thick, and otherwise the rise
below it.

The *Retail levels* and *Commercial levels* are ticked on the Yield page
from the levels a massing can have, or typed on the command line as the run
names them: `Ground`, `Level 01`, `L2`, `3`, `B 01`. Every option in a run
stands in one grid of levels, so a tower option with no ground floor of its
own still starts above the podium option's ground.

## The arithmetic

Each slab is measured to its edge, the way a massing slab is drawn to the
building's outside face: its outline, less its holes, with every arc counted
as the curve it is. That is its **BEA**, the built envelope area. From it,
by the template's *Building Efficiencies*, which the run follows to the
letter and keeps as its defaults:

| | Residential | Commercial | Retail |
|---|---|---|---|
| BEA to GFA | 0.725 | 0.85 | 0.95 |
| GFA to NLA | 0.85 | 0.9 | 0.9 |

- **GFA** is the BEA by *BEA to GFA*; **NLA** is the GFA by *GFA to NLA*.
- **FSR** is each use's GFA over the site, against the permissible FSR the
  sheet splits by use, and the difference. The permissible is typed per use
  (*Permissible FSR, residential* and the others, `--fsr-residential`); left
  blank, the LEP's one FSR is read at the address and written on the
  residential row with a note, to be split in the workbook.
- **Units.** The residential GFA over the *average GFA* of a unit: the
  mix's average NLA -- its sizes by their shares, plus *common areas per
  unit* and a *unit size tolerance* -- over the residential GFA to NLA. The
  units are shared into the mix by its shares, market and affordable apart
  by the *affordable share* of the residential GFA. The sheet does not
  round -- 44.1 units is what it says -- and nor does the run. The units
  the *permissible* residential GFA would hold stand beside them.
- **Parking.** Each type's units by its spaces per unit under the SEPP and
  the DCP, the visitors over every unit, the commercial and retail GFA by a
  space per so many square metres; the total, and the **basements** it
  takes at so many square metres a space over the share of the site a
  basement may cover.
- **Storeys.** The levels with residential floor on them, and the levels
  with floor and none of it residential (the podium).

The mix the sheet opens with is the template's: Studio, 1-bed, 2-bed,
3-bed and 4-bed at 0, 20, 70, 10 and 0 per cent of 35, 50, 75, 100 and 120
m² NLA (the affordable 3-bed at 95), an average NLA of 72.5 m². The parking
rates are the template's too: 0.5, 0.5, 1, 1.5 and 1.5 spaces a unit under
the SEPP, 0.5, 0.5, 1, 1 and 1 under the DCP, 0.1 a unit for visitors, one
space per 100 m² of commercial GFA and per 30 m² of retail under the SEPP
and per 400 m² under the DCP, 40 m² a space, a basement over 40 per cent of
the site. Every one is a setting, on the Yield page or the command line,
and every one is an input cell in the workbook.

The template's own *Option 01* is reproduced exactly by these defaults from
its storey table and its site: 18,813.75 m² of residential GFA, 220.575
units at 44.1, 154.4 and 22.1, 333.0 parking spaces and 4.97 basements.

## What comes out

**The Yield Analysis sheet**, `Yield | Yield Analysis - Option 01` in the
Layout Book, on the master chosen in General: the title and the option's
name, the site, the FSR and GFA by use against the permissible, the unit
mix, the storeys, the parking, the notes that say which efficiencies the
figures were worked with, and a legend. Each option has a sheet of its own;
a run of the same option remakes it.

**The massing beside it.** Name a view in the View Map -- the office's own
3D view of the massing in axonometric, coloured by use with its graphic
override -- in *View beside the table* (`--view`) and it is placed on the
sheet and framed to the page right of the table. A name the View Map does
not have costs the picture and not the sheet; the run says so.

**The workbook**, `Preliminary Yield Analysis.xlsx` in the tables folder
(`--xlsx`), is the office's template, filled, in the template's own look --
its style table, its theme, its column widths and row heights, its green
bars and boxed blocks, carried over cell for cell from the template by
`scripts/extract_feasibility_style.py` into `report/feasibility_style.py`,
to be run again when the office changes the template -- the site in C6, the
permissible FSR in C10:C12, the proposed GFA in D17:D19, the unit mixes in
rows 29 to 43, the parking from row 60, the efficiencies in C86:E88, and
the storey table from J113 -- with the levels' BEA by use in red as the
template has its inputs, and every other figure a formula over them, so a
what-if on an efficiency, a share, a rate or a level's use is typed into
Excel rather than rerun. The columns the template fills by hand -- the
units per level, the ADG cross-ventilation and solar counts -- are left
empty for the office to fill. One sheet per option: a run adds its option
beside the ones already in the workbook (it keeps each option's data on a
hidden sheet to do so), and a run of the same option name replaces that
sheet. A workbook Loriini did not write is left alone, and the run says so.

**The log** prints the slabs counted per layer, the levels and their uses,
what was passed over, the storey table, the sheet's table and the notes.

## Running it

From the window: the **Yield** tab, tick *Yield analysis*, name the option
and the layers, press Run. Run again with another option name and the
other option's layers for the second sheet.

From a command line, the Darlinghurst options on 8 October 2026:

```
sun-study yield --option "Option 01" ^
  --massing-layer "01 | Massing - Main Building.3D OPT1" ^
  --retail-level Ground --commercial-level "Level 01" ^
  --address "91-109 Riley St, Darlinghurst NSW 2010" ^
  --xlsx "Preliminary Yield Analysis.xlsx" --master-layout "DA A1 - VERTICAL - No Scale"
sun-study yield --option "Option 02" ^
  --massing-layer "01 | Massing - Main Building.3D OPT2" ^
  --retail-level Ground --commercial-level "Level 01" ^
  --address "91-109 Riley St, Darlinghurst NSW 2010" ^
  --xlsx "Preliminary Yield Analysis.xlsx" --master-layout "DA A1 - VERTICAL - No Scale"
```

`--residential-layer`, `--commercial-layer` and `--retail-layer` name a
layer per use instead; `--fsr-residential`, `--fsr-commercial` and
`--fsr-retail` split the permissible FSR; `--unit` and `--affordable-unit`
set the mixes, `--affordable-share` the split, `--common-area` and
`--size-tolerance` the allowances on the average; `--parking-rate`,
`--affordable-parking-rate`, `--sqm-per-space` and `--basement-site-ratio`
the parking. An agent connected to `Loriini.exe mcp` runs the same command
through `run_loriini`.

## Several options at once

Each option in the project is usually its own layer. Name them all with
`--option-layer` -- or tick them in *Option layers* on the Yield page -- and
one run reads the slabs once and makes every option: a sheet in the
workbook and a layout each, with the site, the permissible FSR, the
efficiencies and the levels named retail and commercial shared between
them, and a line per option at the foot of the log comparing GFA, FSR,
units and parking. An option is named after its layer's OPT number
(`...3D OPT1` is *Option 01*), or as `Option 02=<layer>`:

```
sun-study yield --option-layer "01 | Massing - Main Building.3D OPT1" ^
  --option-layer "01 | Massing - Main Building.3D OPT2" ^
  --retail-level Ground --commercial-level "Level 01" ^
  --address "91-109 Riley St, Darlinghurst NSW 2010" ^
  --xlsx "Preliminary Yield Analysis.xlsx" --master-layout "DA A1 - VERTICAL - No Scale"
```

The workbook is ticked on the Yield page (*Excel workbook: Preliminary
Yield Analysis*) and goes to the tables folder, or to the path typed under
*Workbook*.

## What to check first on a workstation

1. **A curved slab.** Arcs are counted with Archicad's documented sense --
   an arc angle positive counter-clockwise. Draw a slab with a rounded
   corner and compare the area the run reports with the slab's own area in
   its settings.
2. **The levels.** That the run's levels are the massing's floors, named
   as the office would name them, and that the ground is the right level:
   a massing whose ground floor sits well below the project's ground storey
   is still the ground, being the level nearest it.
3. **The use by level.** That the levels named retail and commercial are
   the ones meant; a level moved from one use to another is also one number
   moved between columns in the workbook's storey table.
4. **The view beside the table.** That it is placed, and framed right of
   the table, on the office's own master.

## What is not here yet

- **Per building.** A level's BEA is the sum of every slab on it; two
  towers on one level are one row.
- **The units per level, and the ADG counts** -- the *proof of concept*
  columns the template fills by hand -- are left for a person, as they are
  in the template; when the apartments are Zones they could be counted.
- **Height controls.** The storey table's heights are tallied but not yet
  set against the LEP's height of buildings.
