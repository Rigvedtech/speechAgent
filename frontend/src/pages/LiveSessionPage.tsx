import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, Copy, Loader2 } from 'lucide-react'
import { useBotStatus } from '@/hooks/useBotStatus'
import { cancelInterviewSetup, getHealth, leaveMeeting, startInterview } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { updateSessionPhase, markSessionCompleted } from '@/lib/session-store'
import { StatusStepper } from '@/components/interview/StatusStepper'
import { PhaseStatusDialog } from '@/components/interview/PhaseStatusDialog'
import { QuestionPlanList } from '@/components/interview/QuestionPlanList'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { truncate } from '@/lib/utils'
import { buildFeedbackUrl } from '@/lib/feedback-url'
import type { PlannedQuestion } from '@/types/api'

export function LiveSessionPage() {
  const { botId = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const status = useBotStatus(botId)
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    staleTime: 60_000,
  })
  const lobbyTimeoutMin = health.data?.lobby_timeout_minutes ?? 15
  const [error, setError] = useState<string | null>(null)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [meetingLinkCopied, setMeetingLinkCopied] = useState(false)
  const [feedbackLinkCopied, setFeedbackLinkCopied] = useState(false)
  const initialQuestions =
    (location.state as { plannedQuestions?: PlannedQuestion[] } | null)?.plannedQuestions ?? []
  const [cachedQuestions, setCachedQuestions] = useState<PlannedQuestion[]>(initialQuestions)

  const data = status.data

  useEffect(() => {
    if (data?.planned_questions?.length) {
      setCachedQuestions(data.planned_questions)
    }
  }, [data?.planned_questions])

  useEffect(() => {
    if (data?.interview_phase) {
      updateSessionPhase(botId, data.interview_phase)
    }
  }, [botId, data?.interview_phase])

  useEffect(() => {
    if (data?.interview_ended) {
      markSessionCompleted(botId)
    }
  }, [botId, data?.interview_ended])

  const startMutation = useMutation({
    mutationFn: () => startInterview(botId, {}),
    onSuccess: (res) => {
      setError(null)
      if (res.planned_questions?.length) {
        setCachedQuestions(res.planned_questions)
      }
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Failed to start interview')
      }
    },
  })

  const leaveMutation = useMutation({
    mutationFn: () => leaveMeeting(botId),
    onSuccess: () => {
      setLeaveOpen(false)
      navigate('/')
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      }
    },
  })

  const cancelMutation = useMutation({
    mutationFn: () => cancelInterviewSetup(botId),
    onSuccess: () => navigate('/interviews/new'),
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Failed to cancel setup')
      }
    },
  })

  const questions = data?.planned_questions?.length
    ? data.planned_questions
    : cachedQuestions

  const setupNotStarted = !data?.interview_started && !data?.interview_ended

  const copyMeetingUrl = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setMeetingLinkCopied(true)
      window.setTimeout(() => setMeetingLinkCopied(false), 2000)
    } catch {
      setError('Could not copy meeting link')
    }
  }

  const feedbackUrl = buildFeedbackUrl(botId)

  const copyFeedbackUrl = async () => {
    try {
      await navigator.clipboard.writeText(feedbackUrl)
      setFeedbackLinkCopied(true)
      window.setTimeout(() => setFeedbackLinkCopied(false), 2000)
    } catch {
      setError('Could not copy feedback link')
    }
  }

  if (status.isLoading && !status.isError) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (status.isError && !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connecting to interview…</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert className="border-warning/30 bg-warning/5">
            {status.isFetching
              ? 'Retrying connection to the interview server…'
              : 'Could not load interview status. The bot may still be joining the meeting.'}
          </Alert>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => status.refetch()}
              disabled={status.isFetching}
            >
              {status.isFetching ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Retrying…
                </>
              ) : (
                'Retry'
              )}
            </Button>
            <Button
              variant="destructive"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? 'Cancelling…' : 'Cancel setup'}
            </Button>
            <Button asChild variant="ghost">
              <Link to="/">Dashboard</Link>
            </Button>
          </div>
          {error && (
            <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
              {error}
            </Alert>
          )}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      <PhaseStatusDialog
        data={data}
        setupNotStarted={setupNotStarted}
        lobbyTimeoutMin={lobbyTimeoutMin}
      />

      {error && (
        <Alert className="shrink-0 border-destructive/30 bg-destructive/5 py-2.5 text-xs leading-snug text-destructive">
          {error}
        </Alert>
      )}

      {data?.interview_ended && (
        <Alert className="shrink-0 border-success/30 bg-success/5 text-xs leading-snug">
          Interview ended.{' '}
          <Button asChild variant="link" className="h-auto p-0 text-xs">
            <Link to={`/interviews/${botId}/report`}>View report</Link>
          </Button>
        </Alert>
      )}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[340px_1fr]">
        <Card className="flex flex-col overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base">
              {data?.candidate_name ?? 'Candidate'}
            </CardTitle>
            <div className="flex flex-wrap gap-2">
              {data?.language_mode && (
                <Badge variant="secondary">{data.language_mode}</Badge>
              )}
              {data?.interview_started && (
                <Badge variant="success">Live</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <StatusStepper
              recallPhase={data?.recall_phase}
              localizationStatus={data?.localization_status}
              readyToStart={data?.ready_to_start}
              interviewStarted={data?.interview_started}
              interviewEnded={data?.interview_ended}
              languageMode={data?.language_mode}
            />

            <div className="flex flex-col gap-2">
              <Button
                disabled={
                  !data?.ready_to_start ||
                  data?.interview_started ||
                  startMutation.isPending ||
                  data?.interview_ended
                }
                onClick={() => startMutation.mutate()}
              >
                {startMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Starting…
                  </>
                ) : (
                  'Start interview'
                )}
              </Button>
              {setupNotStarted ? (
                <Button
                  variant="outline"
                  onClick={() => cancelMutation.mutate()}
                  disabled={cancelMutation.isPending}
                >
                  {cancelMutation.isPending ? 'Cancelling…' : 'Cancel setup'}
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => setLeaveOpen(true)}
                  disabled={leaveMutation.isPending}
                >
                  Leave meeting
                </Button>
              )}
            </div>

            <div className="space-y-2 text-[11px] leading-snug text-muted-foreground">
              <p>
                Progress: {data?.questions_scored ?? 0}/{data?.questions_planned ?? '—'}{' '}
                scored
              </p>
              {data?.meeting_url && (
                <div>
                  <p className="mb-1 font-medium">Meeting</p>
                  <div className="flex items-center gap-1">
                    <p className="min-w-0 flex-1 truncate" title={data.meeting_url}>
                      {truncate(data.meeting_url, 48)}
                    </p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
                      title={meetingLinkCopied ? 'Copied' : 'Copy meeting link'}
                      aria-label={meetingLinkCopied ? 'Meeting link copied' : 'Copy meeting link'}
                      onClick={() => copyMeetingUrl(data.meeting_url!)}
                    >
                      {meetingLinkCopied ? (
                        <Check className="h-3.5 w-3.5 text-success" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>
                </div>
              )}
              {botId && (
                <div>
                  <p className="mb-1 font-medium">Feedback</p>
                  <div className="flex items-center gap-1">
                    <p className="min-w-0 flex-1 truncate" title={feedbackUrl}>
                      {truncate(feedbackUrl, 48)}
                    </p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
                      title={feedbackLinkCopied ? 'Copied' : 'Copy feedback link'}
                      aria-label={feedbackLinkCopied ? 'Feedback link copied' : 'Copy feedback link'}
                      onClick={copyFeedbackUrl}
                    >
                      {feedbackLinkCopied ? (
                        <Check className="h-3.5 w-3.5 text-success" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <h2 className="mb-2 shrink-0 text-sm font-medium">Interview plan</h2>
          <QuestionPlanList
            fillHeight
            questions={questions}
            currentQuestionSlot={data?.current_question_slot}
            questionsScored={data?.questions_scored}
            languageMode={data?.language_mode}
            localizationStatus={data?.localization_status}
          />
        </div>
      </div>

      <Dialog open={leaveOpen} onOpenChange={setLeaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Leave meeting?</DialogTitle>
            <DialogDescription>
              The bot will be removed from the meeting. You can still view the report after the
              interview ends.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setLeaveOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => leaveMutation.mutate()}
              disabled={leaveMutation.isPending}
            >
              Leave
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
