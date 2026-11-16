<script setup lang="ts">
import { downloadCsv } from '~/lib/csv'
import { cutNote, tableOrder } from '~/lib/expectations'

// A check's page: what it is, its outcome against the baseline, and the table of its offending
// rows, worst first, as the build stored them.
const { manifest } = useManifest()
const { checks } = useComparison()

const id = useCheckId()
const entry = computed(() => manifest.value?.checks.find(c => c.id === id.value) ?? null)
const related = computed(() => (entry.value ? checks.value.get(entry.value.name)?.expectation ?? null : null))
const schema = computed(() => entry.value?.columns ?? null)
const { rows, error } = useTable(() => (entry.value?.data ? { path: entry.value.data, hash: entry.value.hash } : null))
const cut = computed(() => (entry.value ? cutNote(entry.value) : null))
const order = computed(() => (entry.value ? tableOrder(entry.value) : ''))

function saveCsv() {
  if (rows.value && schema.value) downloadCsv(rows.value, schema.value, null, {}, id.value.replaceAll('/', '__'))
}
</script>

<template>
  <UnitPage kind="check" :id="id" :entry="entry">
    <template #meta>
      <span>check</span>
    </template>
    <template #files>
      <button v-if="rows?.length" type="button" class="underline hover:text-default" @click="saveCsv">
        CSV
      </button>
    </template>
    <template #strips>
      <OutcomeStrip v-if="entry" :outcome="entry.outcome" :related="related" :why="entry.status !== 'skipped'" />
    </template>
    <template v-if="entry?.data && schema">
      <p v-if="cut" class="text-sm text-muted">
        {{ cut }}; the outcome counts them all.
      </p>
      <UAlert v-if="error" color="error" variant="subtle" title="The table cannot be read" :description="error" />
      <p v-else-if="!rows" class="text-sm text-muted">
        Loading the table…
      </p>
      <DataTable v-else :rows="rows" :schema="schema" :unit="null" :note="order" />
    </template>
  </UnitPage>
</template>
