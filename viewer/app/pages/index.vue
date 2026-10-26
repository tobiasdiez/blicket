<script setup lang="ts">
import { ranked, type BlickComparison } from '~/lib/comparison'
import type { BlickEntry } from '~/lib/manifest'
import { searchText } from '~/lib/roles'

const route = useRoute()
const router = useRouter()
const { manifest } = useManifest()
const { comparison, blicks } = useComparison()

// The search is in the URL, so going back from a Blick restores it.
const search = computed({
  get: () => (typeof route.query.q === 'string' ? route.query.q : ''),
  set: (q: string) => void router.replace({ query: q ? { ...route.query, q } : { ...route.query, q: undefined } }),
})
const chosen = ref<string | null>(null)

useHead({ title: computed(() => (manifest.value ? `${manifest.value.run.id} · blicket` : 'blicket')) })

const groups = computed(() => manifest.value?.groups ?? [])
const tags = computed(() => {
  const all = [...groups.value.flatMap(g => g.tags), ...(manifest.value?.blicks ?? []).flatMap(b => b.definition?.tags ?? [])]
  return [...new Set(all)].toSorted()
})

const words = computed(() => search.value.toLowerCase().split(/\s+/).filter(Boolean))

function matches(entry: BlickEntry): boolean {
  const groupTags = groups.value.find(g => g.name === entry.group)?.tags ?? []
  const entryTags = [...(entry.definition?.tags ?? []), ...groupTags]
  if (chosen.value && chosen.value !== entry.group && !entryTags.includes(chosen.value)) return false
  const text = searchText(entry, groupTags)
  return words.value.every(word => text.includes(word))
}

const shown = computed(() => (manifest.value?.blicks ?? []).filter(matches))
const byName = computed(() => new Map((manifest.value?.blicks ?? []).map(b => [b.name, b])))
// The flagged Blicks with their entries; a removed Blick has none in this build.
const movers = computed(() => ranked(comparison.value?.blicks ?? []).flatMap((blick): { blick: BlickComparison, entry: BlickEntry | null }[] => {
  if (blick.change.flags.includes('removed')) {
    return !chosen.value && words.value.every(word => blick.name.toLowerCase().includes(word)) ? [{ blick, entry: null }] : []
  }
  const entry = byName.value.get(blick.name)
  return entry && matches(entry) ? [{ blick, entry }] : []
}))
const sections = computed(() => groups.value
  .map(group => ({ group, entries: shown.value.filter(b => b.group === group.name) }))
  .filter(section => section.entries.length > 0))
const errors = computed(() => (manifest.value?.problems ?? []).filter(p => p.severity === 'error'))
const warnings = computed(() => (manifest.value?.problems ?? []).filter(p => p.severity === 'warning'))
const total = computed(() => manifest.value?.blicks.length ?? 0)
const failed = computed(() => manifest.value?.blicks.filter(b => b.status === 'error').length ?? 0)
</script>

<template>
  <div v-if="manifest" class="space-y-8">
    <ComparisonBar />
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
      <UInput v-model="search" icon="i-lucide-search" placeholder="Search Blicks" class="w-full sm:max-w-sm" aria-label="Search Blicks" />
      <p class="text-sm text-muted">
        <template v-if="shown.length < total">{{ shown.length }} of </template>{{ total }} Blicks<span v-if="failed"> · {{ failed }} with errors</span><span v-if="manifest.build.incomplete"> · incomplete, a module failed to import</span>
      </p>
    </div>
    <div v-if="tags.length" class="flex flex-wrap gap-1.5">
      <UButton
        v-for="name in [...groups.map(g => g.name), ...tags]"
        :key="name"
        size="xs"
        :variant="chosen === name ? 'solid' : 'outline'"
        color="neutral"
        :label="name"
        @click="chosen = chosen === name ? null : name"
      />
    </div>
    <section v-if="movers.length">
      <h2 class="text-sm font-semibold text-highlighted">
        Changed since the baseline
      </h2>
      <div class="divide-y divide-default">
        <template v-for="{ blick, entry } in movers" :key="blick.name">
          <BlickCard v-if="entry" :entry="entry" :compared="blick" />
          <div v-else class="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-4">
            <span class="min-w-0 flex-1 font-mono text-sm text-muted">{{ blick.name }}</span>
            <span class="flex gap-1.5 sm:justify-end"><FlagBadges :change="blick.change" /></span>
          </div>
        </template>
      </div>
    </section>
    <section v-for="{ group, entries } in sections" :key="group.name">
      <h2 class="text-sm font-semibold text-highlighted">
        {{ group.title ?? group.name }}
        <span v-if="group.title" class="ml-1 font-mono text-xs font-normal text-muted">{{ group.name }}</span>
      </h2>
      <div class="divide-y divide-default">
        <BlickCard v-for="entry in entries" :key="entry.name" :entry="entry" :compared="blicks.get(entry.name) ?? null" />
      </div>
    </section>
    <p v-if="!sections.length" class="text-sm text-muted">
      No Blick matches.
    </p>
    <section v-if="errors.length || warnings.length" class="space-y-3">
      <h2 class="text-sm font-semibold text-highlighted">
        Problems with files and the project
      </h2>
      <ProblemList :problems="[...errors, ...warnings]" />
    </section>
  </div>
</template>
