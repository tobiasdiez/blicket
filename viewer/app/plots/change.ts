// The charts under a compared Blick's chart: the change of each row against the baseline, in the
// Blick's unit or relative to the baseline, in the panels, x axis and series colours of the chart.
import type { TopLevelSpec } from 'vega-lite'
import type { Row } from '../lib/table'
import { definePlot } from './embed'
import { asNumber, baselineValues, cellKey, channels, PADDING, rowKey } from './layout'
import type { ChangeBuilder, ChangeKind, PlotArgs, PlotType } from './types'

// The data fields of a row's change and relative change.
const CHANGE = '__change'
const RELATIVE = '__relative'

// A divisor counts as 0 within this fraction of the largest value compared: the relative change
// against it is none. Numerical noise in a table lies many orders of magnitude below.
const ZERO = 1e-9

// The titles of the change charts, which exported images carry, in two parts that go on two
// lines where the chart is too narrow for one.
const TITLES: Record<ChangeKind, [string, string]> = {
  change: ['Change against the baseline,', 'current minus baseline'],
  relative: ['Relative change against the baseline,', 'as a share of the baseline\'s value'],
}
const TITLE_CHARACTER = 6 // px, about the width of a character of the 12 px title

/** What the change rows are made of: the rows after the filters, of both tables. */
export type Compared = Pick<PlotArgs, 'table' | 'baseline' | 'schema' | 'mapping'>

/** A row of either table, with the current and the baseline's value it compares, or none. */
type Pair = [row: Row, values: [current: number | null, baseline: number | null] | null]

/**
 * The change from `baseline` to `current`, and the relative change, that over the baseline's
 * absolute value. Null counts as 0 against a value, and both null is null. Against a baseline of
 * at most `zero`, the relative change is null, unless the current value is at most `zero` too:
 * then it is 0.
 */
function changes(current: number | null, baseline: number | null, zero: number): [change: number | null, relative: number | null] {
  if (current === null && baseline === null) return [null, null]
  const [to, from] = [current ?? 0, baseline ?? 0]
  const change = to - from
  if (Math.abs(from) > zero) return [change, change / Math.abs(from)]
  return [change, Math.abs(to) <= zero ? 0 : null]
}

/**
 * The rows of either table, each with the values it compares, as the diff routine compares them:
 * a row of one table only is compared with null, unless it has a dimension value the other table
 * lacks, which is a change of the schema, not of a value; such a row compares nothing. A value
 * counts as present when a row of the selection carries it, so under a filter a sparse table can
 * differ from the comparison's verdict on the whole tables.
 */
function pairs(args: Compared): Pair[] {
  const { y } = channels(args)
  const dims = args.schema.dimensions
  const baselineRows = args.baseline ?? []
  const baselineByKey = baselineValues(baselineRows, dims, y)
  const valuesOf = (rows: Row[]) => dims.map(d => new Set(rows.map(row => cellKey(row, d))))
  const [currentValueSets, baselineValueSets] = [valuesOf(args.table), valuesOf(baselineRows)]
  // Whether every dimension value of `row` occurs in the other table.
  const allIn = (row: Row, other: Set<string>[]) => dims.every((d, i) => other[i]!.has(cellKey(row, d)))
  const currentKeys = new Set(args.table.map(row => rowKey(row, dims)))
  const current = args.table.map((row): Pair => {
    const value = asNumber(row[y])
    const baselineValue = baselineByKey.get(rowKey(row, dims))
    if (baselineValue !== undefined) return [row, [value, baselineValue]]
    return [row, allIn(row, baselineValueSets) ? [value, null] : null]
  })
  const vanished = baselineRows
    .filter(row => !currentKeys.has(rowKey(row, dims)))
    .map((row): Pair => [row, allIn(row, currentValueSets) ? [null, asNumber(row[y])] : null])
  return [...current, ...vanished]
}

/**
 * The rows of either table, each with its change and its relative change (see `pairs`). A row
 * that compares nothing has neither: lines skip it, bars draw it with no height, so it keeps the
 * chart's panels and x values.
 */
export function changeRows(args: Compared): Row[] {
  const all = pairs(args)
  const largest = all.reduce((max, [, values]) => (values ? Math.max(max, Math.abs(values[0] ?? 0), Math.abs(values[1] ?? 0)) : max), 0)
  return all.map(([row, values]) => {
    const [change, relative] = values ? changes(values[0], values[1], ZERO * largest) : [null, null]
    return { ...row, [CHANGE]: change, [RELATIVE]: relative }
  })
}

/** Whether a row of the selection has a change, so that the change charts draw something. */
export function comparable(args: Compared): boolean {
  return pairs(args).some(([, values]) => values !== null && (values[0] !== null || values[1] !== null))
}

/** The arguments of the `kind` of change chart of `args`: its change rows, with the change as the measure. */
function changeArgs(args: PlotArgs, kind: ChangeKind): PlotArgs {
  const measure = kind === 'change' ? CHANGE : RELATIVE
  return {
    ...args,
    table: changeRows(args),
    baseline: null,
    schema: { ...args.schema, measures: [{ name: measure, dtype: 'float' }] },
    mapping: { ...args.mapping, y: measure },
    unit: kind === 'change' ? args.unit : null,
  }
}

/**
 * The `kind` of change chart of `args`, `width` wide, as a plot type's `build` draws it, with its
 * title, cut to the chart's width where even two lines do not fit.
 */
export function changeSpec(kind: ChangeKind, build: ChangeBuilder, args: PlotArgs, width: number): TopLevelSpec {
  const [head, tail] = TITLES[kind]
  const line = `${head} ${tail}`
  const room = width - PADDING
  const title = { text: line.length * TITLE_CHARACTER > room ? [head, tail] : line, limit: room }
  return { ...build(changeArgs(args, kind), width, kind), title } as TopLevelSpec
}

/** The browser half of the `kind` of change chart of a plot type that draws it with `build`. */
export function changePlot(kind: ChangeKind, build: ChangeBuilder): PlotType {
  return definePlot((args, width) => changeSpec(kind, build, args, width))
}

/** The name of the exported images of the `kind` of change chart of a chart named `name`. */
export function exportName(name: string, kind: ChangeKind): string {
  return `${name}_${kind === 'change' ? 'change' : 'relative_change'}`
}
