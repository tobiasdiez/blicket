// The encodings of the built-in plot types: channels by dimension type, the colour scale, the
// y axis with its unit, the legend highlight, the baseline's layer and the tooltips.
import * as vega from 'vega'
import type { Dimension } from '../lib/manifest'
import { display, formatter, formatValue, isTime, numberFormat, type Cell } from '../lib/table'
import { BASELINE_VALUE, type Channels, combinations, type FrameChannels, from, labelOf, magnitude, PANEL, plain, plotHeight, plotWidth, SEPARATOR, SERIES, seriesDimensions, type Spec } from './layout'
import { scaled } from './scales'
import { GHOST, INK, seriesColors, SLOTS } from './theme'
import type { PlotArgs, Quantity, Theme } from './types'

/** The size of a scatter's point and of the dot on a hovered point, in px². */
export const POINT_SIZE = 64
// Line types, and lines whose colour repeats past the slots, are told apart by these.
const DASHES = [[1, 0], [6, 3], [2, 3], [8, 3, 2, 3]]
// The line types of points, which have no dash, are told apart by these.
const SHAPES = ['circle', 'square', 'triangle-up', 'diamond', 'triangle-down', 'cross']
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
export function written(value: unknown, quantity: Quantity = 'measure'): string {
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
  const ticks = xTicks(width)
  const count = ticks.tickCount
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

/** The ticks of a continuous x axis `width` wide: about one per 90 px, the first and last label inside the plot. */
export function xTicks(width: number): { tickCount: number, labelFlush: boolean, labelOverlap: boolean } {
  return { tickCount: Math.max(2, Math.round(width / 90)), labelFlush: true, labelOverlap: true }
}

/** The y axis title: the measure with its unit, or the unit alone for the generic `value`. */
export function yTitle(measure: string, unit: string | null): string {
  if (!unit) return measure
  return measure === 'value' ? unit : `${measure} [${unit}]`
}

/** The name of what y shows: the measure, or its change. */
export function measureName(ch: FrameChannels, quantity: Quantity): string {
  if (quantity === 'change') return 'change'
  return quantity === 'relative' ? 'relative change' : ch.y
}

/**
 * The y encoding of the measure, stacked or not, with the unit in its title and a number format
 * for the largest value it shows: of a row, or of a stack per x and panel; only a chart over a
 * dimension on x stacks. A change's axis draws its zero in the ink of the tick labels, so the sign
 * reads, and a relative change's is in percent.
 */
export function yAxis(args: PlotArgs, ch: FrameChannels, stacked: boolean, quantity: Quantity = 'measure'): Spec {
  const stacks = stacked && ch.x ? [ch.x.name, ...args.state.splits] : null
  const format = quantity === 'relative' ? RELATIVE_FORMAT : numberFormat(magnitude(args, ch.y, stacks))
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

/** The x and y encodings of a chart over x, on the plot's scales; `stacked` sizes the axis by the stacks. */
export function overX(args: PlotArgs, ch: Channels, width: number, stacked: boolean, quantity: Quantity = 'measure'): { x: Spec, y: Spec } {
  const across = plotWidth(args, width)
  return { x: scaled(xEncoding(ch.x, across), args, 'x', across), y: scaled(yAxis(args, ch, stacked, quantity), args, 'y', plotHeight(args, quantity)) }
}

/**
 * A legend of `labels` in a chart `width` wide: the width of an entry, about that of the longest
 * label, and as many columns as fit, at most six.
 */
export function legendGrid(labels: string[], width: number): { columns: number, entryWidth: number } {
  const entryWidth = Math.max(...labels.map(label => label.length), 4) * 6.5 + 32
  return { columns: Math.max(1, Math.min(labels.length, 6, Math.floor(width / entryWidth))), entryWidth }
}

/** As many legend columns of the values of `d` as fit `width`, at most six. */
function legendColumns(d: Dimension, width: number): number {
  return legendGrid(d.values.map(value => display(value, d)), width).columns
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
  const range = seriesColors(values.length, theme)
  const encodings: Spec = { color: { field: field(d.name), type: 'nominal', sort: values, scale: { domain: values, range }, legend } }
  if (dashed && values.length > SLOTS) encodings.strokeDash = dashEncoding(d, values.map((_, i) => dash(Math.floor(i / SLOTS))), width)
  return encodings
}

/** The line type encoding: a dash pattern per value. */
export function linetypeEncoding(d: Dimension, width: number): Spec {
  return dashEncoding(d, d.values.map((_, i) => dash(i)), width)
}

/** The point shape of the `i`-th value of a line type, or of the `i`-th round of hues. */
function shape(i: number): string {
  return SHAPES[i % SHAPES.length]!
}

/** The shape encoding of `d`, one of `shapes` per value in display order, with the `legend`'s properties. */
function shapeScale(d: Dimension, shapes: string[], legend: Spec): Spec {
  const values = domain(d)
  return { field: field(d.name), type: 'nominal', sort: values, scale: { domain: values, range: shapes }, legend: { title: d.name, ...legend } }
}

/**
 * The line type encoding of points: a shape per value in display order, repeating past the shapes.
 * Its legend draws the shapes in the muted ink: beside a colour legend, which shows the points'
 * colours, so that the shapes read as shapes only; without a colour channel, every point has the
 * first slot's colour, which the legend leaves out.
 */
export function shapeEncoding(d: Dimension, theme: Theme, width: number): Spec {
  return shapeScale(d, d.values.map((_, i) => shape(i)), { columns: legendColumns(d, width), symbolFillColor: INK[theme].muted })
}

/**
 * The shapes of points coloured by `d` whose hues repeat past the slots: a shape per round of hues,
 * in the colour's legend, as lines get a dash per round; `null` while every value has a hue of its
 * own.
 */
export function roundShapes(d: Dimension, width: number): Spec | null {
  if (d.values.length <= SLOTS) return null
  return shapeScale(d, d.values.map((_, i) => shape(Math.floor(i / SLOTS))), { columns: legendColumns(d, width) })
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

/** The mark of the dot on a hovered point: filled in its series' colour, ringed in the surface colour. */
export function hoverDot(theme: Theme): Spec {
  return { type: 'point', filled: true, size: POINT_SIZE, opacity: 1, stroke: INK[theme].surface, strokeWidth: 2 }
}

/**
 * The `detail` encoding that keeps the baseline's lines of each line type apart: they are drawn
 * solid in their colour, so the lines of one colour would join without it.
 */
export function linetypeDetail(ch: FrameChannels): Spec {
  return ch.linetype ? { detail: { field: field(ch.linetype.name), type: 'nominal' } } : {}
}

/**
 * The layers of a chart compared with its baseline: the baseline's `behind` first, then `marks`
 * and the `hover` layers from the current rows. The legend highlight's param goes with the
 * legend's channel: on the baseline's layer, which draws the colour, or, without a colour, on the
 * current marks, which alone draw the line type.
 */
export function overBaseline(behind: Spec, marks: Spec, hover: Spec[], ch: FrameChannels): Spec[] {
  const series = ch.color ?? ch.linetype
  const current = hover.map(layer => from('current', layer))
  return ch.color
    ? [{ ...behind, params: focus(series) }, from('current', marks), ...current]
    : [behind, from('current', { ...marks, params: focus(series) }), ...current]
}

// A field of the row, and its number as a tooltip shows it, in a Vega expression.
export const datum = (name: string) => `datum[${JSON.stringify(name)}]`
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

/**
 * The `calculate` of the text that tooltips show for the number in the field `name`, into the
 * field `as`, with the number in the field `baseline`, if given, where the two read differently.
 */
export function numberText(name: string, as: string, baseline: string | null = null): Spec {
  return baseline ? compared(name, baseline, as) : { calculate: text(name), as }
}

/** The tooltip entry of a row's panel, when there are panels. */
export function panelEntry(args: PlotArgs): Spec[] {
  return args.state.splits.length ? [{ field: PANEL, title: args.state.splits.join(SEPARATOR) }] : []
}

/** The first tooltip entries of a chart: the x value, and the panel when there are panels. */
export function tooltipHead(args: PlotArgs, x: Spec, d: Dimension): Spec[] {
  const entry = { field: x.field, title: d.name }
  let head: Spec
  if (d.dtype === 'date') head = { ...entry, type: 'temporal', timeUnit: 'utcyearmonthdate' }
  else if (d.dtype === 'datetime') head = { ...entry, type: 'temporal', timeUnit: 'utcyearmonthdatehoursminutesseconds' }
  else if (d.dtype === 'integer') head = { ...entry, type: 'quantitative', format: 'd' }
  else head = { ...entry, type: 'nominal' }
  return [head, ...panelEntry(args)]
}

/**
 * The hover layer of charts over x: a hairline rule that snaps to the nearest x, one per x and
 * panel, whose tooltip lists every series there, pivoted from the rows by their series label;
 * with a baseline, each with the baseline's number where it differs; a change with its sign. A
 * series the current rows lack is not listed, and one without a row at the hovered x shows an en
 * dash.
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
    // The pivot leaves out the field of a series without a row at an x, such as yearly history
    // next to a model's five-year steps.
    transform.push(...labels.map(label => ({ calculate: `isValid(${datum(label)}) ? ${datum(label)} : '${NONE}'`, as: label })))
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
