import { cn } from '@/lib/utils'

interface JoinWizardStepsProps {
  step: number
  labels?: string[]
}

const DEFAULT_LABELS = ['Job', 'Candidate', 'Questions', 'Join']

export function JoinWizardSteps({ step, labels = DEFAULT_LABELS }: JoinWizardStepsProps) {
  const count = labels.length

  return (
    <nav aria-label="Interview setup progress" className="select-none">
      <div className="relative px-1">
        <div
          className="absolute top-4 h-px bg-border"
          style={{
            left: `${100 / count / 2}%`,
            right: `${100 / count / 2}%`,
          }}
          aria-hidden
        />
        <ol
          className="relative grid gap-0"
          style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}
        >
          {labels.map((label, index) => {
            const num = index + 1
            const active = num === step
            const done = num < step
            return (
              <li key={label} className="flex flex-col items-center gap-2">
                <span
                  className={cn(
                    'relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors',
                    active && 'bg-primary text-primary-foreground shadow-sm',
                    done && 'bg-foreground text-background',
                    !active && !done && 'border border-border bg-card text-muted-foreground',
                  )}
                >
                  {done ? '✓' : num}
                </span>
                <span
                  className={cn(
                    'w-full px-0.5 text-center text-[10px] leading-snug sm:text-[11px]',
                    active ? 'font-semibold text-foreground' : 'text-muted-foreground',
                  )}
                >
                  {label}
                </span>
              </li>
            )
          })}
        </ol>
      </div>
    </nav>
  )
}
