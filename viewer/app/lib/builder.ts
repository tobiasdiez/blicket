// The Blick builder of `blicket dev`: what it offers, the request it sends, and its state in the
// URL. The shapes of the options and the request are those of src/blicket/query.py and
// src/blicket/dataset.py, written by hand.
import { SPLIT, Y, strings, type Query } from './controls'
import type { Dimension } from './manifest'
import { CHANNEL_LABELS } from './roles'
import { valueKey } from './table'

/** A quantity of the dataset, such as a flow, a stock or a parameter. */
export interface Quantity {
  /** Unique in the dataset, such as `flows/polymerization => primary_market`. */
  name: string
  title: string
  unit: string | null
  /** Names of the dataset's dimensions, in the model's order. */
  dimensions: string[]
  /** Whether summing over a dimension makes sense; an intensive quantity's are never summed. */
  additive: boolean
  group: string | null
}

export interface Channel {
  name: string
  kind: 'dimension' | 'measure'
  required: boolean
  doc: string
}

/** A plot type the builder offers, with its channels. */
export interface PlotOption {
  name: string
  channels: Channel[]
}

/** What the builder offers, as `dev/dataset` lists it: the quantities, the dimensions, the
 * plot types. */
export interface BuilderOptions {
  quantities: Quantity[]
  dimensions: Dimension[]
  plots: PlotOption[]
}

/** What the builder asks `dev/query` for: the body of the request. */
export interface BuilderRequest {
  quantities: string[]
  plot: string
  /** The plot's dimension channels, bound to dimensions. */
  mapping: Record<string, string>
  /** The dimensions kept besides the mapped ones; every other dimension is summed. */
  keep: string[]
  /** Per dimension, the values kept, as text; all of them when absent. */
  values: Record<string, string[]>
}

/** The dimension that tells several quantities apart; its values are their titles. */
const QUANTITY = 'Quantity'
const DEFAULT_PLOT = 'line'

/**
 * What a dimension does: a dimension channel of the plot (`x`, `color`, `linetype`, `source`,
 * `target`), one panel per value, a filter control, or summed over.
 */
export type Role = string
const PANELS = 'panels'
const FILTER = 'filter'
export const SUM = 'sum'

/** The builder's state, as the URL holds it. */
export interface BuilderState {
  quantities: string[]
  plot: string
  /** The plot's dimension channels, each bound to a dimension. */
  channels: Record<string, string>
  /** The dimensions kept that are on no channel: a filter, or on panels when in `splits`. */
  keep: string[]
  /** The kept dimensions drawn as panels: the Blick page's `_split`. */
  splits: string[]
  /** Per string or boolean dimension, the values kept as text; all of them when absent. */
  only: Record<string, string[]>
  /** Per integer, date or datetime dimension, the first and last value kept, as text. */
  from: Record<string, string>
  to: Record<string, string>
}

// The query keys of the builder. They start with an underscore, as every key that names no
// dimension does.
const Q = '_q'
const PLOT = '_plot'
const KEEP = '_keep'
const CHANNEL = '_c.'
const ONLY = '_only.'
const FROM = '_from.'
const TO = '_to.'

const RANGED: string[] = ['integer', 'date', 'datetime']

const unique = <T>(items: T[]) => [...new Set(items)]

/**
 * Who a query key belongs to: the builder's state, the controls of the chart (the filter values,
 * `_split`, `_y`), or the page (`_tab` and any other key with an underscore).
 */
export function owner(key: string): 'builder' | 'control' | 'page' {
  if (key === Q || key === PLOT || key === KEEP || [CHANNEL, ONLY, FROM, TO].some(prefix => key.startsWith(prefix))) return 'builder'
  if (!key.startsWith('_') || key === SPLIT || key === Y) return 'control'
  return 'page'
}

/** The state of an empty builder. */
export function emptyState(plot = DEFAULT_PLOT): BuilderState {
  return { quantities: [], plot, channels: {}, keep: [], splits: [], only: {}, from: {}, to: {} }
}

