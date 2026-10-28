<script setup lang="ts">
import { inRange, ranged } from '~/lib/builder'
import type { Dimension } from '~/lib/manifest'
import { valueKey } from '~/lib/table'

// The values kept of a dimension in the Blick builder: a multi-select with "all" and "none" for
// strings and booleans, a range for integers, dates and datetimes. `only` is `null` for all
// values; `from` and `to` are `undefined` for an open end.
const props = defineProps<{ dimension: Dimension, only: string[] | null, from: string | undefined, to: string | undefined }>()
const emit = defineEmits<{ only: [values: string[] | null], range: [from: string | undefined, to: string | undefined] }>()

const keys = computed(() => props.dimension.values.map(value => valueKey(value, props.dimension.dtype)))
const items = computed(() => keys.value.map(key => ({ label: key, value: key })))
const selected = computed(() => props.only ?? keys.value)
const start = computed(() => props.from ?? keys.value[0])
const end = computed(() => props.to ?? keys.value.at(-1))
// A range never ends before it starts: each end offers the values on its side of the other.
const startItems = computed(() => items.value.slice(0, Math.max(0, keys.value.indexOf(end.value ?? '')) + 1))
const endItems = computed(() => items.value.slice(Math.max(0, keys.value.indexOf(start.value ?? ''))))

/** Keep `values`, in the dimension's order; all of them is no selection. */
function choose(values: string[]) {
  const chosen = keys.value.filter(key => values.includes(key))
  emit('only', chosen.length === keys.value.length ? null : chosen)
}

/** The range from `from` to `to`; an end at the first or last value is open. */
function range(from: string | undefined, to: string | undefined) {
  emit('range', from === keys.value[0] ? undefined : from, to === keys.value.at(-1) ? undefined : to)
}

const count = computed(() => (ranged(props.dimension) ? inRange(props.dimension, props.from, props.to).length : selected.value.length))
// The count a range shows: all for a whole range, which the dimension's values in the dataset
// may exceed for one quantity, else how many of them.
const rangeCount = computed(() => (props.from === undefined && props.to === undefined ? 'all' : `${count.value} of ${keys.value.length}`))
// What the closed select shows: all, none, a few values by name, or how many of all.
const shown = computed(() => {
  if (count.value === keys.value.length) return 'all'
  if (!count.value) return 'none'
  return count.value <= 3 ? selected.value.join(', ') : `${count.value} of ${keys.value.length}`
})
</script>

<template>
  <div v-if="ranged(dimension)" class="flex items-center gap-2 text-sm">
    <span class="text-xs text-muted">Values</span>
    <USelect
      :model-value="start"
      :items="startItems"
      size="sm"
      class="min-w-24"
      :aria-label="`${dimension.name} from`"
      @update:model-value="(value: string) => range(value, to)"
    />
    <span class="text-muted">to</span>
    <USelect
      :model-value="end"
      :items="endItems"
      size="sm"
      class="min-w-24"
      :aria-label="`${dimension.name} to`"
      @update:model-value="(value: string) => range(from, value)"
    />
    <span class="text-xs text-muted">{{ rangeCount }}</span>
  </div>
  <div v-else class="flex flex-wrap items-center gap-1.5">
    <span class="text-xs text-muted">Values</span>
    <USelectMenu
      :model-value="selected"
      :items="items"
      value-key="value"
      multiple
      :search-input="items.length > 10"
      size="sm"
      class="min-w-0 flex-1"
      :aria-label="`${dimension.name} values`"
      @update:model-value="choose"
    >
      <span class="truncate">{{ shown }}</span>
    </USelectMenu>
    <UButton size="xs" color="neutral" variant="ghost" label="all" :aria-label="`All values of ${dimension.name}`" :disabled="only === null" @click="emit('only', null)" />
    <UButton size="xs" color="neutral" variant="ghost" label="none" :aria-label="`No value of ${dimension.name}`" :disabled="only !== null && !only.length" @click="emit('only', [])" />
  </div>
</template>
