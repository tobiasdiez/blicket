# blicket: a Storybook for data projects

Name: `blicket`, chosen 2026-10-22. The directory was renamed from `compare` to `blicket` the same day; a symlink at the old path remains until Orca is re-pointed. Status: concept and architecture decided, nothing implemented yet. The architecture, the milestones and two walkthroughs are in [architecture.md](architecture.md).

## One sentence

`blicket` is to data transformations and their charts what Storybook is to UI components:
every figure of a project is defined in code as a Blick, rendered in isolation in a browsable
catalog, and checked against a stored snapshot whenever the underlying data or code changes.

## Why

The primary context is scientific modelling, concretely an integrated assessment model (IAM)
and a material flow analysis (MFA), with other models of that kind likely to follow. Such
models produce large, labelled, multi-dimensional output tables per run. Analysis happens
through a set of standard figures that are regenerated after every run.

Today this is done with ad hoc scripts, notebooks, or huge static reports. REMIND's
`compareScenarios`, for example, produces a PDF of roughly a thousand pages. The pain points:

- There is no fast way to see what a code change did to the results.
- Figure definitions drift, get duplicated, and go stale.
- Reviewing changes is all or nothing. Nobody reads a thousand pages.
- Results are hard to share in a form others can actually look at.

The tool should remain useful outside scientific modelling. Anything that produces tabular
data could use it. Generality comes from the data model and the plugin boundaries, not from
domain-specific features.

## Core concepts

**Run.** One execution of a model, or more generally one version of a dataset. The run's raw
outputs are the input to everything else. A run has internal dimensions. The project's loader
defines what a run is; it may collect several model runs, for example several REMIND
scenarios, into one run, with the model run as a dimension.

**Adapter.** Project code, the counterpart of Storybook's `main.ts`: the loader that finds,
reads and labels runs; metadata about dimensions, such as the hierarchy of IAMC variable names
with their summation groups, display order and styles; and the project's own plot types.
blicket ships nothing domain-specific; a standard IAMC adapter may come later.

**Catalog.** The built site for one run: all Blicks of that run, with the overview page as
its front page. One run, one catalog.

**Dimension.** A labelled axis in the run's data: scenario, region, year, variable, material,
process. Dimensions are how comparison *within* a run works, for example SSP1 against SSP2.

**Blick.** The unit of the catalog, what Storybook calls a story. A Blick consists of

1. a transformation function that turns raw run data into a small tidy table,
2. a plot type, and
3. a mapping from the table's dimensions to the plot type's channels.

Dimensions of the output table that are not bound to a channel become controls: filter to
one value, or split by the dimension.

**Plot type.** A named chart kind with a fixed contract (see below). A small vocabulary ships
with the tool: line, stacked area, bar, and similar. A project can define its own plot types,
for example a Sankey diagram for MFA, and then has to implement the full contract.

**Snapshot.** The stored transformed table of a Blick from a build. Snapshots live in a
snapshot store outside git: a directory on a shared filesystem or the cluster, remote backends
later. A build is immutable; the baseline for a new build is resolved from the store along git
ancestry, matching the run profile. Snapshots are the baseline for change detection.

**Change and review.** The difference between a Blick's current transformed table and its
baseline. The review flow lists changed Blicks on the overview page, ranked by change
magnitude. A human inspects and accepts, individually or in bulk, with a recorded reason. The
mechanics of accepting are being redesigned (2026-10-23): the direction is a web UI tied to the
pull request, as in Chromatic, rather than a CLI and files in git.

## Name

Decided on 2026-10-22. The unit was named first, the tool derived from it.

- **Blick.** The unit, what Storybook calls a story. German for "a look". The plural is
  Blicks, in code, CLI output and docs alike.
- **blicket.** The project, the package and the CLI. A little Blick, and a nod to the blicket
  detector of Gopnik and Sobel (2000), the developmental-psychology apparatus that lights up
  when an object with a hidden property is placed on it. Our guard lights up when a Blick
  carries a hidden change.

Everything else uses plain English: catalog, snapshot, overview, comparison.

