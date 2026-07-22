import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { useActiveSessions } from '@/hooks/useActiveSessions'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock,
  Radio,
} from 'lucide-react'
import { listReports, listScheduledInterviews } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import {
  computeDashboardKpis,
  DASHBOARD_PASS_SCORE,
  formatFinishedBreakdownHint,
  STOPPED_LABELS,
} from '@/lib/dashboard-stats'
import { KpiCard } from '@/components/dashboard/KpiCard'
import { FeedbackViewDialog } from '@/components/feedback/FeedbackViewDialog'
import { FeedbackRowButton } from '@/components/feedback/FeedbackRowButton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { formatScore, truncate } from '@/lib/utils'

export function DashboardPage() {
  const [feedbackBotId, setFeedbackBotId] = useState<string | null>(null)
  const [feedbackCandidate, setFeedbackCandidate] = useState<string | undefined>()
  const sessions = useActiveSessions()
  const reports = useQuery({
    queryKey: queryKeys.reports,
    queryFn: listReports,
    retry: 2,
  })
  const scheduled = useQuery({
    queryKey: queryKeys.scheduledInterviews,
    queryFn: listScheduledInterviews,
    retry: 2,
  })

  const reportList = reports.data?.reports ?? []

  const kpis = useMemo(() => computeDashboardKpis(reportList), [reportList])
  const recentReports = useMemo(() => reportList.slice(0, 4), [reportList])

  const liveCount = sessions.data?.active_sessions ?? 0
  const scheduledCount = scheduled.data?.length ?? 0
  const showActiveSection = !sessions.isLoading && liveCount > 0
  const loadingKpis = reports.isLoading || scheduled.isLoading

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          Interview activity and performance at a glance
        </p>
        <Button asChild size="sm">
          <Link to="/interviews/new">New interview</Link>
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {loadingKpis ? (
          <>
            <Skeleton className="h-[108px] rounded-xl" />
            <Skeleton className="h-[108px] rounded-xl" />
            <Skeleton className="h-[108px] rounded-xl" />
            <Skeleton className="h-[108px] rounded-xl" />
          </>
        ) : (
          <>
            <KpiCard
              label="Live & scheduled"
              value={String(scheduledCount)}
              hint={`${liveCount} live, ${scheduledCount} scheduled`}
              icon={Radio}
              iconClassName="text-success"
              to="/interviews/scheduled"
            />
            <KpiCard
              label="Interviews finished"
              value={String(kpis.totalCompleted)}
              hint={formatFinishedBreakdownHint(kpis)}
              icon={CheckCircle2}
              iconClassName="text-success/75"
              to="/reports"
            />
            <KpiCard
              label="Avg score (7 days)"
              value={formatScore(kpis.avgScore7d)}
              hint="Overall average out of 10"
              icon={BarChart3}
              iconClassName="text-brand"
            />
            <KpiCard
              label="Pass rate (7 days)"
              value={kpis.passRate7d != null ? `${Math.round(kpis.passRate7d)}%` : '—'}
              hint={`Score ≥ ${DASHBOARD_PASS_SCORE} / 10`}
              icon={Activity}
              iconClassName="text-brand/75"
            />
          </>
        )}
      </div>

      {showActiveSection ? (
        <Card className="border-success/20">
          <CardHeader className="flex flex-row items-center justify-between pb-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="live-dot" aria-hidden />
                <CardTitle className="text-base font-semibold">Active interviews</CardTitle>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {liveCount} session{liveCount === 1 ? '' : 's'} in progress
              </p>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="pb-3 pr-4 font-medium">Candidate</th>
                    <th className="pb-3 pr-4 font-medium">Meeting</th>
                    <th className="pb-3 pr-4 font-medium">Phase</th>
                    <th className="pb-3 pr-4 font-medium">Started</th>
                    <th className="pb-3 pr-4 font-medium">Scored</th>
                    <th className="pb-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(sessions.data?.bots ?? []).map((bot) => (
                    <tr
                      key={bot.bot_id}
                      className="row-hover border-b border-border last:border-0"
                    >
                      <td className="py-3 pr-4 font-medium">{bot.candidate_name ?? '—'}</td>
                      <td className="py-3 pr-4 text-muted-foreground">
                        {truncate(bot.meeting_url, 40)}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant="secondary">{bot.interview_phase ?? '—'}</Badge>
                      </td>
                      <td className="py-3 pr-4">{bot.is_started ? 'Yes' : 'No'}</td>
                      <td className="py-3 pr-4 tabular-nums">{bot.questions_scored}</td>
                      <td className="py-3">
                        <div className="flex flex-wrap gap-2">
                          <Button asChild variant="outline" size="sm">
                            <Link to={`/interviews/${bot.bot_id}`}>Open</Link>
                          </Button>
                          {(bot.interview_ended || bot.interview_phase === 'ended') && (
                            <Button asChild variant="ghost" size="sm">
                              <Link to={`/interviews/${bot.bot_id}/report`}>Report</Link>
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="select-none">
          <CardHeader className="flex flex-row items-center justify-between pb-4">
            <div>
              <CardTitle className="text-base font-semibold">Recent interviews</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">Latest completed reports</p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link to="/reports">View all</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {sessions.isLoading || reports.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : !recentReports.length ? (
              <div className="rounded-lg border border-dashed border-border bg-muted/30 px-6 py-10 text-center">
                <Clock className="mx-auto h-8 w-8 text-muted-foreground/50" strokeWidth={1.25} />
                <p className="mt-3 text-sm font-medium">No completed interviews yet</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Reports appear here after an interview ends
                </p>
                <Button asChild size="sm" className="mt-4">
                  <Link to="/interviews/new">Schedule first interview</Link>
                </Button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
                      <th className="pb-3 pr-4 font-medium">Candidate</th>
                      <th className="pb-3 pr-4 font-medium">Date</th>
                      <th className="pb-3 pr-4 font-medium">Score</th>
                      <th className="pb-3 pr-4 font-medium">Questions</th>
                      <th className="pb-3 pr-4 font-medium">Outcome</th>
                      <th className="pb-3 font-medium">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentReports.map((row) => (
                      <tr
                        key={row.bot_id}
                        className="row-hover border-b border-border last:border-0"
                      >
                        <td className="py-3 pr-4 font-medium">
                          {row.candidate_name ?? '—'}
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground">
                          {row.completed_at
                            ? new Date(row.completed_at).toLocaleDateString(undefined, {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })
                            : '—'}
                        </td>
                        <td className="py-3 pr-4 tabular-nums">{formatScore(row.overall_average)}</td>
                        <td className="py-3 pr-4 tabular-nums text-muted-foreground">
                          {row.questions_scored}/{row.questions_planned}
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground">
                          {row.stopped_reason
                            ? (STOPPED_LABELS[row.stopped_reason] ?? row.stopped_reason)
                            : '—'}
                        </td>
                        <td className="py-3">
                          <div className="flex flex-wrap gap-2">
                            <Button asChild variant="outline" size="sm">
                              <Link to={`/interviews/${row.bot_id}/report`}>Report</Link>
                            </Button>
                            <FeedbackRowButton
                              hasFeedback={row.has_feedback}
                              onViewSubmitted={() => {
                                setFeedbackBotId(row.bot_id)
                                setFeedbackCandidate(row.candidate_name)
                              }}
                            />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
      <FeedbackViewDialog
        botId={feedbackBotId ?? ''}
        candidateName={feedbackCandidate}
        open={Boolean(feedbackBotId)}
        onOpenChange={(open) => {
          if (!open) {
            setFeedbackBotId(null)
            setFeedbackCandidate(undefined)
          }
        }}
      />
    </div>
  )
}
