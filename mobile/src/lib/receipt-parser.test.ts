import { describe, expect, it } from 'vitest'
import { findAmount, findDate, findMerchant, hasSuggestion, parseReceipt, toRows, type OcrResult } from '@/lib/receipt-parser'
import { REAL_NFCE, REAL_NFCE_TILTED } from '@/lib/nfce-fixture'

const NOW = new Date(2026, 8, 20)

/** Lines in top-to-bottom order, with tops spread evenly. */
function ocr(...lines: string[]): OcrResult {
  return { text: lines.join('\n'), lines: lines.map((text, i) => ({ text, top: i / lines.length })) }
}

// The real output of ML Kit on the Galaxy A55, for a photo of a Stone card slip (the photo the
// upload had already shrunk to 1200x1600). Card and terminal numbers are masked. The line order is
// the recognizer's own, which is not the reading order: `top` puts it right.
const REAL_STONE_SLIP: OcrResult = {
  text: '',
  lines: [
    { text: 'ston', top: 0.334 },
    { text: 'EXTDA 0 DOCUNENTO FISCAL DE N TNDICADO', top: 0.453 },
    { text: 'POSTO TREVAO', top: 0.426 },
    { text: 'CNPJ. 80 200 8 19/000:-31te', top: 0.437 },
    { text: 'AVENIDA FSCE NO KUBITSCEK GE GtIVEIR', top: 0.463 },
    { text: '14050, CIDADE INDUSIRIA. 817030 CURTTEA', top: 0.484 },
    { text: 'PR', top: 0.521 },
    { text: 'COMPRA', top: 0.541 },
    { text: 'VISA - **kA0000', top: 0.659 },
    { text: 'PAYWAVE VISA', top: 0.691 },
    { text: 'stone', top: 0.373 },
    { text: 'STONEID 00000000000000', top: 0.708 },
    { text: 'Apiovado sel senba', top: 0.73 },
    { text: 'ONL', top: 0.821 },
    { text: 'DÉBIT0e RS 100.00', top: 0.598 },
    { text: '06 06.2026 iI 19', top: 0.551 },
    { text: 'AUT PAG 09382:', top: 0.682 },
    { text: 'RRN 25615751 3700', top: 0.766 },
    { text: 'ATC CA3R4', top: 0.806 },
  ],
}

describe('a real slip, as the OCR read it', () => {
  it('finds the amount despite "RS" for "R$" and a dot for the comma', () => {
    expect(parseReceipt(REAL_STONE_SLIP, NOW).amount).toBe('100.00')
  })

  it('finds the date despite the mangled separators', () => {
    expect(parseReceipt(REAL_STONE_SLIP, NOW).date).toBe('2026-06-06')
  })

  it('finds the merchant above the CNPJ, not the terminal brand or the fiscal-document line', () => {
    expect(parseReceipt(REAL_STONE_SLIP, NOW).merchant).toBe('Posto Trevao')
  })
})

describe('a real supermarket cupom fiscal (NFC-e), as the OCR read it', () => {
  it('finds the total although the label and the number came as separate lines', () => {
    // 59,39 appears three times (total, card, received); the row that says "Valor Total" wins, and the
    // item lines (a price with no marker or keyword) and the change (0.00) do not.
    expect(parseReceipt(REAL_NFCE, NOW).amount).toBe('59.39')
  })

  it('finds the merchant above the CNPJ', () => {
    expect(parseReceipt(REAL_NFCE, NOW).merchant).toBe('Pjk Franco e Cia Ltda')
  })

  it('does not invent a date: the visible part of the receipt has none', () => {
    expect(parseReceipt(REAL_NFCE, NOW).date).toBeUndefined()
  })
})

describe('a real cupom fiscal photographed at full resolution, and tilted', () => {
  it('finds the total although the number sits lower than its label (the photo is tilted)', () => {
    expect(parseReceipt(REAL_NFCE_TILTED, NOW).amount).toBe('59.39')
  })

  it('finds the merchant and the issue date printed at the bottom (Emissão 01/08/26)', () => {
    const result = parseReceipt(REAL_NFCE_TILTED, NOW)
    expect(result.merchant).toBe('Pjk Franco e Cia Ltda')
    expect(result.date).toBe('2026-08-01')
  })

  it('attaches each number to its own label, not the one next to it', () => {
    const rows = toRows(REAL_NFCE_TILTED.lines)
    expect(rows).toContain('Valor Total R$ 59,39')
    expect(rows).toContain('Cartao de Debito 59,39')
    expect(rows).toContain('Ualor Troco R$ 0,00')
  })
})

describe('toRows', () => {
  it('joins a label and its number when they sit on the same printed row, left to right', () => {
    const rows = toRows([
      { text: '59,39', top: 0.7235, left: 0.8 },
      { text: 'Valor Total R$', top: 0.7245, left: 0.1 },
    ])
    expect(rows).toEqual(['Valor Total R$ 59,39'])
  })

  it('keeps separate printed rows separate', () => {
    const rows = toRows([
      { text: 'A', top: 0.7, left: 0.1 },
      { text: 'B', top: 0.73, left: 0.1 },
    ])
    expect(rows).toEqual(['A', 'B'])
  })

  it('reads the amount from a split row even when the value is left of the label in the list', () => {
    const result = parseReceipt(
      {
        text: '',
        lines: [
          { text: '45,90', top: 0.5, left: 0.85 },
          { text: 'TOTAL R$', top: 0.501, left: 0.05 },
          { text: 'TROCO R$', top: 0.6, left: 0.05 },
          { text: '4,10', top: 0.6, left: 0.85 },
        ],
      },
      NOW,
    )
    expect(result.amount).toBe('45.90')
  })
})

