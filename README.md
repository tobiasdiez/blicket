# blicket

Storybook for scientific model outputs. A *Blick* is a named view on a model run: a function that
turns the run into a table, and how to plot that table. blicket discovers a project's Blicks,
lists them with every problem it finds in their definitions, builds their tables for a model run,
and shows them in a web viewer. The idea behind it is in
[docs/concept.md](docs/concept.md), the design in [docs/architecture.md](docs/architecture.md).

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

`unit=` names the unit of the measure; the viewer puts it on the y axis and in the tooltips.
`independent_y=True` is for Blicks whose panels differ by orders of magnitude: each panel of a
split then gets its own y axis by default; otherwise the panels share one, and the viewer's toggle
changes either. Both are part of the Blick's definition in the manifest.

```console
$ blicket list
flows  Material flows  [mfa]
  flows/steel_by_process   Steel flows by process   stacked_area

1 group · 1 Blick
```

`blicket list` looks for the project by walking up from the working directory; `--project PATH`
names the project directory instead. `-v` shows tracebacks, `--json` prints the report as JSON.

Exit codes, for every command: 0 success (for `serve`, stopped with Ctrl-C), 2 errors of any kind,
a Blick that fails to build included.

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
blicket derives for them; it covers the Blicks' definitions, their tables and problems, the
settings, the run's profile and fingerprint, and the commit. Building the same run with the same
Blicks at the same commit gives the same id again and leaves the directory as it is. A
transformation that raises, or a table that fails a check, is listed under `errors` like a problem
of `blicket list`; the other Blicks are built all the same, and the exit code is 2. `--json`
prints the manifest, `--out DIR` puts the build directory into `DIR` instead of `.blicket/build`,
and `-v` shows tracebacks. blicket gives `.blicket/` a `.gitignore`, so builds never show up in
`git status`. A build of the same id keeps its manifest and tables; only the files of its copy of
the viewer are replaced when it differs from the installed one (`(built before, viewer
refreshed)`).

## Looking at a build

```console
$ blicket serve .blicket/build/5d0c3f1e2a9b8c47
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
```

Without an argument, `blicket serve` serves the build of the project made last; `--port`,
`--host` and `--open` (open the browser) do what they say. It serves nothing outside the build
directory and the viewer. The overview lists the Blicks by group with a
search box; a Blick's page shows its chart, its controls and a data tab with the rows shown.
Every dimension that the plot does not bind to a channel gets a control: a filter that shows one
value at a time, starting at the first value in display order or at `defaults={dim: value}`, or,
with `controls={dim: "split"}`, one panel per value. The control state is in the URL
(`#/blick/flows/steel_by_process?region=EU&_split=scenario`, `_y` for the y axes, `_tab=data` for
the data tab), so a link reproduces the view. A chart exports as PNG or SVG, the rows shown as
CSV.

The build directory is self-contained: copied to a laptop or a static host such as GitHub Pages, it
works from any sub-path. Opened from the file system it does not, because browsers do not let a
page read the files next to it; `blicket serve` is the way. `serve` answers with the viewer of the
installed blicket first, so an older copy in a build directory does not matter.

## Comparing two tables

The plot types compare a Blick's tables in two builds. The output below comes from a toy project
with the one Blick above, built for the run above and for a second run in which EAF reached 0.77
in 2021 instead of 0.7; a project prints a line per Blick.

```python
from pathlib import Path

import polars as pl

import blicket as bk

old = Path(".blicket/build/<baseline build id>")  # placeholders: two build directories
new = Path(".blicket/build/<current build id>")
before = {entry.id: entry for entry in bk.manifest.read(old).blicks}
for entry in bk.manifest.read(new).blicks:
    previous = before.get(entry.id)
    if entry.data is None or previous is None or previous.data is None:
        continue  # the Blick failed, or has no table in the baseline
    plot = entry.definition.plot
    baseline = pl.read_parquet(old / previous.data)
    current = pl.read_parquet(new / entry.data)
    change = bk.plots.builtin(plot.type).diff(baseline, current, plot.mapping, entry.panels)
    print(entry.id, sorted(change.flags), change.magnitude, change.where)
```

```console
flows/steel_by_process [] 0.03225806451612916 {'year': 2021, 'process': 'EAF'}
```

The magnitude is EAF's change in 2021, 0.07, relative to the highest stack of the panel, 2.17.
`entry.panels` are the dimensions whose values each get their own scale: the filters, and the
splits of a Blick with `independent_y=True`. `diff` sets the flag `schema` and never `value`: a
Blick changed when the magnitude exceeds its tolerance (`tolerance` in `[tool.blicket]`, 1e-5 by
default, or `tolerance=` on the Blick). The magnitude is `None` when no row was compared, and a
row that one table lacks counts as 0. `bk.Change` describes the fields.

## Example

[examples/remind-mfa](examples/remind-mfa) is a project on runs of remind-mfa's plastics model: a
loader that unpickles a run, and ten Blicks, mostly ported from remind-mfa's own figures, which
return flodym arrays and pandas frames. It has its own uv environment with remind-mfa from a
checkout next to this repository. The runs are not in the repository, and producing one needs
remind-mfa's input data, which is not public; the example's README says how to set it up and build
a run.

## Development

```console
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

The viewer is a Nuxt app in [viewer/](viewer); its README says how to work on it, with Node and
pnpm. A development installation has no viewer of its own: generate one and point
`BLICKET_VIEWER` at it, as an absolute path or relative to where blicket runs, for instance from
`examples/remind-mfa`:

```console
$ (cd ../../viewer && pnpm install && pnpm generate)
$ export BLICKET_VIEWER=../../viewer/.output/public
```

`blicket build` then copies it into build directories and `blicket serve` serves it; both need a
viewer and stop with an error without one. `BLICKET_VIEWER` wins over a bundled viewer, so a new
viewer can be tried with a release install. The release wheel bundles the viewer: after
`uv sync`, `uv build --wheel -Csetup-args=-Dviewer=enabled` runs `pnpm install --frozen-lockfile`
and `pnpm generate` and installs the site as `blicket/_viewer`. The meson option `viewer` (in
`meson.options`) is off by default, so `uv sync` and the editable install need no Node; a wheel
built from the sdist without the option, or without network for pnpm, has no viewer.

blicket is built with meson-python without build isolation, so that the editable install made by
`uv sync` can rebuild on import. The build tools therefore live in the `build` dependency group,
which is installed by default; `uv sync --no-default-groups` is not supported for development.
Every module under `src/blicket` must be listed in `meson.build` (a test checks this). The
`cache-keys` in `[tool.uv]`, there for the example's path dependency, also make `uv run` reinstall
the editable package after a source edit, which takes about half a second. `uv build` packs only
committed files; use `uv build --wheel` to try uncommitted work.

## License

MIT
