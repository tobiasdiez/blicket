import { describe, expect, it } from 'vitest'
import type { BlickComparison, Flag } from '../app/lib/comparison'
import type { BlickEntry, Group, Manifest } from '../app/lib/manifest'
import { changedCount, initiallyOpen, noMatch, sidebarGroups, sidebarOrder } from '../app/lib/sidebar'

function entry(name: string, title: string | null, extra: Partial<BlickEntry> = {}): BlickEntry {
  const definition = title === null ? null : { title, description: null, tags: [], plot: { type: 'line', mapping: {} } }
  return { id: name, name, aliases: [], group: name.split('/')[0]!, definition, columns: null, controls: [], problems: [], status: 'ok', ...extra } as unknown as BlickEntry
}

function compared(name: string, flags: Flag[], magnitude: number | null = null): BlickComparison {
  return { name, change: { flags, magnitude }, skipped: false } as unknown as BlickComparison
}

const group = (name: string, title: string | null, tags: string[] = []) => ({ name, title, tags, modules: [] }) as Group
const skipped = (name: string, title: string | null = name) => entry(name, title, { status: 'skipped', skipped: 'a steel run; this Blick reads cement runs' })

// The manifest lists the Blicks of a group apart, as a build of several modules does.
const manifest: Pick<Manifest, 'groups' | 'blicks'> = {
  groups: [group('drivers', 'Drivers and scenario parameters'), group('flows', null, ['mfa']), group('stocks', 'In-use stocks')],
  blicks: [
    entry('drivers/gdp', 'GDP per capita'),
    entry('flows/production', 'Production by source'),
    entry('stocks/by_region', 'In-use stock by region'),
    entry('flows/consumption', null),
    entry('flows/broken', null, { id: null, status: 'error' }),
    skipped('flows/trade', 'Trade'),
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
    expect(groups[1]!.entries.map(e => e.label)).toEqual(['Production by source', 'flows/consumption', 'flows/broken', 'Trade'])
  })

  it('badges the flag a Blick is ranked by, and a Blick in error that no comparison flags', () => {
    const flows = sidebarGroups(manifest, changes, new Set(), '', false)[1]!.entries
    expect(flows.map(e => e.badge?.label)).toEqual(['Δ 2.1%', 'new', 'error', undefined])
    expect(sidebarGroups(manifest, changes, new Set(), '', false)[0]!.entries[0]!.badge).toBeNull()
  })

  it('mutes a skipped Blick that no comparison flags, and badges one that the comparison removes', () => {
    const flows = sidebarGroups(manifest, changes, new Set(), '', false)[1]!.entries
    expect(flows.map(e => e.muted)).toEqual([false, false, false, true])
    const removed = new Map([...changes, ['flows/trade', { ...compared('flows/trade', ['removed']), skipped: true }]])
    const kept = sidebarGroups(manifest, removed, new Set(), '', true)[0]!.entries
    expect(kept.map(e => [e.entry.name, e.badge?.label, e.muted])).toEqual([
      ['flows/production', 'Δ 2.1%', false],
      ['flows/consumption', 'new', false],
      ['flows/trade', 'removed', false],
    ])
    expect(kept[2]!.badge!.spoken).toBe('removed, skipped for this run')
    expect(changedCount(manifest, removed)).toBe(3)
  })

  it('opens at first every group but those whose Blicks are all skipped and unflagged', () => {
    const cement = { groups: [...manifest.groups, group('cement', 'Cement')], blicks: [...manifest.blicks, skipped('cement/clinker'), skipped('cement/output')] }
    expect(initiallyOpen(sidebarGroups(cement, changes, new Set(), '', false))).toEqual(['drivers', 'flows', 'stocks'])
    const removed = new Map([...changes, ['cement/output', { ...compared('cement/output', ['removed']), skipped: true }]])
    expect(initiallyOpen(sidebarGroups(cement, removed, new Set(), '', false))).toEqual(['drivers', 'flows', 'stocks', 'cement'])
    // The group of the Blick whose page is shown opens all the same, in its place.
    const first = { ...cement, groups: [group('cement', 'Cement'), ...manifest.groups] }
    expect(initiallyOpen(sidebarGroups(first, changes, new Set(), '', false), ['cement'])).toEqual(['cement', 'drivers', 'flows', 'stocks'])
  })

  it('finds a skipped Blick by the word skipped and by its reason', () => {
    expect(shown('skipped')).toEqual([['flows', ['flows/trade']]])
    expect(shown('cement run')).toEqual([['flows', ['flows/trade']]])
  })

  it('marks the pinned Blicks, and a Blick without an id as without a page', () => {
    const flows = sidebarGroups(manifest, none, new Set(['flows/production']), '', false)[1]!.entries
    expect(flows.map(e => [e.pinned, e.disabled])).toEqual([[true, false], [false, false], [false, true], [false, false]])
  })

  it('searches for every word, in the group\'s tags too, and leaves out the groups without a match', () => {
    expect(shown('STOCK region')).toEqual([['stocks', ['stocks/by_region']]])
    expect(shown('mfa')).toEqual([['flows', ['flows/production', 'flows/consumption', 'flows/broken', 'flows/trade']]])
    expect(shown('stock gdp')).toEqual([])
  })

  it('keeps the flagged Blicks with the filter, and counts them', () => {
    expect(shown('', true)).toEqual([['flows', ['flows/production', 'flows/consumption']]])
    expect(shown('source', true)).toEqual([['flows', ['flows/production']]])
    expect([changedCount(manifest, changes), changedCount(manifest, none)]).toEqual([2, 0])
  })

  it('lists every Blick for a search of blanks, and nothing for a manifest without groups', () => {
    expect(shown('  ').flatMap(([, names]) => names)).toHaveLength(6)
    expect(sidebarGroups({ groups: [], blicks: [] }, none, new Set(), '', false)).toEqual([])
  })

  it('says which of the search and the filter left nothing', () => {
    expect([noMatch(' stock ', true), noMatch('stock', false), noMatch('', true)]).toEqual(["No changed Blick matches 'stock'.", "No Blick matches 'stock'.", 'No changed Blick.'])
  })

  it('orders the Blicks as it lists them', () => {
    expect(sidebarOrder(manifest).map(e => e.name)).toEqual(['drivers/gdp', 'flows/production', 'flows/consumption', 'flows/broken', 'flows/trade', 'stocks/by_region'])
  })
})
