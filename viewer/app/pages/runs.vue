<script setup lang="ts">
import { failure, postRun } from '~/lib/dev'
import { loadingLine } from '~/lib/jobs'
import { dropQuestion, expensiveBuilt, keepListed, loadLabel, namesOf, runsSetting, ticked, whenText } from '~/lib/runs'
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
// Whether the question before a load that drops expensive Blicks built is open, and whether the
// alert of a load that failed takes the keyboard once it has closed.
const asking = ref(false)
let focusFailure = false

// The rows, the times said relative to when the list came.
const rows = computed(() => {
  const now = new Date()
  return (runs.value?.runs ?? []).map(run => ({
    ...run,
    when: whenText(run, now),
    exact: run.modified === null ? undefined : utcTime(run.modified, true),
  }))
})
// A load that could not reach blicket dev says nothing the list's alert does not say already.
const failureShown = computed(() => failed.value !== null && !(failed.value.unreachable && listing.error.value !== null && listing.unreachable.value))
const names = computed(() => namesOf(picked.value, runs.value?.runs ?? []))
// While the load runs: the cheap Blick it waits for, if one builds, then that the run loads.
const { jobs, later, title } = useJobs()
const loadingNow = computed(() => loadingLine(names.value, jobs.value, later.value, title))
const dropped = computed(() => (noRun.value ? 0 : expensiveBuilt(manifest.value?.blicks ?? [])))
const overview = [{ label: 'Go to the overview', to: '/', color: 'neutral' as const, variant: 'outline' as const, size: 'xs' as const }]
// Whether a run is served, which the page can go back to.
const serving = computed(() => !noRun.value && !!manifest.value)

watch(runs, (list) => {
  if (list) picked.value = keepListed(picked.value, list.runs)
})
// A failure is about the ticks it was loaded with.
watch(picked, () => {
  failed.value = null
})

function tick(path: string, on: boolean | 'indeterminate') {
  picked.value = ticked(picked.value, path, on === true, runs.value?.runs ?? [])
}

function refresh() {
  failed.value = null
  void listing.reload()
}

/** Load the runs ticked, after asking when the load drops expensive Blicks built. */
function press() {
  if (!picked.value.length || loading.value) return
  if (dropped.value) asking.value = true
  else void load()
}

/**
 * Load the runs ticked as one run, in place of the run served, if any, the question closing on
 * blicket dev's answer. Once `blicket dev` serves the run, the viewer starts afresh on the
 * overview, since the session is another; a load that fails leaves the ticks and the run served
 * as they are and says why under the list: the keyboard goes to that alert when the question was
 * asked, once the question has closed, and otherwise stays on Load.
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
    focusFailure = asking.value
    asking.value = false
    await nextTick()
    failureAlert.value?.scrollIntoView({ block: 'nearest' })
  }
}

/**
 * As the question closes, give the keyboard to the alert of the load that failed, where it would
 * go back to Load.
 */
function closeFocus(event: Event) {
  if (!focusFailure) return
  focusFailure = false
  event.preventDefault()
  failureAlert.value?.focus()
}
</script>

<template>
  <div class="max-w-3xl space-y-5">
    <h1 class="text-xl font-semibold text-highlighted">
      Pick a run
    </h1>
    <UAlert v-if="!noRun && !dev" color="neutral" variant="subtle" icon="i-lucide-info" title="The run picker needs blicket dev" :actions="overview">
      <template #description>
        It lists the runs of a project when <code>blicket dev</code> serves it, and this build is served without it.
      </template>
    </UAlert>
    <template v-else>
      <p v-if="runs?.runs.length" class="text-sm text-muted">
        <template v-if="runs.runs[0]?.project">The project itself, computed from its code, then the folders</template><template v-else>Folders</template> that <code>{{ runsSetting(runs.patterns) }}</code> matches, newest first.
        <template v-if="manifest && !noRun">
          The run served, {{ manifest.run.id }}, is marked; loading another replaces it.
        </template>
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
        <p v-if="!runs.patterns.length" class="text-sm text-muted">
          This project sets no <code>runs</code> in <code>[tool.blicket]</code>, so there is nothing to pick; <code>runs = ["output/*"]</code> lists run folders, <code>"."</code> the project itself.
        </p>
        <p v-else-if="!runs.runs.length" class="text-sm text-muted">
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
                  <UBadge v-if="run.served" color="neutral" variant="subtle" size="sm" label="served" class="ms-2 align-middle" />
                </template>
                <template #description>
                  <span :id="`run-time-${index}`">
                    <span v-if="run.project">{{ run.when }}</span>
                    <time v-else :datetime="run.modified ?? undefined" :title="run.exact">{{ run.when }}</time>
                  </span>
                </template>
              </UCheckbox>
            </li>
          </ul>
          <p id="load-hint" class="text-sm text-muted">
            Tick a folder to load it, or several to load them as one run<template v-if="runs.runs[0]?.project">; the project itself loads alone</template>.
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
            @click="press"
          />
          <div class="flex flex-wrap items-center justify-end gap-2">
            <UButton v-if="serving" to="/" label="Back to the overview" icon="i-lucide-arrow-left" color="neutral" variant="ghost" />
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
        </div>
        <div aria-live="polite">
          <p v-if="loading" class="text-sm text-muted wrap-anywhere">
            {{ loadingNow.text }}<span v-if="loadingNow.time" aria-hidden="true" class="tabular-nums">{{ ` ${loadingNow.time}` }}</span>
          </p>
        </div>
        <div v-if="failed && failureShown" ref="failureAlert" tabindex="-1" class="scroll-mb-4 focus:outline-none">
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
    <!-- Without a transition, so that it is gone the moment blicket dev answers: its closing
         animation would wait for a frame of a page that may not be drawn. -->
    <UModal v-model:open="asking" title="Load another run?" :description="dropQuestion(dropped)" :dismissible="!loading" :transition="false" :content="{ onCloseAutoFocus: closeFocus }">
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton label="Cancel" color="neutral" variant="outline" :disabled="loading" @click="asking = false" />
          <UButton
            label="Load"
            :icon="loading ? 'i-lucide-loader-circle' : undefined"
            :aria-busy="loading"
            :ui="{ leadingIcon: loading ? 'animate-spin' : '' }"
            @click="load"
          />
        </div>
      </template>
    </UModal>
  </div>
</template>
