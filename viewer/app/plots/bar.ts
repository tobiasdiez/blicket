import type { TopLevelSpec } from 'vega-lite'
import { display } from '../lib/table'
import { definePlot } from './embed'
import { colorEncodings, domain, field, highlighted, numberTooltip, tooltipHead, yAxis, yTitle } from './encodings'
import { channels, frame, plotWidth, type Spec } from './layout'
import { CATEGORICAL, INK } from './theme'
import type { PlotArgs } from './types'

const MAX_BAR = 24 // px; bars never fill their slot

/**
 * Bars of y at each x: side by side per colour value, or, `stacked`, stacked in the display order
 * of the colour values with a gap in the surface colour between segments. Each bar has its own
 * tooltip and an outline on hover. x is ordinal in display order; labels that do not fit their
 * slot turn upright.
 */
export function barSpec(args: PlotArgs, width: number, stacked: boolean): TopLevelSpec {
  const ch = channels(args)
  const color = ch.color
  const grouped = !stacked && color !== null
  const slot = plotWidth(args, width) / Math.max(1, ch.x.values.length)
  const crowded = Math.max(0, ...ch.x.values.map(value => display(value, ch.x).length)) * 7 + 8 > slot
  const ink = INK[args.theme]
  const values = domain(ch.x)
  const x = {
    field: field(ch.x.name),
    title: ch.x.name,
    type: 'ordinal',
    sort: values,
    // Grouped bars are as wide as their slot within the group, so the gap between groups grows.
    scale: { domain: values, paddingInner: grouped ? Math.min(0.9, Math.max(0.2, 1 - (MAX_BAR * color.values.length) / (0.9 * slot))) : 0.2 },
    axis: crowded ? { labelAngle: -90, labelAlign: 'right', labelBaseline: 'middle', labelOverlap: true } : { labelAngle: 0, labelOverlap: true },
  }
  const tooltip = tooltipHead(args, x, ch.x)
  if (color) tooltip.splice(1, 0, { field: field(color.name), type: 'nominal', title: color.name })
  tooltip.push(numberTooltip(ch.y, yTitle(ch.y, args.unit)))
  const encoding = {
    x,
    y: yAxis(args, ch, stacked && color !== null),
    ...(color ? colorEncodings(color, args.theme, 'square', width) : { color: { value: CATEGORICAL[args.theme][0] } }),
    ...(grouped ? { xOffset: { field: field(color.name), type: 'nominal', sort: domain(color), scale: { domain: domain(color), paddingInner: 0.1 } } } : {}),
    // The hovered bar gets an outline; stacked segments keep a gap in the surface colour.
    stroke: { condition: { param: 'hover', empty: false, value: ink.primary }, value: stacked ? ink.surface : 'transparent' },
    tooltip,
  }
  const mark = {
    type: 'bar',
    ...(grouped ? {} : { width: Math.max(2, Math.min(MAX_BAR, slot * 0.7)) }),
    ...(stacked ? { strokeWidth: 2 } : { strokeWidth: 1.5, cornerRadiusEnd: 4 }),
  }
  const bars = highlighted({ mark, encoding }, color)
  const hover = { name: 'hover', select: { type: 'point', on: 'pointerover', clear: 'pointerout' } }
  return frame(args, ch, { ...bars, params: [...((bars.params as Spec[] | undefined) ?? []), hover] }, width, true)
}

export const bar = definePlot((args, width) => barSpec(args, width, false))
