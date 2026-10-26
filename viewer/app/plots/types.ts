import type { TopLevelSpec } from 'vega-lite'
import type { YAxis } from '../lib/controls'
import type { TableSchema } from '../lib/manifest'
import type { Row } from '../lib/table'

export type Theme = 'light' | 'dark'

/**
 * What a chart draws on y: the Blick's measure, or its change against the baseline, absolute or
 * relative. It names what y is and nothing else: a chart of the measure that differs in
 * presentation only (legend, tooltips, size) gets an argument of its own, never a new value here.
 */
export type Quantity = 'measure' | 'change' | 'relative'

/** The change against the baseline that a chart under the chart of the measure draws. */
export type ChangeKind = Exclude<Quantity, 'measure'>

/**
 * What a chart is drawn from: the rows after the filters, the controls' other settings, and the
 * baseline's rows to draw behind them, which a plot type without a comparison ignores.
 */
export interface PlotArgs {
  table: Row[]
  schema: TableSchema
  /** The plot's channels, such as `x`, mapped to column names. */
  mapping: Record<string, string>
  /** The unit of the measure, if the Blick names one. */
  unit: string | null
  state: { splits: string[], y: YAxis }
  /** The baseline's rows after the same filters, when the chart is compared with a baseline. */
  baseline: Row[] | null
  theme: Theme
  /** The name exported images get, without extension. */
  name: string
}

/** The browser half of a plot type: draws into `el` and resolves to what removes the chart. */
export interface PlotType {
  render(args: PlotArgs & { el: HTMLElement }): Promise<() => void>
}

/**
 * How a plot type draws its change chart: the specification of a chart of `args`, whose measure
 * is the `kind` of change, `width` wide.
 */
export type ChangeBuilder = (args: PlotArgs, width: number, kind: ChangeKind) => TopLevelSpec
