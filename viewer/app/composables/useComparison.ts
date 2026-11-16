import { offered, type BlickComparison, type CheckComparison, type Comparison } from '~/lib/comparison'

const baselines = shallowRef<Comparison[]>([])
const chosen = ref<string | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
let requested = false

const message = (cause: unknown) => (cause instanceof Error ? cause.message : String(cause))

/** One comparison, or `null` with a warning when it cannot be read: the others are still shown. */
async function readComparison(id: string): Promise<Comparison | null> {
  try {
    const response = await fetch(`./compare/${id}/comparison.json`, { cache: 'no-cache' })
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
    // A comparison written for a 0.2 build has neither the checks nor the Blicks' expectations.
    const comparison = (await response.json()) as Comparison
    return {
      ...comparison,
      blicks: comparison.blicks.map(blick => ({ ...blick, expectation: blick.expectation ?? null })),
      checks: comparison.checks ?? [],
    }
  }
  catch (cause) {
    console.warn(`blicket: the comparison with build ${id} cannot be read: ${message(cause)}`)
    return null
  }
}

async function load(): Promise<void> {
  try {
    const response = await fetch('./compare/index.json', { cache: 'no-cache' })
    if (response.status === 404) return
    if (!response.ok) throw new Error(`compare/index.json: ${response.status} ${response.statusText}`)
    const ids = (await response.json()) as string[]
    baselines.value = offered((await Promise.all(ids.map(readComparison))).filter(found => found !== null))
    chosen.value = baselines.value.at(-1)?.baseline.id ?? null
  }
  catch (cause) {
    error.value = `the comparisons cannot be read: ${message(cause)}`
  }
  finally {
    loading.value = false
  }
}

/**
 * The comparisons that `blicket check` wrote into the build directory, fetched once; `baselines`
 * are those offered, with a build of another run, in the order of `compare/index.json`. `chosen`
 * is the baseline shown, at first the one of them checked last, `null` for none; `comparison` is
 * its comparison, one written for a 0.2 build read with no checks, `blicks` every Blick of it by
 * name and `checks` every check by name. The build's own Blicks find themselves
 * there, a skipped one that the comparison removes too; a Blick of the baseline only has a name
 * that no Blick of the build has. A build that was never compared has none, and no error.
 */
export function useComparison() {
  if (!requested) {
    requested = true
    void load()
  }
  const comparison = computed(() => baselines.value.find(c => c.baseline.id === chosen.value) ?? null)
  const blicks = computed(() => new Map<string, BlickComparison>((comparison.value?.blicks ?? []).map(b => [b.name, b])))
  const checks = computed(() => new Map<string, CheckComparison>((comparison.value?.checks ?? []).map(c => [c.name, c])))
  return { baselines, chosen, comparison, blicks, checks, loading, error }
}
