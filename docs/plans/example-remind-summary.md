# REMIND example: the Summary chapter of compareScenarios as Blicks

Status: signed off by Tobias on 2026-10-29 with every recommendation of the open questions below
("Decided by Tobias"); implemented from commit `57b9421`, then revised after a review of the
implementation (the results and deviations at the end). Where a section below differs from the code,
the Deviations at the end are what the code does. Planned 2026-10-29, revised the same day after an
independent review that probed the fetched runs (the mif cells, the units of each stack, the
week-to-week magnitudes, the memory of the run object) and the viewer's limits. A second dogfooding
project next to [examples/remind-mfa](../../examples/remind-mfa), the first on an integrated
assessment model and on IAMC-style output (mif files). Builds on M2.1 (commit `57b9421`). Companion
to [architecture.md](../architecture.md) ("Adapter and loader protocol", "Project basics") and to
the concept's deferred decision on reference and historical data, which this plan settles for one
example without touching the core.

## Goal

`examples/remind/` is a blicket project on REMIND runs: a loader that reads the reporting of
several REMIND output folders into one run, the scenario as a dimension, and Blicks that carry
the content of chapter 1, "Summary", of REMIND's `compareScenarios` report (the PDF that
`piamPlotComparison::compareScenarios` renders from `remind2`'s `cs_01_summary.Rmd`). `blicket
build`, `check`, `serve` and `dev` run end to end on two weekly sets of REMIND's automated model
tests (AMT), so a week's model changes show as flagged Blicks instead of a thousand-page PDF.
blicket's core gains nothing domain specific; what the example cannot express with the current
plot types and viewer is recorded, not worked around.

## The flows this task enables

### 1. Build and look at a scenario set

```console
$ cd examples/remind
$ uv sync
$ uv run blicket list
emissions   GHG and CO2 emissions
  emissions/ghg                GHG emissions by source                  stacked_area
  ...
5 groups · 20 Blicks
$ uv run blicket build ../../data_out/remind/SSP2-NPi2025-AMT_2026-10-23_22.13.50 \
    ../../data_out/remind/SSP2-PkBudg1000-AMT_2026-10-24_00.54.24 \
    ../../data_out/remind/SSP2-PkBudg750-AMT_2026-10-24_00.46.31 \
    ../../data_out/remind/SSP2-PkBudg750_wo100EJBiobound-AMT_2026-10-24_00.50.24
