# M0.7b The comparison in the viewer

Status: plan, 2026-10-24, revised the same day after an independent review that prototyped the
ghost layers with the real spec builders and tables and looked at them in headless Chrome. The
viewer's half of M0.7, split off so that each half has one implementer; builds on M0.7 (commit
`94c7889`). Companion to [architecture.md](../architecture.md), "Viewer (Nuxt)", "Plot type
contract" and walkthrough 1, and to [m1-viewer.md](m1-viewer.md); where this plan fills in or
changes a detail, it says so.

## Goal

A build directory that `check` has compared shows its verdict: the overview opens with the changed
Blicks ranked by magnitude and marks every Blick with its flag, with the schema summary across
Blicks; a Blick page says what changed, opens the controls where the change is largest when that is
a different view, and draws the baseline as a faded, broader ghost in the series' own colours
behind the current chart, with the baseline value in the tooltip where it differs. A build with
several comparisons offers the baseline to show. A build that was never compared looks as it does
today.

## The flows this task enables

1. **The overview after a check.** `blicket serve` on the example's build `c6317235ed070309` (run
   34, checked against run 31's build, among others): a comparison bar under the header says
   `Baseline: run 2026-10-24--01-25-31_plastics_SSP2_h12 · Blick code 604e20c · uncommitted changes
   · built 2026-10-24 20:02 UTC` as a selector over the baselines `compare/index.json` lists that
   are builds of other runs (four of its five), then `No baseline`, which shows the build as if it
   was never checked, and the counts `9 unchanged · 1 value` as text. A section `Changed since the
   baseline` opens the page: the flagged Blicks ranked as the terminal's movers are (magnitude,
   then name; `schema`, `new` and `error` after the `value` ones; removed Blicks as plain rows,
   since they have no page), each with its badge (`Δ 2.1% of scale`, `schema`, `new`, `removed`,
   `error`; the percent is the magnitude, with a title that says what it is). The groups
   follow as today, every card with its badge, unchanged ones without. A schema change shows a line
   per value under the counts, `Region 'ATLANTIS' appeared in 3 Blicks`.

2. **A changed Blick.** Its page shows a strip under the description: the flag badges, `largest
   change 2.1% of the chart's scale at Region SSA, Flow Primary, Time 2100, against run …` (the
   panel, the series and the x value with their dimensions, then the baseline), with a button `Show
   where` only when setting the filters there changes the view (on the example's one changed Blick
   nothing is filtered, so there is no button), the schema details when there are any, and for a
   Blick matched through an alias "compared with its former id". The chart draws the baseline as a
   faded, broader ghost in the series' own colours behind the current marks, as remind-mfa's run
   comparison draws its reference run: wide solid lines at 0.3 opacity under the thin current lines
   of a line chart; for a stacked area the baseline's stack as faded areas, with the current run
   drawn as the thin boundary lines of its layers on top; for bars the baseline bars faded and
   wider behind the current ones. The switch's label `Compare with baseline` carries a faded wide
   line as the key. The tooltip shows `212M` where the sources agree and `−60.1M (baseline −48.1M)`
   where they differ. The switch is on by default and hidden on the data tab; an unchanged Blick
   has no switch and its strip says `unchanged against run …`. While the switch is on, two charts
   follow the chart in its panels, colours and legend, each with a title: the change, current
   minus baseline, in the Blick's unit, and the relative change as a share of the baseline's
   value, in percent (see the follow-up at the end).

3. **No comparison.** A build without `compare/index.json` shows no bar, no section, no badges
   and no strip. A Blick whose columns changed gets no ghost (the strip lists the columns).

4. **Development.** `pnpm dev` proxies `/compare` to `blicket serve` as it proxies the tables.

## Facts the plan rests on (checked 2026-10-24, the chart ones by prototype)

- `check` writes `compare/index.json` (a JSON list of baseline ids, the one checked last at the
  end) and, per baseline, `compare/<id>/comparison.json` with `baseline`/`current` (`BuildRef`: id,
  run, profile, `created_at`, `repository`, `incomplete`), `incomplete` (reasons), and `blicks`,
  each with `id`, `name`, `matched`, `change` (`flags` in a fixed order, `magnitude`,
  `columns_added`/ `columns_removed`, `values_added`/`values_removed`, `where`), `message`,
  `baseline_data` (the copied baseline table, for Blicks flagged `value` or `schema`) and
  `baseline_hash`. `serve` sends the JSON under `compare/` with `no-cache`. The example's build
  `c6317235ed070309` holds comparisons against five baselines, two of them against run 31 and two
  against run 28 at different commits, so the selector's labels need run, commit and time; its one
  changed Blick, `flows/production_by_source`, is a stacked area split by Region whose change is 2
  % of a 500M scale, about 4 px in a 180 px panel, so the ghost is judged on a synthetic baseline.
