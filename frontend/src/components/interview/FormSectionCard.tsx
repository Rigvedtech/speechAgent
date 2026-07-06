import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface FormSectionCardProps {
  title: string
  description?: string
  children: ReactNode
  className?: string
  contentClassName?: string
}

export function FormSectionCard({
  title,
  description,
  children,
  className,
  contentClassName,
}: FormSectionCardProps) {
  return (
    <section
      className={cn(
        'select-none rounded-xl border border-border bg-card p-4 shadow-[0_1px_0_rgba(0,0,0,0.03)]',
        '[&_input]:select-text [&_textarea]:select-text',
        className,
      )}
    >
      <div className="mb-3 shrink-0">
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        {description ? (
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
        ) : null}
      </div>
      <div className={contentClassName}>{children}</div>
    </section>
  )
}
