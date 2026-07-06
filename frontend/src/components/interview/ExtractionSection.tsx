import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

interface ExtractionSectionProps {
  title: string
  count?: number
  defaultOpen?: boolean
  children: ReactNode
  className?: string
}

export function ExtractionSection({
  title,
  count,
  defaultOpen = false,
  children,
  className,
}: ExtractionSectionProps) {
  return (
    <Collapsible defaultOpen={defaultOpen} className={cn('rounded-lg border border-border bg-muted/20', className)}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="group flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sm font-medium hover:bg-muted/40"
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate">{title}</span>
            {count !== undefined && count > 0 ? (
              <span className="shrink-0 rounded-full bg-background px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                {count}
              </span>
            ) : null}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t border-border px-3 pb-3 pt-2">{children}</CollapsibleContent>
    </Collapsible>
  )
}

interface SkillGroupProps {
  label: string
  items?: string[]
}

export function SkillGroup({ label, items }: SkillGroupProps) {
  if (!items?.length) return null
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={`${label}-${item}`}
            className="inline-flex max-w-full rounded-md border border-border bg-background px-2 py-0.5 text-xs text-foreground"
          >
            <span className="truncate">{item}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
