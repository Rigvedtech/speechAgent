import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { PerQuestionReport } from '@/types/api'

function verdictBadge(score: number) {
  if (score >= 8) return <Badge variant="success">Strong</Badge>
  if (score >= 6) return <Badge variant="warning">Adequate</Badge>
  return <Badge variant="destructive">Needs work</Badge>
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
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">
            Question {record.question_index}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              [{record.difficulty} · {record.source}]
            </span>
          </CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{record.score}/10</span>
            {verdictBadge(record.score)}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Question</p>
          <p>{record.question_text}</p>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Answer</p>
          <p className="text-muted-foreground">{answer}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium text-muted-foreground">Develop</p>
            <p>{record.develop || '—'}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Improve</p>
            <p>{record.fix || '—'}</p>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Confident: {record.confident ? 'Yes' : 'No'} · Relevant:{' '}
          {record.relevant ? 'Yes' : 'No'}
          {record.strengths ? ` · ${record.strengths}` : ''}
        </p>
      </CardContent>
    </Card>
  )
}
