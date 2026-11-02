# Negative stacks in stacked_area and stacked_bar

Status: built, 2026-11-02, on commit `2fe15f2`, not committed; the outcome is at the end. Item 5 of "Features blicket still needs" in the
remind-mfa Blicks' README (`blicks/README.md` of the `blicket-replace-visualization` worktree):

> A `stacked_area` or `stacked_bar` whose layers hold negative values stacks them downwards from
> zero, so that `trade/imports_and_exports` shows imports above and exports below the axis.

The consumer: `trade/imports_and_exports`, `stacked_area(x=Time, y=value, color=Flow)`, split by
Region with `independent_y`, `order={Flow: ["Imports", "Exports"], Region: ["World"]}`. Imports
are ≥ 0, exports are negated, so ≤ 0; World holds the global sums, which trade balancing makes
equal, so World's net is 0 at every year. No other consumer Blick stacks negative values.

## What exists already

- **Viewer.** Both stacked types encode `y` with `stack: 'zero'`, and Vega's zero offset stacks
  positive and negative values apart per x: the imports above and the exports below, in the
  chart, the baseline's faded stack and the lines on top of it (checked by rendering the trade
  shape headless). `magnitude` already sizes the axis format by the two stacks apart. The change
  chart of a stacked area is lines, of a stacked bar gains up and losses down: both fine.
- **Python.** `compare(..., stacked_by=color)` already stacks positive and negative values apart
  (`_stacks`), and `docs/architecture.md` states the rule.

**The gap.** Vega's stack puts a value of exactly 0 on the positive side, and Vega-Lite imputes a
missing row of a stacked area as 0. A layer that is negative elsewhere then jumps to the running
top of the positive stack at that x and draws a wedge across the positive layers, as do the lines
on top in a comparison. With the consumer's order this happens to land at 0 (Vega stacks the last
display value first), but with `order={Flow: ["Exports", "Imports"]}`, or a third layer, it does
not (rendered: zero exports in one year wedge up to the top of the imports).

## Approach

**Viewer, `stacked_area.ts` only.** The area layers (the chart's areas, the baseline's faded
areas, the current lines on top) stack a computed field instead of `y`, made in the layer's
transforms: `impute` the measure as 0 for a missing x per layer and panel; `joinaggregate` the
least and largest value per layer and panel; `calculate` the stacked value: the measure, except
that a zero or missing value of a layer that is never positive in its panel and negative at least
once becomes `-Number.MIN_VALUE`, which Vega stacks on the negative side at no visible height.
The transforms run after the source filter, so each stack (source and panel) decides for itself.
The y encoding keeps its title, format and the hover rule its tooltips, which read the measure
itself. A single series, and stacked bars (a zero segment has no height wherever it lies, a
missing one no bar), stay as they are. A layer with values of both signs stacks each value on the
side of its sign, as today; drawing its positive and negative parts as separate bands is left for
later.

**Python: no code change.** The semantics of `diff` for a stacked type, now pinned by tests and
documented:

- **Height of a stack**: at each x of a panel, the larger of the sum of the positive values and
  the absolute sum of the negative ones: the end of the stack farthest from zero, as the chart
  draws it. Not their net, which balanced trade makes 0, and not their span. The panel's scale is
  the highest such height in either table, floored as for any panel.
- **What the sum compares**: the positive sums of the two tables, and the negative sums, each on
  its own; the larger of the two changes is the stack's change. So imports and exports growing
  alike count, though the net does not move; a layer that changes sign moves its amount from one
  stack to the other.
- **`where`**: the row that changed most; or, when one of a stack's two sums changed more than
  every row (by `_STACK_MARGIN`), that stack: its x and the other dimensions, not the colour. It
  does not say which of the two sums.

Tests in `tests/test_diff.py`, one block after the existing stack tests: a balanced mixed stack
measured against max(up, |down|); a change of the negative stack named as the stack; imports and
exports growing alike; a layer crossing zero; `where` in panels. Tests in
`viewer/tests/plots.test.ts`: the trade shape stacks imports up and exports down from 0 in either
display order (stack start and end of the rows), zeros and missing values of a never-positive
layer at the running negative sum, a layer negative in one panel and positive in another, the
baseline's areas and the lines on top the same, a mixed layer by sign, stacked bars down, no
Vega-Lite warnings.

