import { describe, expect, it } from 'vitest'
import type { Job } from '../app/lib/dev'
import { askedEnded, buildingLine, buildMarks, elapsed, expensiveIds, footerText, isInvalid, lineText, loadingLine, notBuiltLine, outcomeLine, overviewNotice, pageState, pendingCount, pendingText, rebuildable, statusLine, visitOf, visitRequest, wallTime, type PageState } from '../app/lib/jobs'
import { byStatus, type BlickEntry, type Problem } from '../app/lib/manifest'

function entry(id: string, extra: Partial<BlickEntry> = {}): BlickEntry {
  return { id, name: id, aliases: [], group: 'g', definition: { title: id.toUpperCase() }, source: { file: 'blicks/g.py', line: 13 }, data: null, hash: null, columns: null, controls: [], problems: [], timing_ms: 3200, skipped: null, status: 'ok', ...extra } as unknown as BlickEntry
}

// An expensive Blick, built or not; a cheap one, built or not.
const costly = (id: string, extra: Partial<BlickEntry> = {}) => entry(id, { expensive: true, ...extra })
const pending = (id: string) => costly(id, { status: 'pending', pending: true, timing_ms: null })
const cheapPending = (id: string) => entry(id, { status: 'pending', pending: true, timing_ms: null })
const problem: Problem = { kind: 'invalid_definition', severity: 'error', source: null, module: null, ids: [], message: 'tolerance must be below 1', traceback: null }
const invalid = entry('p/invalid', { status: 'error', timing_ms: null, problems: [problem] })
const failed = costly('s/scrap', { status: 'error', timing_ms: 400, problems: [{ ...problem, kind: 'transformation' }] })
const T0 = '2026-11-11T12:01:05Z'
const building = (id: string, seconds = 40, asked = true): Job => ({ id, state: 'building', asked, since: T0, seconds })
const background = (id: string, seconds = 1) => building(id, seconds, false)
const queued = (id: string): Job => ({ id, state: 'queued', asked: true, since: T0, seconds: 1 })
const title = (id: string) => id.toUpperCase()

/** The line the page shows `later` seconds after dev/info answered, as one text. */
function text(state: PageState, later = 0, lost = false): string | null {
  const line = statusLine(state, later, lost)
  return line && lineText(line, title)
}

describe('the page of an expensive Blick', () => {
  it('asks for it while no Blick a page asked for builds or waits, the background not counted', () => {
    expect(pageState(pending('c/trade'), [])).toEqual({ kind: 'ask' })
    expect(pageState(pending('c/trade'), [background('s/shares')])).toEqual({ kind: 'ask' })
    expect(visitRequest(pending('c/trade'), { kind: 'ask' }, false)).toBe('build')
  })

  it('offers Build next while another Blick a page asked for builds or waits, instead of queueing behind it', () => {
    expect(pageState(pending('s/prod'), [building('c/trade')])).toEqual({ kind: 'other', other: building('c/trade') })
    expect(pageState(pending('s/prod'), [background('s/shares'), queued('c/trade')])).toEqual({ kind: 'other', other: queued('c/trade') })
    expect(visitRequest(pending('s/prod'), { kind: 'other', other: building('c/trade') }, false)).toBe('wait')
  })

  it('says behind which Blick one is queued, and how many more are queued before it', () => {
    expect(pageState(pending('s/prod'), [building('c/trade'), queued('s/prod')])).toEqual({ kind: 'queued', behind: building('c/trade'), ahead: 0 })
    expect(pageState(pending('s/prod'), [building('c/trade'), queued('a/b'), queued('s/prod')])).toEqual({ kind: 'queued', behind: building('c/trade'), ahead: 1 })
  })

  it('says a Blick builds, and rebuilds when it was built, with one more build after it', () => {
    expect(pageState(pending('c/trade'), [building('c/trade')])).toEqual({ kind: 'building', job: building('c/trade') })
    expect(pageState(costly('c/trade'), [building('c/trade')])).toEqual({ kind: 'rebuilding', job: building('c/trade'), again: false })
    expect(pageState(failed, [building('s/scrap'), queued('s/scrap')])).toEqual({ kind: 'rebuilding', job: building('s/scrap'), again: true })
  })

  it('shows a Blick built, in error or skipped, with Rebuild, and a rebuild queued with those before it', () => {
    for (const built of [costly('c/trade'), failed, costly('p/v', { status: 'skipped', skipped: 'no validation.mif' })]) {
      expect(pageState(built, [])).toEqual({ kind: 'built', behind: null, ahead: 0 })
      expect(rebuildable(built, pageState(built, []))).toBe(true)
      expect(visitRequest(built, pageState(built, []), false)).toBe('none') // only Rebuild builds it again
    }
    expect(pageState(costly('c/trade'), [building('s/prod'), queued('a'), queued('c/trade')])).toEqual({ kind: 'built', behind: building('s/prod'), ahead: 1 })
  })

  it('offers Rebuild only once built, and while it rebuilds', () => {
    const states: PageState[] = [{ kind: 'ask' }, { kind: 'other', other: building('a') }, { kind: 'queued', behind: null, ahead: 0 }, { kind: 'building', job: building('a') }]
    expect(states.map(state => rebuildable(pending('a'), state))).toEqual([false, false, false, false])
    expect([rebuildable(costly('a'), { kind: 'rebuilding', job: building('a'), again: false }), rebuildable(costly('a'), null)]).toEqual([true, false])
  })
})

