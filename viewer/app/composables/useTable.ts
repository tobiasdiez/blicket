import { fetchTable, type Row, type TableFile } from '~/lib/table'

/** The rows of the table `file`, fetched once per content hash. */
export function useTable(file: MaybeRefOrGetter<TableFile | null>) {
  const rows = shallowRef<Row[] | null>(null)
  const error = ref<string | null>(null)
  watch(() => toValue(file), async (current) => {
    rows.value = null
    error.value = null
    if (!current) return
    const stillCurrent = () => toValue(file)?.path === current.path && toValue(file)?.hash === current.hash
    try {
      const loaded = await fetchTable(current)
      if (stillCurrent()) rows.value = loaded
    }
    catch (cause) {
      if (stillCurrent()) error.value = cause instanceof Error ? cause.message : String(cause)
    }
  }, { immediate: true })
  return { rows, error }
}
