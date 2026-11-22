// The run picker's words and ticks: how long ago a run changed, what the load button says,
// which globs the runs come from, how a tick changes the others, which ticks a new list keeps,
// and what a load drops.
import type { RunFolder } from './dev'
import type { BlickEntry } from './manifest'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const relative = new Intl.RelativeTimeFormat('en', { numeric: 'always' })

/**
 * How long before `now` the time `modified` (ISO 8601) was, in the largest whole unit up to days,
 * as "8 days ago"; "just now" under a minute and for a time after `now`, the date itself after a
 * year.
 */
export function ago(modified: string, now: Date): string {
  const then = new Date(modified)
  const elapsed = now.getTime() - then.getTime()
  if (Number.isNaN(elapsed)) return modified
  if (elapsed < MINUTE) return 'just now'
  if (elapsed < HOUR) return relative.format(-Math.floor(elapsed / MINUTE), 'minute')
  if (elapsed < DAY) return relative.format(-Math.floor(elapsed / HOUR), 'hour')
  if (elapsed < 365 * DAY) return relative.format(-Math.floor(elapsed / DAY), 'day')
  return then.toISOString().slice(0, 10)
}

/** What the load button says for `count` runs ticked. */
export function loadLabel(count: number): string {
  return count > 1 ? `Load ${count} runs as one` : 'Load'
}

/** The globs `patterns` as `[tool.blicket]` writes them: `runs = ["output/*"]`. */
export function runsSetting(patterns: string[]): string {
  return `runs = [${patterns.map(pattern => JSON.stringify(pattern)).join(', ')}]`
}

/** The ticks `picked` of folders that the list `runs` still has: a folder gone cannot stay ticked. */
export function keepListed(picked: string[], runs: RunFolder[]): string[] {
  return picked.filter(path => runs.some(run => run.path === path))
}

/** The names of the runs at `paths`, in the order of the list, for the page to say what loads. */
export function namesOf(paths: string[], runs: RunFolder[]): string {
  return runs.filter(run => paths.includes(run.path)).map(run => run.name).join(', ')
}

/** What a run's row says beside its name: how long ago the folder changed, or, for the project itself, that it is computed from code. */
export function whenText(run: RunFolder, now: Date): string {
  return run.project || run.modified === null ? 'computed from code' : ago(run.modified, now)
}

/**
 * The ticks once the run at `path` of the list `runs` is ticked, `on`, or not: the project
 * itself loads alone, so ticking it unticks the folders, and ticking a folder unticks it.
 */
export function ticked(picked: readonly string[], path: string, on: boolean, runs: readonly RunFolder[]): string[] {
  if (!on) return picked.filter(other => other !== path)
  const project = (other: string) => runs.some(run => run.path === other && run.project)
  return project(path) ? [path] : [...picked.filter(other => !project(other)), path]
}

/** How many expensive Blicks the session has built, which loading another run drops. */
export function expensiveBuilt(entries: readonly BlickEntry[]): number {
  return entries.filter(entry => entry.expensive && entry.status !== 'pending').length
}

/** What the picker asks before a load drops `count` expensive Blicks built. */
export function dropQuestion(count: number): string {
  const built = count === 1 ? 'the expensive Blick' : `the ${count} expensive Blicks`
  return `Loading another run drops ${built} built so far.`
}
