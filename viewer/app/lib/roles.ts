import type { BlickEntry } from './manifest'

/** The built-in dimension channels as the viewer names them. */
export const CHANNEL_LABELS: Record<string, string> = { x: 'x', color: 'colour', linetype: 'line type' }

/**
 * The text a search looks in: id, title, description, tags, plot type and dimension names, and of a
 * Blick skipped for the run the word `skipped` and the reason.
 */
export function searchText(entry: BlickEntry, groupTags: string[]): string {
  const definition = entry.definition
  return [
    entry.name,
    definition?.title,
    definition?.description,
    definition?.plot.type,
    ...(definition?.tags ?? []),
    ...groupTags,
    ...(entry.columns?.dimensions.map(d => d.name) ?? []),
    ...(entry.status === 'skipped' ? ['skipped', entry.skipped] : []),
  ].join(' ').toLowerCase()
}
