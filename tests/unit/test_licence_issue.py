"""Issuing licence keys: the key pair, a key from an order, the ledger, the email.

The vendor's side of roadmap R5 (D124), run on the vendor's machine and never
inside Loriini -- but a key it gets wrong is a buyer who cannot start the
program, so it is tested like the rest. The script's commands run end to
end here, in a temporary folder, against a build told to trust the key pair
they make.
"""

from __future__ import annotations

import datetime as dt
import email
import importlib.util
from email import policy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from sun_study import licence, licence_issue, licence_key, licence_public_key, signing

ROOT = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("licence_script", ROOT / "scripts" / "licence.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- terms and numbers -------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "months", "last"),
    [
        (dt.date(2026, 9, 29), 12, dt.date(2027, 9, 28)),
        (dt.date(2026, 1, 1), 12, dt.date(2026, 12, 31)),
        (dt.date(2026, 1, 31), 1, dt.date(2026, 2, 27)),
        (dt.date(2028, 1, 31), 1, dt.date(2028, 2, 28)),  # a leap year
        (dt.date(2026, 11, 15), 3, dt.date(2027, 2, 14)),
    ],
)
def test_a_term_ends_the_day_before_its_anniversary(
    start: dt.date, months: int, last: dt.date
) -> None:
    assert licence_issue.term_end(start, months) == last


def test_licence_numbers_follow_on_from_the_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "licences.csv"
    seed = bytes(range(32))
    assert licence_issue.next_serial(ledger) == 1

    for serial in (1, 2, 7):
        issued, text = licence_issue.issue(
            licence_issue.Order(email=f"buyer{serial}@example.com"),
            seed,
            serial=serial,
            today=dt.date(2026, 9, 29),
        )
        licence_issue.record(ledger, issued, text)

    assert licence_issue.next_serial(ledger) == 8
    rows = ledger.read_text(encoding="utf-8").splitlines()
    assert rows[0] == ",".join(licence_issue.LEDGER_FIELDS)
    # A year from 29 September, and a week's grace after it.
    assert rows[3].startswith("0007,2026-09-29,2027-10-05,1,buyer7@example.com,,LORIINI-")


def test_a_key_runs_to_the_last_day_paid_for_and_a_week_after() -> None:
    """A subscription's key is its paid period, as the shop dates it, plus the
    grace that lets a late renewal email arrive without stopping anybody."""
    seed = bytes(range(32))
    monthly = licence_issue.Order(email="a@b.example", paid_to=dt.date(2026, 10, 31))
    issued, _text = licence_issue.issue(monthly, seed, serial=1, today=dt.date(2026, 10, 1))
    assert issued.expires == dt.date(2026, 11, 7)

    exact = licence_issue.Order(email="a@b.example", months=1, grace_days=0)
    issued, _text = licence_issue.issue(exact, seed, serial=2, today=dt.date(2026, 10, 1))
    assert issued.expires == dt.date(2026, 10, 31)

    with pytest.raises(ValueError, match="grace"):
        licence_issue.issue(licence_issue.Order(email="a@b.example", grace_days=-1), seed, serial=3)


# -- the key pair ---------------------------------------------------------------------


def test_a_key_pair_keeps_its_private_half_and_will_not_be_replaced_by_accident(
    tmp_path: Path,
) -> None:
    private = tmp_path / "keys" / "signing.key"

    public = licence_issue.new_key_pair(private)

    seed = licence_issue.read_signing_key(private)
    assert signing.public_key(seed) == public
    assert private.read_text(encoding="utf-8").startswith("# Loriini licence signing key")
    with pytest.raises(FileExistsError, match="--force"):
        licence_issue.new_key_pair(private)
    assert licence_issue.new_key_pair(private, force=True) != public


def test_the_public_key_module_is_what_a_build_imports(tmp_path: Path) -> None:
    public = signing.public_key(bytes(range(32)))
    written = licence_issue.public_key_module(public)
    namespace: dict[str, Any] = {}
    exec(compile(written, "licence_public_key.py", "exec"), namespace)
    assert namespace["PUBLIC_KEY"] == public.hex()


# -- the email ------------------------------------------------------------------------


def _key_lines(text: str) -> str:
    """The lines of a key as they were set, out of a body of other text."""
    return "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and set(line.strip()) <= set(licence_key.ALPHABET + "-LORIIN")
    )


def _order_and_key() -> tuple[licence_key.LicenceKey, str]:
    return licence_issue.issue(
        licence_issue.Order(email="office@fuse.example", holder="Fuse Architects", seats=12),
        bytes(range(32)),
        serial=42,
        today=dt.date(2026, 9, 29),
    )


