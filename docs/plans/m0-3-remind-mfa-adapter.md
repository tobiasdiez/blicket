# M0.3 remind-mfa adapter and first Blicks

Status: plan, 2026-10-24, revised the same day after an independent review that built a probe
version of the example against the three runs, and signed off by Tobias the same day. Third task of [m0-tasks.md](m0-tasks.md), building
on M0.2 (commit `e46088d`). Companion to [architecture.md](../architecture.md) ("Adapter and
loader protocol", "Project basics").

## Goal

The first real project: `examples/remind-mfa/` loads a pickled remind-mfa run and defines the
first Blicks, ported from remind-mfa's own plastics figures. `blicket build` runs end to end on
the example runs in `data_out/`, and the loader and transformation times are recorded. The
dataset protocol the dev-mode Blick builder will need is sketched on paper, not coded.

## The flow this task enables

1. In the example project, `uv sync` installs blicket and remind-mfa into one environment.
2. `uv run blicket build ../../data_out/<run>` prints

   ```
   run 2026-10-24--01-25-28_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at e46088d · loaded in 666 ms
   10 Blicks: 10 built
   build 7c1e0a9d2b4f6e38 → .blicket/build/7c1e0a9d2b4f6e38
   ```

   and exits 0. The build directory holds one Parquet file per Blick and the manifest with the
   dimension values (regions, end uses, polymers, years) each Blick exposes.
3. Building the other runs yields more build directories: the unchanged rerun's tables are
   byte-identical; the changed run differs in `flows/production_by_source` (recycled production
   10 % lower, primary 2.1 % higher) and, by float rounding only, in the two production tables.

## Facts the plan rests on (checked 2026-10-23/24, several by the plan review's probe build)

- A run folder is `data_out/<prefix>_<model>_<scenario>_<regions>/model.pickle`; the prefix is a
  timestamp by default but configurable in remind-mfa. The pickled object is a `PlasticsModel`
  with `future_mfa` and `historical_mfa` (flodym `MFASystem`s), `cfg` (`cfg.model`,
  `cfg.model_switches.scenario`, `cfg.input.region_mapping` give model, scenario and region
  set), `dims`, `parameters`, `stock_handler`. Unpickling needs `remind_mfa` and `flodym`
  importable; it takes about 0.7 s in the example's environment, hashing the 112 MB file 0.04 s
  when cached, each transformation 3 to 11 ms.
- **The original three runs in `data_out/` predated remind-mfa's HEAD** and were replaced (see
  Measurements). They carried the dimensions `Material` (m) and `Type` (p); since remind-mfa #255
  (2026-10-20) HEAD names them `Polymer` (p) and `Polymer Type` (P). A pickle loads only with the
  remind-mfa version that wrote it (older pickles fail with an `AttributeError` on import), it
  carries no model commit, and the checkout's HEAD must never be reported as one.
- `FlodymArray` supports `sum_to(letters)`, `sum_over`, `get_shares_over`, arithmetic between
  arrays with broadcasting (dividing a (t, r, u) array by `population` (t, r) keeps (t, r, u)),
  and `to_df()` returning a pandas frame with a named MultiIndex and one `value` column. blicket
  accepts the array itself (duck-typed `to_df()`), so Blicks return arrays, not frames.
- The example's environment is not remind-mfa's own: resolving blicket and remind-mfa together
  gives pandas 3.1, flodym 1.1, pyam 4.0, ixmp4 0.17 on Python 3.14. remind-mfa → ixmp4 →
  scse-toolkit pins `polars<2.0`, which conflicts with blicket's `polars>=2.0`; a uv dependency
  override resolves it (137 packages, `uv sync` in 6 s), and the probe Blicks built with it.
- remind-mfa's figures live in `CommonVisualizer` and `PlasticsVisualizer`: use stock by region
  and by end use, consumption by end use, production by polymer, production versus net imports
  versus consumption, end-use split shares, GDP per capita, scenario rates, polymer splits, trade
  per market, and a Sankey (M4).
