# Site and context analysis

Give it a NSW street address; it makes what an office prepares when a DA
starts -- the **Context Analysis** and **Site Analysis** sheets as worksheets
with views and layouts, the **Summary of Controls** straight onto a layout,
and the **Context Model** in 3D -- in the open Archicad project, as native
fills, polylines, texts, meshes and slabs, from open data. No site visit, no
screenshots, nothing traced. These are the **Site tools**; the **Solar tools**
(solar analysis, shadow diagram, sun views) are the other half of the program,
see `docs/restructure.md`.

Ported from the office's `au-site-analysis` generator, endpoint for endpoint
and rule for rule, so the two agree about where every line comes from. That
generator prints an A1 PDF and a DXF; this draws the same content where the
office works, at true ground scale, in the project's own frame.

---

## What it makes

Everything under the tool's prefix (`14 |` unless told otherwise), so it can
be found, switched off or purged as a group.

| | |
|---|---|
| `14 \| Context Analysis` worksheet | LEP zoning wash coloured by the office's categories; schools, hospitals, child care and retail coloured by what they are and labelled by name; heritage items; the rail corridor; cadastre; roads with names on a double-headed arrow (a lane gets a plain label); railway, tram and bus routes; `T`, `L` and `B` roundels for stations and stops; 5 and 10 minute walking catchments; the site on top; a legend of what is on the map |
| `14 \| Site Analysis` worksheet | the boundary with a circle at each survey corner, `SB` dimensions per edge and `RL` levels per corner, read across the slope between the contours; the fall arrow, `FALL` and `AREA`; contours with their levels -- the City of Sydney's 1 m ones where its area covers the sheet, the state's 2 m ones elsewhere, and the legend says which; neighbours as number, storeys and zone; trees the size of their canopy, dashed where nobody recorded one; poles, lamps, hydrants; driveways as access triangles; kerbside parking bands; one-way and lane arrows; noise zigzags along main roads and rail; utilities where OSM has them; OSM building footprints; the sun path with winter and summer discs; prevailing wind banners; a legend |
| `14 \| Summary of Controls` **layout** | the planning-controls table, drawn straight onto a sheet of its own on the A1 master: address, lots, cadastral area; LEP zone, height, FSR and the GFA it allows, minimum lot size, heritage; council DCP rows ruled up empty; the ADG figures worked for this site area. No worksheet, no view, no layer of its own |
| `14 \| Context Analysis.*`, `14 \| Site Analysis.*` layers | five per sheet (aerial, fills, lines, labels, sheet), every fill with an element ID naming its legend entry |
| `14 \| Context Analysis`, `14 \| Site Analysis` **layouts** | each worksheet's view on a sheet of its own, the map field centred on the site beside the title block, and the sheet's **legend drawn on the layout** in the column to the right of the map, above the title block -- not in the worksheet. Without a layout (`--no-layout`, or no master to put one on) the legend stays in the worksheet beside the map, so it is never on neither |
| `14 \| Site Analysis` view folder | a view of each worksheet at its sheet's scale -- 1:3000 for the context sheet, whichever of 1:200 to 1:750 fits the site for the site sheet -- with a layer combination showing that drawing's layers |
| `<run folder>/data/*.json` | everything fetched, so the sheets can be redrawn without the internet, or into another project |

Texts are millimetres on paper and keep that size in any view, so the sheet
prints at its scale whatever the worksheet's own scale is. Symbols -- the
stop roundels, the sun discs, the corner circles -- are geometry sized for
the sheet's scale.

## Running it

From the window: the **Site analysis** tab, an address, the three sheets
ticked, Run. From the command line:

```
sun-study site "26-30 Campsie St, Campsie NSW 2194" --port 19723
```

Options worth knowing:

| | |
|---|---|
| `--no-context`, `--no-site`, `--no-summary` | leave a sheet out |
| `--scale 2000` | the context sheet's scale; sets how much neighbourhood is fetched |
| `--site-scale 300` | pin the site sheet's scale instead of fitting |
| `--anchor site` | put a point of the site at the project origin (see below); the default for a project whose location was never set |
| `--origin-at bottom-left` | with `--anchor site`: that corner of the site is the origin (`bottom-right`, `top-left`, `top-right`, or `centre`); `bottom-left` by default |
| `--master-layout NAME` | the master the sheets go on; without it you are asked, from the project's own masters |
| `--square-to-site` | with `--anchor site`: turn the site so its longest boundary runs level, and write the project's north to match |
| `--no-aerial` | leave the SIX orthophoto out; by default it is fetched, placed under both sheets and saved as JPEG tiles with world files |
| `--fetch-only` | fetch and save; touch nothing in Archicad |
| `--from <folder>` | draw the bundles saved in that folder's `data/`; no fetch |
| `--out <folder>` | where to save; `Documents\Loriini\site-analysis\<address>` by default |
| `--no-layout` | leave the sheets off the A1 master (`--master-layout` picks another) |
| `--set-location` / `--keep-location` | write the site's lat/lon and MGA survey point into Project Location; the default with `--anchor site`, on a city preset, or after a fit, and `--keep-location` leaves it |
| `--model` | terrain mesh, street blocks and neighbour slabs, a layer each (below) |
| `--model-radius 500` | how far each way the model reaches; `0` keeps to the site sheet's extent |
| `--fit-layer auto` | fit the fetched lot onto the boundary drawn on this layer (below); `none` skips it |
| `--north grid` | the project's north angle is an MGA grid bearing from the survey, not a true one |
| `--theme flamingo` | the context sheet's house style: `flamingo`, `kingfisher`, `heron`, `canary` or `oatley` (below) |
| `--site-theme heron` | the site sheet's: `heron`, `kingfisher`, `flamingo`, `canary` or `oatley` |

Needs the Loriini add-on beside Tapir. A worksheet can only be drawn into in
the session that made it if the add-on's own `CreateWorksheet` made it and
entered it (D33), and the fills carry the legend's own RGB through
`CreateFills` (D82).

Put `TFNSW_API_KEY=...` in the environment for authoritative bus stops; free
from opendata.transport.nsw.gov.au. Without it the stops come from
OpenStreetMap along with the routes.

## Themes

A theme is how a sheet looks -- the land-use palette, the inks, the line
styles, which marks stand for the sun and the winds. What a sheet says is
the same in every theme. They are the generator's four, ported colour for
colour from its `src/render/template.ts` into `sun_study.site.theme`, and a
fifth, **Oatley**, which is the office's own legend these sheets were first
drawn in, so a saved run still draws what it drew. The context sheet takes
`--theme`, the site sheet `--site-theme`; the window's Site analysis page
has a *Context style* and a *Site style* row. Flamingo and Heron are the
defaults, as the generator's are.

The generator prints to a PDF, where a tint has an opacity and a texture is
a pattern. Archicad has neither on a fill, so each is realised as what
Archicad does have, and that is the whole of the port (D137):

- a tint **on paper** is the colour laid over white before it is sent, so a
  peach at 22% arrives as the blush a reader would see; a tint **over the
  aerial** is the project's `50%` fill in the colour, as before;
- a **texture** (dots, lines, cross) is a hatch of the drawing's own lines
  in the texture's ink at 2 mm on paper -- lines at 45°, crossed at 135°,
  and dots as lines in the project's `Dotted` line type (`Dashed` where it
  has none);
- a **grey or veiled aerial** is the tile toned with Pillow -- greyscale,
  blended toward white by the veil -- and saved beside the original as
  `aerial_r_c-grey36.jpg`, the site's own lot left in colour; Archicad can
  neither tone a Figure nor mask one. Oatley keeps the white `50%` wash;
- a **white street** is the road centre line widened to the reserve its
  function hierarchy suggests (30 m for a motorway down to 6 m for a lane),
  mitred and round-ended, as one white fill;
- the office's **drawn marks** -- its suns, winds and arrows, taken as paths
  from its symbol sheet -- are flattened to polygons (`sun_study.site.marks`),
  a cubic walked in six straight steps, the eye's pupil a hole;
- a theme's **text scale** applies to the map's words and not the sheet's:
  the title, the legend and the credit keep their size.

Every zone, institution and heritage fill is cut to the map field, with the
site's own lot cut out of the zone it lies in on the site sheet, and a cut
ring that pinches is split into its loops, because Archicad refuses a fill
whose contour touches or nearly touches itself (D137 records what the first
live run refused and why).

Fonts are not themed: the add-on's `CreateTexts` takes no face, so a text
is in the Text tool's default. The generator's Arial Narrow and DejaVu are
a project-template matter.

### Colours, and the sheets' own pens

