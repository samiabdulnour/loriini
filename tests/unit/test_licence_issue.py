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
