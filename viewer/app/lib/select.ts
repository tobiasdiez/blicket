import type { TableSchema, Value } from './manifest'
import { valueKey, type Row } from './table'

/**
 * The rows a chart shows: those that match every filter. Split dimensions, and the dimensions
 * the plot binds to a channel, have no filter and pass through.
 */
export function select(rows: Row[], schema: TableSchema, filters: Record<string, Value>): Row[] {
  const tests = schema.dimensions
    .filter(dimension => dimension.name in filters)
    .map(({ name, dtype }) => ({ name, dtype, key: valueKey(filters[name]!, dtype) }))
  if (tests.length === 0) return rows
  return rows.filter(row => tests.every(({ name, dtype, key }) => valueKey(row[name] ?? null, dtype) === key))
}
