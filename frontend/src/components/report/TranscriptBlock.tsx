import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
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
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Conversation transcript</CardTitle>
          <Button type="button" variant="ghost" size="sm" onClick={() => setOpen((o) => !o)}>
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            {open ? 'Hide' : 'Show'}
          </Button>
        </div>
      </CardHeader>
      {open && (
        <CardContent>
          <div className="max-h-[32rem] space-y-1 overflow-y-auto rounded-md bg-muted/50 p-3 font-mono text-xs">
            {lines.map((line, i) => (
              <div key={`${i}-${line.slice(0, 20)}`}>{line}</div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  )
}
