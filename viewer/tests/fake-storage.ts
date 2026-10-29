// Stand-ins for the browser's storage, for the tests of what keeps things in it.
import type { KeyValueStorage } from '../app/lib/storage'

/** A storage in memory, as `localStorage` holds strings. */
export function memory(initial: Record<string, string> = {}): KeyValueStorage & { data: Map<string, string> } {
  const data = new Map(Object.entries(initial))
  return { data, getItem: key => data.get(key) ?? null, setItem: (key, value) => void data.set(key, value) }
}

/** A storage the browser blocks: every access throws, as `localStorage` does there. */
export const blocked: KeyValueStorage = {
  getItem: () => {
    throw new Error('SecurityError')
  },
  setItem: () => {
    throw new Error('QuotaExceededError')
  },
}
