"""The *Connect Claude* button: the program registered as an MCP server with
Claude Desktop's settings file and with Claude Code's own command."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import sun_study.app.claude_mcp as claude_mcp


def test_the_server_is_this_program() -> None:
    command = claude_mcp.server_command()
    assert command[-2:] == ["sun-study", "mcp"], "from a checkout, through uv"
    assert command[:3] == ["uv", "run", "--directory"]
    assert (Path(command[3]) / "pyproject.toml").is_file(), "the checkout it names"


def test_a_frozen_build_is_the_server_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Loriini\Loriini.exe")
    assert claude_mcp.server_command() == [r"C:\Loriini\Loriini.exe", "mcp"]


def test_the_server_is_added_to_desktops_file_and_the_rest_is_kept(tmp_path: Path) -> None:
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8"
    )
    said = claude_mcp.add_to_desktop(config, ["C:\\Loriini\\Loriini.exe", "mcp"])
    assert said.startswith("the server was added in") and "Restart Claude Desktop" in said
    kept = json.loads(config.read_text(encoding="utf-8"))
    assert kept["theme"] == "dark" and kept["mcpServers"]["other"] == {"command": "x"}
    assert kept["mcpServers"]["loriini"] == {"command": "C:\\Loriini\\Loriini.exe", "args": ["mcp"]}
    # Pressed again from another folder: the entry is replaced, not doubled.
    again = claude_mcp.add_to_desktop(config, ["D:\\Elsewhere\\Loriini.exe", "mcp"])
    assert again.startswith("the server was replaced in")
    assert json.loads(config.read_text())["mcpServers"]["loriini"]["command"].startswith("D:")


def test_a_missing_file_is_made_and_a_broken_one_is_left_alone(tmp_path: Path) -> None:
    fresh = tmp_path / "new" / "claude_desktop_config.json"
    assert claude_mcp.add_to_desktop(fresh, ["uv", "mcp"]).startswith("the server was added")
    assert json.loads(fresh.read_text())["mcpServers"]["loriini"]["args"] == ["mcp"]
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    said = claude_mcp.add_to_desktop(broken, ["uv", "mcp"])
    assert "could not be read" in said and "not added" in said
    assert broken.read_text(encoding="utf-8") == "{not json"


def test_without_the_claude_command_code_is_told_what_to_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    said = claude_mcp.add_to_code(["C:\\Loriini\\Loriini.exe", "mcp"])
    assert "not on this machine's path" in said
    assert "claude mcp add loriini -- C:\\Loriini\\Loriini.exe mcp" in said


def test_with_the_claude_command_it_is_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = stderr = ""

    def run(args: list[str], **_kwargs: Any) -> Done:
        calls.append(args)
        return Done()

    monkeypatch.setattr(shutil, "which", lambda _name: "claude.cmd")
    monkeypatch.setattr(subprocess, "run", run)
    said = claude_mcp.add_to_code(["uv", "run", "sun-study", "mcp"])
    assert said == "the server was added with claude mcp add."
    assert calls[-1] == [
        "claude.cmd",
        "mcp",
        "add",
        "loriini",
        "--",
        "uv",
        "run",
        "sun-study",
        "mcp",
    ]
    assert calls[0][:3] == ["claude.cmd", "mcp", "remove"], "the old entry first"


def test_both_clients_are_answered_in_one_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    added = claude_mcp.add_to_claude(tmp_path / "claude_desktop_config.json")
    said = added.describe()
    assert said.startswith("Claude Desktop: the server was added in")
    assert "Claude Code: the claude command is not" in said
    assert said.endswith("sun-study mcp.")
