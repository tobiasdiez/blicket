// The shape of manifest.json, spec 0.3, written by hand. The source of truth is the blicket
// package: src/blicket/manifest.py, model.py, the expect/ package, errors.py and plots/_base.py.

export const SPEC = '0.3'
/** The specs this viewer reads: 0.2 lacks the checks, levels and outcomes, which `normalized` fills in. */
export const READS = ['0.2', SPEC] as const

export type DimensionType = 'string' | 'integer' | 'boolean' | 'date' | 'datetime'
/** A dimension value as JSON holds it; dates and datetimes are ISO strings. */
export type Value = string | number | boolean

export interface Dimension {
  name: string
  dtype: DimensionType
  values: Value[]
}

export interface Measure {
  name: string
  dtype: 'float'
}

export interface TableSchema {
  dimensions: Dimension[]
  measures: Measure[]
}

export type ControlKind = 'filter' | 'split'

/** What the viewer offers for a dimension the plot leaves unbound, as the build derived it. */
export interface Control {
  dimension: string
  kind: ControlKind
  default: Value | null
}

export interface Source {
  file: string
  line: number | null
}

export interface Problem {
  kind: string
  severity: 'error' | 'warning'
  source: Source | null
  module: string | null
  ids: string[]
  message: string
  traceback: string | null
}

/** How an axis maps values to positions; `linear` is every axis's default. */
export type Scale = 'linear' | 'log'

export interface PlotDefinition {
  type: string
  mapping: Record<string, string>
  /** The scales of the channels whose axis is not linear, such as `{ x: 'log' }`; without it, every axis is linear. */
  scales?: Record<string, Scale>
}

/** What a failed expectation is: not evaluated, a warning, or an error that fails the build. */
export type Level = 'off' | 'warn' | 'error'
/** What the evaluation of an expectation gave; `error` when it could not be evaluated. */
export type Result = 'met' | 'warning' | 'failed' | 'error'

/** An expectation as declared, `bk.expect.*`; a `rows` function by its name. */
export type ExpectationRecord =
  | { kind: 'no_rows', rows: string | null, by: string | null, warn_within: number | null }
  | { kind: 'at_most' | 'at_least', on: string | null, bound: number, warn_within: number | null }
  | { kind: 'between', on: string | null, low: number, high: number, warn_within: number | null }

/** What the evaluation of a unit's expectation on its table gave. */
export interface Outcome {
  result: Result
  /** The expectation in words, the measure resolved: `value between 0 and 1`. */
  expectation: string
  /** The rows a bound was applied to; `null` for `no_rows`. */
  evaluated: number | null
  /** The rows that offend, and those of them within `warn_within`. */
  offending: number
  within: number
  /** The value of the row with the largest distance, and that distance; `null` when nothing ranks the rows. */
  worst: number | null
  distance: number | null
  /** The dimension values of the worst row, or the first, without the null ones. */
  where: Record<string, Value> | null
  /** Why the result is `error`. */
  message: string | null
}

export interface BlickDefinition {
  title: string
  description: string | null
  /** The unit of the measure, such as `t per year`. */
  unit: string | null
  tags: string[]
  plot: PlotDefinition
  /** Whether the panels of a split have their own y axis by default. */
  independent_y: boolean
  /** The control kinds the author asked for; the derived controls are `BlickEntry.controls`. */
  controls: Record<string, ControlKind>
  defaults: Record<string, unknown>
  tolerance: number | null
  dims: string[] | null
  measures: string[] | null
  order: Record<string, Value[]>
  /** The level the Blick gives itself; its entry has the level it has. */
  level: Level | null
  expect: ExpectationRecord | null
}

export interface CheckDefinition {
  title: string
  description: string | null
  tags: string[]
  level: Level | null
  /** `no_rows` unless the check names another. */
  expect: ExpectationRecord
  dims: string[] | null
  measures: string[] | null
}

/** What became of a unit in a build: it built a table, its transformation skipped the run (or a check's level is off), or it failed. */
export const STATUSES = ['ok', 'skipped', 'error'] as const
export type Status = typeof STATUSES[number]

/** Whether `value` is one of `STATUSES`. */
export const isStatus = (value: unknown): value is Status => (STATUSES as readonly unknown[]).includes(value)

/** What a Blick's and a check's entries have in common. */
interface Entry {
  id: string | null
  name: string
  aliases: string[]
  group: string
  module: string | null
  source: Source | null
  /** The level the unit has: its own, its group's or the project's; `null` in a build of spec 0.2. */
  level: Level | null
  /** The table's path relative to the build directory, when the unit stored one. */
  data: string | null
  hash: string | null
  rows: number | null
  columns: TableSchema | null
  /** The outcome of the unit's expectation; `null` without one, at level `off`, without a table, or skipped. */
  outcome: Outcome | null
  timing_ms: number | null
  /** Why the transformation skipped the run with `bk.Skip`, or that a check's level is off; such a unit has no table or problems. */
  skipped: string | null
  problems: Problem[]
  /** `skipped` when `skipped` is set, else `error` when a problem is an error, else `ok`. */
  status: Status
}

