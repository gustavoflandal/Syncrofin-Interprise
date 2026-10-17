import { parseAmount } from '@/lib/money'

/** What the OCR read from a receipt, in the shape the plugin returns it. */
export interface OcrResult {
  text: string
  lines: {
    text: string
    /** 0 (top of the photo) to 1 (bottom) */
    top: number
    /** 0 (left edge) to 1 (right edge). Missing in older captures: then the order given is kept. */
    left?: number
  }[]
}

export interface ReceiptSuggestion {
  /** Positive decimal string ("100.00"), as the API takes it. */
  amount?: string
  /** YYYY-MM-DD */
  date?: string
  /** Merchant name, ready for the description field. */
  merchant?: string
}

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

/** A number on a line of its own: "59,39", "R$ 59,39", "RS 59.39". */
const MONEY_ONLY = /^(?:R\s?[$S5]\s*)?[\dOo]{1,3}(?:[.,][\dOo]{3})*[.,][\dOo]{2}$/

/**
 * How far apart (a fraction of the photo's height) a label and its number can be. A printed row is about
 * 0.02 to 0.03 high; a tilted photo moves the far end of a row by about 0.01 (see REAL_NFCE_TILTED).
 */
const PAIR_DISTANCE = 0.02

/**
 * A receipt lays out "Valor Total R$ ........ 59,39" as two blocks, a label at the left and a number at the
 * right, and the recognizer returns them as two lines. Matching them by "same top" fails on a tilted photo,
 * so instead each number on a line of its own is attached to the label next to it in reading order (the line
 * just before or after it, to its left, and within PAIR_DISTANCE), taking the closer one.
 *
 * Returns one text per input line, in reading order (top to bottom), with each number appended to its label
 * and the lone number itself dropped. A line with no number to attach is returned as it is.
 */
export function toRows(lines: OcrResult['lines']): string[] {
  const sorted = [...lines].sort((a, b) => a.top - b.top)
  const attached = new Map<number, string[]>()
  const consumed = new Set<number>()

  sorted.forEach((line, i) => {
    if (!MONEY_ONLY.test(line.text.trim())) return
    let best: { index: number; distance: number } | undefined
    for (const j of [i - 1, i + 1]) {
      const label = sorted[j]
      if (!label || MONEY_ONLY.test(label.text.trim())) continue
      if (label.left !== undefined && line.left !== undefined && label.left >= line.left) continue
      const distance = Math.abs(label.top - line.top)
      if (distance <= PAIR_DISTANCE && (!best || distance < best.distance)) best = { index: j, distance }
    }
    if (!best) return
    attached.set(best.index, [...(attached.get(best.index) ?? []), line.text.trim()])
    consumed.add(i)
  })

  return sorted.flatMap((line, i) => (consumed.has(i) ? [] : [[line.text, ...(attached.get(i) ?? [])].join(' ')]))
}

// ---------------------------------------------------------------------------
// Amount
// ---------------------------------------------------------------------------

/** "R$", and what an OCR makes of it on thermal paper: "RS", "R5", "R $". */
const CURRENCY_MARK = /R\s?[$S5]\s*$/i

/** 1.234,56 · 1,234.56 · 45,90 · 100.00. Letters O/o stand in for zeros (an OCR habit). */
const MONEY = /(?<![\dOo.,])[\dOo]{1,3}(?:[.,][\dOo]{3})*[.,][\dOo]{2}(?![\dOo])/g

interface Weighted {
  pattern: RegExp
  weight: number
}

// What makes a line likely to hold the amount that was actually paid.
const POSITIVE: Weighted[] = [
  { pattern: /(?<!SUB)\s?TOTAL/i, weight: 4 },
  { pattern: /D[EÉ]B[I1l]T/i, weight: 4 },
  { pattern: /CR[EÉ]D[I1l]T/i, weight: 4 },
  { pattern: /\bP[I1]X\b/i, weight: 4 },
  { pattern: /VALOR/i, weight: 2 },
  { pattern: /PAGO|PAGAR|PAGAMENTO/i, weight: 1 },
]
// What makes a line one that only looks like it: change, discounts, taxes, subtotals.
const NEGATIVE = /SUB\s?TOTAL|TROCO|DESCONTO|DESC\b|TRIBUT|IMPOST|ICMS|\bISS\b|ACR[EÉ]SC|CASHBACK|LIMITE|SALDO|PARCELA/i

/** Minimum score to suggest anything: an amount with no "R$" and no keyword is just a number. */
const MIN_SCORE = 3

export function findAmount(lines: string[]): string | undefined {
  let best: { value: string; score: number } | undefined

  for (const line of lines) {
    const negative = NEGATIVE.test(line)
    for (const match of line.matchAll(MONEY)) {
      const value = parseAmount(match[0].replace(/[Oo]/g, '0'))
      if (!value) continue
      let score = 0
      if (CURRENCY_MARK.test(line.slice(0, match.index))) score += 3
      for (const { pattern, weight } of POSITIVE) if (pattern.test(line)) score += weight
      if (negative) score -= 6
      if (score < MIN_SCORE) continue
      if (!best || score > best.score || (score === best.score && Number(value) > Number(best.value))) {
        best = { value, score }
      }
    }
  }
  return best?.value
}

