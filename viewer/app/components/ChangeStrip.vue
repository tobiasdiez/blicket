<script setup lang="ts">
import type { ControlState } from '~/lib/controls'
import { buildParts, percent, schemaDetails, whereState, whereText, type BlickComparison, type BuildRef } from '~/lib/comparison'
import type { TableSchema } from '~/lib/manifest'

// `state` and `schema` are null for a Blick without a table, whose problems the page lists, the
// comparison's message among them.
const props = defineProps<{ blick: BlickComparison, baseline: BuildRef, state: ControlState | null, schema: TableSchema | null, mapping: Record<string, string> }>()
const emit = defineEmits<{ update: [state: ControlState] }>()

const change = computed(() => props.blick.change)
const against = computed(() => `against ${buildParts(props.baseline, false).join(' · ')}`)
// A Blick in error was not compared, so its sentence names no baseline.
const sentence = computed(() => {
  const { where, magnitude, flags } = change.value
  if (flags.includes('error')) return ''
  if (!where || !magnitude || !props.state) return against.value
  return `largest change ${percent(magnitude)} of the chart's scale at ${whereText(where, props.state, props.mapping)}, ${against.value}`
})
// The controls that show the largest change, when they are not set already.
const there = computed(() => (change.value.where && props.state && props.schema ? whereState(props.state, change.value.where, props.schema) : null))
const details = computed(() => [
  ...schemaDetails(change.value),
  ...(props.blick.matched ? [`compared with its former id ${props.blick.matched}`] : []),
  ...(props.blick.message && props.state ? [props.blick.message] : []),
])
</script>

<template>
  <div class="space-y-1 text-sm">
    <p v-if="!change.flags.length" class="text-muted">
      unchanged {{ against }}
    </p>
    <div v-else class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span class="flex gap-1.5"><FlagBadges :change="change" /></span>
      <span v-if="sentence">{{ sentence }}</span>
      <UButton v-if="there" size="xs" color="neutral" variant="outline" icon="i-lucide-crosshair" label="Show where" @click="emit('update', there)" />
    </div>
    <ul v-if="details.length" class="text-muted">
      <li v-for="text in details" :key="text" class="break-words">
        {{ text }}
      </li>
    </ul>
  </div>
</template>
