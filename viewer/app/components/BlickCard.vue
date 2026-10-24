<script setup lang="ts">
import type { BlickEntry } from '~/lib/manifest'
import { roles } from '~/lib/roles'

const props = defineProps<{ entry: BlickEntry }>()

const summary = computed(() => props.entry.definition?.description?.split(/(?<=[.!?])\s/)[0] ?? '')
</script>

<template>
  <div class="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-4">
    <div class="min-w-0 flex-1">
      <NuxtLink v-if="entry.id && entry.status === 'ok'" :to="`/blick/${entry.id}`" class="font-medium text-highlighted hover:underline">
        {{ entry.definition?.title ?? entry.name }}
      </NuxtLink>
      <span v-else class="font-medium text-highlighted">{{ entry.definition?.title ?? entry.name }}</span>
      <span class="ml-2 font-mono text-xs text-muted">{{ entry.name }}</span>
      <p v-if="summary" class="text-sm text-muted">
        {{ summary }}
      </p>
      <ProblemList v-if="entry.status === 'error'" :problems="entry.problems" class="mt-2" />
    </div>
    <div class="flex flex-wrap gap-1.5 sm:justify-end">
      <UBadge v-if="entry.status === 'error'" color="error" variant="subtle" label="error" />
      <UBadge v-if="entry.definition" color="neutral" variant="outline" :label="entry.definition.plot.type" />
      <UBadge v-for="role in roles(entry)" :key="role" color="neutral" variant="soft" :label="role" />
    </div>
  </div>
</template>