- Evidence for M0.4: on the fresh runs the two unchanged reruns give byte-identical tables for
  all Blicks; the changed run differs in `flows/production_by_source` and, by at most 3.9e-16
  relative per cell, in the two production tables (production is the invariant sum of primary and recycled
  output). Production by polymer holds 573 tiny negatives (down to −1.25e-7 against a maximum of
  9.6e7), sign crossings near zero: the zero floor's test case.

## Approach

### Layout

```
examples/remind-mfa/
  pyproject.toml            a virtual uv project (no build system): deps blicket (path ../..),
                            remind-mfa (path ../../../remind-mfa, editable) and pandas, the polars
                            override, an empty [tool.blicket]
  uv.lock                   committed; it pins remind-mfa's tree and works where the sibling
                            checkout exists
  README.md                 how to sync, where the runs are, how to build
  blicketconf.py            load_run and nothing else, found by convention (decided 2026-10-24
                            after the task: Tobias asked for a root-level file like pytest's
                            conftest.py; `blicket.py` is impossible since the root is on sys.path
                            and would shadow the package)
  blicks/
    stocks.py               use stock by region, by end use
    flows.py                consumption, production by polymer and by source,
                            production/trade/consumption, end-use split
    drivers.py              gdp per capita, scenario rates, polymer splits
```

The example is its own uv project, not a workspace member: it needs remind-mfa's heavy
dependency tree, which blicket's own environment must not carry, and it shares one environment
with blicket because the pickle must unpickle where blicket runs. blicket is a path dependency,
not editable, and builds with isolation (no build group needed in the example). uv rebuilds a
path dependency only when its `pyproject.toml` changes, so blicket's own `pyproject.toml` gets
`[tool.uv] cache-keys` on `pyproject.toml`, `meson.build` and `src/**/*.py`; then `uv run` in the
example picks up blicket changes. remind-mfa is an editable path dependency on the sibling
checkout, so checking out another commit there takes effect at once (a pickle loads only with the
version that wrote it); a git source pinned to a commit is the alternative when the example should
work without the checkout. The runs stay in `data_out/` at the repository root, gitignored. ty
keeps checking the example's `bk.*` calls through a `[[tool.ty.overrides]]` block that ignores the
`remind_mfa` and `flodym` imports it cannot resolve. A `.gitattributes` keeps `examples/` out of
the sdist.

### Loader

```python
def load_run(selection: bk.RunSelection) -> tuple[PlasticsModel, bk.RunInfo]:
    folder = selection.path
    with (folder / "model.pickle").open("rb") as file:
        run = pickle.load(file)
    cfg = run.cfg
    profile = f"{cfg.model.value}_{cfg.model_switches.scenario}_{cfg.input.region_mapping}"
    return run, bk.RunInfo(id=folder.name, profile=profile, fingerprint=bk.fingerprint(folder / "model.pickle"))
```

- The run id is the folder name; the profile comes from the pickle's config, not from parsing
  the name (which breaks on a scenario with underscores and on a custom prefix). A folder without
  `model.pickle` is a loader error naming the expected file.
- The three example runs share one profile, as M0.7's baseline resolution expects for reruns.
- The model commit stays `None`. A commit written by remind-mfa's export is the right source and
  a note for that project, not for blicket.
- The run object is the unpickled model as is. Blicks read `run.future_mfa`; `historical_mfa` is
  available for later Blicks that overlay history.

### The Blicks

Ported from `visualize_common` and the plastics `visualize_custom`; they may look different from
the originals. Each returns a flodym array or, for the three tables that combine several
quantities under a naming dimension, a pandas frame built with `pd.concat({...}, names=[...])`;
no helper module. Dimension names are flodym's as they
appear in the pickle (`Time`, `Region`, `End Use`, `Polymer`), the measure column is `value`.
Dimensions not bound to a channel become controls once M0.5 derives them; here they are declared.

