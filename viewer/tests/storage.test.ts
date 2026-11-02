import { describe, expect, it } from 'vitest'
import { SIDEBAR, storedOpen, storeOpen } from '../app/lib/sidebar'
import { read, write } from '../app/lib/storage'
import { blocked, memory } from './fake-storage'

describe('the browser\'s storage', () => {
  it('keeps text by key', () => {
    const storage = memory()
    write(storage, 'k', 'v')
    expect([read(storage, 'k'), read(storage, 'other')]).toEqual(['v', null])
  })

  it('reads as empty and keeps nothing where the browser blocks it', () => {
    expect(read(blocked, 'k')).toBeNull()
    expect(() => write(blocked, 'k', 'v')).not.toThrow()
  })

  it('keeps whether the sidebar is open, which it is unless kept closed', () => {
    const storage = memory()
    expect(storedOpen(storage)).toBe(true)
    storeOpen(storage, false)
    expect([storage.data.get(SIDEBAR), storedOpen(storage)]).toEqual(['closed', false])
    storeOpen(storage, true)
    expect([storedOpen(storage), storedOpen(blocked)]).toEqual([true, true])
  })
})
