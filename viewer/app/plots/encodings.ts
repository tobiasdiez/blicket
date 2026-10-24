// The encodings of the built-in plot types: channels by dimension type, the colour scale, the
// y axis with its unit, the legend highlight and the tooltips.
import * as vega from 'vega'
import type { Dimension } from '../lib/manifest'
import { display, formatValue, isTime, numberFormat, type Cell } from '../lib/table'
import { type Channels, combinations, labelOf, magnitude, PANEL, plain, plotWidth, SEPARATOR, SERIES, seriesDimensions, type Spec } from './layout'
import { CATEGORICAL, INK, SLOTS } from './theme'
import type { PlotArgs, Theme } from './types'

// Line types, and lines whose colour repeats past the slots, are told apart by these.
const DASHES = [[1, 0], [6, 3], [2, 3], [8, 3, 2, 3]]
const FADED = 0.15
const UNIT = '__unit'

/** The format type of tooltip numbers: three significant digits chosen per value. */
const PER_VALUE = 'blicketNumber'
vega.expressionFunction(PER_VALUE, (value: unknown) => (typeof value === 'number' ? formatValue(value) : String(value ?? '')))

/** A column name as a Vega-Lite field, where `.`, `[` and `]` would mean nesting. */
export function field(name: string): string {
  return name.replace(/[.[\]\\]/g, match => `\\${match}`)
}

/** The dimension's values in display order, as the data handed to Vega holds them. */
export function domain(d: Dimension): Cell[] {
  return d.values.map(value => plain(value, d))
}

/**
 * The x encoding of a chart over x by the dimension's type: integers are quantitative without
 * thousands separators and without padding to zero, so years read 1950; dates are temporal on a
 * UTC scale; anything else is nominal in display order.
 */
function xEncoding(d: Dimension, width: number): Spec {
  const common = { field: field(d.name), title: d.name }
  if (!isTime(d) && d.dtype !== 'integer') {
    const values = domain(d)
    return { ...common, type: 'nominal', sort: values, scale: { domain: values }, axis: { labelAngle: 0, labelOverlap: true } }
  }
  // About one tick per 90 px, the first and last label inside the plot.
  const count = Math.max(2, Math.round(width / 90))
  const ticks = { tickCount: count, labelFlush: true, labelOverlap: true }
  if (d.dtype === 'date') {
    // Days, never hours, while the span is short enough for day ticks.
    const times = d.values.map(value => Date.parse(String(value)))
    const days = (Math.max(...times) - Math.min(...times)) / 86_400_000
    const daily = days <= count * 7 ? { tickCount: { interval: 'day', step: Math.max(1, Math.ceil(days / count)) }, format: '%Y-%m-%d' } : {}
    return { ...common, type: 'temporal', scale: { type: 'utc' }, axis: { ...ticks, ...daily } }
  }
  if (isTime(d)) return { ...common, type: 'temporal', scale: { type: 'utc' }, axis: ticks }
  return { ...common, type: 'quantitative', scale: { nice: false, zero: false }, axis: { ...ticks, format: 'd', tickMinStep: 1 } }
}

/** The y axis title: the measure with its unit, or the unit alone for the generic `value`. */
export function yTitle(measure: string, unit: string | null): string {
  if (!unit) return measure
  return measure === 'value' ? unit : `${measure} [${unit}]`
}

/**
 * The y encoding of the measure, stacked or not, with the unit in its title and a number format
 * for the largest value it shows: of a row, or of a stack per x and panel.
 */
export function yAxis(args: PlotArgs, ch: Channels, stacked: boolean): Spec {
  const format = numberFormat(magnitude(args, ch.y, stacked ? [ch.x.name, ...args.state.splits] : null))
  return {
    field: field(ch.y),
    type: 'quantitative',
    title: yTitle(ch.y, args.unit),
    stack: stacked ? 'zero' : null,
    axis: { format, tickCount: 5 },
  }
}

/** The x and y encodings of a chart over x; `stacked` sizes the axis by the stacks. */
export function overX(args: PlotArgs, ch: Channels, width: number, stacked: boolean): { x: Spec, y: Spec } {
  return { x: xEncoding(ch.x, plotWidth(args, width)), y: yAxis(args, ch, stacked) }
}

/** As many legend columns as fit `width`, at most six. */
function legendColumns(d: Dimension, width: number): number {
  const entry = Math.max(...d.values.map(value => display(value, d).length), 4) * 6.5 + 32
  return Math.max(1, Math.min(d.values.length, 6, Math.floor(width / entry)))
}

