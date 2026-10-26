// The frame around a unit chart: the plot's channels, the data handed to Vega with its panel and
// series labels and the baseline's rows, panels for the split dimensions as a top-level facet,
// sizes, and the theme.
import type { TopLevelSpec } from 'vega-lite'
import type { Dimension } from '../lib/manifest'
import { display, isTime, largest, valueKey, type Cell, type Row } from '../lib/table'
import { config, Y_LABEL_EXTENT } from './theme'
import type { PlotArgs, Quantity } from './types'

/** A part of a Vega-Lite specification. */
export type Spec = Record<string, unknown>

/** The data field naming a row's panel, made of its split values. */
export const PANEL = '__panel'
/** The data field naming a row's series, made of its colour and line type values. */
export const SERIES = '__series'
/** Joins the values of a panel or series label, and the dimension names of its title. */
export const SEPARATOR = ' · '
/** The data field holding, on a current row, the baseline's value of the row with its dimension values. */
export const BASELINE_VALUE = '__baseline'
// The data field naming a row's source, when the chart has a baseline.
const SOURCE = '__source'

type Source = 'current' | 'baseline'

const MIN_PANEL_WIDTH = 240 // px, which sets how many panels go in a row
const PANEL_FLOOR = 90 // px, the least plot width of a panel
const PLOT_FLOOR = 160 // px, the least plot width without panels
// Room for a y axis: its labels, then 8 px of padding and about 12 px for the title's line.
const AXIS_WIDTH = Y_LABEL_EXTENT + 20
/** Vega's padding, left and right, and some slack, in px. */
export const PADDING = 20
const SPACING = 16

/** The plot's dimensions and measure by channel. */
export interface Channels {
  x: Dimension
  y: string
  color: Dimension | null
  linetype: Dimension | null
}

function dimension(args: Pick<PlotArgs, 'schema'>, name: string): Dimension {
  const found = args.schema.dimensions.find(d => d.name === name)
  if (!found) throw new Error(`the table has no dimension ${name}`)
  return found
}

export function channels(args: Pick<PlotArgs, 'mapping' | 'schema'>): Channels {
  const { x, y, color, linetype } = args.mapping
  if (!x || !y) throw new Error('the plot maps no x or no y')
  return {
    x: dimension(args, x),
    y,
    color: color ? dimension(args, color) : null,
    linetype: linetype ? dimension(args, linetype) : null,
  }
}

/** The dimensions that tell the series apart: colour and line type. */
export function seriesDimensions(ch: Channels): Dimension[] {
  return [ch.color, ch.linetype].filter((d): d is Dimension => d !== null)
}

/** The label of a row's combination of values of `dims`, such as `EUR · high`. */
export function labelOf(row: Row, dims: Dimension[]): string {
  return dims.map(d => display(row[d.name] ?? null, d)).join(SEPARATOR)
}

/** The labels of every combination of values of `dims`, in display order. */
export function combinations(dims: Dimension[]): string[] {
  let labels = ['']
  for (const d of dims) labels = labels.flatMap(prefix => d.values.map(v => (prefix ? prefix + SEPARATOR : '') + display(v, d)))
  return labels
}

const splitDimensions = (args: PlotArgs) => args.state.splits.map(name => dimension(args, name))

/** The key of a row's value of `d`, which compares equal across the tables. */
export function cellKey(row: Row, d: Dimension): string {
  return valueKey(row[d.name] ?? null, d.dtype)
}

/** The key of a row's dimension values, which matches a row of one table with the other's. */
export function rowKey(row: Row, dimensions: Dimension[]): string {
  return dimensions.map(d => cellKey(row, d)).join('\u0000')
}

/** A measure's number, or null: NaN counts as none, as null does. */
export function asNumber(cell: Cell | undefined): number | null {
  return typeof cell === 'number' && !Number.isNaN(cell) ? cell : null
}

/** The baseline's number of `measure` by the key of each row's dimension values. */
export function baselineValues(baseline: Row[], dimensions: Dimension[], measure: string): Map<string, number | null> {
  return new Map(baseline.map(row => [rowKey(row, dimensions), asNumber(row[measure])]))
}

/** `layer` drawn from the rows of one source. */
export function from(source: Source, layer: Spec): Spec {
  return { ...layer, transform: [{ filter: { field: SOURCE, equal: source } }, ...((layer.transform as Spec[] | undefined) ?? [])] }
}

/** A dimension value as the data handed to Vega holds it: time as its key, except on a time axis. */
export function plain(value: Cell, d: Dimension): Cell {
  return isTime(d) && value !== null ? valueKey(value, d.dtype) : value
}

/**
 * The rows as Vega reads them: time as keys except on a time x axis (not on a `band`), plus the
 * panel label and the series label. With a baseline, its rows follow the current ones, every row
 * names its source, and a current row holds the baseline's value of the row with its dimension
 * values.
 */