/** The builder's state in a route query. */
export function parseBuilder(query: Query): BuilderState {
  const state = emptyState(strings(query[PLOT])[0] ?? DEFAULT_PLOT)
  state.quantities = unique(strings(query[Q]))
  state.keep = unique(strings(query[KEEP]))
  state.splits = unique(strings(query[SPLIT]))
  for (const [key, entry] of Object.entries(query)) {
    const [first] = strings(entry)
    if (key.startsWith(CHANNEL) && first) state.channels[key.slice(CHANNEL.length)] = first
    else if (key.startsWith(ONLY)) state.only[key.slice(ONLY.length)] = unique(strings(entry))
    else if (key.startsWith(FROM) && first !== undefined) state.from[key.slice(FROM.length)] = first
    else if (key.startsWith(TO) && first !== undefined) state.to[key.slice(TO.length)] = first
  }
  return state
}

const listed = (items: string[]) => (items.length === 1 ? items[0]! : [...items])

/** The query keys of `state`: the builder's and `_split`. An empty values selection is a key
 * without a value. */
function builderEntries(state: BuilderState): Record<string, string | string[] | null> {
  const query: Record<string, string | string[] | null> = {}
  if (state.quantities.length) query[Q] = listed(state.quantities)
  if (state.plot !== DEFAULT_PLOT) query[PLOT] = state.plot
  for (const [channel, dimension] of Object.entries(state.channels)) query[CHANNEL + channel] = dimension
  if (state.keep.length) query[KEEP] = listed(state.keep)
  if (state.splits.length) query[SPLIT] = listed(state.splits)
  for (const [dimension, values] of Object.entries(state.only)) query[ONLY + dimension] = values.length ? listed(values) : null
  for (const [dimension, value] of Object.entries(state.from)) query[FROM + dimension] = value
  for (const [dimension, value] of Object.entries(state.to)) query[TO + dimension] = value
  return query
}

/** What a dimension does in `state`. */
export function roleOf(state: BuilderState, dimension: string): Role {
  const channel = Object.entries(state.channels).find(([, bound]) => bound === dimension)
  if (channel) return channel[0]
  if (state.splits.includes(dimension)) return PANELS
  if (state.keep.includes(dimension)) return FILTER
  return SUM
}

/**
 * The route query with the builder's state `next` in place of `previous`. The page's keys stay,
 * and so does the control state, but the value a filter showed of a dimension whose role
 * changed or that is no longer kept, and with `reset` all of it: the filters and the y axes.
 */
export function mergeBuilder(query: Query, previous: BuilderState, next: BuilderState, reset = false): Query {
  const kept: Query = {}
  for (const [key, entry] of Object.entries(query)) {
    const whose = owner(key)
    if (whose === 'builder' || key === SPLIT) continue // written from `next`
    if (whose === 'control' && (reset || (key !== Y && (roleOf(previous, key) !== roleOf(next, key) || roleOf(next, key) === SUM)))) continue
    kept[key] = entry
  }
  return { ...kept, ...builderEntries(next) }
}

/**
 * The route query with the control state of `controls`, as `queryFromState` writes it, in place
 * of the current one: the filters, `_split` and `_y` are replaced, the builder's keys and the
 * page's stay.
 */
export function mergeControls(query: Query, controls: Record<string, string | string[]>): Query {
  return { ...Object.fromEntries(Object.entries(query).filter(([key]) => owner(key) !== 'control')), ...controls }
}

/** The quantities of `state` that the dataset has, in the order picked. */
export function picked(state: BuilderState, options: BuilderOptions): Quantity[] {
  return state.quantities.flatMap(name => options.quantities.find(q => q.name === name) ?? [])
}

/** The dimension `Quantity` of several quantities: their titles, in the order picked. */
function quantityDimension(quantities: Quantity[]): Dimension {
  return { name: QUANTITY, dtype: 'string', values: quantities.map(q => q.title) }
}

/** A dimension of the form: whether every quantity picked has it. */
export interface FormDimension {
  dimension: Dimension
  shared: boolean
}

/**
 * The dimensions of the quantities picked, in the dataset's order, with `Quantity` first when
 * several are picked; its values are their titles.
 */
