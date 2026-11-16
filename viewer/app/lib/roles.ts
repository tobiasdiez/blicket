import { isCheck, type UnitEntry } from './manifest'

/** The built-in dimension channels as the viewer names them. */
export const CHANNEL_LABELS: Record<string, string> = { x: 'x', color: 'colour', linetype: 'line type', source: 'source', target: 'target' }

/**
 * The text a search looks in: id, title, description, tags, a Blick's plot type and a check's word
 * `check`, dimension names, the expectation in words and its result when it is not met, and of a
 * unit skipped for the run the word `skipped` and the reason.
 */
export function searchText(entry: UnitEntry, groupTags: string[]): string {
  const definition = entry.definition
  const outcome = entry.outcome
  return [
    entry.name,
    definition?.title,
    definition?.description,
    isCheck(entry) ? 'check' : entry.definition?.plot.type,
    ...(definition?.tags ?? []),
    ...groupTags,
    ...(entry.columns?.dimensions.map(d => d.name) ?? []),
    ...(outcome ? [outcome.expectation, ...(outcome.result === 'met' ? [] : [outcome.result])] : []),
    ...(entry.status === 'skipped' ? ['skipped', entry.skipped] : []),
  ].join(' ').toLowerCase()
}
