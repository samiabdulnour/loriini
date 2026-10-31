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
site itself), nothing to keep running; the one script is the front's picture,
inline, talking to nothing.

## What is where

| | |
|---|---|
| `site/index.html` | The front: the name, large, over the top of the picture, and the picture the width of the page, on white; the front runs wider than a tab's page, its margins a share of the window, and its top bar holds only the tabs, while every other page's has the name on the left, linking home; every page runs the same width, its margins a share of the window. The picture is a canvas of whole cells, edge to edge, with a sharp edge all round: five black towers and the lorikeet standing where the sky meets the ground, the bird turned to face left, and their light grey shadows on the strip of khaki ground in front of them. The sky takes the hour's colour, pale at sunrise, blue at noon, red at sunset, passing between them through a nearly white sky and, in the evening, an apricot and an orange, with three uneven bands of glow round the sun, a plain yellow disc, tight at noon and spreading wide at sunrise and sunset; its light colours the ground, the shadows and the bird a little. The sun keeps to the day's arc on its own; the pointer takes it, always behind the towers, the bird and the ground, and the shadows follow it, short when it is high, long when it is low, thrown away from its side. On a narrow screen the picture shows the middle of the scene, round the bird. |
| `site/makes.html`, `site/works.html`, `site/price.html`, `site/download.html` | The tabs: what it makes, how it works, price, download. Contact lives in every footer. |
| `site/terms.html`, `site/privacy.html` | The licence terms and the privacy note, **drafts for a lawyer's hour** (licence-model.md §7). |
| `site/style.css` | The one stylesheet. One typeface in two weights (400, 600) and three sizes (`--s`, `--m`, `--l`) and nothing else; thin 1px lines, flat buttons, a white page. |
| `site/fonts/` | Inter, regular and semibold, Latin and Latin Extended, self-hosted, with its licence (SIL OFL 1.1). |
| `site/favicon.ico`, `site/icon-*.png`, `site/apple-touch-icon.png` | The application icon, the lorikeet over the black L on its orange tile (D151), written by `scripts/make_icon.py`. `icon-52.png`, the mark at double density, is not shown in the top bar, which carries the name alone, as the front does. |
| `site/lorikeet.png` | The whole bird that stands among the front picture's towers, at native resolution and drawn with its pixels whole. |
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
