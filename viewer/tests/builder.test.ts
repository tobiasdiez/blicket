import { describe, expect, it } from 'vitest'
import {
  defaults,
  emptyState,
  formDimensions,
  inRange,
  joinable,
  keptValues,
  mergeBuilder,
  mergeControls,
  notices,
  owner,
  parseBuilder,
  pick,
  request,
  requiredHeld,
  requiredHint,
  roleOf,
  rolesFor,
  setOnly,
  setPlot,
  setRange,
  setRole,
  subtitleParts,
  type BuilderOptions,
  type BuilderState,
  type Quantity,
} from '../app/lib/builder'
import type { Dimension } from '../app/lib/manifest'

const line = { name: 'line', channels: [
  { name: 'x', kind: 'dimension' as const, required: true, doc: '' },
  { name: 'y', kind: 'measure' as const, required: true, doc: '' },
  { name: 'color', kind: 'dimension' as const, required: false, doc: '' },
  { name: 'linetype', kind: 'dimension' as const, required: false, doc: '' },
] }
const bar = { name: 'bar', channels: line.channels.slice(0, 3) }

function quantity(name: string, fields: Partial<Quantity> = {}): Quantity {
  return { name, title: name.split('/').at(-1)!, unit: 't', dimensions: ['Time', 'Region', 'Polymer'], additive: true, group: name.split('/')[0]!, ...fields }
}

const options: BuilderOptions = {
  quantities: [
    quantity('flows/production'),
    quantity('flows/recycling'),
    quantity('flows/imports', { dimensions: ['Time', 'Region'] }),
    quantity('stocks/use', { unit: 'Mt' }),
    quantity('parameters/rate', { unit: 'fraction', dimensions: ['Time', 'Region'], additive: false }),
  ],
  dimensions: [
    { name: 'Time', dtype: 'integer', values: [2020, 2021, 2022, 2023] },
    { name: 'Region', dtype: 'string', values: ['LAM', 'SSA', 'EUR'] },
    { name: 'Polymer', dtype: 'string', values: ['PE', 'PP'] },
  ],
  plots: [line, bar],
}

const one = defaults(options, ['flows/production'])

/** The state after a pick. */
const picking = (state: BuilderState, names: string[]) => pick(state, options, names).state

/** The roles offered per dimension of the form. */
const rows = (state: BuilderState) => new Map(formDimensions(state, options).map(row => [row.dimension.name, rolesFor(state, options, row)]))

/** Why each quantity can or cannot join. */
const incompatibility = (state: BuilderState, candidate: Quantity) => joinable(state, options)(candidate)

