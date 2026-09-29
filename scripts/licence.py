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

Online keys and the licence service (D125, docs/licence-service.md)
------------------------------------------------------------------
Once the licence service runs, it is the issuer and the ledger: it holds the
signing key, numbers every licence, and keeps them. These commands talk to it,
at ``LORIINI_LICENCE_SERVICE`` or the build's own ``SERVICE``, with the admin
token in ``LORIINI_ADMIN_TOKEN`` -- an environment variable, never an
argument, so that it stays out of the shell's history::

    service https://licence.example.com.au     the build's service, once
    issue --email ... --online --send          an online key, through the service
    issue --email ... --trial --send           a fortnight's trial
    issue --email ... --complimentary          never lapses (the first practice)
    status [0042]                              every licence, or one in full
    paid 0042 --to 2026-10-31                  a payment by invoice
    seats 0042 12
    withdraw 0042 --reason "refunded"          and restore 0042
    free 0042 "jsmith on FUSE-PC-07"           a seat, from the vendor's side
    send 0042                                  the key's email, again
    recall --below 1.2.1 --reason "..."        and recall --clear
    notice "..."                               said on every lease; --clear
    set portal=https://billing.stripe.com/...  settings: portal, download, ...
    register --ledger licences.csv             keys issued before the service
    backup --out licences-2026-09-29.sqlite3

``issue`` with ``--signing-key`` still signs on this machine, as before the
service; without it, it asks the service.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sun_study import (
    licence,
    licence_issue,
    licence_key,
    licence_online,
    licence_public_key,
    signing,
)


def _keygen(arguments: argparse.Namespace) -> int:
    private = Path(arguments.out).expanduser()
    try:
        public = licence_issue.new_key_pair(private, force=arguments.force)
    except FileExistsError as exists:
        print(exists, file=sys.stderr)
        return 1
    module = Path(arguments.module)
    module.write_text(
        licence_issue.public_key_module(public, licence_public_key.SERVICE), encoding="utf-8"
    )
    print(f"Private key: {private} -- keep it out of every repository, and back it up.")
    print(f"Public key:  {public.hex()}")
    print(f"Written into {module}. Commit that file; the next build asks for a licence key.")
    return 0


def _order(arguments: argparse.Namespace) -> licence_issue.Order:
    return licence_issue.Order(
        email=arguments.email,
        holder=arguments.holder,
        seats=arguments.seats,
        months=arguments.months,
        starts=dt.date.fromisoformat(arguments.starts) if arguments.starts else None,
        paid_to=dt.date.fromisoformat(arguments.paid_to) if arguments.paid_to else None,
        grace_days=arguments.grace_days,
        online=arguments.online,
        trial=arguments.trial,
        days=arguments.days,
        complimentary=arguments.complimentary,
    )


def _issue(arguments: argparse.Namespace) -> int:
    if not arguments.signing_key:
        return _issue_through_service(arguments)
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
    issued, text = licence_issue.issue(_order(arguments), seed, serial=serial)
    # Read back exactly as a buyer's Loriini will read it, before anything is
    # recorded or sent.
    if licence_key.read(text, trusted) != issued:
        print("The key did not read back as issued; nothing was recorded.", file=sys.stderr)
        return 1
    licence_issue.record(ledger, issued, text)

    print(f"Issued {issued.describe()}.")
    print("\n".join(licence_key.lines(text)))
    print(f"Recorded in {ledger}.")
    return _deliver(arguments, issued, text)


def _deliver(arguments: argparse.Namespace, issued: licence_key.LicenceKey, text: str) -> int:
    """The email of a key issued here: a draft to check and send, or sent."""
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


# -- the licence service ------------------------------------------------------------


class _UnansweredError(Exception):
    """The service could not be asked, or refused; the sentence says which."""


def _service_url(arguments: argparse.Namespace) -> str:
    found = getattr(arguments, "service", None) or licence_online.service()
    if not found:
        raise _UnansweredError(
            "No licence service: set LORIINI_LICENCE_SERVICE, or run "
            "scripts/licence.py service <address> first."
        )
    return str(found)


