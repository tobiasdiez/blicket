import { describe, expect, it } from 'vitest'
import type { Comparison } from '../app/lib/comparison'
import type { DevInfo } from '../app/lib/dev'
import type { BlickEntry, Manifest } from '../app/lib/manifest'
import { afterReading, coalesced, keptChoice, refreshStep, type Step, rowOwners, rowsStay, settled, share, tableKey, tableOf } from '../app/lib/reload'

function entry(name: string, extra: Partial<BlickEntry> = {}): BlickEntry {
  return { id: name, name, status: 'ok', data: `dev/tables/${name}.parquet`, hash: `parquet-sha256:${name}`, columns: { dimensions: [{ name: 'year', dtype: 'integer', values: [2020] }], measures: [] }, controls: [], ...extra } as unknown as BlickEntry
}

const manifest = (...blicks: BlickEntry[]) => ({ spec: '0.2', build: { id: 's' }, blicks }) as unknown as Manifest
const comparison = (id: string, created: string, flags: string[] = []) => ({ created_at: created, baseline: { id }, blicks: [{ name: 'a', change: { flags } }, { name: 'b', change: { flags: [] } }] }) as unknown as Comparison
const key = (e: BlickEntry) => tableKey(tableOf(e))
/** A read of the revisions `revisions`. */
const of = (...revisions: number[]) => ({ revisions })

describe('reading the manifest and the comparisons again', () => {
  it('keeps what did not change, at any depth, and the whole when nothing did', () => {
    const a = entry('a')
    const b = entry('b', { status: 'pending', data: null, hash: null })
    const previous = manifest(a, b)
    expect(share(previous, manifest(entry('a'), entry('b', { status: 'pending', data: null, hash: null })))).toBe(previous)
    const built = entry('b')
    const next = share(previous, manifest(entry('a'), built))
    expect(next).not.toBe(previous)
    expect(next.blicks[0]).toBe(a)
    expect(next.blicks[1]).not.toBe(b)
    expect(next.blicks[1]!.columns).toBe(b.columns) // the schema of the entry rebuilt is the one before
    expect(next.build).toBe(previous.build)
    expect(share(null, previous)).toBe(previous)
  })

  it('keeps the Blicks of a comparison made anew, whose time of making is new', () => {
    const previous = [comparison('x', '12:00'), comparison('y', '12:00')]
    expect(share(previous, [comparison('x', '12:00'), comparison('y', '12:00')])).toBe(previous)
    const next = share(previous, [comparison('x', '12:01'), comparison('y', '12:01', ['value'])])
    expect(next[0]).not.toBe(previous[0])
    expect(next[0]!.blicks).toBe(previous[0]!.blicks)
    expect(next[1]!.blicks[1]).toBe(previous[1]!.blicks[1])
    expect(next[1]!.blicks[0]).not.toBe(previous[1]!.blicks[0])
  })

  it('keeps the baseline chosen, No baseline too, unless it is gone', () => {
    const offered = [comparison('x', ''), comparison('y', '')]
    expect(keptChoice('x', offered)).toBe('x')
    expect(keptChoice(null, offered)).toBeNull()
    expect(keptChoice('gone', offered)).toBe('y')
    expect(keptChoice('gone', [])).toBeNull()
  })

  it('reads them again for an answer of another revision or session, until what it shows is of its revision', () => {
    expect(refreshStep(null, { session: 's', revision: 0 })).toBe('reload') // the first answer
    expect(refreshStep({ session: 's', revision: 3 }, { session: 's', revision: 3 })).toBe('show')
    expect(refreshStep({ session: 's', revision: 3 }, { session: 's', revision: 4 })).toBe('reload')
    // A restart of blicket dev that comes back at the same revision.
    expect(refreshStep({ session: 's', revision: 0 }, { session: 't', revision: 0 })).toBe('reload')
  })

  it('brings a tab over to another session, after a restart of blicket dev or the load of another run', () => {
    const before: Pick<DevInfo, 'session' | 'revision'> = { session: 's', revision: 4 }
    const after: Pick<DevInfo, 'session' | 'revision'> = { session: 't', revision: 0 }
    expect(refreshStep(before, after)).toBe('reload')
  })

  it('shows what it read again only when it is of the revision of the answer, else waits for the next', () => {
    expect(afterReading(4, [of(4), of(4, 4)], false)).toBe('show')
    expect(afterReading(4, [of(5), of(5, 5)], false)).toBe('later') // a Blick was built meanwhile
    expect(afterReading(4, [of(4), of(5)], false)).toBe('later')
    expect(afterReading(0, [of(0), of()], false)).toBe('show') // a build directory names none
    expect(afterReading(4, [null, of(4)], false)).toBe('later') // a later read took over: no warning
    expect(afterReading(4, [null, of(4)], true)).toBe('failed')
  })
})

