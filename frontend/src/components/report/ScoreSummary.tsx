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

interface ScoreSummaryProps {
  report: InterviewReport
}

export function ScoreSummary({ report }: ScoreSummaryProps) {
  const stopped =
    STOPPED_LABELS[report.stopped_reason] ??
    report.stopped_reason.replace(/_/g, ' ')

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Overall average
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-semibold">{formatScore(report.overall_average)}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Last {report.rolling_window} average
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-semibold">{formatScore(report.last_4_average)}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Questions scored
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-semibold">
            {report.questions_scored}/{report.questions_planned}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{stopped}</p>
        </CardContent>
      </Card>
    </div>
  )
}