// The layouts below are written by hand from how such slips usually look. They are not OCR output:
// they test the rules, not the recognizer.
describe('findAmount', () => {
  it('reads a card slip', () => {
    expect(findAmount(['COMPRA APROVADA', 'CREDITO A VISTA', 'VALOR: R$ 45,90'])).toBe('45.90')
  })

  it('prefers the total over what was handed over and the change (cupom fiscal)', () => {
    expect(findAmount(['SUBTOTAL R$ 48,00', 'DESCONTO R$ 2,10', 'VALOR TOTAL R$ 45,90', 'DINHEIRO R$ 50,00', 'TROCO R$ 4,10'])).toBe('45.90')
  })

  it('reads thousands separators in both conventions', () => {
    expect(findAmount(['TOTAL R$ 1.234,56'])).toBe('1234.56')
    expect(findAmount(['TOTAL R$ 1,234.56'])).toBe('1234.56')
  })

  it('reads a Pix receipt', () => {
    expect(findAmount(['Comprovante de Pix', 'Valor R$ 250,00', 'Pix enviado'])).toBe('250.00')
  })

  it('tolerates letters O for zeros', () => {
    expect(findAmount(['TOTAL R$ 1O,OO'])).toBe('10.00')
  })

  it('ignores taxes and installments', () => {
    expect(findAmount(['TRIBUTOS R$ 8,30', 'PARCELA 3 x R$ 33,00'])).toBeUndefined()
  })

  it('suggests nothing for a bare number with no marker or keyword', () => {
    expect(findAmount(['AUT 123,45', 'SN 99,99'])).toBeUndefined()
  })

  it('does not take phone numbers, CNPJ or dates for money', () => {
    expect(findAmount(['CNPJ 80.200.819/0001-31', 'TEL (41) 3333-4444', '06/06/2026 11:19'])).toBeUndefined()
  })
})

describe('findDate', () => {
  it.each([
    ['06/06/2026 11:19', '2026-06-06'],
    ['06.06.2026', '2026-06-06'],
    ['06-06-26', '2026-06-06'],
    ['Data: 1/9/2026', '2026-09-01'],
    ['EMISSAO 03/09/2026', '2026-09-03'], // the O of EMISSAO must not swallow the date
    ['20/09/2026 08:00', '2026-09-20'],
    ['0 6/06/2026', undefined],
  ])('%s -> %s', (input, expected) => {
    expect(findDate([input], NOW)).toBe(expected)
  })

  it('rejects impossible dates and dates in the future', () => {
    expect(findDate(['31/02/2026'], NOW)).toBeUndefined()
    expect(findDate(['15/13/2026'], NOW)).toBeUndefined()
    expect(findDate(['15/01/2027'], NOW)).toBeUndefined()
  })

  it('takes the first plausible date when a line before has none', () => {
    expect(findDate(['CUPOM 000123', 'EMISSAO 03/09/2026'], NOW)).toBe('2026-09-03')
  })

  it('accepts today and tomorrow (clock and time-zone slack), not later', () => {
    expect(findDate(['20/09/2026'], NOW)).toBe('2026-09-20')
    expect(findDate(['21/09/2026'], NOW)).toBe('2026-09-21')
    expect(findDate(['22/09/2026'], NOW)).toBeUndefined()
  })
})

describe('findMerchant', () => {
  it('takes the line above the CNPJ', () => {
    expect(findMerchant(['CUPOM FISCAL', 'PADARIA PAO DOURADO LTDA', 'CNPJ 12.345.678/0001-90', 'RUA DAS FLORES 100'])).toBe('Padaria Pao Dourado Ltda')
  })

  it('falls back to the first name-like line at the top', () => {
    expect(findMerchant(['MERCADO BOM PRECO', 'RUA DAS FLORES 100', 'TOTAL R$ 10,00'])).toBe('Mercado Bom Preco')
  })

  it('skips the terminal brand, addresses and payment plumbing', () => {
    expect(findMerchant(['STONE', 'VIA CLIENTE', 'AVENIDA PAULISTA 1000', 'DEBITO VISA', 'AUT PAG 12345'])).toBeUndefined()
  })

  it('keeps small words lowercase in the title case', () => {
    expect(findMerchant(['CASA DE CARNES DO ZE', 'CNPJ 1'])).toBe('Casa de Carnes do Ze')
  })
})

describe('parseReceipt', () => {
  it('reads in top-to-bottom order whatever order the recognizer used', () => {
    const shuffled: OcrResult = {
      text: '',
      lines: [
        { text: 'TOTAL R$ 10,00', top: 0.8 },
        { text: 'PADARIA CENTRAL', top: 0.1 },
        { text: 'CNPJ 12.345.678/0001-90', top: 0.2 },
      ],
    }
    expect(parseReceipt(shuffled, NOW)).toEqual({ amount: '10.00', merchant: 'Padaria Central' })
  })

  it('returns nothing, without inventing, for text that is not a receipt', () => {
    const result = parseReceipt(ocr('Lorem ipsum', 'dolor sit amet'), NOW)
    expect(result.amount).toBeUndefined()
    expect(result.date).toBeUndefined()
    expect(hasSuggestion(result)).toBe(result.merchant !== undefined)
  })

  it('reports whether there is anything to suggest', () => {
    expect(hasSuggestion({})).toBe(false)
    expect(hasSuggestion({ amount: '1.00' })).toBe(true)
  })
})
