import { describe, expect, it } from 'vitest'
import { utcTime } from '../app/lib/time'

describe('times', () => {
  it('gives a time in UTC, to the minute or to the second', () => {
    expect(utcTime('2026-10-26T10:25:13Z')).toBe('2026-10-26 10:25 UTC')
    expect(utcTime('2026-10-26T11:25:13+01:00', true)).toBe('2026-10-26 10:25:13 UTC')
    expect(utcTime('not a time')).toBe('not a time')
  })
})
