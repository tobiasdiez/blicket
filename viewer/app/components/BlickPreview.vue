<script setup lang="ts">
import { blickBadge, type BlickComparison } from '~/lib/comparison'
import { yAxisOf } from '~/lib/controls'
import { firstLine, type BlickEntry } from '~/lib/manifest'
import { firstProblem, previewCaption, previewLink, previewState } from '~/lib/preview'
import { PLOT_TYPES } from '~/plots'

// A Blick as a card of the overview: its title, which leads to its page, its badge, a small chart
// and a caption. `change` is the Blick in the comparison shown, if any. With `pinnable` the card
// has the button that pins or unpins the Blick, and says when it was clicked (`toggle`); without
// it a pin marks a pinned Blick. `loading` says whether the card waits for the rows it asked for,
// which the overview announces once for all its cards.
const props = defineProps<{ entry: BlickEntry, change: BlickComparison | null, pinnable?: boolean }>()
const emit = defineEmits<{ toggle: [], loading: [loading: boolean] }>()

const { isPinned } = usePins()

const definition = computed(() => props.entry.definition)
const title = computed(() => definition.value?.title ?? props.entry.name)
const defaultY = computed(() => yAxisOf(definition.value))
const preview = computed(() => previewState(props.entry, props.change, defaultY.value))
const link = computed(() => previewLink(props.entry, preview.value, defaultY.value))
const caption = computed(() => previewCaption(props.entry, preview.value, props.change))
const badge = computed(() => blickBadge(props.entry, props.change))
const pinned = computed(() => !!props.entry.id && isPinned(props.entry.id))
const problem = computed(() => firstProblem(props.entry))
// The first line of why the Blick was skipped, with an ellipsis when there is more on its page.
const reason = computed(() => {
  const first = firstLine(props.entry.skipped)
  return first === (props.entry.skipped ?? '').trimEnd() ? first : `${first} …`
})
const drawable = computed(() => !!definition.value && Object.hasOwn(PLOT_TYPES, definition.value.plot.type))

// The rows are fetched once the card first comes near the window, so a long list of cards costs
// what is seen.
const card = useTemplateRef<HTMLElement>('card')
const seen = ref(false)
let observer: IntersectionObserver | null = null
onMounted(() => {
  observer = new IntersectionObserver((records) => {
    if (!records.some(record => record.isIntersecting)) return
    seen.value = true
    observer?.disconnect()
  }, { rootMargin: '200px' })
  if (card.value) observer.observe(card.value)
})
onBeforeUnmount(() => observer?.disconnect())

// The chart waits for the baseline's rows, so it is drawn once; a baseline that cannot be read is
// left out.
const { error, shown, baselineWaiting, chartProps, fileName } = useBlickChart(
  () => props.entry,
  () => preview.value?.state ?? null,
  () => props.change,
  { load: () => seen.value && drawable.value },
)
const waiting = computed(() => !shown.value || baselineWaiting.value)
const loading = computed(() => seen.value && drawable.value && props.entry.status === 'ok' && !error.value && waiting.value)
watch(loading, value => emit('loading', value), { immediate: true })
onBeforeUnmount(() => emit('loading', false))

// Nuxt UI's skeleton is a polite alert with a label; one per card would be announced six times.
const SILENT = { 'aria-hidden': 'true', 'role': undefined, 'aria-label': undefined, 'aria-live': undefined, 'aria-busy': undefined }
</script>

<template>
  <!-- `data-blick` and `data-pin` are how the overview (pages/index.vue) finds a card's pin
       button again after a click changed the cards. -->
  <article ref="card" :data-blick="entry.name" class="flex min-w-0 flex-col gap-2 rounded-lg border border-default p-4">
    <div class="flex items-center gap-2">
      <h3 class="min-w-0 flex-1 font-medium text-highlighted">
        <NuxtLink v-if="link" :to="link" class="hover:underline">
          {{ title }}
        </NuxtLink>
        <template v-else>
          {{ title }}
        </template>
      </h3>
      <FlagBadge v-if="badge" :badge="badge" />
      <div v-if="pinnable && entry.id" data-pin class="-my-1 -me-1.5 shrink-0">
        <PinButton :id="entry.id" :label="title" icon @toggle="emit('toggle')" />
      </div>
      <PinMark v-else-if="pinned" />
    </div>
    <ProblemList v-if="entry.status === 'error'" :problems="problem ? [problem] : []" />
    <div v-else-if="entry.status === 'skipped'" class="text-sm text-muted">
      <p class="font-medium">
        Skipped for this run
      </p>
      <p class="break-words">
        {{ reason }}
      </p>
    </div>
    <p v-else-if="!drawable" class="text-sm text-muted">
      no chart for the plot type <code>{{ definition?.plot.type }}</code>
    </p>
    <UAlert v-else-if="error" color="error" variant="subtle" title="The table cannot be read" :description="error" :ui="{ description: 'wrap-anywhere' }" />
    <USkeleton v-else-if="waiting" class="h-51 w-full" v-bind="SILENT" />
    <p v-else-if="!shown?.length" class="text-sm text-muted">
      No rows for this selection.
    </p>
    <BlickChart v-else-if="chartProps" v-bind="chartProps" :name="fileName" compact />
    <p v-if="caption" class="text-sm text-muted">
      {{ caption }}
    </p>
  </article>
</template>
