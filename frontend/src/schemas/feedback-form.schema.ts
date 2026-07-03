import { z } from 'zod'

export const feedbackFormSchema = z.object({
  overall_rating: z
    .number()
    .refine((v) => v >= 1 && v <= 5, { message: 'Please select a rating' }),
  clarity_rating: z
    .number()
    .refine((v) => v >= 1 && v <= 5, { message: 'Please select a rating' }),
  tech_issues: z.enum(['none', 'minor', 'major']),
  improve_text: z.string().trim().min(1, 'Tell us one thing to improve').max(500),
  would_repeat: z.enum(['yes', 'maybe', 'no']).optional(),
})

export type FeedbackFormValues = z.infer<typeof feedbackFormSchema>

export const TECH_ISSUE_LABELS: Record<FeedbackFormValues['tech_issues'], string> = {
  none: 'No issues',
  minor: 'Minor issues',
  major: 'Major issues',
}

export const WOULD_REPEAT_LABELS: Record<NonNullable<FeedbackFormValues['would_repeat']>, string> = {
  yes: 'Yes',
  maybe: 'Maybe',
  no: 'No',
}
