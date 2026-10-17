import { createContext, useContext } from 'react'
import type { ModuleId } from '@/lib/modules'
import type { Workspace, WorkspaceRole } from '@/types'

interface WorkspaceContextType {
  current: Workspace | null
  workspaces: Workspace[]
  isLoading: boolean
  /** Switch the active workspace. Persists to localStorage and invalidates queries. */
  switchWorkspace: (id: string) => Promise<void>
  /** Re-fetch the list of workspaces the user can access. */
  refresh: () => Promise<void>
  /** Role of the current user inside the active workspace, or null if no active workspace. */
  role: WorkspaceRole | null
  /** True for anyone who administers the workspace (`workspace.manage`): an owner, a manager, or a role given it. */
  canManage: boolean
  /** True for anyone allowed to change some part of the financial data. */
  canWrite: boolean
  /** Whether the current member holds a permission (`export.read`, `roles.manage`...). */
  can: (permission: string) => boolean
  /** Modules the active workspace shows, as resolved by the server. */
  enabledModules: ModuleId[]
  /**
   * The single question the UI asks about modules. False while the
   * workspace list is still loading, so nothing renders on a guess.
   */
  hasModule: (id: ModuleId) => boolean
}

export const WorkspaceContext = createContext<WorkspaceContextType | null>(null)

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider')
  }
  return ctx
}
