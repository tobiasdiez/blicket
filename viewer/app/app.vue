<script setup lang="ts">
import { INK } from '~/plots/theme'

const { manifest, error } = useManifest()
const { open, toggle } = useSidebar()

// The page is the chart surface, so charts sit on it without a frame.
useHead({ style: [{ textContent: `:root{--ui-bg:${INK.light.surface}}.dark{--ui-bg:${INK.dark.surface}}` }] })

const repository = computed(() => manifest.value?.repository ?? null)
// The toggle's tooltip says what it does; its name stays, and `aria-expanded` says the state.
const toggleLabel = computed(() => (open.value ? 'Hide the Blick list' : 'Show the Blick list'))

/** Go past the header and the sidebar to the page. With the hash router, `#main` would be a route. */
function skip() {
  document.getElementById('main')?.focus()
}
</script>

<template>
  <UApp>
    <a href="#main" class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-default focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-primary" @click.prevent="skip">
      Skip to the page
    </a>
    <!-- The sidebar, fixed, reserves its width in this row; the page takes the rest. -->
    <div class="flex min-h-svh">
      <BlickSidebar v-if="manifest" />
      <div class="flex min-w-0 flex-1 flex-col">
        <header class="border-b border-default">
          <!-- As high as the sidebar's header, so that the two lines under them meet. -->
          <div class="mx-auto flex min-h-(--ui-header-height) w-full max-w-7xl flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3 sm:flex-nowrap sm:px-6">
            <div class="flex items-center gap-2">
              <UTooltip v-if="manifest" :text="toggleLabel">
                <UButton
                  icon="i-lucide-panel-left"
                  color="neutral"
                  variant="ghost"
                  aria-label="Blick list"
                  :aria-expanded="open"
                  aria-controls="sidebar"
                  class="-ms-1.5"
                  @click="toggle"
                />
              </UTooltip>
              <NuxtLink to="/" class="font-semibold text-highlighted">
                blicket
              </NuxtLink>
            </div>
            <UColorModeButton class="ml-auto shrink-0 sm:order-last" />
            <!-- Its own full-width row on a narrow page, so nothing is cut off. -->
            <dl v-if="manifest" class="order-last flex w-full min-w-0 flex-wrap gap-x-4 text-sm text-muted sm:order-none sm:w-auto">
              <div class="flex min-w-0 gap-1">
                <dt class="whitespace-nowrap">
                  run
                </dt>
                <dd class="break-all text-default">
                  {{ manifest.run.id }}
                </dd>
              </div>
              <div class="flex gap-1">
                <dt class="whitespace-nowrap">
                  profile
                </dt>
                <dd class="text-default">
                  {{ manifest.run.profile }}
                </dd>
              </div>
              <div v-if="repository" class="flex gap-1">
                <dt class="whitespace-nowrap">
                  Blick code
                </dt>
                <dd class="text-default" :title="repository.commit">
                  <span class="font-mono">{{ repository.commit.slice(0, 7) }}</span>
                  <span v-if="repository.dirty" class="whitespace-nowrap"> · uncommitted changes</span>
                </dd>
              </div>
            </dl>
          </div>
        </header>
        <main id="main" tabindex="-1" class="mx-auto w-full max-w-7xl flex-1 px-4 py-6 focus:outline-none sm:px-6">
          <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" title="The build cannot be shown" :description="error" />
          <NuxtPage v-else-if="manifest" />
          <p v-else class="text-sm text-muted">
            Loading the build…
          </p>
        </main>
        <footer v-if="manifest" class="mx-auto w-full max-w-7xl px-4 pb-8 text-xs text-muted sm:px-6">
          blicket {{ manifest.blicket }} · build {{ manifest.build.id }} · {{ manifest.created_at.slice(0, 16).replace('T', ' ') }} UTC
        </footer>
      </div>
    </div>
  </UApp>
</template>
