# The website: the front on the shop and the download

R7 was decided against on 29 September (nothing in selling Loriini needed a
site) and taken up again on 8 October: a practice looking for Loriini needs
one page that says what it makes, what it costs, where the download is, and
the terms and privacy pages Stripe asks a seller to link to. That is all the
site is. Buying still happens on Stripe's own pages, reached by the payment
links; the key still comes from the licence service
([`licence-service.md`](licence-service.md)).

It is four static files and the current build, served by nginx, on Fly.io
beside the licence service, at `https://loriini.app` (and `www.loriini.app`;
the `loriini-site.fly.dev` address keeps working). No cookies, no analytics,
nothing to keep running; the one script is the home page's pixel-sun
animation, inline, talking to nothing.

## What is where

| | |
|---|---|
| `site/index.html` | The front: the name and the picture (the pixel-sun animation until there is a screen recording), nothing else. |
| `site/makes.html`, `site/works.html`, `site/price.html`, `site/download.html` | The tabs: what it makes, how it works, price, download. Contact lives in every footer. |
| `site/terms.html`, `site/privacy.html` | The licence terms and the privacy note, **drafts for a lawyer's hour** (licence-model.md §7). |
| `site/style.css` | The one stylesheet: a warm grey page, charcoal lines, mono labels, and the lorikeet's colours as pixels. |
| `site/download/` | The current build's zip, put there at deploy time and never committed. |
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
`Loriini_AC26_Win` artifact of the newest successful *Archicad add-on*
workflow run; download it from the run's page and put it in
`site/download/Loriini_AC26_Win.zip`, then update the version, date, size
and SHA-256 under *Download* on the page:

```
sha256sum site/download/Loriini_AC26_Win.zip
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
uv run python scripts/licence.py set download=https://loriini.app/download/Loriini_AC26_Win.zip
```

## What it costs

A shared machine that stops when idle, started by the next visitor: cents a
month. The 65 MB download is inside the image, so a visitor's download comes
from Fly's edge in Sydney.
