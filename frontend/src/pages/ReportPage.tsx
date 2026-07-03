import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Copy, MessageSquare, Printer } from 'lucide-react'
import { getInterviewReport } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { markSessionCompleted } from '@/lib/session-store'
import { ApiError } from '@/lib/api-client'
import { buildFeedbackUrl } from '@/lib/feedback-url'
import { FeedbackViewDialog } from '@/components/feedback/FeedbackViewDialog'
import { ScoreSummary } from '@/components/report/ScoreSummary'
import { ReportInsights } from '@/components/report/ReportInsights'
import { QuestionScoreCard } from '@/components/report/QuestionScoreCard'
import { TranscriptBlock } from '@/components/report/TranscriptBlock'
import { ReportPrintView } from '@/components/report/ReportPrintView'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'

export function ReportPage() {
  const { botId = '' } = useParams()
  const navigate = useNavigate()
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackLinkCopied, setFeedbackLinkCopied] = useState(false)

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
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (reportQuery.isError) {
    const err = reportQuery.error
    if (err instanceof ApiError && err.status === 409) {
      return (
        <div className="space-y-4">
          <Button type="button" variant="outline" size="sm" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <Alert className="border-warning/30 bg-warning/5">
            Report not ready yet. The interview is still in progress or the closing message has
            not finished.
            <Button asChild variant="link" className="ml-2 h-auto p-0">
              <Link to={`/interviews/${botId}`}>Back to live session</Link>
            </Button>
          </Alert>
        </div>
      )
    }
    return (
      <div className="space-y-4">
        <Button type="button" variant="outline" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Alert className="border-destructive/30">
          Could not load report.
          <Button asChild variant="link" className="ml-2 h-auto p-0">
            <Link to="/">Dashboard</Link>
          </Button>
        </Alert>
      </div>
    )
  }

  const report = reportQuery.data!.report
  const completedLabel = report.completed_at
    ? new Date(report.completed_at).toLocaleString()
    : null

  return (
    <>
      <div className="report-page-root screen-only flex h-full min-h-0 flex-col overflow-hidden">
        <div className="no-print mb-4 shrink-0 flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
        <div className="flex min-w-0 items-start gap-3">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="shrink-0"
            aria-label="Go back"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>

          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight">{report.candidate_name}</h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">Interview report</Badge>
              <span>Session {report.bot_id.slice(0, 12)}…</span>
              {completedLabel ? <span>Completed {completedLabel}</span> : null}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setFeedbackOpen(true)}
          >
            <MessageSquare className="h-4 w-4" />
            Feedback
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(buildFeedbackUrl(botId))
                setFeedbackLinkCopied(true)
                window.setTimeout(() => setFeedbackLinkCopied(false), 2000)
              } catch {
                /* clipboard unavailable */
              }
            }}
          >
            <Copy className="h-4 w-4" />
            {feedbackLinkCopied ? 'Copied' : 'Copy feedback link'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-4 w-4" />
            Print
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
        <ScoreSummary report={report} />

        <ReportInsights develop={report.summary_develop} improve={report.summary_fix} />

        <section className="space-y-3">
          <div>
            <h3 className="text-base font-semibold">Question breakdown</h3>
            <p className="text-xs text-muted-foreground">
              Per-question scores, answers, and feedback
            </p>
          </div>
          <div className="space-y-4">
            {report.per_question.map((record) => (
              <QuestionScoreCard key={record.question_index} record={record} />
            ))}
          </div>
        </section>

        {report.transcript ? <TranscriptBlock lines={report.transcript} /> : null}
      </div>
      </div>

      <ReportPrintView report={report} />

      <FeedbackViewDialog
        botId={botId}
        candidateName={report.candidate_name}
        open={feedbackOpen}
        onOpenChange={setFeedbackOpen}
      />
    </>
  )
}
