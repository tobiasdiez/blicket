import { describe, expect, it } from 'vitest'
import { compile } from 'vega-lite'
import { parse, View } from 'vega'
import type { Dimension, TableSchema } from '../app/lib/manifest'
import type { Row } from '../app/lib/table'
import { barSpec } from '../app/plots/bar'
import { nothingToCompare, PLOT_TYPES } from '../app/plots'
import { changeRows, changeSpec, comparable, exportName } from '../app/plots/change'
import { magnitude } from '../app/plots/layout'
import { lineSpec } from '../app/plots/line'
import { stackedAreaSpec } from '../app/plots/stacked_area'
import { CATEGORICAL, INK } from '../app/plots/theme'
import type { ChangeKind, PlotArgs, Theme } from '../app/plots/types'

// The specs are read loosely: their Vega-Lite types are unions too deep to narrow in a test.
type Any = Record<string, any>

const YEARS = [2020, 2021, 2022]

interface Options {
  splits?: string[]
  y?: 'shared' | 'independent'
  unit?: string | null
  theme?: Theme
  measure?: string
  /** The value of the `i`-th row; by default `i * 1500`. */
  value?: (i: number) => number
  /** The baseline's value of the `i`-th row; without it, no baseline. */
  baseline?: (i: number) => number
}

/** Arguments for a table with every combination of the dimensions' values. */
function args(dimensions: Dimension[], mapping: Record<string, string>, options: Options = {}): PlotArgs {
  const measure = options.measure ?? 'value'
  let table: Row[] = [{}]
  for (const d of dimensions) {
    const cell = (value: Dimension['values'][number]) =>
      d.dtype === 'date' ? new Date(`${value}T00:00:00Z`) : d.dtype === 'datetime' ? new Date(`${value}Z`) : value
    table = table.flatMap(row => d.values.map(value => ({ ...row, [d.name]: cell(value) })))
  }
  table = table.map((row, i) => ({ ...row, [measure]: options.value ? options.value(i) : i * 1.5e3 }))
  const schema: TableSchema = { dimensions, measures: [{ name: measure, dtype: 'float' }] }
  const baseline = options.baseline
  return {
    table,
    baseline: baseline ? table.map((row, i) => ({ ...row, [measure]: baseline(i) })) : null,
    schema,
    mapping: { y: measure, ...mapping },
    unit: options.unit ?? null,
    state: { splits: options.splits ?? [], y: options.y ?? 'shared' },
    theme: options.theme ?? 'light',
    name: 'test',
  }
}

const line = (plotArgs: PlotArgs, width = 800): Any => lineSpec(plotArgs, width) as Any
const area = (plotArgs: PlotArgs, width = 800): Any => stackedAreaSpec(plotArgs, width) as Any
const bars = (plotArgs: PlotArgs, stacked: boolean, width = 800): Any => barSpec(plotArgs, width, stacked) as Any

const year: Dimension = { name: 'Time', dtype: 'integer', values: YEARS }
const region: Dimension = { name: 'Region', dtype: 'string', values: ['USA', 'EUR', 'CHA'] }
const scenario: Dimension = { name: 'Scenario', dtype: 'string', values: ['low', 'high'] }
const many: Dimension = { name: 'Polymer', dtype: 'string', values: 'ABCDEFGHIJ'.split('') }
const twelve: Dimension = { name: 'Area', dtype: 'string', values: 'ABCDEFGHIJKL'.split('') }
const day: Dimension = { name: 'Day', dtype: 'date', values: ['2020-01-01', '2020-01-02'] }
const moment: Dimension = { name: 'Moment', dtype: 'datetime', values: ['2020-01-01T00:00:00', '2020-03-01T00:00:00'] }

/**
 * Compile and run the spec headless; returns the Vega-Lite warnings, the compiled Vega spec, the
 * rows of every dataset, the domains of the x and y scales, and the drawn bars.
 */
async function run(spec: Any): Promise<{ warnings: string[], vega: Any, data: Record<string, Any[]>, x: unknown[], y: unknown[] | undefined, rects: Any[] }> {
  const warnings: string[] = []
  const logger: Any = { level: () => logger, warn: (...m: unknown[]) => warnings.push(m.join(' ')), info: () => logger, debug: () => logger, error: (e: unknown) => { throw e } }
  const vega = compile(spec as never, { logger: logger as never }).spec as Any
  const view = new View(parse(vega), { renderer: 'none' })
  await view.runAsync()
  const data = Object.fromEntries(vega.data.map((d: Any) => [d.name, view.data(d.name)]))
  const x = view.scale('x').domain()
  // A facet with independent y axes has no top-level y scale.
  const y = vega.scales.some((scale: Any) => scale.name === 'y') ? view.scale('y').domain() : undefined
  const rects: Any[] = []
  const visit = (node: Any) => {
    if (node.marktype === 'rect' && node.role === 'mark') rects.push(...node.items)
    for (const item of node.items ?? []) visit(item)
  }
  visit((view.scenegraph() as Any).root)
  view.finalize()
  return { warnings, vega, data, x, y, rects }
}

/** The rows of the dataset with a transform that has the properties of `transform`, such as `{ type: 'pivot' }`. */
function rowsAfter(result: { vega: Any, data: Record<string, Any[]> }, transform: Any): Any[] {
  const found = result.vega.data.find((d: Any) => (d.transform ?? []).some((t: Any) => Object.entries(transform).every(([key, value]) => t[key] === value)))
  return result.data[found.name]!
}

