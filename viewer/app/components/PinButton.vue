<script setup lang="ts">
// Pins a Blick to the overview, or unpins it: on its page with a label that says which, and on a
// card of the overview as an icon. `label` is the Blick's title; `toggle` follows a click.
const props = defineProps<{ id: string, label: string, icon?: boolean }>()
const emit = defineEmits<{ toggle: [] }>()

const { isPinned, toggle } = usePins()
const pinned = computed(() => isPinned(props.id))

function flip() {
  toggle(props.id)
  emit('toggle')
}
</script>

<template>
  <UTooltip v-if="icon" :text="pinned ? 'Unpin' : 'Pin to overview'">
    <UButton
      :icon="pinned ? 'i-lucide-pin-off' : 'i-lucide-pin'"
      color="neutral"
      variant="ghost"
      size="sm"
      :aria-label="pinned ? `Unpin ${label}` : `Pin ${label} to the overview`"
      @click="flip"
    />
  </UTooltip>
  <UButton
    v-else
    icon="i-lucide-pin"
    color="neutral"
    :variant="pinned ? 'soft' : 'outline'"
    size="sm"
    :label="pinned ? 'Pinned' : 'Pin to overview'"
    :aria-pressed="pinned"
    @click="flip"
  />
</template>