A fill carries its colour as an RGB, but a line, a fill's contour and a text
take a *pen*, and the nearest pen of an office's table is rarely the colour
meant: measured on the first run, every theme's pens were off, by up to 54
colour-difference units (Heron's slate fall arrow came out a light blue). So
each sheet makes a **pen table of its own**, named for the sheet
(`17 | Context Analysis`, `17 | Site Analysis`): the model's active table with
every colour that sheet draws a pen in written exactly into its top pens,
255 downward, the most used first. The sheet's view is set to it, so the
view and the layout show the colours meant; the worksheet opened on its own
shows the project's active table, as any worksheet does. A sheet's view shows
only the tool's layers, so the pens it overwrites mean nothing else there,
and the table is never made active for the model or for layouts.

The legend on the layout takes no pens at all: a layout element draws in the
layouts' pen table, which is every title block's, so the legend's lines are
drawn as thin fills of their exact colour, a contour with a colour of its own
as its line, and every fill's own contour as a white hairline the paper hides.
Its texts are black and white, which every pen table has.

### Numbered places

In the four site-analyst.com themes the only words on the context sheet's
map are the street names. Every institution and park is a solid disc with
its number knocked out in white -- in the theme's institution ink, the
parks in its park ink -- and the legend carries the key under a `KEY`
heading: the institutions in the legend's category order, then the open
spaces, then the stations under their roundel letter. A sheet with more
than one station numbers them `T1`, `T2`... nearest the site first, and the
light rail `L1`, `L2`... the same way. Past two dozen entries the key's rows
tighten; when even that would overrun the column the places nearest the
site are kept and the rest go, from the map as well as the key, and the
kept ones are numbered again. Two discs on one block are pushed apart until
they clear. Oatley writes the names on the map, as the sheets first had it.
Each disc's element ID is `SA PLACE <n>: <name>`, so a schedule can list them.

### The context sheet

| theme | |
|---|---|
| **Flamingo** (default) | plain paper; four tints, each a family -- peach for the residential zones, sand for the centres, teal for open space and the institutions, blue for water, grey for the rest -- told apart within a family by tone and texture; the streets white strips over the tints; the cadastre a faint grey hairline; street and place names in a light green; solid roundels with a white letter; the bus routes a faint dotted line, the railway a red dotted one; the catchments dotted green with `5 MIN` along them; the site coral |
| **Kingfisher** | Flamingo in a masterplan reference's palette: every zone a pale ground (yellow for R2, pink for R3, cyan for R4, peach mixed use, the centres the blue family told apart by texture, the institutions lavender, industry grey on stone, open space a deep mint with black dots); the cadastre a heavy white line; street names and the discs a peach; the site magenta, heritage purple |
| **Heron** | the office sheet over the aerial in greyscale under a 36% veil; the lots a heavy white line; no street strips and no centre lines (the photo shows them) and the names plain in white; Heron's palette (tan centres, peach residential, mint open space, the institutions outlined in slate); the catchments a continuous green line with solid walker discs; the railway red dotted; the site in Heron's red |
| **Canary** | Heron with the zoning in exactly the NSW ePlanning Land Zoning colours, keyed by code and name in the legend (`R3 MEDIUM DENSITY RESIDENTIAL`, `SP2 INFRASTRUCTURE`...), no institution or railway tint over them, heritage in the ePlanning item tan; the catchments plain black lines with `5 MIN · 400M` along them |
| **Oatley** | the office's own legend over the colour aerial under the white `50%` wash, the grey centre lines, the arrow bands under the street names, ring roundels: the sheet as it was first drawn |

### The site sheet

| theme | |
|---|---|
| **Heron** (default) | the aerial grey outside the site, which keeps its colours; the zones hatched in Heron's palette and tinted under the hatch, since its tints are too pale to read as a hatch alone; the site, its levels, its boundary dimensions and the FALL/AREA words in Heron's red, the fall arrow in its slate; the neighbours as a fine white outline with number and storeys in white; the contours light grey; every word on the map a fifth larger; the sun an open jagged crown of twelve uneven teeth, the four on the diagonals drawn out as flames, each sun from its own seed, on its path, each path a white band 2 mm wide in the grey pen -- summer's whole, winter's in 6 mm dashes -- with a white dot and the time at each solar hour; the noise a white band swelling gently in blue, 11 mm beside each busy road and the railway on the site's side, broken where it would cross the site or leave the sheet; the winds three hand-drawn strands abreast, white in the climate grey, coming in from their compass quarter |
| **Kingfisher** | Kingfisher on paper, no photograph: each lot filled in its zone's pale ground so the roads stay white, water drawn whole; every building in its family's strong colour with a white edge; the white cadastre; the site in magenta on its pink; each solstice's sun path a yellow crescent, deepest at noon, with the office's small rayed sun at each rise and set; each wind a blue crescent over the quarter it blows from with three white broken-shaft arrows on it pointing in |
| **Flamingo** | the same paper and plan in Flamingo's palette, as its context sheet draws them: the lots in its tints and textures, every building white in a heavy outline of its family's ink and finely hatched in it, the cadastre fine grey, the site coral, the names green; the office's drawn marks -- an eight-rayed sun at each rise and set on dashed arcs (winter dotted), the ring carried on round the side the sun never reaches dashed in the wind's blue, the two-curl wind on it -- each solid in the ink of its name |
| **Canary** | the office's classic site sheet in the context Canary's colours: the aerial greyed under its veil, the zones washed in the ePlanning colours and keyed by code; the LEP's heritage items hatched in the ePlanning tan and its conservation areas in red; the site a dash in Canary's red with its levels, the dimensions and the fall in its slate; no contours; each neighbour's number and storeys in black; kerbside parking a hatched zone; the noise the office's zigzag, 10 mm beside each busy road on the site's side; the sun and the winds one black dashed circle about the site -- the winds named around it outside over hatched quarters, the two solstice paths inside it (summer solid, winter dashed, a step further in) with four plain suns named toward the centre, and north an arrowhead standing out of the ring |
| **Oatley** | the sheet as it was first drawn: the colour aerial, the office's red site, blue dimensions and fall, grey building masses with number, storeys and zone, yellow suns with rays, white wind banners at the corners |

Each site theme draws on a context theme for what it does not set itself --
the zones' palette and the categories' inks -- and the four stay paired, so
a context sheet in Kingfisher beside a site sheet in Kingfisher reads as one
package. The retired names still resolve: `conure` is Canary, `flamingo-2`
Kingfisher, `dove` and `cardinal` Heron, `kookaburra` Kingfisher.

The potential views, the indicative kerbs and the neighbours' height limits
the generator's site sheet draws are not here: the Loriini bundle carries
no sight lines, no kerbs and no `HOB` per neighbour.

## Where the site lands

**The boundary drawn in the file wins.** When a layer named for a boundary
(`03 | Site Boundaries`, say; `--fit-layer` names another) holds anything --
corner markers, a polyline, a fill -- the fetched lot is turned and moved to
sit on it: the turn is the difference between the longest sides of the two
convex hulls, the shift the difference of their centroids, and the residual
(mean distance from the drawn corners to the fitted lot's edge) is printed.
A residual over 5 m is not used. The fit reads the floor plan, so it is saved
as `data/fit.json` for the runs that stand in a worksheet, and the project
location is written from the fitted origin.

At Kogarah the fit turned the lot +1.05 degrees and moved it 40 m, with a
residual of 0.11 m on seven survey markers. The turn is the grid convergence
at Sydney: the file's north angle was typed from the survey plan, so it is
an MGA grid bearing, not the true bearing Archicad means by it. `--north
grid` lands such a file without a fit. The sun is a degree out either way;
nothing to correct.

A bundle is in longitude and latitude. To draw it the tool needs to know
where the project is and which way it faces, and it reads both from
**Options > Project Preferences > Project Location**, the same place the sun
studies read them:

1. every point is projected to the MGA2020 grid (zone 56 for Sydney);
2. the project origin's own grid position is subtracted, so the origin is at
   `(0, 0)`;
3. the result is turned so true north sits where the project's north angle
   says it does -- the same turn the sun views make in the other
   direction, checked against the same hand-worked figure in the tests.

So a site drawn into a project that is already georeferenced lands under the
model, facing the right way, and a survey merged later lands on top of it.

The run prints where the site centre landed and how far that is from the
origin. **If the project location was never set** -- none at all, or still
Archicad's city preset -- there is nothing for the site to line up with, so
by default the site goes on the project origin instead, at its bottom-left
corner, north-up unless the project has a north angle (asked 17 October
2026: drawn at the preset, a Campsie site landed 11.8 km off). A located
project keeps `--anchor location`, and `--anchor location` forces it.

Two more for that empty project, since a model is usually set out from a
corner of the lot with its long frontage level rather than from the
address's centroid north-up (asked 8 October 2026). `--origin-at
bottom-left` makes that corner of the site the project origin -- the corner
as the plan reads it, so `bottom-left` is south-west on a north-up frame and
the left end of the long boundary on a squared one -- and `--square-to-site`
turns the site so its longest boundary runs along +X. The turn is written
into Project Location as the project's north, so the sun studies stay right;
the corner moves only the origin, and the north is kept. Both are on the
window's Site page beside *Site lands at*. A boundary already drawn in the
file still wins: with a fit, neither is applied.

## The data

All free, none needing a key except TfNSW. Every source but the site itself
fails soft: a service that is down costs the sheet that layer and prints a
`WARN` line, and a run whose context sheet is missing its bus routes is still
a context sheet.

| need | source |
|---|---|
| geocoding | NSW Spatial `NSW_Geocoded_Addressing_Theme`, with the register's quirks handled: ranged parents, unit noise, suffixes, locality mismatches |
| lot boundary, rail corridor, property parcels | `NSW_Land_Parcel_Property_Theme` 8, 7, 12 |
| zoning, height, FSR, lot size, heritage | ePlanning `EPI_Primary_Planning_Layers` 2, 5, 1, 4, 0 -- the FSR by extent as well as at the site, for the future context |
| roads with names, hierarchy and lanes; railways | `NSW_Transport_Theme` 5, 7 |
| stations, parks, named building complexes, named areas | `NSW_Features_of_Interest_Category` and `NSW_FOI_Transport_Facilities` |
| contours (2 m), neighbour address points, local government areas | `NSW_Elevation_and_Depth_Theme` 2, `NSW_Geocoded_Addressing_Theme` 1, `NSW_Administrative_Boundaries_Theme` 8 |
| contours (1 m) and trees with their size, inside the City of Sydney | the council's Data Hub on ArcGIS Online: `Terrain_Contours` (2020 aerial survey) and `Trees` (height, canopy spread, trunk, species) -- see below |
| bus stops and routes, trees elsewhere, hydrants, poles, lamps, one-ways, driveways, parking, utilities, building footprints | OpenStreetMap through Overpass, mirrors rotated, answers cached for a month under `%LOCALAPPDATA%\Loriini\cache\osm` |
| walking catchments | Valhalla's public server, pedestrian costing, 5 and 10 minutes |
| aerial | NSW SIX imagery export, tiled, with `.jgw` world files on the MGA grid |

The curation is the office's: zoning is the base, and a named complex is
coloured by what its name says it is -- `SCHOOL` is education, `HOSPITAL` is
medical, `CHURCH` is community -- because the register's type codes are
unreliable and its names are not. The palette is the theme's (above);
Oatley's is the office's own legend.

### Whose data it is

Free is not the same as unconditional. Every publisher above asks to be
credited on anything drawn from their data, and a DA sheet is exactly that.
The list, the licences and the wording each publisher asks for live in
`sun_study.site.sources`, and the window shows them: **About** beside the
project picker, or **Where this data comes from** on the Site analysis tab,
which opens the same box at the registers. The box ends with the credit line
for a sheet, ready to copy into a title block.

| source | licence | credit |
|---|---|---|
| NSW Spatial Services, and the SIX imagery | CC BY 4.0 | `© State of New South Wales (Spatial Services, a business unit of the Department of Customer Service NSW)` |
| NSW ePlanning (`EPI` layers) | CC BY 4.0 | `© State of New South Wales and Department of Planning, Housing and Infrastructure` |
| City of Sydney Data Hub (contours, trees) | CC BY 4.0 | `© City of Sydney, CC BY 4.0` -- the council states no wording of its own, so the licence is named, as CC BY asks |
| OpenStreetMap, via Overpass | ODbL 1.0 | `© OpenStreetMap contributors` |
| Valhalla, FOSSGIS e.V., on OSM data | MIT engine, ODbL data | `Walking catchments: Valhalla (FOSSGIS e.V.)`, beside OpenStreetMap's own |
| Transport for NSW Open Data Hub | CC BY 4.0 | `© Transport for NSW` |

**The sheets carry it themselves.** Each Context and Site Analysis worksheet
is drawn with the credit along the foot of its map field, at 2 mm, and the
Summary of Controls carries it under the note that already says where the
figures came from. What is named is what that bundle actually holds --
`ContextBundle.sources_used` and its two siblings read it off the contents,
not off the list of what was asked for. Every fetch but the site's own fails
soft, so a run whose Overpass mirrors were all down draws a sheet with no bus
routes on it, and crediting OpenStreetMap there would be a claim about a line
that is not on the drawing. Bus stops are the case that needs recording
rather than inferring: a stop does not say where it came from, so
`stops_from_tfnsw` is written into the bundle as the run swaps the register's
stops in, and it is saved with the rest, so a sheet redrawn from `--from`
credits what that run fetched rather than what today's environment would.

Two of these have an obligation past the credit. ODbL is share-alike: a
drawing is a produced work and wants the credit and no more, but publishing
the fetched data itself, or a database derived from it, is the other half of
that licence and should be read first. The Overpass mirrors and the Valhalla
demo server are volunteer infrastructure under a fair-use policy, which is
why OSM answers are cached for a month and a run asks Valhalla once.

`tests/unit/test_site_sources.py` reads every `https://` literal in the
`site` package and fails on a host no source answers for, so a new endpoint
is a decision about attribution rather than an omission.

## What the first live run found

Run on the Kogarah solar study, 18-24 Princes Highway, on 11 September 2026.
The fetch, the frame turn and the drawing all held; two walls and one fault
came up, and each is recorded in `docs/addon.md`.

**Entering the worksheet.** Archicad refuses to make a worksheet created in
the same session current, whichever add-on asks -- Tapir's `ChangeWindow`,
the add-on's `SetCurrentDatabase`, both `APIERR_BADDATABASE`. Opening the
worksheet by hand is what makes it current, and the run is built around
that: it creates the worksheet, prints *waiting for '14 | Context Analysis'
to become current*, and polls every two seconds for `--wait-minutes` (five by
default). Double-click the worksheet under Worksheets in the Project Map and
leave it as the front tab; the run draws the moment it sees it. On a later
session the worksheet already exists and is entered without help. The
add-on's own `CreateWorksheet` was refused outright by the first build, from
an undo scope it should not have had; that is fixed for the next build and
the Tapir route stands as the fallback.

**One letter per label.** Every text made through Tapir 1.5.8 showed its
first letter: the Text tool's default box in that project wraps, and Tapir
hands the default through. The add-on now has its own `CreateTexts`, with a
non-breaking box, the layer, the anchor and the pen set at creation; the run
uses it when the installed add-on has it and falls back to Tapir's, and the
layer move, otherwise. Until the new build is installed, setting the Text
tool's default to non-breaking in the project and rerunning is the
workaround.

**One letter, the real cause.** With the add-on's own command the labels
were still one letter, and a one-character and a ten-character text came
back the same width: the content was cut, not wrapped. Archicad 26's text
memo is a byte string (`char **textContent` in its header), and both Tapir
1.5.8 and the first build wrote UTF-16, whose second byte is a NUL. The
command writes UTF-8 now.

**The orthophoto.** No command in Archicad's API or Tapir places a picture,
so the add-on grew `PlaceFigures`: the tile as base64 inside the request,
its box in metres and its turn from the frame. The tiles
are fetched into `data/aerial-context/` and `data/aerial-site/`, and each
sheet draws them under everything else; the zoning and institution washes
then use the project's `50%` fill with a clear background so the photo
shows through, the way the office's sheets have it. Without that fill
attribute the wash is solid and the run says so.

**Still to confirm by eye:** the `angle` of rotated labels is sent in
radians; if street names and boundary dimensions arrive turned wrong, it is
degrees. Fills were given the `Solid Fill` attribute (index 12 on that
project) and dashed lines the `Dashed` line type (14); lines took the nearest
pen of the active table, `00 FA Pens`, and the views are pinned to its
`- Site Analysis` sibling, which the office keeps for these sheets, and to
No Overrides.

## The context model

`--model` (the **3D model** tick in the window) builds the neighbourhood the
shadow diagrams and sun views cast against, in the floor plan, every
element with an `SA ...` element ID, on three layers in the office's site
group -- one per kind, so a view can show any of them without the others:

| layer | holds |
|---|---|
| `03 \| Site Context.Terrain` | the ground mesh |
| `03 \| Site Context.Roads` | the kerbed street blocks the roads run between |
| `03 \| Site Context.Buildings` | the neighbours |

`--context-prefix` moves all three to another group. A rerun clears the
last run by element ID, not by layer, so a model made on the single
`Site Context.3D` layer of an earlier version is replaced too.

- **Terrain**: one mesh from the contours -- the City of Sydney's 1 m ones
  inside its area, the state's 2 m ones outside -- through the add-on's own
  `CreateMesh` (Tapir's `CreateMeshes` answers `APIERR_BADINDEX` for every
  mesh on AC26). Its levels are metres above the storey nearest RL 0, so the
  ground sits where the contours say, whatever storey is current. The level
  lines stay under 12,000 vertices, because Archicad triangulates between all
  of them, and the budget is spent at the site: every contour within 100 m of
  the site's boundary, true to a tenth of a metre, and fewer and simpler
  contours towards the edge (below).
- **Neighbours**: one slab per OSM footprint, `levels x 3.1 m` thick, on the
  ground at its centre. Where OSM has no storeys the LEP height-of-building
  control gives them (`SA NEIGHBOUR 2 STOREY (ASSUMED)`), two storeys where
  there is neither. Footprints on the site's own lots are left out.
  Buildings OSM draws as multipolygons -- a block with a courtyard -- are
  fetched with the rest and stood with their courtyards as holes.
- **Heritage items**: a neighbour whose footprint centre falls on an LEP
  heritage *item* (not a conservation area, which takes in whole streets)
  stands in the `LORIINI HERITAGE` surface, the ochre of the context sheet's
  heritage hatch, every face, with `HERITAGE` on the end of its ID. The
  surface is made in the project on the first run that needs it and found
  again after. The add-on's `CreateSlabs` takes it per slab (`surface`: a
  name and the colour to make it in); Tapir's does not, so an add-on built
  before it leaves them in the Slab tool's surface and the report says so.

**When buildings are missing.** Three causes were found and closed on 23
September 2026; what is left is OSM's own coverage.

- *An Overpass answer cut short.* A busy server stops at its timeout and
  still replies 200 with valid JSON and a `remark`. That is now tried on the
  next mirror and never cached; with nothing complete anywhere, the fullest
  partial answer is used and a `WARN` says so.
- *Buildings drawn as relations*, which a query for tagged ways never
  returned. Around Kogarah station both are apartment blocks.
- *One refused footprint.* Archicad makes a request in one undo step and
  abandons it at the first slab it refuses, which took up to 199 good
  neighbours with it. A refused request is halved and retried down to the
  one bad footprint, which is tried without its holes and then as its
  convex hull before it is given up on; the report counts both.

What remains is data. OSM around Kogarah holds 395 buildings in a
kilometre square, most detached houses unmapped, and no NSW register
publishes footprints to fill the gap -- Spatial Services has points for
named building complexes, not outlines. A house that is not in OSM is not
in the model; draw it, or add it to OSM.
- **Location**: with the project unlocated and the site anchored at the
  origin, `SetGeoLocation` writes the site centre and its MGA survey point
  first, so a survey merged later lands on top.

**Blocks and roads.** The cadastre of the whole square comes with the
model bundle, and every street block -- the lots that touch, dissolved to
their outline, clipped to the model's edge -- is a mesh 150 mm above the
terrain, `SA BLOCK n`. The roads are not modelled; they are the terrain
left showing between the blocks, with the kerb the blocks' own edge. That
is how the office's files do it (a roads mesh with the blocks as holes and
a footpath mesh per block), without the boolean the holes would need. The
site's own lots are left out of their block, so the project's site model
shows there. At Kogarah: 119 blocks; three groups of lots would not
dissolve and are drawn lot by lot, one lot was refused as self-crossing.

