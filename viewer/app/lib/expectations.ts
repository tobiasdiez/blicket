// The outcomes of the expectations as the viewer shows them: their badges, counts and sentences,
// the units not met in order, and the transitions against the baseline in words. The sentences
// are those of the terminal's reports, `outcome_sentence` and `outcome_worst` in
// src/blicket/report.py, but that the viewer writes a place as `Region: SSA` and a number as its
// tables do.
import type { Comparison, ExpectationComparison, Transition } from './comparison'
import { unitPath, type CheckEntry, type Outcome, type Result, type UnitEntry, type Value } from './manifest'
import { formatValue } from './table'

/** The results of an outcome that is not met, which a badge shows: its rows offend, or it cannot be evaluated. */
export type NotMet = Exclude<Result, 'met'>

/** An outcome as a badge shows it: `failed`, `error` or `warning`; none when it is met. */
export interface ExpectationBadge {
  result: NotMet
  label: string
  /** The label where there is room for what it is about: `expectation failed`. */
  wide: string
  /** What the badge means, as its tooltip says it. */
  title: string
  /** The badge as words, read after a unit's name: `expectation failed`. */
  spoken: string
}

/** The colour of each result's badge: failed and error in the error colour, warning in the warning colour. */
export const RESULT_COLORS: Record<NotMet, 'error' | 'warning'> = { failed: 'error', error: 'error', warning: 'warning' }

const BADGES: Record<NotMet, Omit<ExpectationBadge, 'result'>> = {
  failed: { label: 'failed', wide: 'expectation failed', title: 'an expectation failed', spoken: 'expectation failed' },
  error: { label: 'error', wide: 'expectation error', title: 'the expectation cannot be evaluated', spoken: 'expectation cannot be evaluated' },
  warning: { label: 'warning', wide: 'expectation warning', title: 'an expectation gave a warning', spoken: 'expectation warned' },
}

/** Whether rows of an outcome offend: it warned or failed, as `Outcome.offends` says in Python. */
export function offends(outcome: Outcome | null | undefined): outcome is Outcome & { result: 'warning' | 'failed' } {
  return outcome?.result === 'warning' || outcome?.result === 'failed'
}

/** Whether an outcome is not met: its rows offend, or it cannot be evaluated; it carries a badge, and the sidebar's "Not met" keeps it. */
export function isNotMet(outcome: Outcome | null | undefined): outcome is Outcome & { result: NotMet } {
  return !!outcome && outcome.result !== 'met'
}

/** The badge of an outcome, `null` when it is met or there is none. */
export function expectationBadge(outcome: Outcome | null | undefined): ExpectationBadge | null {
  return isNotMet(outcome) ? { result: outcome.result, ...BADGES[outcome.result] } : null
}

/**
 * A measure's value as the tables write it, with three significant digits, and more while
 * rounding would move it as far as its `distance` from the bound it violates, so that it never
 * reads as the bound: `1.0004` for a value at most 1.
 */
export function valueText(value: number, distance: number | null): string {
  const enough = (digits: number) => !distance || digits >= 17 || Math.abs(Number(value.toPrecision(digits)) - value) < distance
  let digits = 3
  while (!enough(digits)) digits++
  return formatValue(value, digits)
}

const counted = (n: number) => n.toLocaleString('en')
const rows = (n: number) => `${counted(n)} ${n === 1 ? 'row' : 'rows'}`

/**
 * How many rows offend, of how many a bound was applied to, how many of them lie within
 * `warn_within`, and that the level made them a warning when it did: `3 of 2,412 rows offend`,
 * `200,131 rows offend, all within warn_within`, `1 row offends, a warning at level warn`.
 */
export function outcomeRows(outcome: Outcome): string {
  const n = outcome.offending
  const verb = n === 1 ? 'offends' : 'offend'
  const parts = [outcome.evaluated === null ? `${rows(n)} ${verb}` : `${counted(n)} of ${rows(outcome.evaluated)} ${verb}`]
  if (outcome.within && outcome.within === n) parts.push('all within warn_within')
  else if (outcome.within) parts.push(`${counted(outcome.within)} within warn_within`)
  if (outcome.result === 'warning' && outcome.within < n) parts.push('a warning at level warn')
  return parts.join(', ')
}

/**
 * An outcome in a sentence: `3 of 2,412 rows offend: expected value between 0 and 1`, `no row
 * offends: expected no rows, by value`, `no row offends, as no row has a value: ...`, or why it
 * cannot be evaluated.
 */
export function outcomeSentence(outcome: Outcome): string {
  if (outcome.result === 'error') return `cannot evaluate ${outcome.expectation}: ${outcome.message ?? ''}`
  if (outcome.result === 'met') return `no row offends${outcome.evaluated === 0 ? ', as no row has a value' : ''}: expected ${outcome.expectation}`
  return `${outcomeRows(outcome)}: expected ${outcome.expectation}`
}