describe('the page of a cheap Blick', () => {
  it('asks for it at once, whatever builds, and then waits in the queue or builds', () => {
    expect(pageState(cheapPending('s/shares'), [building('c/trade')])).toEqual({ kind: 'ask' })
    expect(visitRequest(cheapPending('s/shares'), { kind: 'ask' }, false)).toBe('build')
    expect(pageState(cheapPending('s/shares'), [building('c/trade'), queued('s/shares')])).toEqual({ kind: 'queued', behind: building('c/trade'), ahead: 0 })
    expect(pageState(cheapPending('s/shares'), [background('s/shares')])).toEqual({ kind: 'building', job: background('s/shares') })
  })

  it('builds it again at each visit, without Rebuild', () => {
    const built = entry('s/shares')
    expect(pageState(built, [])).toEqual({ kind: 'built', behind: null, ahead: 0 })
    expect(visitRequest(built, pageState(built, []), false)).toBe('rebuild')
    expect(rebuildable(built, pageState(built, []))).toBe(false)
    // Built again already, as another tab asked: nothing more.
    expect(visitRequest(built, pageState(built, [building('s/shares')]), false)).toBe('none')
  })

  it('shows what was built under Updating…, how long, and after which expensive Blick it waits', () => {
    const built = entry('s/shares')
    expect(pageState(built, [building('s/shares', 8)])).toEqual({ kind: 'updating', job: building('s/shares', 8), behind: null })
    expect(text(pageState(built, [building('s/shares', 8)]))).toBe('Updating… 0:08')
    const expensive = new Set(['c/trade'])
    const behind = pageState(built, [building('c/trade', 42), queued('s/shares')], expensive)
    expect(behind).toEqual({ kind: 'updating', job: queued('s/shares'), behind: building('c/trade', 42) })
    expect(statusLine(behind, 0)).toEqual(['Updating after ', { blick: 'c/trade' }, { time: ' (0:42)' }])
    expect(text(behind)).toBe('Updating after C/TRADE (0:42)')
    // Behind a cheap Blick, which takes no time to speak of: how long it waited.
    expect(text(pageState(built, [background('s/prod'), queued('s/shares')], expensive))).toBe('Updating… 0:01')
    expect(text(behind, 0, true)).toBe('It was updating when blicket dev stopped answering.')
  })

  it('takes the ids of the expensive Blicks from the manifest', () => {
    expect([...expensiveIds([costly('a'), entry('b'), pending('c'), invalid])]).toEqual(['a', 'c'])
  })
})

describe('a visit of a Blick\'s page', () => {
  it('asks once per visit, a visit to another Blick or another session being another', () => {
    expect(visitOf('s1', 'c/trade')).toBe('s1 c/trade')
    expect(visitOf('s2', 'c/trade')).not.toBe(visitOf('s1', 'c/trade'))
    expect(visitOf(undefined, 'c/trade')).toBeUndefined() // before dev/info answers
    expect(visitOf('s1', undefined)).toBeUndefined()
  })

  it('asks nothing of a Blick that builds or waits, of a Blick whose definition is invalid, and once the worker stopped', () => {
    expect(visitRequest(pending('a'), { kind: 'building', job: building('a') }, false)).toBe('none')
    expect(visitRequest(cheapPending('a'), { kind: 'queued', behind: null, ahead: 0 }, false)).toBe('none')
    expect(visitRequest(invalid, { kind: 'invalid' }, false)).toBe('none')
    expect(visitRequest(pending('a'), { kind: 'ask' }, true)).toBe('none')
    expect(visitRequest(null, null, false)).toBe('wait')
  })

  it('never builds a Blick whose definition is invalid, which no build made, and says what to do', () => {
    expect([isInvalid(invalid), isInvalid(failed)]).toEqual([true, false])
    expect(pageState(invalid, [])).toEqual({ kind: 'invalid' })
    expect(rebuildable(invalid, pageState(invalid, []))).toBe(false)
    expect(statusLine({ kind: 'invalid' }, 0)).toBeNull()
    expect(outcomeLine(invalid, null)).toBe('Cannot be built: its definition is invalid. Fix it at blicks/g.py:13 and restart blicket dev.')
  })
})