## Surfaces

- **Library API**: none changes; `bk.plots.stacked_area` and `stacked_bar` take negative values
  as they do now. Docstrings of `BuiltinPlotType` and `compare` say what the height and the sums
  are. Example: `bk.plots.stacked_area(x="Time", y="value", color="Flow")` over a table whose
  `Exports` rows are negative.
- **Viewer (UI)**: the stacked area of `trade/imports_and_exports`: imports above, exports below
  the axis in every panel, in either order of `Flow`, with or without a baseline; a zero or
  missing year of exports pinches the exports area to 0 instead of drawing a wedge into the
  imports. Tooltips, legend highlight and change charts unchanged.
- **Docs**: `README.md` "Defining Blicks" gets a paragraph on stacked types with negative values
  (layers in display order, positives up, negatives down, zeros and gaps of a never-positive layer
  with the negatives, mixed layers by sign) and the comparison's scale and sums; the "Comparing
  two builds" scale sentence names the two stacks. `docs/architecture.md`: an amendment line under
  the built-ins on the viewer's stacking.

## Overlap with the sibling worktrees

Axis scales touch `encodings.ts` (`yAxis`, `overX`) and maybe `stacked_area.ts`'s call of
`overX`: this change leaves both alone and adds its transforms in a separate helper in
`stacked_area.ts`. Scatter and Sankey add plot types to `index.ts`, the README's "Defining Blicks"
and the test files: the README paragraph here is self-contained, and the new tests are one block
in each test file.

## Outcome

Built as planned, after two review rounds (architecture, plan fidelity, code quality, and a UI
review that ran a toy project in the real viewer, light and dark, desktop and narrow). The
general reviewer (omp with qwen3.6) was skipped: no Ollama on this machine.

- `viewer/app/plots/stacked_area.ts`: `stackBySign(args, ch, y)` returns the three transforms
  and the y encoding on `__stacked`; the chart's areas, the baseline's faded areas and the current
  lines on top are written with them. `viewer/app/plots/encodings.ts` only exports `datum`.
- Tests: eight viewer tests in the `negative stacks` block of `viewer/tests/plots.test.ts`, seven
  in `tests/test_diff.py` (one parametrised over three cases); each fix-specific viewer test fails
  with the transforms stripped, each Python one with the stacks measured by their net.

Deviations from the plan:

- The "Comparing two builds" sentence is unchanged: "the highest stack of the panel" stays true,
  and the new paragraph in "Defining Blicks" says what the height is.
- The README also says how the display order lies across zero (the first layer outermost on both
  sides, the last next to zero) and that a layer with values of both signs is best put last,
  where it crosses zero without crossing the others; a test pins that.
- The `__panel` field is in the groupby for the impute's sake: Vega-Lite adds the facet field to
  a `joinaggregate` but not to an explicit `impute`, and without it a year that another panel
  has is not filled in. "Negative at least once" keeps an all-zero layer at 0, since
  `-Number.MIN_VALUE` in the y domain makes `nice` add a tick below 0 on a small scale.
- A null or NaN value of a coloured stacked area now pinches its band to 0 instead of breaking
  it; Vega already stacked it as 0, so no position moves.
- Vega-Lite already imputed a missing x in the stacked lines on top, so they keep the impute: a
  year a layer lacks runs along its running sum (0 for the layer next to zero), as its area does
  without a baseline, now on its own side instead of at the top of the positive stack.

Possible next features:

- A layer with values of both signs, not last in order, still shears across the layers between
  its two sides at a sign change; drawing its positive and negative parts as separate bands, with
  an interpolated zero crossing, would fix that.
- The measure chart's zero line is a plain gridline; where the baseline's faded areas meet at 0
  it is faint. Drawing it in the tick ink for a stacked chart whose domain crosses 0, as the
  change charts do, needs `yAxis` in `encodings.ts` (after the axis-scales merge).
- Totals as a line on stacks with negative items (the architecture's list of later extensions).
- The change charts of a negated layer read inverted for its meaning (exports growing show as a
  negative change); correct for signed values, but a Blick author may want a note.
