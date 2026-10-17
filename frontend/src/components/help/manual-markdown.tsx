import { createContext, useContext, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown, { defaultUrlTransform, type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import { isTopicId } from '@/help/topics'

type NodeProps = { children?: ReactNode }

/**
 * Images in a topic must live under this folder of the app's own files (`public/manual-img/`).
 * Anything else (another site, a data: URL) is shown as its description only: a page of the
 * manual never makes the reader's browser fetch from somewhere else.
 */
export const IMAGE_PREFIX = '/manual-img/'

/** `help:transacoes` links between manual topics; everything else is a normal link. */
export const TOPIC_LINK = /^help:([a-z0-9-]+)$/

interface Props {
  children: string
  className?: string
  /** Called after an in-manual link is followed (the side panel closes itself). */
  onNavigate?: () => void
}

/** Who to tell when an in-manual link is followed. A context, not a prop on the components. */
const NavigateContext = createContext<(() => void) | undefined>(undefined)

function ManualImage({ src, alt }: { src?: string | Blob; alt?: string }) {
  if (typeof src !== 'string' || !src.startsWith(IMAGE_PREFIX) || src.includes('..')) return <span>{alt}</span>
  return (
    <span className="my-3 block">
      <img
        src={src}
        alt={alt ?? ''}
        loading="lazy"
        className="block w-60 max-w-full rounded-2xl border border-border shadow-sm"
      />
      {alt && <span className="mt-1.5 block text-xs text-muted-foreground">{alt}</span>}
    </span>
  )
}

function ManualLink({ href = '', children }: NodeProps & { href?: string }) {
  const onNavigate = useContext(NavigateContext)
  const topic = TOPIC_LINK.exec(href)
  if (topic) {
    const id = topic[1]
    // A link to a topic that does not exist renders as plain text: a dead
    // link in a help page is worse than no link. The content test also
    // fails on it, so it does not ship.
    if (!isTopicId(id)) return <span>{children}</span>
    return (
      <Link to={`/help/${id}`} onClick={onNavigate} className="text-primary underline underline-offset-2 hover:opacity-80">
        {children}
      </Link>
    )
  }
  if (href.startsWith('/')) {
    return (
      <Link to={href} onClick={onNavigate} className="text-primary underline underline-offset-2 hover:opacity-80">
        {children}
      </Link>
    )
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:opacity-80">
      {children}
    </a>
  )
}

/**
 * react-markdown drops any URL whose scheme it does not know (it turns `help:contas`
 * into an empty href, which then rendered as a dead new-tab link). Topic links are
 * ours, so let them through; everything else keeps the library's own filtering.
 */
const urlTransform = (url: string) => (TOPIC_LINK.test(url) ? url : defaultUrlTransform(url))

/**
 * Defined once, at module level. Components declared inline in the render are a new
 * type on every render, and React then throws away and rebuilds the whole rendered
 * page each time the parent re-renders (losing scroll and text selection).
 */
const COMPONENTS: Components = {
  h1: ({ children }: NodeProps) => <h1 className="text-xl font-bold tracking-tight mt-1 mb-3">{children}</h1>,
  h2: ({ children }: NodeProps) => <h2 className="text-base font-semibold mt-6 mb-2 pb-1 border-b border-border">{children}</h2>,
  h3: ({ children }: NodeProps) => <h3 className="text-sm font-semibold mt-4 mb-1.5">{children}</h3>,
  p: ({ children }: NodeProps) => <p className="my-2.5">{children}</p>,
  ul: ({ children }: NodeProps) => <ul className="my-2.5 list-disc pl-5 space-y-1">{children}</ul>,
  ol: ({ children }: NodeProps) => <ol className="my-2.5 list-decimal pl-5 space-y-1">{children}</ol>,
  li: ({ children }: NodeProps) => <li className="marker:text-muted-foreground/70">{children}</li>,
  strong: ({ children }: NodeProps) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }: NodeProps) => <em className="italic">{children}</em>,
  hr: () => <hr className="my-5 border-border" />,
  code: ({ children }: NodeProps) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[12.5px]">{children}</code>
  ),
  pre: ({ children }: NodeProps) => (
    <pre className="my-3 overflow-x-auto rounded-lg bg-muted p-3 font-mono text-[12.5px]">{children}</pre>
  ),
  blockquote: ({ children }: NodeProps) => (
    <blockquote className="my-3 rounded-r-lg border-l-4 border-primary/50 bg-primary/5 px-3 py-2 text-foreground/90 [&>p]:my-1">
      {children}
    </blockquote>
  ),
  table: ({ children }: NodeProps) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-[13px]">{children}</table>
    </div>
  ),
  thead: ({ children }: NodeProps) => <thead className="bg-muted/60">{children}</thead>,
  th: ({ children }: NodeProps) => <th className="px-3 py-1.5 text-left font-semibold">{children}</th>,
  td: ({ children }: NodeProps) => <td className="border-t border-border px-3 py-1.5 align-top">{children}</td>,
  a: ManualLink,
  img: ManualImage,
}

/**
 * Renders a manual topic.
 *
 * No raw HTML, and images only from the app's own `/manual-img/` folder, so a topic is only ever
 * text, tables, links and screenshots: nothing in a Markdown file can run script or reach out to
 * another origin.
 * Links come in three kinds: to another topic (`help:id`, a router link that
 * stays in the app), to a screen (`/transactions`, likewise), and external
 * (`https://…`, a new tab).
 */
export function ManualMarkdown({ children, className, onNavigate }: Props) {
  return (
    <div className={cn('text-sm leading-relaxed text-foreground [&>:first-child]:mt-0', className)}>
      <NavigateContext.Provider value={onNavigate}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={urlTransform} components={COMPONENTS}>
          {children}
        </ReactMarkdown>
      </NavigateContext.Provider>
    </div>
  )
}
