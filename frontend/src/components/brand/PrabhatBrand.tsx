import { cn } from '@/lib/utils'
import { PrabhatMark } from '@/components/brand/PrabhatMark'

interface PrabhatBrandProps {
  className?: string
  markClassName?: string
  /** When set, the PRABHAT trailing dot reflects API health (green/red). */
  serverOnline?: boolean
}

export function PrabhatBrand({
  className,
  markClassName,
  serverOnline,
}: PrabhatBrandProps) {
  const showServerStatus = typeof serverOnline === 'boolean'
  const statusLabel = serverOnline ? 'Server up' : 'Server down'

  return (
    <div className={cn('flex min-w-0 items-center gap-2.5', className)}>
      <PrabhatMark className={cn('h-4 w-auto shrink-0', markClassName)} />
      <span className="truncate text-xl font-semibold leading-none tracking-wide text-sidebar-foreground">
        PRABHAT
        <span
          className={cn(
            'select-none',
            showServerStatus
              ? serverOnline
                ? 'text-success'
                : 'text-destructive'
              : 'text-[#7c3aed] dark:text-[#a78bfa]',
          )}
          role={showServerStatus ? 'status' : undefined}
          aria-label={showServerStatus ? statusLabel : undefined}
          aria-hidden={showServerStatus ? undefined : true}
          title={showServerStatus ? statusLabel : undefined}
        >
          .
        </span>
      </span>
    </div>
  )
}
