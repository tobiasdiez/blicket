import { storedOpen, storeOpen } from '~/lib/sidebar'
import { browserStorage } from '~/lib/storage'

// A window wide enough for the sidebar next to the page, Tailwind's `xl`; on a narrower one it is
// a drawer.
const WIDE = '(min-width: 80rem)'

const open = ref(storedOpen(browserStorage))

/**
 * Whether the sidebar is open, which outlives the pages. `open` is bound to the sidebar, which
 * sets it itself on a narrow window, where it is a drawer: false, and true while the drawer is
 * open. `toggle` flips it, and on a wide window keeps the choice in the browser, so a reload shows
 * the same; `closeDrawer` closes the drawer of a narrow window and leaves a wide one's sidebar.
 */
export function useSidebar() {
  function toggle() {
    open.value = !open.value
    if (matchMedia(WIDE).matches) storeOpen(browserStorage, open.value)
  }
  function closeDrawer() {
    if (!matchMedia(WIDE).matches) open.value = false
  }
  return { open, toggle, closeDrawer }
}
