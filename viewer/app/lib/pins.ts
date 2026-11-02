// The Blicks the user pinned to the overview, kept in the browser as a list of ids.
import type { BlickEntry } from './manifest'
import { read, write, type KeyValueStorage } from './storage'

/** The key of the pinned ids in the browser's storage. */
export const PINS = 'blicket:pins'

/**
 * The pinned ids in `storage`, in the order pinned: none when it holds no list of strings, or when
 * it cannot be read, as where the browser blocks storage.
 */
export function readPins(storage: KeyValueStorage): string[] {
  let value: unknown
  try {
    value = JSON.parse(read(storage, PINS) ?? '[]')
  }
  catch {
    return []
  }
  if (!Array.isArray(value)) return []
  const list: unknown[] = value
  return list.every((id): id is string => typeof id === 'string') ? list : []
}

/** Keep `ids` as the pins in `storage`; a storage that refuses keeps what it had. */
export function writePins(storage: KeyValueStorage, ids: string[]): void {
  write(storage, PINS, JSON.stringify(ids))
}

/** Whether the Blick holds the pinned `id`: as its id, or as one of its former ids, its aliases. */
function holds(entry: BlickEntry, id: string): boolean {
  return entry.id === id || entry.aliases.includes(id)
}

/**
 * The Blicks the pinned `ids` name, by their id or an alias, so a renamed Blick keeps its pin; each
 * once, in the order pinned. An id that no Blick of `entries` holds is passed over.
 */
export function resolvePins(ids: string[], entries: BlickEntry[]): BlickEntry[] {
  const found = new Set<BlickEntry>()
  for (const id of ids) {
    const entry = entries.find(e => holds(e, id))
    if (entry) found.add(entry)
  }
  return [...found]
}

/**
 * The pinned ids with the Blick `id` pinned, at the end, or unpinned: every pin it holds goes, its
 * aliases' too. `entries` are the build's Blicks, which tell the aliases.
 */
export function togglePin(ids: string[], id: string, entries: BlickEntry[]): string[] {
  const entry = entries.find(e => e.id === id)
  const named = (pin: string) => (entry ? holds(entry, pin) : pin === id)
  return ids.some(named) ? ids.filter(pin => !named(pin)) : [...ids, id]
}
