// The builds of a session of `blicket dev`, which builds its Blicks while the viewer is open: a
// cheap Blick in the background and again at each visit of its page, an expensive one when its
// page asks for it. What a Blick's page, its card and its entry in the sidebar say of its build,
// from its manifest entry and the jobs that `dev/info` lists.
import type { Job } from './dev'
import { sourceText, type BlickEntry, type Manifest } from './manifest'

/** Where a Blick stands in the jobs of a session: building, or queued. */
export type BuildMark = Job['state']

/**
 * What a Blick's page shows of its build in a session:
 *
 * - `invalid`: its definition is invalid, so it cannot be built; its problems, no `Rebuild`.
 * - `ask`: not built, and the page asks for it: a cheap Blick, or an expensive one while no Blick
 *   a page asked for builds or waits.
 * - `other`: an expensive Blick not built, while `other`, a Blick a page asked for, builds or
 *   waits first: `Build next`.
 * - `queued`: not built, and queued `behind` the Blick that builds, with `ahead` more before it.
 * - `building`: not built, its `job` building.
 * - `rebuilding`: an expensive Blick built, its `job` building again; `again` when one more build
 *   waits.
 * - `updating`: a cheap Blick built, and built again: its `job`, building or queued, the latter
 *   behind `behind` when that is an expensive Blick that builds, which takes long.
 * - `built`: built, and nothing to do for it; for an expensive Blick, `Rebuild`, and `behind`
 *   names the Blick a rebuild is queued behind, if one is, `ahead` how many more wait before it.
 */
export type PageState =
  | { kind: 'invalid' }
  | { kind: 'ask' }
  | { kind: 'other', other: Job }
  | { kind: 'queued', behind: Job | null, ahead: number }
  | { kind: 'building', job: Job }
  | { kind: 'rebuilding', job: Job, again: boolean }
  | { kind: 'updating', job: Job, behind: Job | null }
  | { kind: 'built', behind: Job | null, ahead: number }

/**
 * Whether an entry is in error since its definition is: no build made it, so it has no timing,
 * as a Blick whose transformation failed has (a Python test holds blicket to that).
 */
export function isInvalid(entry: BlickEntry): boolean {
  return entry.status === 'error' && entry.timing_ms === null
}

/** The ids of the expensive Blicks of `entries`, as the manifest of a session marks them. */
export function expensiveIds(entries: readonly BlickEntry[]): ReadonlySet<string> {
  return new Set(entries.filter(entry => entry.expensive && entry.id !== null).map(entry => entry.id!))
}

/**
 * What the page of `entry` shows in a session whose jobs are `jobs`, in order; `expensive` are
 * the ids of the session's expensive Blicks, which tell whether a cheap Blick built again waits
 * long.
 */
export function pageState(entry: BlickEntry, jobs: readonly Job[], expensive: ReadonlySet<string> = new Set()): PageState {
  if (isInvalid(entry)) return { kind: 'invalid' }
  const building = jobs.find(job => job.state === 'building') ?? null
  const own = building?.id === entry.id ? building : null
  const queue = jobs.filter(job => job.state === 'queued')
  const ahead = queue.findIndex(job => job.id === entry.id)
  if (entry.status === 'pending') {
    if (own) return { kind: 'building', job: own }
    if (ahead >= 0) return { kind: 'queued', behind: building, ahead }
    if (!entry.expensive) return { kind: 'ask' }
    const first = jobs.find(job => job.asked)
    return first ? { kind: 'other', other: first } : { kind: 'ask' }
  }
  if (!entry.expensive) {
    if (own) return { kind: 'updating', job: own, behind: null }
    const waits = queue[ahead]
    if (waits) return { kind: 'updating', job: waits, behind: building && expensive.has(building.id) ? building : null }
    return { kind: 'built', behind: null, ahead: 0 }
  }
  if (own) return { kind: 'rebuilding', job: own, again: ahead >= 0 }
  return { kind: 'built', behind: ahead >= 0 ? building : null, ahead: Math.max(ahead, 0) }
}

