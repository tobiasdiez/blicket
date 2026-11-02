import type { Row } from '../lib/table'
import { bar, barChange } from './bar'
import { comparable, type Compared } from './change'
import { line, lineChange } from './line'
import { flowsChanged, sankey, sankeyChange } from './sankey'
import { belowZero, logChannels } from './scales'
import { leftOut, scatter, scatterChange } from './scatter'
import { stackedArea, stackedAreaChange } from './stacked_area'
import { stackedBar, stackedBarChange } from './stacked_bar'
import type { ChangeBuilder, PlotArgs, PlotType } from './types'

/** What tells whether a chart draws a row of its table: the plot's mapping and scales. */
type Drawable = Pick<PlotArgs, 'mapping' | 'scales'>

/**
 * A built-in plot type: its browser half, how it draws its change against a baseline, and, when it
 * is not `comparable`, how it knows that its change charts draw something. `drawsBaseline` is
 * false for a type whose chart does not draw the baseline behind its marks.
 */
export interface BuiltIn {
  plot: PlotType
  change: ChangeBuilder
  /**
   * Why the chart leaves `row` out on its own account, as a clause of the line under the chart,
   * such as `x or y is missing`; `null` for a row it draws. Only a type that leaves rows out on
   * its own account defines it; the others draw every row whose values their axes have a place for.
   */
  leftOut?: (args: Pick<PlotArgs, 'mapping'>, row: Row) => string | null
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
  scatter: { plot: scatter, change: scatterChange, leftOut },
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

/**
 * Why a chart of the plot `type` leaves out each row of `args.table`, as a clause of the line under
 * the chart, `null` for a row it draws: a built-in leaves out a row with a value at or below zero
 * on a logarithmic axis, which has no place for it, and the rows its type leaves out on its own
 * account. A project's plot type is not asked.
 */
function reasons(type: string, args: Drawable & Pick<PlotArgs, 'table'>): (string | null)[] {
  if (!Object.hasOwn(PLOT_TYPES, type)) return args.table.map(() => null)
  const own = PLOT_TYPES[type]!.leftOut
  const logs = logChannels(args)
  return args.table.map((row) => {
    const reason = own?.(args, row)
    if (reason) return reason
    const below = logs.find(([, column]) => belowZero(row[column]))
    return below ? `a value is at or below zero on the logarithmic ${below[0]} axis` : null
  })
}

/** Whether a chart of the plot `type` leaves out every row of `rows`, though there are some. */
function noneDrawn(type: string, args: Drawable, rows: PlotArgs['table']): boolean {
  return rows.length > 0 && reasons(type, { ...args, table: rows }).every(reason => reason !== null)
}

/**
 * Whether a chart of the plot `type` and its change charts draw nothing, though there are rows: a
 * built-in may leave out every row (see `reasons`), as a scatter does those without an x or a y;
 * then neither the baseline's rows behind nor a change against them may be left to draw.
 */
export function nothingToDraw(type: string, args: Drawable & Compared): boolean {
  if (!noneDrawn(type, args, args.table)) return false
  const baseline = args.baseline ?? []
  return !baseline.length || (noneDrawn(type, args, baseline) && !comparable(args))
}

/**
 * What the chart of the plot `type` says under itself about the rows of `args.table` it leaves
 * out: `12 of 276 rows are not drawn: x or y is missing.`, the reasons in the order first met;
 * empty when it draws all of them. When it draws none, the page says so instead of the chart,
 * unless the baseline's rows or the change charts are drawn.
 */
export function leftOutNote(type: string, args: Drawable & Pick<PlotArgs, 'table'>): string {
  const found = reasons(type, args).filter((reason): reason is string => reason !== null)
  if (!found.length) return ''
  const [count, total] = [found.length, args.table.length].map(n => n.toLocaleString('en'))
  return `${count} of ${total} rows ${found.length === 1 ? 'is' : 'are'} not drawn: ${[...new Set(found)].join(', or ')}.`
}
