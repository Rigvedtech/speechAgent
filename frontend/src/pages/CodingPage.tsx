import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, Loader2, Play } from 'lucide-react'
import {
  getCodingSessionByBot,
  getCodingSessionByInterview,
  getDemoCodingSession,
  runCodingExamples,
  startDemoCodingSession,
  submitCodingByBot,
  submitCodingByInterview,
  submitDemoCodingSession,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { CodeEditor } from '@/components/coding/CodeEditor'
import { Alert } from '@/components/ui/alert'
import { FlashAlert } from '@/components/ui/flash-alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { CodingLanguage, CodingRunExamplesResponse, CodingSession } from '@/types/api'

type Mode =
  | { kind: 'demo'; token?: string }
  | { kind: 'bot'; botId: string }
  | { kind: 'interview'; interviewId: string }

function useCodingMode(): Mode {
  const params = useParams()
  if (params.demoToken) return { kind: 'demo', token: params.demoToken }
  if (params.botId) return { kind: 'bot', botId: params.botId }
  if (params.interviewId) return { kind: 'interview', interviewId: params.interviewId }
  return { kind: 'demo' }
}

export function CodingPage() {
  const mode = useCodingMode()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [code, setCode] = useState('')
  const [language, setLanguage] = useState<CodingLanguage>('python')
  const [error, setError] = useState<string | null>(null)
  const [submittedOk, setSubmittedOk] = useState(false)
  const [runResult, setRunResult] = useState<CodingRunExamplesResponse | null>(null)

  const sessionQuery = useQuery({
    queryKey:
      mode.kind === 'demo' && mode.token
        ? queryKeys.codingDemo(mode.token)
        : mode.kind === 'bot'
          ? queryKeys.codingSessionByBot(mode.botId)
          : mode.kind === 'interview'
            ? queryKeys.codingSessionByInterview(mode.interviewId)
            : ['codingDemo', 'pending'],
    queryFn: async (): Promise<CodingSession> => {
      if (mode.kind === 'demo' && mode.token) return getDemoCodingSession(mode.token)
      if (mode.kind === 'bot') return getCodingSessionByBot(mode.botId)
      if (mode.kind === 'interview') return getCodingSessionByInterview(mode.interviewId)
      throw new Error('No coding session')
    },
    enabled: mode.kind !== 'demo' || Boolean(mode.token),
    retry: 1,
  })

  const startDemoMutation = useMutation({
    mutationFn: () => startDemoCodingSession({ language: 'python' }),
    onSuccess: (session) => {
      const token = session.access_token || session.demo_token
      if (token) {
        // Open candidate-only workspace (no navbar) — same link candidates receive
        window.location.assign(`/c/${token}`)
        return
      }
      navigate('/coding/demo', { replace: true })
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to start demo coding session',
      )
    },
  })

  useEffect(() => {
    const session = sessionQuery.data
    if (!session) return
    setCode(session.code ?? '')
    setLanguage((session.language as CodingLanguage) || 'python')
    setSubmittedOk(session.submission_status === 'submitted')
  }, [sessionQuery.data])

  const runMutation = useMutation({
    mutationFn: async (taskId: string) =>
      runCodingExamples({
        language,
        code,
        task_id: taskId,
      }),
    onSuccess: (res) => {
      setError(null)
      setRunResult(res)
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to run code',
      )
    },
  })

  const submitMutation = useMutation({
    mutationFn: async (status: 'draft' | 'submitted') => {
      const body = { language, code, status }
      if (mode.kind === 'demo' && mode.token) {
        return submitDemoCodingSession(mode.token, body)
      }
      if (mode.kind === 'bot') return submitCodingByBot(mode.botId, body)
      if (mode.kind === 'interview') return submitCodingByInterview(mode.interviewId, body)
      throw new Error('No coding session')
    },
    onSuccess: async (res) => {
      setError(null)
      setSubmittedOk(res.status === 'submitted')
      void queryClient.invalidateQueries()
      if (res.status === 'submitted' && sessionQuery.data?.task.id) {
        try {
          const out = await runCodingExamples({
            language,
            code,
            task_id: sessionQuery.data.task.id,
          })
          setRunResult(out)
        } catch {
          // Submit already succeeded; output panel may stay empty if run fails.
        }
      }
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to submit code',
      )
    },
  })

  if (mode.kind === 'demo' && !mode.token) {
    return (
      <div className="mx-auto flex max-w-lg flex-col gap-4 p-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Coding round demo</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Test Monaco and submit without scheduling a full interview. This creates a disposable
              demo session with one seeded task.
            </p>
            <FlashAlert
              message={error}
              onDismiss={() => setError(null)}
              className="border-destructive/30 bg-destructive/5 text-destructive"
            />
            <Button
              onClick={() => startDemoMutation.mutate()}
              disabled={startDemoMutation.isPending}
            >
              {startDemoMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Starting…
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Start demo task
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (sessionQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading coding task…
      </div>
    )
  }

  if (sessionQuery.isError || !sessionQuery.data) {
    return (
      <div className="mx-auto max-w-lg space-y-3 p-6">
        <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
          {sessionQuery.error instanceof ApiError
            ? formatApiError(sessionQuery.error.message, sessionQuery.error.detail)
            : 'Coding session not available. Enable coding when scheduling, or start a demo.'}
        </Alert>
        <Button asChild variant="outline">
          <Link to="/coding/demo">Open coding demo</Link>
        </Button>
      </div>
    )
  }

  const session = sessionQuery.data
  const task = session.task
  // Demo stays editable so candidates can fix code and re-run after submit.
  const readOnly =
    mode.kind !== 'demo' &&
    (submittedOk || session.submission_status === 'submitted')
  const backTo =
    mode.kind === 'bot'
      ? `/interviews/${mode.botId}`
      : mode.kind === 'interview'
        ? '/interviews/scheduled'
        : '/dashboard'

  const onLanguageChange = (next: CodingLanguage) => {
    if (readOnly) return
    const starter = task.starter_code?.[next] ?? ''
    const currentStarter = task.starter_code?.[language] ?? ''
    setLanguage(next)
    if (!code.trim() || code.trim() === currentStarter.trim()) {
      setCode(starter)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link to={backTo}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h1 className="text-sm font-semibold">{task.title}</h1>
            <p className="text-xs text-muted-foreground">
              {mode.kind === 'demo' ? 'Demo session' : 'Interview coding round'}
              {' · '}
              {session.time_limit_min} min
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{task.difficulty}</Badge>
          {session.proctor_summary?.risk_level ? (
            <Badge
              variant={
                session.proctor_summary.risk_level === 'high'
                  ? 'destructive'
                  : session.proctor_summary.risk_level === 'review'
                    ? 'secondary'
                    : 'success'
              }
            >
              Integrity: {session.proctor_summary.risk_level}
              {' · '}
              {session.proctor_summary.warn_count}w/
              {session.proctor_summary.critical_count}c
            </Badge>
          ) : null}
          {readOnly ? (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 h-3 w-3" />
              Submitted
            </Badge>
          ) : (
            <Badge variant="secondary">Draft</Badge>
          )}
        </div>
      </div>

      <FlashAlert
        message={error}
        onDismiss={() => setError(null)}
        className="shrink-0 border-destructive/30 bg-destructive/5 text-xs text-destructive"
      />

      {submittedOk && (
        <Alert className="shrink-0 border-success/30 bg-success/5 text-xs">
          Solution submitted. You can close this tab; recruiters can review it with the interview
          report.
        </Alert>
      )}

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[340px_1fr]">
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardHeader className="shrink-0">
            <CardTitle className="text-sm">Problem</CardTitle>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 space-y-4 overflow-y-auto text-sm">
            <p className="leading-relaxed whitespace-pre-wrap">{task.statement}</p>
            {task.examples?.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Examples
                </p>
                {task.examples.map((ex, i) => (
                  <div
                    key={i}
                    className="rounded-md border border-border bg-muted/30 p-2.5 text-xs"
                  >
                    <p>
                      <span className="font-medium">Input:</span> {ex.input}
                    </p>
                    <p className="mt-1">
                      <span className="font-medium">Output:</span> {ex.output}
                    </p>
                    {ex.explanation && (
                      <p className="mt-1 text-muted-foreground">{ex.explanation}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
            {task.constraints_text && (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Constraints
                </p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {task.constraints_text}
                </p>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Implement <code>{task.entry_function || 'solution'}</code> and return the
              answer — Run checks examples automatically (no print needed).
            </p>
          </CardContent>
        </Card>

        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardHeader className="flex shrink-0 flex-row flex-wrap items-center justify-between gap-2 space-y-0">
            <CardTitle className="text-sm">Solution</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={language}
                onValueChange={(v) => onLanguageChange(v as CodingLanguage)}
                disabled={readOnly || session.language_locked !== false}
              >
                <SelectTrigger className="h-8 w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(session.allowed_languages?.length
                    ? session.allowed_languages
                    : [language]
                  ).map((lang) => (
                    <SelectItem key={lang} value={lang}>
                      {lang}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="secondary"
                size="sm"
                disabled={runMutation.isPending || submitMutation.isPending || !code.trim()}
                onClick={() => runMutation.mutate(task.id)}
              >
                {runMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Running…
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Run
                  </>
                )}
              </Button>
              {!readOnly && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={submitMutation.isPending || !code.trim()}
                    onClick={() => submitMutation.mutate('draft')}
                  >
                    Save draft
                  </Button>
                  <Button
                    size="sm"
                    disabled={submitMutation.isPending || !code.trim()}
                    onClick={() => submitMutation.mutate('submitted')}
                  >
                    {submitMutation.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Submitting…
                      </>
                    ) : (
                      'Submit'
                    )}
                  </Button>
                </>
              )}
            </div>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden p-0">
            <div className="min-h-0 flex-[1.4]">
              <CodeEditor
                value={code}
                onChange={setCode}
                language={language}
                readOnly={readOnly}
                height="100%"
              />
            </div>
            <div className="shrink-0 border-t border-border bg-muted/20">
              <div className="flex items-center justify-between gap-2 px-3 py-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Output
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {runResult && (
                    <Badge variant={runResult.all_passed ? 'success' : 'secondary'}>
                      {runResult.passed}/{runResult.total} examples passed
                    </Badge>
                  )}
                  {runResult?.complexity && (
                    <Badge
                      variant="secondary"
                      title={
                        runResult.complexity.note
                          ? `${runResult.complexity.note} (${runResult.complexity.confidence || 'estimate'})`
                          : 'Estimated complexity of your current code'
                      }
                    >
                      Time {runResult.complexity.time} · Space {runResult.complexity.space}
                    </Badge>
                  )}
                </div>
              </div>
              <div className="max-h-48 space-y-2 overflow-y-auto px-3 pb-3">
                {!runResult && !runMutation.isPending && (
                  <p className="text-xs text-muted-foreground">
                    Click <span className="font-medium text-foreground">Run</span> to execute your
                    code against the examples and see output here. Submit also runs examples.
                  </p>
                )}
                {runMutation.isPending && (
                  <p className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Running against examples…
                  </p>
                )}
                {runResult?.results.map((row) => (
                  <div
                    key={row.index}
                    className={cn(
                      'rounded-md border px-2.5 py-2 text-xs',
                      row.passed
                        ? 'border-success/30 bg-success/5'
                        : 'border-destructive/30 bg-destructive/5',
                    )}
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-medium">Example {row.index}</span>
                      <span className={row.passed ? 'text-success' : 'text-destructive'}>
                        {row.passed ? 'Passed' : row.timed_out ? 'Timed out' : 'Failed'}
                      </span>
                    </div>
                    <p>
                      <span className="text-muted-foreground">Input:</span> {row.input}
                    </p>
                    <p className="mt-0.5">
                      <span className="text-muted-foreground">Expected:</span> {row.expected}
                    </p>
                    <p className="mt-0.5">
                      <span className="text-muted-foreground">Your output:</span>{' '}
                      <span className="font-mono">
                        {row.actual || (row.stderr ? '(no stdout)' : '(empty)')}
                      </span>
                    </p>
                    {row.stderr && (
                      <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-[11px] text-destructive">
                        {row.stderr}
                      </pre>
                    )}
                    {row.error && !row.stderr && (
                      <p className="mt-1 text-destructive">{row.error}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
