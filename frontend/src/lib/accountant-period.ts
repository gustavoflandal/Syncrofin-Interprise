/** Period presets for the accountant export. Kept out of the component file so it
 *  stays a pure, separately-testable module. */
export type PeriodPreset = 'lastMonth' | 'thisMonth' | 'lastQuarter' | 'thisYear' | 'lastYear' | 'custom'

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/**
 * The [start, end] of a preset, both inclusive, as ISO dates.
 *
 * Built from local calendar parts rather than `toISOString()`: that converts
 * to UTC first, which in a UTC-3 timezone turns "the 1st, 22:00" into the
 * 2nd and shifts every boundary by a day.
 */
export function presetRange(preset: Exclude<PeriodPreset, 'custom'>, today = new Date()): [string, string] {
  const y = today.getFullYear()
  const m = today.getMonth()
  switch (preset) {
    case 'thisMonth':
      return [iso(new Date(y, m, 1)), iso(today)]
    case 'lastMonth':
      return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))]
    case 'lastQuarter': {
      const q = Math.floor(m / 3)
      return [iso(new Date(y, (q - 1) * 3, 1)), iso(new Date(y, q * 3, 0))]
    }
    case 'thisYear':
      return [iso(new Date(y, 0, 1)), iso(today)]
    case 'lastYear':
      return [iso(new Date(y - 1, 0, 1)), iso(new Date(y - 1, 11, 31))]
  }
}
