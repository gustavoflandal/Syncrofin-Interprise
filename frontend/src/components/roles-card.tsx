import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { KeyRound, Pencil, Plus, Trash2 } from 'lucide-react'
import { roles as rolesApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { PermissionInfo, RoleInfo } from '@/types'

export const ROLES_KEY = ['roles'] as const
const GROUPS: PermissionInfo['group'][] = ['data', 'reports', 'admin']

type ApiError = { response?: { data?: { detail?: string } } }

/** The server's message for a refused role change, in the person's language when we know it. */
function useErrorMessage() {
  const { t } = useTranslation()
  return (error: ApiError) => {
    const detail = error.response?.data?.detail ?? ''
    if (/already exists/i.test(detail)) return t('roles.errorNameTaken')
    if (/built-in role/i.test(detail)) return t('roles.errorNameBuiltIn')
    if (/still hold/i.test(detail)) return t('roles.errorInUse')
    if (/at most/i.test(detail)) return t('roles.errorTooMany')
    return t('common.error')
  }
}

interface RoleDialogProps {
  open: boolean
  role: RoleInfo | null
  onClose: () => void
}

/** Create a role, or change one: a name, a note, and which permissions it holds. */
function RoleDialog({ open, role, onClose }: RoleDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const describe = useErrorMessage()
  const catalog = useQuery({ queryKey: ['roles', 'catalog'], queryFn: rolesApi.catalog, enabled: open })
  // Mounted fresh each time it opens (see RolesCard), so it starts from the role being edited, or empty.
  const [name, setName] = useState(role?.name ?? '')
  const [description, setDescription] = useState(role?.description ?? '')
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? []))

  const save = useMutation({
    mutationFn: () => {
      const permissions = [...chosen]
      return role?.id
        ? rolesApi.update(role.id, { name, description, permissions })
        : rolesApi.create({ name, description, permissions })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ROLES_KEY })
      toast.success(t(role ? 'roles.updated' : 'roles.created'))
      onClose()
    },
    onError: (error: ApiError) => toast.error(describe(error)),
  })

  const toggle = (key: string) =>
    setChosen((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t(role ? 'roles.editTitle' : 'roles.newTitle')}</DialogTitle>
          <DialogDescription>{t('roles.dialogDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="role-name" className="text-[13px]">
              {t('roles.name')}
            </Label>
            <Input id="role-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role-description" className="text-[13px]">
              {t('roles.description')}
            </Label>
            <Input
              id="role-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              placeholder={t('roles.descriptionPlaceholder')}
            />
          </div>

          {!role && catalog.data && (
            <div className="space-y-1.5">
              <Label htmlFor="role-template" className="text-[13px]">
                {t('roles.template')}
              </Label>
              <select
                id="role-template"
                defaultValue=""
                onChange={(e) => {
                  const template = catalog.data.templates.find((x) => x.key === e.target.value)
                  if (!template) return
                  setChosen(new Set(template.permissions))
                  if (!name) setName(t(`roles.templates.${template.key}`))
                }}
                className="h-10 w-full rounded-lg border border-input bg-transparent px-3 text-sm"
              >
                <option value="">{t('roles.templateNone')}</option>
                {catalog.data.templates.map((template) => (
                  <option key={template.key} value={template.key}>
                    {t(`roles.templates.${template.key}`)}
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-muted-foreground">{t('roles.templateHint')}</p>
            </div>
          )}

          <div className="space-y-3">
            <p className="text-[13px] font-medium">{t('roles.permissions')}</p>
            <p className="text-xs text-muted-foreground">{t('roles.readsEverything')}</p>
            {GROUPS.map((group) => (
              <fieldset key={group} className="rounded-lg border border-border/60 p-3">
                <legend className="px-1 text-xs font-semibold text-muted-foreground">{t(`roles.groups.${group}`)}</legend>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {(catalog.data?.permissions ?? [])
                    .filter((p) => p.group === group)
                    .map((p) => (
                      <label key={p.key} className="flex items-start gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={chosen.has(p.key)}
                          onChange={() => toggle(p.key)}
                        />
                        <span>{t(`permissions.${p.key}`)}</span>
                      </label>
                    ))}
                </div>
              </fieldset>
            ))}
          </div>
        </div>

        <DialogFooter className="mt-2">
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => save.mutate()} disabled={!name.trim() || save.isPending}>
            {save.isPending ? t('common.loading') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** The workspace's own roles: list, create, edit, delete. Shown to whoever holds `roles.manage`. */
export function RolesCard({ roles }: { roles: RoleInfo[] }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const describe = useErrorMessage()
  const [editing, setEditing] = useState<RoleInfo | null>(null)
  const [creating, setCreating] = useState(false)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const custom = roles.filter((r) => !r.system)

  const remove = useMutation({
    mutationFn: (id: string) => rolesApi.remove(id),
    onSuccess: () => {
      setConfirmId(null)
      void queryClient.invalidateQueries({ queryKey: ROLES_KEY })
      toast.success(t('roles.deleted'))
    },
    onError: (error: ApiError) => {
      setConfirmId(null)
      toast.error(describe(error))
    },
  })

  return (
    <section className="space-y-4 rounded-xl border bg-card p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            {t('roles.title')}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('roles.intro')}</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t('roles.new')}
        </Button>
      </div>

      {custom.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('roles.none')}</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {custom.map((role) => (
            <li key={role.key} className="flex items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{role.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {t('roles.summary', { permissions: role.permissions.length, members: role.member_count })}
                  {role.description ? ` · ${role.description}` : ''}
                </p>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setEditing(role)} title={t('common.edit')} className="rounded-lg">
                <Pencil className="h-4 w-4" />
              </Button>
              {confirmId === role.id ? (
                <Button variant="destructive" size="sm" disabled={remove.isPending} onClick={() => role.id && remove.mutate(role.id)}>
                  {t('roles.confirmDelete')}
                </Button>
              ) : (
                <Button variant="ghost" size="icon" onClick={() => setConfirmId(role.id)} title={t('common.delete')} className="rounded-lg">
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {creating && <RoleDialog open role={null} onClose={() => setCreating(false)} />}
      {editing && <RoleDialog open role={editing} onClose={() => setEditing(null)} />}
    </section>
  )
}
