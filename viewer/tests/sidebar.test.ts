import { describe, expect, it } from 'vitest'
import type { BlickComparison, Flag } from '../app/lib/comparison'
import type { BlickEntry, CheckEntry, Group, Manifest, Outcome, Result } from '../app/lib/manifest'
import { CHECKS, changedCount, filterOptions, footText, initiallyOpen, noMatch, notMetUnits, sidebarChecks, sidebarGroups, sidebarOrder, type SidebarFilter } from '../app/lib/sidebar'

function entry(name: string, title: string | null, extra: Partial<BlickEntry> = {}): BlickEntry {
  const definition = title === null ? null : { title, description: null, tags: [], plot: { type: 'line', mapping: {} } }
  return { id: name, name, aliases: [], group: name.split('/')[0]!, definition, columns: null, controls: [], problems: [], status: 'ok', ...extra } as unknown as BlickEntry
}

function compared(name: string, flags: Flag[], magnitude: number | null = null): BlickComparison {
  return { name, change: { flags, magnitude }, skipped: false } as unknown as BlickComparison
}

const group = (name: string, title: string | null, tags: string[] = []): Group => ({ name, title, tags, modules: [], level: null })
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
const shown = (search: string, filter: SidebarFilter = 'all') => sidebarGroups(manifest, changes, new Set(), search, filter)
  .map(g => [g.value, g.entries.map(e => e.entry.name)])

describe('the sidebar', () => {
  it('lists the groups in manifest order, each with its Blicks, by title or by name', () => {
    const groups = sidebarGroups(manifest, none, new Set(), '', 'all')
    expect(groups.map(g => [g.value, g.label])).toEqual([['drivers', 'Drivers and scenario parameters'], ['flows', 'flows'], ['stocks', 'In-use stocks']])
    expect(groups[1]!.entries.map(e => e.label)).toEqual(['Production by source', 'flows/consumption', 'flows/broken', 'Trade'])
  })

  it('badges the flag a Blick is ranked by, and a Blick in error that no comparison flags', () => {
    const flows = sidebarGroups(manifest, changes, new Set(), '', 'all')[1]!.entries
    expect(flows.map(e => e.badge?.label)).toEqual(['Δ 2.1%', 'new', 'error', undefined])
    expect(sidebarGroups(manifest, changes, new Set(), '', 'all')[0]!.entries[0]!.badge).toBeNull()
  })

  it('mutes a skipped Blick that no comparison flags, and badges one that the comparison removes', () => {
    const flows = sidebarGroups(manifest, changes, new Set(), '', 'all')[1]!.entries
    expect(flows.map(e => e.muted)).toEqual([false, false, false, true])
    const removed = new Map([...changes, ['flows/trade', { ...compared('flows/trade', ['removed']), skipped: true }]])
    const kept = sidebarGroups(manifest, removed, new Set(), '', 'changed')[0]!.entries
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
    expect(initiallyOpen(sidebarGroups(cement, changes, new Set(), '', 'all'))).toEqual(['drivers', 'flows', 'stocks'])
    const removed = new Map([...changes, ['cement/output', { ...compared('cement/output', ['removed']), skipped: true }]])
    expect(initiallyOpen(sidebarGroups(cement, removed, new Set(), '', 'all'))).toEqual(['drivers', 'flows', 'stocks', 'cement'])
    // The group of the Blick whose page is shown opens all the same, in its place.
    const first = { ...cement, groups: [group('cement', 'Cement'), ...manifest.groups] }
    expect(initiallyOpen(sidebarGroups(first, changes, new Set(), '', 'all'), ['cement'])).toEqual(['cement', 'drivers', 'flows', 'stocks'])
  })

  it('finds a skipped Blick by the word skipped and by its reason', () => {
    expect(shown('skipped')).toEqual([['flows', ['flows/trade']]])
    expect(shown('cement run')).toEqual([['flows', ['flows/trade']]])
  })

  it('marks the pinned Blicks, and a Blick without an id as without a page', () => {
    const flows = sidebarGroups(manifest, none, new Set(['flows/production']), '', 'all')[1]!.entries
    expect(flows.map(e => [e.pinned, e.disabled])).toEqual([[true, false], [false, false], [false, true], [false, false]])
  })

  it('searches for every word, in the group\'s tags too, and leaves out the groups without a match', () => {
    expect(shown('STOCK region')).toEqual([['stocks', ['stocks/by_region']]])
    expect(shown('mfa')).toEqual([['flows', ['flows/production', 'flows/consumption', 'flows/broken', 'flows/trade']]])
    expect(shown('stock gdp')).toEqual([])
  })

  it('keeps the flagged Blicks with the filter, and counts them', () => {
    expect(shown('', 'changed')).toEqual([['flows', ['flows/production', 'flows/consumption']]])
    expect(shown('source', 'changed')).toEqual([['flows', ['flows/production']]])
    expect([changedCount(manifest, changes), changedCount(manifest, none)]).toEqual([2, 0])
  })

  it('lists every Blick for a search of blanks, and nothing for a manifest without groups', () => {
    expect(shown('  ').flatMap(([, names]) => names)).toHaveLength(6)
    expect(sidebarGroups({ groups: [], blicks: [] }, none, new Set(), '', 'all')).toEqual([])
  })

  it('says which of the search and the filter left nothing', () => {
    expect([noMatch(' stock ', 'changed'), noMatch('stock', 'all'), noMatch('', 'changed')]).toEqual(["No changed Blick matches 'stock'.", "No Blick matches 'stock'.", 'No changed Blick.'])
  })

  it('orders the Blicks as it lists them', () => {
    expect(sidebarOrder(manifest).map(e => e.name)).toEqual(['drivers/gdp', 'flows/production', 'flows/consumption', 'flows/broken', 'flows/trade', 'stocks/by_region'])
  })
})

