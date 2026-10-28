import type { BuilderRequest } from '~/lib/builder'
import { failure, postQuery } from '~/lib/dev'
import { latest } from '~/lib/latest'
import type { BlickEntry } from '~/lib/manifest'
import { fetchTable, type Row } from '~/lib/table'

// How long the builder waits after a change before it asks, so that a burst of changes is one
// query; the first query goes at once.
const DEBOUNCE = 300 // ms
// How long a query runs before the chart shown is marked as not the latest.
const SLOW = 400 // ms

interface Answer {
  entry: BlickEntry
  rows: Row[] | null
  request: BuilderRequest
}

/**
 * The answer of `dev/query` to `request`, asked again whenever the request changes, debounced;
 * only the latest request's answer counts. `entry` and `rows` are the last good answer and its
 * table, swapped together once the table is there, so a chart drawn from them stays until the
 * next one can be drawn, and `shown` is the request they answer. `failed` is the latest answer
 * when it has an error, `error` why the latest request failed, `unreachable` whether because the
 * server did not answer, `failures` how many requests in a row failed and `failedAt` when the last
 * did; `pending` says that a query waits or runs, `slow` that it has run for a
 * while; `stale` that the chart shown is not the latest: slow, failed or refused.
 */
export function useQuery(request: MaybeRefOrGetter<BuilderRequest | null>) {
  const entry = shallowRef<BlickEntry | null>(null)
  const rows = shallowRef<Row[] | null>(null)
  const shown = shallowRef<BuilderRequest | null>(null)
  const failed = shallowRef<BlickEntry | null>(null)
  const error = ref<string | null>(null)
  const unreachable = ref(false)
  const failures = ref(0)
  const failedAt = ref<Date | null>(null)
  const pending = ref(false)
  const slow = ref(false)
  const stale = computed(() => slow.value || failed.value !== null || error.value !== null)
  let slowTimer: ReturnType<typeof setTimeout> | undefined

  async function work(body: BuilderRequest, signal: AbortSignal): Promise<Answer> {
    slowTimer = setTimeout(() => {
      slow.value = true
    }, SLOW)
    const answer = await postQuery(body, signal)
    if (answer.status !== 'ok' || !answer.data) return { entry: answer, rows: null, request: body }
    const table = await fetchTable({ path: answer.data, hash: answer.hash })
    return { entry: answer, rows: table, request: body }
  }

  const runner = latest(work, (outcome) => {
    clearTimeout(slowTimer)
    pending.value = false
    slow.value = false
    if ('error' in outcome) {
      const why = failure(outcome.error)
      error.value = why.message
      unreachable.value = why.unreachable
      failed.value = null // the refusal shown before is not the latest answer
      failures.value++
      failedAt.value = new Date()
      return
    }
    error.value = null
    unreachable.value = false
    failures.value = 0
    const answer = outcome.value
    if (answer.rows) {
      entry.value = answer.entry
      rows.value = answer.rows
      shown.value = answer.request
      failed.value = null
    }
    else {
      failed.value = answer.entry
    }
  }, () => (entry.value || failed.value ? DEBOUNCE : 0))

  function ask() {
    clearTimeout(slowTimer)
    slow.value = false
    const body = toValue(request)
    if (!body) {
      runner.cancel()
      entry.value = null
      rows.value = null
      shown.value = null
      failed.value = null
      error.value = null
      unreachable.value = false
      failures.value = 0
      pending.value = false
      return
    }
    pending.value = true
    runner.ask(body)
  }

  watch(() => JSON.stringify(toValue(request)), ask, { immediate: true })
  onScopeDispose(() => {
    clearTimeout(slowTimer)
    runner.cancel()
  })
  return { entry, rows, shown, failed, error, unreachable, failures, failedAt, pending, slow, stale, retry: ask }
}
