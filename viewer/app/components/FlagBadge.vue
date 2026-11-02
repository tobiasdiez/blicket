<script setup lang="ts">
import { FLAG_COLORS, type Badge } from '~/lib/comparison'

// A flag's badge. `inline` is for a badge inside a Blick's link, which reads it as words after a
// comma, `Production by source, changed by 2.1% of scale`, rather than as its short label.
defineProps<{ badge: Badge, size?: 'sm' | 'md', inline?: boolean }>()
</script>

<template>
  <span class="inline-flex shrink-0">
    <UBadge :color="FLAG_COLORS[badge.flag]" variant="subtle" :size="size" :label="badge.label" :title="badge.title" :aria-hidden="inline || undefined" />
    <span v-if="inline" class="sr-only">, {{ badge.spoken }}</span>
  </span>
</template>
