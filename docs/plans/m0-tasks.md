# M0 in tasks

Status: proposed on 2026-10-23, before any code, revised the same day after an independent review.
Splits milestone M0 of [architecture.md](../architecture.md) ("Headless build and compare on
remind-mfa") into tasks sized for one plan → review → implement → review loop each. The order
follows the dependencies, and every task leaves something runnable. Each task gets its own plan
file in this directory when it starts; the first one is
[m0-1-skeleton-and-registry.md](m0-1-skeleton-and-registry.md).

## Facts gathered on 2026-10-23 that shape the split

- Loading one remind-mfa `model.pickle` (112 MB) takes 1.4 s in remind-mfa's own environment
  (Python 3.14). That settles the loader-time question M0 was meant to measure: well below the
  ten-second threshold, so no loader cache in M0.
- Unpickling needs `remind_mfa` and `flodym` importable. The example project therefore depends on
  the remind-mfa package (a path dependency on `~/code/remind-mfa` for now) and must share one
  environment with blicket.
- **Python 3.15 clashes with that environment.** remind-mfa depends on pyam-iamc 4.0, which pins
  `numpy<2.5` and `matplotlib<3.11`; those versions and pyyaml have no 3.15 wheels, so a 3.15
  environment builds them from source (numpy alone takes about a minute and needs compilers, also
  on the cluster). blicket's own dependencies (typer, pydantic, polars 2.0) have 3.15 wheels.
  Decided on 2026-10-23: the floor is 3.14 for now and is raised once remind-mfa's dependency
  chain ships 3.15 wheels.
- Three `plastics_SSP2_h12` runs made minutes apart from the same code sit in `data_out/`. Their
  pickles differ byte-wise, so they are a real rerun-noise sample for one machine. Tobias dropped
  the cross-machine requirement on 2026-10-23; M0 measures noise on this machine only.
- The pickled model exposes `future_mfa` and `historical_mfa`, flodym `MFASystem`s with 52 flows,
  5 stocks and 8 dimensions (Time, Historical Time, Region, Element, Material, Type, End Use,
  Driver Scenario). `FlodymArray.to_df()` yields a long table, the input form the architecture
  already planned for.
- Toolchain on this machine: uv 0.13.5, meson and ninja installed, CPython 3.14.8 as system
  Python.

## Tasks

### M0.1 Skeleton and Blick registry

Repository layout and packaging (meson-python, uv, ruff, pytest, ty, MIT), the `[tool.blicket]`
config, `bk.group`, `bk.blick`, `bk.register` and `bk.slug`, discovery with explicit ids, the
default id `<group>/<function>`, aliases, structured discovery errors (duplicate ids, alias
collisions, broken modules) that never abort, the `PlotType` base with channel declarations and
the four built-in factories (declarations only), `blicket list`, and the CLI exit-code policy.

Done when a fresh clone passes `uv sync && uv run pytest`, the wheel installed into a clean
environment runs `blicket list` on a fixture project with the expected output, and a broken
module is reported with exit code 2 without hiding the other Blicks.

### M0.2 Loader, RunInfo and the headless build

`RunInfo` (run id, profile, fingerprint, model commit and branch, dirty flag) and the loader
protocol (`loader = "pkg.mod:load_run"`, called once per build with the run selection). The Blick
output table as a polars frame: conversion from polars, pandas, pyarrow, xarray and flodym,
dimension and measure inference with `dims=` and `measures=`, `order=`, validation (unbound
measures and duplicate dimension keys are an `error`). Running all transformations, capturing
exceptions as `error` entries. The build directory `.blicket/build/<build-id>/` with `blicks/<id>.parquet`
(plain Parquet; canonical form follows in M0.4) and `manifest.json` from pydantic models with a
`spec` version: definitions, RunInfo, HEAD, branch and dirty flag of the Blick repository, per-Blick
table hashes, errors and an `incomplete` flag. The build id as the hash of definitions, table
hashes, run fingerprint and commit; M0.4 only changes what the table hash is computed on.
`blicket build <run dir>` runs it end to end without any comparison.

The manifest is immutable and holds no comparison results. Comparison output (flags, magnitude,
baseline tables) is written next to it, keyed by the baseline build id, from M0.6 on. This
amends the architecture's manifest sketch, which listed flags in the manifest; without the
amendment the same build checked against two baselines would differ while keeping one id. Tobias
accepted the amendment on 2026-10-23; architecture.md is updated when M0.2 lands.

Structural decisions carried over from the M0.1 architecture review, to be done at the start of
this task: the manifest's `BlickDefinition` pydantic model becomes the single description of a
Blick's fields (`Blick` holds it plus `transform` and `PlotSpec`, `to_json` is `model_dump`, the
`BlickOptions` TypedDict and its field table go, and one helper rewords pydantic errors for config
and definitions alike); `FailedBlick` carries the definition when one could be built, so a Blick
with a full definition and a raised transformation is representable; the traceback and path
helpers private to discovery (`project_traceback`, `locate`) move to a shared module; the CLI gets
a reusable `Project` option resolved once in the callback and an `Outcome` (text, JSON, exit code)
protocol before the second command is written (today the exit-code policy sits on the `list`
command's class, so a second command would have to pass the same `cls=`; move it to the app once); `Registry.to_json` writes an absolute `root`, which
the manifest must not inherit, since a build directory is portable. Two further notes from the
round-3 architecture review: the manifest keeps two containers, file-level problems (which make a
build `incomplete`, exposed today as `Registry.incomplete`) and per-Blick status, rather than one
flat list, because the same problem kind means "whole file skipped" in one and "one Blick bad" in
the other; and the decision to describe each shape once in pydantic should extend to `Problem` and
`Source`, so the manifest does not grow a parallel problem model (decide with the manifest in
hand).

Done when a fixture project with a trivial loader builds, a raising transformation lands in the
manifest as an `error` instead of aborting, and the manifest validates against its JSON Schema.

### M0.3 remind-mfa adapter and first Blicks

`examples/remind-mfa/` as its own uv project depending on blicket (path dependency, not editable,
refreshed with `uv sync --reinstall-package blicket`; an editable install would share
meson-python's build directory with the root environment and break on rebuilds) and on remind-mfa.
A loader that reads `model.pickle` from `<timestamp>_<model>_<scenario>_<regions>` folders,
parsed from the right so scenarios with underscores survive, and returns the run object plus
`RunInfo` (run id from the folder name, profile from model, scenario and regions, fingerprint of
the pickle, model commit when the checkout is available). Five to eight Blicks ported from
`visualize_common` and the plastics `visualize_custom`: use stock by end use, consumption,
production, trade, end-use split, GDP per capita, polymer splits. Loader and transformation times
recorded in the plan file. The plan file also sketches
the dataset protocol the builder will need in M2, on paper only, as the architecture asks.

Done when `blicket build` works on each of the three example runs and the timings are recorded.

### M0.4 Canonical form and content hashes

Typed sort on the dimension columns, N significant digits, the zero floor relative to the
Blick-wide scale, Parquet with zstd, and a content hash per table that is independent of the
input library. Designed against the flodym tables from M0.3, not synthetic data. A first noise
measurement across the three local reruns on raw and canonical tables, recorded in the plan.

Done when the same table hashes identically twice and from polars and pandas alike, the three
reruns hash identically at the proposed `digits` default, and a fixture test pins the format.

### M0.5 Plot type contract and change detection

`controls(schema, mapping)` and `diff(baseline, current, mapping, controls)` on `PlotType`, the
`Control` and `Change` types (flag set, magnitude, diagnostics with the panels that changed
most). The shared internal diff routine: outer join on the dimension columns, `schema` with the
named values, `value` with the tolerance relative to the panel scale, the panel scale with its
ε floor, the stacked-scale rule for `stacked_area` and `stacked_bar`, the bounded magnitude per
measure, the formula version in the manifest. The built-ins' `controls`: unbound dimensions
become filters, `split` where the chart facets, dimensions functionally determined by others are
hidden, `controls=` and `defaults=` from the Blick definition apply. Panels are defined by the
filter controls; `split` is the facet.

Carried over from the M0.1 architecture review: derive the plot factories from the channel
declarations (`PlotType.__call__(**mapping) -> PlotSpec`) instead of one hand-written factory per
built-in, so project plot types in M4 get theirs for free.

Done when the property tests from the architecture's verification list pass: identical tables
give 0, scaling both leaves the magnitude unchanged, a sign flip gives 1, an added value gives
`schema`, near-zero and sign-crossing cases behave.

### M0.6 Store, push and `blicket diff`

The `Store` class over a directory (`builds/<build-id>/` with manifest and tables), `push` as an
immutable copy that is a no-op when the build exists, listing and lookup, the default
`.blicket/store` and the `store` config key. The comparison file format next to the manifest.
`blicket diff <build-a> <build-b>` compares two builds from the store or two build directories
Blick by Blick through the plot types' `diff`, matching ids through aliases and reporting `new`
and `removed`, and prints the terminal summary (counts per flag, top movers).

Done when pushing twice is a no-op, `blicket diff` of two remind-mfa builds prints a summary, and
a Blick renamed with an alias is matched to its old table.

### M0.7 Baseline resolution, `blicket check`, reports and exit codes

Candidates by run profile and git ancestry of the Blick repository's HEAD
(`git merge-base --is-ancestor`), `--against <build-id>` and `--against <branch>`, most recent
candidate wins, per-Blick fallback to older candidates, `new` when none.
`blicket check <run dir> [--against ...] [--push]` as build, resolve, diff and report in one
command, with the baseline tables of changed Blicks copied into the build directory's comparison
output. `report.md`, appended to the GitHub step summary when that variable is set, and
`report.json`. Exit codes 0, 1 and 2 as set by the M0.1 policy. `removed` disabled when a module
failed to import.

Done when a feature branch resolves main's latest build as baseline, a second profile resolves its
own, `check` on an unchanged run against its own previous build exits 0, and a deliberate
transformation change is flagged with the expected flags and a sensible magnitude.

### M0.8 Measurements, defaults and M0 verification

A fresh remind-mfa run from the current checkout on this machine, checked against a build of an
older run, confirming or correcting the `tolerance` and `digits` defaults chosen in M0.4;
measurements recorded in `docs/`. Walk the M0 verification list of the architecture, with the
cross-machine item waived. A README with installation and the `check` walkthrough.

Done when the fresh rerun produces zero `value` flags at the defaults, and every other M0 item in
the verification list holds.

## Decisions taken on 2026-10-23

1. **Python floor 3.14** for now, raised when remind-mfa's dependency chain ships 3.15 wheels.
2. **Comparison results outside the manifest** (see M0.2): accepted.
3. **No second-machine run.** The cross-machine noise measurement in the architecture's
   verification list is waived; M0 measures reruns on one machine.
4. **Default ids keep the function name as is** (`flows/steel_by_process`); see the M0.1 plan.

## Not in M0

The viewer and `blicket serve` (M1), the dev server, hot reload and the Blick builder with its
dataset protocol (M2), the accept flow (M3), project plot types (M4). The tasks above keep the
hooks these need, such as the module recorded per Blick for reloading, but do not implement them.
For M2's reload the M0.1 architecture review noted what the discovery primitives still lack: the
set of Blick modules must persist on the discovery state between imports (so a single-module
reload still attributes helpers correctly), `plan(root, config)` and `import_target(target)` should
be public, and the importing state needs a lock once a watcher thread and a request thread share
the process.
