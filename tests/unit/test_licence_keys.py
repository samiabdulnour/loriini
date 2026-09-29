"""Licence keys: written for a person, read back whatever was done to them,
and refused in a sentence that says what to do.

Roadmap R5 (D124). The keys here are signed with a test key pair made from a
fixed seed -- never the product's, whose private half is not in this
repository -- and the build is told to trust it by setting its public key for
the test, which is exactly the one line that differs between a build that
takes keys and one that does not.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sun_study import licence, licence_key, licence_public_key, signing
from sun_study.cli import app
from sun_study.licence_key import (
    KeyExpiredError,
    KeyIncompleteError,
    KeyNotGenuineError,
    KeyRefusedError,
    KeyTooNewError,
    LicenceKey,
)

SEED = bytes(range(32))
PUBLIC = signing.public_key(SEED)
OTHER_SEED = bytes(range(1, 33))

TODAY = dt.date(2026, 9, 29)
FUSE = LicenceKey(
    serial=42,
    email="office@fuse.example",
    holder="Fuse Architects",
    seats=12,
    issued=TODAY,
    expires=dt.date(2027, 9, 28),
)


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A build that takes keys signed with the test pair, and a user folder
    of its own. Returns where the key will be kept."""
    monkeypatch.setattr(licence_public_key, "PUBLIC_KEY", PUBLIC.hex())
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path / "Loriini" / licence.KEY_FILE


# -- the key itself --------------------------------------------------------------


def test_a_key_reads_back_as_what_was_signed() -> None:
    text = licence_key.make(FUSE, SEED)

    assert text.startswith("LORIINI-")
    assert all(len(group) == 5 for group in text.split("-")[1:-1])
    assert licence_key.read(text, PUBLIC) == FUSE
    assert FUSE.describe() == (
        "licence 0042, Fuse Architects (office@fuse.example), 12 seats, until 28 September 2027"
    )


def test_a_key_survives_what_mail_and_people_do_to_it() -> None:
    """Lower case, line breaks, spaces, no dashes, and the letters people
    type for the digits they look like."""
    text = licence_key.make(FUSE, SEED)
    wrapped = "\n".join(licence_key.lines(text))
    assert len(licence_key.lines(text)) > 3

    for pasted in (
        wrapped,
        text.lower(),
        "  " + text.replace("-", " ") + "\n",
        text.replace("-", ""),
        text.replace("0", "O").replace("1", "l"),
    ):
        assert licence_key.read(pasted, PUBLIC) == FUSE, pasted[:30]
    assert licence_key.tidy(text.lower().replace("-", " ")) == text


def test_a_key_cut_short_or_mistyped_says_so_and_not_that_it_is_forged() -> None:
    text = licence_key.make(FUSE, SEED)
    last = text[-1]
    changed = text[:-1] + ("2" if last != "2" else "3")
    middle = len(text) // 2
    swapped = text[:middle] + ("A" if text[middle] != "A" else "B") + text[middle + 1 :]

    for broken in (text[:-5], text[:-1], changed, swapped, text + "7", "LORIINI-", ""):
        with pytest.raises(KeyIncompleteError):
            licence_key.read(broken, PUBLIC)
    with pytest.raises(KeyIncompleteError, match="'U'"):
        licence_key.read(text[:-1] + "U", PUBLIC)


def test_a_key_signed_by_anybody_else_is_not_genuine() -> None:
    foreign = licence_key.make(FUSE, OTHER_SEED)
    with pytest.raises(KeyNotGenuineError, match="not a licence key for this Loriini"):
        licence_key.read(foreign, PUBLIC)


def test_a_key_in_a_later_format_asks_for_the_current_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(licence_key, "VERSION", licence_key.VERSION + 1)
    newer = licence_key.make(FUSE, SEED)
    monkeypatch.undo()
    with pytest.raises(KeyTooNewError, match="newer Loriini"):
        licence_key.read(newer, PUBLIC)


def test_a_key_runs_to_the_end_of_its_last_day_and_not_past_it() -> None:
    assert FUSE.good_on(dt.date(2027, 9, 28))
    assert not FUSE.good_on(dt.date(2027, 9, 29))
    # Issued "tomorrow" by a clock a timezone behind: still good.
    assert FUSE.good_on(TODAY - dt.timedelta(days=1))


def test_what_cannot_be_a_key_is_refused_when_it_is_made() -> None:
    with pytest.raises(ValueError, match="email"):
        licence_key.make(LicenceKey(1, "not an address", "", 1, TODAY, TODAY), SEED)
    with pytest.raises(ValueError, match="seats"):
        licence_key.make(LicenceKey(1, "a@b.c", "", 0, TODAY, TODAY), SEED)
    with pytest.raises(ValueError, match="before it is issued"):
        licence_key.make(LicenceKey(1, "a@b.c", "", 1, TODAY, TODAY - dt.timedelta(1)), SEED)


# -- what a start does with it ------------------------------------------------------


