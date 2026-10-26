import { describe, expect, it } from 'vitest'
import type { ControlState } from '../app/lib/controls'
import { badges, baselineTable, buildParts, counts, offered, percent, ranked, schemaDetails, schemaSummary, whereState, whereText, type BlickComparison, type BuildRef, type Change, type Comparison, type Flag } from '../app/lib/comparison'
import type { TableSchema } from '../app/lib/manifest'

function blick(name: string, flags: Flag[], change: Partial<Change> = {}, extra: Partial<BlickComparison> = {}): BlickComparison {
  return {
    id: name,
    name,
    matched: null,
    change: { flags, magnitude: null, columns_added: {}, columns_removed: {}, values_added: {}, values_removed: {}, where: null, ...change },
    message: null,
    baseline_data: null,
    baseline_hash: null,
    ...extra,
  }
}

const build: BuildRef = { id: '0123456789abcdef', run: 'r', profile: 'p', created_at: '2026-10-24T20:02:43.09Z', repository: null, incomplete: false }

function comparison(blicks: BlickComparison[], incomplete: string[] = []): Comparison {
  return { spec: '0.2', blicket: '0', created_at: build.created_at, baseline: build, current: build, incomplete, blicks }
}

describe('ranked', () => {
  it('ranks values by magnitude to two digits, then by name, the other flags after', () => {
    const blicks = [
      blick('a/unchanged', [], { magnitude: 0 }),
      blick('a/error', ['error']),
      blick('b/small', ['value'], { magnitude: 0.0211 }),
      blick('a/small', ['value'], { magnitude: 0.0209 }),
      blick('a/removed', ['removed']),
      blick('a/new', ['new']),
      blick('a/schema', ['schema'], { magnitude: 0.5 }),
      blick('c/large', ['schema', 'value'], { magnitude: 0.3 }),
    ]
    expect(ranked(blicks).map(b => b.name)).toEqual(['c/large', 'a/small', 'b/small', 'a/schema', 'a/new', 'a/removed', 'a/error'])
  })
})

describe('offered', () => {
  it('leaves out the comparisons with a build of the same run', () => {
    const current = { ...build, id: 'fedcba9876543210', run: 'current' }
    const other = { ...comparison([]), current }
    const same = { ...comparison([]), baseline: { ...build, run: 'current' }, current }
    expect(offered([other, same])).toEqual([other])
  })
})

describe('percent', () => {
  it('writes a magnitude as a percent to two significant digits, without an exponent', () => {
    expect([0.020961, 0.25, 1, 0.995, 0.00012, 0].map(percent)).toEqual(['2.1%', '25%', '100%', '100%', '0.012%', '0%'])
  })
})

describe('badges', () => {
  it('labels the value with its share of the chart\'s scale and says what the number is', () => {
    expect(badges(blick('a', ['schema', 'value'], { magnitude: 0.020961 }).change)).toEqual([
      { flag: 'schema', label: 'schema' },
      { flag: 'value', label: 'Δ 2.1% of scale', title: 'largest change: 2.1% of the largest value in its panel' },
    ])
  })
})

describe('counts', () => {
  it('counts the Blicks per flag, the errors last', () => {
    const blicks = [blick('a', []), blick('b', []), blick('c', ['value']), blick('d', ['error']), blick('e', ['error'])]
    expect(counts(comparison(blicks))).toBe('2 unchanged · 1 value · 2 errors')
  })

  it('says when removed Blicks were not judged', () => {
    expect(counts(comparison([blick('a', []), blick('b', ['value'])], ['x failed to import']))).toBe('1 unchanged · 1 value · removed not judged')
  })
})

describe('buildParts', () => {
  it('names the run, the commit as the header does, and the time in UTC', () => {
    const repository = { commit: '604e20c2b01ef0525d750066a39d755754695c8b', branch: null, dirty: true }
    expect(buildParts({ ...build, created_at: '2026-10-24T22:02:43+02:00', repository }))
      .toEqual(['run r', 'Blick code 604e20c', 'uncommitted changes', 'built 2026-10-24 20:02 UTC'])
  })

  it('leaves the commit out without a repository and says when the build is incomplete', () => {
    expect(buildParts({ ...build, incomplete: true })).toEqual(['run r', 'built 2026-10-24 20:02 UTC', 'incomplete'])
  })

  it('leaves the time out when asked', () => {
    expect(buildParts(build, false)).toEqual(['run r'])
  })
})

