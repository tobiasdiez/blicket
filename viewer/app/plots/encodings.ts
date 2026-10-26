// The encodings of the built-in plot types: channels by dimension type, the colour scale, the
// y axis with its unit, the legend highlight, the baseline's layer and the tooltips.
import * as vega from 'vega'
import type { Dimension } from '../lib/manifest'
import { display, formatter, formatValue, isTime, numberFormat, type Cell } from '../lib/table'
import { BASELINE_VALUE, type Channels, combinations, from, labelOf, magnitude, PANEL, plain, plotWidth, SEPARATOR, SERIES, seriesDimensions, type Spec } from './layout'
import { CATEGORICAL, GHOST, INK, SLOTS } from './theme'
import type { PlotArgs, Quantity, Theme } from './types'

// Line types, and lines whose colour repeats past the slots, are told apart by these.
const DASHES = [[1, 0], [6, 3], [2, 3], [8, 3, 2, 3]]
const FADED = 0.15
// The opacity of the baseline's marks of the series a legend click leaves out.
const GHOST_FADED = 0.1
const UNIT = '__unit'
/** The computed field holding a number's tooltip text. */
export const SHOWN = '__shown'

// The d3 format of a relative change, on its axis and in its tooltips: one on both, so numerical
// noise reads as a long fraction, `0.0000000000000111%`, the price of one format.
const RELATIVE_FORMAT = '.3~p'
const asPercent = formatter(RELATIVE_FORMAT)
// What a tooltip shows for a missing number, as the reports' empty cell.
const NONE = '\u2013'

/**
 * A number as a tooltip writes it: three significant digits chosen per value, a change with its
 * sign, `+1.2M` or `−300k`, a relative one in percent, `+2.1%`; an en dash for none.
 */
function written(value: unknown, quantity: Quantity = 'measure'): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return NONE
  const text = quantity === 'relative' ? asPercent(value) : formatValue(value)
  return quantity !== 'measure' && value > 0 ? `+${text}` : text
}

/** The expression function of tooltip numbers, with the quantity as its optional second argument. */
const PER_VALUE = 'blicketNumber'
vega.expressionFunction(PER_VALUE, written)

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

/** The name of what y shows: the measure, or its change. */
export function measureName(ch: Channels, quantity: Quantity): string {
  if (quantity === 'change') return 'change'
  return quantity === 'relative' ? 'relative change' : ch.y
}

/**
 * The y encoding of the measure, stacked or not, with the unit in its title and a number format
 * for the largest value it shows: of a row, or of a stack per x and panel. A change's axis draws
 * its zero in the ink of the tick labels, so the sign reads, and a relative change's is in percent.
 */
export function yAxis(args: PlotArgs, ch: Channels, stacked: boolean, quantity: Quantity = 'measure'): Spec {
  const format = quantity === 'relative' ? RELATIVE_FORMAT : numberFormat(magnitude(args, ch.y, stacked ? [ch.x.name, ...args.state.splits] : null))
  const ink = INK[args.theme]
  const zero = quantity === 'measure' ? {} : { gridColor: { condition: { test: 'datum.value === 0', value: ink.tick }, value: ink.grid } }
  return {
    field: field(ch.y),
    type: 'quantitative',
    title: yTitle(measureName(ch, quantity), args.unit),
    stack: stacked ? 'zero' : null,
    axis: { format, tickCount: 5, ...zero },
  }
}

