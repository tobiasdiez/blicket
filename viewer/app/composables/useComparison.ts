import { offered, type BlickComparison, type Comparison } from '~/lib/comparison'
import { keptChoice, share } from '~/lib/reload'
import { revisionsOf } from '~/lib/dev'
import { reloadable, type Fetched, type Revised } from '~/lib/resource'

const chosen = ref<string | null>(null)
// Until the first read ended, and the baseline it gave was chosen.
const loading = ref(true)
let requested = false
let read = false // whether the comparisons were read once

const message = (cause: unknown) => (cause instanceof Error ? cause.message : String(cause))

/** One comparison and its revision, or `null` with a warning when it cannot be read. */
async function readComparison(id: string): Promise<Revised<Comparison> | null> {
  try {
    const response = await fetch(`./compare/${id}/comparison.json`, { cache: 'no-cache' })
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
    return { data: (await response.json()) as Comparison, revisions: revisionsOf(response) }
  }
  catch (cause) {
    console.warn(`blicket: the comparison with build ${id} cannot be read: ${message(cause)}`)
    return null
  }
}

/**
 * The comparisons offered, as `compare/index.json` lists them now, none without it. Read first,
 * those that can be read are shown; read again, a comparison that cannot be read fails the read,
 * so that the baseline chosen is not lost to a passing failure.
 */
async function readAll(): Promise<Revised<Comparison[]>> {
  const response = await fetch('./compare/index.json', { cache: 'no-cache' })
  if (response.status === 404) return { data: [], revisions: [] }
  if (!response.ok) throw new Error(`compare/index.json: ${response.status} ${response.statusText}`)
  const ids = (await response.json()) as string[]
  const all = await Promise.all(ids.map(readComparison))
  if (read && all.includes(null)) throw new Error('a comparison it lists cannot be read')
  const found = all.filter(each => each !== null)
  const revisions = [...revisionsOf(response), ...found.flatMap(each => each.revisions)]
  return { data: offered(found.map(each => each.data)), revisions }
}

// Read again, what did not change keeps its objects, and the baseline chosen stays chosen.
const resource = reloadable(readAll, share)
const baselines = computed(() => resource.data.value ?? [])
const error = computed(() => (resource.error.value === null ? null : `the comparisons cannot be read: ${resource.error.value}`))

/**
 * Read the comparisons again without showing them: their revisions and what shows them, the
 * baseline chosen kept.
 */
async function readAgain(): Promise<Fetched | null> {
  const fetched = await resource.fetch()
  if (!resource.loading.value && !fetched) loading.value = false
  return fetched && {
    revisions: fetched.revisions,
    show: () => {
      fetched.show()
      chosen.value = read ? keptChoice(chosen.value, baselines.value) : baselines.value.at(-1)?.baseline.id ?? null
      read = true
      loading.value = false
    },
  }
}

async function reload(): Promise<boolean> {
  const fetched = await readAgain()
  fetched?.show()
  return fetched !== null
}

/**
 * The comparisons that `blicket check` wrote into the build directory, fetched once; `baselines`
 * are those offered, with a build of another run, in the order of `compare/index.json`. `chosen`
 * is the baseline shown, at first the one of them checked last, `null` for none; `comparison` is
 * its comparison and `blicks` every Blick of it by name. The build's own Blicks find themselves
 * there, a skipped one that the comparison removes too; a Blick of the baseline only has a name
 * that no Blick of the build has. A build that was never compared has none, and no error.
 * `reload` reads them again, as a session of blicket dev asks to whenever a Blick is built, without
 * `loading`, and says whether what is shown is what it read; when it is not, `stale` says why.
 * `fetch` reads them without showing them, and gives their revisions and what shows them.
 */
export function useComparison() {
  if (!requested) {
    requested = true
    void reload()
  }
  const comparison = computed(() => baselines.value.find(c => c.baseline.id === chosen.value) ?? null)
  const blicks = computed(() => new Map<string, BlickComparison>((comparison.value?.blicks ?? []).map(b => [b.name, b])))
  return { baselines, chosen, comparison, blicks, loading, error, stale: resource.stale, reload, fetch: readAgain }
}
