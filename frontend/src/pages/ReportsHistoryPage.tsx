import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listReports } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatScore } from '@/lib/utils'

const STOPPED_LABELS: Record<string, string> = {
  completed_all_questions: 'Completed',
  low_recent_average: 'Ended early',
  abuse: 'Policy violation',
  manual: 'Manual',
}

export function ReportsHistoryPage() {
  const reports = useQuery({
    queryKey: queryKeys.reports,
    queryFn: listReports,
    retry: 2,
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Report history</CardTitle>
        <Button asChild size="sm" variant="outline">
          <Link to="/interviews/new">New interview</Link>
        </Button>
      </CardHeader>
      <CardContent>
        {reports.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : !reports.data?.reports.length ? (
          <p className="text-sm text-muted-foreground">
            No completed reports yet.{' '}
            <Link to="/interviews/new" className="text-primary underline">
              Start an interview
            </Link>
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Candidate</th>
                  <th className="pb-2 pr-4 font-medium">Date</th>
                  <th className="pb-2 pr-4 font-medium">Score</th>
                  <th className="pb-2 pr-4 font-medium">Questions</th>
                  <th className="pb-2 pr-4 font-medium">Outcome</th>
                  <th className="pb-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {reports.data.reports.map((row) => (
                  <tr
                    key={row.bot_id}
                    className="border-b border-border last:border-0 hover:bg-muted/40"
                  >
                    <td className="py-3 pr-4">{row.candidate_name ?? '—'}</td>
                    <td className="py-3 pr-4 text-muted-foreground">
                      {row.completed_at
                        ? new Date(row.completed_at).toLocaleString()
                        : '—'}
                    </td>
                    <td className="py-3 pr-4">{formatScore(row.overall_average)}</td>
                    <td className="py-3 pr-4">
                      {row.questions_scored}/{row.questions_planned}
                    </td>
                    <td className="py-3 pr-4 text-muted-foreground">
                      {row.stopped_reason
                        ? (STOPPED_LABELS[row.stopped_reason] ?? row.stopped_reason)
                        : '—'}
                    </td>
                    <td className="py-3">
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
  )
}
