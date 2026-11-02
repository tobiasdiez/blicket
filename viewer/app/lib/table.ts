import { parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'
import * as vega from 'vega'
import { Unreachable } from './dev'
import type { Dimension, DimensionType, Value } from './manifest'

/** A cell of a Blick's table as the viewer holds it; dates are `Date` at UTC midnight. */
export type Cell = string | number | boolean | Date | null
/** A row of a Blick's table, keyed by column name. */
export type Row = Record<string, Cell>

/**
 * The rows of a Parquet file, zstd included. INT64 columns, which come back as BigInt, become
 * numbers: their values are years and counts, far below 2^53.
 */
export async function readTable(buffer: ArrayBuffer): Promise<Row[]> {
  const rows = await parquetReadObjects({ file: buffer, compressors })
  for (const row of rows) {
    for (const key in row) {
      if (typeof row[key] === 'bigint') row[key] = Number(row[key])
    }
  }
  return rows as Row[]
}

/** Where a Blick's table is and what it holds: the path in the build and its content hash. */
export interface TableFile {
  path: string
  hash: string | null
}

// The tables fetched; of the builder's, the one used last is at the end.
const tables = new Map<string, Promise<Row[]>>()

/** A failure to reach the server as `Unreachable`: fetch and the read of a body reject with a
 * TypeError then; any other failure as it is. */
function unreachable(cause: unknown): never {
  throw cause instanceof TypeError ? new Unreachable() : cause
}
/** Where the Blick builder's tables are: a dev session makes a new one for every query. */
const ADHOC = 'dev/tables/'
/** How many of the Blick builder's tables are kept; a build's tables are all kept. */
export const KEPT_TABLES = 50

/** Forget the builder's tables used longest ago, so that `KEPT_TABLES` of them stay. */
function evict() {
  const adhoc = [...tables.keys()].filter(key => key.startsWith(ADHOC))
  for (const key of adhoc.slice(0, Math.max(0, adhoc.length - KEPT_TABLES))) tables.delete(key)
}

/**
 * The rows of `file`, fetched once per content hash; of the builder's tables, only the last
 * `KEPT_TABLES` used are kept. The hash is in the URL and the cache key, so a table of another
 * build at the same path, served on the same port, is another file to the browser. The whole file
 * comes in one request: tables are small, and not every server answers ranges.
 */
export function fetchTable(file: TableFile): Promise<Row[]> {
  // The builder's tables are kept by path, which names their content; a build's by its hash.
  const key = file.path.startsWith(ADHOC) ? file.path : file.hash ?? file.path
  let table = tables.get(key)
  if (table) {
    tables.delete(key)
    tables.set(key, table)
  }
  else {
    const url = file.hash ? `./${file.path}?${encodeURIComponent(file.hash)}` : `./${file.path}`
    table = fetch(url)
      .catch(unreachable)
      .then((response) => {
        if (!response.ok) throw new Error(`${file.path}: ${response.status} ${response.statusText}`)
        return response.arrayBuffer().catch(unreachable)
      })
      .then(readTable)
    table.catch(() => tables.delete(key))
    tables.set(key, table)
    evict()
  }
  return table
}

export const isTime = (d: Dimension) => d.dtype === 'date' || d.dtype === 'datetime'

/**
 * A dimension value in the form that compares equal across the manifest, the URL and the table:
 * dates as `YYYY-MM-DD`, datetimes as ISO strings in UTC, anything else as its string.
 */
export function valueKey(value: Cell | Value, dtype: DimensionType): string {
  if (dtype === 'date') {
    return value instanceof Date ? value.toISOString().slice(0, 10) : String(value).slice(0, 10)
  }
  if (dtype === 'datetime') {
    if (value instanceof Date) return value.toISOString()
    const text = String(value)
    const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(text) ? text : `${text}Z`)
    return Number.isNaN(date.getTime()) ? text : date.toISOString()
  }
  return String(value)
}

/** A dimension value for text: dates as `YYYY-MM-DD`, datetimes in UTC. */
export function display(value: Cell | Value, d: Dimension): string {
  if (!(value instanceof Date)) return String(value)
  return d.dtype === 'date' ? valueKey(value, 'date') : value.toISOString().replace('T', ' ').replace(/\.000Z$/, ' UTC')
}

/**
 * The d3 number format for values that reach `max`: `digits` significant digits, with SI
 * prefixes from 1,000 up (12.3k, 4.5G), plain below, so a share reads 0.25 and not 250m.
 */
export function numberFormat(max: number, digits = 3): string {
  return max >= 1000 ? `.${digits}~s` : `.${digits}~g`
}

// Vega's d3-format, which formats the axes; vega exports it, but its typings omit it.
const locale = (vega as unknown as { defaultLocale(): { format(spec: string): (value: number) => string } }).defaultLocale()

/** A function that formats numbers with the d3 format `spec`. */
export function formatter(spec: string): (value: number) => string {
  return locale.format(spec)
}

/**
 * One value with `digits` significant digits, its format chosen for the value alone, so
 * numerical noise reads 8.88e-16 and not 888a.
 */
export function formatValue(value: number, digits = 3): string {
  return formatter(numberFormat(Math.abs(value), digits))(value)
}

/** The largest absolute value of `measure` in `rows`. */
export function largest(rows: Row[], measure: string): number {
  return rows.reduce((max, row) => Math.max(max, Math.abs(Number(row[measure]) || 0)), 0)
}
