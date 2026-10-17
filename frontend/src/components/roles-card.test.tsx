import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import { RolesCard } from '@/components/roles-card'
import { renderWithProviders, t } from '@/test/utils'
import type { RoleInfo } from '@/types'

const api = vi.hoisted(() => ({
  roles: { catalog: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), list: vi.fn() },
}))
vi.mock('@/lib/api', () => ({ roles: api.roles }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
import { toast } from 'sonner'

const catalog = {
  permissions: [
    { key: 'transactions.write', group: 'data' },
    { key: 'accounts.write', group: 'data' },
    { key: 'export.read', group: 'reports' },
    { key: 'audit.read', group: 'reports' },
    { key: 'members.manage', group: 'admin' },
  ],
  templates: [
    { key: 'accountant', permissions: ['export.read'] },
    { key: 'auditor', permissions: ['export.read', 'audit.read'] },
  ],
}

const builtIn = (key: string): RoleInfo => ({ key, id: null, name: null, description: null, system: true, permissions: [], member_count: 1 })
const accountant: RoleInfo = {
  key: 'c_1a2b3c4d', id: 'r1', name: 'Contador', description: 'Só lê e exporta', system: false,
  permissions: ['export.read'], member_count: 2,
}
const roles = [builtIn('owner'), builtIn('editor'), builtIn('viewer'), accountant]

beforeEach(() => {
  vi.clearAllMocks()
  api.roles.catalog.mockResolvedValue(catalog)
  api.roles.create.mockResolvedValue({ ...accountant, id: 'r2', key: 'c_2' })
  api.roles.update.mockResolvedValue(accountant)
  api.roles.remove.mockResolvedValue(undefined)
})

describe('RolesCard', () => {
  it('lists only the roles the workspace made, with how many permissions and members', () => {
    renderWithProviders(<RolesCard roles={roles} />)

    expect(screen.getByText('Contador')).toBeInTheDocument()
    expect(screen.getByText(new RegExp(t('roles.summary', { permissions: 1, members: 2 })))).toBeInTheDocument()
    expect(screen.queryByText(t('workspace.roleOwner'))).not.toBeInTheDocument()
  })

  it('says how to start when there are none', () => {
    renderWithProviders(<RolesCard roles={[builtIn('owner')]} />)
    expect(screen.getByText(t('roles.none'))).toBeInTheDocument()
  })

  it('creates a role from a template, then lets the permissions be adjusted', async () => {
    const { user } = renderWithProviders(<RolesCard roles={[builtIn('owner')]} />)

    await user.click(screen.getByRole('button', { name: t('roles.new') }))
    const dialog = await screen.findByRole('dialog')
    await user.selectOptions(await within(dialog).findByLabelText(t('roles.template')), 'auditor')

    // The template ticked its permissions and offered its name.
    expect(within(dialog).getByLabelText(t('permissions.export.read'))).toBeChecked()
    expect(within(dialog).getByLabelText(t('permissions.audit.read'))).toBeChecked()
    expect(within(dialog).getByLabelText(t('permissions.transactions.write'))).not.toBeChecked()
    expect(within(dialog).getByLabelText(t('roles.name'))).toHaveValue(t('roles.templates.auditor'))

    await user.click(within(dialog).getByLabelText(t('permissions.transactions.write')))
    await user.click(within(dialog).getByRole('button', { name: t('common.save') }))

    await waitFor(() => expect(api.roles.create).toHaveBeenCalled())
    const payload = api.roles.create.mock.calls[0][0]
    expect(payload.name).toBe(t('roles.templates.auditor'))
    expect([...payload.permissions].sort()).toEqual(['audit.read', 'export.read', 'transactions.write'])
  })

  it('will not save a role with no name', async () => {
    const { user } = renderWithProviders(<RolesCard roles={[builtIn('owner')]} />)
    await user.click(screen.getByRole('button', { name: t('roles.new') }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: t('common.save') })).toBeDisabled()
  })

  it('edits a role from what it has now', async () => {
    const { user } = renderWithProviders(<RolesCard roles={roles} />)

    await user.click(screen.getByRole('button', { name: t('common.edit') }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText(t('roles.name'))).toHaveValue('Contador')
    expect(await within(dialog).findByLabelText(t('permissions.export.read'))).toBeChecked()
    // No template picker when changing a role that exists.
    expect(within(dialog).queryByLabelText(t('roles.template'))).not.toBeInTheDocument()

    await user.click(within(dialog).getByLabelText(t('permissions.audit.read')))
    await user.click(within(dialog).getByRole('button', { name: t('common.save') }))

    await waitFor(() => expect(api.roles.update).toHaveBeenCalledWith('r1', expect.objectContaining({ name: 'Contador' })))
    expect([...api.roles.update.mock.calls[0][1].permissions].sort()).toEqual(['audit.read', 'export.read'])
  })

  it('asks twice before deleting', async () => {
    const { user } = renderWithProviders(<RolesCard roles={roles} />)

    await user.click(screen.getByRole('button', { name: t('common.delete') }))
    expect(api.roles.remove).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: t('roles.confirmDelete') }))

    await waitFor(() => expect(api.roles.remove).toHaveBeenCalledWith('r1'))
  })

  it('explains, in the person\'s words, why a role could not be deleted', async () => {
    api.roles.remove.mockRejectedValue({ response: { data: { detail: 'Members still hold this role: move them to another first' } } })
    const { user } = renderWithProviders(<RolesCard roles={roles} />)

    await user.click(screen.getByRole('button', { name: t('common.delete') }))
    await user.click(screen.getByRole('button', { name: t('roles.confirmDelete') }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(t('roles.errorInUse')))
  })

  it('explains a name that is already taken', async () => {
    api.roles.create.mockRejectedValue({ response: { data: { detail: 'A role with this name already exists' } } })
    const { user } = renderWithProviders(<RolesCard roles={[builtIn('owner')]} />)
    await user.click(screen.getByRole('button', { name: t('roles.new') }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(t('roles.name')), 'Contador')
    await user.click(within(dialog).getByRole('button', { name: t('common.save') }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(t('roles.errorNameTaken')))
  })
})
