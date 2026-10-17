import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import { ApiTokensCard } from '@/components/api-tokens-card'
import { renderWithProviders, t } from '@/test/utils'
import type { ApiTokenInfo } from '@/types'

const api = vi.hoisted(() => ({
  apiTokens: { list: vi.fn(), create: vi.fn(), rotate: vi.fn(), revoke: vi.fn() },
  roles: { catalog: vi.fn() },
}))
vi.mock('@/lib/api', () => ({ apiTokens: api.apiTokens, roles: api.roles }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/hooks/use-display-locale', () => ({ useDateLocale: () => 'pt-BR', useDisplayLocale: () => 'pt-BR' }))
// The person can do everything except write categories.
const state = vi.hoisted(() => ({ cannot: new Set(['categories.write']) }))
vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ can: (p: string) => !state.cannot.has(p) }),
}))
import { toast } from 'sonner'

const catalog = {
  permissions: [
    { key: 'transactions.write', group: 'data' },
    { key: 'categories.write', group: 'data' },
    { key: 'export.read', group: 'reports' },
    { key: 'members.manage', group: 'admin' },
    { key: 'tokens.manage', group: 'admin' },
  ],
  templates: [],
}

const token = (over: Partial<ApiTokenInfo> = {}): ApiTokenInfo => ({
  id: 't1', name: 'Integração ERP', prefix: 'sfn_1a2b3c4d', scopes: ['export.read'],
  created_at: '2026-09-01T00:00:00Z', expires_at: '2026-12-01T00:00:00Z', last_used_at: null, revoked_at: null,
  state: 'active', user_email: 'ana@example.com', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  api.roles.catalog.mockResolvedValue(catalog)
  api.apiTokens.list.mockResolvedValue([token()])
  api.apiTokens.create.mockResolvedValue({ token: 'sfn_1a2b3c4d_SECRETVALUE', item: token() })
  api.apiTokens.rotate.mockResolvedValue({ token: 'sfn_5e6f7a8b_NEWSECRET', item: token({ id: 't2' }) })
  api.apiTokens.revoke.mockResolvedValue(undefined)
})

describe('ApiTokensCard', () => {
  it('lists the tokens with what is safe to show, never the secret', async () => {
    renderWithProviders(<ApiTokensCard />)

    expect(await screen.findByText('Integração ERP')).toBeInTheDocument()
    expect(screen.getByText('sfn_1a2b3c4d…')).toBeInTheDocument()
    expect(screen.getByText(t('apiTokens.states.active'))).toBeInTheDocument()
    expect(screen.getByText(new RegExp(t('apiTokens.neverUsed')))).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/SECRET/)
  })

  it('says how to start when there are none', async () => {
    api.apiTokens.list.mockResolvedValue([])
    renderWithProviders(<ApiTokensCard />)
    expect(await screen.findByText(t('apiTokens.none'))).toBeInTheDocument()
  })

  it('offers only what the person can do, and never the administrative permissions', async () => {
    const { user } = renderWithProviders(<ApiTokensCard />)
    await user.click(await screen.findByRole('button', { name: t('apiTokens.new') }))
    const dialog = await screen.findByRole('dialog')

    expect(await within(dialog).findByLabelText(t('permissions.transactions.write'))).toBeInTheDocument()
    expect(within(dialog).getByLabelText(t('permissions.export.read'))).toBeInTheDocument()
    expect(within(dialog).queryByLabelText(t('permissions.categories.write'))).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText(t('permissions.members.manage'))).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText(t('permissions.tokens.manage'))).not.toBeInTheDocument()
  })

  it('needs a name and at least one permission', async () => {
    const { user } = renderWithProviders(<ApiTokensCard />)
    await user.click(await screen.findByRole('button', { name: t('apiTokens.new') }))
    const dialog = await screen.findByRole('dialog')
    const submit = within(dialog).getByRole('button', { name: t('apiTokens.create') })

    expect(submit).toBeDisabled()
    await user.type(within(dialog).getByLabelText(t('apiTokens.name')), 'Script')
    expect(submit).toBeDisabled()
    await user.click(await within(dialog).findByLabelText(t('permissions.export.read')))
    expect(submit).toBeEnabled()
  })

  it('makes a token, then shows the secret once and says it will not come back', async () => {
    const { user } = renderWithProviders(<ApiTokensCard />)
    await user.click(await screen.findByRole('button', { name: t('apiTokens.new') }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(t('apiTokens.name')), 'Script')
    await user.selectOptions(within(dialog).getByLabelText(t('apiTokens.duration')), '180')
    await user.click(await within(dialog).findByLabelText(t('permissions.export.read')))
    await user.click(within(dialog).getByRole('button', { name: t('apiTokens.create') }))

    await waitFor(() => expect(api.apiTokens.create).toHaveBeenCalledWith({ name: 'Script', scopes: ['export.read'], days: 180 }))
    expect(await screen.findByTestId('api-token-secret')).toHaveTextContent('sfn_1a2b3c4d_SECRETVALUE')
    expect(screen.getByText(t('apiTokens.secretBody'))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t('apiTokens.savedIt') }))
    await waitFor(() => expect(screen.queryByTestId('api-token-secret')).not.toBeInTheDocument())
    expect(document.body.textContent).not.toMatch(/SECRETVALUE/)
  })

  it('rotates after asking twice, and shows the new secret', async () => {
    const { user } = renderWithProviders(<ApiTokensCard />)

    await user.click(await screen.findByRole('button', { name: t('apiTokens.rotate') }))
    expect(api.apiTokens.rotate).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: t('apiTokens.confirmRotate') }))

    await waitFor(() => expect(api.apiTokens.rotate).toHaveBeenCalledWith('t1'))
    expect(await screen.findByTestId('api-token-secret')).toHaveTextContent('sfn_5e6f7a8b_NEWSECRET')
  })

  it('revokes after asking twice', async () => {
    const { user } = renderWithProviders(<ApiTokensCard />)

    await user.click(await screen.findByRole('button', { name: t('apiTokens.revoke') }))
    expect(api.apiTokens.revoke).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: t('apiTokens.confirmRevoke') }))

    await waitFor(() => expect(api.apiTokens.revoke).toHaveBeenCalledWith('t1'))
  })

  it('offers no actions on a token that is already over', async () => {
    api.apiTokens.list.mockResolvedValue([token({ state: 'revoked', revoked_at: '2026-09-10T00:00:00Z' })])
    renderWithProviders(<ApiTokensCard />)

    expect(await screen.findByText(t('apiTokens.states.revoked'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('apiTokens.rotate') })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('apiTokens.revoke') })).not.toBeInTheDocument()
  })

  it('explains, in the person\'s words, that a token cannot carry more than they can do', async () => {
    api.apiTokens.create.mockRejectedValue({ response: { data: { detail: 'You cannot give a token what you cannot do yourself: x' } } })
    const { user } = renderWithProviders(<ApiTokensCard />)
    await user.click(await screen.findByRole('button', { name: t('apiTokens.new') }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(t('apiTokens.name')), 'Script')
    await user.click(await within(dialog).findByLabelText(t('permissions.export.read')))
    await user.click(within(dialog).getByRole('button', { name: t('apiTokens.create') }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(t('apiTokens.errorBeyondYou')))
  })
})
