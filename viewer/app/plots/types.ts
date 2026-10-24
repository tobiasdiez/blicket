import type { YAxis } from '../lib/controls'
import type { TableSchema } from '../lib/manifest'
import type { Row } from '../lib/table'

export type Theme = 'light' | 'dark'

/** What a chart is drawn from: the rows after the filters, and the controls' other settings. */
export interface PlotArgs {
  table: Row[]
  schema: TableSchema
  /** The plot's channels, such as `x`, mapped to column names. */
  mapping: Record<string, string>
  /** The unit of the measure, if the Blick names one. */
  unit: string | null
  state: { splits: string[], y: YAxis }
  theme: Theme
  /** The name exported images get, without extension. */
  name: string
}

/** The browser half of a plot type: draws into `el` and resolves to what removes the chart. */
export interface PlotType {
  render(args: PlotArgs & { el: HTMLElement }): Promise<() => void>
}