- A layer inside the top-level facet that filters on a `__source` field compiles without warnings
  and renders; a layer cannot have its own data inside a facet. A `line` mark with `stack:
  'zero'` traces the stack boundaries of an area, and its stack transform matches the areas'
  when grouped by `detail`. `xOffset` lines outlined bars up with the filled ones. A ghost layer
  can reference the sibling layer's `focus` param.
- The plan review prototyped ghosts: a thin dashed boundary in the series' colour lies inside the
  area of its own colour and a thin outline inside a same-coloured bar vanishes; series colours at
  0.4 opacity reach 1.4 to 2:1 against either surface on their own. Three of the example's four
  line charts colour twelve Regions past the eight slots and so already carry a `strokeDash`
  encoding, which a dashed ghost in series colour would collide with. Tobias chose the style of
  remind-mfa's run comparison instead (pull request 252: the reference run faded at 0.3 opacity
  and drawn wide, 6 px lines, behind the other run's thin lines; stacked areas of the reference
  kept as faded fills with the other run's layers as outlines on top; the legend's run key in
  secondary ink): a wide faded band is read by the offset of the thin current mark on it, not on
  its own, and it carries no dash. Stacked bars drawn without their colour encoding lose their
  stack order.
- The pivot tooltip lists a `<label> (baseline)` column when the baseline rows carry that series
  label; listing every series twice gives `production_by_polymer` 29 rows in a 180 px panel. A
  `calculate` per series after the pivot gives one entry per series, with the baseline named only
  where the formatted values differ (overridden by the Deviations). Charts of a single series take
  the early return in `prepare` and do not pivot. Bars have no pivot; their tooltip is per bar.
- `magnitude` in `layout.ts` only picks the axis number format; Vega's y domain covers every
  layer already. `highlighted` puts the legend condition on one layer; an opacity encoding
  overrides a mark's opacity. Domains, the facet sort, the panel count and the tooltip labels come
  from the current schema and table.
- Query keys with an underscore are the viewer's own and `controls.ts` ignores them; `update()`,
  the breadcrumb, the header link and the cards rebuild links without any extra key.
  Plain vitest runs `lib/` and `plots/` tests without Nuxt auto-imports; composables are not
  tested that way.

## Approach

### Reading the comparison

`lib/comparison.ts` types the file (the mirror of `comparison.py`, with a comment naming it) and
holds the pure functions: `ranked(blicks)` (the flagged Blicks as the terminal's movers: magnitude
to two significant digits descending, then name; `schema`, `new`, `removed` and `error` after the
`value` ones), `schemaSummary(comparison)` (per dimension value that appeared or vanished, the
number of Blicks; columns likewise), `whereState(state, where, schema, controls)` (the state that
shows the row: the filter dimensions' values parsed with `parseValue`, values the dimension lacks
skipped, splits kept; `null` when it equals the state; overridden by the Deviations) and
`whereText(where, state, ch)` (the panel, the series, the x value; overridden by the Deviations).
`pick` is not needed: the composable holds the choice.

`composables/useComparison.ts`, a singleton like `useManifest`: fetches `./compare/index.json` with
`cache: 'no-cache'` (a 404 is "no comparison", not an error), then each listed `comparison.json` on
its own (one damaged or pruned file is skipped, the others shown), and exposes `baselines` (the
comparisons by id in the index's order), `chosen` (the one checked last by default; choosing is
state of the composable, so it survives navigation without a query key) and the error of the index
when it is not a 404 (overridden by the Deviations). No `_against`, no `_ghost`.

### The overview

Under the header, when a comparison is shown: the baseline line (run, `blicks at <commit>`, built
time; worded as the Deviations say, a `USelectMenu` over the baselines when there are several,
labelled by run, short commit and time), the counts as text (`9 unchanged · 1 value`; the `removed
not judged` reasons when `incomplete`), and the schema summary lines. Then the section `Changed
since the baseline` with the ranked Blicks as cards (removed ones as plain rows), then the groups
as today. `BlickCard` takes the Blick's comparison as a prop and shows its badge (`value` with the
magnitude to two digits, `schema`, `new`, `error`). The search applies to both lists.

