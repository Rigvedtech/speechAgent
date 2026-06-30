import { cn } from '@/lib/utils'

interface JoinWizardStepsProps {
  step: number
  labels?: string[]
}

const DEFAULT_LABELS = ['Meeting', 'Candidate', 'Questions']

export function JoinWizardSteps({ step, labels = DEFAULT_LABELS }: JoinWizardStepsProps) {
  return (
    <ol className="mb-6 flex items-center gap-2">
      {labels.map((label, index) => {
        const num = index + 1
        const active = num === step
        const done = num < step
        return (
          <li key={label} className="flex flex-1 items-center gap-2">
            <span
              className={cn(
                'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-medium',
                active && 'bg-primary text-primary-foreground',
                done && 'bg-muted text-foreground',
                !active && !done && 'border border-border text-muted-foreground',
              )}
            >
              {num}
            </span>
            <span
              className={cn(
                'hidden text-sm sm:inline',
                active ? 'font-medium' : 'text-muted-foreground',
              )}
            >
              {label}
            </span>
            {index < labels.length - 1 && (
              <div className="mx-1 hidden h-px flex-1 bg-border sm:block" />
            )}
          </li>
        )
      })}
    </ol>
  )
}
