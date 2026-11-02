import type { TopLevelSpec } from 'vega-lite'
import type { Dimension } from '../lib/manifest'
import { display, isTime, numberFormat, type Cell, type Row } from '../lib/table'
import { changedRows } from './change'
import { definePlot } from './embed'
import { colorEncodings, domain, field, focus, ghost, highlighted, hoverDot, linetypeDetail, linetypeEncoding, measureName, numberText, overBaseline, panelEntry, POINT_SIZE, roundShapes, shapeEncoding, shown, SHOWN, xTicks, yAxis, yTitle } from './encodings'
import { baselineValues, dimension, frame, type FrameChannels, magnitude, plotHeight, plotWidth, rowKey, type Spec } from './layout'
import { belowZero, logChannels, scaled } from './scales'
import { CATEGORICAL } from './theme'
import type { ChangeBuilder, PlotArgs, Quantity } from './types'

const GHOST_SIZE = 196 // px², a point of the baseline
const GHOST_WIDTH = 6 // px, a line of the baseline
// px between the frame and the outermost points: a baseline point's radius, and some room
const POINT_PADDING = 10
// The data fields of a row's position in the display order of the `along` dimension, of the text
// of its x for the tooltip, of the baseline's x of the row, and of the text of a time value by
// channel, since the data handed to Vega holds time as keys.
const ORDER = '__order'
const X_SHOWN = '__x'
const BASELINE_X = '__baseline_x'
const TEXT = '__text_'

/** The measures on x and y, the dimensions that tell the series apart, and the one along which their points connect. */
interface ScatterChannels extends FrameChannels {
  /** The measure on x; `FrameChannels.x` is a dimension on x, which a scatter has none of. */
  xMeasure: string
  along: Dimension | null
}

function scatterChannels(args: Pick<PlotArgs, 'mapping' | 'schema'>): ScatterChannels {
  const { x, y, color, linetype, along } = args.mapping
  if (!x || !y) throw new Error('the plot maps no x or no y')
  return {
    xMeasure: x,
    y,
    color: color ? dimension(args, color) : null,
    linetype: linetype ? dimension(args, linetype) : null,
    along: along ? dimension(args, along) : null,
  }
}

/** The dimensions on the colour, line type and `along` channels, by channel, in the tooltip's order. */
function valueDimensions(ch: ScatterChannels): { channel: string, d: Dimension }[] {
  return ([['color', ch.color], ['linetype', ch.linetype], ['along', ch.along]] as const).flatMap(([channel, d]) => (d ? [{ channel, d }] : []))
}

/**
 * Why a scatter leaves `row` out on its own account, as a clause of the line under the chart: its
 * x or y is missing; `null` for a row with both. A value its logarithmic axes have no place for is
 * every chart's reason (`reasons` in index.ts).
 */
export function leftOut(args: Pick<PlotArgs, 'mapping'>, row: Row): string | null {
  const { x, y } = args.mapping
  return [x, y].every(column => column !== undefined && Number.isFinite(row[column])) ? null : 'x or y is missing'
}

/**
 * The x domain of a scatter and of its change charts, which they share so that they line up: the
 * extent of x of the rows that one of them draws. The chart of the measure draws the rows of
 * either table with an x and a y its axes have a place for; a change chart draws a row with a
 * change against the baseline (see `changeRows`) at its x, also where its y is missing on one
 * side.
 */
function xDomain(args: PlotArgs, xMeasure: string): [number, number] | null {
  const chart = args.above ?? args
  const logs = new Set(logChannels(chart).map(([channel]) => channel))
  const onAxis = (channel: string, value: Cell | undefined): value is number =>
    typeof value === 'number' && Number.isFinite(value) && !(logs.has(channel) && belowZero(value))
  const y = chart.mapping.y!
  const drawn = [...chart.table, ...(chart.baseline ?? [])].filter(row => onAxis('y', row[y]))
  const changed = chart.baseline ? changedRows(chart) : []
  let low = Infinity
  let high = -Infinity
  for (const row of [...drawn, ...changed]) {
    const value = row[xMeasure]
    if (!onAxis('x', value)) continue
    low = Math.min(low, value)
    high = Math.max(high, value)
  }
  return low <= high ? [low, high] : null
}

/** The tooltip entry of the value of `d` on `channel`: an integer without thousands separators, a time as the viewer writes it. */
function valueEntry(channel: string, d: Dimension): Spec {
  const title = d.name
  if (isTime(d)) return { field: TEXT + channel, type: 'nominal', title }
  return d.dtype === 'integer' ? { field: field(d.name), type: 'quantitative', format: 'd', title } : { field: field(d.name), type: 'nominal', title }
}

/** The baseline's rows of a chart, or of the chart of the measure above a change chart. */
function baselineOf(args: PlotArgs): PlotArgs['baseline'] {
  return (args.above ?? args).baseline
}

/**
 * The current rows with what the tooltip shows beside their own values: the baseline's x of the
 * row, and the time values of the series and `along` dimensions as text.
 */
function withTooltipFields(args: PlotArgs, ch: ScatterChannels): Row[] {
  const times = valueDimensions(ch).filter(({ d }) => isTime(d))
  const dims = args.schema.dimensions
  const baseline = baselineOf(args)
  const before = baseline ? baselineValues(baseline, dims, ch.xMeasure) : null
  if (!times.length && !before) return args.table
  return args.table.map((row) => {
    const copy: Row = { ...row }
    if (before) copy[BASELINE_X] = before.get(rowKey(row, dims)) ?? null
    for (const { channel, d } of times) copy[TEXT + channel] = display(row[d.name] ?? null, d)
    return copy
  })
}