describe('what the page says of a build', () => {
  it('counts the time from what dev/info said, as m:ss, and h:mm:ss after an hour', () => {
    expect([elapsed(42), elapsed(62), elapsed(3723), elapsed(-5)]).toEqual(['0:42', '1:02', '1:02:03', '0:00'])
    expect(text({ kind: 'building', job: building('c/trade', 40) }, 2.5)).toBe('Building… 0:42 · what the transformation prints is in the terminal')
  })

  it('names the other Blick by its title, as a link, and where one is queued', () => {
    expect(statusLine({ kind: 'other', other: building('cement/trade', 42) }, 0)).toEqual([{ blick: 'cement/trade' }, ' is building', { time: ' (0:42)' }, '.'])
    expect(text({ kind: 'other', other: building('cement/trade', 42) })).toBe('CEMENT/TRADE is building (0:42).')
    expect(text({ kind: 'other', other: queued('cement/trade') })).toBe('CEMENT/TRADE is about to build.')
    expect(text({ kind: 'queued', behind: building('cement/trade'), ahead: 0 })).toBe('Queued behind CEMENT/TRADE')
    expect(text({ kind: 'queued', behind: building('cement/trade'), ahead: 1 })).toBe('Queued behind CEMENT/TRADE and 1 more')
    expect(text({ kind: 'rebuilding', job: building('a', 12), again: true })).toBe('Rebuilding… 0:12 · one more build follows')
    expect(text({ kind: 'built', behind: building('s/prod'), ahead: 2 })).toBe('Rebuild queued behind S/PROD and 2 more')
    expect(text({ kind: 'built', behind: null, ahead: 0 })).toBeNull()
  })

  it('stops counting when blicket dev does not answer, and says that it was building', () => {
    expect(text({ kind: 'building', job: building('a') }, 30, true)).toBe('It was building when blicket dev stopped answering.')
    expect(text({ kind: 'rebuilding', job: building('a'), again: false }, 30, true)).toBe('It was rebuilding when blicket dev stopped answering.')
    expect(text({ kind: 'other', other: building('b') }, 30, true)).toBe('B was building when blicket dev stopped answering.')
  })

  it('leaves the time out of what a screen reader is told', () => {
    const line = statusLine({ kind: 'building', job: building('a', 42) }, 0)!
    expect(lineText(line, title)).toBe('Building… 0:42 · what the transformation prints is in the terminal')
    expect(lineText(line, title, true)).toBe('Building… · what the transformation prints is in the terminal')
    // The overview's hidden line, without the time and its parentheses.
    expect(lineText(buildingLine([building('a', 5)], 1)!, title, true)).toBe('A is building.')
  })

  it('sees a build it asked for end once the Blick has left the jobs, also when its entry did not change', () => {
    const asked = { id: 's/shares', rebuilt: true }
    expect(askedEnded(asked, [building('s/shares')])).toBeNull()
    expect(askedEnded(asked, [building('c/trade'), queued('s/shares')])).toBeNull()
    // Built again to the same table: the entry is the same, and the jobs alone tell.
    expect(askedEnded(asked, [])).toEqual({ rebuilt: true })
    expect(askedEnded({ id: 'c/trade', rebuilt: false }, [background('s/shares')])).toEqual({ rebuilt: false })
    expect(askedEnded(null, [])).toBeNull()
  })

  it('says how the last build ended, in how long, and when, if the page saw it end', () => {
    const at = new Date(2026, 10, 11, 12, 4, 10)
    expect(outcomeLine(entry('c/trade'), null)).toBe('Built in 3.2 s')
    expect(outcomeLine(entry('c/trade', { timing_ms: 180 }), { rebuilt: true, at })).toBe('Rebuilt in 180 ms at 12:04:10')
    expect(outcomeLine(failed, { rebuilt: false, at })).toBe('Failed in 400 ms at 12:04:10')
    expect(outcomeLine(entry('p/v', { status: 'skipped', timing_ms: 90 }), null)).toBe('Skipped in 90 ms')
    expect(outcomeLine(pending('a'), null)).toBeNull()
    expect([wallTime(412), wallTime(999.6), wallTime(3200), wallTime(59_960), wallTime(75_900), wallTime(3_725_300)])
      .toEqual(['412 ms', '1.0 s', '3.2 s', '1 min 0 s', '1 min 16 s', '1 h 2 min 5 s'])
  })
})