def test_a_build_without_a_public_key_takes_no_keys_and_behaves_as_before(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(licence_public_key, "PUBLIC_KEY", None)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert not licence.keys_required()
    assert licence.standing(TODAY).usable
    licence.check(TODAY)  # silent
    assert "licensed until 1 January 2027" in licence.credential(TODAY)
    with pytest.raises(KeyRefusedError, match="takes no licence keys"):
        licence.install(licence_key.make(FUSE, SEED), TODAY)


def test_a_keyed_build_without_a_key_refuses_the_work_and_says_how(keyed: Path) -> None:
    found = licence.standing(TODAY)
    assert found.required and not found.usable
    assert found.problem == licence.NO_KEY

    with pytest.raises(licence.LicenceKeyError) as refused:
        licence.check(TODAY)
    assert "licence key" in str(refused.value)
    assert "Loriini.exe licence" in str(refused.value)
    # The window asks for a key rather than refusing to open.
    licence.check(TODAY, key_needed=False)


def test_an_installed_key_is_kept_tidy_and_lets_the_work_run(keyed: Path) -> None:
    text = licence_key.make(FUSE, SEED)

    installed = licence.install("\n".join(licence_key.lines(text.lower())), TODAY)

    assert installed == FUSE
    assert keyed.read_text(encoding="utf-8").strip() == text
    licence.check(TODAY)
    assert licence.credential(TODAY).endswith("licensed to Fuse Architects until 1 January 2027"), (
        "the build's own end is earlier than the key's, and it still governs"
    )


def test_a_refused_key_leaves_the_one_before_it_where_it_was(keyed: Path) -> None:
    good = licence_key.make(FUSE, SEED)
    licence.install(good, TODAY)

    with pytest.raises(KeyIncompleteError):
        licence.install(good[:-4], TODAY)
    with pytest.raises(KeyNotGenuineError):
        licence.install(licence_key.make(FUSE, OTHER_SEED), TODAY)
    lapsed = licence_key.make(
        LicenceKey(7, "old@fuse.example", "", 1, dt.date(2025, 1, 1), dt.date(2025, 12, 31)), SEED
    )
    with pytest.raises(KeyExpiredError, match="ended on 31 December 2025"):
        licence.install(lapsed, TODAY)

    assert keyed.read_text(encoding="utf-8").strip() == good


def test_a_key_past_its_last_day_stops_the_work_and_names_the_day(keyed: Path) -> None:
    licence.install(licence_key.make(FUSE, SEED), TODAY)

    later = dt.date(2027, 9, 29)
    with pytest.raises(licence.LicenceExpiredError):
        licence.check(later)  # and the build's own term, earlier, stops it first
    found = licence.standing(later)
    assert not found.usable
    assert "ended on 28 September 2027" in found.problem


def test_a_damaged_key_file_is_a_sentence_not_a_crash(keyed: Path) -> None:
    keyed.parent.mkdir(parents=True, exist_ok=True)
    keyed.write_text("LORIINI-ABCDE-FGHJK", encoding="utf-8")
    found = licence.standing(TODAY)
    assert not found.usable
    assert found.problem.startswith("The licence key installed cannot be used.")


def test_only_the_commands_that_touch_a_project_need_a_key() -> None:
    assert not licence.needs_key([])
    assert not licence.needs_key(["--help"])
    assert not licence.needs_key(["rulesets"])
    assert not licence.needs_key(["info", "--help"])
    assert not licence.needs_key(["licence", "LORIINI-ABCDE"])
    assert licence.needs_key(["shadows", "--port", "19723"])
    assert licence.needs_key(["mcp"])
    assert licence.needs_key(["site", "26-30 Campsie St"])


# -- the command line ----------------------------------------------------------------

runner = CliRunner()


def test_the_licence_command_installs_shows_and_removes(keyed: Path) -> None:
    text = licence_key.make(
        LicenceKey(3, "jane@studio.example", "", 1, dt.date.today(), dt.date(2100, 1, 1)), SEED
    )

    shown = runner.invoke(app, ["licence"])
    assert shown.exit_code == 0
    assert licence.NO_KEY in shown.output

    # Pasted as a shell splits it: several words.
    installed = runner.invoke(app, ["licence", *licence_key.lines(text, groups=3)])
    assert installed.exit_code == 0, installed.output
    assert "Installed: licence 0003, jane@studio.example, 1 seat" in installed.output

    shown = runner.invoke(app, ["licence"])
    assert "Licensed: licence 0003" in shown.output

    refused = runner.invoke(app, ["licence", text[:-6]])
    assert refused.exit_code == 2
    assert "not the whole key" in refused.output

    removed = runner.invoke(app, ["licence", "--remove"])
    assert removed.exit_code == 0 and not keyed.exists()


def test_the_command_line_refuses_work_without_a_key_before_touching_anything(
    keyed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    from sun_study import cli

    monkeypatch.setattr(sys, "argv", ["sun-study", "archicad-info", "--port", "1"])
    touched: list[str] = []
    monkeypatch.setattr(cli, "listen_for_stop", lambda: touched.append("started"))

    with pytest.raises(SystemExit) as stopped:
        cli.main()

    assert stopped.value.code == 5
    assert not touched, "refused at the door, before anything ran"
