// The browser's storage, read and written so that a browser that blocks it costs nothing more
// than what it would have kept.

/** What the viewer keeps things in: `localStorage`, or a stand-in. */
export type KeyValueStorage = Pick<Storage, 'getItem' | 'setItem'>

/**
 * The browser's `localStorage`, looked up at each access: where the browser blocks storage, the
 * lookup itself throws, which `read` and `write` catch.
 */
export const browserStorage: KeyValueStorage = {
  getItem: key => localStorage.getItem(key),
  setItem: (key, value) => localStorage.setItem(key, value),
}

/** The text kept under `key`; `null` when there is none, or when the storage cannot be read. */
export function read(storage: KeyValueStorage, key: string): string | null {
  try {
    return storage.getItem(key)
  }
  catch {
    return null
  }
}

/** Keep `value` under `key`; a storage that refuses, blocked or full, keeps what it had. */
export function write(storage: KeyValueStorage, key: string, value: string): void {
  try {
    storage.setItem(key, value)
  }
  catch {
    // What is not kept lasts as long as the page.
  }
}
