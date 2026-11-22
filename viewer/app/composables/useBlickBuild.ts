import { askedEnded, outcomeLine, pageState, visitOf, visitRequest, type Asked, type Outcome } from '~/lib/jobs'
import type { BlickEntry } from '~/lib/manifest'
import { failureState } from '~/lib/resource'

/**
 * The build of a Blick on its page in a session of `blicket dev`: what the page shows of it,
 * `state`, `null` outside a session; `ask`, which asks for the Blick, once more with `rebuild`,
 * while `asking` says that the request runs and `refused` why the last one failed, which `retry`
 * repeats. Each visit asks once, by itself: for a Blick not built, when it is cheap, or when it
 * is expensive and no Blick a page asked for builds or waits; and for a cheap Blick built, to
 * build it again; and once more after blicket dev was started again. `outcome` says how the
 * Blick's last build ended, and, for a build the page asked for, when: once the Blick has left
 * the jobs, as they are read after blicket dev took the request on, when they could be.
 */
export function useBlickBuild(entry: () => BlickEntry | null) {
  const { dev, noRun } = useManifest()
  const { session, jobs, expensive, stopped, request } = useJobs()
  const state = computed(() => {
    const current = entry()
    return dev.value && !noRun.value && current ? pageState(current, jobs.value, expensive.value) : null
  })
  const asking = ref(false)
  const refused = failureState()
  const decided = ref<string | null>(null)
  const seen = shallowRef<Outcome | null>(null)
  // The build the page asked for that blicket dev took on, until it ended, with the Blick's name.
  const asked = shallowRef<(Asked & { name: string }) | null>(null)
  let last = false

  async function ask(rebuild = false) {
    const current = entry()
    if (!current?.id || asking.value) return
    asking.value = true
    last = rebuild
    try {
      const { answer, fresh } = await request(current.id, rebuild)
      refused.clear()
      // Only jobs of an answer asked for after blicket dev took the build on tell when it ended;
      // without one, the page says no time.
      if (answer !== 'done' && fresh && entry()?.name === current.name) asked.value = { id: current.id, name: current.name, rebuilt: current.status !== 'pending' }
    }
    catch (cause) {
      refused.fail(cause)
    }
    finally {
      asking.value = false
    }
  }

  const visit = computed(() => visitOf(session.value, entry()?.name))
  watch(() => [state.value?.kind, visit.value], () => {
    if (visit.value === undefined || decided.value === visit.value) return
    const wanted = visitRequest(entry(), state.value, stopped.value !== null)
    if (wanted === 'wait') return
    decided.value = visit.value
    if (wanted !== 'none') void ask(wanted === 'rebuild')
  }, { immediate: true })

  // Another Blick on the page: nothing seen of it yet.
  watch(() => entry()?.name, () => {
    seen.value = null
    asked.value = null
  })
  // The build asked for ended once the Blick is not among the jobs any more.
  watch([asked, jobs], () => {
    const ended = askedEnded(asked.value, jobs.value)
    if (!ended) return
    seen.value = { ...ended, at: new Date() }
    asked.value = null
  })

  const outcome = computed(() => {
    const current = entry()
    return state.value && current ? outcomeLine(current, seen.value) : null
  })

  return { state, ask, asking, refused, retry: () => ask(last), outcome }
}
