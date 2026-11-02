<script setup lang="ts">
import type { YAxis } from '~/lib/controls'
import type { Scale, TableSchema } from '~/lib/manifest'
import type { Row } from '~/lib/table'
import { PLOT_TYPES } from '~/plots'
import { changePlot, exportName } from '~/plots/change'
import { belowZeroNote } from '~/plots/scales'
import type { ChangeKind } from '~/plots/types'

const props = defineProps<{
  type: string
  /** The name exported images get, without extension; a change chart's adds the change. */
  name: string
  mapping: Record<string, string>
  /** The scales of the channels whose axis is not linear; without it, every axis is linear. */
  scales?: Record<string, Scale>
  schema: TableSchema
  unit: string | null
  rows: Row[]
  splits: string[]
  y: YAxis
  /** The baseline's rows to draw behind the chart, or to draw the change against. */
  baseline: Row[] | null
  /** The change against the baseline to draw instead of the measure. */
  kind?: ChangeKind
  /** A small chart, without legend and export menu; never a change chart. */
  compact?: boolean
}>()

const container = useTemplateRef<HTMLElement>('container')
const width = useWidth(container)
const theme = useTheme()
// The change of a plot type without a browser half is not drawn: the chart above says why.
const plot = computed(() => {
  const builtIn = PLOT_TYPES[props.type]
  if (!builtIn) return null
  return props.kind ? changePlot(props.kind, builtIn.change) : builtIn.plot
})
// The values the logarithmic axes draw as missing, said under the chart of the measure only.
const note = computed(() => {
  if (props.kind || props.compact) return ''
  return belowZeroNote({ table: props.rows, mapping: props.mapping, scales: props.scales })
})
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
      scales: props.scales,
      unit: props.unit,
      state: { splits: props.splits, y: props.y },
      baseline: props.baseline,
      theme: theme.value,
      name: props.kind ? exportName(props.name, props.kind) : props.name,
      compact: props.compact,
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
watch(() => [props.rows, props.baseline, props.splits, props.y, props.type, props.mapping, props.scales, props.unit, props.compact, theme.value], async () => {
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
  <div v-if="plot || !kind">
    <div v-if="!plot" class="rounded-md border border-dashed border-default p-6 text-sm text-muted">
      This viewer has no browser half for the plot type <code>{{ type }}</code>; the data tab shows the table.
    </div>
    <UAlert v-else-if="failure" color="error" variant="subtle" title="The chart cannot be drawn" :description="failure" />
    <template v-else>
      <div ref="container" class="w-full" />
      <p v-if="note" class="mt-1 text-xs text-muted">
        {{ note }}
      </p>
    </template>
  </div>
</template>