def _ask(
    arguments: argparse.Namespace, method: str, path: str, body: dict[str, Any] | None = None
) -> Any:
    """One request to the service's admin side, answered as JSON (or bytes,
    for the backup)."""
    token = os.environ.get("LORIINI_ADMIN_TOKEN", "")
    if not token:
        raise _UnansweredError("Set LORIINI_ADMIN_TOKEN to the service's admin token.")
    request = urllib.request.Request(
        _service_url(arguments).rstrip("/") + "/v1/admin/" + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
            kind = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        try:
            said = json.loads(error.read()).get("error") or error.reason
        except (ValueError, AttributeError):
            said = error.reason
        raise _UnansweredError(f"The licence service said: {said}") from error
    except (urllib.error.URLError, OSError) as error:
        raise _UnansweredError(f"The licence service could not be reached: {error}") from error
    return json.loads(data) if kind.startswith("application/json") else data


def _day(text: str | None) -> str:
    if not text:
        return "no end"
    when = dt.date.fromisoformat(text)
    return f"{when.day} {when:%B %Y}"


def _line(summary: dict[str, Any]) -> str:
    kind = "trial" if summary["trial"] else "online" if summary["online"] else "offline"
    state = f"withdrawn ({summary['withdrawn']})" if summary["withdrawn"] is not None else ""
    if summary["payment_failed"]:
        state = f"payment failed {summary['payment_failed']}"
    return (
        f"{summary['number']}  {(summary['holder'] or summary['email'])[:32]:<32}  "
        f"{summary['seats']:>3} seats  {summary.get('in_use', 0):>3} in use  "
        f"paid to {summary['paid_to'] or 'no end':<10}  {kind:<7}  {state}"
    ).rstrip()


def _issue_through_service(arguments: argparse.Namespace) -> int:
    order = _order(arguments)
    body = {
        "email": order.email,
        "holder": order.holder,
        "seats": order.seats,
        "months": order.months,
        "starts": order.starts.isoformat() if order.starts else None,
        "paid_to": order.paid_to.isoformat() if order.paid_to else None,
        "grace_days": order.grace_days,
        "offline": not (order.online or order.trial or order.complimentary),
        "trial": order.trial,
        "days": order.days,
        "complimentary": order.complimentary,
        "send": arguments.send,
    }
    answer = _ask(arguments, "POST", "licences", body)
    text = answer["key"]
    trusted = licence.public_key()
    issued = licence_key.read(text, trusted) if trusted else None
    print(f"Issued {issued.describe() if issued else 'licence ' + answer['licence']['number']}.")
    print("\n".join(licence_key.lines(text)))
    if arguments.send:
        print("Emailed by the service." if answer["sent"] else "The service could not email it.")
    if arguments.eml and issued is not None:
        sender = arguments.sender or os.environ.get("LORIINI_MAIL_FROM", "")
        draft = Path(arguments.eml).expanduser()
        draft.write_bytes(licence_issue.draft(licence_issue.email(issued, text, sender=sender)))
        print(f"The email is in {draft}: open it, check it, and press Send.")
    return 0


def _status(arguments: argparse.Namespace) -> int:
    if arguments.number is None:
        for summary in _ask(arguments, "GET", "licences")["licences"]:
            print(_line(summary))
        return 0
    detail = _ask(arguments, "GET", f"licences/{arguments.number}")
    summary = detail["licence"]
    print(_line(summary))
    print(f"  {summary['email']}; issued {summary['issued'] or 'before the service'}")
    if summary["subscription"]:
        print(f"  Stripe: {summary['subscription']} ({summary['customer'] or 'no customer'})")
    print(
        f"  Leases run to {_day(summary['good_to'])} "
        f"({summary['grace_days']} days' grace past what is paid)."
    )
    if summary["note"]:
        print(f"  Note: {summary['note']}")
    print("Computers:")
    for computer in detail["computers"]:
        state = "in use" if computer["in_use"] else "freed" if computer["freed"] else "idle"
        print(
            f"  {computer['name'] or computer['machine']:<40}  {computer['build']:<8}  "
            f"last seen {computer['last_seen']}  {state}"
        )
    print("Recent:")
    for event in detail["events"][:15]:
        print(f"  {event['at']}  {event['what']}")
    print("Key:")
    print("\n".join(f"  {line}" for line in licence_key.lines(detail["key"])))
    return 0


def _change(arguments: argparse.Namespace, body: dict[str, Any]) -> int:
    answer = _ask(arguments, "POST", f"licences/{arguments.number}", body)
    print(_line(answer["licence"]))
    return 0


def _paid(arguments: argparse.Namespace) -> int:
    return _change(arguments, {"paid_to": dt.date.fromisoformat(arguments.to).isoformat()})


def _seats(arguments: argparse.Namespace) -> int:
    return _change(arguments, {"seats": arguments.seats})


def _withdraw(arguments: argparse.Namespace) -> int:
    return _change(arguments, {"withdraw": arguments.reason})


def _restore(arguments: argparse.Namespace) -> int:
    return _change(arguments, {"restore": True})


def _free(arguments: argparse.Namespace) -> int:
    answer = _ask(
        arguments, "POST", f"licences/{arguments.number}/free", {"computer": arguments.computer}
    )
    print(f"Freed {answer['freed']} seat{'s' if answer['freed'] != 1 else ''}.")
    return 0 if answer["freed"] else 1


def _send(arguments: argparse.Namespace) -> int:
    answer = _ask(arguments, "POST", f"licences/{arguments.number}/send", {})
    print("Emailed." if answer["sent"] else "The service could not email it; `status` says why.")
    return 0 if answer["sent"] else 1


def _settings(arguments: argparse.Namespace, body: dict[str, Any]) -> int:
    answer = _ask(arguments, "POST" if body else "GET", "settings", body or None)
    for name, value in sorted(answer["settings"].items()):
        print(f"{name} = {value}")
    return 0


def _recall(arguments: argparse.Namespace) -> int:
    if arguments.clear:
        return _settings(arguments, {"minimum_build": None, "recall_reason": None})
    if not arguments.below:
        raise _UnansweredError("Say which versions: recall --below 1.2.1, or recall --clear.")
    body = {"minimum_build": arguments.below, "recall_reason": arguments.reason}
    if arguments.download:
        body["download"] = arguments.download
    return _settings(arguments, body)


def _notice(arguments: argparse.Namespace) -> int:
    return _settings(arguments, {"notice": None if arguments.clear else " ".join(arguments.text)})


def _set(arguments: argparse.Namespace) -> int:
    body: dict[str, Any] = {}
    for pair in arguments.pairs:
        name, _, value = pair.partition("=")
        body[name.strip()] = value.strip() or None
    return _settings(arguments, body)


def _register(arguments: argparse.Namespace) -> int:
    keys = [" ".join(arguments.key)] if arguments.key else []
    if arguments.ledger:
        with Path(arguments.ledger).expanduser().open(newline="", encoding="utf-8") as opened:
            keys += [row["key"] for row in csv.DictReader(opened) if row.get("key")]
    if not keys:
        raise _UnansweredError("Give a key, or --ledger with the licences.csv to take in.")
    for text in keys:
        answer = _ask(arguments, "POST", "register", {"key": text})
        print(_line(answer["licence"]))
    return 0


def _backup(arguments: argparse.Namespace) -> int:
    data = _ask(arguments, "GET", "backup")
    out = Path(arguments.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"Backed up to {out} ({len(data):,} bytes).")
    return 0


def _service(arguments: argparse.Namespace) -> int:
    address = arguments.address.rstrip("/")
    local = address.startswith(("http://localhost", "http://127.0.0.1"))
    if not (address.startswith("https://") or local):
        print(
            "The service's address starts https:// -- the lease travels over it.", file=sys.stderr
        )
        return 1
    module = Path(arguments.module)
    public = licence.public_key()
    module.write_text(licence_issue.public_key_module(public, address), encoding="utf-8")
    print(f"Written into {module}: builds from this checkout renew online keys at {address}.")
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
    issue.add_argument(
        "--signing-key",
        help="The private key file, to sign here; without it, the licence service issues.",
    )
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
    issue.add_argument(
        "--online", action="store_true", help="An online key, kept in force by the service."
    )
    issue.add_argument("--trial", action="store_true", help="A trial, online, for --days days.")
    issue.add_argument("--days", type=int, default=licence_issue.TRIAL_DAYS, help="A trial's days.")
    issue.add_argument("--complimentary", action="store_true", help="Online, and never lapsing.")
    issue.add_argument("--service", help="The licence service; the build's own otherwise.")
    issue.set_defaults(run=_issue)

    def service_command(name: str, text: str) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=text)
        command.add_argument("--service", help="The licence service; the build's own otherwise.")
        return command

    status = service_command("status", "Every licence, or one in full.")
    status.add_argument("number", nargs="?", type=int, help="A licence number.")
    status.set_defaults(run=_status)
    paid = service_command("paid", "Record a payment: the licence is paid to a day.")
    paid.add_argument("number", type=int)
    paid.add_argument("--to", required=True, help="The last day paid for, YYYY-MM-DD.")
    paid.set_defaults(run=_paid)
    seats = service_command("seats", "Change a licence's seats.")
    seats.add_argument("number", type=int)
    seats.add_argument("seats", type=int)
    seats.set_defaults(run=_seats)
    withdraw = service_command("withdraw", "Withdraw a licence, with the reason Loriini says.")
    withdraw.add_argument("number", type=int)
    withdraw.add_argument("--reason", required=True)
    withdraw.set_defaults(run=_withdraw)
    restore = service_command("restore", "Undo a withdrawal.")
    restore.add_argument("number", type=int)
    restore.set_defaults(run=_restore)
    free = service_command("free", "Free a computer's seat: its name, or its hash.")
    free.add_argument("number", type=int)
    free.add_argument("computer")
    free.set_defaults(run=_free)
    send = service_command("send", "Email a licence its key again.")
    send.add_argument("number", type=int)
    send.set_defaults(run=_send)
    recall = service_command("recall", "Stop the versions below one, with the reason.")
    recall.add_argument("--below", help="The first version that is not recalled.")
    recall.add_argument("--reason", default="", help="Why, as Loriini will say it.")
    recall.add_argument("--download", help="Where the current version is.")
    recall.add_argument("--clear", action="store_true", help="Recall nothing.")
    recall.set_defaults(run=_recall)
    notice = service_command("notice", "A sentence every lease carries, or --clear.")
    notice.add_argument("text", nargs="*")
    notice.add_argument("--clear", action="store_true")
    notice.set_defaults(run=_notice)
    settings = service_command("set", "The service's settings: name=value, or none to list.")
    settings.add_argument("pairs", nargs="*", help="portal=..., download=..., serial_floor=...")
    settings.set_defaults(run=_set)
    register = service_command("register", "Take in keys issued before the service ran.")
    register.add_argument("key", nargs="*", help="A key, pasted whole.")
    register.add_argument("--ledger", help="The licences.csv to take in, every key in it.")
    register.set_defaults(run=_register)
    backup = service_command("backup", "Copy the service's database here.")
    backup.add_argument("--out", required=True, help="The file to write.")
    backup.set_defaults(run=_backup)

    service = commands.add_parser("service", help="Set the build's licence service address.")
    service.add_argument("address", help="https://...")
    service.add_argument(
        "--module",
        default=str(licence_issue.PUBLIC_KEY_MODULE),
        help="Where it is written (the build's own module by default).",
    )
    service.set_defaults(run=_service)

    show = commands.add_parser("show", help="What a key says, and whether it checks out.")
    show.add_argument("key", nargs="+", help="The key, pasted whole.")
    show.set_defaults(run=_show)

    arguments = parser.parse_args(argv)
    try:
        return int(arguments.run(arguments))
    except _UnansweredError as unanswered:
        print(unanswered, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
