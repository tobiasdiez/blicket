// The flows of the Sankey tests: a small material system over two years, with a loop.
import type { Dimension } from '../app/lib/manifest'
import type { Row } from '../app/lib/table'
import type { Extent } from '../app/plots/sankey_graph'
import type { PlotArgs, Theme } from '../app/plots/types'

export const time: Dimension = { name: 'Time', dtype: 'integer', values: [2050, 2100] }
export const from: Dimension = { name: 'From', dtype: 'string', values: ['Production', 'Use', 'End of life', 'Recycling', 'Import', 'Landfill'] }
export const to: Dimension = { name: 'To', dtype: 'string', values: ['Use', 'End of life', 'Recycling', 'Landfill', 'Production', 'Import'] }
export const stage: Dimension = { name: 'Stage', dtype: 'string', values: ['Production', 'Use', 'End of life', 'Recycling'] }
// The flows of 2050, ten times as large in 2100: a loop through recycling back to production, two
// stages between Production and Use, and a missing, a negative and a zero value.
export const FLOWS: [string, string, string, number | null][] = [
  ['Production', 'Use', 'Use', 10],
  ['Production', 'Use', 'Recycling', 2],
  ['Use', 'End of life', 'End of life', 8],
  ['End of life', 'Recycling', 'Recycling', 3],
  ['End of life', 'Landfill', 'End of life', 5],
  ['Recycling', 'Production', 'Recycling', 3],
  ['Use', 'Landfill', 'End of life', null],
  ['Recycling', 'Landfill', 'Recycling', -1],
  ['Use', 'Recycling', 'Recycling', 0],
]
export const EXTENT: Extent = [[24, 12], [576, 468]]

export interface SankeyOptions {
  splits?: string[]
  y?: 'shared' | 'independent'
  theme?: Theme
  color?: boolean
  /** Rows added to the flows of 2050. */
  extra?: [string, string, string, number | null][]
  /** The baseline's value of a flow of the current `value`; without it, no baseline. */
  baseline?: (value: number | null, row: Row) => number | null
}

/** Sankey arguments for the flows of both years, or of 2050 alone without a split, as a filter leaves them. */
export function flows(options: SankeyOptions = {}): PlotArgs {
  const splits = options.splits ?? []
  const years = splits.includes('Time') ? [2050, 2100] : [2050]
  const all = [...FLOWS, ...(options.extra ?? [])]
  const table: Row[] = years.flatMap(Time => all.map(([From, To, Stage, value]) => ({ Time, From, To, Stage, value: value === null || Time === 2050 ? value : value * 10 })))
  const baseline = options.baseline
  return {
    table,
    baseline: baseline ? table.map(row => ({ ...row, value: baseline(row.value as number | null, row) })) : null,
    schema: { dimensions: [time, from, to, stage], measures: [{ name: 'value', dtype: 'float' }] },
    mapping: { source: 'From', target: 'To', value: 'value', ...(options.color === false ? {} : { color: 'Stage' }) },
    unit: 't',
    state: { splits, y: options.y ?? 'shared' },
    theme: options.theme ?? 'light',
    name: 'test',
  }
}
