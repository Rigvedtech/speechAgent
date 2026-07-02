import { useState } from 'react'
import { ChevronDown, ChevronRight, MessageSquareText } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface TranscriptBlockProps {
  lines: string[]
}

export function TranscriptBlock({ lines }: TranscriptBlockProps) {
  const [open, setOpen] = useState(false)
  if (!lines.length) return null

  return (
    <Card>
      <CardHeader className="border-b border-border bg-muted/20 pb-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-foreground/5">
              <MessageSquareText className="h-4 w-4" strokeWidth={1.5} />
            </span>
            <div>
              <CardTitle className="text-base">Conversation transcript</CardTitle>
              <p className="text-xs text-muted-foreground">{lines.length} lines recorded</p>
            </div>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => setOpen((o) => !o)}>
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            {open ? 'Hide transcript' : 'View transcript'}
          </Button>
        </div>
      </CardHeader>
      {open && (
        <CardContent className="pt-4">
          <div className="max-h-[28rem] space-y-1 overflow-y-auto rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed">
            {lines.map((line, i) => (
              <div key={`${i}-${line.slice(0, 20)}`}>{line}</div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  )
}
