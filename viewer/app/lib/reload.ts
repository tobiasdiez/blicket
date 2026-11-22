// Reading the manifest and the comparisons again, as a session of `blicket dev` asks the
// viewer to whenever a Blick is built, without disturbing what the page shows: what did not
// change keeps its object, at any depth, so nothing computed from it is computed again, and a
// Blick rebuilt keeps its entry and rows together until its new rows are there.
import type { Comparison } from './comparison'
import type { DevInfo } from './dev'
import type { BlickEntry } from './manifest'
import type { TableFile } from './table'

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * `next`, read again, sharing with `previous` every part that equals the part it replaces, at any
 * depth: an array or object equal to the one before is that one, and `previous` itself comes back
 * when all of it is equal. Arrays are matched by position, as the manifest and the comparison keep
 * their order.
 */
export function share<T>(previous: unknown, next: T): T {
  if (Object.is(previous, next)) return next
  if (Array.isArray(next)) {
    if (!Array.isArray(previous)) return next
    const items = next.map((item, i) => share(previous[i], item))
    const same = items.length === previous.length && items.every((item, i) => item === previous[i])
    return (same ? previous : items) as T
  }
  if (isRecord(next)) {
    if (!isRecord(previous)) return next
    const keys = Object.keys(next)
    const shared = Object.fromEntries(keys.map(key => [key, share(previous[key], next[key])]))
    const same = keys.length === Object.keys(previous).length && keys.every(key => shared[key] === previous[key])
    return (same ? previous : shared) as T
  }
  return next
}

/**
 * The baseline chosen once the comparisons `offered` are read again: the one `chosen`, `null`
 * ("No baseline") included, while it is offered; otherwise the one checked last.
 */
export function keptChoice(chosen: string | null, offered: readonly Comparison[]): string | null {
  if (chosen === null || offered.some(c => c.baseline.id === chosen)) return chosen
  return offered.at(-1)?.baseline.id ?? null
}

/**
 * What the viewer that follows a session does with an answer of `dev/info`, given the answer whose
 * revision the manifest and the comparisons shown are of, `shown`: show it at once when it is of
 * that revision of that session; otherwise read them again first, also after a restart of
 * `blicket dev` that comes back at the same revision.
 */
export function refreshStep(shown: Pick<DevInfo, 'session' | 'revision'> | null, answer: Pick<DevInfo, 'session' | 'revision'>): 'show' | 'reload' {
  return shown !== null && shown.session === answer.session && shown.revision === answer.revision ? 'show' : 'reload'
}

/**
 * What the refresh does once it read the manifest and the comparisons again, `reads`, for an
 * answer of `dev/info` of `revision`: `show` the three at one moment, when both reads ended and
 * every answer they read was of that revision, or named none, as a build directory's do;
 * `later`, when a later read took one over, or a Blick was built meanwhile, so that the next
 * answer shows them; `failed`, when a read failed, which the page says.
 */
export function afterReading(revision: number, reads: readonly ({ revisions: readonly number[] } | null)[], failed: boolean): 'show' | 'later' | 'failed' {
  if (failed) return 'failed'
  return reads.every(read => read !== null && read.revisions.every(named => named === revision)) ? 'show' : 'later'
}

/** The table of a Blick that a chart draws: of a Blick that built one. */
export function tableOf(entry: BlickEntry | null): TableFile | null {
  return entry?.status === 'ok' && entry.data ? { path: entry.data, hash: entry.hash } : null
}

/** A table as a key, `path?hash`, which tells two tables apart where two objects for one would not. */
export function tableKey(file: TableFile | null): string | null {
  return file ? `${file.path}?${file.hash ?? ''}` : null
}

/**
 * Who owns the rows of each table that the chart of `entry` draws (see `rowsStay`): the Blick
 * its own table's, by its name; the baseline's table, `baseline`, its own rows, by its key.
 */
export function rowOwners(entry: BlickEntry | null, baseline: TableFile | null): { own: string | null, baseline: string | null } {
  return { own: entry?.name ?? null, baseline: tableKey(baseline) }
}

/**
 * Whether the rows a chart shows stay while those of another table are fetched: when there is a
 * table and its `owner` is the one of the rows shown. A Blick's table is owned by the Blick, so
 * that a rebuilt Blick keeps its chart; a baseline's by the table itself, so that another baseline
 * never draws the old one's rows behind the new change.
 */
export function rowsStay(previousOwner: unknown, owner: unknown, key: string | null): boolean {
  return key !== null && Object.is(previousOwner, owner)
}

/**
 * The entry a chart draws: `next`, the entry now, unless it is the Blick of `shown`, the entry
 * drawn, with another table, `nextKey`, than the rows there are, `loadedKey`; then `shown`, so
 * that an entry and its rows change together and the new controls never meet the old rows.
 * Another Blick, an entry without a table and a chart without rows take `next` at once.
 */
export function settled(shown: BlickEntry | null | undefined, next: BlickEntry | null, nextKey: string | null, loadedKey: string | null): BlickEntry | null {
  if (!next || !shown || shown.name !== next.name) return next
  if (nextKey === null || loadedKey === null || nextKey === loadedKey) return next
  return shown
}

/**
 * What a step of `coalesced` did: showed the answer it asked for, found it should ask again at
 * once, or failed to show an answer, which leaves what is shown as it was.
 */
export type Step = 'shown' | 'again' | 'failed'

/**
 * One function for the asks of `step`, which asks something and shows the answer; when it says
 * `again`, it asks again at once, `retries` times at most. Asked while a step runs, it runs one
 * more step after it, for all that asked meanwhile. The promise of each ask settles once a step
 * that started after the ask has ended, asks settling in order: `true` when that step showed its
 * answer, so that whoever asked sees an answer at least as new as the ask, `false` when it gave up
 * or failed. A step that throws failed.
 */
export function coalesced(step: () => Promise<Step>, retries = 0): () => Promise<boolean> {
  let asked = 0 // asks so far
  let answered = 0 // the asks the last step that ended covers
  let running = false
  const waiting: { ask: number, settle: (shown: boolean) => void }[] = []

  async function run() {
    running = true
    try {
      let tries = 0
      while (answered < asked) {
        const covers = asked
        const done = await step().catch((): Step => 'failed')
        if (done === 'again' && tries < retries) {
          tries++
          continue
        }
        tries = 0
        answered = covers
        while (waiting[0] && waiting[0].ask <= covers) waiting.shift()!.settle(done === 'shown')
      }
    }
    finally {
      running = false
    }
  }

  return () => {
    const ask = ++asked
    const answer = new Promise<boolean>(settle => waiting.push({ ask, settle }))
    if (!running) void run()
    return answer
  }
}
