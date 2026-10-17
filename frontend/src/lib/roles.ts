import type { RoleInfo } from '@/types'

const BUILT_IN = ['owner', 'editor', 'viewer', 'manager'] as const

export function isBuiltInRole(key: string): boolean {
  return (BUILT_IN as readonly string[]).includes(key)
}

/**
 * The name a person sees for a role: the built-in ones are translated, a workspace's own carry the
 * name its owner gave them. A key that matches nothing (a role since deleted) is shown as unknown
 * rather than as the raw `c_1a2b3c4d`.
 */
export function roleLabel(key: string, roles: RoleInfo[] | undefined, t: (key: string) => string): string {
  switch (key) {
    case 'owner':
      return t('workspace.roleOwner')
    case 'editor':
      return t('workspace.roleEditor')
    case 'viewer':
      return t('workspace.roleViewer')
    case 'manager':
      return t('workspace.roleManager')
    default:
      return roles?.find((r) => r.key === key)?.name ?? t('roles.unknown')
  }
}

/** A short line about what a role allows, for the built-in roles; a workspace's own carry their description. */
export function roleHint(key: string, roles: RoleInfo[] | undefined, t: (key: string) => string): string {
  switch (key) {
    case 'owner':
      return t('workspace.roleOwnerHint')
    case 'editor':
      return t('workspace.roleEditorHint')
    case 'viewer':
      return t('workspace.roleViewerHint')
    case 'manager':
      return t('workspace.roleManagerHint')
    default:
      return roles?.find((r) => r.key === key)?.description ?? ''
  }
}
