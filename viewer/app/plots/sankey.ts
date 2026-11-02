// The Sankey diagram: the rows the filters leave as flows between nodes, a node per value of the
// source and the target column, so that a value of both is one node, and a link per row in the
// colour of its colour value; a diagram per panel. This module holds what the plot types and the
// change charts need: the channels, the panels' grid, the change bars and whether a flow changed.
// The diagram is drawn by sankey_diagram.ts, which the first diagram loads with d3-sankey-diagram.
// The baseline is not drawn behind, since two layouts do not line up: its change is drawn as bars
// per link.
import type { TopLevelSpec } from 'vega-lite'
import type { Dimension } from '../lib/manifest'
import { display, largest, numberFormat, type Row } from '../lib/table'
import { CHANGE, changeRows, type Compared } from './change'
import { colorEncodings, field, focus, highlighted, legendGrid, shown, SHOWN, yTitle } from './encodings'
import { asNumber, combinations, dimension, labelOf, PADDING, PANEL, plain, SEPARATOR, SPACING, splitDimensions } from './layout'
import { config, INK, seriesColors } from './theme'
import type { ChangeBuilder, PlotArgs, PlotType } from './types'

// The height of a diagram's box, in px: alone, in a panel, and in a compact chart, where it is as
// high as the other charts' cards, whose plots are 160 px high with axes under them.
const HEIGHTS = { single: 480, panel: 320, compact: 204 }
// About the share of its box a diagram draws: the layout leaves room above and below the flows,
// which the drawing cuts.
const DRAWN = 0.75
const MIN_PANEL_WIDTH = 360 // px, which sets how many panels go in a row
const PANEL_FLOOR = 120 // px, the least width of a panel, also in a container without width
/** The room above a chart for its export menu, in px, as the other charts have it. */
export const MENU_ROOM = 36
/** The room above a panel's diagram for its label, in px. */
export const PANEL_LABEL = 24
/** The room between rows of panels, in px. */
export const ROW_GAP = SPACING + 8
/**
 * The header over the diagrams, in px: the baseline of the legend's title, the middle of its first
 * row of entries, the step of its rows and the room under the last; the line of the unit and its
 * baseline's height over the line's bottom; and the room under it all.
 */
export const HEADER = { title: 11, legendTop: 27, legendRow: 20, legendBottom: 6, unitLine: 16, unitBaseline: 4, gap: 12 }
// The change bars: the room of a link's label, the step of a bar, the least width of the plot.
const LABEL_ROOM = 260
const BAR_STEP = 18
const PLOT_FLOOR = 120
// The data field of the size of a link's change, by which the change bars are sorted.
const SIZE = '__size'
// The data field of a link's label, `source → target`.
const LINK = '__link'

/** The plot's dimensions on source, target and colour, and its measure. */
export interface SankeyChannels {
  source: Dimension
  target: Dimension
  value: string
  color: Dimension | null
}

/** The plot's channels in the table; an error when the mapping or the table lacks one. */
export function sankeyChannels(args: Pick<PlotArgs, 'mapping' | 'schema'>): SankeyChannels {
  const { source, target, value, color } = args.mapping
  if (!source || !target || !value) throw new Error('the plot maps no source, target or value')
  return { source: dimension(args, source), target: dimension(args, target), value, color: color ? dimension(args, color) : null }
}

/** The panels' grid for a chart `width` wide: how many go in a row, and the width of each. */
export function panelGrid(count: number, width: number): { columns: number, panelWidth: number } {
  const columns = Math.max(1, Math.min(count, Math.floor((width + SPACING) / (MIN_PANEL_WIDTH + SPACING))))
  return { columns, panelWidth: Math.max(PANEL_FLOOR, Math.floor((width - (columns - 1) * SPACING) / columns)) }
}

/** What the line over the diagrams says of the links' width, or nothing for a bare `value`. */
export function unitLine(ch: SankeyChannels, unit: string | null): string | null {
  return (unit || ch.value !== 'value') ? `Link width: ${yTitle(ch.value, unit)}` : null
}

/** The height of the header over the diagrams, `width` wide: the legend of `labels` and the unit line. */
export function headerHeight(labels: string[], unit: boolean, width: number): number {
  let height = labels.length ? HEADER.legendTop + (Math.ceil(labels.length / legendGrid(labels, width).columns) - 1) * HEADER.legendRow + HEADER.legendBottom : 0
  if (unit) height += HEADER.unitLine
  return height ? height + HEADER.gap : 0
}

/**
 * About the height of the chart of `args` in a container `width` wide: the export menu's room, the
 * header and the rows of panels, each about as high as its diagrams draw; a compact chart's box.
 */
export function reservedHeight(args: PlotArgs, width: number): number {
  const height = diagramHeight(args)
  if (args.compact) return height
  const ch = sankeyChannels(args)
  const labels = ch.color ? ch.color.values.map(value => display(value, ch.color!)) : []
  const header = headerHeight(labels, unitLine(ch, args.unit) !== null, width)
  const splits = splitDimensions(args)
  const panels = splits.length ? new Set(args.table.map(row => labelOf(row, splits))).size : 1
  const rows = Math.ceil(panels / panelGrid(panels, width).columns)
  const label = splits.length ? PANEL_LABEL : 0
  return MENU_ROOM + header + rows * (label + Math.round(DRAWN * height)) + (rows - 1) * ROW_GAP
}

/** The height of the box each panel's diagram is laid out in: lower in panels, lowest in a compact chart. */
export function diagramHeight(args: Pick<PlotArgs, 'compact' | 'state'>): number {
  if (args.compact) return HEIGHTS.compact
  return args.state.splits.length ? HEIGHTS.panel : HEIGHTS.single
}

