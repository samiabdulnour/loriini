# Roadmap

What the office has asked for next, in the order it was asked, with where
each one stands today, the thinking so far, and the first step. Numbered
R1 to R7 so that a commit, a pull request or a conversation can name one.
Written on 28 September 2026. When one is done, its entry says so and points
at the decision in [`decisions.md`](decisions.md) that records how.

## R1 — Shadow diagrams: the larger model, and 3D Documents

**Asked.** The shadow analysis is still not right, and on a larger model it
failed outright. An assisted session in Archicad is needed to see the
failure. The ideal may be to make the shadow diagrams the way the sun views
are made, as 3D Documents, so that Loriini prepares everything and Archicad
draws the shadows.

**Where it stands.** A shadow diagram is computed by Loriini: the add-on
exports the model's geometry (D103, D104), the ray caster casts the shadows
onto the terrain, and what is new shadow and what was there is drawn as
fills on a layout in the legend's colours (D113). The sun views already make
a 3D Document per hour, each with its own projection and sun, through the
add-on's `CreateDocumentFrom3D` and `SetProjection`; D49, which said a 3D
Document could not be made, predates that command.

**Thinking.** The failure has to be read before anything is changed: the
run's log from the larger model says whether the export timed out, the
caster ran out of memory, or a fill was refused, and those are three
different fixes. The assisted session is the way to get it; the log the
window keeps is worth having before the session.

The 3D Document route is real. A 3D Document is a drawing Archicad makes
from a projection, with the sun on the projection and the shadows drawn by
Archicad's own vector shadow engine, at any model size Archicad can display.
A plan projection at each hour with shadows on is a shadow plan for that
hour. Loriini would do for it what it does for the sun views: a document per
hour, its projection and sun set, the layer combination pinned, the
documents placed on layouts, and the site outline, the legend and the
annotations drawn over them as fills and texts.