def test_the_email_carries_the_key_whole_and_says_how_to_install_it() -> None:
    issued, text = _order_and_key()

    message = licence_issue.email(issued, text, sender="sami@example.com")

    assert message["To"] == "office@fuse.example"
    assert message["Subject"] == "Your Loriini licence key (licence 0042)"
    body = message.get_content()
    assert "Hello Fuse Architects," in body
    assert "licence 0042, for 12 people, and it works until 5 October 2027" in body
    assert "a new key comes by email before this" in body
    assert "Loriini.exe licence <the key>" in body
    # The key as set in the email reads back as the key, line breaks and all.
    public = signing.public_key(bytes(range(32)))
    assert licence_key.read(_key_lines(body), public) == issued


def test_the_draft_opens_as_an_unsent_message() -> None:
    issued, text = _order_and_key()
    message = licence_issue.email(issued, text, sender="sami@example.com")

    raw = licence_issue.draft(message)
    reopened = email.message_from_bytes(raw, policy=policy.default)

    assert reopened["X-Unsent"] == "1"
    assert reopened["To"] == "office@fuse.example"
    assert "X-Unsent" not in message, "the message itself is left as it was"


def test_sending_upgrades_to_tls_before_the_password(monkeypatch: pytest.MonkeyPatch) -> None:
    issued, text = _order_and_key()
    message = licence_issue.email(issued, text, sender="sami@example.com")
    said: list[tuple[str, Any]] = []

    class Server:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            said.append(("connect", (host, port)))

        def __enter__(self) -> Server:
            return self

        def __exit__(self, *exc: object) -> None:
            said.append(("quit", None))

        def starttls(self) -> None:
            said.append(("starttls", None))

        def login(self, user: str, password: str) -> None:
            said.append(("login", user))

        def send_message(self, sent: object) -> None:
            said.append(("send", sent))

    licence_issue.send(
        message, host="smtp.example.com", user="sami", password="secret", connect=Server
    )

    assert [step for step, _ in said] == ["connect", "starttls", "login", "send", "quit"]
    assert said[0][1] == ("smtp.example.com", 587)


# -- the script, end to end -------------------------------------------------------------


def test_keygen_then_issue_makes_a_key_the_build_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    private = tmp_path / "private" / "signing.key"
    module = tmp_path / "licence_public_key.py"

    assert script.main(["keygen", "--out", str(private), "--module", str(module)]) == 0
    namespace: dict[str, Any] = {}
    exec(module.read_text(encoding="utf-8"), namespace)
    monkeypatch.setattr(licence_public_key, "PUBLIC_KEY", namespace["PUBLIC_KEY"])
    capsys.readouterr()

    draft = tmp_path / "order.eml"
    code = script.main(
        [
            "issue",
            "--signing-key",
            str(private),
            "--email",
            "office@fuse.example",
            "--holder",
            "Fuse Architects",
            "--seats",
            "12",
            "--eml",
            str(draft),
            "--from",
            "sami@example.com",
        ]
    )
    said = capsys.readouterr().out

    assert code == 0, said
    assert "Issued licence 0001, Fuse Architects (office@fuse.example), 12 seats" in said
    assert (private.parent / "licences.csv").is_file()
    assert b"X-Unsent: 1" in draft.read_bytes()

    # The key the buyer receives installs as their Loriini will install it,
    # pasted out of the email, line breaks and all.
    body = email.message_from_bytes(draft.read_bytes(), policy=policy.default)
    content = body.get_body()
    assert content is not None
    monkeypatch.setenv("APPDATA", str(tmp_path / "buyer"))
    installed = licence.install(_key_lines(content.get_content()))
    assert installed.serial == 1
    assert installed.holder == "Fuse Architects"
    # And the next order gets the next number.
    assert licence_issue.next_serial(private.parent / "licences.csv") == 2


def test_issuing_with_a_key_the_build_does_not_trust_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    private = tmp_path / "signing.key"
    licence_issue.new_key_pair(private)
    monkeypatch.setattr(
        licence_public_key, "PUBLIC_KEY", signing.public_key(bytes(range(32))).hex()
    )

    code = script.main(["issue", "--signing-key", str(private), "--email", "a@b.example"])

    assert code == 1
    assert "not the key this checkout's build trusts" in capsys.readouterr().err
    assert not (tmp_path / "licences.csv").exists(), "nothing recorded"


