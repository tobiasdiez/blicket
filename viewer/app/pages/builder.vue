<script setup lang="ts">
import type { SelectMenuItem } from '@nuxt/ui'
import {
  SUM,
  formDimensions,
  joinable,
  keptValues,
  mergeBuilder,
  mergeControls,
  notices,
  parseBuilder,
  pick,
  request,
  requiredHint,
  roleItem,
  roleOf,
  rolesFor,
  setOnly,
  setPlot,
  setRange,
  setRole,
  subtitleParts,
  type BuilderOptions,
  type BuilderState,
  type FormDimension,
  type Quantity,
} from '~/lib/builder'
import { queryFromState, stateFromQuery, type ControlState } from '~/lib/controls'
import { downloadCsv } from '~/lib/csv'
import { select } from '~/lib/select'

const PLOT_LABELS: Record<string, string> = { line: 'Line', stacked_area: 'Stacked area', bar: 'Bar', stacked_bar: 'Stacked bar', sankey: 'Sankey' }

const route = useRoute()
const router = useRouter()
const devInfo = useDev()
const { dev, info } = devInfo
const dataset = useDataset()
const { options } = dataset

const state = computed(() => parseBuilder(route.query))
const body = computed(() => (options.value ? request(state.value, options.value) : null))
const { entry, rows, shown: answered, failed, error, unreachable, failures, failedAt, pending, slow, stale, retry } = useQuery(body)

// The request of the page's own that failed, `dev/info` or `dev/dataset`, if one did.
const pageFailure = computed(() => {
  if (devInfo.error.value !== null) return devInfo
  return info.value?.dataset && dataset.error.value !== null ? dataset : null
})

const tab = useTab()

const definition = computed(() => entry.value?.definition ?? null)
const schema = computed(() => entry.value?.columns ?? null)
const controls = computed(() => entry.value?.controls ?? [])
const parsed = computed(() => (schema.value ? stateFromQuery(controls.value, schema.value, route.query) : null))
const controlState = computed(() => parsed.value?.state ?? null)
const shownRows = computed(() => (rows.value && schema.value && controlState.value ? select(rows.value, schema.value, controlState.value.filters) : null))
// The warnings of the entry shown; an empty table says so once, below the tabs.
const warnings = computed(() => entry.value?.problems.filter(p => p.severity === 'warning' && !(entry.value?.rows === 0 && p.kind === 'table')) ?? [])
// What the URL asks for that is not there: values the dataset or the table lacks.
const urlNotices = computed(() => [...(options.value ? notices(state.value, options.value) : []), ...(parsed.value?.notices ?? [])])
const chartProps = computed(() => chartPropsOf(definition.value, schema.value, shownRows.value, controlState.value, null))
// What the chart shown was summed over and which values it keeps, as its subtitle.
const subtitle = computed(() => (answered.value && options.value ? subtitleParts(answered.value, options.value).join(' · ') : ''))

const quantities = computed(() => new Map((options.value?.quantities ?? []).map(q => [q.name, q])))
const titles = computed(() => state.value.quantities.map(name => quantities.value.get(name)?.title ?? name))
useHead({ title: computed(() => [...(titles.value.length ? [titles.value.join(', ')] : []), 'Build a Blick', 'blicket'].join(' · ')) })
const fileName = computed(() => `builder__${titles.value.join('_').replaceAll(/[^\w.-]+/g, '-').slice(0, 80) || 'blick'}`)

/** Put the builder's state `next` into the URL; with `reset`, the controls start afresh. */
function change(next: BuilderState, reset = false) {
  void router.replace({ query: mergeBuilder(route.query, state.value, next, reset) })
}

/** Put the control state into the URL; the query stays as it is. */
function updateControls(next: ControlState) {
  if (schema.value) void router.replace({ query: mergeControls(route.query, queryFromState(schema.value, next)) })
}

