import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, Copy, Loader2, RefreshCcw } from 'lucide-react'
import { useBotStatus } from '@/hooks/useBotStatus'
import {
  cancelInterviewSetup,
  getCodingSessionByBot,
  getHealth,
  leaveMeeting,
  rejoinBot,
  startInterview,
  toggleCameraIntegrity,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { updateSessionPhase, markSessionCompleted } from '@/lib/session-store'
import {
  StatusStepper,
  type CodingTaskStepItem,
} from '@/components/interview/StatusStepper'
import { PhaseStatusDialog } from '@/components/interview/PhaseStatusDialog'
import { QuestionPlanList } from '@/components/interview/QuestionPlanList'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert } from '@/components/ui/alert'
import { FlashAlert } from '@/components/ui/flash-alert'
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
  const [codingLinkCopied, setCodingLinkCopied] = useState(false)
  const initialQuestions =
    (location.state as { plannedQuestions?: PlannedQuestion[] } | null)?.plannedQuestions ?? []
  const [cachedQuestions, setCachedQuestions] = useState<PlannedQuestion[]>(initialQuestions)

  const data = status.data
  const codingSessionQuery = useQuery({
    queryKey: queryKeys.codingSessionByBot(botId),
    queryFn: () => getCodingSessionByBot(botId),
    // Load as soon as the bot exists so recruiter can copy the candidate URI in lobby
    enabled: Boolean(botId && data?.interview_configured),
    retry: false,
    refetchInterval: (query) => {
      if (query.state.error) return false
      const session = query.state.data
      if (!session) return 8_000
      if (session.submission_status === 'submitted') return false
      const allDone = (session.assigned_tasks ?? []).every((t) => t.status === 'submitted')
      if (allDone && (session.assigned_tasks?.length ?? 0) > 0) return false
      const endsAt = session.ends_at ? new Date(session.ends_at).getTime() : 0
      if (endsAt > 0 && endsAt < Date.now()) return false
      // Poll more often once the voice interview has ended
      return data?.interview_ended ? 5_000 : 15_000
    },
  })

  const codingSession = codingSessionQuery.data
  const codingNotEnabled =
    codingSessionQuery.isError &&
    codingSessionQuery.error instanceof ApiError &&
    codingSessionQuery.error.status === 404

  const codingToken =
    codingSession?.access_token || codingSession?.demo_token || null
  const codingLink = codingToken
    ? `${window.location.origin}/c/${codingToken}`
    : (codingSession?.coding_uri ?? null)

  const codingTaskTitle = codingSession?.task?.title
  const codingTaskDifficulty = codingSession?.task?.difficulty
  const codingTimeLimit = codingSession?.time_limit_min
  const codingEndsAt = codingSession?.ends_at ? new Date(codingSession.ends_at) : null
  const codingTimedOut =
    Boolean(codingEndsAt) &&
    codingEndsAt!.getTime() < Date.now() &&
    codingSession?.submission_status !== 'submitted'
  const codingSubmitted = codingSession?.submission_status === 'submitted'
  const codingAllSubmitted =
    codingSubmitted ||
    ((codingSession?.assigned_tasks?.length ?? 0) > 0 &&
      (codingSession?.assigned_tasks ?? []).every((t) => t.status === 'submitted'))
  // Settled only after 404 (no coding) or a session payload — never while first load is in flight.
  const codingStatusKnown =
    codingNotEnabled ||
    Boolean(codingSession) ||
    (codingSessionQuery.isError && !codingSessionQuery.isFetching)
  const codingEnabled = Boolean(codingSession && !codingNotEnabled)
  // Timeout ends the round so the live page can reach "Interview done" (does not hang forever).
  const codingRoundComplete = codingAllSubmitted || codingTimedOut
  const codingRoundActive = codingEnabled && !codingRoundComplete
  const codingStatusLabel = codingAllSubmitted
    ? 'Submitted'
    : codingTimedOut
      ? 'Timed out'
      : 'Coding round in progress'
  const interviewFullyComplete = Boolean(
    data?.interview_ended &&
      codingStatusKnown &&
      (!codingEnabled || codingRoundComplete),
  )

  const codingTaskSteps: CodingTaskStepItem[] = (() => {
    if (!codingSession) return []
    const tasks = codingSession.assigned_tasks
    if (tasks && tasks.length > 0) {
      return tasks.map((t) => {
        let status: CodingTaskStepItem['status'] = 'pending'
        if (t.status === 'submitted') status = 'submitted'
        else if (t.is_current && codingTimedOut) status = 'timed_out'
        else if (t.is_current) status = 'in_progress'
        else if (t.status === 'draft') status = 'pending'
        return { task_id: t.task_id, title: t.title, status }
      })
    }
    // Single-task fallback when assigned_tasks is empty
    const status: CodingTaskStepItem['status'] = codingAllSubmitted
      ? 'submitted'
      : codingTimedOut
        ? 'timed_out'
        : 'in_progress'
    return [
      {
        task_id: codingSession.task?.id || 'current',
        title: codingSession.task?.title || 'Coding task',
        status,
      },
    ]
  })()

  const copyCodingUrl = async () => {
    if (!codingLink) return
    try {
      await navigator.clipboard.writeText(codingLink)
      setCodingLinkCopied(true)
      window.setTimeout(() => setCodingLinkCopied(false), 2000)
    } catch {
      setError('Could not copy coding link')
    }
  }

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

  // Voice (+ coding when enabled) finished → brief "Interview done", then open the report.
  useEffect(() => {
    if (!interviewFullyComplete || !botId) return
    const timer = window.setTimeout(() => {
      navigate(`/interviews/${botId}/report`, { replace: true })
    }, 1800)
    return () => window.clearTimeout(timer)
  }, [interviewFullyComplete, botId, navigate])

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
      navigate('/dashboard')
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

  const rejoinMutation = useMutation({
    mutationFn: () => rejoinBot(botId),
    onSuccess: (res) => {
      setError(null)
      // Navigate to new bot session
      navigate(`/interviews/${res.new_bot_id}`, { 
        state: { plannedQuestions: cachedQuestions },
        replace: true,
      })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Failed to rejoin bot to lobby')
      }
    },
  })

  const cameraToggleMutation = useMutation({
    mutationFn: (enabled: boolean) => toggleCameraIntegrity(botId, enabled),
    onSuccess: async () => {
      setError(null)
      await status.refetch()
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Failed to update camera vision setting')
      }
    },
  })

  const questions = data?.planned_questions?.length
    ? data.planned_questions
    : cachedQuestions

  const setupNotStarted = !data?.interview_started && !data?.interview_ended
  const canToggleCameraVision = Boolean(data?.interview_started && !data?.interview_ended)
  const cameraVisionOn = Boolean(data?.camera_integrity_armed)

  // Show rejoin button only when bot is denied/failed (not when successfully in lobby)
  // Button is enabled when bot was denied or failed to join
  const showRejoinButton = Boolean(
    data?.interview_configured &&
    !data?.interview_started &&
    !data?.interview_ended &&
    data?.recall_phase !== 'in_meeting'
  )
  
  const canRejoin = Boolean(
    showRejoinButton &&
    !data?.ready_to_start &&
    (data?.recall_phase === 'ended' ||
     data?.status === 'failed' ||
     data?.status === 'fatal' ||
     data?.status === 'done')
  )

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
              <Link to="/dashboard">Dashboard</Link>
            </Button>
          </div>
          <FlashAlert
            message={error}
            onDismiss={() => setError(null)}
            className="border-destructive/30 bg-destructive/5 text-destructive"
          />
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

      <FlashAlert
        message={error}
        onDismiss={() => setError(null)}
        className="shrink-0 border-destructive/30 bg-destructive/5 py-2.5 text-xs leading-snug text-destructive"
      />

      {data?.interview_ended && interviewFullyComplete && (
        <Alert className="shrink-0 border-success/30 bg-success/5 text-xs leading-snug">
          Interview done. Opening report…
          <Button asChild variant="link" className="ml-2 h-auto p-0 text-xs">
            <Link to={`/interviews/${botId}/report`}>Open now</Link>
          </Button>
        </Alert>
      )}
      {data?.interview_ended && !interviewFullyComplete && codingRoundActive && (
        <Alert className="shrink-0 border-primary/30 bg-primary/5 text-xs leading-snug">
          Voice interview done. Coding round in progress.
          {codingLink ? (
            <span className="text-muted-foreground"> Share the coding link with the candidate.</span>
          ) : null}
        </Alert>
      )}
      {data?.interview_ended && !interviewFullyComplete && !codingRoundActive && !codingStatusKnown && (
        <Alert className="shrink-0 border-success/30 bg-success/5 text-xs leading-snug">
          Voice interview done. Checking coding round…
        </Alert>
      )}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[340px_1fr]">
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardHeader className="shrink-0">
            <CardTitle className="text-base">
              {data?.candidate_name ?? 'Candidate'}
            </CardTitle>
            <div className="flex flex-wrap gap-2">
              {data?.language_mode && (
                <Badge variant="secondary">{data.language_mode}</Badge>
              )}
              {data?.interview_started && !data?.interview_ended && (
                <Badge variant="success">Live</Badge>
              )}
              {data?.interview_ended && codingRoundActive && (
                <Badge variant="secondary">Coding in progress</Badge>
              )}
              {interviewFullyComplete && (
                <Badge variant="success">Interview done</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 space-y-4 overflow-y-auto">
            <StatusStepper
              recallPhase={data?.recall_phase}
              localizationStatus={data?.localization_status}
              readyToStart={data?.ready_to_start}
              interviewStarted={data?.interview_started}
              interviewEnded={data?.interview_ended}
              languageMode={data?.language_mode}
              codingEnabled={codingEnabled}
              codingRoundActive={codingRoundActive}
              codingStatusKnown={codingStatusKnown}
              codingTasks={codingTaskSteps}
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
              {showRejoinButton && (
                <Button
                  variant="secondary"
                  onClick={() => rejoinMutation.mutate()}
                  disabled={!canRejoin || rejoinMutation.isPending}
                >
                  {rejoinMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Rejoining…
                    </>
                  ) : (
                    <>
                      <RefreshCcw className="h-4 w-4" />
                      Resend to Lobby
                    </>
                  )}
                </Button>
              )}
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
              <Button
                variant="secondary"
                onClick={() => cameraToggleMutation.mutate(!cameraVisionOn)}
                disabled={!canToggleCameraVision || cameraToggleMutation.isPending}
              >
                {cameraToggleMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                {cameraVisionOn ? 'Camera vision: ON' : 'Camera vision: OFF'}
              </Button>
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
              {codingLink ? (
                <div>
                  <p className="mb-1 font-medium text-foreground">Coding task URI</p>
                  <div className="flex items-center gap-1 rounded border border-primary/30 bg-primary/5 px-2 py-1">
                    <p className="min-w-0 flex-1 truncate font-mono text-foreground" title={codingLink}>
                      {truncate(codingLink, 48)}
                    </p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
                      title={codingLinkCopied ? 'Copied' : 'Copy coding link'}
                      aria-label={codingLinkCopied ? 'Coding link copied' : 'Copy coding link'}
                      onClick={copyCodingUrl}
                    >
                      {codingLinkCopied ? (
                        <Check className="h-3.5 w-3.5 text-success" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Copy and send this link to the candidate for the coding round.
                  </p>
                </div>
              ) : codingSessionQuery.isFetching && data?.interview_configured ? (
                <p className="text-[10px] text-muted-foreground">Checking coding task link…</p>
              ) : codingNotEnabled ? (
                <p className="text-[10px] text-muted-foreground">
                  No coding round on this interview. Enable coding when you send to lobby.
                </p>
              ) : null}
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
          {data?.interview_ended ? (
            <Card className="mt-3 shrink-0 border-primary/30 bg-primary/5">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-sm">Coding round</CardTitle>
                  {codingLink ? (
                    <Badge
                      variant={
                        codingSubmitted
                          ? 'default'
                          : codingTimedOut
                            ? 'destructive'
                            : 'secondary'
                      }
                    >
                      {codingStatusLabel}
                    </Badge>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                {codingSessionQuery.isLoading ? (
                  <p className="text-muted-foreground">Loading coding task…</p>
                ) : codingLink && codingSession ? (
                  <>
                    <div className="space-y-1">
                      <p className="font-medium text-foreground">
                        {codingTaskTitle || 'Coding task'}
                        {codingSession.task_count && codingSession.task_count > 1
                          ? ` (${codingSession.task_index ?? 1}/${codingSession.task_count})`
                          : ''}
                      </p>
                      <p className="text-muted-foreground">
                        {[
                          codingTaskDifficulty
                            ? codingTaskDifficulty.charAt(0).toUpperCase() +
                              codingTaskDifficulty.slice(1)
                            : null,
                          codingTimeLimit ? `${codingTimeLimit} min` : null,
                          codingSession.domain_name || null,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    </div>
                    <p className="text-muted-foreground">
                      {codingSubmitted
                        ? 'Candidate submitted their solution. Interview done — opening report…'
                        : codingTimedOut
                          ? 'Coding round timed out. Interview done — opening report…'
                          : 'Coding round in progress. Share this link with the candidate, then wait for submit or timeout.'}
                    </p>
                    <div className="flex items-center gap-1 rounded border bg-card px-2 py-1">
                      <p className="min-w-0 flex-1 truncate font-mono" title={codingLink}>
                        {truncate(codingLink, 72)}
                      </p>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
                        title={codingLinkCopied ? 'Copied' : 'Copy coding link'}
                        aria-label={codingLinkCopied ? 'Coding link copied' : 'Copy coding link'}
                        onClick={copyCodingUrl}
                      >
                        {codingLinkCopied ? (
                          <Check className="h-3.5 w-3.5 text-success" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                    {(codingSession.assigned_tasks?.length ?? 0) > 1 ? (
                      <ul className="space-y-1 border-t pt-2 text-muted-foreground">
                        {codingSession.assigned_tasks!.map((t) => (
                          <li key={t.task_id} className="flex justify-between gap-2">
                            <span className={t.is_current ? 'text-foreground' : undefined}>
                              {t.title}
                            </span>
                            <span>
                              {t.status === 'submitted'
                                ? 'Submitted'
                                : t.is_current && codingTimedOut
                                  ? 'Timed out'
                                  : t.is_current
                                    ? 'In progress'
                                    : 'Pending'}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                ) : codingNotEnabled ? (
                  <p className="text-muted-foreground">
                    Coding round is not enabled for this interview.
                  </p>
                ) : (
                  <p className="text-muted-foreground">
                    Could not load the coding session. Try refreshing status.
                  </p>
                )}
              </CardContent>
            </Card>
          ) : null}
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
