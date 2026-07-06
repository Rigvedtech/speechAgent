import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import type { PlannedQuestion } from '@/types/api'

type RowState = 'upcoming' | 'current' | 'answered'

function rowState(
  slot: number,
  currentSlot?: number,
  questionsScored?: number,
): RowState {
  if (questionsScored != null && slot <= questionsScored) return 'answered'
  if (currentSlot != null && slot === currentSlot) return 'current'
  if (currentSlot != null && slot < currentSlot) return 'answered'
  return 'upcoming'
}

interface QuestionPlanListProps {
  questions: PlannedQuestion[]
  currentQuestionSlot?: number
  questionsScored?: number
  languageMode?: string
  localizationStatus?: string
  fillHeight?: boolean
}

export function QuestionPlanList({
  questions,
  currentQuestionSlot,
  questionsScored,
  languageMode,
  localizationStatus,
  fillHeight = false,
}: QuestionPlanListProps) {
  const showSpoken =
    languageMode === 'hinglish' && localizationStatus === 'ready'

  if (!questions.length) {
    return (
      <p className="text-sm text-muted-foreground">No planned questions yet.</p>
    )
  }

  return (
    <div
      className={cn(
        'flex flex-col gap-0 overflow-y-auto rounded-lg border border-border bg-card',
        fillHeight ? 'min-h-0 flex-1' : 'max-h-[calc(100vh-12rem)]',
      )}
    >
      {questions.map((q) => {
        const state = rowState(q.slot, currentQuestionSlot, questionsScored)
        const displayText = showSpoken ? q.spoken_question || q.question : q.question

        return (
          <div
            key={`${q.id}-${q.slot}`}
            className={cn(
              'border-b border-border px-4 py-3 last:border-b-0',
              state === 'current' && 'border-l-[3px] border-l-primary bg-[#f0fdf4]',
              state === 'answered' && 'opacity-70',
            )}
          >
            <div className="mb-1 flex items-center gap-2">
              <span className="text-xs font-medium text-muted-foreground">Q{q.slot}</span>
              <Badge variant="outline">{q.difficulty}</Badge>
              <Badge variant="secondary">{q.source}</Badge>
              {state === 'answered' && <Check className="ml-auto h-4 w-4 text-success" />}
              {state === 'current' && (
                <Badge variant="success" className="ml-auto">
                  Current
                </Badge>
              )}
              {languageMode === 'hinglish' && localizationStatus === 'pending' && (
                <Badge variant="warning" className="ml-auto">
                  Translating…
                </Badge>
              )}
            </div>
            <p className="text-sm leading-relaxed">{displayText}</p>
            {showSpoken && q.spoken_question && q.spoken_question !== q.question && (
              <p className="mt-1 text-xs text-muted-foreground">EN: {q.question}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