describe('the defaults of a pick', () => {
  it('draws a line of the total over time for an additive quantity', () => {
    expect(one).toEqual({ ...emptyState(), quantities: ['flows/production'], channels: { x: 'Time' } })
    expect(request(one, options)).toEqual({ quantities: ['flows/production'], plot: 'line', mapping: { x: 'Time' }, keep: [], values: {} })
  })

  it('keeps the dimensions of an intensive quantity as filters', () => {
    const rate = picking(one, ['parameters/rate'])
    expect(rate.channels).toEqual({ x: 'Time' })
    expect(rate.keep).toEqual(['Region'])
  })

  it('puts Quantity on colour for a second quantity and drops it again', () => {
    const two = picking(one, ['flows/production', 'flows/recycling'])
    expect(two.channels).toEqual({ x: 'Time', color: 'Quantity' })
    expect(formDimensions(two, options).map(row => row.dimension.name)).toEqual(['Quantity', 'Time', 'Region', 'Polymer'])
    expect(formDimensions(two, options)[0]!.dimension.values).toEqual(['production', 'recycling'])
    expect(picking(two, ['flows/recycling']).channels).toEqual({ x: 'Time' })
    const colour = setRole(one, options, 'Polymer', 'color')
    expect(picking(colour, ['flows/production', 'flows/recycling']).channels).toEqual({ x: 'Time', color: 'Polymer', linetype: 'Quantity' })
  })

  it('keeps the plot type chosen when it starts afresh', () => {
    const bars = setPlot(emptyState(), options, 'bar')
    expect(pick(bars, options, ['flows/production']).state.plot).toBe('bar')
    const removed = pick(setPlot(one, options, 'bar'), options, []).state
    expect(picking(removed, ['flows/recycling']).plot).toBe('bar')
    expect(mergeBuilder({}, emptyState(), picking(removed, ['flows/recycling']))._plot).toBe('bar') // in the URL
  })

  it('falls back to a line chart for a plot type the builder does not offer', () => {
    const pie = { ...emptyState(), plot: 'pie' }
    expect(pick(pie, options, ['flows/production']).state.plot).toBe('line')
    expect(picking({ ...one, plot: 'pie' }, ['flows/production', 'flows/recycling']).plot).toBe('line')
  })

  it('starts afresh, the controls too, when no quantity picked before stays', () => {
    const changed = setRole(one, options, 'Region', 'color')
    expect(pick(changed, options, ['flows/recycling'])).toEqual({ state: defaults(options, ['flows/recycling']), reset: true })
    expect(pick(changed, options, [])).toEqual({ state: emptyState(), reset: true })
    expect(pick(changed, options, ['flows/production', 'flows/recycling']).reset).toBe(false)
  })

  it('forgets what it kept of a dimension that no quantity left has', () => {
    const two = setOnly(setRole(picking(one, ['flows/production', 'flows/imports']), options, 'Region', 'panels'), 'Region', ['LAM'])
    const imports = picking(two, ['flows/imports'])
    expect(imports.keep).toEqual(['Region'])
    expect(imports.only).toEqual({ Region: ['LAM'] })
    expect(formDimensions(picking(two, ['flows/production']), options).map(row => row.dimension.name)).toEqual(['Time', 'Region', 'Polymer'])
  })
})

