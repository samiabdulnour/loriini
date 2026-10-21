"""Online keys, end to end: Loriini and the licence service over a real socket.

Roadmap R5's second half (D125). What a subscriber meets: the key installed
and checked, a start that asks only when it must, a day offline that changes
nothing and a fortnight that does, a withdrawal that stops the next start, a
wound-back clock told to be set right, a seat freed as a key is removed. And
what the vendor meets: the build's term binding only the builds the service
cannot reach, and the service's code never inside the program.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sun_study import __version__, licence, licence_issue, licence_online, licence_public_key
from sun_study.cli import app
from sun_study.licence_key import KeyRefusedError
from sun_study.licence_lease import Lease, Reason
from sun_study.licence_lease import make as make_lease
from tests.unit.licence_service_helpers import SEED, Running, online, trust_the_test_pair

TODAY = dt.datetime.now(dt.UTC).date()
PACKAGE = Path(__file__).resolve().parents[2] / "src" / "sun_study"


def nobody_listening() -> str:
    """An address where no service answers: a port just let go of."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Running]:
    with online(monkeypatch, tmp_path, today=TODAY) as running:
        yield running


def installed(service: Running, **order: object) -> str:
    """A licence issued by the service, its key installed on this computer."""
    issued = service.issue(**order)
    licence.install(issued.key, TODAY)
    return issued.key


def go_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(licence_online.SERVICE_VAR, nobody_listening())


# -- installing, and the first lease ------------------------------------------------------


def test_an_online_key_is_kept_and_then_checked_with_the_service(service: Running) -> None:
    installed(service, seats=5, paid_to=TODAY + dt.timedelta(days=30))
    before = licence.standing(TODAY)
    assert not before.usable
    assert before.problem == licence.NOT_YET_CHECKED

    after = licence.renew(TODAY)
    assert after.usable, after.problem
    assert after.lease is not None and after.lease.granted
    said = after.describe()
    assert said.startswith(
        "Licensed: licence 0001, Fuse Architects (office@fuse.example), 5 seats, renewed online."
    )
    assert "1 of 5 seats in use" in said
    assert licence_online.lease_path().is_file()


