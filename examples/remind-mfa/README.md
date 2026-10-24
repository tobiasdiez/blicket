# remind-mfa Blicks

A blicket project on runs of [remind-mfa](https://github.com/pik-piam/remind-mfa)'s plastics model:
a loader that unpickles a run and ten [Blicks](../../README.md), mostly ported from remind-mfa's own
plastics figures. The runs are not in this repository, and producing one needs remind-mfa's input
data, which is not public (it lives on the PIK cluster).

## Prerequisites

- [uv](https://docs.astral.sh/uv/); it fetches Python 3.14 if the machine lacks it.
- remind-mfa checked out next to the blicket checkout, which the example depends on by path. Clone
  the fork the example runs were made from, run in the blicket checkout so that the two checkouts
  sit side by side:

  ```console
  $ git clone https://github.com/tobiasdiez/remind-mfa ../remind-mfa
  ```

- Runs. A run is the folder remind-mfa's pickle export writes,
  `<prefix>_<model>_<scenario>_<regions>/` with a `model.pickle`. They go into `data_out/` at the
  root of the blicket checkout (`mkdir data_out`), which git ignores; any other place works too,
  since `blicket build` takes the run folder as an argument.

A run loads only with the remind-mfa commit that wrote it: the pickle holds remind-mfa's own
classes, and the pickle does not record that commit. The example runs come with
`data_out/RUNS.md`, which names it (`a7c389a`) and the config layers, `default` and `blicket`.
Check out that commit in `../remind-mfa` before building; the loader says so when a run does not
unpickle. Unpickling runs code from the checkout, so build only runs you trust.

## Producing a run

With remind-mfa's input data in place (remind-mfa's README says how to fetch it), in
`../remind-mfa`, write the layer `config/blicket.toml`, which turns the figures off (the pickle
export is on in the default config):

```toml
[base.visualization]
do_visualize = false
```

Then run the plastics model and move the run folder it writes into `data_out/`:

```console
$ uv run remind_mfa.py --config default --config blicket --model plastics
$ mv data_out/<prefix>_plastics_SSP2_h12 ../blicket/data_out/
```

This reproduces the layers `data_out/RUNS.md` names.

## The project

```
pyproject.toml          [tool.blicket], empty: the defaults apply
blicketconf.py          load_run, the loader; found by convention, like pytest's conftest.py
blicks/                 the Blicks
```

`blicketconf.py` is the loader: it unpickles `model.pickle`, takes the run id from the folder
name and the profile, such as `plastics_SSP2_h12`, from the run's config, and rejects runs of
other models. A project whose loader lives inside its own package names it instead with
`loader = "package.module:function"` under `[tool.blicket]`. `blicks/` holds the Blicks, one
group per file:

```
blicks/drivers.py       GDP per capita, scenario rates, polymer splits
blicks/flows.py         consumption, production by polymer and by source, production versus net
                        imports versus consumption, end-use split
blicks/stocks.py        in-use stock by region and by end use
```

`blicket list` prints the groups in this alphabetical order. The Blicks use remind-mfa's dimension
names as the pickle holds them (`Time`, `Region`, `End Use`, `Polymer`) and return flodym arrays,
or pandas frames for the tables that combine several flows. They import remind-mfa and flodym
under `TYPE_CHECKING`, for annotations only, so `blicket list` does not import remind-mfa.

## Environment

```console
$ cd examples/remind-mfa
$ uv sync
$ uv run blicket list
```

`blicket list` needs no run; it lists the three groups and ten Blicks.

The environment holds blicket and remind-mfa together, since a run unpickles only where
remind-mfa is importable. remind-mfa is installed editable, so it is the code checked out in
`../remind-mfa`. remind-mfa itself does not use polars, but its dependency ixmp4 pulls in
scse-toolkit, which pins polars below 2.0; the `override-dependencies` in `pyproject.toml` lifts
that pin for blicket, in this environment only.

`uv.lock` is committed. It pins remind-mfa's dependency metadata, not a commit: after checking out
a commit whose `pyproject.toml` differs, `uv run` rewrites `uv.lock` (do not commit that),
`uv run --frozen` uses the lock as it is, and `uv run --locked` fails instead.

## Building

```console
$ uv run blicket build ../../data_out/2026-10-24--01-25-28_plastics_SSP2_h12
run 2026-10-24--01-25-28_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at e46088d · loaded in 666 ms
10 Blicks: 10 built
build 804f5a5bea3deb5d → .blicket/build/804f5a5bea3deb5d
```

"loaded in" includes importing remind-mfa. The commit after "blicks at" is the one of the blicket
repository, which holds the Blicks, not remind-mfa's, and `(dirty)` after it marks uncommitted
changes there; commit and build id differ from the ones shown here. Building the same run again
prints `(built before, left as it was)` after the build directory. The build directory holds one
Parquet file per Blick; to look at a table, with the id from the build line:

```console
$ uv run python -c "import polars as pl; print(pl.read_parquet('.blicket/build/<id>/blicks/flows/production_by_polymer.parquet'))"
```

`uv run blicket list --json` prints each Blick's description, no run needed; `blicket build
--json` prints the manifest, which adds each table's schema and the values of each dimension.

CI does not build this example: it needs the remind-mfa checkout and the runs, which are not in
the repository.

## Developing blicket

blicket is installed from `../..`, not editable. `uv run` reinstalls it after a change to a `.py`
file under blicket's `src/`, to its `pyproject.toml` or its `meson.build`; after a change to any
other file under `src/`, `uv sync --reinstall-package blicket` does.
