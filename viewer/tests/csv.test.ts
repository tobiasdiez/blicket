import { describe, expect, it } from 'vitest'
import { toCsv } from '../app/lib/csv'
import type { TableSchema } from '../app/lib/manifest'

const schema: TableSchema = {
  dimensions: [
    { name: 'Time', dtype: 'integer', values: [2020] },
    { name: 'Region', dtype: 'string', values: ['EUR'] },
    { name: 'Day', dtype: 'date', values: ['2020-01-01'] },
  ],
  measures: [{ name: 'value', dtype: 'float' }],
}

const mapping = { x: 'Time', y: 'value', color: 'Region' }

describe('CSV', () => {
  it('writes dimensions, then measures in full with the unit, quoting where needed', () => {
    const rows = [{ Time: 2020, Region: 'EU, "west"', Day: new Date(Date.UTC(2020, 0, 1)), value: 8.88e-16 }]
    expect(toCsv(rows, schema, 't', mapping)).toBe('Time,Region,Day,value [t]\n2020,"EU, ""west""",2020-01-01,8.88e-16\n')
    expect(toCsv(rows, schema, null, mapping).split('\n')[0]).toBe('Time,Region,Day,value')
  })

  it('puts the unit on the measure on y only, not on a scatter\'s x', () => {
    const scattered: TableSchema = { ...schema, measures: [{ name: 'GDP per capita', dtype: 'float' }, ...schema.measures] }
    const rows = [{ 'Time': 2020, 'Region': 'EUR', 'Day': new Date(Date.UTC(2020, 0, 1)), 'GDP per capita': 3e4, 'value': 1.5 }]
    expect(toCsv(rows, scattered, 't per person', { x: 'GDP per capita', y: 'value', along: 'Time' })).toBe('Time,Region,Day,GDP per capita,value [t per person]\n2020,EUR,2020-01-01,30000,1.5\n')
  })

  it('puts the unit on every measure of a plot without y', () => {
    const rows = [{ Time: 2020, Region: 'EUR', Day: new Date(Date.UTC(2020, 0, 1)), value: 2 }]
    expect(toCsv(rows, schema, 't', { source: 'Region', value: 'value' }).split('\n')[0]).toBe('Time,Region,Day,value [t]')
  })
})
