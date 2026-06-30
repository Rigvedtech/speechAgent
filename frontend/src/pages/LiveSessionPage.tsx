import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useBotStatus } from '@/hooks/useBotStatus'
import { cancelInterviewSetup, getHealth, leaveMeeting, startInterview } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { updateSessionPhase, markSessionCompleted } from '@/lib/session-store'
import { StatusStepper } from '@/components/interview/StatusStepper'
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

  const lobbyBanner =
    data?.recall_phase === 'lobby' && setupNotStarted
      ? `Bot is in the lobby. Admit it from Teams before starting. If not started within ${lobbyTimeoutMin} minutes, it will leave automatically.`
      : data?.recall_phase === 'lobby'
        ? 'Bot is in the lobby. Admit the bot from Teams before starting.'
        : null

  const localizingBanner =
    data?.language_mode === 'hinglish' && data?.localization_status === 'pending'
      ? 'Translating questions to Hinglish…'
      : null

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
    <div className="space-y-4">
      {(error || lobbyBanner || localizingBanner) && (
        <Alert
          className={
            lobbyBanner || localizingBanner
              ? 'border-warning/30 bg-warning/5'
              : 'border-destructive/30 bg-destructive/5'
          }
        >
          {error ?? lobbyBanner ?? localizingBanner}
        </Alert>
      )}

      {data?.interview_ended && (
        <Alert className="border-success/30 bg-success/5">
          Interview ended.{' '}
          <Button asChild variant="link" className="h-auto p-0">
            <Link to={`/interviews/${botId}/report`}>View report</Link>
          </Button>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <Card>
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

            <div className="space-y-2 text-xs text-muted-foreground">
              <p>
                Progress: {data?.questions_scored ?? 0}/{data?.questions_planned ?? '—'}{' '}
                scored
              </p>
              {data?.meeting_url && (
                <p>Meeting: {truncate(data.meeting_url, 48)}</p>
              )}
            </div>
          </CardContent>
        </Card>

        <div>
          <h2 className="mb-3 text-sm font-medium">Interview plan</h2>
          <QuestionPlanList
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