### The Blick page

- The strip: the badges, the sentence with `whereText`, the `Show where` button when `whereState`
  is not `null` (it calls `update`), the schema details (values and columns added or removed),
  `matched`, and the message for `error`; `unchanged against run …` for an unchanged Blick; for
  a Blick the comparison does not list (none, in practice), nothing.
- The switch `Compare with baseline` with a faded wide line as its key, shown on the chart tab when
  the Blick has `baseline_data` and its columns did not change; a local ref, on by default. The
  baseline rows come through `useTable` with `{ path: baseline_data, hash: baseline_hash }` and
  are filtered with the same `select` as the current ones.
- `BlickChart` gets a `baseline: Row[] | null` prop in its watch list and passes it to `render`.

### The plot type contract and the ghost

`PlotArgs.baseline: Row[] | null`: the baseline rows after the same filters, or `null`. This
folds the architecture's `renderComparison` into `render` (a plot type without a ghost ignores
the argument) and departs from the M1 review's note that the comparison would concatenate the
rows into `args.table`: a plot type unaware of `__source` would draw baseline rows as data. The
architecture gets the amendment. The built-ins, one rule (Tobias's choice, as remind-mfa's run
comparison draws its reference run): the baseline is faded (opacity 0.3) and broader, in the
series' own colours, solid, behind the current marks, which stay as they are:

- `prepare` appends the baseline rows with `__source` (`current` or `baseline`); the series label
  of a baseline row ends in ` (baseline)`; the panel label is computed over both sources, and so
  are the panel count and the tooltip labels (overridden by the Deviations). Every current layer
  filters on `current`.
- `line`: the ghost before the current lines: the same colour scale, `strokeWidth` 6, solid (no
  dash encoding, whatever the current lines carry), `strokeCap` round, opacity 0.3 by its own
  condition on the `focus` param (0.3 when selected or nothing is selected, 0.1 otherwise;
  overridden by the Deviations).
- `stacked_area`: the baseline's stack as faded areas (opacity 0.3, the same colour scale, stacked)
  and the current run on top as thin solid lines on the stacked y (`stack: 'zero'`, a `line` mark
  with `detail` on the colour field, `strokeWidth` 2; overridden by the Deviations), so the current
  stack's boundaries are read against the baseline's fills; without the ghost the areas are drawn
  as today.
- `bar` and `stacked_bar`: the baseline bars before the current ones at the same x and `xOffset`,
  faded (opacity 0.3) and wider (1.4 times the current bar's width), the stacked ones with the
  same colour and order encodings as the current bars.
- The legend key: the switch's label carries a short wide line in the first categorical colour,
  faded as the baseline is.
- Tooltips: after the pivot, one `calculate` per series renders `212M` or `−60.1M (baseline
  −48.1M)` (formatted values compared, so noise at 1e-16 stays hidden) with `blicketNumber`; a
  single-series chart, which does not pivot, gets its baseline value joined per x the same way;
  bars get `__baseline` attached to each current row by `prepare` and one more tooltip line
  (overridden by the Deviations).
- `magnitude`'s stack key includes `__source` when the baseline is present, so stacks do not
  double; the y domain needs nothing (overridden by the Deviations).

### Not in this task, decided here

- A baseline column in the data tab and CSV; thumbnails on the overview; a colour dimension with
  many values offered as a split and a plot type's veto of a split (M4's first non-faceting plot
  type); a filter by flag (the ranked section is the filter); the accept flow.

## Affected areas

- New: `viewer/app/lib/comparison.ts`, `viewer/app/composables/{useComparison,useTheme}.ts`,
  `viewer/app/components/{ComparisonBar,ChangeStrip,FlagBadges}.vue`,
  `viewer/tests/comparison.test.ts`.
