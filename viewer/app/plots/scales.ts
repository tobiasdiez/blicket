// The axis scales of a plot: a logarithmic axis's encoding, and what it does to the data. It has
// no place for a value at or below zero, so the chart draws such a value as missing.
import * as vega from 'vega'
import { formatValue, type Cell, type Row } from '../lib/table'
import type { Spec } from './layout'
import type { PlotArgs } from './types'

type Scaled = Pick<PlotArgs, 'mapping' | 'scales'>

// A logarithmic axis ticks every multiple of a power of ten while it spans fewer powers than its
// tick count, and labels some of them, the others with an empty label. Only the labelled ticks
// get a grid line, so the unlabelled multiples do not crowd the plot.
const UNLABELLED = 'datum.label === \'\''
const LOG_GRID = { gridOpacity: { condition: { test: UNLABELLED, value: 0 }, value: 1 } }
// The labels of an axis without an integer format, as of a measure, are formatted each by itself,
// since the axis's format suits one magnitude while a logarithmic axis spans many, `0.001` to
// `10k`; with up to six significant digits, which a tick, a round number, needs only where the
// axis is narrow: `100.2`, not `100`.
const PER_TICK = 'blicketTick'
vega.expressionFunction(PER_TICK, (value: number) => formatValue(value, 6))
const LOG_LABELS = { labelExpr: `${UNLABELLED} ? '' : ${PER_TICK}(datum.value)` }

// The room per tick of a logarithmic axis, in px, as Vega-Lite gives a linear axis.
const TICK_ROOM = 40

/**
 * `encoding` on the scale the plot gives the axis of `channel`, which is `extent` px long. A
 * linear axis keeps it as it is; a logarithmic axis
 * - says so in its title: "(log scale)", or "(log)" in a panel, where a y title longer than the
 *   panel would push the shared x axis down;
 * - ends at the data, not at the powers of ten around it, so that narrow data fills the plot;
 * - unless it has an integer format, has a tick per 40 px of its `extent`, when given, and labels
 *   written each by itself.
 */
export function scaled(encoding: Spec, args: Pick<PlotArgs, 'scales' | 'state'>, channel: string, extent?: number): Spec {
  if (args.scales?.[channel] !== 'log') return encoding
  const { zero: _, ...scale } = (encoding.scale as Spec | undefined) ?? {}
  const axis = (encoding.axis as Spec | undefined) ?? {}
  const suffix = args.state.splits.length ? 'log' : 'log scale'
  const title = typeof encoding.title === 'string' ? { title: `${encoding.title} (${suffix})` } : {}
  const own = axis.format === 'd' ? {} : { ...LOG_LABELS, ...(extent === undefined ? {} : { tickCount: Math.ceil(extent / TICK_ROOM) }) }
  return { ...encoding, ...title, scale: { ...scale, type: 'log', nice: false }, axis: { ...axis, ...LOG_GRID, ...own } }
}

/** Whether a cell has no place on a logarithmic axis: a number at or below zero. */
export function belowZero(cell: Cell | undefined): boolean {
  return typeof cell === 'number' && cell <= 0
}

/** The channels that the plot draws on a logarithmic axis, each with its column. */
export function logChannels(args: Scaled): [channel: string, column: string][] {
  return Object.entries(args.scales ?? {}).flatMap(([channel, scale]) => {
    const column = args.mapping[channel]
    return scale === 'log' && column ? [[channel, column] as [string, string]] : []
  })
}

/** `rows` with their values at or below zero on a logarithmic axis as null, missing values; `rows` itself without such an axis. */
export function masked(args: Scaled, rows: Row[]): Row[] {
  const columns = logChannels(args).map(([, column]) => column)
  if (!columns.length) return rows
  return rows.map((row) => {
    const off = columns.filter(column => belowZero(row[column]))
    return off.length ? { ...row, ...Object.fromEntries(off.map(column => [column, null])) } : row
  })
}