const outcome = (result: Result): Outcome => ({ result, expectation: 'value between 0 and 1', evaluated: 10, offending: result === 'met' ? 0 : 1, within: 0, worst: null, distance: null, where: null, message: null })
const check = (name: string, result: Result | null, extra: Partial<CheckEntry> = {}): CheckEntry => ({
  kind: 'check',
  id: name,
  name,
  aliases: [],
  group: name.split('/')[0]!,
  module: null,
  source: null,
  definition: { title: `Check ${name.split('/')[1]}`, description: null, tags: [], level: null, expect: { kind: 'no_rows', rows: null, by: null, warn_within: null }, dims: null, measures: null },
  level: 'error',
  data: null,
  hash: null,
  rows: 0,
  columns: null,
  outcome: result === null ? null : outcome(result),
  timing_ms: null,
  skipped: null,
  problems: [],
  status: 'ok',
  ...extra,
})

describe('the sidebar with checks', () => {
  const checked = {
    ...manifest,
    blicks: manifest.blicks.map(b => (b.name === 'drivers/gdp' ? { ...b, outcome: outcome('failed') } : b)),
    checks: [
      check('flows/balance', 'met'),
      check('checks/negative', 'warning'),
      check('checks/raising', null, { status: 'error', problems: [{ kind: 'transformation', severity: 'error', source: null, module: null, ids: [], message: 'raised', traceback: null }] }),
      check('checks/stocks', null, { status: 'skipped', skipped: 'the run has no stocks', rows: null }),
      check('checks/unevaluable', 'error'),
    ],
    build: { id: 'x', incomplete: false, loader_ms: 1 },
  }

  it('lists the checks in one section in the manifest\'s order, each with the badge of its outcome', () => {
    const section = sidebarChecks(checked, '', 'all')!
    expect([section.value, section.label]).toEqual([CHECKS, 'Checks'])
    expect(section.entries.map(e => [e.label, e.expectation?.label, e.badge?.label, e.muted, e.to])).toEqual([
      ['Check balance', undefined, undefined, false, '/check/flows/balance'],
      ['Check negative', 'warning', undefined, false, '/check/checks/negative'],
      ['Check raising', undefined, 'error', false, '/check/checks/raising'],
      ['Check stocks', undefined, undefined, true, '/check/checks/stocks'],
      ['Check unevaluable', 'error', undefined, false, '/check/checks/unevaluable'],
    ])
    expect(section.entries[4]!.expectation!.spoken).toBe('expectation cannot be evaluated')
  })

  it('has no section without checks, or when the filter or the search keeps none', () => {
    expect(sidebarChecks({ ...checked, checks: [] }, '', 'all')).toBeNull()
    expect(sidebarChecks(checked, '', 'changed')).toBeNull()
    expect(sidebarChecks(checked, 'nothing like it', 'all')).toBeNull()
  })

  it('searches the checks by their words, the word check and their results', () => {
    expect(sidebarChecks(checked, 'negative', 'all')!.entries.map(e => e.entry.name)).toEqual(['checks/negative'])
    expect(sidebarChecks(checked, 'warning', 'all')!.entries.map(e => e.entry.name)).toEqual(['checks/negative'])
    expect(sidebarChecks(checked, 'check skipped', 'all')!.entries.map(e => e.entry.name)).toEqual(['checks/stocks'])
  })

  it('keeps the Blicks and checks whose expectation is not met with the third state of the filter', () => {
    expect(sidebarGroups(checked, changes, new Set(), '', 'notMet').map(g => [g.value, g.entries.map(e => [e.entry.name, e.expectation?.label, e.badge?.label])])).toEqual([
      ['drivers', [['drivers/gdp', 'failed', undefined]]],
    ])
    expect(sidebarChecks(checked, '', 'notMet')!.entries.map(e => e.entry.name)).toEqual(['checks/negative', 'checks/unevaluable'])
    expect(notMetUnits(checked)).toBe(3)
  })

  it('offers each state of the filter whose count is not 0, and no filter without either', () => {
    expect(filterOptions(2, 3)).toEqual([
      { value: 'all', label: 'All' },
      { value: 'changed', label: 'Changed (2)' },
      { value: 'notMet', label: 'Not met (3)' },
    ])
    expect(filterOptions(0, 1).map(o => o.label)).toEqual(['All', 'Not met (1)'])
    expect(filterOptions(0, 0)).toEqual([])
  })

  it('counts the checks at its foot, and the units with errors and skipped of both kinds', () => {
    // The errors are the units that failed and those whose expectation cannot be evaluated.
    expect(footText(checked, null)).toBe('6 Blicks and 5 checks · 3\u00A0with\u00A0errors · 2\u00A0skipped')
    expect(footText(checked, 3)).toMatch(/^3 of 11 shown · 6 Blicks and 5 checks · /)
    expect(footText({ ...checked, checks: [] }, null)).toBe('6 Blicks · 1\u00A0with\u00A0errors · 1\u00A0skipped')
    // One Blick is a Blick, as one check is a check.
    const one = { ...checked, blicks: checked.blicks.slice(0, 1) }
    expect(footText({ ...one, checks: [] }, null)).toMatch(/^1 Blick( ·|$)/)
    expect(footText({ ...one, checks: checked.checks.slice(0, 1) }, null)).toMatch(/^1 Blick and 1 check( ·|$)/)
    expect(footText({ ...checked, checks: [] }, 2)).toBe('2 of 6 Blicks · 1\u00A0with\u00A0errors · 1\u00A0skipped')
  })

  it('says what the filter of the expectations left nothing of', () => {
    expect(noMatch('', 'notMet')).toBe('No Blick or check with an expectation not met.')
    expect(noMatch('x', 'all', true)).toBe("No Blick or check matches 'x'.")
  })

  it('opens the checks at first unless they are all skipped', () => {
    const groups = [...sidebarGroups(checked, changes, new Set(), '', 'all'), sidebarChecks(checked, '', 'all')!]
    expect(initiallyOpen(groups)).toContain(CHECKS)
    const skippedOnly = sidebarChecks({ ...checked, checks: [check('checks/stocks', null, { status: 'skipped', skipped: 'none', rows: null })] }, '', 'all')!
    expect(initiallyOpen([skippedOnly])).toEqual([])
  })
})
