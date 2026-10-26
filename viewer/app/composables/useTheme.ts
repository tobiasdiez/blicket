import type { Theme } from '~/plots/types'

/** The colour mode the charts are drawn in. */
export function useTheme() {
  const colorMode = useColorMode()
  return computed<Theme>(() => (colorMode.value === 'dark' ? 'dark' : 'light'))
}
