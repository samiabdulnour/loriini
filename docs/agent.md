# Loriini for an agent

Loriini's studies can be run by an AI agent a person already has -- Claude
Desktop, Claude Code, or any other client of the Model Context Protocol
(MCP). The agent starts `Loriini.exe mcp` and talks to it on its own
stdin and stdout; through it, the agent lists the Archicads running on the
machine, reads the open project's layers and names, and runs the site
analysis, the shadow diagrams and the sun views into the project, or any
other command the command line has. Asked "run the 21 June shadow
diagrams for this project at 9, 12 and 3", the agent finds the port, reads
the layer names, runs the study and reports what it made.

Nothing here is a second way to run a study. Every tool runs the same
command line the window runs, in a child process, and reads its lines back,
so a study started by an agent is exactly the study the window would have
started. It is roadmap item R2; D120 records how it is built.

## Connecting a client

**The button.** *Connect Claude*, beside the project picker at the top of
Loriini's window, does the two things below for the program it is pressed
in: it writes the server into Claude Desktop's settings file, keeping
whatever else is there, and runs `claude mcp add` for Claude Code when that
command is on the path -- and says what it did where, and that Claude
Desktop wants a restart. Pressed again from another folder, it replaces the
entry. By hand, the same:

The program is `Loriini.exe` from the handover folder, and its one argument
is `mcp`. A checkout runs `sun-study mcp` instead.

**Claude Desktop** reads `%APPDATA%\Claude\claude_desktop_config.json`
(Settings > Developer > Edit Config opens it). Add the server and restart
Claude Desktop:

```json
{
  "mcpServers": {
    "loriini": {
      "command": "C:\\Loriini\\Loriini.exe",
      "args": ["mcp"]
    }
  }
}
```

**Claude Code**, in a terminal:

```
claude mcp add loriini -- "C:\Loriini\Loriini.exe" mcp
```

**From a checkout**, for either: the command is `uv` with the arguments
`run --directory <the checkout> sun-study mcp`.

The client shows the tools once it has connected, and asks the person
before a tool that changes the project runs; the listings are marked
read-only and run without asking. A client that shows an icon beside a
server's name is sent the bird for it.

**On another machine**, the same block with that machine's paths: the
handover folder's `Loriini.exe` with the one argument `mcp`, or a checkout
through `uv`. Nothing is shared between machines; each client reads its
own file at start.

## What the agent can do

| Tool | What it does | Changes the project |
|---|---|---|
| `archicad_instances` | Every Archicad running on the machine, the project each has open, and its port. The agent runs this first. | no |
| `project_options` | What the open project offers, read from it: layers, the layers that carry zones and what the zones are called, layer combinations, master layouts, layout subsets, pen sets, graphic overrides, storeys, location, the add-on's version. The studies take these names exactly as spelled. | no |
| `loriini_help` | The command line's own help: the list of commands, or every option of one. | no |
| `run_loriini` | Any command line, as `["shadows", "--port", "19724", ...]`, for what the named tools do not cover: the solar analysis (`archicad-run`, `massing`), the reports, the checks. | yes |
| `site_analysis` | The site tools for an address: the Context Analysis and Site Analysis sheets and the Summary of Controls, optionally the 3D context model and the future context. Sets the project location from the address unless told to keep it. | yes |
| `shadow_diagram` | The shadow diagram: the days and hours asked as 3D Documents from overhead, with Archicad's own sun and shadows, on layouts by day ([`shadow-plans.md`](shadow-plans.md)). Given a legend -- `sources` and `scenarios`, or `existing` and `proposals` -- every row of an hour stacked in one drawing, each in its legend colour. Its layer combination is asked of the person. | yes |
| `shadow_every_hour` | The design's own shadow at every hour asked, imported as fills into one drawing, a sheet per day: the fills route, for that drawing only ([D160](decisions.md)). Refused without a design (a `PROPOSED` row or a scenario). | yes |
| `sun_views` | The sun's-eye views, one per hour, each as a 3D Document on layouts. | yes |

The four study tools take the questions the window's pages ask, and spell
them onto the command line the way the window does (`Window.jobs`), so a
study run by an agent and one run from the window are the same run. What
they do not offer, `run_loriini` does, with `loriini_help` to read the
options first.

While a study runs, every line it prints goes to the client as it is
printed -- as a log message, and as a progress notification when the
client gave the call a progress token -- so the agent and its person watch
it go. The answer is the run's last 120 lines with its exit code; a run that
ended with an error is an error result the agent can read and act on. The
client can cancel a running study, and the study is then asked to stop the
way the window's Stop button asks, through its stop file, so the project's
layers are put back before it ends.

## What to know before letting an agent at a project

A study changes the project it runs into: it makes layouts, views and
elements on its own layers, and clears its previous run. The client asks
before each such tool, and the server's instructions tell the agent to run
into a project only what the person asked for; neither is an undo. Keep the
agent's access to Loriini's own commands, which put the project back in
their `finally` blocks and are covered by the licence check, and not to raw
Archicad commands.

One study at a time. Two studies in one project at once would each hold the
project's layer state and each restore it over the other.

The licence is checked when the server starts, as it is for the window:
an expired build says so on its stderr, which the client shows in its
logs, and exits.

## Trying it without an agent

The server speaks one JSON line per message. From a shell, a client is
three lines, and a pause:

```
(printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"archicad_instances","arguments":{}}}'; \
  sleep 30) | Loriini.exe mcp
```

The answers come back one per line: the handshake, then the tool's result.
The pause matters: the end of the server's stdin is the client leaving,
and a study still running then is stopped, the way the window's Stop
button stops one, rather than left holding the project with nobody to
read its answer. A real client keeps the pipe open until it is done.

Nothing else may appear on stdout -- a stray print would break the
protocol -- which is why the studies run as a child process and the server
itself prints nothing. Whatever the server has to say for itself goes to
stderr, where a client keeps its server logs.

## What is not here yet

The server has been driven by a scripted client and by the tests, not yet
from Claude Desktop on a workstation; that is the next step, and the first
thing to check is that a windowed executable started by a client gets its
stdin and stdout as pipes (the server opens the descriptors directly when
Python has not wrapped them). The protocol's other halves -- resources,
prompts, asking the person a question mid-run -- are not offered; the
first of those worth adding is the question, so that a study could confirm
its port and project with the person before running.
