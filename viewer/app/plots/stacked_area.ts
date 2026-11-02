import type { TopLevelSpec } from 'vega-lite'
import { definePlot } from './embed'
import { colorEncodings, datum, field, focus, ghost, highlighted, hoverRule, overX } from './encodings'
import { type Channels, channels, frame, from, PANEL, type Spec } from './layout'
import { lineSpec } from './line'
import { CATEGORICAL, INK } from './theme'
import type { ChangeBuilder, PlotArgs } from './types'

// The computed fields: a layer's least and largest value in its panel, and the value it stacks.
const LEAST = '__least'
const MOST = '__most'
const STACKED = '__stacked'
// The negative number closest to zero: Vega stacks it downwards, as any value below 0, and it adds
// nothing to the running sum it lies on.
const NEGLIGIBLE = -Number.MIN_VALUE

/**
 * The transforms and the y encoding that stack the layers of the colour by sign; without colour,
 * none and `y` itself. Vega stacks a zero on the positive side, where a layer that is negative
 * elsewhere would reach up to the top of the positive layers. So the layers stack a computed
 * field: the measure, 0 for a missing x or value, and, for a layer that is never positive in its
 * panel and negative at least once, `NEGLIGIBLE` in place of 0, which stacks at the running sum of
 * the negative layers. The transforms follow a layer's source filter and group by layer and panel,
 * so each source and panel stacks by itself; the panel is needed in the impute's groupby, to which
 * Vega-Lite does not add the facet field, or a year that another panel has is not filled in.
 */
function stackBySign(args: PlotArgs, ch: Channels, y: Spec): { transform: Spec[], y: Spec } {
  if (!ch.color) return { transform: [], y }
  const measure = field(ch.y)
  const value = datum(ch.y)
  const groupby = [field(ch.color.name), ...(args.state.splits.length ? [PANEL] : [])]
  // Never positive, and negative at least once: an all-zero layer at NEGLIGIBLE would take the y
  // domain below 0, which `nice` then rounds down to a tick under 0.
  const negativeLayer = `${datum(MOST)} <= 0 && ${datum(LEAST)} < 0`
  // A zero, null or NaN fails both comparisons.
  const nonzero = `${value} > 0 || ${value} < 0`
  const zero = `${negativeLayer} ? ${NEGLIGIBLE} : 0`
  const transform = [
    { impute: measure, key: field(ch.x.name), groupby, value: 0 },
    { joinaggregate: [{ op: 'min', field: measure, as: LEAST }, { op: 'max', field: measure, as: MOST }], groupby },
    { calculate: `${nonzero} ? ${value} : (${zero})`, as: STACKED },
  ]
  return { transform, y: { ...y, field: STACKED } }
}

/**
 * Areas of y over x stacked in the display order of the colour values, separated by a hairline
 * in the surface colour, with a crosshair whose tooltip lists every layer; a single series is a
 * wash under its line. Positive values stack up from zero, negative ones down. With a baseline,
 * its stack is drawn as faded areas, and the current one as the line on top of each layer.
 */
export function stackedAreaSpec(args: PlotArgs, width: number): TopLevelSpec {
  const ch = channels(args)
  const { x, y } = overX(args, ch, width, ch.color !== null)
  const single = CATEGORICAL[args.theme][0]
  const rule = hoverRule(args, x, ch)
  const stack = stackBySign(args, ch, y)
  if (args.baseline) {
    const color = ch.color ? colorEncodings(ch.color, args.theme, 'square', width) : { color: { value: single } }
    const areas = ghost({ mark: { type: 'area' }, transform: stack.transform, encoding: { y: stack.y, ...color } }, ch.color, 'fillOpacity', args.theme)
    const tops = from('current', highlighted({ mark: { type: 'line' }, transform: stack.transform, encoding: { y: stack.y, ...color } }, ch.color))
    return frame(args, ch, { encoding: { x }, layer: [{ ...areas, params: focus(ch.color) }, tops, rule] }, width)
  }
  if (!ch.color) {
    const wash = [{ mark: { type: 'area', color: single, opacity: 0.1 }, encoding: { y } }, { mark: { type: 'line', color: single }, encoding: { y } }]
    return frame(args, ch, { encoding: { x }, layer: [...wash, rule] }, width)
  }
  const color = colorEncodings(ch.color, args.theme, 'square', width)
  const areas = highlighted({ mark: { type: 'area', stroke: INK[args.theme].surface, strokeWidth: 1 }, transform: stack.transform, encoding: { y: stack.y, ...color } }, ch.color)
  return frame(args, ch, { encoding: { x }, layer: [{ ...areas, params: focus(ch.color) }, rule] }, width)
}

export const stackedArea = definePlot(stackedAreaSpec)

/** The change of stacked areas: lines, since the changes of the layers do not stack. */
export const stackedAreaChange: ChangeBuilder = lineSpec