def test_show_says_what_a_key_is_for_support(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    seed = bytes(range(32))
    monkeypatch.setattr(licence_public_key, "PUBLIC_KEY", signing.public_key(seed).hex())
    _issued, text = _order_and_key()

    assert script.main(["show", *licence_key.lines(text)]) == 0
    assert "licence 0042, Fuse Architects" in capsys.readouterr().out
    assert script.main(["show", text[:-5]]) == 1
    assert "not the whole key" in capsys.readouterr().out


# -- online keys, and the licence service (D125) --------------------------------------------


@pytest.mark.parametrize(
    ("order", "last", "online", "trial"),
    [
        ({"paid_to": dt.date(2026, 10, 31)}, dt.date(2026, 11, 7), False, False),
        ({"paid_to": dt.date(2026, 10, 31), "online": True}, dt.date(2026, 10, 31), True, False),
        ({"trial": True}, dt.date(2026, 10, 12), True, True),
        ({"trial": True, "days": 30}, dt.date(2026, 10, 28), True, True),
        ({"complimentary": True}, licence_issue.NO_END, True, False),
    ],
)
def test_each_kind_of_key_ends_where_its_kind_says(
    order: dict[str, Any], last: dt.date, online: bool, trial: bool
) -> None:
    """Offline: the period and the grace. Online: the period alone, where the
    service starts from. A trial: its last day. Complimentary: no end."""
    issued, text = licence_issue.issue(
        licence_issue.Order(email="a@b.example", **order),
        bytes(range(32)),
        serial=1,
        today=dt.date(2026, 9, 29),
    )
    assert (issued.expires, issued.online, issued.trial) == (last, online, trial)
    public = signing.public_key(bytes(range(32)))
    assert licence_key.read(text, public) == issued


def test_an_online_keys_email_says_there_is_no_new_key_to_come() -> None:
    issued, text = licence_issue.issue(
        licence_issue.Order(email="office@fuse.example", holder="Fuse", online=True),
        bytes(range(32)),
        serial=5,
        today=dt.date(2026, 9, 29),
    )
    body = licence_issue.email(issued, text, sender="sami@example.com").get_content()
    assert "for as long as the subscription runs" in body
    assert "there is no new key" in body
    assert "a new key comes by email" not in body


def _vendor(monkeypatch: pytest.MonkeyPatch, running: Any, *arguments: str) -> tuple[int, str, str]:
    """The vendor's script, run against the service with its admin token."""
    from tests.unit.licence_service_helpers import TOKEN

    monkeypatch.setenv("LORIINI_ADMIN_TOKEN", TOKEN)
    capsys = running.capsys
    code = _script().main(list(arguments))
    said = capsys.readouterr()
    return code, said.out, said.err


@pytest.fixture
def served(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> Any:
    from tests.unit.licence_service_helpers import online

    with online(monkeypatch, tmp_path, mail=True) as running:
        running.capsys = capsys  # type: ignore[attr-defined]
        yield running


def test_the_vendor_issues_through_the_service_and_looks_it_up(
    served: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A day ahead of whatever today is: a key cannot end before it is issued,
    # and a day written out here went past on 1 November 2026.
    paid_to = dt.date.today() + dt.timedelta(days=30)
    grace = paid_to + dt.timedelta(days=14)
    draft = tmp_path / "welcome.eml"
    code, out, err = _vendor(
        monkeypatch,
        served,
        "issue",
        "--email",
        "office@fuse.example",
        "--holder",
        "Fuse Architects",
        "--seats",
        "12",
        "--online",
        "--paid-to",
        paid_to.isoformat(),
        "--send",
        "--eml",
        str(draft),
    )
    assert code == 0, err
    assert (
        "Issued licence 0001, Fuse Architects (office@fuse.example), 12 seats, renewed online."
        in out
    )
    assert "Emailed by the service." in out
    assert len(served.sent) == 1
    assert b"X-Unsent: 1" in draft.read_bytes()

    code, out, _err = _vendor(monkeypatch, served, "status")
    assert code == 0
    assert out.startswith("0001  Fuse Architects")
    assert "12 seats" in out and f"paid to {paid_to.isoformat()}" in out

    code, out, _err = _vendor(monkeypatch, served, "status", "1")
    assert f"Leases run to {grace.day} {grace:%B %Y} (14 days' grace past what is paid)." in out
    assert "Key:" in out and "LORIINI-" in out


def test_the_vendor_changes_withdraws_restores_and_frees(
    served: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    served.issue(seats=2)
    served.store.seen(1, "ab" * 16, "amy on PC-1", "1.0", dt.date.today())
    later = (dt.date.today() + dt.timedelta(days=60)).isoformat()
    assert (
        _vendor(monkeypatch, served, "paid", "1", "--to", later)[1].count(f"paid to {later}") == 1
    )
    assert " 5 seats" in _vendor(monkeypatch, served, "seats", "1", "5")[1]
    assert (
        "withdrawn (refunded)"
        in _vendor(monkeypatch, served, "withdraw", "1", "--reason", "refunded")[1]
    )
    assert "withdrawn" not in _vendor(monkeypatch, served, "restore", "1")[1]
    assert _vendor(monkeypatch, served, "free", "1", "amy on PC-1")[1] == "Freed 1 seat.\n"
    assert _vendor(monkeypatch, served, "free", "1", "nobody")[0] == 1
    assert _vendor(monkeypatch, served, "send", "1")[1] == "Emailed.\n"


def test_the_vendor_recalls_a_version_and_speaks_to_everyone(
    served: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, _err = _vendor(
        monkeypatch,
        served,
        "recall",
        "--below",
        "1.2.1",
        "--reason",
        "wrong north",
        "--download",
        "https://loriini.example/download",
    )
    assert code == 0
    assert "minimum_build = 1.2.1" in out and "recall_reason = wrong north" in out
    assert (
        "notice = Loriini 1.3 is out."
        in _vendor(monkeypatch, served, "notice", "Loriini", "1.3", "is", "out.")[1]
    )
    assert (
        "portal = https://billing.example/p"
        in _vendor(monkeypatch, served, "set", "portal=https://billing.example/p")[1]
    )
    out = _vendor(monkeypatch, served, "recall", "--clear")[1]
    assert "minimum_build" not in out
    assert served.store.settings()["notice"] == "Loriini 1.3 is out."


def test_the_old_ledger_is_taken_in_and_the_numbers_follow_on(
    served: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ledger = tmp_path / "licences.csv"
    for serial in (1, 2, 9):
        issued, text = licence_issue.issue(
            licence_issue.Order(email=f"buyer{serial}@example.com"), bytes(range(32)), serial=serial
        )
        licence_issue.record(ledger, issued, text)
    code, out, err = _vendor(monkeypatch, served, "register", "--ledger", str(ledger))
    assert code == 0, err
    assert [line[:4] for line in out.splitlines()] == ["0001", "0002", "0009"]
    assert served.issue().serial == 10


def test_the_vendor_backs_the_service_up(
    served: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sqlite3

    served.issue()
    out = tmp_path / "backups" / "licences.sqlite3"
    code, said, _err = _vendor(monkeypatch, served, "backup", "--out", str(out))
    assert code == 0 and "Backed up to" in said
    copy = sqlite3.connect(out)
    assert copy.execute("SELECT COUNT(*) FROM licences").fetchone() == (1,)
    copy.close()


def test_the_script_says_what_is_missing_to_reach_the_service(
    served: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LORIINI_ADMIN_TOKEN", raising=False)
    assert _script().main(["status"]) == 1
    assert "LORIINI_ADMIN_TOKEN" in served.capsys.readouterr().err
    monkeypatch.setenv("LORIINI_ADMIN_TOKEN", "wrong")
    assert _script().main(["status"]) == 1
    assert "not this service's admin token" in served.capsys.readouterr().err


def test_the_service_address_is_written_into_the_build_beside_its_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    module = tmp_path / "licence_public_key.py"
    public = signing.public_key(bytes(range(32)))
    monkeypatch.setattr(licence_public_key, "PUBLIC_KEY", public.hex())
    assert script.main(["service", "http://licence.example", "--module", str(module)]) == 1
    assert "https://" in capsys.readouterr().err
    assert script.main(["service", "https://licence.example/", "--module", str(module)]) == 0
    namespace: dict[str, Any] = {}
    exec(module.read_text(encoding="utf-8"), namespace)
    assert namespace["PUBLIC_KEY"] == public.hex()
    assert namespace["SERVICE"] == "https://licence.example"

    # A new key pair keeps the service the build already has.
    monkeypatch.setattr(licence_public_key, "SERVICE", "https://licence.example")
    assert (
        script.main(
            ["keygen", "--out", str(tmp_path / "k" / "signing.key"), "--module", str(module)]
        )
        == 0
    )
    namespace = {}
    exec(module.read_text(encoding="utf-8"), namespace)
    assert namespace["SERVICE"] == "https://licence.example"
