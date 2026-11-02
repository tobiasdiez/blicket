# Axis scales

Status: built, 2026-11-02, on commit `2fe15f2`, after two review rounds; the outcome is at the end.
Item 2 of "Features blicket still needs" in the remind-mfa Blicks' README (worktree
`remind-mfa/yabby`, `blicks/README.md`); its wording and its usages in `blicks/drivers.py` and
`blicks/stocks.py` are the spec.

## Goal

`bk.plots.line(..., x_scale="log")` and `y_scale="log"` draw that axis logarithmic, and the scale
is part of the plot definition in the manifest. `drivers/gdp_per_capita` and `drivers/gdp`
(`line(x=TIME, y=VALUE, color=REGION, y_scale="log")`) work as written. The mechanism belongs to
no plot type: any plot type whose channel is a continuous axis declares that the channel takes a
scale, and the spec, the manifest, the viewer and the change charts handle it the same way, so
that `scatter` (built in a sibling worktree, `x_scale="log"` in `stocks.py`) plugs in at the
merge by declaring its channels and passing its two arguments on.

## Approach

- **Python.** `Scale = Literal["linear", "log"]`. `Channel` gains `scales: tuple[Scale, ...] = ()`,
  the scales a Blick can give the channel's axis; empty for a channel that is no continuous axis
  (colour, line type, a bar's band). `PlotSpec` gains `scales: Mapping[str, Scale]`, keyed by
  channel and checked on construction: the channel exists, is bound, and takes that scale.
  `linear`, every axis's default, is dropped, so `y_scale="linear"` and no argument give the same
  spec and the same build id. `make_spec(plot_type, scales={"x": x_scale, "y": y_scale}, **mapping)`
  leaves out the `None`s as it does for channels. `line` declares `scales=("linear", "log")` on x
  and y and takes `x_scale=None, y_scale=None`; the bar and stacked types declare none (a log axis
  under bars or stacks has no zero to stand on).
- **Build.** `tables._check_plot` adds one generic rule: a `log` scale on a dimension channel
  needs an integer dimension; on a string, boolean, date or datetime column it is an error of the
  Blick (`x_scale='log' needs numbers on x, but 'Region' is a string column`). A measure is a
  float, so a log scale on it always passes.
- **Manifest.** `PlotDefinition` gains `scales: dict[str, Scale] = {}`; spec stays 0.2 (the field
  has a default, as `skipped` did). A manifest without the field reads as all linear.
- **Viewer.** `PlotDefinition.scales?` in `lib/manifest.ts`; `chartPropsOf` and `BlickChart` pass
  it on as `PlotArgs.scales?` (absent: every axis linear). One helper in `plots/encodings.ts`,
  `scaled(encoding, args, channel)`, puts `scale.type: 'log'` (and the axis settings a log axis
  needs to read well) on an encoding; `overX` applies it to x and y, so line, and stacked area and
  bars if they ever declare a scale, get it there, and scatter calls it on its own encodings.
  `frame`'s data preparation (`prepare` in `plots/layout.ts`) does the masking below for every
  plot type that goes through `frame`.

## Decisions

- **Values at or below zero on a log axis count as missing.** `prepare` sets them to null in the
  data handed to Vega, so the line breaks there, no point is drawn, the axis domain covers the
  positive values, and the hover tooltip shows the en dash of a missing value (the data tab keeps
  the number). Vega-Lite 6.5 itself filters only null, NaN and infinite values, and Vega maps 0 on
  a log scale to −∞, so the viewer has to do it. The chart says so below itself, in one muted
  line, when the selection has such rows: `3 values at or below zero are not drawn on the
  logarithmic y axis.` (counting the current and the baseline rows shown; not on compact cards,
  not under the change charts). The build neither fails nor warns: the data is valid, and a
  warning would repeat on every build of a Blick whose history starts at zero.
- **The change charts keep the x scale and draw the change on a linear y.** A change or a
  relative change is signed and crosses zero, which no log axis shows; the x axis keeps its scale
  so that the change charts line up with the chart above. `changeArgs` in `plots/change.ts` drops
  `y` from the scales, the channel it already replaces with the change; nothing per plot type.
- **The comparison does not depend on the scale.** `diff` keeps measuring a row's change against
  the largest value of its panel, in the measure's units, whatever the axis shows; its signature
  stays. With the default tolerance of 1e-5 a change of a small series under a log axis is still
  flagged; only the ranking of top movers reads differently from what the log chart suggests.
- **The builder offers no scale.** Its charts stay linear; a scale toggle there is a next feature.

## Surfaces

- Library API: `bk.plots.line(x, y, color=None, linetype=None, x_scale=None, y_scale=None)`,
  `bk.Channel(name, kind, required=False, doc="", scales=())`, `bk.PlotSpec(plot_type, mapping,
  scales)`. Errors, all `DefinitionError` at definition time:
  - `line(x="t", y="v", y_scale="sqrt")` → `y_scale='sqrt' is no scale of y in plot type line;
    it takes linear or log`
  - `PlotSpec(BAR, {"x": "t", "y": "v"}, {"y": "log"})` → `channel 'y' of plot type bar takes no
    scale`
  - `PlotSpec(LINE, {...}, {"z": "log"})` → the unknown-channel message with its "did you mean".
- Manifest: `"plot": {"type": "line", "mapping": {"x": "Time", "y": "value", "color": "Region"},
  "scales": {"y": "log"}}`; `{}` when every axis is linear.
- Viewer: the Blick page and the overview cards draw the log axis; the note under the chart; the
  change charts as above. The builder is unchanged.

## Affected files

`src/blicket/plots/_base.py`, `line.py`, `__init__.py` (export `Scale`), `src/blicket/__init__.py`
if it re-exports plot names, `model.py`, `tables.py`; `viewer/app/lib/manifest.ts`,
`composables/useBlickChart.ts`, `components/BlickChart.vue`, `plots/types.ts`, `encodings.ts`,
`layout.ts`, `change.ts`; tests in `tests/test_plots.py`, `test_tables.py` or `test_build.py`,
`viewer/tests/plots.test.ts`; docs in `README.md` (Defining Blicks), `docs/architecture.md`
(channels as data, the browser half's arguments), `viewer/README.md` (the plots paragraph).

## Overlap with the sibling worktrees

- **Scatter** builds its own `x_scale` and `y_scale`. At the merge, scatter's channels declare
  `scales=("linear", "log")`, its factory passes `scales={"x": x_scale, "y": y_scale}` to
  `make_spec`, its browser half calls `scaled` on its x and y and draws through `frame`, and
  whatever it built of its own for scales goes. Shared files: `_base.py`, `plots/__init__.py`,
  `encodings.ts`, `index.ts`.
- **Negative stacks** touches the stacked types' diff and y encodings (`_diff.py`, `yAxis` and
  `magnitude` in the viewer). This change leaves `yAxis` and `_diff.py` alone; it wraps `yAxis`'s
  result in `overX`.
- **Sankey** adds a plot type, an entry in `PLOT_TYPES` and maybe `PlotArgs` fields; `scales` is
  optional in `PlotArgs` so its args need no change.

## Outcome

Built as planned. All checks pass: pytest (665), ruff, ty, and in `viewer/` vitest (204),
typecheck and lint. There were three review rounds. The first two had architecture, plan
fidelity, library API, UI and code quality reviewers; the third was one combined reviewer, who
found nothing substantive. The optional omp reviewer did not run, since there is no Ollama on the
machine.

### Deviations from the plan

- **`Channel.scales` lists the scales besides `linear`.**
  - Every channel with a scale takes `linear`, its default, which `PlotSpec` then drops. So `line`
    declares `scales=("log",)`, and a declaration cannot leave out the default.
  - `Channel.__post_init__` checks the declaration and stores it without `linear` and without
    repeats. It accepts a list, and rejects a plain string (the `("log")` slip) and unknown names
    with a `DefinitionError`. Before this check, a project plot type with `scales=("sqrt",)`
    crashed the build with an internal error.
- **`linear` on an unbound channel is accepted.** It has the same effect as passing no argument;
  any other scale on a channel without a column is an error.
- **`make_spec(plot_type, *, scales=None, **mapping)`.** `scales` is keyword-only, so it never
  reads as a channel.
- **The messages lead with the factory argument and end with a fix:**
  - `y_scale='sqrt' is no scale of y in plot type line; it takes 'linear' or 'log'`
  - `x_scale='Log' is no scale of x in plot type line; did you mean 'log'? it takes 'linear' or 'log'`
  - `y_scale='log': channel 'y' of plot type bar takes no scale; drop the scale`
  - `size_scale='log' needs a column on size; map size to a column or drop the scale`
  - The build error: `x_scale='log' needs numbers on x, but 'region' is a string column; bind an
    integer dimension to x or drop x_scale`.

  The `<channel>_scale` convention is documented in the docstrings and `docs/architecture.md`.
- **Empty scales are left out of the manifest.** `PlotDefinition.scales` uses
  `Field(default={}, exclude_if=...)`, so a plot with linear axes dumps as it did and build ids
  stay as they were. The scatter worktree does the same.
- **The viewer's scale code is its own module, `viewer/app/plots/scales.ts`.** It holds
  `scaled`, `masked` and `belowZeroNote`. This shrinks the hunks in `encodings.ts` (one import, two
  calls in `overX`) and `layout.ts` (the masking call in `prepare`, and `plotHeight`, now exported
  beside `plotWidth`), which the sibling worktrees edit too.
- **A log axis needs more than `scale.type: 'log'`.** Rendering showed what it takes to read well:
  - `nice: false`, so narrow data fills the plot; niced to powers of ten, 100–101 sat flat at the
    bottom of 100–1000.
  - About one tick per 40 px, `ceil(extent / 40)` from `plotHeight`: 8 on a chart of its own, 5 in
    a panel, 4 on a card. A Vega `height` expression does not resolve inside facets, so the
    extent is an argument of `scaled`.
  - Grid lines at labelled ticks only.
  - Each label formatted by itself, with up to six significant digits. Otherwise the axis format,
    chosen for the largest value, writes the top tick as `1e+3`, and a narrow axis repeats `100`.
    An integer x keeps its own `d` format and ticks, so years read `1950`, not `2k`.
  - " (log scale)" in the axis title, and " (log)" in panels, where the longer title would push
    the shared x axis down. This tells the log chart apart from the linear change charts under
    it.
- **The note counts the current rows only.** Counting the baseline rows too doubled the number
  when "Compare with baseline" was switched on, for the same visible breaks.
- **Tooltips keep the baseline's real value.** A current 1500 against a baseline 0 reads
  `1.5k (baseline 0)`. A row's own masked value still shows the en dash.
- **Smaller changes.**
  - `tooltipHead` names the dimension directly, so the tooltip header is not "Time (log scale)".
  - `Channel.scales` in `viewer/app/lib/builder.ts` is optional, since the builder does not read
    it.

### Not done, and possible next features

- **A `chartPropsOf` test.** No test checks that `chartPropsOf` passes the scales through. It
  imports through Nuxt's `~` alias, which the plain vitest config lacks.
- **A scale toggle in the builder.**
- **A `symlog` scale for data that crosses zero.** In REMIND, CO2 emissions turn negative, and a
  log axis leaves out 280 values there. Showing such data needs a symmetric log scale, which
  Vega-Lite has.
- **A comparison in log space for log axes.** The ranking of top movers would then match what the
  chart shows; `diff` would need the scales.
- **The note in exported images.** It is HTML under the chart, so exported PNG and SVG files lack
  it.
- **Polish:**
  - Below about 1e-6, labels mix exponent and decimal styles.
  - A compact card's 4 ticks give GDP per capita only `1k` and `10k`.

### Merging with scatter

The scatter worktree (`compare/scatter-plot`) built a nearly identical mechanism of its own:
- `Scale` and `SCALES` in `plots/_scales.py`;
- `PlotSpec.scales` with `linear` dropped;
- `PlotDefinition.scales` with `exclude_if`;
- a `viewer/app/plots/scales.ts` with `scaled(encoding, args, channel)`;
- `changeArgs` dropping `y`.

At the merge:
- Keep this branch's `Channel.scales` declarations and their check: scatter declares
  `scales=("log",)` on x and y.
- Keep the keyword-only `make_spec(..., scales=...)`: scatter calls it positionally today.
- Take one home for `Scale`.
- Merge the two `scales.ts`. Scatter's three-argument `scaled` calls work here and only skip the
  tick density rule. Pass `plotWidth`/`plotHeight` as the extent.