/**
 * Points of the measure on y against the measure on x, one colour per colour value and a shape
 * per line type value, or per round of hues past the colour slots; with `along`, a line per series
 * instead, connecting its points in the display order of the `along` values, dashed per line type
 * as a line chart's. Both axes are linear, nice and not forced to zero, or logarithmic as the plot
 * definition chooses; a row without a number on either axis is left out, and a line connects its
 * neighbours. Points keep clear of the frame. The nearest point to the pointer gets a dot and a
 * tooltip with its panel, series, `along` value, x and y, x and y with the baseline's numbers
 * where they differ. The baseline's points or lines lie behind, at the baseline's own x, wider
 * and faded, in their series' colours. A change chart draws the change of y over the x axis of
 * the chart above, its tooltips with the baseline's x where it differs.
 */
export function scatterSpec(args: PlotArgs, width: number, quantity: Quantity = 'measure'): TopLevelSpec {
  const ch = scatterChannels(args)
  const { xMeasure, along } = ch
  const padding = along ? {} : { padding: POINT_PADDING }
  const extent = xDomain(args, xMeasure)
  // On a logarithmic axis too, the x ticks are `xTicks`', about one per 90 px, which leaves room
  // for the labels of the powers of ten and their multiples; `scaled` is given no extent for x.
  const across = plotWidth(args, width)
  const x = scaled({
    field: field(xMeasure),
    type: 'quantitative',
    title: xMeasure,
    scale: { nice: true, zero: false, ...padding, ...(extent && { domain: extent }) },
    axis: { format: numberFormat(magnitude(args, xMeasure, null)), ...xTicks(across) },
  }, args, 'x')
  // A change keeps its zero, which shows its sign; `changeArgs` leaves y linear.
  const yScale = quantity === 'measure' ? { nice: true, zero: false, ...padding } : padding
  const y = scaled({ ...yAxis(args, ch, false, quantity), scale: yScale }, args, 'y', plotHeight(args, quantity))
  // Each layer leaves out the rows it cannot draw, not the chart: a panel of no such row keeps its
  // place, so a change chart has the panels of the chart above. A value a logarithmic axis has no
  // place for is missing already (`prepare`).
  const drawable: Spec[] = [{ filter: `isFinite(datum[${JSON.stringify(xMeasure)}]) && isFinite(datum[${JSON.stringify(ch.y)}])` }]
  if (along) drawable.push({ calculate: `indexof(${JSON.stringify(domain(along))}, datum[${JSON.stringify(along.name)}])`, as: ORDER })
  const fromDrawable = (layer: Spec): Spec => ({ ...layer, transform: [...drawable, ...((layer.transform as Spec[] | undefined) ?? [])] })
  const order = along ? { order: { field: ORDER, type: 'quantitative' } } : {}

  const colors: Spec = ch.color
    ? colorEncodings(ch.color, args.theme, along ? 'stroke' : 'circle', width, along !== null && !ch.linetype)
    : { color: { value: CATEGORICAL[args.theme][0] } }
  const series = ch.color ?? ch.linetype
  const shape = ch.linetype ? shapeEncoding(ch.linetype, args.theme, width) : ch.color && roundShapes(ch.color, width)
  const marks = along
    ? { mark: { type: 'line' }, encoding: { ...colors, ...order, ...(ch.linetype && { strokeDash: linetypeEncoding(ch.linetype, width) }) } }
    : { mark: { type: 'point', filled: true, size: POINT_SIZE, opacity: 1 }, encoding: { color: colors.color, ...(shape && { shape }) } }
  const visible = fromDrawable(highlighted(marks, series))

  const tooltip: Spec[] = [
    ...panelEntry(args),
    ...valueDimensions(ch).map(({ channel, d }) => valueEntry(channel, d)),
    { field: X_SHOWN, title: xMeasure },
    { field: SHOWN, title: yTitle(measureName(ch, quantity), args.unit) },
  ]
  const hover = fromDrawable({
    transform: [shown(args, ch.y, quantity), numberText(xMeasure, X_SHOWN, baselineOf(args) ? BASELINE_X : null)],
    mark: hoverDot(args.theme),
    params: [{ name: 'hover', select: { type: 'point', on: 'pointerover', clear: 'pointerout', nearest: true } }],
    encoding: { color: colors.color, opacity: { condition: { param: 'hover', empty: false, value: 1 }, value: 0 }, tooltip },
  })

  let layer: Spec[] = [{ ...visible, params: focus(series) }, hover]
  if (args.baseline) {
    const behind = along
      ? ghost(fromDrawable({ mark: { type: 'line', strokeWidth: GHOST_WIDTH, clip: true }, encoding: { color: colors.color, ...order, ...linetypeDetail(ch) } }), series, 'strokeOpacity', args.theme)
      : ghost(fromDrawable({ mark: { type: 'point', filled: true, size: GHOST_SIZE, opacity: 1, clip: true }, encoding: { color: colors.color } }), series, 'fillOpacity', args.theme)
    layer = overBaseline(behind, visible, [hover], ch)
  }
  return frame({ ...args, table: withTooltipFields(args, ch) }, ch, { encoding: { x, y }, layer }, width, false, quantity)
}

export const scatter = definePlot(scatterSpec)

/** The change of a scatter: the change of y over the row's x, as points or along lines. */
export const scatterChange: ChangeBuilder = scatterSpec