export function formDimensions(state: BuilderState, options: BuilderOptions): FormDimension[] {
  const quantities = picked(state, options)
  const rows = options.dimensions
    .filter(d => quantities.some(q => q.dimensions.includes(d.name)))
    .map(dimension => ({ dimension, shared: quantities.every(q => q.dimensions.includes(dimension.name)) }))
  if (quantities.length < 2) return rows
  return [{ dimension: quantityDimension(quantities), shared: true }, ...rows]
}

function channelsOf(options: BuilderOptions, plot: string): Channel[] {
  return options.plots.find(p => p.name === plot)?.channels.filter(c => c.kind === 'dimension') ?? []
}

/** Whether every quantity picked that has `dimension` may be summed over it. */
function summable(state: BuilderState, options: BuilderOptions, dimension: string): boolean {
  const quantities = picked(state, options)
  if (dimension === QUANTITY) return quantities.every(q => q.additive)
  return quantities.filter(q => q.dimensions.includes(dimension)).every(q => q.additive)
}

/** The required channel `dimension` holds, if any: one the form must not leave empty. */
export function requiredHeld(state: BuilderState, options: BuilderOptions, dimension: string): string | null {
  const role = roleOf(state, dimension)
  return channelsOf(options, state.plot).some(c => c.name === role && c.required) ? role : null
}

/** Why the role select of `dimension` offers no other role than channels, if it holds a
 * required one. */
export function requiredHint(state: BuilderState, options: BuilderOptions, dimension: string): string | null {
  const channel = requiredHeld(state, options, dimension)
  if (!channel) return null
  const label = CHANNEL_LABELS[channel] ?? channel
  return `${label} always has a dimension. To move ${dimension}, give another dimension the role ${label}.`
}

/**
 * The roles `dimension` may have: the plot's dimension channels, panels and filter, and sum when
 * every quantity having it is additive. A dimension that not every quantity picked has can only
 * be summed; one on a required channel can only swap with a dimension on another channel, so
 * the required one stays filled.
 */
export function rolesFor(state: BuilderState, options: BuilderOptions, row: FormDimension): Role[] {
  const name = row.dimension.name
  const sum = summable(state, options, name) ? [SUM] : []
  if (!row.shared) return sum
  const channels = channelsOf(options, state.plot).map(c => c.name)
  const required = requiredHeld(state, options, name)
  if (required) return [required, ...channels.filter(c => c !== required && state.channels[c])]
  return [...channels, PANELS, FILTER, ...sum]
}

/** `state` without anything about `dimension`: summed, and its values selection dropped too
 * with `values`. */
function cleared(state: BuilderState, dimension: string, values: boolean): BuilderState {
  const next: BuilderState = {
    ...state,
    channels: Object.fromEntries(Object.entries(state.channels).filter(([, bound]) => bound !== dimension)),
    keep: state.keep.filter(d => d !== dimension),
    splits: state.splits.filter(d => d !== dimension),
  }
  if (!values) return next
  const without = <T>(record: Record<string, T>) => Object.fromEntries(Object.entries(record).filter(([name]) => name !== dimension))
  return { ...next, only: without(state.only), from: without(state.from), to: without(state.to) }
}

/**
 * `state` with `dimension` in `role`, which is free. A dimension on panels is kept as a filter
 * is, and is in `splits` too, so that the control bar can turn it into a filter; a summed one has
 * no values selection.
 */
function placed(state: BuilderState, dimension: string, role: Role): BuilderState {
  const next = cleared(state, dimension, role === SUM)
  if (role === PANELS) return { ...next, keep: [...next.keep, dimension], splits: [...next.splits, dimension] }
  if (role === FILTER) return { ...next, keep: [...next.keep, dimension] }
  if (role === SUM) return next
  return { ...next, channels: { ...next.channels, [role]: dimension } }
}

/**
 * `state` with `dimension` in `role`. A channel another dimension holds is swapped: that one
 * takes the role `dimension` had, or becomes a filter when it cannot.
 */
