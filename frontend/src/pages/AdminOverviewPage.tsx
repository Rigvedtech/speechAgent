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
    <div className="flex min-h-0 flex-1 flex-col gap-3 pb-1">
      {overview.isError ? (
        <p className="text-sm text-destructive">
          Could not load stats. Restart the API server and refresh.
        </p>
      ) : overview.isLoading || !data ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Skeleton className="h-[96px] rounded-xl" />
          <Skeleton className="h-[96px] rounded-xl" />
          <Skeleton className="h-[96px] rounded-xl" />
          <Skeleton className="h-[96px] rounded-xl" />
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              className="p-4"
              label="Pending requests"
              value={String(data.pending_requests)}
              hint="Waiting for review"
              icon={Inbox}
              to="/admin/requests"
            />
            <KpiCard
              className="p-4"
              label="Companies"
              value={String(data.customer_orgs)}
              hint={`${data.active_orgs} active · ${data.inactive_orgs} inactive`}
              icon={Building2}
              to="/admin/organizations"
            />
            <KpiCard
              className="p-4"
              label="Org users"
              value={String(data.tenant_users)}
              hint="Org admin, recruiter, viewer"
              icon={Users}
              to="/admin/organizations"
            />
            <KpiCard
              className="p-4"
              label="Platform admins"
              value={String(data.operators)}
              hint="Can grant access"
              icon={Shield}
              to="/admin/operators"
            />
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            <Card className="h-full">
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Companies</CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <DonutChart
                  totalLabel={String(data.customer_orgs)}
                  slices={[
                    { label: 'Active', value: data.active_orgs, color: 'var(--app-foreground)' },
                    { label: 'Inactive', value: data.inactive_orgs, color: 'var(--app-muted-foreground)' },
                  ]}
                />
              </CardContent>
            </Card>
            <Card className="h-full">
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">People</CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <DonutChart
                  totalLabel={String(data.tenant_users + data.operators)}
                  slices={[
                    { label: 'Org admin', value: data.users_by_role?.admin ?? 0, color: 'var(--app-foreground)' },
                    { label: 'Recruiter', value: data.users_by_role?.recruiter ?? 0, color: '#737373' },
                    { label: 'Viewer', value: data.users_by_role?.viewer ?? 0, color: '#a3a3a3' },
                    { label: 'Platform admin', value: data.operators, color: 'var(--app-brand)' },
                  ]}
                />
              </CardContent>
            </Card>
            <Card className="h-full">
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Access requests</CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <DonutChart
                  totalLabel={String(
                    (data.requests_by_status?.pending ?? 0) +
                      (data.requests_by_status?.granted ?? 0) +
                      (data.requests_by_status?.rejected ?? 0),
                  )}
                  slices={[
                    { label: 'Pending', value: data.requests_by_status?.pending ?? 0, color: 'var(--app-warning)' },
                    { label: 'Granted', value: data.requests_by_status?.granted ?? 0, color: 'var(--app-success)' },
                    { label: 'Rejected', value: data.requests_by_status?.rejected ?? 0, color: 'var(--app-muted-foreground)' },
                  ]}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 p-4 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Interviews · last 6 months
              </CardTitle>
              <p className="text-xs tabular-nums text-muted-foreground">
                {data.interviews_this_month} this month
              </p>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <BarChart
                bars={(data.interviews_by_month ?? []).map((row) => ({
                  label: row.label,
                  value: Number(row.count),
                }))}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
