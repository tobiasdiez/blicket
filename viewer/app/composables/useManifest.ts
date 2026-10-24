import { SPEC, type Manifest } from '~/lib/manifest'

const manifest = shallowRef<Manifest | null>(null)
const error = ref<string | null>(null)
let requested = false

async function load(): Promise<void> {
  try {
    const response = await fetch('./manifest.json', { cache: 'no-cache' })
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

/** The manifest of the build directory the viewer sits in, fetched once. */
export function useManifest() {
  if (!requested) {
    requested = true
    void load()
  }
  return { manifest, error }
}
