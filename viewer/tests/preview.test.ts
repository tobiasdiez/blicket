import { describe, expect, it } from 'vitest'
import type { BlickComparison, Flag } from '../app/lib/comparison'
import type { BlickEntry, Control, Dimension, Value } from '../app/lib/manifest'
import { resolvePins } from '../app/lib/pins'
import { pinnedHint, previewCaption, previewLink, previewSections, previewState, skippedLine, troubles } from '../app/lib/preview'

function entry(name: string, extra: Partial<BlickEntry> = {}, mapping: Record<string, string> = { x: 'Time', y: 'value' }): BlickEntry {
  const definition = { title: name.toUpperCase(), description: 'What it shows. And more.', unit: null, tags: [], plot: { type: 'line', mapping }, independent_y: false }
  return { id: name, name, aliases: [], group: 'g', definition, data: `blicks/${name}.parquet`, hash: 'h', columns: null, controls: [], problems: [], status: 'ok', ...extra } as unknown as BlickEntry
}

function compared(name: string, flags: Flag[], magnitude: number | null = null, where: Record<string, Value> | null = null, baseline: string | null = null): BlickComparison {
  const change = { flags, magnitude, columns_added: {}, columns_removed: {}, values_added: {}, values_removed: {}, where }
  return { id: name, name, matched: null, change, skipped: false, message: null, baseline_data: baseline, baseline_hash: null }
}

/** The sections of `entries`, with the comparison's Blicks and the pinned ids as the page has them. */
function sections(entries: BlickEntry[], blicks: BlickComparison[], pins: string[], limit = 6) {
  const changes = new Map(blicks.map(b => [b.name, b]))
  return previewSections(entries, blicks, changes, resolvePins(pins, entries), limit)
}

const names = (cards: { entry: BlickEntry }[]) => cards.map(card => card.entry.name)
const broken = (name: string) => entry(name, { status: 'error', data: null, problems: [{ kind: 'transform', severity: 'error', message: 'NameError: x', source: null, module: null, ids: [], traceback: null }] })
const skipped = (name: string) => entry(name, { status: 'skipped', skipped: 'the run has no trade module\nnor ports', data: null, hash: null })