run 4 scenarios of REMIND 3.7.1.dev72, latest 2026-10-24_00.54.24 · profile H12 · blicks at <commit> · loaded in <n> ms
20 Blicks: 20 built
build <id> → .blicket/build/<id>
$ uv run blicket serve
```

The overview lists the five groups. "GHG emissions by source" opens as the PDF's
first figure does: stacked areas over the years, one panel per scenario, the region filter at
World; switching the split to Region and the filter to a scenario gives the PDF's second page,
the twelve regional panels, with World among them: the panels share one y axis, so World flattens
the regions until the axis toggle gives each panel its own. Every stacked chart of the chapter
works this way; the line charts (CO2 prices, policy costs, final energy per capita) have the
scenarios in colour, the region as a filter, split on demand with a y axis per panel.

### 2. Check this week's set against last week's

With last week's set built and pushed (the same four scenarios of 2026-10-16/17), the command of
flow 1 as `blicket check` finds it as the baseline, since both sets are of the profile `H12`,
and reports which of the 20 Blicks moved and where, with the top movers; `blicket serve` shows
the comparison, the baseline faded behind each chart. Between REMIND `8d9052ef8` (model version
3.7.1.dev59) and `5e5500ec0` (3.7.1.dev72) nearly everything moves: this is a real model change,
not a rerun. The review's probe of eight tables found no `schema` flag and magnitudes from 0.005
(CO2 prices) over 0.02 (GHG by source) and 0.06 (FE by carrier) to 0.4 (policy costs) and 1.0
(FE of the CDR sector); the task records the real numbers of all Blicks below. A week in which
one scenario of the set failed shows as `schema` on every Blick, the scenario named as vanished,
which is the loud failure a guard wants.

### 3. The builder on a REMIND run

`uv run blicket dev <the four folders>` reports `builder: 7760 quantities, 3 dimensions`; the
builder lists every variable of the mif, grouped by its first segment (`Emi`, `FE`, `Price`,
...), with its unit, none of them additive, so every dimension starts as a filter and nothing
is ever summed over regions (which would double count World) or scenarios.

## Facts the plan rests on (checked 2026-10-29 on the cluster and on the fetched runs)

- **The report.** `compareScenarios2.R` in REMIND's `scripts/output/comparison/` starts
  `piamPlotComparison::compareScenarios(projectLibrary = "remind2", mifScen, mifHist, cfgScen,
  ...)` with a profile from `scripts/cs2/profiles.json`; the H12 profile shows the regions CAZ,
  CHA, EUR, IND, JPN, LAM, MEA, NEU, OAS, REF, SSA, USA and World, scenario years 2005–2060 by 5
  and 2070–2100 by 10 (the mif also has 2110, 2130, 2150), historical years from 1990, bar-plot
  years 2020, 2030, 2050, 2100, main region World. `cs_main.Rmd` reads the mifs with quitte,
  keeps `varplus` (the variable name with its `|+|` markers) and strips the markers for
  `variable`, binds the historical mif as scenario `historical` with the data source in `model`,
  then `preprocessing.R` derives `<variable> pCap` (per capita: value / Population × 1e6 or
  1e9, REMIND's own population per scenario, WDI's for historical rows) for a fixed list of
  variables, and `pGDP_PPP` variables. The chapter
  (`remind2/inst/compareScenarios/cs_01_summary.Rmd`) has 25 figure chunks and 7 table chunks;
  the figures are 18 `showAreaAndBarPlots` calls (stacked areas by scenario for World, bars at
  the bar-plot years, then the regional panels without World; the total variable as a black line
  over the areas), 10 `showLinePlots` (World large, regions small, scenarios in colour,
  historical sources as points; four of them, the sector prices, only when those differ from the
  average), one `showRegiLinePlots` (regions in colour without World, one panel per scenario),
  two `showMultiLinePlots` (per-capita lines, IEA history as points) and two
  `showMultiLinePlotsByVariable` (per-capita final energy over per-capita GDP, a scatter with
  year markers). The tables (`calcTimeSeriesStats`) give per scenario and region the year of the
  maximum and minimum of `Emi|CO2` and `Emi|GHG`, the first year below 2 % of 2005, and the peak
  and 2100 value of `Temperature|Global Mean`. The example PDF of 2026-09-22 is of other runs
  (the same four scenarios without `-AMT`), so it guides the shape of the charts, not their
  numbers.
- **The runs.** `/p/projects/remind/modeltests/remind/output/` holds the weekly AMT runs, one
  folder per scenario, `<title>_<YYYY-MM-DD>_<HH.MM.SS>/`; titles contain underscores, so the
  timestamp is read from the right. A folder holds `REMIND_generic_<title>.mif` (27 MB, 90,431
  rows, 7,759 variables with the markers stripped, no two merging, the same 7,759 in all four
  scenarios, years 2005–2150), the same data as `..._withoutPlus.mif`, `historical.mif` (10.8 MB,
  22,150 rows, 41 sources, yearly 1950–2025 plus five-year steps to 2060, byte-identical across
  all eight folders), `cfg.txt` (the run's `cfg` as YAML: `title`, `description`,
  `regionmapping`, `model_version`, `inputRevision` and the 337 GAMS switches) and `log.txt`,
  whose `===== git info =====` block names the REMIND commit (`Latest commit: 5e5500ec0
  2026-10-22 ...`) and branch. The two weeks fetched into `data_out/remind/` are the four
  scenarios of the example PDF, `SSP2-NPi2025-AMT`, `SSP2-PkBudg1000-AMT`,
  `SSP2-PkBudg750-AMT` and `SSP2-PkBudg750_wo100EJBiobound-AMT`, of 2026-10-16/17 (REMIND
  `8d9052ef8`, 3.7.1.dev59) and 2026-10-23/24 (`5e5500ec0`, 3.7.1.dev72), both on input
  revision 8.27; the mif, `historical.mif`, `cfg.txt`, `config.Rdata`, `log.txt` and
  `runtime.log` of each, 295 MB in all.
- **Reading a mif with polars.** `read_csv(separator=";")` with every column as text, the
  trailing empty column dropped: 54 ms; unpivoting the year columns gives 1.7 M rows per
  scenario in 97 ms, and the long form of four scenarios, 6.9 M rows, takes about 650 MB with
  string columns. Missing cells are the literal `NA` (4,500 to 4,800 per mif, 819 MAGICC and
  moving-average variables; `historical.mif` writes `N/A`). In both `SSP2-NPi2025-AMT` runs all
  247 `Population` cells are R vector literals such as `c(73.2029314, 73.20293141)`: in 181 of
  them the two numbers differ, by at most 6.7e-10 relative, the second with more digits.
  `GDP|PPP` appears under two units (`billion US$2017/yr` and `billion constant 2017 Int$PPP`);
  no other variable does. The mifs do not agree on the position of `World`: one lists it last,
  three first.
- **Variables of the chapter.** Every variable the chapter names is in the mif except
  `SE|Electricity|Net Imports` and `Emi|CO2|Cumulated|CDR|Synthetic Fuel CCS`, which the Rmd
  misspells (`Synthetic Fuels CCS` exists). The chapter's variables have no missing values, and
  every stack sums to its total within 3e-7 of the largest total of its region (FE of the CDR sector
  within 7e-5), so the total line loses nothing visible. Two stacks mix units: the GHG items are
  five in `Mt CO2/yr` and three in `Mt CO2eq/yr`, GHG by sector seven and ten. In these H12 runs the
  four sector prices equal `Price|Carbon` in every row, and `Price|Carbon|ETS` and `|ESR` are zero
  everywhere; `Price|Carbon|SCC` and `|Guardrail` exist. Units: `Mt CO2/yr` and `Mt CO2eq/yr` for
  emissions, `Mt CO2` cumulated, `EJ/yr` for energy, `US$2017/t CO2` for carbon prices,
  `billion US$2017/yr` for consumption and GDP loss, `%` for the relative loss, `million` for
  population. `historical.mif` has no carbon price or policy cost; for `FE` and its sectors it has
  `IEA` yearly 1960–2023 for all 13 regions (and IEA-EB-directSum, the ETP and WEO series), for
  `Population` WDI 1960–2023, for the emissions totals PRIMAPhist, EDGARghg and ClimateTrace.
- **blicket today.** A Blick's plot type has `x` (a dimension), `y` (a measure), `color` and,
  for lines, `linetype`; `x` cannot be a measure, there is no scatter and no table plot type
  (both are M2.3), no overlay line on a stack, and no "group" channel for grouped-and-stacked
  bars. `order=` fixes the display order of a dimension's values, and so does a polars `Enum`
  column, whose categories the check takes as the order; `defaults=` names a filter's first
  value, `controls={dim: "split"}` the default split. A loader may take several paths
  (`selection.paths`); `bk.fingerprint` hashes files in the order given. `bk.Frames` makes a
  dataset of tables given as functions, with the dimensions declared ahead; a `Frames.select`
  sums the rows of equal keys. A module under `blicks/` whose name starts with an underscore is
  a helper that discovery skips, importable as `blicks._name`, and M2.2's reload will reload it
  in place, while a change to a module the loader imported restarts the session. The viewer has
  eight categorical hues (`SLOTS` in `viewer/app/plots/theme.ts`); past them the hues repeat,
  with a dash pattern for lines and nothing for stacked areas; a legend label is cut at 220 px.
  The viewer hides a comparison whose baseline has the same run id as the current build. A split
  shares one y axis across its panels unless the Blick sets `independent_y` or the axis toggle is
  flipped, and cannot leave a value out.

## Approach

### Layout

```
examples/remind/
  pyproject.toml          a virtual uv project: blicket (path ../..) and pyyaml; an empty
                          [tool.blicket]
  uv.lock                 committed
  README.md               the runs, how to fetch them, build, check, dev; what the port leaves out
  blicketconf.py          load_run and dataset
  remind.py               reading a run folder (the mif, historical.mif, cfg.txt, log.txt) and
                          the Run object; imported by the loader
  blicks/
    _iamc.py              the helpers the Blicks share: select, per_capita, labels; a helper
                          module, skipped by discovery, reloaded in place by the dev loop
    emissions.py          GHG and CO2 emissions (6 Blicks)
    final_energy.py       final energy by sector and carrier, per capita (7)
    supply.py             electricity and primary energy (2)
    prices.py             CO2 prices (2)
    costs.py              policy costs (3)
