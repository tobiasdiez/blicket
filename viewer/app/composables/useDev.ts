import { isInfo } from '~/lib/dev'
import { devResource } from './devResource'

const resource = devResource('./dev/info', isInfo, 'dev/info', () => useManifest().dev.value)

/**
 * Whether the viewer is in dev mode, served by `blicket dev`, and what `dev/info` says, fetched
 * as soon as the manifest says dev mode; `reload` fetches it again.
 */
export function useDev() {
  const { dev } = useManifest()
  const { data: info, ...state } = resource()
  return { dev, info, ...state }
}