What it would not give is what the fills give now: several hours on one
plan in one colour each, and the *difference* between the existing and the
proposed shadow (and the ADG envelope's), which is the figure a DA argues
with. A document shows the whole shadow of one scenario at one hour;
layouts do not composite drawings, so the comparison would be read across
documents side by side rather than as one drawing. So the two routes answer
different questions -- Archicad's documents are exact and scale, Loriini's
fills are the analysis -- and the office may want both: the documents as the
record, the fills as the argument.

To check in the SDK before deciding: whether a 3D Document's shadow setting
(shadows on, and the fill they take) can be set when the add-on creates it,
or only by a person in its settings once, with later documents copying it.

**First step.** The assisted session on the larger model, with its log.
Then a one-day trial: one shadow 3D Document made by hand in Archicad, to
see exactly what it shows and what it lacks, before any code.

**Done so far (29 September).** The assisted session has not happened yet,
so the log was made worth having first. Every run the window starts is
written to a file as it goes -- `%APPDATA%\Loriini\Logs`, the newest sixty
kept, *Whole log* beside the line at the foot of the window -- and the
shadow diagram prints how long each stage took and how much memory the run
had reached, the size of the grid and any layer that stretched it, and how
far through a long cast it is ([`larger-models.md`](larger-models.md)).
Reading the pipeline for what a larger model would break found two of the
three failures before any session: the caster gathered every ray before
casting the first -- about nine gigabytes for a grid two kilometres across
over the three default days -- and now casts a block at a time with the
same answer; and one fill Archicad refused rolled back its batch of 500 and
ended the run, where it now costs that fill, named. The export, the third,
is for the log to show. The 3D Document route is built too. The SDK
question is answered: a document's shadows are its own, switched on through
the 3D Document defaults as it is made, with their fill in its model
display. **Shadow plans** are a document per hour looking straight down,
with Archicad's sun and shadows, their views pinned and dealt onto sheets by
day -- from the Shadow diagram tab, `sun-study shadow-plans`, and the
agent's `shadow_plans` tool ([`shadow-plans.md`](shadow-plans.md)). D123 is
how. Built against the kit and a scripted Archicad; next is the assisted
session on the larger model with its log, and one live run of the shadow
plans to see the shadows come on.

**Measured (7 October).** The shadow diagram on the Redfern project, a
kilometre of context on `03 | Site Context.Buildings` (32,600 triangles),
the proposal's slabs on `01 | Floor.Structural`, and the terrain named from
`03 | Site Context.Terrain` and `03 | Site.Mesh`: the export takes 20 s and
the figures come out -- 180,000 to 370,000 m² of existing shadow at 9, 12
and 3 on 21 June, the proposal adding about 2,000 m² at each. Without a
terrain layer named the window's run draped onto nothing and left 83% of
the grid undrawn; with one, 48%. The cast is the cost: 9 min 31 s for 1.96
million samples at 1 m over three instants, where a twelfth of the rays (2
m, one instant) took 12 s -- four times slower per ray at full size, at
536 MB. Where the time goes at that size is unread, and is the first thing
to profile; the window's progress line is what shows it on a workstation.
Drawn from the kept model (`--ifc-in`) with `--draw --sheet`: 8,224 fills
on three layers in 14 s, three views and two sheets under *SHADOW
DIAGRAMS* in 8 s. Archicad refused two of the existing shadow's fills, of
760 and 1,157 corners -- the big merged shadow of a whole block at 9 and
12 -- so the plan is short of them while the table counts them; splitting
a fill over some hundreds of corners is the fix, and the second thing to
do here.

## R2 — An agent that operates Loriini

**Asked.** Could an AI agent run Loriini natively, for more users? It saves
time and could speed up the workflow for some.

**Where it stands.** Loriini is driven by its window or by its command
line. This repository is worked on with Claude Code, which runs the command
line -- a developer's route, not a colleague's.

**Thinking.** Three shapes, of which the first is the one to build:

1. *An MCP server shipped with Loriini.* It exposes the studies as tools --
   the site analysis for an address, the shadow diagrams for dates and
   hours, the communal and apartment studies, the sun views, the reports --
   with the add-on as the executor, exactly as the window is. Any agent
   client a person already has (Claude Desktop, Claude Code, others) then
   drives Loriini: "run the 21 June shadow diagrams for this project at 9,
   12 and 3". It is the cheapest to build, because the command line is
   already the API; it puts no key of ours in the product; and the person's
   own agent subscription pays for the tokens.
2. *An assistant inside the window.* A box that turns a sentence into the
   page's settings and runs it. It needs a model call per request on a key
   -- ours, billed to us, or theirs -- and makes us answerable for what the
   model does in a project.
3. *Both,* with the window's assistant built later on the same tool
   definitions as the server.

Whatever drives it, the agent should reach only Loriini's own commands,
which clean up after themselves and are covered by the licence check, and
never raw Tapir commands: an agent in a project can undo nothing.

**First step.** A spike: an MCP server over the existing command line with
three tools (site, shadow, sun views), tried from Claude Desktop on a
workstation. Read the API reference for models and MCP at that point rather
than from memory.

**Done so far (28 September).** The server exists: `Loriini.exe mcp`
(`sun_study.agent`), with seven tools -- the running Archicads, the
project's options, the command help, any command line, and the site
analysis, shadow diagrams and sun views as typed tools -- each running the
same command line the window runs, streaming its lines and stoppable from
the client. Driven by a scripted client and by tests against a fake
command line; not yet from Claude Desktop on a workstation, which is the
next step. [`agent.md`](agent.md) is how to connect; D120 is how it is
built and why the protocol is written here rather than taken from the
`mcp` package.

## R3 — GFA and a yield mix from the massing slabs

**Asked.** Massing is done with slabs. Could Loriini simply produce the
massing numbers -- the GFA, and a yield mix schedule?

**Where it stands.** The site analysis already works out the FSR and the
gross floor area it allows, on the Summary of Controls. The COS schedule is
written as an .xlsx without a library (`report/cos_table.py`, D106), and
the add-on reads the project's elements.

**Thinking.** A *Yield* study. It reads the slabs on the massing layers (a
layer picker, as the other studies have), takes each slab's area and storey,
and sums them: GFA per storey and per building, the building told by the
slab's ID or its layer. From the GFA, by figures the office sets and keeps
as a preset: the saleable area by an efficiency factor; the unit mix by
their rule (the share of one-, two- and three-bedroom units and each one's
typical area, from the ADG or their own table) as unit counts per storey;
parking by rate. Against it, the FSR allowance from the same site bundle:
so many square metres under or over. Out of it, a schedule .xlsx through
the COS writer, and the table on a layout, as the Summary of Controls
already does for its rows.

Questions for the office before it is built: how a slab's use is told
(layer per use, ID, classification); whether GFA is measured to the slab's
edge or wants the external-wall deduction the LEP definition implies (a
massing slab is to the outside face, so an offset or a percentage);
balconies and voids.

**First step.** One massing file from the office, and the yield spreadsheet
they fill in by hand today, to copy its arithmetic exactly.

**Done so far (28 September).** The office sent its sheet, *Area
calculation, GFA + Yield*, and asked for the slabs to be chosen by layer or
by the renovation filter, or simply for the GBA and an approximate GFA. The
study exists: the **Yield** tab and `sun-study yield`. The slabs on the
layers named residential and non-residential -- or only those the
renovation filter shows, or with no layer named every slab showing -- are
measured to their edges, arcs and holes and all; the office's four factors
take GBA to GFA to NSA, the site to an FSR against the LEP's, and the
residential NSA over the mix's average unit to a yield split into the mix.
Out of it: the Area Calculation sheet on a layout, with the office's own 3D
view of the massing placed beside the table when one is named; a live
workbook whose formulas recalculate when a factor or a share is changed;
and the table in the log. The office's sheet is reproduced from its own
figures -- 112 units, 17, 78 and 17 -- and has its two uses' rows the wrong
way round, which the new sheet does not. Tested against a scripted Archicad,
not yet a live project: a curved slab's area and the renovation filter are
the first things to check. [`yield.md`](yield.md) is how to use it; D122 is
how it is built. Per-building figures, parking and the Summary of Controls'
project rows are next.

## R4 — A reference image over the 3D window

**Asked.** Sometimes a view has to be set up from the same angle as a
reference image, and Archicad cannot show an image in the 3D window. A tool
that overlays the 3D window with an image at reduced opacity would do it.

**Thinking.** Archicad's API cannot draw into the 3D window, and Trace
Reference does not work in it. What can: a window of Loriini's own,
borderless, always on top, semi-transparent and click-through (on Windows a
layered window -- Tk gives the transparency and the always-on-top, and the
click-through is one call through ctypes), placed over Archicad's 3D window
(found by its title, or dragged there by hand) and showing the chosen image
scaled to it. An opacity slider, fit or stretch, lock, hide. The person then
orbits the model under it until the two line up. No add-on change, and it
works with any Archicad version; the Mac has the same window kinds for
later.

Beyond it, later: matching the camera to the photograph -- reading its
vanishing lines to set the projection -- which is a bigger thing. The
overlay alone is most of the value.

**First step.** Half a day: the overlay window on Windows, over a 3D window,
with a slider.

**Done so far (28 September).** The overlay exists: *Reference image*
beside the project picker opens a small palette that stays on top, and the
picture -- PNG, JPEG, TIFF, BMP, GIF or WebP, turned the way a phone's
orientation tag says -- is a borderless window over Archicad at the
opacity the slider says. Unlocked it is dragged and sized by its corner,
or laid over the Archicad window showing the chosen project by a button;
locked, the corner goes and the mouse goes through it to the model. Fit
keeps the picture's shape with see-through margins; Stretch pulls it to
the frame. Driven by tests under a virtual display; not yet on a Windows
workstation over Archicad, where the colour key and the click-through are
the two things to check first. [`overlay.md`](overlay.md) is how to use
it; D121 is how it is built, and why Pillow came into the bundle for it.

**Changed (7 October).** The office asked for the picture to be part of the
palette, and for the corner to size it from its top-left corner. It is one
palette now, the way Archicad's own float: the strip of controls stands on
the picture's top edge, as wide as it, and the two move together by the
title bar or by the picture; the corner grows the picture with its top-left
corner fixed, and *Fit* keeps the picture in that corner rather than
centred, so what was lined up stays lined up. Underneath it is still two
windows, so that the locked picture lets the mouse through while the strip
does not; D121 says so.

## R5 — Licence keys sent by mail

**Asked.** Licensing that sends a licence code to the buyer's email, so
that Loriini can be used.

**Where it stands.** The term is compiled in -- `EXPIRES`, 1 January 2027,
in `sun_study.licence` -- and checked at every start; the info box shows
the terms.

**Thinking.** Keys that Loriini verifies offline, so that the office never
depends on a server to open the program. A key is the buyer's email, the
expiry and the seat count, signed with a private key only we hold; the
public key is compiled into Loriini. The window asks for the key once (an
"Enter licence" box, the code pasted from the email), keeps it in the
settings folder, and verifies the signature and the date at each start; the
info box then says whose licence it is and until when. Issuing is a small
script that signs a key from an order and emails it -- run by hand at first
(an order comes in, the script runs), then from the shop's webhook (R7).
Revocation is not possible offline, which is accepted for a key that expires
in a year; the compiled-in date stays as the floor for beta builds. The key
is long, so it is written in groups a person can paste, with a checksum, so
a mistyped one fails as "mistyped" and not as "invalid".

**First step.** Decide the term (a year?) and seats per key; then the
licence module -- parse, verify, install, with a test keypair -- and the box
in the window.

**Done so far (29 September).** The term is decided: Loriini is sold by
subscription, so every key is time-limited to the period paid for, plus a
week's grace, and each renewal brings a new key -- a lapsed subscription
simply runs out, which is the revocation offline keys cannot otherwise have.
The keys exist. A key is the licence number, the subscriber's email and name,
the seats and the last day, signed with Ed25519 -- written here from RFC 8032
with the standard library and checked against the RFC's own vectors, so no
new dependency -- and set in groups of Crockford base 32 with a CRC, so a key
cut short says "copy it again" rather than "invalid". A build carrying a
public key asks for a key when it opens, reads it as it is pasted and says
whose it is, keeps it beside the settings and checks it at every start; the
command line refuses work without one at the door and `Loriini.exe licence`
installs one. The vendor's side is `scripts/licence.py`: `keygen` once, then
`issue` per paid period, which numbers the key from a ledger and writes the
email as an unsent draft or sends it. [`licensing.md`](licensing.md) is how,
for both sides; D124 is why. Next: run `keygen`, commit the public key it
writes, and issue the first keys by hand; the shop's webhook (R7) then calls
the same `issue`.

**Thinking, 29 September.** A monthly subscription and withdrawing access
both need something online. [`licence-model.md`](licence-model.md) analyses
the licence model as a whole: what is counted, for how long, how it is kept,
how it is paid and what runs it. It keeps everything above. It recommends
adding activation and short signed leases from a small licence service of our
own, with a seat counted as a computer used in the last fortnight, and Stripe
for payments. Its §10 lists the decisions that are the owner's to make.

## R6 — Automatic updates

**Asked.** An update server, so that the programs update themselves.

**Thinking.** No server of our own. A static manifest -- the version, the
date, the notes, the download links and the SHA-256 of `Loriini.exe` and of
the add-on -- hosted with the website (R7) and written by the release
workflow when a version is tagged; the handover build exists, so a tag turns
it into a release. Loriini reads the manifest at start, once a day, in the
background, and if there is a newer version says so in the window: what is
new, and an Update button. The program cannot overwrite itself while it
runs, so the new one is downloaded beside it and swapped on exit (Windows
lets a running program be renamed). The add-on is held open by Archicad, so
it is put in place for the next Archicad start and the window says so; the
add-on's version is already checked at connect, which is what an "older
add-on" message comes from. The check sends the request and nothing else:
no identifier.

**First step.** The release workflow -- a tag makes a release with the
handover folder and the manifest -- then the check in the window.

## R7 — The website: promotion, buying, downloading

**Asked.** A website to present Loriini, for clients to buy it and to
download it.

**Thinking.** A static site (Cloudflare Pages, GitHub Pages or Netlify:
nothing to keep running) with the story, the sheets as pictures, the price,
the documentation, and the download of the current build, whose files and
manifest (R6) live there too. Buying goes through a merchant of record that
handles GST and invoices -- Lemon Squeezy or Paddle -- with a webhook that
issues the licence key (R5) on payment and emails it. What the site has to
say: what it makes (the sheets), for whom (NSW architects preparing a DA),
the trial (a fortnight on a trial key), the terms (the `LICENSE`), privacy,
and a support address. The name and the bird are the brand; the icon
exists.

R5 and R6 come first, so that the shop has a key to deliver and a build to
serve; the site is the front on them.

**First step.** The domain and the merchant account, both to be opened by
the owner; then the page.
