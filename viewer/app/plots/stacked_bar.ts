import { barSpec } from './bar'
import { definePlot } from './embed'
import type { ChangeBuilder } from './types'

export const stackedBar = definePlot((args, width) => barSpec(args, width, true))

/**
 * The change of stacked bars: stacked too, the gains up and the losses down from zero, so the ends
 * of a bar read the stack's total gain and loss; the relative change grouped, since ratios do not
 * stack.
 */
export const stackedBarChange: ChangeBuilder = (args, width, kind) => barSpec(args, width, kind === 'change', kind)