def test_a_start_asks_the_service_only_when_no_lease_is_in_force(
    service: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(service)
    licence.check(TODAY)  # no lease yet: asked for, and got
    assert licence.standing(TODAY).usable
    go_offline(monkeypatch)
    licence.check(TODAY)  # asked today already: nothing to ask
    assert licence.renewal_finished(5)


def test_a_lease_fetched_on_an_earlier_day_is_renewed_in_the_background(
    service: Running,
) -> None:
    installed(service)
    licence.renew(TODAY - dt.timedelta(days=1))
    assert licence.standing(TODAY).due(TODAY)
    licence.check(TODAY)
    assert licence.renewal_finished(10)
    kept = licence_online.kept_lease()
    assert kept is not None and kept.fetched == TODAY


def test_a_day_offline_changes_nothing_and_a_fortnight_does(
    service: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(service)
    licence.renew(TODAY)
    go_offline(monkeypatch)
    licence.check(TODAY + dt.timedelta(days=5))  # in force; the renewal fails quietly
    assert licence.renewal_finished(10)
    with pytest.raises(licence.LicenceKeyError) as refused:
        licence.check(TODAY + dt.timedelta(days=15))
    said = str(refused.value)
    assert "Loriini last reached the licence service on" in said
    assert "Loriini could not reach the licence service" in said


# -- what the service says goes -------------------------------------------------------------


def test_a_withdrawal_stops_the_next_start_that_reaches_the_service(service: Running) -> None:
    installed(service)
    licence.renew(TODAY)
    licence_row = service.store.licence(1)
    service.store.save(type(licence_row)(**{**licence_row.__dict__, "withdrawn": "refunded"}))
    tomorrow = TODAY + dt.timedelta(days=1)
    licence.check(tomorrow)  # the lease held is in force; the renewal brings the refusal
    assert licence.renewal_finished(10)
    with pytest.raises(licence.LicenceKeyError, match="Licence 0001 has been withdrawn: refunded"):
        licence.check(tomorrow)


def test_a_refusal_for_seats_names_the_computers_holding_them(service: Running) -> None:
    installed(service, seats=1)
    for number in (1, 2):
        service.store.seen(1, bytes([number] * 16).hex(), f"colleague on PC-{number}", "1.0", TODAY)
    found = licence.renew(TODAY)
    assert not found.usable
    assert found.lease is not None and found.lease.reason is Reason.SEATS
    assert (
        "All 1 seat of licence 0001 are in use, on colleague on PC-1 and colleague on PC-2."
        in found.problem
    )


def test_a_recall_of_another_version_does_not_stop_this_one(service: Running) -> None:
    key = installed(service)
    recall = Lease(
        serial=1,
        machine=licence_online.machine(),
        given=TODAY,
        until=TODAY,
        granted=False,
        reason=Reason.RECALLED,
        build="0.0.0-another",
        notice="Loriini 0.0.0-another has been withdrawn.",
    )
    licence_online.keep_lease(make_lease(recall, SEED), TODAY)
    assert licence.standing(TODAY).problem == licence.NOT_YET_CHECKED
    assert key and licence.renew(TODAY).usable


def test_this_version_recalled_stops_with_the_reason(service: Running) -> None:
    installed(service)
    service.store.set_setting("minimum_build", "999.0")
    service.store.set_setting("recall_reason", "it gives the wrong hours")
    found = licence.renew(TODAY)
    assert not found.usable
    assert f"Loriini {__version__} has been withdrawn: it gives the wrong hours." in found.problem


# -- what a start does not believe ------------------------------------------------------------


def test_a_lease_given_to_another_computer_is_not_believed(
    service: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(service)
    licence.renew(TODAY)
    monkeypatch.setattr(licence_online, "machine", lambda: bytes(range(100, 116)))
    assert licence.standing(TODAY).problem == licence.NOT_YET_CHECKED


def test_a_lease_signed_by_anybody_else_is_not_believed(service: Running) -> None:
    installed(service)
    forged = Lease(
        serial=1,
        machine=licence_online.machine(),
        given=TODAY,
        until=TODAY + dt.timedelta(days=400),
    )
    licence_online.keep_lease(make_lease(forged, bytes(range(1, 33))), TODAY)
    assert licence.standing(TODAY).problem == licence.NOT_YET_CHECKED


def test_a_clock_wound_back_is_told_to_be_set_right(service: Running) -> None:
    installed(service)
    licence.renew(TODAY)
    found = licence.standing(TODAY - dt.timedelta(days=3))
    assert not found.usable
    assert "is earlier than the licence service's" in found.problem
    assert "Set the computer's clock right" in found.problem


def test_a_lease_file_that_is_not_one_is_no_lease(service: Running) -> None:
    installed(service)
    licence_online.lease_path().write_text("{not json", encoding="utf-8")
    assert licence.standing(TODAY).problem == licence.NOT_YET_CHECKED


# -- the build's term ----------------------------------------------------------------------------


def test_the_build_term_binds_offline_keys_and_not_online_ones(
    service: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(licence, "EXPIRES", TODAY)
    installed(service)
    licence.check(TODAY)  # past the term, and an online key: runs
    offline = service.issue(online=False, paid_to=TODAY + dt.timedelta(days=90))
    licence.install(offline.key, TODAY)
    with pytest.raises(licence.LicenceExpiredError):
        licence.check(TODAY)


def test_a_keyed_build_asks_for_a_key_before_it_mentions_its_term(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trust_the_test_pair(monkeypatch, tmp_path)
    monkeypatch.setattr(licence, "EXPIRES", TODAY)
    with pytest.raises(licence.LicenceKeyError, match="needs a licence key"):
        licence.check(TODAY)


def test_a_build_that_does_not_know_the_service_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trust_the_test_pair(monkeypatch, tmp_path)
    _key, text = licence_issue.issue(
        licence_issue.Order(email="a@b.example", online=True), SEED, serial=3
    )
    with pytest.raises(KeyRefusedError, match="does not know where the licence service is"):
        licence.install(text, TODAY)


# -- removing a key -------------------------------------------------------------------------------


def test_removing_an_online_key_frees_its_seat(service: Running) -> None:
    installed(service)
    licence.renew(TODAY)
    said = licence.remove()
    assert said is not None and said.endswith("Its seat is free for another computer.")
    [computer] = service.store.computers(1)
    assert computer.freed == TODAY
    assert not licence.key_path().exists()
    assert not licence_online.lease_path().exists()
    assert licence.remove() is None


def test_removing_it_offline_says_when_the_seat_frees_itself(
    service: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(service)
    licence.renew(TODAY)
    go_offline(monkeypatch)
    said = licence.remove()
    assert said is not None and "so its seat frees itself on" in said


# -- the command line -------------------------------------------------------------------------------


def test_the_licence_command_installs_checks_and_removes_an_online_key(service: Running) -> None:
    issued = service.issue(seats=3)
    runner = CliRunner()
    put = runner.invoke(app, ["licence", issued.key])
    assert put.exit_code == 0, put.output
    assert "Licensed: licence 0001" in put.output
    assert "1 of 3 seats in use" in put.output
    renewed = runner.invoke(app, ["licence", "--renew"])
    assert renewed.exit_code == 0
    assert "checked with the licence service" in renewed.output
    gone = runner.invoke(app, ["licence", "--remove"])
    assert "Its seat is free for another computer." in gone.output


def test_a_key_installed_while_the_service_is_out_of_reach_says_so(
    service: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    issued = service.issue()
    go_offline(monkeypatch)
    put = CliRunner().invoke(app, ["licence", issued.key])
    assert put.exit_code == 2
    assert "but it cannot be used yet" in put.output
    assert "Loriini.exe licence --renew asks again" in put.output
    assert licence.key_path().is_file(), "the key is kept, to try again"


# -- whose licence made a result ----------------------------------------------------------------------


def test_the_licensee_is_what_the_results_record(service: Running) -> None:
    assert licence.licensee() == ""
    installed(service)
    licence.renew()
    assert licence.licensee() == "licence 0001, Fuse Architects"
    assert licence.credential().endswith("· licensed to Fuse Architects")
    trial = service.issue(trial=True, holder="Tryer Studio")
    licence.install(trial.key)
    licence.renew()
    assert licence.licensee() == "trial licence 0002, Tryer Studio"
    assert "trial licence for Tryer Studio until" in licence.credential()


# -- talking to the service ------------------------------------------------------------------------------


def test_the_services_own_sentence_reaches_the_person(service: Running) -> None:
    with pytest.raises(
        licence_online.ServiceError, match=r"The licence service said: .*cannot accept that key"
    ):
        licence_online.ask_for_lease(
            "LORIINI-ABCDE", service=service.url, machine=licence_online.machine(), name="me"
        )


def test_an_address_where_nothing_answers_is_a_sentence_too() -> None:
    with pytest.raises(licence_online.ServiceError, match="could not reach the licence service"):
        licence_online.ask_for_lease(
            "LORIINI-ABCDE", service=nobody_listening(), machine=bytes(16), name="me", timeout=5
        )


def test_the_builds_own_address_falls_back_when_nothing_answers_there(
    service: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An office firewall that resets every connection to a young domain
    leaves the service's other address to ask, and the lease comes from it."""
    monkeypatch.delenv(licence_online.SERVICE_VAR, raising=False)
    monkeypatch.setattr(licence_public_key, "SERVICE", nobody_listening())
    monkeypatch.setattr(licence_online, "FALLBACK_SERVICES", (service.url,))
    installed(service)
    after = licence.renew(TODAY)
    assert after.usable, after.problem
    assert after.lease is not None and after.lease.granted


def test_only_an_address_nothing_answers_at_is_passed_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refusal is the service's word and is not asked again elsewhere; when
    nothing answers anywhere, the build's own address is the one named; and an
    address set in the environment is used alone."""
    monkeypatch.delenv(licence_online.SERVICE_VAR, raising=False)
    monkeypatch.setattr(licence_public_key, "SERVICE", "https://own.example")
    monkeypatch.setattr(licence_online, "FALLBACK_SERVICES", ("https://spare.example",))
    asked: list[str] = []

    def refuse(address: str, *_: object) -> dict[str, object]:
        asked.append(address)
        raise licence_online.ServiceError("The licence service said: no.")

    def unreachable(address: str, *_: object) -> dict[str, object]:
        asked.append(address)
        raise licence_online.UnreachableError(f"Loriini could not reach {address}.")

    def free(address: str) -> bool:
        return licence_online.release("LORIINI-ABCDE", service=address, machine=bytes(16))

    monkeypatch.setattr(licence_online, "_post_once", refuse)
    with pytest.raises(licence_online.ServiceError, match="said: no"):
        free("https://own.example")
    assert asked == ["https://own.example"]

    asked.clear()
    monkeypatch.setattr(licence_online, "_post_once", unreachable)
    with pytest.raises(licence_online.UnreachableError, match=r"own\.example"):
        free("https://own.example")
    assert asked == ["https://own.example", "https://spare.example"]

    asked.clear()
    monkeypatch.setenv(licence_online.SERVICE_VAR, "https://chosen.example")
    with pytest.raises(licence_online.UnreachableError):
        free("https://chosen.example")
    assert asked == ["https://chosen.example"]


def test_a_computer_is_named_the_same_every_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert licence_online.machine() == licence_online.machine()
    assert len(licence_online.machine()) == 16
    # A computer that will not say its own name gets one made, and kept.
    monkeypatch.setattr(licence_online, "_machine_guid", lambda: "")
    first = licence_online.machine()
    assert (tmp_path / "Loriini" / licence_online.IDENTIFIER_FILE).is_file()
    assert licence_online.machine() == first
    assert " on " in licence_online.machine_name() or licence_online.machine_name()


def test_the_lease_file_holds_the_lease_and_the_day_it_came(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert licence_online.kept_lease() is None
    assert licence_online.keep_lease("abc", TODAY)
    held = json.loads(licence_online.lease_path().read_text(encoding="utf-8"))
    assert held == {"lease": "abc", "fetched": TODAY.isoformat()}
    assert licence_online.kept_lease() == licence_online.Kept("abc", TODAY)
    licence_online.forget_lease()
    licence_online.forget_lease()
    assert licence_online.kept_lease() is None


def test_the_service_address_is_the_environments_then_the_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(licence_online.SERVICE_VAR, raising=False)
    monkeypatch.setattr(licence_public_key, "SERVICE", None)
    assert licence_online.service() is None
    monkeypatch.setattr(licence_public_key, "SERVICE", "https://licence.example")
    assert licence_online.service() == "https://licence.example"
    monkeypatch.setenv(licence_online.SERVICE_VAR, "http://127.0.0.1:9")
    assert licence_online.service() == "http://127.0.0.1:9"


# -- the service stays out of the program -------------------------------------------------------------------


def test_nothing_loriini_runs_imports_the_vendors_side() -> None:
    """The issuer and the service are the vendor's: the bundle leaves them out
    (Loriini.spec), and nothing the program imports may pull them back in."""
    vendors = ("sun_study.licence_service", "sun_study.licence_issue")
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE).as_posix()
        if relative.startswith("licence_service/") or relative == "licence_issue.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if isinstance(node, ast.ImportFrom) and node.module == "sun_study":
                names += [f"sun_study.{alias.name}" for alias in node.names]
            offenders += [f"{relative}: {name}" for name in names if name.startswith(vendors)]
    assert not offenders, offenders
