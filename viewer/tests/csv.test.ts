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

describe('CSV', () => {
  it('writes dimensions, then measures in full with the unit, quoting where needed', () => {
    const rows = [{ Time: 2020, Region: 'EU, "west"', Day: new Date(Date.UTC(2020, 0, 1)), value: 8.88e-16 }]
    expect(toCsv(rows, schema, 't')).toBe('Time,Region,Day,value [t]\n2020,"EU, ""west""",2020-01-01,8.88e-16\n')
    expect(toCsv(rows, schema, null).split('\n')[0]).toBe('Time,Region,Day,value')
  })
})
