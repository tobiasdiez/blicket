import { rowsStay, tableKey } from '~/lib/reload'
import { fetchTable, type Row, type TableFile } from '~/lib/table'

/**
 * The rows of the table `file`, fetched once per content hash: a new object for the same path
 * and hash fetches nothing. The rows shown stay until those of another table are there, so that
 * a table read again does not blank the chart, as long as `owner`, such as the Blick's name,
 * stays (`rowsStay`); otherwise, or without a table, they go at once. `loaded` is the key,
 * `path?hash`, of the table the rows are of.
 */
export function useTable(file: MaybeRefOrGetter<TableFile | null>, owner: () => unknown) {
  const rows = shallowRef<Row[] | null>(null)
  const error = ref<string | null>(null)
  const loaded = ref<string | null>(null)
  watch([() => tableKey(toValue(file)), owner], async ([key, who], previous) => {
    const current = toValue(file)
    error.value = null
    if (!current || !rowsStay(previous?.[1], who, key)) {
      rows.value = null
      loaded.value = null
    }
    if (!current || key === null) return
    const stillCurrent = () => tableKey(toValue(file)) === key && Object.is(owner(), who)
    try {
      const fetched = await fetchTable(current)
      if (stillCurrent()) {
        rows.value = fetched
        loaded.value = key
      }
    }
    catch (cause) {
      if (stillCurrent()) error.value = cause instanceof Error ? cause.message : String(cause)
    }
  }, { immediate: true })
  return { rows, error, loaded }
}
