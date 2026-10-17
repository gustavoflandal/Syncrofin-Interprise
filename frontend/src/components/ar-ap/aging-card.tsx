import { useTranslation } from 'react-i18next'
import { formatCurrency } from '@/lib/format'
import type { AgingSide } from '@/lib/api'

interface AgingCardProps {
  title: string
  side: AgingSide
  currency: string
  locale: string
  mask: (v: string) => string
}

export function AgingCard({ title, side, currency, locale, mask }: AgingCardProps) {
  const { t } = useTranslation()
  // Decimal fields are strings from the API; convert before formatting.
  const fmt = (v: string | number) => mask(formatCurrency(Number(v), currency, locale))

  return (
    <div className="rounded-xl border bg-card p-6 space-y-4">
      <h3 className="font-semibold text-lg">{title}</h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{t('arAp.outstanding')}</p>
          <p className="text-xl font-bold">{fmt(side.outstanding)}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{t('arAp.overdue')}</p>
          <p className="text-xl font-bold text-destructive">{fmt(side.overdue_amount)}</p>
          {side.overdue_count > 0 && (
            <p className="text-xs text-muted-foreground">
              {t('arAp.overdueCount', { count: side.overdue_count })}
            </p>
          )}
        </div>
      </div>

      <div>
        <p className="text-sm font-medium mb-2">{t('arAp.aging')}</p>
        <div className="space-y-1 text-sm">
          {[
            { key: 'current', label: t('arAp.current'), value: side.current },
            { key: 'd1_30', label: t('arAp.aging1_30'), value: side.d1_30 },
            { key: 'd31_60', label: t('arAp.aging31_60'), value: side.d31_60 },
            { key: 'd61_90', label: t('arAp.aging61_90'), value: side.d61_90 },
            { key: 'd90_plus', label: t('arAp.aging90plus'), value: side.d90_plus },
          ].map(({ key, label, value }) => (
            <div key={key} className="flex justify-between">
              <span className="text-muted-foreground">{label}</span>
              <span className={Number(value) > 0 && key !== 'current' ? 'text-destructive' : ''}>
                {fmt(value)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {side.upcoming.length > 0 && (
        <div>
          <p className="text-sm font-medium mb-2">{t('arAp.upcoming')}</p>
          <div className="space-y-1">
            {side.upcoming.slice(0, 5).map((inv) => (
              <div key={inv.id} className="flex justify-between text-sm">
                <span className="text-muted-foreground truncate max-w-[140px]">
                  {inv.payee_name ?? (inv.series ? `${inv.series}-${inv.number}` : `#${inv.number}`)}
                </span>
                <span>{fmt(inv.balance)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
