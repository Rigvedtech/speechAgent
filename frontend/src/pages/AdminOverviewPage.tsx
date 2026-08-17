import { Building2, Inbox, Shield, Users } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { getAdminOverview } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { KpiCard } from '@/components/dashboard/KpiCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, DonutChart } from '@/components/admin/AdminCharts'
import { Skeleton } from '@/components/ui/skeleton'

export function AdminOverviewPage() {
  const overview = useQuery({
    queryKey: queryKeys.adminOverview,
    queryFn: getAdminOverview,
  })
  const data = overview.data

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      {overview.isError ? (
        <p className="text-sm text-destructive">
          Could not load stats. Restart the API server and refresh.
        </p>
      ) : overview.isLoading || !data ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Skeleton className="h-[88px] rounded-xl" />
          <Skeleton className="h-[88px] rounded-xl" />
          <Skeleton className="h-[88px] rounded-xl" />
          <Skeleton className="h-[88px] rounded-xl" />
        </div>
      ) : (
        <>
          <div className="grid shrink-0 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              compact
              className="rounded-xl"
              label="Pending requests"
              value={String(data.pending_requests)}
              hint="Waiting for review"
              icon={Inbox}
              iconWell
              iconClassName="text-warning"
              iconWellClassName="bg-warning/10"
              to="/admin/requests"
            />
            <KpiCard
              compact
              className="rounded-xl"
              label="Companies"
              value={String(data.customer_orgs)}
              hint={`${data.active_orgs} active · ${data.inactive_orgs} inactive`}
              icon={Building2}
              iconWell
              iconClassName="text-foreground/70"
              to="/admin/organizations"
            />
            <KpiCard
              compact
              className="rounded-xl"
              label="Org users"
              value={String(data.tenant_users)}
              hint="Org admin, recruiter, viewer"
              icon={Users}
              iconWell
              iconClassName="text-foreground/70"
              to="/admin/organizations"
            />
            <KpiCard
              compact
              className="rounded-xl"
              label="Platform admins"
              value={String(data.operators)}
              hint="Can grant access"
              icon={Shield}
              iconWell
              iconClassName="text-[var(--app-brand)]"
              iconWellClassName="bg-[var(--app-brand)]/10"
              to="/admin/operators"
            />
          </div>

          <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3">
            <div className="grid min-h-0 gap-3 lg:grid-cols-3">
              <Card className="flex min-h-0 flex-col overflow-hidden rounded-xl">
                <CardHeader className="shrink-0 p-3.5 pb-1">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Companies</CardTitle>
                </CardHeader>
                <CardContent className="flex min-h-0 flex-1 items-center p-3.5 pt-1">
                  <DonutChart
                    totalLabel={String(data.customer_orgs)}
                    slices={[
                      { label: 'Active', value: data.active_orgs, color: '#3b82f6' },
                      { label: 'Inactive', value: data.inactive_orgs, color: '#cbd5e1' },
                    ]}
                  />
                </CardContent>
              </Card>
              <Card className="flex min-h-0 flex-col overflow-hidden rounded-xl">
                <CardHeader className="shrink-0 p-3.5 pb-1">
                  <CardTitle className="text-sm font-medium text-muted-foreground">People</CardTitle>
                </CardHeader>
                <CardContent className="flex min-h-0 flex-1 items-center p-3.5 pt-1">
                  <DonutChart
                    totalLabel={String(data.tenant_users + data.operators)}
                    slices={[
                      { label: 'Org admin', value: data.users_by_role?.admin ?? 0, color: '#1d4ed8' },
                      { label: 'Recruiter', value: data.users_by_role?.recruiter ?? 0, color: '#6366f1' },
                      { label: 'Viewer', value: data.users_by_role?.viewer ?? 0, color: '#93c5fd' },
                      { label: 'Platform admin', value: data.operators, color: '#8b5cf6' },
                    ]}
                  />
                </CardContent>
              </Card>
              <Card className="flex min-h-0 flex-col overflow-hidden rounded-xl">
                <CardHeader className="shrink-0 p-3.5 pb-1">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Access requests</CardTitle>
                </CardHeader>
                <CardContent className="flex min-h-0 flex-1 items-center p-3.5 pt-1">
                  <DonutChart
                    totalLabel={String(
                      (data.requests_by_status?.pending ?? 0) +
                        (data.requests_by_status?.granted ?? 0) +
                        (data.requests_by_status?.rejected ?? 0),
                    )}
                    slices={[
                      { label: 'Pending', value: data.requests_by_status?.pending ?? 0, color: '#f59e0b' },
                      { label: 'Granted', value: data.requests_by_status?.granted ?? 0, color: '#10b981' },
                      { label: 'Rejected', value: data.requests_by_status?.rejected ?? 0, color: '#94a3b8' },
                    ]}
                  />
                </CardContent>
              </Card>
            </div>

            <Card className="flex min-h-0 flex-col overflow-hidden rounded-xl">
              <CardHeader className="flex shrink-0 flex-row items-center justify-between gap-3 space-y-0 p-3.5 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Interviews · last 6 months
                </CardTitle>
                <p className="text-xs tabular-nums text-muted-foreground">
                  {data.interviews_this_month} this month
                </p>
              </CardHeader>
              <CardContent className="flex min-h-0 flex-1 flex-col p-3.5 pt-0">
                <BarChart
                  bars={(data.interviews_by_month ?? []).map((row) => ({
                    label: row.label,
                    value: Number(row.count),
                  }))}
                />
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