/**
 * Whether a flow of the selection changed, so that the change bars draw something: of the rows of
 * either table, as the change charts compare them, one has a change other than 0.
 */
export function flowsChanged(args: Compared): boolean {
  return changeRows(args).some(row => !!asNumber(row[CHANGE]))
}

/**
 * The change bars of the `kind` of change, whose rows hold it on `value`: per panel, a bar per
 * link with a change, labelled `source → target`, in its colour, the largest change first. Links
 * between the same nodes in one panel are told apart by their colour value. A panel without a
 * change is left out; the x axes of the others are shared or not as the toggle asks.
 */
export const sankeyChange: ChangeBuilder = (args, width, kind) => {
  const ch = sankeyChannels(args)
  const measure = ch.value
  const splits = splitDimensions(args)
  const all = args.table.map((row): Row => ({
    [LINK]: `${display(row[ch.source.name] ?? null, ch.source)} → ${display(row[ch.target.name] ?? null, ch.target)}`,
    ...(splits.length ? { [PANEL]: labelOf(row, splits) } : {}),
    ...(ch.color ? { [ch.color.name]: plain(row[ch.color.name] ?? null, ch.color) } : {}),
    [measure]: asNumber(row[measure]),
    [SIZE]: Math.abs(asNumber(row[measure]) ?? 0),
  }))
  if (ch.color) {
    const color = ch.color
    const key = (row: Row) => `${row[PANEL] ?? ''}\u0000${row[LINK]}`
    const counts = new Map<string, number>()
    for (const row of all) counts.set(key(row), (counts.get(key(row)) ?? 0) + 1)
    for (const row of all) {
      if (counts.get(key(row))! > 1) row[LINK] = `${row[LINK]}${SEPARATOR}${display(row[color.name] ?? null, color)}`
    }
  }
  const rows = all.filter(row => (row[SIZE] as number) > 0)
  const panels = new Set(rows.map(row => row[PANEL]))
  const { columns, panelWidth } = panelGrid(panels.size, width - PADDING)
  const room = Math.min(LABEL_ROOM, Math.floor(panelWidth * 0.4))
  const plot = Math.max(PLOT_FLOOR, panelWidth - room - 8)
  const ink = INK[args.theme]
  const relative = kind === 'relative'
  const title = yTitle(relative ? 'relative change' : 'change', relative ? null : args.unit)
  const x = {
    field: field(measure),
    type: 'quantitative',
    title,
    axis: {
      orient: 'top',
      grid: true,
      format: relative ? '.3~p' : numberFormat(largest(rows, measure)),
      tickCount: 5,
      // The zero in the ink of the tick labels, so the sign reads.
      gridColor: { condition: { test: 'datum.value === 0', value: ink.tick }, value: ink.grid },
    },
  }
  // Vega lays out a panel's axis by at most its maxExtent, 200 px by default, which longer labels
  // would pass.
  const axis = { labelLimit: room, minExtent: 0, maxExtent: room + 8 }
  const y = { field: LINK, type: 'nominal', title: null, sort: { field: SIZE, op: 'max', order: 'descending' }, axis }
  // The legend starts at the plot's left edge, so it has the plot's width.
  const color = ch.color ? colorEncodings(ch.color, args.theme, 'square', plot) : { color: { value: seriesColors(1, args.theme)[0] } }
  const tooltip = [
    { field: LINK, title: `${ch.source.name} → ${ch.target.name}` },
    ...(ch.color ? [{ field: field(ch.color.name), type: 'nominal', title: ch.color.name }] : []),
    ...(splits.length ? [{ field: PANEL, title: args.state.splits.join(SEPARATOR) }] : []),
    { field: SHOWN, title },
  ]
  const bars = highlighted({
    mark: { type: 'bar', cornerRadiusEnd: 4, strokeWidth: 1.5 },
    encoding: { x, y, ...color, stroke: { condition: { param: 'hover', empty: false, value: ink.primary }, value: 'transparent' }, tooltip },
  }, ch.color)
  const unit = {
    ...bars,
    transform: [shown(args, measure, kind)],
    params: [...focus(ch.color), { name: 'hover', select: { type: 'point', on: 'pointerover', clear: 'pointerout' } }],
  }
  const base = { $schema: 'https://vega.github.io/schema/vega-lite/v6.json', data: { values: rows }, config: config(args.theme) }
  if (!splits.length) return { ...base, width: plot, height: { step: BAR_STEP }, ...unit } as unknown as TopLevelSpec
  return {
    ...base,
    facet: { field: PANEL, type: 'nominal', sort: combinations(splits).filter(label => panels.has(label)), header: { title: null, labelLimit: panelWidth } },
    columns,
    spacing: { row: ROW_GAP, column: SPACING },
    spec: { width: plot, height: { step: BAR_STEP }, ...unit },
    resolve: { scale: { x: args.state.y, y: 'independent' } },
  } as unknown as TopLevelSpec
}

/**
 * The browser half. While the drawing loads with d3-sankey-diagram, which takes a moment the first
 * time, it holds about the chart's room, so that the charts under it do not move; then it draws.
 */
export const sankey: PlotType = {
  async render(args) {
    args.el.style.minHeight = `${reservedHeight(args, args.el.clientWidth)}px`
    try {
      const { draw } = await import('./sankey_diagram')
      return draw(args)
    }
    finally {
      args.el.style.minHeight = ''
    }
  },
}
