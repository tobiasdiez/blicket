<script setup lang="ts">
import { statusLine, type PageState } from '~/lib/jobs'

// What a Blick's page in a session of blicket dev says of its build, on one line that stays while
// the page shows the Blick, so that a screen reader is told when a build starts and how it ended
// and the page does not jump: the line while it builds, is built again or waits, with a spinner,
// or a clock while it is queued, and `Build next` while another Blick a page asked for builds;
// otherwise how its last build ended, `outcome`. Another Blick is named by its title, as a link
// to it. The time is counted from what blicket dev said, and not told to a screen reader; `lost`
// says that blicket dev does not answer, and nothing is counted then. `build` follows a click on
// `Build next`, which then gives the keyboard to the line, since the button goes.
const props = defineProps<{ state: PageState, outcome: string | null, lost?: boolean }>()
const emit = defineEmits<{ build: [] }>()

const { later, title } = useJobs()
const parts = computed(() => statusLine(props.state, later.value, props.lost))
const waits = computed(() => props.state.kind === 'queued' || props.state.kind === 'built' || (props.state.kind === 'updating' && props.state.job.state === 'queued'))
const icon = computed(() => {
  if (!parts.value || props.lost || props.state.kind === 'other') return null
  return waits.value ? 'i-lucide-clock' : 'i-lucide-loader-circle'
})
const line = useTemplateRef<HTMLElement>('line')
const hint = useId()

function build() {
  emit('build')
  line.value?.focus()
}
</script>

<template>
  <div class="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-2 text-sm">
    <p ref="line" role="status" tabindex="-1" class="flex min-w-0 items-center gap-2 text-muted focus:outline-none">
      <UIcon v-if="icon" :name="icon" class="size-4 shrink-0" :class="{ 'animate-spin': !waits }" aria-hidden="true" />
      <span v-if="parts" class="min-w-0 break-words">
        <template v-for="(part, index) in parts" :key="index">
          <template v-if="typeof part === 'string'">{{ part }}</template>
          <NuxtLink v-else-if="'blick' in part" :to="`/blick/${part.blick}`" class="underline hover:text-default">{{ title(part.blick) }}</NuxtLink>
          <span v-else aria-hidden="true" class="tabular-nums">{{ part.time }}</span>
        </template>
      </span>
      <span v-else-if="outcome" class="min-w-0 break-words">{{ outcome }}</span>
    </p>
    <template v-if="state.kind === 'other' && !lost">
      <UButton size="sm" color="neutral" variant="outline" icon="i-lucide-list-plus" label="Build next" :aria-describedby="hint" @click="build" />
      <p :id="hint" class="w-full text-xs text-muted">
        Build next queues it behind {{ title(state.other.id) }}. Otherwise this page asks for it once nothing a page asked for builds or waits.
      </p>
    </template>
  </div>
</template>