/** The layers of a chart, inside the facet when there is one. */
function layers(spec: Any): Any {
  return (spec.spec ?? spec).layer
}

describe('line', () => {
  it('has integer years on a quantitative axis without padding, colour by display order', async () => {
    const spec = line(args([year, region], { x: 'Time', color: 'Region' }, { unit: 't per year' }))
    expect([spec.facet, spec.height]).toEqual([undefined, 320])
    const x = spec.encoding.x
    expect([x.type, x.axis.format, x.scale.nice, x.scale.zero]).toEqual(['quantitative', 'd', false, false])
    const lines = layers(spec)[0]
    expect(lines.encoding.color.scale.domain).toEqual(['USA', 'EUR', 'CHA'])
    expect(lines.encoding.color.scale.range).toEqual(CATEGORICAL.light.slice(0, 3))
    expect(lines.encoding.y.title).toBe('t per year')
    expect(lines.encoding.y.axis.format).toBe('.3~s')
    expect(lines.encoding.strokeDash).toBeUndefined()
    expect((await run(spec)).warnings).toEqual([])
  })

  it('formats the axis plainly below 1,000', () => {
    const spec = line(args([year], { x: 'Time' }, { value: i => i / 10 }))
    expect(layers(spec)[0].encoding.y.axis.format).toBe('.3~g')
  })

  it('highlights a series from the legend, and a second click clears it', async () => {
    const spec = line(args([year, region], { x: 'Time', color: 'Region' }))
    const lines = layers(spec)[0]
    expect(lines.params[0].bind).toBe('legend')
    expect(lines.encoding.opacity.condition).toEqual({ param: 'focus', value: 1 })
    // Every click toggles; with the boolean, only a shift-click would.
    const toggle = (await run(spec)).vega.signals.find((signal: Any) => signal.name === 'focus_toggle')
    expect(toggle.on[0].update).toBe('true')
  })

  it('lists every series at the hovered x in one tooltip, each value formatted by itself', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { unit: 't' })
    plotArgs.table = plotArgs.table.filter(row => row.Region !== 'EUR')
    const rule = layers(line(plotArgs)).at(-1)
    expect(rule.transform[1]).toEqual({ pivot: '__series', value: '__shown', groupby: ['Time'], op: 'max' })
    expect(rule.encoding.tooltip.map((entry: Any) => entry.title)).toEqual(['Time', 'USA', 'CHA', 'unit'])
    const result = await run(line(plotArgs))
    expect(result.warnings).toEqual([])
    expect(rowsAfter(result, { type: 'pivot' }).map(row => row.USA)).toEqual(['0', '4.5k', '9k'])
  })

  it('names the measure and its unit on the y axis', () => {
    const lines = layers(line(args([year], { x: 'Time' }, { unit: 't', measure: 'mass' })))[0]
    expect(lines.encoding.y.title).toBe('mass [t]')
  })

  it('dashes the line type, and the colours past the eighth', async () => {
    const typed = line(args([year, region, scenario], { x: 'Time', color: 'Region', linetype: 'Scenario' }))
    expect(layers(typed)[0].encoding.strokeDash.scale.domain).toEqual(['low', 'high'])
    const crowded = line(args([year, many], { x: 'Time', color: 'Polymer' }))
    const encoding = layers(crowded)[0].encoding
    expect(encoding.color.scale.range[8]).toBe(encoding.color.scale.range[0])
    expect(encoding.strokeDash.scale.range[8]).not.toEqual(encoding.strokeDash.scale.range[0])
    expect((await run(typed)).warnings).toEqual([])
    expect((await run(crowded)).warnings).toEqual([])
  })

  it('puts as many legend columns in a row as fit', async () => {
    const plotArgs = args([year, many], { x: 'Time', color: 'Polymer' })
    expect((await run(line(plotArgs, 1200))).vega.legends[0].columns).toBe(6)
    expect((await run(line(plotArgs, 120))).vega.legends[0].columns).toBe(2)
  })

  it('puts split dimensions into a top-level facet with the y axis the toggle asks for', async () => {
    for (const y of ['shared', 'independent'] as const) {
      const spec = line(args([year, region, scenario], { x: 'Time', color: 'Region' }, { splits: ['Scenario'], y }), 900)
      expect([spec.facet.field, spec.spec.height]).toEqual(['__panel', 180])
      expect(spec.facet.sort).toEqual(['low', 'high'])
      expect(spec.resolve.scale.y).toBe(y)
      expect(spec.data.values[0].__panel).toBe('low')
      expect((await run(spec)).warnings).toEqual([])
    }
    const two = line(args([year, region, scenario], { x: 'Time' }, { splits: ['Scenario', 'Region'] }), 900)
    expect(two.facet.sort.slice(0, 2)).toEqual(['low · USA', 'low · EUR'])
  })

  it('keeps two panels in a row on a narrow page', () => {
    expect(line(args([year, twelve], { x: 'Time' }, { splits: ['Area'] }), 358).columns).toBe(2)
  })

  it('puts dates on a UTC time axis with day ticks, datetimes without', async () => {
    const dates = line(args([day, region], { x: 'Day', color: 'Region' }))
    expect([dates.encoding.x.type, dates.encoding.x.scale.type]).toEqual(['temporal', 'utc'])
    expect(dates.data.values[0].Day).toEqual(new Date(Date.UTC(2020, 0, 1)))
    expect(dates.encoding.x.axis.tickCount).toEqual({ interval: 'day', step: 1 })
    const times = line(args([moment, region], { x: 'Moment', color: 'Region' }))
    expect([times.encoding.x.type, times.encoding.x.scale.type]).toEqual(['temporal', 'utc'])
    expect(typeof times.encoding.x.axis.tickCount).toBe('number')
    expect(layers(times).at(-1).encoding.tooltip[0].timeUnit).toBe('utcyearmonthdatehoursminutesseconds')
    expect((await run(dates)).warnings).toEqual([])
    expect((await run(times)).warnings).toEqual([])
  })
})

