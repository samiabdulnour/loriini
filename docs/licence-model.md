# The licence model: what Loriini sells, and how it is kept

*An analysis, 29 September 2026.* What Loriini should sell, for how long, how the
licence is kept, how it is paid for, and what runs it. It starts from what the product
is and who buys it, looks at how comparable software is licensed and priced, and ends
in a recommendation and the decisions only the owner can make. Nothing here is built
beyond the offline keys of R5 ([`licensing.md`](licensing.md), D124); §9 says what
building it would change.

## The answer

| | |
|---|---|
| **What is sold** | A practice's subscription, counted in **seats**, where a seat is a computer that has used Loriini in the last fortnight. The key names the practice. |
| **For how long** | **Annual** as the anchor, paid by invoice or card; **monthly** at a premium, for a practice that needs Loriini for one DA; a **14-day trial**. No perpetual licence. |
| **How it is kept** | The signed key R5 built, **activated online** once per computer, then kept alive by **short signed leases** the program renews by itself. A new month renews without anyone pasting anything. A withdrawal reaches a computer that is online the same day, and one kept offline within a fortnight. A day offline changes nothing. |
| **How it is paid** | **Stripe, directly, in AUD.** Card or BECS for self-serve plans; annual invoices paid by bank transfer for practices that pay that way. Every invoice is a tax invoice carrying the owner's ABN. It costs less than half what a merchant of record takes. |
| **What runs it** | **A small licence service of our own**: Python and SQLite in one container, on R5's keys, for about A$10 a month. Every service for sale still needs a server of ours for Stripe's webhooks, so buying one adds a vendor without removing the server. Keygen is the fallback if running anything is unwelcome. |
| **Also** | The licensee is named in what Loriini writes into a project. The build's fixed end date gives way to a minimum version the service can raise: a recall for a build with a known wrong result. Offline keys stay, for an office that cannot go online. |

The rest of this note is the reasoning.

## 1. What the product itself says

**Buyers are practices, not people.** A director decides, and a practice manager
often pays against an invoice. Practices run from two people to fifty. A practice that
pays for Archicad pays for its software as a matter of course. The risk is not that it
cracks Loriini: it is that it installs one licence on every desk, or forgets to renew.
In a 2004 poll paid for by the software industry, 48% of architects said some software at work was
unlicensed, the most of the five professions asked. Software vendors in 2026 rank
over-use beside piracy [6]. So the model has to make being licensed the easy path and
over-installing visible. It
must not make a practice manager's life harder than a card on file or one invoice a
year.

**Use comes in bursts.** Solar access is assessed at concept and at DA. A practice with
one apartment project in the year uses Loriini for a few weeks; a practice with a
pipeline uses it every week. A seat paid for all year that sits idle for eleven months
feels expensive, so whatever is counted should follow use, not installation.

**The market is small, local and personal.** It is NSW architects on Archicad who
prepare apartment DAs. That is a few hundred practices at most -- an estimate, since
nobody publishes the number -- mostly in one city. Sales travel by recommendation. A
lockout on a DA deadline costs more in reputation than a year of unpaid seats costs in
revenue.

**One person sells, supports and writes it.** Every "my key doesn't work" is an hour
not spent on the software. So the model must look after itself: licences that renew
without anyone acting, seats that free themselves, and a message on screen that says
exactly what to do -- the standard R5 already set.

**The program is Python.** A PyInstaller bundle unpacks with public tools, so anyone
who wants to can remove a check from it; and by the LICENSE's own words the source may
be read. No enforcement can make not paying impossible. It can make not paying a
deliberate act, which a practice with a professional reputation will not commit.
PyInstaller itself dropped its bytecode encryption in version 6 as ineffective, and
a licensing vendor's own advice is that anti-tamper work has diminishing returns [6].
Time spent on obfuscation is time taken from the product, and it makes antivirus
software -- already suspicious of PyInstaller executables -- more suspicious still.

**Every user already has an Archicad licence.** Archicad is now sold only by
subscription, at A$4,210 a seat a year for Studio. Perpetual licences ended for new
customers at the end of 2024, and for everyone at the end of 2025 [1]. Since February
2026 Graphisoft sells it in Australia itself, having bought its distributor [2]. So
every buyer already pays yearly, per seat, for the program Loriini runs inside.
Archicad 26's API tells an add-on:
- the licence's serial number, and how many seats it has;
- whether it is a network, trial, demo or education licence;
- whether it carries a Forward subscription.

