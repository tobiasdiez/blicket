import type { DevInfo } from '~/lib/dev'
import { afterReading, coalesced, refreshStep, type Step } from '~/lib/reload'

// How often `dev/info` is asked while the tab is visible.
const POLL = 1000 // ms
// How many times in a row a refresh reads again at once when a Blick was built while it read,
// before it leaves it to the next tick, so that a run of quick builds is not read in a loop.
const AT_ONCE = 3

// The answer of dev/info whose revision the manifest and the comparisons shown are of, and when
// it came; why they could not be read again, while what is shown is older; and the time, which
// ticks every second while something builds or is queued, for the times the pages count.
const shown = shallowRef<DevInfo | null>(null)
const shownAt = ref(0)
const stale = ref<string | null>(null)
const now = ref(Date.now())
let started = false

/**
 * What `blicket dev` said last of its session, which changes while it runs: `shown`, the answer
 * of `dev/info` whose revision the manifest and the comparisons shown are of, so that what it
 * says of the jobs never disagrees with them; `shownAt`, when it came; and `stale`, why they
 * could not be read again, which they are again at the next answer.
 *
 * The first call with `when` starts following the session while `when` says so: `dev/info` every
 * second while the tab is visible, and when its session or revision is not the one shown, the
 * manifest and the comparisons are read again before the answer is shown, as after a restart of
 * `blicket dev` or the load of another run. A build directory, for which `when` does not hold,
 * asks nothing. `refresh` asks `dev/info` at once, as after a request, and settles once an
 * answer asked for after the call is shown, `true`, or none could be, `false`.
 */
export function useRefresh(when?: () => boolean) {
  if (when && !started) {
    started = true
    effectScope(true).run(() => follow(when))
  }
  return { shown, shownAt, stale, now, refresh }
}

/**
 * Ask `dev/info` and show its answer, once the manifest and comparisons read again agree; asked
 * while that runs, once more after it; when a Blick was built while they were read, asked again
 * at once, a few times at most. Settles to whether an answer asked for after the call was shown:
 * not when `dev/info` did not answer, a read failed, or a Blick was built at each try.
 */
const refresh = coalesced(async (): Promise<Step> => {
  const devInfo = useDev()
  await devInfo.reload(true)
  const answer = devInfo.info.value
  return devInfo.error.value !== null || answer === null ? 'failed' : show(answer)
}, AT_ONCE)

/**
 * Show `answer`; when it is of another revision or session, once the manifest and the comparisons
 * are read again and are of its revision, as their header says, all three at one moment, so that
 * no page sees a Blick built and still building. When they are not, a Blick was built meanwhile:
 * nothing is shown, and `again` says to ask again; a read that fails leaves what is shown, says
 * why, and `failed`.
 */
async function show(answer: DevInfo): Promise<Step> {
  if (refreshStep(shown.value, answer) === 'reload') {
    const manifest = useManifest()
    const comparison = useComparison()
    const [read, compared] = await Promise.all([manifest.fetch(), comparison.fetch()])
    const failure = (!read && manifest.stale.value) || (!compared && comparison.stale.value) || null
    const step = afterReading(answer.revision, [read, compared], failure !== null)
    if (step === 'failed') stale.value = failure
    if (step !== 'show' || !read || !compared) return step === 'later' ? 'again' : 'failed'
    read.show()
    compared.show()
    stale.value = null
  }
  if (shown.value !== answer) {
    shown.value = answer
    shownAt.value = Date.now()
    now.value = shownAt.value
  }
  return 'shown'
}

/** Every second: the time, while something builds or is queued, and `dev/info`, while visible. */
function tick() {
  if (shown.value?.jobs.length) now.value = Date.now()
  if (document.visibilityState === 'visible') void refresh()
}

function follow(when: () => boolean) {
  let polling: ReturnType<typeof setInterval> | undefined
  watch(when, (on) => {
    if (on && polling === undefined) {
      polling = setInterval(tick, POLL)
      document.addEventListener('visibilitychange', tick)
      void refresh()
    }
    else if (!on && polling !== undefined) {
      clearInterval(polling)
      document.removeEventListener('visibilitychange', tick)
      polling = undefined
    }
  }, { immediate: true })
}
