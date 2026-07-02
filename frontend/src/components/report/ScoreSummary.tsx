import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatScore } from '@/lib/utils'
import type { InterviewReport } from '@/types/api'

const STOPPED_LABELS: Record<string, string> = {
  none: 'In progress',
  completed_all_questions: 'Completed all planned questions',
  low_recent_average: 'Ended early — rolling average below threshold',
  abuse: 'Ended — policy violation',
  manual: 'Ended manually',
}

function outcomeBadge(reason: string) {
  if (reason === 'completed_all_questions') {
    return <Badge variant="success">Completed</Badge>
  }
  if (reason === 'low_recent_average') {
    return <Badge variant="warning">Ended early</Badge>
  }
  if (reason === 'abuse') {
    return <Badge variant="destructive">Policy violation</Badge>
  }
  return <Badge variant="secondary">{STOPPED_LABELS[reason] ?? reason.replace(/_/g, ' ')}</Badge>
}

interface ScoreSummaryProps {
  report: InterviewReport
}

export function ScoreSummary({ report }: ScoreSummaryProps) {
  const stopped =
    STOPPED_LABELS[report.stopped_reason] ?? report.stopped_reason.replace(/_/g, ' ')

  const metrics = [
    {
      label: 'Overall score',
      value: formatScore(report.overall_average),
      hint: 'Average across all scored answers',
    },
    {
      label: `Rolling avg (${report.rolling_window})`,
      value: formatScore(report.last_4_average),
      hint: 'Recent answer performance',
    },
    {
      label: 'Questions',
      value: `${report.questions_scored}/${report.questions_planned}`,
      hint: stopped,
    },
  ]

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/20 pb-4">
        <div>
          <CardTitle className="text-base">Performance summary</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Scores and completion status for this interview
          </p>
        </div>
        {outcomeBadge(report.stopped_reason)}
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid sm:grid-cols-3 sm:divide-x sm:divide-border">
          {metrics.map((metric) => (
            <div key={metric.label} className="px-6 py-5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {metric.label}
              </p>
              <p className="mt-2 text-3xl font-semibold tracking-tight">{metric.value}</p>
              <p className="mt-1.5 text-xs leading-snug text-muted-foreground">{metric.hint}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
