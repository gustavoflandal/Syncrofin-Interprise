import type { HealthComponent } from '@/types'

/** How a component's raw value reads: a percentage, or months of runway. */
export function formatComponentValue(c: HealthComponent, locale: string, monthsLabel: string): string {
  if (c.key === 'reserve') {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(c.value)} ${monthsLabel}`
  }
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 }).format(c.value)
}