/** The x and y encodings of a chart over x; `stacked` sizes the axis by the stacks. */
export function overX(args: PlotArgs, ch: Channels, width: number, stacked: boolean, quantity: Quantity = 'measure'): { x: Spec, y: Spec } {
  return { x: xEncoding(ch.x, plotWidth(args, width)), y: yAxis(args, ch, stacked, quantity) }
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
 * The legend highlight's param on `d`, for the first layer that encodes the legend's channel, from
 * which Vega-Lite draws the legend: clicking an entry fades the other series, clicking it again
 * brings them back.
 */
export function focus(d: Dimension | null): Spec[] {
  // The string: for a legend binding, Vega-Lite ignores the boolean.
  return d ? [{ name: 'focus', select: { type: 'point', fields: [field(d.name)], toggle: 'true' }, bind: 'legend' }] : []
}

/** `layer` faded for the series that the legend highlight on `d` leaves out. */
export function highlighted(layer: Spec, d: Dimension | null): Spec {
  if (!d) return layer
  return { ...layer, encoding: { ...(layer.encoding as Spec), opacity: { condition: { param: 'focus', value: 1 }, value: FADED } } }
}

/**
 * The baseline's `layer`, drawn first, behind the current ones: faded, and fainter still for the
 * series that the legend highlight on `d` leaves out. It fades in `channel`, its stroke or fill
 * opacity, since an `opacity` encoding would fade the legend's symbols too.
 */
export function ghost(layer: Spec, d: Dimension | null, channel: 'strokeOpacity' | 'fillOpacity', theme: Theme): Spec {
  const opacity = d ? { condition: { param: 'focus', value: GHOST[theme] }, value: GHOST_FADED } : { value: GHOST[theme] }
  return from('baseline', { ...layer, encoding: { ...(layer.encoding as Spec), [channel]: opacity } })
}

// A field of the row, and its number as a tooltip shows it, in a Vega expression.
const datum = (name: string) => `datum[${JSON.stringify(name)}]`
const text = (name: string, quantity: Quantity = 'measure') => `${PER_VALUE}(${datum(name)}${quantity === 'measure' ? '' : `, '${quantity}'`})`

/**
 * A `calculate` of the text of the number in the field `current`, with the number in `baseline`
 * where the two read differently: `212M`, or `−60.1M (baseline −48.1M)`.
 */
function compared(current: string, baseline: string, as: string): Spec {
  const both = `(isValid(${datum(current)}) ? ${text(current)} + ' ' : '') + '(baseline ' + ${text(baseline)} + ')'`
  return { calculate: `!isValid(${datum(baseline)}) || ${text(baseline)} === ${text(current)} ? ${text(current)} : ${both}`, as }
}

/**
 * The `calculate` of the text that tooltips show for the `measure` of a current row, into the
 * field `SHOWN`: the number, with the baseline's where it reads differently; a change with its
 * sign.
 */
export function shown(args: PlotArgs, measure: string, quantity: Quantity = 'measure'): Spec {
  return args.baseline ? compared(measure, BASELINE_VALUE, SHOWN) : { calculate: text(measure, quantity), as: SHOWN }
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
 * panel, whose tooltip lists every series there, pivoted from the rows by their series label;
 * with a baseline, each with the baseline's number where it differs; a change with its sign. A
 * series the current rows lack is not listed.
 */
export function hoverRule(args: PlotArgs, x: Spec, ch: Channels, quantity: Quantity = 'measure'): Spec {
  const series = seriesDimensions(ch)
  const tooltip = tooltipHead(args, x, ch.x)
  const transform = [shown(args, ch.y, quantity)]
  if (series.length) {
    const present = new Set(args.table.map(row => labelOf(row, series)))
    const labels = combinations(series).filter(label => present.has(label))
    // `max` keeps a text as it is; each series has one row per x and panel.
    transform.push({ pivot: SERIES, value: SHOWN, groupby: [x.field, ...(args.state.splits.length ? [PANEL] : [])], op: 'max' })
    tooltip.push(...labels.map(label => ({ field: field(label), title: label })))
    if (args.unit) {
      transform.push({ calculate: JSON.stringify(args.unit), as: UNIT })
      tooltip.push({ field: UNIT, title: 'unit' })
    }
  }
  else {
    tooltip.push({ field: SHOWN, title: yTitle(measureName(ch, quantity), args.unit) })
  }
  const rule = {
    transform,
    mark: { type: 'rule', color: INK[args.theme].muted, strokeWidth: 1 },
    params: [{ name: 'hover', select: { type: 'point', fields: [x.field], nearest: true, on: 'pointerover', clear: 'pointerout' } }],
    encoding: { x, opacity: { condition: { param: 'hover', empty: false, value: 1 }, value: 0 }, tooltip },
  }
  return args.baseline ? from('current', rule) : rule
}