describe('the rows a chart shows while another table is fetched', () => {
  it('stay for the Blick they are of, and go for another one, and without a table', () => {
    expect(rowsStay('steel/trade', 'steel/trade', 'dev/tables/new.parquet?h')).toBe(true)
    expect(rowsStay('steel/trade', 'steel/production', 'dev/tables/p.parquet?h')).toBe(false)
    expect(rowsStay('steel/trade', 'steel/trade', null)).toBe(false)
  })

  it('stay for a Blick rebuilt, and go for another baseline, as the chart owns them', () => {
    const before = entry('a', { hash: 'parquet-sha256:1' })
    const rebuilt = entry('a', { hash: 'parquet-sha256:2' })
    const [one, two] = [{ path: 'compare/aaaa/blicks/a.parquet', hash: 'x' }, { path: 'compare/bbbb/blicks/a.parquet', hash: 'y' }]
    expect(rowsStay(rowOwners(before, one).own, rowOwners(rebuilt, one).own, key(rebuilt))).toBe(true)
    expect(rowsStay(rowOwners(before, one).baseline, rowOwners(before, two).baseline, tableKey(two))).toBe(false)
    expect(rowsStay(rowOwners(before, one).baseline, rowOwners(rebuilt, one).baseline, tableKey(one))).toBe(true)
  })

  it('go for another baseline, whose table owns its rows, so that its change is never drawn on the old one', () => {
    const before = 'compare/aaaa/blicks/a.parquet?1'
    const after = 'compare/bbbb/blicks/a.parquet?2'
    expect(rowsStay(before, after, after)).toBe(false)
    expect(rowsStay(after, after, after)).toBe(true)
  })
})

describe('the entry a chart draws', () => {
  const old = entry('a', { hash: 'parquet-sha256:old', data: 'dev/tables/old.parquet' })
  const rebuilt = entry('a', { hash: 'parquet-sha256:new', data: 'dev/tables/new.parquet' })

  it('knows a table by its path and hash, of a Blick that built one', () => {
    expect(tableKey(tableOf(old))).toBe('dev/tables/old.parquet?parquet-sha256:old')
    expect(tableOf(entry('a', { status: 'pending', data: null }))).toBeNull()
    expect(tableOf(entry('a', { status: 'error' }))).toBeNull()
    expect(tableKey(null)).toBeNull()
  })

  it('keeps the old entry with the old rows until the new rows are there', () => {
    expect(settled(old, rebuilt, key(rebuilt), key(old))).toBe(old)
    expect(settled(old, rebuilt, key(rebuilt), key(rebuilt))).toBe(rebuilt)
  })

  it('takes the new entry at once when there is nothing to keep together', () => {
    const failed = entry('a', { status: 'error', data: null, hash: null })
    expect(settled(old, failed, null, key(old))).toBe(failed) // no table to wait for
    expect(settled(failed, rebuilt, key(rebuilt), null)).toBe(rebuilt) // no rows to keep
    expect(settled(old, entry('b'), key(entry('b')), key(old))).toEqual(entry('b')) // another Blick
    expect(settled(null, old, key(old), null)).toBe(old)
  })
})

/** A step that waits until the test lets it go, and the ones begun, to let go with what they did. */
function gated() {
  const steps: ((done?: Step) => void)[] = []
  const step = () => new Promise<Step>(resolve => steps.push((done = 'shown') => resolve(done)))
  return { steps, step }
}

describe('asking dev/info at once', () => {
  it('settles an ask only once a step that started after it has shown its answer', async () => {
    const { steps, step } = gated()
    const ask = coalesced(step)
    const done: string[] = []
    void ask().then(shown => done.push(`first ${shown}`))
    await Promise.resolve()
    expect(steps).toHaveLength(1)
    void ask().then(shown => done.push(`second ${shown}`)) // while the first step runs
    void ask().then(shown => done.push(`third ${shown}`))
    steps[0]!()
    await new Promise(resolve => setTimeout(resolve))
    expect(done).toEqual(['first true']) // the step began before the others asked
    expect(steps).toHaveLength(2) // one more step, for both
    steps[1]!()
    await new Promise(resolve => setTimeout(resolve))
    expect(done).toEqual(['first true', 'second true', 'third true'])
  })

  it('says when no answer newer than the ask was shown: a step failed, or gave up asking again', async () => {
    const { steps, step } = gated()
    const ask = coalesced(step, 1)
    const failed = ask()
    await Promise.resolve()
    steps[0]!('failed') // dev/info did not answer, or a read failed
    expect(await failed).toBe(false)
    const later = ask()
    await Promise.resolve()
    steps[1]!('again') // a Blick was built while the manifest was read: once more
    await new Promise(resolve => setTimeout(resolve))
    steps[2]!('again') // and again: it gives up
    expect(await later).toBe(false)
    const shown = ask()
    await Promise.resolve()
    steps[3]!()
    expect(await shown).toBe(true)
  })

  it('takes a step that throws as one that failed', async () => {
    expect(await coalesced(async () => {
      throw new Error('no answer')
    })()).toBe(false)
  })
})
