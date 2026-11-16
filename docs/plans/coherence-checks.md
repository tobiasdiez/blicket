# Coherence checks: expectations on Blicks, and checks as a second unit

Status: planned on 2026-11-10 on `dcfd796`, revised the same day after an independent review against
the code, accepted by Tobias on 2026-11-16, and built the same day on `dcfd796`, then revised after
a review of what was built; see [Outcome](#outcome). Tobias asked for it after remind-mfa, the first
user, shipped about 200,000 slightly negative flow values from an iso249 run into an export: the
model's own check tolerated them silently (the fix is `c02bf76d` in remind-mfa). blicket so far
answers "what changed against the baseline"; this adds "this run violates a property that must
always hold", declared once, evaluated for every run, shown, compared with the baseline and able to
fail CI. It takes up the concept's deferred decision "Checks". `bk.Skip` (amendment of 2026-11-02,
commit `fbae119`) is the precedent for a feature that crosses the manifest, the reports, the
comparison and the viewer.

## Goal

A project states properties of a run in two places:

- **`expect=` on a Blick**, for a Blick that is plotted for its own sake: its table must meet an
  expectation, evaluated when the Blick is built.
- **A check**, a second unit beside the Blick, for a property nobody wants as a chart: a function
  of the run that returns the offending rows as a long table; no rows means the property holds.

Both give the same outcome record (met, warning or failed; how many rows; the worst; where), which
`build`, `check` and `dev` report, the manifest records, a comparison relates to the baseline, the
viewer shows, and which makes `build` and `check` exit 1 when an expectation of level `error`
failed.

Decided with Tobias before the plan: `expect=` on Blicks; checks as a second unit with their own
section in the viewer, showing a table instead of a chart; no API that runs the checks on a loaded
run without a build.

## Facts the plan rests on (checked 2026-11-10)

- remind-mfa's Blicks (`remind-mfa/yabby`): the run is `Run(models: dict[str, CommonModel])`,
  three models; flows, stocks, trade and parameters are flodym arrays reached per model. About 141
  flows with different dimension sets; about 4.6 million cells at 12 regions, about 95 million at
  249. A table over "all flows of all models" has the columns `Model`, `System`, `Flow` and the
  union of the flows' dimensions, null where a flow lacks one; its rows are still unique.
- The model's own tolerance is absolute and scaled by the largest flow or stock of a whole MFA
  system (flodym's `_absolute_float_precision`), so a check that reproduces it normalises by a
  scale only the check's code knows.
- The Blick "Secondary steel share against the REMIND inputs" returns `[Source, Series, Time,
  Region, value]`: the model's share and REMIND's maximum share are different rows (different
  `Series` and `Source`), and the maximum varies by time, region and scenario. "Share at most the
  maximum" is therefore no comparison of a column with a number; it joins rows of the table.
- remind-mfa's CI (`ci-run.yml`) runs `blicket check … || code=$?` and fails the step on `[ "$code"
  -ne 2 ]` only: exit 1, a flagged change, is expected on a pull request.
- Builds of another `spec` in a store are skipped and counted (`Store.list`, `baseline.resolve`),
  and the viewer refuses a manifest of another spec (`useManifest.ts`). A spec 0.2 manifest
  validates against models whose new fields have defaults.
- `from blicket import check` (`cli.py`, `dev.py`) names the module `blicket/check.py`; once the
  package exports a function `check`, the two collide in both directions.
- The viewer: `lib/manifest.ts` mirrors the manifest by hand; the sidebar's entries, badges and
  the "Changed (N)" toggle are in `lib/sidebar.ts` and `BlickSidebar.vue`, whose header has room
  for the search box and that one toggle; `ChangeStrip.vue` and `whereState` in
  `lib/comparison.ts` implement "Show where"; `DataTable.vue` shows the first 2,000 rows of a
  table with a schema; `useBlickId` reads the route's `id` whatever the route; `Badge` is keyed
  by a comparison flag; `byStatus` and `isStatus` know exactly the three statuses.
- `examples/remind-mfa` has no runs in this worktree; five plastics runs at 12 regions are in
  `/home/tobias/code/blicket/data_out/`. Its run object is the `PlasticsModel`:
  `run.future_mfa.flows`, `.stocks[k].stock/.inflow/.outflow`, `.parameters`.

## Key decisions

1. **Names.** The unit is a **check**: `@bk.check` and `bk.register_check`. The vocabulary is
   `bk.expect.*`. What an expectation gives is its **outcome**; the umbrella word in reports is
   "expectations", since a check is a table plus an expectation. `blicket check` keeps its name:
   it builds, which evaluates the expectations, and compares with the baseline, and "check a run"
   reads better with checks in it than before. The module `blicket/check.py` (the comparison with
   the baseline in the store) is renamed `guard.py`, with its test file: the export `bk.check`
   makes the rename necessary, and the architecture calls that job the guard. The new code lives
   in `blicket/expect.py`.
2. **One outcome model.** An expectation maps a table to its offending rows, each with a distance
   that says how far it offends. A check's expectation is mandatory and defaults to
   `bk.expect.no_rows()`; a Blick's is optional. Both go through the same evaluation and give the
   same `Outcome`, and reports, the comparison, the exit code and the viewer are written once
   against it.
3. **The vocabulary.**
   - `no_rows(rows=None, *, by=None, warn_within=None)`: no row offends. Without `rows`, every row
     of the table offends, the check case. `rows` is a function of the table that returns the
     offending rows, for an expectation that relates rows to each other, as the steel share
     against its maximum does: `bk.expect.no_rows(above_maximum, by="excess")`. `by` names the
     measure whose absolute value is the distance.
   - `at_most(bound)`, `at_least(bound)`, `between(low, high)`, each with `on=` (the measure) and
     `warn_within=`; the distance is how far the value lies outside.
   - One default for `on=` and `by=`, for both kinds: the table's only measure. With several
     measures, `on=` is required, and `by=` left out means that nothing ranks the rows.
   The proposal had `no_rows`, `at_most` and `between`; `at_least` is added because non-negativity
   is the trigger, and the function because the decided example needs it. Bounds are mostly for
   Blicks: a check already returns only what offends.
4. **Round-off against real violations: one expectation, two bounds.** `warn_within=1e-9` makes a
   row whose distance is at most that a warning and one beyond it a failure:
   `bk.expect.no_rows(by="relative", warn_within=1e-9)` on a check,
   `bk.expect.at_least(0, warn_within=1e-9)` on a Blick. Two checks at two levels would compute
   the same large table twice and report every real violation twice. It is not called `tolerance`,
   which on a Blick is the comparison's, relative to the panel scale. It is absolute, in the units
   of the measure; a check that wants it relative returns a normalised measure, since only its
   code knows the scale.
5. **Levels**, after Storybook's accessibility tests: `off` (not evaluated; a check does not run),
   `warn` (reported, never changes the exit code), `error` (the default). `level=` on the check or
   Blick, else on its group (`bk.group(..., level=)`), else `level` in `[tool.blicket]`. A group
   named in several modules takes the first level given, with a warning, as for its title. A
   project that adopts checks sets `level = "warn"` and raises single checks.
6. **Result.** `met`, `warning`, `failed` or `error`: `warning` when rows offend and the level is
   `warn`, or all of them lie within `warn_within`; `failed` when a row offends beyond that at
   level `error`; `error` when the expectation cannot be evaluated (its function raises or returns
   no table, `on=` or `by=` names no measure of the table), with the message. An expectation on a
   table without rows is met.
7. **Status.** The outcome stands beside the status; there is no status `failed` and none `off`.
   A Blick whose expectation failed, or could not be evaluated, built its table, is `ok`, is drawn
   and is compared with the baseline as any Blick: an expectation never removes a chart, and
   "status `error`" keeps meaning "no table". A check is `ok` (it ran), `skipped` (`bk.Skip`, as
   for Blicks, or its level is `off`, with that as the reason) or `error` (it raised or returned
   no table). An outcome `error` counts as an error of the build: exit 2.
8. **A check's table** is the offending rows. Its rules are a Blick's with these differences: a
   dimension may hold nulls (the union of several arrays' dimensions; rows stay unique, nulls
   counting as equal); any number of measures, no plot; an empty table, with or without columns,
   is the normal case, no warning, and writes no file. `None` stays an error, since a forgotten
   `return` would pass. The rows are stored worst first (by distance, then in the order of the
   dimensions, nulls last, so the file is the same on a rerun), at most 100,000 of them, the
   builder's limit; the viewer shows the first 2,000, as for any table. The outcome counts all of
   them, so it says enough without the table.
9. **Exit codes.** A failed expectation makes `build` and `check` exit 1; errors still exit 2 and
   win; `dev` and `diff` exit 0. `check` gets `--exit-zero-on-changes`, Chromatic's flag: flagged
   Blicks then do not make it exit 1, so that 1 means a failed expectation only. Without it a CI
   that tolerates 1 for changes, as remind-mfa's, could not fail on a check; remind-mfa's CI adds
   the flag and fails on any code but 0. This is the first failure that is no error: the
   architecture's principle "a human decides, CI only reports" keeps holding for changes, and an
   expectation is a human's decision made ahead.
10. **Comparison.** The results are ordered met < warning < failed. Against the baseline's outcome
    of the same expectation, one not met now is `broken` when it is worse and `still failing`
    otherwise; one met now that was not met there is `fixed`. Not met now without an outcome of
    the same expectation in the baseline (the unit or the expectation is new or was changed, off,
    skipped or in error there) is `new`. Not met in the baseline and without an outcome now (the
    unit or the expectation is gone, off, skipped or in error) is `dropped`, so that silencing a
    failing check shows. Whether it is the same expectation is read from its record in the two
    manifests. The transitions do not flag a Blick and do not change the exit code. Checks are
    matched by id and alias among checks, as Blicks among Blicks; their tables are not compared.
11. **Manifest.** `spec` 0.3, so that an older viewer refuses a build instead of showing failed
    checks as clean. The expectation and the declared level are part of the definition and of the
    build id, as is the outcome; the expectation in words and the resolved level are blicket's
    derivations and stay out of the id, as the controls do. Checks are a list `checks` beside
    `blicks`, over one base entry, their tables `checks/<id>.parquet`. blicket and its viewer keep
    reading spec 0.2, where every new field has its default, so a store keeps its baselines; their
    expectations read as `new`.
12. **One id namespace.** A check and a Blick cannot share an id or claim each other's as an
    alias, so a report line names one thing. Checks live in the Blick modules (`blicks` globs),
    share their groups, and take `aliases=`.

## Surfaces

### Library API

```python
import functools