Availability on 2026-10-22: the package name is free on PyPI, npm and crates.io; blicket.dev,
blicket.org, blicket.app and blicket.science are free; the GitHub organization `blicket` and
blicket.com are taken. Reserve the free ones before the first release.

## Jobs, in priority order

1. **Development companion.** After a run: build the catalog, see which Blicks changed
   against their snapshots, inspect them with controls, iterate on the model or on the Blick
   code. Blick code changes should hot reload.
2. **Automated guard.** In CI or after each model run: build, compare, produce a change
   report. Fail or warn when unaccepted changes exist. The exact policy is still open.
3. **Communication artifact.** The built catalog is a static site, so it can be shared
   with colleagues, reviewers, or as a paper supplement. This follows from job 1.
4. **Exploration.** The controls on each Blick give basic interactive exploration. In dev
   mode a Blick builder composes an ad hoc Blick from the run's data by GUI: pick runs and
   variables, a plot type, and which dimensions go to which channels. It is a Blick builder,
   not a dashboard builder: one Blick at a time, in the same catalog, with the same controls
   and plot types. Ad hoc Blicks are not saved; a later export turns one into Python or R
   code.

## A day with blicket

- You change the model code and run it. Outputs land in a run directory.
- You build the catalog for that run. Every Blick's transformation runs, per-Blick data is
  written, the static site is rendered, and each Blick is compared with its baseline from the
  store.
- The terminal prints a summary: how many Blicks, how many changed, the top movers.
- The overview page shows all Blicks as a grid coloured by change magnitude, biggest movers
  first. You open a Blick: the chart with its controls, plus a toggle that shows the
  comparison with the baseline in the form the plot type provides.
- Thirty of the changes are the expected consequence of your change. You bulk accept them
  with the reason "updated steel emission factors". Seven look wrong, so you fix the model
  and rerun. (How accepting works is being redesigned; see architecture.md.)
- Accepting makes the build's tables the baseline for later builds. The pull request shows a
  report of the changed Blicks and the recorded reasons; nobody reads snapshot files.
- After a model run on the cluster or in CI, the guard compares the run with its baseline and
  reports changed Blicks on the pull request.

## Plot type contract

Every plot type, built in or project defined, provides three operations:

- **controls(schema, channel mapping)**: given the dimensions of the Blick's output table
  and which of them are bound to channels, decide which controls to show.
- **render(table, control state)**: produce the chart.
- **diff(table_a, table_b)**: produce a normalised change magnitude for ranking, and a
  comparison rendering such as an overlay, a difference chart, or side by side.

This is the plugin boundary. A project that adds a plot type must implement all three.

## Comparison model

Two kinds of comparison, kept deliberately separate:

- **Within a run, along a dimension.** Handled entirely by Blick controls, for example
  split by scenario. Nothing special in the tool.
- **Across versions.** Current run against the stored snapshot. Handled by the review flow.
  Because the snapshot is the baseline, old runs do not have to be available.

The change magnitude comes from the plot type's diff operation, with a generic fallback
based on the table. It is used for ranking and the overview page, not yet for automatic
pass or fail decisions.

## Working architecture assumptions

Not decided, but assumed until something contradicts them:

- Transformations run at build time and produce small per-Blick tables. The browser never
  sees the raw run data.
- The built catalog is a static site. A dev server with hot reload sits on top of the same
  output for the development loop. This mirrors Storybook's own dev server and static build.
- Blicks are defined in code in the host language, with a small manifest for the catalog.
- Snapshots are one Parquet file per Blick inside an immutable build, kept in a snapshot store
  outside git. Only Blick code, plot types and config are in git.

## Decisions taken on 2026-10-22

- The unit is a transformation function plus a chart rendered in a predefined way.
- One catalog is one run. Dimensions live inside a run. Scenario comparison is a
  dimension control, not a cross-run comparison.
- A Blick is a figure with dimension controls. There are no Blicks that pin a selection.
- The baseline is a set of stored Blick snapshots kept next to the code. Superseded on
  2026-10-23: snapshots live in a store outside git.
- Changes are handled by review and accept, supported by ranking by magnitude, an overview
  page of all Blicks, and bulk accept with a recorded reason.
