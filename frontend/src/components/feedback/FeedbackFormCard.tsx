import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { CheckCircle2, Loader2 } from 'lucide-react'
import {
  feedbackFormSchema,
  TECH_ISSUE_LABELS,
  WOULD_REPEAT_LABELS,
  type FeedbackFormValues,
} from '@/schemas/feedback-form.schema'
import { StarRatingField } from '@/components/feedback/StarRatingField'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Alert } from '@/components/ui/alert'

interface FeedbackFormCardProps {
  candidateName?: string
  submitting?: boolean
  submitError?: string | null
  onSubmit: (values: FeedbackFormValues) => void | Promise<void>
}

export function FeedbackFormCard({
  candidateName,
  submitting = false,
  submitError = null,
  onSubmit,
}: FeedbackFormCardProps) {
  const form = useForm<FeedbackFormValues>({
    resolver: zodResolver(feedbackFormSchema),
    mode: 'onChange',
    defaultValues: {
      overall_rating: 0,
      clarity_rating: 0,
      tech_issues: 'none',
      improve_text: '',
      would_repeat: undefined,
    },
  })

  const errors = form.formState.errors

  return (
    <Card className="w-full border-border shadow-sm">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-xl">
            {candidateName ? `Feedback — ${candidateName}` : 'Interview feedback'}
          </CardTitle>
        </div>
        <CardDescription className="text-sm leading-relaxed">
          Quick review — about one minute. Your answers help us improve the AI interview
          experience.
        </CardDescription>
      </CardHeader>

      <CardContent className="pb-8">
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
          <Controller
            name="overall_rating"
            control={form.control}
            render={({ field }) => (
              <StarRatingField
                id="overall_rating"
                label="Overall interview experience"
                value={field.value}
                onChange={field.onChange}
                disabled={submitting}
                error={errors.overall_rating?.message}
              />
            )}
          />

          <Controller
            name="clarity_rating"
            control={form.control}
            render={({ field }) => (
              <StarRatingField
                id="clarity_rating"
                label="Clarity of AI interviewer (speech & questions)"
                value={field.value}
                onChange={field.onChange}
                disabled={submitting}
                error={errors.clarity_rating?.message}
              />
            )}
          />

          <div className="space-y-2">
            <Label>Any audio or connection issues?</Label>
            <Controller
              name="tech_issues"
              control={form.control}
              render={({ field }) => (
                <RadioGroup
                  value={field.value}
                  onValueChange={field.onChange}
                  className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-4"
                  disabled={submitting}
                >
                  {(Object.keys(TECH_ISSUE_LABELS) as FeedbackFormValues['tech_issues'][]).map(
                    (key) => (
                      <div key={key} className="flex items-center gap-2">
                        <RadioGroupItem value={key} id={`tech-${key}`} />
                        <Label htmlFor={`tech-${key}`} className="cursor-pointer font-normal">
                          {TECH_ISSUE_LABELS[key]}
                        </Label>
                      </div>
                    ),
                  )}
                </RadioGroup>
              )}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="improve_text">One thing we should improve</Label>
            <Textarea
              id="improve_text"
              placeholder="e.g. clearer questions, faster bot responses…"
              rows={3}
              maxLength={500}
              disabled={submitting}
              {...form.register('improve_text')}
            />
            {errors.improve_text ? (
              <p className="text-xs text-destructive">{errors.improve_text.message}</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                {form.watch('improve_text').length}/500
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label>Would you do another AI interview like this? (optional)</Label>
            <Controller
              name="would_repeat"
              control={form.control}
              render={({ field }) => (
                <RadioGroup
                  value={field.value ?? ''}
                  onValueChange={(v) =>
                    field.onChange(v === '' ? undefined : (v as FeedbackFormValues['would_repeat']))
                  }
                  className="flex flex-wrap gap-4"
                  disabled={submitting}
                >
                  {(Object.keys(WOULD_REPEAT_LABELS) as NonNullable<
                    FeedbackFormValues['would_repeat']
                  >[]).map((key) => (
                    <div key={key} className="flex items-center gap-2">
                      <RadioGroupItem value={key} id={`repeat-${key}`} />
                      <Label htmlFor={`repeat-${key}`} className="cursor-pointer font-normal">
                        {WOULD_REPEAT_LABELS[key]}
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
              )}
            />
          </div>

          {submitError ? (
            <Alert className="border-destructive/30 bg-destructive/5 text-sm">{submitError}</Alert>
          ) : null}

          <Button type="submit" className="w-full" disabled={submitting || !form.formState.isValid}>
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Submitting…
              </>
            ) : (
              'Submit feedback'
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

export function FeedbackThankYouCard({ candidateName }: { candidateName?: string }) {
  return (
    <Card className="w-full border-border shadow-sm">
      <CardHeader className="text-center">
        <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-success/10 text-success">
          <CheckCircle2 className="h-6 w-6" strokeWidth={1.5} />
        </div>
        <CardTitle>Thank you{candidateName ? `, ${candidateName}` : ''}</CardTitle>
        <CardDescription>
          Your feedback for this interview has been recorded. We appreciate your time.
        </CardDescription>
      </CardHeader>
    </Card>
  )
}