describe('stacked area', () => {
  it('stacks y in the display order of the colour, the hues repeating past eight', async () => {
    const spec = area(args([year, many], { x: 'Time', color: 'Polymer' }))
    const areas = layers(spec)[0]
    expect(areas.mark.type).toBe('area')
    expect(areas.encoding.y.stack).toBe('zero')
    expect(areas.encoding.color.sort).toEqual('ABCDEFGHIJ'.split(''))
    expect(areas.encoding.color.scale.range[8]).toBe(areas.encoding.color.scale.range[0])
    expect(areas.encoding.opacity.condition.param).toBe('focus') // no second colour channel
    expect((await run(spec)).warnings).toEqual([])
  })

  it('splits by date keys', async () => {
    const spec = area(args([year, region, day], { x: 'Time', color: 'Region' }, { splits: ['Day'] }))
    expect(spec.facet.sort).toEqual(['2020-01-01', '2020-01-02'])
    expect((await run(spec)).warnings).toEqual([])
  })

  it('sizes the axis by the stacks: positives and negatives apart, per x and panel', () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { value: i => [5, -3, 4][i % 3]! * 100 })
    // At each year 500 and 400 stack up, -300 stacks down.
    expect(magnitude(plotArgs, 'value', ['Time'])).toBe(900)
    expect(magnitude(plotArgs, 'value', null)).toBe(500)
    expect(layers(area(plotArgs))[0].encoding.y.axis.format).toBe('.3~g')
  })
})

describe('bars', () => {
  it('puts x on an ordinal band in display order and groups by colour', async () => {
    const spec = bars(args([region, scenario], { x: 'Region', color: 'Scenario' }, { unit: 't' }), false)
    expect(spec.encoding.x.type).toBe('ordinal')
    expect(spec.encoding.x.scale.domain).toEqual(['USA', 'EUR', 'CHA'])
    expect(spec.encoding.x.scale.paddingInner).toBeGreaterThan(0.2) // bars no wider than 24 px
    expect(spec.encoding.xOffset.field).toBe('Scenario')
    expect(spec.encoding.y.stack).toBeNull()
    expect(spec.encoding.tooltip.map((entry: Any) => entry.title)).toEqual(['Region', 'Scenario', 't'])
    expect(spec.params.map((param: Any) => param.name)).toEqual(['focus', 'hover'])
    expect((await run(spec)).warnings).toEqual([])
  })

  it('stacks bars no wider than 24 px, integer x as ordinal', async () => {
    const spec = bars(args([year, region, scenario], { x: 'Time', color: 'Region' }, { splits: ['Scenario'] }), true, 1200)
    const inner = spec.spec
    expect(inner.encoding.x.type).toBe('ordinal')
    expect(inner.encoding.x.scale.domain).toEqual(YEARS)
    expect(inner.encoding.y.stack).toBe('zero')
    expect(inner.encoding.xOffset).toBeUndefined()
    expect(inner.mark.width).toBeLessThanOrEqual(24)
    expect((await run(spec)).warnings).toEqual([])
  })

  it('turns x labels upright when they do not fit their slot', () => {
    const plotArgs = args([twelve, scenario], { x: 'Area', color: 'Scenario' })
    expect(bars(plotArgs, true, 1200).encoding.x.axis.labelAngle).toBe(0)
    expect(bars(plotArgs, true, 200).encoding.x.axis.labelAngle).toBe(-90)
  })
})

describe('theme', () => {
  it('draws on the dark surface with the dark palette in dark mode', () => {
    const spec = line(args([year, region], { x: 'Time', color: 'Region' }, { theme: 'dark' }))
    expect(layers(spec)[0].encoding.color.scale.range).toEqual(CATEGORICAL.dark.slice(0, 3))
    expect(spec.config.background).toBe(INK.dark.surface) // opaque, so an exported image keeps it
  })
})

/** The baseline's value of the `i`-th row: the current value, but twice it in the fifth row. */
const sameButFifth = (i: number) => (i === 4 ? 12e3 : i * 1.5e3)
const BASELINE = { filter: { field: '__source', equal: 'baseline' } }
const CURRENT = { filter: { field: '__source', equal: 'current' } }
const GHOST = { condition: { param: 'focus', value: 0.3 }, value: 0.1 }

