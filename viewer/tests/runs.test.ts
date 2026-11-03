import { describe, expect, it } from 'vitest'
import { ago, keepListed, loadLabel, namesOf, runsSetting } from '../app/lib/runs'

const now = new Date('2026-11-03T12:00:00Z')

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

  const runs = ['c', 'b', 'a'].map(name => ({ path: `/data/${name}`, name, modified: '2026-10-26T10:25:13Z' }))

  it('names the runs of a load in the order of the list', () => {
    expect(namesOf(['/data/a', '/data/c'], runs)).toBe('c, a')
    expect(namesOf(['/data/gone'], runs)).toBe('')
  })

  it('keeps the ticks of the folders a new list still has', () => {
    expect(keepListed(['/data/a', '/data/gone', '/data/c'], runs)).toEqual(['/data/a', '/data/c'])
    expect(keepListed([], runs)).toEqual([])
  })
})
