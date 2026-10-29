<script setup lang="ts">
import { PREVIEWS, pinnedHint, previewSections, troubles } from '~/lib/preview'
import { sidebarOrder } from '~/lib/sidebar'

const { manifest, dev } = useManifest()
const { comparison, blicks, loading } = useComparison()
const { pinned } = usePins()

useHead({ title: computed(() => (manifest.value ? `${manifest.value.run.id} · blicket` : 'blicket')) })

const entries = computed(() => (manifest.value ? sidebarOrder(manifest.value) : []))
// Nothing is drawn while the comparisons load, so the first Blicks never show before the changed ones.
const sections = computed(() => (loading.value ? null : previewSections(entries.value, comparison.value?.blicks ?? [], blicks.value, pinned.value, PREVIEWS)))
const total = computed(() => manifest.value?.blicks.length ?? 0)
// While nothing is pinned and nothing changed, the section shows the first Blicks instead.
const firstLook = computed(() => !!sections.value?.unpinned && sections.value.pinned.length > 0)
const more = computed(() => {
  const changed = sections.value?.changed
  return changed?.cards.length && changed.listed.length ? `${changed.listed.length} more changed` : null
})
const broken = computed(() => (manifest.value?.blicks ?? []).filter(b => b.status === 'error'))
const errors = computed(() => (manifest.value?.problems ?? []).filter(p => p.severity === 'error'))
const warnings = computed(() => (manifest.value?.problems ?? []).filter(p => p.severity === 'warning'))
// The trouble of the build in a line, at the top, since the problems are far down the page.
const trouble = computed(() => (manifest.value ? troubles(manifest.value) : ''))
const problemsHeading = useTemplateRef<HTMLElement>('problemsHeading')

/** Bring the problems into view, and the keyboard with them. With the hash router, `#problems` would be a route. */
function seeProblems() {
  problemsHeading.value?.scrollIntoView({ block: 'start' })
  problemsHeading.value?.focus({ preventScroll: true })
}

// The cards of each section that still wait for their rows, by name: a status line per section
// says "Loading charts" once while any does, instead of each card.
const loadingCards = reactive({ changed: new Set<string>(), pinned: new Set<string>() })

function track(section: keyof typeof loadingCards, name: string, waits: boolean) {
  if (waits) loadingCards[section].add(name)
  else loadingCards[section].delete(name)
}

const pinnedCards = useTemplateRef<HTMLElement>('pinnedCards')
const pinnedHeading = useTemplateRef<HTMLElement>('pinnedHeading')

/**
 * Keep the keyboard in the section after a card's pin button changed it: on the button of the
 * Blick's card if it is still there, else of the card that took its place, else on the heading.
 */
async function refocus(name: string, index: number) {
  await nextTick()
  const cards = [...(pinnedCards.value?.querySelectorAll<HTMLElement>('[data-blick]') ?? [])]
  const card = cards.find(c => c.dataset.blick === name) ?? cards[index] ?? cards.at(-1)
  const button = card?.querySelector<HTMLElement>('[data-pin] button')
  if (button) button.focus()
  else pinnedHeading.value?.focus()
}
</script>

