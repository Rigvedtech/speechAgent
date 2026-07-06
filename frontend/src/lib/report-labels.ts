export const STOPPED_LABELS: Record<string, string> = {
  none: 'In progress',
  completed_all_questions: 'Completed all planned questions',
  low_recent_average: 'Ended early — rolling average below threshold',
  abuse: 'Ended — policy violation',
  manual: 'Ended manually',
}

export function verdictLabel(score: number): string {
  if (score >= 8) return 'Strong'
  if (score >= 6) return 'Adequate'
  return 'Needs work'
}

export function outcomeLabel(reason: string): string {
  return STOPPED_LABELS[reason] ?? reason.replace(/_/g, ' ')
}
