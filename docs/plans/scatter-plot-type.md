# The scatter plot type

Status: built, 2026-11-02, uncommitted on `2fe15f2`; the outcome is at the end. Planned in quick
mode of the feature loop (no plan review). Item 3 of "Features
blicket still needs" in the remind-mfa consumer's `blicks/README.md` (worktree `yabby`, branch
`blicket-replace-visualization`); its wording and its four Blicks are the spec:
`stocks/in_use_per_capita_over_gdp`, `stocks/extrapolation_per_capita_over_gdp`,
`stocks/regression_function` and `methods/blending_functions`.

## Goal

`bk.plots.scatter(x, y, color=None, linetype=None, along=None, x_scale=None, y_scale=None)`: a
chart of one measure against another. `x` and `y` are measures; `color` and `linetype` split the
points into series; with `along` naming a dimension, the points of each series are connected in
the display order of that dimension's values (a trajectory over time, a curve over grid points).
Rows with a null `x` or `y` are left out of the chart. `x_scale`/`y_scale="log"` draw that axis
logarithmic. `diff` compares `y` per row as `line` does. The consumer's Blicks work as written.

## Approach

**Library.** `src/blicket/plots/scatter.py`: `Scatter(BuiltinPlotType)` with the channels `x`
(measure, required), `y` (measure, required), `color`, `linetype`, `along` (dimensions), and the
factory `scatter(...)`. The table check already handles two measures, since it takes a column's
role from the kind of the channel it is bound to: a float column on `x` or `y` is a measure, an
integer one gets the existing "counts as a dimension; add measures=" error. `controls` is the
built-ins' unchanged: `along` binds its dimension like any channel, so it gets no filter; every
other unbound dimension gets one. `blicket list` shows `scatter`; the Blick builder offers only
plot types with one measure channel (`query.plot_types`), so it does not offer scatter, as before.

**Diff.** `compare` in `_diff.py` today takes every column but `y` as a dimension, so the `x`
measure would become a join key. `BuiltinPlotType.diff` passes the other measure columns of the
mapping (`x` for scatter), which `compare` leaves out of the dimensions and does not compare; a
measure column that appeared, vanished or changed type is still a `schema` change, as every
column is. Changes of `x` alone are not measured: the spec says `y`, and in the consumer's Blicks
`x` (GDP per capita, a grid over it, fixed blend positions) does not move without `y` moving too.

**Scales**, built in a sibling worktree at the same time for `line`, kept in one small piece per
layer so the merge replaces it:
- Python, `src/blicket/plots/_scales.py`: `Scale = Literal["linear", "log"]` and
  `scales(**given) -> dict[str, Scale]`, which drops `None` and raises `DefinitionError` for any
  other value (`x_scale must be 'linear' or 'log', got 'logarithmic'`). `PlotSpec` gains
  `scales: Mapping[str, Scale]` (default empty), checked to name channels of the plot type.
- Manifest: `PlotDefinition.scales: dict[str, Scale] = {}`, e.g.
  `"plot": {"type": "scatter", "mapping": {...}, "scales": {"x": "log"}}`. Spec stays `0.2`: the
  field is optional. Being part of the definition, it is part of the build id.
- Viewer: `PlotDefinition.scales?` in `lib/manifest.ts`, `PlotArgs.scales` passed through
  `useBlickChart`/`BlickChart` (and the preview cards), and `viewer/app/plots/scales.ts`: the
  Vega-Lite `scale` of a channel (`{ type: 'log' }`) and the filter that leaves out rows a log
  axis cannot show (values ≤ 0), used by `scatter.ts` only.

**Viewer chart**, `viewer/app/plots/scatter.ts`, registered in `plots/index.ts`:
- x and y quantitative on the measure columns, `nice`, not forced to zero; titles: the x column's
  name, y as `yTitle` (the unit belongs to `y`). Number formats per axis from the largest value.
- Without `along`: filled points, one colour per `color` value, a shape per `linetype` value.
  With `along`: a line per series (`color` × `linetype`, dash per line type as in `line`),
  ordered by the position of the row's `along` value in display order (a Vega-Lite `order`
  encoding), no dots except the hovered one.
- Rows with a null (or non-finite) `x` or `y`, and on a log axis those ≤ 0, are filtered out
  before drawing; a line connects their neighbours.
- Hover: the nearest point (Vega-Lite `nearest`), a dot on it, a tooltip with the panel, the
  series, the `along` value, x, and y with the baseline's number where it differs, and the unit.
  Legend highlight as in `line`.
- Baseline: its points or lines drawn behind, faded and wider, in the series' colours, at the
  baseline's own x.