| id | source figure | table (dims → value) | plot |
|---|---|---|---|
| `stocks/use_by_region` | `visualize_use_stock` | Time, Region | line x=Time, color=Region |
| `stocks/use_by_end_use` | `visualize_fdarr_stacked(stock, "End Use", regional=False)` | Time, End Use | stacked_area x=Time, color=End Use |
| `flows/consumption_by_end_use` | `visualize_consumption` | Time, Region, End Use (inflow summed over element and type) | stacked_area x=Time, color=End Use, controls Region split |
| `flows/production_by_polymer` | `visualize_production` | Time, Region, Polymer | stacked_area x=Time, color=Polymer, Region split |
| `flows/production_by_source` | `visualize_production`'s two summands | Flow ∈ {Primary, Recycled}, Time, Region | stacked_area x=Time, color=Flow, Region split (added in review round 1: the only Blick that sees the deliberately changed run) |
| `flows/production_trade_consumption` | `visualize_production_trade_consumption` | Flow, Time, Region | line x=Time, color=Flow, Region split |
| `flows/end_use_split` | `visualize_end_use_split` | Time, Region, End Use (shares, fractions) | stacked_area x=Time, color=End Use, Region split |
| `drivers/gdp_per_capita` | `visualize_gdppc` | Time, Region | line x=Time, color=Region |
| `drivers/scenario_rates` | `visualize_scenario_params` | Parameter, Time, Region (six rates as fractions) | line x=Time, color=Region, Parameter split |
| `drivers/polymer_splits` | `visualize_polymer_splits` | Region, End Use, Polymer (last historical year) | stacked_bar x=Region, color=Polymer, End Use split |

Ten Blicks in three groups (nine planned, one added in review round 1); m0-tasks.md asked for
five to eight and listed trade, which is left out: imports and exports in one chart need a sign convention, a plot-type question for M0.5 or
M4. The six scenario rates are one Blick with a `Parameter` dimension rather than a family: they
are inputs, identical across reruns, and one Blick shows the dimension mechanism as well as six
would. Rates stay fractions (×100 is display); the polymer-split year is the last historical year
(`mfa.dims["h"].items[-1]`), as remind-mfa's own comment intends. Historical overlays are
deferred with the reference-data question of the concept.

### Measurements

The example runs: produced on 2026-10-24 from remind-mfa HEAD `a7c389a` with input data
`rev2.8.0_h12` (fetched from the cluster; HEAD's plastics model needs it, the local 2.4.1
archive lacks the renamed parameter files). A model run takes about 3 s. Folders in `data_out/`:
`2026-10-24--01-25-28` and `2026-10-24--01-25-31` are unchanged reruns (the noise sample),
`2026-10-24--01-25-34` has `collection_rate` scaled by 0.9 in the plastics compute step (the
deliberate change for the comparison tasks); `data_out/RUNS.md` says the same.

Recorded in this plan file when the task ends: the loader line of `blicket build` per run, the
per-Blick `timing_ms` from the manifest, and the total build time for one run. The loader takes
under a second and all transformations together about a tenth of a second (see below), far from
the architecture's ten-second threshold, so no loader cache.

Results, 2026-10-24, blicket at `e46088d` plus this task's changes (dirty), in the example's
environment. `uv run blicket build ../../data_out/<run>` exits 0 with ten built Blicks on each
run:

```
run 2026-10-24--01-25-28_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at e46088d (dirty) · loaded in 666 ms
run 2026-10-24--01-25-31_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at e46088d (dirty) · loaded in 688 ms
run 2026-10-24--01-25-34_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at e46088d (dirty) · loaded in 663 ms
```

The loader time includes importing remind-mfa (the Blick modules import it for type checking
only). A whole `blicket build` of one run, from `uv run` to exit, takes 1.2 to 1.4 s (three
builds of `01-25-28` into fresh directories). `timing_ms` per Blick from the manifest of
`01-25-28`, with the rows of each table:

