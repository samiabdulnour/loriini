"""Make Loriini's signing key, and issue licence keys from orders.

The vendor's tool, run on the vendor's own machine (roadmap R5, D124,
docs/licensing.md). Loriini itself only ever checks keys; this is where they
come from.

Once, to make the key pair::

    uv run python scripts/licence.py keygen --out "D:/Private/loriini-signing.key"

The private half goes into that file -- keep it out of every repository and
backed up somewhere safe. The public half is written into
``src/sun_study/licence_public_key.py``; commit that, and the next build asks
for a licence key.

For each paid period of a subscription::

    uv run python scripts/licence.py issue --signing-key "D:/Private/loriini-signing.key" ^
        --email office@practice.com.au --holder "A Practice" --seats 5 ^
        --paid-to 2026-10-31 --eml order.eml

signs a key that runs to the last day paid for plus a week's grace, with the
next licence number, records it in ``licences.csv`` beside the signing key,
and writes the subscriber's email as an unsent draft that Outlook opens ready
to send. ``--months 1`` or ``--months 12`` from today instead of
``--paid-to``, for a period the shop has not dated. ``--send`` sends it over SMTP instead, with the
server in ``LORIINI_SMTP_HOST``, ``LORIINI_SMTP_PORT``, ``LORIINI_SMTP_USER``
and ``LORIINI_SMTP_PASSWORD``.

And for support, what a key says and whether it checks out::

    uv run python scripts/licence.py show LORIINI-...
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from sun_study import licence, licence_issue, licence_key, signing


def _keygen(arguments: argparse.Namespace) -> int:
    private = Path(arguments.out).expanduser()
    try:
        public = licence_issue.new_key_pair(private, force=arguments.force)
    except FileExistsError as exists:
        print(exists, file=sys.stderr)
        return 1
    module = Path(arguments.module)
    module.write_text(licence_issue.public_key_module(public), encoding="utf-8")
    print(f"Private key: {private} -- keep it out of every repository, and back it up.")
    print(f"Public key:  {public.hex()}")
    print(f"Written into {module}. Commit that file; the next build asks for a licence key.")
    return 0


def _issue(arguments: argparse.Namespace) -> int:
    private = Path(arguments.signing_key).expanduser()
    seed = licence_issue.read_signing_key(private)
    trusted = licence.public_key()
    if trusted is None:
        print(
            "This checkout's build takes no licence keys yet: run keygen first, and "
            "commit the public key it writes.",
            file=sys.stderr,
        )
        return 1
    if signing.public_key(seed) != trusted:
        print(
            f"{private} is not the key this checkout's build trusts; a key it signed "
            f"would be refused as not genuine.",
            file=sys.stderr,
        )
        return 1

    ledger = (
        Path(arguments.ledger).expanduser()
        if arguments.ledger
        else private.with_name("licences.csv")
    )
    serial = arguments.serial or licence_issue.next_serial(ledger)
    starts = dt.date.fromisoformat(arguments.starts) if arguments.starts else None
    paid_to = dt.date.fromisoformat(arguments.paid_to) if arguments.paid_to else None
    order = licence_issue.Order(
        email=arguments.email,
        holder=arguments.holder,
        seats=arguments.seats,
        months=arguments.months,
        starts=starts,
        paid_to=paid_to,
        grace_days=arguments.grace_days,
    )
    issued, text = licence_issue.issue(order, seed, serial=serial)
    # Read back exactly as a buyer's Loriini will read it, before anything is
    # recorded or sent.
    if licence_key.read(text, trusted) != issued:
        print("The key did not read back as issued; nothing was recorded.", file=sys.stderr)
        return 1
    licence_issue.record(ledger, issued, text)

    print(f"Issued {issued.describe()}.")
    print("\n".join(licence_key.lines(text)))
    print(f"Recorded in {ledger}.")

    sender = arguments.sender or os.environ.get("LORIINI_MAIL_FROM", "")
    message = licence_issue.email(issued, text, sender=sender)
    if arguments.eml:
        draft = Path(arguments.eml).expanduser()
        draft.write_bytes(licence_issue.draft(message))
        print(f"The email is in {draft}: open it, check it, and press Send.")
    if arguments.send:
        host = os.environ.get("LORIINI_SMTP_HOST")
        if not host or not sender:
            print(
                "--send needs LORIINI_SMTP_HOST and a sender (--from or LORIINI_MAIL_FROM).",
                file=sys.stderr,
            )
            return 1
        licence_issue.send(
            message,
            host=host,
            port=int(os.environ.get("LORIINI_SMTP_PORT", "587")),
            user=os.environ.get("LORIINI_SMTP_USER"),
            password=os.environ.get("LORIINI_SMTP_PASSWORD"),
        )
        print(f"Sent to {issued.email}.")
    return 0


def _show(arguments: argparse.Namespace) -> int:
    trusted = licence.public_key()
    if trusted is None:
        print("This checkout's build takes no licence keys, so none can be checked.")
        return 1
    try:
        shown = licence_key.read(" ".join(arguments.key), trusted)
    except licence_key.KeyRefusedError as refused:
        print(refused)
        return 1
    state = "in force" if shown.good_on(dt.date.today()) else "past its last day"
    print(f"{shown.describe()}; issued {shown.issued.isoformat()}; {state}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("keygen", help="Make the signing key pair, once.")
    keygen.add_argument("--out", required=True, help="The private key file to write.")
    keygen.add_argument("--force", action="store_true", help="Replace an existing key.")
    keygen.add_argument(
        "--module",
        default=str(licence_issue.PUBLIC_KEY_MODULE),
        help="Where the public key is written (the build's own module by default).",
    )
    keygen.set_defaults(run=_keygen)

    issue = commands.add_parser("issue", help="Sign a key for an order, record it, email it.")
    issue.add_argument("--signing-key", required=True, help="The private key file.")
    issue.add_argument("--email", required=True, help="The buyer's email address.")
    issue.add_argument("--holder", default="", help="The person or practice licensed.")
    issue.add_argument("--seats", type=int, default=1, help="People licensed to use it.")
    issue.add_argument(
        "--months", type=int, default=12, help="The period paid for, when --paid-to is not given."
    )
    issue.add_argument("--paid-to", help="The last day paid for, YYYY-MM-DD, as the shop says it.")
    issue.add_argument(
        "--grace-days",
        type=int,
        default=licence_issue.GRACE_DAYS,
        help="Days the key runs past the period, so a late renewal stops nobody.",
    )
    issue.add_argument("--starts", help="The first day, YYYY-MM-DD; today otherwise.")
    issue.add_argument("--serial", type=int, help="The licence number; the next one otherwise.")
    issue.add_argument("--ledger", help="The ledger; licences.csv beside the key otherwise.")
    issue.add_argument("--eml", help="Write the email here as an unsent draft.")
    issue.add_argument("--send", action="store_true", help="Send the email over SMTP.")
    issue.add_argument("--from", dest="sender", help="The sender's address.")
    issue.set_defaults(run=_issue)

    show = commands.add_parser("show", help="What a key says, and whether it checks out.")
    show.add_argument("key", nargs="+", help="The key, pasted whole.")
    show.set_defaults(run=_show)

    arguments = parser.parse_args(argv)
    return int(arguments.run(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
