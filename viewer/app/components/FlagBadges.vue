<script setup lang="ts">
import { badges, type Change } from '~/lib/comparison'

defineProps<{ change: Change }>()
</script>

<template>
  <FlagBadge v-for="badge in badges(change)" :key="badge.flag" :badge="badge" />
</template>
