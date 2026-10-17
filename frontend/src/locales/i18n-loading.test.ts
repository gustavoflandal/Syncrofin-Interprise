import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.doUnmock('./es.json')
  vi.resetModules()
  window.history.replaceState({}, '', '/')
})

it('loads a selected locale on demand and keeps English fallback keys', async () => {
  vi.resetModules()
  const { default: i18n, i18nReady } = await import('@/lib/i18n')
  await i18nReady
  expect(i18n.hasResourceBundle('es', 'translation')).toBe(false)
  await i18n.changeLanguage('es')
  expect(i18n.hasResourceBundle('es', 'translation')).toBe(true)
  expect(i18n.t('nav.assets')).toBe((await import('./es.json')).default.nav.assets)
  i18n.addResource('en', 'translation', 'testOnlyFallback', 'English fallback')
  expect(i18n.t('testOnlyFallback')).toBe('English fallback')
  expect(document.documentElement.lang).toBe('es')
})

it('finishes loading a persisted locale before initialization resolves', async () => {
  localStorage.setItem('i18nextLng', 'es')
  vi.resetModules()
  const { default: i18n, i18nReady } = await import('@/lib/i18n')
  await i18nReady
  expect(i18n.language).toBe('es')
  expect(i18n.t('nav.assets')).toBe((await import('./es.json')).default.nav.assets)
  expect(document.documentElement.lang).toBe('es')
})

it('still initializes with English fallback if a selected locale asset fails', async () => {
  localStorage.setItem('i18nextLng', 'es')
  vi.doMock('./es.json', () => { throw new Error('synthetic unavailable locale asset') })
  vi.resetModules()
  const { default: i18n, i18nReady } = await import('@/lib/i18n')
  await i18nReady
  expect(i18n.hasResourceBundle('es', 'translation')).toBe(false)
  expect(i18n.t('nav.assets')).toBe((await import('./en.json')).default.nav.assets)
})
