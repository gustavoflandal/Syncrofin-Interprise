import { describe, expect, it } from 'vitest'

import { isBuiltInRole, roleHint, roleLabel } from '@/lib/roles'
import type { RoleInfo } from '@/types'

// A stand-in translator that shows the key it was asked for.
const t = (key: string) => `«${key}»`

const custom: RoleInfo = {
  key: 'c_1a2b3c4d',
  id: 'r1',
  name: 'Contador externo',
  description: 'Só lê e exporta',
  system: false,
  permissions: ['export.read'],
  member_count: 1,
}

describe('roleLabel', () => {
  it('translates the built-in roles', () => {
    expect(roleLabel('owner', undefined, t)).toBe('«workspace.roleOwner»')
    expect(roleLabel('editor', undefined, t)).toBe('«workspace.roleEditor»')
    expect(roleLabel('viewer', undefined, t)).toBe('«workspace.roleViewer»')
    expect(roleLabel('manager', undefined, t)).toBe('«workspace.roleManager»')
  })

  it('shows the name the owner gave a role of their own', () => {
    expect(roleLabel('c_1a2b3c4d', [custom], t)).toBe('Contador externo')
  })

  it('never shows a raw key: a role that was deleted reads as removed', () => {
    expect(roleLabel('c_1a2b3c4d', [], t)).toBe('«roles.unknown»')
    expect(roleLabel('c_1a2b3c4d', undefined, t)).toBe('«roles.unknown»')
  })
})

describe('roleHint', () => {
  it('has a line for each built-in role and the description for a custom one', () => {
    expect(roleHint('viewer', undefined, t)).toBe('«workspace.roleViewerHint»')
    expect(roleHint('c_1a2b3c4d', [custom], t)).toBe('Só lê e exporta')
    expect(roleHint('c_ffffffff', [custom], t)).toBe('')
  })
})

describe('isBuiltInRole', () => {
  it('tells the roles that are not rows from the ones that are', () => {
    expect(['owner', 'editor', 'viewer', 'manager'].every(isBuiltInRole)).toBe(true)
    expect(isBuiltInRole('c_1a2b3c4d')).toBe(false)
  })
})
