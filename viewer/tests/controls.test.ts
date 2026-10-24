import { describe, expect, it } from 'vitest'
import { queryFromState, stateFromQuery, withFilter, withSplit, withoutSplit } from '../app/lib/controls'
import type { Control, TableSchema } from '../app/lib/manifest'

const schema: TableSchema = {
  dimensions: [
    { name: 'Parameter', dtype: 'string', values: ['a', 'b', 'c'] },
    { name: 'Year', dtype: 'integer', values: [2020, 2021] },
    { name: 'Region', dtype: 'string', values: ['EUR', 'USA'] },
    { name: 'Day', dtype: 'date', values: ['2020-01-01', '2020-01-02'] },
    { name: 'y', dtype: 'boolean', values: [false, true] },
  ],
  measures: [{ name: 'value', dtype: 'float' }],
}
const controls: Control[] = [
  { dimension: 'Parameter', kind: 'filter', default: 'b' },
  { dimension: 'Region', kind: 'split', default: 'USA' },
  { dimension: 'Day', kind: 'filter', default: '2020-01-01' },
  { dimension: 'y', kind: 'filter', default: false },
]

describe('the control state in the URL', () => {
  it('falls back to the defaults', () => {
    expect(stateFromQuery(controls, schema, {})).toEqual({
      state: { filters: { Parameter: 'b', Day: '2020-01-01', y: false }, splits: ['Region'], y: 'shared' },
      notices: [],
      unknown: [],
    })
  })

  it('parses values by the dimension type and reports values the dimension lacks', () => {
    const { state, notices } = stateFromQuery(controls, schema, { Parameter: 'zzz', Day: '2020-01-02', y: 'true', _y: 'independent' })
    expect(state.filters).toEqual({ Parameter: 'b', Day: '2020-01-02', y: true })
    expect(state.y).toBe('independent')
    expect(notices).toEqual(["Parameter 'zzz' is not in this build; showing b"])
    const year: Control[] = [{ dimension: 'Year', kind: 'filter', default: 2020 }]
    expect(stateFromQuery(year, schema, { Year: '2021' }).state.filters.Year).toBe(2021)
    expect(stateFromQuery(year, schema, { Year: '1999' }).state.filters.Year).toBe(2020)
  })

  it('names query keys that no control knows, but not the keys with an underscore', () => {
    const { unknown } = stateFromQuery(controls, schema, { Scenario: 'x', _split: ['Region', 'Regoin'], _tab: 'data' })
    expect(unknown).toEqual(['Scenario', '_split=Regoin'])
  })

  it('lets the query split a filter and filter a split', () => {
    const { state } = stateFromQuery(controls, schema, { Region: 'EUR', _split: ['Parameter', 'Day'] })
    expect(state.splits).toEqual(['Parameter', 'Day'])
    expect(state.filters).toEqual({ Region: 'EUR', y: false })
  })

  it('round-trips through the query with prefixed keys', () => {
    const state = withFilter(stateFromQuery(controls, schema, {}).state, 'y', true)
    const query = queryFromState(schema, { ...state, y: 'independent' })
    expect(query).toEqual({ Parameter: 'b', Day: '2020-01-01', y: 'true', _split: 'Region', _y: 'independent' })
    expect(stateFromQuery(controls, schema, query).state).toEqual({ ...state, y: 'independent' })
  })

  it('takes the y axis default from the Blick and writes only a departure from it', () => {
    const { state } = stateFromQuery(controls, schema, {}, 'independent')
    expect(state.y).toBe('independent')
    expect(queryFromState(schema, state, 'independent')._y).toBeUndefined()
    const shared = { ...state, y: 'shared' as const }
    expect(queryFromState(schema, shared, 'independent')._y).toBe('shared')
    expect(stateFromQuery(controls, schema, { _y: 'shared' }, 'independent').state.y).toBe('shared')
  })

  it('splits in the order of the controls and un-splits to the default', () => {
    const split = withSplit(stateFromQuery(controls, schema, {}).state, controls, 'Parameter')
    expect(split.splits).toEqual(['Parameter', 'Region'])
    expect(split.filters).not.toHaveProperty('Parameter')
    const unsplit = withoutSplit(split, controls, schema, 'Region')
    expect(unsplit.splits).toEqual(['Parameter'])
    expect(unsplit.filters.Region).toBe('USA')
    expect(queryFromState(schema, split)._split).toEqual(['Parameter', 'Region'])
  })
})
