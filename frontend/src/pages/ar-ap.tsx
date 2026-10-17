import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Upload } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { AgingCard } from '@/components/ar-ap/aging-card'
import { TitlesList } from '@/components/ar-ap/titles-list'
import { CashFlowForecast } from '@/components/ar-ap/cash-flow-forecast'
import { ImportNfeDialog } from '@/components/ar-ap/import-nfe-dialog'
import { arAp as arApApi } from '@/lib/api'
import { useWorkspace } from '@/contexts/workspace-context'
import { formatCurrency } from '@/lib/format'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'

type Tab = 'overview' | 'receivable' | 'payable' | 'forecast'

export default function ArApPage() {
  const { t } = useTranslation()
  const { current } = useWorkspace()
  const currency = current?.default_currency ?? 'BRL'
  const locale = useDisplayLocale()
  const { mask } = usePrivacyMode()
  const [tab, setTab] = useState<Tab>('overview')
  const [nfeOpen, setNfeOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['ar-ap-overview'],
    queryFn: arApApi.overview,
  })

  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: t('arAp.tabOverview') },
    { id: 'receivable', label: t('arAp.receivable') },
    { id: 'payable', label: t('arAp.payable') },
    { id: 'forecast', label: t('arAp.tabForecast') },
  ]

  return (
    <div className="space-y-6">
      <PageHeader section="business" title={t('arAp.title')} />

      {/* Tab bar */}
      <div className="flex gap-1 border-b">
        {tabs.map((t_) => (
          <button
            key={t_.id}
            onClick={() => setTab(t_.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t_.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t_.label}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <>
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="h-64 rounded-xl bg-muted animate-pulse" />
              <div className="h-64 rounded-xl bg-muted animate-pulse" />
            </div>
          ) : data ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <AgingCard
                  title={t('arAp.receivable')}
                  side={data.receivable}
                  currency={currency}
                  locale={locale}
                  mask={mask}
                />
                <AgingCard
                  title={t('arAp.payable')}
                  side={data.payable}
                  currency={currency}
                  locale={locale}
                  mask={mask}
                />
              </div>

              <div className="rounded-xl border bg-card p-6">
                <p className="text-sm text-muted-foreground">{t('arAp.netPosition')}</p>
                <p className={`text-2xl font-bold ${Number(data.net_position) >= 0 ? 'text-green-600' : 'text-destructive'}`}>
                  {mask(formatCurrency(Number(data.net_position), currency, locale))}
                </p>
              </div>
            </>
          ) : (
            <p className="text-muted-foreground">{t('arAp.noTitles')}</p>
          )}
        </>
      )}

      {/* Receivable tab */}
      {tab === 'receivable' && (
        <TitlesList direction="receivable" currency={currency} />
      )}

      {/* Payable tab */}
      {tab === 'payable' && (
        <>
          <div className="flex justify-end">
            <button
              onClick={() => setNfeOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border hover:bg-muted transition-colors"
            >
              <Upload className="h-4 w-4" />
              {t('arAp.importNfe')}
            </button>
          </div>
          <TitlesList direction="payable" currency={currency} />
          <ImportNfeDialog open={nfeOpen} onClose={() => setNfeOpen(false)} />
        </>
      )}

      {/* Forecast tab */}
      {tab === 'forecast' && (
        <CashFlowForecast currency={currency} />
      )}
    </div>
  )
}
