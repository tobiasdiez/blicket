# Coherence example

A small blicket project that shows [expectations and checks](../../README.md#expectations-and-checks)
at work: three Blicks with an expectation and three checks on a made-up model of a steel cycle,
with two runs in the repository, one coherent and one not. It needs no data from elsewhere.

## Quick start

From the blicket checkout, with [uv](https://docs.astral.sh/uv/), Node 24 or newer and
[pnpm](https://pnpm.io/installation):

```console
$ cd examples/coherence
$ uv sync
$ (cd ../../viewer && pnpm install && pnpm generate)
$ export BLICKET_VIEWER=../../viewer/.output/public
$ uv run blicket check runs/baseline --push    # coherent: exits 0
$ uv run blicket check runs/changed            # two expectations fail: exits 1
$ uv run blicket serve
```

`blicket list` needs neither a run nor the viewer, and prints the Blicks and checks with their
expectations as declared.

## The project

```
pyproject.toml          [tool.blicket]: runs, the folders the run picker offers
blicketconf.py          load_run: a run is a folder of CSV files, each a table
blicks/cycle.py         the Blicks, each with expect=
blicks/checks.py        the checks
runs/baseline/          a coherent run
runs/changed/           a run after a careless change to the model
make_runs.py            writes the two runs: python make_runs.py
```

The model has three regions, North, South and East, and the years 2020 to 2030, in Mt per year.
Steel is made from ore and from collected scrap, goes into use, leaves use as scrap, and the scrap
that is not recycled goes to landfill. A run holds `flows.csv` (the flows between the processes),
`stock.csv` (the steel in use), `end_use.csv` (the shares of the end uses) and `recycling.csv`
(the recycling rate and the most it may be).

## What it shows

| Blick or check | Declared with | Baseline | Changed run |
| --- | --- | --- | --- |
| `cycle/flows` | `expect=bk.expect.at_least(0, warn_within=1e-9)` | warning | warning |
| `cycle/end_use_split` | `expect=bk.expect.between(0, 1)` | met | failed |
| `cycle/recycling_rate` | `expect=bk.expect.no_rows(above_maximum, by="excess")`, `level="warn"` | met | warning |
| `checks/stock_balance` | `@bk.check` | met | failed |
| `checks/steelmaking_balance`, `checks/collection_balance` | `bk.register_check` in a loop | met | met |

- **Round-off is a warning.** South makes steel from scrap alone, and its flow of ore is zero as a
  solver leaves it, down to -1e-13. `warn_within` makes a value that close to the bound a warning;
  a flow below it would fail.
- **A bound on a Blick's table.** Every share of the end-use split lies between 0 and 1; in the
  changed run, packaging in North is -0.03 in 2030.
- **A property that relates rows.** The recycling rate and its maximum are rows of one table, so
  the function `above_maximum` returns the rows that offend, with `excess` as their distance. The
  Blick is at level `warn`: in the changed run East recycles more than the maximum from 2029 on,
  which shows without failing the build.
- **A check.** No chart shows whether the stock balances its flows. `stock_balance` returns the
  regions and years in which it does not, none in the baseline; in the changed run South gains
  steel that no flow brings, from 2026 on. Its expectation is the default, `no_rows()`, and its
  level the default, `error`.
- **A family of checks.** One check per process without a stock, registered with
  `functools.partial` in a loop, so that each has a page and an outcome of its own.

## The two runs

The baseline is coherent, with the one warning:

```console
$ uv run blicket check runs/baseline --push
run baseline · profile steel · blicks at dcfd796 (dirty) · loaded in 39 ms
3 Blicks: 3 built
3 checks: 3 ran
expectations: 5 met · 1 warning
build a9f614408e93d933 → .blicket/build/a9f614408e93d933

expectations warned
  blicks/cycle.py:10  Blick cycle/flows
    4 of 165 rows offend, all within warn_within: expected value at least 0, a warning within 1e-09
    worst -1e-13 at Region=South, Year=2030, From=ore, To=steelmaking

baseline: none (no other pushed build of profile steel)
build a9f614408e93d933 → .blicket/store/builds/a9f614408e93d933
```

It exits 0, and `--push` makes it the baseline of the profile (commits and ids differ on your
checkout). The changed run is then compared with it:

```console
$ uv run blicket check runs/changed
run changed · profile steel · blicks at dcfd796 (dirty) · loaded in 11 ms
3 Blicks: 3 built
3 checks: 3 ran
expectations: 2 met · 2 warnings · 2 failed
build 217d76febde55c9d → .blicket/build/217d76febde55c9d

expectations warned
  blicks/cycle.py:10  Blick cycle/flows
    4 of 165 rows offend, all within warn_within: expected value at least 0, a warning within 1e-09
    worst -1e-13 at Region=South, Year=2030, From=ore, To=steelmaking
  blicks/cycle.py:48  Blick cycle/recycling_rate
    2 rows offend, a warning at level warn: expected no rows of above_maximum, by excess
    worst 0.05 at Region=East, Year=2030, Series=Recycling rate

expectations failed
  blicks/checks.py:20  check checks/stock_balance
    5 rows offend: expected no rows, by gap
    worst -1.5 at Region=South, Year=2030
  blicks/cycle.py:25  Blick cycle/end_use_split
    1 of 99 rows offends: expected value between 0 and 1
    worst -0.03 at Region=North, Year=2030, End use=Packaging

baseline a9f614408e93d933 · run baseline · blicks at dcfd796 (dirty) · built 2026-11-16 14:07 UTC
vs baseline: 3 value
expectations vs baseline: 3 broken · 1 still failing
top movers: cycle/end_use_split 17% of scale (Region=North, Year=2030, End use=Packaging)
            cycle/recycling_rate 16% of scale (Region=East, Year=2030, Series=Recycling rate)
            cycle/flows 11% of scale (Region=East, Year=2030, From=collection, To=landfill)
flagged: 3 of 3 Blicks · failed: 2 expectations
comparison → .blicket/build/217d76febde55c9d/compare/a9f614408e93d933

expectations broken
  Blick cycle/end_use_split  failed, was met
  Blick cycle/recycling_rate  warning, was met
  check checks/stock_balance  failed, was met
```

It exits 1: three Blicks are flagged and two expectations of level `error` failed. With
`--exit-zero-on-changes` the flagged Blicks alone would give 0, and the failed expectations still
give 1, which is what a CI that accepts changes wants. `blicket build runs/changed`, which compares
nothing, exits 1 as well.

## In the viewer

`uv run blicket serve` shows the build made last, the changed run against the baseline:

- The sidebar has the Blicks and, under "Checks", the checks, each with its outcome as a badge;
  the filter next to the search shows all, the changed ones or the ones not met.
- The overview has the section "Expectations": the counts of this run, the transitions against the
  baseline, and a line per expectation not met.
- A Blick's page states the outcome above the chart, and "Show worst row" sets the filters to the
  row that offends most, packaging in North for the end-use split.
- A check's page shows the rows that offend as a table, worst first, instead of a chart:
  `checks/stock_balance` lists South from 2026 to 2030. A check that is met has no table.

## Things to try

- Add `level = "warn"` under `[tool.blicket]` in `pyproject.toml`: every failed expectation becomes
  a warning, `blicket build runs/changed` reports `expectations: 2 met · 4 warnings` and exits 0.
  `level="error"` on a single Blick or check, or `bk.group("checks", level="error")`, raises it
  again.
- Set `level="off"` on a check: it is skipped, with the reason on its page.
- Lower `warn_within` of `cycle/flows` below 1e-13: the round-off fails.
- Change the model in `make_runs.py`, run `python make_runs.py`, and check the changed run again.

## Developing blicket

blicket is installed from `../..`, not editable. `uv run` reinstalls it after a change to a `.py`
file under blicket's `src/`, to its `pyproject.toml` or its `meson.build`. blicket's own tests build
this example (`tests/test_examples.py`), so its outcomes above stay true.
