<script setup lang="ts">
import { sourceText, type Problem } from '~/lib/manifest'

defineProps<{ problems: Problem[] }>()
</script>

<template>
  <ul class="space-y-2">
    <li v-for="(problem, i) in problems" :key="i" class="flex gap-2 text-sm">
      <UIcon
        :name="problem.severity === 'error' ? 'i-lucide-circle-x' : 'i-lucide-triangle-alert'"
        :class="problem.severity === 'error' ? 'text-error' : 'text-warning'"
        class="mt-0.5 size-4 shrink-0"
      />
      <div class="min-w-0">
        <p class="text-muted">
          <span class="font-medium text-default">{{ problem.severity === 'error' ? 'Error' : 'Warning' }}</span>
          · {{ problem.kind.replaceAll('_', ' ') }}
          <span v-if="problem.source" class="font-mono"> · {{ sourceText(problem.source) }}</span>
        </p>
        <p class="whitespace-pre-wrap break-words">{{ problem.message }}</p>
      </div>
    </li>
  </ul>
</template>
