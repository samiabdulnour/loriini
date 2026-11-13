# The licence service: putting it up and keeping it

The licence service keeps online licence keys in force (D125,
[`licensing.md`](licensing.md)). It is a small web service: Python's standard
library and one SQLite file, in one small container. It answers four requests:
- Loriini's, for a lease;
- Loriini's, to free a seat;
- Stripe's, when a payment happens;
- the vendor's script's, with an admin token.

Nothing about it needs to be highly available. Leases run a fortnight, so a
day's outage is never felt.

What it needs, all opened by the owner:
- an account with a container host (Fly.io below; any host that runs a
  container with a disk will do);
- a Stripe account;
- a mail account that can send over SMTP, for the keys it emails;
- nothing else. Its address is `https://<app>.fly.dev` from the start. A name
  of your own (`licence.example.com.au`) can be added at any time, and the
  `fly.dev` address keeps working beside it, so builds that carry it never
  lose the service.

## Putting it up, on Fly.io

From the repository's root, with [flyctl](https://fly.io/docs/flyctl/) installed
and signed in (`fly auth login`). An app's name is shared by everyone on Fly;
below it is `loriini-licences`. If that is taken, pick another, and use it
everywhere below and as `app` in `deploy/licence-service/fly.toml`.

```
fly apps create loriini-licences
fly volumes create licences --app loriini-licences --region syd --size 1
```

The secrets. The signing key is the hex line of the private key file `keygen`
wrote (PowerShell: `(Get-Content D:\Private\loriini-signing.key)[1]`); the
admin token is any long random string (`python -c "import secrets;
print(secrets.token_urlsafe(32))"`), kept in a password manager:

```
fly secrets set --app loriini-licences LORIINI_SIGNING_KEY=<hex> LORIINI_ADMIN_TOKEN=<token>
fly secrets set --app loriini-licences LORIINI_SMTP_HOST=smtp.office365.com ^
    LORIINI_SMTP_PORT=587 LORIINI_SMTP_USER=<user> LORIINI_SMTP_PASSWORD=<password> ^
    LORIINI_MAIL_FROM=<the address keys come from>
```

Then deploy:

```
fly deploy . --config deploy/licence-service/fly.toml --dockerfile deploy/licence-service/Dockerfile --ha=false
```

`--ha=false` keeps it to the one machine on the one volume. Without it, Fly's
first deploy adds a spare machine for availability, with a volume of its own,
and the two would keep two databases that never meet: a licence issued through
one would be unknown to the other.

A name of your own, whenever wanted:
`fly certs add licence.example.com.au --app loriini-licences` prints the DNS
record to add at the domain's registrar.

To check it:
- `https://loriini-licences.fly.dev/v1/health` answers `{"ok": true}`.
- With `LORIINI_LICENCE_SERVICE=https://loriini-licences.fly.dev` and
  `LORIINI_ADMIN_TOKEN` set on the vendor's machine,
  `uv run python scripts/licence.py status` lists no licences, without an
  error.
- `python -m sun_study.licence_service check` says whether the signing key it
  would run with is the one this checkout's build trusts. Run it with the same
  environment the container has. A service signing with any other key gives
  leases no build believes.

Finally, write the address into the build, and commit it:

```
uv run python scripts/licence.py service https://licence.loriini.app
```

## Stripe

1. **The product.** One product, Loriini, with two recurring prices per seat,
   monthly and yearly, in AUD and exclusive of tax. The seller is a Czech
   business, so a sale to an Australian practice carries neither GST nor VAT
   (docs/licence-model.md, §5): no tax rate, no ABN. In Settings → Business,
   the company's details and VAT number, which every invoice then carries.
2. **The checkout.** A payment link or Checkout session for each price:
   - let the quantity (the seats) be adjusted;
   - add a custom text field with the key `practice`, labelled *Practice
     name*, since it becomes the licence's holder;
   - collect the buyer's tax ID, which for a practice is its ABN, so that
     every invoice shows a sale to a business;
   - set a trial period there if wanted.
3. **The webhook.** In Developers → Webhooks, add an endpoint:
   - **address:** `https://loriini-licences.fly.dev/v1/stripe`;
   - **events:** `checkout.session.completed`, `invoice.paid`,
     `invoice.payment_failed`, `customer.subscription.created`,
     `customer.subscription.updated` and `customer.subscription.deleted`.

   Copy its signing secret into the service:

   ```
   fly secrets set --app loriini-licences STRIPE_WEBHOOK_SECRET=whsec_...
   ```

4. **The customer portal.** Turn it on (Settings → Billing → Customer portal),
   so that practices change their card and their seats themselves, and give its
   link to the service, so a failed payment's notice points there:

   ```
   uv run python scripts/licence.py set portal=https://billing.stripe.com/p/login/...
   ```

