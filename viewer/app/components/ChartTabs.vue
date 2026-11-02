<script setup lang="ts">
// The tabs of a chart and its rows, on a Blick's page and in the builder; the tab shown is in
// the URL (useTab).
const tab = defineModel<string>({ required: true })

const tabs = [
  { label: 'Chart', value: 'chart', icon: 'i-lucide-chart-line' },
  { label: 'Data', value: 'data', icon: 'i-lucide-table' },
]
</script>

<template>
  <UTabs v-model="tab" :items="tabs" variant="link" :content="false" class="w-full" />
</template>