import polars as pl

import blicket as bk

bk.group("validation", title="Validation", level="warn")      # level= is new


def above_maximum(table: pl.DataFrame) -> pl.DataFrame:       # the Blick's table
    share = table.filter(Series="Share in production")
    maximum = table.filter(Series="Maximum share").select("Time", "Region", maximum="value")
    return (
        share.join(maximum, on=["Time", "Region"])
        .with_columns(excess=pl.col("value") - pl.col("maximum"))
        .filter(pl.col("excess") > 0)
    )


@bk.blick(
    title="Secondary steel share against the REMIND inputs",
    plot=bk.plots.line(x="Time", y="value", color="Source", linetype="Series"),
    expect=bk.expect.no_rows(above_maximum, by="excess"),
    level="error",                                            # optional, overrides the group
)
def remind_secondary_steel_share(run): ...


@bk.blick(plot=..., expect=bk.expect.between(0, 1))           # on the table's only measure
def end_use_split(run): ...


@bk.check(title="Flows are not negative", expect=bk.expect.no_rows(by="relative", warn_within=1e-9))
def non_negative_flows(run):
    """Every flow of every model, relative to the largest flow or stock of its system."""
    return negative_cells(run)      # Model, System, Flow, Time, Region, …, value, relative


@bk.check                                                     # expect=bk.expect.no_rows()
def stock_balance(run):
    if not has_stocks(run):
        raise bk.Skip("the run has no stocks")
    return unbalanced_stocks(run)


for model in MODELS:                                          # the counterpart of bk.register
    bk.register_check(
        id=f"balance/{model}",
        title=f"Mass balance of {model}",
        transform=functools.partial(mass_balance, model=model),
    )
```

- `@bk.check` works bare and with options; `bk.register_check` requires `id` and `transform`.
  Options of both: `id`, `title`, `description` (default: the docstring), `tags`, `aliases`,
  `expect` (default `bk.expect.no_rows()`), `level`, `dims`, `measures`. The id defaults to
  `<group>/<function name>`, the title to the function name in words, as for Blicks.
- `@bk.blick` and `bk.register` gain `expect=` and `level=`; `bk.group` gains `level=`.
- `bk.expect` is a module, as `bk.plots` is. Its functions validate their arguments and raise
  `DefinitionError` with what to write instead, as the plot factories do: a bound that is no
  finite number, `low > high`, a negative `warn_within`, `rows` that is not a function of one
  argument, `warn_within` on `no_rows` without `by`.
- A `rows` function receives the unit's checked table as a polars frame (dimensions first,
  sorted) and returns what a transformation may return, under a check's table rules; the
  dimension columns it shares with the Blick's table give "where". The reports give its count of
  rows, not a share of the table's.
- New exports: `bk.check`, `bk.register_check`, `bk.expect`, `bk.Check`, `bk.CheckEntry`,
  `bk.Outcome`, `bk.Expectation`. Existing callers do not break: every new option is optional.
- Not added: a function that runs the checks on a loaded run (decision of Tobias).

### `[tool.blicket]`

```toml
[tool.blicket]
level = "warn"   # off, warn or error (default): what a failed expectation is, unless a group or unit says
```

A wrong value gets the message of the other keys: `level must be "off", "warn" or "error", got …`.

### CLI

```
blicket build RUN_PATH...                      exit 1 when an expectation failed (new), 2 on errors
blicket check RUN_PATH... [--exit-zero-on-changes] [--against …] [--push] [--json]
                                               exit 1 when a Blick is flagged or an expectation failed
blicket dev [RUN_PATH]...                      reports them, exits 0
blicket diff BASELINE CURRENT                  reports the transitions, exits 0
blicket list                                   lists the checks, expectations and levels
```

`blicket build`, and the first part of `check` and `dev`:

```console
$ blicket build runs/2026-10-23
run 2026-10-23 · profile baseline · blicks at 0a6b858 · loaded in 12 ms
12 Blicks: 12 built
5 checks: 4 ran · 1 skipped
expectations: 4 met · 1 warning · 1 failed
build 8e21b7c04f6a9d35 → .blicket/build/8e21b7c04f6a9d35