/**
 * Whether the page of `entry` in `state` offers `Rebuild`: an expensive Blick, once it is built,
 * and while it rebuilds. A cheap one is built again when its page is opened.
 */
export function rebuildable(entry: BlickEntry | null, state: PageState | null): boolean {
  return !!entry?.expensive && (state?.kind === 'built' || state?.kind === 'rebuilding')
}

/**
 * A visit of a page to the Blick `name` in the session `session` of blicket dev: one more starts
 * when the page shows another Blick, or blicket dev was started again, which built nothing yet.
 */
export function visitOf(session: string | undefined, name: string | undefined): string | undefined {
  return session === undefined || name === undefined ? undefined : `${session} ${name}`
}

/**
 * What a visit of the page of `entry` in `state` asks of blicket dev, once per visit: `build` the
 * Blick, not built and asked for; `rebuild` it, a cheap Blick built, which each visit builds
 * again; `none`, nothing in this visit, since the Blick builds or waits already, or an expensive
 * one is built, or the worker that builds stopped; or `wait`, nothing yet, while an expensive
 * Blick waits for `Build next` or for no Blick a page asked for to build or wait.
 */
export function visitRequest(entry: BlickEntry | null, state: PageState | null, stopped: boolean): 'build' | 'rebuild' | 'none' | 'wait' {
  if (!entry || !state) return 'wait'
  if (stopped || state.kind === 'invalid') return 'none'
  if (state.kind === 'ask') return 'build'
  if (state.kind === 'other') return 'wait'
  return !entry.expensive && state.kind === 'built' ? 'rebuild' : 'none'
}

const twoDigits = (n: number) => String(n).padStart(2, '0')

/** A duration of `seconds` as the page counts it: `0:42`, `1:02:03`. */
export function elapsed(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  const [h, m, s] = [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60]
  return h ? `${h}:${twoDigits(m)}:${twoDigits(s)}` : `${m}:${twoDigits(s)}`
}

/** How many more Blicks are queued before one, as the end of a line. */
const more = (ahead: number): LinePart[] => (ahead ? [` and ${ahead} more`] : [])

/**
 * A part of a line about a build: words, a Blick by its id, which the page shows by its title as a
 * link to it, or a time, which a screen reader is not told every second.
 */
export type LinePart = string | { blick: string } | { time: string }

/**
 * The line a Blick's page shows of its build, in parts, `null` when the page has nothing to say
 * of it: a Blick built, or invalid. `later` is how many seconds passed since `dev/info` said how
 * long the jobs ran; `lost` that it does not answer any more, so that no time is counted.
 */
export function statusLine(state: PageState, later: number, lost = false): LinePart[] | null {
  // The time, and with it what only goes with it, such as its parentheses.
  const time = (job: Job, shape = (counted: string) => counted): LinePart[] => (lost ? [] : [{ time: shape(elapsed(job.seconds + later)) }])
  switch (state.kind) {
    case 'ask':
      return ['Asking blicket dev to build it…']
    case 'other':
      if (state.other.state !== 'building') return [{ blick: state.other.id }, ' is about to build.']
      if (lost) return [{ blick: state.other.id }, ' was building when blicket dev stopped answering.']
      return [{ blick: state.other.id }, ' is building', ...time(state.other, counted => ` (${counted})`), '.']
    case 'queued':
      return state.behind ? ['Queued behind ', { blick: state.behind.id }, ...more(state.ahead)] : ['Queued']
    case 'building':
      if (lost) return ['It was building when blicket dev stopped answering.']
      return ['Building…', ...time(state.job, counted => ` ${counted}`), ' · what the transformation prints is in the terminal']
    case 'rebuilding':
      if (lost) return ['It was rebuilding when blicket dev stopped answering.']
      return ['Rebuilding…', ...time(state.job, counted => ` ${counted}`), ...(state.again ? [' · one more build follows'] : [])]
    case 'updating':
      if (lost) return ['It was updating when blicket dev stopped answering.']
      return state.behind ? ['Updating after ', { blick: state.behind.id }, ...time(state.behind, counted => ` (${counted})`)] : ['Updating…', ...time(state.job, counted => ` ${counted}`)]
    case 'built':
      return state.behind ? ['Rebuild queued behind ', { blick: state.behind.id }, ...more(state.ahead)] : null
    case 'invalid':
      return null
  }
}

