<script setup lang="ts">
import { baselineTable } from '~/lib/comparison'
import { queryFromState, stateFromQuery, type ControlState, type YAxis } from '~/lib/controls'
import { toCsv } from '~/lib/csv'
import { sourceText } from '~/lib/manifest'
import { select } from '~/lib/select'
import { nothingToCompare } from '~/plots'
import { CATEGORICAL, GHOST } from '~/plots/theme'

// The query key of the tab; like every key with an underscore, it is not a dimension.
const TAB = '_tab'
// The charts of the change against the baseline, under the chart while it is compared.
const CHANGE_KINDS = ['change', 'relative'] as const

const route = useRoute()
const router = useRouter()
const { manifest } = useManifest()
const { comparison, blicks, loading } = useComparison()
const theme = useTheme()

const id = computed(() => {
  const segments = route.params.id
  return Array.isArray(segments) ? segments.join('/') : String(segments ?? '')
})
const entry = computed(() => manifest.value?.blicks.find(b => b.id === id.value) ?? null)
const group = computed(() => manifest.value?.groups.find(g => g.name === entry.value?.group) ?? null)
const definition = computed(() => entry.value?.definition ?? null)
const schema = computed(() => entry.value?.columns ?? null)
const controls = computed(() => entry.value?.controls ?? [])
const defaultY = computed<YAxis>(() => (definition.value?.independent_y ? 'independent' : 'shared'))
const parsed = computed(() => (schema.value ? stateFromQuery(controls.value, schema.value, route.query, defaultY.value) : null))
// The name of exported images and the CSV file.
const fileName = computed(() => id.value.replaceAll('/', '__'))
const state = computed(() => parsed.value?.state ?? null)
const warnings = computed(() => entry.value?.problems.filter(p => p.severity === 'warning') ?? [])

watch(() => parsed.value?.unknown.join(', '), (unknown) => {
  if (unknown) console.warn(`blicket: the URL names ${unknown}, which this Blick has no control for; ignored`)
}, { immediate: true })

const { rows, error } = useTable(() => (entry.value?.status === 'ok' && entry.value.data ? { path: entry.value.data, hash: entry.value.hash } : null))
const shown = computed(() => (rows.value && schema.value && state.value ? select(rows.value, schema.value, state.value.filters) : null))

// The Blick in the comparison shown, and the baseline drawn behind its chart while the switch is on.
const change = computed(() => (entry.value ? blicks.value.get(entry.value.name) ?? null : null))
const baselineFile = computed(() => (change.value ? baselineTable(change.value) : null))
const compare = ref(true)
const { rows: baselineRows, error: baselineError } = useTable(() => (compare.value ? baselineFile.value : null))
const baseline = computed(() => (baselineRows.value && schema.value && state.value ? select(baselineRows.value, schema.value, state.value.filters) : null))

const tabs = [
  { label: 'Chart', value: 'chart', icon: 'i-lucide-chart-line' },
  { label: 'Data', value: 'data', icon: 'i-lucide-table' },
]
// The tab is in the URL too, so a link can open the data.
const tab = computed({
  get: () => (route.query[TAB] === 'data' ? 'data' : 'chart'),
  set: (value: string | number) => void router.replace({ query: { ...route.query, [TAB]: value === 'data' ? 'data' : undefined } }),
})

// The switch shows on the chart of a Blick with a baseline table; the chart waits for the
// comparisons and the baseline's rows, so it is drawn once.
const comparing = computed(() => baselineFile.value !== null && tab.value === 'chart')
const waiting = computed(() => tab.value === 'chart' && (loading.value || (comparing.value && compare.value && !baselineRows.value && !baselineError.value)))
// The switch's key: the first series' colour, faded as the baseline is.
const key = computed(() => ({ backgroundColor: CATEGORICAL[theme.value][0], opacity: GHOST[theme.value] }))
// Exported images say when they carry the baseline, whose key is outside the chart.
const chartName = computed(() => (baseline.value?.length ? `${fileName.value}_vs_baseline` : fileName.value))
// What the chart and the change charts are drawn from.
const chartProps = computed(() => {
  if (!definition.value || !schema.value || !state.value || !shown.value) return null
  const { type, mapping } = definition.value.plot
  return { type, mapping, schema: schema.value, unit: definition.value.unit, rows: shown.value, splits: state.value.splits, y: state.value.y, baseline: baseline.value }
})
// Whether the change charts would have nothing to draw: a flat zero, which reads as no change. It
// depends on the rows, not on the splits or the y axes.
const incomparable = computed(() => {
  if (!definition.value || !schema.value || !shown.value) return false
  const { type, mapping } = definition.value.plot
  return nothingToCompare(type, { table: shown.value, baseline: baseline.value, schema: schema.value, mapping })
})

useHead({ title: computed(() => `${definition.value?.title ?? id.value} · blicket`) })

/** Put the control state into the URL, without a history entry. */
async function update(next: ControlState) {
  if (!schema.value) return
  const query = queryFromState(schema.value, next, defaultY.value)
  await router.replace({ query: tab.value === 'data' ? { ...query, [TAB]: 'data' } : query })
}

