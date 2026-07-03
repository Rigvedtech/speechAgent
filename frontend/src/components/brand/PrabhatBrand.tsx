import { cn } from '@/lib/utils'
import { PrabhatMark } from '@/components/brand/PrabhatMark'

interface PrabhatBrandProps {
  className?: string
  markClassName?: string
}

export function PrabhatBrand({ className, markClassName }: PrabhatBrandProps) {
  return (
    <div className={cn('flex min-w-0 items-center gap-2.5', className)}>
      <PrabhatMark className={cn('h-4 w-auto shrink-0', markClassName)} />
      <span className="truncate text-xl font-semibold leading-none tracking-wide text-sidebar-foreground">
        PRABHAT
        <span className="text-[#7c3aed] dark:text-[#a78bfa]" aria-hidden>
          .
        </span>
      </span>
    </div>
  )
}
