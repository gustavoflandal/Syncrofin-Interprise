import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The rest of the suite pins English (test/setup.ts). These tests are about what a real first visit gets, so
// each one starts from an empty browser and loads i18n fresh: it reads its language once, on load.
async function freshI18n() {
  vi.resetModules()
  const module = await import('@/lib/i18n')
  await module.i18nReady
  return module
}

describe('the default language', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.setItem('i18nextLng', 'en')
  })

  it('is Portuguese for a first-time visitor', async () => {
    const { default: i18n, DEFAULT_LANGUAGE } = await freshI18n()
    expect(DEFAULT_LANGUAGE).toBe('pt-BR')
    expect(i18n.resolvedLanguage).toBe('pt-BR')
    expect(document.documentElement.lang).toBe('pt-BR')
    expect(i18n.t('auth.login')).not.toBe('auth.login')
  })

  it('does not follow an English browser: only an explicit choice changes it', async () => {
    vi.stubGlobal('navigator', { ...navigator, language: 'en-US', languages: ['en-US'] })
    const { default: i18n } = await freshI18n()
    expect(i18n.resolvedLanguage).toBe('pt-BR')
  })

  it('keeps what the person chose', async () => {
    localStorage.setItem('i18nextLng', 'en')
    const { default: i18n } = await freshI18n()
    expect(i18n.resolvedLanguage).toBe('en')
  })

  it('a missing translation still falls back to English, not to a blank', async () => {
    const { default: i18n } = await freshI18n()
    // fallbackLng is a separate decision from the default language.
    expect(i18n.options.fallbackLng).toEqual(['en'])
  })

  it('opens in the Portuguese bundle: the default is one of the two bundled languages', async () => {
    const { default: i18n } = await freshI18n()
    expect(i18n.hasResourceBundle('pt-BR', 'translation')).toBe(true)
  })
})
