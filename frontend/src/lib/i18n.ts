import i18n, { type BackendModule, type ResourceLanguage } from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import ptBR from '@/locales/pt-BR.json'
import en from '@/locales/en.json'

// Keep the default and Brazilian Portuguese bundles available immediately;
// other languages are separate build assets loaded by i18next when selected.
const localeLoaders = import.meta.glob<{ default: ResourceLanguage }>([
  '../locales/*.json', '!../locales/en.json', '!../locales/pt-BR.json',
])

/**
 * What a first-time visitor sees. Portuguese: this is a Brazilian product, and an instance nobody has
 * configured should open in the language of the people it is for. An explicit, persisted choice always wins.
 *
 * `fallbackLng` stays English on purpose: it is what a key missing from a translation falls back to, and
 * that is a different question from which language a stranger gets.
 */
export const DEFAULT_LANGUAGE = 'pt-BR'

// The detector tries its sources in order; the last one is ours and always answers.
const languageDetector = new LanguageDetector()
languageDetector.addDetector({ name: 'productDefault', lookup: () => DEFAULT_LANGUAGE })

function syncHtmlLang(lng: string) {
  document.documentElement.lang = lng
}

export const i18nReady = i18n
  .use<BackendModule>({
    type: 'backend',
    init() {},
    read(language, _namespace, callback) {
      const load = localeLoaders[`../locales/${language}.json`]
      if (!load) {
        callback(null, {})
        return
      }
      load().then(
        ({ default: resource }) => callback(null, resource),
        (error: Error) => callback(error, false),
      )
    },
  })
  .use(languageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'pt-BR': { translation: ptBR },
      en: { translation: en },
    },
    partialBundledLanguages: true,
    // A persisted choice from before the language list was trimmed ("de", "ja"...)
    // is treated as unsupported and resolves to the English fallback instead of
    // setting <html lang> to a language with no bundle.
    supportedLngs: ['en', 'pt-BR', 'es'],
    initAsync: false,
    fallbackLng: 'en',
    // Honour an explicit, persisted choice (querystring/localStorage/cookie), then fall to the product
    // default (pt-BR). The browser's own language is NOT auto-picked: an English browser on a Brazilian
    // company's instance should not flip the interface before anyone has chosen.
    detection: {
      order: ['querystring', 'localStorage', 'cookie', 'productDefault'],
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false,
    },
  })

syncHtmlLang(i18n.language || DEFAULT_LANGUAGE)
i18n.on('languageChanged', syncHtmlLang)

export type SupportedLang = 'pt-BR' | 'en' | 'es'

// Single source of truth for language pickers. When adding a locale, register
// a locale JSON file and add one entry here; every picker stays in sync instead
// of each hand-rolling its own list (the setup screen's button row broke a
// little more with every translation PR before this existed).
export const SUPPORTED_LANGS: { code: SupportedLang; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'pt-BR', label: 'Português (BR)' },
  { code: 'es', label: 'Español' },
]

// Normalise any browser/i18n language tag to one of our supported keys. The
// backend and resource bundles key Portuguese as the region-tagged 'pt-BR'
// while 'en'/'es' are bare, so naively truncating to the primary subtag
// (e.g. 'pt-BR'.split('-')[0] -> 'pt') yields a value neither side recognises
// and silently falls back to English. Match on the primary subtag instead.
// Every Portuguese tag maps to the single pt-BR bundle. A language this build
// no longer ships (a user who picked one before the list was trimmed) falls
// back to English rather than to an empty bundle.
export function resolveSupportedLang(lng?: string | null): SupportedLang {
  const tag = (lng ?? '').toLowerCase()
  if (tag.startsWith('pt')) return 'pt-BR'
  if (tag.startsWith('es')) return 'es'
  return 'en'
}

export default i18n
