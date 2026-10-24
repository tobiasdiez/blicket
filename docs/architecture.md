# blicket: architecture and milestones

Status: decided on 2026-10-23, before any code. Companion to [concept.md](concept.md), which defines the
unit (Blick), the jobs and the plot type contract. The research notes in `research/` were input;
where this document deviates from them, this document wins. One part is deliberately left open:
how changes are accepted and managed (see below).

## Principles

1. **Lean.** A component earns its place only by serving job 1 (development companion) or job 2
   (automated guard). Deferred items in the concept stay deferred.
2. **Data, never pixels.** Baselines are tables. Rendering changes are invisible to the guard by design.
3. **One runtime for users.** Scientists install one Python package. Node is a maintainer-only build tool.
4. **Files are the API.** Build directories and the store are documented directory layouts. The spec is
   extracted from the reference implementation and versioned from the first release.
5. **Builds are immutable.** A build is never modified after it is written. Whatever the accept design
   becomes, it attaches decisions to builds; it does not rewrite them.
6. **A human decides.** A human inspects and accepts; CI only reports.
7. **Measure before choosing.** Tolerance and cache defaults come from real remind-mfa outputs in
   milestone 0, not from synthetic data.

## Components

| Component | What it is | Language |
|---|---|---|
| `blicket` package | CLI, Blick registry and discovery, build pipeline, canonical tables, change detection, store access and baseline resolution, dev server, vendored viewer, built-in plot types | Python + JS |
| Viewer | Nuxt app in client-only mode (`ssr: false`, hash router, relative base URL), generated to static files and shipped inside the wheel. Reads only a build directory through relative paths. | TypeScript / Vue |
| Store | A directory tree holding builds. Default `.blicket/store` in the project (gitignored); shared projects point it at a path on the cluster filesystem. Remote backends later. | files |
| Project | Blick modules, the adapter (run loader with run discovery and labels, dimension metadata, styles), plot types, config in `pyproject.toml` | Python (user) |

What is in git: Blick code, plot types, config. Nothing else. The blicket repository itself is a
monorepo: the Python package at the root, `viewer/` (Nuxt app), `examples/`, `docs/`.

## Data flow

```
run directory
  → project loader(paths) → run object + RunInfo (run id, profile, input fingerprint, model commit and branch, dirty flag)
  → Blick transformations → per-Blick tidy tables → checked tables (roles, typed sort)
  → baseline resolution from the store
  → change flags + magnitude per Blick, via the plot type's diff
  → build dir: manifest.json + current tables + comparison output per baseline + viewer
  → terminal summary; viewer; report
push → copies the build into the store (immutable, keyed by build id)
```

## Store and baseline resolution

```
<store>/
  builds/<build-id>/
    manifest.json             spec version, RunInfo, commit, branch, dirty flag, timestamp, tolerance, per-Blick definitions, schemas and hashes
    compare/<baseline-id>/    flags, magnitude and the baseline tables of changed Blicks, per baseline (amendment of 2026-10-23); if `push` copies it (M0.7)
    blicks/<id>.parquet       canonical tables, zstd
```

- **A build is immutable.** Its id is a hash of the Blick definitions, the per-Blick table hashes,
  the run fingerprint and the commit; the timestamp is not part of it, so an identical rerun
  yields the same id. Pushing the same build twice is a no-op.
  Every pushed build is kept, since storage is no constraint. This also gives run-against-run
  comparison for free: `blicket diff <build-a> <build-b>`. Amendment of 2026-10-24 (M0.6): `diff`
  prints the comparison, as a summary or as the comparison file (`--json`), writes nothing, and
  exits 0 when it finds changes; `check` is the guard. `check` (M0.7) writes the comparison into
  the build directory's `compare/<baseline-id>/` and decides whether `push` copies it; `push`
  copies the manifest and the tables.
- **Baseline resolution** matches builds by run profile and follows git ancestry. The commit that
  anchors ancestry is HEAD of the repository holding the Blick code, read at build time; the
  model commit in the run info is informational. Among candidate builds whose commit is HEAD or
  an ancestor (`git merge-base --is-ancestor`) and whose profile matches, the most recent wins. Per Blick, the baseline is that build's table, with fallback to
  older candidates if the Blick is missing there; no candidate means `new`. A feature branch
  starts from main's build; after a merge, main sees the branch's build as an ancestor. This is
  Chromatic's carry-over with one git command.
