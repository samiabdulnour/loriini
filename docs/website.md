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
| `site/index.html` | The front, as the mock-up of 31 October 2026 (D166): the wordmark, large, at the top left, with three tabs beside its top -- How it works, Plans, Sign in -- and the picture the width of the page under it, on white; every page runs the same width, its margins a share of the window. The picture is one SVG in a thin lemon frame: the Sydney skyline in black, traced from the mock-up as rectangles, under a plain yellow sun on a flat blue sky, on a strip of khaki ground; and a pixel lorikeet on the tower at each end, the two sprites lifted from the mock-up. The birds hop along their roofs the way lorikeets do, a short hop and a pause, round at the roof's edge or on a whim, the wings opening through some hops, by the one script; a reader who asks for reduced motion gets the mock-up as drawn. On a narrow screen the picture keeps a height and shows its left end, where a bird is. The foot is one line: the small print, Terms of use, and the copyright. |
| `site/makes.html`, `site/works.html`, `site/price.html`, `site/download.html` | The tabs: what it makes, how it works, price, download. Contact lives in every footer. |
| `site/terms.html`, `site/privacy.html` | The licence terms and the privacy note, **drafts for a lawyer's hour** (licence-model.md §7). |
| `site/style.css` | The one stylesheet. One typeface in two weights (400, 600) and three sizes (`--s`, `--m`, `--l`) and nothing else; thin 1px lines, flat buttons, a white page. |
| `site/fonts/` | Inter, regular and semibold, Latin and Latin Extended, self-hosted, with its licence (SIL OFL 1.1). |
| `site/favicon.ico`, `site/icon-*.png`, `site/apple-touch-icon.png` | The application icon, the lorikeet over the black L on its orange tile (D151), written by `scripts/make_icon.py`. `icon-52.png`, the mark at double density, is not shown in the top bar, which carries the name alone, as the front does. |
| `site/wordmark.png` | The wordmark, the same file the program's tool bar wears (`assets/loriini-wordmark.png`, D165), black on nothing; inverted in dark mode. |
| `site/lorikeet-perched.png`, `site/lorikeet-wings.png`, `site/lorikeet-flying.png` | The birds of the front, drawn with their pixels whole. Perched: the supplied pixel lorikeet at its own 40 by 53 pixels, facing right, shown at two picture units a pixel. With the wings out, facing right: lifted from the mock-up at its own resolution. And the frame a bird flies with, which the wingbeat alternates with the wings-out one. Each bird shows all three, mirrored to face the way it is going. The flying frame is a copy of the wings-out sprite until the flying lorikeet supplied with the request, which did not reach the repository as a file, is put there under that name; the script reads each sprite's size from its file and scales it by the factor set beside it, so nothing else changes. |
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

From the repository's root, signed in to Fly. The current build is the
`Loriini_Win` artifact of the newest successful *Archicad add-on* workflow
run on `windows` -- the program and one add-on per Archicad version, 26 to
30, with the install note and the licence; download it from the run's page
and put it in `site/download/Loriini_Win.zip` as it comes (GitHub serves
the artifact as that zip; its SHA-256 is the digest shown beside the
artifact on the run's page, so the page's figure can be checked against
it). Then update the version, date, size and SHA-256 under *Download* on
the page, and the Archicad versions wherever the pages name them:

```
sha256sum site/download/Loriini_Win.zip
fly deploy . --config deploy/site/fly.toml --dockerfile deploy/site/Dockerfile --ha=false
```

The first deploy made the app with `fly apps create loriini-site`. The
domain, `loriini.app`, is at Namecheap: A and AAAA records for `@` and `www`
point at the site's Fly addresses (`fly ips list --app loriini-site`), and
`licence` at the licence service's, with certificates from `fly certs add`.
The mailbox the keys come from, `sami@loriini.app`, is Namecheap's Private
Email (`mail.privateemail.com`, port 587, STARTTLS), set on the service with
`fly secrets set`.

Once the site serves the build, tell the licence service where it is, so a
recall's notice can point there:

```
uv run python scripts/licence.py set download=https://loriini.app/download/Loriini_Win.zip
```

## What it costs

A shared machine that stops when idle, started by the next visitor: cents a
month. The 83 MB download is inside the image, so a visitor's download comes
from Fly's edge in Sydney.
