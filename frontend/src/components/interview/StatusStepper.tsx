import { cn } from '@/lib/utils'
import { Check } from 'lucide-react'

const STEPS = [
  { key: 'joining', label: 'Joining' },
  { key: 'lobby', label: 'Lobby' },
  { key: 'in_meeting', label: 'In meeting' },
  { key: 'localizing', label: 'Localizing' },
  { key: 'ready', label: 'Ready' },
  { key: 'live', label: 'Live' },
  { key: 'ended', label: 'Ended' },
] as const

export type StepKey = (typeof STEPS)[number]['key']

function resolveActiveStep(props: {
  recallPhase?: string
  localizationStatus?: string
  readyToStart?: boolean
  interviewStarted?: boolean
  interviewEnded?: boolean
  languageMode?: string
}): StepKey {
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

interface StatusStepperProps {
  recallPhase?: string
  localizationStatus?: string
  readyToStart?: boolean
  interviewStarted?: boolean
  interviewEnded?: boolean
  languageMode?: string
}

export function StatusStepper(props: StatusStepperProps) {
  const active = resolveActiveStep(props)
  const activeIndex = STEPS.findIndex((s) => s.key === active)

  return (
    <ol className="flex flex-col gap-2">
      {STEPS.map((step, index) => {
        const done = index < activeIndex
        const current = index === activeIndex
        const skipLocalizing =
          step.key === 'localizing' && props.languageMode !== 'hinglish'
        if (skipLocalizing) return null

        return (
          <li
            key={step.key}
            className={cn(
              'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
              current && 'bg-[#f0fdf4] font-medium text-foreground',
              done && 'text-muted-foreground',
              !done && !current && 'text-muted-foreground/70',
            )}
          >
            <span
              className={cn(
                'flex h-5 w-5 items-center justify-center rounded-full border text-xs',
                done && 'border-primary bg-primary text-primary-foreground',
                current && 'border-primary',
              )}
            >
              {done ? <Check className="h-3 w-3" /> : index + 1}
            </span>
            {step.label}
          </li>
        )
      })}
    </ol>
  )
}
