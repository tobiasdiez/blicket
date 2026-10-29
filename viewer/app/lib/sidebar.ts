// The Blicks as the sidebar lists them: by group, searched and filtered, each with its badge.
import { blickBadge, type Badge, type BlickComparison } from './comparison'
import type { BlickEntry, Manifest } from './manifest'
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

/** A Blick as the sidebar lists it. */
export interface SidebarEntry {
  entry: BlickEntry
  /** The title, or the name when the Blick has none. */
  label: string
  badge: Badge | null
  pinned: boolean
  /** Whether the Blick has no page, which a Blick without an id lacks. */
  disabled: boolean
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
function flagged(entry: BlickEntry, changes: ReadonlyMap<string, BlickComparison>): boolean {
  return !!changes.get(entry.name)?.change.flags.length
}

/** The number of the build's Blicks the comparison flags; a removed Blick is not one of them. */
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
 * whose search text has every word of `search` and, with `changedOnly`, that the comparison flags.
 * A group left without a Blick is left out. `changes` are the build's Blicks in the comparison by
 * name, `pinned` the names of the pinned Blicks.
 */
export function sidebarGroups(
  manifest: Pick<Manifest, 'groups' | 'blicks'>,
  changes: ReadonlyMap<string, BlickComparison>,
  pinned: ReadonlySet<string>,
  search: string,
  changedOnly: boolean,
): SidebarGroup[] {
  const wanted = words(search)
  return manifest.groups.flatMap((group) => {
    const entries = manifest.blicks
      .filter(entry => entry.group === group.name)
      .filter(entry => !changedOnly || flagged(entry, changes))
      .filter((entry) => {
        const text = searchText(entry, group.tags)
        return wanted.every(word => text.includes(word))
      })
      .map((entry): SidebarEntry => ({
        entry,
        label: entry.definition?.title ?? entry.name,
        badge: blickBadge(entry, changes.get(entry.name) ?? null),
        pinned: pinned.has(entry.name),
        disabled: entry.id === null,
      }))
    return entries.length ? [{ value: group.name, label: group.title ?? group.name, entries }] : []
  })
}

/** What the sidebar says when the search and the filter leave no Blick: which of them did. */
export function noMatch(search: string, changedOnly: boolean): string {
  const query = search.trim()
  const which = changedOnly ? 'changed Blick' : 'Blick'
  return query ? `No ${which} matches '${query}'.` : `No ${which}.`
}
