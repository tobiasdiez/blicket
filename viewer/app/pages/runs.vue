<script setup lang="ts">
import { failure, postRun } from '~/lib/dev'
import { ago, keepListed, loadLabel, namesOf, runsSetting } from '~/lib/runs'
import { utcTime } from '~/lib/time'

const { manifest, dev, noRun } = useManifest()
const { info } = useDev()
const listing = useRuns()
const { runs } = listing

useHead({ title: 'Pick a run · blicket' })

// The paths ticked, whether they load, and the load that failed: the names of its runs, and why.
const picked = ref<string[]>([])
const loading = ref(false)
const failed = ref<{ names: string, message: string, unreachable: boolean } | null>(null)
const failureAlert = useTemplateRef<HTMLElement>('failureAlert')

// The rows, the times said relative to when the list came.
const rows = computed(() => {
  const now = new Date()
  return (runs.value?.runs ?? []).map(run => ({ ...run, ago: ago(run.modified, now), exact: utcTime(run.modified, true) }))
})
// A load that could not reach blicket dev says nothing the list's alert does not say already.
const failureShown = computed(() => failed.value !== null && !(failed.value.unreachable && listing.error.value !== null && listing.unreachable.value))
const names = computed(() => namesOf(picked.value, runs.value?.runs ?? []))
const overview = [{ label: 'Go to the overview', to: '/', color: 'neutral' as const, variant: 'outline' as const, size: 'xs' as const }]

watch(runs, (list) => {
  if (list) picked.value = keepListed(picked.value, list.runs)
})
// A failure is about the ticks it was loaded with.
watch(picked, () => {
  failed.value = null
})

function tick(path: string, on: boolean | 'indeterminate') {
  picked.value = on === true ? [...picked.value, path] : picked.value.filter(other => other !== path)
}

function refresh() {
  failed.value = null
  void listing.reload()
}

/**
 * Load the runs ticked as one run. Once `blicket dev` serves it, the viewer starts afresh on the
 * overview, since it reads the manifest once; a load that fails leaves the ticks as they are and
 * says why under the list, the keyboard staying on Load.
 */
async function load() {
  if (!picked.value.length || loading.value) return
  loading.value = true
  failed.value = null
  try {
    await postRun([...picked.value])
    location.replace('./#/')
    location.reload()
  }
  catch (cause) {
    failed.value = { names: names.value, ...failure(cause) }
    loading.value = false
    await nextTick()
    failureAlert.value?.scrollIntoView({ block: 'nearest' })
  }
}
</script>

<template>
  <div class="max-w-3xl space-y-5">
    <h1 class="text-xl font-semibold text-highlighted">
      Pick a run
    </h1>
    <UAlert v-if="!noRun && manifest && dev" color="neutral" variant="subtle" icon="i-lucide-info" title="A run is loaded" :actions="overview">
      <template #description>
        <code>blicket dev</code> serves the run {{ manifest.run.id }}. To pick another, stop <code>blicket dev</code> and start it again without a run.
      </template>
    </UAlert>
    <UAlert v-else-if="!noRun" color="neutral" variant="subtle" icon="i-lucide-info" title="The run picker needs blicket dev" :actions="overview">
      <template #description>
        It lists the runs of a project when <code>blicket dev</code> starts without one, and this build is served without it.
      </template>
    </UAlert>
    <template v-else>
      <p v-if="runs?.runs.length" class="text-sm text-muted">
        Folders that <code>{{ runsSetting(runs.patterns) }}</code> matches, newest first.
      </p>
      <DevAlert
        v-if="listing.error.value !== null"
        title="The runs could not be listed"
        :message="listing.error.value"
        :unreachable="listing.unreachable.value"
        :failures="listing.failures.value"
        :failed-at="listing.failedAt.value"
        :busy="listing.loading.value"
        announce
        @retry="refresh"
      />
      <p v-if="!runs && listing.error.value === null" class="text-sm text-muted">
        Looking for runs…
      </p>
      <template v-if="runs">
        <p v-if="!runs.runs.length" class="text-sm text-muted">
          No folder matches <code>{{ runsSetting(runs.patterns) }}</code> yet. The globs are relative to the project root<template v-if="info">, <code class="wrap-anywhere">{{ info.root }}</code></template>.
        </p>
        <fieldset v-else class="space-y-2">
          <legend class="sr-only">
            Runs
          </legend>
          <ul class="divide-y divide-default overflow-hidden rounded-lg border border-default">
            <li v-for="(run, index) in rows" :key="run.path" :title="run.path">
              <UCheckbox
                :model-value="picked.includes(run.path)"
                :disabled="loading"
                variant="card"
                :aria-describedby="`run-time-${index}`"
                :ui="{
                  root: 'rounded-none border-0 has-data-[state=checked]:bg-primary/10',
                  wrapper: 'flex min-w-0 flex-col gap-x-4 sm:flex-row sm:items-baseline sm:justify-between',
                  label: 'wrap-anywhere',
                  description: 'shrink-0 whitespace-nowrap text-sm',
                }"
                @update:model-value="(on: boolean | 'indeterminate') => tick(run.path, on)"
              >
                <template #label>
                  {{ run.name }}
                </template>
                <template #description>
                  <time :id="`run-time-${index}`" :datetime="run.modified" :title="run.exact">{{ run.ago }}</time>
                </template>
              </UCheckbox>
            </li>
          </ul>
          <p id="load-hint" class="text-sm text-muted">
            Tick a folder to load it, or several to load them as one run.
          </p>
        </fieldset>
        <div class="flex items-center justify-between gap-3">
          <UButton
            v-if="runs.runs.length"
            :label="loadLabel(picked.length)"
            :icon="loading ? 'i-lucide-loader-circle' : undefined"
            :color="picked.length ? 'primary' : 'neutral'"
            :variant="picked.length ? 'solid' : 'subtle'"
            :disabled="!picked.length"
            :aria-busy="loading"
            aria-describedby="load-hint"
            :ui="{ leadingIcon: loading ? 'animate-spin' : '' }"
            @click="load"
          />
          <UButton
            label="Refresh"
            color="neutral"
            variant="outline"
            :icon="listing.loading.value ? 'i-lucide-loader-circle' : 'i-lucide-refresh-cw'"
            :ui="{ leadingIcon: listing.loading.value ? 'animate-spin' : '' }"
            :disabled="loading"
            :aria-busy="listing.loading.value"
            @click="refresh"
          />
        </div>
        <div aria-live="polite">
          <p v-if="loading" class="text-sm text-muted wrap-anywhere">
            Loading {{ names }}; the loader's output goes to the terminal.
          </p>
        </div>
        <div v-if="failed && failureShown" ref="failureAlert" class="scroll-mb-4">
          <UAlert
            color="error"
            variant="subtle"
            :icon="failed.unreachable ? 'i-lucide-unplug' : 'i-lucide-triangle-alert'"
            :title="failed.unreachable ? 'Cannot reach blicket dev' : `${failed.names} cannot be loaded`"
            :description="failed.message"
            role="alert"
            :ui="{ title: 'wrap-anywhere', description: 'whitespace-pre-wrap wrap-anywhere' }"
          />
        </div>
      </template>
    </template>
  </div>
</template>
