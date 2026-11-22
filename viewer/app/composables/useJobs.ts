import { postBuild, type BuildAnswer } from '~/lib/dev'
import { buildMarks, expensiveIds, type BuildMark } from '~/lib/jobs'

/** What every page takes from `useJobs`, computed once. */
function derive() {
  const { shown, shownAt, stale, now, refresh } = useRefresh()
  const { error } = useDev()
  const { manifest } = useManifest()
  const session = computed(() => shown.value?.session)
  const jobs = computed(() => shown.value?.jobs ?? [])
  const marks = computed<ReadonlyMap<string, BuildMark>>(previous => buildMarks(jobs.value, previous))
  const expensive = computed(() => expensiveIds(manifest.value?.blicks ?? []))
  const stopped = computed(() => shown.value?.stopped ?? null)
  const later = computed(() => Math.max(0, (now.value - shownAt.value) / 1000))
  const lost = computed(() => error.value !== null)
  const titles = computed(() => new Map((manifest.value?.blicks ?? []).map(b => [b.id, b.definition?.title ?? b.name])))
  const title = (id: string): string => titles.value.get(id) ?? id

  async function request(id: string, rebuild = false): Promise<{ answer: BuildAnswer, fresh: boolean }> {
    const answer = await postBuild(id, rebuild)
    return { answer, fresh: await refresh() }
  }

  return { session, jobs, marks, expensive, stopped, later, stale, lost, title, request }
}

let state: ReturnType<typeof derive> | undefined

/**
 * The jobs of a session of `blicket dev`, which builds its Blicks while the viewer is open, as
 * the answer of `dev/info` that `useRefresh` shows says them, computed once for every page: the
 * session's id, `session`, another once blicket dev was started again or loaded another run; the
 * Blick building and the Blicks a page asked for that wait, `jobs`, and where each Blick stands
 * in them, `marks`, which stays the same object while a build only goes on; the ids of the
 * expensive Blicks, `expensive`, from the manifest; why the worker stopped, if it did,
 * `stopped`; how many seconds passed since that answer, `later`, which ticks every second while
 * something builds or is queued; whether `dev/info` does not answer any more, `lost`, so that
 * what it said last may be over; and a Blick's title by its id, `title`. `request` asks for a
 * Blick, once more with `rebuild`: blicket dev's `answer`, and whether an answer of `dev/info`
 * asked for after it is shown, `fresh`.
 */
export function useJobs() {
  // Detached, so that it outlives the component that first asked.
  state ??= effectScope(true).run(derive)!
  return state
}
