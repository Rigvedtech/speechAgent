import { useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { getFeedbackContext, submitFeedback } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import type { FeedbackFormValues } from '@/schemas/feedback-form.schema'
import {
  FeedbackFormCard,
  FeedbackThankYouCard,
} from '@/components/feedback/FeedbackFormCard'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

export function CandidateFeedbackPage() {
  const { botId = '' } = useParams()

  const contextQuery = useQuery({
    queryKey: queryKeys.feedbackContext(botId),
    queryFn: () => getFeedbackContext(botId),
    enabled: Boolean(botId),
    retry: false,
  })

  const submitMutation = useMutation({
    mutationFn: (values: FeedbackFormValues) => submitFeedback(botId, values),
    onSuccess: () => {
      contextQuery.refetch()
    },
  })

  const ctx = contextQuery.data
  const submitted = ctx?.already_submitted

  if (contextQuery.isLoading) {
    return (
      <Card className="w-full border-border shadow-sm">
        <CardHeader>
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-4 w-full" />
        </CardHeader>
        <div className="space-y-4 px-6 pb-8">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </Card>
    )
  }

  if (contextQuery.isError) {
    const err = contextQuery.error
    const message =
      err instanceof ApiError ? formatApiError(err.message, err.detail) : 'Invalid feedback link'
    return (
      <Card className="w-full border-border shadow-sm">
        <CardHeader>
          <CardTitle>Link not found</CardTitle>
          <CardDescription>{message}</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (submitted) {
    return <FeedbackThankYouCard candidateName={ctx?.candidate_name} />
  }

  return (
    <FeedbackFormCard
      candidateName={ctx?.candidate_name}
      submitting={submitMutation.isPending}
      submitError={
        submitMutation.isError
          ? submitMutation.error instanceof ApiError
            ? formatApiError(submitMutation.error.message, submitMutation.error.detail)
            : 'Could not submit feedback. Please try again.'
          : null
      }
      onSubmit={(values) => submitMutation.mutate(values)}
    />
  )
}