/** A line's words, the Blicks by `title`, with the time, or, `spoken`, without: what a screen reader is told. */
export function lineText(parts: readonly LinePart[], title: (id: string) => string, spoken = false): string {
  return parts.map(part => (typeof part === 'string' ? part : 'blick' in part ? title(part.blick) : spoken ? '' : part.time)).join('')
}

/** A build of its Blick that a page saw end: whether it was a rebuild, and when it ended. */
export interface Outcome {
  rebuilt: boolean
  at: Date
}

/** A build a page asked for and that blicket dev took on: the Blick, and whether it was built before. */
export interface Asked {
  id: string
  rebuilt: boolean
}

/**
 * Whether the build a page asked for, `asked`, ended, given the jobs of an answer of `dev/info`
 * that came after blicket dev took it on and is shown with the manifest of its revision: once
 * the Blick is not among `jobs` any more, it was built, whether or not its entry changed; then
 * whether it was a rebuild. `null` while it builds or waits.
 */
export function askedEnded(asked: Asked | null, jobs: readonly Job[]): { rebuilt: boolean } | null {
  return asked && !jobs.some(job => job.id === asked.id) ? { rebuilt: asked.rebuilt } : null
}

/**
 * What a Blick's page says of a Blick built when nothing builds it: how its last build ended, in
 * how long, `Built in 3.2 s`, and, when the page saw it end, when, `Rebuilt in 3.0 s at
 * 12:04:10`; for a Blick whose definition is invalid, what to do. `null` for a Blick not built.
 */
export function outcomeLine(entry: BlickEntry, seen: Outcome | null): string | null {
  if (isInvalid(entry)) {
    const where = entry.source ? ` at ${sourceText(entry.source)}` : ''
    return `Cannot be built: its definition is invalid. Fix it${where} and restart blicket dev.`
  }
  if (entry.status === 'pending') return null
  const took = entry.timing_ms === null ? '' : ` in ${wallTime(entry.timing_ms)}`
  const when = seen ? ` at ${seen.at.toLocaleTimeString('en-GB')}` : ''
  const verb = { ok: seen?.rebuilt ? 'Rebuilt' : 'Built', error: 'Failed', skipped: 'Skipped' }[entry.status]
  return `${verb}${took}${when}`
}

/**
 * How long a build took, in milliseconds, as the terminal says it: `412 ms`, `3.2 s`, then
 * `1 min 15 s` and `1 h 2 min 5 s`; each as it is rounded, so that 999.6 ms is `1.0 s`.
 */
export function wallTime(milliseconds: number): string {
  if (Math.round(milliseconds) < 1000) return `${Math.round(milliseconds)} ms`
  if (Math.round(milliseconds / 100) < 600) return `${(milliseconds / 1000).toFixed(1)} s`
  const whole = Math.round(milliseconds / 1000)
  const [h, m, s] = [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60]
  return h ? `${h} h ${m} min ${s} s` : `${m} min ${s} s`
}

/**
 * Where each Blick stands in `jobs`: building, or queued; a Blick that builds and is queued again
 * builds. `previous`, the marks before, comes back when the marks are the same, as they are while
 * a build only goes on, so that nothing computed from them is computed again every second.
 */