These come from `ACAPI_Protection_*` in the DevKit. From Archicad 28 the API also
gives stable, anonymous identifiers for the signed-in Graphisoft ID user and their
organisation, and Graphisoft's own example uses them to check an add-on's entitlement
[3]. §2 weighs tying seats to either.

**Its numbers end up in DAs.** A tool whose output is a compliance figure owes
something that other tools don't. The build term exists so that a stale copy on a
network drive stops rather than keeps answering (`licence.py`). By the same reasoning,
a *recall* -- stopping a build that is known to be wrong -- is worth more than
revocation. It also makes the terms of use, meaning what the numbers may be relied on
for, part of the licence model rather than an afterthought.

**The first practice already has a grant.** LICENSE clause 1 gives Fuse Architects
internal use at no charge. Whatever is built must carry a complimentary licence that
never lapses. Selling needs terms of its own, since today's LICENSE grants nothing to
anybody else.

**R5 is already built.** It has keys signed with Ed25519 and checked offline, installed
from the email, recorded in a ledger, with the box in the window (PR #12). The model
below keeps all of it and adds to it; nothing is thrown away.

## 2. What is counted

| Unit | Fits bursts of use | Simple for the practice | What enforcing it needs | Support it causes |
|---|---|---|---|---|
| Named user, with a login | partly | middling: accounts and passwords | an identity service | password resets, leavers |
| A computer, activated once | badly: an idle seat is paid for all year | middling | an activation service | moving to a new computer |
| **A computer active in the last 14 days** | **well: seats rotate** | **high: install it anywhere** | **the same activation service** | **little: seats free themselves** |
| Concurrent, while running | best | high | a live seat service with heartbeats; nothing works offline | network trouble in mid-run |
| The whole practice, by size tier | well | highest | nothing, on trust; or metering | least |
| Per Archicad licence (its serial) | badly: every Archicad seat is paid for | high | the add-on reads it, offline | every change to Graphisoft's licensing |
| Per project, as a pass | best for rare users | high | a key with a short term | defining "a project" |

**Recommended: count computers active in the last fortnight.** A seat is a computer
that has renewed a lease in the last 14 days. It gets most of what the whole-practice
tier gets:
- Loriini can be installed on every desk, and it is only counted where it is used.
- A practice that uses it in bursts rotates five seats among fifteen people.
- A computer that is replaced frees its seat by itself.

It also gets what per-seat pricing gets: revenue that grows with the practice, and a
count both sides can see. Tiers can still be the names on the price list ("Studio:
three seats"); underneath, the mechanism is one number.

**Seats are enforced with a margin.** Seats are counted and shown on both sides: the
info box says *4 of 5 seats in use*, and the vendor's list says which computers.
A practice one computer over its seats is told, not stopped, since the overlap is
usually an old computer that has not yet freed itself. A key used on well beyond its
seats is stopped. `Loriini.exe licence --remove` frees a seat at once.

**The whole-practice tier is the strong alternative.** It is the simplest thing that
could be sold, and it needs no counting at all. Its weakness is that "up to ten people"
rests on trust: a practice of forty on a ten-person tier is invisible, and so is a key
passed to a second practice. If the owner prefers it, the same service can meter
instead of enforce: count, report, and leave the rest to a conversation.

**The Archicad serial was considered and not chosen as the unit.** It is
attractive: the practice has already counted its seats for Graphisoft, and it would
work offline. But the serial belongs to hardware and software keys only [3], and a
practice on Graphisoft's cloud licences -- named or floating, on a Graphisoft ID -- has
none in that sense. A licence resting on it rests on another company's internals, which
change with each Archicad version the add-on has to follow. It is better used as a
signal. Where it exists, the activation can report it, so a key that turns up under
several unrelated Archicad licences stands out.

**Graphisoft ID is the unit to move to later.** The add-on builds against the 26.3000
kit, which has only a notification that the signed-in user changed. The identifiers
come with Archicad 28 (reportedly with a late Archicad 26 update, not checked here).
Once the add-on targets a version that has them:
- the practice's Graphisoft organisation can be the licence;
- each Graphisoft user in it can be a seat.

That is the named-user model the rest of the segment uses -- Enscape on a Chaos login,
Forma on an Autodesk one [4] -- without Loriini keeping a single account or password of
its own. The identifiers also exist in Archicad's demo mode, so they say who is using
Loriini, not that anyone has paid; the payment stays with the licence service. The
activation in §4 is built so that the computer can later be swapped for the Graphisoft
user without changing anything else.

**Per project is covered by monthly.** A practice that subscribes for the month of a DA
and then cancels has bought a project pass, without anyone having to define what a
project is.

## 3. For how long

- **Perpetual, with paid upgrades,** suits a finished product in a stable host.
  Loriini is neither. The validation is still open, and Archicad has a new version
  every year, each needing the add-on rebuilt. The ADG and the SEPPs change (SEPP 65
  itself was folded into the Housing SEPP in 2023). Those are recurring costs, which a
  one-off price does not cover. The market has already moved: Archicad and nearly
  every comparable tool in §8 are sold only by subscription. The perpetual licences
  left are older add-ons, tied to a dongle or to the Archicad key [4].
- **Annual** is what a practice budgets for and what an invoice suits, and it churns
  least. It is the anchor price.
- **Monthly** is for the practice with one DA a year. It costs more per month than
  annual -- the usual gap is that twelve months cost what ten do on annual -- so the
  practice that uses Loriini all year chooses annual by itself.
- **A 14-day trial** (R7 already says a fortnight) is fully working, with every sheet
  and table it makes stamped *trial -- not for submission*. The stamp is what converts
  trials, and it costs nothing to enforce, since the outputs carry it.

## 4. How the licence is kept

### 4.1 The ladder

| Step | What it stops | What it costs | Verdict |
|---|---|---|---|
| Terms only | nothing, except by contract | nothing | the floor under everything |
| Offline signed keys, one per period (R5 as built) | copying across time; stale builds | a key per period, pasted on every computer (twelve a year on a monthly plan); no withdrawal; no seat count | kept, for exceptions |
| **Signed key, online activation, short signed leases** | **lapses, withdrawals, over-installation, stale and recalled builds** | **a small service; one check a day** | **recommended** |
| Accounts and logins | keys passed between people | an identity service, password resets | not needed |
| Floating seats with heartbeats | use beyond the seats at any instant | a live service; offline use needs "borrowing" | later, if a large practice asks |
| Obfuscation, anti-tamper | casual patching | time; antivirus false alarms | no |

The owner's instinct -- *something online, for a monthly subscription or for
revoking access* -- is right, and for three reasons beyond the two it names:
- A monthly subscription on offline keys means a new key pasted on every computer every
  month.
- Seats cannot be counted offline.
- A build cannot be recalled offline.

Online also means the office depends on the service. The leases in §4.2 are how that
dependence is kept small enough that nobody feels it.

**What the work carries.** Each run already writes its ruleset, its version and its
time onto the Zones it assesses. Writing the licence number and the practice's name
beside them costs nothing. Every result in a project then says whose licence made it:
an audit trail for the practice, and a quiet reason not to lend a key to another one.
Trial outputs carry the visible stamp (§3).

### 4.2 Leases, in numbers

A **lease** is a small signed statement from the licence service: *licence 0042 is in
force on this computer until 14 October*. It carries:
- the day it was given, and the paid-to date;
- the seats, and how many are in use;
- when there is one, a notice: the payment failed, or an update is due.

It is signed with the same Ed25519 key as the licence keys, under a different domain
tag, so a key can never be passed off as a lease or a lease as a key. The key stays
what the practice pastes once. The lease is what the program fetches by itself.

- **Length: 14 days.** This one number sets three things:
  - the longest a computer works without contact;
  - the longest a withdrawal takes on a computer kept offline on purpose;
  - how long a seat counts as in use.

  It sits in the middle of the segment's norms. Graphisoft's own named licences
  allow 7 days offline, and Chaos lends an Enscape licence for 14. Adobe, Autodesk and
  JetBrains ask for contact every 30 days [6]. Anything longer would hold a seat for a
  month after a burst of use.
- **Renewal: once a day,** at start and in the background. The program waits on the
  network only when no lease is in force, which means the first activation or a
  fortnight offline.
- **A lease never runs past the paid-to date plus the grace.** The grace matches the
  payment provider's retry window: Stripe tries a failed card up to eight times over
  two weeks (§5), so the grace is 14 days. That way a card being retried stops nobody,
  and the lease's notice says what to do in the meantime. R5's week of grace was chosen
  for keys sent by email, and it stays for those.
- **A refusal is signed too,** so the program believes it and stops at once.
  Withdrawal is immediate for a computer that is online. Nobody but the vendor can
  forge a refusal to stop a practice.
- **The clock.** A lease carries the service's own date. A computer whose clock reads
  earlier than the day its lease was given asks the service again before it believes
  the lease, so winding the clock back gains nothing on a computer that is online.
  Off the network, a clock held inside the fortnight still works, as it does against
  any check made offline. No offline-only scheme stops that [6], and on a work
  computer it breaks email and the web first. A clock that runs *ahead* is never
  punished, which is the lockout that remembering dates would have caused (D124).

### 4.3 What the check sends

It sends:
- the licence number;
- a one-way hash of the computer (Windows' machine GUID and the user name, hashed with
  the product's name, so the raw values never leave the computer);
- the computer's name, so a practice can tell its seats apart;
- the Loriini version;
- optionally, the Archicad licence's serial.

It sends nothing about projects, files or results. This is a deliberate change from
R6's stance that the update check sends no identifier. The privacy note on the website
says what is sent and why, and so does `licensing.md`.

### 4.4 When things go wrong

- **The service is down.** Nobody notices for a fortnight. One small instance is
  enough; the service does not need to be highly available. This is the lesson of the
  segment's bad days. An Azure outage in October 2025 reportedly stopped Archicad's
  own cloud licence logins for about seven and a half hours. In January 2025 a
  certificate expiry at Chaos put customers' access at risk [6]. A lease that outlives
  the service's bad days, signed with a key the build carries, is immune to both.
- **An office proxy or firewall blocks it.** The office allows one host name. Failing
  that, it gets an offline key for the year (R5, as built).
- **A computer is replaced.** The old seat frees itself in 14 days, `licence --remove`
  on the old one frees it at once, and the margin covers the overlap.
- **A payment fails.** The lease carries the notice (*the October payment failed;
  update the card at …*), and the grace covers the retries.
- **The vendor stops, for good.** From the ledger, every current subscriber gets an
  offline key for the rest of the period they have paid for. A final build that needs
  no key is published. Saying this in the terms is part of selling to practices: a
  director buying from one person asks "and if you disappear?", and this is the
  answer.

## 5. How it is paid

The buyers are Australian practices that pay in AUD, many of them against an
invoice, and each needs a tax invoice it can claim GST on. That decides most of it [5]:

| | Stripe, direct | Stripe Managed Payments | Paddle | Lemon Squeezy | Polar |
|---|---|---|---|---|---|
| Who sells to the practice | the owner, with the ABN on every invoice | Link, LLC | Paddle (UK) | Lemon Squeezy (US) | Polar (US) |
| On an Australian card subscription | ≈2.35% + A$0.30 (card 1.65% from 1 October 2026, Billing 0.7%) | ≈5.85% + A$0.30 | 5% + 50¢ | ≈8% + 50¢ | ≈6.5% + 50¢, plus payout fees |
| An annual invoice paid by bank transfer, in AUD | yes: bank details on the invoice, marked paid when the money arrives; or BECS direct debit at 1%, capped at A$3.50 | no | only in USD, EUR or GBP | no | not documented |
| A tax invoice with the owner's ABN | yes | no | no | no | no |
| Licence keys | none | none | none | built in | built in |
| Worth knowing | the owner carries GST, disputes and support | new in April 2026; Stripe may refund within 60 days | invoices come from a foreign company | being wound down towards Managed Payments | young; changed its prices in 2026 |

**Recommended: Stripe, directly, in AUD.**
- **Invoices and EFT.** Of the five, it is the only one that gives every practice a
  tax invoice under the owner's ABN. It is also the only one that lets an annual
  invoice be paid by bank transfer in AUD, which is how many practices pay.
- **Cost.** It costs less than half as much: about 2.35% + A$0.30 on an Australian
  card from 1 October 2026, against 5% to 8% for a merchant of record.
- **What a merchant of record adds matters little here.** Its job is collecting other
  countries' taxes, mostly on sales to consumers, and this is a product sold to
  businesses in one state.
- **Leaving is cheap.** If overseas sales ever become real, Managed Payments can be
  turned on in the same Stripe account (+3.5%), or Polar used, and nothing else
  changes, since the licence service only needs to be told *paid to*.

**What the owner needs to set up:**
- **GST registration** is compulsory from A$75,000 a year. Below that it is
  voluntary, and only a registered business can issue a tax invoice, so a practice
  buying from an unregistered seller has no GST to claim. Many practices will ask for
  one, which argues for registering from the start.
- **Invoices.** In Stripe, a manual 10% GST rate (Stripe Tax is not needed for sales
  in Australia), and "Tax invoice" with the ABN on every invoice.
- **Surcharges** on eftpos, Mastercard and Visa cards are banned from 1 October 2026,
  so the card fee is part of the price.
- **An accountant's hour.** A ruling from July 2025 (GSTR 2025/1) bears on software
  sold to Australians through an overseas merchant of record. That is one more reason
  to sell directly, and worth confirming with an accountant either way.

**How it is set up:**
- **Plans.** One product with two prices per seat, annual and monthly, in AUD, quoted
  without GST as practices expect.
- **Checkout** takes a card or BECS. The 14-day trial needs no card.
- **The Customer Portal** lets a practice change its card and its seats and download
  its invoices.
- **Larger practices** get an annual Stripe invoice with the bank details on it,
  marked paid on arrival. Paid that way it costs only Billing's 0.7%.
- **Smart Retries** try a failed card up to eight times over two weeks. That is where
  the lease's grace of 14 days comes from (§4.2).
- **Stripe has no licence keys**; its Entitlements only switch features on and off.
  So the licence service (§6) listens to Stripe's webhooks:
  - an invoice paid moves *paid to*;
  - a change of quantity changes the seats;
  - a cancelled subscription is left to lapse at the end of what was paid.

## 6. What runs it

Stripe collects the money; something has to turn *paid to 31 October* into leases.
It can be built or bought [6]:

| | Cost at 50 to 500 seats | What it gives | What is still ours | Lock-in |
|---|---|---|---|---|
| **A service of our own** | about A$10 a month to host; four to six days to build | §4 exactly: leases, seats with a margin, withdrawal, recall, notices, on R5's keys as they are | running it: one container, SQLite, a nightly copy | none |
| Keygen Cloud (Std 1) | US$990 a year, ≈A$1,400 | licences, machines, heartbeats, machine files and responses signed with Ed25519 | a Stripe webhook handler hosted by us anyway, since Keygen has no Stripe integration; a REST client; R5's keys replaced by Keygen's | low: its source is available |
| Keygen CE, self-hosted | free, plus Postgres and Redis to run | the same, less audit logs | a bigger stack to run than our own | lowest |
| Cryptlex | US$100 a month; US$300 with floating seats | node-locked seats, offline use, clock checks | a Stripe script hosted by us; its own SDK | high |
| LicenseSpring | US$199 a month; US$750 with floating seats | a Stripe app that follows renewals, seats and refunds | its entry plan allows 10,000 calls a month, and a daily check from 500 computers is 15,000 | high |
| Polar's or Lemon Squeezy's keys | inside their 5% to 8% | activation limits; keys that follow the subscription | leases and offline use, since their checks are unsigned and online-only; Lemon Squeezy is winding down | medium to high |

**Recommended: our own.**
- **The hard part is done.** Signing, verifying, the key format and the box are R5,
  built and tested. What is left is small: a table of licences, a table of computers,
  and four kinds of request -- activate or renew, release, Stripe's webhook, and the
  vendor's commands.
- **Buying does not remove the server.** Keygen and Cryptlex still need a webhook
  handler of ours. LicenseSpring's entry plan is capped below one check a day. Polar's
  and Lemon Squeezy's keys are unsigned and online-only, so leases would be built on
  top of them anyway. Buying adds a second vendor and keeps the first job.
- **The trust anchor stays ours.** The key that signs every lease is the one R5 pinned
  in the build. No third party's outage, price change or certificate can lock a
  practice out (§4.4).
- **It costs about A$10 a month,** against A$1,400 a year and upwards.

What it asks of the owner is running it, and the leases make that light:
- one small container on a host with a disk (Fly.io, or a small VPS);
- SQLite, copied nightly somewhere else;
- the signing key and Stripe's webhook secret kept as its secrets.

It can be down for a day without anybody noticing (§4.4). If running anything at all
is unwelcome, Keygen Cloud is the fallback. Its machine files are signed leases in all
but name, at the price of replacing R5's keys with Keygen's.

## 7. Around the edges

- **The first practice.** Fuse Architects gets a complimentary licence under LICENSE
  clause 1: online, so that it receives recalls and notices, but never refused for
  payment, and with more seats than the practice has desks.
- **Trials.** Fourteen days, three seats, online, with outputs stamped. They are issued
  by hand at first; the website issues them later (R7). A trial is tied to an email
  address and a computer, so a second trial on the same computer is visible.
- **Education.** Free, later: Archicad's education flag is readable from the add-on,
  and education outputs are stamped too.
- **Graphisoft, and whoever else sells to these practices.** There is no Graphisoft
  add-on store: one is on its roadmap, "under research" [3]. Add-ons are sold directly,
  as this one will be. Graphisoft now sells Archicad in Australia itself, and with the
  distributor it bought Ci Tools, whose Sites tool checks boundaries and height planes
  -- next door to Loriini, and a reason to know the people there [2]. If anyone ever
  resells Loriini, one price per seat per year leaves room for their margin. The
  service needs one thing for it: a licence whose payer is the reseller and whose
  holder is the practice.
- **The terms.** Selling needs a commercial licence agreement of its own, covering:
  - what the numbers may be relied on for, with the prototype notice until the
    validation is done;
  - the limit of liability;
  - the seats, and the continuity promise in §4.4;
  - the privacy note.

  The Australian Consumer Law's guarantees apply to business purchases under
  $100,000. They cannot be excluded, but for goods and services not ordinarily bought
  for personal use the remedies can be limited, for instance to supplying the service
  again. The agreement is worth a lawyer's hour: the risk to the business is a wrong
  number in a DA, not piracy.

## 8. Price

What comparable things cost, in A$ a seat a year unless said, without GST, converted
at US$1 = A$1.42 and €1 = A$1.62 on 29 September 2026 [4]:

| | Price | Licence |
|---|---|---|
| Archicad Studio / Collaborate | 4,210 / 4,955 | subscription only; Graphisoft ID, named or floating |
| DL-Light SEPP65, for SketchUp: ADG solar access, the nearest competitor | ≈810 the first year, ≈490 a year after; ≈325 for one month | one person, one computer |
| archiZone (Architools): zoning compliance inside Archicad | ≈470, or ≈47 a month | per user, one active computer |
| Shadowmap Studio | ≈850 billed yearly; ≈85 a month on monthly | per user |
| Autodesk Forma Site Design | ≈995, or ≈120 a month | named user |
| Enscape | ≈820 to 1,040 | named user, on a Chaos login |
| Pollination for Rhino / Revit | ≈1,950 / ≈3,900 | concurrent, plus user packs |
| Ladybug Tools, SunHours, Andrew Marsh's tools | free | -- |
| A consultant's DA shadow diagrams | 240 to 1,500 a package | -- |
| A desktop ADG check | from 199 | -- |

What it says:
- **Bands.** Single-purpose AEC tools sit at A$500 to 1,000 a seat a year, and suites
  at A$1,600 to 4,500. Loriini is a single-purpose tool that also does a suite's
  drawing and yield work, inside Archicad, at about a sixth of Archicad's own price.
- **The nearest competitor.** DL-Light sells ADG solar access on SketchUp at about
  A$800 and then A$500 a year. It also sells a one-month licence: the DA burst, priced
  as a product. Nothing found does it inside Archicad.
- **Monthly premiums.** Monthly plans usually cost about 20% more (Shadowmap,
  Archistar). The range runs from 10% (Pollination) to 80% (Enscape).
- **The real competitor.** The free tools are the practice's current chain, Ladybug in
  Grasshopper. They cost a specialist's time, not a licence.
- **Consultants.** They price shadow diagrams low, A$240 to 1,500 a package. Apartment
  ADG studies are quoted per job and never published. Loriini's value is not one
  report; it is being able to run the study again every time the massing moves.

A starting point, to be tested with the first practices:
- **Annual: A$600 to 900 a seat,** less per seat from five seats up.
- **Monthly: a tenth of the annual price a month,** A$60 to 90 a seat. That is 20% more
  over a year, and a DA month on three seats costs less than one consultant's shadow
  package.
- **A founding price while the prototype notice stands.** Selling "not validated for
  submission" at full price is a hard conversation; a founding price, kept for the
  first practices through their renewals, is an honest one. Those practices are also
  the validation.

## 9. What it changes in the roadmap

- **R5.** PR #12 merges as it is: the key format, the box, the command, the ledger and
  the issuing all carry over. What comes next is R5's second half:
  - a flag in the key marking it online;
  - leases, activation and seat counting;
  - withdrawal and recall;
  - the licence service;
  - the vendor's commands against it: `status`, `paid`, `withdraw`, `restore`,
    `seats`, `release`;
  - the licensee written beside each result, and the trial stamp.

  Four to six days, the service included.
- **R6.** The minimum version lives in the lease. The update manifest stays a static
  file, as R6 planned; the lease's notice can point at it.
- **R7.** The shop's webhook stops emailing a new key every period. It tells the
  service *paid to 31 October*, and the leases follow. A practice's first key is still
  emailed once.
- **The build term (`EXPIRES`).** It stays for builds that take no keys, such as
  office builds and betas. A keyed build relies on the service's minimum version
  instead, so paying subscribers never hit a cliff on a fixed date, and a build with a
  known wrong result can be stopped on the day it is found, not on 1 January.

## 10. Decisions for the owner

Each with what this note recommends:

1. **What is counted.** Seats as computers used in the last fortnight, or the whole
   practice by size, metered rather than enforced. *Recommended: seats.*
2. **The seat margin.** *Recommended: one computer over is told, two over is stopped,
   adjustable per licence.*
3. **The price.** *Suggested: A$600 to 900 a seat a year, a tenth of that a month, and
   a founding price for the first practices.* Test it with them before it is printed.
4. **GST.** *Recommended: register from the start, so that every invoice is a tax
   invoice.* An accountant's hour on it, and on GSTR 2025/1.
5. **Payments.** *Recommended: Stripe, directly, in AUD.* The owner opens the account,
   with the ABN.
6. **Build or buy the licence service.** *Recommended: build it,* on R5's keys as
   they are. *Fallback: Keygen Cloud.*
7. **Where it runs.** A small container host or VPS, and a name for it under the
   website's domain (R7). The owner opens both accounts.
8. **The lease and the grace.** *Recommended: 14 days each.*
9. **The terms.** A commercial licence agreement and a privacy note, with the
   continuity promise in them, and a lawyer's hour on both.
10. **The order.** *Recommended:*
    1. merge PR #12;
    2. R5's second half: the service, leases, seats and recall, with Fuse and the
       first practices moved to online keys by hand;
    3. Stripe and the website (R7);
    4. Graphisoft ID seats, when the add-on moves to Archicad 28 or later.

## Sources

Checked on 29 September 2026. Some vendors' pages (Autodesk, Adobe, Graphisoft
support, the ATO) would not load directly. Their figures come from those pages as
search engines index them, and the text says *reportedly* where it leans on one.

1. Archicad's price and licensing:
   - [Graphisoft Australia, Archicad Studio](https://www.graphisoft.com/en-au/plans-and-products/archicad-studio/)
   - [Nemetschek on the move to subscription](https://www.nemetschek.com/en/news-media/graphisoft-announces-next-phase-its-shift-future-proof-subscription-model)
   - [Archicad 29 help on licensing](https://help.graphisoft.com/AC/29/INT/_AC29_Help/022_Licensing/022_Licensing-2.htm)
2. [Architosh: Graphisoft buys its Australian and New Zealand distributors, February 2026](https://architosh.com/2026/02/graphisoft-acquires-its-australian-and-new-zealand-distributors/).
3. The Archicad API:
   - [`ACAPI::GSID`](https://graphisoft.github.io/archicad-api-devkit/class_a_c_a_p_i_1_1_g_s_i_d.html)
   - [licence information and serial numbers](https://graphisoft.github.io/archicad-api-devkit/group___license_info.html)
   - the 26.3000 kit this repository builds against: `ACAPI_Protection_*` in `ACAPinc.h`, and `API_IGraphisoftIDEventHandler` in `APIdefs_Callback.h`
   - [an add-on's MDID](https://archicadapi.graphisoft.com/how-to-get-mdid-for-my-add-on)
   - The add-on store is on Graphisoft's public roadmap, last seen "under research" in April 2025; no live store was found.
4. Comparable tools and services:
   - [DL-Light](https://deluminaelab.com/en/licenses/)
   - [Architools](https://architools.net/)
   - [Shadowmap](https://shadowmap.org/pricing)
   - [Enscape](https://www.chaos.com/enscape/pricing)
   - [Pollination](https://www.pollination.solutions/pricing)
   - [Archistar](https://www.archistar.ai/pricing/)
   - [Cigraph](http://www.cigraph.it/en/node/164)
   - [Andrew Marsh](https://andrewmarsh.com/software/)
   - Autodesk Forma, from Autodesk's page as indexed
   - Consultants: [WeShadow](https://www.weshadow.au/), [Amores](https://www.amores.au/product-page/shadow-diagram), [Feasly's guide](https://www.feasly.com.au/guides/shadow-diagrams-solar-access-australia-developer-guide) and [Town Planning Online](https://www.townplanning.com.au/nsw/adg-check)
5. Payments and GST:
   - Stripe:
     - [Australian pricing](https://stripe.com/au/pricing)
     - [card pricing from October 2026](https://support.stripe.com/questions/updates-to-card-pricing-in-australia-from-october-2026)
     - [Billing pricing](https://stripe.com/au/billing/pricing)
     - [Invoicing pricing](https://support.stripe.com/questions/stripe-invoicing-pricing)
     - [invoice payment methods](https://docs.stripe.com/invoicing/payment-methods)
     - [Australian invoicing](https://docs.stripe.com/invoicing/australia-invoicing)
     - [Smart Retries](https://docs.stripe.com/billing/revenue-recovery/smart-retries)
     - Managed Payments: [pricing](https://support.stripe.com/questions/managed-payments-pricing) and [eligibility](https://docs.stripe.com/payments/managed-payments/eligibility)
   - Paddle: [pricing](https://www.paddle.com/pricing) and [invoices](https://developer.paddle.com/build/invoices/create-issue-invoices)
   - Lemon Squeezy: [2026 update](https://www.lemonsqueezy.com/blog/2026-update) and [fees](https://docs.lemonsqueezy.com/help/getting-started/fees)
   - Polar: [fees](https://polar.sh/docs/merchant-of-record/fees) and [licence keys](https://polar.sh/docs/features/benefits/license-keys)
   - GST:
     - [registering for GST](https://business.gov.au/registrations/register-for-taxes/register-for-goods-and-services-tax-gst)
     - [GSTR 2025/1](https://www.ato.gov.au/law/view/document?DocID=GST%2FGSTR20251%2FNAT%2FATO%2F00001)
     - [the RBA on surcharges](https://www.rba.gov.au/payments-and-infrastructure/review-of-retail-payments-regulation/2026-03/conclusions-paper/faqs/)
6. Licensing services and practice:
   - Keygen: [pricing](https://keygen.sh/pricing/), [Keygen and Stripe](https://keygen.sh/integrate/stripe/) and [security](https://keygen.sh/docs/api/security/)
   - [Cryptlex pricing](https://cryptlex.com/pricing)
   - [LicenseSpring pricing](https://licensespring.com/pricing)
   - Offline periods: [Adobe](https://helpx.adobe.com/creative-cloud/kb/internet-connection-creative-cloud-apps.html), [JetBrains](https://sales.jetbrains.com/hc/en-gb/articles/206544169), [Graphisoft's named licences](https://support.graphisoft.com/hc/en-us/articles/36564607306897), [Chaos](https://support.chaos.com/hc/en-us/articles/360020455278) and Autodesk (via [IMAGINiT](https://resources.imaginit.com/support-blog/how-long-can-an-autodesk-product-on-subscription-be-used-without-an-internet-connection))
   - [PyInstaller 6.0's changes](https://pyinstaller.org/en/v6.0.0/CHANGES.html)
   - [Revenera's 2026 outlook](https://www.globenewswire.com/news-release/2025/11/13/3187406/0/en/Revenera-s-Monetization-Monitor-2026-Outlook-Almost-1-in-3-Software-Producers-say-Piracy-is-a-Major-Problem.html)
   - [Ipsos for the BSA, 2004](https://www.ipsos.com/en-us/online-software-piracy-poll)
   - [the Chaos certificate expiry](https://support.chaos.com/hc/en-us/articles/30185867975185)
