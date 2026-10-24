import type { TopLevelSpec } from 'vega-lite'
import { definePlot } from './embed'
import { colorEncodings, highlighted, hoverRule, overX } from './encodings'
import { channels, frame } from './layout'
import { CATEGORICAL, INK } from './theme'
import type { PlotArgs } from './types'

/**
 * Areas of y over x stacked in the display order of the colour values, separated by a hairline
 * in the surface colour, with a crosshair whose tooltip lists every layer; a single series is a
 * wash under its line.
 */
export function stackedAreaSpec(args: PlotArgs, width: number): TopLevelSpec {
  const ch = channels(args)
  const { x, y } = overX(args, ch, width, ch.color !== null)
  const single = CATEGORICAL[args.theme][0]
  const marks = ch.color
    ? [highlighted({ mark: { type: 'area', stroke: INK[args.theme].surface, strokeWidth: 1 }, encoding: { y, ...colorEncodings(ch.color, args.theme, 'square', width) } }, ch.color)]
    : [{ mark: { type: 'area', color: single, opacity: 0.1 }, encoding: { y } }, { mark: { type: 'line', color: single }, encoding: { y } }]
  return frame(args, ch, { encoding: { x }, layer: [...marks, hoverRule(args, x, ch)] }, width)
}

export const stackedArea = definePlot(stackedAreaSpec)
