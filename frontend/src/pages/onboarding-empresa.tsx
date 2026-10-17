import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { workspaces as workspacesApi } from '@/lib/api'
import { useWorkspace } from '@/contexts/workspace-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Building2,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  LayoutList,
  Users,
  Landmark,
} from 'lucide-react'

// Wizard steps
const STEPS = ['company', 'chart', 'users', 'bank'] as const
type Step = (typeof STEPS)[number]

const STEP_ICONS: Record<Step, React.ReactNode> = {
  company: <Building2 className="h-5 w-5" />,
  chart: <LayoutList className="h-5 w-5" />,
  users: <Users className="h-5 w-5" />,
  bank: <Landmark className="h-5 w-5" />,
}

export default function OnboardingEmpresaPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { current: workspace } = useWorkspace()

  const [step, setStep] = useState<Step>('company')
  const [legalName, setLegalName] = useState('')
  const [address, setAddress] = useState('')
  const [taxId, setTaxId] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')

  const stepIndex = STEPS.indexOf(step)

  const setupMutation = useMutation({
    mutationFn: () =>
      workspacesApi.setup(workspace!.id, {
        legal_name: legalName || undefined,
        address: address || undefined,
        tax_id: taxId || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workspaces'] })
    },
    onError: () => toast.error(t('onboardingEmpresa.saveError')),
  })

  const inviteMutation = useMutation({
    mutationFn: () =>
      workspacesApi.invite(workspace!.id, { email: inviteEmail, role: 'editor' }),
    onSuccess: () => {
      toast.success(t('onboardingEmpresa.inviteSent', { email: inviteEmail }))
      setInviteEmail('')
    },
    onError: () => toast.error(t('onboardingEmpresa.inviteError')),
  })

  const goNext = async () => {
    if (step === 'company') {
      await setupMutation.mutateAsync()
    }
    const next = STEPS[stepIndex + 1]
    if (next) setStep(next)
  }

  const goPrev = () => {
    const prev = STEPS[stepIndex - 1]
    if (prev) setStep(prev)
  }

  const finish = () => {
    toast.success(t('onboardingEmpresa.done'))
    navigate('/')
  }

  if (!workspace) return null

  return (
    <div className="min-h-screen bg-background flex items-start justify-center py-12 px-4">
      <div className="w-full max-w-2xl space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold">{t('onboardingEmpresa.title')}</h1>
          <p className="text-muted-foreground text-sm">{t('onboardingEmpresa.subtitle')}</p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-between gap-2">
          {STEPS.map((s, i) => (
            <div key={s} className="flex-1 flex flex-col items-center gap-1">
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-colors ${
                  i < stepIndex
                    ? 'bg-primary border-primary text-primary-foreground'
                    : i === stepIndex
                      ? 'border-primary text-primary'
                      : 'border-border text-muted-foreground'
                }`}
              >
                {i < stepIndex ? <CheckCircle2 className="h-5 w-5" /> : STEP_ICONS[s]}
              </div>
              <span className={`text-xs font-medium hidden sm:block ${i === stepIndex ? 'text-primary' : 'text-muted-foreground'}`}>
                {t(`onboardingEmpresa.step.${s}`)}
              </span>
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="bg-card border rounded-xl p-6 space-y-6 min-h-[320px]">
          {step === 'company' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">{t('onboardingEmpresa.step.company')}</h2>
              <p className="text-sm text-muted-foreground">{t('onboardingEmpresa.companyDesc')}</p>
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label>{t('onboardingEmpresa.legalName')}</Label>
                  <Input
                    value={legalName}
                    onChange={e => setLegalName(e.target.value)}
                    placeholder={t('onboardingEmpresa.legalNamePlaceholder')}
                  />
                </div>
                <div className="space-y-1">
                  <Label>{t('onboardingEmpresa.taxId')}</Label>
                  <Input
                    value={taxId}
                    onChange={e => setTaxId(e.target.value)}
                    placeholder="00.000.000/0001-00"
                  />
                </div>
                <div className="space-y-1">
                  <Label>{t('onboardingEmpresa.address')}</Label>
                  <Input
                    value={address}
                    onChange={e => setAddress(e.target.value)}
                    placeholder={t('onboardingEmpresa.addressPlaceholder')}
                  />
                </div>
              </div>
            </div>
          )}

          {step === 'chart' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">{t('onboardingEmpresa.step.chart')}</h2>
              <p className="text-sm text-muted-foreground">{t('onboardingEmpresa.chartDesc')}</p>
              <ul className="space-y-2 text-sm">
                {['Revenue', 'COGS', 'OpEx', 'FinEx', 'Taxes', 'Transfers'].map(g => (
                  <li key={g} className="flex items-center gap-2 text-muted-foreground">
                    <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                    {t(`onboardingEmpresa.group.${g}`)}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted-foreground">{t('onboardingEmpresa.chartNote')}</p>
            </div>
          )}

          {step === 'users' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">{t('onboardingEmpresa.step.users')}</h2>
              <p className="text-sm text-muted-foreground">{t('onboardingEmpresa.usersDesc')}</p>
              <div className="flex gap-2">
                <Input
                  type="email"
                  value={inviteEmail}
                  onChange={e => setInviteEmail(e.target.value)}
                  placeholder={t('onboardingEmpresa.invitePlaceholder')}
                  className="flex-1"
                />
                <Button
                  variant="outline"
                  disabled={!inviteEmail || inviteMutation.isPending}
                  onClick={() => inviteMutation.mutate()}
                >
                  {t('onboardingEmpresa.invite')}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{t('onboardingEmpresa.usersNote')}</p>
            </div>
          )}

          {step === 'bank' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">{t('onboardingEmpresa.step.bank')}</h2>
              <p className="text-sm text-muted-foreground">{t('onboardingEmpresa.bankDesc')}</p>
              <Button variant="outline" onClick={() => navigate('/accounts')}>
                {t('onboardingEmpresa.connectBank')}
              </Button>
              <p className="text-xs text-muted-foreground">{t('onboardingEmpresa.bankNote')}</p>
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            onClick={goPrev}
            disabled={stepIndex === 0}
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            {t('common.back')}
          </Button>

          {stepIndex < STEPS.length - 1 ? (
            <Button onClick={goNext} disabled={setupMutation.isPending}>
              {t('common.next')}
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          ) : (
            <Button onClick={finish}>
              <CheckCircle2 className="h-4 w-4 mr-1" />
              {t('onboardingEmpresa.finish')}
            </Button>
          )}
        </div>

        {/* Skip */}
        <div className="text-center">
          <button
            className="text-xs text-muted-foreground underline-offset-4 hover:underline"
            onClick={finish}
          >
            {t('onboardingEmpresa.skip')}
          </button>
        </div>
      </div>
    </div>
  )
}
