import type { TopLevelSpec } from 'vega-lite'
import { definePlot } from './embed'
import { colorEncodings, highlighted, hoverRule, linetypeEncoding, overX } from './encodings'
import { channels, frame, type Spec } from './layout'
import { CATEGORICAL, INK } from './theme'
import type { PlotArgs } from './types'

/**
 * Lines of y over x, one per colour and line type value, with a crosshair whose tooltip lists
 * every line. Past the colour slots the hues repeat with a dash per round; when the dash shows
 * the line type instead, lines of a repeated hue look alike, and the legend highlight tells them
 * apart.
 */
export function lineSpec(args: PlotArgs, width: number): TopLevelSpec {
  const ch = channels(args)
  const { x, y } = overX(args, ch, width, false)
  const encoding: Spec = ch.color
    ? { y, ...colorEncodings(ch.color, args.theme, 'stroke', width, !ch.linetype) }
    : { y, color: { value: CATEGORICAL[args.theme][0] } }
  if (ch.linetype) encoding.strokeDash = linetypeEncoding(ch.linetype, width)
  const dots = {
    mark: { type: 'point', filled: true, size: 64, opacity: 1, stroke: INK[args.theme].surface, strokeWidth: 2 },
    transform: [{ filter: { param: 'hover', empty: false } }],
    encoding: { y, color: encoding.color },
  }
  const layer = [highlighted({ mark: { type: 'line' }, encoding }, ch.color ?? ch.linetype), dots, hoverRule(args, x, ch)]
  return frame(args, ch, { encoding: { x }, layer }, width)
}

export const line = definePlot(lineSpec)
