import { isDevAnswer, isNoRun, revisionsOf } from '~/lib/dev'
import { SPEC, type Manifest } from '~/lib/manifest'
import { share } from '~/lib/reload'
import { reloadable, type Revised } from '~/lib/resource'

// Whether `blicket dev` serves the build: it marks the manifest with a header.
const dev = ref(false)
// Whether `blicket dev` serves no run yet: it answers the manifest with 404 and the header.
const noRun = ref(false)

/**
 * The manifest as `manifest.json` answers it now, and its revision; `null` when `blicket dev`
 * serves no run yet.
 */
async function read(): Promise<Revised<Manifest | null>> {
  const response = await fetch('./manifest.json', { cache: 'no-cache' })
  dev.value = isDevAnswer(response)
  noRun.value = isNoRun(response)
  if (noRun.value) return { data: null, revisions: [] }
  if (!response.ok) throw new Error(`manifest.json: ${response.status} ${response.statusText}`)
  const data = (await response.json()) as Manifest
  if (data.spec !== SPEC) {
    throw new Error(`another version of blicket made this build (manifest spec ${data.spec}; this viewer reads ${SPEC}); rebuild it with blicket build`)
  }
  return { data, revisions: revisionsOf(response) }
}

// Read again, what did not change keeps its objects.
const resource = reloadable(read, share)
const error = computed(() => (resource.error.value === null ? null : `cannot read the build: ${resource.error.value}`))
let requested = false

/**
 * The manifest of the build directory the viewer sits in, fetched once, and whether `blicket dev`
 * serves it, which the header `Blicket-Dev` on the manifest says, so a static host needs no
 * request more; `noRun` when `blicket dev` serves no run yet, so that there is no manifest.
 * `reload` reads it again, as a session asks to whenever a Blick is built, what did not
 * change kept as it was, and says whether the manifest shown is the one read; when it is not,
 * `stale` says why. `fetch` reads it without showing it, and gives its revision and what shows
 * it.
 */
export function useManifest() {
  if (!requested) {
    requested = true
    void resource.reload()
  }
  return { manifest: resource.data, error, stale: resource.stale, dev, noRun, reload: resource.reload, fetch: resource.fetch }
}
