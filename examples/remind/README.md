# REMIND Blicks

A week of REMIND development as 20 charts, each flagged when the model changed it and ranked by
how much: the "Summary" chapter of REMIND's `compareScenarios` report, compared with last week's
runs instead of read as a PDF.

This is a blicket project on runs of [REMIND](https://github.com/remindmodel/remind): a loader
that reads the reporting of several REMIND output folders into one run, the scenario as a
dimension, and 20 [Blicks](../../README.md) that carry chapter 1, "Summary", of the report that
`piamPlotComparison::compareScenarios` renders from remind2's `cs_01_summary.Rmd`. The runs are
not in this repository; they come from the PIK cluster. Neither R nor a REMIND checkout is
needed, only the run folders.

## Quick start

From the blicket checkout, with [uv](https://docs.astral.sh/uv/), Node 24 or newer,
[pnpm](https://pnpm.io/installation), and `<host>` the cluster's SSH target:

```console
$ cd examples/remind
$ mkdir -p ../../data_out/remind
$ for run in SSP2-NPi2025-AMT_2026-10-23_22.13.50 SSP2-PkBudg1000-AMT_2026-10-24_00.54.24 \
      SSP2-PkBudg750-AMT_2026-10-24_00.46.31 SSP2-PkBudg750_wo100EJBiobound-AMT_2026-10-24_00.50.24
  do
    rsync -a --exclude='*_withoutPlus.mif' --include='REMIND_generic_*.mif' \
      --include=historical.mif --include=cfg.txt --include=log.txt --exclude='*' \
      <host>:/p/projects/remind/modeltests/remind/output/$run/ ../../data_out/remind/$run/
  done
$ uv sync
$ (cd ../../viewer && pnpm install && pnpm generate)
$ export BLICKET_VIEWER=../../viewer/.output/public
$ uv run blicket build ../../data_out/remind/*2026-10-2[34]*
$ uv run blicket serve
```

The rest of this README says what each step does, how to compare two weeks, and what the port of the
chapter leaves out. On a cluster without Node, blicket comes from PyPI with its viewer, as
[Building](#building) says; `store = "<directory>"` in `[tool.blicket]` puts the store of baselines
into a directory a team shares, such as one on the cluster's file system.

## The runs

A run is a set of REMIND output folders, one per scenario, as REMIND writes them:
`<title>_<YYYY-MM-DD>_<HH.MM.SS>/`. The loader reads four files of each:
`REMIND_generic_<title>.mif` (the reporting), `historical.mif`, `cfg.txt` and `log.txt`. The
folders go into `data_out/remind/` at the root of the blicket checkout, which git ignores; any
other place works too, since `blicket build` takes the folders as arguments. The `rsync` of the
quick start fetches those four files, 38 to 40 MB per folder.

`runs = ["../../data_out/remind/*"]` in `pyproject.toml` names that place for the run picker:
`uv run blicket` alone, or `uv run blicket dev` without folders, opens the viewer on the eight
folders of `data_out/remind/` instead of loading a set ([The Blick builder](#the-blick-builder)).
Tick the four of one week and press `Load 4 runs as one`; the terminal prints the report of the
check, and the viewer shows the build. Two folders of one scenario, such as the NPi runs of both
weeks, are refused by the loader, and the picker says so under the list. Runs kept elsewhere need
`runs` changed to match.

The example runs are two weekly sets of REMIND's automated model tests (AMT), which run every
week on the cluster and write their folders to `/p/projects/remind/modeltests/remind/output/`.
Each set has the four scenarios of the report the chapter was ported from: `SSP2-NPi2025-AMT`,
`SSP2-PkBudg1000-AMT`, `SSP2-PkBudg750-AMT` and `SSP2-PkBudg750_wo100EJBiobound-AMT`. The set of
2026-10-16/17 was run at REMIND `8d9052ef8`, model version 3.7.1.dev59, and has the folders
`SSP2-NPi2025-AMT_2026-10-16_22.12.36`, `SSP2-PkBudg1000-AMT_2026-10-17_00.56.55`,
`SSP2-PkBudg750-AMT_2026-10-17_00.49.20` and
`SSP2-PkBudg750_wo100EJBiobound-AMT_2026-10-17_00.53.07`; the set of 2026-10-23/24, the one of the
quick start, at `5e5500ec0`, 3.7.1.dev72. Both are on input data revision 8.27 and the region
mapping H12. `data_out/RUNS.md` is a note kept next to the runs, outside the repository like the
runs themselves, with the same facts.

## The project

```
pyproject.toml          [tool.blicket]: runs, the folders the run picker offers; the defaults
                        apply otherwise
blicketconf.py          load_run, the loader, and dataset, the quantities the Blick builder charts
remind.py               the REMIND output folder: cfg.txt, log.txt, the mifs; the run object
blicks/                 the Blicks, one group per file, and _iamc.py, the helpers they share
```

`load_run` takes one folder per scenario and orders them by scenario title, so the order on the
command line does not matter. It reads each folder's mif, without the years after 2100, which
the report never shows, into one table in the mif's wide shape with a `Scenario` column, the
summation markers (`|+|`, `|++|`, ...) stripped from the variable names, and the first folder's
`historical.mif` from 1990; it warns when another folder lacks `historical.mif` or holds a
different one. A cell that the mif writes as `NA` or `N/A` is missing. REMIND's reporting writes
some cells as R vectors, such as `c(73.2029314, 73.20293141)` for the population of the NPi
scenario; such a cell is read as its last number when its numbers agree within 1e-6, and any other
text is missing, with a warning that says how many cells of which variables could not be read.

The run id is the folder's name for one folder, and `4 scenarios of REMIND 3.7.1.dev72, latest
2026-10-24_00.54.24` for a set: REMIND's model version from `cfg.txt` and the timestamp of the
newest folder's name, so two weekly sets have different ids. A set whose folders are of different
REMIND versions or commits, as when a glob picks folders of two weeks, names every version in the
id and gets a warning that lists each folder's commit. The profile is the region mapping from
`cfg.txt`, `H12` for `regionmappingH12.csv`, the same for every set on that mapping. The commit and
branch the build records for the run are REMIND's, from the git info at the top of `log.txt`, when
all folders name the same commit. A path that is no directory, a folder without its mif, two
folders of one scenario, a mif of another scenario than its folder's `cfg.txt` names, a variable
reported twice once the markers are stripped, and folders of different region mappings are errors
that name the folders and say what to pass instead.

`remind.py` reads the folders; the Blicks import only its `Run`, `DIMENSIONS` and `WORLD`.
`blicks/_iamc.py` holds what the Blicks share; discovery skips it, as it skips every module whose
name starts with an underscore. It gives the Blicks `select`, the rows of a list of variables
with a dimension that labels them, from the scenarios or from one source of `historical.mif`,
and `per_person`, which divides them by the population as the report does. A variable that
`select` finds no rows for is named on stderr, once, and a Blick none of whose variables is in the
run fails with an error that names them, so a reporting step that failed shows as an error, not
as an empty chart.

## The Blicks

```
blicks/costs.py         consumption loss, absolute and relative, and GDP loss
blicks/emissions.py     GHG by source, GHG and CO2 by sector, per capita and cumulated
blicks/final_energy.py  final energy by sector, per capita, by carrier, by sector and carrier,
                        non-energy use
blicks/prices.py        the CO2 price, by scenario and by region
blicks/supply.py        electricity generation and primary energy by carrier
```

`blicket list` prints the groups in this alphabetical order; the chapter's order is emissions,
final energy, supply, prices and costs. Each Blick is one figure of the chapter, with the
variables in the order the Rmd lists them, and each legend keeps that order. The five final
energy charts by carrier (the detailed one and one per sector) are one Blick,
`final_energy/by_sector_and_carrier`, with one panel per sector, each with its own y axis. The
dimensions are `Scenario`, `Region` and `Year`, with the mif's values (`SSP2-NPi2025-AMT`,
`World`, `CAZ`, ...), World first, and one more for the stacked charts, such as `Sector` or
`Carrier`, whose values are the variables without the prefix they share (`CO2|Energy` and
`GHG|CH4` for `Emi|CO2|Energy` and `Emi|GHG|CH4`), or a shorter label where that leaves them long
(`Electricity supply (gross)` for `Emi|GHG|Gross|Energy|Supply|Electricity`). In these runs the
layers `CDR Sector (gross)`, `Processes|CDR Sector`, `CDR|OAE` and `CDR|EW` of the GHG and CO2
charts are zero throughout, legend entries without an area; the lists stay the report's.

A stacked chart opens as the report's first figure of a variable does: the stack for World, one
panel per scenario. Switching the split to Region and the filter to a scenario gives the report's
regional page, with World among the regions on a shared y axis, so that World flattens them until
"Own y axis per panel" is on. The line charts (the CO2 price, the policy costs, final energy per
capita) have the scenarios in colour and a region filter, and give each panel its own y axis when
split, as the report's do; `prices/co2_by_region` has the regions in colour, World left out, and
one panel per scenario.

The two per-capita line Blicks, `final_energy/per_capita` and
`final_energy/per_capita_by_sector_lines`, show history as the report does: the IEA's final energy
from 1990, divided by the World Bank's population, as a further scenario, `historical (IEA)`,
which comes after the scenarios. No other Blick has history; the report draws none in its stacked
charts either. History that stays the same from week to week changes nothing in a comparison; a
new IEA year appears as a new `Year`, flagged `schema`, in exactly these two Blicks.

## Environment

```console
$ cd examples/remind
$ uv sync
$ uv run blicket list
```

`blicket list` needs no run; it lists the five groups and 20 Blicks. The environment holds
blicket and pyyaml, which reads `cfg.txt`. `uv.lock` is committed.

## Building

`build` copies the viewer into every build directory, and blicket installed from a checkout has none
of its own, so `build` and `serve` stop with an error until you generate one and set
`BLICKET_VIEWER`, as the quick start and the [root README](../../README.md#development) show.
Without Node, the release from PyPI brings its viewer: with `UV_NO_SOURCES_PACKAGE=blicket`
exported, `uv sync` and `uv run` install it in place of the checkout and rewrite `uv.lock` (do not
commit that), and `BLICKET_VIEWER` is not needed; the Blicks then run on the released blicket, not
on the checkout's. Then, with the set of 2026-10-23/24:

```console
$ uv run blicket build ../../data_out/remind/*2026-10-2[34]*
run 4 scenarios of REMIND 3.7.1.dev72, latest 2026-10-24_00.54.24 · profile H12 · blicks at 57b9421 (dirty) · loaded in 383 ms
20 Blicks: 20 built
build e94ee18b78c4bf21 → .blicket/build/e94ee18b78c4bf21
```

Reading the four mifs and `historical.mif` takes about 0.35 s and the 20 Blicks about 0.15 s
together; the whole command takes 0.8 to 0.9 s and half a GB of memory, most of which parsing the
mifs leaves to the allocator; the run itself holds 67 MB. The commit after "blicks at" is the one
of the blicket repository, which holds the Blicks, not REMIND's, and `(dirty)` after it marks
uncommitted changes there; commit and build id differ from the ones shown here. The folders in
another order give the same build.

## Checking a run

`check` builds a set and compares it with the newest pushed build of its profile. With the set of
2026-10-16/17 built and pushed, checking the set of 2026-10-23/24 compares the two weeks:

```console
$ uv run blicket build ../../data_out/remind/*2026-10-1[67]*
$ uv run blicket push .blicket/build/<id of that build>
$ uv run blicket check ../../data_out/remind/*2026-10-2[34]*
run 4 scenarios of REMIND 3.7.1.dev72, latest 2026-10-24_00.54.24 · profile H12 · blicks at 57b9421 (dirty) · loaded in 398 ms
20 Blicks: 20 built
build e94ee18b78c4bf21 → .blicket/build/e94ee18b78c4bf21 (built before, left as it was)

baseline 92f902375302ceaf · run 4 scenarios of REMIND 3.7.1.dev59, latest 2026-10-17_00.56.55 · blicks at 57b9421 (dirty) · built 2026-10-29 08:48 UTC
vs baseline: 20 value
top movers: final_energy/by_sector_and_carrier 100% of scale (Scenario=SSP2-PkBudg750-AMT, Region=CHA, Year=2100, Sector=CDR, Carrier=Electricity)
            costs/gdp_loss 43% of scale (Scenario=SSP2-PkBudg1000-AMT, Region=USA, Year=2060)
            costs/consumption_loss 36% of scale (Scenario=SSP2-PkBudg750-AMT, Region=USA, Year=2100)
            … and 17 more
flagged: 20 of 20 Blicks
comparison → .blicket/build/e94ee18b78c4bf21/compare/92f902375302ceaf
```

Between model versions 3.7.1.dev59 and 3.7.1.dev72 every Blick moves: the CO2 price by 0.5 % to
0.7 % of the chart's scale, cumulated CO2 by 0.6 %, the other emission and energy charts by 1.1 %
to 6.9 %, the policy costs by 16 % to 43 %. The top mover is the CDR sector of China in 2100,
whose electricity grew from 0.00005 to 0.014 EJ/yr: little in absolute terms, but all of its
panel's scale, since each sector's panel of `final_energy/by_sector_and_carrier` has a scale of
its own, as each of the report's sector charts has.

Here the week moved all 20 charts, so the flags say that the week changed the chapter, and the
movers and the magnitudes say where to look first. `tolerance` in `[tool.blicket]`, or on a
Blick, is for the noise between reruns of one commit, which these runs do not measure, not for
hiding model changes.

The profile is the region mapping, not the set of scenarios, so that a week in which one AMT
scenario failed still finds last week's set as its baseline and reports the loss on every Blick:

```console
$ uv run blicket check ../../data_out/remind/SSP2-NPi2025-AMT_2026-10-23_22.13.50 \
    ../../data_out/remind/SSP2-PkBudg1000-AMT_2026-10-24_00.54.24 \
    ../../data_out/remind/SSP2-PkBudg750-AMT_2026-10-24_00.46.31
...
vs baseline: 20 value · 20 schema
...
schema
  costs/consumption_loss
    Scenario removed: SSP2-PkBudg750_wo100EJBiobound-AMT
  ...
```

With the set in the profile, that week would have no baseline, and `check` exits 0 without one.
The price is that two different sets on one region mapping in one store compare with each other,
`schema` on every Blick, until `--against <id>` names the right baseline. One folder alone is
such a set: its check against the four-scenario baseline flags all 20 Blicks `schema`, with three
scenarios removed (and `value`, as its scenario changed between the weeks); look at one folder
with `build`, or check it with `--against <id>` against a build of that scenario alone.

## Looking at a build

`uv run blicket serve` serves the build made last, with the comparison when it was checked. The
viewer has eight colours; a chart with more layers repeats them, with a dash pattern for lines
and nothing for stacked areas, so seven of the thirteen stacked Blicks have layers of the same
colour, such as Coal and Solar in primary energy: the tooltip and the legend's highlight tell
them apart.

## The Blick builder

`blicket dev` checks a set as `check` does and then serves it, keeping the run in memory for the
Blick builder:

```console
$ uv run blicket dev ../../data_out/remind/*2026-10-2[34]*
```

The report ends with `builder: 7760 quantities, 3 dimensions`: `dataset(run)` in `blicketconf.py`
offers every variable of the mifs, named as the mif names it, with its unit, grouped by its
first segment (`Emi`, `FE`, `Price`, ...); `GDP|PPP`, the one variable in two units, is two
quantities, `GDP|PPP [billion US$2017/yr]` and `GDP|PPP [billion constant 2017 Int$PPP]`. None of
them is additive, so every dimension starts as a filter, and the builder never sums over regions,
which would count World twice, or over scenarios. The list of 7,760 quantities takes three to
four seconds to open; typing a part of a name, such as `Emi|GHG`, narrows it in 0.25 to 0.5 s.
The builder has no variable hierarchy, so no tree and no summation groups, and a stacked area
with Region on colour stacks World on the regions.

## What the port leaves out

- The tables of the chapter, the "Tables of Significant Periods" (the years of the maximum and
  minimum of the CO2 and GHG emissions, the first year below 2 % of 2005, the peak temperature),
  and the two charts of final energy per capita over GDP per capita: blicket has no table and no
  scatter plot type.
- The CO2 prices of the four sectors and of the ETS and ESR: in H12 runs the sector prices equal
  `Price|Carbon` everywhere, so the report leaves them out, and the ETS and ESR prices are zero.
  Runs with the EU regions need them, since there they differ.
- The CO2 price as the social cost of carbon and a guardrail component: `Price|Carbon|SCC` is
  zero in every row of these runs, damages being off, so the chart would be the CO2 price as a
  one-layer stack, flagged with it every week. The report draws it whenever the variable exists.
- The bars at 2020, 2030, 2050 and 2100 next to each stacked chart, and the total drawn as a line
  over each stack: the area chart with one panel per scenario carries the same numbers. In every
  scenario, region and year, the layers differ from the total by at most 3e-7 of the largest
  total of that region in the chart (7e-5 for the CDR sector's final energy, where the mif's
  rounding to 1e-7 EJ/yr meets totals of a few thousandths of an EJ/yr).
- Colours per variable, as the report takes them from mip's `plotstyle`, and more than eight
  hues; see [Looking at a build](#looking-at-a-build).
- The report orders some legends by the data's mean, which would reorder them between builds;
  here every legend has the Rmd's order.
- The per-capita stacks divide every layer by the population; the report has per-capita values
  of only some of the variables, so its charts of GHG and CO2 per capita have fewer layers.
  The CO2 per capita is in t CO2/yr per capita, where the report writes t CO2eq.
- `SE|Electricity|Net Imports`, which the report lists in the electricity chart: these mifs do
  not report it, so the Blick leaves it out. The cumulated CO2 chart reads
  `Emi|CO2|Cumulated|CDR|Synthetic Fuels CCS`, which the Rmd misspells as `Synthetic Fuel CCS`.
- The historical data of the report's line charts other than final energy per capita: the CO2
  prices and the policy costs have none in `historical.mif`.

## Developing blicket

blicket is installed from `../..`, not editable. `uv run` reinstalls it after a change to a `.py`
file under blicket's `src/`, to its `pyproject.toml` or its `meson.build`; after a change to any
other file under `src/`, `uv sync --reinstall-package blicket` does.