- **Which builds are candidates is the deferred decision.** Until the accept design exists, a build
  is compared against an explicit baseline (`--against <build-id>`) or against the most recent
  build of a branch by ancestry (`--against main`). Once acceptance exists, candidates are the
  accepted builds, and the resolution rule stays as it is.
- The store is a plain directory. Everything reads and writes through one small `Store` class, so
  an fsspec backend (SFTP, S3) can be added when the review flow needs it.

## Data model at the Blick output

A labelled long table: dimension columns (string, int, date) and one or more measure columns
(float). Dimensions are inferred as the non-float columns; `dims=` / `measures=` override. Parquet
keeps the types. The charted measure has one unit per Blick (`unit=`, amendment of 2026-10-24); a
table mixing units keeps them in a dimension column. The combination of dimension values
must be unique per row; duplicates are an `error`. Raw run data stays opaque behind the project
loader.

Transformations may return anything Arrow-compatible (polars, pandas, pyarrow, xarray via
`to_dataframe`, flodym arrays via `to_df`); the core converts to polars internally. A Blick may
pass `order={"scenario": [...]}` or use a Categorical dtype to fix the display order of dimension
values; the manifest records it.

## Blick definition

```python
import blicket as bk

bk.group("flows", title="Material flows", tags=["mfa"])

@bk.blick(
    id="flows/steel-by-process",             # default: "<group>/<function name>", independent of the file path
    title="Steel flows by process",
    plot=bk.plots.stacked_area(x="year", y="value", color="process"),
    controls={"region": "split"},            # optional; otherwise the plot type's controls() decides
    defaults={"scenario": "baseline"},
    tolerance=1e-4,                          # overrides the project default
    aliases=["flows/steel_process"],         # former ids, so a rename keeps its baseline
)
def steel_by_process(run):
    ...
```

`bk.register(...)` exists for families generated in loops. blicket requires only that the run
object is reusable across Blicks in one process; what it is comes from the adapter.

## Adapter and loader protocol

The adapter is project code, the counterpart of Storybook's `main.ts`. Nothing domain-specific
ships with blicket for now; a standard IAMC adapter is a later option.

