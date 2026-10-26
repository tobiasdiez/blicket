import type { TopLevelSpec } from 'vega-lite'
import { definePlot } from './embed'
import { colorEncodings, focus, ghost, highlighted, hoverRule, overX } from './encodings'
import { channels, frame, from } from './layout'
import { lineSpec } from './line'
import { CATEGORICAL, INK } from './theme'
import type { ChangeBuilder, PlotArgs } from './types'

/**
 * Areas of y over x stacked in the display order of the colour values, separated by a hairline
 * in the surface colour, with a crosshair whose tooltip lists every layer; a single series is a
 * wash under its line. With a baseline, its stack is drawn as faded areas, and the current one as
 * the line on top of each layer.
 */
export function stackedAreaSpec(args: PlotArgs, width: number): TopLevelSpec {
  const ch = channels(args)
  const { x, y } = overX(args, ch, width, ch.color !== null)
  const single = CATEGORICAL[args.theme][0]
  const rule = hoverRule(args, x, ch)
  if (args.baseline) {
    const color = ch.color ? colorEncodings(ch.color, args.theme, 'square', width) : { color: { value: single } }
    const areas = ghost({ mark: { type: 'area' }, encoding: { y, ...color } }, ch.color, 'fillOpacity', args.theme)
    const tops = from('current', highlighted({ mark: { type: 'line' }, encoding: { y, ...color } }, ch.color))
    return frame(args, ch, { encoding: { x }, layer: [{ ...areas, params: focus(ch.color) }, tops, rule] }, width)
  }
  const marks = ch.color
    ? [{ ...highlighted({ mark: { type: 'area', stroke: INK[args.theme].surface, strokeWidth: 1 }, encoding: { y, ...colorEncodings(ch.color, args.theme, 'square', width) } }, ch.color), params: focus(ch.color) }]
    : [{ mark: { type: 'area', color: single, opacity: 0.1 }, encoding: { y } }, { mark: { type: 'line', color: single }, encoding: { y } }]
  return frame(args, ch, { encoding: { x }, layer: [...marks, rule] }, width)
}

export const stackedArea = definePlot(stackedAreaSpec)

/** The change of stacked areas: lines, since the changes of the layers do not stack. */
export const stackedAreaChange: ChangeBuilder = lineSpec
