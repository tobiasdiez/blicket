// The Blicks as the sidebar lists them, by group, and the checks in a section of their own:
// searched and filtered, each with its badges.
import { blickBadge, type Badge, type BlickComparison } from './comparison'
import { expectationBadge, isNotMet, notMetCount, type ExpectationBadge } from './expectations'
import { byStatus, isCheck, unitPath, units, type BlickEntry, type Manifest, type UnitEntry } from './manifest'
import { searchText } from './roles'
import { read, write, type KeyValueStorage } from './storage'

/** The key of whether the sidebar is open on a wide window, in the browser's storage. */
export const SIDEBAR = 'blicket:sidebar'

/** Whether the user left the sidebar open: open unless `storage` keeps it closed. */
export function storedOpen(storage: KeyValueStorage): boolean {
  return read(storage, SIDEBAR) !== 'closed'
}

/** Keep whether the sidebar is open in `storage`. */
export function storeOpen(storage: KeyValueStorage, open: boolean): void {
  write(storage, SIDEBAR, open ? 'open' : 'closed')
}

/** What the sidebar keeps: every unit, the Blicks the comparison flags, or the units whose expectation is not met. */
export type SidebarFilter = 'all' | 'changed' | 'notMet'

/** The value of the section of the checks among the groups' values; no group name has a colon. */
export const CHECKS = ':checks'

/** A Blick or a check as the sidebar lists it. */
export interface SidebarEntry {
  entry: UnitEntry
  /** The title, or the name when the unit has none. */
  label: string
  /** The badge of the Blick's flags; a check has none. */
  badge: Badge | null
  /** The badge of the outcome of the unit's expectation, when it is not met. */
  expectation: ExpectationBadge | null
  /** Whether the unit was skipped for the run and no badge marks it, which mutes it. */
  muted: boolean
  pinned: boolean
  /** Whether the unit has no page, which one without an id lacks. */
  disabled: boolean
  /** The unit's page. */
  to: string | null
}

/** A group of the manifest as the sidebar shows it, with the Blicks of it that are shown. */
export interface SidebarGroup {
  /** The group's name, which stays the group's while other groups are filtered out. */
  value: string
  /** The title, or the name when the group has none. */
  label: string
  entries: SidebarEntry[]
}

/** The lowercase words of a search. */
function words(search: string): string[] {
  return search.toLowerCase().split(/\s+/).filter(Boolean)
}

/** Whether the comparison flags the Blick; `changes` are the build's Blicks in it by name. */
function flagged(entry: UnitEntry, changes: ReadonlyMap<string, BlickComparison>): boolean {
  return !!changes.get(entry.name)?.change.flags.length
}

/**
 * The units of `entries` that `filter` keeps and whose search text, with their group's `tags`,
 * has every word of `search`; `changes` are the build's Blicks in the comparison by name, which
 * no check is among.
 */
function shown<E extends UnitEntry>(
  entries: readonly E[],
  tags: (entry: E) => string[],
  changes: ReadonlyMap<string, BlickComparison>,
  search: string,
  filter: SidebarFilter,
): E[] {
  const wanted = words(search)
  return entries
    .filter(entry => (filter === 'changed' ? flagged(entry, changes) : filter === 'all' || isNotMet(entry.outcome)))
    .filter((entry) => {
      const text = searchText(entry, tags(entry))
      return wanted.every(word => text.includes(word))
    })
}

/** The unit as the sidebar lists it; a check has no flags. */
function listed(entry: UnitEntry, changes: ReadonlyMap<string, BlickComparison>, pinned: ReadonlySet<string>): SidebarEntry {
  const badge = blickBadge(entry, isCheck(entry) ? null : changes.get(entry.name) ?? null)
  const expectation = expectationBadge(entry.outcome)
  return {
    entry,
    label: entry.definition?.title ?? entry.name,
    badge,
    expectation,
    muted: entry.status === 'skipped' && badge === null && expectation === null,
    pinned: pinned.has(entry.name),
    disabled: entry.id === null,
    to: unitPath(entry),
  }
}

/** The number of the build's Blicks the comparison flags; a Blick of the baseline only is not one of them. */
export function changedCount(manifest: Pick<Manifest, 'blicks'>, changes: ReadonlyMap<string, BlickComparison>): number {
  return manifest.blicks.filter(entry => flagged(entry, changes)).length
}

/**
 * The Blicks in the sidebar's order: by group in the order of the manifest's groups, then in the
 * manifest's order. A Blick of a group the manifest does not list is in no group, and left out.
 */
export function sidebarOrder(manifest: Pick<Manifest, 'groups' | 'blicks'>): BlickEntry[] {
  return manifest.groups.flatMap(group => manifest.blicks.filter(entry => entry.group === group.name))
}

/**
 * The sidebar's groups in the manifest's order, each with its Blicks in the manifest's order: those
 * whose search text has every word of `search` and that `filter` keeps. A group left without a
 * Blick is left out. `changes` are the build's Blicks in the comparison by name, `pinned` the
 * names of the pinned Blicks.
 */
