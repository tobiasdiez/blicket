import type { TopLevelSpec } from 'vega-lite'
import { definePlot } from './embed'
import { colorEncodings, field, focus, ghost, highlighted, hoverRule, linetypeEncoding, overX } from './encodings'
import { channels, frame, from, type Spec } from './layout'
import { CATEGORICAL, INK } from './theme'
import type { ChangeBuilder, PlotArgs, Quantity } from './types'

const GHOST_WIDTH = 6 // px

/**
 * Lines of y over x, one per colour and line type value, with a crosshair whose tooltip lists
 * every line. Past the colour slots the hues repeat with a dash per round; when the dash shows
 * the line type instead, lines of a repeated hue look alike, and the legend highlight tells them
 * apart. The baseline's lines lie behind, wide, faded and solid, in their series' colours.
 */
export function lineSpec(args: PlotArgs, width: number, quantity: Quantity = 'measure'): TopLevelSpec {
  const ch = channels(args)
  const { x, y } = overX(args, ch, width, false, quantity)
  const encoding: Spec = ch.color
    ? { y, ...colorEncodings(ch.color, args.theme, 'stroke', width, !ch.linetype) }
    : { y, color: { value: CATEGORICAL[args.theme][0] } }
  if (ch.linetype) encoding.strokeDash = linetypeEncoding(ch.linetype, width)
  const dots = {
    mark: { type: 'point', filled: true, size: 64, opacity: 1, stroke: INK[args.theme].surface, strokeWidth: 2 },
    transform: [{ filter: { param: 'hover', empty: false } }],
    encoding: { y, color: encoding.color },
  }
  const series = ch.color ?? ch.linetype
  const lines = highlighted({ mark: { type: 'line' }, encoding }, series)
  let layer: Spec[] = [{ ...lines, params: focus(series) }, dots]
  if (args.baseline) {
    // The legend highlight's param goes with the legend's channel: the ghost draws the colour, the
    // current lines alone the line type.
    const detail = ch.linetype ? { detail: { field: field(ch.linetype.name), type: 'nominal' } } : {}
    // Clipped to the plot, so the wide caps do not widen the panels: they line up with the change
    // charts' below.
    const wide = ghost({ mark: { type: 'line', strokeWidth: GHOST_WIDTH, clip: true }, encoding: { y, color: encoding.color, ...detail } }, series, 'strokeOpacity', args.theme)
    layer = ch.color
      ? [{ ...wide, params: focus(series) }, from('current', lines), from('current', dots)]
      : [wide, from('current', { ...lines, params: focus(series) }), from('current', dots)]
  }
  return frame(args, ch, { encoding: { x }, layer: [...layer, hoverRule(args, x, ch, quantity)] }, width, false, quantity)
}

export const line = definePlot(lineSpec)

/** The change of a line chart: lines. */
export const lineChange: ChangeBuilder = lineSpec