// The quantity list, grouped as the dataset groups them and searched by title, group and name; a
// quantity that cannot join the ones picked is disabled, and says why.
const quantityItems = computed<SelectMenuItem[][]>(() => {
  if (!options.value) return []
  const groups = new Map<string, Quantity[]>()
  for (const quantity of options.value.quantities) {
    const group = quantity.group ?? ''
    groups.set(group, [...(groups.get(group) ?? []), quantity])
  }
  const reason = joinable(state.value, options.value)
  return [...groups].map(([group, members]) => [
    ...(group ? [{ type: 'label' as const, label: group }] : []),
    ...members.map((quantity) => {
      const why = reason(quantity)
      const parts = [quantity.unit ?? 'unit unknown', quantity.dimensions.join(', '), ...(why ? [`can't join: ${why}`] : [])]
      return { label: quantity.title, description: parts.join(' · '), value: quantity.name, group, disabled: why !== null }
    }),
  ])
})
// The counts per group, for the empty page.
const groupCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const quantity of options.value?.quantities ?? []) counts.set(quantity.group ?? 'other', (counts.get(quantity.group ?? 'other') ?? 0) + 1)
  return [...counts].map(([group, count]) => `${group} (${count})`).join(', ')
})
// Picking is mostly picking one, so the list closes on a pick.
const pickerOpen = ref(false)

function onPick(names: unknown) {
  pickerOpen.value = false
  if (!options.value) return
  const picks = Array.isArray(names) ? names.filter((name): name is string => typeof name === 'string') : []
  const next = pick(state.value, options.value, picks)
  change(next.state, next.reset)
}

const plotItems = computed(() => (options.value?.plots ?? []).map(p => ({ label: PLOT_LABELS[p.name] ?? p.name, value: p.name })))
const rowsOfForm = computed(() => (options.value ? formDimensions(state.value, options.value) : []))
// The form's helpers, given the options the form is shown for.
const roleItems = (offered: BuilderOptions, row: FormDimension) => rolesFor(state.value, offered, row).map(role => roleItem(role, row.dimension.name))
const hint = (offered: BuilderOptions, row: FormDimension) => requiredHint(state.value, offered, row.dimension.name)
// The first problem of a refused query, shown under the quantity too on a narrow page, where
// the chart comes after the form.
const firstProblem = computed(() => failed.value?.problems.find(p => p.severity === 'error')?.message ?? null)
const capitalized = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

function onPlot(plot: string) {
  if (options.value) change(setPlot(state.value, options.value, plot))
}

function onRole(dimension: string, role: string) {
  if (options.value) change(setRole(state.value, options.value, dimension, role))
}

function saveCsv() {
  if (shownRows.value && schema.value && definition.value) downloadCsv(shownRows.value, schema.value, definition.value.unit, definition.value.plot.mapping, fileName.value)
}

const breadcrumb = [{ label: 'Overview', to: '/' }, { label: 'Build a Blick' }]
</script>

