import { bar, barChange } from './bar'
import { comparable, type Compared } from './change'
import { line, lineChange } from './line'
import { flowsChanged, sankey, sankeyChange } from './sankey'
import { stackedArea, stackedAreaChange } from './stacked_area'
import { stackedBar, stackedBarChange } from './stacked_bar'
import type { ChangeBuilder, PlotType } from './types'

/**
 * A built-in plot type: its browser half, how it draws its change against a baseline, and, when it
 * is not `comparable`, how it knows that its change charts draw something. `drawsBaseline` is
 * false for a type whose chart does not draw the baseline behind its marks.
 */
export interface BuiltIn {
  plot: PlotType
  change: ChangeBuilder
  changed?: (args: Compared) => boolean
  drawsBaseline?: boolean
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
  sankey: { plot: sankey, change: sankeyChange, changed: flowsChanged, drawsBaseline: false },
}

/**
 * Whether the change charts under a chart of the plot `type` have nothing to draw: a built-in's,
 * against a baseline with rows, none of which has a change. A project's plot type, which has no
 * change charts, is not asked: its mapping need not have the built-ins' channels.
 */
export function nothingToCompare(type: string, args: Compared): boolean {
  if (!Object.hasOwn(PLOT_TYPES, type) || !args.baseline?.length) return false
  return !(PLOT_TYPES[type]!.changed ?? comparable)(args)
}

/** Whether a chart of the plot `type` draws the baseline behind its marks: the Sankey diagram's does not. */
export function drawsBaseline(type: string): boolean {
  return PLOT_TYPES[type]?.drawsBaseline ?? true
}