export function setRole(state: BuilderState, options: BuilderOptions, dimension: string, role: Role): BuilderState {
  const previous = roleOf(state, dimension)
  if (previous === role) return state
  const holder = state.channels[role]
  let next = placed(state, dimension, role)
  if (holder && holder !== dimension) {
    const row = formDimensions(next, options).find(r => r.dimension.name === holder)
    if (!row) return normalized(cleared(next, holder, true), options) // a dimension of no quantity
    next = placed(next, holder, rolesFor(next, options, row).includes(previous) ? previous : FILTER)
  }
  return normalized(next, options)
}

/** `state` with the plot type `plot`; a dimension on a channel the plot lacks becomes a filter. */
export function setPlot(state: BuilderState, options: BuilderOptions, plot: string): BuilderState {
  const channels = channelsOf(options, plot).map(c => c.name)
  let next: BuilderState = { ...state, plot }
  for (const [channel, dimension] of Object.entries(state.channels)) {
    if (!channels.includes(channel)) next = placed(next, dimension, FILTER)
  }
  return normalized(next, options)
}

/** `plot` when the builder offers it, else the default: a link may name another. */
function offeredPlot(options: BuilderOptions, plot: string): string {
  return options.plots.some(p => p.name === plot) ? plot : DEFAULT_PLOT
}

/** The first dimension of `dimensions` that counts time or another order: an integer, date or
 * datetime one, else the first. */
function timeDimension(options: BuilderOptions, dimensions: string[]): string | undefined {
  const types = new Map(options.dimensions.map(d => [d.name, d.dtype as string]))
  return dimensions.find(name => RANGED.includes(types.get(name) ?? 'string')) ?? dimensions[0]
}

/**
 * The state for the quantities `names` picked in a fresh form: a chart of the type `plot`, a
 * line chart by default, with the time dimension on x, or a filter for a plot without x, every
 * other dimension summed for an additive quantity and a filter for an intensive one, and with
 * several quantities, `Quantity` on colour.
 */
export function defaults(options: BuilderOptions, names: string[], plot = DEFAULT_PLOT): BuilderState {
  let state: BuilderState = { ...emptyState(offeredPlot(options, plot)), quantities: names }
  const [first] = picked(state, options)
  if (!first) return state
  const time = timeDimension(options, first.dimensions)
  const onX = channelsOf(options, state.plot).some(c => c.name === 'x') ? time : undefined
  if (onX) state.channels.x = onX
  state.keep = first.dimensions.filter(d => d !== onX && (d === time || !first.additive))
  if (names.length > 1) state = withQuantityPlaced(state, options)
  return normalized(state, options)
}

/** `state` with `Quantity` on colour, else on line type, else on panels, whichever is free. */
function withQuantityPlaced(state: BuilderState, options: BuilderOptions): BuilderState {
  const channels = channelsOf(options, state.plot).map(c => c.name)
  const free = ['color', 'linetype'].find(channel => channels.includes(channel) && !state.channels[channel])
  return placed(state, QUANTITY, free ?? PANELS)
}

/** `state` with every dimension that not every quantity picked has summed, and nothing kept of
 * a dimension no quantity picked has. */
function normalized(state: BuilderState, options: BuilderOptions): BuilderState {
  let next = state
  const rows = formDimensions(state, options)
  const present = new Set(rows.map(row => row.dimension.name))
  for (const row of rows) {
    if (!row.shared && roleOf(next, row.dimension.name) !== SUM) next = cleared(next, row.dimension.name, true)
  }
  const mentioned = [...Object.values(next.channels), ...next.keep, ...next.splits, ...Object.keys(next.only), ...Object.keys(next.from), ...Object.keys(next.to)]
  for (const dimension of unique(mentioned)) {
    if (!present.has(dimension)) next = cleared(next, dimension, true)
  }
  return next
}

/**
 * The state after the quantity list changed to `names`, and whether it starts afresh, so that
 * the controls do too. The first pick, and a pick that keeps none of the quantities, starts from
 * the defaults, of the plot type chosen; adding a second quantity places `Quantity`, going back
 * to one drops it.
 */
