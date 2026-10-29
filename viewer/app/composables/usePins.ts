import { PINS, readPins, resolvePins, togglePin, writePins } from '~/lib/pins'
import { browserStorage } from '~/lib/storage'

const ids = ref<string[]>([])
let started = false

/**
 * The Blicks the user pinned to the overview, kept in the browser, per origin: `ids` in the order
 * pinned, read at first use and on another tab's `storage` event, so that the tabs agree; `pinned`
 * the Blicks of the build they name, through aliases too. `isPinned` and `toggle` take a Blick's
 * id; where the browser blocks storage, the pins last as long as the page.
 */
export function usePins() {
  if (!started) {
    started = true
    ids.value = readPins(browserStorage)
    window.addEventListener('storage', (event) => {
      if (event.key === PINS || event.key === null) ids.value = readPins(browserStorage)
    })
  }
  const { manifest } = useManifest()
  const pinned = computed(() => resolvePins(ids.value, manifest.value?.blicks ?? []))

  function isPinned(id: string): boolean {
    return pinned.value.some(entry => entry.id === id)
  }

  /** Pin the Blick, or unpin it, whichever of its ids the pin names. */
  function toggle(id: string) {
    ids.value = togglePin(ids.value, id, manifest.value?.blicks ?? [])
    writePins(browserStorage, ids.value)
  }

  return { pinned, isPinned, toggle }
}
