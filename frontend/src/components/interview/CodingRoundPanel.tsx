import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Code2, Loader2, RefreshCw } from 'lucide-react'
import {
  getCodingBankStatus,
  listCodingDomains,
  previewCodingAssign,
} from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { CodingLanguage, InterviewCodingConfig } from '@/types/api'

const TIME_OPTIONS = [15, 20, 25, 30, 45, 60] as const
const DEFAULT_TASK_TIME = 30
const MAX_ASSIGNED = 5

export type CodingRoundState = {
  enabled: boolean
  domainId: string | null
  defaultLanguage: CodingLanguage
  /** How many tasks the server should auto-assign from the shared bank. */
  problemCount: number
  /** Locked-in preview assignment (sent on schedule/join). */
  taskIds: string[]
  taskTimes: Record<string, number>
  assignedTaskId: string | null
  timeLimitMin: number
}

type CodingRoundPanelProps = {
  value: CodingRoundState
  onChange: (next: CodingRoundState) => void
  disabled?: boolean
  jobPostingId?: string | null
  candidateId?: string | null
}

export function toInterviewCodingConfig(state: CodingRoundState): InterviewCodingConfig | undefined {
  if (!state.enabled) {
    return {
      enabled: false,
      domain_id: null,
      allowed_languages: state.defaultLanguage ? [state.defaultLanguage] : ['python'],
      default_language: state.defaultLanguage,
      problem_count: null,
      task_ids: [],
      assigned_task_id: null,
      time_limit_min: state.timeLimitMin || DEFAULT_TASK_TIME,
      task_time_limits: {},
    }
  }
  if (!state.domainId) return undefined
  const count = Math.max(1, Math.min(MAX_ASSIGNED, state.problemCount || 1))
  const taskIds = state.taskIds.slice(0, count)
  const limits: Record<string, number> = {}
  for (const id of taskIds) {
    limits[id] = state.taskTimes[id] ?? (state.timeLimitMin || DEFAULT_TASK_TIME)
  }
  return {
    enabled: true,
    domain_id: state.domainId,
    allowed_languages: [state.defaultLanguage],
    default_language: state.defaultLanguage,
    problem_count: count,
    // Prefer locked preview IDs so Join sees the same tasks shown here
    task_ids: taskIds,
    assigned_task_id: taskIds[0] ?? null,
    time_limit_min: state.timeLimitMin || DEFAULT_TASK_TIME,
    task_time_limits: limits,
  }
}

