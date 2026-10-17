import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, ArrowRight, BookOpen, Search } from 'lucide-react'
import { HELP_SECTIONS, TOPICS, DEFAULT_TOPIC, isTopicId, type HelpSection } from '@/help/topics'
import { loadAllTopics, searchTopics, titleOf, type HelpDocument } from '@/help/loader'
import { ManualMarkdown } from '@/components/help/manual-markdown'
import { useHelpTopic } from '@/components/help/use-help-topic'
import { ShellLogo } from '@/components/shell-logo'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/**
 * The whole manual: a table of contents by section, search, and one topic at a
 * time. Public on purpose: it is what you want open next to the login screen
 * when you have not got in yet.
 */
export default function HelpPage() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const { topic } = useParams()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [all, setAll] = useState<HelpDocument[] | null>(null)

  const id = isTopicId(topic) ? topic : DEFAULT_TOPIC
  const { doc, loading } = useHelpTopic(id)

  // Titles for the table of contents and the search corpus: loaded once, on demand.
  useEffect(() => {
    let active = true
    loadAllTopics(language).then((docs) => active && setAll(docs))
    return () => {
      active = false
    }
  }, [language])

  const titles = useMemo(() => new Map((all ?? []).map((d) => [d.id, d.title])), [all])
  const results = useMemo(() => (all && query.trim().length >= 2 ? searchTopics(all, query) : []), [all, query])

  const index = TOPICS.findIndex((x) => x.id === id)
  const previous = index > 0 ? TOPICS[index - 1] : null
  const next = index < TOPICS.length - 1 ? TOPICS[index + 1] : null
  const titleFor = (topicId: string) => titles.get(topicId) ?? titleOf('', topicId)

  if (topic && !isTopicId(topic)) return <Navigate to="/help" replace />

  const bySection = HELP_SECTIONS.map((section) => ({
    section,
    topics: TOPICS.filter((x) => x.section === section),
  }))

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link to="/" className="flex items-center gap-2" aria-label={t('app.name')}>
            <ShellLogo size={22} className="text-primary" />
            <span className="hidden font-bold tracking-tight sm:inline">{t('app.name')}</span>
          </Link>
          <span className="text-muted-foreground">/</span>
          <h1 className="flex items-center gap-1.5 text-sm font-semibold">
            <BookOpen size={15} className="text-primary" />
            {t('help.manualTitle')}
          </h1>
          <div className="relative ml-auto w-full max-w-xs">
            <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('help.searchPlaceholder')}
              aria-label={t('help.searchPlaceholder')}
              className="h-9 pl-8 text-sm"
              type="search"
            />
          </div>
          <Link to="/" className="hidden text-xs font-medium text-primary hover:underline md:inline">
            {t('help.backToApp')}
          </Link>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-6 md:grid-cols-[15rem_minmax(0,1fr)]">
        <nav aria-label={t('help.tableOfContents')} className="md:sticky md:top-20 md:self-start md:max-h-[calc(100vh-6rem)] md:overflow-y-auto">
          {bySection.map(({ section, topics }) => (
            <div key={section} className="mb-4">
              <p className="mb-1 px-2 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/70">
                {t(`help.section.${section satisfies HelpSection}`)}
              </p>
              <ul>
                {topics.map((x) => (
                  <li key={x.id}>
                    <Link
                      to={`/help/${x.id}`}
                      aria-current={x.id === id ? 'page' : undefined}
                      className={cn(
                        'block rounded-md px-2 py-1 text-[13px] transition-colors',
                        x.id === id
                          ? 'bg-primary/10 font-medium text-primary'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                      )}
                    >
                      {titleFor(x.id)}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <main className="min-w-0 max-w-3xl">
          {query.trim().length >= 2 ? (
            <section aria-live="polite">
              <h2 className="mb-3 text-base font-semibold">{t('help.searchResults', { count: results.length })}</h2>
              {results.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('help.noResults', { query })}</p>
              ) : (
                <ul className="space-y-2">
                  {results.map((hit) => (
                    <li key={hit.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setQuery('')
                          navigate(`/help/${hit.id}`)
                        }}
                        className="w-full rounded-lg border border-border p-3 text-left transition-colors hover:bg-muted/60"
                      >
                        <span className="block text-sm font-semibold">{hit.title}</span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">{hit.snippet}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : (
            <>
              {doc?.fallback && (
                <p role="note" className="mb-4 rounded-md bg-muted p-3 text-xs text-muted-foreground">
                  {t('help.notTranslated')}
                </p>
              )}
              {loading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
              {!loading && !doc && <p className="text-sm text-muted-foreground">{t('help.unavailable')}</p>}
              {doc && <ManualMarkdown>{doc.markdown}</ManualMarkdown>}

              <div className="mt-10 flex items-center justify-between gap-3 border-t border-border pt-4 text-sm">
                {previous ? (
                  <Link to={`/help/${previous.id}`} className="flex items-center gap-1.5 text-primary hover:underline">
                    <ArrowLeft size={14} />
                    <span>
                      <span className="block text-[10.5px] uppercase text-muted-foreground">{t('help.previous')}</span>
                      {titleFor(previous.id)}
                    </span>
                  </Link>
                ) : (
                  <span />
                )}
                {next && (
                  <Link to={`/help/${next.id}`} className="flex items-center gap-1.5 text-right text-primary hover:underline">
                    <span>
                      <span className="block text-[10.5px] uppercase text-muted-foreground">{t('help.next')}</span>
                      {titleFor(next.id)}
                    </span>
                    <ArrowRight size={14} />
                  </Link>
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