export function pick(state: BuilderState, options: BuilderOptions, names: string[]): { state: BuilderState, reset: boolean } {
  if (!names.length) return { state: emptyState(state.plot), reset: true }
  if (!names.some(name => state.quantities.includes(name))) return { state: defaults(options, names, state.plot), reset: true }
  let next: BuilderState = { ...state, quantities: names, plot: offeredPlot(options, state.plot) }
  if (names.length > 1 && state.quantities.length < 2) next = withQuantityPlaced(next, options)
  return { state: normalized(next, options), reset: false }
}

/** The dimensions `state` keeps: those on channels, on panels and filters. */
function keptDimensions(state: BuilderState): string[] {
  return unique([...Object.values(state.channels), ...state.splits, ...state.keep])
}

/**
 * Why a quantity cannot join the quantities picked, or `null` when it can: it must have every
 * kept dimension, be summable over its others, share the unit and not the title, and be
 * additive when `Quantity` is summed. What the quantities picked share is worked out once, for a
 * list of thousands.
 */
export function joinable(state: BuilderState, options: BuilderOptions): (candidate: Quantity) => string | null {
  const quantities = picked(state, options)
  const titles = new Set(quantities.map(q => q.title))
  const kept = keptDimensions(state).filter(d => d !== QUANTITY)
  const unit = quantities.find(q => q.unit !== null)?.unit
  const quantitySummed = quantities.length > 1 && roleOf(state, QUANTITY) === SUM
  const intensivePicked = quantities.some(q => !q.additive)
  const named = options.dimensions.some(d => d.name === QUANTITY)
  return (candidate) => {
    if (!quantities.length || state.quantities.includes(candidate.name)) return null
    if (named) return `the dataset has a dimension called ${QUANTITY}`
    const missing = kept.find(d => !candidate.dimensions.includes(d))
    if (missing) return `needs ${missing}`
    const summed = candidate.dimensions.filter(d => !kept.includes(d))
    if (!candidate.additive && summed.length) return `not additive, so not summed over ${summed.join(', ')}`
    if (unit && candidate.unit && candidate.unit !== unit) return `in ${candidate.unit}, not ${unit}`
    if (titles.has(candidate.title)) return 'has the title of one picked'
    if (quantitySummed && (!candidate.additive || intensivePicked)) return `not additive, so not summed over ${QUANTITY}`
    return null
  }
}

/** Whether a dimension's values are kept as a range, not picked one by one. */
export const ranged = (dimension: Dimension) => RANGED.includes(dimension.dtype)

// Integers by number; dates and datetimes by their ISO text, which sorts as they do.
function compare(dimension: Dimension, a: string, b: string): number {
  if (dimension.dtype === 'integer') return Number(a) - Number(b)
  return a < b ? -1 : a > b ? 1 : 0
}

/** The values of `dimension` from `from` to `to`, as text; either end open when absent. */
export function inRange(dimension: Dimension, from: string | undefined, to: string | undefined): string[] {
  return dimension.values
    .map(value => valueKey(value, dimension.dtype))
    .filter(key => (from === undefined || compare(dimension, key, from) >= 0) && (to === undefined || compare(dimension, key, to) <= 0))
}

/** `state` with the values kept of `dimension`: `null` for all of them. */
export function setOnly(state: BuilderState, dimension: string, values: string[] | null): BuilderState {
  const only = { ...state.only }
  if (values === null) delete only[dimension]
  else only[dimension] = values
  return { ...state, only }
}

/** `state` with the range kept of `dimension`; an end that is `undefined` is open. */
export function setRange(state: BuilderState, dimension: string, from: string | undefined, to: string | undefined): BuilderState {
  const next = { ...state, from: { ...state.from }, to: { ...state.to } }
  if (from === undefined) delete next.from[dimension]
  else next.from[dimension] = from
  if (to === undefined) delete next.to[dimension]
  else next.to[dimension] = to
  return next
}

/**
 * The values kept of `dimension`, `undefined` for all of them. Values the URL names that the
 * dimension lacks are left out, and a list of nothing but such values keeps all of them, as no
 * list does; an empty list keeps none.
 */
