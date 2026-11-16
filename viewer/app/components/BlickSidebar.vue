<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'
import type { Badge } from '~/lib/comparison'
import type { ExpectationBadge } from '~/lib/expectations'
import { CHECKS, changedCount, filterOptions, footText, initiallyOpen, noMatch, notMetUnits, sidebarChecks, sidebarGroups, type SidebarFilter } from '~/lib/sidebar'

const route = useRoute()
const { manifest, dev } = useManifest()
const { blicks, loading } = useComparison()
const { pinned } = usePins()
const { open, closeDrawer } = useSidebar()
const currentBlick = useBlickId()
const currentCheck = useCheckId()

// The search, the filter and the groups left open live as long as the sidebar, which is mounted
// once and outlives the pages; they are not in the URL. `chosen` are the groups the user left
// open, `null` before the user opened or closed one, when those of `initiallyOpen` are, together
// with `opened`, the groups that a unit's page opened meanwhile; `filtered` those open while a
// search or the filter is active. `opened` is kept apart from `chosen` so that the groups open at
// first follow the comparison, which may load after the page. The checks are a section after the
// groups, opened and closed as one.
const search = ref('')
const filter = ref<SidebarFilter>('all')
const chosen = ref<string[] | null>(null)
const opened = ref<string[]>([])
const filtered = ref<string[]>([])

const pinnedNames = computed(() => new Set(pinned.value.map(entry => entry.name)))
const groups = computed(() => {
  if (!manifest.value) return []
  const checks = sidebarChecks(manifest.value, search.value, filter.value)
  return [...sidebarGroups(manifest.value, blicks.value, pinnedNames.value, search.value, filter.value), ...(checks ? [checks] : [])]
})
const changed = computed(() => (manifest.value ? changedCount(manifest.value, blicks.value) : 0))
const notMet = computed(() => (manifest.value ? notMetUnits(manifest.value) : 0))
const options = computed(() => filterOptions(changed.value, notMet.value))
const filtering = computed(() => search.value.trim() !== '' || filter.value !== 'all')
const total = computed(() => (manifest.value ? manifest.value.blicks.length + manifest.value.checks.length : 0))
const matching = computed(() => groups.value.reduce((sum, group) => sum + group.entries.length, 0))
const foot = computed(() => (manifest.value ? footText(manifest.value, filtering.value ? matching.value : null) : ''))

// A state that is no longer offered, as Changed once no Blick is flagged, gives way to All.
watch(options, (offered) => {
  if (!offered.some(option => option.value === filter.value)) filter.value = 'all'
})

// While a search or the filter is active, every group with a match opens as the matches change;
// a group the user closes meanwhile stays closed until they change again.
watch(() => filtering.value && groups.value.map(group => group.value).join('\n'), () => {
  if (filtering.value) filtered.value = groups.value.map(group => group.value)
}, { immediate: true })

const expanded = computed({
  get: () => (filtering.value ? filtered.value : chosen.value ?? initiallyOpen(groups.value, opened.value)),
  set: (value: string | string[] | undefined) => {
    const list = Array.isArray(value) ? value : value ? [value] : []
    if (filtering.value) filtered.value = list
    else chosen.value = list
  },
})

/** A unit's item of the navigation menu, whose slots know only the groups' items. */
interface BlickItem extends NavigationMenuItem {
  flag: Badge | null
  expectation: ExpectationBadge | null
  /** A unit skipped for the run that no badge marks: its label is in italics. */
  muted: boolean
  pinned: boolean
}

const items = computed<NavigationMenuItem[]>(() => groups.value.map(group => ({
  label: group.label,
  value: group.value,
  children: group.entries.map((shown): BlickItem => ({
    label: shown.label,
    to: shown.to ?? undefined,
    disabled: shown.disabled,
    slot: 'blick',
    flag: shown.badge,
    expectation: shown.expectation,
    muted: shown.muted,
    pinned: shown.pinned,
  })),
})))

// A unit's page opens its group, or the section of the checks, and scrolls its item into view, in
// the sidebar and the drawer; after the group's opening animation, when it had to open.
watch([currentBlick, currentCheck, manifest], async () => {
  const blick = manifest.value?.blicks.find(b => b.id === currentBlick.value)
  const group = blick?.group ?? (manifest.value?.checks.some(c => c.id === currentCheck.value) ? CHECKS : undefined)
  if (!group || !groups.value.some(g => g.value === group)) return
  const opening = !expanded.value.includes(group)
  if (opening && !filtering.value && chosen.value === null) opened.value = [...opened.value, group]
  else if (opening) expanded.value = [...expanded.value, group]
  await nextTick()
  setTimeout(() => {
    for (const link of document.querySelectorAll<HTMLElement>('[data-blick-list] [aria-current="page"]')) link.scrollIntoView({ block: 'nearest' })
  }, opening ? 250 : 0)
}, { immediate: true })

