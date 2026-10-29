import { baselineTable, type BlickComparison } from '~/lib/comparison'
import type { ControlState } from '~/lib/controls'
import type { BlickDefinition, BlickEntry, TableSchema } from '~/lib/manifest'
import { select } from '~/lib/select'
import type { Row } from '~/lib/table'

/**
 * What `BlickChart` draws of a Blick: its plot, the rows and the baseline's rows after the state's
 * filters, and the state's panels and y axes; `null` while any of them is missing.
 */
export function chartPropsOf(definition: BlickDefinition | null, schema: TableSchema | null, rows: Row[] | null, state: ControlState | null, baseline: Row[] | null) {
  if (!definition || !schema || !rows || !state) return null
  const { type, mapping } = definition.plot
  return { type, mapping, schema, unit: definition.unit, rows, splits: state.splits, y: state.y, baseline }
}

/**
 * A Blick's chart at a control state: its rows, and its baseline's when the comparison `change`
 * has a table to draw behind it, fetched by content hash, and both after the state's filters.
 * `load` says whether to fetch at all, `compare` whether to fetch the baseline. `error` and
 * `baselineError` say why a table cannot be read; `shown` and `baseline` are the rows of the
 * state; `baselineFile` the baseline's table, with or without `compare`, and `baselineWaiting`
 * whether the chart still waits for its rows; `chartProps` what `BlickChart` draws, and
 * `fileName` the name of exported files.
 */
export function useBlickChart(
  entry: MaybeRefOrGetter<BlickEntry | null>,
  state: MaybeRefOrGetter<ControlState | null>,
  change: MaybeRefOrGetter<BlickComparison | null>,
  options: { load?: MaybeRefOrGetter<boolean>, compare?: MaybeRefOrGetter<boolean> } = {},
) {
  const loading = () => toValue(options.load) ?? true
  const comparing = () => toValue(options.compare) ?? true
  const schema = computed(() => toValue(entry)?.columns ?? null)

  const { rows, error } = useTable(() => {
    const current = toValue(entry)
    return loading() && current?.status === 'ok' && current.data ? { path: current.data, hash: current.hash } : null
  })
  const baselineFile = computed(() => {
    const compared = toValue(change)
    return compared ? baselineTable(compared) : null
  })
  const { rows: baselineRows, error: baselineError } = useTable(() => (loading() && comparing() ? baselineFile.value : null))

  const filters = computed(() => toValue(state)?.filters ?? null)
  const shown = computed(() => (rows.value && schema.value && filters.value ? select(rows.value, schema.value, filters.value) : null))
  const baseline = computed(() => (baselineRows.value && schema.value && filters.value ? select(baselineRows.value, schema.value, filters.value) : null))
  const baselineWaiting = computed(() => comparing() && baselineFile.value !== null && !baselineRows.value && !baselineError.value)

  const chartProps = computed(() => chartPropsOf(toValue(entry)?.definition ?? null, schema.value, shown.value, toValue(state), baseline.value))
  const fileName = computed(() => {
    const current = toValue(entry)
    return (current?.id ?? current?.name ?? '').replaceAll('/', '__')
  })

  return { error, baselineFile, baselineError, shown, baseline, baselineWaiting, chartProps, fileName }
}
