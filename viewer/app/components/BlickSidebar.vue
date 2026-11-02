<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'
import type { Badge } from '~/lib/comparison'
import { byStatus } from '~/lib/manifest'
import { changedCount, initiallyOpen, noMatch, sidebarGroups } from '~/lib/sidebar'

const route = useRoute()
const { manifest, dev } = useManifest()
const { blicks, loading } = useComparison()
const { pinned } = usePins()
const { open, closeDrawer } = useSidebar()
const current = useBlickId()

// The search, the filter and the groups left open live as long as the sidebar, which is mounted
// once and outlives the pages; they are not in the URL. `chosen` are the groups the user left
// open, `null` before the user opened or closed one, when those of `initiallyOpen` are, together
// with `opened`, the groups that a Blick's page opened meanwhile; `filtered` those open while a
// search or the filter is active. `opened` is kept apart from `chosen` so that the groups open at
// first follow the comparison, which may load after the page.
const search = ref('')
const changedOnly = ref(false)
const chosen = ref<string[] | null>(null)
const opened = ref<string[]>([])
const filtered = ref<string[]>([])

const pinnedNames = computed(() => new Set(pinned.value.map(entry => entry.name)))
const groups = computed(() => (manifest.value ? sidebarGroups(manifest.value, blicks.value, pinnedNames.value, search.value, changedOnly.value) : []))
const changed = computed(() => (manifest.value ? changedCount(manifest.value, blicks.value) : 0))
const filtering = computed(() => search.value.trim() !== '' || changedOnly.value)
const total = computed(() => manifest.value?.blicks.length ?? 0)
const matching = computed(() => groups.value.reduce((sum, group) => sum + group.entries.length, 0))
const statuses = computed(() => byStatus(manifest.value?.blicks ?? []))

// Without a flagged Blick the toggle is gone, and so is its filter.
watch(changed, (count) => {
  if (!count) changedOnly.value = false
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

/** A Blick's item of the navigation menu, whose slots know only the groups' items. */
interface BlickItem extends NavigationMenuItem {
  flag: Badge | null
  /** A Blick skipped for the run that no comparison flags: its label is in italics. */
  muted: boolean
  pinned: boolean
}

const items = computed<NavigationMenuItem[]>(() => groups.value.map(group => ({
  label: group.label,
  value: group.value,
  children: group.entries.map((shown): BlickItem => ({
    label: shown.label,
    to: shown.entry.id ? `/blick/${shown.entry.id}` : undefined,
    disabled: shown.disabled,
    slot: 'blick',
    flag: shown.badge,
    muted: shown.muted,
    pinned: shown.pinned,
  })),
})))

// A Blick's page opens its group and scrolls its item into view, in the sidebar and the drawer;
// after the group's opening animation, when it had to open.
watch([current, manifest], async () => {
  const group = manifest.value?.blicks.find(b => b.id === current.value)?.group
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

/** Show every Blick again: no search, no filter. */
function showAll(event: Event) {
  changedOnly.value = false
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
      <UInput v-model="search" icon="i-lucide-search" placeholder="Search Blicks" aria-label="Search Blicks" class="w-full" :ui="{ trailing: 'pe-1' }">
        <template v-if="search" #trailing>
          <UButton color="neutral" variant="link" size="sm" icon="i-lucide-circle-x" aria-label="Clear the search" @click="clearSearch" />
        </template>
      </UInput>
    </template>
    <template #actions>
      <!-- Its room is kept while the comparisons load, so the search box does not shrink then. -->
      <UButton
        v-if="changed || loading"
        size="sm"
        color="neutral"
        :variant="changedOnly ? 'solid' : 'outline'"
        :aria-pressed="changedOnly"
        :label="`Changed (${changed})`"
        :class="{ invisible: !changed }"
        @click="changedOnly = !changedOnly"
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
          <PinMark v-if="item.pinned" />
        </template>
      </UNavigationMenu>
      <div v-if="total && !groups.length" class="space-y-2 px-2.5 py-1.5 text-sm text-muted">
        <p>{{ noMatch(search, changedOnly) }}</p>
        <UButton size="sm" color="neutral" variant="outline" label="Show all" @click="showAll" />
      </div>
    </div>

    <template #footer>
      <p v-if="manifest">
        <template v-if="filtering">{{ matching }} of </template>{{ total }} Blicks<span v-if="statuses.error.length"> · {{ statuses.error.length }}&nbsp;with&nbsp;errors</span><span v-if="statuses.skipped.length"> · {{ statuses.skipped.length }}&nbsp;skipped</span><span v-if="manifest.build.incomplete"> · incomplete, a module failed to import</span>
      </p>
      <UButton v-if="dev" to="/builder" icon="i-lucide-wand-sparkles" label="Build a Blick" color="neutral" variant="outline" size="sm" />
    </template>
  </USidebar>
</template>
