import { describe, expect, it } from 'vitest'
import { ALL_MESSAGES, pickLang } from '@/lib/i18n'

describe('i18n', () => {
  it('has the same keys in the three languages', () => {
    const keys = (lang: keyof typeof ALL_MESSAGES) => Object.keys(ALL_MESSAGES[lang]).sort()
    expect(keys('en')).toEqual(keys('pt-BR'))
    expect(keys('es')).toEqual(keys('pt-BR'))
  })

  it('has no empty text', () => {
    for (const messages of Object.values(ALL_MESSAGES)) {
      for (const [key, text] of Object.entries(messages)) expect(text, key).not.toBe('')
    }
  })

  it('follows the phone language, with English as the fallback', () => {
    expect(pickLang('pt-BR')).toBe('pt-BR')
    expect(pickLang('pt-PT')).toBe('pt-BR')
    expect(pickLang('es-MX')).toBe('es')
    expect(pickLang('en-US')).toBe('en')
    expect(pickLang('de-DE')).toBe('en')
    expect(pickLang(undefined)).toBe('en')
  })
})
