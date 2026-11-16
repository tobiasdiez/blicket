import { describe, expect, it } from 'vitest'
import type { Comparison, ExpectationComparison } from '../app/lib/comparison'
import {
  cutNote,
  expectationBadge,
  expectationSection,
  fullSentence,
  isNotMet,
  offends,
  outcomeRows,
  outcomeSentence,
  relatedBy,
  resultCounts,
  tableOrder,
  transitionCounts,
  transitionText,
  valueText,
  worstText,
} from '../app/lib/expectations'
import type { BlickEntry, CheckEntry, Outcome, TableSchema, UnitEntry } from '../app/lib/manifest'
import { isCheck, normalized, reads, unitPath, type Manifest } from '../app/lib/manifest'

const outcome = (extra: Partial<Outcome> = {}): Outcome => ({
  result: 'failed',
  expectation: 'value between 0 and 1',
  evaluated: 2412,
  offending: 3,
  within: 0,
  worst: 1.07,
  distance: 0.07,
  where: { Region: 'SSA', Time: 2050 },
  message: null,
  ...extra,
})
const warned = outcome({ result: 'warning', expectation: 'no rows, by relative, a warning within 1e-09', evaluated: null, offending: 200131, within: 200131, worst: -3.2e-12, distance: 3.2e-12, where: { Model: 'plastics', Flow: 'a => b' } })
const met = outcome({ result: 'met', offending: 0, worst: null, distance: null, where: null })
const unevaluable = outcome({ result: 'error', expectation: 'share at most 1', offending: 0, worst: null, distance: null, where: null, evaluated: null, message: "on= names 'share', which is no column of the table" })

const related = (transition: ExpectationComparison['transition'], current: Outcome | null, baseline: Outcome | null, message: string | null = null): ExpectationComparison => ({ transition, current, baseline, message })

describe('an outcome in words', () => {
  it('counts the offending rows of those evaluated, those within warn_within, and a warning by level', () => {
    expect(outcomeRows(outcome())).toBe('3 of 2,412 rows offend')
    expect(outcomeRows(warned)).toBe('200,131 rows offend, all within warn_within')
    expect(outcomeRows(outcome({ evaluated: null, offending: 1 }))).toBe('1 row offends')
    expect(outcomeRows(outcome({ within: 1 }))).toBe('3 of 2,412 rows offend, 1 within warn_within')
    expect(outcomeRows(outcome({ result: 'warning' }))).toBe('3 of 2,412 rows offend, a warning at level warn')
  })

  it('says the outcome as the terminal does, with the worst row in the viewer\'s words', () => {
    expect(outcomeSentence(outcome())).toBe('3 of 2,412 rows offend: expected value between 0 and 1')
    expect(outcomeSentence(met)).toBe('no row offends: expected value between 0 and 1')
    expect(outcomeSentence(outcome({ result: 'met', offending: 0, evaluated: 0 }))).toBe('no row offends, as no row has a value: expected value between 0 and 1')
    expect(outcomeSentence(unevaluable)).toBe("cannot evaluate share at most 1: on= names 'share', which is no column of the table")
    expect(worstText(outcome())).toBe('worst 1.07 at Region: SSA, Time: 2050')
    expect(worstText(outcome({ worst: null }))).toBe('first at Region: SSA, Time: 2050')
    expect([worstText(met), worstText(unevaluable), worstText(outcome({ worst: null, where: {} }))]).toEqual([null, null, null])
    expect(fullSentence(outcome())).toBe('3 of 2,412 rows offend: expected value between 0 and 1, worst 1.07 at Region: SSA, Time: 2050')
  })

  it('writes the worst value as the tables do, never as the bound it violates', () => {
    expect([valueText(1.07, 0.07), valueText(-3.2e-12, 3.2e-12), valueText(200131, 200131)]).toEqual(['1.07', '−3.2e-12', '200k'])
    // At most 1: 1.0004 is 1 to three digits.
    expect(valueText(1.0004, 1.0004 - 1)).toBe('1.0004')
    expect(valueText(100.00000001, 100.00000001 - 100)).toBe('100.00000001')
    expect(valueText(2000.0004, 2000.0004 - 2000)).toBe('2.0000004k')
    expect(valueText(0.5, null)).toBe('0.5')
  })

  it('tells the outcomes whose rows offend from those not met, which carry a badge', () => {
    expect([offends(outcome()), offends(warned), offends(unevaluable), offends(met), offends(null)]).toEqual([true, true, false, false, false])
    expect([isNotMet(outcome()), isNotMet(warned), isNotMet(unevaluable), isNotMet(met)]).toEqual([true, true, true, false])
  })

  it('badges an outcome that is not met, and none that is met', () => {
    expect(expectationBadge(outcome())).toEqual({ result: 'failed', label: 'failed', wide: 'expectation failed', title: 'an expectation failed', spoken: 'expectation failed' })
    expect(expectationBadge(warned)!.label).toBe('warning')
    expect(expectationBadge(unevaluable)!.wide).toBe('expectation error')
    expect([expectationBadge(met), expectationBadge(null)]).toEqual([null, null])
  })

  it('names the transition against the baseline, and why for a new and a dropped one unless the page says it', () => {
    expect(transitionText(related('broken', outcome(), met))).toBe('broken, was met')
    expect(transitionText(related('still_failing', outcome(), outcome()))).toBe('still failing, was failed')
    expect(transitionText(related('new', outcome(), null, 'not in the baseline'))).toBe('new; not in the baseline')
    const dropped = related('dropped', null, outcome(), 'skipped now: the run has no stocks')
    expect(transitionText(dropped)).toBe('dropped, was failed; skipped now: the run has no stocks')
    expect(transitionText(dropped, false)).toBe('dropped, was failed')
    expect([transitionText(related(null, met, met)), transitionText(null)]).toEqual([null, null])
  })

  it('counts the results the worst first, and the transitions in their order', () => {
    const entries = [outcome(), warned, met, met, unevaluable].map(o => ({ outcome: o }) as UnitEntry)
    expect(resultCounts(entries)).toBe('1 failed · 1 cannot be evaluated · 1 warning · 2 met')
    expect(transitionCounts([related('fixed', met, outcome()), related('broken', outcome(), met), related(null, met, met)])).toBe('1 broken · 1 fixed')
  })
})

