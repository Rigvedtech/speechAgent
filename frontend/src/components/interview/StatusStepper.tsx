import { cn } from '@/lib/utils'
import { Check } from 'lucide-react'

const BASE_STEPS = [
  { key: 'joining', label: 'Joining' },
  { key: 'lobby', label: 'Lobby' },
  { key: 'in_meeting', label: 'In meeting' },
  { key: 'localizing', label: 'Localizing' },
  { key: 'ready', label: 'Ready' },
  { key: 'live', label: 'Live' },
  { key: 'ended', label: 'Ended' },
] as const

export type StepKey = (typeof BASE_STEPS)[number]['key'] | 'coding'

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
}): StepKey {
  // After voice interview ends, advance to Coding when that round exists.
  if (props.interviewEnded && props.codingEnabled) return 'coding'
  if (props.interviewEnded) return 'ended'
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
  /** Show Coding step after Ended when true */
  codingEnabled?: boolean
  /**
   * When true, Coding is still in progress (waiting / timed out but not fully submitted).
   * When false with codingEnabled, Coding step shows as complete.
   */
  codingRoundActive?: boolean
  codingTasks?: CodingTaskStepItem[]
}

export function StatusStepper(props: StatusStepperProps) {
  const showCoding = Boolean(props.codingEnabled && props.interviewEnded)
  const codingComplete = showCoding && props.codingRoundActive === false
  const active = resolveActiveStep(props)

  const steps: { key: StepKey; label: string }[] = [
    ...BASE_STEPS.filter(
      (step) => !(step.key === 'localizing' && props.languageMode !== 'hinglish'),
    ),
    ...(showCoding ? [{ key: 'coding' as const, label: 'Coding' }] : []),
  ]

  const activeIndex = steps.findIndex((s) => s.key === active)
  const codingTasks = props.codingTasks ?? []

  return (
    <ol className="flex flex-col gap-2">
      {steps.map((step, index) => {
        const done =
          step.key === 'coding'
            ? codingComplete
            : activeIndex >= 0 && index < activeIndex
        const current =
          step.key === 'coding'
            ? active === 'coding' && !codingComplete
            : index === activeIndex
        const displayNumber = index + 1

        return (
          <li key={step.key} className="flex flex-col gap-1">
            <div
              className={cn(
                'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                current && 'bg-[#f0fdf4] dark:bg-[#166534] font-medium text-foreground',
                done && 'text-muted-foreground',
                !done && !current && 'text-muted-foreground',
              )}
            >
              <span
                className={cn(
                  'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs',
                  done && 'border-primary bg-primary text-primary-foreground',
                  current && 'border-primary',
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
