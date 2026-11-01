# The website: the front on the shop and the download

R7 was decided against on 29 September (nothing in selling Loriini needed a
site) and taken up again on 8 October: a practice looking for Loriini needs
one page that says what it makes, what it costs, where the download is, and
the terms and privacy pages Stripe asks a seller to link to. That is all the
site is. Buying still happens on Stripe's own pages, reached by the payment
links; the key still comes from the licence service
([`licence-service.md`](licence-service.md)).

It is a handful of static files and the current build, served by nginx, on
Fly.io beside the licence service, at `https://loriini.app` (and
`www.loriini.app`; the `loriini-site.fly.dev` address keeps working). No
cookies, no analytics, no third-party requests (the font is served from the
site itself), nothing to keep running; the one script moves the front's
birds, inline, talking to nothing.

## What is where

| | |
|---|---|
| `site/index.html` | The front, as the mock-up of 31 October 2026 (D166): the wordmark, large, at the top left, with three tabs beside its top -- How it works, Plans, Sign in -- and the picture the width of the page under it, on white; every page runs the same width, its margins a share of the window. The picture is one SVG: the Sydney skyline in black, traced from the mock-up as one outline a building, under a plain yellow sun on a flat blue sky, on a strip of khaki ground; and a pixel lorikeet on the tower at each end. The birds hop along their roofs the way lorikeets do, a short hop and a pause, round at the roof's edge or on a whim, the wings coming out through some hops, and swapping towers now and then -- the take-off and the landing as the artist drew them, the cruise on the four airborne wing positions -- by the one script; a reader who asks for reduced motion gets the mock-up as drawn. On a narrow screen the picture keeps a height and shows its left end, where a bird is. The foot is one line: the small print with Terms of use on the left, the copyright from the middle. |
| `site/makes.html`, `site/works.html`, `site/price.html`, `site/download.html` | The tabs: what it makes, how it works, price, download. Contact lives in every footer. |
| `site/terms.html`, `site/privacy.html` | The licence terms and the privacy note, **drafts for a lawyer's hour** (licence-model.md §7). |
| `site/style.css` | The one stylesheet. One typeface in two weights (400, 600) and three sizes (`--s`, `--m`, `--l`) and nothing else; thin 1px lines, flat buttons, a white page. |
| `site/fonts/` | Inter, regular and semibold, Latin and Latin Extended, self-hosted, with its licence (SIL OFL 1.1). |
| `site/favicon.ico`, `site/icon-*.png`, `site/apple-touch-icon.png` | The application icon, the lorikeet over the black L on its orange tile (D151), written by `scripts/make_icon.py`. `icon-52.png`, the mark at double density, is not shown in the top bar, which carries the name alone, as the front does. |
| `site/wordmark.png` | The wordmark, the same file the program's tool bar wears (`assets/loriini-wordmark.png`, D165), black on nothing; inverted in dark mode. |
| `site/lorikeet-sheet.png` | Every pose of the front's birds on one sheet, at the bird's own pixels, shown at two picture units a pixel, facing right and mirrored for a bird going left: the perched bird, the six frames of the take-off from the crouch to the climb, and the seven of the landing from the approach to the fold. Written by `scripts/make_lorikeet_sheet.py` from `assets/lorikeet/` -- the perched drawing and the two animations supplied -- which also writes the page's table of where each cell is, where the artist placed it relative to the perched bird, and how long it holds. Run it when the artwork changes. |
| `site/demo-makes.mp4`, `site/demo-makes.png` | The animation on *What it makes* and its poster, from the engine's own run on the sample building; `site/demo.mp4` and `site/demo-poster.png`, the recording on *How it works*, once cut. See "The demo videos" below. |
| `site/download/` | The current build's zip, `Loriini_Win.zip`, put there at deploy time and never committed. nginx answers the old name, `Loriini_AC26_Win.zip`, with a redirect to it, because that address is in the licence service's recall notice and in mail already sent. |
| `deploy/site/` | The Dockerfile, nginx's config, and `fly.toml` for the `loriini-site` app. |

## Before it goes live

Three things on the page are placeholders, each marked with an HTML comment
beside it:

1. ~~The payment links~~ Live since 10 October: Stripe's live payment links,
   made through the API with the product, the prices, the webhook destination
   (`https://licence.loriini.app/v1/stripe`) and the customer portal.
2. ~~The company's details~~ Filled in on 8 October: Žofia Kosová, trading as
   Loriini.app, IČO 19785283, DIČ CZ0154024321, as on the Stripe account.
3. **The prices** are the placeholders from licence-model.md §8, A$75 a seat
   a month and A$750 a year; change them with the Stripe prices.
4. **Sign in**, on the front, is the Stripe customer portal, where a
   subscriber changes the card and the seats. Its login link is made in the
   Stripe dashboard (Settings > Customer portal); until it is pasted in, the
   tab goes to Plans.

And the two drafts want a lawyer's hour before a practice is asked to accept
them.

## Deploying it

