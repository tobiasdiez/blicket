// The shape of compare/<baseline id>/comparison.json, written by hand. The source of truth is the
// blicket package: BuildRef, BlickComparison and Comparison in src/blicket/comparison.py, Change
// in schema.py.
import { parseValue, type ControlState } from './controls'
import type { Repository, TableSchema, Value } from './manifest'
import { formatter, valueKey, type TableFile } from './table'

export type Flag = 'new' | 'removed' | 'schema' | 'value' | 'error'

/** How a Blick's current table differs from its baseline; no flags means unchanged. */
export interface Change {
  /** In the order of `Flag`. */
  flags: Flag[]
  /** The change of the rows both tables have, relative to the panel's scale, from 0 to 1. */
  magnitude: number | null
  /** Columns only one table has, with their types; a column whose type changed is in both. */
  columns_added: Record<string, string>
  columns_removed: Record<string, string>
  /** Per dimension, the values only one table has. */
  values_added: Record<string, Value[]>
  values_removed: Record<string, Value[]>
  /** The dimension values of the row, or the stack, that changed most. */
  where: Record<string, Value> | null
}

/** What a comparison records of a build. */
export interface BuildRef {
  id: string
  run: string
  profile: string
  created_at: string
  repository: Repository | null
  incomplete: boolean
}

export interface BlickComparison {
  /** The current id; the baseline id of a removed Blick. */
  id: string | null
  name: string
  /** The id of the baseline Blick compared, when it is another one, as for an alias. */
  matched: string | null
  change: Change
  /** Why an `error` Blick was not compared, or why a `new` one has no baseline table. */
  message: string | null
  /** The copy of the baseline table in the build directory, for Blicks flagged `value` or `schema`. */
  baseline_data: string | null
  baseline_hash: string | null
}

export interface Comparison {
  spec: string
  blicket: string
  created_at: string
  baseline: BuildRef
  current: BuildRef
  /** Why removed Blicks were not judged; empty when they were. */
  incomplete: string[]
  /** The current Blicks, then the removed ones. */
  blicks: BlickComparison[]
}

// The order of the flagged Blicks: the changed values first.
const ORDER: Flag[] = ['value', 'schema', 'new', 'removed', 'error']

/**
 * The comparisons to offer as a baseline: those whose baseline is a build of another run than the
 * current build's. A build of the same run is no baseline.
 */
export function offered(comparisons: Comparison[]): Comparison[] {
  return comparisons.filter(c => c.baseline.run !== c.current.run)
}

/** A magnitude to two significant digits, which the movers are ranked by. */
function twoDigits(magnitude: number | null): number {
  return Number((magnitude ?? 0).toPrecision(2))
}

/**
 * A magnitude as the percent of the chart's scale it is, to two significant digits: `2.1%`,
 * `100%`. `_percent` in src/blicket/report.py writes it for the reports.
 */
export const percent = formatter('.2~p')

/**
 * The flagged Blicks as the terminal ranks its movers: those flagged `value` by magnitude to two
 * significant digits, the largest first, then those flagged `schema`, `new`, `removed` and
 * `error`; by name where that leaves a tie.
 */
export function ranked(blicks: BlickComparison[]): BlickComparison[] {
  const rank = (b: BlickComparison) => ORDER.findIndex(flag => b.change.flags.includes(flag))
  const byName = (a: BlickComparison, b: BlickComparison) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0)
  return blicks
    .filter(b => b.change.flags.length)
    .toSorted((a, b) => rank(a) - rank(b) || twoDigits(b.change.magnitude) - twoDigits(a.change.magnitude) || byName(a, b))
}

/**
 * The badges of a Blick's flags: `Δ 2.1% of scale` for `value`, with a title that says what the
 * number is, and the flag itself for the others, `schema`, `new`, `removed`, `error`.
 */
export function badges(change: Change): { flag: Flag, label: string, title?: string }[] {
  return change.flags.map((flag) => {
    if (flag !== 'value') return { flag, label: flag }
    const share = percent(change.magnitude ?? 0)
    return { flag, label: `Δ ${share} of scale`, title: `largest change: ${share} of the largest value in its panel` }
  })
}

/** The Blicks per flag, as `9 unchanged · 1 value`, then whether removed was judged, the errors. */
export function counts(comparison: Comparison): string {
  const flagged = (flag: Flag) => comparison.blicks.filter(b => b.change.flags.includes(flag)).length
  const numbers: [string, number][] = [
    ['unchanged', comparison.blicks.filter(b => !b.change.flags.length).length],
    ...(['value', 'schema', 'new', 'removed'] as const).map((flag): [string, number] => [flag, flagged(flag)]),
  ]
  const parts = numbers.filter(([, n]) => n).map(([word, n]) => `${n} ${word}`)
  if (comparison.incomplete.length) parts.push('removed not judged')
  const errors = flagged('error')
  if (errors) parts.push(`${errors} ${errors === 1 ? 'error' : 'errors'}`)
  return parts.join(' · ')
}

/**
 * What tells a build apart, as the header names the current one: `run …` first, then `Blick code
 * 604e20c` and `uncommitted changes` when there is a repository, `built 2026-10-24 20:02 UTC`
 * unless `built` is false, and `incomplete` when a Blick module failed to import.
 */
export function buildParts(build: BuildRef, built = true): string[] {
  const repository = build.repository
  return [
    `run ${build.run}`,
    ...(repository ? [`Blick code ${repository.commit.slice(0, 7)}`] : []),
    ...(repository?.dirty ? ['uncommitted changes'] : []),
    ...(built ? [`built ${new Date(build.created_at).toISOString().slice(0, 16).replace('T', ' ')} UTC`] : []),
    ...(build.incomplete ? ['incomplete'] : []),
  ]
}