function blick(name: string, o: Outcome | null, declared = true): BlickEntry {
  const definition = { title: `Blick ${name}`, expect: declared ? { kind: 'between', on: null, low: 0, high: 1, warn_within: null } : null, plot: { type: 'line', mapping: {} } }
  return { kind: 'Blick', id: name, name, controls: [], definition, outcome: o, rows: 10, status: 'ok' } as unknown as BlickEntry
}

function check(name: string, o: Outcome | null, extra: Partial<CheckEntry> = {}): CheckEntry {
  const definition = { title: `Check ${name}`, expect: { kind: 'no_rows', rows: null, by: null, warn_within: null } }
  return { kind: 'check', id: name, name, definition, outcome: o, rows: 0, columns: null, status: o ? 'ok' : 'skipped', ...extra } as unknown as CheckEntry
}

const comparing = (blicks: [string, ExpectationComparison | null][], checks: [string, ExpectationComparison | null][]) =>
  ({ blicks: blicks.map(([name, expectation]) => ({ name, expectation })), checks: checks.map(([name, expectation]) => ({ name, expectation })) }) as unknown as Comparison

describe('the overview\'s section on the expectations', () => {
  const entries = [blick('flows/split', outcome()), blick('flows/plain', null, false), check('checks/flows', warned), check('checks/balance', met), check('checks/eval', unevaluable), check('checks/stocks', null)]
  const comparison = comparing(
    [['flows/split', related('broken', outcome(), met)]],
    [
      ['checks/flows', related('still_failing', warned, warned)],
      ['checks/balance', related('fixed', met, outcome())],
      ['checks/stocks', related('dropped', null, outcome({ evaluated: null }), 'skipped now: the run has no stocks')],
      ['checks/gone', related('dropped', null, outcome({ evaluated: null, offending: 1 }), 'not in the current build')],
    ],
  )

  it('lists the units not met, the error colour first, then the fixed and the dropped', () => {
    const section = expectationSection(entries, comparison)!
    expect(section.run).toBe('1 failed · 1 cannot be evaluated · 1 warning · 1 met')
    expect(section.baseline).toBe('1 broken · 1 fixed · 1 still failing · 2 dropped')
    expect(section.notMet.map(u => [u.name, u.kind, u.badge?.label, u.transition, u.to])).toEqual([
      ['flows/split', 'Blick', 'failed', 'broken, was met', '/blick/flows/split'],
      ['checks/eval', 'check', 'error', null, '/check/checks/eval'],
      ['checks/flows', 'check', 'warning', 'still failing, was warning', '/check/checks/flows'],
    ])
    expect(section.notMet[0]!.sentence).toBe('3 of 2,412 rows offend: expected value between 0 and 1, worst 1.07 at Region: SSA, Time: 2050')
    expect(section.resolved.map(u => [u.key, u.badge, u.transition, u.to])).toEqual([
      ['check:checks/balance', null, 'fixed, was failed', '/check/checks/balance'],
      ['check:checks/stocks', null, 'dropped, was failed; skipped now: the run has no stocks', '/check/checks/stocks'],
      ['check:checks/gone', null, 'dropped, was failed; not in the current build', null],
    ])
    expect(section.resolved[1]!.sentence).toBe('in the baseline: 3 rows offend: expected value between 0 and 1, worst 1.07 at Region: SSA, Time: 2050')
  })

  it('lists a removed Blick whose expectation is dropped', () => {
    const removed = comparing([['flows/gone', related('dropped', null, outcome(), 'not in the current build')]], [])
    const section = expectationSection([blick('flows/split', met)], removed)!
    expect(section.resolved.map(u => [u.key, u.kind, u.to])).toEqual([['Blick:flows/gone', 'Blick', null]])
  })

  it('lists a unit not met and dropped once', () => {
    const now = comparing([], [['checks/eval', related('dropped', unevaluable, outcome())]])
    const section = expectationSection([check('checks/eval', unevaluable)], now)!
    expect([...section.notMet, ...section.resolved].map(u => u.key)).toEqual(['check:checks/eval'])
    expect(section.notMet[0]!.transition).toBe('dropped, was failed')
  })

  it('shows a silenced expectation when no unit has one any more', () => {
    const silenced = comparing([['flows/split', related('dropped', null, outcome(), 'no expectation now')]], [])
    const section = expectationSection([blick('flows/split', null, false)], silenced)!
    expect([section.run, section.baseline]).toEqual(['no expectation evaluated', '1 dropped'])
    expect(section.resolved.map(u => [u.key, u.transition])).toEqual([['Blick:flows/split', 'dropped, was failed; no expectation now']])
  })

  it('keeps a Blick\'s record and a check\'s apart when they share a name', () => {
    const both = comparing([['units/x', related('broken', outcome(), met)]], [['units/x', related('fixed', met, outcome())]])
    const relatedOf = relatedBy(both)
    expect(relatedOf(check('units/x', met))!.transition).toBe('fixed')
    expect(relatedOf(blick('units/x', outcome()))!.transition).toBe('broken')
    expect(relatedOf(blick('units/y', outcome()))).toBeNull()
  })

  it('says all are met in one line, and is absent without expectations', () => {
    const all = expectationSection([blick('flows/split', met), check('checks/balance', met)], null)!
    expect([all.run, all.notMet, all.resolved, all.baseline]).toEqual(['all 2 expectations met', [], [], ''])
    expect(expectationSection([check('checks/balance', met)], null)!.run).toBe('the expectation is met')
    expect(expectationSection([blick('flows/plain', null, false)], null)).toBeNull()
  })
})