The *Website* workflow (`.github/workflows/site.yml`) puts the site up: it
runs itself on a push to `windows` that touches `site/`, `deploy/site/` or
itself, and from the Actions tab (*Run workflow*) for anything else. It
takes the current build -- the `Loriini_Win` artifact of the newest
successful *Archicad add-on* run on `windows`, the program and one add-on
per Archicad version with the install note and the licence, or of the run
named when it is started by hand -- puts it at
`site/download/Loriini_Win.zip` as GitHub serves it, writes that file's
own facts under *Download* on the page with `scripts/site_download.py`,
deploys with flyctl on Fly's builder, checks the site serves a zip of the
deployed size, and, with the admin token at hand, tells the licence
service where the download is. It needs one repository secret,
`FLY_API_TOKEN`, a deploy token for the app:

```
fly tokens create deploy -a loriini-site
```

By hand, from the repository's root, signed in to Fly: download the
artifact from the run's page, then

```
python3 scripts/site_download.py site/download/Loriini_Win.zip
fly deploy . --config deploy/site/fly.toml --dockerfile deploy/site/Dockerfile --ha=false
```

The script reads the version, the day it was built and the Archicad
versions out of the zip's own install note and add-ons, and the size and
SHA-256 of the file, and writes them on the page; nothing about the build
is typed by hand. The page in the repository carries the figures of the
build last put on it that way, which is what a deploy from a checkout
serves; the workflow writes the figures of the build it fetches and does
not commit them, so after a deploy from the Actions tab the page's figures
in the repository are a build behind until someone runs the script and
commits.

The first deploy made the app with `fly apps create loriini-site`. The
domain, `loriini.app`, is at Namecheap: A and AAAA records for `@` and `www`
point at the site's Fly addresses (`fly ips list --app loriini-site`), and
`licence` at the licence service's, with certificates from `fly certs add`.
The mailbox the keys come from, `sami@loriini.app`, is Namecheap's Private
Email (`mail.privateemail.com`, port 587, STARTTLS), set on the service with
`fly secrets set`.

Once the site serves the build, tell the licence service where it is, so a
recall's notice can point there -- the workflow does this itself when the
`LORIINI_ADMIN_TOKEN` secret is set:

```
uv run python scripts/licence.py set download=https://loriini.app/download/Loriini_Win.zip
```

## What it costs

A shared machine that stops when idle, started by the next visitor: cents a
month. The 83 MB download is inside the image, so a visitor's download comes
from Fly's edge in Sydney.

## The demo videos

Two, made two ways (D168), and nothing in either is drawn by hand or
generated: the one is the engine's own run, the other the real window.

**What it makes: the animation.** `site/demo-makes.mp4`, fifteen seconds
at the head of the *What it makes* page, with `site/demo-makes.png` as its
poster: the sample building the repository is allowed to show, the sun
swept over it from 09:00 to 15:00 on 21 June, every face of the model
banded by its hours of sun, the ground grid the rays were cast from, and
the four apartments assessed. Three things make it:

| | |
|---|---|
| `scripts/demo_fixture.py` | Runs the engine on `tests/fixtures/sample_building.ifc` -- the massing study and the apartment study, as the command line runs them -- and writes `assets/demo/fixture.js`: the geometry; the skin of cells the model bands are drawn with, each with whether it saw the sun at each instant; the ground grid the same way; the sun's direction; each apartment's lit share instant by instant; the bands and the verdict. Committed, so the site deploys from a checkout. |
| `assets/demo/makes.html` | Draws that file: one SVG, built in painter's order from the north-east and recoloured by the clock, beside the table and the legend. `demo.seek(t)` puts it at any moment, which is how it is filmed; opened in a browser it plays once and rests on the verdict. |
| `scripts/demo_render.py` | Opens the page in a headless Chromium -- Playwright, the `demo` dependency group -- photographs it thirty times a second, and has ffmpeg make the video and the poster. `uv run --group demo playwright install chromium` once, or `--chromium` (or `LORIINI_CHROMIUM`) naming one the machine has. |

**How it works: the screen recording.** `site/demo.mp4`, cut by
`scripts/demo_cut.py` from raw clips in `assets/demo/captures/` (not
committed) as `assets/demo/works.yaml` says: which clip, from when to when,
how much faster than life, what the caption along its foot says, which
part of the frame. The clips come from two scripts:

- `scripts/demo_capture_window.py`, on any machine: the real window over a
  fake project -- the lists the window's tests feed it -- and a fake run
  that says what a run says, a line at a time, under the progress bar. It
  opens Site analysis, types an address, switches the panels on, presses
  Run and waits for Done, while ffmpeg records the window. On Linux it
  starts an Xvfb of its own, with Inter from `assets/fonts` served to it,
  so a runner can make the clip; on Windows it records the window off the
  screen, which is the window as the office sees it, and the one to
  publish. Needs a Python with tkinter (`.venv*` in `.gitignore`) and
  ffmpeg.
- `scripts/demo_capture_archicad.py`, on a workstation with Archicad open
  and the add-on loaded, the one part the cloud cannot make: for each
  study, ffmpeg records the screen while the study runs exactly as the
  command line runs it, then rests on the result. Minutes long; the cut
  list shows them faster. Its first run is also the manual checklist in
  `docs/archicad.md`.

The video block on `works.html` stays commented out until the Archicad
clips are recorded and the cut committed; the cut list already names them,
and `--skip-missing` cuts the demo of what there is meanwhile.

Both videos are H.264 at 1280 x 720, a megabyte or so, muted, served from
the site itself like everything on it: no third-party request. The
animation plays itself and loops; a reader who asks for less motion gets
its poster and a play button. The recording plays when asked.
