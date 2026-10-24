import { bar } from './bar'
import { line } from './line'
import { stackedArea } from './stacked_area'
import { stackedBar } from './stacked_bar'
import type { PlotType } from './types'

/**
 * The browser halves of the built-in plot types, by the name the manifest records. They are
 * bundled with the viewer; a project's own plot types have no browser half here.
 */
export const PLOT_TYPES: Record<string, PlotType> = {
  line,
  stacked_area: stackedArea,
  bar,
  stacked_bar: stackedBar,
}
