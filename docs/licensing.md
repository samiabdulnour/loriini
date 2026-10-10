# Licence keys: a subscription, kept in force online

Loriini is sold by subscription. Each practice is emailed one **licence key**. It
is pasted into Loriini once on each computer, and from then on Loriini keeps it in
force by itself: once a day, while it is used, it asks the licence service for a
**lease** -- a small signed note that says the licence is in force on this
computer for the next fortnight. A monthly renewal needs nothing from anyone. A
lapse, or a licence the vendor withdraws, stops Loriini at the next contact,
with the reason in a sentence.

This is roadmap R5. D124 is how the keys are built and D125 is how they are kept
in force online. [`licence-model.md`](licence-model.md) is why the model is
what it is, and [`licence-service.md`](licence-service.md) is how the service
is run.

An **offline key** -- the whole licence, good to a last day, checked on the
computer alone -- still exists for the office that cannot let Loriini reach the
internet. It is the exception, and the last section says what it gives up.

## For a subscriber

**Installing the key.** Open Loriini. It asks for the key when it opens:
- paste the whole key from the email, from `LORIINI` to the last group (the line
  breaks do not matter);
- read the line under it, which says whose licence the key is *before*
  anything is pressed;
- press **Use this key**.

Loriini then checks the key with the licence service, which takes a second or
two, and the window opens. If the key is not whole -- a mail client cut it, or
a character went wrong -- the line says so in red: *copy it again, all of it*.
If the service refuses it -- every seat is in use, say -- the line says why, and
**Try again** asks once more once that is put right.

Each person using Loriini does the same on their own computer. The key is kept
in `%APPDATA%\Loriini\licence.key`, and the lease beside it in `licence.lease`.

**Day to day there is nothing to do.**
- **Once a day** Loriini asks the service for a fresh lease, in the background,
  when it starts. Nobody waits for it.
- **Offline**, a lease runs a fortnight, so a day without internet changes
  nothing. Loriini waits on the network only when it holds no lease in force:
  the first time, or after a fortnight offline.
- **Renewals** need nothing. When the subscription renews, the lease follows,
  and there is no new key.

**The About box** says whose licence it is and what the service last said:

> Licensed: licence 0042, Fuse Architects (office@fuse.example), 12 seats,
> renewed online. Paid to 31 October 2026; 4 of 12 seats in use; checked with
> the licence service on 29 September 2026.

**Check now** asks the service there and then -- after a payment, say, or a seat
freed on another computer. When the service has something to say -- *the
October payment failed; update the card at …* -- it is said there too, and the
foot of the window points at it.

**Seats** are counted as computers that have used Loriini in the last
fortnight.
- **Rotating.** Loriini can be installed on every desk; a practice using it in
  bursts rotates its seats among everyone.
- **Freeing.** A computer that stops using Loriini frees its seat a fortnight
  after its last use. `Loriini.exe licence --remove` frees it at once, which is
  the thing to do before a computer is handed on.
- **Over the seats.** A practice one computer over is told, not stopped. A
  second computer over is refused, with the names of the computers holding the
  seats.

**When Loriini stops**, it says why, and what to do:
- the subscription was paid to a day and has not been renewed;
- the licence was withdrawn;
- every seat is in use;
- this version of Loriini has been recalled -- a version found to give a wrong
  result, stopped the day that is found, with where the current one is. The
  licence carries over to the new version.

**On a command line**, or for an agent (`Loriini.exe mcp`):

```
Loriini.exe licence LORIINI-XXXXX-XXXXX-...     installs a key, and checks it
Loriini.exe licence                             says what is installed
Loriini.exe licence --renew                     asks the licence service now
Loriini.exe licence --remove                    removes it, freeing its seat
```

A command that would touch a project without a usable licence refuses at the
door, before connecting to Archicad, with the sentence that says what to do.
`--help`, `rulesets`, `info` and `licence` itself always run.

**What Loriini sends** to the licence service, and nothing else:
- the licence key;
- a one-way hash of the computer, made from Windows' machine GUID and the
  user's name with the product's name mixed in, so the raw values never leave
  the computer;
- the user's and computer's names (`jsmith on FUSE-PC-07`), so a practice can
  tell its seats apart;
- the version of Loriini.

Nothing about any project, file or result is sent.

**Through a proxy or firewall**, Loriini needs HTTPS to the licence service's
one address. It uses Windows' own proxy setting and certificate store, as a
browser does.

**Every result says whose licence made it**: the CSV and JSON headers carry a
`licence` line, and the Zone property *Solar Analysis Run* carries it beside
the time of the run.

## For the vendor

### Once: the key pair, and where the service is

