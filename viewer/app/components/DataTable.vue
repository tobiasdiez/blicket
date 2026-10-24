<script setup lang="ts">
import { h, resolveComponent } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { withUnit, type TableSchema } from '~/lib/manifest'
import { display, formatValue, type Cell, type Row } from '~/lib/table'

const props = defineProps<{ rows: Row[], schema: TableSchema, unit: string | null }>()

const LIMIT = 2000
const UButton = resolveComponent('UButton')
const sorting = ref<{ id: string, desc: boolean }[]>([])
const scroller = useTemplateRef<HTMLElement>('scroller')
const width = useWidth(scroller)
// Whether the table is wider than its box, measured whenever the box changes size.
const overflowing = computed(() => width.value !== null && scroller.value !== null && scroller.value.scrollWidth > width.value + 1)

function compare(a: Cell, b: Cell): number {
  if (a === b) return 0
  if (a === null) return 1
  if (b === null) return -1
  if (a instanceof Date && b instanceof Date) return a.getTime() - b.getTime()
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b))
}

const sorted = computed(() => {
  const [by] = sorting.value
  if (!by) return props.rows.slice(0, LIMIT)
  const sign = by.desc ? -1 : 1
  return props.rows.toSorted((a, b) => sign * compare(a[by.id] ?? null, b[by.id] ?? null)).slice(0, LIMIT)
})

// On a narrow page the last column, the value, stays in view while the others scroll.
const STICKY = 'max-sm:sticky max-sm:right-0 max-sm:bg-default'

const columns = computed<TableColumn<Row>[]>(() => [
  ...props.schema.dimensions.map(d => ({ name: d.name, label: d.name, format: (value: Cell) => (value === null ? '' : display(value, d)), numeric: d.dtype === 'integer' })),
  // Six significant digits, chosen per value, so close values stay apart.
  ...props.schema.measures.map(m => ({ name: m.name, label: withUnit(m.name, props.unit), format: (value: Cell) => (typeof value === 'number' ? formatValue(value, 6) : ''), numeric: true })),
].map(({ name, label, format, numeric }, index, all) => ({
  id: name,
  accessorFn: (row: Row) => row[name],
  enableSorting: true,
  header: ({ column }) => {
    const order = column.getIsSorted()
    return h(UButton, {
      color: 'neutral',
      variant: 'ghost',
      size: 'sm',
      label,
      icon: order ? (order === 'asc' ? 'i-lucide-arrow-up-narrow-wide' : 'i-lucide-arrow-down-wide-narrow') : 'i-lucide-arrow-up-down',
      class: '-mx-2.5',
      onClick: () => column.toggleSorting(order === 'asc'),
    })
  },
  cell: ({ row }) => format((row.original[name] ?? null) as Cell),
  meta: {
    class: {
      th: [numeric ? 'text-right' : '', index === all.length - 1 ? STICKY : ''].join(' '),
      td: [numeric ? 'text-right tabular-nums' : '', index === all.length - 1 ? STICKY : ''].join(' '),
    },
  },
})))

</script>

<template>
  <div class="space-y-2">
    <p class="text-sm text-muted">
      <template v-if="rows.length > LIMIT">
        The first {{ LIMIT.toLocaleString('en') }} of {{ rows.length.toLocaleString('en') }} rows shown; the Parquet file has them all.
      </template>
      <template v-else>
        {{ rows.length.toLocaleString('en') }} rows shown.
      </template>
      <span v-if="overflowing"> Scroll sideways for more columns.</span>
    </p>
    <div ref="scroller" class="max-h-[70vh] overflow-auto rounded-md border border-default">
      <UTable
        v-model:sorting="sorting"
        :data="sorted"
        :columns="columns"
        :sorting-options="{ manualSorting: true }"
        sticky
        :ui="{ root: 'overflow-visible', th: 'px-2 py-1.5 sm:px-3', td: 'px-2 py-1 sm:px-3' }"
      />
    </div>
  </div>
</template>
