<script setup lang="ts">
import { RESULT_COLORS, type ExpectationBadge } from '~/lib/expectations'

// The badge of an expectation's outcome that is not met: `failed`, `error` or `warning`, outlined
// and with an icon, so that it stands apart from a flag's filled badge beside it; `wide` where
// there is room says what it is about, `expectation failed`. A screen reader reads its words
// after a comma, `Production by source, expectation failed`.
defineProps<{ badge: ExpectationBadge, size?: 'sm' | 'md', wide?: boolean }>()
</script>

<template>
  <span class="inline-flex shrink-0">
    <UBadge :color="RESULT_COLORS[badge.result]" variant="outline" :size="size" icon="i-lucide-list-checks" :label="wide ? badge.wide : badge.label" :title="badge.title" aria-hidden="true" />
    <span class="sr-only">, {{ badge.spoken }}</span>
  </span>
</template>