5. **Retries.** Stripe's Smart Retries try a failed card up to eight times over
   two weeks. That window is the 14 days' grace every lease allows past what is
   paid, so leave the retries on.

Stripe's test mode is worth a whole round first: a test payment link, a test
card, the key arriving by email, installed on a computer, and the licence under
`status` showing its computer.

## First things, once it runs

- **Take in the keys issued before it**, so their licence numbers are known and
  never issued again:
  `scripts/licence.py register --ledger D:\Private\licences.csv`
- **The first practice's licence** under LICENSE clause 1, complimentary:
  `scripts/licence.py issue --email ... --holder "Fuse Architects" --seats 50
  --complimentary --send`
- **The download address**, for a recall's sentence, once there is one:
  `scripts/licence.py set download=<where the current build is>`. R6 will
  serve the program from the service itself.

## Keeping it

- **Backups.** The *Licence database backup* workflow
  (`.github/workflows/backup.yml`) runs nightly and keeps each copy as an
  artifact for ninety days, `licences-encrypted-<run>`; *Run workflow* takes a
  copy now. By hand: `scripts/licence.py backup --out licences.sqlite3`. The
  backup is the SQLite file itself, copied consistently while the service
  runs. Fly also snapshots volumes daily, kept five days.
- **The backup is encrypted** (D179). The repository is public and so are its
  artifacts, and the database holds every holder's email and name, so the
  workflow encrypts the copy with [age](https://age-encryption.org) before it
  uploads it. It needs, beside the secret `LORIINI_ADMIN_TOKEN`:
  - **A key pair, made once on the vendor's own machine:**
    `age-keygen -o D:\Private\loriini-backup.key` (age: `winget install
    FiloSottile.age`, or `brew install age` on a Mac). It prints the public
    key, `age1...`. The `.key` file is the private half: keep it with the
    signing key, and a copy in the password manager. Lost, no backup made
    with it can be opened; nothing else is lost.
  - **The repository variable `LORIINI_BACKUP_RECIPIENTS`** (Settings >
    Secrets and variables > Actions > Variables): the public key, one per line
    for more than one person. It is not a secret. Without it the workflow
    stops before it fetches anything, so a missing key never makes a plain
    copy.
  - **Opening one:** download the artifact, unzip it, and
    `age --decrypt -i D:\Private\loriini-backup.key -o licences.sqlite3
    licences-<day>.sqlite3.age`.
- **Restoring.** Decrypt the copy as above, then stop the machine, copy the
  file onto the volume as
  `/data/licences.sqlite3` (`fly ssh sftp shell`), and start it again. What
  happened after the backup comes back as follows:
  - Stripe's next events move each licence on;
  - any key the service signed but has no record of is taken in again on its
    next use.
- **Updating.** Deploy again with the same command; the database stays on the
  volume.
- **Logs.** `fly logs --app loriini-licences`. Each lease refused, each payment
  and each change by the vendor is also in the service's own log, under
  `status 0042`.
- **The signing key** is the one thing whose loss matters. Leaked, anybody can
  issue keys and leases. Lost, no further key can be issued for the builds in
  circulation. Either way the cure is a new key pair, a new build, and a new key
  for everyone.
- **Cost.** A small shared machine that stops when idle, and a 1 GB volume: a
  few dollars a month at Fly's current prices. Stripe takes about 2.35% +
  A$0.30 of an Australian card payment.

## Its requests, for reference

| Request | Who | What |
|---|---|---|
| `GET /v1/health` | anything | `{"ok": true}` |
| `POST /v1/lease` | Loriini | `{key, machine, name, build}` gets `{lease}`: a grant, or a signed refusal |
| `POST /v1/release` | Loriini | `{key, machine}` gets `{released}` |
| `POST /v1/stripe` | Stripe | an event, signed with the webhook secret |
| `GET /v1/admin/licences` | the vendor | every licence |
| `POST /v1/admin/licences` | the vendor | issue: `{email, holder, seats, paid_to, months, online/offline, trial, days, complimentary, send}` |
| `GET /v1/admin/licences/0042` | the vendor | the licence, its key, its computers, its log |
| `POST /v1/admin/licences/0042` | the vendor | change: `{paid_to, seats, grace_days, withdraw, restore, email, holder, note}` |
| `POST /v1/admin/licences/0042/free` | the vendor | `{computer}`: its name, or its hash |
| `POST /v1/admin/licences/0042/send` | the vendor | its key's email, again |
| `POST /v1/admin/register` | the vendor | `{key}`: a key issued before the service |
| `GET`, `POST /v1/admin/settings` | the vendor | `minimum_build`, `recall_reason`, `download`, `portal`, `notice`, `serial_floor` |
| `GET /v1/admin/backup` | the vendor | the SQLite file |

Every admin request carries `Authorization: Bearer <token>`. Every error is a
sentence, as `{"error": ...}`.
