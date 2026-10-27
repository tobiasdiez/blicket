# remind-mfa Blicks

A blicket project on runs of [remind-mfa](https://github.com/pik-piam/remind-mfa)'s plastics model:
a loader that unpickles a run and ten [Blicks](../../README.md), mostly ported from remind-mfa's own
plastics figures. The runs are not in this repository, and producing one needs remind-mfa's input
data, which is not public (it lives on the PIK cluster).

## Prerequisites

- [uv](https://docs.astral.sh/uv/); it fetches Python 3.14 if the machine lacks it.
- Node 24 or newer and [pnpm](https://pnpm.io/installation), to generate the viewer that `build`
  copies into every build directory (see [Building](#building)); `blicket list` needs neither.
- remind-mfa checked out next to the blicket checkout, which the example depends on by path.
  Clone it from the blicket checkout, so that the two sit side by side:

  ```console
  $ git clone https://github.com/pik-piam/remind-mfa ../remind-mfa
  ```

- Runs. A run is the folder remind-mfa's pickle export writes,
  `<prefix>_<model>_<scenario>_<regions>/` with a `model.pickle`. They go into `data_out/` at the
  root of the blicket checkout (`mkdir data_out`), which git ignores; any other place works too,
  since `blicket build` takes the run folder as an argument. [Producing a run](#producing-a-run)
  says how to make one.

The example runs are of two generations: three of 2026-10-24, made at remind-mfa `a7c389a` on
input data 2.8.0, and two of 2026-10-26, made at `710302d`, eight commits later, on input data
2.9.1. Below, a run goes by the seconds of its timestamp: run 28 is
`2026-10-24--01-25-28_plastics_SSP2_h12`, run 00 is `2026-10-26--11-25-00_plastics_SSP2_h12`.
Runs 31 and 13 are unchanged reruns of runs 28 and 00; run 34 has `collection_rate` scaled by
0.9. `data_out/RUNS.md` is a note kept next to the runs, outside the repository like the runs
themselves; it names each run's commit, input data revision and config layers, `default` and
`blicket`.

A run loads with the remind-mfa commit that wrote it, or with one whose classes still match: the
pickle holds remind-mfa's own classes and does not record the commit. The runs of `a7c389a` load
at `710302d` and give the same tables there. When a run does not unpickle, the loader says so;
check out the commit `RUNS.md` names, as in `git -C ../remind-mfa checkout a7c389a`. Unpickling
runs code from the checkout, so build only runs you trust.

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

## Producing a run

Building and comparing need runs, and producing one needs the input data from the PIK cluster. In
`../remind-mfa`:

1. Check out the commit the run is to come from; a fresh clone sits at `main`:

   ```console
   $ git checkout 710302d
   ```

   `710302d` made the second generation of the example runs, `a7c389a` the first.

2. Fetch the input data. remind-mfa reads it from an archive in `madrat_output/`, of the revision
   that `input_data_revision` in `config/default.toml` names: 2.8.0 at `a7c389a`, 2.9.1 at
   `710302d`. `<host>` is the cluster's SSH target, `user@host` or a host alias from
   `~/.ssh/config`, as remind-mfa's README says:

   ```console
   $ uv run scripts/fetch_from_hpc.py mfa-archive --config default <host>
   ```

3. Write the layer `config/blicket.toml`, which turns the figures off (the pickle export is on in
   the default config):

   ```toml
   [base.visualization]
   do_visualize = false
   ```

4. Run the plastics model:

   ```console
   $ uv run remind_mfa --config default --config blicket --model plastics
   ```

   remind-mfa runs as a package; at `a7c389a` and before, it ran as the script `remind_mfa.py`,
   with the same options. A run takes a few seconds; the first one on a new input data revision
   unpacks the archive into `data_in/`.

5. Move the run folder it wrote into `data_out/`:

   ```console
   $ mv data_out/<prefix>_plastics_SSP2_h12 ../blicket/data_out/
   ```

The layers `default` and `blicket` are the ones `RUNS.md` names.

## Building

`build` copies the viewer into every build directory, and blicket installed from a checkout has
none of its own, so `build` and `serve` stop with an error until you generate one and set
`BLICKET_VIEWER` as the [root README](../../README.md#development) shows. Then:

```console
$ uv run blicket build ../../data_out/2026-10-24--01-25-28_plastics_SSP2_h12
run 2026-10-24--01-25-28_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at e7a2a23 (dirty) · loaded in 949 ms
10 Blicks: 10 built
build dfa92620f1ae4726 → .blicket/build/dfa92620f1ae4726
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

## Comparing runs

With runs 28, 31 and 34 built, `diff` compares two of them Blick by Blick, here run 28 with run
34:

```console
$ uv run blicket diff .blicket/build/<id of run 28> .blicket/build/<id of run 34>
baseline bfa7f61fc79b65c2 · run 2026-10-24--01-25-28_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at fe4d2dd (dirty)
current  34247dcb88fd54c3 · run 2026-10-24--01-25-34_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at fe4d2dd (dirty)
10 Blicks: 9 unchanged · 1 value
top movers: flows/production_by_source 2.1% of scale (Flow=Primary, Time=2100, Region=SSA)
```

The lower collection rate shows in production by source only: primary production in SSA in 2100
changed by 2.1% of the highest stack of the chart, whose regions share one scale as they share the
y axis. Run 28 against run 31, an unchanged rerun, gives `10 Blicks: 10 unchanged`.
`uv run blicket push .blicket/build/<id>` copies a build into `.blicket/store`, after which `diff`
takes its id alone; `--json` prints the comparison as JSON.

## Checking a run

`check` builds a run and compares it with its baseline in one go: the newest pushed build of the
run's profile whose commit is the one checked out or an ancestor of it. With the builds of runs 28,
31 and 34 pushed, checking run 34 finds the newest of the pushed builds, here run 28's (commits
and ids differ on your checkout):

```console
$ uv run blicket check ../../data_out/2026-10-24--01-25-34_plastics_SSP2_h12
run 2026-10-24--01-25-34_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 604e20c (dirty) · loaded in 953 ms
10 Blicks: 10 built
build c6317235ed070309 → .blicket/build/c6317235ed070309

baseline bfa7f61fc79b65c2 · run 2026-10-24--01-25-28_plastics_SSP2_h12 · blicks at fe4d2dd (dirty) · built 2026-10-24 13:28 UTC
vs baseline: 9 unchanged · 1 value
top movers: flows/production_by_source 2.1% of scale (Flow=Primary, Time=2100, Region=SSA)
flagged: 1 of 10 Blicks
comparison → .blicket/build/c6317235ed070309/compare/bfa7f61fc79b65c2
```

It exits 1, since a Blick is flagged. The comparison in `compare/bfa7f61fc79b65c2/` holds
`comparison.json` and run 28's table of production by source, 35 KB next to the build's 594 KB
of manifest and tables. `--against <branch>` searches that branch's history instead of the commit
checked out, `--against <id>` compares with that build, and `--push` pushes the build afterwards,
its comparisons included; without a pushed build of the profile, `check` says `baseline: none
(...)` and exits 0.

A profile does not know the model version, so the newest pushed build is the baseline whatever
run produced it: with run 00's build the newest, checking run 13 finds it, and run 34 is compared
with run 00 unless `--against` names another build. Checking run 13 then reports `vs baseline:
10 unchanged` and exits 0, an unchanged rerun again; checking run 34 reports the model change, the
data change and the lower `collection_rate` together. Between the generations alone, `diff` of
run 28's build and run 00's, both pushed, so that their ids alone name them, gives `10 Blicks: 3
unchanged · 7 value`: the drivers stay as they were, and every flow and stock Blick moves, by 13%
to 22% of the chart's scale, the most in SSA in 2100.

## Looking at a build

`uv run blicket serve` serves the build made last; a build made with an older viewer gets the
current one on its next `build`.

The Blicks give their units with `unit=`. The flows split by Region into one panel per region on a
shared y axis, so the regions compare by size; "Scenario rates" shows one `Parameter` at a time,
starting at `collection_rate`, and its panels, when split, each have their own y axis
(`independent_y=True`), since the rates differ by orders of magnitude.

## Developing blicket

blicket is installed from `../..`, not editable. `uv run` reinstalls it after a change to a `.py`
file under blicket's `src/`, to its `pyproject.toml` or its `meson.build`; after a change to any
other file under `src/`, `uv sync --reinstall-package blicket` does.