describe('a check\'s table', () => {
  it('says how its rows are ordered, and that an unevaluable expectation was not applied', () => {
    const columns: TableSchema = { dimensions: [], measures: [{ name: 'value', dtype: 'float' }, { name: 'relative', dtype: 'float' }] }
    const by = check('checks/flows', warned, { columns, definition: { title: 'F', expect: { kind: 'no_rows', rows: null, by: 'relative', warn_within: 1e-9 } } as CheckEntry['definition'] })
    expect(tableOrder(by)).toBe('Worst first, by relative.')
    expect(tableOrder(check('checks/one', outcome(), { columns: { dimensions: [], measures: [{ name: 'gap', dtype: 'float' as const }] } }))).toBe('Worst first, by gap.')
    expect(tableOrder(check('checks/many', outcome(), { columns }))).toBe('In the order of their dimensions; nothing ranks the rows.')
    expect(tableOrder(check('checks/eval', unevaluable))).toBe('The rows as the check returned them, in the order of their dimensions; the expectation was not applied.')
  })

  it('says how many of the offending rows the build stored when it cut them', () => {
    expect(cutNote(check('checks/flows', warned, { rows: 100000 }))).toBe('100,000 of 200,131 offending rows are stored')
    expect([cutNote(check('checks/split', outcome({ evaluated: null }), { rows: 3 })), cutNote(check('checks/eval', unevaluable, { rows: 4 })), cutNote(check('checks/met', met))]).toEqual([null, null, null])
  })
})

describe('a manifest as the viewer reads it', () => {
  it('tags each entry with its kind, which gives its page', () => {
    const read = normalized({ spec: '0.3', config: { tolerance: 1e-5, level: 'error' }, groups: [], blicks: [{ id: 'a/b', name: 'a/b' }], checks: [{ id: 'a/c', name: 'a/c' }] } as unknown as Manifest)
    expect(read.blicks.map(b => [b.kind, isCheck(b), unitPath(b)])).toEqual([['Blick', false, '/blick/a/b']])
    expect(read.checks.map(c => [c.kind, isCheck(c), unitPath(c)])).toEqual([['check', true, '/check/a/c']])
    expect(unitPath({ ...read.checks[0]!, id: null })).toBeNull()
  })

  it('reads a manifest of spec 0.2 as one of 0.3 without checks, levels or outcomes', () => {
    const old = { spec: '0.2', config: { tolerance: 1e-5 }, groups: [{ name: 'flows', title: null, tags: [], modules: [] }], blicks: [{ name: 'flows/x', definition: { title: 'X' } }] } as unknown as Manifest
    expect([reads('0.2'), reads('0.3'), reads('0.1')]).toEqual([true, true, false])
    const read = normalized(old)
    expect([read.checks, read.config.level, read.groups[0]!.level, read.blicks[0]!.outcome, read.blicks[0]!.definition!.expect]).toEqual([[], 'error', null, null, null])
  })
})
