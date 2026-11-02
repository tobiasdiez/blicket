// What the overview shows: the changed and the pinned Blicks as small charts, and the state each
// small chart is drawn at.
import { baselineTable, blickBadge, ranked, whereState, whereText, type Badge, type BlickComparison } from './comparison'
import { queryFromState, stateFromQuery, withoutSplit, type ControlState, type YAxis } from './controls'
import { byStatus, firstLine, type BlickEntry, type Dimension, type Manifest, type Problem, type Value } from './manifest'
import { display, valueKey } from './table'

/** How many Blicks a section of the overview shows as cards, unless they are pinned. */
export const PREVIEWS = 6

/** A Blick as a card of the overview, with the Blick in the comparison shown, if any. */
export interface PreviewCard {
  entry: BlickEntry
  change: BlickComparison | null
}

/** A flagged Blick in the list under the cards. */
export interface ListedBlick {
  name: string
  /** The title of a Blick of the build that did not fail, otherwise the name. */
  label: string
  /** Whether `label` is the name: of a Blick of the baseline only, one in error, or one without a title. */
  byName: boolean
  /** The Blick's page; none for a Blick of the baseline only, or one without an id. */
  to: string | null
  badge: Badge | null
  /** Why a Blick in error is, its first problem, or why a skipped one was skipped. */
  note: string | null
}

/** The sections of the overview. */
export interface PreviewSections {
  /** The flagged Blicks, the first with a table as cards, the rest listed; `null` when none is flagged. */
  changed: { cards: PreviewCard[], listed: ListedBlick[] } | null
  /** The pinned Blicks; while none is, the first Blicks with a table, unless *changed* has cards. */
  pinned: PreviewCard[]
  /** Whether nothing is pinned, so that `pinned` holds the first Blicks, if any. */
  unpinned: boolean
}

/** Whether the Blick has a table, which a card draws. */
const hasTable = (entry: BlickEntry) => entry.status === 'ok' && entry.data !== null

/** The first error of a Blick, or its first problem. */
export function firstProblem(entry: BlickEntry): Problem | null {
  return entry.problems.find(p => p.severity === 'error') ?? entry.problems[0] ?? null
}

/** Why a Blick has no table, if it has none: its first error, or the first line of why it was skipped. */
function noteOf(entry: BlickEntry): string | null {
  if (entry.status === 'skipped') return `skipped: ${firstLine(entry.skipped)}`
  return entry.status === 'error' ? firstProblem(entry)?.message ?? null : null
}

/** `n` things, `one` or `many` of them: `1 error`, `2 errors`. */
const counted = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/**
 * The build's trouble in a line, for the top of the overview, `1 Blick failed to build · build
 * incomplete · 1 error in files or the project`; empty when there is none. Warnings, such as a
 * project outside git, and skipped Blicks are no trouble.
 */
export function troubles(manifest: Pick<Manifest, 'blicks' | 'build' | 'problems'>): string {
  const failed = byStatus(manifest.blicks).error.length
  const errors = manifest.problems.filter(p => p.severity === 'error').length
  return [
    ...(failed ? [`${counted(failed, 'Blick', 'Blicks')} failed to build`] : []),
    ...(manifest.build.incomplete ? ['build incomplete'] : []),
    ...(errors ? [`${counted(errors, 'error', 'errors')} in files or the project`] : []),
  ].join(' · ')
}

/**
 * What the overview says of the Blicks skipped for this run, `24 of 33 Blicks are skipped for this
 * run.`, and that nothing is left to show when every Blick is; empty when none is.
 */
export function skippedLine(entries: readonly BlickEntry[]): string {
  const skipped = byStatus(entries).skipped.length
  if (!skipped) return ''
  const all = skipped === entries.length ? '; nothing to show' : ''
  return `${skipped} of ${counted(entries.length, 'Blick', 'Blicks')} ${skipped === 1 ? 'is' : 'are'} skipped for this run${all}.`
}

/**
 * The overview's sections, from the build's Blicks in the sidebar's order, `entries`, the Blicks
 * of the comparison shown, `compared`, removed ones included, the build's among them by name,
 * `changes`, and the pinned Blicks. *Changed*, when the comparison flags a Blick: the flagged
 * Blicks in ranked order, the first `limit` with a table as cards and the others listed, removed
 * Blicks, skipped ones and Blicks in error among them. A flagged Blick is the build's Blick of its
 * name, if any: a skipped Blick of the build can be removed, and a Blick of the baseline only has a
 * name no Blick of the build has. *Pinned*: the pinned Blicks in the sidebar's order as cards, a
 * Blick in error or skipped too; while none is pinned, no cards when *changed* has some, and
 * otherwise the first `limit` Blicks with a table. A Blick both changed and pinned is a card in both.
 */
export function previewSections(
  entries: BlickEntry[],
  compared: BlickComparison[],
  changes: ReadonlyMap<string, BlickComparison>,
  pinned: BlickEntry[],
  limit: number,
): PreviewSections {
  const byName = new Map(entries.map(entry => [entry.name, entry]))
  const card = (entry: BlickEntry): PreviewCard => ({ entry, change: changes.get(entry.name) ?? null })

  const flagged = ranked(compared)
  let changed: PreviewSections['changed'] = null
  if (flagged.length) {
    const cards: PreviewCard[] = []
    const listed: ListedBlick[] = []
    for (const blick of flagged) {
      const entry = byName.get(blick.name) ?? null
      if (entry && hasTable(entry) && cards.length < limit) {
        cards.push({ entry, change: blick })
        continue
      }
      const title = entry && entry.status !== 'error' ? entry.definition?.title : undefined
      listed.push({
        name: blick.name,
        label: title ?? blick.name,
        byName: title === undefined,
        to: entry?.id ? `/blick/${entry.id}` : null,
        badge: blickBadge(entry, blick),
        note: entry ? noteOf(entry) : null,
      })
    }
    changed = { cards, listed }
  }

  const chosen = new Set(pinned)
  if (chosen.size) return { changed, pinned: entries.filter(entry => chosen.has(entry)).map(card), unpinned: false }
  const fill = changed?.cards.length ? [] : entries.filter(hasTable).slice(0, limit).map(card)
  return { changed, pinned: fill, unpinned: true }
}

