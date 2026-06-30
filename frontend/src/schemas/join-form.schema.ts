import { z } from 'zod'

export const DIFFICULTY_PATTERN = [
  'Low',
  'Hard',
  'Intermediate',
  'Low',
  'Hard',
  'Intermediate',
  'Low',
  'Hard',
  'Intermediate',
  'Low',
] as const

export const REQUIRED_COUNTS = {
  Low: 4,
  Hard: 3,
  Intermediate: 3,
} as const

const questionSchema = z.object({
  id: z.string().min(1, 'ID is required'),
  difficulty: z.enum(['Low', 'Hard', 'Intermediate', 'low', 'hard', 'intermediate', 'easy', 'medium']),
  source: z.enum(['jd', 'resume', 'other', 'Job Description', 'Resume']),
  question: z.string().min(10, 'Question must be at least 10 characters'),
})

export const joinFormSchema = z.object({
  meeting_url: z.string().url('Enter a valid meeting URL'),
  bot_name: z.string().optional(),
  candidate_name: z.string().trim().min(2, 'Name must be at least 2 characters').max(100),
  language_mode: z.enum(['english', 'hinglish']),
  jdText: z.string().trim().min(100, 'Job description must be at least 100 characters'),
  cvText: z.string().trim().min(50, 'Resume must be at least 50 characters'),
  greeting_message: z.string().optional(),
  questions: z.array(questionSchema).min(1, 'Add at least one question'),
})

export type JoinFormValues = z.infer<typeof joinFormSchema>

export function normalizeDifficulty(d: string): 'Low' | 'Hard' | 'Intermediate' {
  const lower = d.toLowerCase()
  if (['low', 'easy', 'beginner'].includes(lower)) return 'Low'
  if (['hard', 'difficult', 'advanced'].includes(lower)) return 'Hard'
  return 'Intermediate'
}

export function normalizeSource(s: string): string {
  const lower = s.toLowerCase()
  if (lower === 'job description' || lower === 'jd') return 'jd'
  if (lower === 'resume' || lower === 'cv') return 'resume'
  return 'other'
}

export function checkBankCoverage(questions: JoinFormValues['questions']): {
  ok: boolean
  counts: Record<string, number>
  missing: string[]
} {
  const counts: Record<string, number> = { Low: 0, Hard: 0, Intermediate: 0 }
  for (const q of questions) {
    const diff = normalizeDifficulty(q.difficulty)
    counts[diff] = (counts[diff] ?? 0) + 1
  }
  const missing: string[] = []
  for (const [diff, required] of Object.entries(REQUIRED_COUNTS)) {
    if ((counts[diff] ?? 0) < required) {
      missing.push(`${diff}: need ${required}, have ${counts[diff] ?? 0}`)
    }
  }
  return { ok: missing.length === 0, counts, missing }
}

export function toApiQuestions(questions: JoinFormValues['questions']) {
  return questions.map((q) => ({
    id: q.id,
    difficulty: normalizeDifficulty(q.difficulty),
    source: normalizeSource(q.source),
    question: q.question.trim(),
  }))
}
