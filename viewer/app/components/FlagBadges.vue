<script setup lang="ts">
import { badges, type Change, type Flag } from '~/lib/comparison'

defineProps<{ change: Change }>()

const COLORS: Record<Flag, 'warning' | 'info' | 'neutral' | 'error'> = { value: 'warning', schema: 'warning', new: 'info', removed: 'neutral', error: 'error' }
</script>

<template>
  <UBadge v-for="badge in badges(change)" :key="badge.flag" :color="COLORS[badge.flag]" variant="subtle" :label="badge.label" :title="badge.title" />
</template>
