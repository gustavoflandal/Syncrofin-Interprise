/** Compact relative-time formatter shared by chat lists and similar
 *  surfaces — "2m ago / 3h ago / yesterday / 4d ago / Mar 14".
 *  Plain Date math, no date library. */
export function formatRelative(iso: string): string {
  const d = new Date(iso)
  const diffMs = Date.now() - d.getTime()
  if (Number.isNaN(diffMs)) return ''
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}h ago`
  const diffD = Math.floor(diffH / 24)
  if (diffD === 1) return 'yesterday'
  if (diffD < 7) return `${diffD}d ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

/**
 * "5 min ago" / "há 5 min" / "hace 5 min": the same idea as `formatRelative`,
 * written in the reader's language. `formatRelative` predates translations and
 * is English-only; use this one for anything a signed-in person reads.
 * `now` is injectable so the result is testable without fake timers.
 */
export function formatRelativeLocalized(iso: string, locale: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((then - now) / 1000) // negative = past
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'short' })
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.trunc(seconds / size), unit)
  }
  return formatter.format(0, 'second') // "now" / "agora" / "ahora"
}
