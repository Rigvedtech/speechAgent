import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getInterviewReport } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { markSessionCompleted } from '@/lib/session-store'
import { ApiError } from '@/lib/api-client'
import { ScoreSummary } from '@/components/report/ScoreSummary'
import { QuestionScoreCard } from '@/components/report/QuestionScoreCard'
import { TranscriptBlock } from '@/components/report/TranscriptBlock'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert } from '@/components/ui/alert'
import { useEffect } from 'react'

export function ReportPage() {
  const { botId = '' } = useParams()

  const reportQuery = useQuery({
    queryKey: queryKeys.report(botId),
    queryFn: () => getInterviewReport(botId),
    enabled: Boolean(botId),
    refetchInterval: (query) => {
      const err = query.state.error
      if (err instanceof ApiError && err.status === 409) return 5000
      return false
    },
    retry: (failureCount, error) => {
      if (error instanceof ApiError && (error.status === 409 || error.status === 400)) {
        return false
      }
      return failureCount < 2
    },
  })

  useEffect(() => {
    if (reportQuery.data?.report) {
      markSessionCompleted(botId)
    }
  }, [botId, reportQuery.data])

  if (reportQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (reportQuery.isError) {
    const err = reportQuery.error
    if (err instanceof ApiError && err.status === 409) {
      return (
        <Alert className="border-warning/30 bg-warning/5">
          Report not ready yet. The interview is still in progress or the closing message has
          not finished.
          <Button asChild variant="link" className="ml-2 h-auto p-0">
            <Link to={`/interviews/${botId}`}>Back to live session</Link>
          </Button>
        </Alert>
      )
    }
    return (
      <Alert className="border-destructive/30">
        Could not load report.
        <Button asChild variant="link" className="ml-2 h-auto p-0">
          <Link to="/">Dashboard</Link>
        </Button>
      </Alert>
    )
  }

  const report = reportQuery.data!.report

  return (
    <div className="space-y-6">
      <div className="no-print flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">{report.candidate_name}</h2>
          <p className="text-sm text-muted-foreground">Session {report.bot_id.slice(0, 12)}…</p>
        </div>
        <Button variant="outline" onClick={() => window.print()}>
          Print
        </Button>
      </div>

      <ScoreSummary report={report} />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Areas to develop</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm">
              {report.summary_develop.length ? (
                report.summary_develop.map((item) => <li key={item}>{item}</li>)
              ) : (
                <li className="text-muted-foreground">None noted</li>
              )}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Suggested improvements</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm">
              {report.summary_fix.length ? (
                report.summary_fix.map((item) => <li key={item}>{item}</li>)
              ) : (
                <li className="text-muted-foreground">None noted</li>
              )}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold">Per-question scores</h3>
        {report.per_question.map((record) => (
          <QuestionScoreCard key={record.question_index} record={record} />
        ))}
      </div>

      {report.transcript && <TranscriptBlock lines={report.transcript} />}
    </div>
  )
}
