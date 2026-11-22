import { isRunList } from '~/lib/dev'
import { devResource } from './devResource'

const resource = devResource('./dev/runs', isRunList, 'dev/runs', () => useManifest().dev.value)

/**
 * The run folders to pick, from `dev/runs`: fetched once the manifest says that `blicket dev`
 * serves the viewer, which tells whether the project sets `runs`; `reload` looks for them again.
 */
export function useRuns() {
  const { data: runs, ...state } = resource()
  return { runs, ...state }
}
