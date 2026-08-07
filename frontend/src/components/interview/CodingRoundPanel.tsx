import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Code2, Loader2, Lock } from 'lucide-react'
import { listCodingDomains, listDomainCodingTasks } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
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
  /** Ordered selected task ids (multi-select). */
  taskIds: string[]
  /** Per-task recruiter time (minutes). Prefills from AI estimate. */
  taskTimes: Record<string, number>
  /** @deprecated kept for callers that still read single-task fields */
  assignedTaskId: string | null
  timeLimitMin: number
}

type CodingRoundPanelProps = {
  value: CodingRoundState
  onChange: (next: CodingRoundState) => void
  disabled?: boolean
}

function nearestTimeOption(minutes: number): number {
  let best: number = TIME_OPTIONS[0]
  let bestDiff = Math.abs(minutes - best)
  for (const opt of TIME_OPTIONS) {
    const diff = Math.abs(minutes - opt)
    if (diff < bestDiff) {
      best = opt
      bestDiff = diff
    }
  }
  return best
}

function estimateForTask(estimated?: number | null): number {
  if (estimated != null && Number.isFinite(estimated)) {
    return nearestTimeOption(Math.max(5, Math.min(180, Number(estimated))))
  }
  return DEFAULT_TASK_TIME
}

export function toInterviewCodingConfig(state: CodingRoundState): InterviewCodingConfig | undefined {
  if (!state.enabled) {
    return {
      enabled: false,
      domain_id: null,
      allowed_languages: state.defaultLanguage ? [state.defaultLanguage] : ['python'],
      default_language: state.defaultLanguage,
      task_ids: [],
      assigned_task_id: null,
      time_limit_min: state.timeLimitMin || DEFAULT_TASK_TIME,
      task_time_limits: {},
    }
  }
  if (!state.domainId || state.taskIds.length === 0) return undefined
  const firstId = state.taskIds[0]
  const limits: Record<string, number> = {}
  for (const id of state.taskIds) {
    limits[id] = state.taskTimes[id] ?? DEFAULT_TASK_TIME
  }
  return {
    enabled: true,
    domain_id: state.domainId,
    allowed_languages: [state.defaultLanguage],
    default_language: state.defaultLanguage,
    task_ids: state.taskIds,
    assigned_task_id: firstId,
    time_limit_min: limits[firstId] ?? DEFAULT_TASK_TIME,
    task_time_limits: limits,
  }
}

