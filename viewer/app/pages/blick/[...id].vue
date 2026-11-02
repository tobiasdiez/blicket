<script setup lang="ts">
import { TAB, queryFromState, stateFromQuery, yAxisOf, type ControlState } from '~/lib/controls'
import { downloadCsv } from '~/lib/csv'
import { sourceText } from '~/lib/manifest'
import { drawsBaseline, nothingToCompare } from '~/plots'
import { CATEGORICAL, GHOST } from '~/plots/theme'

// The charts of the change against the baseline, under the chart while it is compared.
const CHANGE_KINDS = ['change', 'relative'] as const

const route = useRoute()
const router = useRouter()
const { manifest } = useManifest()
const { comparison, blicks, loading } = useComparison()
const theme = useTheme()

const id = useBlickId()
const entry = computed(() => manifest.value?.blicks.find(b => b.id === id.value) ?? null)
const group = computed(() => manifest.value?.groups.find(g => g.name === entry.value?.group) ?? null)
const definition = computed(() => entry.value?.definition ?? null)
const schema = computed(() => entry.value?.columns ?? null)
const controls = computed(() => entry.value?.controls ?? [])
const defaultY = computed(() => yAxisOf(definition.value))
const parsed = computed(() => (schema.value ? stateFromQuery(controls.value, schema.value, route.query, defaultY.value) : null))
const state = computed(() => parsed.value?.state ?? null)
const warnings = computed(() => entry.value?.problems.filter(p => p.severity === 'warning') ?? [])

watch(() => parsed.value?.unknown.join(', '), (unknown) => {
  if (unknown) console.warn(`blicket: the URL names ${unknown}, which this Blick has no control for; ignored`)
}, { immediate: true })

// The Blick in the comparison shown, and the baseline drawn behind its chart while the switch is on.
const change = computed(() => (entry.value ? blicks.value.get(entry.value.name) ?? null : null))
// A skipped Blick that no flag marks was not compared, so a strip would wrongly say unchanged.
const strip = computed(() => (change.value && !(change.value.skipped && !change.value.change.flags.length) ? change.value : null))
const compare = ref(true)
// `fileName` names exported images and the CSV file; `chartProps` is what the chart and the
// change charts are drawn from.
const { error, baselineFile, baselineError, shown, baseline, baselineWaiting, chartProps, undrawn, leftOut, fileName } = useBlickChart(entry, state, change, { compare })

const tab = useTab()

// The switch shows on the chart of a Blick with a baseline table; the chart waits for the
// comparisons and the baseline's rows, so it is drawn once.
const comparing = computed(() => baselineFile.value !== null && tab.value === 'chart')
const waiting = computed(() => tab.value === 'chart' && (loading.value || baselineWaiting.value))
// Whether the chart draws the baseline behind; the Sankey diagram has its change charts alone.
const baselineDrawn = computed(() => drawsBaseline(definition.value?.plot.type ?? ''))
// The switch's key: the first series' colour, faded as the baseline is.
const key = computed(() => ({ backgroundColor: CATEGORICAL[theme.value][0], opacity: GHOST[theme.value] }))
// Exported images say when they carry the baseline, whose key is outside the chart.
const chartName = computed(() => (baseline.value?.length && baselineDrawn.value ? `${fileName.value}_vs_baseline` : fileName.value))
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

function saveCsv() {
  if (shown.value && schema.value && definition.value) downloadCsv(shown.value, schema.value, definition.value.unit, definition.value.plot.mapping, fileName.value)
}

// The overview is the one page above a Blick; the group is a label, not a page. On a narrow
// page the title, which the heading repeats, makes room for the group.
const breadcrumb = computed(() => [
  { label: 'Overview', to: '/' },
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
    <UButton to="/" icon="i-lucide-arrow-left" variant="outline" color="neutral" label="Overview" />
  </div>
  <div v-else class="space-y-5">
    <div class="space-y-1">
      <UBreadcrumb :items="breadcrumb" />
      <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <h1 class="min-w-0 text-xl font-semibold text-highlighted">
          {{ definition?.title ?? entry.name }}
        </h1>
        <PinButton :id="id" :label="definition?.title ?? entry.name" class="shrink-0" />
      </div>
      <p v-if="definition?.description" class="max-w-3xl text-sm text-muted">
        {{ definition.description }}
      </p>
      <p class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span class="font-mono">{{ entry.name }}</span>
        <span v-if="definition">{{ definition.plot.type }}</span>
        <span v-if="definition?.unit">unit: {{ definition.unit }}</span>
        <span v-if="entry.rows !== null">{{ entry.rows.toLocaleString('en') }} rows</span>
        <a v-if="entry.data" :href="`./${entry.data}`" download class="underline hover:text-default">Parquet file</a>
        <button v-if="shown?.length" type="button" class="underline hover:text-default" @click="saveCsv">
          CSV of this selection
        </button>
        <span v-if="source">defined at <span class="font-mono">{{ source }}</span></span>
      </p>
    </div>

    <ChangeStrip
      v-if="strip"
      :blick="strip"
      :baseline="comparison!.baseline"
      :state="state"
      :schema="schema"
      :mapping="definition?.plot.mapping ?? {}"
      @update="showWhere"
    />
    <ProblemList v-if="entry.status === 'error'" :problems="entry.problems" />
    <UAlert v-else-if="entry.status === 'skipped'" color="neutral" variant="subtle" icon="i-lucide-circle-slash" title="Skipped for this run" :description="entry.skipped ?? undefined" :ui="{ description: 'whitespace-pre-wrap wrap-anywhere' }" />
    <template v-else-if="schema && state && definition">
      <ProblemList v-if="warnings.length" :problems="warnings" />
      <UAlert v-for="notice in parsed?.notices" :key="notice" color="neutral" variant="subtle" icon="i-lucide-info" :title="notice" />
      <ControlBar v-if="controls.length || comparing" ref="controlBar" :controls="controls" :schema="schema" :state="state" :axes="tab === 'chart'" @update="update">
        <template v-if="comparing">
          <USwitch v-model="compare" size="sm">
            <template #label>
              <span class="inline-flex items-center gap-2">
                Compare with baseline
                <span v-if="baselineDrawn" aria-hidden="true" class="h-1.5 w-6 rounded-full" :style="key" />
              </span>
            </template>
          </USwitch>
          <span v-if="baseline && !baseline.length" class="text-sm text-muted">no baseline rows for this selection</span>
          <span v-else-if="incomparable" class="text-sm text-muted">nothing to compare in this selection</span>
        </template>
      </ControlBar>
      <ChartTabs v-model="tab" />
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
      <p v-else-if="tab === 'chart' && undrawn" class="text-sm text-muted">
        No row of this selection can be drawn; the data tab lists the rows.
      </p>
      <div v-else-if="tab === 'chart' && chartProps" class="space-y-4">
        <BlickChart v-bind="chartProps" :name="chartName" :note="leftOut" />
        <template v-if="baseline?.length && !incomparable">
          <BlickChart v-for="kind in CHANGE_KINDS" :key="kind" v-bind="chartProps" :name="fileName" :kind="kind" />
        </template>
      </div>
      <DataTable v-else :rows="shown" :schema="schema" :unit="definition.unit" :mapping="definition.plot.mapping" />
    </template>
  </div>
</template>
