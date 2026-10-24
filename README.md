# blicket

Storybook for scientific model outputs. A *Blick* is a named view on a model run: a function that
turns the run into a table, and how to plot that table. blicket discovers a project's Blicks,
lists them with every problem it finds in their definitions, and builds their tables for a model
run. The idea behind it is in
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
    plot=bk.plots.stacked_area(x="year", y="value", color="process"),
)
def steel_by_process(run):
    return run["flows"]
```

```console
$ blicket list
flows  Material flows  [mfa]
  flows/steel_by_process   Steel flows by process   stacked_area

1 group · 1 Blick
```

`blicket list` looks for the project by walking up from the working directory; `--project PATH`
names the project directory instead. Exit codes: 0 success, 2 errors of any kind. `-v` shows
tracebacks, `--json` prints the report as JSON.

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
`dims=` overrides the other way. Every measure must be bound to a plot channel, and no two rows may
share their dimension values, which become strings, integers, booleans, dates or datetimes.

```console
$ blicket build runs/2026-10-22
run 2026-10-22 · profile baseline · blicks at 0a6b858 · loaded in 12 ms
1 Blick: 1 built
build 5d0c3f1e2a9b8c47 → .blicket/build/5d0c3f1e2a9b8c47
```

The first line names the run and its profile, the commit of the repository that holds the Blicks
(`blicks at`, marked `(dirty)` with uncommitted changes), and the loader's wall time.

The build directory holds `manifest.json`, which describes the run, the project's settings and git
state, every Blick's definition, table schema and problems, and one `blicks/<id>.parquet` per Blick
that built. The build id is a hash of the manifest without the timestamps and timings, the blicket
version, tracebacks, the run's id, paths and model checkout, the repository's branch and dirty flag,
and where the Blicks are defined; it covers the Blicks, their tables and problems, the settings, the
run's profile and fingerprint, and the commit. Building the same run with the same Blicks at the
same commit gives the same id again and leaves the directory as it is. A transformation that raises,
or a table that fails a check, is listed under `errors` like a problem of `blicket list`; the other
Blicks are built all the same, and the exit code is 2. `--json` prints the manifest, `--out DIR`
puts the build directory into `DIR` instead of `.blicket/build`, and `-v` shows tracebacks. blicket
gives `.blicket/` a `.gitignore`, so builds never show up in `git status`.

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

blicket is built with meson-python without build isolation, so that the editable install made by
`uv sync` can rebuild on import. The build tools therefore live in the `build` dependency group,
which is installed by default; `uv sync --no-default-groups` is not supported for development.
Every module under `src/blicket` must be listed in `meson.build` (a test checks this). The
`cache-keys` in `[tool.uv]`, there for the example's path dependency, also make `uv run` reinstall
the editable package after a source edit, which takes about half a second. `uv build` packs only
committed files; use `uv build --wheel` to try uncommitted work.

## License

MIT
