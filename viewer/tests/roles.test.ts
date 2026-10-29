import { describe, expect, it } from 'vitest'
import type { BlickEntry, TableSchema } from '../app/lib/manifest'
import { searchText } from '../app/lib/roles'

const schema: TableSchema = {
  dimensions: [
    { name: 'Time', dtype: 'integer', values: [2020] },
    { name: 'Region', dtype: 'string', values: ['EUR'] },
    { name: 'Day', dtype: 'date', values: ['2020-01-01'] },
  ],
  measures: [{ name: 'value', dtype: 'float' }],
}

const entry = {
  name: 'flows/x',
  definition: { title: 'X', description: 'About x.', unit: null, tags: [], plot: { type: 'line', mapping: { x: 'Time', y: 'value', color: 'Region' } }, independent_y: false },
  columns: schema,
} as unknown as BlickEntry

describe('the search', () => {
  it('searches plot types and dimension names too', () => {
    const text = searchText(entry, ['mfa'])
    for (const word of ['line', 'region', 'day', 'about', 'mfa']) expect(text).toContain(word)
  })
})
