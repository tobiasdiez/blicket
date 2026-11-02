import { unitOf, withUnit, type TableSchema } from './manifest'
import { display, type Row } from './table'

function quote(text: string): string {
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/**
 * The rows as CSV: dimensions then measures, the header of the measure the `unit` belongs to with
 * the unit (see `unitOf`), dates as `YYYY-MM-DD`, numbers in full.
 */
export function toCsv(rows: Row[], schema: TableSchema, unit: string | null, mapping: Record<string, string>): string {
  const names = [...schema.dimensions.map(d => d.name), ...schema.measures.map(m => withUnit(m.name, unitOf(m.name, unit, mapping)))]
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

/** Save the rows as `<name>.csv` in the browser, as `toCsv` writes them. */
export function downloadCsv(rows: Row[], schema: TableSchema, unit: string | null, mapping: Record<string, string>, name: string): void {
  const url = URL.createObjectURL(new Blob([toCsv(rows, schema, unit, mapping)], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${name}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
