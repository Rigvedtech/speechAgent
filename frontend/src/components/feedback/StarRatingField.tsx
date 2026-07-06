import { Star } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'

interface StarRatingFieldProps {
  id: string
  label: string
  value: number
  onChange: (value: number) => void
  disabled?: boolean
  error?: string
}

export function StarRatingField({
  id,
  label,
  value,
  onChange,
  disabled,
  error,
}: StarRatingFieldProps) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id} className="text-sm font-medium">
        {label}
      </Label>
      <div
        id={id}
        role="radiogroup"
        aria-label={label}
        className="flex gap-1"
      >
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            disabled={disabled}
            role="radio"
            aria-checked={value === star}
            aria-label={`${star} star${star === 1 ? '' : 's'}`}
            onClick={() => onChange(star)}
            className={cn(
              'rounded-md p-1.5 transition-colors hover:bg-muted disabled:opacity-50',
              value >= star ? 'text-brand' : 'text-muted-foreground/40',
            )}
          >
            <Star
              className="h-7 w-7"
              strokeWidth={1.5}
              fill={value >= star ? 'currentColor' : 'none'}
            />
          </button>
        ))}
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  )
}
