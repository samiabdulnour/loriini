# Licence keys: a subscription, a key per paid period

Loriini is sold by subscription. Each subscriber is emailed a **licence key**
for the period they have paid for; they paste it into Loriini once, and
Loriini checks it at every start, offline. When the subscription renews, a new
key comes the same way. When it lapses, the last key runs out and Loriini asks
for a new one. This is roadmap R5; D124 records how it is built.

## For a subscriber

**Installing a key.** Open Loriini. A build that takes keys asks for one when
it opens: paste the whole key from the email -- from `LORIINI` to the last
group; the line breaks do not matter -- and read the line under it. It says
whose licence the key is and until when, *before* anything is pressed:

> This is licence 0042, Fuse Architects (office@fuse.example), 12 seats,
> until 5 October 2027.

If the key is not whole -- a mail client cut it, or a character went wrong --
the line says so in red: *copy it again, all of it*. That is not the key
being refused as a forgery, and the fix is a second paste. Press **Use this
key** and the window opens. The key is kept in `%APPDATA%\Loriini\licence.key`,
beside the saved settings, so it is asked for once per person per machine.

**Renewing.** Each renewal brings a new key by email before the old one runs
out, with a week's grace after the paid period so a late email stops nobody.
Install it from the info box (ⓘ, then **Enter licence key…**), or simply when
Loriini asks for it after the old key's last day.

**On a command line**, or for an agent (`Loriini.exe mcp`):

```
Loriini.exe licence LORIINI-XXXXX-XXXXX-...     installs a key
Loriini.exe licence                             says what is installed
Loriini.exe licence --remove                    forgets it
```

A command that would touch a project without a usable key refuses at the
door, before connecting to Archicad, with the sentence that says what to do.
The ones that only say something -- `--help`, `rulesets`, `info` -- and
`licence` itself always run.

**The foot of the window** says whose licence it is and until when.

## For the vendor

### Once: the key pair

```
uv run python scripts/licence.py keygen --out "D:\Private\loriini-signing.key"
```

This makes an Ed25519 key pair. The **private half** goes into the file named
-- keep it out of every repository, back it up, and treat it like a
certificate's private key: with it anybody can issue keys, and without it no
further key can be issued for the builds in circulation. The **public half** is
written into `src/sun_study/licence_public_key.py`. Commit that file: from the
next build on, Loriini asks for a licence key.

Until that file carries a key, a build takes no keys at all and runs on its
own term (`licence.EXPIRES`) exactly as the office's builds always have. The
two kinds of build are the same code with one line different.

### For each paid period

```
uv run python scripts/licence.py issue --signing-key "D:\Private\loriini-signing.key" ^
    --email office@fuse.example --holder "Fuse Architects" --seats 12 ^
    --paid-to 2027-09-28 --eml order.eml
```

- The key runs to `--paid-to`, the last day paid for as the shop dates it,
  plus `--grace-days` (7 by default). Without `--paid-to`, `--months 1` or
  `--months 12` from today (or from `--starts`).
- It gets the next licence number from `licences.csv`, the ledger beside the
  signing key, and is recorded there -- so a lost email is answered by sending
  the same key again, and the ledger says what is out there.
- It is read back exactly as a subscriber's Loriini will read it before
  anything is recorded or sent.
- `--eml` writes the subscriber's email as an **unsent draft**: Outlook and
  Windows Mail open it ready to check and send. `--send` sends it over SMTP
  instead, with the server in `LORIINI_SMTP_HOST`, `LORIINI_SMTP_PORT`,
  `LORIINI_SMTP_USER` and `LORIINI_SMTP_PASSWORD`, and the sender in `--from`
  or `LORIINI_MAIL_FROM`.

The script refuses a signing key that is not the one this checkout's build
trusts, since every key it signed would be refused.

`scripts/licence.py show LORIINI-...` says what a key is and whether it
checks out, for support.

Issuing by hand is the start. The shop's webhook (roadmap R7) is the same
`issue`, called with the paid-through date of each invoice.

## What is checked, and what is not

Checked, at every start: that the key is **whole** (a CRC over it), that it is
**genuine** (an Ed25519 signature by the vendor's private key, checked with
the public key compiled into the build), and that it is **in force** on the
machine's own date. Offline: nothing is sent anywhere, and nothing needs a
server to be up for Loriini to open.

Not checked:

- **Seats** are what the subscriber agreed to, printed on the key and in the
  info box. Offline there is nothing to count them against.
- **Revocation.** A key cannot be withdrawn once issued. For a subscription
  that is the model rather than a gap: a subscription that is not renewed
  lapses when its last key does, a period plus a week later.
- **The clock.** A key is checked against the system date, so winding the
  clock back defeats it -- the same speed bump as the build's own term, and
  said as plainly. Remembering the latest date seen was considered and not
  done: a machine whose clock once jumped a year ahead would lock a paying
  subscriber out, which is worse than what it prevents.

**The build's own term stays as the floor.** A key good until 2028 does not
make a build that ends in 2027 run past its end: the prototype's term
(`licence.EXPIRES`) still stops an old build, whatever key it holds. Set it
per release, far enough ahead of the subscriptions it will serve, or keep the
subscribers on current builds (roadmap R6).

## How the key is written

`LORIINI-` and groups of five characters in Crockford's base 32 -- digits and
capitals without I, L, O or U, read back case-blind, with O taken as 0 and
I or L as 1 -- so a key survives being read aloud, retyped, lower-cased or
wrapped over lines. Inside: a format version, the licence number, the
issue date and the last day, the seats, the email and the holder's name, then
the signature over all of them and a domain tag, then the CRC. About 200
characters; nobody types it, and pasting does not mind.