export interface BlickEntry extends Entry {
  /** Not in the file: `normalized` tags each entry with the list it came from. */
  kind: 'Blick'
  definition: BlickDefinition | null
  controls: Control[]
}

/**
 * A check's entry: its table is the offending rows, worst first, at most as many as the build
 * stores, so `rows` may be fewer than `outcome.offending`; a met check stores none.
 */
export interface CheckEntry extends Entry {
  /** Not in the file: `normalized` tags each entry with the list it came from. */
  kind: 'check'
  definition: CheckDefinition | null
}

/** A unit of either kind, as the overview and the sidebar list them. */
export type UnitEntry = BlickEntry | CheckEntry

export interface Group {
  name: string
  title: string | null
  tags: string[]
  modules: string[]
  /** The level of the group's units that give none. */
  level: Level | null
}

/** The state of the git repository holding the Blick code when the build ran. */
export interface Repository {
  commit: string
  branch: string | null
  dirty: boolean
}

export interface Manifest {
  spec: string
  blicket: string
  created_at: string
  build: { id: string, incomplete: boolean, loader_ms: number }
  config: { tolerance: number, level: Level }
  run: {
    id: string
    profile: string
    fingerprint: string
    commit: string | null
    branch: string | null
    dirty: boolean | null
    paths: string[]
  }
  repository: Repository | null
  groups: Group[]
  blicks: BlickEntry[]
  checks: CheckEntry[]
  problems: Problem[]
}

/** An entry with the fields a build of spec 0.2 lacks: no level and no outcome. */
const upgraded = <E extends Entry>(e: E) => ({ ...e, level: e.level ?? null, outcome: e.outcome ?? null })

/** Whether a build of this `spec` can be shown. */
export const reads = (spec: string): boolean => (READS as readonly string[]).includes(spec)

/**
 * A manifest as this viewer reads it: every entry tagged with its `kind`, from the list it is in,
 * and one of spec 0.2, which has no checks, levels or outcomes, with them filled in as a build of
 * spec 0.3 would have them, every unit without an expectation.
 */
export function normalized(manifest: Manifest): Manifest {
  return {
    ...manifest,
    config: { ...manifest.config, level: manifest.config.level ?? 'error' },
    groups: manifest.groups.map(group => ({ ...group, level: group.level ?? null })),
    blicks: manifest.blicks.map(b => ({
      ...upgraded(b),
      kind: 'Blick' as const,
      definition: b.definition && { ...b.definition, level: b.definition.level ?? null, expect: b.definition.expect ?? null },
    })),
    checks: (manifest.checks ?? []).map(c => ({ ...upgraded(c), kind: 'check' as const })),
  }
}

/** The units of a build, its Blicks, then its checks. */
export function units(manifest: Pick<Manifest, 'blicks' | 'checks'>): UnitEntry[] {
  return [...manifest.blicks, ...manifest.checks]
}

/** The entries of each status, each list in the order of `entries`. */
export function byStatus<E extends UnitEntry>(entries: readonly E[]): Record<Status, E[]> {
  const found: Record<Status, E[]> = { ok: [], skipped: [], error: [] }
  for (const entry of entries) found[entry.status].push(entry)
  return found
}

/** Whether an entry is a check's, as `normalized` tagged it. */
export function isCheck(entry: UnitEntry): entry is CheckEntry {
  return entry.kind === 'check'
}

/** The page of a unit: `/blick/<id>` or `/check/<id>`; `null` for one without an id. */
export function unitPath(entry: UnitEntry): string | null {
  return entry.id === null ? null : `/${isCheck(entry) ? 'check' : 'blick'}/${entry.id}`
}

/** The first line of a text, such as the reason a Blick was skipped; empty for none. */
export function firstLine(text: string | null): string {
  return text?.split(/\r?\n/, 1)[0] ?? ''
}

/** Where a definition or problem is, as `file:line`. */
export function sourceText(source: Source): string {
  return source.line ? `${source.file}:${source.line}` : source.file
}

/** A measure's name with the Blick's unit, as table headers show it: `value [t per year]`. */
export function withUnit(measure: string, unit: string | null): string {
  return unit ? `${measure} [${unit}]` : measure
}

/**
 * The unit of a measure column, as tables show it: the Blick's unit is the unit of the measure on
 * y, so another measure, such as a scatter's x, has none; for a plot that binds no column to y,
 * every measure has it.
 */
export function unitOf(measure: string, unit: string | null, mapping: Record<string, string>): string | null {
  return mapping.y === undefined || mapping.y === measure ? unit : null
}