/** A row's dimension values as the viewer writes them: `Region: SSA, Time: 2050`. */
export function placeText(where: Record<string, Value>): string {
  return Object.entries(where).map(([name, value]) => `${name}: ${String(value)}`).join(', ')
}

/**
 * Where an outcome's offending rows are worst, `worst 1.07 at Region: SSA, Time: 2050`, or
 * `first at …` when nothing ranks them; `null` for an outcome whose rows do not offend, or with
 * nothing to say.
 */
export function worstText(outcome: Outcome): string | null {
  if (!offends(outcome)) return null
  const at = outcome.where && Object.keys(outcome.where).length ? ` at ${placeText(outcome.where)}` : ''
  if (outcome.worst !== null) return `worst ${valueText(outcome.worst, outcome.distance ?? null)}${at}`
  return at ? `first${at}` : null
}

/** An outcome's sentence with where it is worst: `3 of 2,412 rows offend: expected value between 0 and 1, worst 1.07 at Region: SSA`. */
export function fullSentence(outcome: Outcome): string {
  const worst = worstText(outcome)
  return worst ? `${outcomeSentence(outcome)}, ${worst}` : outcomeSentence(outcome)
}

/** The transitions in the order the counts give them, and as words. */
export const TRANSITIONS: Transition[] = ['broken', 'new', 'fixed', 'still_failing', 'dropped']
export const TRANSITION_WORDS: Record<Transition, string> = { broken: 'broken', new: 'new', fixed: 'fixed', still_failing: 'still failing', dropped: 'dropped' }

/**
 * A transition against the baseline in words, `broken, was met`, `fixed, was failed`, with why a
 * side has no outcome for a new or a dropped one, `dropped, was failed; skipped now: …`, unless
 * `why` is false, where the page says it already; `null` without a transition.
 */
export function transitionText(related: ExpectationComparison | null | undefined, why = true): string | null {
  if (!related?.transition) return null
  const words = [TRANSITION_WORDS[related.transition], ...(related.baseline ? [`was ${related.baseline.result}`] : [])].join(', ')
  const reason = why && (related.transition === 'new' || related.transition === 'dropped') && related.message ? `; ${related.message}` : ''
  return words + reason
}

/** `n` things, `one` or `many` of them. */
const things = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** Whether a unit declares an expectation; a check always does. */
export const hasExpectation = (entry: UnitEntry): boolean => !!entry.definition?.expect

/** How many units have an outcome that is not met, of both kinds. */
export function notMetCount(entries: readonly UnitEntry[]): number {
  return entries.filter(entry => isNotMet(entry.outcome)).length
}

/** How many units have an outcome that cannot be evaluated, of both kinds. */
export function unevaluableCount(entries: readonly UnitEntry[]): number {
  return entries.filter(entry => entry.outcome?.result === 'error').length
}

/** The outcomes per result, the worst first: `1 failed · 1 cannot be evaluated · 2 warnings · 4 met`. */
export function resultCounts(entries: readonly UnitEntry[]): string {
  const of = (result: Result) => entries.filter(entry => entry.outcome?.result === result).length
  return [
    ...(of('failed') ? [`${of('failed')} failed`] : []),
    ...(of('error') ? [`${of('error')} cannot be evaluated`] : []),
    ...(of('warning') ? [things(of('warning'), 'warning', 'warnings')] : []),
    ...(of('met') ? [`${of('met')} met`] : []),
  ].join(' · ')
}

/** The transitions against the baseline, `1 broken · 1 fixed`; empty without any. */
export function transitionCounts(related: Iterable<ExpectationComparison>): string {
  const all = [...related]
  return TRANSITIONS.map(t => [t, all.filter(r => r.transition === t).length] as const)
    .filter(([, n]) => n)
    .map(([t, n]) => `${n} ${TRANSITION_WORDS[t]}`)
    .join(' · ')
}

/**
 * The comparison's record of the expectation of a unit of the build, its Blick's or its check's
 * by name, looked up in maps made once for the comparison.
 */
export function relatedBy(comparison: Comparison | null): (entry: UnitEntry) => ExpectationComparison | null {
  const records = new Map<string, ExpectationComparison | null>([
    ...(comparison?.blicks ?? []).map(unit => [`Blick:${unit.name}`, unit.expectation] as const),
    ...(comparison?.checks ?? []).map(unit => [`check:${unit.name}`, unit.expectation] as const),
  ])
  return entry => records.get(`${entry.kind}:${entry.name}`) ?? null
}

/** A unit in the overview's section on the expectations. */
export interface ListedExpectation {
  /** The unit's kind and name, unique in a section. */
  key: string
  name: string
  /** The title, or the name for a unit without one or of the baseline only. */
  label: string
  kind: 'Blick' | 'check'
  /** The unit's page; none for a unit of the baseline only, or without an id. */
  to: string | null
  badge: ExpectationBadge | null
  /** The outcome now in a sentence with where it is worst; for a dropped one, the baseline's, saying so. */
  sentence: string | null
  /** The transition against the baseline in words. */
  transition: string | null
}

