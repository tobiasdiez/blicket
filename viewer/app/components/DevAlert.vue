<script setup lang="ts">
// A request to blicket dev that failed, with Retry: a server that does not answer, or one that
// answered with an error. Retry stays focusable while it runs, shows that it runs for at least
// the time a click needs to be seen, and a retry that fails again says when.
const props = defineProps<{
  /** The title when the server answered with an error. */
  title: string
  message: string
  unreachable: boolean
  /** How many requests in a row failed, and when the last did. */
  failures: number
  failedAt: Date | null
  busy: boolean
  /** Announce the alert on its own, outside a live region of the page. */
  announce?: boolean
}>()
const emit = defineEmits<{ retry: [] }>()

const HOLD = 300 // ms
const holding = ref(false)
const working = computed(() => props.busy || holding.value)
const again = computed(() => {
  if (props.failures < 2 || !props.failedAt) return ''
  const at = props.failedAt.toLocaleTimeString('en-GB')
  return props.unreachable ? `Still no answer at ${at}.` : `Failed again at ${at}.`
})

function retry() {
  if (working.value) return
  holding.value = true
  setTimeout(() => {
    holding.value = false
  }, HOLD)
  emit('retry')
}
</script>

<template>
  <UAlert
    color="error"
    variant="subtle"
    :icon="unreachable ? 'i-lucide-unplug' : 'i-lucide-circle-alert'"
    :title="unreachable ? 'Cannot reach blicket dev' : title"
    :role="announce ? 'alert' : undefined"
    :ui="{ description: 'wrap-anywhere' }"
  >
    <template #description>
      <p>{{ message }}</p>
      <p v-if="again">
        {{ again }}
      </p>
    </template>
    <template #actions>
      <UButton
        size="xs"
        color="neutral"
        variant="outline"
        label="Retry"
        :icon="working ? 'i-lucide-loader-circle' : 'i-lucide-rotate-cw'"
        :aria-busy="working"
        :ui="{ leadingIcon: working ? 'animate-spin' : '' }"
        @click="retry"
      />
    </template>
  </UAlert>
</template>