export function keptValues(state: BuilderState, dimension: Dimension): string[] | undefined {
  const only = state.only[dimension.name]
  if (only === undefined || !only.length) return only
  const keys = new Set(dimension.values.map(value => valueKey(value, dimension.dtype)))
  const known = only.filter(value => keys.has(value))
  return known.length ? known : undefined
}

/** What the URL asks for that the dataset lacks: values of a dimension it does not have. */
export function notices(state: BuilderState, options: BuilderOptions): string[] {
  return formDimensions(state, options).flatMap(({ dimension }) => {
    const known = new Set(dimension.values.map(value => valueKey(value, dimension.dtype)))
    const unknown = (state.only[dimension.name] ?? []).filter(value => !known.has(value))
    return unknown.map(value => `${dimension.name} '${value}' is not in the dataset; it is left out`)
  })
}

/**
 * The request for `state`, or `null` without a quantity. The dimensions on panels are kept as
 * filters are, since a split is the viewer's; a range becomes the values in it, and values the
 * dimension lacks are left out.
 */
export function request(state: BuilderState, options: BuilderOptions): BuilderRequest | null {
  if (!state.quantities.length) return null
  const rows = new Map(formDimensions(state, options).map(row => [row.dimension.name, row.dimension]))
  const mapping = { ...state.channels }
  const mapped = new Set(Object.values(mapping))
  const keep = unique([...state.keep, ...state.splits]).filter(d => !mapped.has(d))
  const values: Record<string, string[]> = {}
  for (const name of [...mapped, ...keep]) {
    const dimension = rows.get(name)
    const only = dimension ? keptValues(state, dimension) : state.only[name]
    if (only !== undefined) values[name] = only
    else if (dimension && (state.from[name] !== undefined || state.to[name] !== undefined)) values[name] = inRange(dimension, state.from[name], state.to[name])
  }
  return { quantities: state.quantities, plot: state.plot, mapping, keep, values }
}

/**
 * What a chart of the request `asked` shows of its quantities, for a line under its title: the
 * dimensions summed over, and the values kept of each dimension that keeps fewer than all.
 */
export function subtitleParts(asked: BuilderRequest, options: BuilderOptions): string[] {
  const quantities = asked.quantities.flatMap(name => options.quantities.find(q => q.name === name) ?? [])
  const kept = new Set([...Object.values(asked.mapping), ...asked.keep])
  const summed = options.dimensions.map(d => d.name).filter(name => !kept.has(name) && quantities.some(q => q.dimensions.includes(name)))
  if (quantities.length > 1 && !kept.has(QUANTITY)) summed.unshift(QUANTITY)
  const parts = summed.length ? [`Summed over ${summed.join(', ')}`] : []
  for (const [name, values] of Object.entries(asked.values)) {
    const dimension = name === QUANTITY ? quantityDimension(quantities) : options.dimensions.find(d => d.name === name)
    const all = dimension?.values.length ?? values.length
    if (values.length === all) continue
    if (!values.length) parts.push(`${name}: none`)
    else if (dimension && ranged(dimension)) parts.push(`${name} ${values[0]}–${values.at(-1)}`)
    else if (values.length <= 3) parts.push(`${name}: ${values.join(', ')} (${values.length} of ${all})`)
    else parts.push(`${name}: ${values.length} of ${all}`)
  }
  return parts
}

/** A role as the form names it, with what it does to `dimension`. */
export function roleItem(role: Role, dimension: string): { label: string, description: string, value: Role } {
  const descriptions: Record<string, string> = {
    x: 'the horizontal axis',
    color: 'one colour per value',
    linetype: 'one dash pattern per value',
    source: 'the nodes flows leave',
    target: 'the nodes flows enter',
    [PANELS]: 'one panel per value',
    [FILTER]: 'pick the value above the chart',
    [SUM]: `add up over ${dimension}`,
  }
  return { label: CHANNEL_LABELS[role] ?? role, description: descriptions[role] ?? '', value: role }
}
