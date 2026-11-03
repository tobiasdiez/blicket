# blicket

Storybook for scientific model outputs. A *Blick* is a named view on a model run: a function that
turns the run into a table, and how to plot that table. blicket discovers a project's Blicks,
lists them with every problem it finds in their definitions, builds their tables for a model run,
shows them in a web viewer, compares two builds, and checks a run against its baseline; while you
develop, it keeps a run in memory and charts any quantity of it in a Blick builder. The idea
behind it is in
[docs/concept.md](https://github.com/tobiasdiez/blicket/blob/main/docs/concept.md), the design in
[docs/architecture.md](https://github.com/tobiasdiez/blicket/blob/main/docs/architecture.md).

## Installation

blicket is on [PyPI](https://pypi.org/project/blicket/) and can be installed via

```console
$ uv add blicket
$ uv run blicket --version
```

`pip install blicket` works as well, in any environment with Python 3.14 or newer.

### From the repository

Changes that are not released yet come from the repository, with a build setting for the viewer
in the project's `pyproject.toml`:

```toml
[tool.uv.config-settings-package]
blicket = { setup-args = "-Dviewer=enabled" }
```

```console
$ uv add git+https://github.com/tobiasdiez/blicket
```

The build generates the viewer and bundles it, which takes Node 24 or newer, and
[pnpm](https://pnpm.io/installation).

## Defining Blicks

```toml
# pyproject.toml
[tool.blicket]
blicks = ["blicks/**/*.py"]  # the default
```

The loader is `load_run` in `blicketconf.py` next to `pyproject.toml`, found by convention like
pytest's `conftest.py`; a project whose loader lives inside its own package sets
`loader = "mymodel.blicket:load_run"` instead.

```python
# blicks/flows.py
import blicket as bk

bk.group("flows", title="Material flows", tags=["mfa"])


@bk.blick(
    title="Steel flows by process",
    unit="t per year",
    plot=bk.plots.stacked_area(x="year", y="value", color="process"),
)
def steel_by_process(run):
    return run["flows"]
```

`unit=` names the unit of the measure on `y`, or of a Sankey's `value`; the viewer puts it on the
y axis, or over a Sankey diagram as the width of its links, and in the tooltips.
`independent_y=True` is for Blicks whose panels differ by orders of magnitude: each panel of a
split then gets its own y axis by default; otherwise the panels share one, and the viewer's toggle
changes either. Both are part of the Blick's definition in the manifest.

`stacked_area` and `stacked_bar` stack the layers of `color` at each x in their display order,
positive values up from zero and negative ones down: over a table whose exports are negative,
`bk.plots.stacked_area(x="year", y="value", color="flow")` draws the imports above the axis and the
exports below it. On each side the first layer is the outermost and the last lies next to zero, so
a layer with values of both signs, which stacks each value on its own side, is best put last, where
it crosses zero without crossing the other layers. In a `stacked_area`, a layer that is never
positive in a panel, and negative at least once, keeps its zeros and gaps with the negative layers
rather than on top of the positive ones. A comparison measures against the height of the stacks,
the larger of the positive sum and the absolute negative one, and compares the positive and the
negative sums of the two builds each on its own, so imports and exports that grow alike are a
change though their net stays the same.

A line chart takes a logarithmic axis for values that span orders of magnitude, such as GDP
across regions:

```python
@bk.blick(plot=bk.plots.line(x="year", y="value", color="region", y_scale="log"))
def gdp_per_capita(run):
    return run["gdp_per_capita"]
```

`x_scale="log"` does the same for x, which then needs an integer dimension. `bar`, `stacked_bar`
and `stacked_area` take no scale: bars and stacks stand on zero, which a logarithmic axis has
not. Nor has it a place for a negative value, so a value at or below zero is drawn as missing:
on y the line breaks there and the tooltip shows a dash, on x the row is left out, and a note
under the chart says how many values it left out. The charts of the change against a baseline keep the x scale and draw the change,
which crosses zero, on a linear y axis. The scales are part of the plot's definition in the
manifest; `linear`, the default, is not recorded.

```console
$ blicket list
flows  Material flows  [mfa]
  flows/steel_by_process   Steel flows by process   stacked_area

1 group · 1 Blick
```

`blicket list` looks for the project by walking up from the working directory; `--project PATH`
names the project directory instead. `-v` shows tracebacks, `--json` prints the report as JSON.

Exit codes, for every command: 0 success (for `serve` and `dev`, stopped with Ctrl-C; for `diff`,
changes found included), 1 for `check` when a Blick is flagged, 2 errors of any kind, a Blick that
fails to build included, except in `dev`, which reports it and goes on.

### Plot types

The built-in plot types in `bk.plots` bind table columns to their channels, `x` and `y`, or a
Sankey's `source`, `target` and `value`, always, the others optional:

- `line(x, y, color, linetype, x_scale, y_scale)`: lines of the measure `y` over the dimension
  `x`, one per colour and line type value; `x_scale` and `y_scale` as for `scatter` below.
- `stacked_area(x, y, color)`: areas of `y` over `x`, one stacked layer per colour value.
- `bar(x, y, color)` and `stacked_bar(x, y, color)`: bars of `y` at each value of `x`, one per
  colour value, side by side or stacked.
- `scatter(x, y, color, linetype, along, x_scale, y_scale)`: the measure `y` against the measure
  `x`, both float columns (an integer column needs `measures=`), a point per row, coloured by
  `color` and shaped by `linetype`. With `along` naming a dimension, the points of each series are
  connected in the display order of its values instead, a trajectory over time or a curve over
  grid points, dashed by `linetype`. Rows with a null `x` or `y` are left out, and the viewer says
  how many under the chart. `x_scale="log"` or `y_scale="log"` draws that axis logarithmic,
  without the values at or below zero; the scales are part of the definition. `diff` and `check`
  compare `y` row by row, as for a line; a change of `x` alone is not flagged.
- `sankey(source, target, value, color)`: a Sankey diagram with a link per row from the node of
  its `source` value to that of its `target` value, as wide as the measure `value` and coloured by
  `color`; a value that is in both columns is one node, so flows may loop, as recycling does. A
  row with no value, 0 or a negative value draws no link, nor does one from a node to itself, and
  a caption under the diagram counts the negative ones and the ones from a node to itself; a value
  within a billionth of the largest of its panel is noise and counts as 0. Every dimension the
  plot leaves unbound gets a control, as for the other types, so a Sankey of flows by year and
  region shows one year and region at a time.

```python
@bk.blick(
    title="In-use stock per capita over GDP per capita",
    unit="t per person",
    plot=bk.plots.scatter(
        x="GDP per capita", y="value", color="region", along="year", x_scale="log"
    ),
)
def stock_over_gdp(run):
    return run["stock_per_capita"]  # year, region, GDP per capita and value
```

The unit is the unit of `y`, or of a Sankey's `value`; a scatter's `x` is a measure of its own,
named by its column.

```python
@bk.blick(
    title="Sankey diagram",
    unit="t per year",
    plot=bk.plots.sankey(source="From", target="To", value="value", color="Stage"),
    defaults={"Time": 2050, "Region": "World"},
)
def sankey(run):
    return run["process_flows"]  # the columns Time, Region, From, To, Stage and value
```

A Sankey's table has one row per source, target and colour value for each combination of the
other dimensions: add parallel flows up in the Blick, since blicket refuses two rows with the same
dimension values, and a column that tells them apart belongs on `color`. Keep the flows that are 0
rather than leaving their rows out: a node or colour value that vanishes from the table is flagged
`schema` and its rows are left out of the magnitude, and the change bars can only show a flow whose
ends the selection of the other table still carries. A split draws a diagram per value, and with
`independent_y=True` each has a link scale of its own; the comparison measures a row's change
against the largest flow of its panel, the largest absolute value in either table, so a negative
value, which is not drawn, sets the scale all the same.

## Building a run

The `loader` in `[tool.blicket]` names a function that loads a run and says what it is:

```python
# blicketconf.py
import polars as pl

import blicket as bk


def load_run(selection: bk.RunSelection) -> tuple[object, bk.RunInfo]:
    path = selection.path
    run = {"flows": pl.read_csv(path / "flows.csv")}
    info = bk.RunInfo(id=path.name, profile="baseline", fingerprint=bk.fingerprint(path))
    return run, info
```

A run is then a directory such as `runs/2026-10-22/` with a `flows.csv`:

```csv
year,process,value
2020,BOF,1.5
2020,EAF,0.5
2021,BOF,1.4
2021,EAF,0.7
```

`selection.path` is the run path given on the command line and fails when there are several; a
loader that collects several runs into one reads `selection.paths`. `fingerprint` is required: it
identifies the input files, and `bk.fingerprint` computes one from them. `profile` names the run
configuration, such as "baseline" or "policy", so that each has its own baseline.

A transformation returns a long table: a polars or pandas frame, an Arrow table, or an object with
`to_df()` or `to_dataframe()`, such as a flodym array or an xarray object. Named levels of a pandas
index become columns and unnamed levels are dropped; a Series is not accepted. Float columns are
measures and the others dimensions, so an integer column that holds values needs `measures=[...]`;
`dims=` overrides the other way. Every measure must be bound to a plot channel and hold no infinite
value (NaN counts as null), and no two rows may share their dimension values, which become
strings, integers, booleans, dates or datetimes.

```console
$ blicket build runs/2026-10-22
run 2026-10-22 · profile baseline · blicks at 0a6b858 · loaded in 12 ms
1 Blick: 1 built
build 5d0c3f1e2a9b8c47 → .blicket/build/5d0c3f1e2a9b8c47
```

The first line names the run and its profile, the commit of the repository that holds the Blicks
(`blicks at`, marked `(dirty)` with uncommitted changes), and the loader's wall time.

The build directory holds `manifest.json`, which describes the run, the project's settings and git
state, every Blick's definition, table schema, controls and problems, one `blicks/<id>.parquet` per
Blick that built, and a copy of the viewer (`index.html`, `favicon.svg`, `_nuxt/`, and a
`viewer-version` marker listing the copied files). The build id is a hash of the manifest without
the timestamps and timings, the blicket version, tracebacks, the run's id, paths and model
checkout, the repository's branch and dirty flag, where the Blicks are defined, and the controls
blicket derives for them; it covers the Blicks' definitions, tables, problems and skip reasons, the
settings, the run's profile and fingerprint, and the commit. Building the same run with the same
Blicks at the same commit gives the same id again and leaves the directory as it is. A
transformation that raises, or a table that fails a check, is listed under `errors` like a problem
of `blicket list`; the other Blicks are built all the same, and the exit code is 2. `--json`
prints the manifest, `--out DIR` puts the build directory into `DIR` instead of `.blicket/build`,
and `-v` shows tracebacks. blicket gives `.blicket/` a `.gitignore`, so builds never show up in
`git status`. A build of the same id keeps its manifest and tables; only the files of its copy of
the viewer are replaced when it differs from the installed one (`(built before, viewer
refreshed)`).

A transformation raises `bk.Skip(reason)` when its Blick does not apply to the run, for example
because the run has no trade module. A second Blick in `blicks/flows.py`, say, reads trade, which
the run above lacks:

```python
@bk.blick(
    title="Steel trade by process",
    unit="t per year",
    plot=bk.plots.stacked_area(x="year", y="value", color="process"),
)
def trade_by_process(run):
    if "trade" not in run:
        raise bk.Skip("the run has no trade module")
    return run["trade"]
```

```console
$ blicket build runs/2026-10-22
run 2026-10-22 · profile baseline · blicks at 0a6b858 · loaded in 12 ms
2 Blicks: 1 built · 1 skipped
build 9c41e7a2b05d3f86 → .blicket/build/9c41e7a2b05d3f86

skipped
  the run has no trade module
    flows/trade_by_process
```

A skipped Blick is not an error: the manifest records it with the status `skipped` and the reason,
without a table, and the exit code does not change. The section `skipped` lists the skipped Blicks
under their reasons; `diff` and `check` show the first line of a reason. `blicket list` runs no
transformation, so it cannot tell which Blicks a run skips.

## Looking at a build

```console
$ blicket serve .blicket/build/5d0c3f1e2a9b8c47
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
```

Without an argument, `blicket serve` serves the build of the project made last; `--port`, `--host`
and `--open` (open the browser) do what they say. Without `--port`, it listens on 8765, or, when
that port is taken, on the next free one and says so on stderr; a port that `--port` names and that
is taken is an error. It serves nothing outside the build directory and the viewer. A sidebar on
every page lists the Blicks by group, with a search box, a badge on each
Blick the comparison flags (see [Comparing two builds](#comparing-two-builds)) and a filter that
keeps those; it collapses, and on a window narrower than 1280 px it is a drawer. The overview shows
small charts: of the Blicks that changed since the baseline, the largest change first, each at the
panel where its change is largest with the baseline faded behind (but for a Sankey diagram, which
does not draw the baseline), and of the Blicks you pinned.
While nothing is pinned and nothing changed, it shows the first six Blicks instead, as "A first
look", each card with a button that pins it. A line at the top says when Blicks failed to build or
the build is incomplete; their problems are listed under the charts. Pins are kept in the browser
per origin, that is per address and port: the builds that `blicket serve` shows on one port share
them, as do the catalogs on one static host, and nothing is written to the project or the build. A
pinned Blick that a build lacks is left out, and a renamed one keeps its pin through its aliases. A
Blick's page shows its chart, its controls and a data tab with the rows shown.
Every dimension that the plot does not bind to a channel gets a control: a filter that shows one
value at a time, starting at the first value in display order or at `defaults={dim: value}`, or,
with `controls={dim: "split"}`, one panel per value. The control state is in the URL
(`#/blick/flows/steel_by_process?region=EU&_split=scenario`, `_y` for the y axes, `_tab=data` for
the data tab), so a link reproduces the view. A chart exports as PNG or SVG, the rows shown as
CSV. A Blick skipped for the run is in italics in the sidebar, unless a flag of the comparison
gives it a badge, and the sidebar counts the skipped Blicks at its foot; the overview says how many
the run skipped, and a card or page gives the reason instead of a chart.

The build directory is self-contained: copied to a laptop or a static host such as GitHub Pages, it
works from any sub-path. Opened from the file system it does not, because browsers do not let a
page read the files next to it; `blicket serve` is the way. `serve` answers with the viewer of the
installed blicket first, so an older copy in a build directory does not matter.

## Comparing two builds

```console
$ blicket diff .blicket/build/5d0c3f1e2a9b8c47 .blicket/build/8e21b7c04f6a9d35
baseline 5d0c3f1e2a9b8c47 · run 2026-10-22 · profile baseline · blicks at 0a6b858
current  8e21b7c04f6a9d35 · run 2026-10-23 · profile baseline · blicks at 0a6b858
1 Blick: 1 value
top movers: flows/steel_by_process 3.2% of scale (year=2021, process=EAF)
```

The output comes from a toy project with the first Blick above, built for the run above and for a
second run in which EAF reached 0.77 in 2021 instead of 0.7. The baseline comes first; each build
is a build directory or the id of a build in the store (below). `diff` matches the Blicks of the
two builds by id, or through `aliases=`, so a renamed Blick keeps its baseline, and compares their
tables through the plot type. A Blick gets a set of flags; none means unchanged. The summary
counts the Blicks per flag, leaving out the flags no Blick has, and names the Blicks of each flag
but `value`:

- `value`: the magnitude exceeds the Blick's tolerance (`tolerance` in `[tool.blicket]`, 1e-5 by
  default, or `tolerance=` on the Blick). The magnitude is the largest change of a row, relative
  to the scale of its panel, at most 1, and `None` when no row was compared; a row that one table
  lacks counts as 0. Here it is EAF's change in 2021, 0.07, relative to the highest stack of the
  panel, 2.17. Each value of a dimension that a control filters on has a scale of its own, and so
  has each value of a split of a Blick with `independent_y=True`. The top movers are the three
  Blicks flagged `value` with the largest magnitudes, as percents of the scale (`3.2% of scale`),
  with the row that changed most.
- `schema`: columns or dimension values appeared or vanished; the summary names them, five
  values per dimension at most. The magnitude covers the rows both tables have.
- `new`: the baseline has no table for the Blick; the summary says when the Blick did not build
  in the baseline, or was skipped there, and why.
- `removed`: a baseline Blick with a table that no current Blick claims by its id or aliases.
  When a module of the current build failed to import or another file-level error occurred, or a
  Blick has no usable id, nothing is removed, and the summary says why. A build line ends with
  `incomplete (Blicks missing)` when a module of that build failed to import or another
  file-level error occurred.
- `error`: the Blick did not build, its plot type is not one this blicket knows, or the plot type
  cannot compare the tables; the summary gives the reason.

A Blick that the current build skipped has no table to compare: it is `removed` when the baseline
has a table for it, also in an incomplete build, and the summary gives the first line of the
reason; otherwise it has no flag. Either way it is not unchanged: `skipped` counts the Blicks
skipped in the current build, whether or not they are also `removed`, as in
`4 Blicks: 1 unchanged · 3 skipped · 1 removed`.

`diff` exits 0 when it finds changes, which are an answer, not a failure; it exits 2 when a build
cannot be read, a Blick is flagged `error`, or removed Blicks were not judged. `--json` prints the
comparison instead, which is also its file format, read back by `bk.Comparison`: `spec`, the version
of blicket that compared (`blicket`, which names the formula of the magnitude), `created_at`, the
`baseline` and `current` builds (id, run, profile, time, `repository` with commit, branch and dirty
flag, and `incomplete`), `incomplete`, the reasons why removed Blicks were not judged, empty when
they were, and `blicks`, the current Blicks in the order of the manifest followed by the removed
ones, each with its `id`, `name`, `matched`, the id of the baseline Blick when it differs, as for a
Blick matched through an alias, `change` (the flags, the magnitude, the columns and values added and
removed, and `where`, the row that changed most; `bk.Change` describes the fields), `skipped`,
whether the current Blick was skipped, and `message`, why an `error` Blick has no table or was not
compared, that a `new` Blick did not build in the baseline or was skipped there, and why, or why a
skipped Blick has no table (`skipped: ...`). `baseline_data` and `baseline_hash`, the path of the
copied baseline table in the build directory and its hash in the baseline manifest, are set by
`check` (below) for the Blicks flagged `value` or `schema`, and are `null` otherwise.

`blicket push` copies a build into the store, where it is never changed again:

```console
$ blicket push .blicket/build/5d0c3f1e2a9b8c47
build 5d0c3f1e2a9b8c47 → .blicket/store/builds/5d0c3f1e2a9b8c47
```

Then `blicket diff 5d0c3f1e2a9b8c47 ...` finds it by id. The store is `.blicket/store` in the
project, or the directory `store` in `[tool.blicket]` names, relative to the project, such as a
directory on a cluster's file system that a team shares. It holds a build's manifest, tables and
the comparisons `check` wrote into it (below) under `builds/<id>/`, not the viewer, so
`blicket serve .blicket/store/builds/<id>` serves it with the installed one. Pushing a build that
is there already does nothing and says so (`(in the store already, left as it was; comparisons
are not added to a stored build)`), also when the build directory has gained comparisons since.
The first push gives `builds/` a `.gitignore`, so the builds never show up in `git status`.

## Checking a run

`blicket check` builds a run, finds its baseline in the store, compares the two as `diff` does,
and writes the comparison into the build directory:

```console
$ blicket check runs/2026-10-23
run 2026-10-23 · profile baseline · blicks at 0a6b858 · loaded in 12 ms
1 Blick: 1 built
build 8e21b7c04f6a9d35 → .blicket/build/8e21b7c04f6a9d35

baseline 5d0c3f1e2a9b8c47 · run 2026-10-22 · blicks at 0a6b858 · built 2026-10-22 09:14 UTC
vs baseline: 1 value
top movers: flows/steel_by_process 3.2% of scale (year=2021, process=EAF)
flagged: 1 of 1 Blick
comparison → .blicket/build/8e21b7c04f6a9d35/compare/5d0c3f1e2a9b8c47
```

The baseline is the newest build in the store (by the time it was built, on the baseline line)
of the run's profile whose commit, the one after "blicks at", is the current build's commit
or an ancestor of it in the repository holding the Blicks. The current build itself, builds whose
manifest says they are incomplete, and builds without a commit are never the baseline; builds with
uncommitted changes (`dirty`) are. On a branch this finds the branch's own previous pushed build,
so a change shows once and reads as unchanged at the next commit; `--against origin/main` keeps
comparing with main's builds until the merge, after which main finds the branch's builds, which
is what CI wants. `--against` takes a git ref, whose commit then replaces the current build's, or
names the baseline itself: the id of a build in the store or a build directory, of any profile.

Without a baseline, `check` says why (`baseline: none (no other pushed build of profile
baseline)`, or that none of the pushed builds is at the commit or its ancestors), writes no
comparison and exits 0: nothing to compare is not a change. It exits 2 with `error: no baseline:
…` when the baseline named by `--against` cannot be found, and when no pushed build of the profile
is on the history while the clone lacks the commits of some, since one of them may be the
baseline, as in a shallow clone; GitHub Actions clones one commit by default. The message names
those builds with their commits and says what helps: fetch the full history, with `git fetch
--unshallow` or `fetch-depth: 0` in GitHub Actions, or name the baseline with `--against <id>`.
When a baseline is found, newer builds at commits the clone lacks, such as one pushed from a
laptop at a commit never pushed to git, are skipped with a warning that names them. A build made
outside git records no commit; it needs `--against` once builds of its profile have been pushed.

The comparison goes into `compare/<baseline id>/` in the build directory: `comparison.json`, the
comparison file that `diff --json` prints, with `baseline_data` and `baseline_hash` set for the
Blicks flagged `value` or `schema`, and their baseline tables under `blicks/`, so that the build
directory shows what changed without the store. `compare/index.json` lists the baselines a build
was compared with, the latest written last. Checking against the same baseline again replaces its
directory. When `GITHUB_STEP_SUMMARY` is set, as in GitHub Actions, `check` appends a Markdown
summary to the file it names, which GitHub shows as the job's summary: the two builds, the
counts, a table of the flagged Blicks with their largest change as a percent of the chart's scale
and where they changed most, the values that appeared or vanished, the messages of the `new` and
`removed` Blicks, and the errors; or why there is no baseline. A skipped Blick that is removed has
the flags `removed (skipped)` there. A summary that cannot be appended is a warning.

`check` exits 0 when no Blick is flagged, 1 when one is flagged `value`, `schema`, `new` or
`removed`, and 2 on errors: a Blick in error, removed Blicks not judged, a baseline that cannot be
resolved. `--push` pushes the build afterwards, its comparisons included, whatever the exit code,
so that CI keeps what it checked; the push line names the comparisons. `--json` prints the
comparison file on stdout instead of the report, `null` without a baseline, and the report on
stderr. `--out` and `--project` work as for `build`.

`blicket serve` on a checked build directory shows the comparison. The overview names the baseline's
run in a selector over the baselines the build was checked against, the one checked last first, each
with its commit and time, and "No baseline", which shows the build as if it was never checked; a
baseline of the same run is not offered. Then come the counts per flag and the values and columns
that appeared or vanished across Blicks, and "Changed since the baseline": the flagged Blicks ranked
as `check` ranks its movers, the first six as small charts and the others as a list under a line
such as "4 more changed", each with a badge such as `Δ 2.1%` (the largest change, as a percent of
the chart's scale), `schema` or `new`, which the sidebar shows too. A card's caption names the panel
it shows and the rest of the row that changed most: `Region: SSA · largest change at Flow: Primary,
Time: 2100 · baseline faded`; a Sankey diagram's says nothing of the baseline.

A Blick's page says what changed: its flags, the largest change, where it is and against which
baseline (`largest change 2.1% of the chart's scale at Region: SSA, Flow: Primary, Time: 2100,
against run …`), with a "Show where" button when that is another filter setting, and the values or
columns that appeared or vanished. "Compare with baseline", on by default, draws the baseline
behind the chart, faded and broader in each series' colour: wide lines behind the lines, the
baseline's stack as faded areas under the current one drawn as lines, wider bars behind the bars.
The tooltip shows the baseline's number where it differs, as `−60.1M (baseline −48.1M)`. A Sankey
diagram has no baseline behind it, since two layouts do not line up; a link's tooltip gives the
baseline's value and the change.

While the switch is on, two charts under the chart, in its panels, colours and legend, draw the
change of each row against the baseline, in the Blick's unit and relative to the baseline's value:
lines, grouped bars for bars, and stacked bars for the change of stacked bars, gains up and losses
down; for a Sankey diagram, a bar per link that changed, labelled `source → target`, the largest
change first. As in `check`, a row missing from one table counts as 0; a row with a dimension
value only one table has gets no change drawn, and when the selection has nothing to compare, the
page says so instead of drawing the two charts. A build that was never checked looks as before.

## Developing Blicks

`blicket dev` checks a run as `check` does, without pushing it, then serves the build as `serve`
does and keeps the run in memory for the [Blick builder](#the-blick-builder):

```console
$ blicket dev runs/2026-10-23
run 2026-10-23 · profile baseline · blicks at 0a6b858 · loaded in 12 ms
1 Blick: 1 built
build 8e21b7c04f6a9d35 → .blicket/build/8e21b7c04f6a9d35

baseline 5d0c3f1e2a9b8c47 · run 2026-10-22 · blicks at 0a6b858 · built 2026-10-22 09:14 UTC
vs baseline: 1 value
top movers: flows/steel_by_process 3.2% of scale (year=2021, process=EAF)
flagged: 1 of 1 Blick
comparison → .blicket/build/8e21b7c04f6a9d35/compare/5d0c3f1e2a9b8c47
builder: 1 quantity, 2 dimensions
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
```

The line `builder:` says whether the Blick builder is on, with the size of the project's dataset,
or why it is off. `dev` takes `--against`, `--out` and `--project` as `check` does and `--port`,
`--host` and `--open` as `serve` does; it binds the port before loading the run, so a taken `--port`
fails at once. It exits 0 when stopped with Ctrl-C, whatever the build holds: flagged Blicks and
Blicks that fail are in the report and the viewer, and a baseline that `--against` names but cannot
be found is in the report. Only a session that cannot start exits 2, as `check` would: an invalid
`[tool.blicket]`, a loader that raises, no viewer, a taken `--port`, no run given and no `runs`
to pick one from. `-v` shows tracebacks, of the Blicks at the start, of a run picked in the viewer
that cannot be loaded, and of the builder's queries while the session runs. A project with a loader
and no Blick yet is no error in `dev`: the report says `no Blicks yet`, the build holds no Blick and
is complete, and the overview offers the builder, as the foot of the Blick list always does. The
viewer knows it is served by `dev` from the header `Blicket-Dev: 1` on `manifest.json`, which `dev`
answers from memory, and with a 404 while it serves no run yet.

`blicket` without a command is `blicket dev`, and so is `blicket` followed by an option of `dev` or
a run path: `blicket runs/2026-10-23` is `blicket dev runs/2026-10-23`, `blicket --port 8800` is
`blicket dev --port 8800`. A first argument that is neither a command nor an existing path, and
has no `/`, stays an unknown command (`blicket lst` says `No such command 'lst'. Did you mean
'list'?`), so a run folder named like a command takes `blicket ./list`. Options before a command
stay options blicket does not have: `blicket --port 8000 serve` says `No such option: --port
(options go after the command: blicket serve --port 8000)`, while the value of an option of `dev`
is no command (`blicket --out build runs/x` is `blicket dev --out build runs/x`).
`blicket --help` (or `-h`) and `blicket --version` are blicket's own; `blicket` alone outside a
project says that `blicket --help` lists the commands.

### Picking the run in the viewer

Started without a run, `dev` offers the project's run folders in the viewer, those that the globs
of `runs` in `[tool.blicket]` match:

```toml
[tool.blicket]
runs = ["runs/*"]  # folders the run picker offers; default: none
```

```console
$ blicket
runs: 2 in runs/*
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
pick a run in the viewer, or pass one: blicket RUN_PATH
```

The globs are relative to the project root (`..` and `**` allowed) and match directories only,
hidden ones left out; a link to a folder is listed under its own name, and a folder matched twice
once. The viewer opens on the picker, which lists the folders newest change first, each with its
name and how long ago it changed, its path as the tooltip. You tick one, or several for a
loader that combines them into one run (`Load 2 runs as one`), and press Load: `dev` loads, builds
and checks the run as it does one given on the command line, prints the report under the time and
the paths picked, and the viewer starts afresh on the overview of the build. A run that cannot be
loaded leaves the picker as it was, with the error under the list, which the terminal prints as
well (`error: cannot load <paths>: ...`); you pick another, and a folder gone since the list
came asks for a Refresh. The run is picked once per session; another one takes a restart. `runs`
is read when `dev` starts, and the folders are looked for afresh whenever the picker lists them,
so a model run that lands while `dev` waits shows on Refresh. Without `runs`, `blicket` without a
run exits 2 with `error: no run to serve; pass one (blicket RUN_PATH), or set runs =
["output/*"] in [tool.blicket] to pick one in the viewer`. A `runs` that matches no folder yet
serves the picker all the same, empty, with Refresh.

## The Blick builder

In `blicket dev`, "Build a Blick" at the foot of the Blick list opens the builder, which composes an
ad hoc Blick from the run: you pick a quantity of the model, a plot type, what each dimension does
(an axis or a colour, panels, a filter, or summed over) and, for each dimension kept, the values to
keep, and the chart follows. A dimension on a filter is shown one value at a time, picked above the
chart as on a Blick's page. The dev server runs the query in Python and checks the table as it
checks a Blick's; the chart, its controls, the data tab and the exports are those of a Blick's page,
and a line under the title says what was summed and which values are kept. Picking more quantities
of one unit puts them into one chart, told apart by a dimension `Quantity` that holds their titles,
on colour at first; summed over `Quantity`, they add up. The dimension on `x` can only swap with one
on another channel, since a chart needs an `x`. A Sankey diagram starts with nothing on `source` and
`target`, and time as a filter; the chart waits until both have a dimension, and from then on they
can only swap. A query that cannot run, such as one that sums a
quantity that is not additive, or one whose table exceeds 100,000 rows (the problem names the
dimensions and their sizes), shows its problem above the last chart, which stays dimmed until the
next query runs. The builder's state is in the URL
(`#/builder?_q=flows/steel&_c.x=year&_keep=process&_split=process`), so a link reproduces the chart
for as long as the session runs; nothing is saved, and a Blick worth keeping is written as code.

The builder reads the run through a dataset: `dataset(run)` next to `load_run` in
`blicketconf.py`, or in the module that `loader` names, returns one. The stock dataset is
`bk.Frames`, tables that blicket filters and sums itself. For the run of
[Building a run](#building-a-run):

```python
# blicketconf.py, below load_run
def dataset(run):
    frames = bk.Frames()
    frames.add("flows/steel", run["flows"], unit="t per year")
    return frames
```

`add` takes the quantity's name and its table, a long table as a transformation returns one: the
dimensions as columns and one measure column, the last. The table may also be a function that
returns it, called once the quantity is first charted, which leaves a model's arrays as they are
until then. The other arguments are the quantity's: a `title` for the list and the chart (the name
without its `group` by default), the `unit` if known, `dimensions` to name the dimension columns
when the measure is not the last, `additive`, and a `group` the list groups it under. `additive`
is true by default; a rate, share or price sets it false, and the builder then never sums it over
a dimension, so its dimensions start as filters. The dimensions come from the tables: the type
from the column (`string`, `integer`, `boolean`, `date` or `datetime`), the values sorted, strings
in the order they appear; `bk.Frames(dimensions=[bk.Dimension(name="process", dtype="string",
values=["BOF", "EAF"])])` gives one its order instead. A subclass that overrides `select` sums its
own way, say with a model's exact aggregation; `self.frame(quantity)` is the table as polars. The
last eight tables read stay converted.

Any object with three methods is a dataset, as `bk.Dataset` spells out:

- `quantities()` lists the quantities as `bk.Quantity`: a `name` unique in the dataset, `title`,
  `unit`, the `dimensions` it has, `additive` and `group`, as above.
- `dimensions()` lists every dimension once, as `bk.Dimension`: its name, its `dtype` and its
  values in display order.
- `select(quantity, keep, values)` returns the table of one quantity, as a transformation returns
  one: the `keep` dimensions as columns and one measure column, its rows restricted to `values` for
  the dimensions named there, and summed over the quantity's other dimensions; with no `keep`, one
  row, the total. A value the quantity lacks gives no rows. blicket asks to sum only an additive
  quantity, filters the kept dimensions once more, and checks the table.

`dev` reads `quantities()` and `dimensions()` once, when it starts, and checks them: names unique,
dimensions known, values of their dimension's type. A project without `dataset` has no builder,
and the builder's page says what to add; a `dataset(run)` that raises, or returns something else
than such an object, is a warning at start, and the builder is off for the session.

## Examples

[examples/remind-mfa](https://github.com/tobiasdiez/blicket/tree/main/examples/remind-mfa) is a
project on runs of remind-mfa's plastics model: a loader that unpickles a run, and ten Blicks,
mostly ported from remind-mfa's own figures, which return flodym arrays and pandas frames. It has
its own uv environment with remind-mfa from a checkout next to this repository. The runs are not in
the repository, and producing one needs remind-mfa's input data, which is not public; the example's
README says how to set it up and build a run.

[examples/remind](https://github.com/tobiasdiez/blicket/tree/main/examples/remind) is a project on
runs of the integrated assessment model REMIND: a loader that reads the reporting (mif files) of
several REMIND output folders into one run, the scenario as a dimension, and 20 Blicks that carry
the "Summary" chapter of REMIND's `compareScenarios` report, so that a week of model development
shows as flagged Blicks. Its environment needs only blicket and pyyaml. The runs are REMIND's weekly
test runs on the PIK cluster, not in the repository; the example's README says how to fetch them,
build, check and look at them.

## Development

In a clone of the repository (`git clone https://github.com/tobiasdiez/blicket`):

```console
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

The viewer is a Nuxt app in [viewer/](https://github.com/tobiasdiez/blicket/tree/main/viewer); its
README says how to work on it, with Node and pnpm. A development installation has no viewer of its
own: generate one and point `BLICKET_VIEWER` at it, as an absolute path or relative to where blicket
runs, for instance from `examples/remind-mfa`:

```console
$ (cd ../../viewer && pnpm install && pnpm generate)
$ export BLICKET_VIEWER=../../viewer/.output/public
```

`blicket build` then copies it into build directories and `blicket serve` and `blicket dev` serve
it; the three need a viewer and stop with an error without one. `BLICKET_VIEWER` wins over a
bundled viewer, so a new viewer can be tried with an installed wheel. The meson option `viewer`
(in `meson.options`) bundles the viewer: with it, as in
[From the repository](#from-the-repository), the build runs `pnpm install --frozen-lockfile` and
`pnpm generate` and installs the site as `blicket/_viewer`, and it fails when pnpm is missing or
cannot fetch. The option is off by default, so `uv sync` and the editable install need no Node,
and a wheel built without it, as from the sdist on PyPI, has no viewer.

blicket is built with meson-python without build isolation, so that the editable install made by
`uv sync` can rebuild on import. The build tools therefore live in the `build` dependency group,
which is installed by default; `uv sync --no-default-groups` is not supported for development.
Every module under `src/blicket` must be listed in `meson.build` (a test checks this). The
`cache-keys` in `[tool.uv]`, there for the example's path dependency, also make `uv run` reinstall
the editable package after a source edit, which takes about half a second. `uv build` packs only
committed files; use `uv build --wheel` to try uncommitted work.

Releases are made by [release-please](https://github.com/googleapis/release-please) from the
[Conventional Commits](https://www.conventionalcommits.org/) on `main`: it keeps a release pull
request open that sets the next version in `pyproject.toml` and the three `uv.lock` files and adds
the commits to `CHANGELOG.md` under their type (`feat`, `fix`, `docs`, `chore`). Merging that pull
request tags the release, and the release workflow builds the sdist, and the wheel with the
viewer, checks that the installed wheel finds the viewer, and publishes both to PyPI.

