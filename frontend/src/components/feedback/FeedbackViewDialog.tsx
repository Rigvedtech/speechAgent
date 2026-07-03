import { useQuery } from '@tanstack/react-query'
import { Loader2, MessageSquare } from 'lucide-react'
import { getFeedback } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import {
  TECH_ISSUE_LABELS,
  WOULD_REPEAT_LABELS,
  type FeedbackFormValues,
} from '@/schemas/feedback-form.schema'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Alert } from '@/components/ui/alert'

interface FeedbackViewDialogProps {
  botId: string
  candidateName?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

function Stars({ value }: { value: number }) {
  return (
    <span className="tabular-nums text-foreground">
      {value}/5 <span className="text-muted-foreground">★</span>
    </span>
  )
}

export function FeedbackViewDialog({
  botId,
  candidateName,
  open,
  onOpenChange,
}: FeedbackViewDialogProps) {
  const feedbackQuery = useQuery({
    queryKey: queryKeys.feedback(botId),
    queryFn: () => getFeedback(botId),
    enabled: open && Boolean(botId),
  })

  const data = feedbackQuery.data?.feedback

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-brand" strokeWidth={1.5} />
            Candidate feedback
          </DialogTitle>
          <DialogDescription>
            {candidateName ?? data?.candidate_name ?? 'Interview'}{' '}
            {data?.submitted_at
              ? `· ${new Date(data.submitted_at).toLocaleString()}`
              : null}
          </DialogDescription>
        </DialogHeader>

        {feedbackQuery.isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : feedbackQuery.isError ? (
          <Alert className="text-sm">
            {feedbackQuery.error instanceof ApiError && feedbackQuery.error.status === 404
              ? 'No feedback submitted yet for this interview.'
              : 'Could not load feedback.'}
          </Alert>
        ) : data ? (
          <dl className="space-y-4 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Overall experience</dt>
              <dd>
                <Stars value={data.overall_rating} />
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">AI clarity</dt>
              <dd>
                <Stars value={data.clarity_rating} />
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">Technical issues</dt>
              <dd>
                <Badge variant="outline">
                  {TECH_ISSUE_LABELS[data.tech_issues as FeedbackFormValues['tech_issues']]}
                </Badge>
              </dd>
            </div>
            {data.would_repeat ? (
              <div className="flex items-center justify-between gap-4">
                <dt className="text-muted-foreground">Would repeat</dt>
                <dd>
                  {
                    WOULD_REPEAT_LABELS[
                      data.would_repeat as NonNullable<FeedbackFormValues['would_repeat']>
                    ]
                  }
                </dd>
              </div>
            ) : null}
            <div className="space-y-1.5 rounded-lg border border-border bg-muted/30 p-3">
              <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Improvement suggestion
              </dt>
              <dd className="leading-relaxed text-foreground">{data.improve_text}</dd>
            </div>
          </dl>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