- **Loader.** `load_run` in `blicketconf.py` next to `pyproject.toml` (found by convention, like
  pytest's `conftest.py`; amendment of 2026-10-24), or the function named by
  `loader = "mymodel.blicket:load_run"`, receives a run selection (paths, labels) and
  returns the run object and a `RunInfo` (run id, profile name such as "baseline" or "policy",
  fingerprint of the input files, model commit and branch if known). The loader defines what a
  run is: it may collect several model runs, for example several REMIND scenario folders, into
  one blicket run, with the model run as a dimension. The profile lets several run
  configurations per branch each have their own baseline.
- **Run discovery and labels.** The adapter may implement `discover(root) -> list[RunInfo]` and
  default labels, which the dev-mode run picker uses. Defaults come from the project config; a
  selection changed in the dev session is not written back.
- **Dataset protocol, optional.** Code Blicks only need the run object. The Blick builder needs
  a run object that also implements a small protocol: the quantities (flows, stocks, parameters,
  variables) with their units, per quantity the dimensions and their values, an
  optional hierarchy per dimension (a tree plus summation groups, for IAMC variable names
  with the plus-sign convention), display order, a style registry per dimension value, and
  `select(...)` returning a labelled long table for a set of dimension values. The core's
  generic query transformation is written against this protocol and nothing else.

The default id does not depend on the module path, because moving a file would otherwise turn
every Blick in it into `removed` plus `new` and skip the comparison. A module without a group
call uses its basename as the group. Orphans are reported only
after complete discovery. Rename detection by content hash is not planned.

## Plot type contract

Every plot type, built in or project defined, implements the whole contract. There is no generic
fallback in the core; the built-ins are ordinary plot types that ship with the package, which
exercises the plugin path from day one.

```python
class StackedArea(bk.PlotType):
    module = "stacked_area.js"                                   # browser half

    def controls(self, schema, mapping) -> list[bk.Control]:     # build time
        ...                                                      # unbound dimensions → filter or split

    def diff(self, baseline, current, mapping, panels) -> bk.Change:     # build time, headless
        ...                                                      # flags + magnitude + diagnostics
```

```ts
// stacked_area.js — browser half, loaded by dynamic import; framework-agnostic, never sees Vue
export default {
  render({ el, table, schema, mapping, unit, state, theme, name }) { ...; return cleanup },
  renderComparison({ el, current, baseline, mapping, state, change }) { ... },
}
```

- **Channels are declared as data.** `controls(schema, mapping)` derives controls once a mapping
  exists; the builder needs the list of channels before any mapping exists, to offer dropdowns.
  So a plot type also declares `channels`: for each channel its name, whether it takes a
  dimension or a measure, whether it is required, and constraints such as "line type only for
  line plots" or "x defaults to time". The builder reads this list; nothing else about the
  contract changes.
- The build-side half runs in Python at build time, because the terminal summary, the report and
  CI need flags and magnitude without a browser. The browser half renders the chart and the
  comparison.
- The core provides the data plumbing (canonical tables, baseline resolution, manifest, URL control
  state, filtering by control state before `render`) and nothing chart-specific. Internal routines
  used by the built-ins (an outer-join change table, a bounded magnitude, a Vega-Lite template
  renderer with a ghost overlay) may be promoted to public helpers later, once two project plot
  types have wanted the same thing.
- Built-ins: line, stacked area, bar (grouped, stacked) in M0/M1; scatter and table in M2. Their
  `render` uses Vega-Lite templates; their `diff` uses a shared internal routine. Their `controls`
  turn each unbound dimension into a filter by default and allow `split` where the chart supports
  facets. Hiding dimensions that are functionally determined by other unbound dimensions (unit by
  variable) waits for a project that needs it (amendment of 2026-10-24).
- Amendment of 2026-10-24 (M0.5): `diff` takes `panels` instead of `controls`, the dimensions
  whose value combinations each get their own scale. The core derives them, since it lays out the
  panels (the filters, and the splits when the Blick sets `independent_y`); the plot type scales
  and compares within them.

## Change detection, as implemented by the built-in diff routine

Per Blick, the comparison gives a **set of flags** and a magnitude. A set, not one type, because a
Blick can gain a scenario and change values in the same run, and one type per Blick would hide the
second. Amendment of 2026-10-24: the plot type's `diff` sets `schema` and computes the magnitude;
the core sets `value` when the magnitude exceeds the Blick's tolerance, so the two cannot
disagree, and `new`, `removed` and `error`.

| Flag | Meaning | Shown as |
|---|---|---|
| `new` | no baseline exists | needs a look |
| `removed` | baseline Blick without a current Blick, after complete discovery | reported |
| `schema` | columns, or dimension values, appeared or vanished | diagnostics name the values, summarised across Blicks |
| `value` | some common row differs beyond tolerance | ranked by magnitude |
| `error` | the module failed to import, the transformation raised, or the output is invalid | exit code 2; never aborts the build; a failed module or another file-level error marks the build incomplete; that, or a Blick without a usable id, disables `removed` |

No flags means unchanged. The magnitude is computed on the common keys, also when `schema` is set
because dimension values appeared or vanished; it is `None` when the columns differ, since then
nothing is compared (amendment of 2026-10-24). What happens to flagged Blicks after a human has
looked at them belongs to the deferred accept design.

**Tolerance.** `[tool.blicket] tolerance = 1e-5` project-wide, `tolerance=` per Blick, in the
same relative-to-panel-scale units as the magnitude. A row is *same* when
|current − baseline| / s ≤ tolerance, with s the panel scale. Amendment of 2026-10-24: nothing
rounds and nothing is flushed to zero, so the `digits` key is gone; the tolerance alone absorbs
solver noise and must be positive and below 1. The defaults are validated in M0: a rerun of remind-mfa on another machine must produce
zero `value` flags. Small changes are never hidden; they rank low.

**Magnitude** (built-in routine), of the measure on `y`, bounded to [0, 1]:

- Panel: one combination of the filter values, plus the split values when the Blick sets
  `independent_y` (amendment of 2026-10-24); otherwise split dimensions share a scale inside the
  panel, as the facets share their y axis. "Panel" names such a scale group here; the viewer
  section uses the word for a facet.
- Panel scale s: the maximum absolute value of the measure on `y` in the panel across both tables,
  over the compared rows (the common keys), floored at ε times the Blick-wide scale, so that a panel
  that is all zero in the baseline cannot rank a 1e-9 ripple as a total change.
- Deviation per row = |current − baseline| / s, a row that one table lacks counting as 0;
  magnitude = min(1, max over rows). Amendment of 2026-10-24: `where` holds the dimension values
  of the first row, in the table's sort order, that reached the magnitude, or of the stack when a
  stack (below) changed more.
- Stacked plot types use s = max(sum of positives, |sum of negatives|) at each x of each panel,
  so negative flows cannot cancel the stack to zero. Amendment of 2026-10-24: they compare these
  two sums as well, so a change that moves every layer together counts as much as the stack top
  moves.
- Unit-free, bounded, matches what the eye sees on the chart, stable when values cross zero. No
  formula version is stored: the comparison file records the blicket version that wrote it
  (amendment of 2026-10-24). The formula will be iterated on real data.

## Build directory

```
my-model/
  pyproject.toml            [tool.blicket]: blick globs, loader, store path, tolerance
  blicks/**.py              Blick code
  blicks/plot_types/        project plot types (.py + .js)
  .blicket/                 gitignored
    build/<build-id>/
      manifest.json
      blicks/<id>.parquet         current tables
      compare/<baseline-id>/      comparison result and the baseline tables of changed Blicks, so the
                                  site is self-contained but small; additive, never changes the manifest;
                                  written by `check`, not `diff` (amendment of 2026-10-24)
      <viewer assets>
    store/                        default store location
```

The build directory is the portable unit: it can be copied from a cluster to a laptop and viewed
there with `blicket serve <dir>`. Relative paths in the manifest, a Nuxt build generated with a
relative base URL, and hash routing mean a build directory works on GitHub Pages, under subpaths,
on plain file servers, and after being copied. Amendment of 2026-10-24 (M1): `blicket build` copies
the installed viewer into the build directory with a `viewer-version` marker; the viewer files are
not in the manifest and do not affect the id, and building an existing id again replaces only them,
when the installed viewer differs. `build` and `serve` require a viewer: the bundled one, or the
one `BLICKET_VIEWER` names in a checkout.

## Viewer (Nuxt)

- `ssr: false`, `router.options.hashMode: true`, generated with a relative base URL (`./`, the
  default of `nuxt.config.ts` outside the dev server); the
  generated `.output/public` is installed into the wheel by a meson custom target. Node and Nuxt
  are maintainer-only dependencies.
- Overview: Blicks ranked by magnitude and coloured by flags, filters by flag, tag and group, the
  schema summary across Blicks.
- Blick page: chart, controls derived by the plot type, URL-carried control state, comparison
  toggle, diagnostics strip with the control combination where the change is largest.
- Builder page, dev mode only: see the Blick builder section.
- The viewer's own dev server proxies a Python-built build directory during viewer development.
- Opening from `file://` is blocked by browsers for `fetch`; `blicket serve` is the answer, a
  folder picker a later nicety.
- Amendment of 2026-10-24 (M1): the build derives each Blick's controls through the plot type and
  records them in the manifest (`BlickEntry.controls`), so the viewer only reads them; panels of
  split dimensions share their y axis unless the Blick sets `independent_y=True`, and a toggle
  changes either. A plot type's browser half is `{ render }` alone. `blicket serve` is a
  stdlib static server that answers from the installed viewer first, then from the build
  directory; the viewer's dev server proxies the build's files to it. The viewer uses Nuxt UI
  with its icons bundled, and the built-ins' browser halves are bundled with it.

## Development loop

`blicket dev <run dir>` runs the server, a watcher, and the build in one process with the loader
memoised.

- A changed Blick or helper module reloads **code, not data**: project modules are reloaded in
  import order except the loader, the memoised run object survives, only the affected Blicks are
  rebuilt, the server and the SSE connection stay alive. Only a change to the loader or the config
  restarts the process.
- A server-sent event tells the browser to refetch the changed Blicks while keeping control state.
- The run directory is polled with a quiet period, because inotify is unreliable on cluster
  filesystems and fires mid-write; `--no-watch-run` and a "reload run" button exist.
- The loader output is fingerprinted before and after a build, so a transformation that mutates
  the shared run object in place is reported instead of silently diverging from a clean `check`.
- Each dev rebuild is a build with an id and records the dirty flag. Dev builds are not pushed by
  default.
- Loader time on remind-mfa is measured in M0; a cached loader output is added only if it exceeds
  about ten seconds. No separate worker process.
- Target: under one second from save to updated chart for typical transformations.

## Blick builder (dev mode)

The custom view: an ad hoc Blick composed by GUI, available only with `blicket dev`. It is a
Blick builder, not a dashboard builder: one Blick at a time, shown in the same catalog with the
same controls and plot types.

- **Inputs come from the adapter.** The run picker uses the adapter's discovery and labels, and
  can add, remove and relabel model runs within the session; the loader reassembles the run.
  The variable picker uses the dataset protocol: a hierarchical dimension is shown as a tree,
  summation groups let one pick a derived "sub-variable" dimension once.
- **Layout is the plot type and its channels.** The user picks a plot type and assigns
  dimensions to the channels the plot type declares: facet for subplots, colour, line type,
  bar group. A dimension assigned to one channel disappears from the others. Dimensions not
  assigned become filter controls; every dimension has item selection with select all and
  unselect all.
- **Execution happens in Python.** The browser sends the builder state (runs, variables,
  sub-variable group, mapping, item selection) to the dev server, which runs the generic query
  transformation over the dataset protocol, canonicalises the table and returns it. The
  browser renders it with the plot type's browser half, exactly like a code Blick. The state
  also lives in the URL, so a link reproduces the ad hoc Blick within the session.
- **Nothing is saved.** Ad hoc Blicks sit in a scratch group for the session, are not built,  
  have no snapshot and never reach the guard. There is no declarative definition format. A  
  saved Blick is Python or R code; "export as code" is a later feature.
- **Later extensions** from the feature list, all deferred: differences relative to a
  reference run and a difference heatmap, run groups as a second label dimension, separate row
  and column facets, several hierarchy levels in one dimension, default years for bar charts,
  an enlarged World panel, unit conversion, label and appearance tweaks, totals as a line on
  stacks with negative items, export of several Blicks to png or pdf, validation data.

## Guard

`blicket check <run dir> [--against <build|branch>] [--push]` builds, resolves the baseline,
prints the summary, writes `report.md` (to the GitHub step summary when present) and
`report.json` (whether that is the comparison file under `compare/<baseline-id>/` is M0.7's to
decide, amendment of 2026-10-24), and exits 0 when nothing is flagged, 1 when something is, 2 on errors. It runs as a
post-run step on the cluster or in CI for models that run there. It never changes the store beyond
pushing its own build. Whether a flagged-but-reviewed change still exits 1 is part of the deferred
design.

## Accepting and managing changes: deferred

Not designed yet. What is fixed:

- Direction: **a UI plus PR-first interaction, as in Chromatic.** Changes are reviewed where the
  pull request is, in a web UI tied to the branch or PR, not through CLI selectors and record files.
- Constraints carried over from the concept: a human decides, with a recorded reason, individually
  or in bulk; CI only reports; builds are immutable, so acceptance is data attached to builds;
  baseline resolution follows git ancestry over accepted builds and matches the run profile.
- Open for that design: where the acceptance state lives (store, GitHub, a small service); how the
  UI reaches a cluster store; how the PR comment and status are produced and refreshed; what
  happens on dirty working trees; how the first baseline is seeded; how a removed Blick is retired.
- Everything in M0 to M2 works without it, by comparing against an explicit baseline build or the
  latest build of a branch.

## Language boundary and R

After M4. The build directory layout, the store layout and the manifest schema are the boundary.
Plot types have a Python build half, so R plot types are an open design problem for then; R Blicks
that use built-in plot types are the realistic first step.

## Libraries (reversible)

Python: polars, typer, starlette + uvicorn, watchfiles, pydantic (manifest models and JSON
Schema). Build backend: meson-python, with the viewer's `nuxt generate` as a meson custom target
whose output is installed into the wheel. Viewer: Nuxt 4 with Vue, vega-lite + vega-embed,
hyparquet for reading Parquet in the browser. Sankey (M4): d3-sankey-diagram, which supports
loops. TypeScript types for the manifest are hand-written for now.

## Project basics (decided 2026-10-23)

- Licence MIT. The repository lives under Tobias's own GitHub account for now, later under
  pik-piam. The GitHub organisation `blicket` is taken; the PyPI name was free on 2026-10-22 and
  is to be reserved.
- Python floor: the latest stable release at the time, 3.15. Tooling: uv, ruff, pytest,
  meson-python.
- Dogfooding: the remind-mfa adapter reads `model.pickle` from run folders named
  `<timestamp>_<model>_<scenario>_<regions>` and lives under `examples/remind-mfa/` in this
  repository, together with Blicks ported from remind-mfa's existing visualisations; they may
  look different from the originals. Example runs sit in `data_out/`, which is gitignored and
  never pushed. The remind-mfa checkout at `~/code/remind-mfa` can produce further runs.

## Milestones

- **M0 Headless build and compare on remind-mfa.** Package skeleton, config, registry and
  discovery with explicit ids and aliases, the adapter and loader protocol (the optional dataset
  protocol is only sketched; it is designed with the builder in M2), `RunInfo` with profile,
  canonical form,
  `PlotType` contract with built-in line, stacked area, bar (Python halves only), store with push
  and baseline resolution by profile and git ancestry against an explicit or branch baseline, flags
  and magnitude, `blicket check`, `blicket diff <build> <build>`, `report.md`, exit codes. No
  viewer. Dogfood on remind-mfa under `examples/remind-mfa/` with the pickled runs in
  `data_out/`, with two measurements: loader time, and the noise level across reruns and
  machines, which sets the tolerance default.
- **M1 Catalog.** Nuxt viewer with overview, Blick page with controls and comparison toggle,
  browser halves of the built-ins, `blicket build`, `blicket serve <dir>`. Amendment of
  2026-10-24: built ahead of M0.5–M0.7, so without the comparison toggle, which comes with them.
- **M2 Dev loop.** `blicket dev` with code reload, SSE, run-directory polling. Scatter and table
  plot types. The Blick builder with run picker, variable picker, channel mapping and item
  selection, on the remind-mfa adapter. This completes job 1.
- **M3 Review and accept.** Its own design session first, in the direction above. Then: the UI,
  the link from a cluster run to a branch or PR, the PR comment and commit status, and the store
  backend that makes the UI reach the builds. This completes job 2.
- **M4 Plugins and hardening.** A project plot type end to end (Sankey for MFA), `spec` version
  documented as the protocol, difference chart, store `gc`.
- **Later.** R; composition of several models or runs; preview deploys; DuckDB in the browser for
  large tables; the concept's deferred items (variants, checks, auto-accept, grouping).

## Verification

- Every milestone: the `examples/` project builds; `blicket check` on an unchanged run against its
  own previous build exits 0 on a second machine; a deliberate transformation change is detected
  with the expected flags and a sensible magnitude; from M1 the viewer renders the example.
- Store: pushing the same build twice is a no-op; a feature branch resolves main's latest build as
  baseline; a second profile resolves its own.
- Canonical form: the same table written twice hashes identically; the same data from polars and
  pandas hashes identically.
- Tolerance: a rerun of remind-mfa on a different machine produces zero `value` flags at the
  chosen defaults.
- Magnitude: property tests (identical tables give 0, scaling both tables leaves it unchanged, a
  sign flip gives 1, an added value gives `schema`, near-zero and sign-crossing cases).
- Hot reload (M2): editing a transformation updates the chart without reloading the page, control
  state preserved; editing a helper does not reload the run data.

## Two walkthroughs

### 1. The edit-and-look loop on the laptop (job 1)

Setup once: `[tool.blicket]` names the Blick globs, the loader, the store path and the tolerance;
the loader takes a run directory and returns the run object plus `RunInfo`.

1. You change model code and run remind-mfa. Outputs land in a run directory.
2. You start the companion on that run directory:

   ```
   $ blicket dev output/baseline-2026-10-23
   run baseline-2026-10-23 · profile baseline · blicks at a1b2c3 (dirty) · baseline: build 7f3e (main, 2026-10-20)
   48 Blicks: 41 unchanged · 5 value · 1 schema · 1 new · 0 errors
   top movers: flows/steel-by-process 0.31 · stocks/buildings 0.12 · flows/scrap 0.04
   viewer: http://127.0.0.1:8765/#/
   ```

   Behind this: discovery imports the Blick modules, the loader runs once and stays in memory,
   every transformation runs, tables go to canonical form, the store is searched for the baseline
   build, each plot type's diff runs against it, and a build directory with a fresh id is written.
3. The overview lists Blicks ranked by magnitude and coloured by flag, with filters by flag, tag and
   group. The schema summary says which value appeared, for example "process 'EAF-DRI' added in 3
   Blicks".
4. You open the top mover. The chart has the controls the plot type derived: a scenario dropdown, a
   region split toggle. The URL carries the control state, so a link reproduces the view. A toggle
   shows the plot type's comparison, for the built-ins a ghost of the baseline. A diagnostics strip
   shows counts and the control combination where the change is largest; clicking it sets the
   controls there.
5. Two outcomes. If the Blick's transformation is at fault, you edit its code; saving reloads the
   project code without reloading the run data, only that Blick is rebuilt, and the chart updates
   in under a second with the controls unchanged. If the model is at fault, you fix it and rerun;
   the run directory is polled, a new run triggers a full rebuild under a new build id, and the
   overview refreshes.
6. What is intended, you accept. How: see the deferred design.

### 2. A cluster run, looked at on the laptop (job 2)

1. You push a branch and open a PR. On the cluster you start a run from that commit. The run
   directory records the commit, either because the model writes it or because the loader reads it
   from the checkout.
2. A post-run step runs the guard on the cluster, with the store on the cluster filesystem:

   ```
   $ blicket check output/pr-142 --against main --push
   baseline: build 9c1d (main, 2026-10-21) · profile baseline
   48 Blicks: 42 unchanged · 6 value · 0 schema · 0 new · 0 errors
   build 4e8a pushed to /p/projects/remind-mfa/blicket-store
   exit 1
   ```

3. You copy the build to the laptop and look at it with the same viewer as in walkthrough 1:

   ```
   $ rsync -a cluster:/p/projects/remind-mfa/blicket-store/builds/4e8a .blicket/build/
   $ blicket serve .blicket/build/4e8a
   ```

4. Review, acceptance, the PR comment and the commit status: the deferred design, direction UI
   plus PR-first. After a merge, the branch's build is an ancestor of main, so the next run on main
   resolves it as baseline without further action.

### 3. An ad hoc Blick in dev mode (job 4)

1. In `blicket dev`, you open the builder. The run picker lists the model runs the adapter
   discovered, with labels you can edit; you add one fetched from the cluster.
2. You pick a variable from the tree, and "sub-variable" from one of its summation groups.
3. You choose stacked area, put sub-variable on colour and region on facet, and unselect two
   regions. The dev server runs the query, and the chart appears with the remaining dimensions
   as filter controls.
4. You copy the URL into a chat message; a colleague with the same dev session state sees the
   same Blick. Nothing is written to the project. If the Blick is worth keeping, you write it
   as code, until "export as code" exists.

## Decisions taken on 2026-10-23

- Python core, static Nuxt viewer vendored in the wheel, files as the API.
- Snapshots in a store, not in git (reverses the 2026-10-22 decision); builds immutable; baseline
  resolved by run profile and git ancestry.
- Parquet with zstd for stored tables; every pushed build kept; storage is no constraint.
- Labelled long table with dimensions and measures at the Blick output; raw data opaque.
- Full plot type contract implemented by every plot type including the built-ins; no generic
  fallback in the core.
- Change flags plus a bounded per-measure magnitude; project-wide tolerance with per-Blick
  override; unchanged means no row beyond tolerance.
- Default id `<group>/<function>`, aliases from M0, no rename detection by hash.
- Reload code not data in the dev loop; no worker process; cache only if measured loader time
  demands it.
- The build directory is the portable unit; cluster builds are copied to the laptop for viewing
  until a remote store exists.
- remind-mfa first; R after M4.
- Vega-Lite for built-in rendering.
- The custom view is a dev-mode Blick builder over the adapter's dataset protocol; transient,
  not saved, no declarative definition format. A saved Blick is code; export as code is later.
- The adapter is project code; no IAMC adapter ships for now. Plot types declare channels.
- Amendment of 2026-10-23 (M0.2 plan): the manifest is immutable and holds no comparison results.
  Flags, magnitude and baseline tables live in `compare/<baseline-id>/` inside the build directory,
  because the build id excludes the baseline and one build may be compared against several.
- Deferred: the accept and review workflow (M3, UI plus PR-first), TypeScript type generation,
  per-PR preview deploys, difference chart (M4), the `definition` change type, remote store
  backends until M3, export of ad hoc Blicks as code, a shipped IAMC adapter.