function prepare(args: PlotArgs, ch: Channels, band: boolean): Row[] {
  const times = args.schema.dimensions.filter(d => isTime(d) && (band || d !== ch.x))
  const splits = splitDimensions(args)
  const series = seriesDimensions(ch)
  const baseline = args.baseline
  if (!times.length && !splits.length && !series.length && !baseline) return args.table
  const withLabels = (row: Row): Row => {
    const copy: Row = { ...row }
    for (const d of times) copy[d.name] = plain(row[d.name] ?? null, d)
    if (splits.length) copy[PANEL] = labelOf(row, splits)
    if (series.length) copy[SERIES] = labelOf(row, series)
    return copy
  }
  if (!baseline) return args.table.map(withLabels)
  const dims = args.schema.dimensions
  const before = baselineValues(baseline, dims, ch.y)
  return [
    ...args.table.map(row => ({ ...withLabels(row), [SOURCE]: 'current', [BASELINE_VALUE]: before.get(rowKey(row, dims)) ?? null })),
    ...baseline.map(row => ({ ...withLabels(row), [SOURCE]: 'baseline' })),
  ]
}

/** The width of a panel, and how many panels go in a row, for a container `width` wide. */
function layout(args: PlotArgs, width: number): { columns: number, panelWidth: number } {
  const splits = splitDimensions(args)
  const count = new Set([...args.table, ...(args.baseline ?? [])].map(row => labelOf(row, splits))).size
  // At least two in a row, so many panels do not make a narrow page very long.
  const columns = Math.max(Math.min(2, count), Math.min(count, Math.floor(width / (MIN_PANEL_WIDTH + SPACING))))
  const axes = args.state.y === 'independent' ? columns : 1
  const panelWidth = Math.floor((width - PADDING - axes * AXIS_WIDTH - (columns - 1) * SPACING) / columns)
  return { columns, panelWidth: Math.max(PANEL_FLOOR, panelWidth) }
}

/** The width of the plot area of a chart `width` wide, of one panel when there are panels. */
export function plotWidth(args: PlotArgs, width: number): number {
  return args.state.splits.length ? layout(args, width).panelWidth : Math.max(PLOT_FLOOR, width - PADDING - AXIS_WIDTH)
}

/**
 * The largest absolute value the y axis shows, of the current rows and the baseline's: per row, or
 * per stack of the `stackedBy` keys.
 */
export function magnitude(args: PlotArgs, measure: string, stackedBy: string[] | null): number {
  return Math.max(...[args.table, args.baseline ?? []].map(rows => largestIn(rows, measure, stackedBy)))
}

/** The largest absolute value of `measure` in `rows`: of a row, or of a stack of the `stackedBy` keys. */
function largestIn(rows: Row[], measure: string, stackedBy: string[] | null): number {
  if (!stackedBy) return largest(rows, measure)
  const sums = new Map<string, [number, number]>()
  for (const row of rows) {
    const key = stackedBy.map(name => String(row[name])).join('\u0000')
    const value = Number(row[measure]) || 0
    const sum = sums.get(key) ?? [0, 0]
    sum[value > 0 ? 0 : 1] += value
    sums.set(key, sum)
  }
  return Math.max(0, ...[...sums.values()].map(([positive, negative]) => Math.max(positive, -negative)))
}

/**
 * The whole specification around a unit chart (`encoding` and `layer`, or `mark`): the data, the
 * panels of the split dimensions as a top-level facet with wrapped columns and a shared or
 * independent y axis, the sizes and the theme. `band` says that x is a band (bars). A chart of a
 * change, under the chart of the measure, is lower.
 */
export function frame(args: PlotArgs, ch: Channels, unit: Spec, width: number, band = false, quantity: Quantity = 'measure'): TopLevelSpec {
  const data = { values: prepare(args, ch, band) }
  const base = { $schema: 'https://vega.github.io/schema/vega-lite/v6.json', data, config: config(args.theme) }
  // The height of the plot area without panels, and of a panel.
  const [single, panel] = quantity === 'measure' ? [320, 180] : [200, 140]
  if (!args.state.splits.length) {
    return { ...base, width: plotWidth(args, width), height: single, ...unit } as unknown as TopLevelSpec
  }
  const { columns, panelWidth } = layout(args, width)
  return {
    ...base,
    // A panel's label is cut to the panel's width, so it does not reach into the next one or off the page.
    facet: { field: PANEL, type: 'nominal', sort: combinations(splitDimensions(args)), header: { title: null, labelLimit: panelWidth } },
    columns,
    spacing: { row: SPACING + 8, column: SPACING },
    spec: { width: panelWidth, height: panel, ...unit },
    resolve: { scale: { y: args.state.y } },
  } as unknown as TopLevelSpec
}
