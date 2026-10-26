<script setup lang="ts">
import { buildParts, counts, schemaSummary } from '~/lib/comparison'

const { baselines, chosen, comparison, error } = useComparison()

// The selector's value for no baseline; a build id is hexadecimal.
const NONE = 'none'
const selected = computed({
  get: () => chosen.value ?? NONE,
  set: (value: string) => {
    chosen.value = value === NONE ? null : value
  },
})
// Baselines are told apart by run, commit and time; the one checked last comes first, and "No
// baseline" last, after a separator.
const items = computed(() => [
  baselines.value.toReversed().map((c) => {
    // The run is the first part.
    const [run, ...rest] = buildParts(c.baseline)
    return { label: run, description: rest.join(' · '), value: c.baseline.id }
  }),
  [{ label: 'No baseline', value: NONE }],
])
// The open list is wider than the selector, from its start, so that the items' descriptions fit a
// line, and high enough for a handful of baselines and "No baseline" without scrolling.
const LIST = 'min-w-[min(28rem,calc(100vw-2rem))] max-h-[min(24rem,var(--reka-combobox-content-available-height,24rem))]'
// The baseline shown: the closed selector names its run, as the items do, or says `Baseline:
// none`; its accessible name has all the parts.
const shown = computed(() => (comparison.value ? buildParts(comparison.value.baseline) : ['none']))
const summary = computed(() => (comparison.value ? schemaSummary(comparison.value) : []))
</script>

<template>
  <UAlert v-if="error" color="warning" variant="subtle" icon="i-lucide-triangle-alert" title="No comparison shown" :description="error" />
  <section v-else-if="baselines.length" class="space-y-1 text-sm" aria-label="Comparison with the baseline">
    <div class="flex items-center gap-2">
      <span class="shrink-0 text-muted">Baseline:</span>
      <USelectMenu
        v-model="selected"
        :items="items"
        value-key="value"
        :search-input="false"
        size="sm"
        class="min-w-0"
        :aria-label="`Baseline: ${shown.join(' · ')}`"
        :content="{ align: 'start' }"
        :ui="{ content: LIST, itemLabel: 'whitespace-normal wrap-anywhere', itemDescription: 'whitespace-normal wrap-anywhere' }"
      >
        <span class="truncate">{{ shown[0] }}</span>
      </USelectMenu>
    </div>
    <template v-if="comparison">
      <p class="text-muted">
        {{ counts(comparison) }}
      </p>
      <p v-if="comparison.incomplete.length" class="text-muted">
        removed not judged: {{ comparison.incomplete.join('; ') }}
      </p>
      <ul v-if="summary.length" class="text-muted">
        <li v-for="text in summary" :key="text">
          {{ text }}
        </li>
      </ul>
    </template>
  </section>
</template>
