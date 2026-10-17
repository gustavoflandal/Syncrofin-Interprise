import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { FileLock2 } from 'lucide-react'
import { dataRequests as api } from '@/lib/api'
import { Skeleton } from '@/components/ui/skeleton'

/** How many titular requests (D1) are waiting on the administrator, with a link to the queue. */
export function DataRequestsCard() {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['admin-data-requests-pending-count'],
    queryFn: () => api.adminList('pending'),
  })

  return (
    <div className="mt-6 rounded-xl border border-border/60 bg-card overflow-hidden">
      <div className="px-5 py-4 border-b border-border/40">
        <div className="flex items-center gap-2 mb-0.5">
          <FileLock2 size={15} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">{t('admin.dataRequests.card.title')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('admin.dataRequests.card.description')}</p>
      </div>
      <div className="space-y-2 px-5 py-4">
        {isLoading ? (
          <Skeleton className="h-6 w-24" />
        ) : (
          <p className="text-2xl font-semibold text-foreground">{data?.items.length ?? 0}</p>
        )}
        <Link to="/admin/data-requests" className="inline-block text-xs font-medium text-primary hover:underline">
          {t('admin.dataRequests.card.viewAll')}
        </Link>
      </div>
    </div>
  )
}