describe('the roles of the dimensions', () => {
  it('swaps a channel another dimension holds', () => {
    const colour = setRole(one, options, 'Polymer', 'color')
    expect(roleOf(colour, 'Polymer')).toBe('color')
    const swapped = setRole(colour, options, 'Polymer', 'x')
    expect(swapped.channels).toEqual({ x: 'Polymer', color: 'Time' })
    const panels = setRole(setRole(one, options, 'Region', 'panels'), options, 'Region', 'x')
    expect(roleOf(panels, 'Time')).toBe('panels')
  })

  it('offers sum only where every quantity having the dimension is additive, and only sum where not every quantity has it', () => {
    expect(rows(one).get('Region')).toEqual(['x', 'color', 'linetype', 'panels', 'filter', 'sum'])
    expect(rows(setPlot(one, options, 'bar')).get('Region')).toEqual(['x', 'color', 'panels', 'filter', 'sum'])
    expect(rows(picking(one, ['parameters/rate'])).get('Region')).toEqual(['x', 'color', 'linetype', 'panels', 'filter'])
    const mixed = picking(one, ['flows/production', 'flows/imports'])
    expect(rows(mixed).get('Polymer')).toEqual(['sum'])
    expect(formDimensions(mixed, options).find(row => row.dimension.name === 'Polymer')!.shared).toBe(false)
  })

  it('clears a dimension of no quantity that holds a channel, as a hand-made URL can bind one', () => {
    const odd = { ...one, channels: { x: 'Time', color: 'End Use' } }
    const next = setRole(odd, options, 'Region', 'color')
    expect(next.channels).toEqual({ x: 'Time', color: 'Region' })
    expect([next.keep, roleOf(next, 'End Use')]).toEqual([[], 'sum'])
    expect(setRole(odd, options, 'Polymer', 'filter').channels).toEqual({ x: 'Time' })
  })

  it('keeps a required channel filled: its dimension can only swap with one on another channel', () => {
    expect(requiredHeld(one, options, 'Time')).toBe('x')
    expect(requiredHeld(one, options, 'Region')).toBeNull()
    expect(requiredHint(one, options, 'Time')).toBe('x always has a dimension. To move Time, give another dimension the role x.')
    expect(requiredHint(one, options, 'Region')).toBeNull()
    expect(rows(one).get('Time')).toEqual(['x'])
    const colour = setRole(one, options, 'Polymer', 'color')
    expect(rows(colour).get('Time')).toEqual(['x', 'color'])
    expect(setRole(colour, options, 'Time', 'color').channels).toEqual({ x: 'Polymer', color: 'Time' })
  })

  it('drops a dimension of no quantity on a plot change', () => {
    const odd = { ...one, channels: { x: 'Time', linetype: 'End Use' } }
    const bars = setPlot(odd, options, 'bar')
    expect([bars.channels, bars.keep, roleOf(bars, 'End Use')]).toEqual([{ x: 'Time' }, [], 'sum'])
  })

  it('moves a dimension off a channel the new plot lacks to the filters', () => {
    const lines = setRole(one, options, 'Region', 'linetype')
    expect(roleOf(setPlot(lines, options, 'bar'), 'Region')).toBe('filter')
  })

  it('keeps the values of a kept dimension and drops those of a summed one', () => {
    const only = setOnly(setRole(one, options, 'Region', 'color'), 'Region', ['LAM'])
    expect(request(only, options)!.values).toEqual({ Region: ['LAM'] })
    expect(setRole(only, options, 'Region', 'filter').only).toEqual({ Region: ['LAM'] })
    expect(setRole(only, options, 'Region', 'panels').only).toEqual({ Region: ['LAM'] })
    expect(setRole(only, options, 'Region', 'sum').only).toEqual({})
  })

  it('keeps a dimension on panels as a filter, so the control bar can unsplit it', () => {
    const panels = setOnly(setRole(one, options, 'Region', 'panels'), 'Region', ['LAM', 'SSA'])
    expect([panels.keep, panels.splits]).toEqual([['Region'], ['Region']])
    const query = { ...mergeBuilder({}, emptyState(), panels), _tab: 'data' }
    const unsplit = parseBuilder(mergeControls(query, { Region: 'LAM' }))
    expect(roleOf(unsplit, 'Region')).toBe('filter')
    expect(request(unsplit, options)).toEqual(request(panels, options))
  })
})

describe('which quantities can join', () => {
  const two = picking(setRole(one, options, 'Region', 'color'), ['flows/production', 'flows/recycling'])

  it('needs the kept dimensions, a sum it allows, the unit and another title', () => {
    expect(incompatibility(one, options.quantities[1]!)).toBeNull()
    expect(incompatibility(one, options.quantities[2]!)).toBeNull()
    expect(incompatibility(setRole(one, options, 'Polymer', 'color'), options.quantities[2]!)).toBe('needs Polymer')
    expect(incompatibility(one, options.quantities[3]!)).toBe('in Mt, not t')
    expect(incompatibility(one, quantity('flows/other', { title: 'production' }))).toBe('has the title of one picked')
    expect(incompatibility(one, quantity('parameters/share', { additive: false }))).toBe('not additive, so not summed over Region, Polymer')
    expect(incompatibility(emptyState(), options.quantities[3]!)).toBeNull()
    expect(incompatibility(two, options.quantities[0]!)).toBeNull() // picked, so it can go
  })

  it('refuses any quantity when the dataset has a dimension called Quantity', () => {
    const named = { ...options, dimensions: [...options.dimensions, { name: 'Quantity', dtype: 'string' as const, values: ['a'] }] }
    expect(joinable(one, named)(options.quantities[1]!)).toBe('the dataset has a dimension called Quantity')
  })

  it('needs every quantity additive when Quantity is summed, the ones picked too', () => {
    const mixed: BuilderState = { ...emptyState(), quantities: ['flows/production', 'parameters/rate'], channels: { x: 'Time' }, keep: ['Region'] }
    expect(roleOf(mixed, 'Quantity')).toBe('sum')
    expect(incompatibility(mixed, options.quantities[1]!)).toBe('not additive, so not summed over Quantity')
  })

  it('needs additive quantities when Quantity is summed', () => {
    const summed = setRole(two, options, 'Quantity', 'sum')
    const intensive = quantity('flows/share', { additive: false, dimensions: ['Time', 'Region'] })
    expect(incompatibility(summed, intensive)).toBe('not additive, so not summed over Quantity')
  })
})

