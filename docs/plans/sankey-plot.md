# A Sankey plot type

Status: built 2026-11-02 on `2fe15f2`, quick feature loop with three review rounds, uncommitted;
the outcome, the deviations and the follow-ups are at the end. Item 4 of "Features blicket still
needs" in the remind-mfa consumer's `blicks/README.md`; its `flows/sankey` Blick is the spec and
must work as written.

## Goal

`bk.plots.sankey(source, target, value, color=None)`: `source` and `target` are dimensions,
`value` a measure, `color` an optional dimension. The viewer draws the rows the filters leave as a
Sankey diagram whose links are coloured by `color`; `diff` compares `value` per row. Flows may
loop: the consumer's table (`Time`, `Region`, `From`, `To`, `Stage`, `value`, every fifth year,
World first) has processes that are source and target at once, and recycling and reuse close
cycles (`End of life → Recycling → Production`), so the renderer is d3-sankey-diagram 0.9.4
(research §4.3), the first plot type that is not a Vega-Lite spec.

## Approach

**Python.** `src/blicket/plots/sankey.py`: `Sankey(BuiltinPlotType)`, name `sankey`, channels
`source`, `target` (dimension, required), `value` (measure, required), `color` (dimension). It
inherits `controls` (a filter per unbound dimension, so `Time` and `Region` are filters at the
Blick's `defaults`) and overrides `diff` with `compare(baseline, current, mapping["value"],
panels)`: per row against the largest link of its panel, as `line` does. `_base.py` stays as it
is. Registered in `plots/__init__.py` and `meson.build`. The Blick builder offers it on its own,
since `query.plot_types()` takes every built-in with one measure channel.

**Viewer, the chart.** `viewer/app/plots/sankey.ts` exports a `PlotType` whose `render` imports
d3-sankey-diagram dynamically (its own chunk, loaded only by a page that draws a Sankey) and draws
SVG into `el`; `BlickChart.vue` needs no change, since it only calls `render` and its cleanup.
A pure function turns the rows into one graph per panel (nodes from the display values of both
columns, so a process that is source and target is one node; a link per row, its `type` the colour
value, so several stages between two processes stay apart); rows with a null value are left out,
and so are negative values, which a caption under the diagram counts. Splits work as for the other
types: one diagram per panel in a grid with the panel label above, the link scale shared across
panels or each panel's own after `state.y` (the "Own y axis per panel" switch). Colours: the
colour dimension's values in display order take the `CATEGORICAL[theme]` slots, so a stage keeps
its colour across years; links without `color` take the first slot; node bars and labels in `INK`,
the diagram on the surface colour, redrawn on a theme switch like the other charts. A legend of
the colour values above the diagram, as the Vega charts place theirs. A tooltip on links (`From →
To`, colour value, value with unit; with a baseline also the baseline's value and the change) and
on nodes (in and out totals), in the look of the other charts' tooltips. Height from the
layout: about 480 px for one diagram, less per panel, tuned on the consumer's data. An export menu
at the top right like vega-embed's (SVG and PNG at twice the size, the same file name). Compact
(the overview's cards): 160 px, no labels, legend or export menu, tooltips kept (built: 204 px, see
the outcome).

**Viewer, the comparison.** The diagram does not draw the baseline: two layouts do not line up.
The change charts under it, while "Compare with baseline" is on, are horizontal bars, one per link
of the selection labelled `From → To`, coloured by `color`, largest absolute change (or relative
change) first, links without a change left out, through `change.ts` and `definePlot` like the
other types' change charts. `change.ts` takes the measure from `mapping.y ?? mapping.value`, one
line; `whereText` in `lib/comparison.ts` names `source` and `target` too.

**Builder.** `PLOT_LABELS` gets `sankey: 'Sankey'`, `CHANNEL_LABELS` `source` and `target`;
`defaults()` puts time on `x` only for a plot type with an `x` channel.

## Surfaces

- Library: `bk.plots.sankey(source="From", target="To", value="value", color="Stage")` returns a
  `PlotSpec`; a column bound twice, or a missing required channel, is the usual `DefinitionError`.
- Manifest: `{"type": "sankey", "mapping": {"source": …, "target": …, "value": …, "color": …}}`,
  no new field, spec unchanged.
- Viewer, Blick page: control bar (filters, split), the diagram, the change bars under it when
  compared; the data tab unchanged. Loading: "Loading the table…" as now, then the renderer chunk;
  empty selection: "No rows for this selection." as now; a selection whose values are all null or
  negative: the caption alone; a render error: the existing "The chart cannot be drawn" alert.
- Viewer, overview: compact cards as above. Builder: "Sankey" in the plot type list, channels
  source, target, colour.
- CLI: unchanged; `blicket list` shows `sankey` as the plot type.

## Overlap with the sibling worktrees

Scatter, axis scales and negative stacks branch off the same `main`. Shared files, each touched in
a few lines: `plots/__init__.py` (`_BUILTINS`, `__all__`), `meson.build`,
`viewer/app/plots/index.ts` (`PLOT_TYPES`), `change.ts` (the measure lookup, which scatter may
also generalise), `lib/comparison.ts` (`whereText`), `builder.vue`/`roles.ts` labels, and the
README's and architecture's lists of plot types. Nothing in `_base.py`, `_diff.py`, `layout.ts`
or `encodings.ts`.

## Tests

Python: channels and factory, spec errors, controls, `diff` per row and per panel, a generated
project whose Sankey Blick builds and whose manifest records the mapping, the builder offering
it. Viewer: the graph per panel (loop, shared node, null and negative values, colours by display
order), the layout of a graph with a cycle in node (d3-sankey-diagram's layout needs no DOM), the
change bars, `comparable` with a `value` mapping, the builder's defaults. By hand: the consumer's
`flows/sankey` on a plastics run in `data_out`, light and dark, panels, compared.

## Bundle cost

Measured with `pnpm generate` on `2fe15f2` and with the Sankey, in bytes; gzip is Python's
`gzip.compress(b, 9)` of each `.js` file of `.output/public/_nuxt`, summed.

| | files in `_nuxt` | `_nuxt` | JS | JS, gzip |
|---|---|---|---|---|
| before | 29 | 2,210,544 | 2,002,254 | 690,924 |
| after | 30 | 2,317,454 | 2,108,758 | 726,501 |

The new file is the Sankey chunk, 101,597 bytes, 34,510 gzipped: d3-sankey-diagram with its d3 v1
modules and @dagrejs/graphlib, the drawing (`sankey_diagram.ts`), the rules without the DOM
(`sankey_graph.ts`) and the SVG export (`svg_export.ts`). Only a page that draws a Sankey loads it:
a line chart's page fetches 26 chunks, the Sankey's 27. The other chunks grew by 4,907 bytes, 1,067
gzipped: the channels, the change bars, the header's and the held room's sizes and the plot type
(`sankey.ts`), and the builder's and the comparison's few lines; vega-tooltip came with vega-embed
already.

## Outcome

Built as planned, with these deviations, most of them from the three review rounds (architecture,
plan fidelity, UI in a browser, library API, code quality):

- **What is drawn.** Rows with a null or zero value draw no link (the consumer's table has many
  exact zeros, which would make zero-height nodes), and neither do values within 1e-9 of the
  panel's largest finite positive value (the consumer's ~46 values around -1e-11). Negative values,
  non-finite values and flows from a node to itself are left out and counted in a caption under the
  diagram; d3-sankey-diagram mislays a whole panel when a source node feeds itself. On a compact
  card the caption shows only when nothing can be drawn.
- **Modules.** `sankey.ts` (eager: channels, panel grid, heights, the change bars, the `render` that
  reserves the chart's height and imports the rest) and a lazy chunk of `sankey_diagram.ts` (DOM
  drawing), `sankey_graph.ts` (pure rules: graphs, caption, tooltips, label placement, ordering,
  loop fitting, ribbons) and `svg_export.ts` (an export menu in vega-embed's look, SVG and PNG at
  twice the size), with hand-written declarations in `d3.d.ts`. Tests in `viewer/tests/sankey.test.ts`
  and `sankey-flows.ts`; the change bars' tests stay in `plots.test.ts`.
- **Layout.** d3-sankey-diagram breaks cycles by a depth-first walk from the first source; in display
  order it drew the main production chain as one huge backward loop. `walkOrder` simulates the walk
  from each source and lays out the order that turns back the least flow (checked against the real
  layout). Forward links are drawn as sheared ribbons (two cubic Béziers), not the library's arcs,
  which cut thick, steep links into wedges; turned-back links keep the library's arcs, beneath the
  forward ones at a lower opacity. Loops are fitted into the panel horizontally (`overhang`, up to
  three narrowing passes, never past half the box) and rows of panels vertically (`fitRows`).
- **Size.** About 480 px alone and 320 px per panel before fitting; compact cards are 204 px, the
  height of the other cards with their axes, not 160. Below 61 px per layer of nodes (854 px for the
  consumer's 14 layers) the diagram keeps that width in a box that scrolls sideways, with a fade at
  its right edge, `role="region"` and a name; the page itself never scrolls sideways.
- **Labels.** Placed largest node first (`placeLabels`, pure `labelBox` geometry, measured once per
  line variant): beside the bar in two or three lines, then above or below, with a one-step repair;
  other nodes' bars are obstacles. Every node of the consumer's 2050/World, 2100/CAZ and 1950/World
  is labelled at 1400, 900 and 390 px.
- **Interaction.** Tooltips through vega-tooltip's `Handler` (vega-tooltip 1.1.0 is now a direct
  dependency), clamped into the window; on touch they open on a tap, not on a swipe. Hovering a node
  fades the links of its panel that do not touch it; clicking a legend entry fades the other colour
  values' links; entries without a flow in the selection are dimmed and inert. A unit line, "Link
  width: <unit>", sits under the legend and goes into exports. The accessible name says what the
  diagram shows and points to the Data tab.
- **Comparison.** `nothingToCompare` asks a Sankey whether some flow changed (`BuiltIn.changed`), so
  an unchanged selection says "nothing to compare in this selection" instead of drawing empty bars.
  `BuiltIn.drawsBaseline: false` keeps the Compare switch's faded swatch, the `_vs_baseline` file
  name and the cards' "baseline faded" off a Sankey; `lib/preview.ts` takes it as an argument. The
  change bars drop panels without a change, and links between the same two nodes are labelled with
  their colour value. `change.ts` finds the measure with `measureChannel` (`y` or `value`), and
  `changeArgs` writes the change into that channel.
- **Shared files.** Beyond the plan's list: one-word exports in `layout.ts` (`SPACING`,
  `dimension`, `splitDimensions`) and `encodings.ts` (`written`), `legendGrid` in `encodings.ts`
  and `seriesColors` and `FONT` in `theme.ts` shared with the Vega charts, `definePlot`'s cleanup
  removing vega-embed's classes (a Sankey drawn into the same element got a stray scrollbar),
  `query.py` naming all empty required channels in one refusal, and `builder.ts` putting time on a
  filter for a plot type without `x`.
- **Tests.** A test's project plot type was renamed from `sankey` to `chord`, since `sankey` is now
  a built-in.

Checked: `uv run pytest` 657 passed, ruff and ty clean; viewer `pnpm test` 227 passed in 15
files, typecheck and lint clean. By hand, in Chromium through Playwright: the consumer's
`flows/sankey`, through a stand-in loader for the older pickles in `data_out`, alone and compared
(two plastics runs of 2026-10-24), at 1400, 900 and 390 px, light and dark, split by Time and by
Region with a shared and an own scale, touch taps and swipes, the export, the overview card, the
builder's Sankey, and a scratch project with negative flows and self-loops.

## Follow-ups

- The "Own y axis per panel" switch scales the links of a Sankey; it could say "Own scale per
  panel" for one.
- Link the change bars and the diagram: hovering a bar marks its link, "Show where" marks the link
  that changed most; node tooltips with the comparison.
- Keep node positions stable across years and regions (the library ranks each selection afresh), and
  keep the scroll position across redraws.
- Cap the change bars to the largest N per panel on long selections; wrap their labels on phones.
- Contrast of thin links and of the slot colours on the dark surface; keyboard access to the legend
  (the Vega charts' legends lack it too).
- Label coverage in a split into many narrow panels: about a fifth of the nodes stay unlabelled
  (the tooltip still names them), a few more with an own scale per panel than with a shared one.
- Consolidate `BuiltIn`'s per-type hooks (`changed`, `drawsBaseline`, and scatter's `leftOut`) into
  the browser half's contract once the sibling branches have merged, so a project plot type can
  declare them; a `measure` channel on `BuiltinPlotType` instead of `Sankey.diff`'s override; a
  definition-time refusal of a project plot type named like a built-in.
- `defaults=` naming a dimension the plot binds is silently ignored, while `controls=` refuses it.
- The library's layout cost grows fast with dense graphs (a random 94-flow graph takes 10.8 s); the
  consumer's 47 flows take 15–150 ms per layout, two per panel with a shared scale.
