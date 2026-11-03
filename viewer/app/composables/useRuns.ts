import { isRunList } from '~/lib/dev'
import { devResource } from './devResource'

const resource = devResource('./dev/runs', isRunList, 'dev/runs', () => useManifest().noRun.value)

/**
 * The run folders to pick, from `dev/runs`: fetched once the manifest says that `blicket dev`
 * serves no run yet; `reload` looks for them again.
 */
export function useRuns() {
  const { data: runs, ...state } = resource()
  return { runs, ...state }
}
