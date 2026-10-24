<script setup lang="ts">
import type { YAxis } from '~/lib/controls'
import type { TableSchema } from '~/lib/manifest'
import type { Row } from '~/lib/table'
import { PLOT_TYPES } from '~/plots'

const props = defineProps<{
  type: string
  name: string
  mapping: Record<string, string>
  schema: TableSchema
  unit: string | null
  rows: Row[]
  splits: string[]
  y: YAxis
}>()

const container = useTemplateRef<HTMLElement>('container')
const width = useWidth(container)
const colorMode = useColorMode()
const plot = computed(() => PLOT_TYPES[props.type])
const failure = ref<string | null>(null)
let cleanup: (() => void) | null = null
let drawnAt = 0
let unmounted = false

// One render at a time: vega-embed empties the element when it starts, so overlapping renders
// could leave an older chart in place.
let queue = Promise.resolve()
function schedule() {
  queue = queue.then(draw)
}

async function draw() {
  const el = container.value
  const type = plot.value
  if (!el || !type || unmounted) return
  drawnAt = el.clientWidth
  cleanup?.()
  cleanup = null
  try {
    const done = await type.render({
      el,
      table: props.rows,
      schema: props.schema,
      mapping: props.mapping,
      unit: props.unit,
      state: { splits: props.splits, y: props.y },
      theme: colorMode.value === 'dark' ? 'dark' : 'light',
      name: props.name,
    })
    if (unmounted) done()
    else cleanup = done
  }
  catch (cause) {
    failure.value = cause instanceof Error ? cause.message : String(cause)
  }
}

let resize: ReturnType<typeof setTimeout> | undefined
watch(width, (current) => {
  clearTimeout(resize)
  resize = setTimeout(() => {
    if (current !== null && Math.abs(current - drawnAt) > 16) schedule()
  }, 150)
})

onMounted(schedule)
watch(() => [props.rows, props.splits, props.y, props.type, props.mapping, props.unit, colorMode.value], async () => {
  failure.value = null
  await nextTick()
  schedule()
})
onBeforeUnmount(() => {
  unmounted = true
  clearTimeout(resize)
  cleanup?.()
})
</script>

<template>
  <div>
    <div v-if="!plot" class="rounded-md border border-dashed border-default p-6 text-sm text-muted">
      This viewer has no browser half for the plot type <code>{{ type }}</code>; the data tab shows the table.
    </div>
    <UAlert v-else-if="failure" color="error" variant="subtle" title="The chart cannot be drawn" :description="failure" />
    <div v-else ref="container" class="w-full" />
  </div>
</template>
