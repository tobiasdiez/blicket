import { describe, expect, it } from 'vitest'
import { compile } from 'vega-lite'
import { parse, View } from 'vega'
import type { Dimension, TableSchema } from '../app/lib/manifest'
import type { Row } from '../app/lib/table'
import { barSpec } from '../app/plots/bar'
import { magnitude } from '../app/plots/layout'
import { lineSpec } from '../app/plots/line'
import { stackedAreaSpec } from '../app/plots/stacked_area'
import { CATEGORICAL, INK } from '../app/plots/theme'
import type { PlotArgs, Theme } from '../app/plots/types'

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
  return {
    table,
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

/** Compile and run the spec headless; returns the Vega-Lite warnings and the compiled Vega spec. */
async function run(spec: Any): Promise<{ warnings: string[], vega: Any }> {
  const warnings: string[] = []
  const logger: Any = { level: () => logger, warn: (...m: unknown[]) => warnings.push(m.join(' ')), info: () => logger, debug: () => logger, error: (e: unknown) => { throw e } }
  const vega = compile(spec as never, { logger: logger as never }).spec as Any
  const view = new View(parse(vega), { renderer: 'none' })
  await view.runAsync()
  view.finalize()
  return { warnings, vega }
}

/** The layers of a chart, inside the facet when there is one. */
function layers(spec: Any): Any {
  return (spec.spec ?? spec).layer
}

describe('line', () => {
  it('has integer years on a quantitative axis without padding, colour by display order', async () => {
    const spec = line(args([year, region], { x: 'Time', color: 'Region' }, { unit: 't per year' }))
    expect(spec.facet).toBeUndefined()
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
    expect(rule.transform[0]).toEqual({ pivot: '__series', value: 'value', groupby: ['Time'] })
    expect(rule.encoding.tooltip.map((entry: Any) => entry.title)).toEqual(['Time', 'USA', 'CHA', 'unit'])
    expect(rule.encoding.tooltip[1].formatType).toBe('blicketNumber')
    expect((await run(line(plotArgs))).warnings).toEqual([])
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
      expect(spec.facet.field).toBe('__panel')
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
