/**
 * An amount as the person typed it ("12,50", "1.234,56", "R$ 1,234.56") turned into the
 * plain decimal string the API takes ("12.50"). Null when it is not a positive amount.
 *
 * Strings, not floats: the value goes to the server exactly as written, with no rounding
 * error on the way.
 */
export function parseAmount(input: string): string | null {
  const cleaned = input.replace(/[^\d.,]/g, '')
  if (!/\d/.test(cleaned)) return null

  // The last "." or "," is the decimal separator only when 1 or 2 digits follow it;
  // otherwise it is a thousands separator ("1.234" is one thousand two hundred and thirty-four).
  const match = /^(.*?)[.,](\d{1,2})$/.exec(cleaned)
  const integerPart = (match ? match[1] : cleaned).replace(/[.,]/g, '')
  const fraction = match ? match[2].padEnd(2, '0') : '00'
  if (!integerPart && !match) return null

  const integer = integerPart.replace(/^0+(?=\d)/, '') || '0'
  const value = `${integer}.${fraction}`
  return Number(value) > 0 ? value : null
}

export function formatMoney(value: number | string, currency: string, locale: string): string {
  const number = typeof value === 'string' ? Number(value) : value
  try {
    return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(number)
  } catch {
    // An unknown currency code must not break the list.
    return `${number.toFixed(2)} ${currency}`
  }
}