describe('schemaSummary', () => {
  it('counts the Blicks per value, values found in as many Blicks on one line', () => {
    const summary = schemaSummary(comparison([
      blick('a', ['schema'], { values_added: { Region: ['ATLANTIS', 'MU', 'LEMURIA'] } }),
      blick('b', ['schema'], { values_added: { Region: ['ATLANTIS', 'MU'] } }),
      blick('c', []),
    ]))
    expect(summary).toEqual(['Region \'ATLANTIS\', \'MU\' appeared in 2 Blicks', 'Region \'LEMURIA\' appeared in 1 Blick'])
  })

  it('names the first five values of a line and how many more', () => {
    const summary = schemaSummary(comparison([blick('a', ['schema'], { values_removed: { Time: [2101, 2102, 2103, 2104, 2105, 2106] } })]))
    expect(summary).toEqual(['Time 2101, 2102, 2103, 2104, 2105 and 1 more vanished from 1 Blick'])
  })

  it('names columns with their types, a type change as one that vanished and one that appeared', () => {
    const summary = schemaSummary(comparison([
      blick('a', ['schema'], { columns_added: { unit: 'string', value: 'integer' }, columns_removed: { value: 'float' } }),
    ]))
    expect(summary).toEqual(['columns \'unit\' (string), \'value\' (integer) appeared in 1 Blick', 'column \'value\' (float) vanished from 1 Blick'])
  })

  it('puts the lines of a dimension next to each other, the most Blicks first', () => {
    const summary = schemaSummary(comparison([
      blick('a', ['schema'], { values_added: { Region: ['MU'] } }),
      blick('b', ['schema'], { values_added: { Region: ['ATLANTIS'], Flow: ['Scrap'] } }),
      blick('c', ['schema'], { values_added: { Region: ['ATLANTIS'] } }),
    ]))
    expect(summary).toEqual(['Region \'ATLANTIS\' appeared in 2 Blicks', 'Region \'MU\' appeared in 1 Blick', 'Flow \'Scrap\' appeared in 1 Blick'])
  })
})

describe('schemaDetails', () => {
  it('lists the values per dimension and verb', () => {
    expect(schemaDetails(blick('a', ['schema'], { values_added: { Region: ['ATLANTIS', 'MU'] }, values_removed: { Parameter: ['incineration_rate'] } }).change))
      .toEqual(['Region values \'ATLANTIS\', \'MU\' appeared', 'Parameter value \'incineration_rate\' vanished'])
  })

  it('says after the columns that the baseline is not drawn', () => {
    expect(schemaDetails(blick('a', ['schema'], { columns_added: { Scenario: 'string' }, values_added: { Region: ['MU'] } }).change))
      .toEqual(['column \'Scenario\' (string) appeared; baseline not drawn: the columns differ', 'Region value \'MU\' appeared'])
  })
})

describe('baselineTable', () => {
  const copied = { baseline_data: 'compare/0123456789abcdef/blicks/a.parquet', baseline_hash: 'parquet-sha256:00' }

  it('is the copy of the baseline table', () => {
    expect(baselineTable(blick('a', ['value'], {}, copied))).toEqual({ path: copied.baseline_data, hash: copied.baseline_hash })
  })

  it('is none without a copy', () => {
    expect(baselineTable(blick('a', ['new']))).toBeNull()
  })

  it('is none when the columns changed', () => {
    expect(baselineTable(blick('a', ['schema'], { columns_removed: { unit: 'string' } }, copied))).toBeNull()
  })
})

describe('where', () => {
  const schema: TableSchema = {
    dimensions: [
      { name: 'Parameter', dtype: 'string', values: ['collection', 'landfill'] },
      { name: 'Day', dtype: 'date', values: ['2020-01-01', '2020-01-02'] },
      { name: 'Region', dtype: 'string', values: ['EUR', 'SSA'] },
      { name: 'Flow', dtype: 'string', values: ['Primary', 'Secondary'] },
      { name: 'Time', dtype: 'integer', values: [2050, 2100] },
    ],
    measures: [{ name: 'value', dtype: 'float' }],
  }
  const state: ControlState = { filters: { Parameter: 'collection', Day: '2020-01-01' }, splits: ['Region'], y: 'independent' }
  const mapping = { x: 'Time', y: 'value', color: 'Flow' }

  it('sets the filters to the row, parsing its values, and keeps the splits', () => {
    const where = { Parameter: 'landfill', Day: '2020-01-02', Region: 'SSA', Flow: 'Primary', Time: 2100 }
    expect(whereState(state, where, schema)).toEqual({ filters: { Parameter: 'landfill', Day: '2020-01-02' }, splits: ['Region'], y: 'independent' })
  })

  it('skips a value the dimension lacks', () => {
    expect(whereState(state, { Parameter: 'incineration', Day: '2020-01-02' }, schema)?.filters).toEqual({ Parameter: 'collection', Day: '2020-01-02' })
  })

  it('is null when the controls show the row already', () => {
    expect(whereState(state, { Parameter: 'collection', Region: 'SSA', Time: 2100 }, schema)).toBeNull()
  })

  it('names the panel, the series and the x value with their dimensions', () => {
    expect(whereText({ Flow: 'Primary', Time: 2100, Region: 'SSA' }, { ...state, filters: {} }, mapping)).toBe('Region SSA, Flow Primary, Time 2100')
  })

  it('names the filtered values first', () => {
    expect(whereText({ Time: 2050, Region: 'EUR', Parameter: 'landfill' }, state, mapping)).toBe('Parameter landfill, Region EUR, Time 2050')
  })
})