// The drawer of a narrow window closes when a Blick is picked.
watch(() => route.fullPath, closeDrawer)

/**
 * Clear the search, and keep the keyboard on the search box of the sidebar or the drawer that was
 * clicked: the header is drawn in both, so it is found from the click, not by a template ref.
 */
function clearSearch(event: Event) {
  search.value = ''
  const content = (event.target as Element).closest('[data-slot="header"], [data-slot="body"]')?.parentElement
  content?.querySelector<HTMLInputElement>('[data-slot="header"] input')?.focus()
}

/** Show every unit again: no search, no filter. */
function showAll(event: Event) {
  filter.value = 'all'
  clearSearch(event)
}

/**
 * The drawer starts on the current Blick's item, or on its close button: on a phone, the search
 * box would open the keyboard over the list.
 */
function focusOnOpen(event: Event) {
  event.preventDefault()
  const content = event.target as HTMLElement
  const target = content.querySelector<HTMLElement>('[data-blick-list] [aria-current="page"]') ?? content.querySelector<HTMLElement>('[data-slot="close"]')
  target?.focus()
}
</script>

<template>
  <USidebar
    id="sidebar"
    v-model:open="open"
    collapsible="offcanvas"
    breakpoint="xl"
    :menu="{ title: 'Blicks', content: { onOpenAutoFocus: focusOnOpen } }"
    :inert="!open"
    :ui="{
      root: '[--sidebar-width:18rem]',
      container: 'bg-default',
      // The search box is the title: not cut off, so its focus ring shows.
      title: 'text-clip font-normal',
      body: 'p-2',
      footer: 'flex-col items-start gap-3 text-sm text-muted',
    }"
  >
    <template #title>
      <UInput v-model="search" icon="i-lucide-search" :placeholder="manifest?.checks.length ? 'Search' : 'Search Blicks'" :aria-label="manifest?.checks.length ? 'Search Blicks and checks' : 'Search Blicks'" class="w-full" :ui="{ trailing: 'pe-1' }">
        <template v-if="search" #trailing>
          <UButton color="neutral" variant="link" size="sm" icon="i-lucide-circle-x" aria-label="Clear the search" @click="clearSearch" />
        </template>
      </UInput>
    </template>
    <template #actions>
      <!-- Its room is kept while the comparisons load, so the search box does not shrink then. -->
      <USelect
        v-if="options.length || loading"
        v-model="filter"
        :items="options"
        value-key="value"
        size="sm"
        aria-label="Show"
        :highlight="filter !== 'all'"
        :class="['w-30 shrink-0', { invisible: !options.length }]"
        :content="{ align: 'end' }"
      />
    </template>

    <div data-blick-list>
      <UNavigationMenu
        v-model="expanded"
        :items="items"
        orientation="vertical"
        highlight
        aria-label="Blicks"
        :ui="{
          // Titles wrap rather than being cut off; the focus ring is opaque, as the buttons' are.
          linkLabel: 'text-clip',
          link: 'before:outline-primary',
        }"
      >
        <template #blick-label="{ item }: { item: BlickItem }">
          <span :class="{ italic: item.muted }">{{ item.label }}</span><span v-if="item.muted" class="sr-only"> (skipped)</span>
        </template>
        <template #blick-trailing="{ item }: { item: BlickItem }">
          <FlagBadge v-if="item.flag" :badge="item.flag" size="sm" inline />
          <OutcomeBadge v-if="item.expectation" :badge="item.expectation" size="sm" />
          <PinMark v-if="item.pinned" />
        </template>
      </UNavigationMenu>
      <div v-if="total && !groups.length" class="space-y-2 px-2.5 py-1.5 text-sm text-muted">
        <p>{{ noMatch(search, filter, !!manifest?.checks.length) }}</p>
        <UButton size="sm" color="neutral" variant="outline" label="Show all" @click="showAll" />
      </div>
    </div>

    <template #footer>
      <p v-if="manifest">
        {{ foot }}
      </p>
      <UButton v-if="dev" to="/builder" icon="i-lucide-wand-sparkles" label="Build a Blick" color="neutral" variant="outline" size="sm" />
    </template>
  </USidebar>
</template>
