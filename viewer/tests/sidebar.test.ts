import { describe, expect, it } from 'vitest'
import type { BlickComparison, Flag } from '../app/lib/comparison'
import type { BlickEntry, Group, Manifest } from '../app/lib/manifest'
import { changedCount, noMatch, sidebarGroups, sidebarOrder } from '../app/lib/sidebar'

function entry(name: string, title: string | null, extra: Partial<BlickEntry> = {}): BlickEntry {
  const definition = title === null ? null : { title, description: null, tags: [], plot: { type: 'line', mapping: {} } }
  return { id: name, name, aliases: [], group: name.split('/')[0]!, definition, columns: null, controls: [], problems: [], status: 'ok', ...extra } as unknown as BlickEntry
}

function compared(name: string, flags: Flag[], magnitude: number | null = null): BlickComparison {
  return { name, change: { flags, magnitude } } as unknown as BlickComparison
}

const group = (name: string, title: string | null, tags: string[] = []) => ({ name, title, tags, modules: [] }) as Group

// The manifest lists the Blicks of a group apart, as a build of several modules does.
const manifest: Pick<Manifest, 'groups' | 'blicks'> = {
  groups: [group('drivers', 'Drivers and scenario parameters'), group('flows', null, ['mfa']), group('stocks', 'In-use stocks')],
  blicks: [
    entry('drivers/gdp', 'GDP per capita'),
    entry('flows/production', 'Production by source'),
    entry('stocks/by_region', 'In-use stock by region'),
    entry('flows/consumption', null),
    entry('flows/broken', null, { id: null, status: 'error' }),
  ],
}
const changes = new Map([
  ['flows/production', compared('flows/production', ['schema', 'value'], 0.020961)],
  ['drivers/gdp', compared('drivers/gdp', [])],
  ['flows/consumption', compared('flows/consumption', ['new'])],
])
const none = new Map<string, BlickComparison>()
const shown = (search: string, changedOnly = false) => sidebarGroups(manifest, changes, new Set(), search, changedOnly)
  .map(g => [g.value, g.entries.map(e => e.entry.name)])

describe('the sidebar', () => {
  it('lists the groups in manifest order, each with its Blicks, by title or by name', () => {
    const groups = sidebarGroups(manifest, none, new Set(), '', false)
    expect(groups.map(g => [g.value, g.label])).toEqual([['drivers', 'Drivers and scenario parameters'], ['flows', 'flows'], ['stocks', 'In-use stocks']])
    expect(groups[1]!.entries.map(e => e.label)).toEqual(['Production by source', 'flows/consumption', 'flows/broken'])
  })

  it('badges the flag a Blick is ranked by, and a Blick in error that no comparison flags', () => {
    const flows = sidebarGroups(manifest, changes, new Set(), '', false)[1]!.entries
    expect(flows.map(e => e.badge?.label)).toEqual(['Δ 2.1%', 'new', 'error'])
    expect(sidebarGroups(manifest, changes, new Set(), '', false)[0]!.entries[0]!.badge).toBeNull()
  })

  it('marks the pinned Blicks, and a Blick without an id as without a page', () => {
    const flows = sidebarGroups(manifest, none, new Set(['flows/production']), '', false)[1]!.entries
    expect(flows.map(e => [e.pinned, e.disabled])).toEqual([[true, false], [false, false], [false, true]])
  })

  it('searches for every word, in the group\'s tags too, and leaves out the groups without a match', () => {
    expect(shown('STOCK region')).toEqual([['stocks', ['stocks/by_region']]])
    expect(shown('mfa')).toEqual([['flows', ['flows/production', 'flows/consumption', 'flows/broken']]])
    expect(shown('stock gdp')).toEqual([])
  })

  it('keeps the flagged Blicks with the filter, and counts them', () => {
    expect(shown('', true)).toEqual([['flows', ['flows/production', 'flows/consumption']]])
    expect(shown('source', true)).toEqual([['flows', ['flows/production']]])
    expect([changedCount(manifest, changes), changedCount(manifest, none)]).toEqual([2, 0])
  })

  it('lists every Blick for a search of blanks, and nothing for a manifest without groups', () => {
    expect(shown('  ').flatMap(([, names]) => names)).toHaveLength(5)
    expect(sidebarGroups({ groups: [], blicks: [] }, none, new Set(), '', false)).toEqual([])
  })

  it('says which of the search and the filter left nothing', () => {
    expect([noMatch(' stock ', true), noMatch('stock', false), noMatch('', true)]).toEqual(["No changed Blick matches 'stock'.", "No Blick matches 'stock'.", 'No changed Blick.'])
  })

  it('orders the Blicks as it lists them', () => {
    expect(sidebarOrder(manifest).map(e => e.name)).toEqual(['drivers/gdp', 'flows/production', 'flows/consumption', 'flows/broken', 'stocks/by_region'])
  })
})