- Change charts: the change of y per row (as `changeRows` computes it) drawn as a scatter over
  the row's x, current x, the baseline's for a row only the baseline has, same x scale, same
  series and `along`. `change.ts` reads `mapping.y` instead of calling `channels()`, which needs
  `x` to be a dimension; `frame`/`prepare` in `layout.ts` take the series dimensions and the
  measure rather than requiring a dimension on `x`.
- `whereText` (comparison.ts) orders `along` with the series dimensions.
- The data table and its CSV export put the unit on the `y` measure only, not on `x`.

## Surfaces

- **Library API**: `bk.plots.scatter(...)` as above, exported in `bk.plots.__all__`.
  ```python
  @bk.blick(title="Stock over GDP", unit="t per person",
            plot=bk.plots.scatter(x="GDP per capita", y="value", color="Region",
                                  linetype="Period", along="Time", x_scale="log"))
  ```
  Errors (DefinitionError at import): missing `x`/`y`, a bad scale value, the same column on two
  channels; table errors at build: a non-float column on `x`/`y`, a column the table lacks.
- **Manifest**: `plot.scales` as above.
- **UI**: a Blick page draws the scatter with its controls (filters for unbound dimensions, splits
  as panels, shared or independent y); compared with a baseline, the ghost and the two change
  charts; the overview's preview card draws it compact. Empty: a filter that leaves no row with
  both x and y shows the Blick page's existing empty state. No new screens, no CLI change.

## Affected files

`src/blicket/plots/{scatter.py,_scales.py,_base.py,_diff.py,__init__.py}`, `model.py`
(`PlotDefinition`), `meson.build`; `viewer/app/plots/{scatter.ts,scales.ts,index.ts,layout.ts,
change.ts,types.ts}`, `lib/manifest.ts`, `lib/comparison.ts`, `lib/csv.ts`,
`components/{BlickChart.vue,DataTable.vue}`, `composables/useBlickChart.ts`, `lib/preview.ts`;
tests `test_plots.py`, `test_diff.py`, `test_build.py`, `test_query.py`,
`viewer/tests/plots.test.ts`; docs `README.md` ("Defining Blicks": a short list of the built-in
plot types and their channels, with scatter and the scales), `docs/architecture.md` (built-ins
list, channels may be several measures, `scales` in the definition).

## Overlap with the sibling worktrees

- axis-scales: `_scales.py`, `PlotSpec.scales`, `PlotDefinition.scales`, `plots/scales.ts`,
  `PlotArgs.scales` and its plumbing. Kept to those places; the merge keeps one of the two.
- sankey-plot: a new entry in `_BUILTINS`, `PLOT_TYPES`, `meson.build`, the README's plot type
  list and the architecture's built-ins; possibly `channels()`/`frame` in `layout.ts` and
  `compare`'s measure handling (its `value` is the one measure, so likely not).
- negative-stacks: `_diff.py` (stacks), not the lines this touches.

## Testing

Generated projects (tests/support.py): a scatter Blick with two measure columns builds, its
manifest records type, mapping and scales, `along` gets no filter and an unbound dimension does,
null x/y rows build; an integer column on `x` fails with the existing message; `diff` compares
`y`, ignores `x`'s values, and flags a vanished `x` column as `schema`; the builder does not offer
scatter. Viewer unit tests of `scatterSpec` (log scale, filter, order, ghost, change chart) and of
`changeRows`/`comparable` with a scatter mapping. Then the app: a generated project and the
consumer's Blicks on a plastics run in `data_out`, built with this worktree's blicket into the
scratchpad.

## Outcome (2026-11-02)

Built in one implementation pass and three review rounds (architecture, plan fidelity, library
API with a caller project, UI with the app running, code quality; the general reviewer, omp with
qwen3.6, was unavailable: no Ollama on this machine). Checks: 675 pytest, ruff, ty, 228 vitest,
typecheck, oxlint, all green. The consumer's four scatter Blicks build and draw on a plastics run
of `data_out` (yabby's own venv with this worktree's `src`, its import hook for the main checkout's
editable blicket removed, and stand-ins for the visualization classes the pickled runs reference);
its `drivers.py` and `flows.py` still fail to import, on `line(..., y_scale=)` and
`bk.plots.sankey`, which the sibling worktrees build. Where the code departs from the plan above,
the list is complete.

### Deviations

