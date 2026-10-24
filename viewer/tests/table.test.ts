import { readFile } from 'node:fs/promises'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { display, fetchTable, formatValue, formatter, numberFormat, readTable, valueKey } from '../app/lib/table'

const parquet = async () => {
  const file = await readFile(new URL('table.parquet', import.meta.url))
  return file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength) as ArrayBuffer
}

describe('table rows', () => {
  it('reads a zstd Parquet file as polars writes it', async () => {
    // tests/table.parquet, written by polars 2 with its defaults (zstd):
    // pl.DataFrame({"Time": pl.Series([1950, 2100, 2100], dtype=pl.Int64),
    //               "Region": ["EUR", "EUR", "USA"],
    //               "Day": [date(2020, 1, 1), date(2020, 1, 2), date(2020, 1, 3)],
    //               "value": [1.5, None, 2.5e9]}).write_parquet("table.parquet")
    const rows = await readTable(await parquet())
    expect(rows).toHaveLength(3)
    expect(rows[0]).toEqual({ Time: 1950, Region: 'EUR', Day: new Date(Date.UTC(2020, 0, 1)), value: 1.5 })
    expect(typeof rows[0]!.Time).toBe('number') // INT64 arrives as BigInt
    expect(rows[1]!.value).toBeNull()
  })

  it('gives dates and datetimes one key, from the manifest, the URL and the table alike', () => {
    expect(valueKey(new Date(Date.UTC(2020, 0, 2)), 'date')).toBe('2020-01-02')
    expect(valueKey('2020-01-02', 'date')).toBe('2020-01-02')
    const moment = new Date(Date.UTC(2020, 0, 2, 3, 4, 5))
    expect(valueKey('2020-01-02T03:04:05', 'datetime')).toBe(valueKey(moment, 'datetime'))
    expect(display(moment, { name: 't', dtype: 'datetime', values: [] })).toBe('2020-01-02 03:04:05 UTC')
  })
})

describe('numbers', () => {
  it('formats an axis by its largest value: SI prefixes only from 1,000 up', () => {
    expect(formatter(numberFormat(5e8))(4.567e8)).toBe('457M')
    expect(formatter(numberFormat(5e8))(0)).toBe('0')
    expect(formatter(numberFormat(1))(0.25)).toBe('0.25')
  })

  it('formats a single value by itself, so noise is not read as atto or femto', () => {
    expect(formatValue(8.88e-16)).toBe('8.88e-16')
    expect(formatValue(-1.99e-13)).toBe('−1.99e-13')
    expect(formatValue(22191.7)).toBe('22.2k')
    expect(formatValue(0.25)).toBe('0.25')
    expect(formatValue(22191.7, 6)).toBe('22.1917k')
  })
})

describe('fetching tables', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches a table once per content hash, with the hash in the URL', async () => {
    const body = await parquet()
    const fetch = vi.fn(async () => new Response(body.slice(0)))
    vi.stubGlobal('fetch', fetch)
    const first = await fetchTable({ path: 'blicks/a/b.parquet', hash: 'parquet-sha256:1' })
    expect(await fetchTable({ path: 'blicks/a/b.parquet', hash: 'parquet-sha256:1' })).toBe(first)
    await fetchTable({ path: 'blicks/a/b.parquet', hash: 'parquet-sha256:2' })
    expect(fetch.mock.calls.map(call => (call as unknown[])[0])).toEqual([
      './blicks/a/b.parquet?parquet-sha256%3A1',
      './blicks/a/b.parquet?parquet-sha256%3A2',
    ])
  })

  it('forgets a failed fetch, so the next one tries again', async () => {
    const body = await parquet()
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response('down', { status: 500, statusText: 'Internal Server Error' }))
      .mockResolvedValueOnce(new Response(body.slice(0)))
    vi.stubGlobal('fetch', fetch)
    const file = { path: 'blicks/a/c.parquet', hash: 'parquet-sha256:3' }
    await expect(fetchTable(file)).rejects.toThrow('blicks/a/c.parquet: 500 Internal Server Error')
    expect(await fetchTable(file)).toHaveLength(3)
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