<template>
  <!-- The cards go in two columns when the page, not the window, is wide enough: the sidebar
       takes some of the window. -->
  <div v-if="manifest" class="@container space-y-8">
    <ComparisonBar />
    <UAlert
      v-if="trouble"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-x"
      :title="trouble"
      orientation="horizontal"
      :actions="[{ label: 'See problems', color: 'error', variant: 'outline', size: 'xs', onClick: seeProblems }]"
    />
    <template v-if="sections && total">
      <section v-if="sections.changed" class="space-y-3" aria-labelledby="changed">
        <h2 id="changed" class="text-sm font-semibold text-highlighted">
          Changed since the baseline
        </h2>
        <div v-if="sections.changed.cards.length" class="grid gap-4 @3xl:grid-cols-2">
          <BlickPreview v-for="card in sections.changed.cards" :key="card.entry.name" :entry="card.entry" :change="card.change" @loading="track('changed', card.entry.name, $event)" />
        </div>
        <p role="status" class="sr-only">
          {{ loadingCards.changed.size ? 'Loading charts' : '' }}
        </p>
        <template v-if="sections.changed.listed.length">
          <p v-if="more" class="pt-2 text-sm text-muted">
            {{ more }}
          </p>
          <ul class="divide-y divide-default">
            <li v-for="item in sections.changed.listed" :key="item.name" class="flex flex-wrap items-baseline gap-x-2 gap-y-1 py-2 text-sm">
              <NuxtLink v-if="item.to" :to="item.to" class="min-w-0 font-medium text-highlighted hover:underline" :class="{ 'font-mono font-normal': item.byName }">
                {{ item.label }}
              </NuxtLink>
              <span v-else class="min-w-0 font-mono text-muted">{{ item.label }}</span>
              <FlagBadge v-if="item.badge" :badge="item.badge" size="sm" />
              <p v-if="item.problem" class="w-full whitespace-pre-wrap break-words text-muted">
                {{ item.problem }}
              </p>
            </li>
          </ul>
        </template>
      </section>
      <section class="space-y-3" aria-labelledby="pinned">
        <h2 id="pinned" ref="pinnedHeading" tabindex="-1" class="text-sm font-semibold text-highlighted">
          {{ firstLook ? 'A first look' : 'Pinned' }}
        </h2>
        <p v-if="sections.unpinned" class="text-sm text-muted">
          {{ pinnedHint(sections.pinned.length) }}
        </p>
        <div v-if="sections.pinned.length" ref="pinnedCards" class="grid gap-4 @3xl:grid-cols-2">
          <BlickPreview
            v-for="(card, index) in sections.pinned"
            :key="card.entry.name"
            :entry="card.entry"
            :change="card.change"
            pinnable
            @toggle="refocus(card.entry.name, index)"
            @loading="track('pinned', card.entry.name, $event)"
          />
        </div>
        <p role="status" class="sr-only">
          {{ loadingCards.pinned.size ? 'Loading charts' : '' }}
        </p>
      </section>
    </template>
    <div v-if="!total && dev" class="space-y-3">
      <p class="text-sm text-muted">
        No Blicks yet. Build one from the run, or write it as code.
      </p>
      <UButton to="/builder" icon="i-lucide-wand-sparkles" label="Build a Blick" color="neutral" variant="outline" />
    </div>
    <p v-else-if="!total" class="text-sm text-muted">
      This build has no Blicks.
    </p>
    <!-- Whatever the comparison: the Blicks that did not build, and the build's own problems. -->
    <section v-if="trouble || warnings.length" class="space-y-4" aria-labelledby="problems">
      <h2 id="problems" ref="problemsHeading" tabindex="-1" class="scroll-mt-4 text-sm font-semibold text-highlighted">
        Problems
      </h2>
      <p v-if="manifest.build.incomplete" class="text-sm">
        This build is incomplete: a Blick module failed to import, so the Blicks it defines are missing.
      </p>
      <div v-for="entry in broken" :key="entry.name" class="space-y-2">
        <h3 class="text-sm font-medium text-highlighted">
          <NuxtLink v-if="entry.id" :to="`/blick/${entry.id}`" class="font-mono hover:underline">
            {{ entry.name }}
          </NuxtLink>
          <span v-else class="font-mono">{{ entry.name }}</span>
        </h3>
        <ProblemList :problems="entry.problems" />
      </div>
      <div v-if="errors.length || warnings.length" class="space-y-2">
        <h3 class="text-sm font-medium text-highlighted">
          Files and the project
        </h3>
        <ProblemList :problems="[...errors, ...warnings]" />
      </div>
    </section>
  </div>
</template>
