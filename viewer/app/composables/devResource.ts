import { bodyOf, devFetch } from '~/lib/dev'
import { share } from '~/lib/reload'
import { failureState } from '~/lib/resource'

/**
 * A resource of `blicket dev` at `path`, fetched as soon as `ready` turns true and again on
 * `reload`: its `data`, of the shape `is` checks, or why it is missing, `error`, and whether
 * because the server did not answer, `unreachable`. `loading` says that a fetch runs, `failures`
 * how many fetches in a row failed, `failedAt` when the last one did. A `quiet` reload, as a poll
 * makes it, leaves `loading` as it is. The data fetched last stays while a fetch fails, and an
 * answer equal to it keeps it, so that nothing computed from it is computed again. The returned
 * function gives the refs, the watch on `ready` installed on its first call.
 */
export function devResource<T>(path: string, is: (body: unknown) => body is T, what: string, ready: () => boolean | undefined) {
  const data = shallowRef<T | null>(null)
  const loading = ref(false)
  const { message: error, unreachable, failures, failedAt, fail, clear } = failureState()
  let scope: ReturnType<typeof effectScope> | null = null

  async function reload(quiet = false): Promise<void> {
    if (!quiet) loading.value = true
    try {
      data.value = share(data.value, await bodyOf(await devFetch(path, { cache: 'no-store' }), is, what))
      clear()
    }
    catch (cause) {
      fail(cause)
    }
    finally {
      if (!quiet) loading.value = false
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