/** The dash pattern of the `i`-th value of a line type, or of the `i`-th round of hues. */
function dash(i: number): number[] {
  return DASHES[i % DASHES.length]!
}

/** The dash encoding of `d`, one pattern per value in display order. */
function dashEncoding(d: Dimension, patterns: number[][], width: number): Spec {
  const values = domain(d)
  return {
    field: field(d.name),
    type: 'nominal',
    sort: values,
    scale: { domain: values, range: patterns },
    legend: { title: d.name, symbolType: 'stroke', columns: legendColumns(d, width) },
  }
}

/**
 * The colour encoding of `d`: one slot per value in display order, the same for every filter, so
 * a value keeps its colour; past the slots the hues repeat. With `dashed`, lines of a repeated
 * hue get a dash pattern per round, shown in the same legend.
 */
export function colorEncodings(d: Dimension, theme: Theme, symbol: string, width: number, dashed = false): Spec {
  const values = domain(d)
  const legend = { title: d.name, symbolType: symbol, columns: legendColumns(d, width) }
  const range = values.map((_, i) => CATEGORICAL[theme][i % SLOTS])
  const encodings: Spec = { color: { field: field(d.name), type: 'nominal', sort: values, scale: { domain: values, range }, legend } }
  if (dashed && values.length > SLOTS) encodings.strokeDash = dashEncoding(d, values.map((_, i) => dash(Math.floor(i / SLOTS))), width)
  return encodings
}

/** The line type encoding: a dash pattern per value. */
export function linetypeEncoding(d: Dimension, width: number): Spec {
  return dashEncoding(d, d.values.map((_, i) => dash(i)), width)
}

/**
 * `layer` with a legend highlight on `d`: clicking an entry fades the other series, clicking it
 * again brings them back.
 */
export function highlighted(layer: Spec, d: Dimension | null): Spec {
  if (!d) return layer
  return {
    ...layer,
    // The string: for a legend binding, Vega-Lite ignores the boolean.
    params: [{ name: 'focus', select: { type: 'point', fields: [field(d.name)], toggle: 'true' }, bind: 'legend' }],
    encoding: { ...(layer.encoding as Spec), opacity: { condition: { param: 'focus', value: 1 }, value: FADED } },
  }
}

/** A tooltip entry of a number, formatted per value. */
export function numberTooltip(name: string, title: string): Spec {
  return { field: field(name), type: 'quantitative', title, formatType: PER_VALUE }
}

/** The first tooltip entries of a chart: the x value, and the panel when there are panels. */
export function tooltipHead(args: PlotArgs, x: Spec, d: Dimension): Spec[] {
  const entry = { field: x.field, title: x.title }
  let head: Spec
  if (d.dtype === 'date') head = { ...entry, type: 'temporal', timeUnit: 'utcyearmonthdate' }
  else if (d.dtype === 'datetime') head = { ...entry, type: 'temporal', timeUnit: 'utcyearmonthdatehoursminutesseconds' }
  else if (d.dtype === 'integer') head = { ...entry, type: 'quantitative', format: 'd' }
  else head = { ...entry, type: 'nominal' }
  return args.state.splits.length ? [head, { field: PANEL, title: args.state.splits.join(SEPARATOR) }] : [head]
}

/**
 * The hover layer of charts over x: a hairline rule that snaps to the nearest x, one per x and
 * panel, whose tooltip lists every series there, pivoted from the rows by their series label.
 */
export function hoverRule(args: PlotArgs, x: Spec, ch: Channels): Spec {
  const series = seriesDimensions(ch)
  const tooltip = tooltipHead(args, x, ch.x)
  const transform: Spec[] = []
  if (series.length) {
    const present = new Set(args.table.map(row => labelOf(row, series)))
    const labels = combinations(series).filter(label => present.has(label))
    transform.push({ pivot: SERIES, value: field(ch.y), groupby: [x.field, ...(args.state.splits.length ? [PANEL] : [])] })
    tooltip.push(...labels.map(label => numberTooltip(label, label)))
    if (args.unit) {
      transform.push({ calculate: JSON.stringify(args.unit), as: UNIT })
      tooltip.push({ field: UNIT, title: 'unit' })
    }
  }
  else {
    tooltip.push(numberTooltip(ch.y, yTitle(ch.y, args.unit)))
  }
  return {
    transform,
    mark: { type: 'rule', color: INK[args.theme].muted, strokeWidth: 1 },
    params: [{ name: 'hover', select: { type: 'point', fields: [x.field], nearest: true, on: 'pointerover', clear: 'pointerout' } }],
    encoding: { x, opacity: { condition: { param: 'hover', empty: false, value: 1 }, value: 0 }, tooltip },
  }
}
