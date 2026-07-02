import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { listReports } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { reportsWithinDays, STOPPED_LABELS } from '@/lib/dashboard-stats'
import { formatScore } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

type DaysFilter = 'all' | 7 | 15 | 30

const DATE_FILTERS: { value: DaysFilter; label: string }[] = [
  { value: 'all', label: 'All time' },
  { value: 7, label: 'Last 7 days' },
  { value: 15, label: 'Last 15 days' },
  { value: 30, label: 'Last 30 days' },
]

export function ReportsHistoryPage() {
  const [search, setSearch] = useState('')
  const [daysFilter, setDaysFilter] = useState<DaysFilter>('all')

  const reports = useQuery({
    queryKey: queryKeys.reports,
    queryFn: listReports,
    retry: 2,
  })

  const allReports = reports.data?.reports ?? []

  const filteredReports = useMemo(() => {
    let list = allReports
    if (daysFilter !== 'all') {
      list = reportsWithinDays(list, daysFilter)
    }
    const query = search.trim().toLowerCase()
    if (query) {
      list = list.filter((row) => (row.candidate_name ?? '').toLowerCase().includes(query))
    }
    return list
  }, [allReports, daysFilter, search])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CardHeader className="shrink-0 space-y-4 pb-4">
          <CardTitle>Report history</CardTitle>

          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative w-full max-w-sm">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                strokeWidth={1.5}
              />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by candidate name"
                className="pl-9"
                aria-label="Search by candidate name"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              {DATE_FILTERS.map(({ value, label }) => (
                <Button
                  key={value}
                  type="button"
                  size="sm"
                  variant={daysFilter === value ? 'default' : 'outline'}
                  onClick={() => setDaysFilter(value)}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>

        <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden pb-4">
          {reports.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : !allReports.length ? (
            <p className="text-sm text-muted-foreground">
              No completed reports yet.{' '}
              <Link to="/interviews/new" className="text-primary underline">
                Start an interview
              </Link>
            </p>
          ) : !filteredReports.length ? (
            <p className="text-sm text-muted-foreground">
              No reports match your search or date filter.
            </p>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-card text-left text-muted-foreground">
                    <th className="sticky top-0 z-10 bg-card px-4 py-2.5 font-medium">Candidate</th>
                    <th className="sticky top-0 z-10 bg-card px-4 py-2.5 font-medium">Date</th>
                    <th className="sticky top-0 z-10 bg-card px-4 py-2.5 font-medium">Score</th>
                    <th className="sticky top-0 z-10 bg-card px-4 py-2.5 font-medium">Questions</th>
                    <th className="sticky top-0 z-10 bg-card px-4 py-2.5 font-medium">Outcome</th>
                    <th className="sticky top-0 z-10 bg-card px-4 py-2.5 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {filteredReports.map((row) => (
                    <tr
                      key={row.bot_id}
                      className="border-b border-border last:border-0 hover:bg-muted/40"
                    >
                      <td className="px-4 py-3">{row.candidate_name ?? '—'}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {row.completed_at
                          ? new Date(row.completed_at).toLocaleString()
                          : '—'}
                      </td>
                      <td className="px-4 py-3">{formatScore(row.overall_average)}</td>
                      <td className="px-4 py-3">
                        {row.questions_scored}/{row.questions_planned}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {row.stopped_reason
                          ? (STOPPED_LABELS[row.stopped_reason] ?? row.stopped_reason)
                          : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <Button asChild variant="outline" size="sm">
                          <Link to={`/interviews/${row.bot_id}/report`}>View</Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
