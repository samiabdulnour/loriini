# Decisions

Domain assumptions matter more than the code here. A wrong one produces confident,
wrong numbers that no amount of testing catches, because the arithmetic is fine — it is
being applied to the wrong windows.

Every decision that changes a headline compliance percentage is recorded here with the
option taken and the reasoning. **Open** decisions are ones the tool cannot sensibly
default; they are listed with a proposed default and must be settled before the
milestone that depends on them.

---

## Settled

### D1 — Solar position: NOAA in-house, pvlib as a dev-only reference

*Milestone M0. Alternatives: pvlib as a runtime dependency; NOAA with no cross-check.*

`core.solar` implements the NOAA algorithm directly, roughly 250 lines and no new
runtime dependency. `pvlib` is installed only in the dev group, where CI uses it to
cross-check a year of positions at seven latitudes against an independent SPA
implementation.

Taking pvlib at runtime would have pulled pandas and scipy into every office install
for a geometry tool, and its pandas-indexed API is an awkward fit for the numpy
`(n_points × n_suns)` ray batching the occlusion engine needs. Keeping it as a
validation reference gets the cross-check without the weight, and mirrors how Ladybug
is treated: a thing we measure against, never a thing we depend on.

Measured accuracy is in [`validation.md`](validation.md).

### D2 — `tzdata` is a runtime dependency

*Milestone M0.*

A pure-data wheel, no code. Python's `zoneinfo` reads the system tz database first and
falls back to this package; Windows ships no system tz database at all, and Windows is
the primary deployment platform. Declared unconditionally rather than Windows-only so
that Linux CI exercises the same code path the office machines will.

### D3 — Timezone is explicit configuration, never inferred

*Milestone M0. Alternative: derive from latitude/longitude via `timezonefinder`.*

The run configuration must name an IANA zone. There is no default and no inference, and
an unknown or missing zone raises `UnknownTimezoneError` rather than falling back.

IFC carries latitude and longitude but no reliable IANA timezone, so something has to
decide that 21 June 09:00 in Sydney means UTC+10. Deriving it from coordinates would
add a dependency with tens of megabytes of boundary data and, worse, make the decision
invisible — exactly the silent-wrong-answer hazard the brief flags around north and
geolocation. An hour of error moves every sun position by 15° of hour angle.

The resolved zone is echoed in the console banner and in every output file header.

### D4 — Azimuth uses the `atan2` form, not NOAA's `arccos` form

*Milestone M0.*

Algebraically identical; NOAA's form divides by `cos(lat) · sin(zenith)`, which is zero
at the poles and at the sub-solar point. `test_azimuth_forms_agree` asserts the two
agree to 1e−9° across a dense grid of latitudes and dates, so the substitution is
verified rather than assumed.

### D5 — Sun vectors use apparent (refracted) elevation

*Milestone M0.*

`SolarPosition` exposes both `elevation_deg` (refraction-corrected) and
`true_elevation_deg` (geometric). `unit_vectors_enu()` defaults to the apparent
position, because refraction is why a low sun's shadow falls where it actually falls.
Near the horizon the two differ by about half a degree, which is roughly one sun
diameter — not negligible for a 9am midwinter assessment. `apparent=False` is available
and the choice will be stated in the output header.

### D13 — `core` stays numpy-only, and the numpy ray caster is the real backend

*Milestone M1. Alternative: `trimesh` + `embreex` as the primary occlusion engine.*

This is a deployment decision. The tool has to run on office Windows workstations
alongside Archicad 26, and a native ray tracer that needs a compiler to install is a
tool that does not deploy. `core.occlusion` is therefore a pure-numpy BVH with no build
step — the production path, not a fallback that only keeps CI green.

The consequence is that its performance is a real concern rather than an academic one,
so it is measured (`scripts/benchmark_occlusion.py`) and the leaf size is tuned from the
measurement rather than guessed. About 38k rays/s on a 96k-triangle scene, roughly 20
seconds for a 200 apartment job. See [`validation.md`](validation.md) §2.2.

The whole of `core` is held to standard library plus numpy, enforced by
`test_architecture.py`. `trimesh` and `ifcopenshell` arrive at M2 confined to `ingest`,
where a failure to install stops geometry loading rather than the analysis engine. An
embree fast path can be added later behind the same `Occluder` interface; nothing will
depend on it existing.

*Still to settle, before M4:* how the tool is actually delivered to a workstation —
`uv tool install` from the repository, a pinned virtual environment, or a frozen
executable. Not urgent, but it should be decided before the Archicad adapter lands
rather than after.

### D14 — Sun vectors are consumed in the model frame, never in ENU

*Milestone M1.*

`core.analysis.sunlit_matrix` takes sun vectors in the same frame as the geometry, and
`core.orientation` is the only thing that converts ENU into that frame. Passing raw ENU
vectors alongside a rotated model is the single easiest way to produce a confident wrong
answer, so the conversion has one home, an explicit derivation in the module docstring,
and cardinal-point tests that pin the sign.

Two consequences worth stating: the model frame must be Z-up, because the below-horizon
test is on the +Z component; and `SiteOrientation` has no default for any field, since a
dataclass default is the easiest way for a guess to become invisible.

---

## Implemented with the proposed defaults — still awaiting confirmation

These are live in the code as `SceneConfig` fields, each echoed in the run banner and
in every output header. They are **defaults, not answers**: the code no longer blocks
on them, but the numbers it prints depend on them being right for the project.

### D6 — What counts as a "living room window"

**This is the one that most changes the headline percentage**, and Archicad will not
tell us. Options: Zone category convention, a window property flag, or a naming
convention.

*Implemented as proposed.* `SceneConfig.living_room_space_names`, default
`("Living Room",)`, matched case-insensitively against the parent `IfcSpace`'s
`LongName` **and** `Name`; a window inherits "living room" from the space it serves.
Override with `--living-room`, repeatable.

Matching both fields matters. Archicad puts the Zone category in `LongName` and the
apartment identifier in `Name`, and an earlier version that checked only `Name` matched
nothing — which reads as *a compliant building with no living rooms*, not as a
configuration error. `test_a_non_matching_room_name_assesses_nothing` keeps that
failure visible, and the run banner always prints the count assessed.

*Also needs deciding:* what happens to a studio apartment where the living space and
bedroom are one Zone, and to a space with no category set. Proposed: fail loudly and
list the offending Zone GUIDs rather than silently assessing or silently skipping.

### D7 — Balcony geometry source

Zones are cleanest, but offices do not always zone balconies. A slab-based fallback
needs a rule for which slabs count.

*Partly implemented.* Slabs whose name starts with a configured prefix (default
`"Balcony"`) are private open space, attached to the apartment they serve, with the
resolution route counted in `Scene.provenance`. The Zone-based route is not built yet;
the fixture has no balcony Zones to develop it against.

Attaching a balcony to its apartment needed more than nearest-neighbour — see
[`validation.md`](validation.md) §5.6 for the equidistance trap that silently gave the
upper storeys no open space at all.

### D8 — Glazing extent

Whole window opening versus glazed area net of frame.

*Implemented as proposed.* The whole `IfcWindow` solid's dominant outward face is
gridded, so the assessed area is the opening rather than the glazed area net of frame.

One limitation worth stating: a curved or heavily faceted window is treated as its
largest flat face, which is wrong for curtain walling. Recorded here rather than
discovered later.

### D9 — Context building extent

Radius cutoff, and whether approved-but-unbuilt developments are included.

*Implemented, default unlimited.* `--context-radius` drops occluders beyond that many
metres, measured from the analysed spaces rather than the file origin, which in Archicad
is often an arbitrary survey point. With no radius given the header says "context radius
unlimited" rather than staying silent. Approved-but-unbuilt developments are whatever
the IFC contains; there is no separate mechanism yet.

### D10 — Vegetation

*Implemented, and it has a published basis.* Vegetation is excluded and the header says
so. This is not merely convention: the NSW technical note defines solar access as
sunlight "without obstruction from other buildings or impediments, **not including
trees**", so excluding vegetation is what the regulation asks for.

---

## Implemented, defaults still awaiting confirmation

### D11 — Sample weighting across the assessment window

**Implemented with the proposed default; still needs your confirmation.**
`core.analysis` offers `TRAPEZOIDAL` (the default) and `UNIFORM`, and the choice travels
on every `SunlightResult`. Switching the default is a one-line change until a ruleset
depends on it.

Not in the brief's list, but found while writing `assessment_times`, and it is the same
class of error.

09:00–15:00 at a 10-minute step yields **37** instants, not 36, because both endpoints
are included. Multiplying a count of sunlit instants by the timestep therefore reports
up to 370 minutes of sun in a 360-minute window — an apartment can come out at 6.17
hours. It is a small bias, always optimistic, and it lands right on the 2-hour
threshold that decides compliance.

*Proposed default:* trapezoidal weighting, so the two endpoints count half. That
preserves the 37 published sun positions, totals exactly 360 minutes, and is the
standard treatment. The alternative — half-open intervals with 36 samples — is also
defensible and simpler; it just discards the 15:00 position.

Whichever is chosen must be stated in the output header, not left implicit.

### D12 — `continuity`: cumulative versus continuous

**Implemented as proposed; still open for confirmation.** `cumulative` is set in
`rules/rulesets/nsw_adg.yaml`, printed in every output header, and carried on every
result record alongside the ruleset name and version. Switching to `continuous` is a
one-line YAML edit and needs no code change, which is proven by a test.

Councils differ; some DCPs require an unbroken duration. It must never be an invisible
assumption, because the same building passes under one reading and fails under the
other.

---

## Settled during massing mode

### D20 — `rhino3dm` as a validation-only reader

*Alternative: compare against an IFC re-export of the same scheme.*

The reference Ladybug study was run on `.3dm` geometry. Comparing against an IFC
re-export of it would introduce geometry differences that appear as a systematic
offset — indistinguishable from an engine error, in the one check the project's
credibility rests on. So `ingest/rhino.py` reads the 3dm directly.

`rhino3dm` sits in the dev group beside `pvlib`, is imported lazily, and is a pure
openNURBS wheel needing no Rhino installation or licence. `core` stays numpy-only. The
product still ingests IFC; this is not a second supported input.

Two things that took finding. Rhino stores NURBS Breps, which `rhino3dm` cannot
tessellate — but it *can* reach the render mesh Rhino already cached, and the API is on
`BrepFace.GetMesh`, not on `Brep`. And a fresh `File3dm()` defaults to **millimetres**,
so writing metre coordinates without setting the unit system makes every length 1000×
too small and every area a million times too small.



### D17 — Massing stage measures facade *area*, not apartments

*Alternative: extend the per-apartment metric downward. Not possible.*

The office's massing decks report **"areas on facade get sunlight hours on 21 Jun
>2hrs"** as a percentage, and that is the fitness goal an optimisation run maximises
(29.7% → 38.8% on the reference scheme). It is a share of **square metres**.

The ADG's criterion is a share of *apartments*, and at massing stage there are no
apartments — no Zones, no windows, just a mass. The per-apartment metric therefore
cannot be computed at all, and the area share is not an approximation of it but a
different measurement that happens to use the same 2 hour threshold.

They are never quoted for one another. `sun-study massing` prints an area share and its
header says in words that it is not a compliance figure; `sun-study run` prints the ADG
verdict. The threshold still comes from the ruleset, so both stay anchored to the same
cited number.

### D18 — Samples carry their area, and bands are area-weighted

Every square-metre figure in those decks depends on knowing how much surface each
sample stands for. `SamplePoints` therefore carries `areas`, and `band_by_area` weights
by it rather than counting samples. The two agree only when every sample represents the
same area, which is true of a regular grid on one window and never true of a
triangulated massing.

The band scheme matches the published one exactly, including two details that are
load-bearing: `0hr` is held **separate** from `0–2hrs` (a surface receiving nothing is a
different finding from one receiving forty minutes, and only the former counts for ADG
criterion 3), and the `>2hrs` roll-up is **inclusive** of exactly two hours because the
criterion reads "a minimum of 2 hours".

### D19 — Massing runs default to a 1 m grid

*Alternative: keep the 200 mm developed-model default.*

An optimisation run evaluates hundreds of variants. At 200 mm a facade of roughly
18,000 m² is about 445,000 samples and several minutes per variant — most of a day for
a full run. At 1 m it is about 18,000 samples and a few seconds.

A test asserts the coarse and fine settings agree on the headline share to within 3
percentage points, so the fast setting is not reporting a different building. The
spacing used is printed in the banner and written into every output header, because a
coarse number quoted as a fine one is exactly the failure this project exists to avoid.

---

## Settled during M3

### D15 — Reading the published wording into a per-apartment verdict

*Milestone M3.*

The ADG states the criteria but not how to turn them into a yes or no for one
apartment. Three readings are needed, and because they are readings rather than
regulation they live in a separate `interpretation:` block in the ruleset, are
configurable, and are printed in every output header next to — but visibly distinct
from — the criteria themselves.

**`compliance_requires: both`.** "Living rooms *and* private open spaces of at least
70% of apartments" reads as both having to meet the minimum, so an apartment is
governed by whichever of the two is worse. The fixture's L00-A is exactly this case:
its balcony clears two hours, its living room does not, and it fails.

**`no_sunlight_requires: both`.** Criterion 3 speaks of the *apartment* receiving no
direct sunlight, so it counts only when nothing the apartment has receives any.
`either` would count an apartment whose balcony is in full sun but whose living room is
not, which is a materially harsher rule.

**`apartments_without_open_space: living_room_only`.** Not every apartment has private
open space. Assessing such an apartment on its living room alone is the common reading;
the alternatives are to exclude it from the denominator or to fail it outright, and
which is right is a project-level question. A studio with no balcony is a different
case from one whose balcony never sees the sun, so the two are never collapsed —
`None` and `0.0` stay distinct all the way into the CSV, where the former is blank.

### D21 — Results are written as `string`, not `boolean`, property values

*Milestone M5. Alternative: declare the pass/fail columns `boolean` and guess the literal.*

`SetPropertyValuesOfElements` takes a **display string** and lets Archicad parse it into
the property's declared type. For numbers that is safe and checkable: Tapir's
`PropertyConversionUtils` (in `PropertyCommands.cpp`) hard-codes a `.` decimal
delimiter, metres, square metres and decimal degrees, so `"2.35"` means 2.35 hours
whatever the project's unit preferences are set to. That is read out of the source, not
assumed.

Nothing anywhere states what string a **boolean** property parses from — `"true"`,
`"1"`, a localised `"Yes"`, or something else. A wrong guess does not error; it either
refuses the value or, worse, lands the opposite of the truth in a compliance column. So
`Meets Minimum`, `No Direct Sunlight` and `Counted in Compliance` are `string`
properties holding `Yes`/`No`. A string set from a string cannot be misparsed, and the
columns still sort and filter in an Archicad schedule.

`test_no_property_is_declared_boolean` holds this in place. It can be revisited once
someone at a workstation confirms the literal — that is on the checklist in
[`archicad.md`](archicad.md).

### D22 — Geometry travels by IFC; the JSON API is used for everything else

*Milestone M4. Alternative: read geometry over the Tapir API and skip the export.*

Tapir can return element geometry, so a direct read is possible. It is still the wrong
choice. The IFC path is the one covered by a committed fixture, a golden file and a
validated end-to-end comparison; a second geometry route would need all of that
duplicated, and would silently diverge from the first the moment an Archicad IFC
translator setting changed. The export is also the same file the office already
produces by hand, so what the tool analyses is what a colleague can open and check.

The consequence is that Archicad's own georeferencing is not the source of truth —
the IFC's is. That is deliberate, and it is what makes the north cross-check possible:
two independent statements of the same fact, with disagreement fatal.

### D23 — Archicad's north angle, and why the cross-check compares sums

*Milestone M4. Opened as an assumption; **closed by measurement** on an Archicad 26
project.*

`GetGeoLocation` returns `north` in radians and documents nothing else. The add-on
sources, the JSON schemas and the Grasshopper components are all silent on whether the
angle runs clockwise or anticlockwise, and from which axis. This shipped as a named
guess, `ASSUMED_NORTH_SENSE`, deliberately load-bearing on nothing.

A real export settled it. Three independent numbers out of one nine-storey AC26 model:

| Source | Value |
|---|---|
| `GetGeoLocation` | `north = 0.856118 rad` = 49.0518° |
| `IfcSite` `RefDirection` | `(0.755304, 0.655374)` = `(sin 49.0518°, cos 49.0518°)` |
| Walls, measured in world coordinates | 40.948° = 90° − 49.0518° |

So **`placeInfo.north` is the angle of true north measured counter-clockwise from the
project +X axis, in radians**, and the bearing of project +Y is `degrees(north) − 90`.
The mirrored convention predicts walls at 130.9°; they were at 41°. Two further checks
agree: the offset makes Archicad's default north π/2 rather than 0, which is what
"true north runs along project +Y" ought to report, and substituting all three numbers
into the cross-check balances to 1.6 × 10⁻⁵ degrees — the rounding on six decimal
places of radians.

**The same file exposed a false positive in the cross-check**, which matters more than
the constant did. Archicad reports north in the *project* frame. An IFC export need not
be in that frame: the "Survey Point" model position rotates the geometry through
`IfcSite`'s placement and then writes `TrueNorth` as `(0,1)`, because the world
coordinates it produces genuinely are north-aligned. Comparing Archicad's angle against
`TrueNorth` alone rejected a completely correct export — 49° against 0°.

What is comparable is the total rotation from project frame to true north:

```
project +Y bearing  ==  TrueNorth bearing  -  site placement rotation
```

That identity holds under both model-position options without having to detect which
was used, because whichever half of the file carries the angle, the sum is unchanged.
`ingest.ifc` therefore records `site_rotation_deg` alongside `true_north_bearing_deg`.

**The analysis still uses `TrueNorth` alone**, and must: it reads world coordinates,
which already have the site placement baked in. Adding the rotation there would count
it twice. `test_the_site_rotation_does_not_reach_the_analysis` pins that, and
`test_a_survey_point_export_is_not_reported_as_a_mismatch` pins the false positive
using the measured numbers above.

### D24 — Living-room glazing can be marked on the opening, not the room

*Milestone M4. Extends D6 rather than replacing it; both routes ship.*

D6 identifies a living room by naming the Zone. That works when a practice zones by
*room*. It cannot work at all when a practice zones by **unit**, which is common: there
is no living-room Zone to match, and matching the unit Zone would count every window in
the apartment — bedrooms, bathroom, kitchen — as living-room glazing. That does not
fail. It returns an optimistically wrong number, which is the exact failure this project
exists to prevent.

`SceneConfig.livable_opening_suffix` is the second route. An opening whose ID ends with
the configured marker is living-room glazing, and the space it serves becomes an
apartment. One practice uses `_L`; the tool takes whatever suffix it is given and echoes
it on every run.

Three details, each learned from a real export rather than assumed:

**Doors are in the default `livable_opening_classes`.** A living room's glazing is
usually a balcony slider, which Archicad models with the Door tool. In the reference
project 110 of 252 marked openings were `SD2.x_L` doors — reading windows alone would
have measured 44% less glass and reported it as the whole.

**The marker must be a genuine suffix.** The same practice's library contains
`D06L_Bathroom cavity slider_Livable`, where the trailing `L` means something unrelated.
Matching a bare final letter would sweep in a bathroom door.

**`_read_space_boundaries` had to learn about doors too**, or every marked slider would
fall through to the geometric fallback.

**What the marker means, confirmed by the practice that uses it:** `_L` marks the
openings of *rooms that require sunlight* — habitable rooms. It is a **room-level**
marker and is unrelated to the unit-level `Liveable` / `Adaptable/Livable` properties in
the same project, which record the accessible-housing standard.

**That is wider than ADG 4A-1, which is about living rooms specifically**, and the
difference is not academic. An apartment whose bedroom faces north and whose living room
faces south passes on the bedroom's sun if the two are pooled. The arithmetic in the
reference project points the same way: 252 marked openings across roughly 91 apartments
is 2.8 each, where living-room-only would give one or two — a slider and perhaps a
window — and living-plus-bedrooms predicts about 257.

So the tool reports the distribution rather than assuming either reading.
`_openings_per_apartment` histograms how many marked openings each apartment received
and prints it in the run banner, because that single line says which criterion the
result actually answers and it is invisible in a compliance percentage. Two openings per
apartment is a living-room convention; three or four in a two-bedroom apartment is a
habitable-room one.

Narrowing habitable-room glazing down to living rooms needs a second signal the model
does not yet carry. The balcony slider is a good proxy — the room you step out from is
the living room in nearly every apartment — but it is a proxy, and it is not offered as
a default.

### D25 — Scene selection can key on Archicad layers

*Milestone M4.*

Practices run their modelling standards on layers. A layer matrix says *"all 3D context
elements outside the site boundaries go here"* and *"unit zone duplicate, used to
schedule SEPP 65"*; it promises nothing about what any individual object is called. So
selecting by name asks the wrong question, and a neighbouring building imported from a
survey will not be named "Context".

Layers survive Archicad's IFC export. `IfcPresentationLayerAssignment` points at
representations rather than at products, so the mapping is walked backwards — verified
on a real export, 18,202 products resolved, names verbatim (`01 | Wall.External`).

Three selections can now be keyed on them: which zones are apartments, which are private
open space, and which elements are context. The first matters most: a real project
carries unit zones, GFA zones, NLA zones, storage zones and a SEPP 65 duplicate set, and
assessing all of them inflates the compliance denominator without looking wrong.

**Matching is strict, and a filter that selects nothing is fatal.** Layer names carry
punctuation nobody reproduces from memory — the real project's `06 | Zone.Units` typed
as `06|Zone.Units` matches nothing — and quietly selecting zero zones would report a
building with no apartments as a result rather than as a typo. `SceneConfigError` names
what was asked for and lists the layers the file actually contains. Loose matching was
considered and rejected: a visible failure is cheaper than two layers silently
collapsing into one.

**Zones and slabs are gridded differently, and getting this wrong is invisible.** A
balcony slab is a solid whose walking surface is its top face. A balcony Zone is a
*void*, and its top face is the underside of whatever is above — gridding that puts
every sample a metre into the storey overhead and still returns plausible hours. A Zone
is therefore gridded on its floor, with the sample normals flipped back up.

### D26 — The diagram is drawn natively, on the floor plan, on its own layer

*Milestone M5. Alternative: render an image and place it on the sheet.*

A number in a schedule is the record; a coloured plan is what gets looked at. So the
tool draws one — but as Archicad elements, not as a picture.

`CreateHatches` (Tapir 1.5.7) takes a polygon, and `GetDetailsOfElements` returns each
Zone's `polygonOutline`, so the fill is the apartment's real shape rather than a
bounding box. Each lands on the Zone's own `floorIndex`, which gives a per-storey
diagram set rather than one flattened plan. An exported image would print at one scale,
ignore the pen table, and be unfixable by the person holding the drawing.

**Pens, not colours, and that is a feature.** `CreateHatches` takes pen *indices*. A
practice runs a pen table — `00 FA Pens` in the reference office — and a diagram drawn
from it stays consistent with everything else on the sheet, where an imported analysis
palette would not. Which pen carries which band is then read out of the project itself
rather than configured; see [D27](#d27--the-pen-is-derived-from-the-colour-not-configured).

An override naming a band that does not exist is an error rather than a no-op: `--pen
'2-3 hours=42'` — "hours", not "hrs" — would otherwise draw the defaults and look
entirely correct.

**Re-running replaces.** Everything goes on one dedicated layer and the previous run's
Hatches and Texts are deleted first. Without that a second run doubles up: the new fills
land exactly on the old, the plan looks unchanged, and the stale colours underneath are
what print if the top layer is ever hidden. Deletion is scoped to the two element types
this tool creates, so anything else a person put on the layer survives.

**The join is shared with the write-back.** `match_apartments` runs once and feeds both
the property values and the fills. Two independent joins over the same data would agree
almost always, and the time they did not would be a diagram whose colours belonged to
the neighbouring apartments.

Two limits, reported rather than hidden. `CreateHatches` takes a single contour, so an
apartment wrapping a lift core is drawn over the void — the run says how many. And
curved zone edges become straight segments between their nodes.

**Version gating is separate.** `CreateHatches` needs 1.5.7 where the rest of the
package needs 1.5.1, so `require_tapir_at_least` gates drawing on its own. Someone who
wants the numbers should not be blocked by a picture they did not ask for.

### D27 — The pen is derived from the colour, not configured

*Milestone M5. Supersedes the "defaults are a stated guess" half of [D26](#d26--the-diagram-is-drawn-natively-on-the-floor-plan-on-its-own-layer).*

A pen index means nothing outside the pen table it came from. Pen 92 is a mid blue in
one office and a hairline black in the next, so any hard-coded default is guaranteed
wrong in somebody's project — and wrong in the worst way, because it draws a complete,
plausible diagram in colours nobody chose. Nothing downstream catches that. Asking every
new user to supply seven `--pen` numbers before their first run is the other way to be
wrong: it makes the tool feel broken out of the box.

The colour is the part that everybody already agrees on. The seven band colours were
decoded from the reference study's own legend during the Ladybug validation — by
integrating area per colour until the published table reproduced exactly — so they are
measured, not chosen. So the colour is the input and the pen is looked up: read the
project's active pen table over `GetPenTables`, and give each band the nearest pen by
Euclidean RGB distance.

**The distance is reported, because `min()` always answers.** A palette with no yellow
in it still returns *a* pen for the 3–4 hour band, and the only sign that the answer is
poor is how far it had to reach. Each run prints the mapping with a quality label —
`exact`, `close`, `POOR MATCH` — and a poor match names the `--pen` override that fixes
it. Explicit overrides are applied after matching, so one band can be corrected without
losing the other six.

**The assignment is one-to-one, and that took a real project to notice.** Matching each
band independently is the obvious implementation, and on the first office pen table it
put the 3–4 and 4–5 hour bands both on pen 124: their reference colours are only 30
apart, and the palette had a single amber nearest to both. Distinct bands drawn in one
colour make the plan unable to show where the four-hour line falls — and it looks
finished, so nothing prompts a second look. So pens are claimed globally: every band–pen
pairing is ranked by distance, the closest wins, and that band and that pen both leave
the pool. Greedy rather than optimal — with seven bands it is within a hair of the best
assignment, and "closest pairing first" is a rule a person can follow when checking why
a band got the pen it did.

Where there are fewer pens than bands the tail keeps its default rather than reusing a
pen. An incomplete mapping that says so beats a complete one that hides a boundary.

**Distinct pens are still not distinct colours.** A palette can hold two ambers a hair
apart, and a one-to-one assignment will use both — technically correct, unreadable at
the boundary. So a separate check reports any two bands whose assigned pens are closer
than `INDISTINGUISHABLE_RGB`. That threshold is 30, measured rather than chosen: it is
the tightest adjacent pair in the reference legend itself, so anything closer is a
finer distinction than the published study asks a reader to make.

Plain Euclidean RGB, not a perceptual metric. The job is picking the obvious match out
of a palette of a few hundred, not ranking near-misses, and a metric nobody can compute
in their head is harder to argue with when it is wrong.

Two failure modes are deliberately not fatal. A project that lists no pen table warns and
keeps the guessed defaults rather than refusing to draw. And when several pen tables
exist but the build will not say which is active, the first is used — not knowing is a
worse reason to stop than drawing from the table that is almost always the only one.

### D16 — There is no `rules/nsw_adg.py`

*Milestone M3. Deviation from the brief's architecture sketch, stated deliberately.*

The brief's §4 layout lists `rules/nsw_adg.py` for "ADG assessment logic", but §5.7
says "the engine reads a ruleset; it does not know what 'ADG' means". Those pull in
different directions and §5.7 is the sharper statement, so the code follows it: the
engine is `rules/assessment.py` and everything ADG-specific is data in
`rules/rulesets/nsw_adg.yaml`.

A module named after one jurisdiction is exactly where the next council's threshold
ends up hardcoded. Adding a DCP that requires three continuous hours should be a new
YAML file and no new code, and a test proves it is.

### D28 — The sheet is made through the View Map, not by drawing into a worksheet

*Milestone M5. The last step of the practice's own described sequence.*

The workflow as described ends "copy everything in a worksheet, the plan and create
legend in worksheet". Taken literally that means creating the fills *inside* a Worksheet
database, and Archicad's API will not do it: `CreateHatches` takes a layer and a storey
but no database, so it draws into whatever is currently active. There is no
`SetActiveDatabase` in the add-on. The only way to honour the literal reading is to ask a
person to open the worksheet first and then run the tool — an implicit precondition that
fails silently, drawing an apartment diagram into whatever happened to be on screen.

So the fills stay on the floor plan, where the practice already agreed they could live
("it can be in a floor plan of course in own layer"), and the sheet is made from that:

    GetNavigatorItemTree     1.1.7   find the storeys that carry fills
    CloneProjectMapItemToViewMap
                             1.1.7   a View per storey, to place from
    CreateLayout             1.4.0   the sheet
    CreateDrawings           1.4.0   the plan on the sheet, at a stated scale

**This is better than the literal reading, not merely possible.** A Drawing placed from
a View stays *linked*: re-run the study, the fills change, and the sheet updates itself.
Geometry copied into a worksheet is a snapshot, and a snapshot of a compliance diagram is
the exact failure this whole tool exists to remove — a picture that was true when it was
made and silently is not any more.

**Storeys are matched on the floor number, not the name.** A Story navigator item carries
its floor number in `prefix`, which is the same integer `DrawReport.storeys` reports.
Storey naming is a practice's own business — `Level 08`, `L08`, `08 RESIDENTIAL` — and a
tool matching on it finds nothing the first time a project names them differently.

**Nothing is deleted and nothing existing is edited.** A re-run creates a *new* Layout.
A sheet can carry a title block, notes and a revision history that nobody wants
regenerated, so tidying up is a person's decision; the run names what it made so there is
something to tidy up by. This is the opposite of the drawing layer's policy, and
deliberately: that layer is the tool's own and nothing else goes on it, while a Layout is
shared ground.

**A failed sheet does not fail the run.** By the time layouts are attempted the numbers
are written and the fills are drawn — those are the deliverable. Losing the convenience
on top is worth a warning, not an exit code.

### D29 — Rooms are label objects, matched to apartments by position and storey

*Milestone M6. Settled by measurement on a real project, not by convention.*

A Zone in this practice's projects is a whole apartment **unit**. The rooms inside it are
not Zones at all — they are GDL label objects (`Room Name and Size Label 19`) carrying a
short code in the `room_txt` parameter. Measured on the reference project: 329 such
labels, 299 with a code, and the vocabulary is

    K 33 · S 32 · LY 29 · L/D 29 · EN 29 · B 29 · B1 28 · B2 28 · B3 26 · ST 18 · UT 9

Three of those read backwards from the obvious guess, and all three were settled by
looking at a typical floor plan rather than by inference: **`ST` is study, `S` is
storage, and `B` is the bathroom** — the bedrooms are `B1`, `B2`, `B3`, drawn with beds
in them, while `B` is a 1.8 × 3.1 room beside the ensuite. A letter is not a
description, and a bedroom is habitable where a bathroom is not.

`L/D` is living/dining, and ADG 4A-1 is about living rooms, so **that code is the only
thing in the model that separates the room the standard cares about from the rooms it
does not.** Neither the Zone nor the window carries it.

The vocabulary is built in rather than configured, because it was measured. `--living`
only *adds* codes; it cannot remove one, since a caller able to replace the measured set
would silence it invisibly. Two of the codes read backwards from the obvious guess and
were confirmed by the practice: **`ST` is study, `S` is storage.** Neither is a living
room, so ADG 4A-1 is unaffected today — it would matter the moment a ruleset asked about
habitable rooms. `BP` remains unclassified because nobody has said what it is, and every
unrecognised code is printed each run: an unclassified living room is simply not
assessed, and no other line of output would say so.

The parameter name was found rather than guessed. `archicad-objects --parameter` exists
for exactly that: parameter names belong to whoever authored the library part, and every
office library names them differently.

**The join is geometric, and the storey half of it is not optional.** A label is
annotation: nothing in the model relates it to a Zone. So a label belongs to the
apartment whose outline contains its point — *on the same storey*.

**Containment alone is too strict, and the failure was one-sided.** On the reference
project, strict containment matched 75 rooms into 10 of 10 apartments — every ensuite,
bedroom and kitchen — and **not one of the 14 living rooms on those same storeys.** That
is not a coincidence: a label is dragged to wherever it reads well on the drawing, and
for the biggest room in a plan that is often past the wall the zone stops at. Requiring
containment therefore lost precisely the rooms ADG 4A-1 is about, while looking like it
had worked.

So a label outside every outline is attached to the *nearest* apartment on its storey,
within `DEFAULT_TOLERANCE_M`. Every use of the tolerance is reported with its distance,
because each one is a judgement made on a person's behalf.

**Reporting the distances immediately falsified the reasoning above.** The measured
reaches were **0.00 m to 0.30 m, median 0.00 m** — the labels are not dragged anywhere,
they sit *exactly on* the outline, and a point on an edge is neither in nor out by a
strict test. Coincident geometry, not loose draughting. The tolerance is therefore 0.5 m
rather than the 1.5 m first guessed: past the worst case observed, and too small to reach
into a neighbouring room, since no habitable room is a metre wide. A tolerance that spans
a real room would eventually attach a bedroom to the flat next door and never say so.
`--tolerance 0` restores strict containment.

**A flat has one living room, so several means the zone is wrong.** With the tolerance in
place the reference project matched 145 labels into 10 apartments — a median of 11 rooms
each and 30 in the worst. Those are not apartments. `UNIQUE_ROOM_CODES` names the rooms a
unit has exactly one of (living, kitchen, laundry, ensuite; *not* bedrooms, since `B1`,
`B2` and `B3` are already distinct), and a zone holding two of any of them is reported.
The cause is a zone outline spanning several units, or apartments sitting on a layer the
run did not read — and either way every downstream number is wrong while still reading as
plausible, which is the failure mode this whole document exists to prevent.

The storey test is what makes this safe. These labels live inside hotlinked unit-type
modules whose masters are parked above the building; the reference project has three such
sets, at roughly 64 m, 158 m and 280 m, on storeys 9–14, 38–39 and 71–76. **A master's
label sits at the same X and Y as the placed instance it came from.** Point-in-polygon
alone therefore matches it to a real apartment — confidently, silently — and every
apartment ends up holding two or four copies of every room. Comparing storeys is the only
thing that tells the copy from the original, and there is a test named after that trap.

**Codes are configuration, echoed every run.** `--living` defaults to `L/D` and the room
mix found is always printed, because which code means "living room" is a practice's own
business and a wrong one moves the headline percentage without any other symptom.

Two consequences worth stating plainly. An apartment with no label in it cannot be
assessed against 4A-1 at all — the run names those rather than assuming the whole unit is
a living room. And labels with a blank code are dropped rather than counted as unnamed
rooms; 30 of 329 were blank, and a room with no name cannot be classified as anything.

---

### D30 — Parked hotlink masters are cut by height, not by layer

`--exclude-above <metres>` drops every element whose geometry lies **entirely** above a
stated height, spaces included.

The earlier advice, recorded above and in `archicad.md`, was to exclude the hotlink
layers from the export. On the reference project that is not possible: the masters carry
the *same* layers as the real building. `01 | Wall.External` is the tower's external wall
and the master's external wall, and no layer combination separates them.

What does separate them is height. The reference project's real building occupies z 57 m
to 85 m; its masters sit at 157–163 m (`L1`, `L2-L3`), 166–179 m (`CORE A`, `CORE B` and
their variants) and 262–281 m (`3B - T01`, `4B - T01`, `3B - Penthouse` and the rest).
Cutting at 100 m removes 1,500 elements and, with them, **four Zones that had been
counted as apartments** — the master copies of the unit type, which matched the apartment
filter as exactly as the real ones did and brought their own marked glazing with them.

Cut once, at the model, before anything is selected. Doing it to the occluder set alone
would leave those four Zones in the denominator: a run would then report 14 apartments
where the building has 10, and the four extras would carry sunlight figures measured
90 m above the site.

**Entirely above, not partly.** A roof that crosses the plane is kept. The threshold is a
project coordinate, which is exactly what the existing overhead warning prints, so the
number can be read straight off a run that did not use the flag.

Height, not storey name, because a storey filter would need the office's own storey
naming to be stable across projects and it is not — `L1` here is a master, `LEVEL 01` is
real, and the next project will use neither.

---

### D31 — Filtering the apartments must not move their numbers

Selecting which Zones are apartments is a *denominator* decision. It changed the
numerator, and silently.

Windows resolve to the space they serve by nearest bounding box, and that search ran over
the surviving spaces only. Filter an apartment out and its glazing goes looking for a new
home: on the fixture, restricting a run to `Apartment L00-A` doubled its window count and
took its living room from **106 minutes to 202** — a fail turned into a pass by naming one
zone. Balconies did the same through the level-matching owner search.

Resolving against every room instead is the obvious repair and it is worse. A marked
living-room slider sits in the wall *between* the unit Zone and its own balcony Zone, near
enough to equidistant that the balcony wins as often as not, and the glazing is then
dropped as somebody else's: 3 of 40 marked openings on the reference project.

So a window keeps the apartment it resolved to unless a room outside the run is **clearly**
nearer — `UNASSESSED_OWNER_MARGIN_M`, 0.5 m — or unless an `IfcRelSpaceBoundary` names
that outside room, which is the export stating the answer outright and beats any distance.
Open space is decided the other way round, over every room including the excluded ones,
because what settles a balcony is vertical (the apartment stands on top of it) and no
distance margin can separate a balcony from the ceiling it is flush against. One dropped
that way is reported as `another-room` rather than merged into the communal count.

---

### D32 — The per-instant series is kept, because "when" is not recoverable from "how long"

`sunlit_matrix` has always produced an `(n_points, n_instants)` boolean, and
`_durations` has always collapsed it to two floats per apartment and dropped it.
That is everything the assessment needs and nothing a drawing needs: a study
sheet showing 09:00, 09:15, 09:30 cannot be reconstructed from "106 minutes".

`core.analysis.lit_share_per_instant` reduces the matrix to
`(n_parents, n_instants)` — the **area-weighted** share of each element's
glazing or open space in sun at each instant — and `PipelineResult.instants`
carries it out with the clock times beside it. Cost is one float per apartment
per instant; a 200-apartment job at 37 instants is 60 kB.

**Area-weighted, not sample-counted**, for the same reason durations are: a 6 m
slider and a 0.8 m highlight window in one room are not one vote each, and
counting samples flatters a room whose real glazing is in shadow.

**It agrees with the compliance number by construction** and there is a test
that says so: with equal sample areas, the share summed over instants against
the same weights *is* the cumulative duration. A drawing that disagreed with
the schedule printed beside it would be the worst failure this tool could have,
so the two are tied to one matrix rather than computed twice.

The share is clipped to `[0, 1]`. It is a fraction by construction, but a sum
divided by itself lands a hair above 1.0 for a fully lit element and no caller
should have to know that.

---

### D33 — D28 was right about the mechanism and wrong about the limit

D28 states: *"There is no `SetActiveDatabase` in the add-on."* There is no
command by that name, but `ChangeWindow` does the same job —
`{"databaseId": ..., "windowType": ...}` calls
`ACAPI_Database_ChangeCurrentDatabase`, which is precisely what element creation
follows. Measured live: a fill created with a worksheet active lands **in the
worksheet** and is absent from the floor plan.

So the literal reading of the office workflow — draw the study into a worksheet
— *is* reachable, and D28's conclusion has to rest on its second argument
rather than its first. That argument still holds and is the stronger one: a
Drawing placed from a View stays **linked**, so re-running the study updates the
sheet, while geometry drawn into a worksheet is a snapshot. Both are now
offered; the linked route stays the default.

Two limits decide how a worksheet target must be exposed, and both are
measured rather than assumed:

- **The worksheet has to exist already.** One created in the same session
  cannot be activated — `-2130313110`, before and after `RebuildView`, whether
  the id comes from `CreateWorksheets` or from the navigator. So the tool names
  a worksheet and asks for it to exist, rather than making one and drawing into
  it.
- **A worksheet has no storeys.** `floorInd` is meaningless there, and six
  storeys of fills drawn into one worksheet land on top of each other. A
  worksheet target is therefore per storey, or it is one storey only.

See `archicad.md` for the measurements.

---

### D34 — The patch is drawn on the floor, and the compliance number is not read off it

`--patch-grid` grids the floor of every assessed apartment and its open space,
casts against an occluder set with the **glazing removed**, and draws the lit
cells. That is a second question about the same building, not a refinement of
the first, and the two are kept apart on purpose:

| | Assessment | Patch |
|---|---|---|
| Surface | the glazing plane | the floor |
| Occluders | everything, glazing included | glazing removed |
| Grid | 200 mm | 250 mm |
| Answers | did this apartment get two hours | where was the sun at 09:15 |

**Nothing about compliance changed.** The ADG figure still comes off the
glazing, still by the route the golden file and the pvlib cross-check cover.
The patch is a drawing, and a drawing that quietly became the compliance
number would be the worst of both -- a coarser grid, a different surface, and a
threshold nobody agreed to.

**The glazing has to come out of the occluder set** or the answer is trivially
"no sun indoors, ever": a window exported from Archicad is a solid, so the pane
shades the room behind it. The opening in the wall is a real hole in the wall
mesh, so removing the glazing leaves the sun a way in and leaves every wall,
sill, reveal and balcony above still blocking it. Measured on the fixture:
2244 lit floor cells with the panes solid, 2409 with them removed.

**Rectangles, not a contour.** Marching squares, alpha shapes and polygon
unions all want a dependency this project has ruled out, all produce polygons
with holes, and `CreateHatches` takes a single contour and no holes. The grid
is already a set of squares: merging lit cells into runs and merging identical
runs across rows tiles the patch exactly, with no dependency and nothing lost.
The stepped edge that results is not an approximation of the patch -- it is the
sampling resolution, drawn honestly, and the office's own reference drawings
have the same edge for the same reason.

**Sampled at 50 mm, not at the 1 m open-space plane.** A patch is a picture of
sun on the floor, and under a 20 degree winter sun a metre of height is 2.7 m
of displacement -- the patch would be in the wrong room.

---

### D35 — The series is one row per level, and the level comes from the geometry

A Worksheet has no storeys. Six levels of apartments drawn at their own
coordinates therefore land on top of each other, and the tile becomes a
composite of the whole tower: a plan of nothing.

It is also wrong *numerically*, which is what settled it. `merge_lit_cells`
snaps to a plan lattice, so cells from six levels at the same x and y merge
into one rectangle and the lit area is counted once instead of six times. The
composite reported 134 m² where the levels sum to 364 m².

So the sheet is levels down the side and time across the top, which is what a
study sheet has always been.

**The level is taken from the floor's own elevation, not from the storey the
export names.** On the reference project every `IfcSpace` comes through with
`storey` unset -- the first attempt drew all ten apartments as one row and
looked plausible. The geometry always knows what level it is on. Where a storey
name *is* present it is used as the label, and the elevation is the fallback.

---

### D36 — The study drawing goes on the floor plan, and the patch is fitted onto it

`--plan-instant` draws, per apartment and per instant: the sun patch, the
outline of the assessed area, and a text block. That is the reference
deliverable's own language, read off its drawings. The whole-day banded
diagram (`--draw`) stays, because it answers a different question -- did this
flat pass -- but it is no longer the only picture on offer.

**On the floor plan, not in a worksheet**, because the plan linework is
already there and the patch has to be read against the rooms it falls in. The
worksheet series ([D35](#d35)) is the opposite trade: the whole day at once,
deliberately abstract, with no plan under it. One layer per instant keeps the
moments separable.

**The patch has to be fitted onto the project frame.** It is computed in the
export's world coordinates and those are not Archicad's project coordinates:
an export made with the Survey Point option is already north-aligned, so the
project is rotated relative to it. `core.geometry.fit_plan_transform` fits a
rigid transform -- rotation and translation, never scale, never reflection --
over one pair per apartment, and the residual is a **refusal** above 0.5 m
rather than a warning, because a patch drawn through a bad transform lands on
the wrong flat and looks entirely plausible.

Two measurements shaped that:

* **Pair on the dwelling, not on its floor cells.** The cells include the
  balcony, which sits on one side of the flat and drags the centre by a
  different amount for every apartment: 2.96 m of residual, and the drawing
  refused for a reason that had nothing to do with the model.
* **Compare box centres, not means.** A mean is weighted by how the points
  happen to be distributed, and an outline's vertices and a grid's cells are
  not distributed alike.

After both, the reference project fits to **195 mm** across ten apartments --
under one grid cell.

---

### D37 — A floor grid is clipped to its room; a window grid is not

`planar_face_grid` grids the *bounding rectangle* of the face it picks. For a
window that is the face. For a room it is not: an L-shaped flat gets a grid
over the rectangle it fits inside, and the sun patch drawn from it reaches
into rooms the apartment does not contain.

Measured on the reference project by reading the drawn fills back out of
Archicad and testing them against the Zone outlines: **37% of the patch area
sat outside any apartment**. With `clip_to_face=True` on the floor grids, the
same check gives 129.7 m² inside and 1.9 m² out -- and that remainder is edge
cells displaced by the 195 mm transform residual, which is less than one cell.

The clip is a barycentric test against the face's own triangles, exact for a
triangulated surface and needing nothing but numpy. It is **off by default**:
a window needs no clipping, and this is not free.

It also corrects the reported areas. An unclipped grid overstates both the
floor and the lit part of it, and those figures are what the annotation prints
against each flat.

---

### D38 — A worksheet left in front empties the next export, and only a person can clear it

Recorded because this tool creates the situation and cannot undo it.

`draw_patch_series` activates a worksheet, and on AC26 nothing switches the
window back: `ChangeWindow` with a floor plan's `databaseId`, with a
`storyIndex`, or with neither, all return `{"success": true}` and leave the
worksheet on screen. `windowType: "Section"` fails outright and `"3D"` is not a
valid value at all.

What makes it dangerous is that everything *else* keeps working. Element reads
answer normally — 1,415 walls, 142 zones — because those follow the current
**database**, which did move. Only the IFC export follows the **window**, and
with a worksheet in front it writes 5.8 kB: an `IfcSite`, an `IfcBuilding`, no
storeys and no elements. The next run then fails three steps later, in the
scene filter, as `apartment zone layers matched nothing` — pointing at a layer
name that was right all along.

An earlier version of this file called that cosmetic, on the strength of one
export that came out whole. That was a single measurement against a mechanism
nobody had established, and it was wrong. The behaviour above is repeatable.

So the series is drawn **last** in a run, the run says plainly that a floor
plan must be opened before the next one, and `_connect` puts the *database*
back even though it cannot move the window.

---

### D39 — Sheet geometry: four units, and a save that makes a layout readable

Placing a Drawing correctly took four separate corrections, each of which
looked like the last one had worked. Recorded together because they only make
sense together.

**The scale is on the view; the Drawing is placed at 100%.** `CreateDrawings`'
`scale` field is a *magnification*, not a scale denominator. Passing 200 for
"1:200" put the drawing on at 20000%. The view carries the scale
(`drawingScale: 200`) and the Drawing goes on at `1.0`.

**Positions are in metres; the page is described in millimetres.**
`GetLayoutSettings` reports an A1 as `841 x 594`, and a Drawing's position is
in metres. Computing a grid from the page size and passing it straight through
put a drawing meant for x = 200 mm at x = 200 m — a quarter of a kilometre off
a sheet 0.841 m wide. Those two bugs hid each other: the magnification made
the drawing enormous, the units put it far away, and each made the other look
plausible.

**The angle comes from the Drawing tool's default**, not from the view. Every
drawing arrived at 279.9° — the project's own north — with the view's
`rotation` at 0. There is no angle field on `CreateDrawings`; it is fixed
afterwards with `RotateElements`, which takes no angle either, only a centre
and the two ends of an arc.

**Saving is what makes a layout readable.** A layout created in the current
session answers `GetDetailsOfElements` with a per-element error, which is what
made the first attempt at measure-and-move impossible — and what preceded
Archicad exiting. After `SaveProject` the same read answers normally. So the
order is: create, **save**, measure, straighten, measure again, move. Twice,
because rotating changes the bounding box and the tiling needs the new one.

`SaveProject` also means a long run can commit its work in stages instead of
holding hours of drawing in an unsaved file.

---

### D40 — The current database is not the current window, and reads follow the database

A run kept reporting zero apartments on a project holding 142 zones. The
window said `FloorPlan`; the *database* was a Layout, left there by the
previous step's `ChangeWindow`, and `GetElementsByType` follows the database.

So `ensure_model_database` does not ask what the window is. It asks whether a
read can see any walls, and switches when it cannot. The window type is
advisory; what a read returns is the fact.

The two are genuinely independent, and which one an operation follows has to
be established rather than assumed:

| | follows |
|---|---|
| Element creation (`CreateHatches`, `CreateTexts`) | the current **database** |
| Element reads (`GetElementsByType`) | the current **database** |
| Element deletion | the current **database**, but silently refuses on a hidden layer |
| The IFC export | the current **window** |

---

### D41 — A patch is drawn as one outline where that is exact, and as tiles where it is not

`trace_lit_regions` walks the boundary of the lit cells and returns one
polygon per connected patch, which is what a reader expects a sun patch to be
and what an editor can work with: on the reference project it took a banded
plan from 2,354 fills to 946.

It is used only where it is **exact**. `CreateHatches` takes a single contour
and no holes, so a patch with a hole in it can be drawn as one shape only by
filling the hole — claiming sunlight on floor that never saw any. Those fall
back to the tiled rectangles, which cover the same area exactly and only need
more of them. A drawing is a claim about sunlight, and a tidier drawing is not
worth a false one.


### D42 — An element's surface cannot be set; new geometry carries the colour instead

The reference study's facade page shows the building painted by hours of sun.
The obvious implementation is to give every wall the surface of its band. That
is not reachable through this API, and the search for it is worth recording so
nobody repeats it:

* `GetDetailsOfElements` reports a `surfaceId` only for library-part based
  elements — Objects. A Wall, Slab, Roof or Mesh reports geometry and nothing
  about its appearance, so its surface can be neither read nor written.
* `SetDetailsOfElements` reaches `floorIndex`, `layerIndex`, `drawIndex` and a
  `typeSpecificDetails` union whose `WallSettings` is purely geometric. There
  is no setter anywhere in the add-on that attaches a Surface to an existing
  element.
* `CreateMorphs` — the natural element for a coloured skin, since a morph takes
  a `surfaceId` directly — validates its input on this build and then answers
  `Failed to create morph` for every shape tried, box and explicit body alike.
  A morph is not reachable on Archicad 26 either.

What is reachable is creating geometry that already carries the colour:
`CreateSurfaces` takes an RGB, `CreateBuildingMaterials` takes a
`cutSurfaceIndex`, and `CreateWalls` takes a `buildingMaterialId`. So the
facade picture is a skin of thin walls standing 30 mm proud of the real one,
one per merged rectangle, on a layer of its own. It is native 3D — it shows in
the 3D window, in a 3D document and in a rendering — and switching the layer
off restores the model exactly.

Two smaller findings from the same session. `CreateSurfaces` answers with
attribute *ids* while a building material wants an *index*, and there is no
converting one to the other except by reading the attribute list back.
`CreateWalls` has no `layerIndex`: new walls land on the Wall tool's default
layer and have to be moved afterwards.

### D43 — A hidden layer silently refuses modification, not just deletion

D31 recorded that `DeleteElements` answers `{"success": true}` and removes
nothing when the target sits on a hidden layer. The same is true of
`SetDetailsOfElements`, which matters more than it sounds: new walls land on
the Wall tool's default layer, on the reference project that layer is hidden,
and so the move onto the tool's own layer reported success for every element
and moved none of them.

Chasing that produced a false lead worth naming. Sending `layerIndex` as a
float appeared to fix it — the int failed, `144.0` returned success — and it
had not; the layer was unchanged either way, and the float call was simply the
one made after something else had changed. The rule that catches this is the
one already in force everywhere else here: **re-read, never believe the
response.** The layers involved are therefore forced visible for the duration
of the change and put back exactly as they were, and the elements' layers are
read back before the run reports success.

### D44 — The no-sun band is spelled two ways, and reading one of them loses most of the drawing

`band_by_area` gives the no-sun band an upper bound of exactly 0.
`BandStyle` gives it `1e-9`, the tolerance below which a duration counts as
none. `_band_mask` recognised only the first, so a legend built from
`BandStyle` produced an *empty* no-sun band — silently, with every other band
correct.

On the reference facade that is 5,885 m² of wall, 83% of the elevation, and
the failure is invisible in the output: the percentages that appear all look
reasonable, and the missing band simply is not mentioned. It was caught by
totalling the bands against the surface area, which is now what the test does.
Any banding of a whole surface should carry that check.

### D45 — Surface reflectances are percentages, and a fraction renders black

``CreateSurfaces`` takes its colour as three fractions in ``[0..1]`` and its
reflectances as percentages in ``[0..100]``, truncated to whole numbers. The
two live side by side in the same object, so the natural thing — writing
``1.0`` for "full" throughout — stores ambient 1% and diffuse 0%.

The failure is a quiet one. Every band colour is stored exactly right and
reads back exactly right; the surfaces simply reflect nothing, so the coloured
model renders black and the diagram looks like a bug in the geometry rather
than in two numbers. Confirmed by probing: ``1.0`` comes back as ``1``, ``0.5``
as ``0``, ``100`` as ``100``.

Both are now sent at 100. A diagram's band has to read as its legend colour
wherever it appears rather than shading off with the angle of the face it sits
on -- that shading is a second, competing signal about sunlight in a drawing
whose entire subject is sunlight. Specular and shine stay at zero for the same
reason: a highlight reads as sun on a face that may have had none.

``DeleteAttributes`` takes ``attributesToDelete``, each entry an
``attributeType`` **and** an ``attributeId`` — not the ``attributeIds`` list
every other attribute command takes.

### D46 — Geometry built from the export must be fitted onto the project first

The first facade skin was created straight from the export's world
coordinates, and appeared beside the building and turned — the failure D30's
``PlanTransform`` exists to prevent, repeated because the massing path was
written without it. The two frames differ by the project's own rotation
(279.9 degrees here) and a shift; on this project fitting them leaves 0.175 m
of residual.

Anything created in the project from geometry computed on the export needs
that fit, not only the 2D patches that first needed it. The pairing is Zones,
because a Zone exists identically on both sides — the same room, a GlobalId in
the file and an outline in the project — and the same ``MAX_FIT_RESIDUAL_M``
guard applies: over half a metre of residual means the export is not of the
project's current state, and a wrong placement is worse than none.

The standoff that pushes the skin clear of the wall is applied in the export's
frame, *before* the transform, so it stays perpendicular to its own face.
Applied afterwards it would push every rectangle along one rotated direction.

### D47 — A 3D window answers reads with what it is showing

``GetElementsByType`` in a 3D window returned 873 of the 1,968 walls the
previous pass had drawn on the tool's own layer. The clear-out therefore
deleted 873, re-read, found none left, and reported itself finished — a
verified count that was verified against the same partial view that produced
it.

This is D40 with a sharper edge: it is not only that reads follow the current
database, it is that a 3D database's answer depends on what the view is set to
show. Any operation that has to see *all* of something forces a floor plan
first. Re-reading is still necessary and is not, on its own, sufficient.

### D48 — A wall is the only element that can be created with a material, so a flat patch is a wall lying down

Only ``CreateWalls`` takes a ``buildingMaterialId``. ``CreateSlabs``,
``CreateMeshes``, ``CreateRoofs``, ``CreateBeams`` and ``CreateColumns`` all
take a shape and no material at all -- their only route to one is
``favoriteName``, which needs a Favorite somebody made by hand. So the
horizontal half of the picture -- balcony decks, terraces, soffits, which take
more sun than any wall does -- cannot be slabs.

It can still be walls. A wall is a box: give it the rectangle's long side as
its length, its short side as the *thickness*, and 40 mm as the height, and it
lies on a deck as a coloured plate. Nothing is lost except lean, which is why
sloping faces are not panelled at all.

Grouping faces by plane had to change with it. The key was the two horizontal
components of the normal plus the plane offset, which is enough to separate
upright faces and puts a slab's top and its soffit in the same group -- both
have x and y of zero. All three components are keyed now.

### D49 — A 3D Document cannot be created, only used

There is no command in the add-on that creates a 3D Document; the nearest
names -- ``GenerateDocumentation``, ``Set3DCutPlanes`` -- do something else.
What can be done is make a *View* of one the project already has, through
``CreateViewsInViewMap``, and pin a layer combination to it.

That is worth doing rather than routing around, because the two model views
are different things. The 3D window is live: it shows the model as it is now,
turns freely, and is what somebody checks a study in. A 3D Document is a
drawing made from a 3D view, with its own pen and fill overrides and its own
dimensions, and is what goes on a sheet. An office wants both, and the tool
can supply the first outright and the second only if one exists.

### D50 — A wall shows its material only when its surface override is off, and nothing turns that off

The first coloured skin rendered uniformly grey, with every band's Surface
carrying the right colour and every band's Building Material pointing at the
right Surface -- both verified by reading them back. The cause is a third
thing: a wall's own **surface override**. With it on, the wall shows the
overriding surface and its building material's colour never appears.

Nothing in the add-on turns an override off. ``WallSettings`` is geometry
only; ``CreateWalls`` on 1.5.7 has no ``favoriteName`` field, though the
newer published schema does. What is left is the Wall tool's *defaults*, which
``CreateWalls`` inherits and ``ApplyFavoritesToElementDefaults`` can set from
a Favorite. So one Favorite, made by hand from a wall with the override
switched off, fixes every later run -- and is the only route there is.

**1.5.8 makes it a field, and the difference is whose session it touches.**
Read out of the installed ``.apx``'s own schema: every wall in ``wallsData``
now takes an optional ``favoriteName``, *"applied first, then the explicitly
given fields override them"* -- which is exactly the order this needs, because
the Favorite carries one thing (the override, off) and the band's own
``buildingMaterialId`` still has to win. ``draw_model_bands`` therefore names
the Favorite per wall when the add-on is 1.5.8 or newer, and falls back to
``apply_favorite_to_defaults`` below that. Both build the same skin. The
difference is that the defaults are shared, visible state: setting them
changes what the *next* wall a person draws by hand looks like, and it outlives
the run. A field on the request changes nothing outside it.

The check is ``has_tapir_at_least``, which answers rather than raises. A
capability with a working fallback must not become a version requirement --
somebody on 1.5.7 still gets their facade.

The existence check stays on both paths, in ``require_wall_favorite``. Neither
route refuses a name that matches nothing: the defaults route applies nothing,
and ``CreateWalls`` takes an unknown ``favoriteName`` and builds the wall
anyway. Both then produce a silently grey skin, which reads as a finding
rather than as a missing Favorite.

Worth knowing for diagnosis: ``GetFavoritePreviewImage`` renders a Favorite in
3D and returns a PNG, which is the only way from here to *see* what a created
element looks like. It is what showed the grey.

### D51 — A drawing made from a 3D source is created at a placeholder size

A Drawing placed from a plan view has its true extent as soon as the project
is saved. A Drawing placed from a 3D view or a 3D Document does not: it is
created 59 mm square and keeps that until Archicad regenerates it, which
happens when somebody opens the layout. ``UpdateDrawings`` would force it and
refuses below Archicad 27.

Two consequences. Straightening still works -- the angle is set through
``DrawingSettings`` and holds -- but tiling on the first run arranges
placeholders. And a run must therefore *not* delete and re-place the drawings
it finds, or every run resets them to the placeholder and no run ever tiles a
real size; existing drawings are reused by name and only the missing ones
placed. Open the sheet once, run again, and the arrangement uses true sizes.

Also: ``CreateLayout`` does not care that a layout of that name exists, and
will make a second. Layouts are reused by name -- unlike views, a layout
*can* be deleted, but reuse avoids needing to.


### D52 — A hidden layer is an export filter, and it fails in the wrong words

The translator exports what the current layer combination *shows*. On the
reference project, opened on a site-plan combination, all four ``06 | Zone.*``
layers were hidden and locked; the export came out at 35 MB carrying 386
walls, 92 windows, 90 slabs and **no ``IfcSpace`` at all**.

What the run then said was true and useless: ``apartment zone layers ['06 |
Zone.Units'] matched nothing``, followed by the eleven layers that *did*
export. The layer at fault is by construction absent from that list, so the
message asks the reader to notice an absence in a list of eighteen names, and
arrives only after a multi-minute export. Both diagnostics available at that
point -- the export's layers and the export's spaces -- describe the symptom.

So visibility is checked against the *live project* before the export, where
the answer is one boolean per layer. ``hidden_layers`` asks Archicad, and the
run stops in about two seconds naming the layers to switch on.

It stops rather than warns because there is nothing else it could do. Tapir
1.5.7 has no command that changes layer visibility or activates a layer
combination -- ``SetLayers``, ``SetLayerCombination``, ``ApplyLayerCombination``,
``OpenView``, ``ActivateNavigatorItem`` and ``SetCurrentWindow`` all answer
code 4010, unregistered. ``CreateLayerCombinations`` exists and is no help: a
combination that cannot be activated changes nothing. This is a hand in
Archicad, and the message says so instead of implying a flag might fix it.

A name Archicad does not recognise is deliberately *not* reported here. That
is a typo, not a hidden layer, and sending the reader to Layer Settings for a
name that is not in them is worse than silence; ``_require_matches`` already
catches it against the export, which is where the correct spellings are.

### D53 — Two sheet-building paths, and only one of them was ever fixed

The storey-plan sheet and the times-of-day sheets came out of the same run and
only one of them was right. Every correction D33 to D39 recorded had been made
in ``layout_from_views`` and none of them in ``layout_results``, so the
``Sun Study`` layout carried all three original faults at once, measured on
the reference project:

* **Positions in millimetres, sent to a field measured in metres.** Drawings
  meant for x = 140 mm sat at x = 140 m, and the sheet ran from 140 to 888
  metres across an 841 mm page.
* **The scale denominator sent as the Drawing's magnification.** ``scale`` on
  ``CreateDrawings`` is a magnification where 1.0 is 100%, so 200 asked for
  20000% and produced floor plans 187 metres wide.
* **No second pass**, so all eighteen stood at 279.9 degrees -- the project's
  own north, which is the Drawing tool's default angle.

Nobody had noticed because the run reported both sheets in the same green
line, and the one that was checked was the one that was right.

``layout_results`` is now three lines that clone the storey views, pin the
scale on them and hand them to ``layout_from_views``. A fix that lands in one
of two copies is not a fix, and the second copy is where it will be needed
next.

### D54 — A tiling has to fit the page in both directions, and a drawing that cannot has to shrink

The number of columns was chosen from the page **width** alone. Six band
diagrams 197 mm tall therefore went into one column: 1,254 mm of drawing on a
594 mm page, with four of the six off the paper and the sheet reading as
though the study had produced nothing.

Every arrangement from one column to one row is now considered, and each is
asked whether the block fits and how much of the page it wastes. What fits and
wastes least wins, and a block shaped like the page beats a strip of the same
area -- which is why six drawings that would fit in a row of six go three by
two instead.

Some drawings fit at no arrangement. A view of the coloured model arrived
1,429 x 1,256 mm on an A1, and one drawing has only one arrangement. So the
tiling also returns *what the drawings must be multiplied by* to fit, and the
sheet pass applies it. Uniformly, including to drawings that would have fitted
alone: three diagrams of one building at three times of day are read against
each other, and two at one size beside a third at another is a picture of
nothing.

The shrink is always reported, and below a quarter it is reported as a
diagnosis rather than an outcome. 14.8% is not a page slightly too small, it
is the wrong scale for the sheet, and the run says so.

### D55 — A Drawing's scale cannot be set, its magnification can, and its bounds follow neither

Three findings, and the third is the one that bites.

``SetDetailsOfElements`` accepts ``drawingScale``, answers
``{"success": true}`` and leaves the scale exactly as it was -- D43 again, in a
new place. ``ratio``, the magnification, does change. So the only handle on a
drawing that will not fit its sheet is how big it is on the paper, not what
scale it is at, which is a reason to put a study on a **no-scale** title block
rather than one that prints a figure the drawing may no longer be at.

The third: **bounds do not follow magnification.** Set a drawing to 46.9% and
46.9% is what reads back, while the bounds go on reporting the size from
before, until Archicad regenerates the drawing -- which happens when somebody
opens the layout. A pass that re-read to check its own work therefore
recomputed the full size as "bounds over magnification", got 3,050 mm from a
drawing 1,429 mm wide, and shrank it again: 46.9%, then 22.1%, halving on
every run forever.

This is the one case in this codebase where **re-reading is wrong**. What is
dependable is that bounds and magnification agree *until this code touches
them*, because Archicad drew them together; so the full size is bounds over
magnification, computed once, written once, never verified. The guard that
makes it safe is a rule rather than a measurement: a drawing already below
full size has been fitted already and is left alone, because nothing readable
distinguishes one that has regenerated from one that has not.

It costs something real. A sheet does not re-fit itself when the building
outgrows it, and the run says what magnification it left so there is a handle:
delete the drawings and let the next run place them fresh.

### D56 — A master layout is named from memory, so it is matched by its words

An office keeps dozens of masters -- seventy-one on the reference project --
punctuated every way there is: ``DA A1 - VERTICAL - No Scale`` sits three rows
from ``DA A1 - VERTICAL COVER/NO SCALE``. What a person types is "A1 no
scale".

Exact-match-or-nothing answered that by printing all seventy-one names and
stopping, which is the least useful place to put the right answer: in a wall
of text that has already scrolled past. Now the name is read as the words it
contains, every master carrying all of them is a candidate, and the one
carrying the fewest words nobody asked for wins. A tie is still a question --
two masters equally close is something only the person can settle, and either
guess puts the study on a title block meant for something else.

The one thing this cannot fix is a layout that already exists. Layouts are
reused by name, nothing in the add-on changes an existing layout's master, and
``SetLayoutSettings`` does not offer one. So a re-run with ``--master-layout``
leaves an old sheet exactly where it was, and the run now says that outright
instead of reporting the master it would have used.

### D57 — Finishing a sheet leaves you standing in it, and a Layout has no Zones

Adding the straighten-and-tile pass to the storey sheet broke every drawing
step after it. The pass has to make the layout current to work in it, and it
left it current; ``read_zones`` then read the *layout's* database, found no
Zones, and the plan transform paired 0 apartments of 10.

What the run said was "the export and the project disagree about where the
apartments are". That is D40's rule -- reads follow the current database --
arriving four steps from its cause and dressed as a geometry problem, on a
project where the export had been correct all along.

Every path that finishes a sheet now puts a floor plan back, in a ``finally``,
because the failure also happens when the sheet pass raises. The rule this
follows is the one ``ensure_model_database`` was written for: the current
database is a shared piece of the session, and anything that moves it owns
putting it back.

### D58 — A Drawing's angle field is writable, reports back, and does not turn the drawing

``straighten_and_tile`` was written with ``RotateElements``, which needs a
centre and two points on an arc to imply an angle. That was replaced with
``SetDetailsOfElements`` and a ``DrawingSettings`` ``angle`` of zero, because
the schema offers the field and one number is plainly better than an arc.

The field takes the write. It reads back as zero. The drawing does not move.

Six drawings on the reference project were reported straightened, twice, and
the sheet came out visibly crooked with Archicad's own dialog insisting the
angle was 0.00 degrees. What settles it is the ``clipPolygon``, the frame's
own corners: every one of them stood at 9.90 degrees off axis -- 279.9 modulo
a quarter turn, the Drawing tool's default angle, which is this project's
north. The office's own drawings on the same project measure 0.00.

So the angle is read from the corners and never from the field, and the turn
is ``RotateElements`` again, arc and all. This is the third member of a family
now -- ``layerIndex`` on a hidden layer (D43), ``drawingScale`` on a Drawing
(D55), and ``angle`` -- where the add-on accepts a write, stores it, returns
it, and changes nothing. Reading a value back is not evidence that it did
anything; reading the *geometry* back is.

### D59 — A layer combination cannot be activated, but it can be copied

D52 stopped the run when a layer the study needed was switched off, and said
there was nothing else it could do. Five commands had been tried --
``SetLayers``, ``SetLayerCombination``, ``ApplyLayerCombination``,
``OpenView``, ``ActivateNavigatorItem`` -- and all were unregistered.

That conclusion was right about combinations and wrong about layers. A
combination is only a set of per-layer visibilities, and those are writable:
``CreateLayers`` with ``overwriteExisting`` sets ``isHidden`` and
``isLocked``, which the facade skin already relied on to borrow a hidden
layer. What was missing was the other half -- ``GetLayerCombinations``, whose
parameter is ``attributes`` rather than the ``attributeIds`` every neighbouring
command takes, and which returns a combination's full per-layer state. Read
one, write it onto the layers, and the project is in that combination in every
way that matters to an export, without Archicad ever being asked to switch.

So the export sets its own layer state, in three steps. A base -- one of the
project's own combinations by name, usually its IFC export combination, which
is an office's own account of what belongs in an export -- or everything shown
if none is named. Then the layers the study needs are forced on, and
``--hide-layer`` forced off.

The middle step is not a refinement. On the reference project *neither*
``12 | IFC ARCH. EXPORT`` nor ``12 | IFC CONSULT. CHECK`` shows the
``06 | Zone.*`` layers, so following the office's own export settings exactly
reproduces D52: an export with no ``IfcSpace`` in it and a run reporting no
apartments. What belongs in an export and what a solar study needs are
different questions, and only the run knows the second.

Everything is snapshotted and restored in a ``finally``. Measured on a project
with 89 of 142 layers hidden and 63 locked: 94 changed for the export, all 94
back afterwards, ``06 | Zone.Units`` switched on for the export and off again
after it. The apartment figures came out identical to the run made against a
hand-selected combination, which is the check that this reproduces rather than
approximates.

The restore matters as much as the change. This tool spent three sessions
re-selecting a combination it had itself clobbered by opening its own views,
and a run that rearranges what somebody sees and leaves it that way has just
moved the problem.

Two smaller findings. ``DeleteAttributes`` will not remove a
``LayerCombination``: it validates the type name -- a wrong spelling is
refused as invalid -- and then answers ``Attribute not found`` for an id
``GetAttributesByType`` had just handed over. So combinations are reused by
name like layouts and views. And the tool records its own resolved state as a
real combination, ``SS Sun Study Export``, which changes nothing on its own
but gives the choice a name in Layer Settings that a person can inspect.

### D60 — A Text has no layer, so it lands on the office's annotation layer

``CreateTexts`` accepts a coordinate, a string, a ``height``, a ``pen``, a
``justification``, an ``angle`` and a ``floorIndex``. Probed one field at a
time: there is no ``layerIndex``, no ``penIndex``, no ``charHeight``, no
``styleName``. So a Text is created on whatever layer the Text tool defaults
to, which on the reference project is ``05 | Dims/Notes.DA`` -- one of the
office's own annotation layers for the drawing set.

That is wrong twice. The study's key is filed in somebody else's layer, and it
is outside what the next run clears, so switching the study's layer off leaves
the legend sitting on the plan with nothing to explain it.

The fix is the one the facade skin's walls already use: create, then move with
``SetDetailsOfElements``, then **read the layer back**, because that write
answers success and does nothing when either layer is hidden (D43).

Two related findings from the same probing. ``GetDetailsOfElements`` refuses a
Text outright -- ``Not yet supported element type`` -- so a text's content and
height cannot be read at all; its ``layerIndex`` and ``floorIndex`` are
readable because they sit outside ``details``. And ``Get3DBoundingBoxes``
*does* answer for a Text, which is the only way from here to find out where
one actually is. That is what located five stray probe texts at the model
origin -- which then would not delete until their layer was switched on, D31
again.

### D61 — Text height is inherited unless it is set, and the legend was spaced for a guess

The legend's rows were 1.5 m apart in model space, for a 1.0 m swatch. The
labels beside them were 1.27 m tall, because a Text created without a
``height`` takes the Text tool's default -- an office's default, set for its
own drawings, with no reason to suit a key drawn beside a plan. Consecutive
rows therefore overlapped and the legend read as one smear of text.

It is worse than a fixed error, because a text's model-space size scales with
the view: the same legend at 1:300 is half again as tall while the 1.5 m
spacing does not move.

So the height is stated rather than inherited, and the row spacing is derived
from it instead of guessed alongside it. Measured: at the stated height a
label's whole bounding box, ascender and descender included, is 0.43 m, and
rows now step by 1.5 times the taller of swatch and label.

### D62 — Moving an element off a hidden layer means borrowing that layer first

D60 moved the study's labels onto the study's layer, and every one of them
refused: ``8 of 8 legend labels would not move``. The target layer was
visible; the layer they were *created* on was not. ``05 | Dims/Notes.DA`` is
hidden on the reference project, and ``SetDetailsOfElements`` answers success
and changes nothing for an element sitting on a hidden layer -- D43, from the
other side. Every earlier instance of that trap was about the layer being
written *to*; this one is about the layer being written *from*.

So the move reads where the elements actually landed, switches those layers on
for the duration, moves, re-reads, and puts them back exactly. Which layer to
borrow is not something the caller can know: the Text tool's default is a
project's own setting, and the answer is whatever the elements report about
themselves.

Elements already on the target are left alone rather than moved to where they
are -- no write, and nothing unhidden in order to make it.

Worth knowing about the earlier runs: labels created before this fix are still
on the office's annotation layer, and the run's clean-up only ever touches its
own layer, so they are not swept up by a later run. Two hundred of them on the
reference project, findable only by ``Get3DBoundingBoxes`` because a Text will
not report its own contents.

### D63 — Layer visibility belongs to a database, not to the project

D62 left one thing unexplained: after a run the reference project's
``05 | Dims/Notes.DA`` read visible, though the borrow that unhid it restored
correctly in isolation. The conclusion recorded at the time -- that switching
views drifts the layer state and the drift needs undoing -- was wrong, and
wrong in a way that would have produced a fix for a problem nobody had.

Measured, in this order, on the reference project:

1. On a floor plan, the layer reads hidden.
2. Switch to a layout: the same layer reads **visible**. The layout's
   combination is what is being reported.
3. Write it hidden while the layout is current: the write takes effect there.
4. Switch to a floor plan and back to the layout: **visible again**. The
   combination is reapplied on every switch and the write is gone.
5. Write it *visible* while the layout is current, then switch to the floor
   plan: the floor plan reads **hidden**. The write never reached the model.

So layer visibility is not one fact the project holds. It is whatever the
current database says, each database has its own answer, and a write outside
the model is scratch that the next switch discards.

Nothing had drifted. The check that reported drift was itself run after a tour
of six layouts -- ``measure_drawings`` switches into each one -- so it read a
layout's combination and reported it as the project's. The measurement was the
bug.

Two things follow. Layer work is refused anywhere but a floor plan, rather
than answering wrongly: a snapshot taken in a layout and restored later does
not restore anything, it writes a layout's opinion over the model, which is
what ``export_state`` would have done had a database switch ever landed inside
its ``with``. And the tool has to *remember* where it is, because Archicad
will not say -- ``GetCurrentDatabase``, ``GetCurrentWindow`` and
``GetDatabases`` are all unregistered on Tapir 1.5.7 and, re-probed live,
on 1.5.8 as well, and
``GetCurrentWindowType`` answers for the window on screen, which moves
separately from the database. Every ``ChangeWindow`` in this package goes
through ``run_tapir``, so the note is taken there and cannot be bypassed by a
fifth call site.

The limit is stated rather than hidden: a person who clicks into a layout
mid-run makes the note stale, and a connection that has not moved anything
says ``None`` and is left alone.

### D64 — A layer combination is a statement about the model, so read the model

D63 said layer state belongs to a database. This is where that was already
costing something, unnoticed.

``ensure_layer_combination`` builds each sheet's combination from "the layers
as they stand", which is the right idea: everything a reader expects on a plan
stays as it is, and only the named layers are forced. But *as they stand where*
was never asked. The sheets are made in a loop, and ``layout_from_views``
leaves a layout current -- so from the second sheet onward the layers "as they
stand" were the previous sheet's layout answering with its own combination.
Each sheet inherited what the sheet before it happened to show.

The named layers were never affected: ``--hide-layer`` forces those either way,
which is why the complaint that fixed the grids and dimension layers appeared
to work. Everything the run does *not* name is what drifted, and that is most
of a project.

So the model is made current before the layers are read. That is cheap now:
``ensure_model_database`` answers from the note the connection takes on every
``ChangeWindow`` and only pays for the two reads when the tool has not moved
the database itself -- a fresh process inheriting whatever the last run left,
which is the case those reads exist for.

Two things came out of consolidating the read onto ``read_layers``, which is
what made the bug visible at all. There were four copies of "GetAttributesByType
then GetLayers" in this package. And ``LayerState`` carried only visibility and
lock, while a combination names ``isWireframe`` and ``intersectionGroupNr`` too
-- and ``CreateLayers`` writes the *whole* layer, so a field left out is a field
reset to its default. Restoring a borrowed layer had been quietly turning
wireframe off and moving the layer to intersection group 1. ``LayerState`` now
carries the whole layer, and a restore puts back what was there.

``ensure_layer_combination`` had no tests at all before this. It decides what
every drawing shows.

### D65 — The tool's output is named into the project's own numbering

``SS`` was this tool's mark on everything it made: ``SS Sun Study 09:00``,
layers called ``Sun Study.Results`` with no group at all. On the reference
project the layer groups run ``00 |`` to ``13 |``, each with a divider of its
own, and the combinations follow the same scheme. Output called ``SS`` sorts
nowhere and reads as somebody's initials.

So everything the tool creates now leads with ``14 |`` -- the next free group:
layers ``14 | Sun Study.Results`` and ``14 | Sun Study.Facade``, combinations
``14 | Sun Study 09:00``, surfaces, views and layouts the same.

The prefix could not simply be deleted, which is the part worth recording.
``remove_previous`` finds a run's own work by it, so an empty prefix matches
every view and every layout in the project and the clean-up before a rerun
would delete the practice's drawings. Replacing one marker with another keeps
that guarantee; removing it would have been the most expensive kind of tidying.

It lives in ``archicad/naming.py``, alone, because five modules need the same
string and none of them should import another to get it -- and because ``14``
is right for a project whose groups end at 13 and wrong for the next office.

The property group is deliberately *not* renamed. ``Sun Study Note`` and its
siblings are written onto Zones and already carry values on this project;
renaming them would orphan every one and leave a schedule pointing at nothing.
A property is not a layer.

### D66 — A layout cannot be created into a subset, only moved into one

Asked to file its sheets with the practice's own, in ``SHADOW DIAGRAMS`` and
``ADG DIAGRAMS`` rather than at the root of a book of 299 layouts.

``CreateLayout`` looks like it does this. Its schema accepts
``parentNavigatorItemId`` -- strict enough elsewhere to refuse a misspelt
field by name -- and answers with a database id. Measured: the sheet arrived
under the book root, not under the subset. Accepted, and ignored.

``MoveNavigatorItem`` does it, taking ``navigatorItemIdToMove`` and
``parentNavigatorItemId``, verified by reading the book back and finding the
layout at ``SAMPLE > DEVELOPMENT APPLICATION > SHADOW DIAGRAMS``. So a sheet
is made first and filed second, and the filing is read back rather than
believed -- both commands answer ``{"success": true}`` either way.

Which subset by what the sheet *is*: a clock time is a shadow diagram, and the
banded and two-hour plans are ADG diagrams. Both names are options, and a
subset that is not there is reported rather than created. The Layout Book is
the practice's structure; inventing a subset in it is a bigger decision than a
sun study gets to make on its own.

### D67 — A balcony Zone is a void, so you stand on its floor, not its top

Reported from the drawings: the sun patch on the wrong floor. On the ground
floor the balcony was bare; on the floor above, where the balcony is smaller,
a patch was drawn that overhung the apartment outline.

``_open_space_owner`` decides which flat a balcony belongs to. Nearest box is
not enough -- a balcony sits at its own apartment's floor level, which puts it
flush against the ceiling of the apartment below, so the two are exactly
equidistant and iteration order picks the winner. The disambiguator is the
level of the surface somebody stands on, and that was read as
``slab.bounds[1][2]``: the top.

Right for a slab, wrong for a Zone, and this project models balconies as
Zones. A Zone is a *void*: you stand on its floor and its top is the ceiling,
one storey up. So every balcony matched the apartment whose floor was level
with its ceiling and went up a floor. ``_floor_grid`` already makes exactly
this distinction, in a docstring twenty lines long, for exactly this reason;
the owner rule did not.

Measured before: 8 of 11 apartments had floor cells spanning 3.20 m -- one
storey height -- because the flat's own floor and a borrowed balcony floor
were in the same set. After: every apartment on one plane, all 12 balconies
level-matched, no fallbacks, the same 22,541 cells.

What made this hard to see is that nothing about it looks wrong. The patch is
drawn at the balcony's true position in plan, on a storey one above where it
belongs, and a plan of a floor with a smaller balcony is exactly where a patch
overhanging the outline is visible. Every other suspect checked out: 48 of 48
spaces matched a zone on the correct floor, all 35 zones sat within 0.0 m of
the storey they claimed, and the plan transform fitted to 0.29 m.

### D68 — The prefix is a setting, so nothing may hold it as a constant

``14 |`` leads the name of everything this tool creates (D65), and ``14`` is
right for a project whose layer groups end at 13. The next office numbers
differently, so it became ``--layer-prefix`` and a field in the window.

The interesting half is not the flag. It is that six modules held a name
*derived* from the prefix at module level -- ``DEFAULT_LAYER_NAME =
layer("Results")``, ``EXPORT_COMBINATION = named("Sun Study Export")``,
``VIEW_PREFIX``, ``ATTRIBUTE_PREFIX``, and four more in ``cli`` of which two
were Typer option defaults. Every one of those is evaluated at import, before
a command line has been read, so a run told to use another prefix would have
drawn on ``ZZ | Sun Study.Results`` while ``remove_previous`` searched for
``14 |``, and cleaned up neither. Both names look correct on their own; the
only symptom is a project that quietly accumulates every run it has ever had.

So they are functions now, called at the point of use, and the two Typer
defaults take ``None`` and resolve in the body after the prefix is set. A test
walks the package's AST and fails on any module-level call to ``layer``,
``named``, ``group`` or ``prefix``, because this is not a mistake anybody
would catch by reading -- the wrong version is shorter and looks tidier.

The prefix is process-wide state set once before any work, rather than an
argument threaded through forty call sites. That is the shape of the thing: a
run measures one project with one prefix.

An empty prefix is refused rather than accepted as a tidier name. ``remove_previous``
deletes navigator items whose name starts with it, so an empty one matches
every view and every layout in the project -- the practice's drawings deleted
by a sun study's clean-up. And a prefix *changed* between runs orphans the
last run's sheets, which is stated in the flag's help rather than worked
around: finding them would mean searching by something looser than the prefix,
which is the same danger by another route.

### D69 — A layer says where the apartments are; a name says which of them are apartments

The window was passing ``--apartment-zone-layer`` and nothing else. On the
reference project that layer, ``06 | Zone.Units``, carries 15 dwellings named
``G08``, 20 balconies named ``BY`` and the storage cupboards -- so every run
from the window assessed 41 apartments, two thirds of which have no living
room and cannot have one. It also passed no ``--open-space-zone-layer``, which
falls back to slabs named ``Balcony*``; this project has none, so no balcony
was assessed at all and every apartment was judged on its living-room limb
alone. Both failures are silent and both push the result the same way, which
is why a percentage that came out too low looked like the building's fault.

The command line has had the flags for these since D50. The window did not
offer them, and a setting that exists only on a command line does not exist
for the person the window was built for.

They are offered rather than typed, like every other project property here:
the probe reads the zones once and answers with what they are *called* on each
layer, how many carry each name, and the median floor area of each.

Which of them are dwellings is guessed from area, and the guess is shown. The
names are an office's own codes and mean nothing outside it, while a dwelling
is tens of square metres and a balcony is a few, on every project there has
ever been. The cuts are the ADG's own figures -- 30 m2, under the smallest
35 m2 studio, and a 4 m2 floor under the smallest balcony -- so a storage
cupboard is neither and is left out of both. The line under each field says
what the layer turned out to carry and what was taken, and the chooser lists
every name with its size beside it, because a guess nobody can see is the
thing this window exists to avoid.

Both of Archicad's name fields are offered. The IFC export puts one in
``Name`` and the other in ``LongName``, which is which varies by translator,
and the assessment matches either -- so a person picking from the list is
right whichever way round their project has it.

One case is refused rather than passed on: the open-space layer is only sent
when something narrows it. Naming the apartments' own layer as the open space
with no names to narrow it would take every apartment for a balcony and leave
the assessment with no apartments in it, which is a worse answer than the one
this whole entry is about.

### D70 — A windowed app cannot ask a Windows process to stop, so it leaves a note

Found by pressing Stop during an export. The button's own docstring said
"terminate, not kill: the study restores the project's layer state in a
``finally``". On Windows ``Popen.terminate()`` *is* ``TerminateProcess``,
which runs no ``finally`` at all, so the one thing this tool guarantees about
somebody else's file -- that it puts the layers back -- was being dropped in
precisely the situation the guarantee was written for. On POSIX the default
``SIGTERM`` disposition ends the process without unwinding either. The comment
described an intention that neither platform honours.

The obvious fix does not work here. The only way to *ask* a Windows process to
stop is a console control event, and the packaged app is ``--windowed``: it has
no console, so it cannot send one. Measured, with ``CREATE_NEW_PROCESS_GROUP``
and ``CTRL_BREAK_EVENT``: nothing arrived, and the run was killed at the
twenty-second deadline with the layers as the export had left them.

So the window writes a file and the run watches for it, on a thread whose only
job is to call ``interrupt_main`` when it appears. That raises
``KeyboardInterrupt`` in the main thread, which every ``with`` in this package
is already correct about -- Ctrl-C at a terminal has always been able to
interrupt a run -- and it behaves the same packaged or not, console or none.
The file is never created up front: the run stops when it *appears*, so one
lying about would stop the next run before it began.

Two things are worth knowing about the delay. A pending interrupt is delivered
between bytecodes, so it lands at the end of whatever call is in flight:
immediate during the ray-casting, one Archicad round trip during the drawing,
and not until the translator returns during the export. And a single long
``time.sleep`` swallows it entirely on Windows -- measured at 10 s of 10, against
1.01 s for a main thread doing work. The first version of the test slept, and
failed for that reason rather than for the one it was written to catch.

Terminate and then kill are still there, in that order, behind a twenty-second
deadline. A run too wedged to notice a file is worse than one stopped roughly.

### D71 — The window is grouped by what comes out of it, not by how hard a setting is

The window asked thirty questions in one column, with about half of them folded
into an *Advanced* panel at the bottom. That was the wrong cut, and it got worse
with every study added.

"Advanced" is not a property of a setting. *Facade layers* is not harder than
*Year* — it is simply the facade study's, and it sat under Advanced only because
the reference project needed it named and the next project might not. The
consequence was that no study could be read in one place: somebody setting up the
facade skin ticked a box at the top of the page, then scrolled past nine settings
belonging to two other studies to find the layer list that decides what the skin
is even measuring. A study whose inputs are scattered is a study somebody sets up
half of, and this tool's entire subject is the wrong answer nobody noticed.

So the settings are now a tab per **output** — General, Facade skin, Solar
diagrams — because that is the form the work is asked for in: a job wants the
facade skin, or it wants the solar diagrams. Apartment plans and communal open
space share one section because they are one deliverable, banding a plan by hours
of direct sun and read at the same drawing, so where their sheets are filed is
asked once for the pair.

What survives of Advanced is General, and it is a different claim. The year, the
title block, the layer combination the export starts from, the numbering the
results file themselves under and the wait a slow export needs are not advanced,
they are **shared**: every output is drawn on them, and a copy of each in three
sections would be three chances to disagree. *Also export* is there for that
reason and not because it is obscure — the facade skin and the communal study
both need the zone layers forced into the export, and neither owns the setting.

Tabs cost one thing, and it is the thing this window exists to prevent: a section
nobody opens is a section nobody knows the state of. A colleague could tick
Communal open space in March and never see it again. So it is paid for twice, in
`Window._sync`:

* a tab whose study will run carries a tick on its own label, so the state of
  every section is legible without opening any of them; and
* a line directly above Run names every study queued — *"Will run: facade skin,
  then apartment plans and sheets"* — because with the ticks spread over three
  sections there is otherwise nowhere on screen that answers "what happens if I
  press this", and this is a run of several minutes.

Both read from one list, `Window._studies`, which also carries the names `jobs`
labels the run with. A study called one thing before it runs and another in the
log is a study nobody can follow.

Two sections are declared and empty — **Shadow diagram** and **Sun eye view**.
They are here so the shape of the tool is visible and so a setting arriving later
has a decided place to land instead of being wedged into whichever section is
nearest; the clock-time subset now says in its own tooltip that it moves to
Shadow diagram when that study is built. Each says plainly that it does nothing
yet, and neither carries a tick: an empty page is honest, and a switch that does
nothing is not. They are not greyed out, because a tab that cannot be opened
cannot explain itself and reads as something broken.

Every tab scrolls on its own rather than the notebook sitting inside one
scroller. Solar diagrams is two studies and a dozen questions, each with its
explanation underneath, and is three times General; a single scroller would size
itself to the longest and leave every short tab with a bar that moves nothing.

Nothing about the command lines changed. `jobs` builds the same argv from the
same widgets, which is what the tests assert, and the saved settings are keyed on
names rather than on position for exactly this case — every field kept the name
it was saved under, so a settings file written before the sections existed opens
into them unchanged. The one key that went is `advanced_open`; `open_section`
replaces it, holding a title rather than a number so that inserting a section
cannot reopen somebody on a different page than the one they left, and a title
this build has never heard of leaves the notebook where it is. Losing which tab
was open is the cheapest thing in that file to lose.

### D72 — A shadow diagram is drawn in the plan, and its subject is attribution

The office's shadow diagrams were made from a 3D Document: model the scheme,
set the sun, place the document on a sheet, twenty-one times. That has two
costs, and only the first is about effort.

A 3D Document **cannot be created** through the add-on (D49), so every one of
them is somebody's hand work before this tool can touch it. And a rendered
shadow is *a* shadow. It cannot show the split between the shade that was
already there and the shade the proposal adds — which is the only thing a
consent authority reads the sheet for. Getting that split out of a render means
building the scheme twice, once present and once absent, and subtracting the
two by eye.

Computed, it is two ray casts and a boolean:

```
shaded_before = ~sunlit(context alone)
shaded_after  = ~sunlit(context and the proposal)

existing   = shaded_before
additional = shaded_after and not shaded_before
```

and the same subtraction against a planning envelope answers "how much of that
could have been cast by anything the controls allow here anyway". All three
come off one grid and are differenced against the same `before`, so the fills
abut rather than overlap and their areas add. That last part is tested, because
overlapping masks would put the blue on top of the grey and the sheet would
quietly claim the proposal darkened ground it did not.

**One horizontal plane, not the terrain.** Every consent authority draws to a
flat datum, and it is the only surface on which the outlines stay legible at
1:1000 — draped on a site mesh the shadow steps at every roof edge and every
contour. It is not a claim about the ground, and a sloping site really does
catch a shadow further up the hill than this says.

**The datum is project zero, and this cost a run to learn.** It defaulted to
the lowest point of the geometry, which is the bottom of the basement
excavation — 10.83 m under the street on the reference project. A plane down
there is below the whole site, so everything above shades it: measured, 24% of
the plane permanently dark and 875,156 m² of "existing shadow" on a suburban
block. Archicad's zero is conventionally the ground floor level, which is the
right default; `--shadow-datum` moves it. The related trap is the site mesh
handed in among the context, which fills the sheet solid grey the same way and
cannot be seen in the drawing — `permanently_dark_share` is reported so it
shows up as a number instead.

**One layer to an hour, and a combination to match.** Twenty-one hours on one
layer is twenty-one overlapping fills. They could go on twenty-one worksheets,
which is what the communal hourly plans do — but a worksheet carries only what
this tool draws into it, and a shadow diagram is meaningless without the
neighbourhood under it. The reference sheets show roads, boundaries and every
neighbouring building, and that context is the *model*. So each hour gets a
layer and a Layer Combination that shows it and hides its twenty siblings, and
a View pinned to that combination is the site plan with exactly one hour on it.
The combination leaves every other layer as it found it: what belongs on a site
plan is the practice's decision, already recorded in whatever combination they
draw site plans with.

**North needs no correction here, and that is worth writing down.** The export
reports a true north bearing of 0°, which looks like a lost georeference and is
not: Archicad's Survey Point model position rotates the geometry through
`IfcSite`'s placement and then writes `TrueNorth` as (0,1), because the world
coordinates really are north-aligned (see `cross_check_georeferencing`). The
command runs that cross-check before any number reaches the screen, for the
same reason `archicad-run` does.

**What was not built at the time, and now is.** The LEP envelope was
implemented in `core.shadow` and reachable from Python but not from the command
line, because extruding one wants the site boundary as a polygon and the
boundary Archicad holds is in the project frame while the shadows are computed
in the export's. D77 goes around that rather than through it: a height-limit
massing on a real project is *modelled*, not extruded at run time, so it needs
finding, not building.

### D73 — Fills carry an ID and a group, because they cannot carry each other

The drawings say how much sun something gets; the numbers behind them left the
project by a different door — a CSV, or the run's log. A figure that lives
outside the file it describes is one somebody reconciles by hand, or scales off
a drawing with a rule.

Archicad already has the machinery and it is a Schedule: list every Fill whose
ID contains `SOLAR`, group by ID, sum `Area`. `Area` is a built-in property of
a Fill and `Element ID` is a writable one, so the only missing part was the
tool filling the ID in.

```
SUN STUDY / SOLAR  / 2-3 hrs
SUN STUDY / SHADOW / JUNE 21 -9AM / ADDITIONAL
```

`SUN STUDY` first so one filter finds everything the tool drew — the group word
and not the layer prefix, because `14 |` in an element ID reads as a mistake.
Then the study, because that is the split a reader wants first and what a
schedule filters on. Then enough detail that the same schedule breaks down by
band, or by hour and by whose shadow it is.

**What is deliberately not tagged is the part that matters.** A legend swatch
or a site boundary caught by the same filter is added to the area, and nothing
on the schedule says so. The first cut of this tagged the site boundary
`SUN STUDY / SHADOW / SITE BOUNDARY` and would have added the whole site to
every shadow total. So only measured fills are tagged; legend swatches, the
site boundary and the floor footprint under a sun patch are created untagged
and pass through as `None`. Tested, because none of it is visible in the
drawing.

**Ordering is refused, not repaired.** Create commands answer in the order they
were given, and that order is the only link between a hatch and the hour it was
drawn for. On a count mismatch `stamp_in_order` writes nothing and says so: IDs
against a shifted list would put "9AM EXISTING" on a fill drawn for three in
the afternoon, and a schedule would total it without complaint. That is worse
than no ID at all.

#### Merging is impossible, and grouping is what was actually wanted

`CreateHatches` documents its own limit — *"The 2D coordinates of the hatch
outline (single contour, no holes)"* — with `additionalProperties: false`, so
no holes field can be smuggled in. (`CreateSlabs` and `CreateZones` do take
`holes`; fills do not.) Two apartments, or a shadow and the sunlit courtyard
inside it, can never be one element.

It is also the wrong goal: merged into one element the schedule loses the
per-band area, which is the number the IDs were added for. What Archicad offers
for "these belong together" is a **Group**, and `CreateGroups` (Archicad 26 and
newer) does it: one group per category, keyed on the same string the ID carries
so selection and schedule always agree. The elements stay separate, so each
keeps its own `Area`.

What *was* available was tracing instead of tiling. `series` still merged lit
cells into maximal rectangles while `penetration` had moved to traced outlines.
On a synthetic diagonal band at half-metre cells — the shape a real sun-patch
edge takes — that is 531 rectangles against 17 outlines. The lit area is now
counted off the mask rather than summed from rectangles: equivalent, and it
stays right if the shapes ever change again.

#### No contour, as far as the add-on reaches

There is no switch. `CreateHatches` exposes `contourPenIndex`, which sets
`element.hatch.contPen.penIndex`, and nothing else — no "show contour" flag. So
`BandStyle.contour_pen` defaults to `None`, meaning *draw it in the fill's own
pen*, which is invisible against the fill. A black hairline round every cell of
a patch turns a colour field into a grid of boxes, and at 1:200 the boxes are
what a reader sees.

A genuinely contour-less fill is reachable one way and it needs a person: make
a Favorite by hand with the contour switched off and pass its name, since
`CreateHatches` takes `favoriteName` and applies it before the explicit fields.
The same route D50 needed for a wall's surface override, and the only one there
is.

---

### D74 — A refusal to draw is not a report, and the last save is not a step

Both halves of this came off one colleague's run of the reference project. The
console showed ten sheets built, tiled, given tables and filed, and then:

```
CommandFailedError: Tapir command SaveProject failed: Failed to save the
project. (code -2130312308)
[the study stopped, exit code 1]
```

**The sheets were empty.** Every band drawing had been refused, one line per
band, in red, and the run had gone on regardless:

```
The export and the project disagree about where the apartments are:
0.70 m of residual, over the 0.5 m limit.
```

`_draw_zone_groups` answered `True` for *both* "Archicad refused this" and
"the plan is drawn but incomplete", and the caller appended to `made` without
consulting either. So the layer was empty and the run still built a layout, a
view, a layer combination and a table around it. Ten of them. A blank drawing
under a correct title is worse than a missing sheet, because a reader takes it
for a finding rather than for a failure.

So a refusal now answers `None` and an incomplete report answers itself. The
difference is the whole point: an incomplete plan has fills behind it and is
worth a sheet; a refused one has nothing. `_sheet_per_instant` says so and
stops when it is handed no labels at all.

**The last save is not a step, and nothing may depend on it.** The first
`SaveProject` in `_sheet_per_instant` is load-bearing — a layout is unreadable
until it exists on disk (D39) — and has been guarded since. The last one is
not: by the time it runs the fills are in the model, the sheets are made,
straightened, tabled and filed, and the file reaching disk changes nothing
that follows. It was the function's last statement, unguarded, and it took the
whole study down with it, losing every step of `massing` that came after.

Why Archicad refuses a save it accepted a minute earlier is its own business —
a dialog open in front of it, a `.pln` on a network share or under a sync
client, a lock. `-2130312308` is `APIERR_COMMANDFAILED` — *"the invoked undoable
command threw an exception"*, the generic answer out of
`ACAPI_CallUndoableCommand`, not the file-layer error this entry first called it,
and it names no cause at all. Tapir relays it without adding to it. The tool cannot fix that and should not
pretend to; what it can do is say so loudly, say that nothing is lost, and
carry on. The same guard is on the statistics sheet's final save, which had
the same shape.

`SaveProject` was later called on that same project, on Tapir 1.5.8, and
answered `{"success": true}`. So the refusal was something about the moment —
a dialog, a lock, a sync client — and not a broken command or an old add-on.
That is an argument for the guard rather than against it: a step that works
until it does not is exactly the kind nothing else may depend on.

---

### D75 — A run measures what it names, and a refusal names what disagrees

Two things from the same communal open space study, both about the run doing
work whose result nobody could use.

#### The residual now says which Zone

`0.70 m of residual, over the 0.5 m limit` and nothing else. It is a plan fit
— height is discarded before fitting (`fit_plan_transform` takes `[:, :2]`) —
and it is *relative*: rigid, so a whole export shifted or rotated fits
perfectly. What it measures is the paired Zones disagreeing with each other.
For a communal study those Zones are mostly flats borrowed to place the
drawing and none of them is the thing being measured, which is also why the
message must not say "apartments". It did.

Per-pair distances alone are not the diagnosis, which the first attempt got
wrong. A rigid fit cannot isolate an outlier: it rotates and shifts to split
the difference, so one Zone moved by 2 m leaves every other pair out too.
Measured, one 2 m outlier among five pairs reads

```
1.27, 0.62, 0.58, 0.28, 0.17 m
```

which is indistinguishable by eye from a uniformly stale export. **Refitting
without each pair does separate them.** If dropping one takes the rest inside
the limit, that Zone is the disagreement; if several removals each rescue the
fit, the export has drifted as a whole; if none does, it is badly out of step.
Three verdicts, three different remedies, and the refusal now gives one by
name. Not computed below four pairs, where dropping one leaves two, which fit
perfectly by construction and would clear whichever Zone was asked about.

#### The site surfaces are not computed for a Zone study

The same run measured 1,070,938 m² of facade and 1,946,135 m² of open ground,
every sample ray-cast at every instant of the window, to answer a question
about 828 m² of courtyard. Roughly three thousand times the area, for figures
nothing in the tool reads: `--model-bands` casts its own rays over its own
panels, and the facade and ground tables are consumed only by the report of
them.

So a run measures what it names. Name a Zone and the study is about that Zone;
name none and it is the ordinary massing run, facade and ground, unchanged.
`MassingConfig.assess_facade` / `assess_ground` are `bool | None`, `None`
following the rule, so setting either explicitly still gets both — and the
rule has one home, read through `measures_facade`, rather than one copy per
caller. The CLI states nothing.

A surface that was not assessed is `None`, never an empty band table, and
reads as `facade not assessed` rather than `0 facade samples (0.0 m2)`. The
two are different findings and only one is worth chasing: a facade measured as
zero means the subject filter matched nothing.

On the test fixture — a 93 m² zone in a 1,640 m² site, so a mild case — that
is 4.5x. On the project it came from, the ratio of areas is a thousand times
larger.

---

### D76 — Which storey to draw on and which storey to sheet are two questions

Reported from a real project: the communal fills came out on level 8, where
the Zones are not. The study's spaces were sky terraces at 98, 108 and 127 m.

The storey was chosen with `next(iter(...))` over a **set** of the measured
Zones' storey indices — so which Zone won was arbitrary, and since `str`
hashing is randomised per process, the same study could put its fills on a
different floor on the next run. Whichever won, every cell of every Zone was
then forced onto it: two thirds of that drawing was on a floor its subject is
not on.

`draw_cell_groups` already had the right path. `on_storey=None` groups the
cells by their parent and puts each on that parent Zone's own `floorInd`,
which is what the apartment diagrams have always done; the forced storey
exists for *open ground*, which belongs to no Zone and genuinely has one
level. A Zone study is not that case. So a storey is forced only when the
Zones actually share one.

**And then the sheets disappeared.** The sheet block was gated on that same
forced storey — `if sheet and on_storey is not None` — so the moment the Zones
stopped sharing a level, which is precisely the case the forcing exists to
avoid, no sheet was made at all. Silently: the fills were drawn correctly on
three storeys and nothing was ever put on paper.

They are two questions. *Where may the fills be forced?* Only onto a shared
storey. *Which plans do the sheets come from?* All of them —
`_sheet_per_instant` takes a list and makes a view per storey, so there was
never a choice to make. `_zone_storeys` answers both and is a pure function,
because the bug was in the reasoning and not in anything Archicad said.

A Zone whose storey Archicad will not report is dropped from the second answer
rather than guessed at. It still gets fills, on whatever storey is current,
which is the best available without a home for it — and the run says so
instead of making an empty sheet.


### D77 — A shadow diagram's legend is the project's to declare, not the tool's

`core.shadow` was written for three fills — existing, envelope, additional —
and three is a number taken from one sheet. Set the office's own reference
sheets side by side and it does not hold: SSDA 411 carries two rows, and SSDA
401, the Campsie SSDA set, carries six — existing neighbouring buildings,
future neighbouring context buildings, existing structures within the site, the
current LEP 2023 height limit, the Canterbury Bankstown LEP height limit, and
the proposed building envelope. The same sheet redrawn for Crows Nest swaps the
two LEP rows for a TOD height limit and a SEARs massing. Three hard-coded
constants could draw one of those and never the others, and the constants were
load-bearing in five modules: layer names, Element IDs, group keys, the style
table, the drawing order and the console table.

So `cast_shadows` takes an ordered list of sources instead, and every one of
those six spellings is read off it.

**The roles are the decision, not the count.** Making the list variable is
mechanical; deciding how its members combine is not, and getting it wrong
produces a drawing that reads perfectly and is wrong. Two roles:

A **baseline** is something that will be there — the existing neighbours, the
buildings approved next door, the structures being kept on the site. Baselines
accumulate in the order given, each charged only for the ground the earlier
ones had not already darkened. Their fills abut and their areas add to the
total shadow, which is what lets a reader add the grey rows up.

A **scenario** is something that might be — what a height limit allows, what
the SEARs massing is, what is being applied for. Each is cast against the whole
baseline and against *no other scenario*, so two scenarios overlap. That
overlap is the comparison the sheet exists to make. Differencing them against
each other would show the second one only where it beat the first, which is not
a shadow of anything, and the arithmetic would still produce a plausible
drawing — which is why the role is two flags at the command line rather than
one flag with a keyword in it. A SEARs massing silently demoted to a baseline
would charge the proposal only for what it added on top, and nobody reading the
sheet could catch it.

Cost stays linear: one ray cast per source, a baseline against the baselines
before it and a scenario against all of them. The old three-fill study is
`default_sources`, still the behaviour of a run that names nothing, and its
tests pass unchanged.

**Sources are found by Element ID, not by layer.** The six massings of a
comparison like this are one modelling exercise by one person and they do not
land on six tidy layers; they are, however, named. Prefix-matched, because
`TOD-01`, `TOD-02` and `TOD-PODIUM` are one massing and listing them
individually is a rule nobody keeps current against a model still being drawn.
An element no rule claims is reported by count and by example rather than
dropped quietly: a neighbouring building missing from the baseline is a drawing
whose proposal fill has grown to cover ground that building was already
darkening — wrong in the applicant's favour, and invisible.

**Colours are read, not chosen.** The two ramps — three greys for baselines,
three blues for scenarios — are sampled straight out of SSDA 401's own legend,
so a run reproduces the sheet the office already draws rather than approximating
it. A seventh source in either role cycles back to the lightest step, which is
visibly wrong on the sheet on purpose: the answer there is to pass a colour, not
to have the tool invent one.


### D78 — A shadow lands on what is standing, and a saved view says what stands

Settled on Crows Nest against a real SSDA set, after four wrong answers that
each looked plausible on the sheet. The pipeline below is the one that
reproduces the drawing; every step of it exists because the step before it
was not enough.

**The legend comes from saved views, not from layers.** The eight SHADOW
ANALYSIS views carry four renovation filters between them, so two scenarios
can sit on identical layers and differ only by renovation status — a
layer-derived rule merges them silently and the sheet then compares a massing
with itself. Archicad knows the answer and cannot be asked directly:
`ChangeWindow` takes a navigator item only from Archicad 27, and this is 26.
Publisher can, and applies each view's whole state when it writes it out. So
a Publisher Set of per-view IFCs is the input, one file to a legend row.

**The receiving surface is the terrain and everything standing on it.** This
was the last thing wrong and the one that mattered most. Received on terrain
alone, a shadow reaching a thirty-metre neighbour was drawn as though it
carried on to the ground *underneath* that neighbour — tens of metres too far
in plan, on a site ringed by buildings, in one direction only. Measured: the
existing-neighbour row fell 32% at 9am and 54% at 11am once roofs caught what
they actually catch.

It also cured a symptom misdiagnosed twice. All four scenarios had returned
identical areas at 9am through every run, blamed first on duplicate published
files and then on stray elements shared between the views. Neither was it: with
shadows carrying under buildings the baseline swallowed whatever each massing
did and left the same residual for all of them. On the real receiving surface
they separate at every hour.

One surface for the whole run, built from the terrain and every baseline,
rather than one per source. Per source is truer — a scenario's own roof
catches its own shadow — but each source is differenced against the ones
before it, and two masks measured on surfaces at different heights cannot be
subtracted from one another: the fills would stop tiling and the areas would
stop adding. The baselines stand in every scenario anyway.

**Terrain is a receiver and never an occluder**, claimed before any legend row
sees it. Handed in among the sources it puts every sample below the hill in
permanent shade and prints a solid grey sheet — measured at 81% of the plane.

**Ground the survey does not reach is drawn nowhere.** Off-survey samples sit
on a fallback datum abutting real terrain tens of metres away in height, and a
shadow crossing that step is an artefact of the seam.

**The frame is derived from the two norths, and geometry only checks it.**
Both frames state where north is — Archicad through its georeferencing, the
export through `IfcSite` — and the angle between those answers is the angle
between the frames, exactly. Fitting it from matched geometry instead gave
-33.12, then +0.00, then -32.37 degrees across three attempts while the true
answer, -31.60, never moved: the pairs are an element's plan centre against
its *bounding box* centre, and a box is axis-aligned in whichever frame it is
measured. They are good enough to check on, not to fit on.

**What the drawing looks like is the project's to say.** `CreateHatches` has a
contour pen and no switch to turn one off, and its background pen decides
whether a fill is opaque — and a shadow diagram is read *through*. Both are
left off the request when a Fill Favorite is named, so the Favorite's own
answer survives along with its fill type. The fill pen stays the tool's, since
it is what separates one legend row from the next.

**What was checked rather than assumed.** A 50 m cube on flat ground casts
12,700 m2 at 9am against 12,787 predicted, 6,300 at noon against 6,386, and
13,200 at 3pm against 13,282. Solar noon elevation comes out 32.75 degrees
where Sydney's winter solstice is 32.73. The shadows are long because at 9am
on 21 June the sun is 19 degrees up and a shadow runs 2.9 times the height.


### D79 — A shadow's edge is found, not approximated by the cells it was sampled on

A shadow computed from a grid can only be drawn along cell edges, so at one
metre on a 1:500 sheet its outline is a two millimetre staircase — above pen
width and plainly pixellated. A finer grid is the obvious answer and the wrong
one: cost goes with the *area* while all that is wanted is a better line, and a
staircase with smaller steps is still a staircase.

Sampling was never the limit. The occlusion test answers anywhere, not only at
lattice points, so the boundary can be **found**: it is where the answer flips,
and a flip can be bracketed and bisected. Marching squares gives the topology —
which cells the boundary crosses and in what order, which is what a mask can be
trusted for — and each crossing's position comes from bisecting the lattice edge
it sits on. Measured on a circle of radius 12.3 at one metre: every vertex within
26 microns of the true curve, and the traced area 0.1% off the analytic answer
where counting the cells is 1.2% off. It is *more* accurate than the mask, not
merely prettier.

**Not the silhouette projection this set out to be.** Extruding a massing's
silhouette and intersecting it with a plane is exact and simple; the receiver
here is terrain and every building on it (D78), so exactness there means
three-dimensional boolean geometry and polygon booleans for every difference
between sources. The flat-plane version would undo the roof-catching that moved
the areas by a third at nine in the morning. Bisection gets the same edge on the
receiver that is actually there.

**Holes are the whole difficulty**, because a fill takes one contour and none.
Two routes, and both are needed. A hole can be seamed to its outline by a cut
walked up one side and back down the other — but the cut must not cross
anything, and *which order* the holes are taken in decides whether one exists:
190 of 194 patches seamed first try, and the four that did not were the largest,
where each new cut had to dodge the slivers already made. Six orders are tried.
Where none works the patch is **sliced** instead: sweep a horizontal line, and
between two heights the interior is a run bounded left and right, carried down
as chains and closed only where the shape divides or joins. Slicing asks nothing
and cannot fail.

**What the add-on refuses, established by asking it rather than reasoning.** A
plain square, an edge one millimetre long, nodes half a millimetre apart: all
fine. A bow tie: *Failed to create new Hatch*. A contour that touches itself gets
the same answer. So self-intersection is the whole of it — not size — and every
contour is checked before it is sent, because each fault in this path first
appeared as fills that silently never drew after a run that reported success.

**Three faults worth naming**, all found by measurement after guessing produced
three wrong fixes in a row. The tell each time was a failure count that did not
move: 26 twice, 1,742 twice, 2 twice.

*The seam's sliver opens on a side*, and the wrong side sends the return leg back
across the outgoing one.

*A run can pinch to nothing and reopen* — two lobes touching at a point. It never
divides, so matching by overlap carries the piece through the pinch and the left
chain comes out on the right.

*A horizontal edge is not in the sweep* — it has no crossing — but the boundary
steps sideways along it, and a piece carried through that height recorded only
where it continued from. That cut the corner off every step: 7.15 m² across one
patch, in errors of exactly 0.5 and exactly 1.0, which at a one metre grid is a
little triangle and a little rectangle.

**Areas are unchanged and must be.** They are counted from the cell mask, which
is what tiles and what differences against the other sources; this draws a better
line around the same measurement. On the Crows Nest set every one of the 49
figures is identical to the cell-drawn run, while the fills fall from 22,951 to
2,616.

---

### D80 — A building ends at a storey, so that is what the cut names

`--exclude-above <metres>` (D30) is right about the mechanism and wrong about the
unit. The metre has to be looked up per project, and looking it up wrongly is
invisible: the elements simply stay, and the run reports a plausible number
measured through them.

That is exactly what happened on the Kogarah project. The run's own
`top of apartments 193.5 m` suggested 195 was a generous cut, and it removed
almost nothing — because the 193.5 was itself measured from parked Zones. The
real building ends at storey 20, `LIFT OVERRUN`, level **49.8 m**. Storeys 21 to
108 hold a quarter of a kilometre of parked test-fit material above it, to 338 m:
`UT1.07`, `UT2.12`, `Unit Types`, `BLD A - North Walls L4-L5`. That stack was
shading the tower it belongs to, which is why the lower floors read as sunless.

`--exclude-above-storey "LIFT OVERRUN"` names the storey instead and resolves it
through `GetStories` at run time. "Above the lift overrun" is a sentence about a
building and, as Sami put it, usually the same name in every project; 49.8 is a
number somebody has to find first. The name is matched the way a name is copied —
stripped and case-folded — and one that matches nothing is refused with the
project's own storey list, since a name that misses is normally a name from
another job. It resolves once, next to the connection, so everything downstream
still sees the metres D30 describes.

---

### D81 — Zero minutes is two findings, and only one of them has a remedy

An apartment that receives no direct sunlight is reported as one number. On
Kogarah that number was 22 of 91, and it turned out to be two unrelated
groups.

Four flats face 139 degrees. Between 09:00 and 15:00 on 21 June the sun runs
from bearing 54 through north to 306, so it is never in front of that glazing
at all — not once, before anything is asked about what stands nearby. Nothing
is shading them and nothing can stop shading them: the aspect is the answer,
and it was settled at sketch stage.

The other eighteen face 81 to 197 degrees. The sun does come round to them,
for a few of the thirteen half-hourly instants, and **every one of those is
blocked** — by the building's own fabric within 3.5 m, an `SD2.x` sliding door
across a recess, the wall opposite, the slab overhead. That is an obstruction,
and an obstruction is a design question with options.

Told as one figure the two mislead in opposite directions: the first four send
someone hunting for a shadow that is not there, and the eighteen disappear into
what looks like an unavoidable orientation problem. So `reached_by_sun` runs
the facing half of `sunlit_matrix` with no rays cast, and the sunless count
now names how many of itself the sun never reaches. Asked only of an apartment
that received nothing, because for one that got sun the answer is already
known; `None` from a caller that never ran the test stays silent rather than
becoming a finding.

### D82 — Two add-ons, because the missing commands are Archicad's and not Tapir's

The office's solar penetration diagram is made by aiming the 3D window along
the sun for one hour, making a 3D Document from it, and repeating. Neither of
those first two steps can be asked for from outside Archicad. Tapir 1.5.8's
command catalogue, read out of the installed `.apx`, holds no camera,
projection or 3D Document command, and its `ViewSettings` schema stops at the
layer combination, scale, rotation, zoom and 3D style. Archicad's own API
answers `API.Get3DProjectionInfo` with *"not found"*, code 2002.

So the gap is not Tapir being behind. It is that the JSON API has never
exposed `APIEnv_Change3DProjectionSetsID` or `APIDb_NewDatabaseID`, and only
a compiled add-on can reach them.

Three ways to close it, and the choice matters for years rather than for this
feature. **Forking Tapir** means the office runs a custom build of a tool it
otherwise gets from a release page, and every Tapir release has to be
re-merged across the five Archicad versions Tapir supports. **Waiting for an
upstream pull request** puts the delivery date in somebody else's review queue.
**A second add-on** costs one more file to install and nothing else: two
add-ons coexist, each registering its own command namespace, and the transport
is `API.ExecuteAddOnCommand` either way — which is why `run_loriini` is
`run_tapir` with one word changed.

The second add-on won, and it is deliberately three commands wide. Everything
Tapir already does keeps going through Tapir. If Tapir ever ships these, ours
is deleted and one constant changes.

Two things follow from that narrowness. The add-on holds no analysis: the menu
item starts the Python app rather than computing anything, because a second
implementation of the astronomy is a second thing to be wrong. And the sun is
handed to Archicad as a **date** rather than as angles, through
`API_SunPosition_GivenByDate`, so Archicad computes the sun from the project's
own georeferencing. Pushing our own angles in would make the two agree by
construction and destroy the only free cross-check available — the same
reasoning as the georeferencing check in [D23](#d23--archicads-north-angle-and-why-the-cross-check-compares-sums).

`API_AxonoPars::tranmat` was the one thing this could not settle from a
header, and `GetProjection` shipped as the instrument to settle it with. It
has been: read against the office's own hand-aimed sun view on the Kogarah
solar study, the matrix is what `ViewMatrix` builds, its frame is the
project's rather than true north, and `SetProjection` and
`CreateDocumentFrom3D` both hold on a live Archicad. The measurement, and the
two kit facts the first build got wrong on the way, are in `docs/addon.md`.

### D83 — The site analysis is a port, drawn where the office works, and the site lands by the project's own georeferencing

The office's `au-site-analysis` generator already answers "what is around this
address": a TypeScript pipeline over NSW open data that prints the context
analysis, the site analysis and the development summary to an A1 PDF, with a
DXF beside it for import. Asked to bring that into Loriini, three choices
were open and each was made the same way.

**Port, not wrap.** Running the TypeScript from Python -- a Node on the
workstation, a subprocess, a DXF merged by hand -- would have kept one
implementation but put Node, Chromium and `pyproj` on machines that cannot
install anything (see the workstation note in memory). The fetch layer is
small and stdlib-shaped: ArcGIS REST queries, Overpass, one Valhalla call.
So it is ported, endpoint for endpoint and rule for rule, into a `site`
layer that knows nothing about Archicad, with the transverse Mercator
arithmetic written out (Redfearn, from the GDA Technical Manual, checked
against its worked example to the millimetre) rather than imported. The
approved dependency set is unchanged.

**Draw, not import.** The generator's DXF puts everything on `SA_` layers in
MGA metres for a person to merge. Drawing the same content as native elements
into a worksheet -- through the add-on's `CreateWorksheet` (D33) and
`CreateFills` with the legend's RGB (D82), then Tapir's polylines and texts
(D60) -- means no file on disk, no merge dialog, no pen matching, and a
rerun that clears its own worksheet. The aerial is the one thing not drawn:
no command places a picture, so it is saved with world files for placing by
hand.

**The site lands where the project says it is.** A bundle is in longitude
and latitude and the project has a location and a north angle, so there is
exactly one place for every point: projected to the MGA grid, moved so the
origin's own grid position is zero, turned so true north sits where the
project's north angle puts it -- corrected for the grid's own convergence,
about one degree at Sydney, which is the difference between a survey's
north and the sun's. It is the same turn the sun eye views make in the other
direction, tested against the same figure, so a site and a sun study cannot
face different ways. A project whose location is still the Sydney preset
would put the site eleven kilometres off; the run says so, and
`--anchor site` puts the site's centre at the origin instead.

What follows from the port: the site bundle stores every OpenStreetMap
building footprint in its extent with the storeys and height OSM records,
which the sheets only label. That is the material for the next step, a
massing of the neighbours on a context layer, and the reason it is fetched
now rather than later.

### D84 — A worksheet made in the session is entered by a person, and the run waits for that

Measured on the Kogarah solar study on 11 September 2026, drawing the site
sheets. The add-on's `CreateWorksheet` was refused from its undo scope, the
same fault D82's 3D Document command had, and is fixed. Tapir's
`CreateWorksheets` then made the worksheet, and entering it was refused too:
`APIDb_ChangeCurrentDatabaseID`, the add-on's own call, answers
`APIERR_BADDATABASE` for a worksheet made in the session, so the wall D33
blamed on Tapir's `ChangeWindow` is Archicad's. A save did not lift it.

What does lift it is the one thing the API cannot do: a person opening the
worksheet. With it double-clicked in the Project Map, `GetCurrentDatabase`
reported the worksheet by id and by name, and the site sheet drew into it.

So the run no longer claims to enter a worksheet it cannot. It creates one
if there is none, tries the move once, and then polls for up to
`--wait-minutes`, saying exactly which worksheet to open. Matched by database
id rather than by name, because the add-on reports an empty name for a floor
plan and a name is a weaker key than an id anyway. A rerun in a later session
enters the existing worksheet without help, as the docs measured for the
penetration series.

*Corrected 15 September 2026 by [D95](#d95--a-worksheet-made-through-the-api-is-opened-by-a-person-once-ever-and-a-reopen-does-not-do-it).
The later run enters it because a person opened it during the first, not
because the session changed. Reopening the project lifts nothing.*

The alternative -- drawing into the floor plan and asking a person to move
the elements -- was not taken. A context sheet is 6,000 elements at
1:3000 over a kilometre of the model's storey, and nothing about that is
tidier than a click.

### D85 — The context model fetches its own square, and reads the ground from an index

Asked for on 11 September 2026, after the site sheet's 34 footprints had
been modelled: "a large context, ideally 1 km radius" became 600 m and then
"make it 500 m". The site sheet's bundle covers about 300 m; the model
wants a kilometre across, and the furniture query that serves the sheet
(fifteen kinds at once, sized for 1:500) is the wrong fetch for it.

So `run_model` fetches a square of `--model-radius` metres each way: the
contours, the height-of-building control, and the footprints alone through
one Overpass query, saved as `data/model.json`. It is a `SiteBundle` with
the sheet fields empty rather than a fourth kind: the model reads the same
five fields either way, and one loader serves both. At Kogarah that is 483
footprints and 36,191 contour vertices, fetched in 38 s and modelled in 5 s.

Two things had to change for that size. The ground under each slab was
found by scanning every contour vertex for every footprint -- fine at 34,
seventeen million distances at 483 -- and is now a 40 m grid of the
vertices, the same inverse-distance-between-two-levels answer from the
cells around the point. And the mesh's level lines are thinned to 12,000
vertices, halving contours and points in turn, because Archicad
triangulates between every one and a kilometre of 2 m contours reads as
ground long before that. `--model-radius 0` keeps to the site sheet's
bundle for a small study.

### D86 — The drawn boundary places the site, and the blocks are kerbed meshes with the roads between

Asked on 11 September 2026: "check the proper north with project location
setting, so everything is placed properly", and whether roads could be
part of the terrain.

The north was right and the origin was not. The fetched lot came out the
same size and the same way round as the modelled building, 35 m and 20 m
away, because the run had put the site's centre at the project origin and
the office's origin is a boundary corner. A file that has been modelled
knows where its site is better than any fetch: the `03 | Site Boundaries`
layer held seven survey markers, and fitting the lot's convex hull to
theirs (longest side for the turn, centroid for the shift) landed it with
a residual of 0.11 m. The fit is `--fit-layer`, on by default, saved to
the run folder for the runs that stand in a worksheet, and the project
location is written from the fitted origin so `--anchor location` is right
afterwards.

The turn was +1.05 degrees, the grid convergence at Sydney: the file's
north angle is an MGA bearing typed from the survey, where Archicad means
a true one. Most files will be like that. `--north grid` says so
explicitly; the north angle itself is not touched, because the sun study
was made with it and a degree does not move a shadow.

Roads: the office's own files carry a roads mesh with the blocks as holes
and a footpath mesh per block. The add-on's `CreateMesh` has no holes, and
the road reserve as one polygon would need a boolean over a thousand
lots. So the inverse: every block (lots that touch, dissolved, clipped to
the model's square) is a mesh 150 mm above the terrain, and the roads are
the terrain between them. Same picture, no holes, no boolean. 119 blocks
at Kogarah in a minute and a half, three drawn lot by lot where the
dissolve found three edges at a point.

### D87 — The summary of controls is drawn on a layout; a session-made layout can be entered

Measured 11 September 2026 while looking for a way round D84 for the
third sheet. Loriini's `SetCurrentDatabase` with `windowType: Layout`
enters a layout made moments earlier by `CreateLayout` -- the one thing a
worksheet refuses -- and `CreateTexts`, `CreatePolylines` and
`CreateFills` then draw into it. A layout element will not take an
element ID; nothing else differs. Layout coordinates are metres, upward
from the bottom-left (`docs/addon.md`).

A table is paper, not model: it has no scale to keep and nothing to sit
over. So the Summary of Controls skips the worksheet, the view, the
drawing and the five layers, and goes on its sheet as 31 rules and 54
texts hung 15 mm inside the usable corner of the A1 master. Half a second
against thirty for the same table through a worksheet, and nobody has to
open anything.

One rule came out of it: **never delete the layout that is the current
database**. The second run of the summary did, to remake the sheet, and
Archicad went away mid-call (its recovery dialog blamed memory). The
layout is left for the floor plan first; unlike a worksheet it can be
entered again after.

### D88 — One program, two toolsets

Asked 11 September 2026: "we need to restructure the whole selection
program ... 2 different toolsets ... unite them under one add-on program".
`docs/restructure.md` is the plan; this records what changed and why.

The window had six tabs, one per output, and the same question in three
of them. It has three: General (what every sheet needs), Site tools (an
address and four outputs) and Solar tools (four tabs of its own: the model
the three solar tools export, then a tool each). The title-block width
moved from the sun views' tab to General, because every tool places a
sheet; the export layer state moved from General to Solar tools, because
only the solar tools export. The words follow the plan -- Context
Analysis, Site Analysis, Summary of Controls, Context Model; Solar
Analysis, Shadow Diagram, Sun Views -- in the window, the commands
(`site`, `sun-views`, the old names hidden), the Archicad navigator and
the docs. The product is Loriini; the property group stays `Sun Study`
(D-something earlier: renaming it orphans written values).

The neighbours go through the add-on's own `CreateSlabs` -- layer, storey
and ID with the outline, holes allowed -- in one pass where Tapir needed
three; 480 slabs in 19 s against 100. `CreateMesh` takes holes now too.
And the IFC reader loads on first use instead of with every command and
the window: 0.2 s to start rather than the geometry kernel's several.

### D89 — Every solar tool takes a day, and a day that is not the ruleset's is stamped on everything

Asked 14 September 2026: "add option to all solar tools. the summer
solstice and spring equinox". The shadow diagram already drew three days;
the apartment plans, the facade bands, the communal study and the sun
views read the one day in `nsw_adg.yaml` and offered no other, on the
argument (D16, `docs/addon.md`) that a study on the wrong day is a
plausible picture of the wrong day.

That argument stands, so the option keeps it honest in three ways. The
vocabulary is one module, `rules/days.py`: `winter` (21 June), `equinox`
(21 September), `summer` (21 December), or any `MM-DD`, with the aliases
people type -- `midwinter`, `spring`, `midsummer`. The 21st is the drawing
convention every council set is drawn to, not the astronomical instant,
which drifts a day either way; a council that wants the 22nd types it.
The window, the step and the thresholds stay the ruleset's, and a run on
another day says so in yellow, in the same words the window override
uses: *these figures are not that ruleset's criterion*.

And the names. A summer run of the apartment plans would otherwise have
written its hours into the same Zone properties the ADG schedule reads,
and its bands onto the same layer. So `naming.set_day` stamps the day on
every name a run makes when the day is not the ruleset's own -- `14 |
Solar Analysis 21 Dec.Results`, `14 | Sun Views 21 Dec`, the property
group `Solar Analysis 21 Dec` -- and leaves every name alone on 21 June,
so nothing anybody has written moves. A name that already says the day,
as a sun view named for its instant does, is not told twice.

In the window it is one box, Day, in General beside Year, read by the
four solar tools; the shadow diagram keeps its own list of days because it
draws all three at once. 21 December in Sydney is on daylight saving;
`ZoneInfo` gives the right offset and 09:00 stays the clock hour a
council names, which is now said in `core.solar` where D3 had assumed
AEST.

### D90 — The future context is the lot set back by the ADG, stepped, and capped by the LEP

Asked 14 September 2026: "possibility of showing future context in site
analysis and model it into 3d geometry with help of understanding of
ADG". The site sheet and the context model show what stands next door.
What a design lives beside is what the controls allow there, and a
Kogarah cottage on an R4 lot under a 25 m control is an eight-storey
neighbour whether or not it has been sold.

The envelope is worked out lot by lot in `site/envelope.py`, pure metres:

- **Set back** by the ADG's Part 3F separation, halved to the boundary:
  6 m for the first four storeys, 9 m for the next four, 12 m above. The
  street setback is the DCP's and the register does not carry it, so it
  is an option with a stated default of 6 m. Which edges are the street
  is read off the cadastre -- an edge no other lot shares fronts the road
  reserve -- because the cadastre is complete and the centrelines are
  not.
- **Stepped** on storey lines, not on the band's metres: a fourth storey
  at 3.1 m ends at 12.4 m and is still in the first band. The first cut
  stepped at 12 m and left a 0.4 m sliver at 9 m in.
- **Capped** by the height control, and then by the floor-space ratio:
  storeys come off the top until the envelope's gross floor area, counted
  storey by storey on the tier each stands in, fits the ratio times the
  lot. The caption says which bound it: `FUTURE 4 STOREY / 12.4 m / FSR
  1.5:1 BINDS`.

The inset is a true erosion traced by the shadow tool's own edge tracer
(D79): a lattice at half a metre, a point kept when it is inside and at
least its edge's setback from that edge as a segment, the outline bisected
onto the setback line with the corners recovered. The first cut clipped
the lot by one half-plane per edge, which is exact for a rectangle and
lost a battleaxe's head to its handle's edge; the erosion keeps the head,
keeps an L's arm, and gives a re-entrant corner the arc a setback really
leaves there. Rectangles come out within 4 mm; a turned lot's corners
within half a metre.

Which lots: within a reach of the site (100 m), zoned where a flat
building or shop-top housing is permitted (R1, R3, R4, the B and E centre
zones, MU1), with a height control, and not the site's own. A lot zoned
R2 keeps its house. Amalgamation is not attempted; two small lots that
would be developed together are two small envelopes, or none, and the
report says how many were too small once set back.

Where it goes: dashed magenta on the Site Analysis sheet's Context layer
with the caption in it, and one slab per tier on a layer of its own,
`LORIINI FUTURE`, not the context model's, because a saved view says what
stands (D78) and a future neighbour is a question a view answers -- with,
without -- not a fact the model asserts. The FSR is now fetched by extent
for the site and model bundles (`EPI/1`), the model bundle fetches the
zoning too, and the cadastre carries its lot ids so the slabs are named
for their lots. The Summary of Controls gains the 3F separation row the
envelopes use. Not yet run live against Kogarah; the tests stand a 30 m
square under 25 m at 1.5:1 and get four storeys, FSR binding.

### D91 — Drawings are dealt onto sheets one way, chosen once: one, two, or each

Asked 14 September 2026: "there should be 3 modes in terms of solar
tools. 1 layout - all 7 drawings on one layout, 2 layouts half of
drawings on 1 layout, second half, or less on 2nd layout - both layouts
will have the same composition, with 1 drawing possibly missing on second
layout. 3. option is drawing per layout ... applicable for all solar
tools drawings".

Four builders had four answers to how many drawings share a sheet: the
shadow diagrams a fixed four, the sun views four with a `--per-sheet`
knob, the apartment plans one per instant, the communal plans every hour
on one sheet per storey. Two of them chunked the same way in two copies
with two naming rules and two tilers -- the D53 shape again. So the
answer is one module, `archicad/sheeting.py`, and one word on every
solar command and one box in the window's General tab: `--sheets one`,
`two` or `each`.

`two` deals the larger half first, so seven is four and three and nine
(8am to 4pm, which some councils ask for) is five and four. The second
sheet is laid out on the first's grid: `layout_from_views` and
`straighten_and_tile` take `cells`, the fullest sheet's count, and tile
for that many, so three drawings sit in the two-by-two's first three
cells at the two-by-two's size rather than in a row of three at another.
The sun views already did this for their own four; now every tool does.

Names follow the drawings on the sheet: one sheet keeps the plain name;
a split is `09:00-12:00` and `13:00-15:00` (the shadow diagrams keep their
`(1 of 2)`); a sheet of one is named for its hour, because `(3 of 7)`
says nothing a reader is looking for. A sheet carrying several instants
of the apartment plans stacks their figures tables under a heading each,
since two tables on one sheet would overwrite each other.

Defaults on the command line are what each tool did before -- the shadow
diagrams and the sun views `two`, the apartment plans `each`, the
communal plans `one` -- so a script keeps its sheets. The window sends
one choice to all four, `two` unless changed, because that is the
question the office asks once per set of drawings, not once per tool.
`--per-sheet` is gone; a saved `eye_per_sheet` setting is ignored.

### D92 — A Drawing cannot be pointed at a file, so the orthophoto is drawn into one

Asked 14 September 2026, after the first live Bondi run: "the ortophoto
map. is it possible to place it like a drawing?"

It is not, in the sense meant. A Drawing linked to the JPEG on disk, that
refreshes when the imagery is refetched, is not something an add-on can
make: `API_DrawingType` carries no path, `linkUId` is documented "not used
yet", and `API_DrawingLinkInfo` has a getter and no setter. Developers ask
on the Graphisoft forum and the answer does not change.

What is possible is a Drawing whose content is its own captured data. The
add-on starts a capture, creates the picture inside it, stops the capture
and hands the result to a Drawing element -- the kit's `Element_Test`
example is the pattern. That gives a real Drawing: a clip frame, a ratio, a
name, a row in the Drawing Manager, placeable in the model or on a layout.
It does not give a link. The image still travels inside the project, the
same weight as the Figure.

So both are offered and neither is a default surprise: `--aerial-as figure`
is what the sheets have always done and stays the default, `--aerial-as
drawing` uses the new command. The Python side is one branch in `_figures`,
because the two requests differ only in the command, the key, and the
anchor a Drawing does not take.

Placed at the site's own altitude like everything else (D-datum above), and
the run says which add-on command is missing if the installed build is
older than this one.


### D93 — One prefix number per tool, not one for the whole tool

Asked 15 September 2026: *"It makes sense for every tool to have its own prefix
number possibility."*

Until now `--layer-prefix` set one number for everything a run made, and the
four drawings were told apart only by the group word after it — `14 | Solar
Analysis.Results` beside `14 | Shadow Diagram.9AM`, `14 | Sun Views 21 Jun
09:00` and `14 | Site Analysis.Context`. In a layer list those sort as one
block, and a colleague looking for the shadow sheets has to know to read past
the number to find them. They are not one drawing: the apartment results are
read by the person assessing the flats, the shadow diagram by the neighbours'
side of the argument, the site analysis by whoever is writing the SEE.

So each tool carries its own default, in `naming.py`:

| Tool | Number |
|---|---|
| `massing`, `archicad-run` — the solar analysis | `14 \|` |
| `shadows` — the shadow diagram | `15 \|` |
| `sun-views` — the sun views | `16 \|` |
| `site` — site and context analysis | `17 \|` |

**The solar analysis keeps 14** so that nothing anybody has already drawn
moves. The other three step up from it.

**They are defaults, not fixtures.** `--layer-prefix` still wins, for an office
whose own groups run past 17 — it is just said once per tool now instead of
once for the lot. In the window that is four boxes in General where there was
one, and the saved `layer_prefix` setting keeps its name and drives the solar
box, so a prefix somebody already chose goes on applying where it used to.

**An empty prefix is still refused, default or no default.** A tool number
standing in quietly for a typo would hide it, and the refusal exists because an
empty prefix matches every layout in the project — which is the practice's
drawings inside a sun study's clean-up.

The wiring is walked rather than trusted, in `test_naming.py`: a command that
calls `set_prefix` without naming its tool silently takes the solar analysis's
number, the run succeeds, every name looks right, and the only symptom is two
drawings sharing a layer group.


### D94 — The context goes in the office's own site group, not a layer of the tool's

Asked 15 September 2026, after D93: *"existing context gonna be XX | Site
Context.3D, depending on chosen number in the program... if you input prefix for
example 50 | it will create new layers."*

The fetched context — the neighbours inside the radius and the ground under
them — went on a layer called `LORIINI`, and the future envelopes on `LORIINI
FUTURE`. Both are the tool talking to itself. The office template already has
somewhere for neighbours: on the reference project `03 | Site Context.3D`, under
`03 ------------------------------ SITE` beside the boundaries, the setbacks
and the survey mesh. A colleague looking for the context looks there.

So the context is filed under the site group, and the group number is the
setting:

| | |
|---|---|
| `03 \| Site Context.3D` | the neighbours and the ground under them |
| `03 \| Site Context.Future buildings` | what the controls would allow, D90 |

`Future buildings` is the spelling the shadow tool's own `--shadow-source`
example already used, so a legend row copied from that help finds the geometry.

**Find or create, which is one call.** `ensure_layer` looks the layer up by
name: the template's is used and left alone, and a group the project does not
have — `50 |` — gets its layers made. There is nothing to decide at the call
site and no second layer beside the template's.

**Only the number is settable.** The wording after it is the template's, so a
run cannot invent `03 | Neighbours` and leave the next one looking in the wrong
place. `--context-prefix` on the `site` command, one box in the window, and it
reaches only that command because only that command makes the context.

**It is deliberately not one of D93's four numbers.** Those say where the
*study* is filed; this says where the *neighbourhood* is. Moving one must not
move the other, which is why they are separate settings rather than one.

**Nothing is orphaned by the move.** `_clear_previous` deletes by Element ID
alone — `SA NEIGHBOUR`, `SA TERRAIN`, `SA BLOCK`, `SA FUTURE` — and not by
layer, precisely so a slab a failed move left in the wrong place is still found.
A rerun therefore clears what earlier runs left on `LORIINI` as well as what it
put in the site group.


### D95 — A worksheet made through the API is opened by a person once, ever, and a reopen does not do it

Asked 15 September 2026, after a site run stopped twice waiting to be let in:
*"this is not optimal. next task is to find a way around it so you dont need my
assistence."*

[D84](#d84--a-worksheet-made-in-the-session-is-entered-by-a-person-and-the-run-waits-for-that)
read the refusal as a property of the *session*, and `connection.py` said so in
the hint it raised: *"cannot be activated until the project has been reopened."*
That was inference from a rerun working the next day, not a measurement, and it
is wrong.

Measured on the Bondi file, 15 September 2026. A worksheet was created through
`Loriini.CreateWorksheet` and never opened by anyone; entering it was refused
with `APIERR_BADDATABASE` (-2130313110). The project was saved and reopened
through Tapir's `OpenProject` — eighteen seconds, against under one for the
same call on an already-open file, so the reload was real. It was still
refused. Then all three worksheets in that one reopened file were tried
together:

| Worksheet | History | Entered |
|---|---|---|
| `17 \| Context Analysis` | double-clicked once by a person | yes |
| `17 \| Site Analysis` | double-clicked once by a person | yes |
| `ZZ Reopen Probe` | never opened by anyone | **no** |

Same file, same session, same reopen. The discriminator is not the session. It
is whether a person has ever opened that worksheet. Once they have, it is
enterable for good; until they do, nothing the API can say will enter it.

`CloseProject` also refused (-2130312308) on a project that was the only one
open, so "close, then open" is not available to route around it either.

**What this changes.** D84's waiting is still right, and its cost is better
than it looked: once per worksheet for the life of the project, not once per
session. What it kills is the obvious fix — there is no save-and-reopen dance
that makes a fresh worksheet drawable.

**What is left.** Two routes, and the first is already proven in this codebase.
[D87](#d87--the-summary-of-controls-is-drawn-on-a-layout-a-session-made-layout-can-be-entered)
found that a layout made moments earlier *can* be entered, drawn into, and
needs nobody — that is how the Summary of Controls is built, at half a second
against thirty through a worksheet. Moving the site and context sheets the same
way would end the waiting outright. The second is the add-on: a double-click
opens a navigator item, which is not the same call as changing the current
database, and Loriini only ever tries the latter. Whether AC26's API exposes
the former is unread — the kit is not on this workstation.

*Taken up on 7 October 2026, after the wait tripped again on the site tools.*
The second route is built, blind. The kit does expose opening a window:
`APIDo_ChangeWindowID` through `ACAPI_Automate`, which `ModelCommands.cpp`
already uses to bring the 3D window to the front before an export. The
add-on's `SetCurrentDatabase` takes `open: true` and makes that call on the
worksheet's own window before the database move, and `_enter` in
`site_analysis.py` tries the plain move, then the open one, and only then
waits for the person. Tapir's `ChangeWindow` never reached this call for a
fresh worksheet: it changes the database first and returns on that refusal.
If Archicad opens a fresh worksheet's window this way, the waiting ends; if
it refuses that too, the first route — the sheets on layouts, as the Summary
of Controls is — is what is left, and it is certain.

*Measured the same evening, on the Redfern project with the rebuilt add-on.*
It works. The Site Analysis worksheet did not exist; the run made it, the
plain move was refused as always, the open call took it, and the sheet drew
with nobody touching the Project Map. **The waiting is over**: a worksheet
made through the API is entered by opening its window, which is what a
double-click was doing all along. D84's wait stays in the code as the
fallback behind both tries, and should never be seen again.


### D96 — A worksheet already in the project enters without help; only one the run made is refused

The other half of [D95](#d95--a-worksheet-made-through-the-api-is-opened-by-a-person-once-ever-and-a-reopen-does-not-do-it),
measured on Bondi the same afternoon, and the one that ends the waiting.

D95 established that a worksheet the API had just made stayed refused through
a save and a reopen, and that the two a person had double-clicked entered
freely. That left the discriminator ambiguous: was it the double-click, or was
it simply being in the file already? Three worksheets nobody had touched in
that session answered it:

| Worksheet | Origin | Entered |
|---|---|---|
| `BASIX`, `Survey DWG`, `Scale Bar` | in the project, made by a person | yes |
| `ZZ Reopen Probe` | made by `Loriini.CreateWorksheet` this session | **no** |

Nobody opened the first three. They entered anyway. So the click is not what
lifts the refusal — being in the project before the run started is. Archicad
refuses only the worksheet the running session created.

**So the fix is the template, not the tool.** Put `17 | Site Analysis` and
`17 | Context Analysis` in the office template — or make them once, by hand,
on a project that has none — and the site run never creates a worksheet, never
asks and never waits. `ensure_worksheet` already prefers the one it finds
([D84](#d84--a-worksheet-made-in-the-session-is-entered-by-a-person-and-the-run-waits-for-that)),
so no code had to change for the unattended case to work.

What did change: the run now looks for those worksheets **before** the
geocoding and the fetching rather than discovering the problem four minutes
later, names the ones it is about to have trouble with, and says that the
template ends it. It does not refuse to run — the sheet still draws once the
worksheet is opened, and a person at the machine may not mind.

This also retires the search for a way round: there is no save, no reopen and
no API call that enters a worksheet the session made. There is only not making
one.


### D97 — A mesh skirt is a depth below the mesh, not a level, and the sign is invisible until you look from underneath

Reported 15 September 2026, with a screenshot: *"look. its upside down"*. The
Bondi context model was a flat plate with the whole neighbourhood hanging
beneath it.

The surface was never wrong. Read back off the element, the terrain outline ran
`+10.2` and `+11.6` on the west edge and `-45.8` and `-46.7` on the east —
which is the real landform, rising toward Bondi Junction and falling toward the
beach. The neighbours were right too: tops from `+29.6` beside the site down to
`-47.5` half a kilometre away, following the contours as they should.

What was inside out was the solid body. `_terrain` computed the skirt as a
level — `lowest - SKIRT_M`, `-53.818` — and Archicad put the solid between the
surface and **+53.8**, mirrored about the mesh level, which is the plate in the
screenshot. Archicad then reads the field back as `+53.818` for a skirt whose
bottom is 53.8 m *down*: the field is a **depth below the mesh's own level,
positive downward**, and not the level its name suggests.

| | before | after | from the contours |
|---|---|---|---|
| terrain zMin | −51.8 | **−53.8** | −53.8, the skirt |
| terrain zMax | **+53.8** | **+16.2** | ≈ +18.2, the 94 m contour |
| span | 105.6 | **70.0** | ~74 |

The giveaway, before the screenshot arrived, was that the terrain covered 31 m
more range than the contours it was built from — 105.6 m against 74 — which
interpolation between two contour levels cannot do.

**Why it is a function.** `_skirt_depth` exists so the convention is stated
once, beside the measurement, and because three call sites send it: the
terrain, the 236 road blocks and the Tapir fallback. One left on the old sign
would turn that mesh inside out while the others looked right. A test walks the
module's AST and fails if any of them sends a bare level again.

**Why nothing caught it.** The run reports the same counts, layers and element
IDs either way. A mesh inside out is not an error, it is a shape — and the only
symptom is the model seen from below, which nothing in a headless run ever
does.


### D98 — The 3D window's storey filter is the add-on's to set, because a saved view keeps it

Asked 15 September 2026: *"there is filter applied by default on every 3d view
filtering 0.AHD floor... apply no filter on storey"*.

A saved 3D view keeps the "Filter Elements in 3D" settings it was made under,
so a window left on one storey bakes half a model into every sun view and
nothing in the run says so. It bites on exactly this pairing: the context model
is homed on the storey nearest level zero — `AHD`, 0.000, on the Bondi file —
while the building stands on `GROUND` at 10.0 and the storeys above, so a
single-storey filter can never show both.

Nothing already reachable sets it. Tapir's `SetViewSettings` carries the layer
combination, the graphic override, the renovation filter, the 3D style, the pen
set and the scale, and no storey range; Tapir 1.5.8's own catalogue has
`GetStories`, `SetStories` and `Set3DCutPlanes`, none of which is this. So it is
the fourteenth thing the add-on carries because no command for it exists
anywhere.

`APIEnv_Get3DImageSetsID` and `APIEnv_Change3DImageSetsID` carry
`API_3DFilterAndCutSettings`, read out of the 26.3000 kit rather than guessed:

    short  firstStory3D;        // first floor to convert
    short  lastStory3D;         // last floor to convert
    bool   allStories;          // if false, firstStory3D..lastStory3D is valid
    API_MarqueeFilter marqueeFilter;
    bool   trimToStoryRange;
    API_3DFilterModeID filterMode;
    std::map<API_ElemTypeID, bool> elemTypeFilter;

`allStories` is the whole question, and `Loriini.Set3DFilter` sets it.

**Read, modify, write, read back.** The struct also carries the marquee filter
and the element type filter, so a command that built it from nothing would
throw away a marquee somebody set without mentioning it. And the answer is read
back from Archicad rather than echoed, because a refused field reported as set
is a sun view that is wrong and says it is right. The change is written with the
kit's *must convert* flag, or the settings move and the window goes on showing
what it already converted — which reads exactly like the command doing nothing.

**An older add-on is said, not fatal.** A build without `Set3DFilter` answers
that it has no such command; the run says so in yellow and goes on, because the
views were made that way until now and are still worth making. What is not
acceptable is making them quietly.

**And the documents already in the project keep a filter of their own.**
Setting the window mends nothing that exists: `API_DocumentFrom3DType` carries
an `API_3DFilterAndCutSettings` as its *first field*, so each 3D Document holds
a private copy and goes on converting the storeys it was made under. Measured
on Bondi: the window was set to every storey, three dates were re-run, all
twenty-one documents reported `kept`, and the sun views were still empty.

A document cannot be remade either. `DeleteNavigatorItems` reports success on
one and leaves all twenty-one in the Project Map — measured, 15 September 2026
— which is what `make_sun_eye_documents` already meant by keeping what it
finds. So `Set3DFilter` takes an optional `databaseId` and mends the document
in place through `APIEnv_ChangeDocumentFrom3DSettingsID`, which is the only
mend there is short of a person deleting them by hand. The run does it to every
document under its own prefix before making views, and counts what would not
take.

**And a third copy, in the saved view, which nothing can edit.** Reported from
the model: *"the filter setting is written in view itself. so if i open view,
change the floor filter. I need to do redefine with current window to keep
filter turned off."* That is the behaviour, and the API offers no way round it
— `API_NavigatorView` carries the zoom, the model view options, the structure
display, the layer combination and stats, the scale, the dimensions, the pens,
the transformation, the renovation filter, the override combination, the 3D
style and the rendering scene, and **no storey range**. There is nothing to
set.

What there is: a view saved while the window is unfiltered keeps that, because
saving a view is what "redefine from current window" does. So the views have to
be *deleted and made again* rather than edited, and `sun-views` now calls
`remove_previous` before it makes any — layouts first and then views, which is
what that function already does and why, since a view a placed Drawing points
at cannot be deleted and Archicad reports success either way. It is scoped to
the tool's own number, so it reaches the sun views and nothing else — which is
[D93](#d93--one-prefix-number-per-tool-not-one-for-the-whole-tool) paying for
itself.

Three copies of one setting, then: the window, each document, and each view.
The first two are set; the third is made afresh. Nothing in the API reads a
view's filter back, so that last one is checked by opening the sheet.


### D99 — The clean-up steps off a layout first, everywhere, not only where it was learned

Archicad closed mid-command on the Bondi file, 15 September 2026, on the second
of three sun-view dates. The project went with it.

The rule was already written down. [D87](#d87--the-summary-of-controls-is-drawn-on-a-layout-a-session-made-layout-can-be-entered)
recorded it on 11 September — *"never delete the layout that is the current
database"* — and `_remove_layout` in `site_analysis.py` has moved to the floor
plan first ever since. `remove_previous` in `views.py` deletes layouts too and
never learned it, which did not matter while nothing called it straight after
making layouts. Wiring it into `sun-views` (D98) made that exactly what
happens: the run places drawings on a layout, leaves it current, and the next
run for the next date deletes it.

So the guard moves to where the deleting is. `remove_previous` reads the
current window type and steps to the floor plan before the first
`DeleteNavigatorItems`, unconditionally and cheaply — one call against a crash
with the project unsaved — and a layout can be entered again afterwards, so
nothing is lost by leaving it.

**The test is about order, not about the call.** A guard that moves off the
layout *after* the delete passes every "does it move" assertion and crashes
exactly as before, so the test asserts that the move's index comes before every
delete's.

The general lesson is the one worth keeping: a rule discovered in one module is
not guarded until every module that can hit it guards it. This one was two days
old, in the same repository, written by the person whose Archicad it closed.

*Widened the same day, after it crashed twice more.* The first guard tested for
`Layout`, because a layout is where D87 met it. That is the wrong question. A
sun-view run mends its own 3D Documents (D98) and is left standing in one, so
the window is a **document** when the views and layouts are deleted a moment
later, the test for `Layout` does not fire, and Archicad closes exactly as
before. Measured three times — twice on Bondi and once on a clean Redfern file,
always on the **second of three dates**, because the first date has nothing to
delete yet and so never reaches the deletion at all. That is also why both
functions passed when tested alone: run by hand the window happened to be the
3D model, which is safe.

So the guard asks the question that matters — *am I standing in something that
is about to be deleted?* — and steps to the floor plan from anywhere that is not
already the floor plan. The floor plan is the one database this never deletes.

### D100 — A guard that cannot do its job stops the run; Archicad accepts moves it does not make

Archicad closed on the Redfern file again on 16 September 2026, on the equinox
— the second of three dates, the same place it has always closed. D99 was in
and its guard fired. The guard was the problem.

`_stand_somewhere_safe` asked for a floor plan and threw the answer away:

```python
with suppress(ArchicadError):
    connection.run_tapir("ChangeWindow", {"windowType": "FloorPlan"})
```

It never looked to see whether the window had moved. `remove_previous` then
deleted the previous date's views and layouts while Archicad was still standing
in one of the seven 3D Documents the run had just mended — which is precisely
the crash D87 and D99 were written to prevent. The last line before the socket
closed was *"took the storey filter off 7 of 7 documents already there"*, one
call before the first delete.

**That Archicad refuses these moves is measured, not supposed.** The same
session asked `SetCurrentDatabase` to step from a worksheet to a floor plan and
was told, in as many words:

> Archicad accepted the move and stayed where it was. (-2130313215)

There is no reason to think `ChangeWindow` is more honest than
`SetCurrentDatabase` about a move it did not make. So the guard asks again
afterwards, and compares.

**And when the move did not happen, the run stops.** This is the part worth
keeping. The whole purpose of the guard is that deleting the current database
closes Archicad with the project unsaved; a guard that has failed to move and
proceeds anyway is not a guard, it is the crash with an extra step. Refusing
costs one sentence and one click. Continuing costs the afternoon — three times
on Bondi, twice on Redfern.

The general lesson, and it is the second time this rule has been learned in this
file: **the API reports success for things it did not do.** `DeleteNavigatorItems`
reports success and leaves the view (D-see `remove_previous`), a hidden layer
reports a successful delete and removes nothing (`clear_database`), and now a
window move reports success and does not move. Every one of them was found the
same way — by counting afterwards rather than by reading the response. Assume
the answer describes the request, not the outcome.

### D101 — The documents a run makes are mended after it makes them, not only the ones it found

Reported 16 September 2026: *"the sun views are not drawn directly because by
default there is filter on views created — filtering 0.AHD floor"*. The same
complaint as [D98](#d98--the-3d-windows-storey-filter-is-the-add-ons-to-set-because-a-saved-view-keeps-it),
after D98 shipped.

D98 found three copies of the storey filter — the window, each 3D Document,
each saved view — and set the first two. It set the second one in the wrong
place. `mend_document_filters` was called once, at the top of the run:

| step | what it reaches |
|---|---|
| `show_every_storey` | the 3D window |
| `mend_document_filters` | documents **already there** |
| `remove_previous` | deletes the last run's views and layouts |
| `make_sun_eye_documents` | **makes this run's documents** |
| `make_sun_eye_sheets` | places **those** on the layouts |

So the mend only ever reached documents left by earlier runs, and every
document the run made kept whatever `CreateDocumentFrom3D` gave it. Those are
the databases the sheets place. A first run on a clean project — which has no
earlier documents at all — therefore had nothing mended and every sheet wrong.

D98 had the mechanism right and the timing wrong: it reasoned that a document
"made while the window was filtered" keeps that filter, and then mended before
any document of this run existed. A document carries its own copy **from the
moment it is created**, so the only moment the mend is worth anything is after
creation.

So the mend runs again over what was just made. It is cheap — one call per
document, read back as D98 already required — and unconditional, because the
alternative is a sheet that is wrong and does not say so.

**The test is about order, not about the call**, exactly as D99's was: a mend
that runs only before the documents exist passes any "was it mended" assertion
and ships the identical wrong sheet. The test asserts two mends and that the
second falls after the making.

Still unmended, and still true: the third copy, in the saved view. Nothing in
`API_NavigatorView` carries a storey range and `Set3DFilter` reaches a window
or a document and nothing else. The sheets place documents, so they are now
right; a person opening the *view* may still meet the filter, and redefining
from the current window is still the only cure.

### D102 — A fill with no contour is `contourPen 0`, and it is the standard for solar analysis

Confirmed on screen, 16 September 2026, in an untitled file: six 20% patches
drawn side by side, each with a different contour treatment, and the one with
`contourPen: 0` is the one with no visible edge.

It had to be looked at. Archicad *accepted* every variant -- pen 0, `Hidden
Line`, `Wipeout_Contour`, zero pen weight -- and `GetDetailsOfElements` reports
nothing back for a Hatch, so there was no way to measure which had worked.
[D100](#d100--a-guard-that-cannot-do-its-job-stops-the-run-archicad-accepts-moves-it-does-not-make)
is the standing reason not to believe an acceptance; here the answer came from
drawing the six and asking.

**Why it matters more than it sounds.** Against a *solid* fill the old trick
worked: draw the contour in the fill's own pen and it disappears against it.
Against a **percentage** fill it does not -- the pattern is read through, so the
contour stays as a hard edge round every cell of the grid. The moment the
patches became 20% fills, the contour became visible, and there was nothing in
Tapir's `CreateHatches` to turn it off: it has a contour pen and no switch.
That is the wall, and `Loriini.CreateFills` is over it, because pen 0 is the
project's "no pen" -- the same convention `background_pen=0` has always relied
on for a see-through background.

This retires the Fill Favorite workaround for these drawings. A Favorite was
"the only contour-less fill there is" while Tapir was the only route; it is not
any more.

**And the shapes differ, which would have cost the next run.** Tapir answers
`{"elementId": {"guid": ...}}` and the add-on `{"guid": ...}`, while
`ids.stamp_element_ids` keeps only the elements carrying an `elementId` --
silently, with no count. Handed the add-on's shape it writes nothing, and a
Schedule totalling on Element ID would find an empty drawing beside a run that
said it drew every fill. The add-on's elements are re-shaped to Tapir's on the
way out.

*Corrected the same evening.* The commit that made this change, and an earlier
draft of this entry, both said the Silverwater run of 16 September had drawn
332 patch fills and stamped none of them. It had not. That run finished at
18:12 on `32dad45`, where both fill paths still went through Tapir's
`CreateHatches` and were stamped correctly; `_create_fills` did not exist until
`b3af822` at 18:32 and was re-shaped in `74f978d` at 19:09. No run was made in
those thirty-seven minutes, so no drawing anybody has was ever left unstamped.
The bug was real and worth the test that now pins it, but it was latent, and
saying otherwise sent a reader to check a schedule that was never wrong.

Only a contourless fill takes the add-on route. With a contour wanted both
commands draw the same thing, so Tapir is used and an older add-on install
costs nothing; asked for no contour without the add-on, the run says so rather
than drawing the edge anyway.

### D103 — The geometry comes from the add-on, because the IFC cannot be made small from here

Asked 17 September 2026, after the Silverwater export came to 692 MB twice:
*"is it possible to promote new ifc translator setting via addon?"* and then,
on hearing it could only be done by configuring each machine, *"for commercial
usage, setting up ifc export is undoable."*

Both halves are right, and together they settle the design.

**The translator cannot be reached.** Every IFC function the API offers reads,
converts, or opens a dialog: `GetIFCExportTranslatorsList`,
`GetIFCRelationshipData`, `GetIFCDifference`, the guid conversions,
`InvokeIFCDifferenceExportSettingsDlg`. There is no call that creates or edits
a translator, so "Properties to export -> Element Parameters only" is a thing a
person does in Translator Setup and nowhere else.

`API_SavePars_Ifc` does carry a `translatorIdentifier`, so an export can *pick*
a translator by name. That is a real option and it was offered: make a lean
translator once, then name it every run. It was refused for the right reason --
it still means somebody sets it up by hand on every machine, and a tool that
ships to an office cannot start with a configuration step nobody will do.

**So the geometry is read directly.** `API_BodyType` carries a `parent`, the
floor plan element the body was converted from, and that header holds the
guid, the layer and the storey. With the triangles that is the whole of what
the analysis uses -- it has never read a property, a quantity or a
classification, which is precisely why nine tenths of the IFC was waste.

`Loriini.ExportModel` walks the bodies, groups them by element, and writes
triangles. On the reference project 1.64 M occluder triangles are about 59 MB
as float32 against 692 MB of IFC, and Archicad is spared writing 1.5 M
`IfcPropertySingleValue` entities, which is where the minutes went.

**Holes are why this is not a fan over whatever arrives.** A wall face with a
window in it is one polygon with an inner contour, and fanning that fills the
opening. A window that stops sunlight is not a detail here: the apartment
penetration study *is* the light coming through it. So a polygon's contour is
walked to its first zero separator -- where the outer contour closes -- and
everything after it, which is the holes, is left out.

**The seam is `IfcModel`.** Everything downstream consumes it and learns
nothing about where the geometry came from, so this is a reader beside
`ingest/ifc.py` rather than a second pipeline. `read_model` tells the two apart
by the file's first bytes rather than its extension, because an extension is a
hint somebody can rename.

**And the IFC route stays.** Not as a grudging fallback: it is how a file on
disk is analysed at all, how a model from another office is read, and
`--ifc-in` snapshots are how a run is repeated without paying for the export
again -- which is what made the Redfern debugging affordable on 16 September.
An add-on too old to have `ExportModel` falls back to it with a line saying so.

Unproven at the time of writing: the add-on is C++ and builds in CI, so the
format is pinned from both ends by a Python writer in the tests, and the first
live run is what confirms the add-on writes what the reader expects.

### D104 — The native route is the one to use, and the IFC stays as the way back

Verified on Silverwater's `L2 COS ANALYSIS OPT 2`, 17 September 2026, against
the same study run through the IFC an hour earlier. Three runs, two entirely
independent geometry pipelines:

| | IFC | native, from 3D | native, from a floor plan |
|---|---|---|---|
| zone measured | 990.4 m2 | 1021.7 m2 | 1021.7 m2 |
| **sunlit >=2 hrs** | **514.41 m2** | **513.25 m2** | **514.01 m2** |
| share | 51.94% | 50.23% | 50.31% |
| export | 664.8 MB | 68.9 MB | 67.1 MB |
| export time | minutes | ~25 s | ~25 s |

**The sunlit area agrees to 0.4 m2 -- 0.08%.** That is the number the study
reports and the one a consultant would check, and two pipelines that share no
code landed on it from different starting states.

**The denominator says the native route is the more faithful of the two.**
Archicad reports that Zone as 1,022.9 m2. The native read gives 1,021.7 -- a
tenth of a percent out. The IFC gives 990.4, which is 32 m2 short: the export
is losing a little of the Zone, and nothing in an IFC-only run would ever say
so. The percentages differ between the routes for that reason alone.

**And it runs unattended**, which was the whole point. The last run began with
Archicad on a floor plan, the Zones hidden in "Filter Elements in 3D" *and*
their layers switched off -- the ordinary state of a real project, since nobody
wants zone solids in a rendering. The add-on switched to the 3D window, forced
the Zone filter on, rebuilt the model with the layers `export_state` had just
made visible, walked it, and put the filter back.

**The IFC route stays, and not only for an add-on too old to have
`ExportModel`.** It is how a file on disk is analysed at all, how a model from
another office is read, and `--ifc-in` snapshots are how a run is repeated
without paying for the export again. `--export ifc` forces it outright, which
is what a deliverable on the proven path should use until the native route has
a few more projects behind it; `--export native` refuses rather than fall back,
which is what a comparison needs. `auto` prefers the add-on and says so in
yellow when it falls back.

*Not yet proven, and worth saying plainly.* One project, one zone, one day. The
hole handling in the body walk -- a wall's window is a polygon with an inner
contour, and the contour is walked to its first zero separator -- has been
exercised by these runs and not by a case built to break it. The apartment
penetration study, which depends on sunlight coming *through* those windows, has
not been run this way at all.

### D105 — An Archicad menu is one resource per item, and the compiled add-on is the reference

Loriini's menu was broken for most of 17 September 2026 and the fix went the
wrong way once before it went the right way. Both the wrong turn and the right
one came from the same place, so it is worth writing down which.

The original `RINT/LoriiniAddOn.grc` declared two menu resources, one for
"Solar Analysis..." and one for "Solar Analysis Palette", and each carried the
name line `"Loriini"` **twice**. The first line names the submenu. A second one
is another submenu inside it. So the menu bar held `Loriini > Loriini > Solar
Analysis...`, which reads as greyed-out nesting, and the duplicate also pushed
the real item from index 1 to index 2, where `MenuCommandHandler`'s `case
ID_ADDON_MENU_OPEN` — which is 1 — never saw it. Nothing happened when it was
clicked.

The diagnosis was that Archicad draws a submenu per registered menu resource,
so the two resources were collapsed into one holding two items. That is wrong,
and it shipped: Archicad dispatched the second item as though it were the
first, and choosing "Solar Analysis Palette" started the app.

What settled it was not more reasoning. Tapir has a working menu of ten items
in the same Archicad, and its own `ResourceIds.hpp` records the shape in a
comment: "own resID, exactly one item — confirmed working end to end (menu
display AND click dispatch)". Reading the shipped `TapirAddOn_AC26_Win.apx` off
the Desktop shows the same thing compiled, one `STR#` per item:

    36 00 00 00  "Tapir"  "About Tapir...^E3^ES^EE^EI^ED^EL^EW^ET^EM^32503"
    2f 00 00 00  "Tapir"  "Tapir Palette^E3^ES^EE^EI^ED^EL^EW^ET^EM"

Resources that share a name line are grouped into one submenu, which is how ten
resources make one menu. So: one resource per item, one name line, one item at
index 1, and dispatch on `menuItemRef.menuResID` rather than on an item index
that only ever has one value.

That dump carried two further facts neither the signature of
`ACAPI_Register_Menu` nor a grep of Tapir's sources would give.

The `^E<x>` codes are enable flags. Without them an add-on item is live on the
floor plan and greyed everywhere else — including the 3D window, which is where
a solar study is normally started. Loriini's items had none. They are now copied
verbatim from the working binary rather than guessed.

And the trailing `^32503` and `^32510` are Tapir's own `'GICN'` ids, so **a menu
item does carry an icon**, in its string. D-note and memory had both recorded
the opposite, reasoned from `ACAPI_Register_Menu` taking no icon argument and
from `iconId`/`menuIcon` appearing nowhere in Tapir's source — which they do
not, because the icon is never passed in code. That wrong conclusion is what
justified the palette as "the only surface in Archicad that can show a
drawing". The palette is still worth having, for the reason that survives — all
seven studies visible at once as pictures beats a hidden list of words — but it
was not forced, and the menu item should get its icon too.

**The general lesson, which cost four restarts:** for resource-level questions
the compiled `.apx` is the reference, not the header signature and not a grep of
somebody's source. A hex dump around a known caption shows the whole `STR#`
block — length, name line, item — and settles in seconds what reasoning from
the API got wrong twice.

### D106 — The COS schedule is split per Zone, and written as an .xlsx without a library

Asked 18 September 2026, after the Silverwater options were run over five
COS levels at once and the per-level figures had to be pulled out by hand:
*"this is how the table for COS solar should look like ... please implement
this into our program."* The table is the office's own: `L2 COS SOLAR
ANALYSIS`, then TIME / AREA (sqm) / PERCENTAGE, a row per hour.

**Every other output of a multi-level zone run is the sum.** The console, the
`--zone-csv` rows and the table on each storey's sheet all total the Zones
together, which answers "how much of the communal open space" and hides "how
does this terrace do". On Silverwater that hid the whole story: only L2 differs
between the three options, and L3 and L4 barely see the sun in any of them.
`--zone-table` splits by the Zone each sample was cut from. Verified on the
three options: the five per-Zone tables add back up to each run's hourly
totals to the tenth of a square metre.

**The workbook is built from the standard library.** A runtime dependency is a
conversation here, and an `.xlsx` is a zip of six small XML parts, so there
was nothing to have it about. Each percentage is a formula over the cells
beside it and also carries its value: it recalculates when somebody edits an
area, and still reads right in a previewer that never calculates. Areas are
rounded as written, so the recalculated share matches the one printed. Checked
by opening the output in Excel, not only by parsing it.

**The format is the decision; the geometry route is not.** The table reads
only the per-sample results every route produces, so it carries over unchanged
when the study moves off the IFC.

*Not done, and worth doing:* the table on each storey's sheet in Archicad is
still the five-level sum, repeated on every sheet. It should be that storey's
own schedule, and now that the split exists it can be.

### D107 — The sheets panel deals by the Sheets row, and the page can be saved as a preset

Asked 21 September 2026, after the window's first build went out: *"the sheets
in right bar need to be connected with the sheet setting 1sheet/2sheets/
multiple sheets ... needs to correspond truthfully to the actual output
settings"*, and *"make possible to save preset and import presets."*

**The panel was drawing one sheet per drawing whatever General said.** Seven
shadow hours were seven thumbnails while the run, set to *Two layouts*, made a
four-and-three pair. The count on the strip was wrong by the same factor, and
the count is the one thing the panel exists to get right. Three other
untruths came out in the same pass: the shadow sheets were drawn for the days
ticked in Model, when the shadow study is one job that reads its own Days row;
the sun views were drawn at the apartment instants rather than their own
Hours; and the communal study's threshold plan, its hourly set and its areas
table were not drawn at all.

**Dealt by the same function the run calls.** `Window.planned` now builds each
study's drawings and passes them through `sheeting.sheet_chunks` with the mode
the Sheets row sends -- or, when the row is blank and sends nothing, the mode
each command falls back to on its own, because that is what a blank row does.
A `Sheet` carries its `drawings`, the `cells` of the grid it is laid out on,
and its place in the set; the short second sheet of a pair keeps the first
one's grid with a cell drawn empty, as the run leaves it. The thumbnail lays
the cells out by the same wasted-cells-then-nearest-square rule as
`sun_eyes.sheet_cells_for`, so four drawings are a block and not a row. The
band lists the sun at every drawing on a sheet.

**Presets are the settings file, wherever the person puts it.** Two buttons
in the run bar, *Save preset…* and *Load preset…*, write and read the same
JSON `Save as default` writes -- one format on purpose, so a preset copied
over `settings.json` is the defaults and the defaults sent on are a preset.
Loading changes only what the file names, and the open project then has the
last word exactly as it does over the saved defaults: layer names it does not
carry are dropped and said out loud. `preferences.read` is the one function in
that module that raises, because the person chose the file and wants to know
why it did not load. The dialogs open in Documents, not `%APPDATA%`: a preset
exists to be found.

### D108 — Hours and days are pressed, the plans row picks bands or times, and each sheet says its own scale

Asked 21 September 2026, on seeing the first build with the dealt panel:
*"bigger names of sheets. correct scale on the sheets written. possibility to
choose if i want bands by hour or just the sunlight in actual time. site
analysis and context analysis should have different miniature. days and hours
needs to be clickable, not write entry."*

**Hours and days are buttons.** Five typed fields -- the plan times, the
communal window, the shadow days and hours, the sun-view hours -- took three
spellings between them, and a person had to know which. `Ticks` is a row of
buttons, six in the morning to seven at night or the four assessment days,
that answers `get`, `delete` and `insert` the way the Entry did, so
`Window.apply`, the saved files and the run see the same text as before. The
text is *kept*, not rebuilt: a file that says `9, 3pm` lights nine and three
and is sent as `9, 3pm`, and a value no button stands for is sent as typed
and lights nothing, so nothing saved on purpose is rounded to a button. The
communal window is a span: press the first hour and the last.

**Bands or times, for both plan studies.** The apartment plans and the
communal plans each drew the whole day in bands *and* the sun at each time,
with only the communal hourly set switchable. One Plans row in Solar analysis
now chooses for both: bands, times, or both. For the apartments, bands is
`--draw` and times is `--plan-instant`, with `--no-draw --sheet` making the
instant sheets alone. For the communal space, times is `--zone-hourly` and a
new `--no-zone-bands` skips the banded and threshold plans; the figures are
still computed, because the areas sheet and the CSV quote them.

**Each sheet says the scale its command sends.** The block said 1:1000 on
every thumbnail. It now says what the run will place the drawings at: the sun
views' own Scale row, the context sheet's, 1:1000 for the shadows, 1:200 for
the apartment plans and the model, 1:300 for the communal plans -- and
honestly "to fit" for the site sheet, whose scale the run picks from a list
to suit the site, and nothing for the summary, which is a table.

**Three site sheets, three pictures**, and the sheet name set at 11 points
rather than 9, because the name is what tells one sheet from the next across
the panel and a thumbnail is not a print preview. Each site sheet now follows
its own tick, as the command does with `--no-context` and the rest.

**A model is drawn as geometry, not as a sheet.** Asked in the same session:
*"if we creating model, there should not be sheet visible but miniature of
actual model without the sheet."* The context model and the future model are
geometry on their own layers and the run makes no layout of them, so the
panel draws them as an isometric of the ground within the radius, the blocks
on it and the site among them -- the future model with the allowed envelopes
dashed over the lots within reach -- with no paper, no shadow and no sheet
number. The strip's count stays the count of sheets; the study's own line
says "3 sheets, 2 models".

**The facade study is a model too.** Asked next: *"facade solar analysis is
not sheet as well as creating 3d geometry. repair its miniature."* Checked
against `jobs`: the window never sends `--model-views`, so the facade run
colours the model -- a skin of 3D elements, one colour per band -- and makes
no layout at all. The panel had drawn it as a sheet. It is now a model per
day, the building's faces striped by hours of sun with the sun over it.

**Chip rows wrap inside the pane.** From the same screenshot: fourteen
apartment names ran off the right of the page in one line, and the rows that
did wrap lined up on the first row's column edges. Two faults. A frame is
given whatever width it asks for, and a row that measured *itself* asked for
one long line -- so the row now measures the scroller's canvas less its own
offset. And `grid` lines columns up down the page, so the chips are `place`d
from measured widths, each row from the left, and the row states its own
size because placed children do not size their parent.

### D109 — The window's design principles: three surfaces, thin contours, one radius scale, air

Asked 21 September 2026, after a review of the window as built: *"some tabs,
windows inside the program are not fully detailed ... there should be couple
contours distinguishing different windows ... really need to commit to some
design principles. rounded corners etc"*, and the brief: *"everything very
airy. archicad, light grey, light blue, apple kind of style. thin contour."*

**The review found four things.** The page and every panel were white, so on
a short tab the panel dissolved into empty page and the only contour was a
hairline doing all the work. Two rows on Solar analysis floated outside any
panel. The run bar gave Run, Stop and four settings actions equal weight in
one row. And the page scrollbar drew its trough down a page that did not
scroll. The palette, the type, the rounded faces and the dock were sound.

**The principles are written into `theme.py`'s docstring**, seven of them,
and every change since is one of them: three surfaces (light grey ground,
white cards, blue tint for chosen); thin one-pixel contours wherever a region
ends and never a frame inside a frame; one radius scale (4 px controls, 6 px
cards, 5 px tab tops, 0 on paper and geometry); air, with cards inset and
rows stepping six pixels; every control in a card under a header; one mark
per state on its own axis; Segoe UI at the system size.

**What changed to meet them.** A `PAGE` colour, a shade lighter than the
surround, under the sections; the open tab's face redrawn in it so the tab
still joins the page; cards standing on it rather than on white, which is a
`STANDS_ON` entry because a face's corners show the style's background. A
one-pixel rule between page and dock, above the info band and above the run
bar. A *Filing and plans* card for the two shared rows. A gap in the run bar
between the run buttons and the settings buttons. The scrollbar shown only
when the page is taller than its pane. Wider card padding and row spacing.

*Not changed, on purpose:* the queued mark. The orange dot on a drawing tab's
icon is the sun the section icons carry, not a second queued mark; queued is
the blue name and its dot, one mark on one axis, as before.

**Sized to Archicad's own dialogs.** Sami sent the Work Environment dialog as
the reference for sizes and choices: buttons no taller than the field beside
them, a one-pixel edge, a small radius, a grey capitalised band heading a
section. So every button and field is now set at the same compact height,
the tiles carry 20 px drawings instead of 24, *+ Add* matches the chips, and
a settings card's title is capitals on the grey band -- the tint is kept for
what is switched on. The tabs are rounded cards on the chrome and the page
is a rounded card of its own a gap below them, because a tab whose face
merged into the page had no contour and read as neither. The captions over
the two groups of tabs are gone; the rule between them says it. A rule under
the project bar parts *which Archicad* from everything else. The pen set is
chosen from the project's own pen tables rather than typed. And the foot of
the window carries the licence line -- product, version, author, term --
instead of the prototype warning, which stays on every sheet and export where
the figures are.

**One height, and more pictures.** Measured rather than eyeballed: every
button, tile, field and list now asks for the same 29 px, so a row is a row
whatever it holds. The three assessment days are buttons with the sun at
that day's height instead of check boxes; the site study's outputs keep
their boxes and gain their pictures; Browse carries a folder. The dotted
focus rectangle is gone from tabs and tiles -- their face says their state,
and the ring read as a second mark.

**Named for the drawing.** A thumbnail led with the day -- *21 JUN · ALL
DAY* -- which says almost nothing; it now leads with what the drawing is,
*Communal open space by hour*, *Sun view*, *Facade model*, with the day and
the hour under it and the sun last and smallest. The models say what they
are rather than what they are not: "not a sheet" is gone.

**Named for Archicad.** *Where the results are filed* did not say it meant
layers, and a colleague who has not read the code should not have to guess.
The cards and rows now use Archicad's own words: *Archicad layers the results
are drawn on* with *Layer prefix* rows, *Layout Book filing* with *Subset*
rows, *Master layout*, *Layer combination*, *Layers forced visible*, *Layers
hidden on sheets*, *Model export: the layers that leave Archicad*. The
communal icon is a courtyard between two wings with a tree in it, in place of
a field of dots nobody could read.

### D110 — Tapir is built into the Loriini add-on, and no longer installed on its own

**Decided 21 September 2026.** Every study needed two add-ons side by side:
Tapir for the ~60 ordinary JSON commands the Python side uses (elements,
layers, the navigator, hatches, layouts, views) and Loriini for the ones no
JSON command exposes. Two installs, two versions to keep in step, and two
things to go wrong on a workstation without admin rights.

**What.** Tapir 1.5.8's command sources (MIT) are copied into
`archicad-addon/Tapir` and compiled into `LoriiniAddOn_AC26_Win.apx`. Its
registration list is kept verbatim as `InstallTapirCommands`, called at the end
of Loriini's `Initialize`: 233 commands. Left out: Tapir's menus, palette,
script runner and Script UI commands, self-updater and developer commands. No
command's code was edited. 1.5.8 because it is the build the Python side was
verified against live; `GetAddOnVersion` still answers 1.5.8, so every version
gate holds.

**A namespace of its own, `LoriiniTapir`.** Not `TapirCommand`: a standalone
Tapir left installed would claim the same namespace and names, and Loriini's
own `CreateSlabs` and `CreateTexts` differ from Tapir's commands of the same
name. So the one change to Tapir's code is the namespace string in
`CommandBase.cpp`.

**Either order.** `run_tapir` sends to `LoriiniTapir` first. On a first-call
"not registered" (4010, at either level, or no add-on response) it retries once
under `TapirCommand`, and whichever answers is kept for the connection. So an
old Loriini with Tapir beside it still works, and the new Loriini works with or
without Tapir. Once the new build loads, Tapir can be removed.

**Unverified until it loads.** The build is CI's (no admin rights here), with
Tapir's own recipe: the 26.3000 kit and v142. Tapir compiles clean under /W4
/WX there, so Loriini's /W3 /WX should pass; it has not yet been loaded into
Archicad.



### D111 — The aerial photo is fetched and placed without being asked for

Asked 21 September 2026, on learning the orthophoto was placed only when a box
was ticked: "there should be automatic then."

The box dated from before D92, when nothing could place a picture and the
tiles were a download for placing by hand. Once `PlaceFigures` and
`PlaceDrawings` put the photo under both sheets, an unticked box meant a
context sheet with no ground under the zoning wash -- not what the office's
sheets look like -- and the tooltip still said it could not be drawn.

So the checkbox is gone from the window and `--aerial` is on by default;
`--no-aerial` leaves it out for a run that has to be quick or offline. A
failed imagery fetch stays soft, as it always was: the sheets are drawn
without it and the run says so. Settings files that still carry
`site_aerial` are read as before, the key ignored.


### D112 — The Plans row lights either or both, not one of three

Asked 21 September 2026: "in solar analysis - the plans. this shouldnt be pick
option. all should be selecteble, not only one of them?"

D108 made the row three tiles of which one was lit: bands, times, or a third
tile for both. A third tile that means "the other two" is a pick standing in
for a switch. `Tiles` now takes `multi`: each tile turns on and off by
itself, the value is the lit ones joined by commas, and the last one lit
stays lit, because neither is no plan study at all. "Bands and times" is
gone as a tile and read as both wherever it is still written down. The row
is also saved with the window's settings now; it never was.


### D113 — Shadow diagrams come from layers and the native model, drawn in the legend's colours

Asked 21 September 2026: "update it in exe file. so we dont use published
views of ifc model but layers? no fill favorite. match hatch to this legend
for shadow analysis. in sun views there should be graphic override and
layers selectable from actual model."

**The model.** `shadows` takes `--export` like the other studies and defaults
to `native`: the geometry is the add-on's `ExportModel`, and there is no quiet
fallback to an IFC. The native file already sits in the project's frame, so
the drawing frame's check reads its samples as Archicad guids instead of
looking them up as IFC GlobalIds, and the turn comes out at zero. On the
native route the database is not moved before the export (the same rule as
`_export_for_massing`). The terrain layers now go into the export's `only`
set with the legend rows, because without them a layer-trimmed export has no
ground and the run stops.

**The window.** The shadow page no longer asks for a folder of published
views. It has one layer picker per legend row -- Existing, Future, Existing on
site, TOD, SEARs, Proposed -- plus the ground, all read out of the open
project, and sends each as `NAME=layer,layer`. What this gives up is what a
view could say beyond layers (a renovation filter, pinned geometry); a project
that separates its massings that way has to put them on their own layers.
`--shadow-from-views` stays on the command line.

**The fills.** Drawn through `Loriini.CreateFills` in the project's solid
fill, with the legend's own RGB and contour pen 0. No pen matching and no Fill
Favorite. The colours are `shadows.LEGEND`, read off the marked-up legend
pixel by pixel. The greys are the SSDA 401 ramp exactly; the three blues were
off by a few units and were corrected. Rows are coloured by name, not by
position, so leaving one out does not shift the rest. An add-on without
`CreateFills` falls back to `CreateHatches` and the report says the colours
are pens. `--shadow-favourite` still works from the command line and takes
the Tapir route.

**Sun views.** Graphic override and base layer combination are pickers
filled from the project. Layer combinations come through Tapir. The overrides
come through a new add-on command, `GetGraphicOverrideCombinations`
(`ACAPI_Override_GetOverrideCombinationList`), because Tapir can pin a view
to an override by name but cannot list them. On an older add-on the field is
still typed.


### D114 — One tables folder, every hour on one drawing, and overrides read from the views

Asked 21 September 2026: "I am not able to choose the graphic override for
sun view if i need something else then default one. the comunal are csv.
there should be only one option for tables. writing all of them, COS and
apartments together. and you need to have option to browse through the file
system to find proper folder to save. in shadows. make possibility to create
view showing all shadows from designed building in every selected hour in
one drawing."

**Overrides.** The list came only from the add-on's new command, and the
Archicad in use had been started a minute before that add-on was installed,
so the list was empty. With the add-on's command missing, the probe now reads
the override names the project's saved views use, through Tapir's
`GetViewSettings`. It found 24 in 0.4 s on the live project. The only override
it misses is one that no view uses.

**Tables.** The two communal file boxes are gone. General has one **Tables**
folder with a Browse button, and every table goes there: `Apartments.csv`
from the apartment study, `COS areas.csv` and `COS schedule.xlsx` from the
communal one. The command line puts the day in each file's name
(`_day_tagged`), as it already did for the schedule, so the window's
one-job-per-day runs sit side by side instead of overwriting.

**Every hour on one drawing.** `--shadow-all-hours` (a tick on the shadow page)
casts the designed building once more on its own. The designed building is
the PROPOSED row, or else the last scenario. That cast gives the building's
whole shadow rather than the part it adds to existing shadow. Each hour is
traced from it and drawn on one layer per day as closed polylines, with the
hour written at the tip of each outline. The day then gets a combination, a
view and a sheet of its own. Outlines rather than fills, because fills laid
over each other hide each other, and pattern fills stacked on one another
line up exactly and do not darken. The outlines follow the grid cells, so at
a 1 m grid they are stepped. Every single-hour combination hides the layer.

### D115 — Each sun study keeps its own days, the site outputs are buttons, the storey is picked, and the apartment plans are three

Asked 22 September 2026, going through the program build: "in model tab
there is section days studied - that should be under solar analysis and sun
views separately. in site analysis ... under it is list of outputs. this
should be main staff but its so easy to miss. can you make them maybe
horizontal buttons with simplified text?" And a minute later: "in shadow
analysis there is 'days' make it the same buttons as they are in solar and
sun view analysis. they should be the same. draw on storey section should be
selectable from actual model, not type in stuff. in solar analysis for
apartments there should be 3 different plans. one mapping the sunlight in
every hour. one mapping the heatmap ... with band of hours. and one filling
the whole apartment with united fill telling the number of hours in whole
apartment in whole day."

**Days.** The one box of three day buttons sat on the Model tab, a page
about what geometry leaves Archicad, and every solar tool read it, the sun
views included. The shadow page had its own row of four dates spelled
differently. Now there is one builder, `_days_panel`, and three boxes headed
DAYS STUDIED: on Solar analysis (with the Year, which every sun tool still
reads), on Sun views and on Shadow diagram. Each holds its own three
buttons and its own custom-day field, and only its own study reads it. The
custom-day field takes several days with commas between, which is how a
settings file from the old shadow row (`shadow_dates`) restores: into the
shadow box's custom field, deduplicated against whatever is lit. The lit
buttons are saved too, as `day_*`, `sun_view_day_*` and `shadow_day_*`. All
three default to midwinter alone; the shadow page used to default to three
days, and now says so with its buttons like the other two.

**Site outputs.** Six ticks, each with a sentence, read as small print under
the address. They are two rows of buttons now over the same six variables:
Sheets (Context, Site, Controls) and Project (Future context, 3D context,
Location). The sentence each tick carried is the button's tooltip, titled
with the old long label. The icons moved from `BY_LABEL` to `BY_OUTPUT`,
keyed by the short word, because the label test refuses a table entry no
widget renders.

**Storey.** "Draw on storey" was a typed index. It is a combo of the
project's storey names, filled by the same read that fills the height band,
and the run translates the name to the index the command takes through a
new `storey_indices` on the probe. A number typed the old way, or restored
from an older file, still goes through as the index.

**Three plans.** The Plans row had two tiles; "Bands by hour" was the floor
heat map and the flat-by-flat total together. It has three: Sun at each
time (`--plan-instant` per time), Floor heat map (`--plan-bands`) and
Apartment total (`--draw`). Nothing new is drawn; the two whole-day
drawings were already two sheets, and the run already took them as two
flags. A file that says "Bands by hour" lights the last two; "Bands and
times" lights all three. The communal study has one banded plan, so either
whole-day tile asks for it.

### D116 — The future context is today's buildings raised; the model is three layers; a missing building is a bug until proven data

Six decisions from one review of the program on 23 September 2026, recorded
together because they came from the same question -- what does a colleague
actually get out of a run -- and each changes what the drawings show.

**The future context raises what is there.** D90's envelope -- each lot set
back by the ADG's separation, stepped, capped by the height and the ratio --
answered "what could stand on this lot" and drew buildings where there are
none today, moving every neighbour off the footprint a person recognises.
The office reads a future context as the street as it is, each building
built up to its limit, and that is also what a shadow diagram needs: the
same gaps between the same buildings, each as high as it may go. So each
existing footprint within reach, on land zoned for flats and under a height
control, is raised to the whole storeys the LEP control allows; never
lowered. The control is the LEP's because the register has it; a DCP is not
open data. The envelope code stays, for the question it does answer -- what
the *site* could hold.

**The shadow diagram compares an ADG envelope.** A seventh legend row, a
scenario like the proposal and drawn just under it in a lilac of its own:
the proposal with room to move, whose visible fringe is what the room would
cost the neighbours.

**The context model is three layers.** `Site Context.Terrain`, `.Roads`
and `.Buildings` in the office's site group, not one `Site Context.3D`: each
is switched on for a different reason -- the terrain for the sun views, the
roads for a site plan, the buildings for a shadow -- and one layer made
every view take all three or none.

**A missing building is a bug until proven to be data.** Buildings went
missing from the model for three technical reasons before OSM's coverage
was to blame: an Overpass answer cut short and cached for a month, buildings
drawn as multipolygon relations never asked for, and one refused slab
rolling back a request of two hundred. All three are closed (see
`docs/site-analysis.md`, *When buildings are missing*). What remains is
data: around Kogarah, OSM has 395 buildings in a kilometre square and most
detached houses are unmapped, and no NSW register publishes footprints.

**The Model tab is what every study sees, and every study sees it.** The
native route exports no file, but the add-on reads the model Archicad has
built, which holds only what is shown, so the layer state still decides
every number. The neighbouring-buildings layers reached the communal study
alone; the facade and apartments studies were measured without them when
the combination hid them. They reach all three now.

**The plans sit on a named combination.** The apartments' heat-map and
hourly plans were made with no base, so each run started from what the last
left on screen -- the drift ``ensure_layer_combination`` documents, down to
two layers shown of 155. A **Plan combination** on the Solar analysis tab
is the base for the apartment and communal plans alike, picked from the
project's plan-like combinations and never one of the tool's own.

### D117 — The info box says the terms and never the date; the credits sit beside the fetching

Two questions arrive together the first time somebody sends a Context Analysis
sheet out of the office: *may I pass this program on*, and *whose data is this
drawing made of*. Both are now answered by one box, opened by the **ⓘ** beside
the project picker or by **Where this data comes from** on the Site analysis
tab, which opens the same box scrolled to the registers.

**The data half is the one that matters.** The site analysis fetches from six
publishers, five of them under CC BY and OpenStreetMap under ODbL, and every
one of those licences asks for a credit on a produced work. A DA sheet is a
produced work. Nobody can supply that credit from memory, and two publishers
ask for particular wording — `© State of New South Wales (Spatial Services, a
business unit of the Department of Customer Service NSW)` is not what anybody
writes unprompted. So the list lives in `sun_study.site.sources`, beside the
code that does the fetching rather than in a document that goes stale the
first time an endpoint moves, and the box ends with the whole credit line in a
field with a Copy button. `tests/unit/test_site_sources.py` reads every
`https://` literal in the `site` package and fails on a host no source answers
for, which makes adding an endpoint a decision about attribution rather than
an omission.

**The licence half shows the terms and not the term.** `licence.py` is
deliberately silent about when a build expires while the build is inside its
term — no banner, no countdown, nothing in `--help`, and nothing in the window
— because the term is not the subject of the software and a warning every run
is noise for a year. An info box is the easiest place to break that by
accident: a date put there is a countdown, and a colleague reading the licence
to answer a question about redistribution would meet an expiry they were not
asking about. So `licence.SUMMARY` states the grant, the restrictions and the
warranty in six lines and never names a date, `test_licence` pins that it does
not, and the date stays where it was: said once, at the door, on the day it
matters.

The full text is the `LICENSE` file, which the box will show on request — in a
window of its own rather than handed to the operating system, because the file
has no extension and a Windows double-click answers that with "how do you want
to open this file". `Loriini.spec` now ships it at the root of the bundle; a
build without it hides the button rather than breaking it, since the summary is
a constant in the executable either way.

**And the sheet says it too, in the publishers' words and only for what is on
it.** A box in the window answers the question for whoever opened the window;
the drawing leaves the office on its own. So the Context and Site Analysis
sheets carry the credit along the foot of the map field at 2 mm, and the
Summary of Controls under the note that already says where its figures came
from.

What it names is read off the bundle -- `sources_used` on each of the three --
and not off the list of registers the run meant to ask. Every fetch but the
site's own fails soft, so a run whose Overpass mirrors were all down draws a
sheet with no bus routes on it, and a credit to OpenStreetMap there would be a
claim about a line that is not on the drawing. It cuts the other way as well:
the aerial is credited only when tiles were placed, ePlanning only when the
controls answered.

The bus stops are the one case that has to be *recorded* rather than read.
A `Stop` does not carry its provenance, and the same symbols on the same
sheet are Transport for NSW's or OpenStreetMap's depending on nothing but
whether a key was in the environment that morning -- so `stops_from_tfnsw`
is written into the bundle as the run makes the swap, and saved with it, so
a sheet redrawn from `--from` credits the run that fetched it rather than the
machine that is redrawing it.

Valhalla's credit is the engine alone. It routes over OpenStreetMap, so a
catchment adds both slugs and the line reads `...; © OpenStreetMap
contributors; Walking catchments: Valhalla (FOSSGIS e.V.).` rather than
naming the contributors twice in one sentence.

### D118 — The handover folder is built on GitHub, in the add-on's own run

`Loriini.exe` came from one PC. `Loriini.spec` held that machine's absolute
paths, as every spec PyInstaller writes for itself does, so the recipe ran
nowhere else and the only executable in existence was whichever one had last
been built there. The add-on had been built on GitHub from the start, because
a runner is the only place it can be compiled. The program had not.

**Now both come from one run.** The `Archicad add-on` workflow gains a second
job. It builds the program with `scripts/build_app.py` on a Windows runner,
puts the add-on the first job has just compiled beside it with
`How to install.txt` and `LICENSE.txt`, and uploads the folder as the
`Loriini_AC26_Win` artifact. Both halves come from the same commit, so an
executable cannot arrive with an add-on that lacks a command it calls. The
spec takes every path from `SPECPATH`, so the same recipe still builds on a
PC, and `build_app.py` writes the same four files there.

**It proves the program starts before handing it over.** A PyInstaller build
that succeeds can still fail when it runs, on a module or a data file its scan
missed. So the job starts the packaged executable once, the way the window
starts its child, with `SUN_STUDY_RUN_CLI=1`, and requires it to list the
rulesets. That needs the bundled command line and the rulesets' YAML, which
nothing imports. It opens no window and no IFC, so it is a floor under the
build rather than a test of every path through it.

**When it runs is a cost decision.** The repository is private, and GitHub
bills a Windows minute as two. The program takes several, so a folder is made
by a push that changes the add-on, the spec or the build script, and otherwise
on request: **Run workflow** on the Actions tab, with the branch picked. It is
never made for a pull request, whose push has already built the same commit.
So the newest folder can be a commit or more behind its branch. The install
note names the commit it was built from, which makes that visible rather than
assumed.

Artifacts also expire, after 90 days unless the repository says otherwise.
That is one more reason the folder is cheap to remake and is not kept in the
repository.

### D119 — The City of Sydney's contours and trees, and a terrain that spends its vertices at the site

Asked on 28 September 2026, after the office's `au-site-analysis` generator
took them the day before: inside the City of Sydney the contours and the
trees come from the council, because its contours are better and its trees
have a size and a place; the window says whose data that is; and whether
the context model could be made differently, perhaps from the better
contours.

**The registers.** The council publishes, under CC BY 4.0 on its Data Hub,
1 m contours from its 2020 aerial survey and an inventory of every street and
park tree with its height, north-south canopy spread, trunk diameter,
species and age. Both are taken where they cover the ground and not
otherwise, each through a registry of one entry (`terrain.COUNCIL_CONTOURS`,
`trees.COUNCIL_TREES`) in the generator's shape, so the next council to
publish is a line and a credit. The council is a source of its own in
`site.sources` -- the window's info box and every credit line name it --
and a sheet credits it only when its lines or its trees reached that sheet:
contours and trees now say whose they are, one by one, because a council's
register stops at its boundary and the same sheet can hold the council's
trees and OpenStreetMap's. OpenStreetMap is no longer credited for a
council's trees.

**The sheet's rule is the generator's, with its blind spot closed.** A sheet
takes the council's contours only where they cover 85% of the map field, so
one sheet is drawn to one interval. The generator measures "cover" by the box
of the lines, and at King Street, Newtown -- the boundary between the City
and Inner West -- the council's lines on one side reach every edge of the
sheet between them: 100% by their box, 36% of the sheet in fact, and two
thirds of it drawn with no contours. The rule here also asks the state's
register of local government areas how much of the sheet is the council's,
and takes the smaller. The generator should do the same.

**The model's rule is not the sheet's.** A kilometre square crosses a council
boundary more often than a sheet does, and all-or-nothing would throw the
council's lines away exactly where the model needs them, at the site. So the
model takes the council's lines inside the boundary and the state's outside,
cut at it: at Newtown 47% of the square is the council's. And it asks the
council's server to generalise the lines to 0.1 m before they are sent,
because a square kilometre is 440,000 vertices as published -- a vertex every
quarter of a metre, the staircase of the grid the lines were traced from.

**The terrain had to change for any of this to matter.** The mesh has a budget
of 12,000 level-line vertices (D85), and the old rule met it by halving
contours and points everywhere: Kogarah's 2 m contours became 4 m ones, and
the council's 1 m contours would have become 8 m ones -- worse than the
state's, the site included. Four ways were weighed:

| | |
|---|---|
| raise the budget | the same halving, later; nothing measured says what Archicad takes, and the terrain far from the site does not need it |
| a regular grid, from the state's 5 m elevation model or from the contours | uniform, so as coarse at the site as at the edge, and the 5 m model is the coarser survey |
| a TIN, stood as a Morph | the most faithful surface, but a new add-on command (`ACAPI_Body_*`) nobody can run until the next build is loaded, and a Morph is not the Mesh the office edits site terrain as |
| **spend the budget at the site** | the contours as they are, as a Mesh, through the command already proven live; only which vertices are sent changes |

The last was taken (`site.ground.mesh_lines`). Every contour within 100 m of
the site's boundary is kept, simplified by 0.1 m; past it the tolerance
grows with distance, and past 100 m and 250 m fewer contours are kept, plan by
plan until one fits -- far contours before a larger tolerance, because a
coarse line among many close ones crosses them. At Surry Hills that is 8,272
vertices: every 1 m contour to 100 m, every 2 m to 250 m, every 5 m beyond.
At Newtown every contour fits, and at Campsie every 2 m one. Each line is
carried to the edge of the square rather than stopping at its last vertex
inside it.

Two things came up building it that are worth keeping. *Simplified lines
cross.* Douglas-Peucker moves each line on its own, and where the ground is
steep two of them can pass through each other; a mesh then has to invent the
ground between them. The spans that cross are simplified again at half the
tolerance until they do not -- 23 lines at Surry Hills -- and a plan whose
mending would break the budget gives way to the next (keeping every 1 m
contour to the edge crosses 228 lines, and mending them would take 50,000
vertices). *The published lines cross too.* By millimetres, where the ground
drops at a wall: every one of the 38 pairs still crossing at Surry Hills
crosses as published. That is the survey's, and a span stops being mended
once neither side moves a centimetre. Measuring every vertex's gap to its
neighbours first, which would have prevented new crossings by construction,
was tried and took 35 to 100 seconds a square; checking the simplified lines
and mending only what crosses takes under two.

**Levels are read across the slope,** as the generator now reads them
(`lib/levels.ts`, ported rule for rule): the corner RLs on the sheet, and in
the model the ground under every slab, kerb and envelope. The two nearest
contours are not the two either side -- with 1 m contours that put a corner
half a metre low -- and past the last contour on a slope the ground carries
on, one interval at most, where it used to stop between the last two. The
model's slabs beyond the last contour of a fixture stand two metres higher
than before for that reason; the tests say so.

**Trees are drawn the size of their canopy,** a wash so the kerb under it
shows, a dot at the trunk, dashed where nobody recorded a size and the nominal
6 m stands in, so the sheet never claims what it does not know. The
council's record is in each tree's element ID -- `SA TREE London Plane
(Platanus x acerifolia), canopy 10 m, 12 m high, trunk 45 cm` -- so a schedule
can list the trees near the site. An OSM tree within 4 m of an inventory tree
is the same tree mapped twice, and OSM's tree rows become trees 8 m apart.
The model does not stand trees up yet: a tree is a library part, not a slab,
and which one the office wants is a question for it.

*Not yet run in Archicad.* The mesh is built by the command the Kogarah and
Bondi runs proved, with the same budget; what is new is which vertices it is
sent, and that the level lines now meet the square's edge. Whether Archicad
minds level lines that cross by millimetres was never asked -- the old
thinning sent them too -- and the first run on a City of Sydney site should
look at the terrain from below and at a wall.

### D120 — An agent drives Loriini over MCP on stdio, spoken here, and the studies stay in a child process

Asked on 28 September 2026 (roadmap R2): could an AI agent operate Loriini
for more users, to save time and speed the workflow?

**The shape is a tool server, not an assistant in the window.** A server the
person's own agent client connects to -- Claude Desktop, Claude Code, any
client of the Model Context Protocol -- exposes the studies as tools. It is
the cheapest shape to build, because the command line is already the API;
it puts no model key of ours into the product, so nothing is billed to us
and nothing of the person's project goes anywhere we chose; and the
person's own subscription pays for the tokens. An assistant inside the
window would need a key per user and would make us answerable for what a
model does in a project. It can be built later on the same tool
definitions, if it is wanted.

**The protocol is written here, not taken from the official package.** The
``mcp`` package on PyPI, at 2.2, brings twenty-eight packages with it -- a
web server, an SSE framework, a JWT library and its cryptography, telemetry
-- for two transports Loriini does not use, into a one-file executable that
is already 58 MB; and it renamed its main class this year. What a tool
server on stdio needs is five methods (``initialize``, ``ping``,
``tools/list``, ``tools/call``, ``logging/setLevel``) and three
notifications (progress, log, cancelled), stable across every published
version of the protocol. ``agent/protocol.py`` is that, in three hundred
lines, with pydantic -- already a dependency -- giving each tool its schema
and its validation. The same reasoning as the ``.xlsx`` writer (D106).
What it gives up is the package's other halves (resources, prompts,
sampling, elicitation), none of which the agent needs today; the first
worth adding is elicitation, so that a study could confirm its port and
project with the person before it runs.

**The studies run in a child process, as the window runs them.** Through
``app.runner``: the same command line anybody would type, one tested path,
and no second implementation of what a run means. Two more reasons that
are the server's own. Stdout is the protocol, and a study prints; a study
in-process would have to be silenced line by line, where a child's lines
come back through a pipe and go to the client as log and progress
messages. And a client can cancel a call; the runner's stop file asks the
study to stop and lets its ``finally`` blocks put the project's layers
back, where a thread could only be abandoned.

**Tool calls run on their own thread.** A ping during a six-minute study
is answered from the reading thread; a client that hears nothing for a
minute gives the server up for dead. The client leaving -- its stream
ending -- stops what is running and waits for it, so a study is never
left holding a project with nobody to stop it.

**Breadth first, typed tools where a study is asked for often.** The three
studies the office runs most have tools whose arguments are the questions
the window's pages ask, spelled onto the command line as ``Window.jobs``
spells them. Everything else is ``run_loriini``, any command line, with
``loriini_help`` to read the options: the agent-design rule of starting
with breadth and promoting an action to a typed tool where it needs
gating, rendering or a schema.

**Not yet tried from a client on a workstation.** The server has been
driven by a scripted client on its stdin and stdout and by the tests, which
run a fake command line through the real runner. The windowed executable
may hand Python no wrapped standard streams; ``serve`` opens the
descriptors directly then, which is untested until Claude Desktop starts
``Loriini.exe mcp`` on Windows.

### D121 — The reference image is a window of Loriini's own over Archicad's 3D window, and Pillow comes into the bundle for it

Asked on 28 September 2026 (roadmap R4): a view sometimes has to be set
up from the angle a photograph was taken at, Archicad cannot show a
picture in its 3D window, and a tool that lays one over it at reduced
opacity would do.

**A window of our own, not a drawing in Archicad.** Nothing in the API
draws into the 3D window, and Trace Reference is for the plan, the
sections and the elevations. What can be put over the 3D window is a Tk
toplevel of Loriini's: borderless (``overrideredirect``), always on top
(``-topmost``), and as see-through as its slider says (``-alpha``, which on
Windows is a layered window). It touches neither the project nor the
add-on, works over any version of Archicad, and the Mac has the same three
window attributes for later. ``app.overlay`` is the whole of it.

**Two windows, because the picture has to let the mouse through.** The
point of the overlay is to orbit the model *through* it, which on Windows
is one bit of the window's extended style (``WS_EX_TRANSPARENT`` on the
layered window Tk already made, set through ``ctypes`` on the window Tk
wraps every toplevel in). A slider on a window the mouse goes through
would be a slider the mouse goes through, so the controls are a second
small toplevel that stays on top with the picture; the picture itself has
two states, placed (dragged, sized by its corner) and locked (the corner
gone, the mouse through it).

*Changed on 7 October 2026: one palette to the eye, two windows
underneath.* The office asked for the picture to be part of the palette,
as Archicad's own palettes are one floating thing, and for the corner to
size it from its top-left. The two toplevels stay, for the reason above,
but are glued: the strip of controls stands on the picture's top edge and
is as wide as it, moving the strip by its title bar moves the picture,
dragging the picture moves the strip, and dragging the corner widens the
strip with the picture while both keep their top-left corner. A single
toplevel was weighed and refused: ``WS_EX_TRANSPARENT`` is a property of
the whole window, so a strip in the same window would let the mouse
through too and nothing could unlock it; and ``HTTRANSPARENT`` from a
hit-test, which could exempt a region, only passes the mouse to windows
of the same thread, never to Archicad. *Fit* now keeps the picture in the
frame's top-left corner rather than centred, so that pulling the corner
out leaves what was lined up on the model where it was.

**Fit's margins are a colour key.** A picture kept in its own shape inside
a frame of another shape has margins, and margins over a model have to be
see-through. Tk's ``-transparentcolor`` asks Windows to leave one colour
out of the window (``LWA_COLORKEY``, which sits beside the alpha), so the
margins -- and a PNG's own transparency, laid on the same colour -- are
holes. The key is nearly black, ``#010203``, rather than black, because a
photograph's shadows are full of black and every such pixel would be a
hole. The alternative, a window with per-pixel alpha
(``UpdateLayeredWindow``), means drawing the whole window by hand outside
Tk, and margins are not worth it. Off Windows the margins are a dark mat.

**Pillow comes in.** The dependency note in ``pyproject.toml`` said the
approved set, and Pillow was kept out of the bundle because Tk reads the
icons' PNGs by itself (``Loriini.spec`` excluded it). A reference is nearly
always a JPEG photograph, which Tk cannot read; a phone's photograph is
turned by an EXIF tag rather than in its pixels; and a picture has to be
resized cleanly to any frame, where Tk scales by whole numbers. Two ways
round it were weighed. GDI+ through ``ctypes`` reads JPEG on Windows with
nothing added, but is Windows-only, untestable from here, and leaves the
orientation and the resampling to be written by hand. Tk's own readers
cover PNG and GIF and integer zooms, which for a photograph is no tool at
all. Pillow does all three in three calls, is already used to draw the
icons, and costs a few megabytes in a 58 MB executable; it is the runtime
dependency now, and ``PIL`` leaves the spec's excludes.

**Finding the Archicad window is by title, and is only a start.** The
Archicad window is found among the top-level windows by the word in its
title, and the one whose title names the project chosen in the picker is
taken over a bigger one, since two projects open is the ordinary case.
What is found is the whole area inside its frame; the 3D window is a tab
inside that, under the toolbars and beside the palettes, and no call names
where. So the picture starts there and the corner is dragged in, which is
five seconds against a heuristic on child windows that could not be tested
here and would be wrong on the next layout of palettes.

**Untested on Windows.** The overlay has been driven by its tests under a
virtual display on Linux: the fit and the stretch, the opacity, the lock,
the hide, a file that is not a picture, a phone's orientation tag, a PNG's
transparency. The colour key and the click-through are Win32 calls made
blind, and are the first two things to check on a workstation; the third
is where the frame lands on a high-DPI display, where Tk and the Win32
calls should be speaking the same scaled coordinates because they are
asked by the same process.

### D122 — The area calculation measures the slabs' own outlines, and the office's factors take GBA to yield

Asked on 28 September 2026 (roadmap R3), with the office's sheet as the
expected output: *Area calculation, GFA + Yield* -- GBA, GFA, NSA and FSR,
total and by use, and the yield in a mix -- from a massing modelled in
slabs, with the slabs chosen by layer or by the renovation filter, or
simply the GBA and an approximate GFA.

**The slabs are measured here, from their polygons.** Tapir's
``GetDetailsOfElements`` gives a slab's outline, its holes and its arcs in
project metres, with its storey and its layer (``archicad.slabs``); the area
is the shoelace sum of the corners plus the circular segment of each arc,
less the holes (``core.plan_area``). The alternative, Archicad's own area
properties through ``GetPropertyValuesOfElements``, arrives as a display
string in the project's units and language, and would have to be found by
its localised name first. The one thing the polygon route takes on trust is
the sense of an arc's angle -- counter-clockwise positive, as the API and
GDL document it -- and a curved slab compared with its own area is the
first thing to check live (``docs/yield.md``).

**Which slabs, three ways, all Archicad's own filters where they can be.**
By layer, which also says the use: residential layers and non-residential
layers, a layer in both refused, a slab on neither passed over and listed.
By the renovation filter, through Tapir's ``IsVisibleByRenovation`` on the
floor plan -- whatever filter the person has set. And, with no layer named,
everything on a showing layer (``IsVisibleByLayer``), as residential: the
quick GBA. Loriini's own context slabs, marked ``SA``, are never counted.

**The arithmetic is the office's, with its numbers as settings.** GBA to GFA
at 0.75 and 0.9, GFA to NSA at 0.85 and 0.9, FSR over the site; the yield
is the residential NSA over the mix's average unit, rounded down, split by
the largest remainder so the types add back up (``rules.area_yield``). The
office's sheet is the test fixture and comes out exactly, 112 units at 17,
78 and 17 -- and it showed that sheet's two uses' rows swapped, which is
said in the docs rather than copied.

**The site and the target come from the address when they are not typed.**
The Summary of Controls already reads the cadastral lots' area and the LEP's
FSR (``site.pipeline.run_summary``); the study reads them the same way,
only for what is left blank.

**Three outputs from one list of rows.** The sheet on a layout, the table in
the log and the workbook are built from ``report.area_table.rows``, so they
cannot disagree. The sheet is drawn straight on a layout, as the Summary of
Controls is -- texts and lines, the legend's swatches as close lines since
fills are not drawn on paper here -- and a named view is placed with the
machinery the sun views use (``layout_from_views``, ``ArrangeDrawings``).
The workbook is written with the standard library (``report.xlsx``, the same
reasoning as D106) and is live: the inputs are cells and everything else a
formula, the mix's split included as working columns. LibreOffice Calc,
recalculating it with every cached value removed, gives Loriini's figures;
a test does that wherever Calc is installed.

**The window grew a seventh tab, and measures its strip.** Seven tabs need
more room than the page was sized for, in any font; the strip now says how
wide it is, the sheets panel folds below that, and the window opens at
least that wide.

### D123 — A larger model is read from a log; shadow plans are 3D Documents with Archicad's own shadows

Asked on 28 September 2026 (roadmap R1): the shadow analysis failed outright
on a larger model, and the ideal might be to make the diagrams as 3D
Documents, the way the sun views are made, so that Loriini prepares and
Archicad draws the shadows. The roadmap's first step was an assisted session
to read the failure, with the log the window keeps.

**The window keeps its log, on disk.** It kept every line of a run in memory
and cleared it on the next run, and showed one line; a failure forty minutes
in was unreadable after the fact. Now each run is written to
`%APPDATA%\Loriini\Logs` as it comes, flushed line by line, the newest sixty
kept, with a head saying which build, on what, with how much memory, and what
was asked (``app.run_log``). Nothing about it may stop a run: a folder that
will not take a file costs the transcript and not the study.

**The shadow diagram says what it did, stage by stage.** A ``timing:`` line
per stage -- export, read, drape, cast, draw, sheets -- with its duration and
the peak memory so far (``core.resources``, the standard library only, the
Windows working set through ``ctypes``); the grid's size before the cast, and
the rays each cast will take; progress every thirty seconds of a long cast.
The last stage named is the one that was running, and the memory beside it
says whether the machine ran out.

**Two failures were found by reading, and fixed before a session.** The
caster gathered an origin and a direction for every (sample, hour) pair
before casting the first -- about nine gigabytes for a grid two kilometres
across over three days -- so ``sunlit_matrix`` now casts 65,536 samples at a
time; the answer is identical, which a test checks against the single batch,
and the time is unchanged. And the add-on's ``CreateFills`` draws a batch as
one undo step, so one fill Archicad refused took back 500 and ended the run
naming nothing; now a refused batch is halved down to the fill, which is left
out and named, and a refusal of every fill still stops the run. The grid is
left as large as it was -- it is laid over every solid in the export, and a
long winter shadow may reach a far one -- but a layer holding a solid more
than 500 m from every legend row is named, since that is the usual reason a
grid is enormous. Out of memory is said with the numbers and the ways out.

**Shadow plans: the SDK answers the roadmap's question.** A 3D Document's
vectorial sun shadows are its own and not its view's -- Tapir refuses a 3D
style on a view of a document, which is what the add-on's header had
suggested using -- and the kit reaches them twice: a new document takes
*Vectorial Sun Shadows* from ``API_DocumentFrom3DDefaults::vectSunShadow``,
and every document carries its shadow fill in ``attributeOptions``. An
existing document's switch is somewhere in ``effects3D``, which the kit
documents as "Effects to apply" and nothing more. So ``CreateDocumentFrom3D``
takes ``sunShadows`` and switches the defaults for that one creation, putting
them back whatever happens, writes ``shadowFill`` onto both, and answers the
document's ``effects3D`` read back; ``SetDocumentFrom3D`` re-aims a document
already there -- none can be deleted through the API -- and copies
``effects3D`` whole from a document the run just made with shadows, rather
than guessing a bit.

**One document per hour, overhead, Archicad's sun.** ``archicad.shadow_plans``
makes a document per date and hour at altitude 90, which the add-on snaps to
a top view with the project's +Y up, with the sun as a date so it is
Archicad's; takes the storey filter off before and after (D98); pins a view of
each to the layer combination, the planned renovation filter and 1:1000; and
deals them onto sheets by day, captioned in the fills' words, with the
placement the sun views use (``sun_eyes.place_on_sheets``, shared). The days
and hours are the shadow diagram's own, so the two routes draw the same
instants under the same names, and the window's Shadow diagram tab has both.

**What the documents cannot say, they do not pretend to.** A document shows
the whole shadow of its layer combination; the split between existing and
additional shadow is the fills' alone. A set name puts two runs -- two
combinations -- side by side to be compared sheet against sheet, which is
how the office compared them by hand. The fills stay the argument, and the
documents are the record, and the route for a model too big for the caster.

### D124 — Licence keys are time-limited per subscription period, signed with Ed25519 from the standard library, and checked offline

Asked on 28 September 2026 (roadmap R5): licensing that sends a licence code
to the buyer's email, so that Loriini can be used; and on 29 September, that
Loriini will be sold by subscription, so the keys should be time-limited.

**A key per paid period.** Every key carries its last day: the end of the
period paid for, as the shop dates it, plus a week's grace so a renewal email
that arrives late -- a card retried, a junk folder -- stops nobody on a
deadline. Each renewal brings a new key. Offline keys cannot be revoked, and
under a subscription they need not be: one not renewed lapses when its last
key does. Seats are printed on the key and not counted, since there is
nothing offline to count them against.

**Ed25519, written here.** The check runs at every start on a workstation
with no administrator rights, so it is in the bundle, and a runtime
dependency is a conversation here (D106). RFC 8032's reference algorithm is a
page of integer arithmetic that Python's ``int`` and ``hashlib.sha512`` do
exactly (``sun_study.signing``); it passes all five of the RFC's Ed25519 test
vectors, agreed with the ``cryptography`` package on two hundred random keys
when written, and makes every decoding check the RFC asks for -- a coordinate
past the prime, a point off the curve, a zero with its sign set, ``S`` not
below ``L``. Verification is about 4 ms and touches only public data.
Signing is the vendor's, on the vendor's machine.

**Written for a person.** ``LORIINI-`` and groups of five in Crockford's base
32, read case-blind with O as 0 and I and L as 1, spaces, dashes and line
breaks ignored; a CRC-32 over everything, checked before the signature, so a
key cut short or mistyped is said as that and not as a forgery; a version
byte first, so a later format is refused politely; and a domain tag under the
signature, so no Ed25519 signature made for anything else reads as a licence
(``sun_study.licence_key``).

**One line decides whether a build takes keys.** ``licence_public_key.py``
carries the public key, or ``None``. With ``None`` nothing about keys reaches
the screen and a build runs on its own term, as the office's always have; the
vendor's ``keygen`` writes the key there, and the next build asks for one. So
an office build and a sold build are the same code. The private key is never
in the repository: ``keygen`` writes it to a file the vendor names.

**Where it is asked for.** The window asks before it opens, in a box that
reads the key as it is pasted and says whose it is and until when, or in red
what to do instead; the info box changes it. The command line refuses a
command that touches a project without a usable key, at the door, with exit
code 5 and the sentence that says how to install one -- and keeps ``--help``,
``rulesets``, ``info`` and ``licence`` open, so a refusal can always be acted
on and the handover build's own start-up check still runs keyless. The
``licence`` command is hidden from the list of commands, as the licence is
everywhere the program is silent about its terms while they hold.

**The build's own term stays as the floor** (roadmap R5's own words): a key
good past a build's ``EXPIRES`` does not keep that build running, so a
prototype that has not been replaced still stops. Set per release, or keep
subscribers on current builds (R6).

**Not done, on purpose.** Remembering the latest date seen, to defeat a clock
wound back: a machine whose clock once jumped ahead would then lock a paying
subscriber out, which is worse than what it prevents. The clock stays the
speed bump it always was, and ``docs/licensing.md`` says so.

**The vendor's side** is ``sun_study.licence_issue`` -- in the package so it
is tested, excluded from the bundle so Loriini never carries the code that
makes keys -- behind ``scripts/licence.py``: ``keygen`` once; ``issue`` per
paid period, numbered from a CSV ledger beside the private key, read back as
a subscriber's Loriini will read it before anything is recorded, and the
email written as an unsent ``.eml`` draft (``X-Unsent: 1``) or sent over SMTP
with TLS; ``show`` for support. The shop's webhook (R7) will call ``issue``
with each invoice's paid-through date.


### D125 — Online keys, kept in force by signed leases from a licence service of our own

Asked on 29 September 2026: "I think I need something online, for monthly sub or
revoking the access", then, once docs/licence-model.md had weighed it, "go with
your recommendations, merge and build the online part".

**A key and a lease.** An online key is an R5 key with a flag set: the licence's
identity, pasted once, kept while the subscription lasts. On its own it grants
nothing. What keeps it in force is a *lease* (``sun_study.licence_lease``):
- what it says: the licence, a one-way hash of the computer, the service's date,
  the last day it is in force, the paid-to date, the seats and how many are in
  use, the version it was given to, and a notice;
- how it is signed: with the same Ed25519 key as the licence keys, under a
  domain tag of its own, so neither can pass for the other.

A key's last day is the end of the first period paid for, where the service
starts from. After that Loriini never looks at it. A flag it does not know
refuses the key as too new rather than reading it as offline.

**Fourteen days, asked once a day.** A lease runs a fortnight past the service's
date, never past the paid-to date plus the grace, and is in force from the day
before it was given: the service keeps UTC, and the Americas are a day behind.
- **When a start asks.** It renews in the background when the lease held was
  fetched on an earlier day. It waits, up to 15 seconds, only when no lease is
  in force: the first time, or after a fortnight offline.
- **How it compares.** Graphisoft's named licences allow 7 days offline, Chaos
  14, and Adobe, Autodesk and JetBrains 30. The same fortnight is how long a
  seat stays taken after its computer's last contact.

**A refusal is signed like a grant**, and carries its reason in a sentence:
withdrawn, lapsed, seats, recalled. Loriini believes it and stops at the next
contact, and nobody but the vendor can forge one to stop a practice. Anything
unsigned from the network is only "the service could not be reached", and
changes nothing.

**Seats are computers used in the last fortnight, with a margin of one.**
Loriini installs anywhere, and a burst of use rotates the seats. A computer
that is replaced frees its seat by itself, and ``licence --remove`` frees one
at once. A computer new to a licence already on as many computers as its
seats is granted, with a notice that says which seat frees itself when. One
more is refused, with the names of the computers holding the seats. A computer
already counted is never refused for seats.

**A recall instead of the fixed term, for online keys.** The service refuses
versions below a minimum the vendor sets, with the reason and where the
current one is. A refusal given to another version is ignored, so updating
lifts it. ``EXPIRES`` keeps binding builds that take no keys, and offline
keys, where nothing else can reach them. A keyed build with no key is asked
for one before its term is mentioned.

**The clock.** A computer whose date is earlier than the day before its lease
was given is told to set its clock right, with the service's date. A clock
that once ran ahead is never punished afterwards, which was D124's objection
to remembering dates. Off the network, a clock held inside the fortnight still
works, as any check made offline would.

**The service is ours** (``sun_study.licence_service``).
- **What it is.** The standard library, SQLite, a WSGI app behind the host's
  TLS, one small container (``deploy/licence-service``).
- **Why ours.** R5's keys and signing were already built and tested, and every
  service for sale would still need a server of ours for Stripe's webhooks.
  Its signing key is the trust anchor, pinned in the build, so no third party's
  outage or certificate can lock a practice out.
- **The ledger.** It numbers and keeps every licence. A genuine key it has
  never seen is taken in from what the key says.
- **The vendor's side.** Behind an admin token: issue, look up, change,
  withdraw, restore, free a seat, recall, notices, and a backup that is the
  SQLite file itself.
- **Kept out of the program.** Nothing Loriini imports reaches it (a test
  says so), and the bundle leaves it out, as it leaves out ``licence_issue``.

**Stripe, directly, in AUD** (docs/licence-model.md §5).
- **Webhooks.** Each is checked against the endpoint's secret with a
  five-minute tolerance, and handled once by event id. What arrives about a
  subscription before its checkout is noted and taken up when the licence is
  made.
- **Checkout.** It makes the licence, issues its online key, and emails it.
- **Payments.** Only ``invoice.paid`` moves the paid-to date. A subscription
  starts its next period before the card has paid for it.
- **A failed payment** puts its date on every lease while Stripe retries.
- **The grace** is 14 days, Stripe's retry window. A subscription set to end
  loses it, and gets it back if it is set going again.
- **Other buyers.** A practice paying by invoice gets ``paid``.

**What the check sends:**
- the key;
- the computer's hash: Windows' machine GUID and the user's name, hashed with
  the product's name, or an identifier made once where there is no GUID;
- ``user on computer``, so a practice can tell its seats apart;
- the version.

Nothing about any project is sent. This is a deliberate change from R6's "no
identifier", and the privacy note says it.

**Whose licence made a result.** The CSV and JSON headers carry a ``licence``
line, and the Zone property *Solar Analysis Run* carries it beside the time. A
build that takes no keys writes neither, so its files are unchanged. A trial's
reads "trial licence".

**Not done, on purpose:**
- floating seats with heartbeats, and accounts or logins: later, if a large
  practice asks;
- seats by Graphisoft ID: once the add-on targets Archicad 28, whose API has
  the identifiers;
- obfuscation, which only makes antivirus software more suspicious;
- rate limiting beyond the host's;
- a trial stamp drawn on sheets: every sheet already says "not validated for
  submission" while the prototype notice stands. The stamp is due when that
  notice goes.

### D126 — A refusal for "ongoing user input" is waited out, not failed

Seen on 7 October 2026, on the site tools. The run had made the Context
Analysis worksheet, asked for it to be double-clicked in the Project Map,
seen it come to the front, and sent its next command -- and Archicad
refused it with code 4001, *Invalid program status (ongoing user input)*.
The connection read every 4001 as a modal dialog left open, told the person
to close a dialog that was not there, and stopped the run. The person had
done exactly what was asked; the mouse was still down from the double-click.

**The same code means two things, and Archicad says which.** With *there is
an open modal dialog: X* the API is refused until a person closes X, and the
run can only say so and stop. With *ongoing user input* it is refused for as
long as a hand is on the mouse or a field is being edited, which is a moment.
So `ArchicadConnection.run_official`, which every add-on command also passes
through, sends a request refused for ongoing input again every second for up
to thirty seconds before it gives up, and gives up in words that say what to
let go of rather than what to close. The dialog case still fails at once:
waiting on a dialog nobody is told about would look like a hang.

**Thirty seconds, silently.** Long enough for a drag or a rename; short
enough that a field left mid-edit is reported within the minute. Nothing is
printed while it waits: the connection is also used in the agent's server
process, whose stdout is the protocol (D120), so it has nothing to print
with. The stop file is not watched either; thirty seconds is less than the
runner's own patience.

### D127 — The yield analysis is the office's feasibility template, cell for cell, with its efficiencies as the rule

Asked on 8 October 2026 (roadmap R3): the office put its *Feasibility
template* -- *Preliminary Yield Analysis*, an .xlsx with a sheet per
option -- in the project folder and asked for the yield study to produce
that table, for two massing options in the open project, and to follow
the template's efficiencies strictly.

**The template's arithmetic replaces the earlier sheet's.** The area
calculation of D122 had two uses at 0.75/0.9 and 0.85/0.9 and a yield
rounded down and split by the largest remainder. The template has three
uses -- residential, commercial, retail -- at *BEA to GFA* 0.725, 0.85 and
0.95 and *GFA to NLA* 0.85, 0.9 and 0.9, a permissible FSR split by use,
and units that are the residential GFA over the mix's *average GFA* (the
average NLA over the residential GFA-to-NLA), shared into the mix by its
shares and between a market and an affordable mix by a share of the GFA,
*not rounded*: 220.575 units is what the sheet says. Parking is each type's
units by a rate under the SEPP and under the DCP, visitors over every unit,
commercial and retail GFA by a space per so many square metres, and the
basements at 40 m² a space over the share of the site a basement may take.
``rules.area_yield`` is that, with the template's every figure as a
default and a setting; the template's own *Option 01* is the test fixture
and comes out to the cent. The earlier rounding was a view the tool took;
the office's sheet is the office's view, and it is the one asked for.

**The workbook is the template, filled, not a table of Loriini's own.**
Somebody who knows the template finds the site in C6, the permissible FSR
in C10:C12, the units in D29:E33, the efficiencies in C86:E88 and the
storey table from J113, with the inputs in red as the template has them and
everything else a formula (``report.area_table``). A mix of other than five
types moves the rows below it down; the storey table takes as many rows as
the massing has levels. The columns the office fills by hand -- units per
level, the ADG counts -- are left empty with their formulas in place. One
sheet per option: the workbook keeps each option's data as JSON on a hidden
sheet, so a run reads the options already there and writes them all back
with its own added or replaced (``report.xlsx`` grew several sheets, a
hidden one, and a reader for one cell). A workbook without that sheet is
one Loriini did not write, and is refused rather than overwritten: the
office's template lives in the same folder.

**A slab stands where its height says, not where its storey does.** The
Darlinghurst options are stacks of storey-thick slabs -- 4.3 m for the
ground, 3 m above -- every one homed on the GROUND storey and offset up, so
a table by home storey would be one row. Tapir gives a slab's reference
plane (``zCoordinate``), the offset of its top from it and its thickness;
the underside is worked from those, undersides within half a metre are one
level, and the levels are named up from the one nearest the project's
storey called Ground (``rules.area_yield.levels_from``). The floor-to-floor
is the rise to the level above, and the top level's its own thickness when
the slabs are storey-thick.

**An option on one layer has its use told by level.** Each Darlinghurst
option is one layer, podium and tower together, so a layer per use could
not say what was retail. A *massing* layer's slabs take their use from the
level they stand on -- the levels named retail, the levels named
commercial, the rest residential -- beside the layer-per-use way, which
stays. Which levels are which is the office's to say; a level moved from
one use to another is also one number moved between columns in the
workbook's storey table, and the formulas follow.

**The look is the template's, lifted once.** Asked on 9 October, seeing
the two side by side: the office's sheet is boxed, barred in green, its
inputs red, and a plain grid of the same numbers is not the same sheet.
``scripts/extract_feasibility_style.py`` reads the template's style table,
its theme, its column widths, its row heights and the style index of each
of its 1,720 cells into ``report/feasibility_style.py``, generated and
committed, so the program ships no data file and never opens the template;
``xlsx.Workbook`` takes that style table verbatim and the yield sheet
styles each cell as the template cell it stands for -- the same address in
the blocks that do not move, a role's row where a mix has more or fewer
types, and the first, middle and last level rows for the storey table --
and writes the template's blank styled cells too, so the boxes close.

**Several options are one run.** Each option is usually its own layer, so
``--option-layer`` (the *Option layers* picker) takes any number, reads the
slabs once, and makes every option -- a sheet and a layout each, named
after the layer's OPT number -- with the levels indexed across all of them
together, since a tower option with no ground floor of its own would
otherwise read its lowest floor as the ground. The retail and commercial
levels are ticked from a list rather than typed, as the layers are.

**What was assumed for the two options.** The office did not say which
podium levels are retail or commercial. The two sheets were run with the
ground floor retail, the first level commercial and the rest residential,
the LEP's one FSR read at the address and written on the residential row
with a note; the run's log says so, and both are one flag or one cell to
change.

### D128 — A start proves the model with any element, and moves the database without the window

Reported on 9 October 2026, and there since the beginning: when Loriini
opens, Archicad's floor plan is left "stuck" -- deaf to the mouse until
another tab is clicked. The window's first read of a project runs
``ensure_model_database``, which had to prove that the current database was
a floor plan before trusting any read, and its proof was the walls. A
massing project is slabs and has no walls, so on every such project the
proof failed, the check went to the Project Map and made the ground storey
current through Tapir's ``ChangeWindow`` -- which ends in
``ACAPI_Window_ChangeWindow``, a window switch made from inside an API
command. That switch is what leaves the plan half-activated.

**Any element is the proof.** ``GetAllElements`` -- the walls only where an
add-on is too old to have it. A massing, a site model, a project of
zones: all read, and nothing is moved. An empty project reads as empty and
is moved as before, harmlessly.

**When the database has strayed under a floor plan, only the database is
moved.** The add-on's own ``SetCurrentDatabase`` (D95) changes the current
database with ``APIDb_ChangeCurrentDatabaseID`` and touches no window; so
with a floor plan in front it is tried first, and Tapir's ``ChangeWindow``
is the fallback -- for an add-on that lacks the command, a refused move,
or a layout in front, where the window itself has to change for an export
to see the building. The connection notes the move as it notes
``ChangeWindow``'s, so the layer guard stays on.

### D129 — The window after its first sale: the terms it was sold under, and nothing learnt by hovering

Asked on 10 October 2026, after the first live purchase, for a review of the
window as a subscriber meets it, and then for every finding to be fixed.
The review was made from the window itself, opened over a fake project and
photographed page by page.

**About shows the terms the build was sold under.** It summarised the
repository's source-available licence -- the firm it was written for, the
MIT versions, "passing it outside the firm needs written permission" --
to a practice that had just accepted the subscription terms, while the
LICENSE.txt beside the program said otherwise. A build that takes licence
keys now shows ``licence.TERMS_SUMMARY`` and *Read the full terms* opens
``site/terms.html`` as text, by ``sun_study.terms``, the renderer that also
writes the download's LICENSE.txt; the bundle carries the page for it. A
build without keys, which is the source, keeps the source licence.

**Every control says what it is without being hovered.** The choice tiles
carry a word beside their drawing (*One layout*, *Floor heat map*, *Project
location*); labels the review found opaque are spelt out (*TOD envelope*,
*SEARs envelope*, *Ignore ground below (m)*, *3 zone layers*); the top bar
says *Connect Claude* and *About* where it said *Add to Claude* and showed a
bare (i). Every row label carries an icon, or a clear square the size of
one, so the labels on a page start at one line -- the Yield page had none
and sat a column to the left of every other page.

**Run says what it will run.** *Run 3 studies*, or *Tick a study to run*
and off, where it looked ready with nothing ticked and answered a press
with a line at the foot of the window.

**Space that said nothing is given back.** The sheets panel waits at its
edge while nothing is ticked and comes out at the first tick, unless it was
opened by hand; the progress trough is shown only during a run; the licence
line moved to the right of the run's own line instead of a row of its own.

**The same card in the same place.** *Days studied* is the first card on
all three sun pages; it was first on one and last on the other two. The
sun views' hours open lit at the ruleset's window, as the shadow diagram's
do, and lit exactly so they send nothing, so the ruleset's window stands.

**Smaller.** The no-location notice on a thumbnail is shorter and stops
short of the title block; the grid of drawings ends clear of the title
under it; the licence box's text field has the theme's one-pixel edge in
place of Tk's black focus ring.

### D130 — The window on a Mac: one label column, Run filled, About in the program menu

Asked on 11 October 2026 for a review of the Mac build's window, page by
page, and then for every finding to be fixed. The review was made from the
window opened from source on a Retina Mac and photographed tab by tab.

**Nothing is cut off.** A study's header is placed at ``PANEL_HEAD`` and
the tick heading it asked for 34 px of the 29 it is given at a Mac's
four-thirds type, so every study's name lost its descenders. On a Mac the
tick has no vertical padding and is centred in its slot; Windows is as it was.

**One label column.** ``LABEL_COLUMN`` was measured against Segoe UI, and
the Mac's longer labels outgrew it, so each card widened its own column and
the fields started at a different place on every card. After the build,
every card takes the width of the widest label in any of them.

**A field is as wide as what goes in it.** Numbers and prefixes are twelve
characters; lists of the project's names thirty-six; the address, the
custom day and the other worded fields still run the card.

**The strip stands still.** The open tab's bold name is wider, so every tab
after it moved as tabs were opened. The tabs share one width.

**Run is filled.** D109 had it tinted, on the grounds that solid blue beside
grey reads as a warning; in use it read as the sixth of six equal buttons.
It is now the one filled control, with the play disc knocked out white, and
the grey face when there is nothing to run. Save as default, the presets
and Forget act on the window rather than the project and share one
*Settings* menu at the right of the bar. The chosen tile keeps the tint Run
used to wear (``face_chosen``).

**The project bar is about the project.** Refresh is the one button beside
the picker; the reference image and Claude are flat tools that tint under
the pointer. On a Mac, About is in the program's menu with the data
sources and the last log under Help; Windows keeps the button, having no
program menu to put it in.

**No Archicad is not a fault.** The picker says *No Archicad open* and the
line under it gives the next step beside a drained plug with no red mark
(``waiting``); the red mark stays for a project that answered and could not
be read.

**The folded sheets panel says what it holds** -- *No sheets yet*, *21
sheets* -- in body type, and the whole strip opens it, not only its chevron.

**Tk 9.** ``Combobox.current`` raises on Tk 9 when the text is not one of the
values, which a Mac's Tk is; ``_picked`` reads it as none chosen, and the
first Refresh to find an Archicad no longer stops there.

The drop-down's arrow is a drawn chevron rather than clam's boxed arrow,
which inside a rounded field read as a second button. The orange marks on
the sun studies' icons were looked at and kept: ochre is the sun.

**The Mac window was a third too big, and opened across the screen.** Asked
the same day, from the built program on a laptop: "the font and window is
too big ... ideally 75 or 50 percent". ``MAC_POINTS`` assumed a Mac's Tk
counts a point as a pixel and scaled every size by four thirds; Tk 9 already
counts 1.33 pixels to the point, so the type came out a third larger than
it was drawn, and every measurement taken from it -- the tabs, the label
column, the width the window opens at -- grew with it. The factor is now
worked out from the Tk's own ``scaling`` (``theme._fit_points``). Clam's
floor of eleven characters under every tab is gone, each tab keeping room
only for its own name in bold; and on a Mac the window opens on at most
three quarters of the screen either way (``Window.MAC_SHARE``), the sheets
panel starting folded when that leaves too little room beside the page. On
a 1512 x 982 laptop the window went from 1471 x 856 to 1090 x 736.

**The reference picture and its palette are two windows again.** Asked the
same day: the picture "is connected to the reference image option window
... moving and resizing together". D121's one palette glued the controls'
foot to the picture's top edge, so the controls went wherever the picture
was lined up -- over the model -- and the picture could be no narrower than
the strip. Now each moves and sizes on its own; *Over Archicad* and the
first placing lay only the picture, and the palette stays where it was put.

Tried on the Mac, three more: the corner must hold the top-left, the
palette must never be under its picture, and a locked picture must let the
mouse through. The corner now sets the frame's position with its size --
given a size alone, a Mac kept the window's bottom-left, its own origin. A
press or release on the picture, and every showing of it, lifts the palette
back over it. And a Mac has a click-through of its own: ``-[NSWindow
setIgnoresMouseEvents:]`` on the Cocoa window Tk made for the picture,
found by its title (``overlay.MAC_TITLE``) among the application's windows
and called through the Objective-C runtime with ``ctypes``, as the Windows
half goes through user32.

### D131 — Option A: a sidebar of pages, panels that fold, and the help in the sidebar

Asked after a design review (the "Loriini Design Review" canvas, Option A
chosen out of two): "modern but still Archicad like". Built as close to the
mock-ups as Tk allows.

**A sidebar replaces the tab strip.** The strip's 32 px drawings took about
140 px off every page, and its only mark for *queued* was a blue name and a
dot. The pages are now rows down the left in three groups -- SET UP, STUDIES,
TOOLS -- the way Archicad lists the pages of a settings dialog. The open page
is a rounded blue bar; a study page has a switch that queues it and a pill
with the sheets it will make. A page with several studies (Solar analysis,
Shadow diagram) turns its lead study on from the sidebar and all of them off
(``Window.LEADS``); the others are switched on the page.

**The help is a card at the foot of the sidebar.** The band across the foot
of the window cost every page three lines of height. The card says the same
-- what the thing under the pointer is, what it is set to, and what happens
when it is wrong -- in room the sidebar had spare, and never covers a field.
The sheets panel's hover goes to it too.

**Panels.** Headed by a fold triangle and their name in sentence case, not
capitals; a study's header carries its count and a switch where the 12 px
tick was. A study switched off starts folded; switching it on opens it.
Labels are right-aligned against their fields and the icon on every row is
gone. Choice tiles with words are segments: words only, the chosen one blue.

**The bars.** The tool bar is the program, the project picker (as wide as a
name, not the window), Refresh, and one menu holding Connect Claude… and the
settings actions. The run bar is one line: the project's status, what is
queued by study, the build, and Run -- which counts sheets ("Run 6 sheets")
the way the panel draws them. Stop is shown only during a run.

**Tools › Reference image.** The controls that were a palette window are a
page; while a picture is open the main window is kept on top and lifted
over it, so the picture can never cover them. The picture's window is made
the first time there is a picture.

**Sheet miniatures.** One text style -- one size, regular, ink -- on shared
baselines: the name and the hours at the foot of the field, level with the
scale and the number in the title block, with north at the block's top-left.
The wordmark, the block's placeholder rules, the circled numbers and the "No
project location" line are gone; at 300 px they were noise.

**The drawings on them, in the drawing set's own palette.** Checked with every
study on, against the review's mock-up: the site boundary red and dash-dotted,
the massing grey in the heaviest line, neighbours light, a flat in the sun
amber and one in shade hatched, the ADG total blue or orange, and every
shadow hatched -- by hand, ``_hatch``, since Tk on a Mac draws no stipple.
A cell's hour is inside the cell (under it, it sat on the drawing below); a
drawing is fitted to the site, not to the square around it; a title too long
for its line is cut short rather than wrapped up over the drawings; and the
title block is wide enough for 1:3000, with "NTS" for a sheet with no scale.

**A fault found on the way.** ``option_add("*Font", body)`` filled in every
ttk label's own ``-font``, which beat the style -- so every bold title in the
window had been set in the body face. ``*TLabel.Font`` is now left empty.

**A narrow page rearranges itself.** With the sheets panel open on a laptop
the page is about 560 px wide -- less than a row of hours beside a 200 px
label column -- and the first build cut the rows off at the panel's edge.
Asked the same day: "the sheet panel can't overlay the middle panel like
that ... restructure the middle panel". Below ``ROOMY_PAGE`` the label
column narrows and its labels wrap, every row of buttons wraps inside its
panel (``_wrap``: the choice tiles, the days, the hours, the unit mix), a
study's caption wraps to the panel, and a list of the project's names gives
up the 36 characters it asked for. So the panel stays open beside the page
from about 1100 px (``PAGE_LEAST``), and folds only below that. The room a
row has is worked out from the page's width, not read off the panel: a
panel is as wide as what is in it, and measured from there each wrap made
the next.

Before a project has a location, the sheets panel draws the sun over Sydney
(``STAND_IN_PLACE``), Archicad's own preset. Earlier it drew no sun at all,
because a shadow cast at a guessed latitude looks right without being right.
In practice a shadow diagram with no shadows on it showed nothing worth
checking. The card says the sun is Sydney's until the project's location
is set, and the run itself still uses the project's real location. Shadows
are clipped to the site, so a long morning shadow stays inside its cell.

On 12 October 2026, from the Windows build: "there is no reason to have
archicad layers in two rows. there is plenty of space even with sheets open".
A page under 720 px wrapped every label, and with the sheets panel open on a
1260 px window the page is about 690 -- beside fields with a third of it
spare. The labels now give up their width only when the fields beside a
full-width column would have less than ``FIELD_LEAST`` (280 px); the rows of
buttons still wrap to whatever room they have. The same sitting found the
window slow: every keystroke and tick redrew all of the sheets panel's
miniatures, about 70 ms of a 180 ms sync, and now the panel is redrawn only
when its sheets or its filing line change. The project picker is as wide as
the longest project's name, from 34 to 72 characters, because an office's
file names ran past 34 before the port.

The same day, two more from Windows. The reference picture's corner slid the
picture as it sized it: a Toplevel's bindings fire for every widget inside it,
so a pull on the corner ran the picture's move as well as its resize, and the
top-left followed the pull. The move now ignores a press that starts on the
corner, and a test drives the corner through Tk's own events rather than
calling the handlers, which is how the first test missed it. And a sidebar row
drew Tk's dotted focus box after it was clicked, beside the blue bar of the
open row: the rows now go without the ring (``theme.NO_RING``), as the tabs
and tiles already did.

The ☰ menu carries About and the web site on both platforms, since the
menu is where the program's own things now are. Trackpad scrolling follows
Tk 9's ``<TouchpadScroll>``, which it sends in place of the wheel on a Mac.

### D132 — The window refreshed: a pale accent under ink, rounder corners, a warm ground, Inter

Asked 23 October 2026, after the web site was rebuilt (D-site, `docs/website.md`)
and the window was put beside it: *"have a deep think about good redesign of
it. to make it look better. maybe more rounded edges. lighter green or
yellow. just to make it look fresher"*, with two references -- pale lime bars
under black figures, and a lemon ground under a magenta line -- and, from the
three drawings that followed, the lemon chosen: *"lemon. build it into the
app!"* Two earlier drafts were refused on the way and are recorded so they
are not drawn again: a dense, flat, Ableton-like instrument panel with
monospace labels (*"too much"*), and pixel marks in the sidebar and on the
day buttons (*"i dont like the pixel like things. just forget them"*).

**What the references share is one idea.** Both put pale colour under dark
text. The window did the opposite: a dark blue that carried white, which is
Windows' own way of saying *chosen*. Flipping that is the whole redesign.
Once *chosen* is a pale fill with ink on it, the open sidebar row, the chosen
day, the switch that is on and the Run button all become light shapes on a
light window instead of dark blocks, and the window lifts without any other
trick. So the accent is a pale lemon, `theme.ACCENT` `#FFF07A`, with its
tint `#FFF9CF` for a chosen card's header and a chip, its edge `#E6D65A` for
a hover and the rule under a chosen header, and `ON_ACCENT`, which is ink,
for whatever sits on it. Nothing in the interface is blue any more. The
icons and the sheet thumbnails keep theirs, deliberately: they are pictures
of the interface drawn in Archicad's blue, and a picture of a chosen thing
is not the chosen thing. `theme.BLUE` and its three companions stay for
them, and say so.

**The ground is warm.** `CHROME` is `#F1F0E6`, the web site's sage lightened
to an off-white; the page is a shade lighter still, `#F8F7F0`, a rounded
panel the white cards sit on. The sidebar and the dock are the surround's
own colour: neither is a panel of its own, the rows and the cards on them
are the things with edges. D109's reason for Archicad's neutral grey -- that
a warm grey "made it look like a different program parked on top of"
Archicad -- was weighed and set aside: the warmth is slight, the window
still sits beside Archicad's grey, and it is the one thing that says the
window and the site are the same product. The help card at the sidebar's
foot is a white card like the others.

**Rounder, and flat.** Eight pixels on a control, twelve on a card, ten on
the open sidebar row; the corner slices of the nine-slice faces follow
(`FACE_SLICE` 9, `PANEL_SLICE` 13), one more than the radius so the curve
is never in the part that is tiled. No face is lifted any more: the pixel of
shadow under a button and the two-stop ramp across it are gone, and a face
is one colour and one edge. A switch that is on is the one dark shape in
the window -- an ink track with a lemon knob -- so it reads as *on* on the
surround and on the open row alike. Fields keep an edge that clears 3:1 on
white, as before; a button's edge is lighter, as before.

**Inter.** The face the site is set in, carried in `assets/fonts` (Regular
and Bold, with its OFL licence) and registered for the running process
alone with `AddFontResourceEx(FR_PRIVATE)` when the theme is applied:
nothing is installed, no administrator is asked, it is gone when the
program exits. GDI is what Tk enumerates fonts through on Windows, so a
face registered that way is one Tk can be given. Anywhere that fails --
not Windows, no files, a GDI that refuses -- the window is set in Segoe UI
as it was. A Mac takes the same face, registered through CoreText with
the process scope (`CTFontManagerRegisterFontsForURL`), and falls back to
the system's own (D130) where that fails; the sizes go through `points` as
before. Both builds carry the folder: the Mac spec takes its collection
from `Loriini.spec`.

**Where it was decided.** On a design canvas, with the window as built
rendered beside the drawings from the program's own code, so the comparison
was against the real thing and not a memory of it. The drawings are
`Fresh.dc.html` (lime) and `FreshLemon.dc.html`; the window follows the
lemon one.

*What this does not change:* the layout, the controls, the words, and the
principles of D109 except where its text named the grey, the blue and Segoe
UI; those lines in `theme.py`'s docstring now read as D132 has them.

### D133 — The sheets in the panel rounded, on the button's edge and lift, in the window's greys

Asked 23 October 2026, with D132 on screen: *"open claude visual artefact for
sheets. they are not right. make them fresh too. maybe with rounded corners.
not know. do multiple designs. look at colours used there. maybe even
illustation there should be little rounded."* Five were drawn on a page at
the panel's own width -- the sheet rounded with its title block kept; a card
with the block turned under it as a footer; the drawing alone on a tile with
its words under it on the chrome; a card with a lemon cap, after the study
boxes; the number worn as a chip -- and the first chosen: *"please, make it
Rounded sheet."*

**The paper is a face.** Eight pixels of radius, the button's edge
(`theme.FACE_EDGE`, `#CFCEC3`, the figure the faces are drawn with) and one
pixel of lift under it, ink at a tenth over the chrome. It was square since
D-dock, on the grounds that paper has corners and that was the line between
the interface and the thing it makes; beside D132's rounded window the
square sheets read as holes cut in it. The ink frame a printed sheet
carries goes with the corners: the paper's own edge is the frame now, and a
second line a few pixels inside a curve reads as a misregistration. The
title block stays where General sets it, with its rule and the rule over its
two figures in the divider grey the cards use, not ink. Under the pointer
the rim turns the lemon edge every button turns, at a pixel and a half,
where it was ink at two. The models, which have no paper, keep their rim
hollow and take the same lemon.

**The drawing is rounded too, by two pixels, and warmed.** Every block,
boundary and table on a miniature is a `smooth` polygon with its corners
cut, which is the one way Tk's canvas rounds anything, through `_rounded`;
a boundary gets a pixel more than a block it rings. Bands that meet edge to
edge -- the facade's, a plate's cells -- stay square, or a notch opens at
each join. The streets on the context sheet end round. The greys were
Archicad's cool ones, `#E4E4E4` and `#EDEDED` under `#8D8D8D`, and beside
the lemon chrome they read blue; they are the window's warm greys now
(`MASSING`, `NEIGHBOUR`, `NEIGHBOUR_EDGE`, `ROAD`, `RING`). The boundary's
red and the pin's blue stay: they are a drawing set's conventions, not the
interface's colours, and D132 said as much of the thumbnails' blue.

*What this does not change:* what a sheet says, where its words sit, the
block's width, and the panel round it.

### D134 — A page settles into place as it opens, and that is the only movement

Asked 23 October 2026, with the rounded sheets (D133) on screen: *"can you
introduce good profesional ux? smooth effects when you click between tabs"*.

**One movement, and small.** When a page opens, it settles into place from
twelve pixels off, over 180 ms, easing out -- fast away from where it
started and slowing to a stop. Which side it comes from says which way the
person went: down the sidebar and the page rises into place, up it and the
page drops. Nothing else moves: no fade (Tk cannot blend a widget, and a
fade faked with a cover would cost more than it says), no bounce, nothing
the person waits for. Opening the same page again moves nothing, and a
page opened before the last has settled finds that one put in its place at
once.

**How, in Tk.** Tk has no animation; it has `after` and a canvas item that
can be moved. Every page is one item in its `Scroller`'s canvas, so
sliding a page is moving one item, which Tk does without laying anything
out again; the scroll region is re-measured once it has stopped. The frames
are paced by the clock and not counted, so a page slow to paint arrives in
the same time as a quick one with fewer steps. The page is in place in
the window from the moment it is opened -- `_show_section` packs it and
returns -- and the movement is the item in its canvas, so nothing in the
window, and no test, waits on it. All of it is `app/motion.py`.

**And none of it where none was asked for.** macOS's Reduce Motion
(`defaults read com.apple.universalaccess reduceMotion`) and Windows'
client-area animation setting are read once, when the first page opens,
and a page then opens where it belongs with no movement at all. Any doubt
about what the system said -- no such tool, a key never set, a hang -- is
taken as *move*: the setting is a request for less, and less is the
default already. A window nobody can see (a test's, or one withdrawn)
moves nothing either.

*What this does not change:* which page opens, when, and what it says.

### D135 — A sun date is read in Archicad's own clock, and the add-on says what that is

Asked 24 October 2026: *"i want you to check current project which is
opened. sample project. I want to work on shadows diagram via 3d doc"*. The
Graphisoft sample project -- the Sheung Wan tower, 7,785 elements, 23
storeys, in a diamond of site context -- open in Archicad 30 on the Mac,
with the add-on answering. The second live run of the shadow plans after
Redfern (8 October, R1), the first on a Mac, and the first on a project
whose time zone was not the hours' own.

**What held.** Three documents for 21 June in 3.4 s; the shadows on and
drawn in the `50 %` fill, `effects3D` 128 read back from each; the plan
north up and matching the floor plan exactly (a first look read a quarter
turn into it; the *site* is a diamond, and the walls in model coordinates
are at 0 and 90). A re-aim takes: tilted to 45 degrees from the south and
set back, the document redrew each time. A second run found the three by
name, re-set them, and made the sheets once a master was named. The stacked
run made its two combinations -- the named one with the context on and the
tower's nine layers off, and with them on -- four documents and two sheets
in 17 s, the pens matched from the legend's colours.

**What did not: the hour.** Loriini's sun at 09:00 Dubai stands at 43.6
degrees; Archicad's documents carried the sun of 10:00. Measured where the
sun can be read back, the 3D window: `SetProjection` with the date 21 June
09:00 and `GetProjection` after it gave azimuth 5.8 and altitude 57.1, and
this tool's own sun for 10:00 Dubai is altitude 57.14 at bearing 84.2 --
90 minus 84.2 is 5.8, so Archicad's `sunAzimuth` runs anticlockwise from +X
toward the sun, like its camera azimuth. The same date with `summerTime` on
gave 9.8 and 43.6: this tool's 09:00. So Archicad reads a sun date in the
project location's own time zone, `API_PlaceInfo::timeZoneInMinutes`, +180
on this file against Asia/Dubai's +240, with the daylight flag taking an
hour off. Loriini sent the wall-clock of `--timezone` with that zone's
daylight flag, which agrees with Archicad exactly where the project's zone
is that zone's standard offset -- an AEST project with Sydney hours, which
is why Redfern showed nothing -- and is an hour out anywhere else.

**Decided.** The sun stays a date, not a pair of angles: the point of a
date was that a disagreement would show on the drawing, and it did. What
changes is whose clock the date is in. The add-on reports the project
location whole, zone included (`Loriini.GetPlace`); `archicad.clock` turns
the instant into that zone with the flag off, so 09:00 Dubai goes over as
08:00 and Archicad draws 09:00 Dubai under a document still named for
09:00; and the run prints whose clock the hours are in, with one worked
example. An add-on built before `GetPlace` cannot say, gets the old
behaviour, and the run says the clock is unknown rather than guessing --
a quiet guess here is the hour's error that was found.

**Also found and fixed.** The run's advice for a subset the Layout Book
does not have named `--layout-subset`, which `shadow-plans` does not have;
the filing now names the flag the command took the name from. Not changed:
at 1:1000 an A3 cell shows about 150 m around the model origin, which is
right for the office's sheets and small for this site's 420 m diamond.

**Verified the same afternoon,** with the new bundle installed and Archicad
restarted on the sample project: `GetPlace` answered `timeZoneInMinutes`
180; the rerun printed *Archicad's clock is UTC+03:00 ... 09:00 as 08:00*
and re-set the three documents; and the 3D window, handed the same date the
documents now get -- hour 8, flag off -- read back altitude 43.6 and
azimuth 9.8, this tool's sun for 09:00 Dubai, where hour 9 reads 57.1.

*What this does not change:* which hours are drawn, their names and
captions, the fills' route, or the sun views' own sun -- they take the same
clock, through the same function.

### D136 — The sheets drawn as what the run makes, the info box as a page of the window, and the lorikeet as the mark

Asked 24 October 2026, with the rounded sheets (D133) on screen and the
manual's own output sheets open beside them: *"redesign the sheets so they
look better, more united with an app"*, then, over seven rounds on a
mock-up of the panel, *keep the right strip instead of a down strip, as is
typical for sheets*; *remove the north mark*; *the communal heat map should
look like the apartment heat map, pixelated*; *the facade bands should
respect the colour bands of the heat maps*; *the site and context pictures
full wide, with no margin*; *the sun could be more fun*; *not sure with the
blue*; *the building we do should be red*; *not a U but an O, with the COS
courtyard*; *the sun on the site, where there is more space*. Then: *"apply
the lemon theme also on About Loriini"*, and a pixel lorikeet, *"add this
logo to the app top left corner instead of the current one"*.

**The paper and the block stay; what is on them changes.** A sheet is still
D133's rounded paper with its lift, the field 10 mm in, and the title block
down the right at the width General sets -- a strip on the right is what a
sheet has, and a caption rail along the foot, tried first, read as a card
and not as a sheet. The block is drawn as a title block is printed: four
lines of text at its head and two lower down, as bars in the divider grey
too small to read, which is what they are at this size; a rule at the foot
boxes the scale, in the hint grey, over the sheet number in the chip the
sidebar wears (lemon-tinted, hairline edge, ink on it, fully lemon under
the pointer with the sheet's edge). The north ring goes: the master carries
one, and a ring that was the only mark in the block read as the block's
subject. Under the field, level with the block's two fields, the name at
the body weight and under it the hour and which of a pair it is, in the
hint grey -- one size still, two inks now, which is how every card header
in the window is set. The hour under a cell is centred and in the same
grey.

**Each study in its own colours, taken from the sheets it makes.** The
panel's drawings were one grey box under every study, and a reader could
not tell a shadow sheet from an apartment sheet without the words. Now the
context sheet is a grid of streets with the lots washed lilac where the
LEP zones them, a park, the rail line with its station and the five-minute
walk round it in the interface's blue, and the site red on its block; the
site sheet is the aerial's terraces running back from two streets, the
street trees' canopies, three contours across the slope in ochre, the lot
with a circle at each survey corner and its frontage dimensioned, the pin,
and the sun. Both run to the edges of the field, as the map and the aerial
run to the sheet's margin on paper -- laid out inside the frame by
construction, because a Tk canvas clips nothing. On an apartment sheet the
sun stands where it stands at the hour, with eight rays and no dot in it,
its light reaching the window wall of every flat it is in as a pale amber
beam (pre-blended: no alpha on a canvas) and inside each lit flat the amber
wedge the plans show falling across the floor; the hatching goes. The
whole-day sheet grids each floor and bands it cell by cell on the communal
legend's seven steps, and the ADG total shows each flat in the two
answers: the sun's amber for one that reaches the two hours, the warm grey
of no sun for one that falls short -- not blue, because on these sheets
blue is the pin and the rail line and never an answer. The communal space
is a courtyard building, a ring of flats round the open space, which is the
shape a reader knows a communal open space by -- a U, tried first, read as
a plan of something else -- with the courtyard gridded the way the study
samples it and banded on the same seven steps, three trees over it and the
sun on the site's north side where the boundary leaves it room; the hourly
sheet is the same ring with the wings' shadow swinging across the courtyard
and the sun crossing above it. The shadow diagram draws the town's own
shadows in grey and the proposal's extra shadow in the blue the diagram
tells it apart with, the lots over them and the boundary over those. A sun
view is the white town the 3D Documents draw, the proposal a storey taller
in the heavier line with its glazing lit yellow on the face the sun
reaches, and the sun over it. A schedule has a tinted heading row and its
labels and figures held inside their columns; the yield sheet is the
section beside the office workbook's green-headed table. The two models
gain the terrain's contours, the streets, the verge trees and a heritage
block in the run's ochre; our building is the red block among the grey
neighbours, the fetch radius a grey ring, and the facade model's skin is
banded by storey on the heat maps' ramp, the top floors in the most sun.
`HOURS_RAMP` grows from four steps to the legend's seven and is the one
way the panel says hours of sun; the colours added are each the colour of
a thing the run draws (`ZONING`, `CANOPY`, `CONTOUR`, `SHADOW_CAST`,
`SHADOW_EXTRA`, `GLAZING`...), and the window's greys, blue and red stay.

**The info box is a page of the window.** It was a white sheet of prose
with separators between headings, themed but of no place. It is now the
window's own anatomy: a chrome band at the top with the mark, the name,
the version in the window's chip and the author and copyright lines under
them; the page under it, with a white card per section headed the way a
settings panel is headed; and a chrome band at the foot with the buttons,
the one action -- the full terms -- in the Run button's lemon. `look_at`
scrolls to a card rather than a heading, and the licence text window
stands on the page grey.

**The mark is the lorikeet.** The pixel bird, on no tile, standing on the
chrome at the top left: `assets/loriini-mark-32.png`, reduced from the
1024-pixel artwork with a proper filter (Tk can only drop pixels), with a
64 for later and the artwork beside it. The application icon and the Dock's
picture are not touched: a tile is right for a Dock and wrong for a tool
bar.

*What this does not change:* what a sheet says, how many sheets a tick is
worth, the grid a sheet is dealt on, the block's width, the hover and the
figures in the band below, the panel's heads and day lines, what the info
box says, and anything the run itself draws in Archicad.

### D137 — The sheets take the generator's themes, each realised as what Archicad has

Asked 24 October 2026: *"introduce the themes for context analysis and site
analysis. its basically visual upgrade of what we have now. you need to look
on github au-site-analysis repo to get the themes so you can implement them
for archicad use."*

**The themes are the generator's, as data.** `au-site-analysis` draws its
context sheet in four graphic templates and its site sheet in four themes of
the same names -- Flamingo, Kingfisher, Heron, Canary -- each a record in
`src/render/template.ts`: a land-use palette, the inks, which line styles,
which marks. They are ported colour for colour into `sun_study.site.theme`
as the same kind of record, so the two programs agree about what a house
style is and a new one is a data change here as it is there. The office's
own Oatley legend, which `curate.CATEGORIES` holds and these sheets were
drawn in until now, stays as a fifth theme on both sheets, so a saved preset
or a `--from` redraw still produces what it did, and so the refactor had a
fixed point: the Oatley drawing is asserted unchanged by the tests that were
already there. The defaults move to the generator's (Flamingo, Heron),
because the ask was the upgrade.

**Each theme is realised, not approximated.** The generator prints to a PDF
and Archicad is not one, so every property a theme has was mapped to the one
thing Archicad can do in its place, and the mapping is the port:

- *Opacity.* A fill has none. On paper the tint is blended over white before
  it is sent (`Category.on_paper`), which is what a reader sees of a 22%
  peach; over the aerial it is the project's `50%` fill in the colour, as D82
  already had it.
- *Texture.* A fill pattern scaled for 1:100 reads solid at 1:3000 (the
  heritage hatch found this), so a texture is a hatch of the drawing's own
  polylines at 2 mm on paper in the texture's ink: 45° for lines, crossed for
  cross, and dots as lines in the project's `Dotted` line type, `Dashed`
  standing in where there is none.
- *The aerial in grey, under a veil, with the site in colour.* No command
  tones a Figure and none masks one. The tile is toned with Pillow -- which
  D121 already brought into the bundle -- and written beside the original as
  `aerial_r_c-grey36.jpg`, the site's lot composited back in its own colours
  from the untouched tile; the original and its world file are never
  touched, and the toned copy is reused while the original is no newer. A
  theme that keeps the colours keeps the white `50%` wash instead.
- *White streets.* The register has centre lines, not kerbs. A street is its
  centre line widened to the reserve its function hierarchy suggests, 30 m
  for a motorway to 6 m for a lane, mitred at each bend with the mitre
  clamped, round-ended, as one fill per road feature rather than a rectangle
  and a disc per segment -- 6,000 fills were already the sheet's measure.
- *The office's drawn marks.* Its suns, winds and arrows are SVG paths taken
  from its symbol sheet. `site.marks` flattens them: M, L, C and Z, a cubic
  walked in six straight steps, the subpath inside another made its hole
  (the eye's pupil), and the y axis turned over, since the office drew with
  it pointing down. The crown sun, the crescents and the hand-drawn strands
  are ported as the generator computes them, seed and all.
- *Text scale.* It multiplies the map's words and not the sheet's: the
  title, the legend and the credit keep their size, because they are the
  sheet's and a credit has a size for a reason (D117).

**What is not themed, and why.** Fonts: `CreateTexts` takes no face, and a
face that is not installed falls back silently, which the generator's own
header warns is worse than none. The potential views, the indicative kerbs
and the neighbours' height limits: the Loriini bundle carries no sight
lines, no kerbs and no `HOB` per neighbour, and a theme is a way of drawing
what is there.

**Where it is chosen.** `--theme` and `--site-theme` on `sun-study site`,
`theme` and `site_theme` on the agent's site tool, and a *Context style* and
a *Site style* row on the window's Site analysis page, saved with the
preset. Two rows and not one, because the office's packages put a context
sheet on paper beside a site sheet on the photograph; the site themes name
the context theme they draw on, so the pairs still match when a person wants
them to. The retired names resolve as the generator's do: `conure`,
`flamingo-2`, `dove`, `cardinal`, `kookaburra`.

**What the first live run found** (Parramatta, 24 October 2026, all four
themes on both sheets). The dotted line type was there, the toned tiles
placed like the originals, and the crescents, arrows and lot fills went in
whole. What Archicad refused was geometry, eight fills in all, and each
refusal was a rule of its own:

- *A zone a kilometre past the sheet.* Fit in Window showed a 3 km extent
  for a 276 m sheet. Zone, institution and heritage fills are now cut to
  the map field (`_clipped`, Sutherland-Hodgman against the field's four
  edges, which may be turned). A hole is cut to a window 30 cm inside the
  field, so that where both it and its outer ran past the sheet the hole
  still sits strictly inside the outer's cut edge.
- *The site under the zone wash.* Canary's site is meant to keep the
  photograph's colours; the site's lot is now a hole in the zone it lies in.
- *A street strip that crossed itself* at a tight bend: the mitred strip is
  kept where it holds and a rectangle per segment with a disc per joint
  drawn where it does not.
- *A cut zone that pinched* -- came back through a point it had passed, or
  within two centimetres of an edge: Archicad refuses both. The ring is
  split into its loops at the pinch (`_loops`), a near miss first snapped
  into an exact one (`_pinched`), and the smaller loop parted from the
  shared vertex by five centimetres (`_parted`), so a loop that becomes a
  hole no longer touches its outer.

And one bug of the run's own: with `--no-site` the fit step read
`site_rings` off the context bundle, which has only `site_lots`.

*What this does not change:* what either sheet says, where the site lands,
the layers, the element IDs, the credit, or anything about the context model.

### D138 — The legend goes on the layout, the places are numbered, and the map is centred from the bottom margin

Asked 24 October 2026, with the Untitled project's layouts on screen: *"the
layouts are slightly shifted. also the legend should be in layout in the
right as it normaly is. you dont need legend in worksheet it self but mainly
on the layout"*, and while that was being done, *"can you put numbers instead
of names of institutions in analysis, as it is in site-analyst.com outputs?"*

**The shift was two things.** The one on screen was stale: the layouts had
been made by an earlier run with the site centred, and the two runs after
were `--no-layout`, so when the site moved onto its corner nobody moved the
drawings -- 12 mm on the context sheet, about 100 mm on the site sheet. A run
with layouts remakes them, and read back with `GetDrawings` both drawings'
origins sat within 0.05 mm of where the site's centre puts them. The other
was a real bug that this master's equal margins hid: `_sheet_frame` centred
the field vertically from the *top* margin, and layout coordinates run up
from the bottom-left (`docs/addon.md`), so on a master with a deeper top
margin the map sat low by the difference. It is centred from the bottom
margin now.

**The legend is the layout's.** The office's sheets keep the legend in the
column to the right of the map, over the title block, and a worksheet is the
drawing, not the sheet. So `_legend` records its rows on the drawing, the
elements carry the part they belong to, and when the run will make a layout
the legend is taken off the worksheet (`Drawing.without`) and drawn straight
onto the layout at paper size: from the frame's top, 8 mm right of it, as
wide as the column, the long labels broken onto a second line. The legend's
swatches are fills, so drawing on paper now takes fills as well as rules and
texts; `CreateFills` leaves a missing layer at the Fill tool's, which is what
a layout element wants. The master is settled before anything is drawn, so a
person is asked once, and a run that cannot have one -- `--no-layout`, or no
master given and nobody to ask -- keeps its legend in the worksheet. The
legend is never on neither.

**The places are numbered, as site-analyst.com draws them.** Ported from
the generator's `sheet.ts`: every institution and park a solid disc with its
number in white, ordered institutions by legend category then open spaces,
each name once; the key under the legend; stations `T1`, `T2`... nearest the
site first; the key's rows tightening past two dozen and, past what the
column holds above the title block (`LEGEND_FOOT_MM`, 90 mm), the nearest
places kept and numbered again; discs on one block pushed apart. A theme
field, `places`: the four site-analyst themes number, Oatley names, because
Oatley is the sheet as it was first drawn. The legend's station and bus rows
show the roundel itself now, not the letter alone.

**Heron's sun path and the noise, as the generator draws them.** Asked the
same day, with Heron's site sheet open: *"the sun path is not actual and
noise line is not right."* Each solstice's path is now Heron's white band,
2 mm wide in a 0.7 mm grey pen, summer's whole and winter's in 6 mm dashes
5 mm apart, the hour dots and the crowns and strands in the same pen; it had
been a bare grey line. And the noise had been the office's zigzag drawn on
every theme along the road's own centre line, which the generator never
does: it runs beside the source on the site's side and breaks where it would
cross the site or leave the sheet -- Heron and the two paper themes as a
white band swelling gently in the noise pen 11 mm out, Canary as the zigzag
10 mm out. Oatley keeps the zigzag on the road, as first drawn.

*What this does not change:* the worksheet's map, its title, north point and
credit, where the site lands, and the site sheet's content.

### D139 — Each sheet has a pen table of its own, and the colours are the generator's

Asked 24 October 2026: *"control the colour if they are accurate. compare
the site-analyst output with created analysis by colour. if there are
differences. create custom pens"*, and *"also go through all themes to check
correct colours"*.

**Measured three ways.** The palette, field by field against the generator's
`template.ts` (loaded with Node and dumped as JSON): three differences --
Flamingo's site buildings are edged 1.5 mm, not 0.8; its wind band is
`#5ba8e1`, not Kingfisher's `#4aa3e8` it had inherited; and the generator's
Canary site sheet draws on Flamingo for what it does not set, not on Canary.
The colours the generator's site sheet sets outside any theme
(`siteSheet.ts`): its trees in Flamingo's park teal at 38%, its parking in
the plum at 35% (a hatched zone at 18% under lines of the plum's ink), bus
stops a white disc in a `#2f7fd6` ring, the muted building `#d9d9d6`, white
lots at 0.7 mm, contours at 0.6 mm, and no railway line on the site sheet;
all now so in its four themes, Oatley keeping what it was first drawn in.
And what Archicad paints: every colour a theme draws a pen in, against the
nearest pen of the Untitled project's active table -- every theme off, most
by 15 to 30 colour-difference units and some by over 50.

**The pens are the sheet's.** A pen table per sheet, named for it, copied
from the model's active one with the sheet's colours written exactly into
pens 255 downward (a sheet uses 15 to 25; there is room for 120), its view
set to it. Never made active for the model or for layouts, and a sheet's
view shows only the tool's layers, so the overwritten pens mean nothing else
there. One table per sheet and not one for both, so that rerunning one sheet
in another theme cannot recolour the other. The office's `Site Analysis` pen
table is the fallback when the table cannot be made.

**The layout legend takes none.** A layout's own elements draw in the
layouts' pen table, which is the title blocks', and that is not the tool's to
rewrite. So on paper every colour is a fill's RGB: lines become the thin
fills that draw them (dashes as dashes), a contour of a colour of its own
becomes its line, and every fill's own contour is a white 0.01 mm hairline.

**Two choices of hand.** Archicad lines have no opacity, so Flamingo's lots
(the road grey at 60%) are drawn in the blend, `#bababa`. And the generator
draws the traffic arrows white in every theme, which on the paper themes is
white on the white road; they are white over the photograph here and stay
the road grey on paper, where they can be seen.

**Oatley is called FUSE.** Asked the same day: *"call oatley FUSE"*. The
theme is the office's own legend, still read off its Oatley (2546) sheet,
which is where the old name came from. `oatley` and `office` still resolve
to it on the command line, and a preset saved with "Oatley" in a style row
draws FUSE.

*What this does not change:* what a sheet shows, or any fill's colour.

### D140 — The Yield page asks which slabs and which renovation status, and shows only the rows the answer needs

Asked 24 October 2026, with the Yield page on screen: *"the yield is a
little too much to set up. is there posibility to simplify this? usualy you
just have different slabs. maybe you should have possibility to select
renovation filter. the options are confusing. think of easier way of doing
this."*

**Seven rows were four ways of saying one thing, all asked at once.**
Option layers, three use layers, massing layers and two level rows sat one
under another, and which of them a run would read depended on which were
filled -- a rule the page never said. They are the answers to one question,
so the page now asks it: *Slabs*, four tiles -- *Everything showing* (the
usual answer, use told by level), *Chosen layers* (the same, on the layers
chosen), *Layer per use*, *Layer per option* -- and shows only the rows that
answer reads, usually just the two level rows. A hidden row sends nothing,
so a layer left in it from another day cannot change the count. Nothing went
to an Advanced panel: the window's rule (its own docstring) is that a section
does not hide its inputs somewhere else, and none is hidden here -- the
answer decides what is asked.

**The renovation filter is chosen, not set beforehand.** Tapir can carry a
renovation filter's GUID onto a view but cannot list the project's filters
by name or set one on the floor plan, so choosing a filter by name would
need a new add-on command and a rebuild. What a filter decides is each
element's *Renovation Status*, which is a built-in property Tapir does read.
So *Renovation* is four tiles -- *Any*, *New only*, *Existing and new*,
*Floor plan's filter* -- the first three read off each slab
(`--renovation-status`), the last the old checkbox's behaviour. Measured on
the sample project: 453 slabs, all Existing, of which *New only* counts none
and says so. The status is read in the project's language; English, German
and French are known, and any other word is reported rather than guessed.

**A preset saved the old way opens as what it meant**: option layers filled
read as *Layer per option*, use layers as *Layer per use*, massing layers as
*Chosen layers*, and the renovation checkbox ticked as *Floor plan's filter*.

*What this does not change:* the command line's flags, which still combine
as before, and the arithmetic.

### D141 — A 3D Document draws its shadows on its surfaces, so two documents cannot stack into one split

Asked 24 October 2026, after the clock was put right (D135): *"I need to
see 2 shadows in one drawings in different colours"*. The stacked shadow
plans (`shadow-plans --existing --proposed`, shadow-plans.md) were made for exactly that
-- the existing set's document over each proposal's, the upper one's uncut
surfaces unfilled so the proposal's pen shows wherever only the proposal
casts -- and on the sample project the stacked sheet showed outlines and no
shadow.

**Measured.** The Existing 09:00 document, read back: shadows on
(`effects3D` 128), a solid fill in its pen, uncut surfaces unfilled. In its
own window: outlines only. `SetDocumentFrom3D` with `fillUncutSurfaces`
true and a rebuild: the whole shadow picture, at once. Back to false: gone
again. The plain documents, whose surfaces are filled, had shown their
shadows from the first run. So Archicad draws a 3D Document's vectorial sun
shadows as fills *on its surfaces*: no surface drawn, nothing to draw a
shadow on. A document that draws its surfaces is opaque, so two documents
cannot stack into one drawing with the split between them. The stack as
designed cannot work in Archicad 30, and the dev kit's uncut-surface
options -- `uncutSurfaceFillType`, `uncutSurfaceBkgPen` -- choose how the
surfaces are filled, not whether a filled surface hides what lies under it.

**Decided, and overtaken the same evening by D142.** The stacked mode stays, since its documents and sheets are
made correctly and may be wanted, but the run says plainly that the split
does not show and where it does: the fills route. `sun-study shadows` with
`--shadow-source` and `--shadow-scenario` draws existing and additional
shadow in two colours on one plan by construction, and ran on this model
the same afternoon -- the full tower, 534,000 triangles, exported in 58 s
and cast in 80 s, 95 fills on three layers and two sheets. The 3D
Documents' comparison is the two sets side by side, as before the stack.

**Also found.** The project location had been set to Sydney between the
restart and this run, so the fills asked for in Dubai time came back as
night at noon and 3pm; `--timezone` has to be the location's. The fills'
sheets at 1:1000 on an A3 overflow the page for a 420 m site; the run
neither says so nor scales down. An A1 was asked for instead; whether the
reused layouts took the new master is for the next look at the sheets.

*What this does not change:* the plain shadow plans, their sun (D135), or
the fills route's drawing.

### D142 — The stack draws on surfaces filled in the transparent pen, and takes the fills' legend

Asked 24 October 2026, after D141 and after the fills route was run in its
place without asking: *"why you produced fills? this should go only by 3d doc
route"*, and then *"the combinig 3d docs with multiple colours for shadow is
the main way. please stick to it and try to make it work. kind of same
categories as in previous version - you select layers of different object.
neighbour building, neighbor future building, proposed TOD etc. and want one
sheet with all"*. The fills, their views, sheets, layers and combinations
were taken out of the sample project first; the shadow diagrams are the 3D
Documents' from here, and the fills route is not run in their place.

**The lever.** D141 found that a document draws its shadows on filled
surfaces only, and a filled document is opaque. The Archicad 30 kit's
`API_UniformAttributeOptions` has two more fields than the add-on wrote:
`uncutSurfaceFillType` -- the Model Display's *Pen color*, *Material color,
shaded* and *not shaded* -- and `uncutSurfaceBkgPen`, the pen a *Pen color*
fill is drawn in; and pen 0 is `APIPen_Transparent`. The same fields are in
the Archicad 26 kit, so every build takes them. `CreateDocumentFrom3D` and
`SetDocumentFrom3D` now take `uncutSurfaces {fill, fillType, pen}` and read
it back, and `ArrangeDrawings` takes a drawing's own `transparentBackground`.

**Measured, sample project, Archicad 30 on the Mac.** The Existing 09:00
document set to filled, *Pen color*, pen 0: its shadows drew in their pen
(236, a pale green in this project's table) and the surfaces drew nothing,
white with their outlines. A stack of two rows, neighbours over the tower,
made in that mode with every upper drawing's background transparent: in each
cell the neighbours' shadow in its pen and, where only the tower casts, the
tower's -- except that the lowest document, left on the materials' colours,
drew its shadows as the material shaded darker, dark grey, ignoring its pen.
Put in the same *Pen color*, pen 0 mode, it drew them in its pen, 156, a
pale blue. So every document of a stack takes the mode, the lowest too.

Two more things the same evening. A drawing of a 3D Document is **not
redrawn** when its document's settings change, and opening the layout does
not do it: the sheet kept the dark grey until Tapir's `UpdateDrawings` was
asked for. The combined sheet now asks for it after every run, best effort,
since it needs Archicad 27. And reopening a project does not reload an
add-on: the new build took only after Archicad itself was quit and started,
three tries in.

**Decided: the legend.** The stack takes the fills' own rows, from the same
words and the same parser: `--shadow-source` rows accumulate, `--shadow-scenario`
rows are compared, `LABEL=layer,layer`, coloured by the legend's name or by
role and position. `--existing` and `--proposed` remain as the short way for
one row that stands and the proposals, and the two do not mix. A layer
combination per row (a source shows itself and every earlier source, a
scenario every source and itself), a document per row and hour, and one
**combined** sheet set, `15 | Shadow Plans Combined - JUNE 21`, with every
row's drawing of an hour in one cell. The order, bottom to top, is the
scenarios in the order named and then the sources from the last to the
first: a document draws its whole shadow and a drawing is seen only where
everything above it casts nothing, so the first source shows whole, each
later source what it adds, and each scenario what it adds over every source,
the last named over the earlier where two overlap -- the fills' legend, with
the subtraction done by the order on the sheet. The window's Shadow plans
box takes the Shadow diagram page's legend rows, so one legend is chosen
once for both routes; the agent's tool takes `sources` and `scenarios`.

**Run.** The neighbours as `EXISTING`, the tower's structure layers as
`PROPOSED`, 21 June at 9, 12 and 3, one A1 sheet: six documents and the
sheet in 18 s, a rerun in 12 s with the drawings redrawn. The tower's
additional shadow showed south-west at 9, south at noon and south-east at
3, and nowhere the neighbours already shade.

*Still to do:* the legend and the site outline on the combined sheet; a page
size or scale that fits a wide site, since each drawing is clipped to its
cell; and the colours, which are the nearest pens in the project's table --
on the sample project the legend's pale grey matched a pale green.

### D143 — The combined sheet: the site fitted, the legend's colours, the legend and the site on it

Asked 24 October 2026, after D142's first combined sheet, which left three
things the D142 entry named: *"well continue, to correct the rest"*.

**The site fitted.** Each drawing is placed by its own origin at its cell's
centre and clipped to the cell; a 420 m site at 1:1000 in a 230 mm cell was
cut at both edges. The run now measures the plan extent of everything the
rows show -- read-only, from the 2D bounding boxes of the model elements on
the layers the rows' combinations show; Archicad's element list includes the
elements of hidden layers (6,115 of them on the sample project, measured),
so the filter is by layer, not by what is on screen -- and puts each
drawing's origin where that window's centre lands in the middle of the cell.
With no `--scale`, the scale is the largest standard one at which the window
fits a cell of the chosen master, which is now settled before anything is
made, since its page is what a cell is cut from. And the grid follows the
window's shape: three cells dealt to waste none were three strips 166 mm
wide, 1:5000 for the sample's square site; dealt to draw it largest, two by
two at 269 x 243 mm, 1:2000.

**The legend's colours.** A 3D Document's shadow is a pen, and the sample
project's table had no pale grey: `EXISTING` matched pen 236, a pale green.
Pinning a pen set on the views changed nothing, and nor did placing the
drawings fresh after pinning it: a drawing of a 3D Document prints in the
model's active pen table. So the run makes `15 | Shadow Plans` with Tapir's
`CreatePenTables` -- a copy of the table the drawings print in, each matched
row's pen set to the legend's exact colour; matched first, so a pen moves
only a little and whatever else is drawn in it hardly changes -- and the
add-on's `ArrangeDrawings` gives every drawing that pen table by index
(`penTableIndex`). Live: pen 236 printed at (235, 235, 235) and pen 156 at
(156, 172, 191), the legend's own. A pen given by hand keeps its colour;
Archicad 26 has no `CreatePenTables` and keeps the nearest pens, as the run
says.

**The legend and the site.** On the sheet, in the column left of the title
block that every study's legend takes, the cells keeping clear of it: the
title, a swatch per row in the exact colour the drawings print it in, drawn
with the add-on's `CreateFills` in that colour, and the legend's words. The
site is the boundary layer's outlines -- a layer whose name mentions a
boundary, its slabs' `polygonOutline` on the sample project -- drawn in the
red nearest the layout's pen table with the project's empty fill, so only
the contour shows, over every plan where the drawing puts it. Three things
the first live attempt found: the add-on closes a contour itself, and a ring
that already ended where it began is a zero-length edge Archicad refused the
fill for (-2130313102); Tapir's per-type element list answers for the
current database, which after the sheets is a layout, so the boundary is
read from the whole model's list as the window is; and a fill drawn after
the drawings still lands at its tool's display level, 6, under the drawings
at 14 -- the outline was there and could not be seen until it was moved to
14 with Tapir's `SetDetailsOfElements` `drawIndex`. All of it goes on
Archicad's own layer, which no combination hides, and is cleared and redrawn
every run.

**Run, sample project.** `EXISTING` and `PROPOSED`, three hours on one A1:
the plans drawn at 1:2000 two by two with the whole 421 m site in each, the
drawings in the stack's own pen set, the legend and three boundary outlines
on the sheet, 17 s; the outlines read back at the top level over the plans.

*What this does not change:* the stack itself (D142), the hours and their
sun (D135), or the plain set's sheets beyond the same fit.

### D144 — The 3D Documents are the shadow diagram; the fills draw the design's every hour

Asked 25 October 2026: *"the 3d doc is the main route there. try to make 3 -
4 - 5 3d doc shadows. the original route with computation of shadow now will
be only used for actual design mass, in case when we need to see shadows
made by our design in every hour in one drawing. basicaly 7 shadows of one
building in one drawing, besides that, when it involves neighbour building
we use 3D doc"*, with three layers of slabs added to the sample project --
`SHADOW 2` for the future context, `SHADOW 3` for TOD, `SHADOW 4` for SEARs
-- *"please update the diagram so every layer has different colour shadow
... after that please build the shadow of every hour of proposed building
seen. use floorplan for fills"*.

**Decided.** Two routes, one job each. A diagram that involves the
neighbours is the stacked 3D Documents (D141 to D143), as many legend rows
as the project has. The fills -- Loriini's own caster, the route the shadow
diagram began on -- are kept for one drawing: the designed building's own
shadow at every hour on one plan, which the documents cannot draw, since a
document is one hour. `sun-study shadows --shadow-all-hours-only` draws that
and nothing else: the every-hour outlines labelled by hour on the floor
plan, its combination, its view and its sheet; no fill, layer, combination,
view or sheet per hour. It implies `--shadow-all-hours`, and refuses without
a designed building (the `PROPOSED` row, or the last scenario).

**Five rows, run.** `EXISTING` (the neighbours) and `FUTURE` (`SHADOW 2`) as
sources, `TOD` (`SHADOW 3`), `SEARS` (`SHADOW 4`) and `PROPOSED` (the
tower's structure layers) as scenarios, 21 June at 9, 12 and 3: fifteen
documents and one A1 at 1:2000 in 49 s, stacked TOD < SEARS < PROPOSED <
FUTURE < EXISTING, each row's pen -- 236, 216, 196, 116 and 156, the nearest
in the office's `00 ENZ PRINT` -- printed at the legend's own colour through
the run's pen set. One thing the run said wrongly and now does not: a row
an earlier run had made, stacked over a row made in this one, was re-set
without the new documents' shadow switch, and the run said every document
had been there before. The switch is now carried from set to set.

**The every-hour drawing, run.** The tower over the neighbours and the
ground, 21 June at every hour from 9 to 3: one layer, `15 | Shadow
Diagram.JUNE 21 ALL HOURS`, carrying nineteen outlines and seven hour
labels and no fill, its combination, one view and one sheet, `15 | Shadow
Diagrams - JUNE 21 ALL HOURS`, in 5 min 43 s, most of it the export and the
cast of seven hours over half a million samples.

*What this does not change:* the stack, its fit, its pen set and its legend
(D141 to D143), and the fills route's own per-hour diagram, which a run
without the new flag still draws.

### D145 — The every-hour drawing is a fill per hour, empty, on a continuous line

Asked 25 October 2026, of the design's every-hour drawing (D144): *"for some
reason you choose dense dotted line. there is no reason to use this. if
anything use continuous. but it should be a fill. not polyline"*.

**Why it was dotted.** Each hour's outline was a polyline made through
Tapir's `CreatePolylines` with a pen and no line type, so it took the
Polyline tool's default -- `Dense Dotted` on the sample project. Nothing
chose it; nothing chose against it either.

**Decided.** Each hour's outline is a fill, made through the add-on's
`CreateFills`: its contour in the outline pen on a named continuous line
type (`Solid Line`, `Solid` or `Continuous`, first found), its pattern the
project's empty fill (`Empty Fill`, `Empty` or `Background`), its background
the transparent pen. Empty, because the seven hours lie over one another and
a filled hour would hide the ones under it; a fill, so each hour is an
element a person can select, measure, or give a pattern of their own. Not
tagged with the study's Element ID, so a schedule of the shadow areas does
not count the design's whole shadow seven times. A project with no empty
fill is told which to add before anything is drawn, rather than given seven
solid hours of which only the last shows.

**Run, sample project.** The tower, 21 June at every hour from 9 to 3: the
earlier run's nineteen dotted polylines and seven labels cleared, nineteen
fills drawn in `Empty Fill` with a transparent background, the seven labels
again, no polyline left on the layer; 5 min 29 s, the export and the cast.

*What this does not change:* which shadow is drawn, the labels, the layer,
its combination, view and sheet (D144).

### D146 — The continuous line is the main line of the context and site sheets

Asked 25 October 2026, after the design's every-hour drawing came out in a
dense dotted line nobody had chosen (D145): *"the solid line needs needs to
be the main line in your context and site analysis"*.

**Why it could have been anything.** The context and site sheets name a line
type only where a line is meant to be dashed or dotted -- the site's outline,
the uncanopied trees, the bus routes, the catchments. Every other line and
every fill's contour was sent with none, and an element given no line type
takes its tool's own: the Polyline tool's or the Fill tool's, whatever a
person last left it on. On the sample project the Polyline tool was on
`Dense Dotted`, which is how the every-hour drawing came out dotted.

**Decided.** The sheets look the continuous line type up by name -- `Solid
Line`, `Solid` or `Continuous`, first found -- with their other attributes,
and send it on every line and every fill contour that is neither dashed nor
dotted, on the worksheets and on the layouts alike. Dashed and dotted keep
their own. A project with no continuous line type by any of those names
keeps the old behaviour, the tool's own. The combined shadow sheet's site
outline (D143) is sent it too.

*What this does not change:* any colour, weight or pen, any line that is
meant to be dashed or dotted, or which elements a sheet draws.

### D147 — The shadow fills are the office's: 25 %, drafting, red or blue, no outline

Asked 25 October 2026, with a screenshot of the every-hour drawing (D145)
showing each hour as a solid black block in a thick jagged outline: *"when
you create shadows, make them 25%, drafting fill, red or blue without
outline. this is correct setting"* -- the Fill tool set to `25 %`, Drafting
Fill, fill pen 45 (red), background pen 0, the outline off.

**Why black.** The add-on draws a fill from the Fill tool's defaults and
changes only what it is told. The every-hour fills were not told their
category, so they took the Fill tool's, and drawn as that category under
the floor plan's model view options they came out solid black; their
contour, in pen 1 with the tool's weight, was the thick outline. The same
was true of the shadow diagram's own legend fills and the combined sheet's
swatches and site outlines: none named its category.

**Decided.** Every fill the shadow routes make names `drafting`. The
every-hour drawing is drawn as the office draws its shadow fills: the `25 %`
fill (`25 %`, `25%` or `Percent 25`, first found), in the pen nearest the
office's red -- (204, 9, 32), its pen 45 -- or with
`--shadow-all-hours-colour blue` the nearest blue, a transparent background
and no outline (contour pen 0). Dots rather than a solid, so the seven hours
over one another all show. A project without the 25 % fill is told before
anything is drawn. The stacked 3D Documents keep their solid shadows: the
split between the rows is the upper rows covering the lower, and dots would
let every row show through every other.

**Run, sample project.** The tower at every hour from 9 to 3: nineteen fills
in `25 %`, pen 45, background 0, contour 0, seven labels, no polyline; read
back through Tapir, which does not report a fill's category.

*What this does not change:* which shadow is drawn, the hours, the labels,
the layer, its view and sheet (D144, D145), or the stack (D141 to D143).

### D148 — A combined cell shows one title, the hour's

Asked 25 October 2026, with a screenshot of the combined sheet (D142):
*"when you overlay shadow 3D docs, the names are crashing. is it possible to
tunr name of drawing only on one of the drawings?"*, then *"or name them all
the same"*.

**Why they crashed.** Every drawing of a cell is placed on the same frame,
so Archicad put each one's title in the same spot: five titles, `JUNE 21
-9AM TOD` to `JUNE 21 -9AM EXISTING`, printed over one another, each with
its own drawing number.

**Not the same name.** A sheet finds its drawings by name, on every rerun
(`layout_from_views`, `place_stacks_on_sheets`); five of one name would be
one drawing found and four made again on the next run.

**Decided.** The top drawing of each cell is named for the hour alone,
`JUNE 21 -9AM`, and is the cell's one title; the drawings under it keep the
hour and the row in their names and are given no title -- the title's
library part index set to 0 through Tapir's `SetDetailsOfElements`, which is
how Graphisoft's Element_Test example removes one -- and are left out of the
sheet's drawing numbering, so the titles that remain read 1, 2, 3. A top
drawing without a title, one that lay under another on an earlier run, is
given the title the others wore. Done after every placement, best effort: a
refusal is said, the sheet stands. The bundled Tapir already reads and
writes the index, so the add-on is unchanged and Archicad need not restart.

**Run, sample project.** The five-row sheet, rerun: fifteen drawings, the
three top ones titled with index 32 (Archicad's own drawing title), the
twelve under them with index 0, no title element and out of the numbering;
the 9 AM top drawing, its title removed by hand to try the index, was given
it back. The three top drawings of the earlier run, named `... EXISTING`,
were renamed by hand once, so the rerun reused them instead of placing new.

*What this does not change:* the stack, its order, colours or transparency
(D141 to D143), or the sheets of one row, whose drawings keep their titles.

### D149 — The every-hour sheet is fitted to its shadows

Asked 25 October 2026, of the every-hour drawing's sheet (D144): *"can you
place correctly shadows in the plan on the layout?"*

**What was wrong.** Read back on the sample project, the sheet `15 | Shadow
Diagrams - JUNE 21 ALL HOURS` carried a 78 x 86 mm drawing at 1:1000, its
lower-left corner at the middle of an 841 x 594 mm page, while the shadows
it is for spread 214 x 142 m. Two causes. The view was made with no zoom,
so it took whatever the floor plan was zoomed to when the run reached it,
and the drawing showed that much of the plan; and the drawing was put down
by its corner where the one cell's middle is, as `layout_from_views` puts
every drawing, and never arranged. Most of the shadow was outside the frame
and what was inside sat up and right of the middle.

**Decided.** The drawing step records, per day, the plan extent of the
every-hour fills and their labels. The sheet is then made as the combined
shadow plans make theirs (D143): the view's zoom is that extent with 10 m
round it, the scale the largest standard one at which it fits the sheet's one
cell clear of the title block, and the drawing is arranged through
`place_on_sheets`, its origin set so the extent's middle is the cell's and
its frame clipped to the cell. `--drawing-scale` now defaults to none: given,
it is the every-hour sheet's scale as well as each hour's; left out, each
hour's sheet stays at 1:1000 and the every-hour sheet is fitted. The run
says the extent and the scale.

**Run, sample project.** The tower at every hour from 9 to 3: the shadows and
their margin 234 x 162 m, drawn at 1:500 on `A1 Landscape`; read back, the
drawing is at 1:500, clipped to the cell from 34 to 707 mm across and 34 to
560 mm up, its origin placed so the cell's middle is project (25, -55.5) --
the middle of the shadows -- with all of them inside the frame.

*What this does not change:* the fills, their style or labels (D145, D147),
the hourly sheets' placement, or the combined sheets (D141 to D148).


### D151 — The lorikeet over the L is the icon, and the icon is the mark

Asked 25 October 2026, with a new picture: a pixel lorikeet, wings open,
perched on the foot of a black L on an orange square -- *"I need to change
the icon of loriini everywhere"*.

**One artwork for every place.** `assets/loriini-icon-1024.png` is the new
picture, and `scripts/make_icon.py` writes every size from it as before: the
.ico, the .icns on Apple's grid, the Dock's and the MCP server's 256, the
site's favicon and large icons. Until now the window's top left and the
About box wore a mark of their own, the whole bird on no tile (D136), and the
site's header a head cut from it. Both now wear the icon: the script also
writes `loriini-mark-32.png` and `-64.png` from the tile, `site/icon-52.png`
for the header beside the name, and `site/apple-touch-icon.png`, square and
opaque on the tile's orange, because a phone rounds the corners itself. The
bird-only artwork and the head (`loriini-mark-1024.png`,
`site/lorikeet-head.png`) are gone.

**The square, inside the old rounded tile.** The picture is a square to its
edges and the tile keeps D136's rounded corners: a square icon stands out in
a Mac's Dock and on a Windows desktop beside rounded ones. The wing's tip
reaches the top right corner, and the rounding cut 212 of its pixels, so the
picture is drawn 976 pixels across in the 1024 with its own orange (235, 81,
41) for the margin: nothing of the bird or the L is lost, and the margin is
the ground's colour, so it cannot be seen.

**From the picture that came.** It came as a 360-pixel screenshot, and like
the last lorikeet its squares are not on a regular grid, so it was enlarged
with Lanczos rather than square by square; reducing its colours to a palette
to sharpen the squares lost the purple and the eye's white. Every size people
look at, 256 and under, is a reduction and sharp; the 512 and 1024 a Mac
shows in the Finder's large views are an enlargement and a little soft. A
larger original dropped in as `loriini-icon-1024.png` and the script rerun
replaces all of it.

*What this does not change:* the bird the site's mosaic perches on its tower
(`site/lorikeet.png`), which is a picture and not the mark; the add-on's
palette in Archicad, whose first button is the solar study's sun on a massing
like the others; or the lemon theme around the mark.

### D152 — Site-analyst.com's four styles, and only those

Asked 25 October 2026: *"remove fuse theme from site and context analysis.
its gonna be only those four. give a link on site-analyst.com in explanation
and in about"*.

**FUSE goes.** The context and site sheets are drawn in Flamingo,
Kingfisher, Heron or Canary -- site-analyst.com's four -- and nothing else.
FUSE, the office's own legend over the colour aerial that the sheets were
drawn in before the themes, kept since as a fifth so a saved run would draw
what it drew, is out of both style rows, both lists in
`sun_study.site.theme`, the CLI's `--theme` / `--site-theme`, and the MCP
tool's choices; its retired names `office` and `oatley` go with it. A preset
that chose it names nothing now and is drawn in the default (Flamingo,
Heron), and the CLI says so on the way, as it does for any name it does not
know. The fields' defaults in `Theme` and `SiteLook` were FUSE's values and
stay as they are -- every theme sets what it draws differently, and the
drawing code is not touched.

**Where the styles are from, a click away.** `theme.SITE_ANALYST` is the
address. The two style rows' explanations say the styles are
site-analyst.com's, and under the rows a link, *The four styles at
site-analyst.com*, opens it: an explanation in the sidebar card changes as
the pointer moves to it, so the link is on the page. The info box has a card
of its own, *The sheets' styles*, saying the sheets are drawn in its four,
ported colour for colour and named as it names them, with the address under
it as the registers' terms are.

**Tests.** The drawing tests that read their colours off FUSE now read them
off Heron's palette (the context sheet, the worksheet through the add-on,
the site's dimensions) or Kingfisher's (the neighbours as fills); the tests
of FUSE alone -- the names on the map, the zigzag on the road's own line --
are gone.

*What this does not change:* the four styles, their colours or defaults, or
the office's palette in `curate`, which maps the zones onto the legend's
categories for every theme.

### D153 — Every grey in the window is neutral

Asked 25 October 2026, with the window's picture recoloured by hand: *"also
please change the grey background in software. I redid that in artefact ...
so please do it for all versions"*.

**The rule the picture follows.** Read pixel by pixel against the capture it
was made from, every warm grey in it became the neutral grey of the same
lightness (Rec. 601 luma, rounded) -- the surround `#F1F0E6` to `#EFEFEF`, the
page `#F8F7F0` to `#F7F7F7`, the dividers `#E3E2D8` to `#E1E1E1`, the ink
`#1F1F1D` to `#1F1F1F` -- and nothing with a colour in it moved: the lemon,
its tint, the blue, the ochre. So that is the rule, applied to the source
rather than to a picture of it: every colour in `sun_study.app.theme`,
`window.py` (the sheets panel's drawings) and `scripts/make_icons.py` whose
channels lie within 16 of each other with blue the lowest -- the warm greys,
and the sage of a courtyard -- is that grey now. The bluish pale of the icons
(`#F3F7FD`) is a tint and stays.

**All versions.** The palette is one module for Windows and the Mac alike,
so both builds take it. The icons are drawn from the same figures, so
`make_icons.py` was rerun: 476 of the window's PNGs changed, and the eight
palette icons of the add-on in Archicad, which are neutral now beside
Archicad's own greys. The contrast the comments promise still holds: the
hint grey `#6A6A6A` is 5.4:1 on white, a field's edge `#888888` 3.5:1.

*What this does not change:* the web site, whose pale sage ground the warm
surround was lightened from (D132); the sheets drawn in Archicad; or the
lemon accent and the blue.

### D154 — On Windows the window is set in Archicad's face, and the sheets measure their type

Asked 26 October 2026, testing the merged Mac work on Windows: *"fix that
unsaved-file case! then please check the sheets. miniatures there look of.
also the font, in windows the font should be the same as it is in
archicad"*.

**Archicad's face.** Archicad 26's palettes on Windows are set in the
system's message font: Segoe UI 9 on an English Windows, read off the
registry's `WindowMetrics` and matched letter for letter against a capture
of the Navigator. Tk builds `TkDefaultFont` from the same setting, so
`theme._archicads_face` asks Tk for it rather than naming a face, and a
Windows set in another language gets its own, as Archicad does. Inter is no
longer registered on Windows. The Mac keeps D132's Inter: the request was
for Windows, and on a Mac the window does not sit inside Archicad's frame.

**The sheets measure their type.** A miniature is laid out in sheet
millimetres, which scale with the panel, and lettered at eight points,
which do not. At eleven pixels, which eight points are on Windows, two
figures did not hold: the 13 mm left under a cell
for its hour was shorter than the hour's line, and every hour sat on the
bottom of its drawing; the 34 mm chip was narrower than "SD.01", and the
number ran into its edges. The room under a cell is now the hour's line and
three pixels, and the chip is the number's width and five pixels a side,
within the title block -- each at least what it was.

**A project never saved is read.** Archicad gives one no name, only
`isUntitled`, and the window took a blank name for a project it could not
read: a new file read in full (135 layers, 55 masters, 11 storeys) was
shown as "could not read the project", with every list empty. It is named
`Untitled`, as Archicad's title bar names it, in the picker and in the
probe; the run already said an unsaved project's results cannot be traced
to a file.

*What this does not change:* the Mac's face, the sizes, the drawings
inside the miniatures, or Tk's drawing on Windows, which does not smooth
its edges as the Mac's does.

### D155 — The context sheet draws the buildings, white over the cadastre, on paper

Asked 26 October 2026, looking at the first context sheet drawn on Windows:
*"there are building fills missing in context analysis. is it possible to
get them? there should be white fills over caddaster"*.

**They were never there.** The context bundle fetched the lots, the
zoning, the roads and the transport, and no buildings; only the site sheet
fetched footprints. site-analyst.com's paper sheets, which Flamingo and
Kingfisher are ported from (D152), draw every building white. So the
context bundle now carries OpenStreetMap's footprints over the sheet's
extent -- the site sheet's source, so the two sheets agree and the credit
is one already on them -- and a bundle saved before this reads as having
none.

**White over the cadastre, on paper.** A theme's new `buildings` is `white`
for Flamingo and Kingfisher and `none` for Heron and Canary, whose aerial
already shows the roofs. Each building is a white fill edged in the
cadastre's own ink and weight, on the sheet's Land Use layer, cut to the
map field as the zoning is, its courtyards left open; the legend gains
*BUILDING FOOTPRINTS (OSM)*.

**A fill cannot cover a line.** Archicad draws every polyline over every
fill whatever order they are made in -- a fill's display order is 6, a
polyline's 9 (Tapir's notes in `ElementCommands.cpp`) -- so a white roof
would have had its lot lines and its zone's texture lines drawn across it.
Rather than move thousands of elements up the display order, the lines
drawn before the buildings are cut where they run under a roof
(`_cut_under`), and what is drawn after -- the railway, the bus routes, the
catchments, the stops and the labels -- stays over them, as it should.

*What this does not change:* the aerial styles, the site sheet's
buildings, or the model.

### D156 — No office's presets in the app: tool words for prefixes, no picked names, the wait an hour and off the page

Asked 26 October 2026, with the General page on screen: *"also i need to
strip every company preset from the app ... and remove archicad connection
bracket entirely. as we dont export ifc that way anymore. keep there 1 hour
archicad wait thing, hidden"*. Asked which presets: the layer prefixes,
the built-in view and subset names, the window's guesses by an office's
words, and the shadow legend's project notes -- not the yield sheet's
figures.

**The prefixes are words.** `14 |` to `18 |` and `03 |` were one office's
numbers, chosen to sit after its groups `00 |` to `13 |`; in anybody else's
project they filed the study among groups it had nothing to do with. They
could not simply be emptied: the prefix is how a rerun finds its own views
and layouts to delete (D93), and an empty one matches everything in the
project, so a name a person typed -- a layout called *Shadow Diagram 1* --
would be cleared with the run's. So each tool's default is its own word
and a bar: `Solar |`, `Shadow |`, `Sun View |`, `Site |`, `Yield |`. The
clean-up is unchanged and as narrow as before; the empty prefix is still
refused. An office that numbers its groups types its number in the
General page, as before. The context group, which nothing searches by, has
no default at all: the neighbours go on `Site Context.Buildings`, `.Terrain`
and `.Roads`, under a group only when one is given.

**No built-in names.** The sun views' base combination (`04 | Shadow
Diagrams`), override (`Sun Eye Views`) and model view options (`DA General
Arrangement`), the plans' subsets (`SHADOW DIAGRAMS`, `ADG DIAGRAMS`) and the
shadow plans' `50 %` fill are gone from the window and the command line. A
blank means none: the plan as it stands, no override, the sheets at the root
of the Layout Book, the project's own 3D Document fill. The one that cannot
mean none is the shadow plans' combination, which the views are pinned to:
it is asked for, by the command (`--layer-combination` is needed) and by
Run, as the master layout is.

**No guesses by name.** The window picked layers, combinations, subsets and
a schedule out of the project by an office's words -- `Zone.Unit`, `IFC
ARCH`, `SHADOW`, `ADG`, `COS solar`, `Sun Eye`, `PLAN`, `Wall.External` --
and, failing those, the first name in the list. Both are gone: a box the
person has not filled stays blank. What stays is a pick from the project's
content: the apartments' layer is the one its apartment-sized zones are on,
as the zone names already were picked by size.

**The legend's notes are generic.** The TOD and SEARs rows said *Current LEP
2023* and *Canterbury Bankstown LEP* building height limits, one project's
controls, on the page and on the drawn legend. They read *TOD building
envelope* and *SEARs building envelope* now, as the ADG and proposed rows do.

**The wait is an hour, and not on the page.** The *Archicad connection* card
held one field, minutes to wait on a command, which existed for the IFC
export; the studies no longer export that way. The card is gone and every
run is sent `--timeout 3600`. A saved setting for it is ignored.

*What this does not change:* the command line's own `--timeout` default, the
yield sheet's figures, the site sheets' styles, or a project already drawn
under the old numbers -- its layers stay where they are, and a run under the
new prefix leaves them alone, as any change of prefix does.

### D157 — The site page in four panels, each placed on its own and run on its own

Asked 26 October 2026, with the Site analysis page on screen: *"can we
sort of structure the site analysis into windows as its done in solar
analysis? basic window where you can select controls sheet and location,
Context window where you can select the origin, north, theme, scale. site
analysis window where you can select north, theme, scale etc. and 3d
context - where will be option to add future context, origin, north radius
( will be same radius for future)"*. Asked whether origin and north should
be one setting for all, which keeps every output lined up, or one per
panel: *per panel, as asked*.

**Four panels, as the solar analysis has.** *Address* holds what the
outputs share: the address, where the data comes from, *Controls* (the
Summary of Controls) and *Location*, the drawn boundary and the run folder.
Then a panel per output, each headed by its own switch and the sheets it is
worth: *Context Analysis* (origin, north, style, scale), *Site Analysis*
(origin, north, style, and a scale of its own -- blank still fits the site)
and *3D context* (future context, origin, north, one radius, model levels).
Each is a study of its own in the window's list, so the sidebar, the run
line and the sheets panel count them apart; the sidebar's switch turns on
the Context Analysis, its lead. *Site lands at* and *Origin at* became one
*Origin*: *Project location*, or a point of the site at the project origin.

**One run per panel.** The command places everything one run draws in one
frame, so a panel placed its own way is a run of its own -- the window sends
one `site` command per lit panel, each with only its own output on. What
that costs is a geocode and a fetch per run; what it buys is a site sheet
turned to its long boundary beside a model on the project's north.

**One location, written once.** The project has one location and one north,
and every run that places the site at the origin, or finds the location on a
city preset, would write its own. So only the first run may: the 3D context
when it is on -- the model has to line up with the building -- then the
Context Analysis, then the Site Analysis; it runs first, so a later panel
placed by *Project location* finds the location it wrote, and every other run
is sent `--keep-location`. The north is written by that run alone, and only
when its own panel turns the site.

**The future context is the 3D context's.** It stands its slabs in the 3D
context's frame. The Site Analysis run draws the same envelopes dashed on its
sheet in its own frame and stands nothing: the command takes
`--no-future-slabs` for that, so two runs do not stand the future twice in
two places. One radius serves the model and the future's reach, as asked,
where there were two fields, 500 m and 100 m.

*What this does not change:* the command line's one-run `site`, which still
draws every output it is asked for in one frame; the sheets, the styles and
the model themselves.

### D158 — The window does not fit to a drawn boundary

Asked 26 October 2026, after the *Drawn boundary* row was explained:
*"please, remove this option for now. its missleading"*.

The row turned and moved every output onto a boundary drawn in the file
when a layer's name mentioned one, and in doing so overrode each panel's
*Origin* and *North* (D157) without the page saying so; and when the
layer was empty, or a worksheet was in front, it quietly did nothing. So
it is gone from the window, and the window sends every site run
`--fit-layer none`: what the panels say is where the outputs go. Leaving
the command's own default, which fits, would have kept the override and
only hidden the row that admitted to it. The command line keeps
`--fit-layer` as it was, for when the fit comes back with a clearer name.

The *Run folder* row went with it, asked the same day: *"also remove run
folder. that is not necessary to pick"*. A run keeps what it fetched in
`Documents\Loriini\site-analysis`, one folder per address, which is what a
blank row always sent; the command line keeps `--out`.

And the two sheets' scales are lists, asked the same day: *"for scale, put
there arrow with options. no type in"*. The context sheet's runs 1:1000 to
1:5000, 1:3000 the default; the site sheet's is *Fit the site*, the default,
or one of the scales the run fits it from, 1:200 to 1:750. Making them lists
showed what a list could not do: a read-only list ignores the delete and
insert that put saved settings back, so the sheets' styles had never come
back on reopening. A saved value is now set on such a list, and only one it
offers.

### D159 — The Yield page in three panels, and shops and offices one use

Asked 26 October 2026: *"in yield, make basic window, make commercial and
retail one category"*. Asked what the one category is called and at whose
rates: *Commercial, at the commercial rates*; and what the basic panel
holds: *the massing and what it is written to, with the site apart*.

**Three panels.** The study's own, under its switch: Slabs, Renovation,
Option, the layer and level pickers the Slabs answer needs (D140), the view
beside the table and the workbook. *Site and controls*: the site area and
the permissible FSR, residential and commercial. *Efficiencies, mix and
parking*, as before.

**One non-residential use.** Retail was a third use with rates of its own
-- BEA to GFA 0.95 against commercial's 0.85, a parking space per 30 m² of
GFA under the SEPP against commercial's per 100 m² -- and a row of its own on
the sheet and in the workbook. It is gone: a shop is commercial floor,
counted at the commercial rates, told by a commercial layer or a
commercial level, with one share of the permissible FSR. The command line
loses `--retail-layer`, `--retail-level`, `--gfa-retail`, `--nla-retail`
and `--fsr-retail`; the sheet's legend loses the retail colour; the
workbook is re-laid for two uses from the number of uses rather than from
offsets written for three, every cell still styled as the template cell
it stands for, and a recalculation of all its formulas checks each against
the value written. The template's own figures change with it, and the
tests say how by hand: its retail floor counted as commercial, its
permissible FSR's retail 0.4 joined to the commercial 0.2.

**Older files.** A preset's retail layers and levels join its commercial
ones in the window. A workbook written before reads its retail floor and
its retail FSR back as commercial; its retail efficiencies and parking rate
are dropped, so that floor takes commercial's.

*What this does not change:* the residential figures, the mix, the
parking per unit, or how a slab is measured.

### D160 — The window's Shadow diagram is the 3D Documents; the fills are its every-hour panel

Asked 27 October 2026, of the window's Shadow diagram page: *"The main route
is to do shadows via 3d doc, and the separate path is to import fills into
drawings!"*, and with a screenshot of the page's first panel -- the legend
rows, the ground, the hours, the every-hour tick, the storey and the subset:
*"all this should be done by 3d docs, and the small window should be done.
yeah rebuild"*.

**Why the page was still the other way.** D144 settled the two routes on 25
October, but in the command line and the drawing code only. The window kept
the arrangement it was given in September (D123) and carried through the
Option A redesign (D131): the fills were the page's study, *Shadow diagram*,
the switch the sidebar and the palette's Shadow button turned on, a fill per
hour per legend row; the documents were a second panel, *Shadow plans*,
described as the same hours drawn a second way and the route for a model too
large for the caster; and the every-hour drawing was a tick that ran beside
the fills' per-hour diagram, never on its own.

**Decided.** Under the days, one panel both drawings read, then a small
panel for each, under its own switch. Asked of the first build: *"where do i
select the massing layer? there should be one genereal, where i select hours
and layers. and then 2 small options if i go for shadow diagram or every
hour on one drawing"*.

- **Layers and hours**, set up rather than switched on: the legend rows --
  the Proposed row is the design's massing -- the hours, and the sheets'
  subset.
- **Shadow diagram** is the documents (`shadow-plans`): the layer
  combination, the pen set, and the set name and shadow pen for a set
  without the legend. It is the study the sidebar's switch and the
  palette's Shadow button turn on.
- **Every hour on one drawing** is the fills (`shadows
  --shadow-all-hours-only`) and nothing else: the design's massing at every
  hour, imported as fills into one drawing, a sheet per day fitted to its
  shadows. It says which row it draws and its layers -- *Proposed: 20 |
  Massing.Envelope* -- so the massing is found where it is chosen, and asks
  for its own the three things only Loriini's caster uses -- the ground it
  lands on, the ground to ignore below, the storey the fills are drawn on --
  and its colour, red or blue (D147), which the window had not offered.

The fills' per-hour diagram is no longer in the window; the command line
keeps it.

**Asked before anything runs.** Run asks for the documents' layer
combination when it is blank (D156), and for the design when the every-hour
drawing is on and no row being compared has layers. Without a design the
command used to say so and draw a fill per hour instead -- the diagram the
documents draw now -- so `--shadow-all-hours-only` without one now stops
before the cast, with nothing drawn.

**Drawn.** The first build's every-hour run, 27 October, exported the
model, cast the seven hours, printed their areas and drew nothing: the
window's fills job had never sent `--draw` and `--sheet`, without which
`shadows` only measures, and the agent's tool was written the same way. Both
send them now.

**Older presets.** A preset saved before this has the documents as
`study_shadow_plans`, and the every-hour tick as `shadow_all_hours`, which
only ran beside the fills: both are read as the switches they are now. Its
`study_shadows` asked for the shadow diagram, and turns on the documents. The
palette's `shadow plans` turns on the documents too.

**The agent too.** Asked the same day, *"update the agent"*: its tools had
the routes the same way round as the window, `shadow_diagrams` the fills and
`shadow_plans` the documents, offered for a model too large for the fills.
They are `shadow_diagram`, the documents, whose layer combination is now
required and asked of the person as `cos_solar`'s are (D156 left the
command no default, and the tool still said it had one); and
`shadow_every_hour`, the fills, which runs `--shadow-all-hours-only` with a
colour, red or blue, and is refused without a design. The instructions a
client is shown on connecting say which is which.

*What this does not change:* the documents, the stack, its fit, its pen set
and its legend (D141 to D143), the every-hour drawing itself (D144, D145,
D147, D149), or the `shadows` command's other modes.

### D161 — The every-hour drawing's edges are found, its hours are written at the tips, and its grid is chosen

Asked 27 October 2026, of the first every-hour drawing the window drew:
*"why are some of the times missing. also add option og shadow quality - same
as we have in sun studies"*.

**The hours.** None was missing from the project: its every-hour layer held
seven texts. Each was put on the vertex of its hour's outline farthest from
the middle of all of them, and the long 9 and 3 o'clock shadows pull that
middle well to the south, so for the short midday hours the farthest vertex
was the far side of the building, and their labels sat on it rather than on
the shadows they name. Each instant now records which way its shadows run --
the sun's horizontal direction turned round, in the model's frame, turned
into the project's as the rings are -- and the label goes at the vertices
farthest along it, in the middle of them where the far end is an edge.

**The edges.** The regions have been traced to the true shadow edge since
D79; the every-hour outlines, added later, were still traced along the cells,
and came out as a staircase at every hour the sun was not square to the
grid. They are traced as the regions are, against the design alone, with the
cell path behind them.

**The grid.** The every-hour panel offers the four steps every solar grid
offers -- Rough 1 m, Normal 0.5, Detailed 0.25, Finest 0.1 -- sent as
`--shadow-grid`, Normal to start with where the command's own is 1 m. The
agent's `shadow_every_hour` takes the same as `grid_m`.

*What this does not change:* the documents, the fills' colours (D147), or the
sheet's fit (D149).

### D165 — The tool bar wears the name written, not the icon

Asked 31 October 2026, with the artwork: *"instead of picture of loriini
there will be written loriini, exactly with this. please take this exact
logo and put it in"* -- the word in a heavy sans, the L cut to the x-height,
round dots over the i's.

**The written name in place of the tile.** The top left of the window showed
the icon at 32 pixels beside the name in the heading face (D151). It now
shows the wordmark alone, `assets/loriini-wordmark.png`, and the About box's
band the same, with the version chip beside it. One file, black on nothing
at a size no screen reaches, fitted by Pillow to the height of a line of the
heading face the name was set in -- so it stands where the name stood and
grows with the type on a scaled screen -- because Tk shrinks a picture only
by dropping rows and columns, which leaves letters in pieces. Without the
file, or a Tk that will not take it, the bar shows the name in the heading
face as before: a missing picture costs the picture, as with every icon.
`Loriini.spec` carries the file where it carried the mark, and the Mac
recipe reads it from there.

**The file is a reconstruction until the original is dropped in.** The
artwork reached the request as a picture in a message, not as a file, so the
committed PNG is the wordmark redrawn to it: Inter Display Bold, whose stem
is the same share of the x-height as the artwork's (0.28), the L cut at the
x-height, the dots replaced with circles a stroke wide, a fifth of a stroke
above the stems. Put the original at `assets/loriini-wordmark.png`, any
size, black on transparent, and nothing else changes.

**What goes.** `loriini-mark-32.png` and `-64.png`, and `make_icon.py` no
longer writes them. The icon itself is as D151 left it everywhere else: the
.ico and .icns, the Dock, the MCP server's picture, the site's favicon.

*What this does not change:* the icon (D151); the site's top bar, which
carries the name alone in type (docs/website.md); or the About box's lines
under the name.

### D166 — The front is the mock-up: the wordmark, three tabs, the skyline, and two lorikeets that hop

Asked 31 October 2026, with a picture of the page: *"update website to have
this on a front page"*, and then *"i want birds to be moving ... from side
to side, jump like they normaly doo"*.

**The page is the picture.** The wordmark (D165), large, at the top left,
with How it works, Plans and Sign in beside its top; the picture the width
of the page; one line of small print at the foot, with the terms. The
company's details and the privacy link stay on every other page's foot. Sign
in is the Stripe customer portal, whose login link is not in the repository;
until it is pasted in the tab goes to Plans, marked as the page's fourth
placeholder (docs/website.md).

**The picture is traced, not pasted.** The mock-up was a raster; the page
draws it as one SVG so it is sharp at any width and weighs a few kilobytes:
the skyline as the one outline a building its dark pixels make, their
seams closed first -- the mock-up's skyline was a pasted raster whose blocks
met with a pixel of grey between them, and traced as rectangles those showed
as hairlines in the page -- the sun a circle, the sky and the ground flat
colours sampled from it. The second mock-up, of the same day, has no frame
round the picture and the copyright from the middle of the foot, and the
page follows it. The slight second blue behind the
skyline in the mock-up, where a pasted layer did not quite match, is not
kept. The birds are the pixel lorikeet supplied afterwards, at its own 40 by 53
pixels and shown at two picture units a pixel: the mock-up's perched bird
was that sprite pasted wider than it is tall, and the file is the drawing.
Every pose is a cell of one sheet, `site/lorikeet-sheet.png`, which
`scripts/make_lorikeet_sheet.py` writes from the artwork in
`assets/lorikeet/`: the perched drawing, and the take-off and landing
animations that followed it, each frame cut at the bird's own pixels with
the place the artist drew it in relative to the perched bird. The coarser
bird the front had goes, and so does the wings-out bird lifted from the
mock-up, which the landing's approach replaces.

**The birds hop, and swap towers.** Each bird keeps to the flat top of its
tower and moves the way a lorikeet on a ledge does: a short hop, a pause of
a second or two, another; it turns round at the roof's edge or on a whim,
and through some hops the wings come out, which is the take-off's crouch,
every cell mirrored to face the way the bird is going. Every ten to twenty
seconds the two swap: one takes off, the other once the first is well up,
and they cross over the skyline and land on each other's roof. The take-off
and the landing are the artist's: each frame is shown where the animation
drew it, relative to the perched bird, so the crouch, the lift, the climb,
the approach with the feet out and the fold on the roof are as supplied.
Between them the bird cruises at a steady height with a slight rise and
fall, looping the four airborne wing positions of the take-off, each cell
centred so the wings' reach does not jolt the body. A standing bird in the
air, which the first attempt flew with, is what this replaces. The hops and
flights are in the picture's units, so they scale with it. A reader who asks
for reduced motion gets the page as drawn. The sun's arc, the
hour-coloured sky and the shadows of the front before this (docs/website.md,
until this change) are gone with the scene they belonged to.

*What this does not change:* the other pages, their four tabs and their
foot; the download (the previous commit); the wordmark itself (D165).

### D167 — The site is put up by a workflow, and the download page says what the zip says

Asked 31 October 2026, after the front and the download page had changed in
one pull request: *"now lets deploy everything on web"*.

**A workflow, because the deploy could not be done from where the work
was.** The site had been deployed by hand from a checkout signed in to Fly
(docs/website.md). The session that made the changes could reach GitHub
but not Fly, so the deploy is now a workflow, *Website*, that anybody with
the repository can run from the Actions tab, and that runs itself when a
push to `windows` touches the site or how it is served. It needs a deploy
token for the app as the `FLY_API_TOKEN` secret, and nothing else: the
build comes from the repository's own artifacts, and flyctl builds the
image on Fly's builder.

**The page's figures are the file's.** The download page's version, build
day, Archicad versions, size and SHA-256 had been typed by hand from the
run's page. `scripts/site_download.py` now reads them out of the zip --
the install note inside says the version and the day, the add-ons' names
say the Archicad versions, and the file says its size and digest -- and
writes them on the page before every deploy, so the page cannot say one
thing about the file and the file another. The workflow then checks that
the site serves a zip of the size it deployed. By hand the script is the
step between downloading the artifact and `fly deploy`.

*What this does not change:* the licence service's deploy
(docs/licence-service.md), which stays by hand; what the pages say about
the program; the artifact the workflow takes, which is still the newest
successful add-on build on `windows`.

### D168 — The front's sun is the pointer's again, the buildings stand on the ground, the birds have seven roofs, and the wordmark is the mock-up's

Asked 31 October 2026, after the front went up: *"the logo is wrong look at
the dots above the ii in loriini. make it precise"*; *"there are
imperfections in the animation, like gap between house and ground"*; *"let
the parrots fly on different places"*; *"the sun scrip should be still
active. cursor as a sun casting shadows"*.

**The wordmark is the mock-up's lettering.** D165's wordmark was redrawn
from a picture in Inter Display Bold, and its dots were not the mock-up's.
Measured on the mock-up, the lettering is Arial Bold's: a stem 0.26 of the
x-height, the word 5.1 x-heights wide, round dots 1.06 stems across set
0.46 of a stem above the x-height line, centred on their stems. Liberation
Sans Bold has Arial's metrics and near enough its shapes, so the wordmark
is now that face, the L cut to the x-height, the square dots taken off and
round ones put on at those proportions. One file still serves the site and
the program's tool bar.

**The buildings stand on the ground.** Traced from a raster, the
skyline's feet ended a pixel above the ground line, and the sky showed
through as a hairline. Each building's outline now runs on eight units
under the ground, and the ground is drawn over it; the outline's vertices
are snapped to a four-unit grid, which takes the raster's one-pixel steps
off the roofs without touching the tower's mast.

**The birds have seven roofs.** Every flat roof wide enough for a bird is
a perch, found on the outline; a bird flies to any of them, never the one
the other bird is on, and well away from where it stands when such a roof
exists. The take-off and the landing are the same frames at the artist's
positions wherever the roof is; the cruising height drops for a high roof.

**The sun is the pointer's, as the first front's was.** Over the picture
the sun goes where the pointer goes, easing after it, and drifts back to
where the mock-up drew it when the pointer leaves. The sky takes the
hour's colour from the first front's day (docs/website.md, until D166),
with the mock-up's blue at noon. Every building throws its own shadow on
the ground: the same outline sheared away from the sun by up to three
units a unit of height and flattened onto the ground, as far as the sun is
low, clipped to the ground strip, at a fifth of black over the khaki. The
birds cast none: on a roof their shadow would fall on the roof.

*What this does not change:* the sheet of poses and the hops (D166); the
pages besides the front; the program, which wears the wordmark as before.

### D169 — The first front's sun is back in the second: pixel sun and glow, its own day, one shadow; the birds only fly; the wordmark's second dot is square

Asked 1 November 2026, with the mock-up's wordmark enlarged: *"the logo
is not precise. look at dots above the 'i' please be precise. one dot is
circle one dot is square"*; and of the front: *"keep the pixalated sun and
bands around the sun"*, *"the parrots do not jump, just let them fly from
place to place"*, *"the sun should move automaticaly as a day
progressing"*, *"the sun shadow is parallel - the shadows have the same
direction for all building"*.

**Round, square, round.** The mock-up's three i's do not wear the same
dot: the first and the third have a round one, the second the face's own
square. D168 had made all three round. Every dot is the mock-up's size and
height -- 1.06 stems across, its foot 0.46 of a stem above the x-height
line, centred on its stem -- and the middle one is a square of that side.

**The sun and its glow as the first front drew them.** D168 drew the sun
as a plain circle in the vector picture. The first front (docs/website.md
until D166) drew it cell by cell: a yellow disc with three uneven bands of
glow, tight at noon and wide at sunrise and sunset, on a sky of the hour's
colour, every cell scaled up whole. That is back: the sky, the sun and the
bands are painted on a canvas of 198 by 58 cells, eight picture units a
cell, twenty times a second, and set behind the vector skyline as the
picture's sky; the first front's day of colours is kept, with the mock-up's
blue at noon. Without the script, a plain disc stands in where the mock-up
drew it.

**The sun keeps to the day's arc on its own.** A day runs sunrise to
sunset every two and a half minutes, starting where the mock-up put the
sun. The pointer takes the sun while it is over the picture and the sun
eases back to the arc when it leaves, which is what the first front did.

**One shadow.** D168 gave each building its own shadow, thrown away from
the sun as from a lamp. Sunlight is parallel: the skyline is now sheared as
one, in one direction for every building, by as much as the sun is low and
to the side.

**The birds only fly.** The hops and turns of D166 go: a bird sits still
on its roof until, every eight to twenty seconds, it flies to another, with
the take-off, cruise and landing as before.

*What this does not change:* the skyline, the roofs and the sheet of poses
(D166, D168); the pages besides the front.

### D170 — The front's shadows in cells, the glow shimmering, the birds' shadows and their turn, the tower symmetrical

Asked 1 November 2026, with a crop of the tower and the artist's animation
of the bird turning round: *"even the shadow needs to be pixelated. I like
the bands around sun. is it possible to make the bands around sun moving
even though it stays on one place? so its flickering all the time like
water does in the sun?"*; *"is it possible to cas shadow from parrots?"*;
*"this is not correct the tower should be symetrical"*; *"when parrots
turns around, it should make this animation"*.

**The shadow in the same cells as the sun.** D169 painted the sky and the
sun cell by cell and left the shadow a vector shape, the skyline sheared
onto the ground. The canvas now covers the whole picture, 198 by 73 cells,
and the ground and its shadows are cells too: a ground cell is shaded when
most of nine points in it, carried back along the sun's light (the shear of
D169 run backwards), land on something solid -- the skyline, rasterised
once into the same cells, or a bird. One point a cell would do for a short
shadow but breaks a long one into dashes where the gaps between buildings
cross it, so it is a vote of nine. The vector shadow and the ground
rectangle are gone from the SVG; the skyline is clipped at the ground line
instead of running on under a rectangle.

**The glow shimmers.** The bands' uneven edges were a fixed noise over the
cells. The noise now drifts with the clock, two layers of it, one broad and
slow and one finer and quicker, so the edges move all the while even when
the sun stands still, and the glow flickers as sunlight on water does. A
reader who asks for reduced motion gets the glow still.

**The birds throw shadows.** Each bird's window on the sheet -- which
cell, where, mirrored or not -- is kept as it is shown, and a point carried
back by the light that lands in a window is solid where the sheet's pixel
is. So the perched bird's shadow lies on the ground beside its building's,
and a flying bird's shadow crosses the ground under it. The page reads the
sheet's pixels back through a canvas, which a browser allows only from the
site's own origin: opened as a file, the birds throw no shadow and nothing
else changes.

**The birds turn round as drawn.** The artist's `turn.gif` is the perched
bird turning to its mirror image in nineteen frames, about two and a half
seconds, and back again by the same frames reversed. The nineteen are on
the sheet after the landing, and a bird plays them, mirrored or not for the
way it faces, whenever it turns: as often as not once while it sits, to
look the other way, and before a flight to a roof behind it, so no bird
flips about any more. The bird stands on its feet where the artist's turn
has its axis, 23.5 pixels along the perched cell instead of the 24.9 of
D166, so the turn's last frame and the mirrored perched bird are in the
same place.

**The Sydney Tower is symmetrical.** The outline traced from the mock-up
(D168) had a bump on one side of the turret and a notch on the other, from
the mock-up's own pixels. It is now symmetrical about its mast: the mast,
the upper block, the neck, the turret, the base and the stem each the
wider of the traced halves on both sides.

*What this does not change:* the sun's day and arc (D169); the other
buildings and the roofs (D168); the take-off and landing (D166); the pages
besides the front.

### D171 — The wordmark is the logo's own pixels, not a font's

Asked 1 November 2026, with the mock-up and the site side by side: *"the
mockup and now logo is different. different L different r. the logo needs
to be exactly the same."*

D165 set the wordmark in a face, and D168 and D169 chose and adjusted the
face until its widths and dots were the logo's. Its letters never were:
Liberation Sans Bold has Arial's metrics and its own shapes, so the L's
foot ran longer and the r's arm further than the logo's. No face on hand
draws the logo's letters, and the logo was supplied as the thing to use:
*"take this exact logo and put it in"*.

So the wordmark is now made from the logo image itself. Its ink, with the
anti-aliasing the image carries, is enlarged eight times, cut at half ink
so every edge lands where the image's grey levels put it, and brought down
to twice the logo's size with a box filter, which gives clean edges at
every size the site or the tool bar shows it. The L cut to the x-height
and the round, square and round dots are the logo's own; nothing is drawn
over it. One file serves the site and the program, as before.

*What this does not change:* where the wordmark goes and how large (D166,
D168); the tool bar's fitting of it (D165); the front's picture (D170).

### D172 — The build follows the wordmark and the site follows the build; the front's day is a minute

Asked 1 November 2026: *"this logo needs to be updated in app as well not
only on web. also in the animation on welcome page - the sun can go
faster."*

**The program carries the wordmark it is built with.** The tool bar reads
`assets/loriini-wordmark.png` (D165), and D171 replaced that file; but the
*Archicad add-on* workflow, which builds the program and the handover
folder, ran on a push only for the add-on sources, its own file, the spec,
the build script and the icon. The wordmark is now on that list beside the
icon, so a change to it is a new build, and the merge of this entry's
change to the workflow builds one with the D171 wordmark.

**The site follows the build.** The *Website* workflow took the newest
successful build when it ran, but ran only for a change to the site or by
hand, so a new build sat on its run page until someone remembered. It now
runs itself as well when an *Archicad add-on* run on `windows` completes
with success, and serves that run's folder: the download is the newest
build as soon as there is one. A failed build puts nothing up.

**A day a minute.** The front's sun crossed its arc in two and a half
minutes (D169), too slow to be seen moving on a visit. It is a minute now.

*What this does not change:* what the build contains and what the page
says of it (D167); the program's own look (D165); the rest of the front
(D170, D171).

### D173 — Every page's top bar wears the wordmark

Asked 1 November 2026, with the other pages' bars beside the front's:
*"change the logo on whole web"*.

The front had the wordmark (D166) while the other six pages still wrote
the name in capitals in their bar, as the first site did. Now every bar
wears the wordmark, the same file, 1.3 rem tall where the name was, so it
sits with the tabs beside it; the front keeps it large. One picture of the
name everywhere, on the site and in the program.

*What this does not change:* the wordmark itself (D171); the front's
layout (D166, D168); the pages' content.

### D174 — The front's ground is the day's sun-hours map, and the birds take the hour's light

Asked 1 November 2026, with one of the program's own sun-hours drawings:
*"change the colours of the lorikeet as he should have different colours
in different sunlight? so his colours reacts to change of lights"*;
*"change the colour of the ground. is it possible to mimic somehow the
results from solar analysis"*.

**The ground as the program would draw it.** The front's ground was plain
khaki with the moving shadow on it. It is now the day's sun-hours map, the
result the program exists to draw: each ground cell is coloured by the
share of the day's arc from which the sun reaches it, worked out once at
the start from the skyline alone, the sun stepped through forty-eight
positions of its arc and each cell's shadow test (D170) run for every one.
The colours are the drawings': blue where the skyline shades a cell most
of the day, through a pale blue and a khaki to yellow and, in the open,
orange -- five flat steps of a fifth of the day each and no gradient
between, so every edge in the map is a cell's edge. (The first cut ran
the colours smoothly from stop to stop and, at cell size, read as water:
*"this ground is a bit blurry looking like a sea. just simplify the
ground to be more sharp edges"*.) The moving shadow of the hour, the birds' too, is painted over it
in the shade's own blue, a step deeper than the map's blue so it still
shows where the map is blue already (first tried as a darkening of the
map, and asked blue: *"i think the shadow should be blue in this case
too"*). The day's result and the moment's shadow are both there. The pointer moves the sun and its shadow,
not the map, which is the day's.

**The birds in the hour's light.** Both birds are drawn through one colour
matrix, set every repaint from the hour: the sun's own glow colour, taken
up to six tenths as the sun nears the horizon and not at all at noon, and
the whole dimmed to seven tenths at the horizon. A lorikeet at sunset is
warm and dark, at noon its own colours. The matrix keeps the pixels crisp,
being a colour operation and not a blur.

*What this does not change:* the shadows' geometry (D169, D170); the sun's
day (D169, D172); the sheet of poses (D166, D170).

### D175 — The download page offers the Mac build beside the Windows one

Asked 1 November 2026: *"please, put there also macos version for
download"*.

**The Mac build goes up the way the Windows one does.** The *Archicad
add-on (macOS)* workflow has made the Mac folder -- `Loriini.app`, one
add-on per Archicad version as a `.bundle`, the install note and the
licence, zipped by ditto so the program keeps its links and execute bits
(macos.md) -- as the `Loriini_Mac` artifact of each run, but it sat on the
run's page: the site served the Windows folder alone. The *Website*
workflow now takes the newest successful run of that workflow on `windows`
as well as of the Windows one, serves the ditto zip inside the artifact as
`site/download/Loriini_Mac.zip`, runs itself when either build completes
(D172), and checks the site serves both. A run of either can still be
named from the Actions tab.

**Two boxes, each saying what its file says.** The download page has a
box per platform, side by side, and `scripts/site_download.py` writes a
build's facts into its own box and no other, telling the two apart by the
program in the zip and reading the Mac folder through the parent folder
ditto zips it under. A Mac's box also says which Macs, from the install
note's own line -- an Apple silicon Mac on macOS 11 or later, because the
program is built for the runner's processor (macos.md). The Windows box's
*Runs on* is the page's own words, since the Windows note names no
Windows. The description and every footer say Windows and macOS; How it
works says where a Mac's install differs, which is the one Terminal
command; the terms say what is licensed runs on both; the privacy note
says what a Mac sends in place of Windows' machine identifier, which is
the identifier Loriini makes once and keeps.

**The recall notice points at the page.** The licence service's download
address was the Windows zip. With two builds it is the download page,
which offers both; the old zip address in notices already sent still
redirects (D167).

*What this does not change:* what either folder contains, and how it is
made; how a Mac is installed, which is the install note's four steps
(macos.md); the Windows build's address, `Loriini_Win.zip`; the page's
figures being the files' (D167).

### D176 — The site is light only

Asked 1 November 2026: *"loriini web should have only light mode"*.

**One appearance, the white page.** The stylesheet carried a dark
palette: on a system set to dark, the page went near-black with pale
ink, the lines, tints and the notice darkened with it, and the wordmark
was inverted to match, under a `data-theme` attribute that nothing on
the site set. That is gone. The page is white with dark ink whatever the
system is set to, as the mock-up drew it (D166) and as the stylesheet's
own first lines say, and `color-scheme: light` on the root tells the
browser so, so its own parts -- the scroll bar, a form control -- follow
the page rather than the system.

*What this does not change:* the colours themselves (D166 onwards); the
front's picture, which never had a dark version; the program's window,
which has one appearance of its own (app/theme.py).

### D177 — A site is every lot of the properties its addresses name

Asked 3 November 2026, of an amalgamation of 91-93, 95-97, 99-107 and 109
Riley Street, Darlinghurst: *"I tried multiple sites connected, but it does
not work"*, with the four properties outlined as the site.

**A property, not the lot under its point.** An address point sits on one
lot, and the site was the lots under the points. 99-107 is three lots under
one address, its point on the southern one, so the other two were left out
and the amalgamation fell into two pieces with a gap between 95-97 and
99-107. `nsw.site_lots` now reads each address's property from the
cadastre's property layer (12) and takes every lot with a point inside its
outline (`geo.interior_point`, `geo.point_in_rings`). The cadastre has no
join from lot to property, and the server's own "within" test returns
nothing on the edges the two layers share, so the test runs here. A
property of more than 40 lots or 5 ha, a campus or a corridor rather than a
site, keeps only the lot under the address. A failed property query costs
the rest of its lots, never the site.

**Named by every address.** An amalgamation's title is all its addresses in
street order, `91-93, 95-97, 99-107, 109 RILEY STREET DARLINGHURST`
(`geocode.site_address_of`), not whichever the register returned first; on
the site analysis's frame and in the development summary.

**A range found is not asked again.** The geocoder's second stage asked
for every number of a range, eight at most, though "91-107" is filed as
91-93, 95-97 and 99-107: three lookups find all nine. It now skips a
number a range already found covers, so a long range is found in fewer
lookups and reaches further.

*What this does not change:* how the lots are dissolved into the site's
outline (`pipeline._site_rings`), which already kept every piece; a corner
or through site whose lots front two streets, which still cannot be typed
as one address; the planning controls, still read at the centre of the
address points. The same change is in the web tool (au-site-analysis#121).

### D178 — The compared rows are Proposed, Proposed 2 and Proposed 3

Asked 3 November 2026, of the shadow diagram's Layers and hours: *"instead
of TOD envelope, SEARs envelope, ADG envelope. proposed. Lets name them
Proposed, Proposed 2, Proposed 3. so we keep it universal."*

**Named for no one control.** The rows being compared were named for the
controls one job tested: a TOD envelope, a SEARs massing, an ADG envelope.
The next job tests something else, and its rows then said the wrong thing
on the page and on the sheet. They are now Proposed, Proposed 2 and
Proposed 3, on the page in that order, and on the sheet as PROPOSED,
PROPOSED 2 and PROPOSED 3 BUILDING ENVELOPE. Three rows where there were
four: Proposed kept its name and is still the design the every-hour drawing
outlines.

**Proposed still lies on top.** The page lists Proposed first, but the rows
are sent in the legend's order, which is the order drawn, back to front:
Proposed 2, Proposed 3, then Proposed, in the strongest blue, over them.
Proposed 3 takes the lilac that was the ADG envelope's, drawn just under the
proposal. Proposed 2 takes the middle blue, which is what a second proposal
takes by position, so a stack's own numbered proposals (`Proposed 1`,
`Proposed 2`, from `--proposed`) never land in the same colour.

**The older names still draw.** TOD, SEARS and ADG ENVELOPE stay in the
legend's colours as `OLDER_LEGEND`, for a command line or an agent that
still names them. A preset saved with those rows opens with the first two
filled in Proposed 2 and Proposed 3; a third filled has no row now, and the
log names its layers rather than dropping them unseen.

*What this does not change:* the grey rows; how a row is cast (a baseline
accumulates, a scenario is compared against every baseline and no other
scenario); the shadow plans' `--existing` and `--proposed` route, whose
proposals are still `Proposed 1`, `Proposed 2` and on, so a project's
layers and combinations keep their names.

### D179 — The licence database backup is encrypted before it is uploaded

The repository went public on 11 November 2026, and with it every Actions
artifact: anyone signed in to GitHub can download one. The nightly
*Licence database backup* had been uploading the licence service's SQLite
file as it came, and that file holds every licence's email, holder, Stripe
customer and the names of the computers holding its seats.

**Encrypted to a key GitHub never sees.** The workflow now encrypts the copy
with age to the public keys in the repository variable
`LORIINI_BACKUP_RECIPIENTS` and uploads only the `.age` file, as
`licences-encrypted-<run>`. The private half stays on the vendor's machine
beside the signing key, so neither the repository, its workflows nor a
leaked token can open a backup. A public key rather than a passphrase held
as a secret: what the runner holds can only seal, never open.

**No key, no copy.** The first step checks the variable before the database
is fetched, the plain file is written outside the uploaded folder and
removed once sealed, and the upload takes only `*.age` files after checking
the file starts with age's own header. A missing or wrong key stops the
job; it never falls back to a plain copy.

*What this does not change:* the service's backup request, `scripts/licence.py
backup` by hand (a plain file on the vendor's own disk), the ninety days, or
the schedule. The plain `licences-<run>` artifacts uploaded before this are
not touched by it and are deleted by hand.