| Blick | rows | ms |
|---|---|---|
| `drivers/gdp_per_capita` | 1812 | 34.6 |
| `drivers/scenario_rates` | 10872 | 9.9 |
| `drivers/polymer_splits` | 1248 | 4.7 |
| `flows/consumption_by_end_use` | 14496 | 9.7 |
| `flows/production_by_polymer` | 23556 | 11.0 |
| `flows/production_by_source` | 3624 | 6.2 |
| `flows/production_trade_consumption` | 7248 | 9.4 |
| `flows/end_use_split` | 14496 | 8.1 |
| `stocks/use_by_region` | 1812 | 3.9 |
| `stocks/use_by_end_use` | 1208 | 4.1 |

102 ms for all ten. The first Blick carries the warm-up of the table conversion: in other builds
`drivers/gdp_per_capita` took 11 ms, and the others are within a millisecond or two per Blick.

Table hashes from the manifests:

- `01-25-28` against `01-25-31` (unchanged reruns): all ten identical, although the pickles,
  and so the fingerprints, differ. Unlike the old runs of the probe build, these reruns show no
  solver noise in the raw tables.
- `01-25-28` against `01-25-34` (`collection_rate` × 0.9): `flows/production_by_source`
  carries the deliberate change. Recycled production is 10 % lower and primary production 2.1 %
  higher over all years and regions (1.0 % in 2025, 3.2 % in 2100); the largest cell changes by
  1.1e7 t, 2.7 % of the table's largest value. `flows/production_by_polymer` and
  `flows/production_trade_consumption` differ by float rounding only (at most 1.5e-16 of the
  table's largest value), because production is the sum of primary and recycled, which the change
  leaves invariant; they are a second noise sample. The other seven are identical: consumption,
  stocks and the stored parameters do not change, `collection_rate` included, since the scaling
  happens in the compute step.

### Dataset protocol, sketched on paper

What the M2 Blick builder will ask of a run object, as a Python protocol in this plan only,
implemented nowhere yet:

```python
class Dataset(Protocol):
    def quantities(self) -> list[Quantity]: ...          # flows, stocks, parameters: name, unit, dimensions
    def dimensions(self, quantity: str) -> list[DimensionInfo]: ...   # name, values, display order
    def hierarchy(self, dimension: str) -> Tree | None: ...  # IAMC variable trees with summation groups
    def styles(self, dimension: str) -> dict[str, Style]: ...  # colours per value, optional
    def select(self, quantity: str, values: Mapping[str, Sequence[Hashable]]) -> Table: ...  # labelled long table
```

MFA quantities have different dimension sets (a flow on t, e, r, p; a parameter on t, r), so
dimensions are per quantity and a "quantity" choice comes before the dimension choices; units
belong to the quantity. What the ten Blicks actually do adds two operations the sketch must
carry: seven of them aggregate (`sum_to` a chosen set of dimensions), so `select` needs a
keep-dimensions argument; and three Blicks stack several quantities under a naming dimension
(`pd.concat(..., names=["Flow"])`), which the builder needs as "several quantities, one chart".
Arithmetic between quantities and shares stay outside the builder. A blicket helper for stacking
earns its place only when M2's builder needs the same operation; until then `pd.concat` is the
answer and no helper is added. For remind-mfa, `quantities` would list `future_mfa.flows`,
`stocks` and `parameters`, `dimensions` would read the array's `dims`, `select` would be `sum_to`
plus `to_df()`, and `hierarchy` is `None`. Nothing in this task depends on the sketch.

## Affected areas

- New: everything under `examples/remind-mfa/`, `.gitattributes`.
- Changed: the root `pyproject.toml` (`[tool.uv] cache-keys`, a `[[tool.ty.overrides]]` block for
  `examples/**`), the root `README.md` (the example paragraph, the run line, the development
  note); in `src/blicket/`, three small fixes the example revealed, each with a test:
  `_validation.py` (the transformation signature check evaluated annotations, which broke
  `TYPE_CHECKING`-only imports on 3.14), `builder.py` and `cli.py` (the run line showed the
  stored build's load time and called the Blick repository's commit `HEAD`).
- The CI workflow does not build the example (it needs the sibling checkout and the gitignored
  runs); the example's README says so.

## Testing

The example has no test suite of its own: pytest is not among its dependencies, CI never runs
it, and tests on synthetic flodym arrays would be the fixture sprawl the conventions avoid. The
acceptance test is the recorded build: `blicket build` on each run in `data_out/` exits 0 with
ten built Blicks; the manifests of the two unchanged reruns differ only in build id, run id,
paths, fingerprint and timings (their tables are byte-identical), and the changed run differs in
`flows/production_by_source` (and by float rounding only in the two production tables). blicket's
own suite, extended by the tests of the three fixes, still passes; `ty` and `ruff` pass with the
example included.

## Out of scope

Canonical form and the noise measurement (M0.4), controls and diff (M0.5), trade and Sankey
Blicks, historical overlays, display names and colours (viewer), a shipped IAMC adapter, a model
commit in the run info (remind-mfa's side).

## Decided by Tobias on 2026-10-24

1. **Fresh runs from the current checkout.** The old runs in `data_out/` are deleted and
   replaced by runs produced from HEAD: two unchanged reruns (the noise sample) and one with a
   constant changed in the plastics compute step (`collection_rate` scaled by 0.9), which is the
   "real change" sample for the comparison tasks. Which folder is which is recorded below. The
   Blicks are written against HEAD's names (`Polymer`).
2. **Path dependency** on `~/code/remind-mfa`; the Blicks live in this repository under
   `examples/remind-mfa/`, remind-mfa is only a dependency.
3. **Nine Blicks** as listed, trade left out, the six rates as one Blick. (Review round 1 added a
   tenth, `flows/production_by_source`, because the changed run was invisible to the nine.)

## Decisions taken here, not asked

- The example is a virtual uv project with blicket as a non-editable path dependency and a
  dependency override for polars; blicket's pyproject gets `cache-keys` so the example sees
  blicket changes.
- One run folder per selection; the profile comes from the pickle's config; the model commit
  stays unknown.
- Blicks return flodym arrays directly; no helper module; dimension names are flodym's.
- No test suite in the example; the recorded build is the acceptance test.

## Deviations

- `drivers/scenario_rates` is a third table built with `pd.concat`, with the six parameter
  names (`collection_rate`, ...) as the values of `Parameter`.
- The Blick modules import `flodym` and `remind_mfa` under `TYPE_CHECKING`, for annotations
  only, so `blicket list` does not import remind-mfa and the loader time includes its import.
  That revealed a bug: blicket's check of a transformation's signature evaluated its annotations,
  so on Python 3.14 a name imported under `TYPE_CHECKING` failed the module's import with a
  `NameError`. `_validation._transform` now reads the signature with
  `annotation_format=Format.FORWARDREF`; a test in `test_definitions.py` covers it.
- The loader rejects a pickle written by another remind-mfa version (`AttributeError` or
  `ImportError` while unpickling) with a message naming the remind-mfa checkout, and a run
  of another model than plastics; both failed with raw errors or plastics titles on steel runs
  before. remind-mfa is an editable path dependency, so a run unpickles with the code of the
  commit checked out next to this repository; non-editable, uv would keep the version of the
  last sync.
- Ten Blicks: `flows/production_by_source` (primary and recycled production per region) is
  added because none of the nine shows the deliberate change of `collection_rate`.
- blicket's run line shows this build's load time on a rebuild, from the manifest it computed,
  not the stored one's, and names the Blick repository's commit as `blicks at <commit>` instead of
  `HEAD <commit>`, which read as the model's.
- ty checks the example through a `[[tool.ty.overrides]]` that ignores `unresolved-import`
  instead of excluding it; `.gitattributes` keeps `examples/` out of the sdist.
- `Build.manifest` is the manifest the build computed, not the stored copy of an existing build
  of the same id, which may hold another run id, paths, branch, dirty flag and load time; the
  stored copy is still read, to report a damaged build directory. `Build.loader_ms` is gone.
- The loader's version-mismatch message names the checkout, the underlying error, that the pickle
  records no commit (see `data_out/RUNS.md`), and that the Blicks read plastics runs only.
