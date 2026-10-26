<script setup lang="ts">
import { withFilter, withSplit, withoutSplit, parseValue, type ControlState } from '~/lib/controls'
import type { Control, Dimension, TableSchema } from '~/lib/manifest'
import { valueKey } from '~/lib/table'

// `axes` shows the y axis switch, which only the chart needs; the slot holds the page's switches.
const props = defineProps<{ controls: Control[], schema: TableSchema, state: ControlState, axes: boolean }>()
const emit = defineEmits<{ update: [state: ControlState] }>()

const rows = computed(() => props.controls.flatMap((control) => {
  const dimension = props.schema.dimensions.find(d => d.name === control.dimension)
  if (!dimension) return []
  const items = dimension.values.map((value) => {
    const key = valueKey(value, dimension.dtype)
    return { label: key, value: key }
  })
  const current = props.state.filters[control.dimension]
  return [{ dimension, items, split: props.state.splits.includes(control.dimension), selected: current === undefined ? undefined : valueKey(current, dimension.dtype) }]
}))

function choose(dimension: Dimension, key: string | undefined) {
  const value = key === undefined ? undefined : parseValue(dimension, key)
  if (value !== undefined) emit('update', withFilter(props.state, dimension.name, value))
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-5 gap-y-3">
    <div v-for="row in rows" :key="row.dimension.name" class="flex flex-wrap items-center gap-1.5">
      <span class="text-sm text-muted">{{ row.dimension.name }}</span>
      <span v-if="row.split" class="flex h-8 min-w-36 items-center text-sm">all (panels)</span>
      <USelectMenu
        v-else
        :model-value="row.selected"
        :items="row.items"
        value-key="value"
        :search-input="row.items.length > 10"
        size="sm"
        class="min-w-36"
        :aria-label="row.dimension.name"
        @update:model-value="(key: string | undefined) => choose(row.dimension, key)"
      />
      <UButton
        v-if="row.items.length > 1"
        size="sm"
        color="neutral"
        :variant="row.split ? 'soft' : 'ghost'"
        icon="i-lucide-layout-grid"
        label="Split into panels"
        :aria-pressed="row.split"
        :title="row.split ? `Show one ${row.dimension.name} at a time again` : `One panel per ${row.dimension.name}`"
        @click="emit('update', row.split ? withoutSplit(state, controls, schema, row.dimension.name) : withSplit(state, controls, row.dimension.name))"
      />
    </div>
    <USwitch
      v-if="axes && state.splits.length"
      :model-value="state.y === 'independent'"
      label="Own y axis per panel"
      size="sm"
      @update:model-value="(own: boolean) => emit('update', { ...state, y: own ? 'independent' : 'shared' })"
    />
    <slot />
  </div>
</template>