The model fetches its own square, `--model-radius` metres each way from the
site (500 by default: a kilometre across, about 500 footprints and 36,000
contour vertices at Kogarah), saved as `data/model.json` beside the sheets'
bundles. The ground level under each slab and each kerb corner is read the
way the site sheet reads its corners -- across the slope, between the two
contours that bracket the point (below) -- from an index of the contours'
segments, so a thousand kerb corners read a kilometre of contours in
seconds. A rerun deletes the last run's slabs and mesh by their IDs first,
so the model is replaced, not stacked.

## The City of Sydney's registers

Inside its own area the City of Sydney publishes, under CC BY 4.0, two
registers no statewide layer matches, and the site analysis takes both where
they cover the ground. They are one entry each in a registry (`terrain`,
`trees`), the shape the office's generator uses, so the next council that
publishes its own is a line and a credit.

**Contours.** 1 m contours from the council's 2020 aerial survey -- the
ground, interpolated under the buildings -- in place of the state's 2 m ones.
Two rules, because a sheet and a model want different things at a boundary:

- *A sheet* takes the council's only where it covers the map field -- 85% of
  it -- and the state's everywhere otherwise, so one sheet is drawn to one
  interval and one legend row says whose. "Covers" is tested twice: the
  lines reach across the sheet (the generator's test) *and* the council's
  area holds the sheet, read from the state's register of local government
  areas. The first alone is fooled by a boundary down the middle: at King
  Street, Newtown, the council's lines reach every edge of the sheet between
  them while only 36% of it is the council's, and two thirds of the sheet
  would have had no contours at all. The generator has the same test and the
  same blind spot.
- *A model* takes both, cut at the boundary: the council's lines inside its
  area, the state's outside. A kilometre square crosses a council boundary
  more often than not -- 47% of the Newtown square is the City's -- and the
  sheet's rule would throw the finer lines away exactly where the model
  needs them, at the site. The model also has the council's server generalise
  its lines to 0.1 m before sending them: a square kilometre is 440,000
  vertices as published, a vertex every quarter metre, most of them the
  staircase of the grid the lines were traced from.

The corner levels are read across the slope rather than from the two nearest
lines, which with 1 m contours put a corner half a metre low (the generator's
`lib/levels.ts`, ported rule for rule): twelve directions through the point,
the first contour each way, and the steepest pair of different levels wins.
Past the last contour on a slope the slope carries on, one interval at most.

**The terrain mesh.** The old rule halved contours and points everywhere until
the level lines were under 12,000 vertices: a kilometre of the state's 2 m
contours became 4 m ones at Kogarah, and the council's 1 m ones would have
become 8 m ones -- worse than what they replace, the site included. The
budget is now spent where the site is (`site.ground.mesh_lines`):

| | Surry Hills (council) | Newtown (both) | Campsie (state) |
|---|---|---|---|
| contour vertices fetched | 180,600 | 53,800 | 25,100 |
| level-line vertices | 8,272 | 8,675 | 1,933 |
| within 100 m of the site | every 1 m contour | every 1 m contour | every 2 m contour |
| to 250 m, and beyond | every 2 m, every 5 m | every contour | every contour |

Douglas-Peucker with a tolerance of its own at every vertex: 0.1 m within
100 m of the site's boundary, growing with distance past it, so one contour
running from the site to the edge is exact at one end and coarse at the
other. The plans are tried finest first -- far contours go before the
tolerance grows -- and the first that fits the budget is used. Each line is
carried to the edge of the model's square rather than stopping at its last
vertex inside it.

Simplifying lines one at a time can make two of them cross where the ground
is steep, and a mesh has to invent the ground where its level lines cross. So
the simplified lines are checked, and the two spans of every crossing
simplified again at half the tolerance, and again, span by span -- at Surry
Hills 23 lines, 2,100 vertices between them. What still crosses with neither
span moving a centimetre crossed as published: the council's contours touch
and cross by millimetres where the ground drops at a wall, and every one of
the 38 pairs still crossing at Surry Hills crosses in the published lines
too. That is the survey's to mend, not the mesh's. Keeping every 1 m contour
to the edge instead makes 228 lines cross, and mending them would take
50,000 vertices -- which is why far contours go before the tolerance grows,
and why a plan whose mending breaks the budget gives way to the next.

**Trees.** Every street and park tree the council keeps -- 278 in a 300 m
square around a Surry Hills site -- with where it stands, its height, the spread of its
canopy north to south, the diameter of its trunk and its species. The sheet
draws each at the size of its canopy on the ground, as a wash so the kerb
under it shows, with a dot at the trunk; its element ID carries the rest
(`SA TREE London Plane (Platanus x acerifolia), canopy 10 m, 12 m high,
trunk 45 cm`), so a schedule can list the trees near the site. OpenStreetMap's
trees fill in around the inventory -- one standing within 4 m of an inventory
tree is the same tree mapped twice -- with whatever size their tags record,
and a nominal 6 m canopy drawn dashed where nobody recorded one, so the sheet
never claims a size it does not have. Outside the City of Sydney that is
most trees: across inner Sydney 37 of 24,638 OSM trees carry a crown size.

## The future context

`--future` (the **Future Context** tick in the window) shows the street as
the controls would let it be, not as it stands: each existing building near
the site, kept on its own footprint, raised to the storeys the LEP's
height-of-building control allows where it stands. Never lowered -- a
building already at or over its control is its own future, and the context
model already has it.

- **On the Site Analysis sheet**: each raised building's footprint, dashed
  in magenta on the Context layer, with `FUTURE 8 STOREY / 24.8 m` written
  in it. A legend row names it.
- **In the model**: one slab per building on `Site Context.Future
  buildings`, a layer of its own so a shadow diagram's saved view can
  include the neighbours as they are or as they could be. Element IDs read
  `SA FUTURE 2//DP1 8 STOREY 0-24.8 m`, named by the lot the building
  stands on. A rerun deletes the last run's future slabs by that ID and
  leaves the context model's.

The rules, in the order they apply:

| step | rule | source |
|---|---|---|
| which buildings | every OSM footprint in the model's square, 20 m2 and over | OpenStreetMap |
| not the site's | a footprint whose centre is on the site is what the proposal replaces | the cadastre |
| within reach | within `--future-reach` (100 m) of the site's boundary | |
| zoned for flats | in `--future-zones` (R1, R3, R4, B1-B4, E1, E2, MU1); a house on land zoned for houses keeps its height | `EPI` 2 |
| a control | a height-of-building control where it stands | `EPI` 5 |
| storeys | the control over 3.1 m, rounded down; left out when the building already has that many | `EPI` 5, OSM's storeys |

The control is the LEP's because the register carries it; a council's DCP
can say less, and is not open data. Nothing is set back and no ratio is
applied: the footprint is the one a person recognises, which is the point.
The lot envelope this replaced -- the lot set back by the ADG's separation,
stepped, capped by the ratio -- is still in `site.envelope`, the right
shape for a different question: what the *site* could hold, which the
shadow diagram's **ADG envelope** row compares against the proposal.

Not yet run live. The tests raise a two-storey building on an R4 lot under
a 25 m control to eight storeys, and leave alone the one on the site, the
nine-storey one already over its control, the house on R2 land and the one
three hundred metres off.
