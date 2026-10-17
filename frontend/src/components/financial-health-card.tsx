import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, HeartPulse } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { dashboard } from '@/lib/api'
import { formatCurrency } from '@/lib/format'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { cn } from '@/lib/utils'
import { formatComponentValue } from '@/lib/health-format'
import type { HealthLevel } from '@/types'

const LEVEL_STYLE: Record<HealthLevel, { ring: string; text: string; bar: string }> = {
  good: { ring: 'border-emerald-500/40', text: 'text-emerald-600 dark:text-emerald-400', bar: 'bg-emerald-500' },
  attention: { ring: 'border-amber-500/40', text: 'text-amber-600 dark:text-amber-400', bar: 'bg-amber-500' },
  risk: { ring: 'border-red-500/40', text: 'text-red-600 dark:text-red-400', bar: 'bg-red-500' },
  unknown: { ring: 'border-border', text: 'text-muted-foreground', bar: 'bg-muted-foreground' },
}

function shortDate(iso: string, locale: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(locale, { day: '2-digit', month: '2-digit' })
}

/**
 * "Am I okay?" and "will I run out?" on one card.
 *
 * The score is a plain weighted average (see `health_service.py`), and every
 * component is shown with the value behind it and its target, so the number
 * can always be argued with. The forecast beside it only counts what is
 * already promised (recurring bills and open invoices), which the card says.
 */
export function FinancialHealthCard() {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const { mask } = usePrivacyMode()

  const { data: health } = useQuery({
    queryKey: ['dashboard', 'financial-health'],
    queryFn: () => dashboard.financialHealth(),
    staleTime: 5 * 60 * 1000,
  })
  const { data: forecast } = useQuery({
    queryKey: ['dashboard', 'cash-flow-forecast', 90],
    queryFn: () => dashboard.cashFlowForecast(90),
    staleTime: 5 * 60 * 1000,
  })

  if (!health || !forecast) return null

  const currency = health.primary_currency
  const style = LEVEL_STYLE[health.level]
  const money = (v: number) => mask(formatCurrency(v, currency, locale))
  const goesNegative = forecast.first_negative_week_start !== null

  const chartData = [
    { label: shortDate(forecast.start_date, locale), balance: forecast.starting_balance },
    ...forecast.buckets.map((b) => ({ label: shortDate(b.end, locale), balance: b.balance })),
  ]

  return (
    <section
      data-testid="financial-health-card"
      className="bg-card rounded-xl border border-border shadow-sm mb-5"
      aria-label={t('health.title')}
    >
      <div className="px-5 py-4 border-b border-border flex items-center gap-2">
        <HeartPulse size={16} className="text-primary" />
        <h2 className="text-sm font-semibold text-foreground">{t('health.title')}</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-6 p-5">
        {/* Score + components */}
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div
              className={cn('flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-full border-4', style.ring)}
              aria-label={t('health.scoreAria', { score: health.score ?? '—' })}
            >
              <span className={cn('text-2xl font-bold leading-none', style.text)}>
                {health.score ?? '—'}
              </span>
              <span className="text-[10px] text-muted-foreground">/100</span>
            </div>
            <div>
              <p className={cn('text-sm font-semibold', style.text)}>{t(`health.level.${health.level}`)}</p>
              <p className="text-xs text-muted-foreground">
                {health.score === null
                  ? t('health.noData')
                  : t('health.basedOn', { months: health.months_analysed })}
              </p>
            </div>
          </div>

          <ul className="space-y-3">
            {health.components.map((c) => (
              <li key={c.key}>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="font-medium text-foreground">{t(`health.component.${c.key}`)}</span>
                  <span className="text-muted-foreground">
                    {formatComponentValue(c, locale, t('health.months'))}
                    <span className="opacity-60">
                      {' · '}
                      {t('health.target')}{' '}
                      {formatComponentValue({ ...c, value: c.target }, locale, t('health.months'))}
                    </span>
                  </span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-muted overflow-hidden" role="presentation">
                  <div
                    className={cn('h-full rounded-full', LEVEL_STYLE[c.status].bar)}
                    style={{ width: `${Math.max(2, Math.min(100, c.score))}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>

          {health.overdue_receivables.count > 0 && (
            <p className="flex items-start gap-2 rounded-md bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-300">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              {t('health.overdueReceivables', {
                count: health.overdue_receivables.count,
                total: money(health.overdue_receivables.total),
              })}
            </p>
          )}
        </div>

        {/* Forecast */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-semibold text-foreground">{t('health.forecastTitle')}</p>
            <p className="text-xs text-muted-foreground">
              {t('health.forecastRange', { days: 90 })}
            </p>
          </div>

          <div className="mt-2 h-44" role="img" aria-label={t('health.forecastAria')}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="fh-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-primary, #6767e7)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--color-primary, #6767e7)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" opacity={0.1} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis hide domain={['auto', 'auto']} />
                <ReferenceLine y={0} stroke="#ef4444" strokeDasharray="4 4" />
                <Tooltip
                  formatter={(value) => [money(Number(value)), t('health.balance')]}
                  contentStyle={{ fontSize: 12, borderRadius: 8 }}
                />
                <Area
                  type="monotone"
                  dataKey="balance"
                  stroke="var(--color-primary, #6767e7)"
                  strokeWidth={2}
                  fill="url(#fh-fill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
            <div>
              <dt className="text-muted-foreground">{t('health.today')}</dt>
              <dd className="font-semibold text-foreground">{money(forecast.starting_balance)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t('health.lowest')}</dt>
              <dd className={cn('font-semibold', forecast.lowest_balance < 0 ? 'text-red-600 dark:text-red-400' : 'text-foreground')}>
                {money(forecast.lowest_balance)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t('health.in90')}</dt>
              <dd className="font-semibold text-foreground">{money(forecast.ending_balance)}</dd>
            </div>
          </dl>

          {goesNegative && forecast.first_negative_week_start && (
            <p
              role="alert"
              className="mt-3 flex items-start gap-2 rounded-md bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-300"
            >
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              {t('health.negativeWarning', {
                date: shortDate(forecast.first_negative_week_start, locale),
              })}
            </p>
          )}
          <p className="mt-3 text-[11px] leading-snug text-muted-foreground">{t('health.assumptions')}</p>
        </div>
      </div>
    </section>
  )
}
