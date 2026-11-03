// The run picker's words and ticks: how long ago a run changed, what the load button says,
// which globs the runs come from, and which ticks a new list keeps.
import type { RunFolder } from './dev'

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
