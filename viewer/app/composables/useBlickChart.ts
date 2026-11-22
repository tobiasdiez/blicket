import { baselineTable, type BlickComparison } from '~/lib/comparison'
import type { ControlState } from '~/lib/controls'
import type { BlickDefinition, BlickEntry, TableSchema } from '~/lib/manifest'
import { rowOwners, settled, tableKey, tableOf } from '~/lib/reload'
import { select } from '~/lib/select'
import type { Row } from '~/lib/table'
import { leftOutNote, nothingToDraw } from '~/plots'

/**
 * What `BlickChart` draws of a Blick: its plot with its scales, the rows and the baseline's rows
 * after the state's filters, and the state's panels and y axes; `null` while any of them is
 * missing.
 */
export function chartPropsOf(definition: BlickDefinition | null, schema: TableSchema | null, rows: Row[] | null, state: ControlState | null, baseline: Row[] | null) {
  if (!definition || !schema || !rows || !state) return null
  const { type, mapping, scales } = definition.plot
  return { type, mapping, scales, schema, unit: definition.unit, rows, splits: state.splits, y: state.y, baseline }
}

/**
 * A Blick's chart at a control state: its rows, and its baseline's when the comparison `change`
 * has a table to draw behind it, fetched by content hash, and both after the state's filters.
 * `load` says whether to fetch at all, `compare` whether to fetch the baseline. `entry` is the
 * entry drawn: the one given, but while the Blick's new table is fetched, after a rebuild, the
 * one before, whose rows are still there, so that the state, which the caller makes of its
 * controls, matches the rows. `error` and `baselineError` say why a table cannot be read;
 * `shown` and `baseline` are the rows of the state; `baselineFile` the baseline's table, with or
 * without `compare`, and `baselineWaiting` whether the chart still waits for its rows;
 * `chartProps` what `BlickChart` draws, `undrawn` whether it and its change charts would draw
 * nothing, such as of a scatter's rows without an x, and `leftOut` the line under the chart about
 * the rows it leaves out; `fileName` the name of exported files. A manifest read again shares
 * what did not change, so that its rows are not selected anew. The baseline's rows go as soon as
 * the baseline's table is another, so that another baseline never draws the old one's rows.
 */
export function useBlickChart(
  entry: MaybeRefOrGetter<BlickEntry | null>,
  state: MaybeRefOrGetter<ControlState | null>,
  change: MaybeRefOrGetter<BlickComparison | null>,
  options: { load?: MaybeRefOrGetter<boolean>, compare?: MaybeRefOrGetter<boolean> } = {},
) {
  const loading = () => toValue(options.load) ?? true
  const comparing = () => toValue(options.compare) ?? true
  const file = () => (loading() ? tableOf(toValue(entry)) : null)
  const baselineFile = computed(() => {
    const compared = toValue(change)
    return compared ? baselineTable(compared) : null
  })
  const baselineShown = () => (loading() && comparing() ? baselineFile.value : null)
  const owners = () => rowOwners(toValue(entry), baselineShown())

  const { rows, error, loaded } = useTable(file, () => owners().own)
  const shownEntry = computed<BlickEntry | null>(previous => settled(previous, toValue(entry), tableKey(file()), loaded.value))
  const schema = computed(() => shownEntry.value?.columns ?? null)
  const definition = computed(() => shownEntry.value?.definition ?? null)
  const { rows: baselineRows, error: baselineError } = useTable(baselineShown, () => owners().baseline)

  const filters = computed(() => toValue(state)?.filters ?? null)
  const shown = computed(() => (rows.value && schema.value && filters.value ? select(rows.value, schema.value, filters.value) : null))
  const baseline = computed(() => (baselineRows.value && schema.value && filters.value ? select(baselineRows.value, schema.value, filters.value) : null))
  const baselineWaiting = computed(() => comparing() && baselineFile.value !== null && !baselineRows.value && !baselineError.value)

  const chartProps = computed(() => chartPropsOf(definition.value, schema.value, shown.value, toValue(state), baseline.value))
  // The chart's plot type and what tells which of its rows, and of the baseline's, it draws.
  const drawing = computed(() => {
    const chart = chartProps.value
    return chart && { type: chart.type, args: { table: chart.rows, baseline: chart.baseline, schema: chart.schema, mapping: chart.mapping, scales: chart.scales } }
  })
  const undrawn = computed(() => !!drawing.value && nothingToDraw(drawing.value.type, drawing.value.args))
  const leftOut = computed(() => (drawing.value ? leftOutNote(drawing.value.type, drawing.value.args) : ''))
  const fileName = computed(() => {
    const current = toValue(entry)
    return (current?.id ?? current?.name ?? '').replaceAll('/', '__')
  })

  return { shownEntry, error, baselineFile, baselineError, shown, baseline, baselineWaiting, chartProps, undrawn, leftOut, fileName }
}