describe('the overview\'s sections', () => {
  const entries = ['a', 'b', 'c', 'd'].map(name => entry(name))

  it('show the changed Blicks in ranked order, the first as cards and the others listed', () => {
    const shown = sections(entries, [compared('a', ['value'], 0.01), compared('b', ['new']), compared('c', ['value'], 0.5), compared('d', [])], [], 2)
    expect(names(shown.changed!.cards)).toEqual(['c', 'a'])
    expect(shown.changed!.listed).toEqual([{ name: 'b', label: 'B', byName: false, to: '/blick/b', badge: expect.objectContaining({ label: 'new' }), note: null }])
  })

  it('list removed Blicks and Blicks in error by name, with the error, never as a card', () => {
    const shown = sections([...entries, broken('e')], [compared('e', ['error']), compared('gone', ['removed']), compared('a', ['value'], 0.1)], [])
    expect(names(shown.changed!.cards)).toEqual(['a'])
    expect(shown.changed!.listed.map(item => [item.label, item.byName, item.to, item.note])).toEqual([
      ['gone', true, null, null],
      ['e', true, '/blick/e', 'NameError: x'],
    ])
  })

  it('list a skipped Blick the comparison removes by its title, with its page and why it was skipped', () => {
    const shown = sections([...entries, skipped('t')], [{ ...compared('t', ['removed']), skipped: true }, compared('gone', ['removed'])], [])
    expect(shown.changed!.cards).toEqual([])
    expect(shown.changed!.listed.map(item => [item.label, item.byName, item.to, item.badge?.label, item.note])).toEqual([
      ['gone', true, null, 'removed', null],
      ['T', false, '/blick/t', 'removed', 'skipped: the run has no trade module'],
    ])
  })

  it('show a Blick both changed and pinned in both sections, the pinned in the sidebar\'s order', () => {
    const shown = sections(entries, [compared('b', ['value'], 0.1)], ['c', 'b'])
    expect([names(shown.changed!.cards), names(shown.pinned), shown.unpinned]).toEqual([['b'], ['b', 'c'], false])
    expect(shown.pinned[0]!.change!.change.flags).toEqual(['value'])
  })

  it('show a pinned Blick in error or skipped as a card, and a pin through a former id', () => {
    const renamed = entry('f', { aliases: ['old/f'] })
    const shown = sections([...entries, broken('e'), skipped('t'), renamed], [], ['e', 't', 'old/f'])
    expect(names(shown.pinned)).toEqual(['e', 't', 'f'])
  })

  it('fill in nothing while something changed and nothing is pinned', () => {
    const shown = sections(entries, [compared('b', ['value'], 0.1)], ['not in this build'])
    expect([shown.pinned, shown.unpinned]).toEqual([[], true])
  })

  it('fill in the first Blicks with a table while nothing changed and nothing is pinned', () => {
    const shown = sections([broken('a'), skipped('b'), ...entries.slice(2)], [], [], 2)
    expect([shown.changed, names(shown.pinned), shown.unpinned]).toEqual([null, ['c', 'd'], true])
    expect(sections([broken('a')], [compared('a', ['error'])], []).pinned).toEqual([])
    expect(sections([skipped('a')], [compared('a', [])], []).pinned).toEqual([])
  })

  it('sum up the trouble of a build in a line, which skipped Blicks are not', () => {
    const problem = broken('e').problems[0]!
    const warning = { ...problem, severity: 'warning' as const }
    expect(troubles({ blicks: [broken('e'), skipped('t'), entries[0]!], build: { id: 'b', incomplete: true, loader_ms: 0 }, problems: [problem, problem, warning] }))
      .toBe('1 Blick failed to build · build incomplete · 2 errors in files or the project')
    expect(troubles({ blicks: [...entries, skipped('t')], build: { id: 'b', incomplete: false, loader_ms: 0 }, problems: [warning] })).toBe('')
  })

  it('say how many Blicks the run skipped, and when nothing is left to show', () => {
    expect([skippedLine(entries), skippedLine([...entries, skipped('t')]), skippedLine([entries[0]!, skipped('t'), skipped('u')])]).toEqual([
      '',
      '1 of 5 Blicks is skipped for this run.',
      '2 of 3 Blicks are skipped for this run.',
    ])
    expect([skippedLine([skipped('t'), skipped('u')]), skippedLine([skipped('t')])]).toEqual([
      '2 of 2 Blicks are skipped for this run; nothing to show.',
      '1 of 1 Blick is skipped for this run; nothing to show.',
    ])
  })

  it('say how to pin, and which Blicks show while none is pinned', () => {
    expect([pinnedHint(0), pinnedHint(1), pinnedHint(6)]).toEqual([
      'Nothing pinned yet. Pin Blicks on their pages to show them here.',
      'Nothing pinned yet; this is the first Blick. Pin Blicks here or on their pages to choose what shows.',
      'Nothing pinned yet; these are the first six Blicks. Pin Blicks here or on their pages to choose what shows.',
    ])
  })
})

const time: Dimension = { name: 'Time', dtype: 'integer', values: [2020, 2100] }
const flow: Dimension = { name: 'Flow', dtype: 'string', values: ['Primary', 'Recycled'] }
const region: Dimension = { name: 'Region', dtype: 'string', values: ['CAZ', 'SSA'] }
const parameter: Dimension = { name: 'Parameter', dtype: 'string', values: ['collection', 'recycling'] }
const split: Control = { dimension: 'Region', kind: 'split', default: 'CAZ' }
const filter: Control = { dimension: 'Parameter', kind: 'filter', default: 'recycling' }
const columns = (...dimensions: Dimension[]) => ({ dimensions, measures: [{ name: 'value', dtype: 'float' as const }] })

// Production by source as the example draws it: a panel per region, colour by flow.
const source = entry('flows/source', { columns: columns(flow, time, region), controls: [split] }, { x: 'Time', y: 'value', color: 'Flow' })
const largest = compared('flows/source', ['value'], 0.021, { Flow: 'Primary', Time: 2100, Region: 'SSA' }, 'compare/b/flows/source.parquet')
const rates = entry('drivers/rates', { columns: columns(parameter, time, region), controls: [filter, split] })
const plain = entry('drivers/gdp', { columns: columns(time, region) }, { x: 'Time', y: 'value', color: 'Region' })

