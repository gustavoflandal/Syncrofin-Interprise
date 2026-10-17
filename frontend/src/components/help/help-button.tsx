import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Dialog as DialogPrimitive } from 'radix-ui'
import { BookOpen, CircleHelp, X } from 'lucide-react'
import { helpAvailableAt, topicForPath } from '@/help/topics'
import { isTypingTarget } from '@/help/typing'
import { ManualMarkdown } from '@/components/help/manual-markdown'
import { useHelpTopic } from '@/components/help/use-help-topic'

/**
 * The help button, on every screen.
 *
 * Mounted once, at the root of the app, so no screen has to remember to include
 * it (and a new screen cannot forget). It reads the URL to decide which topic of
 * the manual to open: the reader asks for help *here* and gets the page about
 * *here*, with a way out to the whole manual.
 *
 * `?` or `F1` opens it, unless the reader is typing in a field. It is left out
 * of the manual itself (which is help already) and of the public invoice link a
 * client opens (who is not a user of the product).
 */
export function HelpButton() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  // Remember *where* it was opened: moving to another screen closes it without an
  // effect, because "open" simply stops being true for the new path.
  const [openPath, setOpenPath] = useState<string | null>(null)
  const open = openPath === pathname
  const setOpen = useCallback((value: boolean) => setOpenPath(value ? pathname : null), [pathname])
  const available = helpAvailableAt(pathname)
  const topicId = topicForPath(pathname)
  const { doc, loading } = useHelpTopic(open ? topicId : undefined)

  const toggle = useCallback(() => setOpenPath((current) => (current === pathname ? null : pathname)), [pathname])

  useEffect(() => {
    if (!available) return
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return
      const isHelpKey = event.key === 'F1' || (event.key === '?' && !isTypingTarget(event.target))
      if (!isHelpKey) return
      event.preventDefault()
      toggle()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [available, toggle])

  if (!available) return null

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <button
          type="button"
          data-testid="help-button"
          className="fixed bottom-4 right-4 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-lg transition-colors hover:bg-primary hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={t('help.button')}
          title={`${t('help.button')} (?)`}
        >
          <CircleHelp size={20} />
        </button>
      </DialogPrimitive.Trigger>

      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          data-testid="help-panel"
          className="fixed right-0 top-0 z-50 flex h-full w-full flex-col border-l border-border bg-background shadow-2xl outline-none sm:max-w-md data-[state=open]:animate-in data-[state=open]:slide-in-from-right"
        >
          <header className="flex items-center gap-2 border-b border-border px-4 py-3">
            <BookOpen size={16} className="text-primary" />
            <DialogPrimitive.Title className="flex-1 truncate text-sm font-semibold">
              {t('help.panelTitle')}
            </DialogPrimitive.Title>
            <DialogPrimitive.Close
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label={t('help.close')}
            >
              <X size={16} />
            </DialogPrimitive.Close>
          </header>
          <DialogPrimitive.Description className="sr-only">{t('help.panelDescription')}</DialogPrimitive.Description>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {doc?.fallback && (
              <p role="note" className="mb-3 rounded-md bg-muted p-2.5 text-xs text-muted-foreground">
                {t('help.notTranslated')}
              </p>
            )}
            {loading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
            {!loading && !doc && <p className="text-sm text-muted-foreground">{t('help.unavailable')}</p>}
            {doc && (
              <ManualMarkdown onNavigate={() => setOpen(false)}>{doc.markdown}</ManualMarkdown>
            )}
          </div>

          <footer className="flex items-center justify-between gap-2 border-t border-border px-4 py-3 text-xs">
            <span className="text-muted-foreground">{t('help.shortcutHint')}</span>
            <Link
              to={`/help/${topicId}`}
              onClick={() => setOpen(false)}
              className="font-medium text-primary hover:underline"
            >
              {t('help.openManual')}
            </Link>
          </footer>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
