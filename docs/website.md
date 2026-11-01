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
| `site/index.html` | The front, as the mock-up of 31 October 2026 (D166, D168, D169, D170): the wordmark, large, at the top left, with three tabs beside its top -- How it works, Plans, Sign in -- and the picture the width of the page under it, on white; every page runs the same width, its margins a share of the window. The picture is one SVG with a small canvas behind it: everything but the skyline and the birds is drawn cell by cell, eight picture units a cell, and scaled up whole, as the first front drew it -- the sky, the sun and its three uneven bands of glow, whose edges drift all the while so the glow shimmers as light on water does, the khaki ground, and on the ground the shadows; the Sydney skyline in black over it, traced from the mock-up as one outline a building, the Sydney Tower symmetrical about its mast, cut at the ground line; and a pixel lorikeet on a rooftop at each end. The sun crosses the day's arc on its own, a day every two and a half minutes, the sky taking the hour's colour, pale at sunrise, the mock-up's blue at noon, red at sunset, the glow tight at noon and wide at either end; the pointer takes the sun while it is over the picture, and it finds the arc again after. The skyline and the birds, perched or in the air, throw their shadows on the ground in cells: a ground cell is shaded when most of it would be reached by the sun's light through something solid, everything sheared away from the sun in one direction, as sunlight is, short when the sun is high and long when it is low. The birds sit, and every so often one flies to another rooftop -- any of the seven wide enough, never the one the other bird is on -- the take-off and the landing as the artist drew them, the cruise on the four airborne wing positions, by the one script; a bird turns round on its feet, frame by frame as the artist drew the turn, as often as not once while it sits and before any flight to a roof behind it. A reader who asks for reduced motion gets the birds as drawn, the glow still and the sun where the mock-up put it, the pointer still able to take it. On a narrow screen the picture keeps a height and shows its left end, where a bird is. The foot is one line: the small print with Terms of use on the left, the copyright from the middle. |
| `site/makes.html`, `site/works.html`, `site/price.html`, `site/download.html` | The tabs: what it makes, how it works, price, download. Contact lives in every footer. |
| `site/terms.html`, `site/privacy.html` | The licence terms and the privacy note, **drafts for a lawyer's hour** (licence-model.md §7). |
| `site/style.css` | The one stylesheet. One typeface in two weights (400, 600) and three sizes (`--s`, `--m`, `--l`) and nothing else; thin 1px lines, flat buttons, a white page. |
| `site/fonts/` | Inter, regular and semibold, Latin and Latin Extended, self-hosted, with its licence (SIL OFL 1.1). |
| `site/favicon.ico`, `site/icon-*.png`, `site/apple-touch-icon.png` | The application icon, the lorikeet over the black L on its orange tile (D151), written by `scripts/make_icon.py`. `icon-52.png`, the mark at double density, is not shown in the top bar, which carries the name alone, as the front does. |
| `site/wordmark.png` | The wordmark, the same file the program's tool bar wears (`assets/loriini-wordmark.png`, D165, D168, D169): the mock-up's own lettering, Liberation Sans Bold with the L cut to the x-height and, over the three i's, a round dot, a square one and a round one at the mock-up's size and height, black on nothing; inverted in dark mode. |
| `site/lorikeet-sheet.png` | Every pose of the front's birds on one sheet, at the bird's own pixels, shown at two picture units a pixel, facing right and mirrored for a bird going left: the perched bird, the six frames of the take-off from the crouch to the climb, the seven of the landing from the approach to the fold, and the nineteen of the turn from the perched bird to its mirror image (the turn back is the same frames reversed, so the page plays these, mirrored or not, for either turn). Written by `scripts/make_lorikeet_sheet.py` from `assets/lorikeet/` -- the perched drawing and the three animations supplied -- which also writes the page's table of where each cell is, where the artist placed it relative to the perched bird, and how long it holds. The page reads the sheet's pixels back for the birds' shadows, so the sheet is served from the site's own origin. Run the script when the artwork changes. |
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
