import type { Control, Dimension, TableSchema, Value } from './manifest'
import { valueKey } from './table'

/** Whether split panels share their y axis or each has its own. */
export type YAxis = 'shared' | 'independent'

/** What the controls of a Blick are set to. */
export interface ControlState {
  /** The value shown, per dimension that is shown one value at a time. */
  filters: Record<string, Value>
  /** The dimensions drawn as one panel per value, in the order of the controls. */
  splits: string[]
  y: YAxis
}

/** A route query, as vue-router gives it. */
export type Query = Record<string, string | null | (string | null)[] | undefined>

// The query keys that are not dimensions start with an underscore, so that a dimension called
// `split` or `y` has its own key.
const SPLIT = '_split'
const Y = '_y'

function strings(entry: Query[string]): string[] {
  const list = Array.isArray(entry) ? entry : [entry]
  return list.filter((item): item is string => typeof item === 'string')
}

/** The value of `dimension` that `text` names, parsed by the dimension's type, if there is one. */
export function parseValue(dimension: Dimension, text: string): Value | undefined {
  const key = valueKey(text, dimension.dtype)
  return dimension.values.find(value => valueKey(value, dimension.dtype) === key)
}

/** A control's default, or the first value when the build recorded none. */
function fallback(control: Control, dimension: Dimension | undefined): Value | undefined {
  return control.default ?? dimension?.values[0]
}

/** A control state read from a query, with what in the query was not used. */
export interface Parsed {
  state: ControlState
  /** Values the query names that a dimension lacks, each with the value shown instead. */
  notices: string[]
  /** Query keys without an underscore, and `_split` entries, that name no control. */
  unknown: string[]
}

/**
 * The control state a query asks for. A dimension listed under `_split` is split, one given as
 * `dim=value` is filtered on that value, and any other has its control's kind and default;
 * values that the dimension lacks fall back to the default. `_y` is `shared` or `independent`;
 * without it the y axes are `defaultY`. Other keys with an underscore belong to the page.
 */
export function stateFromQuery(controls: Control[], schema: TableSchema, query: Query, defaultY: YAxis = 'shared'): Parsed {
  const dimensions = new Map(schema.dimensions.map(dimension => [dimension.name, dimension]))
  const names = new Set(controls.map(control => control.dimension))
  const splitAsked = strings(query[SPLIT])
  const [y] = strings(query[Y])
  const state: ControlState = {
    filters: {},
    splits: [],
    y: y === 'independent' || y === 'shared' ? y : defaultY,
  }
  const notices: string[] = []
  const unknown = [
    ...Object.keys(query).filter(key => !key.startsWith('_') && !names.has(key)),
    ...splitAsked.filter(name => !names.has(name)).map(name => `${SPLIT}=${name}`),
  ]
  for (const control of controls) {
    const dimension = dimensions.get(control.dimension)
    const [text] = strings(query[control.dimension])
    const asked = dimension && text !== undefined ? parseValue(dimension, text) : undefined
    const split = splitAsked.includes(control.dimension) || (control.kind === 'split' && text === undefined)
    if (split) {
      state.splits.push(control.dimension)
      continue
    }
    const value = asked ?? fallback(control, dimension)
    if (value === undefined) continue
    state.filters[control.dimension] = value
    if (text !== undefined && asked === undefined) {
      notices.push(`${control.dimension} '${text}' is not in this build; showing ${String(value)}`)
    }
  }
  return { state, notices, unknown }
}

/**
 * The query that reproduces `state`: every filter as `dim=value`, the splits under `_split`, and
 * `_y` when there are panels and their axes differ from `defaultY`.
 */
export function queryFromState(schema: TableSchema, state: ControlState, defaultY: YAxis = 'shared'): Record<string, string | string[]> {
  const query: Record<string, string | string[]> = {}
  for (const dimension of schema.dimensions) {
    const value = state.filters[dimension.name]
    if (value !== undefined) query[dimension.name] = valueKey(value, dimension.dtype)
  }
  if (state.splits.length === 1) query[SPLIT] = state.splits[0]!
  else if (state.splits.length > 1) query[SPLIT] = [...state.splits]
  if (state.splits.length && state.y !== defaultY) query[Y] = state.y
  return query
}

/** `state` with `dimension` shown at `value`. */
export function withFilter(state: ControlState, dimension: string, value: Value): ControlState {
  return { ...state, filters: { ...state.filters, [dimension]: value } }
}

/** `state` with `dimension` split into panels, in the order of the controls. */
export function withSplit(state: ControlState, controls: Control[], dimension: string): ControlState {
  const filters = Object.fromEntries(Object.entries(state.filters).filter(([name]) => name !== dimension))
  const splits = controls.map(c => c.dimension).filter(d => d === dimension || state.splits.includes(d))
  return { ...state, filters, splits }
}

/** `state` with `dimension` no longer split: a filter at its control's default. */
export function withoutSplit(state: ControlState, controls: Control[], schema: TableSchema, dimension: string): ControlState {
  const control = controls.find(c => c.dimension === dimension)
  const value = control && fallback(control, schema.dimensions.find(d => d.name === dimension))
  const splits = state.splits.filter(d => d !== dimension)
  const filters = value === undefined ? state.filters : { ...state.filters, [dimension]: value }
  return { ...state, splits, filters }
}