describe('the baseline of a line chart', () => {
  it('lies behind the lines, wide, faded, solid and in the series colours, clipped to the plot', async () => {
    const spec = line(args([year, many], { x: 'Time', color: 'Polymer' }, { baseline: sameButFifth }))
    const ghost = layers(spec)[0]
    expect(ghost.transform).toEqual([BASELINE])
    expect(ghost.mark).toEqual({ type: 'line', strokeWidth: 6, clip: true })
    expect(ghost.encoding.color.scale).toEqual(layers(spec)[1].encoding.color.scale)
    expect(ghost.encoding.strokeDash).toBeUndefined()
    expect(ghost.encoding.strokeOpacity).toEqual(GHOST)
    expect((await run(spec)).warnings).toEqual([])
  })

  it('draws the current lines, their dots and the crosshair from the current rows', () => {
    const spec = line(args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth }))
    expect(layers(spec).slice(1).map((layer: Any) => layer.transform[0])).toEqual([CURRENT, CURRENT, CURRENT])
  })

  it('keeps the legend click of the colour, whose legend the ghost draws', async () => {
    const spec = line(args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth }))
    expect(layers(spec)[1].encoding.opacity.condition).toEqual({ param: 'focus', value: 1 })
    expect((await run(spec)).vega.signals.map((signal: Any) => signal.name)).toContain('focus_Region_legend')
  })

  it('keeps the legend click of a line type, whose legend the current lines alone draw', async () => {
    const spec = line(args([year, scenario], { x: 'Time', linetype: 'Scenario' }, { baseline: sameButFifth }))
    const result = await run(spec)
    expect(result.warnings).toEqual([])
    expect(result.vega.signals.map((signal: Any) => signal.name)).toContain('focus_Scenario_legend')
  })

  it('fades less on the dark surface', () => {
    const spec = line(args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth, theme: 'dark' }))
    expect(layers(spec)[0].encoding.strokeOpacity.condition.value).toBe(0.4)
  })

  it('fades a single series without a legend highlight', async () => {
    const spec = line(args([year], { x: 'Time' }, { baseline: sameButFifth }))
    expect(layers(spec)[0].encoding.strokeOpacity).toEqual({ value: 0.3 })
    expect((await run(spec)).warnings).toEqual([])
  })

  it('keeps the lines of a line type apart without their dash', async () => {
    const spec = line(args([year, region, scenario], { x: 'Time', color: 'Region', linetype: 'Scenario' }, { baseline: sameButFifth }))
    expect(layers(spec)[0].encoding.detail.field).toBe('Scenario')
    expect(layers(spec)[0].encoding.strokeDash).toBeUndefined()
    expect((await run(spec)).warnings).toEqual([])
  })

  it('names the baseline in the tooltip where the numbers differ', async () => {
    const result = await run(line(args([year, region], { x: 'Time', color: 'Region' }, { unit: 't', baseline: sameButFifth })))
    expect(result.warnings).toEqual([])
    // The rows of EUR are the second, fifth and eighth.
    expect(rowsAfter(result, { type: 'pivot' }).map(row => row.EUR)).toEqual(['1.5k', '6k (baseline 12k)', '10.5k'])
  })

  it('shows its own number for a series the baseline lacks', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth })
    const result = await run(line({ ...plotArgs, baseline: plotArgs.baseline!.filter(row => row.Region !== 'CHA') }))
    expect(rowsAfter(result, { type: 'pivot' }).map(row => row.CHA)).toEqual(['3k', '7.5k', '12k'])
  })

  it('leaves a series only in the baseline out of the tooltip', () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth })
    const rule = layers(line({ ...plotArgs, table: plotArgs.table.filter(row => row.Region !== 'EUR') })).at(-1)
    expect(rule.encoding.tooltip.map((entry: Any) => entry.title)).toEqual(['Time', 'USA', 'CHA'])
  })

  it('names the baseline in the tooltip of a single series', async () => {
    const spec = line(args([year], { x: 'Time' }, { baseline: i => (i === 2 ? 1e3 : i * 1.5e3) }))
    expect(layers(spec).at(-1).encoding.tooltip.at(-1)).toEqual({ field: '__shown', title: 'value' })
    const result = await run(spec)
    expect(result.warnings).toEqual([])
    expect(rowsAfter(result, { as: '__shown' }).map(row => row.__shown)).toEqual(['0', '1.5k', '3k (baseline 1k)'])
  })
})

describe('the baseline of a stacked area', () => {
  it('stacks the baseline as faded areas', async () => {
    const spec = area(args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth }))
    const ghost = layers(spec)[0]
    expect([ghost.transform, ghost.mark.type, ghost.encoding.y.stack, ghost.encoding.fillOpacity]).toEqual([[BASELINE], 'area', 'zero', GHOST])
    expect((await run(spec)).warnings).toEqual([])
  })

  it('draws the current stack as the lines on top of its layers', () => {
    const spec = area(args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth }))
    const tops = layers(spec)[1]
    expect([tops.transform, tops.mark, tops.encoding.y.stack]).toEqual([[CURRENT], { type: 'line' }, 'zero'])
    expect(tops.encoding.color).toEqual(layers(spec)[0].encoding.color)
    expect(tops.encoding.opacity.condition.param).toBe('focus')
  })

  it('names the baseline in the tooltip where the numbers differ', async () => {
    const result = await run(area(args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth })))
    expect(rowsAfter(result, { type: 'pivot' }).map(row => row.EUR)).toEqual(['1.5k', '6k (baseline 12k)', '10.5k'])
  })

  it('draws a single series as a faded area under its line', async () => {
    const spec = area(args([year], { x: 'Time' }, { baseline: sameButFifth }))
    expect(layers(spec).map((layer: Any) => [layer.mark.type, layer.transform[0]])).toEqual([['area', BASELINE], ['line', CURRENT], ['rule', CURRENT]])
    expect((await run(spec)).warnings).toEqual([])
  })

  it('fades a single series without a legend highlight', () => {
    expect(layers(area(args([year], { x: 'Time' }, { baseline: sameButFifth })))[0].encoding.fillOpacity).toEqual({ value: 0.3 })
  })
})

