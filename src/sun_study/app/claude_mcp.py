"""The *Connect Claude* button: Loriini registered as an MCP server with the
Claude a person already has.

docs/agent.md says how to connect a client by hand: a block in Claude
Desktop's ``claude_desktop_config.json``, or ``claude mcp add`` in a
terminal for Claude Code. This does both for them, with this very program
as the server -- the packaged ``Loriini.exe`` with the one argument ``mcp``,
or, from a checkout, ``uv run --directory <checkout> sun-study mcp`` -- so
the path is never typed and never wrong.

Claude Desktop reads its file at start, so a restart is part of the
answer. Claude Code keeps its own list, through its own command, which is
run here when ``claude`` is on the path and skipped, and said, when it is
not. Nothing else in the file is touched: another server already there
stays there, and a ``loriini`` entry pointing somewhere else -- an older
folder -- is replaced, which is the point of pressing the button again.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SERVER_NAME", "Added", "add_to_claude", "desktop_config_path", "server_command"]

#: What the server is called in the client's list.
SERVER_NAME = "loriini"

#: Windows only, and only when frozen: no console behind ``claude mcp add``.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def server_command() -> list[str]:
    """This program as an MCP server: the command and its arguments."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "mcp"]
    checkout = Path(__file__).resolve().parents[3]
    return ["uv", "run", "--directory", str(checkout), "sun-study", "mcp"]


def desktop_config_path() -> Path:
    """Where Claude Desktop keeps its servers, on this platform."""
    home = Path.home()
    places = {
        "win32": Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "Claude",
        "darwin": home / "Library" / "Application Support" / "Claude",
    }
    folder = places.get(sys.platform, home / ".config" / "Claude")
    return folder / "claude_desktop_config.json"


@dataclass(frozen=True)
class Added:
    """What happened, in sentences a message box can show."""

    desktop: str
    code: str
    command: tuple[str, ...]

    def describe(self) -> str:
        return "\n\n".join(
            (
                f"Claude Desktop: {self.desktop}",
                f"Claude Code: {self.code}",
                "The server is " + " ".join(self.command) + ".",
            )
        )


def add_to_desktop(config: Path, command: list[str]) -> str:
    """The server into Claude Desktop's file, the rest of it kept."""
    settings: dict[str, object] = {}
    if config.exists():
        try:
            loaded = json.loads(config.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as error:
            return (
                f"{config} could not be read ({error}); the server was not added. "
                "Settings > Developer > Edit Config opens the file to look at."
            )
        if not isinstance(loaded, dict):
            return f"{config} is not a settings file; the server was not added."
        settings = loaded
    servers = settings.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        settings["mcpServers"] = servers
    was = servers.get(SERVER_NAME)
    servers[SERVER_NAME] = {"command": command[0], "args": command[1:]}
    try:
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        return f"{config} could not be written ({error}); the server was not added."
    verb = "replaced" if was is not None else "added"
    return f"the server was {verb} in {config}. Restart Claude Desktop to see it."


def add_to_code(command: list[str]) -> str:
    """The server into Claude Code's list, through its own command."""
    claude = shutil.which("claude")
    if claude is None:
        return (
            "the claude command is not on this machine's path, so nothing was added "
            "there. In a terminal with it: claude mcp add loriini -- " + " ".join(command)
        )
    try:
        subprocess.run(
            [claude, "mcp", "remove", SERVER_NAME],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=_NO_WINDOW,
            check=False,
        )
        done = subprocess.run(
            [claude, "mcp", "add", SERVER_NAME, "--", *command],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"claude mcp add could not be run ({error}); nothing was added there."
    if done.returncode != 0:
        said = (done.stderr or done.stdout).strip()
        return f"claude mcp add refused it: {said or done.returncode}"
    return "the server was added with claude mcp add."


def add_to_claude(config: Path | None = None) -> Added:
    """Both clients, and what each said."""
    command = server_command()
    return Added(
        desktop=add_to_desktop(config or desktop_config_path(), command),
        code=add_to_code(command),
        command=tuple(command),
    )