```
uv run python scripts/licence.py keygen --out "D:\Private\loriini-signing.key"
uv run python scripts/licence.py service https://loriini-licences.fly.dev
```

`keygen` makes the Ed25519 key pair.
- **The private half** goes into the file named. Keep it out of every
  repository, back it up, and give it to the licence service as a secret: with
  it anybody can issue keys and leases.
- **The public half** is written into `src/sun_study/licence_public_key.py`.

`service` writes the service's address into the same file. Commit it: from the
next build on, Loriini asks for a key and keeps online keys in force at that
address. Until that file carries a key, a build takes no keys at all and runs on
its own term (`licence.EXPIRES`), as the office's builds always have.

[`licence-service.md`](licence-service.md) is how to put the service up (one
small container), point Stripe at it, and take in the keys issued before it
ran.

### Selling

Stripe does it, and the service follows. Somebody subscribes through Stripe
Checkout or a payment link:
- the service makes the licence, for the seats bought and the practice named
  at the checkout;
- it issues the online key and emails it;
- each invoice paid moves the licence's paid-to date;
- a failed card is said on every lease while Stripe retries, and the 14 days'
  grace covers the retries;
- a cancelled subscription lapses on the day it was paid to.

Nothing is done by hand.

### By hand, through the service

With `LORIINI_ADMIN_TOKEN` set to the service's admin token:

```
scripts/licence.py issue --email office@fuse.example --holder "Fuse Architects" ^
    --seats 12 --online --paid-to 2026-10-31 --send      a practice paying by invoice
scripts/licence.py issue --email ... --trial --send      a fortnight's trial, 1 seat
scripts/licence.py issue --email ... --complimentary     never lapses (LICENSE clause 1)
scripts/licence.py paid 0042 --to 2026-11-30             their next invoice, paid
scripts/licence.py status [0042]                         every licence, or one in full
scripts/licence.py seats 0042 14
scripts/licence.py withdraw 0042 --reason "refunded"     and restore 0042
scripts/licence.py free 0042 "jsmith on FUSE-PC-07"      a seat, from the vendor's side
scripts/licence.py send 0042                             the key's email, again
scripts/licence.py recall --below 1.2.1 --reason "..."   stop a wrong version; --clear
scripts/licence.py notice "Loriini 1.3 is out."          said on every lease; --clear
scripts/licence.py backup --out D:\Backups\licences.sqlite3
```

`status 0042` says everything the service knows about a licence: the key (to
send again), the computers holding its seats and when each was last seen, and
what has happened to it.

### Offline keys, still

`scripts/licence.py issue --signing-key "D:\Private\loriini-signing.key" ...`
without `--online` signs an offline key on the vendor's own machine, as R5 did:
the period paid for plus a week, recorded in `licences.csv` beside the signing
key and emailed as a draft or over SMTP. It is for the office that cannot let
Loriini reach the internet, paid a year ahead. `show LORIINI-...` says what any
key is and whether it checks out.

## What is checked, and what is not

**Checked, at every start:**
- the key is **whole** (a CRC over it);
- it is **genuine** (an Ed25519 signature by the vendor's key, checked with the
  public key compiled into the build);
- for an online key, the **lease** held is genuine, is for this key on this
  computer, and is in force on this computer's date. A lease copied from
  another computer, written by hand or served by anything but the licence
  service is refused, like a forged key;
- for an offline key, the key is in force on this computer's date.

**Stopped at the next contact with the service:** a lapse, a withdrawal, a
licence over its seats, a recalled version. On a computer kept offline on
purpose, within a fortnight.

**The clock.** A computer whose date is earlier than the day its lease was
given is told to set its clock right, with the service's date. Off the network,
a clock held inside the fortnight still works, as against any check made
offline, and on a work computer it breaks email and the web first. A clock that
once ran ahead is never punished afterwards.

**The build's own term** (`licence.EXPIRES`) binds builds that take no keys, and
offline keys. It does not bind an online key: the service's recall stops a
version known to be wrong on the day it is found, rather than every version on
a fixed date.

**An offline key gives up the rest:** it cannot be withdrawn, seats are printed
on it but not counted, and a renewal is a new key by email.

## How the key is written

`LORIINI-` and groups of five characters in Crockford's base 32: digits and
capitals without I, L, O or U, read back case-blind, with O taken as 0 and I or
L as 1. So a key survives being read aloud, retyped, lower-cased or wrapped over
lines.

Inside it:
- a format version, and whether it is online, a trial, or offline;
- the licence number;
- the issue date, and the last day (an online key's first period);
- the seats;
- the email and the holder's name;
- the signature over all of them and a domain tag;
- then the CRC.

It is about 200 characters. Nobody types it, and pasting does not mind.
