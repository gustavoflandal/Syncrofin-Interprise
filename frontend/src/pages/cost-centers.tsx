import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { costCenters as ccApi } from '@/lib/api'
import type { CostCenter } from '@/types'

export default function CostCentersPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<CostCenter | null>(null)
  const [form, setForm] = useState({ name: '', code: '', description: '' })
  const [editingActive, setEditingActive] = useState(true)

  const { data: ccs = [] } = useQuery({
    queryKey: ['cost-centers', { includeInactive: true }],
    queryFn: () => ccApi.list({ includeInactive: true }),
  })

  const save = useMutation({
    mutationFn: () =>
      editing
        ? ccApi.update(editing.id, {
            name: form.name,
            code: form.code || null,
            description: form.description || null,
            is_active: editingActive,
          })
        : ccApi.create({
            name: form.name,
            code: form.code || null,
            description: form.description || null,
          }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cost-centers'] })
      setOpen(false)
      setEditing(null)
    },
    onError: () => toast.error(t('common.error')),
  })

  const remove = useMutation({
    mutationFn: (id: string) => ccApi.remove(id),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['cost-centers'] })
      toast.success(result ? t('costCenter.deactivated') : t('costCenter.deleted'))
    },
    onError: () => toast.error(t('common.error')),
  })

  function openCreate() {
    setEditing(null)
    setForm({ name: '', code: '', description: '' })
    setEditingActive(true)
    setOpen(true)
  }

  function openEdit(cc: CostCenter) {
    setEditing(cc)
    setForm({ name: cc.name, code: cc.code ?? '', description: cc.description ?? '' })
    setEditingActive(cc.is_active)
    setOpen(true)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        section={t('costCenter.description')}
        title={t('costCenter.title')}
        action={
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4 mr-1" /> {t('costCenter.add')}
          </Button>
        }
      />

      <div className="rounded-xl border bg-card divide-y">
        {ccs.length === 0 && (
          <p className="p-6 text-sm text-muted-foreground text-center">{t('common.empty')}</p>
        )}
        {ccs.map((cc) => (
          <div key={cc.id} className="flex items-center justify-between px-5 py-3">
            <div>
              <span className="font-medium text-sm">{cc.name}</span>
              {cc.code && (
                <span className="ml-2 text-xs text-muted-foreground font-mono">{cc.code}</span>
              )}
              {!cc.is_active && (
                <span className="ml-2 text-xs bg-gray-100 text-gray-500 rounded px-1.5">
                  {t('costCenter.inactive')}
                </span>
              )}
            </div>
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" onClick={() => openEdit(cc)}>
                <Pencil className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => remove.mutate(cc.id)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? t('common.edit') : t('costCenter.add')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('costCenter.name')}</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <Label>{t('costCenter.code')}</Label>
              <Input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                placeholder={t('costCenter.codeHint')}
              />
            </div>
            <div>
              <Label>{t('costCenter.description_field')}</Label>
              <Input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
            {editing && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editingActive}
                  onChange={(e) => setEditingActive(e.target.checked)}
                  className="h-4 w-4 rounded border-border"
                />
                <span className="text-sm text-foreground">{t('costCenter.active')}</span>
              </label>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => save.mutate()}
              disabled={!form.name || save.isPending}
            >
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