/** The overview's section on the expectations; see `expectationSection`. */
export interface ExpectationSection {
  /** This run's outcomes per result, `2 failed · 1 warning · 4 met`, or `all 6 expectations met`, after "This run:". */
  run: string
  /** The transitions against the baseline, `1 broken · 1 fixed`; empty without any. */
  baseline: string
  /** The units not met, failed and in error first, then warned, each kind in its order. */
  notMet: ListedExpectation[]
  /** The units fixed and dropped against the baseline that are not among them, after them. */
  resolved: ListedExpectation[]
}

// The order of the units not met: the error colour first.
const SEVERITY: Record<NotMet, number> = { failed: 0, error: 1, warning: 2 }
const severity = (entry: UnitEntry) => (isNotMet(entry.outcome) ? SEVERITY[entry.outcome.result] : 3)

/**
 * The overview's section on the expectations of `entries`, the build's units in the sidebar's
 * order, against `comparison`, the comparison shown, whose units of the baseline only, a removed
 * Blick or a check gone, are listed when their expectation is dropped. `null` when no unit has an
 * expectation and the comparison relates none.
 */
export function expectationSection(entries: readonly UnitEntry[], comparison: Comparison | null): ExpectationSection | null {
  // The comparison's units with the kind of the list each is in.
  const compared = [
    ...(comparison?.blicks ?? []).map(unit => ({ unit, kind: 'Blick' as const })),
    ...(comparison?.checks ?? []).map(unit => ({ unit, kind: 'check' as const })),
  ]
  const transitions = compared.flatMap(({ unit }) => (unit.expectation ? [unit.expectation] : []))
  if (!entries.some(hasExpectation) && !transitions.some(related => related.transition)) return null
  const present = new Set(entries.map(entry => `${entry.kind}:${entry.name}`))
  const relatedOf = relatedBy(comparison)
  const listed = (entry: UnitEntry): ListedExpectation => {
    const related = relatedOf(entry)
    const dropped = !entry.outcome && related?.transition === 'dropped' ? related.baseline : null
    return {
      key: `${entry.kind}:${entry.name}`,
      name: entry.name,
      label: entry.definition?.title ?? entry.name,
      kind: entry.kind,
      to: unitPath(entry),
      badge: expectationBadge(entry.outcome),
      sentence: entry.outcome ? fullSentence(entry.outcome) : dropped ? `in the baseline: ${fullSentence(dropped)}` : null,
      transition: transitionText(related),
    }
  }
  const notMet = entries.filter(entry => isNotMet(entry.outcome)).toSorted((a, b) => severity(a) - severity(b))
  const resolved = entries.filter((entry) => {
    const transition = relatedOf(entry)?.transition
    return !isNotMet(entry.outcome) && (transition === 'fixed' || transition === 'dropped')
  })
  const gone = compared
    .filter(({ unit, kind }) => !present.has(`${kind}:${unit.name}`) && unit.expectation?.transition === 'dropped')
    .map(({ unit, kind }): ListedExpectation => ({
      key: `${kind}:${unit.name}`,
      name: unit.name,
      label: unit.name,
      kind,
      to: null,
      badge: null,
      sentence: unit.expectation?.baseline ? `in the baseline: ${fullSentence(unit.expectation.baseline)}` : null,
      transition: transitionText(unit.expectation),
    }))
  const evaluated = entries.filter(entry => entry.outcome !== null).length
  const allMet = evaluated > 0 && !notMet.length
  const run = allMet
    ? (evaluated === 1 ? 'the expectation is met' : `all ${evaluated} expectations met`)
    : resultCounts(entries) || 'no expectation evaluated'
  return { run, baseline: transitionCounts(transitions), notMet: notMet.map(listed), resolved: [...resolved.map(listed), ...gone] }
}

/**
 * How the rows of a check's stored table are ordered, beside DataTable's own note: `worst first,
 * by relative`, or by the order of their dimensions when nothing ranks them; and for an outcome
 * that cannot be evaluated, that they are the rows as the check returned them.
 */
export function tableOrder(entry: CheckEntry): string {
  if (entry.outcome?.result === 'error') return 'The rows as the check returned them, in the order of their dimensions; the expectation was not applied.'
  const expect = entry.definition?.expect
  const named = expect ? (expect.kind === 'no_rows' ? expect.by : expect.on) : null
  const measures = entry.columns?.measures ?? []
  const by = named ?? (measures.length === 1 ? measures[0]!.name : null)
  return by ? `Worst first, by ${by}.` : 'In the order of their dimensions; nothing ranks the rows.'
}

/**
 * How many of a check's offending rows the build stored, when it stored fewer than offend: `100,000
 * of 200,131 offending rows are stored`; `null` otherwise.
 */
export function cutNote(entry: CheckEntry): string | null {
  const outcome = entry.outcome
  if (!offends(outcome)) return null
  const stored = entry.rows ?? 0
  return stored < outcome.offending ? `${counted(stored)} of ${counted(outcome.offending)} offending rows are stored` : null
}
