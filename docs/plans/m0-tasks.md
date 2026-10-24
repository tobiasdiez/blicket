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
- `data_out/` holds runs produced on 2026-10-24 from remind-mfa HEAD `a7c389a` with input data
  2.8.0 (see `data_out/RUNS.md`): two unchanged reruns and one with `collection_rate` scaled by
  0.9. The reruns' raw tables are byte-identical, so there is no rerun noise on this machine.
  Tobias dropped the cross-machine requirement on 2026-10-23. (The original three runs of
  2026-10-22 came from an older remind-mfa and were deleted.)
- The pickled model exposes `future_mfa` and `historical_mfa`, flodym `MFASystem`s with 52 flows,
  5 stocks and 8 dimensions (Time, Historical Time, Region, Element, Polymer, Polymer Type, End
  Use, Driver Scenario). `FlodymArray.to_df()` yields a long table with a named MultiIndex, and
  blicket accepts the array itself. A pickle loads only with the remind-mfa version that wrote it.
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
protocol (`load_run` in `blicketconf.py` by convention, or `loader = "pkg.mod:load_run"`, called
once per build with the run selection). The Blick
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
this task, as trimmed by the review of the M0.2 plan: the manifest's `BlickDefinition` pydantic
model becomes the single *output* description of a Blick's fields (`Blick` stays a dataclass and
gains `definition()`; the hand-written `to_json` methods go; input validation stays in
`_validation.py`, because it runs at decoration time before id and group exist, and the
`BlickOptions` TypedDict stays for keyword typing); one `BlickEntry` shape describes a Blick in the
registry and in the manifest alike, carrying id and aliases at the top level and the definition
when one could be built, so a Blick with a full definition and a raised transformation is
representable and a failed Blick is never mistaken for a removed one; the
traceback and path helpers private to discovery (`project_traceback`, `locate`) move to a shared
module; the CLI gets shared `--project` and `-v` option aliases and one `finish(text, failed)` for
output and exit code before the second command is written (today the exit-code policy sits on the `list`
command's class, so a second command would have to pass the same `cls=`; move it to one place); `Registry.to_json` writes an absolute `root`, which
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

`examples/remind-mfa/` as its own virtual uv project depending on blicket (path dependency, not
editable; blicket's pyproject gets `cache-keys` so the example sees source changes) and on
remind-mfa (editable path dependency on the sibling checkout, with a dependency override for
polars, which remind-mfa's tree pins below 2.0). A loader that reads `model.pickle` from the run folder and
returns the run object plus `RunInfo` (run id from the folder name, profile from the pickle's
config, fingerprint of the pickle; no model commit, since the pickle carries none and the
checkout's HEAD is not the commit that produced a run). Ten Blicks ported from
`visualize_common` and the plastics `visualize_custom`: use stock by region and by end use,
consumption, production, production versus net imports versus consumption, end-use split, GDP
per capita, scenario rates, polymer splits (trade waits for a sign convention in M0.5 or M4).
Loader and transformation times recorded in the plan file. The plan file also sketches the
dataset protocol the builder will need in M2, on paper only, as the architecture asks. The runs
in `data_out/` must come from the remind-mfa commit the Blicks are written against.

Done when `blicket build` works on each of the example runs and the timings are recorded.

### M0.4 Canonical form and content hashes

Input from M0.3: on the fresh runs (remind-mfa HEAD, input data 2.8.0) two unchanged reruns
produce byte-identical raw tables for all Blicks, so there is no rerun noise to measure on one
machine. The deliberately changed run (`collection_rate` × 0.9) is visible in
`flows/production_by_source`; the two production tables differ from the reruns by a relative
3.9e-16 only, float rounding that counts as a second noise sample. `flows/production_by_polymer`
holds 573 tiny negatives (down to −1.25e-7), 881 positives below 1e-12 of the maximum and 1604 rows
under 1e-9 of it, while genuine small values start near 1e-7 of the maximum: the zero floor belongs
near 1e-9 to 1e-8 of the Blick scale, not 1e-6. The canonical form fixes the dimension column
order, so a rewrite of a Blick (`pd.concat` puts the naming dimension first) does not change
hashes.

Typed sort on the dimension columns, N significant digits, the zero floor relative to the
Blick-wide scale, Parquet with zstd, and a content hash per table that is independent of the
input library. Designed against the flodym tables from M0.3, not synthetic data. A measurement on the example
runs on raw and canonical tables, recorded in the plan.

Done when the same table hashes identically twice and from polars and pandas alike, the two
unchanged reruns hash identically and the changed run differs in exactly the two production
tables at the proposed `digits` default, and a test pins the format.

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

From M0.3: `flows/production_trade_consumption` puts Production (5e8) and sign-crossing net
imports (−9e7) in one panel (Region split, Flow colour); a panel-relative tolerance turns a 10 %
change of net imports into about 1 %, so decide per-series versus per-panel scale on this Blick.
Carried over from the M0.1 architecture review: derive the plot factories from the channel
declarations (`PlotType.__call__(**mapping) -> PlotSpec`) instead of one hand-written factory per
built-in, so project plot types in M4 get theirs for free.

Done when the property tests from the architecture's verification list pass: identical tables
give 0, scaling both leaves the magnitude unchanged, a sign flip gives 1, an added value gives
`schema`, near-zero and sign-crossing cases behave.

### M0.6 Store, push and `blicket diff`

Carried over from the M0.2 architecture review: before the second report-producing command,
introduce a `Report` protocol (`failed`, `text(verbose)`, `json()`) with the text renderers in a
`report.py`, so `diff`'s flag counts and top movers and M0.7's `report.md` are renderers over the
same data instead of more branches in `cli.py`. `push` copies the manifest and the tables with the
umask-respecting directory modes blicket writes (never `copystat` of a private directory).

The `Store` class over a directory (`builds/<build-id>/` with manifest and tables), `push` as an
immutable copy that is a no-op when the build exists, listing and lookup, the default
`.blicket/store` and the `store` config key. The comparison file format next to the manifest.
`blicket diff <build-a> <build-b>` compares two builds from the store or two build directories
Blick by Blick through the plot types' `diff`, matching ids through aliases and reporting `new`
and `removed`, and prints the terminal summary (counts per flag, top movers).

Done when pushing twice is a no-op, `blicket diff` of two remind-mfa builds prints a summary, and
a Blick renamed with an alias is matched to its old table.

### M0.7 Baseline resolution, `blicket check`, reports and exit codes

Carried over from the M0.2 architecture review: `compare/<baseline-id>/` cannot be enumerated over
HTTP on static hosting, so `check` also writes `compare/index.json` additively, listing the
baselines a build was compared against, for the viewer. From M0.3: one example project will hold
Blicks for several models (plastics, steel, cement) with one loader and one profile per model, so
a Blick that does not apply to a run (a plastics Blick on a steel run) needs a status distinct
from `error` and `removed`; design it together with `removed`.

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