describe('the builder in the URL', () => {
  const state: BuilderState = {
    quantities: ['flows/production', 'flows/recycling'],
    plot: 'stacked_area',
    channels: { x: 'Time', color: 'Polymer' },
    keep: ['Quantity', 'Region'],
    splits: ['Region'],
    only: { Region: ['LAM', 'SSA'], Polymer: [] },
    from: { Time: '2021' },
    to: {},
  }

  it('says who each query key belongs to', () => {
    expect(['_q', '_plot', '_keep', '_c.x', '_only.Region', '_from.Time', '_to.Time'].map(owner)).toEqual(Array(7).fill('builder'))
    expect(['Region', '_split', '_y'].map(owner)).toEqual(['control', 'control', 'control'])
    expect(['_tab', '_other'].map(owner)).toEqual(['page', 'page'])
  })

  it('round-trips, ranges and an empty selection included', () => {
    const query = mergeBuilder({}, emptyState(), state)
    expect(query).toEqual({
      '_q': ['flows/production', 'flows/recycling'],
      '_plot': 'stacked_area',
      '_c.x': 'Time',
      '_c.color': 'Polymer',
      '_keep': ['Quantity', 'Region'],
      '_split': 'Region',
      '_only.Region': ['LAM', 'SSA'],
      '_only.Polymer': null,
      '_from.Time': '2021',
    })
    expect(parseBuilder(query)).toEqual(state)
  })

  it('makes the request: panels kept, ranges expanded to the values', () => {
    expect(request(state, options)).toEqual({
      quantities: ['flows/production', 'flows/recycling'],
      plot: 'stacked_area',
      mapping: { x: 'Time', color: 'Polymer' },
      keep: ['Quantity', 'Region'],
      values: { Time: ['2021', '2022', '2023'], Polymer: [], Region: ['LAM', 'SSA'] },
    })
    const ranged = setRange(state, 'Time', '2021', '2022')
    expect(request(ranged, options)!.values.Time).toEqual(['2021', '2022'])
    expect(request(setRange(ranged, 'Time', undefined, undefined), options)!.values.Time).toBeUndefined()
    expect(request(emptyState(), options)).toBeNull()
  })

  it('leaves out values a dimension lacks, with a notice, and keeps all when it lacks every one', () => {
    const odd = setOnly(state, 'Region', ['LAM', 'MARS'])
    expect(request(odd, options)!.values.Region).toEqual(['LAM'])
    expect(notices(odd, options)).toEqual(["Region 'MARS' is not in the dataset; it is left out"])
    expect(notices(state, options)).toEqual([])
    const unknown = setOnly(state, 'Region', ['MARS'])
    expect(request(unknown, options)!.values.Region).toBeUndefined()
    const region = formDimensions(unknown, options).find(row => row.dimension.name === 'Region')!.dimension
    expect([keptValues(unknown, region), keptValues(setOnly(state, 'Region', []), region)]).toEqual([undefined, []])
  })

  it('keeps the control state on a builder change, but a stale filter value', () => {
    const before = setRole(one, options, 'Region', 'filter')
    const query = { ...mergeBuilder({}, emptyState(), before), Region: 'SSA', _y: 'independent', _tab: 'data' }
    const same = mergeBuilder(query, before, setOnly(before, 'Region', ['SSA', 'EUR']))
    expect(same).toMatchObject({ Region: 'SSA', _y: 'independent', _tab: 'data' })
    const moved = mergeBuilder(query, before, setRole(before, options, 'Region', 'color'))
    expect(moved.Region).toBeUndefined()
    expect(moved['_c.color']).toBe('Region')
    const summed = mergeBuilder(query, before, setRole(before, options, 'Region', 'sum'))
    expect([summed.Region, summed['_keep']]).toEqual([undefined, undefined])
    const reset = mergeBuilder(query, before, defaults(options, ['flows/recycling']), true)
    expect(reset).toEqual({ '_q': 'flows/recycling', '_c.x': 'Time', '_tab': 'data' })
  })

  it('merges a control change: the filters, _split and _y replaced, the builder kept', () => {
    const query = { ...mergeBuilder({}, emptyState(), state), Quantity: 'production', _tab: 'data' }
    const merged = mergeControls(query, { Quantity: 'recycling', _split: ['Region', 'Quantity'] })
    expect(merged).toMatchObject({ 'Quantity': 'recycling', '_split': ['Region', 'Quantity'], '_tab': 'data', '_c.x': 'Time', '_keep': ['Quantity', 'Region'] })
    expect(parseBuilder(merged).splits).toEqual(['Region', 'Quantity'])
    expect(roleOf(parseBuilder(merged), 'Quantity')).toBe('panels')
    expect(mergeControls(query, {})._split).toBeUndefined()
  })
})

