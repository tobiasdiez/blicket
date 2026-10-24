// The frame around a unit chart: the plot's channels, the data handed to Vega with its panel and
// series labels, panels for the split dimensions as a top-level facet, sizes, and the theme.
import type { TopLevelSpec } from 'vega-lite'
import type { Dimension } from '../lib/manifest'
import { display, isTime, largest, valueKey, type Cell, type Row } from '../lib/table'
import { config } from './theme'
import type { PlotArgs } from './types'

/** A part of a Vega-Lite specification. */
export type Spec = Record<string, unknown>

/** The data field naming a row's panel, made of its split values. */
export const PANEL = '__panel'
/** The data field naming a row's series, made of its colour and line type values. */
export const SERIES = '__series'
/** Joins the values of a panel or series label, and the dimension names of its title. */
export const SEPARATOR = ' · '

const MIN_PANEL_WIDTH = 240
const AXIS_WIDTH = 64 // room for a y axis with its labels and title
const PADDING = 20 // Vega's padding, left and right, and some slack
const SPACING = 16

/** The plot's dimensions and measure by channel. */
export interface Channels {
  x: Dimension
  y: string
  color: Dimension | null
  linetype: Dimension | null
}

function dimension(args: PlotArgs, name: string): Dimension {
  const found = args.schema.dimensions.find(d => d.name === name)
  if (!found) throw new Error(`the table has no dimension ${name}`)
  return found
}

export function channels(args: PlotArgs): Channels {
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

/** A dimension value as the data handed to Vega holds it: time as its key, except on a time axis. */
export function plain(value: Cell, d: Dimension): Cell {
  return isTime(d) && value !== null ? valueKey(value, d.dtype) : value
}

/**
 * The rows as Vega reads them: time as keys except on a time x axis (not on a `band`), plus the
 * panel label and the series label.
 */
function prepare(args: PlotArgs, ch: Channels, band: boolean): Row[] {
  const times = args.schema.dimensions.filter(d => isTime(d) && (band || d !== ch.x))
  const splits = splitDimensions(args)
  const series = seriesDimensions(ch)
  if (!times.length && !splits.length && !series.length) return args.table
  return args.table.map((row) => {
    const copy: Row = { ...row }
    for (const d of times) copy[d.name] = plain(row[d.name] ?? null, d)
    if (splits.length) copy[PANEL] = labelOf(row, splits)
    if (series.length) copy[SERIES] = labelOf(row, series)
    return copy
  })
}

/** The width of a panel, and how many panels go in a row, for a container `width` wide. */
function layout(args: PlotArgs, width: number): { columns: number, panelWidth: number } {
  const splits = splitDimensions(args)
  const count = new Set(args.table.map(row => labelOf(row, splits))).size
  // At least two in a row, so many panels do not make a narrow page very long.
  const columns = Math.max(Math.min(2, count), Math.min(count, Math.floor(width / (MIN_PANEL_WIDTH + SPACING))))
  const axes = args.state.y === 'independent' ? columns : 1
  const panelWidth = Math.floor((width - PADDING - axes * AXIS_WIDTH - (columns - 1) * SPACING) / columns)
  return { columns, panelWidth: Math.max(100, panelWidth) }
}

/** The width of the plot area of a chart `width` wide, of one panel when there are panels. */
export function plotWidth(args: PlotArgs, width: number): number {
  return args.state.splits.length ? layout(args, width).panelWidth : Math.max(160, width - PADDING - AXIS_WIDTH)
}

/** The largest absolute value the y axis shows: per row, or per stack of the `stackedBy` keys. */
export function magnitude(args: PlotArgs, measure: string, stackedBy: string[] | null): number {
  if (!stackedBy) return largest(args.table, measure)
  const sums = new Map<string, [number, number]>()
  for (const row of args.table) {
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
 * independent y axis, the sizes and the theme. `band` says that x is a band (bars).
 */
export function frame(args: PlotArgs, ch: Channels, unit: Spec, width: number, band = false): TopLevelSpec {
  const data = { values: prepare(args, ch, band) }
  const base = { $schema: 'https://vega.github.io/schema/vega-lite/v6.json', data, config: config(args.theme) }
  if (!args.state.splits.length) {
    return { ...base, width: plotWidth(args, width), height: 320, ...unit } as unknown as TopLevelSpec
  }
  const { columns, panelWidth } = layout(args, width)
  return {
    ...base,
    facet: { field: PANEL, type: 'nominal', sort: combinations(splitDimensions(args)), header: { title: null } },
    columns,
    spacing: { row: SPACING + 8, column: SPACING },
    spec: { width: panelWidth, height: 180, ...unit },
    resolve: { scale: { y: args.state.y } },
  } as unknown as TopLevelSpec
}