skipped
  the run has no stocks
    checks/stock_balance

expectations warned
  blicks/checks.py:12  check checks/non_negative_flows
    200,131 rows, all within 1e-09 (no rows, by relative)
    worst -3.2e-12 at Model=plastics, System=future, Flow=a => b, Region=EUR, Time=2050

expectations failed
  blicks/flows.py:41  Blick flows/end_use_split
    3 of 2,412 rows: value between 0 and 1
    worst 1.07 at Region=SSA, Time=2050, End Use=Packaging
$ echo $?
1
```

- The lines `N checks:` and `expectations:` appear only in a project that has checks or
  expectations; `N checks:` counts `ran`, `skipped` and `error`. The sections end with the most
  severe, as today: `skipped`, `warnings`, `expectations warned`, `expectations failed`, `errors`.
  A check in error, and an expectation that cannot be evaluated, are under `errors` with the
  Blicks.
- `check` adds, after `vs baseline:`, a line `expectations vs baseline: 1 broken · 1 new · 1 fixed
  · 2 still failing · 1 dropped` and, in the details, sections naming the units of each but
  `still failing`; the verdict line reads `flagged: 6 of 48 Blicks · failed: 1 expectation`. With
  `--exit-zero-on-changes` the exit code is 1 only for the second half.
- The Markdown step summary gains a table "Expectations" of those not met, fixed or dropped: unit,
  result, rows, worst, where, against the baseline. Without a baseline, the summary lists the
  expectations not met under the line that says why there is none, so CI shows them on a first
  run too.
- `check --json` still prints the comparison file, whose expectation records hold the current
  outcomes; without a baseline it prints `null` and may exit 1, the outcomes then being in the
  manifest only (`build --json`), which the help says.
- `blicket list` shows a check in its group with `check` where a Blick has its plot type, and a
  level when it is not `error`; the summary counts `N checks`. It runs nothing, so it names an
  expectation without the measure a default would pick. `--json` gains `checks`.
- `--help` of `build` and `check` state the exit codes; the module docstring and the README's
  exit code paragraph follow.

### Manifest and comparison file (spec 0.3)

```jsonc
// manifest.json
"config": {"tolerance": 1e-05, "level": "error"},
"groups": [{"name": "validation", "title": "Validation", "tags": [], "modules": [...], "level": "warn"}],
"blicks": [{
  "id": "flows/end_use_split", "status": "ok", ...,
  "definition": {..., "level": null,
    "expect": {"kind": "between", "on": null, "low": 0, "high": 1, "warn_within": null}},
  "level": "error",
  "outcome": {"result": "failed", "expectation": "value between 0 and 1",
              "evaluated": 2412, "offending": 3, "within": 0,
              "worst": 1.07, "where": {"Region": "SSA", "Time": 2050, "End Use": "Packaging"},
              "message": null}
}],
"checks": [{
  "id": "checks/non_negative_flows", "name": "checks/non_negative_flows", "aliases": [],
  "group": "checks", "module": "blicks.checks", "source": {"file": "blicks/checks.py", "line": 12},
  "definition": {"title": "Flows are not negative", "description": "…", "tags": [], "level": null,
    "expect": {"kind": "no_rows", "rows": null, "by": "relative", "warn_within": 1e-09},
    "dims": null, "measures": null},
  "level": "error", "status": "ok",
  "data": "checks/checks/non_negative_flows.parquet", "hash": "parquet-sha256:…",
  "rows": 100000, "columns": {"dimensions": [...], "measures": [...]},
  "outcome": {"result": "warning", "expectation": "no rows, by relative, a warning within 1e-09",
              "evaluated": null, "offending": 200131, "within": 200131,
              "worst": -3.2e-12, "where": {"Model": "plastics", "Flow": "a => b", ...},
              "message": null},
  "skipped": null, "problems": [], "timing_ms": 812.4
}]
```

- `definition.expect` is the expectation as declared, a `rows` function by its name.
  `outcome.expectation` is the expectation in words with the measure resolved, written by the
  build so that the reports and the viewer say the same. `evaluated` counts the rows a bound was
  applied to and is `null` for `no_rows`; `offending` those that offend, `within` those of them
  inside `warn_within`; `worst` is the value of the row with the largest distance, `null` when
  nothing ranks the rows; `where` the dimension values of that row without the null ones, or of
  the first offending row; `message` says why a result is `error`. `outcome` is `null` for a unit
  without an expectation, at level `off`, without a table, or skipped. A check's `rows` and
  `columns` describe the stored table; a check that is met has `data`, `hash` and `columns` null.
- Not in the build id, as for Blicks: a check's `timing_ms`, `module`, `source` and tracebacks;
  for both kinds the resolved `level` and `outcome.expectation`.
- `comparison.json`: each Blick gains `expectation`, `null` or `{"transition": "broken" | "new" |
  "fixed" | "still_failing" | "dropped" | null, "current": <outcome> | null, "baseline":
  <outcome> | null}`; a list `checks` holds the same per current check, and per baseline check
  whose expectation is dropped, with `id`, `name`, `matched` and `message` (why there is no
  outcome on a side).
- The store's `push` copies the tables the entries of both kinds name.

### Viewer

Flows and states:

1. **Sidebar.** Under the Blicks' groups, a section "Checks": the checks as one flat list in the
   manifest's order, since their groups are the Blicks' and would repeat as headings; each a link
   to its page with a badge, `failed` or `error` (error colour) or `warning`, none when met; a
   skipped check in italics as a skipped Blick. A Blick whose expectation is not met carries the
   same badge beside its flag badge. The one filter control of the header becomes a choice of
   "All", "Changed (N)" and "Not met (N)", the last over Blicks and checks whose expectation
   warned, failed or could not be evaluated; an option with N = 0 is not offered, and without
   either the control is absent, as today. The search covers checks. The foot counts the checks.
   The section is absent in a build without checks.
2. **Overview.** Above "Changed since the baseline", a section "Expectations": one line with the
   counts (`1 failed · 1 warning · 4 met`, and against the baseline `1 broken · 1 fixed`), then
   the units not met, the worst result first, each with its badge, its outcome sentence and its
   transition, linked to its page; the fixed and the dropped ones after them. All met: the line
   alone (`All 6 expectations met`). None defined: no section. The trouble line and the Problems
   section count checks in error with the Blicks, and a build with checks only does not say that
   it has no Blicks without naming the checks.
3. **A check's page** (`#/check/<id>`): breadcrumb, title, description, the meta line (id, rows,
   Parquet, CSV, where it is defined), the outcome strip (badge, the expectation in words, the
   outcome sentence, the transition against the baseline), then the table of the offending rows,
   worst first, with sortable columns. States: met (`No row offends: <expectation>`, no table),
   not met (the table; DataTable's note when it shows the first 2,000, and `100,000 of 200,131
   offending rows are stored` when the build cut it), outcome in error (the message, and the
   table), skipped (the reason, as on a Blick's page), error (the problems), no such check.
4. **A Blick's page.** Under the change strip, a strip with the outcome: badge, sentence
   (`3 of 2,412 rows: value between 0 and 1, worst 1.07 at Region: SSA, Time: 2050`), the
   transition, and "Show where", which sets the filters to the worst row through `whereState`, as
   the change strip's button does. Met: one muted line (`meets: value between 0 and 1`). An
   outcome in error: the message, the chart below it as ever. A preview card of a Blick whose
   expectation is not met carries the badge.
5. Narrow screens, keyboard, light and dark follow the existing components: the table scrolls in
   its box, the filter is one labelled control, badges have spoken labels.

## Approach

1. **`expect.py`.** The expectations as frozen values with two operations: their record for the
   manifest, and the evaluation of a table, which returns the offending rows ranked by distance
   with the counts, the worst and where. `Outcome` and the level's resolution (unit, group,
   config) sit with them. Property tests on the evaluation: bounds are inclusive, nulls never
   offend, `within` never exceeds `offending`, the worst has the largest distance, the order is
   total.
2. **Definitions and assembly.** `@bk.check` and `bk.register_check` go through the pipeline of
   `@bk.blick` (`_define`, the option checks, the module record, assembly with default ids, groups,
   duplicate ids and aliases across both kinds), parameterised by the kind, not copied. `Check`
   and `CheckEntry` share with `Blick` and `BlickEntry` a base that holds what they have in
   common. The registry holds checks beside Blicks; a module with checks only defines something;
   a project with checks and no Blick builds.
3. **Tables.** `tables.compute` gets the check's variant of the table rules (decision 8) and, for
   both kinds, the evaluation after the table is checked; an evaluation that fails leaves the
   table and gives the outcome `error`. The note "the table has no rows" stays for Blicks.
4. **Build.** `builder.write` runs the checks after the Blicks, writes `checks/<id>.parquet`, and
   records levels and outcomes; `manifest.py` gets `checks`, the config's level, spec 0.3 written
   and 0.2 read, and the id exclusions. `Manifest` offers the entries of both kinds as one
   sequence, used wherever forgetting a kind is a bug: `has_errors`, the statuses, the files
   `push` copies, why removed Blicks are not judged, the build summary.
5. **Comparison and guard.** `comparison.py` relates outcomes (decision 10) in `compare_builds`,
   for Blicks and checks; `check.py` becomes `guard.py`.
6. **Reports and CLI.** `report.py` renders outcomes once (a sentence per outcome, used by the
   build report, the check report, the Markdown and `list`); `cli.py` gets the exit code rule and
   `--exit-zero-on-changes`.
7. **Viewer.** Types in `lib/manifest.ts` and `lib/comparison.ts`, a manifest of spec 0.2
   normalised when it is read; a new `lib/expectations.ts` (its own badge type, counts, sentences,
   the units not met in order, the transitions' words) with tests; the sidebar's model in
   `lib/sidebar.ts` gains the checks section and the filter's third state;
   `pages/check/[...id].vue`; an outcome strip component used by both pages; the overview's
   section; `DataTable` without a plot mapping; `useBlickId` and the sidebar's "current item" made
   aware of the route.
8. **Example.** `examples/remind-mfa`: `blicks/checks.py` with `non_negative_flows` (all flows of
   the future and the historical system, the distance relative to the system's largest flow or
   stock, `no_rows(by="relative", warn_within=…)`) and `stock_balance` (the stock's change against
   inflow minus outflow); `expect=bk.expect.between(0, 1)` on `end_use_split` and
   `polymer_splits`. Built on a run in `/home/tobias/code/blicket/data_out/` if the example's
   environment can be set up from this worktree; the README says what the checks find.
9. **Docs.** README: a section "Expectations and checks" after "Building a run", and the exit
   codes, "Checking a run", the viewer paragraphs, `dev`, the manifest's description and the
   examples. `docs/concept.md`: the check as a core concept, "Checks" out of the deferred list,
   the CI policy for expectations, a dated decision. `docs/architecture.md`: amendments of
   2026-11-10 to principle 6, the Blick definition, the change detection (status and outcome), the
   build directory, the guard's exit codes and the viewer. `viewer/README.md`,
   `examples/remind-mfa/README.md`, `meson.build`.

## Affected areas

- Python: `expect.py` (new), `__init__.py`, `_validation.py`, `definitions.py`, `assembly.py`,
  `model.py`, `schema.py`, `tables.py`, `builder.py`, `manifest.py`, `config.py`, `comparison.py`,
  `check.py` → `guard.py`, `report.py`, `cli.py`, `store.py`, `dev.py` (imports), `errors.py`
  (kinds), `meson.build`.
- Viewer: `lib/manifest.ts`, `lib/comparison.ts`, `lib/expectations.ts` (new), `lib/sidebar.ts`,
  `lib/preview.ts`, `lib/roles.ts`, `components/BlickSidebar.vue`, `DataTable.vue`,
  `BlickPreview.vue`, an outcome strip (new), `pages/index.vue`, `pages/blick/[...id].vue`,
  `pages/check/[...id].vue` (new), `composables/useBlickId.ts`, `composables/useManifest.ts`.
- Docs and examples as in step 9; `tests/projects/minimal/expected-list.txt` only if `list`
  changes for a project without checks, which it should not.

## Testing

- Python, each surface as a user meets it, success and failure: definitions (`@bk.check` bare and
  with options, `register_check` in a loop, invalid options with their messages, an id or alias
  shared by a Blick and a check, levels inherited, a group's level given twice); the evaluation
  (property tests); tables (nulls in a check's dimensions, repeated rows, an empty table with and
  without columns, `None`, the order and the cut); builds through `bk.build` and the CLI on
  generated projects (a met, a warned and a failed expectation, `off`, `bk.Skip`, a check that
  raises, a `rows` function that raises with the Blick's table kept; exit codes 0, 1 and 2 of
  `build` and `check`, with and without `--exit-zero-on-changes`; `dev` reporting and going on);
  the manifest (spec, a 0.2 manifest read, the id changing with the expectation and the outcome,
  not with the timings or the wording, the same id on a rerun); the comparison (each transition,
  a changed expectation, skipped on a side, matched by alias, a 0.2 baseline); the reports' text,
  the Markdown with and without baseline, `list` and its JSON; `push` copying the checks' tables;
  the config key.
- Viewer: vitest for `lib/expectations.ts` and the sidebar's model; typecheck and lint; the app
  run on a generated project and on the example, every state of the four flows looked at, in both
  colour modes and on a narrow window.
- The example builds on a real run, and its outcomes are in the plan's outcome section.

## Out of scope

- Running checks on a loaded run without a build (decided).
- Comparing a check's table with the baseline's; flagging a Blick for a broken expectation.
- A breakdown of the offending rows per dimension value in the outcome; marking the offending
  rows in a Blick's chart or data tab; storing the rows a Blick's `rows` function returns.
- Checks or expectations on the builder's ad hoc Blicks.
- Porting remind-mfa's own checks and changing its CI, which happen in its repository.

## Decisions

Put to Tobias on 2026-11-10 and accepted on 2026-11-16 as proposed:

1. **Exit codes** (decision 9): a failed expectation exits 1, and `check --exit-zero-on-changes`
   keeps flagged Blicks from doing so. Exit 2, as an error, and a code of its own (3) were the
   alternatives.
2. **`warn_within` on one expectation** (decision 4), not two checks at two levels.
3. **`no_rows(function)`** (decision 3), not a vocabulary for bounds taken from rows.
4. **Names** (decision 1): `check` for the unit beside `blicket check`; `level` as the one word in
   `[tool.blicket]`, `bk.group` and the units; the results `met`, `warning`, `failed`.
5. **An expectation that cannot be evaluated keeps the Blick's chart** and is an error of the
   build (decisions 6 and 7).
6. **Five transitions**, `new` and `dropped` beside broken, fixed and still failing (decision 10).
7. **Spec 0.3 written, 0.2 still read** (decision 11), so stores keep their baselines.

## Review of the plan (2026-11-10)

An independent review against the code changed these points: the transitions (a warning that
became a failure read "still failing"; an expectation just added read "broken"; a silenced one
said nothing); an expectation that cannot be evaluated no longer costs the Blick its table; a
check's rows stay unique and are stored in a total order, up to 100,000 instead of the 1,000
worst, and a met check writes no file; `warn_within` on `no_rows` and the function as its
positional argument, `where=` being taken by the outcome; one default measure for both kinds; no
status `off`; 0.2 manifests stay readable and the derived fields leave the build id; the filter
is one control with three states, since the sidebar's header has no room for a second button; the
sections of the reports end with the most severe. It confirmed the outcome beside the status, one
outcome model, the levels, one id namespace, two lists over one base entry, and the rename of
`check.py`, which the export `bk.check` requires.

## Outcome

Built on 2026-11-16 as planned, on `dcfd796`, with the deviations and the decisions the plan left
open listed below, then revised the same day after three rounds of review; [Review round
1](#review-round-1), [Review round 2](#review-round-2) and [Review round 3](#review-round-3) say
what each changed, and the sections before them describe the result.

### What was built

- **Python.** The package `blicket/expect/`: its `__init__` is the vocabulary, `bk.expect`
  (`no_rows`, `at_most`, `at_least`, `between`, `Expectation`, `Outcome`); the private modules
  `_levels` (the levels and their resolution), `_outcome`, `_vocabulary` (the expectations, their
  records, words, measure and distance) and `_evaluation` hold the rest; `blicket._callables` checks
  a function's signature for both `_validation` and `no_rows`. `Unit` and `Entry` in `model.py` are
  the bases of `Blick`/`Check` and `BlickEntry`/`CheckEntry`; `entry()` is declared in `Unit` and
  implemented by each kind from a `Made` record of what the build made of it. Definitions
  (`@bk.check`, `bk.register_check`, `expect=`, `level=`, `bk.group(level=)`), the option checks and
  assembly take the kind as a parameter; one namespace of ids and aliases; group levels merge as
  titles do. `tables.py` checks a table against `_Rules` of either kind and evaluates the
  expectation after it (`_evaluated`, `_picked` for a `rows` function). The builder runs the checks
  after the Blicks and writes `checks/<id>.parquet`; the manifest is spec 0.3 with `checks`, the
  config's `level`, `entries`, `outcomes`, `results` and `failed_expectations`, and reads 0.2.
  `comparison.py` relates outcomes (`relate`, `ExpectationComparison`) on a base `UnitComparison` of
  `BlickComparison` and `CheckComparison`, so that `Comparison.units` and `expectations()` walk both
  kinds, and matches checks through one `_Counterparts` with the Blicks. `check.py` is `guard.py`.
  `report.py` says an outcome through `outcome_rows`, `outcome_sentence` and `outcome_worst` in
  every report; `cli.py` has the exit-code rule and `--exit-zero-on-changes`; the `Registry` holds
  the project's level, which `discover` reads once, and resolves a unit's (`level_of`).
- **Viewer.** Types for spec 0.3 in `lib/manifest.ts`, with `normalized` for 0.2 tagging every
  entry with its `kind`, and `units`; `lib/comparison.ts`, and `useComparison` with a map of the
  checks beside the Blicks'; `lib/expectations.ts` (badges, counts, sentences, the numbers in
  them, the overview's section, the transitions in words, the check page's notes) used by the
  sidebar, the overview and both pages; `lib/sidebar.ts` with the Checks section, the three-state
  filter (`filterOptions`) and the foot; `UnitPage` as the frame of both pages, `OutcomeBadge`,
  `OutcomeStrip`, `pages/check/[...id].vue`; the overview's section "Expectations"; the strip with
  "Show worst row" on a Blick's page; the badge on a card; `DataTable` without a plot mapping;
  `useBlickId` and `useCheckId` by route; `/checks` in the dev proxy.
- **Example.** `examples/remind-mfa/blicks/checks.py` with `non_negative_flows` and
  `stock_balance`; `between(0, 1)` on `end_use_split` and `polymer_splits`; the project at
  `level = "warn"`, the flows' check at `error`.
- **Docs.** README (section "Expectations and checks", exit codes, `list`, the build directory,
  the viewer, the comparison file and transitions, `check`, `dev`, the examples),
  `docs/concept.md` (the check as a core concept, the CI policy for expectations, decisions of
  2026-11-16), `docs/architecture.md` (amendments of 2026-11-16), `viewer/README.md`,
  `examples/remind-mfa/README.md`.

### Deviations from the plan, and decisions where it was silent

- The amendments of the architecture are dated 2026-11-16, the day the feature was built, not
  2026-11-10.
- The comparison's `message`, why a side has no outcome or that the expectation changed, is part of
  the expectation record of both kinds, not a field of the check entry only, so that a Blick's
  dropped or new expectation says why too. Every unit of a comparison, `BlickComparison` and
  `CheckComparison`, has `id`, `name`, `matched`, `expectation` and `message`, the cause of a unit
  in error, and for a Blick also why it has no table or was not compared.
- An outcome `error` counts as no outcome for the transitions: failed before and unevaluable now is
  `dropped`, and the error itself is reported as an error of the build. When the expectation
  changed and there is an outcome now, `baseline` is `null` (the baseline's outcome is of another
  expectation); without one now, `baseline` is the outcome the baseline had, so a dropped one says
  what was dropped.
- `evaluated` counts the rows with a value, since a bound is not applied to a null.
- With `no_rows(by=...)`, a row whose measure is null offends, is not within `warn_within`, and
  ranks last.
- One shape of sentence for all outcomes: `3 of 2,412 rows offend: expected value between 0 and
  1`, and for rows within the bound `200,131 rows offend, all within warn_within: expected no
  rows, by relative, a warning within 1e-09`. The plan's `all within 1e-09 (no rows, by
  relative)` needs the bound's number, which the outcome does not hold; the expectation in words
  says it. The worst row is a second line in the text (`worst -3.2e-12 at ...`, `first at ...`
  when nothing ranks the rows) and part of the sentence in the viewer (`..., worst 1.07 at Region:
  SSA`). A met outcome reads `no row offends: expected ...`; one that cannot be evaluated `cannot
  evaluate <expectation>: <message>`.
- `expectations:` counts `N cannot be evaluated` for outcomes that cannot be evaluated, and says
  `none evaluated` when units declare expectations but none was evaluated (all off or skipped).
- A check at level `off` is skipped with the reason `its level is off`.
- A check whose expectation cannot be evaluated stores its table as it returned it, in the order of
  its dimensions, cut at 100,000, so its page shows the message and the table. A met check has
  `rows` 0 beside `data`, `hash` and `columns` null.
- A check's schema lists a dimension's values without null; a column of nulls only, as an empty
  pandas frame converts, is a string dimension in a check's table.
- A `rows` function's result is checked under a check's table rules with the roles inferred; an
  exception it raises, `bk.Skip` included, or one raised while its result is converted or checked,
  becomes the outcome's message with where it was raised, without a traceback, since an outcome has
  no field for one. On a Blick the rows it picks are counted and the Blick stores its own table; a
  check stores them as its table, since they are what offends.
- `list` shows `expect: <words>` as declared and, for a unit with an expectation, `level: <level>`
  when it is not `error`, as cells after the plot type, and a group's own level in its heading.
- The warning of a module without definitions, and the notes that a file's Blicks are missing,
  name checks when the project defines some (`defines no Blicks or checks; add @bk.blick or
  @bk.check, ...`, `the Blicks and checks in this file are missing`), and keep the base commit's
  words otherwise. `NothingToBuild` says `no Blick or check can be built` in a project with checks,
  `no Blick can be built` otherwise.
- Reports: the details of `check` and `diff` end with `expectations fixed`, `dropped`, `new`,
  `broken`, then `errors`, each line `<kind> <name>  <result now>, was <result then>; <message>`.
  The Markdown table is `#### expectations`, lower case as the other headings, with the columns
  Blick or check, result, rows, worst, where and, with a baseline, against the baseline; failed
  first, then warned, dropped and fixed.
- Viewer: the filter is a select labelled "Show"; an outcome's badge (`OutcomeBadge`) is outlined,
  with an icon of a checklist, a flag's filled, so the two stand apart beside each other. The
  trouble line says `N checks failed to run`, not `failed`, which is a result. A dropped unit in
  the overview gives the baseline's outcome as `in the baseline: ...`. The foot reads `6 of 12
  shown · 4 Blicks and 8 checks · ...`.
- Property tests of the evaluation run over seeded random tables, without a new dependency.
- `schema.py` is unchanged, and `errors.py` has no new kind: an outcome that cannot be evaluated is
  no `Problem`. `errors.py` has `MISSING_UNITS`, the wording of a file whose Blicks and checks are
  missing, `DefinitionError.checks` for an error of the API of checks, and `bk.Skip`'s docstring
  names checks and `rows` functions. Store listings now take builds of spec 0.2 as candidates,
  which reading 0.2 implies.
- Example: the plan's `Model` column is left out, since a plastics run is one model; the rows carry
  `System` and `Flow` or `Stock`. `warn_within` is `1e-13`, a little above flodym's 100 float
  epsilons (2.2e-14), whose exact value prints as `2.220446049250313e-14`. The levels follow the
  plan's advice for a project adopting checks.

### Review round 1

Seven reviewers read and ran the build of 2026-11-16 (architecture, plan fidelity, UI, CLI,
library API, code quality, a general review). Every finding they triaged was acted on; what was
chosen where the finding left a choice:

- **Bugs.** Any failure of converting or checking a `rows` function's result is an outcome `error`,
  not a crash. A named `on`/`by` is checked whenever the table has columns, rows or not, and at
  definition time against declared `dims=`/`measures=`. The overview lists a removed Blick whose
  expectation is dropped, lists a unit in error now and dropped once, keeps the section when the
  only expectation is gone, and keys units by kind and name. The Markdown summary of `check`, with
  and without a baseline, and `diff` list the errors of checks and the expectations that cannot be
  evaluated as they do for Blicks. Numbers: the reports print three significant digits, and more
  while rounding would move a value as far as its distance from the bound, so `1.0004` stays
  `1.0004` for `at most 1`; for that the outcome records the worst row's `distance` (a new field of
  `Outcome`, free while spec 0.3 is unreleased). The viewer writes numbers as its tables do
  (`formatValue`), with the digits that keep a value apart from its bound (`valueText`). The
  banner, the foot and the Problems list count and list expectations that cannot be evaluated
  (`1 check failed to run · 2 expectations cannot be evaluated`); the foot counts against all
  units (`6 of 12 shown · 4 Blicks and 8 checks · 3 with errors`); long ids break at 390 px.
  `@bk.check` with a non-callable argument is a `DefinitionError`. `expect=` takes only the four
  concrete expectations, so the base `Expectation` or a subclass is a definition error of the unit.
  Bounds and `warn_within` take any real number (`numbers.Real`, not `bool`), numpy's included,
  typed `SupportsFloat`. Plurals and a comment that named a timeline are fixed.
- **Structure.** The project's level lives on the `Registry`, which `discover` gives it;
  `cli.py` loads the config once. The viewer reaches a unit's comparison record one way
  (`useComparison` with `blicks` and `checks`), `expectationSection` walks both kinds of the
  comparison, `expectationsByName` is gone, and `units()` lists the entries. "Offends" (`Outcome.
  offends`, `offends` in the viewer: warning or failed) is told from "not met" (`isNotMet`, which
  adds `error` and carries a badge). `compare_builds` builds a Blick's comparison in
  `_blick_comparison` and relates the expectation once. `UnitPage` holds the frame both pages
  share; the level shows on both meta lines, only where the unit has an expectation and its level
  is not `error`. `bk.expect` is a package whose `__init__` exports only the vocabulary,
  `Expectation` and `Outcome`; `Level` is exported from `blicket`. The duplicates are merged: a
  check's default expectation is the field's default, `NoRows()`; `_CHECK_OPTIONS` derives from
  `CheckOptions`; one `_units_line` counts statuses with the verb; one filter rule in the
  sidebar; `storedNote` is `tableOrder` and `cutNote`; one signature check
  (`_callables.one_argument_problem`); `Manifest.failed_expectations`; each viewer entry carries
  its `kind`, set by `normalized` from the list it is in. `Unit.kind` and `is_rows_function` are
  gone, the nits fixed.
- **Wording.** An outcome says what offends and what was expected: `4 rows offend: expected no
  rows, by value`, `no row offends: expected value at least 0`, `no row offends, as no row has a
  value: ...` when no row had a value to bound, and `1 row offends, a warning at level warn: ...`
  when the level, not `warn_within`, made it a warning; README, viewer and tests use the same
  sentences. The terminal's count line says `N cannot be evaluated`, as the viewer does. A column
  named by `by=`/`on=` that is a dimension says so: `integer and string columns are dimensions;
  cast it to float, or name it in measures=`. Messages name checks where the kind is known to
  include them, the check's transformation `check`, and a check that returns no table gets the
  hint `a check returns the rows that offend as a table, an empty one when the property holds`; a
  project without checks prints what the base commit printed (`tests/projects/minimal/
  expected-list.txt` and the report tests guard it). `expect=` misuse says what to write (one
  expectation; wrap a function in `no_rows`; call `bk.expect.at_least`), and an expectation's
  `repr` is the call that makes it. `list` shows a level only beside an expectation. A
  checks-only project leaves out the Blicks line and says `vs baseline: no Blicks`. Help:
  `unless --exit-zero-on-changes`, "errors still exit 2", a line on levels and where they are set,
  the top-level help "A catalog of charts (Blicks) built from model runs, and of checks of the
  properties every run must have.", and the docstrings of `bk.check`, `bk.register_check`, the
  bounds and `bk.Skip`. Markdown cells turn line breaks into spaces; the first column is "Blick or
  check". The outcome strip's button is "Show worst row" and says "Worst row shown" after the
  click. An outcome's badge has a checklist icon, and in the overview the word "expectation"
  (`expectation failed`); its spoken text is always rendered. A check's table says how it is
  ordered (`Worst first, by relative.`, `In the order of their dimensions; nothing ranks the
  rows.`, and for an outcome `error` `The rows as the check returned them, in the order of their
  dimensions; the expectation was not applied.`); a skipped or dropped check's strip gives the
  baseline's outcome and leaves the reason to the alert. The overview's counts are two lines,
  `This run: ...` and `Against the baseline: ...`. `#/blick/<id of a check>` opens the check's page
  and the reverse; `#/check/` says "The address names no check."
- **Docs.** README: `warn_within` of `no_rows` needs `by`; a `rows` function's rows on a Blick and
  on a check; it is recorded by name, so editing its body or a `functools.partial` argument is no
  change of the expectation; `bk.Skip` in it is an outcome `error`; a `register_check` family and
  that it is registered at import time; a baseline of 0.2 makes every expectation not met `new`;
  dropped checks are listed only when the current build is complete; the manifest's new fields;
  the count line; the viewer's new states. An expectation that cannot be evaluated exits 2 at
  level `warn` too, only `off` avoids it: decision 7 (an outcome `error` is an error of the build)
  wins over decision 5 (`warn` makes a failure a warning), since a check that cannot say whether
  the property holds is broken, not failing. Rewraps without content were reverted, the long
  lines wrapped.
- **Not taken as worded.** C1 suggested `none expected, by value`; `offend: expected no rows`
  keeps one shape for `no_rows` and the bounds (`expected value at least 0`). A5 suggested up to 6
  significant digits with a fallback; the digits grow until rounding cannot reach the bound, which
  needs no fixed cap, and `repr` is the fallback. C2's met sentence names the empty case instead
  of a count, which a met outcome otherwise does not give. A3's fourth case is solved by keying
  units by kind and name rather than by a separate map. In C11 the icon goes on the outcome's badge
  only, so a flag's badge stays as it was.

### Review round 2

Six reviewers confirmed the items of round 1 resolved, the exit codes (39 scenarios) as the plan
has them, and a project without checks as at the base commit. What they found, and what was
chosen:

- **An empty table.** Round 1 checked a named `on`/`by` on a table without rows against the roles
  of its columns, which failed expectations that hold on a clean run: `no_rows(above_maximum,
  by="excess")`, whose `excess` is a column of what the function returns, and a check returning an
  untyped empty frame, whose columns are dimensions by their type. On a table without rows only
  the named column's presence among the columns is checked now, whatever its role; without a
  name the only measure is the default, and several are no error; a `rows` function is not called
  and nothing is checked against the input table.
- **Exit codes of `diff`.** `diff` exits 2 for errors of any kind, a check in error and an
  expectation that cannot be evaluated as a Blick in error, as the README says for every command
  but `dev`. `message` moved to `UnitComparison`, so that every unit of a comparison has it (in a
  Blick's JSON it now comes before `change`, free while spec 0.3 is unreleased);
  `UnitComparison.error` says whether the unit is in error, `Comparison.errors()` gives the units
  in error and `Comparison.unevaluable()` the outcomes that cannot be evaluated, and the `errors`
  sections of `diff`, `check` and the Markdown are built on them; `_unit_errors` is gone.
  `Comparison.has_errors` covers all of them, and `check`'s verdict "nothing flagged, but the build
  is incomplete" hangs on `incomplete` alone, so that a check in error does not read as an
  incomplete build.
- **Viewer.** `UnitPage` shows the warnings of a unit that is not in error, before the skip reason
  or the page's body, so a met check, which has no table, shows them too. The foot says `1 Blick`.
  A check's table says how it is ordered only while no column is sorted. The redirect between
  `#/blick/` and `#/check/` keeps the query. The comparison's record of a unit is looked up in
  maps made once (`relatedBy`); `troubles` takes the checks and uses `units()`; a Blick's
  `expectation` is required, `null` in a comparison of 0.2, which `useComparison` normalises.
- **Messages.** A dimension named by `by=` in a `rows` function's result says `cast it to float in
  the rows function`, since `measures=` does not reach that table; an error of a `rows` function,
  raised or in reading its result, keeps its first line. A `Decimal` bound is taken; a bound beyond
  a float's range is a `DefinitionError`. `repr` works for the base `Expectation` and any subclass
  (`Expectation()`, `Mine(by='value')`); misuse says `got Mine(), which bk.expect does not make`
  and, for a class, `not the class Expectation`. A file lost on a `DefinitionError` of the API of
  checks (`@bk.check`, `bk.expect`) says its Blicks and checks are missing, and `NothingToBuild`
  then names checks (`Registry.with_checks`). A line break in a dimension value is a space in the
  terminal's `worst ... at ...` line; the top movers' line prints as at the base commit. `diff`
  and the Markdown say `no Blicks` for a project of checks only, as `check` does.
- **Docs.** The README's family snippet has its imports; `help(bk.expect.no_rows)` says what a
  raising `rows` function gives and that it is not called on an empty table, `help(bk.Skip)` that
  it skips nothing there. The README says what an empty table is checked for, that `diff` exits 2
  for every error, and the comparison file's `message` of a check. The paragraph of the viewer's
  README on the dev server keeps its wrapping with `/checks/` added, one line of 108 columns.
- **Beyond the plan.** `Outcome.distance`, the distance of the worst row, is a field the plan did
  not have, added in round 1 so that a value is printed with the digits that keep it apart from
  its bound; it is in the manifest and so in the build id. The foot's `1 Blick` changes the viewer
  of a project with exactly one Blick and no checks, which said `1 Blicks` at the base commit.

### Review round 3

The reviewers found the items of round 2 fixed; this round tidied what was left:

- A signaling NaN as a bound or `warn_within`, `Decimal("sNaN")`, is the usual `DefinitionError`
  instead of a raw `ValueError`.
- Every `DefinitionError` of the API of checks has a case, with its own message, in the test of a
  file lost on a check.
- Docstrings: the CLI module's says that `dev` exits 0 whatever the build holds and `diff` 0
  whatever the changes and transitions are, 2 for errors of any kind; `bk.expect`, `no_rows` and the
  bounds state the rule for a table without rows. `help(bk.blick)` and `help(bk.register)` list no
  options, so they gained no mention of `expect=` and `level=`.
- Documents: the README says that `check` without a baseline exits 0 unless an expectation of level
  `error` failed (1) or the build has errors (2), and the architecture's amendment that the first
  `check` of a profile exits 0 only then; that the trouble line and the Problems list cover checks
  and expectations that cannot be evaluated; that with a `rows` function, or on a table without
  columns, nothing is looked up on an empty table; that `incomplete` holds back dropped checks too.
  The base text of the architecture's Guard paragraph and of the README's paragraph on `diff`'s
  exit codes and the comparison file keep their wrapping, which round 2 had changed; the additions
  follow on lines of their own.

### Verification

- `uv run pytest`: 994 passed after review round 3 (971 after round 1, 934 after the first build,
  749 before). New:
  `tests/test_expect.py` (the vocabulary and its messages, words and records, and the evaluation of
  40 seeded random tables at two levels against six expectations: inclusive bounds, nulls never
  offending, `within <= offending`, the worst first with the largest distance, the same rows in any
  input order, the result from rows, level and bound), `tests/test_checks.py` (definitions, levels,
  one namespace, the check's table rules, builds, the manifest, ids, push),
  `tests/test_transitions.py` (each transition through two builds, a changed expectation, skipped
  and off now, a removed check, an alias, a baseline of spec 0.2), `tests/test_expectations_cli.py`
  (the reports, Markdown with and without baseline, exit codes of `build` and `check` with and
  without `--exit-zero-on-changes`, `diff`, `list` and its JSON), and a `dev` test. `uv run ruff
  check .`, `uv run ruff format --check .`, `uv run ty check`: clean.
- Viewer: `pnpm test` 315 passed after review round 3, as after round 1, whose later cases were
  added to existing tests (308 after the first build; `tests/expectations.test.ts`, the sidebar's
  new cases); `pnpm typecheck`, `pnpm lint`: clean.
- Review round 1 added tests for each bug it fixed: a `rows` function whose result cannot be read
  (duplicate columns, a UInt64 beyond 2^63, `bk.Skip`), a misnamed measure on an empty table with
  columns, numpy scalars as bounds, the base `Expectation` and a subclass, the Markdown summary and
  `diff` with a raising check and an unevaluable expectation, `1.0004` against `at most 1`, the
  overview's four dropped cases, `tableOrder`, `cutNote` and the kind tags, the help of `build` and
  `check`.
- A generated demo project with every state (met, warned, failed, skipped, off and raising checks,
  a cut table, Blicks with a failed, a warned, a met and an unevaluable expectation, against a
  baseline with every transition) was served and looked at in a browser: the sidebar with the
  Checks section and the filter in its three states, the overview's section, the check page in each
  state, the Blick page's strip and its "Show where", a checks-only build, light and dark, a 390 px
  window and its drawer.
  After review round 1 the states it touched were looked at again in Chromium (Playwright), light,
  dark and 390 px: the overview's two count lines, wide badges and Problems with the expectations
  that cannot be evaluated, the foot under the filter "Not met", the check page cut, in error,
  skipped and dropped, met and fixed, the Blick page's "Show worst row" and "Worst row shown", the
  level on the meta line, the redirect of a wrong route, `#/check/`, and a long dropped id at
  390 px; no page scrolls sideways. The example's build of run 00 was served too: the overview, the
  stock balance's page with its table worst first by `relative`, and `end_use_split` with its met
  expectation. After review round 2: the warning of a met check, light and at 390 px in dark, the
  foot's `1 Blick and 2 checks` of a build with one Blick, the check table's order note gone once
  a column is sorted, and the redirect from `#/blick/<check>?Region=EUR` keeping its query.
- `pnpm generate` writes an `index.html` that says only "Redirecting..." with the dependencies of
  `dcfd796` already (Nitro 2.13.5's prerender with the base URL `./`); the viewer was generated with
  `NUXT_APP_BASE_URL=/` for the look, which `blicket serve` serves at the root.
- The example ran on the five plastics runs in `data_out/`, with remind-mfa at `710302d` from a
  local clone, outside the repository. Every build exits 0. `non_negative_flows`: 4,062 to 4,186
  negative cells, all round-off, the worst -3.9e-19 (run 00, -1.8e-9 t) to -1.1e-17 (run 34) of
  the system's scale.
  `stock_balance`: 330,104 to 332,884 cells with a gap, 78,370 to 78,559 of them beyond round-off,
  all in the future system's `use` stock, in the years 1953 to 2024 and none after, the worst 2.4e7
  t, 0.31% to 0.35% of the system's scale (7e9 to 7.8e9 t); every other stock balances within
  round-off. The shares meet `between(0, 1)`. The checks take about 20 ms and 250 ms of a build of
  about 1.7 s, the loader 0.6 to 0.8 s. `diff` of runs 28 and 34 says `expectations vs baseline: 2
  still failing` beside its value change.

### A self-contained example (2026-11-16, after the reviews)

Asked for after the wrap-up: `examples/coherence/`, a small project that shows the feature without
data from elsewhere. A made-up steel cycle in three regions; two runs as CSV files in the
repository, written by `make_runs.py`; three Blicks with `expect=` (`at_least` with `warn_within`
on a Sankey of the flows, `between` on the end-use split, `no_rows` with a `rows` function at level
`warn` on the recycling rate) and three checks (`@bk.check` for the stock balance, a family of two
with `bk.register_check`). `check runs/baseline` exits 0 with one warning; `check runs/changed`
exits 1 with two failed expectations, two warnings, three broken and one still failing. It has its
own uv environment and lock file as the other examples have, a README with the reports, and a
paragraph in the root README. `tests/test_examples.py` builds a copy of it and holds the outcomes
and the runs against `make_runs.py` (3 tests; `uv run pytest`: 997 passed). It was not part of the
three review rounds.

## Follow-ups

Kept here, as the other plans do.

- `pnpm generate` on `dcfd796` writes a viewer whose `index.html` is "Redirecting...", whatever
  this feature; the release workflow and the meson option build the viewer the same way.
- The stock balance of remind-mfa's future `use` stock in 1953 to 2024 is for remind-mfa's
  maintainers to judge; the example warns on it.
- remind-mfa's CI can add `--exit-zero-on-changes` and fail on any code but 0, and port its own
  checks; both happen in its repository.
- A failing expectation that is changed and met now has no transition, by the plan's rule that
  `fixed` needs the same expectation; a transition `changed` may be wanted.
- A check that failed to run and an expectation that cannot be evaluated both carry a badge
  `error`, told apart by style and spoken label only.
- An exception of a `rows` function keeps its location but not its traceback, so `-v` cannot show
  it.
- On a check's page with a long sentence, the outcome's badge stands on a line of its own.
- `BlickDefinition` and `CheckDefinition` share seven fields without a base (`UnitDefinition`);
  adding one changes the key order in `manifest.json`, free while spec 0.3 is unreleased.
- One badge component for `FlagBadge` and `OutcomeBadge`; one "Show where" button for the change
  and the outcome; one transition wording function for the terminal and Markdown.
- "Show where" and "Show worst row" replace the history entry, have no undo and do not mark the
  point in the chart.
- A check's table: a third sort state back to the stored order, the `by` column marked and kept in
  view, null cells told from empty strings; sorting 100,000 rows takes about 0.9 s; the table
  cache is unbounded.
- Reports have no cap (`and N more`) for many failing units and no cut for very long `where`
  strings.
- The evaluation sorts all offending rows before keeping 100,000 (20M offending rows: 3.4 s,
  4.2 GB); a top-k would bound it.
- A unit going from `met` to an outcome that cannot be evaluated has no transition; it is an error
  of the build.
- A warning that stays a warning reads `still failing`; the counts are best first in the terminal
  and worst first in the viewer.
- `no_rows` names its measure `by=`, the bounds `on=`; the wrong one is a plain `TypeError`.
- `blicket <command> --help | head` prints "unexpected BrokenPipeError", at the base commit too.
- `ty` does not flag unknown keyword names of `@bk.check` and `@bk.blick`; pyright does.
- The sidebar's filter is a select also in a project without checks, where the base commit had a
  one-click "Changed (N)" toggle.
- A sentence can mix notations in the viewer, `expected value at most 1e+06, worst 1.0004M`: the
  words come from Python, the number from `formatValue`.
- A Blick's `on=` could be checked against the plot's measure channels at definition time.
- `Expectation.distance` returns a polars expression, and is part of the public base class.
- The Markdown `errors` list is ordered differently with and without a baseline.
- The viewer's Vue components and composables have no automated tests (vitest covers `app/lib` and
  `app/plots` only), so the warnings in `UnitPage`, the redirect keeping the query, the table's
  order note and `readComparison`'s normalisation are checked in the browser only.
