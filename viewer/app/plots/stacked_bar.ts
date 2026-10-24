import { barSpec } from './bar'
import { definePlot } from './embed'

export const stackedBar = definePlot((args, width) => barSpec(args, width, true))
