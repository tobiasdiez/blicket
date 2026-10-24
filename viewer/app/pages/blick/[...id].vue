<script setup lang="ts">
import { queryFromState, stateFromQuery, type ControlState, type YAxis } from '~/lib/controls'
import { toCsv } from '~/lib/csv'
import { sourceText } from '~/lib/manifest'
import { select } from '~/lib/select'

// The query key of the tab; like every key with an underscore, it is not a dimension.
const TAB = '_tab'

const route = useRoute()
const router = useRouter()
const { manifest } = useManifest()

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

const tabs = [
  { label: 'Chart', value: 'chart', icon: 'i-lucide-chart-line' },
  { label: 'Data', value: 'data', icon: 'i-lucide-table' },
]
// The tab is in the URL too, so a link can open the data.
const tab = computed({
  get: () => (route.query[TAB] === 'data' ? 'data' : 'chart'),
  set: (value: string | number) => void router.replace({ query: { ...route.query, [TAB]: value === 'data' ? 'data' : undefined } }),
})

useHead({ title: computed(() => `${definition.value?.title ?? id.value} · blicket`) })

/** Put the control state into the URL, without a history entry. */
function update(next: ControlState) {
  if (!schema.value) return
  const query = queryFromState(schema.value, next, defaultY.value)
  void router.replace({ query: tab.value === 'data' ? { ...query, [TAB]: 'data' } : query })
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

    <ProblemList v-if="entry.status === 'error'" :problems="entry.problems" />
    <template v-else-if="schema && state && definition">
      <ProblemList v-if="warnings.length" :problems="warnings" />
      <UAlert v-for="notice in parsed?.notices" :key="notice" color="neutral" variant="subtle" icon="i-lucide-info" :title="notice" />
      <ControlBar v-if="controls.length" :controls="controls" :schema="schema" :state="state" :axes="tab === 'chart'" @update="update" />
      <UTabs v-model="tab" :items="tabs" variant="link" :content="false" class="w-full" />
      <UAlert v-if="error" color="error" variant="subtle" title="The table cannot be read" :description="error" />
      <p v-else-if="!shown" class="text-sm text-muted">
        Loading the table…
      </p>
      <p v-else-if="entry.rows === 0" class="text-sm text-muted">
        This Blick's table has no rows.
      </p>
      <p v-else-if="!shown.length" class="text-sm text-muted">
        No rows for this selection.
      </p>
      <BlickChart
        v-else-if="tab === 'chart'"
        :type="definition.plot.type"
        :name="fileName"
        :mapping="definition.plot.mapping"
        :schema="schema"
        :unit="definition.unit"
        :rows="shown"
        :splits="state.splits"
        :y="state.y"
      />
      <DataTable v-else :rows="shown" :schema="schema" :unit="definition.unit" />
    </template>
  </div>
</template>
