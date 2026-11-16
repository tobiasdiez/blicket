<script setup lang="ts">
import { hasExpectation } from '~/lib/expectations'
import { sourceText, unitPath, type UnitEntry } from '~/lib/manifest'

// The frame of a Blick's page and a check's: the breadcrumb, the title with the `actions`, the
// description, a meta line (the name, the `meta` of the kind, the rows, the Parquet file, the
// `files` of the kind, the level where there is an expectation and it is not error, where the
// unit is defined), the `strips`, then the problems of a unit in error, or the warnings of one
// that is not and the reason of a skipped one or the default slot. An id the build has a unit of
// the other kind of opens that unit's page instead, with the same query; one it has nothing of
// says so.
const props = defineProps<{ kind: 'Blick' | 'check', id: string, entry: UnitEntry | null }>()

const router = useRouter()
const route = useRoute()
const { manifest } = useManifest()

const group = computed(() => manifest.value?.groups.find(g => g.name === props.entry?.group) ?? null)
const title = computed(() => props.entry?.definition?.title ?? props.entry?.name ?? props.id)
const rows = computed(() => {
  const count = props.entry?.rows
  return count === null || count === undefined ? null : `${count.toLocaleString('en')} ${count === 1 ? 'row' : 'rows'}`
})
const level = computed(() => (props.entry && hasExpectation(props.entry) && props.entry.level && props.entry.level !== 'error' ? props.entry.level : null))
const source = computed(() => (props.entry?.source ? sourceText(props.entry.source) : null))
const warnings = computed(() => props.entry?.problems.filter(p => p.severity === 'warning') ?? [])
// A unit of the other kind with the id the route names, whose page the route meant.
const other = computed(() => {
  if (props.entry || !props.id || !manifest.value) return null
  const list = props.kind === 'Blick' ? manifest.value.checks : manifest.value.blicks
  const found = list.find(unit => unit.id === props.id)
  return found ? unitPath(found) : null
})
watch(other, (path) => {
  if (path) void router.replace({ path, query: route.query })
}, { immediate: true })

useHead({ title: computed(() => `${title.value} · blicket`) })

// The overview is the one page above a unit; the group is a label, not a page. On a narrow page
// the title, which the heading repeats, makes room for the group.
const breadcrumb = computed(() => [
  { label: 'Overview', to: '/' },
  { label: group.value?.title ?? props.entry?.group ?? '', ui: { separator: 'max-sm:hidden' } },
  { label: title.value, ui: { item: 'max-sm:hidden' } },
])
</script>

<template>
  <div v-if="!entry" class="space-y-3">
    <h1 class="text-lg font-semibold text-highlighted">
      No such {{ kind }} in this build
    </h1>
    <p class="text-sm text-muted">
      <template v-if="id">
        This build has no {{ kind }} <code class="break-all">{{ id }}</code>.
      </template>
      <template v-else>
        The address names no {{ kind }}.
      </template>
    </p>
    <UButton to="/" icon="i-lucide-arrow-left" variant="outline" color="neutral" label="Overview" />
  </div>
  <div v-else class="space-y-5">
    <div class="space-y-1">
      <UBreadcrumb :items="breadcrumb" />
      <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <h1 class="min-w-0 text-xl font-semibold text-highlighted">
          {{ title }}
        </h1>
        <slot name="actions" />
      </div>
      <p v-if="entry.definition?.description" class="max-w-3xl text-sm text-muted">
        {{ entry.definition.description }}
      </p>
      <p class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span class="font-mono break-all">{{ entry.name }}</span>
        <slot name="meta" />
        <span v-if="rows">{{ rows }}</span>
        <a v-if="entry.data" :href="`./${entry.data}`" download class="underline hover:text-default">Parquet file</a>
        <slot name="files" />
        <span v-if="level">level: {{ level }}</span>
        <span v-if="source">defined at <span class="font-mono">{{ source }}</span></span>
      </p>
    </div>
    <slot name="strips" />
    <ProblemList v-if="entry.status === 'error'" :problems="entry.problems" />
    <template v-else>
      <ProblemList v-if="warnings.length" :problems="warnings" />
      <UAlert v-if="entry.status === 'skipped'" color="neutral" variant="subtle" icon="i-lucide-circle-slash" title="Skipped for this run" :description="entry.skipped ?? undefined" :ui="{ description: 'whitespace-pre-wrap wrap-anywhere' }" />
      <slot v-else />
    </template>
  </div>
</template>