const quoted = (value: Value) => (typeof value === 'string' ? `'${value}'` : String(value))

function listing(items: string[]): string {
  return items.length > 5 ? `${items.slice(0, 5).join(', ')} and ${items.length - 5} more` : items.join(', ')
}

/** Something that appeared or vanished: its dimension, `null` for a column, the verb and the item. */
type Entry = [dimension: string | null, verb: 'appeared' | 'vanished', item: string]

const columnEntries = (found: Record<string, string>, verb: Entry[1]) => Object.entries(found).map(([name, dtype]): Entry => [null, verb, `'${name}' (${dtype})`])
const valueEntries = (found: Record<string, Value[]>, verb: Entry[1]) => Object.entries(found).flatMap(([name, all]) => all.map((value): Entry => [name, verb, quoted(value)]))

/** What appeared or vanished in a change: the columns, then the dimension values. */
function entries(change: Change): Entry[] {
  return [
    ...columnEntries(change.columns_added, 'appeared'),
    ...columnEntries(change.columns_removed, 'vanished'),
    ...valueEntries(change.values_added, 'appeared'),
    ...valueEntries(change.values_removed, 'vanished'),
  ]
}

/** `items` grouped by `key`, the groups and their items in the order first seen. */
function grouped<T>(items: T[], key: (item: T) => string): T[][] {
  const groups = new Map<string, T[]>()
  for (const item of items) groups.set(key(item), [...(groups.get(key(item)) ?? []), item])
  return [...groups.values()]
}

const subjectKey = ([dimension, verb]: Entry) => JSON.stringify([dimension, verb])
const columnWord = (items: string[]) => (items.length > 1 ? 'columns' : 'column')

/**
 * What appeared or vanished across the Blicks, with the number of Blicks: a line per dimension,
 * verb and number of Blicks, such as `Region 'ATLANTIS' appeared in 3 Blicks`, and the same for
 * columns, with their types. A dimension's lines are adjacent, the most Blicks first.
 */
export function schemaSummary(comparison: Comparison): string[] {
  const counted = grouped(comparison.blicks.flatMap(({ change }) => entries(change)), entry => JSON.stringify(entry))
    .map(same => ({ entry: same[0]!, blicks: same.length }))
  const lines: string[] = []
  for (const subject of grouped(counted, ({ entry }) => subjectKey(entry))) {
    for (const line of grouped(subject.toSorted((a, b) => b.blicks - a.blicks), ({ blicks }) => String(blicks))) {
      const [dimension, verb] = line[0]!.entry
      const items = line.map(({ entry }) => entry[2])
      const blicks = line[0]!.blicks
      const where = verb === 'appeared' ? 'appeared in' : 'vanished from'
      lines.push(`${dimension ?? columnWord(items)} ${listing(items)} ${where} ${blicks} ${blicks === 1 ? 'Blick' : 'Blicks'}`)
    }
  }
  return lines
}

/**
 * The columns and dimension values that appeared or vanished in a Blick, a line per dimension and
 * verb, such as `Parameter value 'incineration_rate' vanished`; the last line of the columns says
 * that the baseline is not drawn.
 */
export function schemaDetails(change: Change): string[] {
  const all = entries(change)
  const columns = detailLines(all.filter(([dimension]) => dimension === null))
  if (columns.length) columns[columns.length - 1] += '; baseline not drawn: the columns differ'
  return [...columns, ...detailLines(all.filter(([dimension]) => dimension !== null))]
}

function detailLines(found: Entry[]): string[] {
  return grouped(found, subjectKey).map((same) => {
    const [dimension, verb] = same[0]!
    const items = same.map(([, , item]) => item)
    const subject = dimension === null ? columnWord(items) : `${dimension} ${items.length > 1 ? 'values' : 'value'}`
    return `${subject} ${listing(items)} ${verb}`
  })
}

/** The baseline table to draw behind a Blick's chart: none without a copy, or when the columns changed. */
export function baselineTable(blick: BlickComparison): TableFile | null {
  const { columns_added: added, columns_removed: removed } = blick.change
  if (blick.baseline_data === null || Object.keys(added).length || Object.keys(removed).length) return null
  return { path: blick.baseline_data, hash: blick.baseline_hash }
}

/**
 * The control state that shows the row `where`: each filter set to the row's value of its
 * dimension, when the dimension has that value; the splits and the y axes kept. `null` when that
 * is `state` itself.
 */
export function whereState(state: ControlState, where: Record<string, Value>, schema: TableSchema): ControlState | null {
  const filters = { ...state.filters }
  let changed = false
  for (const dimension of schema.dimensions) {
    const shown = filters[dimension.name]
    if (shown === undefined || !(dimension.name in where)) continue
    const value = parseValue(dimension, String(where[dimension.name]))
    if (value === undefined || valueKey(value, dimension.dtype) === valueKey(shown, dimension.dtype)) continue
    filters[dimension.name] = value
    changed = true
  }
  return changed ? { ...state, filters } : null
}

/**
 * The row `where` in the order a reader finds it: the filtered values, the panel, the series and
 * the x value, each with its dimension, such as `Region SSA, Flow Primary, Time 2100`.
 */
export function whereText(where: Record<string, Value>, state: ControlState, mapping: Record<string, string>): string {
  const order = new Set([...Object.keys(state.filters), ...state.splits, mapping.color, mapping.linetype, mapping.x])
  return [...order]
    .filter((name): name is string => name !== undefined && name in where)
    .map(name => `${name} ${String(where[name])}`)
    .join(', ')
}
