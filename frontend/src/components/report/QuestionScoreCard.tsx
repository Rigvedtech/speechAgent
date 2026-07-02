import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { cn, formatScore } from '@/lib/utils'
import type { PerQuestionReport } from '@/types/api'

function verdictBadge(score: number) {
  if (score >= 8) return <Badge variant="success">Strong</Badge>
  if (score >= 6) return <Badge variant="warning">Adequate</Badge>
  return <Badge variant="destructive">Needs work</Badge>
}

function scoreAccent(score: number) {
  if (score >= 8) return 'border-success'
  if (score >= 6) return 'border-warning'
  return 'border-destructive'
}

interface QuestionScoreCardProps {
  record: PerQuestionReport
}

export function QuestionScoreCard({ record }: QuestionScoreCardProps) {
  const answer =
    record.answer_text.length > 600
      ? `${record.answer_text.slice(0, 600)}…`
      : record.answer_text

  return (
    <Card className={cn('overflow-hidden border-l-4', scoreAccent(record.score))}>
      <CardHeader className="space-y-3 bg-muted/20 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">Question {record.question_index}</span>
              <Badge variant="outline">{record.difficulty}</Badge>
              <Badge variant="secondary">{record.source}</Badge>
            </div>
            <p className="max-w-3xl text-sm leading-relaxed">{record.question_text}</p>
          </div>

          <div className="flex shrink-0 flex-col items-end gap-1.5">
            <span className="text-2xl font-semibold tracking-tight">
              {formatScore(record.score)}
              <span className="text-sm font-normal text-muted-foreground">/10</span>
            </span>
            {verdictBadge(record.score)}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span className="rounded-md border border-border bg-card px-2 py-1">
            Confident: {record.confident ? 'Yes' : 'No'}
          </span>
          <span className="rounded-md border border-border bg-card px-2 py-1">
            Relevant: {record.relevant ? 'Yes' : 'No'}
          </span>
          {record.strengths ? (
            <span className="rounded-md border border-border bg-card px-2 py-1">
              {record.strengths}
            </span>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-4">
        <section>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Candidate answer
          </p>
          <p className="rounded-lg bg-muted/40 p-3 text-sm leading-relaxed text-muted-foreground">
            {answer || '—'}
          </p>
        </section>

        <Separator />

        <div className="grid gap-4 md:grid-cols-2">
          <section>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              To develop
            </p>
            <p className="text-sm leading-relaxed">{record.develop || '—'}</p>
          </section>
          <section>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              To improve
            </p>
            <p className="text-sm leading-relaxed">{record.fix || '—'}</p>
          </section>
        </div>
      </CardContent>
    </Card>
  )
}