// The counts of first Blicks as words, up to the cards of a section.
const NUMBERS = ['one', 'two', 'three', 'four', 'five', 'six']

/** What the pinned section says while nothing is pinned, over the `count` first Blicks it shows. */
export function pinnedHint(count: number): string {
  if (!count) return 'Nothing pinned yet. Pin Blicks on their pages to show them here.'
  const these = count === 1 ? 'this is the first Blick' : `these are the first ${NUMBERS[count - 1] ?? count} Blicks`
  return `Nothing pinned yet; ${these}. Pin Blicks here or on their pages to choose what shows.`
}

/** The state a card draws a Blick at, and how it came to be. */
export interface Preview {
  state: ControlState
  /** Whether the card shows where the comparison finds the largest change: its filters agree. */
  largest: boolean
}

/** Whether `value` is the value `where` names of the dimension. */
function agrees(where: Record<string, Value>, dimension: Dimension | undefined, value: Value): boolean {
  const named = dimension ? where[dimension.name] : undefined
  return dimension !== undefined && named !== undefined && valueKey(named, dimension.dtype) === valueKey(value, dimension.dtype)
}

/**
 * The state a Blick's card draws it at: the state of its page without a query, but every split a
 * filter at its control's default, so the card is one panel; then, when the comparison names where
 * the largest change is, the filters set there. `null` for a Blick without a table.
 */
export function previewState(entry: BlickEntry, change: BlickComparison | null, defaultY: YAxis): Preview | null {
  const schema = entry.columns
  if (!schema) return null
  const initial = stateFromQuery(entry.controls, schema, {}, defaultY).state
  let state = initial
  for (const dimension of initial.splits) state = withoutSplit(state, entry.controls, schema, dimension)
  const where = change?.change.where ?? null
  state = (where && whereState(state, where, schema)) ?? state
  const dimensions = new Map(schema.dimensions.map(d => [d.name, d]))
  // Every filter, the former splits too, at the value `where` names.
  const largest = where !== null && Object.entries(state.filters).every(([name, value]) => agrees(where, dimensions.get(name), value))
  return { state, largest }
}

/** The first sentence of a Blick's description, or nothing. */
function summary(entry: BlickEntry): string {
  return entry.definition?.description?.split(/(?<=[.!?])\s/)[0] ?? ''
}

/**
 * What a card's caption says, in one line: the filter values it shows, in the order of the
 * controls, such as `Region: SSA`; where the comparison finds the largest change, the rest of its
 * row, `largest change at Flow: Primary, Time: 2100`, whose size the card's badge gives, and
 * `baseline faded` when the baseline is drawn behind; or, for a panel the comparison did not
 * choose, which of how many it is. The first sentence of the description when there is nothing of
 * that.
 */
export function previewCaption(entry: BlickEntry, preview: Preview | null, change: BlickComparison | null): string {
  if (!preview) return summary(entry)
  const { state } = preview
  const dimensions = new Map((entry.columns?.dimensions ?? []).map(d => [d.name, d]))
  const parts: string[] = []
  const shown = entry.controls.flatMap(({ dimension }) => {
    const value = state.filters[dimension]
    const d = dimensions.get(dimension)
    return value === undefined ? [] : [`${dimension}: ${d ? display(value, d) : String(value)}`]
  })
  if (shown.length) parts.push(shown.join(', '))
  const where = change?.change.where
  if (preview.largest && where) {
    const rest = Object.fromEntries(Object.entries(where).filter(([name]) => state.filters[name] === undefined))
    const at = whereText(rest, state, entry.definition?.plot.mapping ?? {})
    parts.push(at ? `largest change at ${at}` : 'largest change')
    if (baselineTable(change)) parts.push('baseline\u00A0faded')
  }
  else {
    // The panels the Blick's splits draw on its page, of which the card shows one: the first, when
    // each split is at its first value.
    const split = entry.controls.flatMap(c => (c.kind === 'split' ? dimensions.get(c.dimension) ?? [] : []))
    const count = split.reduce((product, d) => product * d.values.length, 1)
    const first = split.every((d) => {
      const [head] = d.values
      const value = state.filters[d.name]
      return head !== undefined && value !== undefined && agrees({ [d.name]: head }, d, value)
    })
    if (split.length) parts.push(`${first ? 'first' : 'one'} of ${count} panels`)
  }
  return parts.length ? parts.join(' · ') : summary(entry)
}

/**
 * Where a card's title leads: the Blick's page at the card's state when the card shows the largest
 * change, so what the card shows is what opens; otherwise the page as its author laid it out.
 * `null` for a Blick without an id.
 */
export function previewLink(entry: BlickEntry, preview: Preview | null, defaultY: YAxis): { path: string, query: Record<string, string | string[]> } | null {
  if (!entry.id) return null
  const path = `/blick/${entry.id}`
  return preview?.largest && entry.columns ? { path, query: queryFromState(entry.columns, preview.state, defaultY) } : { path, query: {} }
}
