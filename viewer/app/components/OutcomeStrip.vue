<script setup lang="ts">
import { whereState, type ExpectationComparison } from '~/lib/comparison'
import type { ControlState } from '~/lib/controls'
import { expectationBadge, fullSentence, offends, transitionText } from '~/lib/expectations'
import type { Outcome, TableSchema } from '~/lib/manifest'

// The outcome of a unit's expectation, on a Blick's page and a check's: its badge, the outcome in a
// sentence with the expectation in words and where it is worst, and the transition against the
// baseline shown; without an outcome now, the baseline's when the expectation is dropped. A met
// outcome is one muted line. `why` false leaves out why a side has no outcome, which the page
// says itself, as for a skipped unit. On a Blick's page, `state` and `schema` are its controls',
// and "Show worst row" sets the filters to the worst row (`update`), as the change strip's button
// does for the largest change; once they are there, the button says so.
const props = withDefaults(defineProps<{
  outcome: Outcome | null
  related: ExpectationComparison | null
  state?: ControlState | null
  schema?: TableSchema | null
  why?: boolean
}>(), { state: null, schema: null, why: true })
const emit = defineEmits<{ update: [state: ControlState] }>()

const badge = computed(() => expectationBadge(props.outcome))
const sentence = computed(() => {
  if (props.outcome) return fullSentence(props.outcome)
  const dropped = props.related?.transition === 'dropped' ? props.related.baseline : null
  return dropped ? `in the baseline: ${fullSentence(dropped)}` : null
})
const transition = computed(() => transitionText(props.related, props.why))
// Whether the worst row lies on a filter the Blick has, so that the button can show it.
const showable = computed(() => {
  const where = props.outcome?.where
  return offends(props.outcome) && !!where && !!props.state && !!props.schema && Object.keys(props.state.filters).some(name => name in where)
})
// The filters that show the worst row, `null` when they are set already.
const there = computed(() => (showable.value && props.state && props.schema && props.outcome?.where ? whereState(props.state, props.outcome.where, props.schema) : null))
</script>

<template>
  <div v-if="sentence || transition" class="space-y-1 text-sm" role="group" aria-label="Expectation">
    <p v-if="!badge" class="text-muted">
      {{ sentence ?? 'no outcome now' }}<template v-if="transition">
        · {{ transition }}
      </template>
    </p>
    <div v-else class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <OutcomeBadge :badge="badge" />
      <span class="min-w-0 break-words">{{ sentence }}</span>
      <span v-if="transition" class="text-muted">{{ transition }}</span>
      <UButton v-if="showable && there" size="xs" color="neutral" variant="outline" icon="i-lucide-crosshair" label="Show worst row" @click="emit('update', there)" />
      <UButton v-else-if="showable" size="xs" color="neutral" variant="ghost" icon="i-lucide-check" label="Worst row shown" disabled />
    </div>
  </div>
</template>
