import { describe, expect, it } from 'vitest'
import { isoDate, monthRange, parseIsoDate, shiftMonth } from '@/lib/dates'

describe('dates', () => {
  it('formats a local date without the UTC shift', () => {
    // 23:30 local must stay the same day (toISOString would move it in most time zones).
    expect(isoDate(new Date(2026, 8, 20, 23, 30))).toBe('2026-09-20')
    expect(isoDate(new Date(2026, 0, 1, 0, 5))).toBe('2026-01-01')
  })

  it('gives the first and last day of a month, including leap February', () => {
    expect(monthRange(2026, 8)).toEqual({ from: '2026-09-01', to: '2026-09-30' })
    expect(monthRange(2028, 1)).toEqual({ from: '2028-02-01', to: '2028-02-29' })
    expect(monthRange(2026, 1)).toEqual({ from: '2026-02-01', to: '2026-02-28' })
  })

  it('moves across year boundaries', () => {
    expect(shiftMonth(2026, 0, -1)).toEqual({ year: 2025, month: 11 })
    expect(shiftMonth(2026, 11, 1)).toEqual({ year: 2027, month: 0 })
  })

  it('parses an ISO date as a local date', () => {
    const d = parseIsoDate('2026-09-20')
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 8, 20])
    expect(parseIsoDate('2026-09-20T10:00:00Z').getDate()).toBe(20)
  })
})
