import { isDevAnswer, isNoRun } from '~/lib/dev'
import { SPEC, type Manifest } from '~/lib/manifest'

const manifest = shallowRef<Manifest | null>(null)
const error = ref<string | null>(null)
// Whether `blicket dev` serves the build: it marks the manifest with a header.
const dev = ref(false)
// Whether `blicket dev` serves no run yet: it answers the manifest with 404 and the header.
const noRun = ref(false)
let requested = false

async function load(): Promise<void> {
  try {
    const response = await fetch('./manifest.json', { cache: 'no-cache' })
    dev.value = isDevAnswer(response)
    if (isNoRun(response)) {
      noRun.value = true
      return
    }
    if (!response.ok) throw new Error(`manifest.json: ${response.status} ${response.statusText}`)
    const data = (await response.json()) as Manifest
    if (data.spec !== SPEC) {
      throw new Error(`another version of blicket made this build (manifest spec ${data.spec}; this viewer reads ${SPEC}); rebuild it with blicket build`)
    }
    manifest.value = data
  }
  catch (cause) {
    error.value = `cannot read the build: ${cause instanceof Error ? cause.message : String(cause)}`
  }
}

/**
 * The manifest of the build directory the viewer sits in, fetched once, and whether `blicket dev`
 * serves it, which the header `Blicket-Dev` on the manifest says, so a static host needs no
 * request more; `noRun` when `blicket dev` serves no run yet, so that there is no manifest.
 */
export function useManifest() {
  if (!requested) {
    requested = true
    void load()
  }
  return { manifest, error, dev, noRun }
}
