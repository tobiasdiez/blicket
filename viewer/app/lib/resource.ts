// What the viewer reads and may read again, and how a request that failed is remembered: the
// manifest and the comparisons go through `reloadable`, the requests to `blicket dev` that can
// fail again and again through `failureState`; `dev/info` goes through `devResource`.
import { ref, shallowRef } from 'vue'
import { failure } from './dev'

const text = (cause: unknown) => (cause instanceof Error ? cause.message : String(cause))

/**
 * What a read gives: its `data`, and the revisions of `blicket dev` that the answers it read
 * named in their header `Blicket-Revision`, none when they named none, as a build directory's do.
 */
export interface Revised<T> {
  data: T
  revisions: number[]
}

/** A read done and not shown yet: the revisions it is of, and what shows it. */
export interface Fetched {
  revisions: number[]
  show: () => void
}

/**
 * A resource that `read` reads, and reads again on `reload`; only the latest read counts.
 * `data` is what was read, `merge`d into what was there, `null` before the first read succeeds;
 * `error` says why the first read failed, `stale` why the last read again failed while `data`
 * stays as it was; `loading` is true until the first read ends. `reload` says whether `data` is
 * what it read, and not older, as after a failure or a later read that took over. `fetch` reads
 * without showing: it gives the revisions read and what shows the read, or `null` when it failed
 * or another took over, so that a caller can show several resources of one revision at one moment.
 */
export function reloadable<T>(read: () => Promise<Revised<T>>, merge: (previous: T, next: T) => T = (_, next) => next) {
  const data = shallowRef<T | null>(null)
  const error = ref<string | null>(null)
  const stale = ref<string | null>(null)
  const loading = ref(true)
  let reads = 0

  async function fetch(): Promise<Fetched | null> {
    const mine = ++reads
    try {
      const found = await read()
      if (mine !== reads) return null
      return {
        revisions: found.revisions,
        show: () => {
          if (mine !== reads) return
          data.value = data.value === null ? found.data : merge(data.value, found.data)
          error.value = null
          stale.value = null
        },
      }
    }
    catch (cause) {
      if (mine !== reads) return null
      if (data.value === null) error.value = text(cause)
      else stale.value = text(cause)
      return null
    }
    finally {
      if (mine === reads) loading.value = false
    }
  }

  async function reload(): Promise<boolean> {
    const fetched = await fetch()
    fetched?.show()
    return fetched !== null
  }

  return { data, error, stale, loading, fetch, reload }
}

/**
 * Why a request to `blicket dev` failed, for the alert that says so: its `message`, whether the
 * server did not answer, `unreachable`, how many requests in a row failed, `failures`, and when
 * the last did, `failedAt`. `fail` records a failure, `clear` a success.
 */
export function failureState() {
  const message = ref<string | null>(null)
  const unreachable = ref(false)
  const failures = ref(0)
  const failedAt = ref<Date | null>(null)

  function fail(cause: unknown) {
    const why = failure(cause)
    message.value = why.message
    unreachable.value = why.unreachable
    failures.value++
    failedAt.value = new Date()
  }

  function clear() {
    message.value = null
    unreachable.value = false
    failures.value = 0
  }

  return { message, unreachable, failures, failedAt, fail, clear }
}