const controlBar = useTemplateRef<{ $el: HTMLElement }>('controlBar')

/** Show the largest change, and keep the keyboard focus on the page: on the first control. */
async function showWhere(next: ControlState) {
  await update(next)
  await nextTick()
  controlBar.value?.$el.querySelector<HTMLElement>('button, input')?.focus()
}

function downloadCsv() {
  if (!shown.value || !schema.value) return
  const url = URL.createObjectURL(new Blob([toCsv(shown.value, schema.value, definition.value?.unit ?? null)], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${fileName.value}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

// The overview is the one page above a Blick; the group is a label, not a page. On a narrow
// page the title, which the heading repeats, makes room for the group.
const breadcrumb = computed(() => [
  { label: 'All Blicks', to: '/' },
  { label: group.value?.title ?? entry.value?.group ?? '', ui: { separator: 'max-sm:hidden' } },
  { label: definition.value?.title ?? id.value, ui: { item: 'max-sm:hidden' } },
])
const source = computed(() => (entry.value?.source ? sourceText(entry.value.source) : null))
</script>

<template>
  <div v-if="!entry" class="space-y-3">
    <h1 class="text-lg font-semibold text-highlighted">
      No such Blick in this build
    </h1>
    <p class="text-sm text-muted">
      This build has no Blick <code>{{ id }}</code>.
    </p>
    <UButton to="/" icon="i-lucide-arrow-left" variant="outline" color="neutral" label="All Blicks" />
  </div>
  <div v-else class="space-y-5">
    <div class="space-y-1">
      <UBreadcrumb :items="breadcrumb" />
      <h1 class="text-xl font-semibold text-highlighted">
        {{ definition?.title ?? entry.name }}
      </h1>
      <p v-if="definition?.description" class="max-w-3xl text-sm text-muted">
        {{ definition.description }}
      </p>
      <p class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span class="font-mono">{{ entry.name }}</span>
        <span v-if="definition">{{ definition.plot.type }}</span>
        <span v-if="definition?.unit">unit: {{ definition.unit }}</span>
        <span v-if="entry.rows !== null">{{ entry.rows.toLocaleString('en') }} rows</span>
        <a v-if="entry.data" :href="`./${entry.data}`" download class="underline hover:text-default">Parquet file</a>
        <button v-if="shown?.length" type="button" class="underline hover:text-default" @click="downloadCsv">
          CSV of this selection
        </button>
        <span v-if="source">defined at <span class="font-mono">{{ source }}</span></span>
      </p>
    </div>

    <ChangeStrip
      v-if="change"
      :blick="change"
      :baseline="comparison!.baseline"
      :state="state"
      :schema="schema"
      :mapping="definition?.plot.mapping ?? {}"
      @update="showWhere"
    />
    <ProblemList v-if="entry.status === 'error'" :problems="entry.problems" />
    <template v-else-if="schema && state && definition">
      <ProblemList v-if="warnings.length" :problems="warnings" />
      <UAlert v-for="notice in parsed?.notices" :key="notice" color="neutral" variant="subtle" icon="i-lucide-info" :title="notice" />
      <ControlBar v-if="controls.length || comparing" ref="controlBar" :controls="controls" :schema="schema" :state="state" :axes="tab === 'chart'" @update="update">
        <template v-if="comparing">
          <USwitch v-model="compare" size="sm">
            <template #label>
              <span class="inline-flex items-center gap-2">
                Compare with baseline
                <span aria-hidden="true" class="h-1.5 w-6 rounded-full" :style="key" />
              </span>
            </template>
          </USwitch>
          <span v-if="baseline && !baseline.length" class="text-sm text-muted">no baseline rows for this selection</span>
          <span v-else-if="incomparable" class="text-sm text-muted">nothing to compare in this selection</span>
        </template>
      </ControlBar>
      <UTabs v-model="tab" :items="tabs" variant="link" :content="false" class="w-full" />
      <UAlert v-if="baselineError && comparing" color="warning" variant="subtle" title="The baseline's table cannot be read" :description="baselineError" :ui="{ description: 'wrap-anywhere' }" />
      <UAlert v-if="error" color="error" variant="subtle" title="The table cannot be read" :description="error" />
      <p v-else-if="!shown || waiting" class="text-sm text-muted">
        Loading the table…
      </p>
      <p v-else-if="entry.rows === 0" class="text-sm text-muted">
        This Blick's table has no rows.
      </p>
      <p v-else-if="!shown.length" class="text-sm text-muted">
        No rows for this selection.
      </p>
      <div v-else-if="tab === 'chart' && chartProps" class="space-y-4">
        <BlickChart v-bind="chartProps" :name="chartName" />
        <template v-if="baseline?.length && !incomparable">
          <BlickChart v-for="kind in CHANGE_KINDS" :key="kind" v-bind="chartProps" :name="fileName" :kind="kind" />
        </template>
      </div>
      <DataTable v-else :rows="shown" :schema="schema" :unit="definition.unit" />
    </template>
  </div>
</template>