describe('a card', () => {
  it('turns a split into a filter, and shows the panel a split dimension in `where` names', () => {
    expect(previewState(source, null, 'shared')).toEqual({ state: { filters: { Region: 'CAZ' }, splits: [], y: 'shared' }, largest: false })
    expect(previewState(source, largest, 'shared')).toEqual({ state: { filters: { Region: 'SSA' }, splits: [], y: 'shared' }, largest: true })
  })

  it('shows the largest change where `where` names the panel shown first', () => {
    const there = compared('flows/source', ['value'], 0.021, { Flow: 'Primary', Time: 2100, Region: 'CAZ' })
    const preview = previewState(source, there, 'shared')
    expect([preview!.largest, previewCaption(source, preview, there), previewLink(source, preview, 'shared')]).toEqual([
      true,
      'Region: CAZ · largest change at Flow: Primary, Time: 2100',
      { path: '/blick/flows/source', query: { Region: 'CAZ' } },
    ])
  })

  it('sets a filter control where `where` names it', () => {
    const there = compared('drivers/rates', ['value'], 0.1, { Parameter: 'collection', Region: 'SSA', Time: 2100 })
    expect(previewState(rates, there, 'shared')).toEqual({ state: { filters: { Parameter: 'collection', Region: 'SSA' }, splits: [], y: 'shared' }, largest: true })
  })

  it('leaves the channels\' dimensions of `where`, and values the build lacks, to the chart', () => {
    const bound = compared('flows/source', ['value'], 0.021, { Flow: 'Primary', Time: 2100 })
    expect(previewState(source, bound, 'shared')!.largest).toBe(false)
    const lacking = compared('flows/source', ['value'], 0.021, { Flow: 'Primary', Time: 2100, Region: 'ATLANTIS' })
    expect(previewState(source, lacking, 'shared')).toEqual({ state: { filters: { Region: 'CAZ' }, splits: [], y: 'shared' }, largest: false })
  })

  it('is the plain chart of a Blick without controls, with the y axes it asks for', () => {
    expect(previewState(plain, null, 'independent')).toEqual({ state: { filters: {}, splits: [], y: 'independent' }, largest: false })
    expect(previewState(entry('broken', { status: 'error' }), null, 'shared')).toBeNull()
    expect(previewState(skipped('t'), null, 'shared')).toBeNull()
  })

  it('names the largest change, with the rest of its row, and leads to the page there', () => {
    const preview = previewState(source, largest, 'shared')
    expect([previewCaption(source, preview, largest), previewLink(source, preview, 'shared')]).toEqual([
      'Region: SSA · largest change at Flow: Primary, Time: 2100 · baseline\u00A0faded',
      { path: '/blick/flows/source', query: { Region: 'SSA' } },
    ])
    const gdp = compared('drivers/gdp', ['value'], 0.5, { Region: 'EUR', Time: 2050 })
    expect(previewCaption(plain, previewState(plain, gdp, 'shared'), gdp)).toBe('largest change at Region: EUR, Time: 2050')
  })

  it('says nothing of the baseline for a chart that does not draw it, a Sankey diagram\'s', () => {
    const sankey = entry('flows/sankey', { columns: columns(flow, time, region), controls: [split] }, { source: 'Flow', target: 'Time', value: 'value' })
    const change = compared('flows/sankey', ['value'], 0.021, { Flow: 'Primary', Time: 2100, Region: 'SSA' }, 'compare/b/flows/sankey.parquet')
    const preview = previewState(sankey, change, 'shared')
    expect([previewCaption(sankey, preview, change, false), previewCaption(sankey, preview, change)]).toEqual([
      'Region: SSA · largest change at Flow: Primary, Time: 2100',
      'Region: SSA · largest change at Flow: Primary, Time: 2100 · baseline\u00A0faded',
    ])
  })

  it('names the panel it shows of how many, and leads to the page as laid out', () => {
    const first = previewState(rates, null, 'shared')
    expect([previewCaption(rates, first, null), previewLink(rates, first, 'shared')]).toEqual([
      'Parameter: recycling, Region: CAZ · first of 2 panels',
      { path: '/blick/drivers/rates', query: {} },
    ])
    const later = { ...source, controls: [{ ...split, default: 'SSA' }] }
    expect(previewCaption(later, previewState(later, null, 'shared'), null)).toBe('Region: SSA · one of 2 panels')
  })

  it('is named by the description\'s first sentence without filters or a change', () => {
    expect(previewCaption(plain, previewState(plain, null, 'shared'), null)).toBe('What it shows.')
    expect(previewLink(entry('x', { id: null }), null, 'shared')).toBeNull()
  })
})
