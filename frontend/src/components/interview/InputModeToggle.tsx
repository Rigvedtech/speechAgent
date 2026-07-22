import { FileUp, Keyboard } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { DocumentInputMode } from '@/schemas/join-form.schema'

export type { DocumentInputMode }

interface InputModeToggleProps {
  value: DocumentInputMode
  onChange: (mode: DocumentInputMode) => void
  disabled?: boolean
  uploadLabel?: string
  manualLabel?: string
  className?: string
}

export function InputModeToggle({
  value,
  onChange,
  disabled,
  uploadLabel = 'Upload file',
  manualLabel = 'Enter manually',
  className,
}: InputModeToggleProps) {
  const options = [
    { value: 'upload' as const, label: uploadLabel, icon: FileUp },
    { value: 'manual' as const, label: manualLabel, icon: Keyboard },
  ]

  return (
    <div
      role="group"
      aria-label="Document input mode"
      className={cn('grid grid-cols-2 gap-2', className)}
    >
      {options.map(({ value: option, label, icon: Icon }) => {
        const selected = value === option
        return (
          <button
            key={option}
            type="button"
            disabled={disabled}
            aria-pressed={selected}
            onClick={() => onChange(option)}
            className={cn(
              'flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors',
              selected
                ? 'border-foreground bg-foreground text-background'
                : 'border-border bg-card text-foreground hover:bg-muted/50',
              disabled && 'pointer-events-none opacity-50',
            )}
          >
            <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
            <span className="font-medium">{label}</span>
          </button>
        )
      })}
    </div>
  )
}
