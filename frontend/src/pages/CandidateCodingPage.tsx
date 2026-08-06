import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FilePlus2,
  Loader2,
  Play,
  Save,
  Send,
  Trash2,
  XCircle,
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import {
  getPublicCodingSession,
  runPublicCodingExamples,
  savePublicCodingSession,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { cn } from '@/lib/utils'
import {
  codingLanguageMeta,
  defaultEntryForLanguage,
  monacoLanguageFor,
} from '@/lib/coding-languages'
import type {
  CodingLanguage,
  CodingRunExamplesResponse,
  CodingWorkspace,
} from '@/types/api'

function defaultEntry(language: CodingLanguage) {
  return defaultEntryForLanguage(language)
}

function monacoLang(path: string, language: CodingLanguage) {
  return monacoLanguageFor(path, language)
}

function formatRemaining(totalSec: number) {
  const s = Math.max(0, Math.floor(totalSec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

const RESULTS_MIN = 120
const RESULTS_DEFAULT = 220

export function CandidateCodingPage() {
  const { token = '' } = useParams()
  const queryClient = useQueryClient()
  const [language, setLanguage] = useState<CodingLanguage>('python')
  const [workspace, setWorkspace] = useState<CodingWorkspace>({
    files: {},
    activePath: 'main.py',
    entryPath: 'main.py',
  })
  const [error, setError] = useState<string | null>(null)
  const [runResult, setRunResult] = useState<CodingRunExamplesResponse | null>(null)
  const [submittedOk, setSubmittedOk] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [showAddFile, setShowAddFile] = useState(false)
  const [remainingSec, setRemainingSec] = useState<number | null>(null)
  const [timeLocked, setTimeLocked] = useState(false)
  const [resultsHeight, setResultsHeight] = useState(RESULTS_DEFAULT)
  const [draggingResults, setDraggingResults] = useState(false)
  const autoLockedRef = useRef(false)
  const workspaceRef = useRef(workspace)
  const languageRef = useRef(language)
  const editorColRef = useRef<HTMLElement | null>(null)
  const dragRef = useRef<{ startY: number; startH: number } | null>(null)

  useEffect(() => {
    workspaceRef.current = workspace
  }, [workspace])
  useEffect(() => {
    languageRef.current = language
  }, [language])

  const sessionQuery = useQuery({
    queryKey: queryKeys.codingPublic(token),
    queryFn: () => getPublicCodingSession(token),
    enabled: Boolean(token),
    retry: 1,
  })

  useEffect(() => {
    const session = sessionQuery.data
    if (!session) return
    const lang = (session.language as CodingLanguage) || 'python'
    setLanguage(lang)
    const allDone =
      session.submission_status === 'submitted' && !session.has_next_task
    setSubmittedOk(session.submission_status === 'submitted' && !session.has_next_task)
    if (allDone) {
      setTimeLocked(true)
    } else {
      setTimeLocked(false)
      autoLockedRef.current = false
      setSubmittedOk(false)
    }
    if (session.workspace?.files && Object.keys(session.workspace.files).length) {
      setWorkspace(session.workspace)
    } else {
      const entry = defaultEntry(lang)
      setWorkspace({
        files: { [entry]: session.code || '' },
        activePath: entry,
        entryPath: entry,
      })
    }
    setRunResult(null)
  }, [sessionQuery.data])

  const saveMutation = useMutation({
    mutationFn: (status: 'draft' | 'submitted') => {
      const ws = workspaceRef.current
      const lang = languageRef.current
      return savePublicCodingSession(token, {
        language: lang,
        code: ws.files[ws.entryPath] ?? ws.files[ws.activePath] ?? '',
        status,
        workspace: ws,
      })
    },
    onSuccess: async (res) => {
      setError(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.codingPublic(token) })
      if (res.status === 'submitted' && res.has_next_task) {
        // Advance to next problem — session refetch loads new task + timer
        setSubmittedOk(false)
        setTimeLocked(false)
        autoLockedRef.current = false
        setRunResult(null)
        return
      }
      if (res.status === 'submitted' && !res.has_next_task) {
        setSubmittedOk(true)
        if (!autoLockedRef.current) {
          try {
            const ws = workspaceRef.current
            const out = await runPublicCodingExamples(token, {
              language: languageRef.current,
              code: ws.files[ws.entryPath] ?? ws.files[ws.activePath] ?? '',
              workspace: ws,
            })
            setRunResult(out)
          } catch {
            // keep submit success even if run fails
          }
        }
      }
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to save solution',
      )
    },
  })

  useEffect(() => {
    const session = sessionQuery.data
    if (!session || (session.submission_status === 'submitted' && !session.has_next_task)) {
      return
    }

    const endsAtMs = session.ends_at
      ? new Date(session.ends_at).getTime()
      : session.started_at
        ? new Date(session.started_at).getTime() +
          (session.time_limit_min || 30) * 60_000
        : Date.now() + (session.time_limit_min || 30) * 60_000

    const tick = () => {
      const left = Math.ceil((endsAtMs - Date.now()) / 1000)
      setRemainingSec(left)
      if (left <= 0 && !autoLockedRef.current) {
        autoLockedRef.current = true
        setRemainingSec(0)
        void saveMutation
          .mutateAsync('submitted')
          .then((res) => {
            if (!res.has_next_task) setTimeLocked(true)
          })
          .catch(() => {
            setTimeLocked(true)
          })
      }
    }
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- save once on expiry
  }, [
    sessionQuery.data?.ends_at,
    sessionQuery.data?.started_at,
    sessionQuery.data?.time_limit_min,
    sessionQuery.data?.submission_status,
    sessionQuery.data?.task?.id,
    sessionQuery.data?.has_next_task,
  ])

  const activeCode = workspace.files[workspace.activePath] ?? ''
  const fileNames = useMemo(
    () => Object.keys(workspace.files).sort((a, b) => a.localeCompare(b)),
    [workspace.files],
  )

  const setActiveCode = (next: string) => {
    setWorkspace((prev) => ({
      ...prev,
      files: { ...prev.files, [prev.activePath]: next },
    }))
  }

  const runMutation = useMutation({
    mutationFn: () =>
      runPublicCodingExamples(token, {
        language,
        code: workspace.files[workspace.entryPath] ?? activeCode,
        workspace,
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

  const addFile = () => {
    const name = newFileName.trim().replace(/\\/g, '/')
    if (!name || name.includes('..') || workspace.files[name]) return
    setWorkspace((prev) => ({
      ...prev,
      files: { ...prev.files, [name]: '' },
      activePath: name,
    }))
    setNewFileName('')
    setShowAddFile(false)
  }

  const removeFile = (path: string) => {
    if (fileNames.length <= 1) return
    setWorkspace((prev) => {
      const files = { ...prev.files }
      delete files[path]
      const nextActive =
        prev.activePath === path ? Object.keys(files)[0] ?? prev.entryPath : prev.activePath
      const nextEntry =
        prev.entryPath === path ? Object.keys(files)[0] ?? nextActive : prev.entryPath
      return { files, activePath: nextActive, entryPath: nextEntry }
    })
  }

  const locked = submittedOk || timeLocked
  const timerUrgent =
    remainingSec !== null && remainingSec <= 5 * 60 && remainingSec > 0
  const langLabel = codingLanguageMeta(language).label
  const runEnvError =
    runResult?.results.find((r) => r.error)?.error ||
    runResult?.results.find((r) => r.stderr)?.stderr ||
    null

  const onResultsDragStart = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    dragRef.current = { startY: e.clientY, startH: resultsHeight }
    setDraggingResults(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onResultsDragMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return
    const dy = dragRef.current.startY - e.clientY
    const colH = editorColRef.current?.clientHeight ?? 600
    const maxH = Math.max(RESULTS_MIN, Math.floor(colH * 0.72))
    setResultsHeight(
      Math.min(maxH, Math.max(RESULTS_MIN, dragRef.current.startH + dy)),
    )
  }

  const onResultsDragEnd = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = null
    setDraggingResults(false)
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // already released
    }
  }

  if (!token) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-400">
        Invalid coding link.
      </div>
    )
  }

  if (sessionQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Preparing your workspace…
      </div>
    )
  }

  if (sessionQuery.isError || !sessionQuery.data) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <AlertCircle className="h-8 w-8 text-rose-400" />
        <p className="text-sm text-rose-300">
          {sessionQuery.error instanceof ApiError
            ? formatApiError(sessionQuery.error.message, sessionQuery.error.detail)
            : 'This coding link is invalid or expired.'}
        </p>
        <p className="max-w-md text-xs text-zinc-500">
          Open the exact link shared for your coding round.
        </p>
      </div>
    )
  }

  const task = sessionQuery.data.task
  const busy = saveMutation.isPending || runMutation.isPending
  const entryFn = task.entry_function || 'solution'

  return (
    <div
      className={cn(
        'coding-workspace relative flex h-full min-h-0 flex-col bg-[#0f1115] text-zinc-200',
        draggingResults && 'coding-dragging',
      )}
    >
      {timeLocked && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-[#0f1115]/96 px-6 text-center backdrop-blur-sm">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/30">
            <CheckCircle2 className="h-7 w-7 text-emerald-400" />
          </div>
          <p className="text-xl font-semibold tracking-tight text-white">
            Thank you for your time
          </p>
          <p className="max-w-md text-sm leading-relaxed text-zinc-400">
            Your coding round has ended. Your latest work was saved automatically. You can
            close this window.
          </p>
        </div>
      )}

      {/* Toolbar */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-white/5 bg-[#14171d] px-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-sky-500/15 text-[11px] font-bold text-sky-300">
            P
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-sm font-semibold tracking-tight text-white">
                {task.title}
              </h1>
              {(sessionQuery.data.task_count ?? 1) > 1 && (
                <span className="shrink-0 rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-medium text-zinc-300 ring-1 ring-white/10">
                  Task {sessionQuery.data.task_index ?? 1} of{' '}
                  {sessionQuery.data.task_count}
                </span>
              )}
              {submittedOk && !timeLocked && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300 ring-1 ring-emerald-500/30">
                  <CheckCircle2 className="h-3 w-3" />
                  Submitted
                </span>
              )}
            </div>
            <p className="truncate text-[11px] text-zinc-500">
              Prabhat Coding
              {sessionQuery.data.domain_name
                ? ` · ${sessionQuery.data.domain_name}`
                : ''}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {remainingSec !== null && (
            <div
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 font-mono text-sm tabular-nums tracking-wide',
                remainingSec <= 0
                  ? 'bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30'
                  : timerUrgent
                    ? 'bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30'
                    : 'bg-white/5 text-zinc-200 ring-1 ring-white/10',
              )}
              title="Time remaining"
            >
              <Clock className="h-3.5 w-3.5 opacity-80" />
              {formatRemaining(remainingSec)}
            </div>
          )}

          <div
            className="hidden h-8 items-center rounded-md bg-white/5 px-2.5 text-xs text-zinc-300 ring-1 ring-white/10 sm:flex"
            title={
              sessionQuery.data.language_locked !== false
                ? `Language locked to ${langLabel}`
                : 'Language'
            }
          >
            {sessionQuery.data.language_locked !== false ? (
              <span>{langLabel}</span>
            ) : (
              <select
                className="bg-transparent text-xs outline-none"
                value={language}
                disabled={locked}
                onChange={(e) => setLanguage(e.target.value as CodingLanguage)}
              >
                {(sessionQuery.data.allowed_languages?.length
                  ? sessionQuery.data.allowed_languages
                  : [language]
                ).map((lang) => (
                  <option key={lang} value={lang} className="bg-[#14171d]">
                    {codingLanguageMeta(lang).label}
                  </option>
                ))}
              </select>
            )}
          </div>

          <button
            type="button"
            disabled={busy || locked}
            onClick={() => runMutation.mutate()}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-sky-600 px-3 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-40"
          >
            {runMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5 fill-current" />
            )}
            Run
          </button>

          {!locked && (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => saveMutation.mutate('draft')}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-white/5 px-3 text-xs font-medium text-zinc-200 ring-1 ring-white/10 hover:bg-white/10 disabled:opacity-40"
              >
                {saveMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                Save
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => saveMutation.mutate('submitted')}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-emerald-600 px-3 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
              >
                <Send className="h-3.5 w-3.5" />
                Submit
              </button>
            </>
          )}
        </div>
      </header>

      {error && (
        <div className="flex shrink-0 items-start gap-2 border-b border-rose-500/20 bg-rose-500/10 px-4 py-2 text-xs text-rose-300">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px]">
        {/* Editor column */}
        <section
          ref={editorColRef}
          className="flex min-h-0 min-w-0 flex-col border-r border-white/5"
        >
          {/* File tabs */}
          <div className="flex h-9 shrink-0 items-center gap-1 overflow-x-auto border-b border-white/5 bg-[#12151a] px-2">
            {fileNames.map((name) => {
              const active = workspace.activePath === name
              const isEntry = workspace.entryPath === name
              return (
                <div
                  key={name}
                  className={cn(
                    'group flex h-7 shrink-0 items-center gap-1 rounded-md px-2 text-[11px]',
                    active
                      ? 'bg-white/10 text-white'
                      : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200',
                  )}
                >
                  <button
                    type="button"
                    className="max-w-[140px] truncate"
                    onClick={() => setWorkspace((p) => ({ ...p, activePath: name }))}
                  >
                    {name}
                    {isEntry ? (
                      <span className="ml-1 text-[9px] uppercase tracking-wide text-sky-400">
                        entry
                      </span>
                    ) : null}
                  </button>
                  {!isEntry && !locked && (
                    <button
                      type="button"
                      title="Set as entry file"
                      className="hidden text-[9px] uppercase tracking-wide text-zinc-500 group-hover:inline hover:text-sky-400"
                      onClick={() => setWorkspace((p) => ({ ...p, entryPath: name }))}
                    >
                      set
                    </button>
                  )}
                  {fileNames.length > 1 && !locked && (
                    <button
                      type="button"
                      className="hidden text-zinc-500 group-hover:inline hover:text-rose-300"
                      onClick={() => removeFile(name)}
                      title="Remove file"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              )
            })}
            {!locked && (
              showAddFile ? (
                <div className="flex items-center gap-1 pl-1">
                  <input
                    autoFocus
                    value={newFileName}
                    onChange={(e) => setNewFileName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') addFile()
                      if (e.key === 'Escape') {
                        setShowAddFile(false)
                        setNewFileName('')
                      }
                    }}
                    placeholder="Helper.java"
                    className="h-7 w-28 rounded-md border border-white/10 bg-[#0f1115] px-2 text-[11px] text-zinc-200 outline-none focus:border-sky-500/50"
                  />
                  <button
                    type="button"
                    onClick={addFile}
                    className="h-7 rounded-md bg-sky-600 px-2 text-[11px] text-white"
                  >
                    Add
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowAddFile(true)}
                  className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11px] text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
                  title="Add file"
                >
                  <FilePlus2 className="h-3.5 w-3.5" />
                  File
                </button>
              )
            )}
          </div>

          <div className="min-h-0 flex-1">
            <Editor
              height="100%"
              language={monacoLang(workspace.activePath, language)}
              value={activeCode}
              onChange={(v) => setActiveCode(v ?? '')}
              theme="vs-dark"
              options={{
                readOnly: locked,
                minimap: { enabled: false },
                fontSize: 14,
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                wordWrap: 'on',
                automaticLayout: true,
                scrollBeyondLastLine: false,
                tabSize: 2,
                padding: { top: 12, bottom: 12 },
                lineNumbers: 'on',
                renderLineHighlight: 'line',
                scrollbar: { verticalScrollbarSize: 4, horizontalScrollbarSize: 4 },
                overviewRulerLanes: 0,
              }}
            />
          </div>

          {/* Drag handle — pull up/down like IDE terminal */}
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize results panel"
            onPointerDown={onResultsDragStart}
            onPointerMove={onResultsDragMove}
            onPointerUp={onResultsDragEnd}
            onPointerCancel={onResultsDragEnd}
            className={cn(
              'group relative z-10 flex h-1.5 shrink-0 cursor-row-resize items-center justify-center border-t border-white/5 bg-[#12151a] hover:bg-sky-500/20',
              draggingResults && 'bg-sky-500/30',
            )}
          >
            <div
              className={cn(
                'h-0.5 w-10 rounded-full bg-zinc-600 group-hover:bg-sky-400',
                draggingResults && 'bg-sky-400',
              )}
            />
          </div>

          {/* Results */}
          <div
            className="flex shrink-0 flex-col bg-[#12151a]"
            style={{ height: resultsHeight }}
          >
            <div className="flex h-9 shrink-0 items-center justify-between gap-2 px-4">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                  Results
                </span>
                {runResult && (
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[10px] font-medium ring-1',
                      runResult.all_passed
                        ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
                        : 'bg-rose-500/15 text-rose-300 ring-rose-500/30',
                    )}
                  >
                    {runResult.passed}/{runResult.total} passed
                  </span>
                )}
                {runResult?.complexity && (
                  <span
                    className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-medium text-violet-200 ring-1 ring-violet-500/30"
                    title={
                      runResult.complexity.note
                        ? `${runResult.complexity.note} (${runResult.complexity.confidence || 'estimate'})`
                        : 'Estimated complexity of your current code'
                    }
                  >
                    Time {runResult.complexity.time}
                    <span className="mx-1 text-violet-400/60">·</span>
                    Space {runResult.complexity.space}
                  </span>
                )}
              </div>
              <span className="truncate text-[11px] text-zinc-600">
                Your output = return value of{' '}
                <code className="text-sky-300/90">{entryFn}</code>
              </span>
            </div>

            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 pb-3">
              {!runResult && !runMutation.isPending && (
                <div className="flex h-full min-h-[80px] items-center justify-center rounded-lg border border-dashed border-white/10 px-4 text-center text-xs text-zinc-500">
                  Click Run to see expected vs your code’s return value for each example.
                </div>
              )}

              {runMutation.isPending && (
                <div className="flex items-center gap-2 px-1 py-3 text-xs text-zinc-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Running examples…
                </div>
              )}

              {runEnvError && runResult && !runResult.all_passed && (
                <div className="flex items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <div className="min-w-0">
                    <p className="font-medium">Couldn’t execute your code</p>
                    <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-amber-100/80">
                      {runEnvError}
                    </pre>
                  </div>
                </div>
              )}

              {runResult?.results.map((row) => {
                const yourOutput = (row.actual || '').trim()
                const hasYourOutput = yourOutput.length > 0
                return (
                  <div
                    key={row.index}
                    className={cn(
                      'rounded-lg border px-3 py-2.5',
                      row.passed
                        ? 'border-emerald-500/20 bg-emerald-500/5'
                        : 'border-rose-500/20 bg-rose-500/5',
                    )}
                  >
                    <div className="mb-2.5 flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-zinc-200">
                        Example {row.index}
                      </span>
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 text-[11px] font-medium',
                          row.passed ? 'text-emerald-300' : 'text-rose-300',
                        )}
                      >
                        {row.passed ? (
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        ) : (
                          <XCircle className="h-3.5 w-3.5" />
                        )}
                        {row.passed
                          ? 'Passed'
                          : row.timed_out
                            ? 'Timeout'
                            : row.error
                              ? 'Error'
                              : 'Failed'}
                      </span>
                    </div>

                    <div className="space-y-2 text-[11px] leading-relaxed">
                      <div>
                        <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                          Input
                        </p>
                        <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-black/25 px-2 py-1.5 font-mono text-zinc-300">
                          {row.input}
                        </pre>
                      </div>

                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <div>
                          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                            Expected
                          </p>
                          <pre className="overflow-x-auto whitespace-pre-wrap rounded-md border border-white/10 bg-black/20 px-2 py-1.5 font-mono text-zinc-300">
                            {row.expected || '—'}
                          </pre>
                        </div>
                        <div>
                          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-sky-400/90">
                            Your output
                          </p>
                          <pre
                            className={cn(
                              'overflow-x-auto whitespace-pre-wrap rounded-md border px-2 py-1.5 font-mono',
                              row.passed
                                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                                : hasYourOutput
                                  ? 'border-sky-500/40 bg-sky-500/10 text-sky-100'
                                  : 'border-zinc-600/40 bg-black/30 text-zinc-500',
                            )}
                          >
                            {hasYourOutput
                              ? yourOutput
                              : row.timed_out
                                ? '(timed out — no return value)'
                                : row.error
                                  ? '(no return value — see error below)'
                                  : '(empty — function returned nothing)'}
                          </pre>
                        </div>
                      </div>

                      {!row.passed && hasYourOutput && (
                        <p className="text-[11px] text-rose-300/90">
                          Mismatch: your code returned{' '}
                          <code className="rounded bg-black/30 px-1 font-mono text-sky-200">
                            {yourOutput}
                          </code>
                          , but expected{' '}
                          <code className="rounded bg-black/30 px-1 font-mono text-zinc-200">
                            {row.expected}
                          </code>
                          .
                        </p>
                      )}

                      {(row.stderr || row.error) && (
                        <div>
                          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-400/90">
                            Console / error
                          </p>
                          <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-1.5 font-mono text-[11px] text-amber-100/90">
                            {[row.error, row.stderr].filter(Boolean).join('\n')}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        {/* Problem panel */}
        <aside className="flex min-h-0 flex-col bg-[#14171d]">
          <div className="flex h-9 shrink-0 items-center border-b border-white/5 px-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Problem
            </span>
          </div>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
            <div>
              <h2 className="text-base font-semibold tracking-tight text-white">
                {task.title}
              </h2>
              <p className="mt-1.5 text-[11px] text-zinc-500">
                {sessionQuery.data.time_limit_min} min · {langLabel}
                {(sessionQuery.data.task_count ?? 1) > 1
                  ? ` · problem ${sessionQuery.data.task_index ?? 1}/${sessionQuery.data.task_count}`
                  : ''}
              </p>
            </div>

            <div className="rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-3 text-[12px] leading-relaxed text-zinc-200">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-sky-300/90">
                What you must do
              </p>
              <p className="mt-1.5">
                Implement{' '}
                <code className="rounded bg-black/35 px-1.5 py-0.5 font-mono text-sky-300">
                  {entryFn}
                </code>
                . Read the input, compute the answer, and{' '}
                <span className="font-medium text-white">return</span> it (do not rely on{' '}
                <code className="font-mono text-zinc-400">print</code>).
              </p>
              <p className="mt-2 text-zinc-400">
                Grading compares your <span className="text-zinc-200">return value</span> to
                each example’s Output. The examples below are the source of truth.
              </p>
            </div>

            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                Description
              </p>
              <p className="text-[13px] leading-relaxed text-zinc-300 whitespace-pre-wrap">
                {task.statement}
              </p>
            </div>

            {task.examples?.length > 0 && (
              <div className="space-y-2.5">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                    Examples (graded)
                  </p>
                  <p className="mt-0.5 text-[11px] text-zinc-500">
                    For each Input, your function must return exactly the Output shown.
                  </p>
                </div>
                {task.examples.map((ex, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-white/8 bg-[#0f1115] px-3 py-2.5"
                  >
                    <p className="mb-1.5 text-[11px] font-medium text-zinc-400">
                      Example {i + 1}
                    </p>
                    <div className="space-y-1.5 text-[11px] leading-relaxed">
                      <div>
                        <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                          Input
                        </p>
                        <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap rounded-md bg-black/25 px-2 py-1.5 font-mono text-zinc-200">
                          {ex.input}
                        </pre>
                      </div>
                      <div>
                        <p className="text-[10px] font-medium uppercase tracking-wide text-emerald-400/80">
                          Required return
                        </p>
                        <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap rounded-md border border-emerald-500/20 bg-emerald-500/5 px-2 py-1.5 font-mono text-emerald-100">
                          {ex.output}
                        </pre>
                      </div>
                    </div>
                    {ex.explanation ? (
                      <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
                        {ex.explanation}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            )}

            {task.constraints_text ? (
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                  Constraints
                </p>
                <p className="mt-1.5 text-[12px] leading-relaxed text-zinc-400 whitespace-pre-wrap">
                  {task.constraints_text}
                </p>
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  )
}