export function CodingRoundPanel({
  value,
  onChange,
  disabled,
  jobPostingId,
  candidateId,
}: CodingRoundPanelProps) {
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const domainsQuery = useQuery({
    queryKey: queryKeys.codingDomains,
    queryFn: listCodingDomains,
    staleTime: 60_000,
  })
  const bankStatusQuery = useQuery({
    queryKey: queryKeys.codingBankStatus,
    queryFn: getCodingBankStatus,
    staleTime: 30_000,
    enabled: value.enabled,
  })

  const count = Math.max(1, Math.min(MAX_ASSIGNED, value.problemCount || 1))
  const previewEnabled = Boolean(value.enabled && value.defaultLanguage && value.domainId)

  const previewQuery = useQuery({
    queryKey: [
      ...queryKeys.codingAssignPreview(value.defaultLanguage, count),
      jobPostingId ?? '',
      candidateId ?? '',
    ],
    queryFn: () =>
      previewCodingAssign({
        language: value.defaultLanguage,
        count,
        job_posting_id: jobPostingId,
        candidate_id: candidateId,
      }),
    enabled: previewEnabled,
    staleTime: 0,
  })

  // Sync previewed task IDs into form state for schedule/join
  useEffect(() => {
    if (!previewEnabled || !previewQuery.data) return
    const tasks = previewQuery.data.tasks
    const ids = tasks.map((t) => t.id)
    const same =
      ids.length === value.taskIds.length && ids.every((id, i) => id === value.taskIds[i])
    if (same) return
    const times: Record<string, number> = { ...value.taskTimes }
    for (const t of tasks) {
      if (times[t.id] == null) {
        times[t.id] = value.timeLimitMin || DEFAULT_TASK_TIME
      }
    }
    onChangeRef.current({
      ...value,
      taskIds: ids,
      taskTimes: times,
      assignedTaskId: ids[0] ?? null,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync only when preview payload changes
  }, [previewQuery.data, previewEnabled])

  const domains = domainsQuery.data ?? []
  const bankCount = bankStatusQuery.data?.problem_count ?? 0
  const bankEmpty = value.enabled && bankStatusQuery.isSuccess && bankCount === 0
  const picked = previewQuery.data?.tasks ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sky-500/15 ring-1 ring-sky-500/30">
            <Code2 className="h-4 w-4 text-sky-300" />
          </div>
          <p className="text-sm font-medium">Enable coding round</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={value.enabled}
          disabled={disabled}
          onClick={() =>
            onChange({
              ...value,
              enabled: !value.enabled,
              taskIds: [],
              assignedTaskId: null,
            })
          }
          className={cn(
            'relative h-6 w-11 rounded-full transition-colors',
            value.enabled ? 'bg-sky-500' : 'bg-muted',
            disabled && 'opacity-50',
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform',
              value.enabled && 'translate-x-5',
            )}
          />
        </button>
      </div>

      {value.enabled ? (
        <div className="space-y-4 rounded-lg border border-border/60 bg-muted/20 p-3">
          {domainsQuery.isLoading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading languages…
            </div>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Language</Label>
                  <Select
                    value={value.domainId ?? ''}
                    disabled={disabled}
                    onValueChange={(id) => {
                      const domain = domains.find((d) => d.id === id)
                      if (!domain) return
                      onChange({
                        ...value,
                        domainId: domain.id,
                        defaultLanguage: domain.language as CodingLanguage,
                        taskIds: [],
                        assignedTaskId: null,
                      })
                    }}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder="Select language" />
                    </SelectTrigger>
                    <SelectContent>
                      {domains.map((d) => (
                        <SelectItem key={d.id} value={d.id}>
                          {d.name} ({d.language})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">Tasks assigned</Label>
                  <Select
                    value={String(value.problemCount || 1)}
                    disabled={disabled}
                    onValueChange={(v) =>
                      onChange({
                        ...value,
                        problemCount: Number(v),
                        taskIds: [],
                        assignedTaskId: null,
                      })
                    }
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <SelectItem key={n} value={String(n)}>
                          {n} task{n === 1 ? '' : 's'}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Time per task</Label>
                <Select
                  value={String(value.timeLimitMin || DEFAULT_TASK_TIME)}
                  disabled={disabled}
                  onValueChange={(v) =>
                    onChange({
                      ...value,
                      timeLimitMin: Number(v),
                    })
                  }
                >
                  <SelectTrigger className="h-9 w-full sm:w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIME_OPTIONS.map((m) => (
                      <SelectItem key={m} value={String(m)}>
                        {m} min
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {bankEmpty ? (
                <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  Coding bank is empty — open Coding dashboard and Seed bank first.
                </p>
              ) : null}

              {previewEnabled ? (
                <div className="space-y-2 border-t border-border/50 pt-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-foreground">Assigned tasks</p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-[11px]"
                      disabled={disabled || previewQuery.isFetching}
                      onClick={() => void previewQuery.refetch()}
                    >
                      {previewQuery.isFetching ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3.5 w-3.5" />
                      )}
                      Re-pick
                    </Button>
                  </div>
                  {previewQuery.isLoading ? (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Picking tasks…
                    </div>
                  ) : previewQuery.isError ? (
                    <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
                      Could not load assigned tasks. Restart the API server, then click Re-pick.
                    </p>
                  ) : picked.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No tasks available in the bank.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {picked.map((task, index) => (
                        <li
                          key={task.id}
                          className="flex items-start justify-between gap-2 rounded-md border border-border/50 bg-card/60 px-2.5 py-2"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-xs font-medium">
                              {index + 1}. {task.title}
                            </p>
                            <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                              {(task.skill_tags || []).slice(0, 3).join(' · ') || 'DSA'}
                            </p>
                          </div>
                          <Badge variant="secondary" className="shrink-0 text-[9px] uppercase">
                            {task.difficulty}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                  {bankStatusQuery.data ? (
                    <p className="text-[11px] text-muted-foreground">
                      Bank {bankStatusQuery.data.problem_count}/{bankStatusQuery.data.max_problems}
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="text-[11px] text-muted-foreground">
                  Select a language to preview assigned tasks.
                </p>
              )}
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}
