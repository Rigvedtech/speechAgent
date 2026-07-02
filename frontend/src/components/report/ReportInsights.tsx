import { Lightbulb, Target } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface ReportInsightsProps {
  develop: string[]
  improve: string[]
}

function InsightList({
  items,
  emptyLabel,
  accentClass,
}: {
  items: string[]
  emptyLabel: string
  accentClass: string
}) {
  if (!items.length) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>
  }

  return (
    <ol className="space-y-2.5">
      {items.map((item, index) => (
        <li key={`${index}-${item.slice(0, 24)}`} className="flex gap-3 text-sm leading-relaxed">
          <span
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold',
              accentClass,
            )}
          >
            {index + 1}
          </span>
          <span className="min-w-0 pt-0.5">{item}</span>
        </li>
      ))}
    </ol>
  )
}

export function ReportInsights({ develop, improve }: ReportInsightsProps) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border bg-muted/30 pb-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-warning/10 text-warning">
              <Target className="h-4 w-4" strokeWidth={1.5} />
            </span>
            <div>
              <CardTitle className="text-base">Growth areas</CardTitle>
              <p className="text-xs text-muted-foreground">
                Skills and topics to strengthen
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <InsightList
            items={develop}
            emptyLabel="No major growth areas noted."
            accentClass="bg-warning/10 text-warning"
          />
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border bg-muted/30 pb-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-foreground/5 text-foreground">
              <Lightbulb className="h-4 w-4" strokeWidth={1.5} />
            </span>
            <div>
              <CardTitle className="text-base">Recommended actions</CardTitle>
              <p className="text-xs text-muted-foreground">
                Practical steps for the candidate
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <InsightList
            items={improve}
            emptyLabel="No additional recommendations."
            accentClass="bg-muted text-foreground"
          />
        </CardContent>
      </Card>
    </div>
  )
}
