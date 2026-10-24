import { withUnit, type TableSchema } from './manifest'
import { display, type Row } from './table'

function quote(text: string): string {
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/**
 * The rows as CSV: dimensions then measures, the measures' header with the `unit`, dates as
 * `YYYY-MM-DD`, numbers in full.
 */
export function toCsv(rows: Row[], schema: TableSchema, unit: string | null): string {
  const names = [...schema.dimensions.map(d => d.name), ...schema.measures.map(m => withUnit(m.name, unit))]
  const lines = [names.map(quote).join(',')]
  for (const row of rows) {
    const cells = [
      ...schema.dimensions.map(d => (row[d.name] == null ? '' : display(row[d.name]!, d))),
      ...schema.measures.map(m => (row[m.name] == null ? '' : String(row[m.name]))),
    ]
    lines.push(cells.map(quote).join(','))
  }
  return `${lines.join('\n')}\n`
}