describe('what a chart shows', () => {
  it('names the dimensions summed and the values kept', () => {
    const summed = request(one, options)!
    expect(subtitleParts(summed, options)).toEqual(['Summed over Region, Polymer'])
    const narrowed = setRange(setOnly(setRole(one, options, 'Region', 'panels'), 'Region', ['LAM', 'SSA']), 'Time', '2021', undefined)
    expect(subtitleParts(request(narrowed, options)!, options)).toEqual(['Summed over Polymer', 'Time 2021–2023', 'Region: LAM, SSA (2 of 3)'])
    const two = picking(one, ['flows/production', 'flows/recycling'])
    expect(subtitleParts(request(setRole(two, options, 'Quantity', 'sum'), options)!, options)[0]).toBe('Summed over Quantity, Region, Polymer')
  })
})

describe('what a chart shows, of longer lists', () => {
  const regions = { name: 'Region', dtype: 'string' as const, values: ['LAM', 'SSA', 'EUR', 'CHA', 'IND'] }
  const wide: BuilderOptions = { ...options, dimensions: [options.dimensions[0]!, regions, options.dimensions[2]!] }
  const kept = setRole(defaults(wide, ['flows/production']), wide, 'Region', 'panels')

  it('counts more than three values, and says none', () => {
    expect(subtitleParts(request(setOnly(kept, 'Region', ['LAM', 'SSA', 'EUR', 'CHA']), wide)!, wide)).toContain('Region: 4 of 5')
    expect(subtitleParts(request(setOnly(kept, 'Region', []), wide)!, wide)).toContain('Region: none')
  })

  it('names the quantities a Quantity filter keeps', () => {
    const two = setRole(picking(one, ['flows/production', 'flows/recycling']), options, 'Quantity', 'filter')
    const parts = subtitleParts(request(setOnly(two, 'Quantity', ['production']), options)!, options)
    expect(parts).toEqual(['Summed over Region, Polymer', 'Quantity: production (1 of 2)'])
  })
})

describe('ranges of values', () => {
  it('compare integers as numbers and dates and datetimes as their ISO text', () => {
    const years: Dimension = { name: 'Time', dtype: 'integer', values: [5, 10, 100] }
    expect(inRange(years, '10', undefined)).toEqual(['10', '100'])
    const days: Dimension = { name: 'Day', dtype: 'date', values: ['2020-01-01', '2020-02-01', '2021-01-01'] }
    expect(inRange(days, '2020-01-15', '2020-12-31')).toEqual(['2020-02-01'])
    const moments: Dimension = { name: 'At', dtype: 'datetime', values: ['2020-01-01T00:00:00', '2020-01-01T12:00:00'] }
    expect(inRange(moments, undefined, '2020-01-01T06:00:00.000Z')).toEqual(['2020-01-01T00:00:00.000Z'])
  })
})
