import { cn } from '@/lib/utils'
import { Check } from 'lucide-react'

const BASE_STEPS = [
  { key: 'joining', label: 'Joining' },
  { key: 'lobby', label: 'Lobby' },
  { key: 'in_meeting', label: 'In meeting' },
  { key: 'localizing', label: 'Localizing' },
  { key: 'ready', label: 'Ready' },
  { key: 'live', label: 'Live' },
  { key: 'ended', label: 'Voice interview done' },
] as const

export type StepKey =
  | (typeof BASE_STEPS)[number]['key']
  | 'coding'
  | 'interview_done'

export type CodingTaskStepStatus = 'pending' | 'in_progress' | 'submitted' | 'timed_out'

export interface CodingTaskStepItem {
  task_id: string
  title: string
  status: CodingTaskStepStatus
}

function resolveActiveStep(props: {
  recallPhase?: string
  localizationStatus?: string
  readyToStart?: boolean
  interviewStarted?: boolean
  interviewEnded?: boolean
  languageMode?: string
  codingEnabled?: boolean
  codingRoundActive?: boolean
  /** False while coding session lookup has not settled (avoid false “interview done”). */
  codingStatusKnown?: boolean
}): StepKey {
  if (props.interviewEnded) {
    // Still resolving whether a coding round exists — stay on voice-done.
    if (props.codingStatusKnown === false) return 'ended'
    if (props.codingEnabled && props.codingRoundActive) return 'coding'
    return 'interview_done'
  }
  if (props.interviewStarted) return 'live'
  if (props.readyToStart) return 'ready'
  if (
    props.languageMode === 'hinglish' &&
    props.localizationStatus === 'pending' &&
    props.recallPhase === 'in_meeting'
  ) {
    return 'localizing'
  }
  if (props.recallPhase === 'in_meeting') return 'in_meeting'
  if (props.recallPhase === 'lobby') return 'lobby'
  return 'joining'
}

function taskStatusLabel(status: CodingTaskStepStatus): string {
  switch (status) {
    case 'submitted':
      return 'Complete'
    case 'timed_out':
      return 'Timed out'
    case 'in_progress':
      return 'In progress'
    default:
      return 'Pending'
  }
}

interface StatusStepperProps {
  recallPhase?: string
  localizationStatus?: string
  readyToStart?: boolean
  interviewStarted?: boolean
  interviewEnded?: boolean
  languageMode?: string
  /** Show Coding step after voice interview ends when true */
  codingEnabled?: boolean
  /**
   * When true, coding is still in progress.
   * When false with codingEnabled, Coding step shows as complete.
   */
  codingRoundActive?: boolean
  /**
   * Whether we know if a coding round exists.
   * Pass false while the coding-session lookup is still in flight.
   */
  codingStatusKnown?: boolean
  codingTasks?: CodingTaskStepItem[]
}

export function StatusStepper(props: StatusStepperProps) {
  const codingKnown = props.codingStatusKnown !== false
  const showCoding = Boolean(props.codingEnabled && props.interviewEnded && codingKnown)
  const codingComplete = showCoding && props.codingRoundActive === false
  const showInterviewDone = Boolean(props.interviewEnded && codingKnown)
  const active = resolveActiveStep(props)

  const steps: { key: StepKey; label: string }[] = [
    ...BASE_STEPS.filter(
      (step) => !(step.key === 'localizing' && props.languageMode !== 'hinglish'),
    ),
    ...(showCoding
      ? [
          {
            key: 'coding' as const,
            label: codingComplete
              ? 'Coding round done'
              : 'Coding round in progress',
          },
        ]
      : []),
    ...(showInterviewDone
      ? [{ key: 'interview_done' as const, label: 'Interview done' }]
      : []),
  ]

  const activeIndex = steps.findIndex((s) => s.key === active)
  const codingTasks = props.codingTasks ?? []

  return (
    <ol className="flex flex-col gap-2">
      {steps.map((step, index) => {
        const done =
          step.key === 'coding'
            ? codingComplete || active === 'interview_done'
            : step.key === 'interview_done'
              ? active === 'interview_done'
              : activeIndex >= 0 && index < activeIndex
        const current =
          step.key === 'coding'
            ? active === 'coding'
            : step.key === 'interview_done'
              ? active === 'interview_done'
              : index === activeIndex
        const displayNumber = index + 1

        return (
          <li key={step.key} className="flex flex-col gap-1">
            <div
              className={cn(
                'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                current && 'bg-[#f0fdf4] dark:bg-[#166534] font-medium text-foreground',
                done && !current && 'text-muted-foreground',
                !done && !current && 'text-muted-foreground',
              )}
            >
              <span
                className={cn(
                  'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs',
                  done && 'border-primary bg-primary text-primary-foreground',
                  current && !done && 'border-primary',
                )}
              >
                {done ? <Check className="h-3 w-3" /> : displayNumber}
              </span>
              {step.label}
            </div>

            {step.key === 'coding' && codingTasks.length > 0 ? (
              <ol className="ml-7 space-y-1 border-l border-border/70 pl-3">
                {codingTasks.map((task, taskIndex) => (
                  <li
                    key={task.task_id}
                    className={cn(
                      'flex items-start justify-between gap-2 py-0.5 text-[11px] leading-snug',
                      task.status === 'in_progress' && 'font-medium text-foreground',
                      task.status === 'submitted' && 'text-muted-foreground',
                      task.status === 'timed_out' && 'text-destructive',
                      task.status === 'pending' && 'text-muted-foreground',
                    )}
                  >
                    <span className="min-w-0">
                      Task {taskIndex + 1}
                      {task.title ? `: ${task.title}` : ''}
                    </span>
                    <span className="shrink-0">{taskStatusLabel(task.status)}</span>
                  </li>
                ))}
              </ol>
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}
