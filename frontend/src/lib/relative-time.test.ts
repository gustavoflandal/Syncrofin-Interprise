import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { formatRelative, formatRelativeLocalized } from '@/lib/relative-time'

const NOW = new Date('2026-06-15T12:00:00.000Z')

/** ISO string for `minutes` before the frozen now. */
function ago(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString()
}

describe('formatRelative', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('collapses anything under a minute to "now"', () => {
    expect(formatRelative(ago(0))).toBe('now')
    expect(formatRelative(ago(0.5))).toBe('now')
  })

  it('counts whole minutes up to an hour', () => {
    expect(formatRelative(ago(1))).toBe('1m ago')
    expect(formatRelative(ago(59))).toBe('59m ago')
  })

  it('switches to hours at sixty minutes', () => {
    expect(formatRelative(ago(60))).toBe('1h ago')
    expect(formatRelative(ago(60 * 23))).toBe('23h ago')
  })

  it('says yesterday for the first full day', () => {
    expect(formatRelative(ago(60 * 24))).toBe('yesterday')
    expect(formatRelative(ago(60 * 47))).toBe('yesterday')
  })

  it('counts days up to a week', () => {
    expect(formatRelative(ago(60 * 48))).toBe('2d ago')
    expect(formatRelative(ago(60 * 24 * 6))).toBe('6d ago')
  })

  it('falls back to a calendar date past a week', () => {
    const result = formatRelative(ago(60 * 24 * 30))
    expect(result).not.toMatch(/ago|now|yesterday/)
    // Formatted in the machine's own locale, so the expectation is built the same
    // way rather than hard-coding an English month name ("May" vs "mai.").
    const then = new Date(Date.now() - 60 * 24 * 30 * 60_000)
    expect(result).toBe(then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }))
  })

  it('returns an empty string for an unparseable timestamp', () => {
    // Never render "NaNm ago" into the UI.
    expect(formatRelative('not a date')).toBe('')
    expect(formatRelative('')).toBe('')
  })
})

describe('formatRelativeLocalized', () => {
  const now = Date.parse('2026-05-20T12:00:00Z')
  const ago = (seconds: number) => new Date(now - seconds * 1000).toISOString()

  it('reads in the language of the interface, not always in English', () => {
    expect(formatRelativeLocalized(ago(300), 'en', now)).toMatch(/5 min/)
    expect(formatRelativeLocalized(ago(300), 'pt-BR', now)).toMatch(/há 5 min/)
    expect(formatRelativeLocalized(ago(300), 'es', now)).toMatch(/hace 5 min/)
  })

  it('picks the largest fitting unit', () => {
    expect(formatRelativeLocalized(ago(3 * 3600), 'en', now)).toMatch(/3 hr/)
    expect(formatRelativeLocalized(ago(2 * 86400), 'en', now)).toMatch(/2 days/)
  })

  it('says "now" for the last few seconds and returns "" for garbage', () => {
    expect(formatRelativeLocalized(ago(5), 'pt-BR', now)).toMatch(/agora/)
    expect(formatRelativeLocalized('not-a-date', 'en', now)).toBe('')
  })
})
