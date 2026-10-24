<script setup lang="ts">
import { INK } from '~/plots/theme'

const { manifest, error } = useManifest()

// The page is the chart surface, so charts sit on it without a frame.
useHead({ style: [{ textContent: `:root{--ui-bg:${INK.light.surface}}.dark{--ui-bg:${INK.dark.surface}}` }] })

const repository = computed(() => manifest.value?.repository ?? null)
</script>

<template>
  <UApp>
    <header class="border-b border-default">
      <div class="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3 sm:flex-nowrap sm:px-6">
        <NuxtLink to="/" class="font-semibold text-highlighted">
          blicket
        </NuxtLink>
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
    <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" title="The build cannot be shown" :description="error" />
      <NuxtPage v-else-if="manifest" />
      <p v-else class="text-sm text-muted">
        Loading the build…
      </p>
    </main>
    <footer v-if="manifest" class="mx-auto max-w-7xl px-4 pb-8 text-xs text-muted sm:px-6">
      blicket {{ manifest.blicket }} · build {{ manifest.build.id }} · {{ manifest.created_at.slice(0, 16).replace('T', ' ') }} UTC
    </footer>
  </UApp>
</template>
