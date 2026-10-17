import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import type { ArApForecastBucket } from '@/lib/api'
import { arAp as arApApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/format'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'

interface CashFlowForecastProps {
  currency: string
}

export function CashFlowForecast({ currency }: CashFlowForecastProps) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const { mask } = usePrivacyMode()
  const [period, setPeriod] = useState<'month' | 'week'>('month')

  const { data, isLoading } = useQuery({
    queryKey: ['ar-ap-forecast', currency, period],
    queryFn: () => arApApi.forecast(currency, period, period === 'month' ? 12 : 8),
  })

  const fmt = (v: string | number) => mask(formatCurrency(Number(v), currency, locale))

  const maxAbs = data
    ? Math.max(...data.buckets.map((b: ArApForecastBucket) => Math.max(Number(b.receivable), Number(b.payable), Number(b.taxes ?? 0))), 1)
    : 1

  return (
    <div className="space-y-4">
      {/* Period toggle */}
      <div className="flex gap-2">
        <Button
          size="sm"
          variant={period === 'month' ? 'default' : 'outline'}
          onClick={() => setPeriod('month')}
        >
          {t('arAp.forecastPeriodMonth')}
        </Button>
        <Button
          size="sm"
          variant={period === 'week' ? 'default' : 'outline'}
          onClick={() => setPeriod('week')}
        >
          {t('arAp.forecastPeriodWeek')}
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-10 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : !data || data.buckets.every((b) => Number(b.receivable) === 0 && Number(b.payable) === 0 && Number(b.taxes ?? 0) === 0) ? (
        <p className="text-muted-foreground text-sm py-8 text-center">{t('arAp.forecastEmpty')}</p>
      ) : (
        <div className="rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium">{t('common.period', 'Período')}</th>
                <th className="px-4 py-2 text-right font-medium text-green-600">{t('arAp.forecastReceivable')}</th>
                <th className="px-4 py-2 text-right font-medium text-destructive">{t('arAp.forecastPayable')}</th>
                <th className="px-4 py-2 text-right font-medium text-orange-600">{t('tax.taxForecast')}</th>
                <th className="px-4 py-2 text-right font-medium">{t('arAp.forecastNet')}</th>
                <th className="px-4 py-2 w-48" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.buckets.map((bucket) => {
                const net = Number(bucket.net)
                const recv = Number(bucket.receivable)
                const pay = Number(bucket.payable)
                const recvWidth = Math.round((recv / maxAbs) * 100)
                const payWidth = Math.round((pay / maxAbs) * 100)
                const tax = Number(bucket.taxes ?? 0)
                const taxWidth = Math.round((tax / maxAbs) * 100)
                return (
                  <tr key={bucket.label} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs">{bucket.label}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-green-600">{fmt(recv)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-destructive">{fmt(pay)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-orange-600">{fmt(tax)}</td>
                    <td className={`px-4 py-3 text-right tabular-nums font-medium ${net >= 0 ? 'text-green-600' : 'text-destructive'}`}>
                      {fmt(net)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-0.5">
                        <div className="h-1.5 rounded-full bg-green-200 dark:bg-green-900/40" style={{ width: `${recvWidth}%` }} />
                        <div className="h-1.5 rounded-full bg-red-200 dark:bg-red-900/40" style={{ width: `${payWidth}%` }} />
                        <div className="h-1.5 rounded-full bg-orange-200 dark:bg-orange-900/40" style={{ width: `${taxWidth}%` }} />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
