import { bar, barChange } from './bar'
import { comparable, type Compared } from './change'
import { line, lineChange } from './line'
import { stackedArea, stackedAreaChange } from './stacked_area'
import { stackedBar, stackedBarChange } from './stacked_bar'
import type { ChangeBuilder, PlotType } from './types'

/** A built-in plot type: its browser half, and how it draws its change against a baseline. */
export interface BuiltIn {
  plot: PlotType
  change: ChangeBuilder
}

/**
 * The built-in plot types, by the name the manifest records. They are bundled with the viewer; a
 * project's own plot types have no browser half here.
 */
export const PLOT_TYPES: Record<string, BuiltIn> = {
  line: { plot: line, change: lineChange },
  stacked_area: { plot: stackedArea, change: stackedAreaChange },
  bar: { plot: bar, change: barChange },
  stacked_bar: { plot: stackedBar, change: stackedBarChange },
}

/**
 * Whether the change charts under a chart of the plot `type` have nothing to draw: a built-in's,
 * against a baseline with rows, none of which has a change. A project's plot type, which has no
 * change charts, is not asked: its mapping need not have the built-ins' channels.
 */
export function nothingToCompare(type: string, args: Compared): boolean {
  return Object.hasOwn(PLOT_TYPES, type) && !!args.baseline?.length && !comparable(args)
}