describe('the Blicks of a session elsewhere', () => {
  it('marks each Blick building or queued, one word for one state', () => {
    expect([...buildMarks([building('a'), queued('b'), queued('a')])]).toEqual([['a', 'building'], ['b', 'queued']])
    expect([...buildMarks([background('s')])]).toEqual([['s', 'building']]) // a spinner for the background too
  })

  it('keeps the marks it gave while only the time of the jobs goes on, so nothing is computed again', () => {
    const before = buildMarks([building('a', 1), queued('b')])
    expect(buildMarks([building('a', 2), queued('b')], before)).toBe(before)
    expect(buildMarks([building('b', 0)], before)).toEqual(new Map([['b', 'building']]))
    expect([pendingText('building'), pendingText('queued'), pendingText(undefined)]).toEqual(['Building…', 'Queued', 'Not built yet'])
  })

  it('counts the Blicks not built yet over all of them', () => {
    const entries = [pending('a'), pending('b'), entry('c'), failed, invalid]
    expect(notBuiltLine(entries)).toBe('2 of 5 Blicks not built yet')
    expect(notBuiltLine([entry('c')])).toBe('None of the 1 Blick is left to build')
    expect(pendingCount(entries)).toBe('2 not built yet')
    expect(pendingCount([entry('c')])).toBe('')
    expect(byStatus(entries).pending.map(e => e.name)).toEqual(['a', 'b'])
  })

  it('says on the overview which Blick a page asked for builds first, and not the background', () => {
    expect(lineText(buildingLine([building('a', 5), queued('b')], 1)!, title)).toBe('A is building (0:06).')
    expect(lineText(buildingLine([background('s'), queued('b')], 1)!, title)).toBe('B is about to build.')
    expect(buildingLine([background('s')], 0)).toBeNull()
    expect(buildingLine([], 0)).toBeNull()
    expect(lineText(buildingLine([building('a', 5)], 1, true)!, title)).toBe('A was building when blicket dev stopped answering.')
  })

  it('notes on the overview that an expensive Blick is built when opened, and counts what is left', () => {
    const notice = overviewNotice([pending('a'), costly('b'), entry('c')], 'A is building (0:06).')
    expect(notice).toEqual({ title: 'An expensive Blick is built when you open it.', description: '1 of 3 Blicks not built yet · A is building (0:06).' })
    expect(overviewNotice([costly('b'), entry('c')], null)).toEqual({ title: 'An expensive Blick is built when you open it.', description: 'None of the 2 Blicks is left to build' })
    // Without an expensive Blick, the count alone while the background builds, then nothing.
    expect(overviewNotice([cheapPending('a'), entry('c')], null)).toEqual({ title: '1 of 2 Blicks not built yet', description: '' })
    expect(overviewNotice([entry('c')], null)).toBeNull()
  })

  it('says on the run picker which Blick a load waits for, and how long it has built, then that the run loads', () => {
    expect(loadingLine('b', [background('s/shares', 11)], 1, title)).toEqual({ text: 'Waiting for S/SHARES to build…', time: '0:12' })
    expect(loadingLine('b', [], 0, title)).toEqual({ text: 'Loading b; the loader\'s output goes to the terminal.', time: null })
  })

  it('names the session in the footer, and a build when there is one', () => {
    const manifest = { blicket: '0.6.0', build: { id: '5d0c3f1e2a9b8c47', incomplete: false, loader_ms: 1 }, created_at: '2026-11-11T12:01:05.123Z' }
    expect(footerText(manifest, false)).toBe('blicket 0.6.0 · build 5d0c3f1e2a9b8c47 · 2026-11-11 12:01 UTC')
    expect(footerText(manifest, true)).toBe('blicket 0.6.0 · session started 2026-11-11 12:01 UTC')
  })
})