const grouped = () => bars(args([region, scenario], { x: 'Region', color: 'Scenario' }, { baseline: sameButFifth }), false)
const stacked = () => bars(args([year, region], { x: 'Time', color: 'Region' }, { baseline: sameButFifth }), true)

describe('the baseline of bars', () => {
  it('puts wider, faded bars behind grouped bars, each on its bar', async () => {
    const [ghost, current] = grouped().layer
    expect([ghost.transform, ghost.mark.width, ghost.encoding.fillOpacity]).toEqual([[BASELINE], { expr: `1.4 * bandwidth('xOffset')` }, GHOST])
    expect(ghost.encoding.xOffset).toEqual(current.encoding.xOffset)
    expect((await run(grouped())).warnings).toEqual([])
  })

  it('keeps the hover on the current bars and the legend highlight on the first layer', () => {
    const [ghost, current] = grouped().layer
    expect([ghost.params.map((p: Any) => p.name), current.params.map((p: Any) => p.name), current.transform[0]]).toEqual([['focus'], ['hover'], CURRENT])
  })

  it('names the baseline in a bar\'s tooltip where the numbers differ', async () => {
    expect(grouped().layer[1].encoding.tooltip.at(-1)).toEqual({ field: '__shown', title: 'value' })
    expect(rowsAfter(await run(grouped()), { as: '__shown' }).map(row => row.__shown)).toEqual(['0', '1.5k', '3k', '4.5k', '6k (baseline 12k)', '7.5k'])
  })

  it('puts the baseline of grouped bars into panels too', async () => {
    const split = bars(args([region, scenario, year], { x: 'Region', color: 'Scenario' }, { baseline: sameButFifth, splits: ['Time'] }), false)
    expect((await run(split)).warnings).toEqual([])
  })

  it('stacks wider, faded bars behind stacked bars, in their colours', async () => {
    const [ghost, current] = stacked().layer
    expect(ghost.mark.width).toBeCloseTo(current.mark.width * 1.4)
    expect([ghost.encoding.color, ghost.encoding.y.stack, ghost.encoding.fillOpacity]).toEqual([current.encoding.color, 'zero', GHOST])
    expect((await run(stacked())).warnings).toEqual([])
  })

  it('fades the bars of a single series without a legend highlight', async () => {
    const spec = bars(args([region], { x: 'Region' }, { baseline: sameButFifth }), false)
    expect(spec.layer[0].encoding.fillOpacity).toEqual({ value: 0.3 })
    expect((await run(spec)).warnings).toEqual([])
  })

  it('draws nothing behind when the baseline has no rows for the selection', async () => {
    expect((await run(bars({ ...args([region, scenario], { x: 'Region', color: 'Scenario' }), baseline: [] }, false))).warnings).toEqual([])
  })
})

describe('the baseline\'s panels and axis', () => {
  const both = args([year, scenario], { x: 'Time' }, { splits: ['Scenario'], value: i => i / 10, baseline: i => i * 1e4 })
  const current = { ...both, table: both.table.filter(row => row.Scenario === 'low') }

  it('counts the panels over both sources', async () => {
    expect([line({ ...current, baseline: null }, 900).columns, line(current, 900).columns]).toEqual([1, 2])
    expect((await run(line(current, 900))).warnings).toEqual([])
  })

  it('sizes the axis over both sources', () => {
    expect(layers(line({ ...current, baseline: null }, 900))[0].encoding.y.axis.format).toBe('.3~g')
    expect(layers(line(current, 900))[1].encoding.y.axis.format).toBe('.3~s')
  })

  it('sizes a stacked axis by the stacks of each source, not their sum', () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { value: i => [5, -3, 4][i % 3]! * 100, baseline: i => [5, -3, 4][i % 3]! * 100 })
    expect(magnitude(plotArgs, 'value', ['Time'])).toBe(900)
  })
})

/** The baseline's value of the `i`-th row: two thirds of the current value, but twice it in the fifth row. */
const twoThirdsButFifth = (i: number) => (i === 4 ? 12e3 : i * 1e3)
const change = (plotArgs: PlotArgs, type: string, kind: ChangeKind = 'change', width = 800): Any => changeSpec(kind, PLOT_TYPES[type]!.change, plotArgs, width) as Any
const keyed = (values: Record<string, number | null>) => Object.entries(values).map(([Key, value]) => ({ Key, value }))
const yOf = (spec: Any) => layers(spec)[0].encoding.y
const panels = (spec: Any) => [...new Set(spec.data.values.map((row: Any) => row.__panel))]

