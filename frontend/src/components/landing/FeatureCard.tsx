import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export type FeatureAccent = 'blue' | 'violet' | 'amber' | 'emerald' | 'sky' | 'cyan'

const accentStyles: Record<
  FeatureAccent,
  { icon: string; box: string; card: string }
> = {
  blue: {
    icon: 'text-muted-foreground/60 transition-colors duration-200 group-hover:text-blue-600 dark:group-hover:text-blue-400',
    box: 'transition-[background-color,border-color] duration-200 group-hover:border-blue-500/30 group-hover:bg-blue-500/10 dark:group-hover:border-blue-400/35 dark:group-hover:bg-blue-500/15',
    card: 'hover:border-blue-500/20 dark:hover:border-blue-400/25',
  },
  violet: {
    icon: 'text-muted-foreground/60 transition-colors duration-200 group-hover:text-[#7c3aed] dark:group-hover:text-[#a78bfa]',
    box: 'transition-[background-color,border-color] duration-200 group-hover:border-[#7c3aed]/30 group-hover:bg-[#7c3aed]/10 dark:group-hover:border-[#a78bfa]/35 dark:group-hover:bg-[#7c3aed]/18',
    card: 'hover:border-[#7c3aed]/20 dark:hover:border-[#a78bfa]/25',
  },
  amber: {
    icon: 'text-muted-foreground/60 transition-colors duration-200 group-hover:text-amber-600 dark:group-hover:text-amber-400',
    box: 'transition-[background-color,border-color] duration-200 group-hover:border-amber-500/30 group-hover:bg-amber-500/10 dark:group-hover:border-amber-400/35 dark:group-hover:bg-amber-500/15',
    card: 'hover:border-amber-500/20 dark:hover:border-amber-400/25',
  },
  emerald: {
    icon: 'text-muted-foreground/60 transition-colors duration-200 group-hover:text-emerald-600 dark:group-hover:text-emerald-400',
    box: 'transition-[background-color,border-color] duration-200 group-hover:border-emerald-500/30 group-hover:bg-emerald-500/10 dark:group-hover:border-emerald-400/35 dark:group-hover:bg-emerald-500/15',
    card: 'hover:border-emerald-500/20 dark:hover:border-emerald-400/25',
  },
  sky: {
    icon: 'text-muted-foreground/60 transition-colors duration-200 group-hover:text-sky-600 dark:group-hover:text-sky-400',
    box: 'transition-[background-color,border-color] duration-200 group-hover:border-sky-500/30 group-hover:bg-sky-500/10 dark:group-hover:border-sky-400/35 dark:group-hover:bg-sky-500/15',
    card: 'hover:border-sky-500/20 dark:hover:border-sky-400/25',
  },
  cyan: {
    icon: 'text-muted-foreground/60 transition-colors duration-200 group-hover:text-cyan-600 dark:group-hover:text-cyan-400',
    box: 'transition-[background-color,border-color] duration-200 group-hover:border-cyan-500/30 group-hover:bg-cyan-500/10 dark:group-hover:border-cyan-400/35 dark:group-hover:bg-cyan-500/15',
    card: 'hover:border-cyan-500/20 dark:hover:border-cyan-400/25',
  },
}

interface FeatureCardProps {
  icon: LucideIcon
  title: string
  description: string
  accent: FeatureAccent
  className?: string
}

export function FeatureCard({
  icon: Icon,
  title,
  description,
  accent,
  className,
}: FeatureCardProps) {
  const styles = accentStyles[accent]

  return (
    <Card
      className={cn(
        'landing-card group flex h-full cursor-pointer flex-col border-border/80 bg-card transition-[background-color,border-color] duration-200 ease-out hover:bg-muted/25 dark:hover:bg-muted/35',
        styles.card,
        className,
      )}
    >
      <CardHeader className="pb-2">
        <div
          className={cn(
            'mb-3 flex h-9 w-9 items-center justify-center rounded-md border border-border bg-muted/50',
            styles.box,
          )}
        >
          <Icon className={cn('h-4 w-4', styles.icon)} strokeWidth={1.5} />
        </div>
        <CardTitle className="text-base font-semibold tracking-tight">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}