export function sidebarGroups(
  manifest: Pick<Manifest, 'groups' | 'blicks'>,
  changes: ReadonlyMap<string, BlickComparison>,
  pinned: ReadonlySet<string>,
  search: string,
  filter: SidebarFilter,
): SidebarGroup[] {
  return manifest.groups.flatMap((group) => {
    const members = manifest.blicks.filter(entry => entry.group === group.name)
    const entries = shown(members, () => group.tags, changes, search, filter).map(entry => listed(entry, changes, pinned))
    return entries.length ? [{ value: group.name, label: group.title ?? group.name, entries }] : []
  })
}

/**
 * The section of the checks, under the groups of the Blicks: the checks as one list in the
 * manifest's order, since their groups are the Blicks' and would repeat as headings, searched as
 * the Blicks, their group's tags included, and kept by `filter`, which keeps no check for
 * `changed`; `null` when it keeps none, and in a build without checks.
 */
export function sidebarChecks(
  manifest: Pick<Manifest, 'groups' | 'checks'>,
  search: string,
  filter: SidebarFilter,
): SidebarGroup | null {
  const tags = new Map(manifest.groups.map(group => [group.name, group.tags]))
  const entries = shown(manifest.checks, entry => tags.get(entry.group) ?? [], new Map(), search, filter)
    .map(entry => listed(entry, new Map(), new Set()))
  return entries.length ? { value: CHECKS, label: 'Checks', entries } : null
}

/** A choice of the sidebar's filter. */
export interface FilterOption {
  value: SidebarFilter
  label: string
}

/**
 * What the sidebar's filter offers: `All`, `Changed (N)` with the Blicks the comparison flags and
 * `Not met (N)` with the units whose expectation is not met, each of the last two when its N is
 * not 0; none at all without either, when there is nothing to filter.
 */
export function filterOptions(changed: number, notMet: number): FilterOption[] {
  const options: FilterOption[] = [
    ...(changed ? [{ value: 'changed' as const, label: `Changed (${changed})` }] : []),
    ...(notMet ? [{ value: 'notMet' as const, label: `Not met (${notMet})` }] : []),
  ]
  return options.length ? [{ value: 'all', label: 'All' }, ...options] : []
}

/** The number of the build's units whose expectation is not met, Blicks and checks. */
export function notMetUnits(manifest: Pick<Manifest, 'blicks' | 'checks'>): number {
  return notMetCount(units(manifest))
}

/**
 * What the sidebar's foot says: `4 Blicks and 8 checks · 3 with errors · 2 skipped`, with errors
 * counting the units that failed and those whose expectation cannot be evaluated, and that a
 * module failed to import; while a search or the filter is active, how many units of all are
 * shown first: `6 of 12 shown · 4 Blicks and 8 checks`, or `6 of 10 Blicks` without checks.
 */
export function footText(manifest: Pick<Manifest, 'blicks' | 'checks' | 'build'>, matching: number | null): string {
  const all = units(manifest)
  const errors = all.filter(entry => entry.status === 'error' || entry.outcome?.result === 'error').length
  const skipped = byStatus(all).skipped.length
  const checks = manifest.checks.length
  const blicks = `${manifest.blicks.length} ${manifest.blicks.length === 1 ? 'Blick' : 'Blicks'}`
  const counted = checks ? [...(matching === null ? [] : [`${matching} of ${all.length} shown`]), `${blicks} and ${checks} ${checks === 1 ? 'check' : 'checks'}`] : [`${matching === null ? '' : `${matching} of `}${blicks}`]
  return [
    ...counted,
    ...(errors ? [`${errors}\u00A0with\u00A0errors`] : []),
    ...(skipped ? [`${skipped}\u00A0skipped`] : []),
    ...(manifest.build.incomplete ? ['incomplete, a module failed to import'] : []),
  ].join(' · ')
}

/**
 * The groups open while the user has chosen none, in their order: all but those whose units are
 * all skipped for the run and unmarked, which hold nothing to look at, unless `opened` names them,
 * as the group of the Blick whose page is shown.
 */
export function initiallyOpen(groups: SidebarGroup[], opened: readonly string[] = []): string[] {
  return groups
    .filter(group => opened.includes(group.value) || !group.entries.every(item => item.muted))
    .map(group => group.value)
}

/**
 * What the sidebar says when the search and the filter leave no unit: which of them did; `checks`
 * says that the build has checks, which the search looks for too.
 */
export function noMatch(search: string, filter: SidebarFilter, checks = false): string {
  const query = search.trim()
  const which = { all: checks ? 'Blick or check' : 'Blick', changed: 'changed Blick', notMet: 'Blick or check with an expectation not met' }[filter]
  return query ? `No ${which} matches '${query}'.` : `No ${which}.`
}
