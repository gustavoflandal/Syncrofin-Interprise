import { TOPIC_IDS } from '@/help/topics'

/**
 * Loading the manual's text.
 *
 * Each topic is a Markdown file, one folder per language. Files load lazily (a
 * reader opens one topic, not the whole manual). A language without a folder, or
 * a topic missing from a language's folder, falls back to Portuguese and says so:
 * the manual is written in Portuguese first, and a half-translated manual that
 * silently switched language mid-page would be worse than an honest notice.
 */

export const SOURCE_LANGUAGE = 'pt-BR'

const files = import.meta.glob('./content/*/*.md', {
  query: '?raw',
  import: 'default',
}) as Record<string, () => Promise<string>>

const PATH = /\/content\/([^/]+)\/([^/]+)\.md$/

/** language -> topic id -> loader */
const index = new Map<string, Map<string, () => Promise<string>>>()
for (const [path, loader] of Object.entries(files)) {
  const match = PATH.exec(path)
  if (!match) continue
  const [, language, id] = match
  if (!index.has(language)) index.set(language, new Map())
  index.get(language)!.set(id, loader)
}

export interface HelpDocument {
  id: string
  /** The language the text is actually in (may differ from the one asked for). */
  language: string
  markdown: string
  title: string
  /** True when the reader's language had no version and Portuguese was used. */
  fallback: boolean
}

/** First `# Heading` of a document, which is its title. */
export function titleOf(markdown: string, fallback = ''): string {
  const match = /^#\s+(.+?)\s*$/m.exec(markdown)
  return match ? match[1] : fallback
}

export function availableLanguages(): string[] {
  return [...index.keys()]
}

export async function loadTopic(id: string, language: string): Promise<HelpDocument | null> {
  const tried = language === SOURCE_LANGUAGE ? [SOURCE_LANGUAGE] : [language, SOURCE_LANGUAGE]
  for (const lang of tried) {
    const loader = index.get(lang)?.get(id)
    if (loader) {
      const markdown = await loader()
      return { id, language: lang, markdown, title: titleOf(markdown, id), fallback: lang !== language }
    }
  }
  return null
}

export async function loadAllTopics(language: string): Promise<HelpDocument[]> {
  const docs = await Promise.all(TOPIC_IDS.map((id) => loadTopic(id, language)))
  return docs.filter((d): d is HelpDocument => d !== null)
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
export interface SearchHit {
  id: string
  title: string
  snippet: string
  score: number
}

/** Lowercase and strip accents, so "transacoes" finds "Transações". */
export function normalize(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

function plain(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[#>*_`|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * Case- and accent-insensitive search over every topic. A title match outranks
 * a body match; every word of the query must appear somewhere in the topic, so
 * "criar regra" does not return everything containing "criar".
 */
export function searchTopics(docs: HelpDocument[], query: string, limit = 12): SearchHit[] {
  const words = normalize(query).split(/\s+/).filter((w) => w.length >= 2)
  if (words.length === 0) return []

  const hits: SearchHit[] = []
  for (const doc of docs) {
    const body = plain(doc.markdown)
    const haystack = normalize(body)
    const title = normalize(doc.title)
    if (!words.every((w) => haystack.includes(w) || title.includes(w))) continue

    let score = 0
    for (const w of words) {
      if (title.includes(w)) score += 10
      score += Math.min(5, haystack.split(w).length - 1)
    }
    const at = haystack.indexOf(words[0])
    const start = Math.max(0, at - 50)
    const snippet = (start > 0 ? '…' : '') + body.slice(start, start + 140).trim() + '…'
    hits.push({ id: doc.id, title: doc.title, snippet, score })
  }
  return hits.sort((a, b) => b.score - a.score).slice(0, limit)
}