export function CodingRoundPanel({ value, onChange, disabled }: CodingRoundPanelProps) {
  const [localTimes, setLocalTimes] = useState<Record<string, number>>({})

  const domainsQuery = useQuery({
    queryKey: queryKeys.codingDomains,
    queryFn: listCodingDomains,
    staleTime: 60_000,
  })

  const tasksQuery = useQuery({
    queryKey: queryKeys.codingDomainTasks(value.domainId ?? ''),
    queryFn: () => listDomainCodingTasks(value.domainId!),
    enabled: Boolean(value.enabled && value.domainId),
    staleTime: 30_000,
  })

  const domains = domainsQuery.data ?? []
  const tasks = (tasksQuery.data ?? []).slice(0, MAX_ASSIGNED)
  const selectedDomain = domains.find((d) => d.id === value.domainId)
  const selected = new Set(value.taskIds)

  useEffect(() => {
    setLocalTimes({})
  }, [value.domainId])

  // Prefill times from AI estimates when tasks load
  useEffect(() => {
    if (!tasks.length) return
    setLocalTimes((prev) => {
      const next = { ...prev }
      let changed = false
      for (const task of tasks) {
        if (next[task.id] == null && value.taskTimes[task.id] == null) {
          next[task.id] = estimateForTask(task.estimated_time_min)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [tasks, value.taskTimes])

  const timeForTask = (taskId: string, estimated?: number | null) =>
    value.taskTimes[taskId] ??
    localTimes[taskId] ??
    estimateForTask(estimated)

  const emitSelection = (
    taskIds: string[],
    timesPatch?: Record<string, number>,
  ) => {
    const mergedTimes = { ...localTimes, ...value.taskTimes, ...(timesPatch || {}) }
    for (const id of taskIds) {
      if (mergedTimes[id] == null) {
        const task = tasks.find((t) => t.id === id)
        mergedTimes[id] = estimateForTask(task?.estimated_time_min)
      }
    }
    setLocalTimes(mergedTimes)
    onChange({
      ...value,
      taskIds,
      taskTimes: Object.fromEntries(taskIds.map((id) => [id, mergedTimes[id]])),
      assignedTaskId: taskIds[0] ?? null,
      timeLimitMin: taskIds[0]
        ? mergedTimes[taskIds[0]] ?? DEFAULT_TASK_TIME
        : value.timeLimitMin,
    })
  }

  const toggleTask = (taskId: string, estimated?: number | null) => {
    if (disabled) return
    if (selected.has(taskId)) {
      emitSelection(value.taskIds.filter((id) => id !== taskId))
      return
    }
    if (value.taskIds.length >= MAX_ASSIGNED) return
    const minutes = timeForTask(taskId, estimated)
    emitSelection([...value.taskIds, taskId], { [taskId]: minutes })
  }

  const setTaskTime = (taskId: string, minutes: number, estimated?: number | null) => {
    const nextTimes = {
      ...localTimes,
      ...value.taskTimes,
      [taskId]: minutes,
    }
    setLocalTimes(nextTimes)
    const taskIds = selected.has(taskId) ? value.taskIds : [...value.taskIds, taskId]
    if (!selected.has(taskId) && value.taskIds.length >= MAX_ASSIGNED) {
      // Already at max and not selected — only update local preview time
      return
    }
    emitSelection(taskIds.slice(0, MAX_ASSIGNED), {
      [taskId]: minutes || estimateForTask(estimated),
    })
  }

  const totalMinutes = value.taskIds.reduce(
    (sum, id) => sum + (value.taskTimes[id] ?? localTimes[id] ?? DEFAULT_TASK_TIME),
    0,
  )

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Code2 className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
            <Label className="text-sm font-medium">Coding task round</Label>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Choose a domain, select one or more problems, and set time per task.
            The candidate works them one-by-one; each task uses its own timer.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={value.enabled}
          disabled={disabled || domainsQuery.isLoading}
          onClick={() => {
            const enabling = !value.enabled
            const firstDomain = domains[0]
            const lang = (firstDomain?.language as CodingLanguage) || 'python'
            onChange({
              ...value,
              enabled: enabling,
              domainId: enabling ? value.domainId || firstDomain?.id || null : value.domainId,
              defaultLanguage: enabling
                ? ((domains.find((d) => d.id === (value.domainId || firstDomain?.id))
                    ?.language as CodingLanguage) || lang)
                : value.defaultLanguage,
            })
          }}
          className={cn(
            'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors',
            value.enabled ? 'border-primary bg-primary' : 'border-border bg-muted',
            (disabled || domainsQuery.isLoading) && 'opacity-50',
          )}
        >
          <span
            className={cn(
              'inline-block h-4 w-4 transform rounded-full bg-background shadow transition-transform',
              value.enabled ? 'translate-x-6' : 'translate-x-1',
            )}
          />
        </button>
      </div>

      {domainsQuery.isLoading && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Loading domains…
        </p>
      )}

      {value.enabled && (
        <div className="space-y-4 rounded-lg border border-border bg-muted/20 p-3">
          <div className="max-w-md">
            <Label>Domain</Label>
            <Select
              value={value.domainId ?? undefined}
              onValueChange={(id) => {
                const domain = domains.find((d) => d.id === id)
                const lang = (domain?.language as CodingLanguage) || 'python'
                onChange({
                  ...value,
                  domainId: id,
                  defaultLanguage: lang,
                  assignedTaskId: null,
                  taskIds: [],
                  taskTimes: {},
                })
              }}
              disabled={disabled}
            >
              <SelectTrigger className="mt-1.5">
                <SelectValue placeholder="Select domain" />
              </SelectTrigger>
              <SelectContent>
                {domains.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name} ({d.language})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedDomain && (
              <p className="mt-1.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                <Lock className="h-3 w-3" />
                Candidate locked to {selectedDomain.language}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <Label>Assign problems from this domain</Label>
                <p className="text-[11px] text-muted-foreground">
                  Select one or more tasks. Time defaults to the AI estimate — change it if needed.
                </p>
              </div>
              {value.taskIds.length > 0 && (
                <p className="text-[11px] text-muted-foreground">
                  {value.taskIds.length} selected · ~{totalMinutes} min total
                </p>
              )}
            </div>
            {tasksQuery.isLoading && (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading problems…
              </p>
            )}
            <div className="space-y-2">
              {tasks.map((task) => {
                const isSelected = selected.has(task.id)
                const aiEstimate = estimateForTask(task.estimated_time_min)
                const rowTime = timeForTask(task.id, task.estimated_time_min)
                return (
                  <div
                    key={task.id}
                    className={cn(
                      'w-full rounded-md border px-3 py-2.5 transition-colors',
                      isSelected
                        ? 'border-primary bg-primary/5'
                        : 'border-border bg-background hover:bg-muted/40',
                      disabled && 'pointer-events-none opacity-50',
                    )}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-2.5">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-primary"
                          checked={isSelected}
                          disabled={disabled || (!isSelected && value.taskIds.length >= MAX_ASSIGNED)}
                          onChange={() => toggleTask(task.id, task.estimated_time_min)}
                        />
                        <span className="min-w-0">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium">{task.title}</span>
                            <Badge variant="secondary">{task.difficulty}</Badge>
                          </span>
                          <span className="mt-1 block text-[11px] text-muted-foreground">
                            {(task.skill_tags ?? []).join(' · ') || task.slug}
                          </span>
                          <span className="mt-1 block text-[11px] text-muted-foreground">
                            AI estimate: {aiEstimate} min
                          </span>
                        </span>
                      </label>
                      <div
                        className="w-[7.5rem] shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Select
                          value={String(rowTime)}
                          onValueChange={(v) =>
                            setTaskTime(task.id, Number(v), task.estimated_time_min)
                          }
                          disabled={disabled}
                        >
                          <SelectTrigger
                            className="h-8"
                            aria-label={`Time limit for ${task.title}`}
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {TIME_OPTIONS.map((n) => (
                              <SelectItem key={n} value={String(n)}>
                                {n} min
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
            {!value.domainId && (
              <p className="text-xs text-destructive">Select a domain first.</p>
            )}
            {value.domainId && !tasksQuery.isLoading && tasks.length === 0 && (
              <p className="text-xs text-destructive">
                No coding task assigned — this domain has no problems yet.
                Go to the Coding dashboard and generate tasks, then come back
                and select one or more.
              </p>
            )}
            {value.domainId && tasks.length > 0 && value.taskIds.length === 0 && (
              <p className="text-xs text-destructive">
                No coding task assigned yet — select at least one problem and set its time.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