- Charts come from a fixed vocabulary, extended by project-defined plot types that implement
  the full contract including diff and controls.
- Development companion and automated guard are the first two jobs to get right.
- The unit is called a Blick and the project blicket. Everything else uses plain English.

## Decisions taken on 2026-10-23

Taken after an architecture plan and its adversarial review; details in architecture.md.

- Snapshots are not stored in git. They live in a snapshot store (a directory, on the cluster for
  shared projects); builds are immutable; the baseline is resolved along git ancestry and by run
  profile, as Chromatic does. Storage is no constraint.
- Project plot types implement the full contract (controls, render, diff), confirmed. The core
  provides no generic fallback; helpers may come later.
- Noise tolerance is a project-wide setting with a per-Blick override, defined relative to the
  panel scale; defaults are measured on real outputs.
- First dogfooding project: remind-mfa. R comes after milestone 4.
- Cluster builds are copied to the laptop for viewing for now. Goal: a cluster run is linked to a
  branch or pull request and the comparison is visible on GitHub.
- The viewer is a Nuxt app in client-only mode; built-in plot types render with Vega-Lite.
- How changes are accepted and managed is deliberately not decided. Direction: a UI plus
  PR-first interaction, as in Chromatic. This is its own design step before milestone 3.
- Several run configurations per branch are handled by a run profile in the run info; each
  profile has its own baseline.
- The custom view is a Blick builder in dev mode. It composes transient Blicks from the run's
  data through the adapter; nothing is saved, and there is no declarative definition format.
  A saved Blick is code. An export to Python or R is a later feature.
- The adapter is project code. No IAMC adapter ships with blicket for now.
- Plot types declare their channels, so that the builder can offer them.

## Deferred decisions

- **Data model.** Labelled long table as the core, fully agnostic, or agnostic core with
  adapters. Note: the controls mechanism needs named dimensions on Blick outputs, so some
  labelled-table assumption at that level seems unavoidable. Raw inputs can stay opaque.
- **Language.** Python first. R after milestone 4 (2026-10-23), through the file layout of
  builds and the store.
- **Reference and historical data.** As a dimension value, as a pseudo-run, or per Blick.
- **Variants.** Saved control presets per Blick. Useful for communication, skipped for now.
- **Checks.** Assertions such as mass balance or non-negativity. Out of scope for now.
- **Auto-accepting** small changes, and **grouping** of changes by shared input variables.
  Both plausible triage aids, not chosen yet. (The noise tolerance itself is decided; see
  2026-10-23.)
- **CI policy.** Whether unreviewed changes fail the build or only produce a report. Tied to
  the accept design.
- **Arbitrary run against run** comparison. Any two builds in the store can be diffed; the
  user interface for it is deferred.
- **Export of ad hoc Blicks** as Python or R code, and predefined Blick sets generated from
  remind2's compareScenarios2 as code.
- **A shipped IAMC adapter**: mif and xlsx reading, the run-folder naming scheme, the plus-sign
  hierarchy, plotstyle colours, validation data.

## Open questions

- Several models per repository.
- Whether the static-first assumption limits exploration too much.

Resolved on 2026-10-23 and recorded in architecture.md: snapshot size and storage (store outside
git, storage no constraint), dimension values appearing or disappearing (a `schema` flag that
names them), Blick identity (explicit ids with aliases), raw data access (a project loader,
memoised in the process), several runs per branch (run profiles).

## Prior art

- **Storybook and Chromatic.** Catalog of isolated components, stories as fixed inputs,
  review and accept of visual changes.
- **REMIND compareScenarios** (R, `mip` package). Standard plots across runs as a PDF.
  Powerful, but static and without diffs.
- **DVC plots.** Templated plots diffed across git revisions, built for small ML metrics.
- **pyam and the IIASA Scenario Explorer.** IAMC data handling and database browsing.
- **MLflow, Weights & Biases.** Experiment comparison on scalar metrics.
- **Jest and pytest snapshot testing.** Snapshot as baseline, updated on accept.
- **Quarto and Jupyter.** Flexible reports without a catalog or diff awareness.
