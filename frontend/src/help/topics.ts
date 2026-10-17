import { matchPath } from 'react-router-dom'

/**
 * The manual's table of contents, and which screen shows which topic.
 *
 * One source of truth for two things that must not drift apart:
 *
 *   - the manual page lists topics from here, in this order, by section;
 *   - the help button on any screen opens the topic whose `paths` match the
 *     current URL.
 *
 * A screen with no topic is a screen with no help, which is exactly what
 * `topics.test.ts` refuses: it reads the router in `App.tsx` and fails when a
 * route is added without a home here.
 *
 * The text of each topic is Markdown under `content/<language>/<id>.md`.
 */

export type HelpSection =
  | 'start'
  | 'daily'
  | 'organize'
  | 'analyze'
  | 'business'
  | 'account'
  | 'admin'
  | 'reference'

export interface HelpTopic {
  id: string
  section: HelpSection
  /** Router patterns (react-router syntax) whose screens this topic explains. */
  paths: string[]
}

/** Section order in the manual's navigation. */
export const HELP_SECTIONS: HelpSection[] = [
  'start',
  'daily',
  'organize',
  'analyze',
  'business',
  'account',
  'admin',
  'reference',
]

export const DEFAULT_TOPIC = 'introducao'

export const TOPICS: HelpTopic[] = [
  { id: 'introducao', section: 'start', paths: [] },
  {
    id: 'primeiros-passos',
    section: 'start',
    paths: ['/setup', '/login', '/register', '/forgot-password', '/reset-password', '/auth/oidc/callback', '/auth/saml/callback'],
  },
  { id: 'navegacao', section: 'start', paths: [] },

  { id: 'painel', section: 'daily', paths: ['/'] },
  { id: 'transacoes', section: 'daily', paths: ['/transactions'] },
  { id: 'contas', section: 'daily', paths: ['/accounts', '/accounts/:id', '/oauth/callback', '/enable-banking'] },
  { id: 'importar', section: 'daily', paths: ['/import', '/assets/import'] },

  { id: 'categorias', section: 'organize', paths: ['/categories'] },
  { id: 'centros-de-custo', section: 'organize', paths: ['/cost-centers'] },
  { id: 'provisoes', section: 'organize', paths: ['/accruals'] },
  { id: 'regras', section: 'organize', paths: ['/rules'] },
  { id: 'colecoes', section: 'organize', paths: ['/collections'] },
  { id: 'pessoas', section: 'organize', paths: ['/payees'] },

  { id: 'orcamentos', section: 'analyze', paths: ['/budgets'] },
  { id: 'metas', section: 'analyze', paths: ['/goals'] },
  { id: 'recorrentes', section: 'analyze', paths: ['/recurring'] },
  { id: 'patrimonio', section: 'analyze', paths: ['/assets'] },
  { id: 'relatorios', section: 'analyze', paths: ['/reports'] },
  { id: 'dre', section: 'analyze', paths: ['/dre'] },
  { id: 'saude-financeira', section: 'analyze', paths: [] },

  { id: 'grupos', section: 'business', paths: ['/groups', '/groups/:id'] },
  { id: 'cobrancas', section: 'business', paths: ['/invoices', '/invoices/:id'] },
  { id: 'emissao-nfe', section: 'business', paths: [] },
  { id: 'boleto-pix', section: 'business', paths: [] },
  { id: 'titulos', section: 'business', paths: ['/ar-ap'] },
  { id: 'pagamentos', section: 'business', paths: ['/payments'] },
  { id: 'conciliacao', section: 'business', paths: [] },
  { id: 'contador', section: 'business', paths: [] },
  { id: 'obrigacoes-fiscais', section: 'business', paths: [] },
  { id: 'retencao-documental', section: 'business', paths: [] },

  { id: 'retencao-dados', section: 'account', paths: [] },
  { id: 'onboarding-empresa', section: 'account', paths: ['/workspace/onboarding'] },
  { id: 'workspace', section: 'account', paths: ['/workspace/settings'] },
  { id: 'auditoria', section: 'account', paths: ['/workspace/audit'] },
  { id: 'seguranca-conta', section: 'account', paths: [] },
  { id: 'notificacoes', section: 'account', paths: [] },
  { id: 'app-celular', section: 'account', paths: [] },

  { id: 'administracao', section: 'admin', paths: ['/admin', '/admin/access-log', '/admin/data-requests'] },
  { id: 'publicar-https', section: 'admin', paths: [] },
  { id: 'tokens-api', section: 'admin', paths: [] },
  { id: 'agentes', section: 'admin', paths: ['/agents', '/agents/connections', '/agents/:id'] },
  { id: 'periods', section: 'admin', paths: ['/workspace/periods'] },
  { id: 'approvals', section: 'admin', paths: ['/workspace/approvals'] },
  { id: 'webhooks', section: 'admin', paths: ['/workspace/webhooks'] },
  { id: 'conectores-erp', section: 'admin', paths: ['/workspace/erp'] },
  { id: 'consolidated', section: 'analyze', paths: ['/consolidated'] },

  { id: 'faq', section: 'reference', paths: [] },
]

export const TOPIC_IDS = TOPICS.map((t) => t.id)

export function isTopicId(value: string | undefined): value is string {
  return !!value && TOPIC_IDS.includes(value)
}

/**
 * The topic for a URL path. Falls back to the introduction rather than to
 * nothing, so the help button is never a dead end on a screen nobody mapped.
 */
export function topicForPath(pathname: string): string {
  for (const topic of TOPICS) {
    if (topic.paths.some((pattern) => matchPath({ path: pattern, end: true }, pathname))) return topic.id
  }
  return DEFAULT_TOPIC
}

/** Screens that should not offer help at all. */
const NO_HELP_PREFIXES = [
  // A client opening an invoice link they were sent. They are not a user of the
  // product, and the manual describes the product's screens, not theirs.
  '/i/',
  // The manual itself.
  '/help',
]

export function helpAvailableAt(pathname: string): boolean {
  return !NO_HELP_PREFIXES.some((prefix) => pathname === prefix.replace(/\/$/, '') || pathname.startsWith(prefix))
}