export function buildMarks(jobs: readonly Job[], previous?: ReadonlyMap<string, BuildMark>): ReadonlyMap<string, BuildMark> {
  const marks = new Map<string, BuildMark>()
  for (const job of jobs) {
    if (!marks.has(job.id) || job.state === 'building') marks.set(job.id, job.state)
  }
  const same = previous !== undefined && previous.size === marks.size && [...marks].every(([id, mark]) => previous.get(id) === mark)
  return same ? previous : marks
}

/** What a card says of a Blick not built yet: building, queued, or not built yet. */
export function pendingText(mark: BuildMark | undefined): string {
  return mark === 'building' ? 'Building…' : mark === 'queued' ? 'Queued' : 'Not built yet'
}

/**
 * What the overview of a session says of its Blicks, all of them counted: how many are not
 * built yet, `53 of 56 Blicks not built yet`, or that none is left to build.
 */
export function notBuiltLine(entries: readonly BlickEntry[]): string {
  const pending = entries.filter(entry => entry.status === 'pending').length
  const total = `${entries.length} ${entries.length === 1 ? 'Blick' : 'Blicks'}`
  return pending ? `${pending} of ${total} not built yet` : `None of the ${total} is left to build`
}

/** How many Blicks are not built yet, as the sidebar's foot counts them, in one piece: `62 not built yet`; empty for none. */
export function pendingCount(entries: readonly BlickEntry[]): string {
  const pending = entries.filter(entry => entry.status === 'pending').length
  return pending ? `${pending} not built yet` : ''
}

/**
 * What the overview says of the first job a page asked for, as a line: `Steel trade is building
 * (0:42).`; `lost`, that blicket dev does not answer any more, it says that it was building then.
 * The background is not named: it is cheap, and its Blicks follow one another quickly.
 */
export function buildingLine(jobs: readonly Job[], later: number, lost = false): LinePart[] | null {
  const first = jobs.find(job => job.asked)
  return first ? statusLine({ kind: 'other', other: first }, later, lost) : null
}

/**
 * The notice of the overview of a session: the note on expensive Blicks, when the session has
 * one, as its title, and how many Blicks are not built yet and which builds, `building`, as its
 * description; without an expensive Blick, the count is the title and the Blick that builds the
 * description, and there is no notice once every Blick is built. `null` when there is nothing to
 * say.
 */
export function overviewNotice(entries: readonly BlickEntry[], building: string | null): { title: string, description: string } | null {
  const expensive = entries.some(entry => entry.expensive)
  const pending = entries.some(entry => entry.status === 'pending')
  if (!expensive && !pending) return null
  const count = notBuiltLine(entries)
  return expensive
    ? { title: 'An expensive Blick is built when you open it.', description: [count, building].filter(Boolean).join(' · ') }
    : { title: count, description: building ?? '' }
}

/**
 * What the page's footer says: the blicket that made the build, its id and time; for a session
 * of blicket dev, which makes no build, that it is one and when it started.
 */
export function footerText(manifest: Pick<Manifest, 'blicket' | 'build' | 'created_at'>, session: boolean): string {
  const time = `${manifest.created_at.slice(0, 16).replace('T', ' ')} UTC`
  return session
    ? `blicket ${manifest.blicket} · session started ${time}`
    : `blicket ${manifest.blicket} · build ${manifest.build.id} · ${time}`
}

/**
 * What the run picker says while its load runs, the time returned apart, so that a screen reader
 * is not told it every second: that it waits for the Blick that builds, as a load waits for a
 * cheap build, and for how long it has built, `Waiting for Steel trade to build…` and `0:12`;
 * once nothing builds, that the runs `names` load.
 */
export function loadingLine(names: string, jobs: readonly Job[], later: number, title: (id: string) => string): { text: string, time: string | null } {
  const building = jobs.find(job => job.state === 'building')
  return building
    ? { text: `Waiting for ${title(building.id)} to build…`, time: elapsed(building.seconds + later) }
    : { text: `Loading ${names}; the loader's output goes to the terminal.`, time: null }
}