- **Scales take the axis-scales worktree's shapes.** `make_spec(plot_type, *, scales=None,
  **mapping)`; `PlotSpec` drops `linear` (so `x_scale="linear"` equals no argument) and requires a
  scale's channel to be bound; the error is theirs (`x_scale='logarithmic' is no scale of x in
  plot type scatter; it takes linear or log`); `_scales.py` holds only `Scale` and `SCALES`.
  `viewer/app/plots/scales.ts` is their `scales.ts` (`scaled`, `belowZero`, `logChannels`,
  `masked`) without their note helpers and with `belowZero`/`logChannels` exported. A log axis
  says "(log scale)" in its title ("(log)" in panels), ends at the data instead of powers of ten,
  labels powers and 2×/3× each in its own format, and draws grid lines at labelled ticks only.
- **Values ≤ 0 on a log axis** become null in `layout.ts prepare` (`masked`), as theirs; scatter's
  own filter leaves out rows whose x or y is not a finite number, per layer, since a filter on the
  whole unit drops a facet panel and the change charts then no longer line up.
- **`scales` is left out of the manifest when empty**, so the build id of a project without scales
  is unchanged (checked against a base build: same id).
- **One x domain** for the chart and its change charts: the x of the rows any of them draws, in
  either table (`PlotArgs.above` hands the chart's arguments to its change charts). Point charts
  get 10 px of scale padding. The log x axis keeps the linear axis's tick per 90 px; the sibling's
  tick per 40 px crowded the labels of a log x and dropped the powers of ten on 3+ decades.
- **Rows left out are said.** Under the chart: "2 of 138 rows are not drawn: x or y is missing."
  (", or a value is at or below zero on the logarithmic x axis."). `reasons()` in
  `plots/index.ts` owns the log reason for every built-in; a type's `leftOut` hook adds its own
  (scatter: x or y missing). When neither the chart nor its comparison has anything to draw, the
  page says "No row of this selection can be drawn; the data tab lists the rows." (the card:
  without the second half). Computed once in `useBlickChart`.
- **The unit is the unit of the measure on y** (`unitOf` in `lib/manifest.ts`): the data table
  and the CSV header put it on `y` only, on every measure for a plot that binds no `y`.
  `toCsv`/`downloadCsv`/`DataTable` take the mapping, hence the touch on `pages/builder.vue`.
- **Viewer details beyond the plan:** the tooltip shows the baseline's x where it differs, in the
  chart and the change charts; points past the colour slots get a shape per round of hues, as
  lines get a dash; date and datetime values read as `display()` writes them; shared helpers in
  `encodings.ts` (`xTicks`, `panelEntry`, `hoverDot`, `linetypeDetail`, `overBaseline`,
  `POINT_SIZE`) used by `line.ts` too, whose charts are pixel-identical to before.
- **`compare(..., *, measures=())`** is keyword-only; `README.md` got a "Plot types" subsection.

### At the merge with axis-scales

1. Python: delete `_scales.py` and its `meson.build` line, import `Scale` from `_base.py` in
   `scatter.py` and `plots/__init__.py`, drop `_check_scale` from `_base.py`, give scatter's `x`
   and `y` channels `scales=("log",)` as their `line.py` does, and rewrite the scale error asserts
   in `tests/test_plots.py` to their wording. `make_spec` is identical on both sides.
2. Viewer: take their `scales.ts` and re-export `belowZero` and `logChannels`; take their
   `layout.ts`, keeping `FrameChannels` and `prepare`'s signature; in `BlickChart.vue` keep the
   `note` prop fed by `useBlickChart` and drop their `belowZeroNote` call, its helpers and its
   test (`leftOutNote` covers values ≤ 0 on a log axis for every built-in, with other wording:
   their owner should agree); `nothingToDraw` gives a line chart the empty state too.
3. Keep scatter's x calling `scaled` without an extent, or limit the tick-per-40-px rule to y.
4. Docs: `README.md`'s plot type list gets `x_scale, y_scale` on `line`; the two rewrites of the
   same paragraph of `viewer/README.md` merge into one that says `useBlickChart` makes the note.
   Small textual conflicts in `types.ts`, `manifest.ts`, `change.ts`, `encodings.ts`
   (`tooltipHead`), `__init__.py`.

### Next

- Measure units per column (`Measure.unit` set by the build) instead of "the unit is y's": a
  scatter's x has a unit too, and the Sankey's `value` will.
- `diff` compares `y` only; a scatter whose x moved alone reads unchanged (documented). Measuring
  x too, against its own scale, is a small change in `compare` if a consumer needs it.
- A build-time warning for a scatter with no drawable row; a scale on a dimension channel through
  a direct `PlotSpec` is accepted and ignored until the merge brings per-channel scale
  declarations.
- Log axes spanning under a decade label unevenly (3 4 5 … 10 with 7–9 blank), and a single tick
  reads "46.4159k": both are the shared `scaled` label rule.
- Trajectories show no direction (no start or end marker); ghosts are not connected to their
  current points; more than eight colours plus a line type repeat hues, as in `line`.
- `docs/architecture.md`'s milestone list and `docs/plans/m0-tasks.md` still list scatter as
  upcoming.
