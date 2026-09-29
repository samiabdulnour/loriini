# The shadow diagram on a larger model: reading a run

The shadow diagram failed outright on a larger model, and the first step of
roadmap R1 is to read that failure rather than guess at it. There are three
ways a run on a big project can fail, and each wants a different fix:

1. **Archicad's export** takes longer than a command is allowed (30 minutes
   by default, `--timeout`) or refuses the model;
2. **the caster** asks for more memory than the machine has, or takes hours;
3. **the drawing**: Archicad refuses a fill it is asked to draw.

This page is how a run now says which, and what was changed for the second
and third before anybody had to watch one fail. D123 records it.

## Where the whole log is

The window shows one line of a run. Every line is now also written to a file
as it comes, flushed line by line, so a run that takes the process down with
it still leaves everything up to that moment:

```
%APPDATA%\Loriini\Logs\2026-09-29 143205 shadow diagram.log
```

The newest sixty are kept. **Whole log**, beside the line at the foot of the
window, opens the last run's; when a run stops with an error, the line left
on screen says where its file is. The head of each file says which build ran,
on which Windows, with how much memory, and what was asked for -- the first
questions of any diagnosis. That file is what to send.

## How to read it

Every stage of the shadow diagram prints a `timing:` line: what it did, how
long it took, and the most memory the run had held by then.

```
  model written to C:\...\shadow.loriini (245 MB)
  timing: exported the model in 3 min 12 s, memory at most 180 MB
  timing: read the model and sorted it into the legend in 41 s, memory at most 1.9 GB
  grid 1,340 x 1,120 m at 1 m, 150 m past everything: about 1,500,800 samples
    stretched by '00 | Temp Delete', which has a solid 1,440 m clear of every legend row; ...
  timing: draped the grid onto the ground in 12 s, memory at most 2.0 GB
  31,516,800 rays a cast, 4 casts
  casting EXISTING: 1,500,800 samples x 21 instants against 412,000 triangles
    38% of EXISTING, 5 min 00 s
  ...
  timing: cast and traced the shadows in 41 min 10 s, memory at most 2.4 GB
  timing: drew the fills in 2 min 03 s, memory at most 2.4 GB
  timing: the whole run took 49 min 20 s
```

**The last stage named is the one that was running.** A log that ends after
`exported the model` failed reading the model; one that ends mid-cast, with
the percentage lines stopping, died in the caster -- and the memory figure on
the line before says how close to the machine's own memory it had come.

## What changed

**The caster's memory no longer grows with the grid.** Every (sample, hour)
pair that faces the sun is a ray, and they used to be gathered all at once
before the first was cast: a grid two kilometres across at a metre, over the
three default days, is about a hundred million rays and nine gigabytes before
any work is done. They are now cast 65,536 samples at a time, and the answer
is the same bit for bit (`core.analysis.sunlit_matrix`, tested against the
single-batch answer). The time is unchanged: a big grid is still a long cast,
and the log now says how long, and how far through, while it runs.

**The grid is said before it is cast, and what stretched it.** The grid is
laid over every solid in the export, with a margin, and its cost goes with
its area. One solid parked a kilometre away -- a hotlink master, a copy of
the massing left beside the site, a marker at the origin -- stretches it to
reach that far. The run now names any layer holding a solid more than 500 m
clear of every legend row. The grid itself is left as it was, since a long
winter shadow may really reach that far; taking the layer out of the export
is the fix.

**A refused fill costs that fill, not the run.** The add-on draws fills 500 at
a time as one undo step, and Archicad refusing any one of them took back the
whole batch and ended the run with nothing said about which. Now a refused
batch is halved and sent again until the refused fill is found; it is left
out and named -- its hour, its legend row, its corners and where it is -- and
everything else is drawn. The areas in the log still count it, so the table
and the plan can be compared. A refusal of every fill is about the run, not a
fill, and still stops it.

**Out of memory is said plainly.** With the grid and the machine's memory in
the message, and what to do: a 2 m `--shadow-grid` is a quarter of the
samples; a smaller `--shadow-margin`, fewer days at once, or a stretching
layer taken out shrink the grid; and [shadow plans](shadow-plans.md) have
Archicad draw the hours instead.

## When the model is simply too big

Some models will be. The caster is pure Python and numpy, deliberately (it
installs on a workstation with no compiler), and casts about 40,000 rays a
second on a 100,000-triangle scene; a four-million-sample grid over
twenty-one hours is hours of work however little memory it takes. For those
the answer is [shadow plans](shadow-plans.md), where Archicad casts the
shadows -- at the cost of the split between existing and additional shadow,
which only the fills can draw.
