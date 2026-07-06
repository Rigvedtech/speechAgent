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

export function splitFullName(full: string): { first: string; last: string } {
  const trimmed = full.trim()
  if (!trimmed) return { first: '', last: '' }
  const space = trimmed.indexOf(' ')
  if (space === -1) return { first: trimmed, last: '' }
  return { first: trimmed.slice(0, space), last: trimmed.slice(space + 1).trim() }
}

export function formatCandidateDisplayName(first: string, last?: string): string {
  const f = first.trim()
  const l = (last ?? '').trim()
  if (!f) return 'Candidate'
  return l ? `${f} ${l}` : f
}

export const joinFormSchema = z.object({
  meeting_url: z.string().url('Enter a valid meeting URL'),
  bot_name: z.string().optional(),
  candidate_first_name: z
    .string()
    .trim()
    .min(2, 'First name must be at least 2 characters')
    .max(50),
  candidate_last_name: z.string().trim().max(50),
  language_mode: z.enum(['english', 'hinglish']),
  position_name: z.string().trim().min(2, 'Position name must be at least 2 characters').max(120),
  jdText: z.string().trim().min(100, 'Job description must be at least 100 characters'),
  cvText: z.string().trim().min(50, 'Resume must be at least 50 characters'),
  greeting_message: z.string().optional(),
  questions: z.array(questionSchema).min(1, 'Add at least one question'),
})

export type JoinFormValues = z.infer<typeof joinFormSchema>

export const step1Fields = ['candidate_first_name', 'candidate_last_name', 'language_mode'] as const
export const step2Fields = ['position_name'] as const
export const step4Fields = ['meeting_url', 'bot_name'] as const

export function isStep1Ready(
  values: Pick<JoinFormValues, 'candidate_first_name'>,
  cvFile: File | null,
) {
  return values.candidate_first_name.trim().length >= 2 && cvFile !== null
}

export function isStep2Ready(values: Pick<JoinFormValues, 'position_name'>, jdFile: File | null) {
  return values.position_name.trim().length >= 2 && jdFile !== null
}

export function isStep1bReady(values: Pick<JoinFormValues, 'cvText'>) {
  return values.cvText.trim().length >= 50
}

export function isStep2bReady(values: Pick<JoinFormValues, 'jdText'>) {
  return values.jdText.trim().length >= 100
}

export function isStep3TextReady(values: Pick<JoinFormValues, 'jdText' | 'cvText'>) {
  if (values.jdText.trim().length < 100) return false
  if (values.cvText.trim().length < 50) return false
  return true
}

export function isStep3Ready(values: Pick<JoinFormValues, 'jdText' | 'cvText' | 'questions'>) {
  if (!isStep3TextReady(values)) return false
  return checkBankCoverage(values.questions).ok
}

export function isStep4Ready(meetingUrl: string) {
  return z.string().url().safeParse(meetingUrl.trim()).success
}

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
