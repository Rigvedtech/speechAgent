import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

interface KpiCardProps {
  label: string
  value: string
  hint?: string
  icon: LucideIcon
  iconClassName?: string
  className?: string
  to?: string
}

export function KpiCard({
  label,
  value,
  hint,
  icon: Icon,
  iconClassName,
  className,
  to,
}: KpiCardProps) {
  const classes = cn(
    'surface-hover select-none rounded-lg border border-border bg-card p-5 hover:border-foreground/15',
    to ? 'cursor-pointer' : 'cursor-default',
    className,
  )

  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          {label}
        </p>
        <Icon
          className={cn('h-4 w-4 shrink-0', iconClassName ?? 'text-muted-foreground/60')}
          strokeWidth={1.25}
        />
      </div>
      <p className="mt-3 text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p> : null}
    </>
  )

  if (to) {
    return (
      <Link to={to} className={classes}>
        {content}
      </Link>
    )
  }

  return <div className={classes}>{content}</div>
}
