import { bodyOf, devFetch, failure } from '~/lib/dev'

/**
 * A resource of `blicket dev` at `path`, fetched as soon as `ready` turns true and again on
 * `reload`: its `data`, of the shape `is` checks, or why it is missing, `error`, and whether
 * because the server did not answer, `unreachable`. `loading` says that a fetch runs, `failures`
 * how many fetches in a row failed, `failedAt` when the last one did. The returned function
 * gives the refs, the watch on `ready` installed on its first call.
 */
export function devResource<T>(path: string, is: (body: unknown) => body is T, what: string, ready: () => boolean | undefined) {
  const data = shallowRef<T | null>(null)
  const error = ref<string | null>(null)
  const unreachable = ref(false)
  const loading = ref(false)
  const failures = ref(0)
  const failedAt = ref<Date | null>(null)
  let scope: ReturnType<typeof effectScope> | null = null

  async function reload(): Promise<void> {
    loading.value = true
    try {
      data.value = await bodyOf(await devFetch(path, { cache: 'no-store' }), is, what)
      error.value = null
      unreachable.value = false
      failures.value = 0
    }
    catch (cause) {
      const why = failure(cause)
      error.value = why.message
      unreachable.value = why.unreachable
      failures.value++
      failedAt.value = new Date()
    }
    finally {
      loading.value = false
    }
  }

  return () => {
    if (!scope) {
      // Detached, so that the watch outlives the component that first asked.
      scope = effectScope(true)
      scope.run(() => watch(ready, (on) => {
        if (on) void reload()
      }, { immediate: true }))
    }
    return { data, error, unreachable, loading, failures, failedAt, reload }
  }
}