- Changed: `viewer/app/pages/index.vue`, `viewer/app/pages/blick/[...id].vue`,
  `viewer/app/components/{BlickCard,BlickChart}.vue`, `viewer/app/plots/{types,layout,encodings,
  line,stacked_area,bar}.ts`, `viewer/nuxt.config.ts` (the `/compare` proxy),
  `viewer/tests/plots.test.ts`, `viewer/README.md`, `docs/architecture.md` (the contract
  amendment: `baseline` in `render`; the overview's "ranked by magnitude" as built),
  `docs/plans/m0-tasks.md` (M0.7b built; the "M0.7 start" note superseded), README (what the
  viewer shows after `check`).
- Python: nothing.

## Testing

- `lib/comparison.ts`: `ranked` (magnitude order, ties by name, the other flags after, removed
  included), `schemaSummary` (values and columns across Blicks), `whereState` (filters set from
  parsed values, splits kept, a missing value skipped, `null` when nothing changes), `whereText`.
- The specs, through the existing `run()` and asserting no Vega-Lite warnings: with `baseline`,
  each built-in's unit spec holds the ghost layer with the expected mark, filter, width and
  opacity and the series colour scale, the stacked area's current run as boundary lines, the
  current layers filter on `current`, the tooltip entry carries the baseline where it differs,
  the panel count covers both sources; without `baseline`, the specs are as today (the existing
  tests pass unchanged).
- `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm generate`; the Python suite unchanged.
- By hand, recorded here with screenshots in the scratchpad: the example's build
  `c6317235ed070309` served (the bar with the selector, the ranked section, the strip), and the
  ghost on a scratch build with a synthetic baseline for each of the four plot types, light and
  dark, 1280 and 390 px.

Checked by hand (2026-10-25, headless Chrome, the generated viewer under `blicket serve`;
screenshots in the session scratchpad, `m07b/shots/`, those of the review's rounds in
`m07b/shots/r1/` and `m07b/shots/r2/`): the example's build `c6317235ed070309` shows `Baseline: run
2026-10-24--01-25-31_plastics_SSP2_h12 · Blick code 604e20c · uncommitted changes · built
2026-10-24 20:02 UTC` as a selector over its five baselines, the one checked last first, with
wrapped descriptions at 390 px (`r2/E5-selector-390.png`). Choosing the baseline of the same run at
fe4d2dd turns `9 unchanged · 1 value` into `10 unchanged` and removes the ranked section
(`r2/selector-switched-to-unchanged.png`). The example ranks Production by source with a `value
0.021` badge, and its page's strip reads `largest change 0.021 of the chart's scale at Region SSA,
Flow Primary, Time 2100, against run 2026-10-24--01-25-31_plastics_SSP2_h12 · Blick code 604e20c ·
uncommitted changes` without a button; the ghost is invisible at that size, the tooltip names the
baseline where it differs (`4.7M (baseline 4.69M)` in LAM, 1991,
`r2/example-LAM-1991-tooltip.png`), and the export menu's links name
`flows__production_by_source_vs_baseline.png` and `.svg` (read from the page). A cold load draws
the chart once. A scratch copy of that build with a synthetic baseline (scaled tables for two line
charts, the stacked area, the stacked bars, a bar Blick and a line Blick with a line type alone
added over production_by_source's table, plus a schema, a column, a new, an error, a matched and a
removed Blick) shows: wide faded bands in the series' colours behind the thin lines, the changed
series' bands off their lines; the baseline stack as faded fills under the current layers' tops,
the Primary top running above its fill where the baseline is lower; faded, wider bars behind
grouped and stacked bars, centred on them, standing out where the baseline is taller; the legend in
full colour, its click fading the other series and their ghosts, for a colour and for a line type
alone (`r2/A1-linetype-legend-click.png`); tooltips such as `59.5k (baseline 47.6k)` and `50.7M
(baseline 66M)`; "Show where" setting `Parameter=landfill_rate`, the keyboard focus moving to the
Parameter control with its focus ring (`r2/focus-after-show-where.png`); `no baseline rows for this
selection` beside the switch for a Parameter value the baseline lacks; a long filter value fitting
390 px (`r2/E1-long-filter-390.png`); the warning for a missing baseline table wrapping its path at
390 px; the column change listed with `baseline not drawn: the columns differ` and no switch; the
error Blick's strip without a baseline; "compared with its former id"; the removed Blick as a plain
row; the search filtering both lists; the switch hidden on the data tab. In dark mode the ghost at
0.4 keeps the twin hues apart and the switch's key is the first series' colour (`r1/E7-*`). Light
and dark, 1280 and 390 px, without console errors. A build without `compare/` looks as before, with
the browser's own 404 line for `compare/index.json` in the console; a garbled index shows a warning
above the search, and a listed comparison that is missing is skipped. `pnpm dev` proxies
`/compare/`.

## Decided by Tobias on 2026-10-24

1. **The ghost is faded and broader, in the series' own colours**, as remind-mfa's run
   comparison draws its reference run (pull request 252), not dashed ink: wide faded lines
   behind the thin current lines; the baseline stack as faded areas with the current run's
   layer boundaries on top; faded, wider bars behind the current bars.
2. **The overview opens with "Changed since the baseline"**, the flagged Blicks ranked as the
   terminal's movers, and the groups follow with badges.
3. **The ghost is on by default** for a Blick with a baseline table, and absent for an unchanged
   one or one whose columns changed.

## Decisions taken here, not asked

- `baseline` is an argument of `render`, not a second method; the chosen baseline lives in the
  composable, not in the URL.
- Every comparison file is fetched to label the selector, each on its own.
- The baseline rows pass through the same filters as the current ones.

## Deviations

Recorded by the implementation, 2026-10-25, and completed after the review's rounds. The body
above predates these deviations and is overridden where they differ: the flows are edited in
place; elsewhere a sentence that a deviation overrides says so (the tooltip's `(baseline)` series
label and per-series calculates, `whereState` and `whereText`, what `useComparison` exposes, the
baseline line's wording, the ghost's opacity channel, `detail` on the colour field, the stack key
with `__source`).

- One mechanism carries the baseline into tooltips: `prepare` joins the baseline's value to each
  current row, and one `calculate` before the pivot writes the text (`212M`, or `−60.1M (baseline
  −48.1M)`) that the pivot spreads by series with `op: 'max'`, which keeps a text; no baseline
  series label, no `calculate` per series. The text is computed without a baseline too, so a
  tooltip entry is a field and a title, with no format type; this changes the tooltips' spec
  without a baseline and one assertion of the existing tests. A series only in the baseline is
  not in the tooltip; its ghost is drawn. Bars carry the baseline in their value line, as lines
  and areas do.
- The ghost fades through `strokeOpacity` (lines) or `fillOpacity` (areas, bars), since an
  `opacity` encoding fades the legend's symbols too; the current marks keep the highlight's
  opacity. The highlight's param sits on the layer that draws the legend's channel: the ghost for
  a colour (Vega-Lite draws a legend from the first layer with that channel), the current lines
  for a line type alone, which the ghost does not dash. The ghost fades to 0.4 on the dark
  surface, where twin hues dull at 0.3 (`GHOST` in `theme.ts`).
- The switch's key is the first categorical colour at the ghost's opacity, not `INK.secondary`:
  a grey bar was nearly invisible in dark mode. The colour mode the charts and the key are drawn
  in comes from one composable, `useTheme`.
- The stacked area's current layers are lines with the colour encoding, not `detail` on the
  colour field: the colour groups and stacks them alike, in the areas' order.
- Grouped ghost bars are `1.4 * bandwidth('xOffset')` wide, an expression: Vega-Lite centres a
  width relative to the band on the x band, which put the ghost off its bar in the group.
- `magnitude` takes the largest stack of each source, instead of a stack key with `__source`.
- `whereState(state, where, schema)` takes no `controls`: the state's filters are the dimensions
  shown one value at a time. `whereText` takes the `mapping`, not the channels, and names the
  filtered values first, each value with its dimension (`Parameter landfill_rate, Region EUR,
  Time 2100`), so the sentence says which view the row is in.
- The bar reads `Baseline: run … · Blick code 604e20c · uncommitted changes · built …`, as the
  header names the current build, with `incomplete` when the baseline build is; the selector
  lists the baseline checked last first, its options' descriptions wrap, and its accessible name
  carries the line. The strip ends with `against` and the same parts but the time, for changed
  and unchanged Blicks alike, and leaves it out for a Blick in error, which was not compared; the
  `value` badge's title says what the number is.
- The schema summary puts the values of a dimension found in as many Blicks on one line, the
  first five and how many more, a dimension's lines adjacent with the most Blicks first. The
  strip says `Parameter value 'incineration_rate' vanished`, and its columns line ends with
  `baseline not drawn: the columns differ`.
- `useComparison` returns the chosen `comparison`, its current Blicks by name (`blicks`) and
  whether it is `loading`. The chosen baseline lives in the composable only: a reload or a shared
  link shows the one checked last, a limitation left to the accept design.
- The chart waits for the comparisons and the baseline's table, so a cold load draws it once.
- The Blick page shows the switch's control bar when there are controls or a switch, a warning that
  wraps its path when the baseline's table cannot be read, `no baseline rows for this selection`
  beside the switch, and names exported images `…_vs_baseline` when they carry the ghost, whose key
  is outside the chart. "Show where" moves the keyboard focus to the first control. A Blick without
  a table leaves the comparison's message to its problem list.
- The flag badges are a component of their own, `FlagBadges.vue`, shared by the cards, the removed
  rows and the strip; `ControlBar` takes the switch in a slot, and its row of a dimension wraps,
  so a long filter value fits 390 px. `Repository` is a type of its own in `manifest.ts`.
- `--ui-info`, `--ui-warning` and `--ui-error` are darker in light mode for the whole app, alerts
  and badges: info and error the 700 shade (6.7 and 6.3:1 on the surface, 5.7 and 5.2:1 on a
  badge's tint, from 3.7 and 3.2:1), warning the 800 shade (6.7 and 5.7:1, from 1.9 and 1.7:1).

## Follow-up decided by Tobias on 2026-10-25

After the first look at the result (the "Checked by hand" record above predates this), three
asks, applied on the same day with one review round:

1. **The selector offered a build of the same run** (the example's build has a comparison against
   an earlier build of run 34, its own run). A run against itself is no baseline: such a
   comparison is not offered (`offered` in `lib/comparison.ts`), and the selector ends with `No
   baseline`, which turns the comparison off (`chosen` is `null`: no section, no badges, no
   strip, no switch, no ghost). The selector shows whenever a baseline is offered, also for one,
   and reads `Baseline: run …` closed (`none` for no baseline), with the commit and time in the
   options; with none offered the build looks as if it was never checked. `blicket check` still resolves
   the baseline as before, so it may compare a run with an earlier build of itself; the viewer
   skips that comparison.
2. **`value 0.021` was not understandable.** The magnitude is the largest change of a row (or a
   stack) relative to the scale of its panel, the largest value in it, not a relative change of
   the value. It is written as a percent of the scale to two significant digits, everywhere: the
   badge `Δ 2.1% of scale` with the title `largest change: 2.1% of the largest value in its
   panel`, the strip's `largest change 2.1% of the chart's scale at …`, the terminal's movers
   `flows/production_by_source 2.1% of scale (Flow=Primary, …)` and the Markdown table's column
   `largest change (of the chart's scale)` with cells `2.1%`. The ranking still uses two
   significant digits; `percent` in the viewer and `Change.percent` in `schema.py` mirror each other.
3. **Absolute and relative change charts under the main chart.** While "Compare with baseline"
   is on and the baseline has rows for the selection, two charts follow the chart: the change,
   current minus baseline, in the Blick's unit, and the relative change, that over the baseline's
   absolute value, in percent. Decided here: the rows of both tables are matched by their
   dimension values as `_diff.py` matches them (a row of one table only is compared with null,
   which counts as 0; a row carrying a value only one table has is kept with no change, so the
   panels and the x range are the main chart's; a value counts as present when a row of the
   selection carries it, so a sparse table under a filter can differ from the report's row-level
   verdict); when nothing of the selection can be compared the charts are left out and a muted
   sentence says so, asked of built-in types only; a baseline of at most `1e-9` of the largest value compared counts as 0, a
   zero test for the divisor, and the relative change against it is null; the marks follow the
   Blick's plot type (lines for `line` and `stacked_area`, never stacked; grouped bars for `bar`;
   for `stacked_bar` the change stacked, positives up and negatives down, and the relative change
   grouped); the same x encoding, colours, line types, panels, y toggle and legend with its
   highlight as the main chart, so the panels line up (the ghost lines are clipped to the plot,
   y axes have a label floor of 48 px, grouped bars pad half the inner padding outside, panel
   labels are cut to the panel, change bars keep their all-null panels, a stacked segment of
   zero height has no stroke); a title inside each chart (`Change against the baseline, current
   minus baseline`; `Relative change against the baseline, as a share of the baseline's value`),
   the y axes `change [unit]` and `relative change`; heights 200 and 140 against the main chart's
   320 and 180; a zero grid line in the tick ink; tooltips with the sign (`+1.32M`, `−10%`) and
   a dash for a null; exports named `…_change` and `…_relative_change`; nothing for a plot type
   without a browser half. The change charts are built through the same specification builders
   as the chart, with a `Quantity` (`measure`, `change`, `relative`) that names what y is.

Left out, to be asked for: a hint on a Blick page when no baseline is chosen; collapsing the
change charts on pages with many panels; the absolute change at `where` in the strip's sentence;
renaming the `value` flag in the counts (`1 value`), which is the vocabulary of the whole tool.
