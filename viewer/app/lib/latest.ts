/** What became of a request: its value, or why it failed. */
export type Outcome<T> = { value: T } | { error: unknown }

/** Runs only the latest of a series of requests; see `latest`. */
export interface Latest<R> {
  /** Ask for `request`, in place of any request asked before. */
  ask(request: R): void
  /** Drop the request waiting or running; its outcome is never settled. */
  cancel(): void
}

/**
 * Runs only the latest of a series of requests. `ask` cancels the request that waits or runs,
 * waits `delay()` ms, so that a burst of requests runs once, and runs `work` with a signal that
 * aborts when a newer request is asked. An outcome reaches `settle` only when no newer request
 * was asked meanwhile, so an answer that comes late never replaces a newer one, and an aborted
 * request settles nothing.
 */
export function latest<R, T>(
  work: (request: R, signal: AbortSignal) => Promise<T>,
  settle: (outcome: Outcome<T>) => void,
  delay: () => number,
): Latest<R> {
  let ticket = 0
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | undefined

  function cancel(): void {
    clearTimeout(timer)
    controller?.abort()
    controller = null
    ticket++
  }

  function ask(request: R): void {
    cancel()
    const mine = ticket
    timer = setTimeout(() => {
      const abort = new AbortController()
      controller = abort
      work(request, abort.signal).then(
        (value) => {
          if (mine === ticket) settle({ value })
        },
        (error: unknown) => {
          if (mine === ticket) settle({ error }) // an aborted request is never the latest
        },
      )
    }, delay())
  }

  return { ask, cancel }
}
