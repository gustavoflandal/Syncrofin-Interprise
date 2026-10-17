import { describe, expect, it } from 'vitest'

import { SOURCE_LANGUAGE, availableLanguages, loadAllTopics, loadTopic, normalize, searchTopics, titleOf } from '@/help/loader'
import { TOPIC_IDS } from '@/help/topics'

describe('titleOf', () => {
  it('takes the first heading', () => {
    expect(titleOf('intro\n\n# Contas\n\ntext\n## Sub')).toBe('Contas')
  })

  it('does not mistake a subheading for the title', () => {
    expect(titleOf('## Only sub', 'fallback')).toBe('fallback')
  })
})

describe('normalize', () => {
  it('ignores case and accents', () => {
    expect(normalize('Transações')).toBe('transacoes')
    expect(normalize('ORÇAMENTO')).toBe('orcamento')
  })
})

describe('loadTopic', () => {
  it('ships Portuguese, the language the manual is written in', () => {
    expect(availableLanguages()).toContain(SOURCE_LANGUAGE)
  })

  it('loads a topic in its own language without a fallback flag', async () => {
    const doc = await loadTopic('contas', SOURCE_LANGUAGE)
    expect(doc).not.toBeNull()
    expect(doc?.fallback).toBe(false)
    expect(doc?.language).toBe(SOURCE_LANGUAGE)
    expect(doc?.title).toBeTruthy()
  })

  it('falls back to Portuguese, and says so, for a language with no translation', async () => {
    const doc = await loadTopic('contas', 'es')
    expect(doc?.language).toBe(SOURCE_LANGUAGE)
    expect(doc?.fallback).toBe(true)
  })

  it('returns null for a topic that does not exist', async () => {
    expect(await loadTopic('does-not-exist', SOURCE_LANGUAGE)).toBeNull()
  })

  it('loads the whole manual, in table-of-contents order', async () => {
    const docs = await loadAllTopics(SOURCE_LANGUAGE)
    expect(docs.map((d) => d.id)).toEqual(TOPIC_IDS)
  })
})

describe('searchTopics', () => {
  const doc = (id: string, title: string, body: string) => ({
    id,
    title,
    markdown: `# ${title}\n\n${body}`,
    language: 'pt-BR',
    fallback: false,
  })
  const docs = [
    doc('a', 'Transações', 'Lançamentos de receita e despesa.'),
    doc('b', 'Orçamentos', 'Limite mensal por categoria. Veja também transações.'),
    doc('c', 'Metas', 'Objetivos de poupança.'),
  ]

  it('finds without accents or case', () => {
    expect(searchTopics(docs, 'TRANSACOES').map((h) => h.id)).toEqual(['a', 'b'])
  })

  it('ranks a title match above a body match', () => {
    expect(searchTopics(docs, 'transacoes')[0].id).toBe('a')
  })

  it('requires every word, not any', () => {
    expect(searchTopics(docs, 'limite categoria').map((h) => h.id)).toEqual(['b'])
    expect(searchTopics(docs, 'limite poupanca')).toEqual([])
  })

  it('ignores one-letter noise and empty queries', () => {
    expect(searchTopics(docs, '')).toEqual([])
    expect(searchTopics(docs, ' a ')).toEqual([])
  })

  it('does not search code blocks or link targets', () => {
    const only = [doc('x', 'Título', 'Texto [link](help:secreto)\n\n```\nsegredo\n```')]
    expect(searchTopics(only, 'secreto')).toEqual([])
    expect(searchTopics(only, 'link').map((h) => h.id)).toEqual(['x'])
  })

  it('finds real manual content', async () => {
    const all = await loadAllTopics(SOURCE_LANGUAGE)
    expect(searchTopics(all, 'conciliacao')[0].id).toBe('conciliacao')
    expect(searchTopics(all, 'exportar contador').map((h) => h.id)).toContain('contador')
  })
})