```

The example is its own uv project, as remind-mfa is; it needs no R and no REMIND checkout, only
the run folders. `pyyaml` reads `cfg.txt`. The runs stay in `data_out/remind/` at the repository
root, gitignored, with a `RUNS.md` next to them naming each folder's commit and model version,
as remind-mfa's runs have. ty checks the example through the existing `examples/**` override.
The reader stays apart from the helpers because the dev loop treats them differently: an edit to
`blicks/_iamc.py` rebuilds the Blicks on the run in memory, an edit to `remind.py` reloads the
run.

### The loader and the run object (`remind.py`, `blicketconf.py`)

`load_run(selection)` takes one folder per scenario, sorts the folders by scenario title, so
that nothing depends on the order on the command line, and returns a `Run`:

- `scenarios`: one polars frame over all folders in the mif's wide shape, a `Scenario` column
  added: `Scenario`, `Region`, `Variable` (markers stripped), `Unit`, then one Float64 column
  per year up to 2100, from each folder's `REMIND_generic_<title>.mif`, found by the glob
  without `withoutPlus`. The years after 2100 are dropped, as the report never shows them. The
  frame stays wide (360,000 rows for four scenarios) and is unpivoted per selection, since the
  long form of four scenarios is 6.9 M rows. `NA` and `N/A` are null. A cell that is an R
  vector literal `c(a, b, ...)` whose numbers agree within 1e-6 relative is read as its last
  number, the one with the most digits; any other text is null, and the loader prints to stderr
  how many cells of which variables it could not read, so a reporting bug costs a value, never
  the build, and never silently. `Scenario`, `Region`, `Variable` and `Unit` are categorical,
  which keeps the frame around 50 MB.
- `historical`: `historical.mif` the same way, with the data source in `Model` as the mif names
  it, the years from 1990 as the H12 profile shows them, null values dropped. The eight copies
  are identical today; the loader reads the first folder's and warns when another folder's
  differs.
- `regions`: `World` first, then the regions sorted, the display order of every Blick.

The `RunInfo`: `id` is the folder name for one folder and `"<n> scenarios, latest <timestamp>"`
for several, the timestamp the newest folder's, which differs between two weekly sets as the
viewer's comparison needs; `profile` is the region mapping's name from `cfg.txt`
(`regionmappingH12.csv` → `H12`), the same for every set run on that mapping, and the loader
refuses folders of different mappings; `fingerprint` covers the mifs, the historical mif and
the `cfg.txt` files in the sorted order; `commit` and `branch` come from `log.txt` when every
folder names the same commit, else stay `None`; `dirty` stays `None`, since the log reports
untracked files in prose. A folder without a mif, two folders with the same scenario title, or a
mif whose `Scenario` column is not the folder's title is a loader error that names the folder.

The profile is the mapping, not the scenario set, on purpose. With the set in the profile, the
week in which one AMT scenario fails would find no baseline, and `check` exits 0 without a
baseline: the guard would pass in silence exactly when something broke. With the mapping, the
shrunk set compares with last week's and every Blick says which scenario vanished. The price is
that two different sets on one mapping in one store compare with each other, `schema` on every
Blick, until `--against` names the right build; the README says so (open question 3).

`dataset(run)` is a `bk.Frames` with the dimensions `Scenario`, `Region` and `Year`, and one
quantity per variable and unit of the mif: the variable as its name, with the unit appended in
brackets for the one variable that has two, the unit from the mif, the first segment of the name
as its group, `additive=False` throughout, and a function that filters the wide frame to the
variable and unit and unpivots it. 7,760 quantities is what the builder gets until the IAMC
hierarchy exists; the README says so, and that a stacked area with `Region` on colour adds World
to the regions.

### The Blicks

`blicks/_iamc.py` gives the Blicks `select(run, items, dimension, unit, *, equivalent=())`: the rows
of the variables in `items`, unpivoted to `Scenario`, `Region`, `Year`, the new dimension column and
`value`, the `Unit` column dropped after a check that every row's unit is `unit` or one of
`equivalent` (CO2 and CO2eq are numerically equal, so the GHG stacks pass
`equivalent=("Mt CO2/yr",)`); a unit outside that set, as `GDP|PPP`'s second unit would be, is an
error. `items` is a list of variables or a dict of variable to label; the labels of a list drop the
longest common `|`-separated prefix of the variables, as mip's `shorten_legend` does
(`Emi|CO2|Energy` → `CO2|Energy` next to `GHG|CH4`), and the long-item charts give short labels
through the dict, so no legend label exceeds what the viewer shows. The dimension column is an
`Enum` in the order of `items`, so the legend keeps the report's order without `order=`; an item the
run lacks is named in a warning and leaves the others, and a Blick none of whose items is in the run
is an error (the Deviations say how this replaced the report's silent drop).
`per_capita(frame, run)` divides by REMIND's `Population` of the same scenario, region and year, and
by WDI's for historical rows, with the report's factors and units.

Every stacked chart is one Blick, `stacked_area` with `x="Year"`, `color=<item dimension>`,
`controls={"Scenario": "split"}` and `defaults={"Region": "World"}`; the region filter and the
scenario split swap by the viewer's controls, which gives the report's regional pages. The line
Blicks set `independent_y=True`, as the report's panels have free y axes. The bar variants and
the total line are left out (open question 2, and "Out of scope").

| id | report chunk | table (dims → value) | plot |
|---|---|---|---|
| `emissions/ghg` | GHG emissions | Scenario, Region, Year, Source (8 items) | stacked_area, color=Source, unit Mt CO2eq/yr |
| `emissions/ghg_by_sector` | GHG by sector | …, Sector (17 items incl. the CDR options) | stacked_area |
| `emissions/ghg_per_capita_by_sector` | GHG pCap by sector | …, Sector (17) | stacked_area, t CO2eq/yr per capita |
| `emissions/co2_by_sector` | CO2 by sector | …, Sector (17) | stacked_area, Mt CO2/yr |
| `emissions/co2_per_capita_by_sector` | CO2 pCap by sector | …, Sector (17) | stacked_area |
| `emissions/co2_cumulated_by_sector` | CO2 cumulated by sector | …, Sector (16, `Synthetic Fuels CCS` spelled as the mif has it) | stacked_area, Mt CO2 |
| `final_energy/by_sector` | FE by sector | …, Sector (CDR, Transport, Buildings, Industry) | stacked_area, EJ/yr |
| `final_energy/per_capita_by_sector` | FE per capita, area | …, Sector | stacked_area, GJ/yr per capita |
| `final_energy/per_capita` | FE per capita, line graph (total) | Scenario (+ `historical (IEA)`), Region, Year | line, color=Scenario; Region filter World |
| `final_energy/per_capita_by_sector_lines` | FE per capita, line graph (sectors) | …, Sector | line, color=Scenario, Sector split, Region filter |
| `final_energy/by_carrier` | FE by carrier | …, Carrier (6) | stacked_area |
| `final_energy/by_sector_and_carrier` | FE by carrier (detailed), FE Industry, Buildings, Transport and CDR by carrier | …, Sector, Carrier (21 sector × carrier variables, the union of the four sector charts) | stacked_area, color=Carrier, Sector split, Region filter, Scenario filter |
| `final_energy/non_energy_use_by_carrier` | FE Non-energy Use by carrier | …, Carrier (3) | stacked_area |
| `supply/electricity_by_carrier` | SE Electricity by carrier | …, Carrier (15, without Net Imports) | stacked_area |
| `supply/primary_energy_by_carrier` | PE by carrier | …, Carrier (9) | stacked_area |
| `prices/co2` | CO2 Prices, `showLinePlots` | Scenario, Region, Year | line, color=Scenario, Region filter World |
| `prices/co2_by_region` | `showRegiLinePlots` | the same without World | line, color=Region, Scenario split |
| `costs/consumption_loss` | Policy Costs Consumption | Scenario, Region, Year | line, color=Scenario, billion US$2017/yr |
| `costs/consumption_loss_relative` | Policy Costs Relative | the same | line, % |
| `costs/gdp_loss` | Policy Costs GDP | the same | line |

20 Blicks in five groups, one module each, in the chapter's order. The five final-energy
carrier charts of the chapter are one Blick with a `Sector` split: their items are the same 21
variables, the chart has six hues instead of 21, and a change in one variable flags one Blick
instead of two. The item order of each stack is the Rmd's list (`orderVars = "user"` where the
Rmd says so, and the listed order elsewhere too, since the report's mean ordering depends on the
data and would reorder the legend between builds). The per-capita stacks divide every item of
their chart, while the report's `pCapVariables` list lacks four of the GHG and six of the CO2
items, so these two Blicks show more layers than the PDF. Dimension values are the mif's
(`CAZ`, `World`, the scenario titles); a `Year` is an integer, so the x axis is quantitative and
the historical rows' yearly values and the model's five-year steps share it.

Two line charts of the chapter are left out of this example because they show nothing in H12
runs: the four sector prices (the report draws them only when they differ from the average,
and they do not here) and the ETS and ESR prices (zero in every region and scenario). The README
names both as the first Blicks to add for EU runs, where they carry information. For the same
reason the stacked chart of the CO2 price as the social cost of carbon and a guardrail is left
out: `Price|Carbon|SCC` is zero in every row of every AMT run, damages being off, so the chart
would be the CO2 price as a one-layer stack (decided in the implementation's review).

### Historical data

Settled for this example as "a dimension value", the first of the concept's three options,
limited to the two per-capita line Blicks, the only charts of the chapter where the report
draws history: they get the rows of the source `IEA` of `historical.mif` from 1990 as a further
value of `Scenario`, named `historical (IEA)`, divided by WDI's population as the report's
preprocessing does. The review checked the consequences: identical history contributes no
change, since the panel scale is per region and the comparison sees the same rows in both
builds; a new IEA year flags `schema` and `value` in exactly these two Blicks; the table passes
the checks (1,274 rows, 442 of them IEA's, no nulls); WDI covers every IEA row. From 1990 the
model years keep most of the x axis. The stacked charts get none, as in the report. Nothing in
the core changes for it; the one viewer fix made on the way is listed under Affected areas. A
`Source` dimension or a pseudo-run can replace this when a second project wants history on more
charts (open question 1).

### What the example exposes, recorded rather than fixed

- Seven of the thirteen stacked Blicks have more layers than the viewer has hues: 17, 17, 17,
  17, 16, 15 and 9 layers over eight hues, so `Coal` and `Solar` share a blue in primary energy
  and the legend shows swatches twice. Only the tooltip and the legend highlight tell such
  layers apart. This is the style registry the architecture defers (mip's `plotstyle` colours
  per value), or a larger ordinal palette for stacks; the README names it as the main gap, and
  the item labels are kept short so that at least the legend reads (open question 7).
- A Region split shares its y axis with World, and cannot leave World out; the axis toggle is
  the answer today, "an enlarged World panel" is on the deferred list already.
- Found while implementing, in the core and the viewer (recorded, one fixed):
  - A line chart's tooltip printed the literal `undefined` for a series without a row at the
    hovered x, which the per-capita Blicks hit in most years, since they mix the yearly history
    with the model's five-year steps. Fixed in this task: the hover rule writes an en dash
    (`viewer/app/plots/encodings.ts`, with a test in `viewer/tests/plots.test.ts`).
  - The loader's `commit` and `branch`, REMIND's here, appear nowhere in the viewer or in the
    check's baseline line, which name the run id and the Blicks' commit only; this example puts
    the model version into the run id instead.
  - A stacked layer that changes sign draws a diagonal across the chart (Land-Use Change in the
    cumulated CO2).
  - Groups are ordered alphabetically, with no way to give the chapter's order.
  - The check's `schema` section repeats one line per Blick where the overview condenses the
    values that vanished across Blicks; the overview lists every Blick twice when all are
    flagged, in "Changed since the baseline" and in its group.
  - Numbers such as `29.5024k`, and a `1e+3` axis tick (primary energy).
  - The builder's quantity picker renders every one of its 7,760 options and takes three to four
    seconds to open.

### Documentation

The example's README, in the shape of remind-mfa's: the runs and the cluster path, what the loader
reads and how it names the run and the profile, the groups, the environment, building, checking,
`dev`, and what the port leaves out and why. The root README's "Examples" section names both
examples. `architecture.md`, "Project basics": a line on the second dogfooding project and that the
reference-data question was settled for it as a dimension value in two Blicks. `data_out/RUNS.md`
gains the REMIND folders (outside the repository).

## Affected areas

- New: everything under `examples/remind/`; `data_out/remind/` (outside the repository) with its
  note in `data_out/RUNS.md`; this plan.
- Changed: the root `README.md` ("Examples"), `docs/architecture.md` ("Project basics", one
  amendment), the root `.gitignore` (`data_out` without the slash, so that a worktree's symbolic
  link is ignored), and in the viewer `viewer/app/plots/encodings.ts` with a test in
  `viewer/tests/plots.test.ts` (the tooltip of a series without a row at the hovered x). Nothing
  under `src/blicket/` unless the example reveals a bug, each fix with a test, as M0.3's did.
- CI does not build the example (it needs the runs). `ruff` and `ty` cover it through the root
  configuration.

## Testing

As for remind-mfa, the example has no test suite; the recorded build is the acceptance test:

- `uv run blicket list` prints 20 Blicks in five groups with no problem.
- `uv run blicket build` on each weekly set exits 0 with 20 built; the loader line, the
  per-Blick `timing_ms` and the loader's resident memory are recorded here. Building the same
  set with the folders in another order gives the same build id.
- `uv run blicket check` of the 2026-10-24 set against the pushed 2026-10-17 set: the counts
  per flag, the top movers and the magnitudes are recorded here, as the first look at what a
  week of REMIND development does to the Summary chapter; `schema` flags, if any, are
  explained. Then the same check with one folder left out, which must flag every Blick `schema`
  with that scenario vanished.
- `uv run blicket dev` on the 2026-10-24 set starts with the builder on; the time the quantity
  picker takes to open and to search with 7,760 entries is recorded, and `Emi|GHG` is charted
  for one region.
- The viewer: each Blick is opened once at its defaults and once split by Region, against the
  PDF's pages 18 to 75 for the shape of the charts; what looks wrong is fixed or recorded.
- blicket's own suite, `ruff` and `ty` pass with the example included.

## Out of scope

- The "Tables of Significant Periods" (seven table chunks) and "FE per capita, GDP domain" (two
  scatter chunks): they need the table and scatter plot types of M2.3; the README names them as
  the chapter's missing parts.
- The sector prices, the ETS and ESR prices and the SCC chart, empty in H12 runs (see above).
- The bar variants of the stacked charts and the total drawn as a line over a stack.
- Colours per value (the style registry) and a palette beyond eight hues.
- The other chapters of the report, the validation thresholds (piamValidation), the scenario
  descriptions and the file reference table of chapter 0, per-GDP variables, the IAMC hierarchy
  and summation groups in the builder.
- The REMIND noise level and a tolerance for it: two runs of one commit are not among the AMT
  runs fetched; a later measurement.

## Open questions for Tobias

1. **History in the two per-capita line Blicks** as the scenario value `historical (IEA)`
   (proposed), or no history at all in this example, leaving the concept's decision open.
2. **Bars.** Leave the bar variants out (proposed: the area chart with the scenario split
   carries the information, and more Blicks would double every flag), or add them as a family
   through `bk.register`, `stacked_bar` with `x="Scenario"` and a `Year` filter at 2050.
3. **The profile.** The region mapping (`H12`, proposed), so that a week with a failed scenario
   compares loudly instead of passing without a baseline, at the price of `--against` when one
   store holds several sets; or the exact scenario set, which never compares different sets
   but passes in silence when a scenario is missing. The run id `4 scenarios, latest
   2026-10-24_00.54.24` either way.
4. **The builder's dataset** over all 7,760 variables, none additive (proposed), or no dataset
   until the IAMC hierarchy exists.
5. **The data.** The two weekly sets of the PDF's four scenarios (fetched already, 295 MB), or
   a different or smaller selection; the `default-AMT` runs are an alternative single-scenario
   set.
6. **Scope confirmed:** the tables and the GDP-domain scatter wait for M2.3; the sector, ETS and
   ESR price charts are left out as empty in H12 runs; the five final-energy carrier charts are
   one Blick.
7. **Colours.** Record the eight-hue limit as the gap this example exposes (proposed), or widen
   the viewer's palette for stacks in this task.

## Decided by Tobias on 2026-10-29

All seven open questions as recommended: history as `historical (IEA)` in the two per-capita line
Blicks; no bar variants; the region mapping as the profile; the builder's dataset over every
variable; the two weekly sets fetched; the tables, the GDP-domain scatter and the sector, ETS and
ESR price charts out of scope, the five carrier charts as one Blick; the eight-hue limit recorded,
not widened.

## Decisions taken here, not asked

- A separate example project `examples/remind/`, not an extension of remind-mfa; `pyyaml` as its
  only dependency besides blicket.
- One Blick per figure chunk of the chapter, the five carrier charts merged, stacked areas and
  lines only, 20 in five groups named by content, not by the chapter's numbering.
- The reader and the run object at the project root (`remind.py`), the Blicks' helpers under
  `blicks/_iamc.py`; the Blicks import the helpers, blicket, polars, and from `remind.py` only its
  run type and constants.
- The folders are sorted by title, the run is kept wide and unpivoted per selection, the years
  end at 2100, and a `c(a, b)` cell is read as its last number when the numbers agree.
- Labels drop the common prefix of the variables, or come from a dict where the common prefix
  leaves them long; dimension values and scenario names are the mif's; `World` comes first.

## Results (2026-10-29)

Measured on 2026-10-29 with the code as it is, blicket at `57b9421` plus this task's changes
(dirty), in the example's environment (Python 3.14, polars 2.1.0, pyyaml 6.0.3), on a laptop with
8 cores. `build`, `serve` and `dev` used a viewer generated in the worktree from `57b9421` with
this task's tooltip fix (`pnpm generate`), not the main checkout's, which is generated from
uncommitted viewer changes.

**`blicket list`** exits 0 without a problem:

```
costs  Policy costs
  costs/consumption_loss                    Policy cost: consumption loss                             line
  costs/consumption_loss_relative           Policy cost: consumption loss relative to the reference   line
  costs/gdp_loss                            Policy cost: GDP loss                                     line
emissions  GHG and CO2 emissions
  emissions/ghg                             GHG emissions by source                                   stacked_area
  ...
supply  Electricity and primary energy
  supply/electricity_by_carrier             Electricity generation by carrier                         stacked_area
  supply/primary_energy_by_carrier          Primary energy by carrier                                 stacked_area

5 groups · 20 Blicks
```

The groups come in alphabetical order, not the chapter's; within a group the Blicks keep the
order of their module.

**`blicket build`** exits 0 with 20 built on each weekly set:

```
run 4 scenarios of REMIND 3.7.1.dev59, latest 2026-10-17_00.56.55 · profile H12 · blicks at 57b9421 (dirty) · loaded in 356 ms
20 Blicks: 20 built
build 92f902375302ceaf → .blicket/build/92f902375302ceaf

run 4 scenarios of REMIND 3.7.1.dev72, latest 2026-10-24_00.54.24 · profile H12 · blicks at 57b9421 (dirty) · loaded in 383 ms
20 Blicks: 20 built
build e94ee18b78c4bf21 → .blicket/build/e94ee18b78c4bf21
```

In five builds the loader took 0.34 to 0.43 s and the whole `uv run blicket build` 0.81 to 0.88 s,
with a peak resident memory of about 450 to 550 MB over the builds measured (zsh's `time`, `%M`;
`/usr/bin/time` is not installed). The run holds 67 MB of it (polars' estimate: 50 MB for the wide
frame of 361,724 rows and 20 columns with categorical keys, 17 MB for the 554,330 historical rows);
a Python process measured around `load_run` has 60 to 70 MB resident after its imports and about 490
to 510 MB after loading, the rest being what parsing the four 27 MB mifs as text allocated and the
allocator keeps. The build directory is 2.8 MB, 684 KB of it tables. The run records REMIND's commit
and branch (`8d9052ef8`, `5e5500ec0`, `develop`). The 2026-10-24 set with its folders given in
another order (`wo100EJBiobound`, `PkBudg1000`, `NPi2025`, `PkBudg750`) gives the same build,
`e94ee18b78c4bf21 (built before, left as it was)`. One folder alone builds as `run
SSP2-NPi2025-AMT_2026-10-16_22.12.36 · profile H12`; the NPi folder of one week with the PkBudg1000
folder of the other builds as `run 2 scenarios of REMIND 3.7.1.dev59, 3.7.1.dev72, latest
2026-10-24_00.54.24`, after `warning: the folders are of different REMIND commits:
SSP2-NPi2025-AMT_2026-10-16_22.12.36 3.7.1.dev59 at 8d9052ef8,
SSP2-PkBudg1000-AMT_2026-10-24_00.54.24 3.7.1.dev72 at 5e5500ec0`. `timing_ms` per Blick from the
two manifests:

| Blick | rows | ms, 10-17 set | ms, 10-24 set |
|---|---|---|---|
| `costs/consumption_loss` | 832 | 4.3 | 4.3 |
| `costs/consumption_loss_relative` | 832 | 3.6 | 3.4 |
| `costs/gdp_loss` | 832 | 4.1 | 3.7 |
| `emissions/ghg` | 6656 | 6.6 | 6.1 |
| `emissions/ghg_by_sector` | 14144 | 8.0 | 7.8 |
| `emissions/ghg_per_capita_by_sector` | 14144 | 11.2 | 10.8 |
| `emissions/co2_by_sector` | 14144 | 8.3 | 9.5 |
| `emissions/co2_per_capita_by_sector` | 14144 | 12.0 | 11.8 |
| `emissions/co2_cumulated_by_sector` | 13312 | 8.6 | 8.4 |
| `final_energy/by_sector` | 3328 | 7.0 | 5.7 |
| `final_energy/per_capita_by_sector` | 3328 | 7.1 | 7.5 |
| `final_energy/per_capita` | 1274 | 10.8 | 10.8 |
| `final_energy/per_capita_by_sector_lines` | 3822 | 15.8 | 10.7 |
| `final_energy/by_carrier` | 4992 | 8.4 | 4.6 |
| `final_energy/by_sector_and_carrier` | 17472 | 11.4 | 9.6 |
| `final_energy/non_energy_use_by_carrier` | 2496 | 7.1 | 5.3 |
| `prices/co2` | 832 | 5.6 | 4.8 |
| `prices/co2_by_region` | 768 | 4.5 | 4.7 |
| `supply/electricity_by_carrier` | 12480 | 9.8 | 7.1 |
| `supply/primary_energy_by_carrier` | 7488 | 8.4 | 6.0 |

163 ms and 143 ms for all 20. No table has a null value. The history of the two per-capita line
Blicks is 442 rows of IEA (13 regions, 1990 to 2023) next to the 832 of the scenarios, so
`final_energy/per_capita` has 1,274 rows and the sector lines three times that; WDI's population
covers every IEA row. The stacks against their totals, the difference of the layers' sum and the
total in every scenario, region and year divided by the largest total of that region: at most
2.9e-7 in every chart but the CDR sector's final energy, and 7.1e-5 there, whose totals are a few
thousandths of an EJ/yr and whose difference is the mif's rounding to 1e-7 EJ/yr. In both weeks
`Price|Carbon|SCC` is zero in all 832 rows, and the GHG and CO2 layers of the CDR sector (gross),
the CDR sector's process emissions, OAE and EW are zero in all 832 rows each, cumulated or not.

**`blicket check`** of the 2026-10-24 set, with the 2026-10-17 set pushed, exits 1:

```
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

Every Blick is flagged `value`, none `schema`: both sets have the same scenarios, regions, years,
items and IEA years. The magnitudes from `comparison.json`, largest first:

| Blick | magnitude | where |
|---|---|---|
| `final_energy/by_sector_and_carrier` | 0.996 | SSP2-PkBudg750-AMT, CHA, 2100, CDR, Electricity |
| `costs/gdp_loss` | 0.43 | SSP2-PkBudg1000-AMT, USA, 2060 |
| `costs/consumption_loss` | 0.364 | SSP2-PkBudg750-AMT, USA, 2100 |
| `costs/consumption_loss_relative` | 0.156 | SSP2-PkBudg750-AMT, USA, 2100 |
| `final_energy/non_energy_use_by_carrier` | 0.0686 | SSP2-PkBudg750-AMT, USA, 2100, Gases |
| `final_energy/by_carrier` | 0.0614 | SSP2-PkBudg750-AMT, USA, 2100, Liquids |
| `final_energy/per_capita_by_sector_lines` | 0.0387 | SSP2-PkBudg750-AMT, USA, 2100, Transport |
| `supply/primary_energy_by_carrier` | 0.0343 | SSP2-PkBudg1000-AMT, USA, 2100 |
| `supply/electricity_by_carrier` | 0.0305 | SSP2-PkBudg750-AMT, USA, 2100 |
| `emissions/co2_by_sector` | 0.025 | SSP2-PkBudg750-AMT, USA, 2100 |
| `emissions/co2_per_capita_by_sector` | 0.0222 | SSP2-PkBudg750-AMT, MEA, 2100, CDR\|DACCS |
| `emissions/ghg_by_sector` | 0.0221 | SSP2-PkBudg750-AMT, USA, 2100 |
| `emissions/ghg` | 0.0213 | SSP2-PkBudg750-AMT, USA, 2100, CO2\|Energy |
| `final_energy/by_sector` | 0.0203 | SSP2-PkBudg750-AMT, USA, 2100, Transport |
| `emissions/ghg_per_capita_by_sector` | 0.0164 | SSP2-PkBudg750-AMT, MEA, 2100, CDR\|DACCS |
| `final_energy/per_capita_by_sector` | 0.0157 | SSP2-PkBudg750-AMT, USA, 2100, Transport |
| `final_energy/per_capita` | 0.011 | SSP2-PkBudg750-AMT, MEA, 2100 |
| `prices/co2_by_region` | 0.00737 | SSP2-PkBudg1000-AMT, CAZ, 2070 |
| `emissions/co2_cumulated_by_sector` | 0.0058 | SSP2-PkBudg750-AMT, MEA, 2100, CDR\|DACCS |
| `prices/co2` | 0.00515 | SSP2-PkBudg1000-AMT, CAZ, 2070 |

The review's probe is confirmed: 0.005 for the CO2 price, 0.02 for GHG by source, 0.06 for FE by
carrier, 0.4 for the policy costs and 1.0 for the FE of the CDR sector. The top mover is a real
change that is small in absolute terms: the electricity of China's CDR sector in 2100 in
SSP2-PkBudg750-AMT went from 0.00005 to 0.014 EJ/yr (direct air capture starting), all of the
scale of that sector's panel, which has its own scale with `independent_y` (see Deviations); on a
shared axis across the sectors the same Blick measured 0.149. The policy costs move most among the
rest, because they are differences of two scenarios. The two IEA histories contribute no change.
The `where` of a stacked Blick names no layer when the stack's sum changed most.

**`blicket check` with one folder left out** (`SSP2-PkBudg750_wo100EJBiobound-AMT`) finds the
same baseline, since the profile is the region mapping, and exits 1:

```
run 3 scenarios of REMIND 3.7.1.dev72, latest 2026-10-24_00.54.24 · profile H12 · blicks at 57b9421 (dirty) · loaded in 276 ms
20 Blicks: 20 built
build 2e4069e5994c0759 → .blicket/build/2e4069e5994c0759

baseline 92f902375302ceaf · run 4 scenarios of REMIND 3.7.1.dev59, latest 2026-10-17_00.56.55 · blicks at 57b9421 (dirty) · built 2026-10-29 08:48 UTC
vs baseline: 20 value · 20 schema
top movers: (as above)
flagged: 20 of 20 Blicks
comparison → .blicket/build/2e4069e5994c0759/compare/92f902375302ceaf

schema
  costs/consumption_loss
    Scenario removed: SSP2-PkBudg750_wo100EJBiobound-AMT
  ... (the same line for each of the 20 Blicks)
```

`blicket check` of the folder `SSP2-PkBudg1000-AMT_2026-10-24_00.54.24` alone finds the same
baseline and reports `20 value · 20 schema`, each Blick with `Scenario removed: SSP2-NPi2025-AMT,
SSP2-PkBudg750-AMT, SSP2-PkBudg750_wo100EJBiobound-AMT`, exit 1.

**The loader's errors and warnings**, on small folders made for the purpose: a run path that is a
file (`... is not a directory; pass one REMIND output folder per scenario`), a `cfg.txt` without
`title` and `model_version` (`.../cfg.txt sets no title, model_version`), a mif with
`FE|+|Transport` and `FE|Transport` (`.../REMIND_generic_Twin.mif reports FE|Transport (EJ/yr) twice
in a region, with the summation markers stripped`), a folder without its mif (`... holds no
REMIND_generic_NoMif.mif; did the run finish, and was the file fetched (see the README)?`), two
folders of one scenario (`SSP2-PkBudg1000-AMT_2026-10-24_00.54.24 and
SSP2-PkBudg1000-AMT_2026-10-17_00.56.55 are both of SSP2-PkBudg1000-AMT; pass one folder per
scenario`), two region mappings (`pass runs of one region mapping; these are of several:
Eu_2026-10-24_00.00.00 21_EU11, Tiny2_2026-10-24_00.00.00 H12`) and a mif of another scenario
(`.../REMIND_generic_SSP2-PkBudg750-AMT.mif holds the scenario SSP2-PkBudg1000-AMT, not
SSP2-PkBudg750-AMT as .../cfg.txt names it`) each exit 2 with the loader error. A small folder with
only `FE`, `FE|Transport` and `Population` builds 1 Blick and fails 19, each naming its variables
(`transformation raised ValueError: the run has none of Price|Carbon`); its Population with
`c(6500, NaN)` and `NA` cells gives `warning: ...: 1 cells could not be read and are missing:
Population (1)` and fails the per-capita Blicks with `no Population for Tiny: 2005, 2010`. With a
complete population it builds the per-capita lines with `warning: the run has no FE|Buildings,
FE|Industry` and `warning: 2 historical rows have no WDI population`, the EU27 rows of its
`historical.mif` left out without an error. The real mifs give no warning: the 247 Population cells
of each NPi mif are read as their second numbers (World 7,859.46 million in 2020 in all four
scenarios).

**`blicket dev`** on the 2026-10-24 set (`--port 8781`) prints the check's report and
`builder: 7760 quantities, 3 dimensions`. `/dev/dataset`, the builder's list, is 1.7 MB of JSON,
answered in 9 ms. A query of `Emi|GHG` as lines by scenario for EUR answers in 6 ms with 64 rows;
`GDP|PPP [billion US$2017/yr]` for World works the same; `Emi|GHG` summed over Region is refused
(`Emi|GHG is not additive, so it cannot be summed over Region; keep it as a filter or on a
channel`). In headless Chrome (1500 × 1100, driven over the DevTools protocol), the quantity picker
takes 3.0 to 4.0 s to open with its 7,760 options (six openings), and `Emi|GHG` pasted into its
search leaves 105 options after 0.24 to 0.48 s; the builder URL
`#/builder?_q=Emi%7CGHG&_c.x=Year&_c.color=Scenario&_keep=Region&Region=EUR` charts it. The picker
renders every option (Nuxt UI's `USelectMenu` without virtualisation), which is what the three
seconds are; recorded, not fixed. `blicket serve` of the checked build serves the manifest and
`compare/index.json`.

**The viewer.** Each Blick was opened in the `dev` session at its defaults and split by Region
(`?_split=Region&Scenario=SSP2-PkBudg750-AMT` for the stacked ones, `?_split=Region` for the lines,
with `Sector=Industry` or `Sector=Transport` for the two Blicks split by sector, and
`prices/co2_by_region` filtered to a scenario instead, since Region is its colour), as full-page
screenshots in headless Chrome with the comparison on, and compared with the PDF's pages 18, 20, 34,
35, 36 and 66 for the shape. The screenshots of the ten Blicks whose titles or tables are not those
of the first screenshots (nine retitled, and the electricity chart without Net Imports) and of
`final_energy/per_capita_by_sector` were taken again with the code as it is, 22 and the overview.
`final_energy/per_capita` hovered at 1996, 2013 and 2016 lists the four scenarios as `–` and
`historical (IEA)` with its number (47.3, 52.9, 52.7 GJ/yr per capita). What matches: every chart
renders without a console error; the stacked charts open as the report's first figure (World, one
panel per scenario) and give the regional page when split, World first and flattening the regions on
the shared axis, readable with "Own y axis per panel"; the per-capita stacks are comparable across
regions on the shared axis; the line charts have the scenarios in colour with the IEA history from
1990 to 2023 joining the model years on one axis (World final energy per capita about 55 GJ in 2020,
73 in 2100 for NPi, about 62 for the budgets, as on page 36); the CO2 prices end at 520 and 740
US$2017/t as on page 66; the faded baseline and the two change charts work in every Blick. What
looked wrong, and what became of it:

- The Blicks' descriptions showed reST's double backticks literally (``` ``Emi|GHG`` ```); the
  Blick docstrings name variables in plain text now. The helpers and the loader keep the
  backticks of blicket's own docstrings, since the viewer never shows them.
- The long titles wrapped the overview's rows; the GHG titles say "GHG", the policy costs are
  "Policy cost: ...", since "Changed since the baseline" shows titles without their group.
- The tooltip's `undefined`, fixed (see "What the example exposes").
- Hues repeat in the seven stacked Blicks with more than eight layers: Hydrogen and Biomass w/ CC
  share a blue in electricity, Coal and Solar in primary energy, as planned; `prices/co2_by_region`
  tells its twelve regions apart by dashes. Recorded (open question 7).
- The viewer stacks the first legend item on top; the report stacks it at the bottom (CO2 from
  energy under the other gases on page 18). Recorded; the legend order and the stack agree.
- The IEA history is a line, where the report draws points. Recorded; there is no point mark.
- The relative change chart under a near-zero baseline runs off to −25,000 % (CO2 from non-energy
  CDR in CHA). Recorded; the absolute change chart above it reads well.
- Panel titles of the long scenario name are cut (`SSP2-PkBudg750_wo100EJBiobound-...`) in rows of
  four panels with their own y axes. Recorded.

What could not be verified: the `rsync` command of the README against the cluster (its filter was
tried on a local copy), a build on a second machine, the dev loop's reload, which does not exist
yet, and the viewer by hand rather than in screenshots.

From the worktree root, blicket's suite (615 tests, run with `TMPDIR` and `--basetemp` under the
home directory, since `/tmp` was full), `ruff check`, `ruff format --check` and `ty check` pass with
the example included; in `viewer/`, `pnpm test` (149 tests, the new one included), `pnpm lint` and
`pnpm typecheck` pass.

## Deviations

- The helpers are two functions: `select(run, items, unit, dimension=None, *, equivalent=(),
  source=None)`, which reads the scenarios or, with `source`, one source of `historical.mif`
  (filtered to the run's regions) under the scenario `historical (<source>)`, and
  `per_person(run, items, unit, dimension=None, *, equivalent=(), history=())`, which selects the
  scenarios and each history source and divides by REMIND's population for a scenario and WDI's
  for a source (joined in millions, `validate="m:1"`, factors 1 for Mt and 1e3 for EJ), instead
  of `select(run, items, dimension, unit, ...)` and `per_capita(frame, run)`. The units are named
  constants in `_iamc.py`, `DIMENSIONS` and `WORLD` live in `remind.py`, and the run gains
  `sources`, the data sources of `historical.mif`, so that `Scenario` is an Enum of the titles,
  then every `historical (<source>)`, and history sorts last whatever its name.
- An item the run lacks is not silent: `select` names the variables it finds no rows for on
  stderr, and raises `ValueError` (`the run has none of ...`) when it finds none, so a Blick of a
  failed reporting step is an error that names its variables. A scenario row without a population
  is an error naming the scenario and years; a historical row without one is left out with a
  warning. The plan had a missing item drop out silently, as the report only warns.
- `prices/co2_components` is left out: `Price|Carbon|SCC` is zero in every row of every AMT run,
  so the chart was the CO2 price as a one-layer stack, flagged with it every week. The example has
  20 Blicks, `prices.py` two. `SE|Electricity|Net Imports` is out of the electricity list, which
  would otherwise warn on every build.
- The run id names the REMIND version, `4 scenarios of REMIND 3.7.1.dev72, latest ...`, from
  `model_version` in `cfg.txt`; folders of different versions or commits name every version and
  get a warning that lists each folder's commit, so a set that mixes weeks does not build a
  plausible, wrong comparison without a word. One folder keeps its name as the id.
- Titles: "GHG emissions by source/by sector/per capita by sector", "Final energy per capita, with
  IEA history" (the total line), "Final energy per capita by sector, with IEA history" (the lines),
  "Final energy for non-energy use by carrier", "Policy cost: consumption loss", "... relative to
  the reference" (unit `% of reference consumption`), "Policy cost: GDP loss"; the descriptions
  say "per capita" and name "REMIND's compareScenarios report".
- The Blick modules import polars and, from `remind`, its `Run`, `DIMENSIONS` and `WORLD` at
  runtime, as `_iamc.py` imports both anyway; polars for the annotations, the split of the
  sector-carrier variables into `Sector` and `Carrier` and for leaving World out of
  `prices/co2_by_region`, `WORLD` for every `defaults={"Region": WORLD}`. The plan had the Blicks
  import nothing but the helpers and blicket; `remind.py` imports only polars and yaml, so they
  import no more of the loader than its run type and constants.
- `final_energy/by_sector_and_carrier` sets `independent_y=True`. Its Sector split stands for the
  report's five separate charts, each with its own axis, and the CDR sector is four orders of
  magnitude below industry, so on a shared axis its panel is flat and its changes measure nothing
  (0.149 instead of 0.996 in the check above, the CDR change then invisible).
- The CO2 per capita is in `t CO2/yr per capita`, where the report writes `t CO2eq/yr/pCap` for
  CO2 too; the per-capita units say "per capita" where the report writes `/pCap`, as the plan's
  table has them.
- The plan's "eight of the fifteen stacked Blicks" were seven of fourteen (14 stacked and 7 line
  Blicks of 21); with the SCC chart left out, seven of thirteen. The seven are those with the 17,
  17, 17, 17, 16, 15 and 9 layers the plan lists.
- The loader reads `title`, `regionmapping` and `model_version` from `cfg.txt`, a missing one a
  named error, and finds the mif by name, `REMIND_generic_<title>.mif`, instead of by a glob. The
  mapping's name drops `regionmapping` and an underscore after it (`regionmapping_21_EU11.csv` →
  `21_EU11`). The run id of several folders needs the timestamp in each folder's name; a renamed
  folder in a set is an error that names it. A folder other than the first without
  `historical.mif`, or with a different one, is a warning; the first must have one. The errors
  say what to do (pass a directory, one folder per scenario, runs of one mapping; check that the
  run finished and the file was fetched).
- After the markers are stripped, each mif must have (Scenario, Region, Variable, Unit) unique; a
  marked and an unmarked twin is a loader error naming the variable, where it would otherwise be
  a duplicate-row error on a Blick or a double count in the builder.
- A number that is not finite (`Inf`, `NaN`, also inside `c(a, b)`) counts as a cell that could
  not be read, missing and in the warning, since blicket refuses infinite values in a table.
- Four variables of the mifs have no unit (`Internal|Price|Biomass|Multfactor`,
  `Internal|Price|Biomass|Shiftfactor`, `PVP2|Good`, `PVP3|Permit`); their quantities in the
  dataset have no unit, and the table function matches the missing unit. Some variables carry
  brackets in their names already (`SE|Biochar [Mt]`); only `GDP|PPP` gets a unit appended.
- In the viewer, outside the example: the hover rule's tooltip writes an en dash for a series
  without a row at the hovered x instead of `undefined` (`viewer/app/plots/encodings.ts`, a test in
  `viewer/tests/plots.test.ts`), found on the per-capita Blicks.
- The example's README has parts the plan's Documentation section did not ask for: a quick start
  at the top, a sentence on installing from a wheel on a cluster without Node and on a shared
  `store`, a paragraph on what all 20 flagged means and what `tolerance` is for, one on checking a
  single folder, and the note that four layers of the GHG and CO2 charts are zero in these runs.
- The root `.gitignore` ignores `data_out` without the trailing slash, so that the `data_out`
  symbolic link of a worktree is ignored like the directory. The root README's section is
  "Examples", for the two.
