import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

export interface KpiSplitMetric {
  label: string
  value: string
  to?: string
}

interface KpiCardProps {
  label: string
  value?: string
  hint?: string
  icon: LucideIcon
  iconClassName?: string
  className?: string
  to?: string
  /** When set, show two metrics side-by-side instead of a single value. */
  split?: [KpiSplitMetric, KpiSplitMetric]
}

export function KpiCard({
  label,
  value,
  hint,
  icon: Icon,
  iconClassName,
  className,
  to,
  split,
}: KpiCardProps) {
  const classes = cn(
    'surface-hover select-none rounded-lg border border-border bg-card p-5 hover:border-foreground/15',
    to && !split ? 'cursor-pointer' : 'cursor-default',
    className,
  )

  const header = (
    <div className="flex items-start justify-between gap-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
        {label}
      </p>
      <Icon
        className={cn('h-4 w-4 shrink-0', iconClassName ?? 'text-muted-foreground/60')}
        strokeWidth={1.25}
      />
    </div>
  )

  const content = split ? (
    <>
      {header}
      <div className="relative mt-3 flex items-center">
        {split.map((metric, index) => {
          const accentColor = index === 0 ? 'success' : 'primary'
          const body = (
            <div className="flex items-baseline gap-2.5">
              <div
                className={cn(
                  'h-9 w-0.5 shrink-0 rounded-full',
                  index === 0 ? 'bg-success/60' : 'bg-primary/60',
                )}
                aria-hidden
              />
              <div className="flex flex-col">
                <p className="text-3xl font-semibold tabular-nums leading-none tracking-tight">
                  {metric.value}
                </p>
                <p className="mt-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground/70">
                  {metric.label}
                </p>
              </div>
            </div>
          )
          const wrapClass = cn(
            'group relative flex min-w-0 flex-1 transition-all duration-200',
            index > 0 && 'pl-5',
            metric.to && 'cursor-pointer hover:translate-x-0.5',
          )
          if (metric.to) {
            return (
              <Link key={metric.label} to={metric.to} className={wrapClass}>
                {body}
              </Link>
            )
          }
          return (
            <div key={metric.label} className={wrapClass}>
              {body}
            </div>
          )
        })}
        <div className="absolute left-1/2 top-1/2 h-8 w-px -translate-x-1/2 -translate-y-1/2 bg-border/40" aria-hidden />
      </div>
      {hint ? <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p> : null}
    </>
  ) : (
    <>
      {header}
      <p className="mt-3 text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p> : null}
    </>
  )

  if (to && !split) {
    return (
      <Link to={to} className={classes}>
        {content}
      </Link>
    )
  }

  return <div className={classes}>{content}</div>
}
