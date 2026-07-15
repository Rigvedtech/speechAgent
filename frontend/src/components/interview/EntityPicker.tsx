import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

const NEW_VALUE = '__new__'

interface EntityPickerProps {
  label: string
  placeholder: string
  value: string | null
  options: { id: string; label: string; hint?: string }[]
  loading?: boolean
  disabled?: boolean
  onChange: (id: string | null) => void
  onClear?: () => void
  /** Optional right-side control (e.g. From ATS) */
  action?: ReactNode
  helperText?: string
}

export function EntityPicker({
  label,
  placeholder,
  value,
  options,
  loading,
  disabled,
  onChange,
  onClear,
  action,
  helperText = 'Choose a saved record, or create a new one below.',
}: EntityPickerProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-sm font-medium">{label}</Label>
        <div className="flex shrink-0 items-center gap-1">
          {value && onClear ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground"
              onClick={onClear}
            >
              Clear
            </Button>
          ) : null}
          {action}
        </div>
      </div>
      <Select
        value={value ?? NEW_VALUE}
        disabled={disabled || loading}
        onValueChange={(v) => onChange(v === NEW_VALUE ? null : v)}
      >
        <SelectTrigger className="h-10 bg-card">
          <SelectValue placeholder={loading ? 'Loading…' : placeholder} />
        </SelectTrigger>
        <SelectContent
          position="popper"
          className="z-[80] max-h-64 w-[var(--radix-select-trigger-width)]"
        >
          <SelectItem value={NEW_VALUE} className="text-muted-foreground">
            Create new…
          </SelectItem>
          {options.map((opt) => (
            <SelectItem key={opt.id} value={opt.id} className="py-2 pr-3">
              <span className="block max-w-full truncate">
                {opt.label}
                {opt.hint ? (
                  <span className="text-muted-foreground"> · {opt.hint}</span>
                ) : null}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {helperText ? (
        <p className={cn('text-xs text-muted-foreground')}>{helperText}</p>
      ) : null}
    </div>
  )
}
