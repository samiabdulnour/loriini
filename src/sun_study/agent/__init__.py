"""Loriini's studies, served to an AI agent.

An agent someone already has -- Claude Desktop, Claude Code, any client of
the Model Context Protocol -- starts ``Loriini.exe mcp`` and talks to it on
its stdin and stdout. Through it the agent can list the Archicads running
on the machine, read the open project's layers, zone names, combinations
and master layouts, and run the site analysis, the shadow diagrams and the
sun views into the project, or any other command the command line offers.

Nothing here is a second way to run a study. Every tool runs the same
command line the window runs, in a child process, and reads its lines back
-- so there is one tested path, and a study started by an agent is exactly
the study the window would have started (``app.runner``).

The protocol is written here rather than taken from a library; ``protocol``
says why. R2 in docs/roadmap.md is the ask, and docs/agent.md is how a
person connects their client.
"""

from __future__ import annotations

from sun_study.agent.tools import build, serve

__all__ = ["build", "serve"]
