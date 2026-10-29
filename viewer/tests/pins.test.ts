import { describe, expect, it } from 'vitest'
import type { BlickEntry } from '../app/lib/manifest'
import { PINS, readPins, resolvePins, togglePin, writePins } from '../app/lib/pins'
import { blocked, memory } from './fake-storage'

const entries = [
  { id: 'a/new', aliases: ['a/old'] },
  { id: 'b/y', aliases: [] },
] as unknown as BlickEntry[]

describe('the pins', () => {
  it('are kept as a list of ids, in the order pinned', () => {
    const storage = memory()
    expect(readPins(storage)).toEqual([])
    writePins(storage, ['b/y', 'a/x'])
    expect([storage.data.get(PINS), readPins(storage)]).toEqual(['["b/y","a/x"]', ['b/y', 'a/x']])
  })

  it('are none when the storage holds something else', () => {
    for (const value of ['{"a": 1}', '["a", 2]', '"a"', 'not json']) expect(readPins(memory({ [PINS]: value }))).toEqual([])
  })

  it('are none, and kept by nobody, where the browser blocks storage', () => {
    expect(readPins(blocked)).toEqual([])
    expect(() => writePins(blocked, ['a/x'])).not.toThrow()
  })

  it('name a renamed Blick through its aliases, each Blick once, and pass over the ids a build lacks', () => {
    expect(resolvePins(['b/y', 'gone', 'a/old', 'a/new'], entries)).toEqual([entries[1], entries[0]])
  })

  it('pin at the end and unpin every id of the Blick, its aliases too', () => {
    expect(togglePin(['gone'], 'b/y', entries)).toEqual(['gone', 'b/y'])
    expect(togglePin(['a/old', 'b/y', 'a/new'], 'a/new', entries)).toEqual(['b/y'])
    expect(togglePin(['gone'], 'gone', entries)).toEqual([])
  })

  it('follow the page where the browser blocks storage, which keeps nothing', () => {
    let ids: string[] = []
    for (const id of ['a/new', 'a/new', 'b/y', 'a/new']) {
      ids = togglePin(ids, id, entries)
      writePins(blocked, ids)
    }
    expect(ids).toEqual(['b/y', 'a/new'])
  })
})