<template>
  <div class="space-y-5">
    <div class="space-y-1">
      <UBreadcrumb :items="breadcrumb" />
      <h1 class="text-xl font-semibold text-highlighted">
        Build a Blick
      </h1>
    </div>
    <UAlert v-if="!dev" color="neutral" variant="subtle" icon="i-lucide-info" title="The Blick builder needs blicket dev">
      <template #description>
        It charts the quantities of a run that <code>blicket dev</code> keeps in memory, and this build is served without it.
        Start <code>blicket dev</code> on a run of the project and open the viewer it names.
      </template>
    </UAlert>
    <DevAlert
      v-else-if="pageFailure"
      :title="pageFailure === dataset ? 'The dataset could not be loaded' : 'The dev session could not be read'"
      :message="pageFailure.error.value ?? ''"
      :unreachable="pageFailure.unreachable.value"
      :failures="pageFailure.failures.value"
      :failed-at="pageFailure.failedAt.value"
      :busy="pageFailure.loading.value"
      announce
      @retry="pageFailure.reload()"
    />
    <UAlert v-else-if="info && !info.dataset && info.failed" color="warning" variant="subtle" icon="i-lucide-triangle-alert" title="The dataset of this project failed" :ui="{ description: 'whitespace-pre-wrap wrap-anywhere' }">
      <template #description>{{ info.message }}. Fix it and restart <code>blicket dev</code>.</template>
    </UAlert>
    <UAlert v-else-if="info && !info.dataset" color="neutral" variant="subtle" icon="i-lucide-info" title="This project has no dataset" :description="`${capitalized(info.message ?? 'no dataset(run)')}.`" />
    <p v-else-if="!options" class="text-sm text-muted">
      Loading the dataset…
    </p>
    <div v-else class="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <form class="space-y-5" aria-label="The Blick" @submit.prevent>
        <div class="space-y-1.5">
          <label for="quantities" class="text-sm font-medium text-highlighted">Quantity</label>
          <USelectMenu
            id="quantities"
            v-model:open="pickerOpen"
            :model-value="state.quantities"
            :items="quantityItems"
            value-key="value"
            multiple
            :filter-fields="['label', 'group', 'value']"
            class="w-full"
            :content="{ align: 'start' }"
            :ui="{ content: 'min-w-[min(32rem,calc(100vw-2rem))] max-h-[min(60vh,var(--reka-combobox-content-available-height,60vh))]', itemLabel: 'whitespace-normal wrap-anywhere', itemDescription: 'whitespace-normal wrap-anywhere' }"
            @update:model-value="onPick"
          >
            <span class="truncate text-muted">{{ state.quantities.length ? 'Add a quantity' : 'Pick a quantity' }}</span>
            <template #empty>
              No quantity matches
            </template>
          </USelectMenu>
          <div v-if="state.quantities.length" class="flex flex-wrap gap-1.5">
            <UButton
              v-for="(name, index) in state.quantities"
              :key="name"
              size="xs"
              color="neutral"
              variant="soft"
              trailing-icon="i-lucide-x"
              :label="titles[index]"
              :aria-label="`Remove ${titles[index]}`"
              class="max-w-full"
              :ui="{ label: 'whitespace-normal text-left wrap-anywhere' }"
              @click="onPick(state.quantities.filter(other => other !== name))"
            />
          </div>
          <p v-if="state.quantities.length === 1" class="text-xs text-muted">
            Pick more quantities with the same unit to chart them together. To chart a different quantity, remove this one first.
          </p>
          <p v-if="firstProblem" class="text-sm text-error lg:hidden" aria-hidden="true">
            {{ firstProblem }}
          </p>
        </div>
        <template v-if="state.quantities.length">
          <URadioGroup
            :model-value="state.plot"
            :items="plotItems"
            legend="Plot type"
            orientation="horizontal"
            size="sm"
            :ui="{ legend: 'text-sm font-medium text-highlighted mb-1.5', fieldset: 'flex-wrap gap-x-4 gap-y-1', item: 'py-1.5' }"
            @update:model-value="onPlot"
          />
          <fieldset class="space-y-3">
            <legend class="mb-1.5 text-sm font-medium text-highlighted">
              Dimensions
            </legend>
            <div v-for="row in rowsOfForm" :key="row.dimension.name" class="space-y-1.5">
              <div class="flex items-center justify-between gap-3">
                <span class="min-w-0 truncate text-sm" :title="row.dimension.name">{{ row.dimension.name }}</span>
                <USelect
                  v-if="row.shared"
                  :model-value="roleOf(state, row.dimension.name)"
                  :items="roleItems(options, row)"
                  size="sm"
                  class="w-32 shrink-0"
                  :content="{ align: 'end' }"
                  :ui="{ content: 'min-w-56' }"
                  :aria-label="`${row.dimension.name}: role`"
                  @update:model-value="(role: string) => onRole(row.dimension.name, role)"
                />
                <span v-else class="shrink-0 text-sm text-muted">sum (not in every quantity)</span>
              </div>
              <p v-if="row.shared && hint(options, row)" class="text-xs text-muted">
                {{ hint(options, row) }}
              </p>
              <BuilderValues
                v-if="row.shared && roleOf(state, row.dimension.name) !== SUM"
                :dimension="row.dimension"
                :only="keptValues(state, row.dimension) ?? null"
                :from="state.from[row.dimension.name]"
                :to="state.to[row.dimension.name]"
                @only="(values) => change(setOnly(state, row.dimension.name, values))"
                @range="(from, to) => change(setRange(state, row.dimension.name, from, to))"
              />
            </div>
          </fieldset>
        </template>
      </form>

      <section class="min-w-0 space-y-4" aria-label="Chart">
        <div v-if="!state.quantities.length" class="max-w-prose space-y-2 text-sm text-muted">
          <p>Pick a quantity to start.</p>
          <p>
            The builder charts the quantities of the run that <code>blicket dev</code> keeps: pick one, then say what each of its dimensions does, an axis, a colour, panels, a filter, or summed over. This run has {{ groupCounts }}.
          </p>
        </div>
        <template v-else>
          <div class="space-y-4" aria-live="polite">
            <DevAlert
              v-if="error !== null"
              title="The query failed"
              :message="error"
              :unreachable="unreachable"
              :failures="failures"
              :failed-at="failedAt"
              :busy="pending"
              @retry="retry"
            />
            <ProblemList v-if="failed" :problems="failed.problems" />
            <UAlert v-for="notice in urlNotices" :key="notice" color="neutral" variant="subtle" icon="i-lucide-info" :title="notice" />
            <p v-if="!entry && pending" class="text-sm text-muted">
              Running the query…
            </p>
            <!-- Its height is kept while a chart is shown, so the chart does not move. -->
            <p v-if="entry" class="min-h-5 text-sm text-muted">
              <template v-if="failed || error !== null">
                Showing the last chart that ran.<template v-if="failed">
                  Fix the problem above to update it.
                </template>
              </template>
              <template v-else-if="slow">
                Updating…
              </template>
            </p>
          </div>
          <div v-if="entry && schema && controlState && definition" class="space-y-4 transition-opacity" :class="{ 'opacity-40': stale }" :inert="stale || undefined">
            <div class="space-y-1">
              <h2 class="font-semibold text-highlighted">
                {{ definition.title }}
              </h2>
              <p v-if="subtitle" class="text-sm text-muted">
                {{ subtitle }}
              </p>
              <p class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                <span>{{ definition.plot.type }}</span>
                <span v-if="definition.unit">unit: {{ definition.unit }}</span>
                <span v-if="entry.rows !== null">{{ entry.rows.toLocaleString('en') }} rows</span>
                <button v-if="shownRows?.length" type="button" class="underline hover:text-default disabled:no-underline" :disabled="stale" @click="saveCsv">
                  CSV of this selection
                </button>
              </p>
            </div>
            <ProblemList v-if="warnings.length" :problems="warnings" />
            <ControlBar v-if="controls.length" :controls="controls" :schema="schema" :state="controlState" :axes="tab === 'chart'" @update="updateControls" />
            <ChartTabs v-model="tab" />
            <p v-if="entry.rows === 0" class="text-sm text-muted">
              The query gives no rows.
            </p>
            <p v-else-if="!shownRows?.length" class="text-sm text-muted">
              No rows for this selection.
            </p>
            <BlickChart v-else-if="tab === 'chart' && chartProps" v-bind="chartProps" :name="fileName" />
            <DataTable v-else :rows="shownRows" :schema="schema" :unit="definition.unit" :mapping="definition.plot.mapping" />
          </div>
        </template>
      </section>
    </div>
  </div>
</template>
