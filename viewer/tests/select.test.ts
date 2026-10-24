import { describe, expect, it } from 'vitest'
import type { TableSchema } from '../app/lib/manifest'
import { select } from '../app/lib/select'
import type { Row } from '../app/lib/table'

const schema: TableSchema = {
  dimensions: [
    { name: 'Parameter', dtype: 'string', values: ['a', 'b'] },
    { name: 'Day', dtype: 'date', values: ['2020-01-01', '2020-01-02'] },
    { name: 'Region', dtype: 'string', values: ['EUR', 'USA'] },
    { name: 'Year', dtype: 'integer', values: [2020, 2021] },
  ],
  measures: [{ name: 'value', dtype: 'float' }],
}

function rows(): Row[] {
  const result: Row[] = []
  for (const Parameter of ['a', 'b']) {
    for (const Day of [new Date(Date.UTC(2020, 0, 1)), new Date(Date.UTC(2020, 0, 2))]) {
      for (const Region of ['EUR', 'USA']) {
        for (const Year of [2020, 2021]) result.push({ Parameter, Day, Region, Year, value: result.length })
      }
    }
  }
  return result
}

describe('select', () => {
  it('keeps the rows that match every filter and leaves the other dimensions in', () => {
    const shown = select(rows(), schema, { Parameter: 'b', Day: '2020-01-02' })
    expect(shown).toHaveLength(4)
    expect(new Set(shown.map(row => row.Region))).toEqual(new Set(['EUR', 'USA']))
    expect(shown.every(row => row.Parameter === 'b' && (row.Day as Date).getUTCDate() === 2)).toBe(true)
  })

  it('compares integers by value and returns every row without filters', () => {
    expect(select(rows(), schema, { Year: 2021 })).toHaveLength(8)
    expect(select(rows(), schema, {})).toHaveLength(16)
  })
})