describe('the change against the baseline', () => {
  const key: Dimension = { name: 'Key', dtype: 'string', values: 'ABCDEFGHIJ'.split('') }
  const joined = (table: Row[], baseline: Row[]) => changeRows({ ...args([key], { x: 'Key' }), table, baseline }).map(row => [row.Key, row.__change, row.__relative])

  it('compares the rows both tables have, a null or NaN as 0 against a value', () => {
    // A relative change is against the baseline's absolute value, and none against a baseline of 0
    // unless nothing changed. G is in the current table only and H in the baseline only, values
    // the other table lacks: no change.
    expect(joined(
      keyed({ A: 3, B: -1, C: null, D: 3, E: 0, F: null, G: 1, I: Number.NaN }),
      keyed({ A: 2, B: -2, C: 4, D: 0, E: null, F: null, H: 5, I: 2 }),
    )).toEqual([
      ['A', 1, 0.5], ['B', 1, 0.5], ['C', -4, -1], ['D', 3, null], ['E', 0, 0], ['F', null, null], ['G', null, null], ['I', -2, -1], ['H', null, null],
    ])
  })

  it('compares a row missing from one table with 0, when the other has all its values', () => {
    const rows = changeRows({ ...args([year, region], { x: 'Time', color: 'Region' }), table: [{ Time: 2020, Region: 'USA', value: 1 }, { Time: 2021, Region: 'EUR', value: 2 }], baseline: [{ Time: 2021, Region: 'USA', value: 3 }, { Time: 2020, Region: 'EUR', value: 0 }] })
    expect(rows.map(row => [row.Time, row.Region, row.__change, row.__relative])).toEqual([[2020, 'USA', 1, null], [2021, 'EUR', 2, null], [2021, 'USA', -3, -1], [2020, 'EUR', 0, 0]])
  })

  it('counts a baseline within a billionth of the largest value compared as 0', () => {
    expect(joined(keyed({ A: 5, B: 0, C: 1e3 }), keyed({ A: 1e-9, B: 1e-9, C: 1e3 }))).toEqual([['A', 5 - 1e-9, null], ['B', -1e-9, 0], ['C', 0, 0]])
    // A small value of a large chart, Recycled at SSA in 1981, is not 0.
    expect(joined(keyed({ A: 260.5, B: 5e8 }), keyed({ A: 288.7, B: 5e8 }))[0]![2]).toBeCloseTo(-0.0977, 4)
    // A row that compares nothing does not count.
    expect(joined(keyed({ A: 2 }), keyed({ A: 0.5, H: 1e12 }))).toEqual([['A', 1.5, 3], ['H', null, null]])
  })

  it('draws no change for a row with a value only one table has', () => {
    const rows = changeRows({ ...args([year, region], { x: 'Time', color: 'Region' }), table: [{ Time: 2020, Region: 'USA', value: 1 }, { Time: 2023, Region: 'USA', value: 2 }], baseline: [{ Time: 2020, Region: 'USA', value: 0 }, { Time: 2020, Region: 'MU', value: 3 }] })
    expect(rows.map(row => [row.Time, row.Region, row.__change])).toEqual([[2020, 'USA', 1], [2023, 'USA', null], [2020, 'MU', null]])
  })

  it('draws lines for line charts and stacked areas, never stacked, in the chart\'s colours', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: twoThirdsButFifth })
    for (const type of ['line', 'stacked_area']) {
      const lines = layers(change(plotArgs, type))[0]
      expect([lines.mark.type, lines.encoding.y.field, lines.encoding.y.stack]).toEqual(['line', '__change', null])
      expect(lines.encoding.color.scale).toEqual(layers(area(plotArgs))[1].encoding.color.scale)
      expect((await run(change(plotArgs, type))).warnings).toEqual([])
    }
  })

  it('draws grouped bars for bars, on the chart\'s x', async () => {
    const plotArgs = args([region, scenario], { x: 'Region', color: 'Scenario' }, { baseline: twoThirdsButFifth })
    for (const kind of ['change', 'relative'] as const) {
      const spec = change(plotArgs, 'bar', kind)
      expect([spec.mark.type, spec.encoding.xOffset.field, spec.encoding.y.stack]).toEqual(['bar', 'Scenario', null])
      expect(spec.encoding.x).toEqual(bars({ ...plotArgs, baseline: null }, false).encoding.x)
      expect((await run(spec)).warnings).toEqual([])
    }
  })

  it('stacks the change of stacked bars, gains up and losses down, and groups the relative change', async () => {
    const plotArgs = args([region, scenario], { x: 'Region', color: 'Scenario' }, { baseline: twoThirdsButFifth })
    const gains = change(plotArgs, 'stacked_bar')
    expect([gains.encoding.y.stack, gains.encoding.xOffset, gains.mark.width]).toEqual(['zero', undefined, bars({ ...plotArgs, baseline: null }, true).mark.width])
    expect(gains.encoding.x).toEqual(bars({ ...plotArgs, baseline: null }, true).encoding.x)
    const relative = change(plotArgs, 'stacked_bar', 'relative')
    expect([relative.encoding.y.stack, relative.encoding.xOffset.field]).toEqual([null, 'Scenario'])
    // With half the inner padding outside, a band's centre is where it is with any padding, so a
    // group stands under its stack.
    expect(relative.encoding.x.scale.paddingOuter).toBe(relative.encoding.x.scale.paddingInner / 2)
    expect((await run(gains)).warnings).toEqual([])
    expect((await run(relative)).warnings).toEqual([])
  })

  it('has the chart\'s legend and its highlight', async () => {
    const plotArgs = args([year, region, scenario], { x: 'Time', color: 'Region', linetype: 'Scenario' }, { baseline: twoThirdsButFifth })
    const result = await run(change(plotArgs, 'line'))
    expect([result.warnings, result.vega.legends.map((legend: Any) => legend.title)]).toEqual([[], ['Region', 'Scenario']])
    expect(result.vega.signals.map((signal: Any) => signal.name)).toContain('focus_Region_legend')
    expect(layers(change(plotArgs, 'line'))[0].encoding.opacity.condition).toEqual({ param: 'focus', value: 1 })
    expect((await run(change(plotArgs, 'bar'))).vega.legends.map((legend: Any) => legend.title)).toEqual(['Region'])
  })

  it('says in its title what it shows, and names the change on the y axis', () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { unit: 't', baseline: twoThirdsButFifth })
    const [absolute, relative] = [change(plotArgs, 'line'), change(plotArgs, 'line', 'relative')]
    expect([absolute.title, relative.title]).toEqual([
      { text: 'Change against the baseline, current minus baseline', limit: 780 },
      { text: 'Relative change against the baseline, as a share of the baseline\'s value', limit: 780 },
    ])
    expect(change(plotArgs, 'line', 'relative', 358).title).toEqual({ text: ['Relative change against the baseline,', 'as a share of the baseline\'s value'], limit: 338 })
    expect([yOf(absolute).title, yOf(absolute).axis.format, yOf(relative).title, yOf(relative).axis.format]).toEqual(['change [t]', '.3~s', 'relative change', '.3~p'])
    expect(yOf(change({ ...plotArgs, unit: null }, 'line')).title).toBe('change')
    expect(change(plotArgs, 'bar').encoding.tooltip.at(-1).title).toBe('change [t]')
  })

  it('draws the zero in the ink of the tick labels, so the sign reads', () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: twoThirdsButFifth, theme: 'dark' })
    expect(yOf(change(plotArgs, 'line')).axis.gridColor).toEqual({ condition: { test: 'datum.value === 0', value: INK.dark.tick }, value: INK.dark.grid })
    expect(change(plotArgs, 'bar', 'relative').encoding.y.axis.gridColor.condition.value).toBe(INK.dark.tick)
    expect(layers(line(plotArgs))[1].encoding.y.axis.gridColor).toBeUndefined()
  })

  it('lines up with the chart\'s panels, lower, with the y axis the toggle asks for', async () => {
    expect(change(args([year, region], { x: 'Time', color: 'Region' }, { baseline: twoThirdsButFifth }), 'line').height).toBe(200)
    for (const y of ['shared', 'independent'] as const) {
      const plotArgs = args([year, region, scenario], { x: 'Time', color: 'Region' }, { splits: ['Scenario'], y, baseline: twoThirdsButFifth })
      const [spec, main] = [change(plotArgs, 'line', 'change', 900), line(plotArgs, 900)]
      expect([spec.facet.field, spec.facet.sort, spec.columns, spec.spec.width, spec.resolve.scale.y, spec.spec.height]).toEqual(['__panel', ['low', 'high'], main.columns, main.spec.width, y, 140])
      expect((await run(spec)).warnings).toEqual([])
    }
  })

  it('keeps the chart\'s x range and panels where one table has a value the other lacks', async () => {
    const plotArgs = args([year, region, scenario], { x: 'Time', color: 'Region' }, { splits: ['Scenario'], baseline: twoThirdsButFifth })
    const sparse = { ...plotArgs, table: plotArgs.table.filter(row => row.Time !== 2020), baseline: plotArgs.baseline!.filter(row => row.Scenario !== 'high') }
    const [spec, main] = [change(sparse, 'line', 'change', 900), line(sparse, 900)]
    expect([panels(spec), spec.columns]).toEqual([panels(main), main.columns])
    const [under, above] = [await run(spec), await run(main)]
    expect([under.warnings, under.x]).toEqual([[], above.x])
  })

  it('draws when no row of one table matches the other\'s, in panels too', async () => {
    const plotArgs = args([year, region, scenario], { x: 'Time', color: 'Region' }, { splits: ['Scenario'], baseline: twoThirdsButFifth })
    const renamed = { ...plotArgs, baseline: plotArgs.baseline!.map(row => ({ ...row, Scenario: `${row.Scenario} (old)` })) }
    for (const type of Object.keys(PLOT_TYPES)) {
      expect((await run(change(renamed, type))).warnings).toEqual([])
    }
  })

  it('draws the change of a row that vanished from a sparse table', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: twoThirdsButFifth })
    // The eighth row, EUR in 2022, vanished.
    const result = await run(change({ ...plotArgs, table: plotArgs.table.filter((_, i) => i !== 7) }, 'line'))
    expect(rowsAfter(result, { type: 'pivot' }).map(row => row.EUR)).toEqual(['+500', '−6k', '−7k'])
  })

  it('writes the change in the tooltip with its sign, without the baseline', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { unit: 't', baseline: twoThirdsButFifth })
    // The rows of EUR are the second, fifth and eighth.
    const absolute = await run(change(plotArgs, 'line'))
    expect(rowsAfter(absolute, { type: 'pivot' }).map(row => row.EUR)).toEqual(['+500', '−6k', '+3.5k'])
    expect(layers(change(plotArgs, 'line')).at(-1).encoding.tooltip.map((entry: Any) => entry.title)).toEqual(['Time', 'USA', 'EUR', 'CHA', 'unit'])
    const relative = await run(change(plotArgs, 'line', 'relative'))
    expect(rowsAfter(relative, { type: 'pivot' }).map(row => row.EUR)).toEqual(['+50%', '−50%', '+50%'])
    expect(rowsAfter(relative, { type: 'pivot' }).map(row => row.USA)).toEqual(['0%', '+50%', '+50%'])
  })

  it('writes the relative change as its axis does, and a dash where there is none', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { value: i => [0, 1, 15][i % 3]!, baseline: i => [0, 0, 1][i % 3]! })
    const relative = rowsAfter(await run(change(plotArgs, 'line', 'relative')), { type: 'pivot' })
    expect([relative.map(row => row.USA), relative.map(row => row.EUR), relative.map(row => row.CHA)]).toEqual([['0%', '0%', '0%'], ['–', '–', '–'], ['+1400%', '+1400%', '+1400%']])
  })

  it('writes the change in a bar\'s tooltip with its sign', async () => {
    const plotArgs = args([region, scenario], { x: 'Region', color: 'Scenario' }, { baseline: twoThirdsButFifth })
    expect(change(plotArgs, 'bar').encoding.tooltip.at(-1)).toEqual({ field: '__shown', title: 'change' })
    expect(rowsAfter(await run(change(plotArgs, 'bar')), { as: '__shown' }).map(row => row.__shown)).toEqual(['0', '+500', '+1k', '+1.5k', '−6k', '+2.5k'])
  })

  it('knows whether any row of the selection has a change', () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: twoThirdsButFifth })
    const renamed = { ...plotArgs, baseline: plotArgs.baseline!.map(row => ({ ...row, Region: `${row.Region} (old)` })) }
    expect([comparable(plotArgs), comparable(renamed)]).toEqual([true, false])
    // Rows in both tables with a null measure in both have no change either.
    const empty = { ...plotArgs, table: plotArgs.table.map(row => ({ ...row, value: null })) }
    expect(comparable({ ...empty, baseline: empty.table })).toBe(false)
    expect([nothingToCompare('line', plotArgs), nothingToCompare('line', renamed), nothingToCompare('line', { ...plotArgs, baseline: [] })]).toEqual([false, true, false])
  })

  it('does not ask a project\'s plot type, whose mapping need not have the built-ins\' channels', () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: twoThirdsButFifth })
    expect(nothingToCompare('sankey', { ...plotArgs, mapping: { source: 'Region', value: 'value' } })).toBe(false)
  })

  it('keeps every panel of the chart, also one without a change, for bars and lines', async () => {
    const latest: Dimension = { name: 'Scenario', dtype: 'string', values: ['new', 'low', 'high'] }
    for (const y of ['shared', 'independent'] as const) {
      const plotArgs = args([year, region, latest], { x: 'Time', color: 'Region' }, { splits: ['Scenario'], y, baseline: twoThirdsButFifth })
      const lacking = { ...plotArgs, baseline: plotArgs.baseline!.filter(row => row.Scenario !== 'new') }
      for (const type of Object.keys(PLOT_TYPES)) {
        const main = await run((type.endsWith('bar') ? bars(lacking, type === 'stacked_bar') : line(lacking)))
        for (const kind of ['change', 'relative'] as const) {
          const result = await run(change(lacking, type, kind))
          expect([result.warnings, result.data.facet_domain!.map(row => row.__panel)]).toEqual([[], main.data.facet_domain!.map(row => row.__panel)])
        }
      }
    }
  })

  it('has 0 on its y axis, also without a change', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { baseline: twoThirdsButFifth })
    const renamed = { ...plotArgs, baseline: plotArgs.baseline!.map(row => ({ ...row, Region: `${row.Region} (old)` })) }
    for (const type of Object.keys(PLOT_TYPES)) {
      for (const kind of ['change', 'relative'] as const) expect((await run(change(renamed, type, kind))).y).toEqual([0, 0])
    }
  })

  it('leaves out the gap of a stacked segment of no height, which would cut the zero line', async () => {
    const plotArgs = args([year, region], { x: 'Time', color: 'Region' }, { value: i => [5, 3, 0][i % 3]!, baseline: i => [5, 1, 0][i % 3]! })
    for (const spec of [bars({ ...plotArgs, baseline: null }, true), change(plotArgs, 'stacked_bar')]) {
      const strokes = (await run(spec)).rects.map(item => [item.height > 0, item.stroke])
      expect(new Set(strokes.map(stroke => JSON.stringify(stroke)))).toEqual(new Set([JSON.stringify([true, INK.light.surface]), JSON.stringify([false, 'transparent'])]))
    }
  })

  it('names its exported images after the change', () => {
    expect([exportName('a', 'change'), exportName('a', 'relative')]).toEqual(['a_change', 'a_relative_change'])
  })

  it('is drawn by every built-in plot type, in both kinds', async () => {
    const plotArgs = args([year, region, scenario], { x: 'Time', color: 'Region' }, { splits: ['Scenario'], baseline: twoThirdsButFifth })
    for (const type of Object.keys(PLOT_TYPES)) {
      for (const kind of ['change', 'relative'] as const) {
        expect((await run(change(plotArgs, type, kind))).warnings).toEqual([])
      }
    }
  })
})

describe('tooltips', () => {
  it('show a dash for a missing number', async () => {
    const plotArgs = args([year], { x: 'Time' }, { value: i => (i === 1 ? Number.NaN : i) })
    const result = await run(line({ ...plotArgs, table: plotArgs.table.map((row, i) => (i === 2 ? { ...row, value: null } : row)) }))
    expect(rowsAfter(result, { as: '__shown' }).map(row => row.__shown)).toEqual(['0', '–', '–'])
  })
})
