import type { TopLevelSpec } from 'vega-lite'
import { display } from '../lib/table'
import { definePlot } from './embed'
import { colorEncodings, domain, field, focus, ghost, highlighted, measureName, shown, SHOWN, tooltipHead, yAxis, yTitle } from './encodings'
import { channels, frame, from, plotWidth, type Spec } from './layout'
import { CATEGORICAL, INK } from './theme'
import type { ChangeBuilder, PlotArgs, Quantity } from './types'

const MAX_BAR = 24 // px; bars never fill their slot
const GHOST_SCALE = 1.4 // the width of the baseline's bars, in bar widths

/**
 * Bars of y at each x: side by side per colour value, or, `stacked`, stacked in the display order
 * of the colour values with a gap in the surface colour between segments. Each bar has its own
 * tooltip and an outline on hover. x is ordinal in display order; labels that do not fit their
 * slot turn upright. The baseline's bars stand behind, faded and wider, stacked as the current
 * ones are.
 */
export function barSpec(args: PlotArgs, width: number, stacked: boolean, quantity: Quantity = 'measure'): TopLevelSpec {
  const ch = channels(args)
  const color = ch.color
  const grouped = !stacked && color !== null
  const slot = plotWidth(args, width) / Math.max(1, ch.x.values.length)
  const crowded = Math.max(0, ...ch.x.values.map(value => display(value, ch.x).length)) * 7 + 8 > slot
  const ink = INK[args.theme]
  const values = domain(ch.x)
  // Grouped bars are as wide as their slot within the group, so the gap between groups grows. The
  // outer padding is half the inner, as Vega-Lite pads a band without groups, so each group stands
  // where a stack of the same chart stacked would.
  const padding = grouped ? Math.min(0.9, Math.max(0.2, 1 - (MAX_BAR * color.values.length) / (0.9 * slot))) : 0.2
  const x = {
    field: field(ch.x.name),
    title: ch.x.name,
    type: 'ordinal',
    sort: values,
    scale: { domain: values, paddingInner: padding, paddingOuter: padding / 2 },
    axis: crowded ? { labelAngle: -90, labelAlign: 'right', labelBaseline: 'middle', labelOverlap: true } : { labelAngle: 0, labelOverlap: true },
  }
  const tooltip = tooltipHead(args, x, ch.x)
  if (color) tooltip.splice(1, 0, { field: field(color.name), type: 'nominal', title: color.name })
  tooltip.push({ field: SHOWN, title: yTitle(measureName(ch, quantity), args.unit) })
  // A change chart shows its rows without a change, as bars of no height, so that its facet has
  // every panel of the chart above; a panel of them has the y domain [0, 0].
  const change = quantity !== 'measure'
  const y = yAxis(args, ch, stacked && color !== null, quantity)
  const placed = {
    x,
    y: change ? { ...y, scale: { domain: { unionWith: [0] } } } : y,
    ...(color ? colorEncodings(color, args.theme, 'square', width) : { color: { value: CATEGORICAL[args.theme][0] } }),
    ...(grouped ? { xOffset: { field: field(color.name), type: 'nominal', sort: domain(color), scale: { domain: domain(color), paddingInner: 0.1 } } } : {}),
  }
  const barWidth = Math.max(2, Math.min(MAX_BAR, slot * 0.7))
  // The hovered bar gets an outline; stacked segments keep a gap in the surface colour, except a
  // segment of no height, whose gap would cut the line it lies on.
  const hovered = { param: 'hover', empty: false, value: ink.primary }
  const value = `datum[${JSON.stringify(ch.y)}]`
  const flat = { test: `!(${value} > 0 || ${value} < 0)`, value: 'transparent' }
  const encoding = {
    ...placed,
    stroke: stacked ? { condition: [hovered, flat], value: ink.surface } : { condition: hovered, value: 'transparent' },
    tooltip,
  }
  const mark = {
    type: 'bar',
    ...(grouped ? {} : { width: barWidth }),
    ...(stacked ? { strokeWidth: 2 } : { strokeWidth: 1.5, cornerRadiusEnd: 4 }),
    ...(change ? { invalid: 'show' } : {}),
  }
  const bars = { ...highlighted({ mark, encoding }, color), transform: [shown(args, ch.y, quantity)] }
  const hover = { name: 'hover', select: { type: 'point', on: 'pointerover', clear: 'pointerout' } }
  let unit: Spec = { ...bars, params: [...focus(color), hover] }
  if (args.baseline) {
    // A width relative to the band is centred on the x band, which puts a wider bar off its place
    // in a group; the offset band's width in an expression is centred on its bar.
    const ghostWidth = grouped ? { expr: `${GHOST_SCALE} * bandwidth('xOffset')` } : barWidth * GHOST_SCALE
    const behind = ghost({ mark: { ...mark, width: ghostWidth }, encoding: placed }, color, 'fillOpacity', args.theme)
    unit = { layer: [{ ...behind, params: focus(color) }, from('current', { ...bars, params: [hover] })] }
  }
  return frame(args, ch, unit, width, true, quantity)
}

export const bar = definePlot((args, width) => barSpec(args, width, false))

/** The change of grouped bars: grouped bars. */
export const barChange: ChangeBuilder = (args, width, kind) => barSpec(args, width, false, kind)
