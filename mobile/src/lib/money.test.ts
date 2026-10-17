import { describe, expect, it } from 'vitest'
import { formatMoney, parseAmount } from '@/lib/money'

describe('parseAmount', () => {
  it.each([
    ['12,50', '12.50'],
    ['12.50', '12.50'],
    ['12', '12.00'],
    ['0,5', '0.50'],
    ['1.234,56', '1234.56'],
    ['1,234.56', '1234.56'],
    ['1.234', '1234.00'],
    ['1,234', '1234.00'],
    ['1.234.567,89', '1234567.89'],
    ['R$ 45,90', '45.90'],
    ['  7,05  ', '7.05'],
    ['007,10', '7.10'],
    [',75', '0.75'],
  ])('%s -> %s', (input, expected) => {
    expect(parseAmount(input)).toBe(expected)
  })

  it.each(['', 'abc', '0', '0,00', '-', ',', 'R$'])('rejects %j (not a positive amount)', (input) => {
    expect(parseAmount(input)).toBeNull()
  })

  it('keeps the exact digits, with no float rounding on the way', () => {
    expect(parseAmount('0,1')).toBe('0.10')
    expect(parseAmount('9007199254740993,01')).toBe('9007199254740993.01')
  })
})

describe('formatMoney', () => {
  it('formats in the given currency and locale', () => {
    expect(formatMoney(1234.5, 'BRL', 'pt-BR').replace(/\s/g, ' ')).toBe('R$ 1.234,50')
  })

  it('does not break on an unknown currency code', () => {
    expect(formatMoney(3, 'XX', 'pt-BR')).toContain('3')
  })
})
