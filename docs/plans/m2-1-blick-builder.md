# M2.1 The Blick builder, on the dev server

Status: signed off 2026-10-27 with the decisions below as proposed; implemented the same day from
commit `444eb87`, reviewed in four rounds, and extended on 2026-10-28 with `bk.Frames`, the stock
dataset (Deviation 26). Planned
2026-10-27, revised the same day after an independent review that probed the model's arrays
(dimensions, intensive parameters, 0-d arrays, the historical system), flodym's slicing and
polars' `concat` and `is_in`. The first task of milestone M2 of
[architecture.md](../architecture.md) ("Blick builder (dev mode)", walkthrough 3, "Adapter and
loader protocol": the dataset protocol), pulled to the front of M2 on Tobias's decision of
2026-10-27. Builds on M0.8 (commit `444eb87`). The dev loop (code reload, the run poller, the
viewer's refresh) follows as M2.2, planned in [m2-2-dev-loop.md](m2-2-dev-loop.md); scatter and
table are M2.3. Where this plan fills in or changes a detail of the architecture, it says so; the
architecture gets the amendments when the task lands.

## Goal

Job 4, exploration, gets its tool: in `blicket dev`, a builder page composes an ad hoc Blick from
the run's data by GUI. You pick a quantity of the model (a flow, a stock, a parameter), a plot
type, the role of each dimension (an axis or a colour, panels, a filter, or summed over), and the
values to keep; the dev server runs the query over the project's dataset in Python and the browser
draws the result with the same chart, controls and data tab as a code Blick. The state lives in
the URL, so a link reproduces the chart within a session; nothing is saved. To get there, the
dataset protocol sketched in `m0-3-remind-mfa-adapter.md` is designed and implemented for
remind-mfa, and `blicket dev` comes into being as `check` without `--push` plus the server
holding the run in memory and answering the builder. The watcher and the reload are M2.2's.

## The split of M2, proposed here

- **M2.1** (this plan): the dataset protocol and remind-mfa's dataset; the query; the dev
  endpoints on the existing server; `blicket dev` without the watch; the builder page.
- **M2.2**: the dev loop: code reload, the run poller with a restart, the viewer's refresh and dev
  indicator, the fixture project, the editor link. Its plan is written and builds on this task.
- **M2.3**: the `scatter` and `table` plot types, both halves. The builder's query makes one
  measure; a scatter of two quantities is a pivot, a later builder feature.

## The flows this task enables

### 1. Build a Blick from the run

```
$ cd examples/remind-mfa
$ uv run blicket dev ../../data_out/2026-10-26--11-25-13_plastics_SSP2_h12
run 2026-10-26--11-25-13_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 444eb87 (dirty) · loaded in 672 ms
10 Blicks: 10 built
build 2224d63eb5ef42e1 → .blicket/build/2224d63eb5ef42e1

baseline 976f428f3d33dbdf · run 2026-10-26--11-25-00_plastics_SSP2_h12 · blicks at 81d752e (dirty) · built 2026-10-26 10:25 UTC
vs baseline: 10 unchanged
nothing flagged
comparison → .blicket/build/2224d63eb5ef42e1/compare/976f428f3d33dbdf
builder: 112 quantities, 6 dimensions
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
```

1. The overview is the one `serve` shows, plus a button "Build a Blick" next to the search, in dev
   mode only. It opens `#/builder`.
2. The builder page has the form on the left and the chart on the right (the form above the chart
   on a narrow page). **Quantity**: a searchable list of the dataset's quantities, grouped as the
   adapter groups them (`flows`, `stocks`, `parameters`, `historical`), each with its unit and
   dimensions, such as `polymerization => primary_market · t per year · Time, Element, Region,
   Polymer`. You pick it, and a chart appears at once: a line of the world total over time, since
   the pick fills the form with defaults (plot `line`, the time dimension on `x`, every other
   dimension summed for an additive quantity, filtered for an intensive one).
3. **Plot type**: `line`, `stacked_area`, `bar`, `stacked_bar`; you pick `stacked_area`.
   **Dimensions**: one row per dimension of the quantity with a role select: the plot type's
   dimension channels (`x`, `colour`; `line type` for lines), `panels`, `filter`, and `sum` for an
   additive quantity. Choosing a channel another dimension holds swaps the two. You put `Polymer`
   on `colour` and `Region` on `panels`; `Element` stays summed. **Values**: a dimension on a
   channel or on panels gets a values control under its row, a multi-select with "all" and "none"
   for strings and booleans, a range for years and dates; you unselect two regions. A filter
   dimension gets none here: the control bar picks its value. (As built, a filter dimension has
   the values control too, and the dimension on `x` only swaps: see Deviations 16 and 18.)
4. Each change sends the query to the server, debounced; the chart follows within a fraction of a
   second, the old one standing until the new rows are there: ten panels, Polymer stacked, Time on
   x, the y axis titled `t per year`. The control bar above the chart holds what a code Blick's
   would: `Region` as `all (panels)` with the split toggle, the y-axis switch, a dropdown for a
   filter dimension. The data tab shows the rows, the CSV link and the export menu work. A query
   that cannot run (a channel bound to a dimension the quantity lacks, a table of more than
   100,000 rows) is a problem shown where a Blick's problems are, with the last good chart kept
   dimmed until the next good query.
5. The URL carries everything, in the Blick page's convention of underscore keys:
   `#/builder?_q=flows/polymerization%20%3D%3E%20primary_market&_plot=stacked_area&_c.x=Time&_c.color=Polymer&_keep=Region&_split=Region&_only.Region=LAM&…`.
   Pasted into another tab of the same session it draws the same chart. The control keys
   (`<dim>=value`, `_split`, `_y`, `_tab`) are the Blick page's own, so the control bar behaves as
   there, and a control change is no new query: the split and the y axes are view state.
6. **Several quantities, one chart**: the quantity list allows more than one when they agree on
   their dimensions after the roles are applied; three flows picked give a dimension `Quantity`
   with the flows' titles as values, on `colour` by default, so "Production, net imports and
   consumption" as a line chart is a few clicks, and `Quantity` summed gives primary plus recycled
   production by polymer. The net imports themselves, a difference, are not: arithmetic stays
   outside the builder, as the M0.3 plan says. Quantities whose units differ are refused. (As
   built: a quantity that lacks a kept dimension is refused; the dimensions summed may differ, see
   Deviation 24.)

### 2. A project without a dataset, or without Blicks

`blicket dev` on a project whose loader module has no `dataset` serves the viewer as `serve`
does; the builder page says `This project has no dataset: add dataset(run) next to load_run in
blicketconf.py, which returns the quantities and dimensions of a run (see the README)`. A
`dataset(run)` that raises is a warning at start and the same page with the error; the session
goes on without the builder. A project with a loader but no Blick yet, job 4's natural start, gets
an empty overview and the builder: `dev` writes the build whatever it holds, where `build` refuses
with `NothingToBuild`.

## Facts the plan rests on (checked 2026-10-27, the model facts on run B of 2026-10-26)

- The run object is remind-mfa's `PlasticsModel`; blicket cannot add methods to it, so the
  dataset is a wrapper the adapter provides. `run.future_mfa` holds 54 flows named `<from> =>
  <to>`, 5 stocks (`use_dsm`, `use`, `atmospheric`, `landfill`, `uncontrolled`), each with
  `stock`, `inflow` and `outflow` arrays, and 33 parameters; `run.historical_mfa` has 10 flows,
  one stock and 31 parameters, 18 of them the same objects as the future system's, and its arrays
  are on `Historical Time` (75 years), not `Time` (151). Across both systems each dimension name
  has one letter and one item list (Region 12, Element 2, Polymer 13, Polymer Type 3, End Use 8);
  `Driver Scenario` occurs in no array, `Polymer Type` in parameters only. A flodym array has
  `dims` (each with `name`, `letter`, `dtype` and `items` in order) and no unit; `sum_to(letters)`
  aggregates and `to_df()` gives a long pandas frame with a named MultiIndex of plain strings (so
  the model's order of regions and polymers is lost unless passed as `order`) and one `value`
  column: 2 to 10 ms for a flow summed to three dimensions, 76 ms for the five-dimensional
  `use` stock whole (376,896 rows, 1.9 MB as Parquet). `sum_to(())` and `to_df()` of a 0-d array
  raise (`mechanical_recycling_yield`, `reclmech_loss_uncontrolled_rate`,
  `chemical_recycling_yield` are 0-d). A subset of a dimension's items is selected with a new
  `Dimension` object (`array[{"r": fd.Dimension(name=..., letter="R", items=[...])}]`), so the
  adapter can filter before it aggregates. `gdppc`, `population` and `end_use_split_limit` have
  `name == "unnamed"`; the dict keys name every array.
- Most parameters are intensive: the rates and shares are fractions, `gdppc` is in USD per person,
  `lifetime_mean` is in years, `polymer_type_mapping` is a 0/1 matrix. Summing them over regions
  is meaningless; the ten Blicks sum flows and stocks only. Units the Blicks know: `t per year`
  for flows, inflows and outflows, `t` for stocks, `fraction` for the rates and shares, `2005 USD
  PPP per person` for `gdppc`. `use_dsm.stock` equals `use.stock` summed to Time, Region and End
  Use.
- `tables.to_polars` and `tables.check(frame, blick)` turn a returned table into a checked polars
  frame and its `TableSchema`, given a `Blick`; `builder._checked(blick, run, root)` (as built
  `tables.compute`) runs the transformation and turns any exception into a problem with the
  project's traceback.
  `Blick` is a keyword-only dataclass with a required `transform`; built outside discovery with a
  plot spec from `plots.builtin(name)` and a mapping, without a source, nothing in `_validation`
  objects (it runs only through `bk.blick` and `bk.register`). `PlotSpec` itself raises
  `DefinitionError` for a missing required channel and for a column bound twice, and
  `plots.builtin` for an unknown name, so those cases have no `Blick` to make an entry from.
  `Blick.entry(...)` makes the `BlickEntry` the viewer consumes, controls derived through the
  plot type (every unbound dimension a filter at its first value, or the default). On polars
  2.0, `pl.col("Time").is_in(["2020"])` raises on an integer column, `pl.concat` raises when the
  column order or the integer widths differ unless `how="vertical_relaxed"`.
- The viewer's Blick page renders an entry: `ControlBar` from `entry.controls`, `useTable` from
  `{path, hash}`, `BlickChart` from the definition's plot and mapping, `DataTable`, `ProblemList`;
  `fetchTable` caches rows by hash for the page's lifetime without eviction and fetches
  `./<path>?<hash>`; `useTable` sets its rows to `null` whenever path or hash changes, and the
  page then shows "Loading the table…" and remounts the chart. The page's `update()` replaces the
  whole route query with the control state. The comparison is woven through its template (the
  switch slot, `waiting`, `incomparable`, the change charts, `ChangeStrip`), so a shared
  chart-area component is no clean cut.
- `PlotType.channels` declares each built-in's channels with `kind` (`dimension` or `measure`),
  `required` and `doc`; the built-ins are `LINE`, `STACKED_AREA`, `BAR`, `STACKED_BAR`.
- The loader convention: `load_run(selection)` in `blicketconf.py` next to `pyproject.toml`, or
  `loader = "pkg.mod:function"` in `[tool.blicket]`; `loader._resolve` imports the module and
  takes the attribute. `builder.build()` discovers, then loads the run inside and lets it go; the
  dev server must keep it. `cli.check_command` holds the check pipeline inline; nothing in it
  resists extraction.
- `serve.py` is a stdlib `ThreadingHTTPServer` with one handler: the installed viewer first, then
  the build directory; no directory listing; nothing outside the two directories, not through a
  symbolic link; a NUL in the path is 400; `Cache-Control: no-cache` on `/`, `/index.html`,
  `/manifest.json` and the JSON under `compare/`; its threads are daemons, so Ctrl-C ends it with
  connections open. `tests/test_serve.py` covers each rule over a real socket. The review of the
  M2.2 plan measured server-sent events under uvicorn and the stdlib and the browser's six
  connections per host; M2.2 polls, and both tasks stay on the stdlib server.
- Nitro's dev proxy forwards response headers (probed by the M2.2 review), so a header on
  `manifest.json` reaches the viewer under `pnpm dev` too. The viewer's query keys without an
  underscore are dimensions, with one the page's (`_split`, `_y`, `_tab`).

## Approach

### The dataset protocol (`src/blicket/dataset.py`)

What the builder asks of a run, as a `Protocol` for the documentation and the type checker, checked
at runtime by the presence of its three callables with a message that names the missing one:

```python
class Quantity(BaseModel):            # frozen
    name: str                          # unique in the dataset: "flows/polymerization => primary_market"
    title: str | None = None           # what the picker shows; the name without its group by default
    unit: str | None = None            # "t per year"; None when the model does not say
    dimensions: tuple[str, ...]        # names of the dataset's dimensions, in the model's order
    additive: bool = True              # whether summing over a dimension makes sense
    group: str | None = None           # the picker's grouping: "flows", "stocks", "parameters"

class Dataset(Protocol):
    def quantities(self) -> Sequence[Quantity]: ...
    def dimensions(self) -> Sequence[Dimension]: ...
    def select(self, quantity: str, keep: Sequence[str], values: Mapping[str, Sequence[Any]] = {}) -> Any: ...
```

`dimensions` returns the dataset's dimensions once, as `schema.Dimension`s (name, dtype, values
in display order), the shape the manifest has; a quantity names the ones it has. A value a
quantity lacks gives no rows, which is what IAMC data does too. `select` returns a table
`tables.to_polars` accepts: the `keep` dimensions as columns and one measure column, the rows
restricted to `values` for the dimensions named there, before the aggregation, and aggregated over
the dimensions not kept; with an empty `keep`, one row, the total. The adapter aggregates and
filters, because it knows how (flodym's `sum_to` is exact; a subset is a new `Dimension`); blicket
filters the kept dimensions once more, which costs nothing and keeps a careless adapter honest.
`additive=False` says that the builder must never ask to aggregate: such a quantity's dimensions
are kept, as filters by default. `hierarchy` and `styles` from the sketch are left out until a
project needs them (the IAMC adapter will); the protocol grows then. `Quantity` and `Dataset` are
exported as `bk.Quantity` and `bk.Dataset`. What `quantities()` returns is validated (names
unique, dimensions known).

The dataset comes from `dataset(run)` in the module the loader target names, `blicketconf` by
default, next to `load_run`: one rule, no config key. It is optional; a module without it has no
builder, and one that raises is a warning and a message on the builder page.

### remind-mfa's dataset (`examples/remind-mfa/blicketconf.py`)

`dataset(run)` returns an `MfaDataset` over `run.future_mfa` and `run.historical_mfa`. Quantities:
`flows/<key>` (`t per year`, additive), `stocks/<key>/stock` (`t`), `stocks/<key>/inflow` and
`/outflow` (`t per year`), `parameters/<key>` (not additive; the unit from a small table in the
adapter: `fraction` for the rates and shares, `2005 USD PPP per person` for `gdppc`, `years` for
the lifetimes, none otherwise; 0-d parameters left out), and the historical system's flows and
stock under `historical/…` (its parameters left out: half are the future's own objects). The
adapter names `Historical Time` as `Time`, since its values are the same calendar years, so a
historical flow and its future counterpart can share a chart. `dimensions` comes from the systems'
dimension objects (the dtype from the items); `select` slices the kept and filtered dimensions
with subset `Dimension`s, `sum_to` the kept letters (or `sum_values` for none) and `to_df()`. The
example's README gets a paragraph. The class lives in `blicketconf.py`, the adapter's file by the
loader convention; a project with more adapter code moves it into a package.

### The query (`src/blicket/query.py`)

The builder's request, which the URL encodes too:

```python
class Query(BaseModel):                # frozen
    quantities: tuple[str, ...]        # one or more
    plot: str                          # a plot type name
    mapping: dict[str, str]            # the plot's dimension channels -> dimension
    keep: tuple[str, ...]              # unbound dimensions kept as controls
    values: dict[str, tuple[Any, ...]] # per dimension, the values kept; absent means all
```

The request carries what shapes the data and nothing of the view: the split and the y axes live in
the URL as on a Blick page, and every kept unbound dimension is a filter control that the URL may
turn into a split. So a control change is no round trip. `run_query(dataset, query, root) ->
Result`:

- The kept dimensions are the mapped ones and `keep`; every other dimension of a quantity is
  aggregated by the adapter, which is refused with a problem for a quantity that is not additive.
  The measure channel is the one whose `kind` is `measure`, bound to `value`.
- The transient `Blick` (id `builder/query`, group `builder`, a title from the quantities' titles,
  the unit, the plot spec from `plots.builtin(plot)` and the mapping, `dims=` the kept dimensions,
  `measures=("value",)`, `order` for every kept dimension from `dimensions()`) has as its
  `transform` the query itself: for each quantity `dataset.select(name, keep, values)`, converted
  with `to_polars`, the measure renamed to `value`, the values typed by the dimension's dtype and
  filtered once more, the columns selected in a fixed order; several quantities concatenated
  (`vertical_relaxed`) with a `Quantity` column of their titles, in the order picked, which
  `order` fixes, and summed by blicket over `Quantity` when it is not kept; more than 100,000 rows
  is a problem that suggests summing a dimension or narrowing the values. The transformation runs
  through `builder._checked` (as built `tables.compute`), so an adapter's exception is a problem
  with its project traceback,
  and the table passes the checks a code Blick's does.
- Problems the construction itself finds (an unknown quantity or plot type, a channel bound to a
  dimension the quantity lacks, a missing required channel, quantities with different dimensions
  after the roles (as built: one that lacks a kept dimension; the dimensions summed may differ)
  or with different known units, duplicate titles, a model dimension called
  `Quantity` with several quantities picked) make an entry by hand, `definition=None`, with the
  problem; the page shows it through `status`.
- The result is the `BlickEntry` from `blick.entry(...)` (`data` as `dev/tables/<hex>.parquet`,
  `hash` as `parquet-sha256:<hex>`, `rows`, `columns`, `controls`, `problems`, `timing_ms`) and
  the Parquet bytes.

### `blicket dev` and the dev endpoints

`build()` is split into the steps the dev server needs and stays as their composition inside the
stdout redirect, as M2.2 wants them too: `prepare(root, paths, out) -> Prepared` (the config, the
viewer, the loader target, the run paths, the destination: what raises before anything is
written), `load(prepared) -> LoadedRun` (the run, its `RunInfo`, the loader time and the resolved
paths), `write(prepared, registry, loaded) -> Build` (from the repository state to the rename and
the viewer copy). `check.py` takes the comparison out of `cli.check_command`: `compare(build, root,
against) -> Compared(resolution, comparison, warnings)` lists the store, resolves the baseline,
compares and writes `compare/<baseline id>/`; the CLI keeps the push, the step summary, `--json`
and the exit codes.

`blicket dev RUN... [--against BUILD|REF] [--port] [--host] [--open] [--project] [--out] [-v]`:
`prepare`, `discover`, `load`, `write` (also with no buildable Blick, see flow 2), `compare`
(no push, no step summary), the dataset (`dataset` in the loader's module, if there), the report
as `check` prints it and the `viewer:` line, then serve until Ctrl-C with exit 0; a start that
fails exits 2 as `check` would; flags never set the exit code. The session holds the run, the
dataset, the current build and comparison, a lock that every query takes (M2.2's builds take it
too), and the last fifty query tables by hash.

The server stays `serve.py`'s handler, which gains a `current()` callable for the build directory
and a dev object or `None`:

- `GET /manifest.json` in dev answers from the current `Build.manifest` in memory, always 200, with
  the header `Blicket-Dev: 1`: the dev marker, which costs the viewer no request that a static
  host would 404.
- `GET /dev/info` → `{"root": "<absolute project root>", "dataset": true | false, "message":
  "<why not, when the dataset raised>"}`, `no-store`; M2.2 adds its fields.
- `GET /dev/dataset` → the quantities, the dimensions, and the plot types with their channels
  (`name`, `kind`, `required`, `doc`); 404 with the message of flow 2 without a dataset.
- `POST /dev/query` with a `Query` as JSON → the `BlickEntry` as JSON. The request must carry
  `Content-Type: application/json`, a `Host` that is the server's, and a `Sec-Fetch-Site` of
  `same-origin` or `none`, so a page of another site cannot query the model.
- `GET /dev/tables/<hex>.parquet` → the bytes from the session's cache, immutable by content, 404
  for an unknown hash.

### The builder page (viewer)

- `lib/builder.ts`: the types (`Quantity`, `DatasetInfo`, `Query`); the URL state and its encoding:
  `_q` (repeatable), `_plot`, `_c.<channel>` for the plot's dimension channels, `_keep`
  (repeatable; a dimension under `_split` is kept too), `_only.<dim>` (repeatable: the values kept
  of a string or boolean dimension), `_from.<dim>` and `_to.<dim>` (the range kept of an integer,
  date or datetime dimension), and the Blick page's own keys for the control state; the request
  body from the state (ranges expanded to values from the dataset's dimensions); the role of a
  dimension (`x`, `color`, `linetype`, `panels`, `filter`, `sum`) and the swap when a channel is
  taken; the defaults on picking a quantity; the compatibility of several quantities; the merge of a
  control change into the route query, which replaces the control keys and leaves the builder's,
  and clears a stale `<dim>=value` when a role changes.
- `composables/useDev.ts`: whether the viewer is in dev mode (the header, read in `useManifest`)
  and `dev/info`; `useDataset.ts`: the dataset listing, fetched once; `useQuery.ts`: posts the
  query debounced (300 ms), aborts a stale request, ignores out-of-order answers, fetches the
  table before it swaps `entry` and `rows` together, so the chart never unmounts between two good
  queries, and keeps the last good pair while a query runs or fails, with `stale` for the dimming.
  `fetchTable`'s cache gets a bound (the last 50 tables), since a session of ad hoc tables would
  otherwise grow without limit.
- `pages/builder.vue`: the form (a `USelectMenu` with search over the quantities, grouped, unit and
  dimensions as the item description, multiple; a radio group for the plot type; the dimension
  rows with their role select and values control), and the chart area composed directly from
  `ControlBar`, `UTabs`, `BlickChart`, `DataTable` and `ProblemList` with the entry and rows from
  `useQuery`, about thirty lines; the Blick page is left alone. Empty state: "Pick a quantity to
  start". The page title names the quantities.
- The overview's "Build a Blick" button, dev mode only. `nuxt.config.ts` proxies `/dev` to the
  blicket server. The generated site carries the builder page; opened from a served build
  directory it says it needs `blicket dev`.

### Dependencies, packaging, docs

No new runtime dependency. `dataset.py`, `query.py` and `check.py` join `meson.build`. README:
"Developing Blicks" with `blicket dev` and "The Blick builder" with the dataset protocol and
`dataset(run)`; the example's README: its dataset; `viewer/README.md`: the builder page and the
proxied path; `docs/architecture.md`: the dataset protocol as built (`additive`, `values`,
dataset-level dimensions, `hierarchy` and `styles` deferred), the builder section (one run per
session; the roles of a dimension; `Quantity` as a dimension; the view state outside the query),
the dev marker, the libraries line (the stdlib server stays; Starlette and uvicorn are not
needed); `m0-tasks.md`: the M2 split and this task's entry.

## Affected areas

- New: `src/blicket/dataset.py`, `query.py`, `check.py`; `viewer/app/pages/builder.vue`,
  `viewer/app/lib/builder.ts`, `viewer/app/composables/{useDev,useDataset,useQuery}.ts`;
  `tests/test_query.py` (the protocol, the query and the dataset lookup), `tests/test_dev.py`,
  `viewer/tests/builder.test.ts`. As built, also `src/blicket/dev.py`,
  `viewer/app/lib/{latest,dev}.ts`, `viewer/app/composables/useTab.ts`,
  `viewer/app/components/{BuilderValues,ChartTabs}.vue`, `viewer/tests/{latest,dev}.test.ts`
  (see Deviations).
- Changed: `src/blicket/builder.py` (`prepare`, `load`, `write`), `serve.py` (the dev routes, the
  in-memory manifest, `current()`), `cli.py` (`dev`, `check` through `check.py`), `__init__.py`
  (`Quantity`, `Dataset`), `meson.build`, `tests/test_serve.py` (the dev routes), `examples/
  remind-mfa/blicketconf.py` and its README, `viewer/app/pages/index.vue` (the button),
  `composables/useManifest.ts` (the header), `lib/table.ts` (the cache bound), `nuxt.config.ts`,
  `viewer/README.md`, the root README, `docs/architecture.md`, `docs/plans/m0-tasks.md`. As built,
  also `src/blicket/{errors,loader,schema,store,tables}.py` and `plots/__init__.py` (the moves of
  Deviation 5), `tests/{support,test_build,test_cli,test_schema,test_tables}.py`,
  `viewer/app/lib/{controls,csv,roles}.ts` and `pages/blick/[...id].vue` (the pieces shared with
  the builder, Deviation 21), `viewer/tests/table.test.ts`.
- Untouched: the plot types' Python halves, the comparison, the store's format, the baseline
  resolution, the Blick page's behaviour, the manifest (spec stays 0.2: nothing in a build
  directory changes).

## Testing

- **The protocol and the query** (`tests/test_query.py`, a toy dataset in the test module: two
  additive quantities and one intensive one as polars frames over `year`, `region`, `process`,
  one with a unit, and a `select` that records what it was asked): a query keeps the mapped and
  `keep` dimensions and asks the adapter to aggregate the rest, with `values` passed through and
  applied once more; a range and a list of values typed by dtype (years as integers from strings);
  an intensive quantity with a dimension to sum is a problem; two quantities give a `Quantity`
  dimension in the order picked, summed when not kept, their shared unit, and a problem when their
  kept dimensions or units differ, when titles repeat, or when the data has a `Quantity` dimension;
  `order` follows the dataset's dimensions; an unknown quantity or plot type, a channel bound to a
  dimension the quantity lacks, a missing `x`, a table over the row cap, and a `select` that raises
  each give an entry with a problem and no table, the last with the project's traceback; the
  entry's controls are filters for the kept unbound dimensions; the table hash names the Parquet
  bytes. The dataset lookup: in `blicketconf`, in a module named by `loader`, absent, raising, one
  that lacks a method, one whose quantities are invalid.
- **The server and `dev`** (`tests/test_serve.py`, `tests/test_dev.py`, over a real socket as
  today): `manifest.json` from memory with the header in dev and from the file without; `dev/info`
  and `dev/dataset` with and without a dataset; `dev/query` returns the entry and
  `dev/tables/<hex>.parquet` the table, an unknown hash 404, a missing content type or a foreign
  `Sec-Fetch-Site` refused; the CLI's `dev` prints the check report and the `viewer:` line and
  stops on Ctrl-C (the serve tests' pattern), loads the run once, serves a project without
  Blicks, warns on a dataset that raises, and exits 2 on a loader that does. `tests/test_check.py`
  and today's serve tests pass unchanged.
- **The viewer**: vitest on `lib/builder.ts` (the URL round trip, ranges included; the request
  body; the roles and the swap; the defaults on a pick; the compatibility of quantities; the merge
  of a control change). By hand on the example in headless Chrome, recorded here: flow 1 end to
  end, the pasted URL, a problem and the dimmed last chart, the three-quantity line chart, a
  historical flow with its future counterpart, a parameter with its filters, a project without a
  dataset, light and dark, 1280 and 390 px.

As built, the tests also cover, beyond the list above: the request bodies over a raw socket (an
unread body never read as a request, also with `Transfer-Encoding`, under `dev` and `serve`, and a
body shorter than announced), the routes' statuses (403, 405 with `Allow`, 411, 400, 413, 415, 500,
a malformed request line, a lone surrogate in a path), the `Host` check as a table, the build
taken once per request on a kept-alive connection, the session's table cache by recency
(`tests/test_serve.py`); the CLI's `dev` with a pushed baseline, `--against`, `-v`, the port bound
first and both no-Blicks cases (`tests/test_dev.py`); `tables.ordered`, `Raised` and `compute`
(`tests/test_tables.py`); the `polars_type` round trip (`tests/test_schema.py`); and in the
viewer the latest-request runner (`viewer/tests/latest.test.ts`), the requests to `blicket dev`
and the shapes of their answers (`viewer/tests/dev.test.ts`) and the table cache's bound
(`viewer/tests/table.test.ts`).

### Recorded by hand, 2026-10-27

This record predates the reviews; where it differs from the later records and the Deviations,
those win. Its quotes are brought up to date where the wording changed since.

On the working tree of this task (base `444eb87`), with the viewer generated by `pnpm generate`
and `BLICKET_VIEWER` pointing at `viewer/.output/public`, from `examples/remind-mfa`:
`uv run blicket dev ../../data_out/2026-10-26--11-25-13_plastics_SSP2_h12 --port 8790`. The
browser was Chrome (`google-chrome-stable --headless=new`) driven over the DevTools protocol by a
small script that clicks with real mouse events, reads the DOM, records console messages and
exceptions, and takes screenshots; the pages were looked at in the screenshots.

- **The start** printed the report of flow 1 as written above (`loaded in 960 ms`, `10 Blicks: 10
  built`, the baseline `976f428f3d33dbdf`, `vs baseline: 10 unchanged`, `nothing flagged`, the
  comparison line) and `viewer: http://127.0.0.1:8790/#/   (Ctrl-C stops)`. Ctrl-C (SIGINT) at
  the end, with the browser's connections gone, ended it with exit 0 within about 10 ms.
- **curl:** `GET /manifest.json` 200 with `Blicket-Dev: 1` and `Cache-Control: no-cache`; `GET
  /dev/info` 200, `no-store`, `{"root": ".../examples/remind-mfa", "dataset": true, "message": null,
  "failed": false}`; `GET /dev/dataset` 112 quantities (54 flows, 15 stock quantities, 30
  parameters, 13 historical), the six dimensions Time, Region, Element, Polymer, Polymer Type and
  End Use, and the four plot types with their channels; `POST /dev/query` (polymerization, stacked
  area, Polymer on colour, Region kept with three values) 200 with an `ok` entry of 5,889 rows, a
  Region filter control and the Region values in the model's order, in 18 ms; `GET
  /dev/tables/<hex>.parquet` 200, `application/vnd.apache.parquet`, `max-age=31536000, immutable`,
  bytes whose sha256 is the hex; an unknown hash 404; a query without `Sec-Fetch-Site`, with `Host:
  evil.example:8790` or with `Sec-Fetch-Site: cross-site` 403 with the reason, one without
  `Content-Type: application/json` 415; `collection_rate` with nothing kept an `error` entry without
  a definition: `collection_rate is not additive, so it cannot be summed over Region; keep it as a
  filter or on a channel`.
- **Flow 1, by clicks:** the overview shows "Build a Blick" next to the search; it opens
  `#/builder` with "Pick a quantity to start". The quantity list opens with 112 options grouped
  under `flows`, `stocks`, `parameters`, `historical`, each with unit and dimensions as its
  description. Picking `polymerization => primary_market` gave at once a line of the world total
  over time (`_q=…&_c.x=Time`, 151 rows, y axis `t per year`), the page title naming the
  quantity. Then "Stacked area", Polymer to colour, Region to panels, CHA and IND unselected:
  ten panels, Polymer stacked, 19,630 rows, the control bar with `Region all (panels)`, the split
  toggle and the y-axis switch; the data tab showed the first 2,000 of 19,630 rows with `_tab=data`
  in the URL. A role change to the new chart took 400 ms in the browser, the 300 ms debounce
  included (the query 27 ms, the table 1 ms).
- **The pasted URL:** the flow-1 URL loaded in a fresh page drew the same ten panels and 19,630
  rows.
- **A problem and the dimmed last chart:** with the URL changed to bind colour to `End Use`,
  which the flow lacks, the problem `End Use is on the colour channel, but polymerization =>
  primary_market has no dimension End Use` stood above the last chart, dimmed. `stocks/use/stock`
  with Polymer on colour and Region and End Use on panels gave `the table has 188,448 rows, more
  than the 100,000 the builder draws; …`, the last chart dimmed again.
- **Three quantities:** polymerization, `aux_recyclate_market => primary_market` and `use/inflow`
  picked one after the other: the second put `Quantity` on colour, and with two picked 36 of the
  list's quantities were disabled with the reason (`use/stock` with `in t, not t per year`); the
  line chart had three lines named by the titles, 453 rows. `Quantity` set to sum gave their
  total, 151 rows.
- **A historical flow and its future counterpart:** `polymerization => primary_market
  (historical)` and `polymerization => primary_market` on one line chart, 226 rows, the historical
  line ending in 2024; Element, Polymer and Polymer Type, which only one of the two has, showed as
  `sum` without a choice.
- **A parameter with its filters:** `collection_rate` started with Time on x and Region as a
  filter (`_keep=Region`), the control bar's Region dropdown at LAM; choosing SSA changed only
  `Region=SSA` in the URL and ran no query.
- **A project without a dataset:** `blicket dev` on a scratch project whose `blicketconf.py` has
  no `dataset` started as `check` does; `dev/info` said `dataset: false` with the message of flow
  2, `dev/dataset` answered 404 with it, and the builder page showed "This project has no
  dataset" with that message, without asking `dev/dataset`. The same build under `blicket serve`
  has no "Build a Blick" button, and `#/builder` there says that the builder needs `blicket dev`.
- **Light and dark, 1280 and 390 px:** flow 1 and the parameter in both modes and both widths: the
  form stacks above the chart at 390 px, no horizontal scroll (`scrollWidth` 390), the dark mode
  charts in the dark palette.
- **`pnpm dev`:** with `BLICKET_SERVE=http://127.0.0.1:8790`, `manifest.json` came through the
  proxy with its header, a query through `/dev/query` was answered (the proxy's `changeOrigin`
  rewrites the `Host` header), and the builder page drew its chart.
- **The console** showed no exception and no error from the app; the browser logged the 404 of
  `compare/index.json` on the scratch project, which was never checked, as it does for any such
  build.

Not checked by hand: other browsers; the PNG and SVG exports (the export menu is there, not
clicked) and the CSV download (the link is there, the file not opened); a query from a real
page of another origin (only curl sent a foreign `Sec-Fetch-Site` or `Host`); Ctrl-C with
browser connections still open (M2.2's verification has it; the server's threads are daemons, as
before).

### Recorded by hand after the first review, 2026-10-27

This record predates the second and third reviews; where it differs from the last record and the
Deviations, those win (the empty page now reads `flows (54), …`, the x hint `x always has a
dimension. …`, and `Updating…` shows on a line above the title).

The same setup, the viewer generated again, `uv run --frozen blicket dev` on the same run.

- **The start** printed the same report with the new line `builder: 112 quantities, 6
  dimensions` before `viewer:`. A port in use now fails before the run loads (the test
  `test_dev_binds_the_port_before_it_loads_the_run` shows it; not timed by hand).
- **The quantity list:** the empty page says what the builder does and counts the quantities by
  group (`54 flows, 15 stocks, 30 parameters, 13 historical`). Searching `polym` leaves 12 of
  112 (64 before, when the search read units and dimensions). The list closes on a pick; the
  picked quantity shows as a chip with ×; incompatible items read `can't join: in t, not t per
  year`.
- **The required channel:** with Time alone on x, Time's role select offers only `x`, with the
  hint `The x channel needs a dimension: give another one the role x to move Time.`; with
  Polymer on colour it offers `x` and `colour`, and choosing colour swaps the two. The role
  items carry short descriptions (`filter: pick the value above the chart`, `sum: add up over
  Polymer`).
- **The split toggle both ways:** Region set to panels by the form wrote `_keep=Region&
  _split=Region` and ran a query (3 queries so far). The control bar's "Split into panels" toggle
  turned it into `_keep=Region&Region=LAM`: the form shows `filter`, the Region dropdown is in the
  control bar, and no query ran (still 3). The toggle again gave `_split=Region` back, the form
  `panels`, still 3 queries.
- **The range:** with Time from 2050, the "to" list offers 2050 to 2100 only (51 values). The
  subtitle read `Summed over Element · Time 2050–2100`.
- **A five-dimension parameter's first pick:** `manufactured_products_imports` (intensive) gave
  Time on x and Region, Polymer Type, Polymer and End Use as filters, and the problem `the table
  has 280,800 rows, more than the 100,000 the builder draws (Time 75 × Region 12 × Polymer 13 ×
  Polymer Type 3 × End Use 8); …`. End Use narrowed to Packaging through its values control (`none`,
  then Packaging) gave a chart of 35,100 rows, the control bar's End Use dropdown at Packaging.
- **The stale chart:** after a good chart, a URL with End Use on colour showed `End Use is on the
  colour channel, but polymerization => primary_market has no dimension End Use`, the line
  `Showing the last chart that ran. Fix the problem above to update it.`, and the title,
  controls, tabs and chart dimmed and `inert`, the CSV button disabled.
- **A slow query:** under an emulated latency of 800 ms, the chart dimmed and `Updating…` showed
  next to the title within the second, both gone once the answer came; with no latency, a role
  change never dimmed the chart (sampled every 50 ms for 600 ms).
- **A project without Blicks:** `blicket dev` on a copy of the README's project with no `blicks/`
  printed `0 Blicks: 0 built · 1 warning` (the warning: no git repository), `no Blicks yet
  (blicks/**/*.py defines none); write one as code, or build one from the run in the viewer` and
  `builder: 1 quantity, 2 dimensions`; the overview said `0 Blicks` and `No Blicks yet. Build one
  from the run, or write it as code.` with the "Build a Blick" button, no error; the builder drew
  `flows/steel` (2 rows).
- **Two quantities at 390 px in dark mode and at 1280 px in light mode:** the chips wrap, the
  subtitle reads `Summed over Element, Polymer · Region: LAM, SSA (2 of 12)`, no horizontal scroll.
- **The console:** no exception and no error from the app. A first pass after moving the tab items
  into a composable logged `failed to load icon lucide:chart-line` and `lucide:table`, since the
  icon scan reads `.vue` files only; the tabs are a component now (`ChartTabs.vue`) and the
  warnings are gone.

### Recorded by hand after the second review, 2026-10-27

The viewer generated again, `uv run --frozen blicket dev … -v` on the same run, curl, a raw
socket and headless Chrome as before.

- **An unread body:** on one connection, a `POST /dev/info` with `Content-Type: text/plain` whose
  body is a complete `POST /dev/query` with `Sec-Fetch-Site: same-origin`, followed by a `GET
  /dev/info`, got one answer, `405 Method Not Allowed` with `Connection: close`, and the server
  closed the connection: neither the smuggled query nor the `GET` was answered. `GET /dev/query`
  is 405, a `Content-Length: 1_0` 400 (`Content-Length '1_0' is no length`).
- **`dev -v`:** the query `collection_rate` with nothing kept logged `query {…}` and `error:
  collection_rate is not additive, so it cannot be summed over Region; …` on stderr.
- **The lost connection:** with the chart of the flow drawn, the server stopped, and Region set
  to colour, the page showed `Cannot reach blicket dev` / `It may have stopped; check the
  terminal.` with Retry, `Showing the last chart that ran.`, and the last chart dimmed and
  `inert`. The server started again on the same port and Retry pressed, the alert went and the
  chart with a line per region came.
- **A large first pick at 390 px:** `manufactured_products_imports` showed the row-cap problem
  under the quantity, at y 348 of the window's 844, besides the problem above the (empty) chart
  area further down.
- **The no-dataset page:** on the scratch project without `dataset`, the title "This project has
  no dataset" and `No dataset(run) next to load_run in blicketconf.py; add one that returns the
  quantities and dimensions of a run (see "The Blick builder" in the README).`; the terminal said
  `builder: off, no dataset(run) next to load_run in blicketconf.py; …`.
- **The failed-dataset page:** on a copy whose `dataset(run)` raises `KeyError('flows')`, the
  terminal said `warning: dataset(run) in blicketconf raised KeyError: 'flows' (raised at
  blicketconf.py:11)` and `builder: off, dataset(run) failed; fix it and restart blicket dev`;
  the page showed "The dataset of this project failed" and `dataset(run) in blicketconf raised
  KeyError: 'flows' (raised at blicketconf.py:11). Fix it and restart blicket dev.`
- **Stopping:** these sessions ran in the background of a non-interactive shell, which ignores
  SIGINT, so they were stopped with SIGTERM; Ctrl-C itself was walked in the first records (exit
  0, about 10 ms).

### Recorded by hand after the third review, 2026-10-27

The same setup.

- **The plot type:** with `Bar` chosen, the quantity removed with its × and another picked, the
  URL kept `_plot=bar`.
- **The range:** the Time row of a historical flow reads `Values 1950 to 2100 all`, at 390 px
  without horizontal scroll.
- **No shift:** under an emulated latency of 800 ms, the title stayed at y 189 (sampled every
  50 ms for 1.5 s) while `Updating…` showed.
- **Retry while the server is down:** the click disabled the button while the request ran, and
  the failed retry added `Still no answer at 14:46:34.` to the alert; with the server started
  again, Retry brought the chart back and the alert went.
- **Idle connections:** the page left open for 35 s, the server's log had no `timed out` line.
- **Not checked by hand:** the page's own alert for a failed `dev/info` or `dev/dataset` (it
  needs the server to go while the page loads), and a 500 on `dev/query` in the browser (the
  server's test covers the 500 itself).

### Verified in the fourth review, 2026-10-27

The fourth review's UX reviewer ran the page against the server and verified what the records
above do not: a 500 from `dev/info`, `dev/dataset` and `dev/query` each shows its alert with
Retry and recovers once the server answers again; a 502 with an HTML body reads `dev/info: 502
Bad Gateway`; Retry was disabled while its request ran (since changed: it stays focusable with
`aria-busy`, see Deviation 19); `Still no answer` showed after a second failure; and the page's
own alert showed once when the server stopped before `dev/dataset` was loaded. After the fourth
round's changes, checked here by hand: with the server stopped, Retry kept the keyboard focus,
showed `aria-busy` while the request ran, and a second Enter on it added `Still no answer at
15:13:45.` on its own line.

## Deviations

Where the implementation departs from the plan, or fills in what the plan left open. Items marked
*review* came from the four review rounds of 2026-10-27; where they reverse a sentence of the
plan, they say so.

1. **`bk.Dimension` is exported** next to `bk.Quantity` and `bk.Dataset`: an adapter builds the
   `schema.Dimension`s that `dimensions()` returns and needs the class.
2. **`select`'s `values` has no default in the protocol.** blicket always passes it, and a
   mutable default in a protocol is a lint error; an adapter may still declare one.
3. **The session is `src/blicket/dev.py`** (*review*): `Session` and `start(root, runs, …) ->
   (Session, report)`; `cli.dev_command` is as thin as `serve_command`, and the tests start a
   session with `start()`. The plan put the dev object beside `serve.py`'s handler and M2.2 made
   `dev.py` new; the M2.2 plan's references to it are corrected. The session keeps the project as
   prepared, the baseline asked for, the run, its dataset and the build served with its
   comparison as one immutable `Current`, which `current()` returns, so that M2.2 can swap it
   whole. `serve.py` depends on a narrow `DevSession` protocol (`current`, `info`, `options`,
   `query`, `table`) and takes the session's current build once per request, not per
   connection, so a kept-alive connection never reads an old build. It answers through a route
   table keyed by method and path, plus the one route of the tables. `make_server` takes a
   directory or none, the session being attached once the port is bound, and `run` refuses a
   server with neither.
4. **`build()`'s steps:** `prepare` checks the run paths before discovery, as the plan's
   `prepare` says, so `build` with a missing run path now fails with that error before it could
   fail with `NothingToBuild`. `LoadedRun` holds the run, its `RunInfo` and the loader time; the
   run paths are `Prepared`'s, and the unresolved ones M2.2's (*review*). Two existing tests
   patched `builder.load`, which is now the step that takes a `Prepared`; they patch
   `loader.load` instead. `test_cli.py`'s list of commands gained `dev`.
5. **Moves** (*review*): running a transformation and checking its table is `tables.compute`
   (planned as `builder._checked`), the store of a project `Store.of_project`, the parse of a
   loader target `loader.split_target`, the field of a validation issue `errors.issue_field`,
   `DatasetError` is in `errors.py`, the polars type of a dimension type `schema.polars_type`,
   and the plot types the builder offers are the built-ins with one measure channel
   (`plots.builtins()`), not a list kept by hand. What `dev/dataset` returns is the pydantic model
   `query.Options` (`BuilderOptions` in the viewer). `dataset.find` is the one lookup of a
   dataset and returns the contents or why there are none. `typed` is `coerce`.
6. **`run_query` takes the checked `Contents`**, not the bare dataset, and `Query` refuses
   unknown fields (`extra="forbid"`). `Kind.QUERY` is the kind of the problems a query has of its
   own (refusals, the row cap).
7. **The query's refusals:** two more cases (a dimension in `keep` or `values` that the dataset
   lacks, a kept dimension called `value`), and the builder's words for a missing required
   channel (`the x channel needs a dimension; give one the role x`), for a channel (`process is
   on the colour channel, but …`) and for a kept dimension (`… is a filter or on panels, but …`)
   (*review*). The row-cap problem names the dimensions and their sizes and, for a quantity that
   is not additive, suggests narrowing a Values list rather than a sum (*review*). An exception
   raised by `select` reads `select('flows/x') of the dataset raised …`, and a column `select`
   returns that cannot be read as its dimension's type reads `select('flows/x') returned a 'year'
   column that cannot be read as integers: …`, not `transformation raised …` (*review*). Under
   `dev -v` each query's problems go to stderr with their tracebacks.
8. **Display order** (*review*): the table is checked once, and `tables.ordered` puts the values
   of each dimension in the dataset's order afterwards; the transient Blick has no `order`, so
   values a query leaves out are never reported missing. The columns are `Quantity` first, then
   the kept dimensions in the dataset's order; the title joins the quantities' titles with commas.
9. **`dev/info`** is the pydantic model `serve.Info` (*review*): `root`, `dataset`, `message`,
   which also says why there is no dataset when `dataset` is absent, and `failed` when
   `dataset(run)` failed (the plan listed `root`, `dataset` and `message`). The page asks
   `dev/dataset` only when `dev/info` says there is a dataset. `dev/dataset` and a query answer
   404 with the message without a dataset, the session raising `DatasetError`, and `dev/dataset`
   is sent with `no-cache`, as found and not. A query's entry names project files relative to
   the root, as the manifest does (*review*).
10. **The routes' answers** (*review*): a request not from the viewer's own page is 403, a body
    not sent as JSON 415, a missing `Content-Length` 411, a malformed one (ASCII digits only) or
    a body that is no query 400, a body over 1 MB 413, a known path with another method 405 with
    `Allow`, any other path 404, a `POST` under `blicket serve` too (it was 501, the stdlib's
    answer), and a route that fails 500 with the traceback on stderr. A request that is not a
    `GET` or `HEAD`, or that carries a body (a `Content-Length` other than 0, or a
    `Transfer-Encoding`), closes the connection unless a route reads its body in full, and every
    answer on a connection that closes, a static file's too, says `Connection: close` once:
    before, an unread body was read as the next request, which let a page of another site smuggle
    a query. A body framed ambiguously, with a `Transfer-Encoding` or two `Content-Length`s, is
    400 and closes the connection; a `Content-Length` of more digits than 1 MB has is 413 before
    it is converted. A client that stays silent for 30 s while it sends a body loses the
    connection, a deadline on that read alone, so an idle kept-alive connection logs nothing; the
    deadline is per read, so a client that trickles a byte at a time can hold a thread longer.
    Nothing of a request carries over to the next on a connection, also when its line cannot be
    parsed. A request line that cannot be parsed and a path no
    file can have (an escaped lone surrogate) are answered (400, 414, 505; 404) instead of
    ending in a traceback; both came from the stdlib handler before this task.
11. **The `Host` check** accepts the server's port with an IP address, `localhost` or the address
    it listens on, and the machine's name when it listens on every address; a domain name that
    only resolves to the server, as DNS rebinding makes one, is refused.
12. **A baseline that `--against` cannot resolve does not stop `dev`:** the report says `error: no
    baseline: …` as `check`'s does, and the session serves the build without a comparison. Only a
    start that raises exits 2: the config, the viewer, a run path, the loader, the port, a build
    that cannot be written, and git that cannot run when the baseline is resolved.
13. **The terminal** (*review*): the report ends with `builder: <n> quantities, <n> dimensions` or
    `builder: off, <why>` before `viewer:`; a `dataset(run)` that raises is a `warning:` line and
    `builder: off, dataset(run) failed; fix it and restart blicket dev`. `dev` binds the port
    before it loads the run.
14. **No Blick yet is no error in `dev`** (*review*, beyond the plan's "dev writes the build
    whatever it holds"): the errors that say a project has no Blick (`no_match`, and the
    project-level `no_blicks`) are left out of the dev build, which is therefore complete; the
    report says `no Blicks yet (<globs> defines none); write one as code, or build one from the
    run in the viewer`, and the overview `No Blicks yet. Build one from the run, or write it as
    code.`; a build without Blicks served by `blicket serve` says `This build has no Blicks.`
    `build` and `check` are unchanged.
15. **Flow 2's words as built:** the terminal says `builder: off, no dataset(run) next to load_run
    in blicketconf.py; add one that returns the quantities and dimensions of a run (see "The Blick
    builder" in the README)`, and the page, under the title "This project has no dataset", the
    same sentence. A `dataset(run)` that raises gives the page "The dataset of this project
    failed" with the error and "Fix it and restart `blicket dev`."
16. **The values control on filter dimensions** (*review*), reversing the plan's "A filter
    dimension gets none here: the control bar picks its value": every kept dimension has it, so
    an intensive quantity with many dimensions can be narrowed below the row cap; the control
    bar's filter then offers the values kept. A summed dimension has none, and making a
    dimension a sum drops its values.
17. **A dimension on panels is kept as a filter is** (*review*): it is in `_keep` and in `_split`,
    so the control bar's split toggle turns it into a filter without a new query (before, it left
    the dimension in neither and the next query summed it). Values of a dimension that is no
    longer kept, or that no quantity picked has, leave the URL with it. `_only` values the
    dimension lacks are left out with a notice, and a list of nothing but such values keeps all
    values, as no list does (before, it kept none). A dimension of no quantity picked that a
    hand-made URL binds to a channel is cleared at the form's next change.
18. **A required channel stays filled** (*review*): the role select of the dimension on `x`
    offers `x` and the channels other dimensions hold, so a choice swaps, with the hint `x always
    has a dimension. To move Time, give another dimension the role x.` `Quantity` goes on colour,
    or on line type or panels when colour is taken; a dimension on a channel the new plot type
    lacks becomes a filter. Ranges never end before they start.
19. **The query in the viewer:** the first query goes at once, later ones after 300 ms;
    `lib/latest.ts` runs only the latest, and `lib/dev.ts` makes the requests, checks the shape
    of each answer and calls a server that does not answer unreachable, with a message, also when
    the connection is lost while the table is fetched (*review*: both plain modules, so vitest
    covers them). The chart dims only after a query has run for 400 ms, `Updating…` showing on a
    line above it whose height stays while a chart is shown, so nothing moves, and after a failed
    or refused one, when the title, controls, tabs and chart are dimmed and `inert`, the CSV
    button disabled, and that line says the chart is the last that ran; the status line and the
    problems are announced once (`aria-live`) (*review*). A failed query offers Retry, a lost
    connection and a server error alike, through one component (`DevAlert.vue`): the button
    stays focusable while the request runs, shows a spinner and `aria-busy` for at least 300 ms,
    ignores clicks meanwhile, and a retry that fails again says `Still no answer at 13:25:02.` for
    a lost connection and `Failed again at 13:25:02.` for an error answer, on its own line
    (*review*). A refusal shown before is cleared when a later request fails, and a connection
    lost while the table is fetched is told from a table that cannot be read (in `lib/table.ts`,
    around the fetch and the read of the body only). The page shows
    notices for values the URL names that are not there, the warnings of a good entry, and, for
    an empty table, one line (*review*). A subtitle says what the chart was summed over and which
    values it keeps (*review*).
20. **The page's form** (*review*): the picked quantities are chips with ×, with the hint to
    remove one to chart another; the list closes on a pick, is up to 60 % of the window high,
    searches titles, groups and names, not units, and says `No quantity matches`; an item that
    cannot join says `can't join: <why>`, and a missing unit reads `unit unknown`; a dimension
    not in every quantity reads `sum (not in every quantity)`; each values control, the range
    too, has a `Values` label, a range shows `all` when whole and `n of m` otherwise, a list
    `10 of 12` for a larger partial selection; the plot types have a larger touch target.
    Breadcrumb, heading and title say "Build a Blick". The page's own requests (`dev/info`,
    `dev/dataset`, both through one `devResource` helper) tell a lost server, `Cannot reach
    blicket dev. It may have stopped; check the terminal.`, from a failed answer, `The dataset
    could not be loaded` or `The dev session could not be read` with the server's message, both
    with Retry and announced as an alert (`role="alert"`). On a narrow page the first
    problem of a refused query also shows under the quantity (hidden from screen readers, which
    hear it in the chart's area), since the chart comes after the form. The empty page counts
    the quantities per group.
21. **Shared viewer pieces** (*review*): `downloadCsv` in `lib/csv.ts`, the tabs as
    `components/ChartTabs.vue` with `useTab()`, the channel labels as `CHANNEL_LABELS` in
    `lib/roles.ts`, the page's query keys (`_split`, `_y`, `_tab`) and `strings()` exported from
    `lib/controls.ts`; one `owner(key)` decides who a query key belongs to. The Blick page uses
    them; its behaviour is unchanged. The request type is `BuilderRequest` (the plan's `Query`,
    which `lib/controls.ts` names the route query); `pick` says whether the controls start afresh,
    and `joinable` works out once per state what a quantity must share to join.
22. **The browser's table cache** keeps the last 50 of the builder's tables (`dev/tables/`) and
    every table of a build (*review*: a bound on all tables would refetch a large build's).
23. **The example's adapter** gives a subset `Dimension` a letter the array does not use, since
    flodym refuses a replacement dimension with a letter already in the array, and returns a
    polars frame for the total and for a selection that matches no item. Its `dimensions()` come
    from the arrays it added, in the model's order, typed by their items (*review*). Its README
    no longer counts the quantities in prose, which depend on the remind-mfa version.
24. **Quantities summed over different dimensions share a chart:** the plan's "quantities with
    different dimensions after the roles" is, as built, a quantity that lacks a dimension kept;
    two flows of which one has `Element` and the other not chart together, each summed over its
    own others (*review*: a test pins it, and the plan's lines say so).

25. **The plot type stays when the form starts afresh** (*review*): removing the one quantity
    and picking another, or picking the first quantity of a link that names a plot type, keeps
    the plot type chosen; the defaults are a line chart only for a new form, and a pick falls
    back to a line chart when the link names a plot type the builder does not offer.

26. **`bk.Frames`, the stock dataset** (Tobias, 2026-10-28, after the loop): a dataset by hand
    asks for three methods, of which `select` is the hurdle (25 lines of flodym subsets and spare
    letters in remind-mfa). `Frames` in `dataset.py` takes tables, one per quantity, as frames or
    as functions that return them, called when first needed; reads the dimensions not declared
    ahead from the tables (the dtype from the column, values sorted, strings in order of
    appearance); and filters and sums with polars, which a subclass overrides. remind-mfa's
    dataset is a `Frames` over the arrays' `to_df()` with the model's dimensions declared, so
    they keep its order, and the flodym `select` is gone. Measured on run B: converting all 112
    arrays takes 1.0 s for 6.7 M rows, the largest 63 ms for 377,000 rows, a query on a converted
    frame 4 ms against flodym's 1 ms; a quantity's first pick costs about 120 ms once, and the
    last eight frames read stay converted. The protocol is unchanged; a dataset by hand still
    works, and the README leads with `Frames`.

Not done from the reviews, and why:

- A collapsible form or a sticky chart heading on narrow screens: the form above the chart reads
  well at 390 px, and the first problem of a refused query shows under the quantity instead.

## Out of scope

The run picker and runs as a dimension (the adapter has no `discover(root)` and no labels, and
the example's loader takes one path; one run per session here, the one `dev` loaded); the
hierarchy and summation groups and the styles of the protocol sketch; arithmetic between
quantities and shares; a scatter of two quantities (a pivot); a values selection on summed
dimensions in the form (the protocol allows it, the first form does not offer it); export as code;
saving ad hoc Blicks or a scratch group on the overview; the dev loop (M2.2); scatter and table
(M2.3); end-to-end browser tests.

## Decisions

Put to Tobias on 2026-10-27 and accepted as proposed:

1. **The order of M2**: the builder first, on `blicket dev` without the watch; the loop second;
   scatter and table third.
2. **One run per session**: the run picker waits for the adapter's `discover` and a loader that
   combines runs; the builder works on the run `dev` loaded.
3. **Several quantities in one chart** through a `Quantity` dimension, with the rules above
   (shared unit, unique titles, summable when not kept): in, as flow 1 describes it.
4. **The protocol**: `additive` on the quantity, `select(quantity, keep, values)` with the adapter
   aggregating and filtering, one `dimensions()` for the dataset, no `hierarchy`, no `styles` yet.
5. **`dataset(run)` found in the loader's module**, no config key.
6. **The stdlib server stays**, for this task and M2.2, which polls instead of streaming events;
   Starlette and uvicorn are not added. The architecture's libraries line is amended.
