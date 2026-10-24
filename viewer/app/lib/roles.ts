import type { BlickEntry } from './manifest'

const CHANNELS: Record<string, string> = { x: 'x', color: 'colour', linetype: 'line type' }

/**
 * What each dimension of a Blick does, for its card: the channels it is bound to (x, colour,
 * line type), then the splits into panels, then the filters.
 */
export function roles(entry: BlickEntry): string[] {
  const mapping = entry.definition?.plot.mapping ?? {}
  const bound = Object.entries(CHANNELS)
    .filter(([channel]) => mapping[channel])
    .map(([channel, label]) => `${label}: ${mapping[channel]}`)
  const of = (kind: string) => entry.controls.filter(control => control.kind === kind).map(control => control.dimension)
  return [...bound, ...of('split').map(name => `panels: ${name}`), ...of('filter').map(name => `filter: ${name}`)]
}

/** The text a search looks in: id, title, description, tags, plot type and dimension names. */
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
  ].join(' ').toLowerCase()
}
