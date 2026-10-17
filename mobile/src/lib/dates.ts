const pad = (n: number) => String(n).padStart(2, '0')

/** Local calendar date as YYYY-MM-DD (never toISOString: that is UTC and shifts the day at night). */
export function isoDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function today(): string {
  return isoDate(new Date())
}

/** First and last day of a month (month is 0-based, like Date). */
export function monthRange(year: number, month: number): { from: string; to: string } {
  return { from: isoDate(new Date(year, month, 1)), to: isoDate(new Date(year, month + 1, 0)) }
}

/** Move a (year, month) pair by `delta` months. */
export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
  const d = new Date(year, month + delta, 1)
  return { year: d.getFullYear(), month: d.getMonth() }
}

/** "2026-09-20" as a local date for display, without the UTC shift of `new Date("2026-09-20")`. */
export function parseIsoDate(value: string): Date {
  const [y, m, d] = value.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}
