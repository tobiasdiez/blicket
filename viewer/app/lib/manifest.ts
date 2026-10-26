// The shape of manifest.json, spec 0.2, written by hand. The source of truth is the blicket
// package: src/blicket/manifest.py, model.py, errors.py and plots/_base.py.

export const SPEC = '0.2'

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

export interface PlotDefinition {
  type: string
  mapping: Record<string, string>
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
}

export interface BlickEntry {
  id: string | null
  name: string
  aliases: string[]
  group: string
  module: string | null
  source: Source | null
  definition: BlickDefinition | null
  /** The table's path relative to the build directory, when the Blick built. */
  data: string | null
  hash: string | null
  rows: number | null
  columns: TableSchema | null
  controls: Control[]
  timing_ms: number | null
  problems: Problem[]
  status: 'ok' | 'error'
}

export interface Group {
  name: string
  title: string | null
  tags: string[]
  modules: string[]
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
  config: { tolerance: number }
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
  problems: Problem[]
}

/** Where a definition or problem is, as `file:line`. */
export function sourceText(source: Source): string {
  return source.line ? `${source.file}:${source.line}` : source.file
}

/** A measure's name with the Blick's unit, as table headers show it: `value [t per year]`. */
export function withUnit(measure: string, unit: string | null): string {
  return unit ? `${measure} [${unit}]` : measure
}
