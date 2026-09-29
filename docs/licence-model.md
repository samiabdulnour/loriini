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
| **How it is kept** | The signed key R5 built, **activated online** once per computer, then kept alive by **short signed leases** the program renews by itself. A new month renews without anyone pasting anything, a lapse or a withdrawal lands within a fortnight at most, and a day offline changes nothing. |
| **How it is paid** | *Pending: the comparison of payment providers (§5).* |
| **What runs it** | *Pending: build or buy (§6).* |
| **Also** | The licensee is named in what Loriini writes into a project. The build's fixed end date gives way to a minimum version the service can raise: a recall for a build with a known wrong result. Offline keys stay, for an office that cannot go online. |

The rest of this note is the reasoning.

## 1. What the product itself says

**Buyers are practices, not people.** A director decides, and a practice manager
often pays against an invoice. Practices run from two people to fifty. A practice that
pays for Archicad pays for its software as a matter of course. The risk is not that it
cracks Loriini: it is that it installs one licence on every desk, or forgets to renew.
So the model has to make being licensed the easy path and over-installing visible. It
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
deliberate act, which a practice with a professional reputation will not commit. Time
spent on obfuscation or anti-tamper is time taken from the product. It also makes
antivirus software -- already suspicious of PyInstaller executables -- more
suspicious still.

**Every user already has an Archicad licence.** Archicad has been sold only by
subscription since 2025, at A$4,210 a seat a year for Studio [1], and since February
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
  every comparable tool in §8 are sold only by subscription, and the perpetual
  add-ons that remain are the ones tied to Archicad dongles [4].
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

The user's instinct -- *something online, for a monthly subscription or for revoking
access* -- is right, and for three reasons beyond the two it names:
- A monthly subscription on offline keys means a new key pasted on every computer every
  month.
- Seats cannot be counted offline.
- A build cannot be recalled offline.

Online also means the office depends on the service. The leases in §4.2 are how that
dependence is kept small enough that nobody feels it.

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
- **Renewal: once a day,** at start and in the background. The program waits on the
  network only when no lease is in force, which means the first activation or a
  fortnight offline.
- **A lease never runs past the paid-to date plus the grace.** The grace matches the
  payment provider's retry window, 7 to 14 days, so a card being retried stops nobody.
  The lease's notice says what to do while it is retried.
- **A refusal is signed too,** so the program believes it and stops at once.
  Withdrawal is immediate for a computer that is online. Nobody but the vendor can
  forge a refusal to stop a practice.
- **The clock.** Winding the clock back still works against a computer kept off the
  network, as it does against any check made offline. On a work computer it breaks
  email and the web first, so it stays the speed bump it is today.

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
  enough; the service does not need to be highly available.
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

*Pending: Stripe direct against the merchants of record (Paddle, Lemon Squeezy, Polar, FastSpring), on fees, GST, invoices and bank transfer, and licence keys.*

## 6. What runs it

*Pending: a small service of our own against Keygen, Cryptlex, LicenseSpring and the payment providers' own licence keys.*

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
    `seats`, `release`.
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

*Pending, once §5, §6 and §8 are written.*

## Sources

*Pending.*
