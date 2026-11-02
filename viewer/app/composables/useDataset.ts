import { isOptions } from '~/lib/dev'
import { devResource } from './devResource'

const resource = devResource('./dev/dataset', isOptions, 'dev/dataset', () => useDev().info.value?.dataset)

/**
 * What the Blick builder offers, from `dev/dataset`: fetched once `dev/info` says there is a
 * dataset, so a project without one costs no request; `reload` fetches it again.
 */
export function useDataset() {
  const { data: options, ...state } = resource()
  return { options, ...state }
}