// ---------------------------------------------------------------------------
// Date
// ---------------------------------------------------------------------------

// Day and month must start with a real digit: the letter O stands in for a zero only *inside* a number.
// (Without that, the O of "EMISSAO 03/09/2026" starts a bogus match that eats the real date.)
const DATE = /(?<![\d])([0-3][\dOo]|\d)[\s./-]{1,2}([01][\dOo]|\d)[\s./-]{1,2}((?:20)?[\dOo]{2})(?![\d])/g

/** The first plausible date (not in the future), as YYYY-MM-DD. */
export function findDate(lines: string[], now: Date = new Date()): string | undefined {
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  const pad = (n: number) => String(n).padStart(2, '0')
  for (const line of lines) {
    // Every match, not just the first: the "O" of "EMISSAO" can start a bogus one before the real date.
    for (const match of line.matchAll(DATE)) {
      const [day, month, yearRaw] = match.slice(1, 4).map((part) => Number(part.replace(/[Oo]/g, '0')))
      const year = yearRaw < 100 ? 2000 + yearRaw : yearRaw
      const candidate = new Date(year, month - 1, day)
      // new Date rolls 31/02 into March: compare back to reject impossible dates.
      if (candidate.getFullYear() !== year || candidate.getMonth() !== month - 1 || candidate.getDate() !== day) continue
      if (candidate > tomorrow) continue
      return `${year}-${pad(month)}-${pad(day)}`
    }
  }
  return undefined
}

// ---------------------------------------------------------------------------
// Merchant
// ---------------------------------------------------------------------------

/** Lines that are never the merchant: paperwork, addresses, payment plumbing. */
const NOT_MERCHANT =
  /VIA\b|CLIENTE|ESTABELEC|COMPROVANTE|DOCUMENTO|DOCU|FISCAL|CUPOM|NOTA\b|\bNFC|\bNFS|EXTRATO|CNPJ|CPF|\bIE\b|INSC|\bAV\b|AVENIDA|\bRUA\b|\bR\.|RODOVIA|\bCEP\b|TEL\b|FONE|TOTAL|VALOR|D[EÉ]B[I1l]T|CR[EÉ]D[I1l]T|COMPRA|VISA|MASTER|ELO\b|AMEX|HIPER|APROVAD|AUTORIZ|PAYWAVE|CONTACTLESS|\bPIX\b|\bAUT\b|\bNSU\b|\bRRN\b|\bARQC\b|\bATC\b|\bAID\b|\bSN\b|\bEC\b|ONL\b|SEQUENCE|DATA\b|HORA\b|WWW\.|HTTP|@/i

/** The maquininha's own brand is printed on every slip: it is not who was paid. */
const TERMINAL_BRANDS = /^(stone|cielo|rede|getnet|pagseguro|pagbank|sumup|mercado\s?pago|safra\s?pay|infinitepay|ton)$/i

function usable(line: string): boolean {
  const text = line.trim()
  const letters = (text.match(/[A-Za-zÀ-ÿ]/g) ?? []).length
  if (letters < 4 || text.length > 40) return false
  // Mostly letters and spaces: a name, not a code (AUT PAG 09382, SN PBO92...).
  const junk = (text.match(/[^A-Za-zÀ-ÿ\s&'.-]/g) ?? []).length
  if (junk > 1) return false
  if (TERMINAL_BRANDS.test(text) || NOT_MERCHANT.test(text)) return false
  return true
}

function titleCase(text: string): string {
  return text
    .toLowerCase()
    .split(/\s+/)
    .map((word) => (word.length <= 2 && /^(de|da|do|e|em)$/.test(word) ? word : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(' ')
}

/**
 * The line just above the CNPJ is, on almost every slip and cupom, the trade name; failing that,
 * the first line near the top that reads like a name. `lines` must be in reading order.
 */
export function findMerchant(lines: string[]): string | undefined {
  const cnpjAt = lines.findIndex((line) => /CNPJ/i.test(line))
  if (cnpjAt > 0) {
    for (let i = cnpjAt - 1; i >= Math.max(0, cnpjAt - 3); i -= 1) {
      if (usable(lines[i])) return titleCase(lines[i].trim())
    }
  }
  for (const line of lines.slice(0, 12)) {
    if (usable(line)) return titleCase(line.trim())
  }
  return undefined
}

// ---------------------------------------------------------------------------

/** Turns the OCR output into suggestions. Anything it cannot find with confidence is left out. */
export function parseReceipt(ocr: OcrResult, now: Date = new Date()): ReceiptSuggestion {
  // The recognizer returns blocks in its own order; reading order is top to bottom.
  const lines = [...ocr.lines].sort((a, b) => a.top - b.top).map((l) => l.text)
  const suggestion: ReceiptSuggestion = {}
  // The amount is looked for in rows (a label with the number printed beside it) as well as in single lines.
  const amount = findAmount([...toRows(ocr.lines), ...lines])
  const date = findDate(lines, now)
  const merchant = findMerchant(lines)
  if (amount) suggestion.amount = amount
  if (date) suggestion.date = date
  if (merchant) suggestion.merchant = merchant
  return suggestion
}

export function hasSuggestion(s: ReceiptSuggestion): boolean {
  return !!(s.amount || s.date || s.merchant)
}
