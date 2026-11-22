import { describe, expect, it } from 'vitest'
import type { BlickEntry } from '../app/lib/manifest'
import { ago, dropQuestion, expensiveBuilt, keepListed, loadLabel, namesOf, runsSetting, ticked, whenText } from '../app/lib/runs'

const now = new Date('2026-11-03T12:00:00Z')
const blick = (expensive: boolean, status: string) => ({ expensive, status }) as unknown as BlickEntry

describe('the run picker', () => {
  it('says how long ago a run changed, in the largest whole unit', () => {
    expect(ago('2026-10-26T10:25:13Z', now)).toBe('8 days ago')
    expect(ago('2026-11-02T12:00:00Z', now)).toBe('1 day ago')
    expect(ago('2026-11-03T09:30:00Z', now)).toBe('2 hours ago')
    expect(ago('2026-11-03T11:59:00Z', now)).toBe('1 minute ago')
    expect(ago('2026-11-03T11:59:30Z', now)).toBe('just now')
    expect(ago('2026-11-03T12:05:00Z', now)).toBe('just now') // a clock ahead of the browser's
    expect(ago('2025-06-01T08:00:00Z', now)).toBe('2025-06-01')
    expect(ago('not a time', now)).toBe('not a time')
  })

  it('names the load and the globs the runs come from', () => {
    expect([0, 1, 2, 3].map(loadLabel)).toEqual(['Load', 'Load', 'Load 2 runs as one', 'Load 3 runs as one'])
    expect(runsSetting(['../../data_out/*_plastics_*'])).toBe('runs = ["../../data_out/*_plastics_*"]')
    expect(runsSetting(['output/*', 'archive/"old"/*'])).toBe('runs = ["output/*", "archive/\\"old\\"/*"]')
  })

  const runs = ['c', 'b', 'a'].map(name => ({ path: `/data/${name}`, name, modified: '2026-10-26T10:25:13Z', project: false, served: false }))

  it('names the runs of a load in the order of the list', () => {
    expect(namesOf(['/data/a', '/data/c'], runs)).toBe('c, a')
    expect(namesOf(['/data/gone'], runs)).toBe('')
  })

  it('keeps the ticks of the folders a new list still has', () => {
    expect(keepListed(['/data/a', '/data/gone', '/data/c'], runs)).toEqual(['/data/a', '/data/c'])
    expect(keepListed([], runs)).toEqual([])
  })

  it('says that the project itself is computed from code, where a folder says when it changed', () => {
    expect(whenText({ path: '/p', name: 'This project', modified: null, project: true, served: false }, now)).toBe('computed from code')
    expect(whenText(runs[0]!, now)).toBe('8 days ago')
  })

  it('loads the project itself alone: ticking it unticks the folders, and ticking a folder unticks it', () => {
    const listed = [{ path: '/p', name: 'This project', modified: null, project: true, served: false }, ...runs]
    expect(ticked(['/data/a', '/data/c'], '/p', true, listed)).toEqual(['/p'])
    expect(ticked(['/p'], '/data/a', true, listed)).toEqual(['/data/a'])
    expect(ticked(['/data/a'], '/data/c', true, listed)).toEqual(['/data/a', '/data/c'])
    expect(ticked(['/data/a', '/data/c'], '/data/a', false, listed)).toEqual(['/data/c'])
  })

  it('asks before a load drops the expensive Blicks built so far, and counts only those', () => {
    expect(expensiveBuilt([blick(true, 'ok'), blick(true, 'error'), blick(true, 'pending'), blick(false, 'ok')])).toBe(2)
    expect(dropQuestion(12)).toBe('Loading another run drops the 12 expensive Blicks built so far.')
    expect(dropQuestion(1)).toBe('Loading another run drops the expensive Blick built so far.')
  })
})
