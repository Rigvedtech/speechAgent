import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm, FormProvider } from 'react-hook-form'
import { useMutation } from '@tanstack/react-query'
import { Loader2, Sparkles } from 'lucide-react'
import { joinMeeting } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import {
  extractCvFromFile,
  extractJdFromFile,
  generateQuestionsFromText,
} from '@/lib/n8n'
import { upsertSession } from '@/lib/session-store'
import {
  clearInterviewDraft,
  loadInterviewDraft,
  loadInterviewDraftMeta,
  saveInterviewDraft,
  saveInterviewDraftMeta,
} from '@/lib/draft-store'
import { isTeamsLauncherUrl, MEETING_URL_HINT } from '@/lib/meeting-url'
import {
  checkBankCoverage,
  formatCandidateDisplayName,
  isStep1Ready,
  isStep1bReady,
  isStep2Ready,
  isStep2bReady,
  isStep3Ready,
  isStep4Ready,
  joinFormSchema,
  splitFullName,
  toApiQuestions,
  type JoinFormValues,
} from '@/schemas/join-form.schema'
import type { ApiErrorDetail } from '@/types/api'
import {
  asCvStructured,
  asJdStructured,
  type CvStructured,
  type JdStructured,
} from '@/types/extraction'
import { JoinWizardSteps } from '@/components/interview/JoinWizardSteps'
import { QuestionBankEditor } from '@/components/interview/QuestionBankEditor'
import { FormSectionCard } from '@/components/interview/FormSectionCard'
import { CompactFileUpload } from '@/components/interview/CompactFileUpload'
import { CvExtractionReview } from '@/components/interview/CvExtractionReview'
import { JdExtractionReview } from '@/components/interview/JdExtractionReview'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Alert } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const DEFAULT_BOT_NAME = 'Prabhat'

const defaultValues: JoinFormValues = {
  meeting_url: '',
  bot_name: DEFAULT_BOT_NAME,
  candidate_first_name: '',
  candidate_last_name: '',
  language_mode: 'english',
  position_name: '',
  jdText: '',
  cvText: '',
  greeting_message: '',
  questions: [
    {
      id: '1',
      difficulty: 'Low',
      source: 'jd',
      question: '',
    },
  ],
}

const WIZARD_LABELS = ['Candidate', 'Job', 'Questions', 'Join']
const TOTAL_STEPS = 6

function displayWizardStep(step: number): number {
  if (step <= 2) return 1
  if (step <= 4) return 2
  if (step === 5) return 3
  return 4
}

function resolveInitialStep(
  savedStep: number | undefined,
  meta: ReturnType<typeof loadInterviewDraftMeta>,
): number {
  if (!savedStep || savedStep < 1 || savedStep > TOTAL_STEPS) return 1
  if (savedStep >= 2 && !meta?.cvStructured && !meta?.cvFileName) return 1
  if (savedStep >= 4 && !meta?.jdStructured && !meta?.jdFileName) return 3
  return savedStep
}

export function NewInterviewPage() {
  const navigate = useNavigate()
  const savedDraft = loadInterviewDraft()
  const savedMeta = loadInterviewDraftMeta()

  const [step, setStep] = useState(() => resolveInitialStep(savedMeta?.wizardStep, savedMeta))
  const [error, setError] = useState<string | null>(null)
  const [jdFile, setJdFile] = useState<File | null>(null)
  const [cvFile, setCvFile] = useState<File | null>(null)
  const [cvStructured, setCvStructured] = useState<CvStructured | null>(
    savedMeta?.cvStructured ?? null,
  )
  const [jdStructured, setJdStructured] = useState<JdStructured | null>(
    savedMeta?.jdStructured ?? null,
  )
  const [questionsGenerated, setQuestionsGenerated] = useState(() => {
    if (savedMeta?.questionsGenerated) return true
    return (savedDraft?.questions ?? []).some((q) => q.question.trim().length >= 10)
  })
  const [duplicateDialog, setDuplicateDialog] = useState<{
    botId: string
    message: string
  } | null>(null)

  const form = useForm<JoinFormValues>({
    defaultValues: savedDraft ?? defaultValues,
    mode: 'onChange',
  })

  const values = form.watch()

  useEffect(() => {
    const sub = form.watch((draftValues) => {
      saveInterviewDraft(draftValues as JoinFormValues)
    })
    return () => sub.unsubscribe()
  }, [form])

  useEffect(() => {
    if (step === 6) {
      form.setValue('bot_name', DEFAULT_BOT_NAME)
    }
  }, [step, form])

  useEffect(() => {
    saveInterviewDraftMeta({
      cvFileName: cvFile?.name ?? null,
      jdFileName: jdFile?.name ?? null,
      wizardStep: step,
      cvStructured,
      jdStructured,
      questionsGenerated,
    })
  }, [cvFile, jdFile, step, cvStructured, jdStructured, questionsGenerated])

  const step1Ready = isStep1Ready(values, cvFile)
  const step1bReady = isStep1bReady(values)
  const step2Ready = isStep2Ready(values, jdFile)
  const step2bReady = isStep2bReady(values)
  const step3Ready = isStep3Ready(values)
  const step4Ready = isStep4Ready(values.meeting_url ?? '')

  const proceedEnabled = useMemo(() => {
    if (step === 1) return step1Ready
    if (step === 2) return step1bReady
    if (step === 3) return step2Ready
    if (step === 4) return step2bReady
    if (step === 5) return questionsGenerated ? step3Ready : true
    return step4Ready
  }, [step, step1Ready, step1bReady, step2Ready, step2bReady, step3Ready, step4Ready, questionsGenerated])

  const questionCount = values.questions?.filter((q) => q.question.trim()).length ?? 0

  const handleJoinSuccess = (data: Awaited<ReturnType<typeof joinMeeting>>) => {
    clearInterviewDraft()
    upsertSession({
      botId: data.bot_id,
      candidateName: formatCandidateDisplayName(
        form.getValues('candidate_first_name'),
        form.getValues('candidate_last_name'),
      ),
      meetingUrl: data.meeting_url,
      languageMode: data.language_mode ?? form.getValues('language_mode'),
      createdAt: new Date().toISOString(),
    })
    navigate(`/interviews/${data.bot_id}`, {
      state: { plannedQuestions: data.planned_questions },
    })
  }

  const joinMutation = useMutation({
    mutationFn: joinMeeting,
    onSuccess: handleJoinSuccess,
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as ApiErrorDetail | undefined
        if (detail?.bot_id) {
          setDuplicateDialog({
            botId: detail.bot_id,
            message: formatApiError(err.message, err.detail),
          })
          return
        }
      }
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Failed to send bot to meeting')
      }
    },
  })

  const extractCvMutation = useMutation({
    mutationFn: () => {
      if (!cvFile) throw new Error('Upload a resume file')
      return extractCvFromFile(cvFile)
    },
  })

  const extractJdMutation = useMutation({
    mutationFn: () => {
      if (!jdFile) throw new Error('Upload a job description file')
      return extractJdFromFile(jdFile)
    },
  })

  const questionsMutation = useMutation({
    mutationFn: () =>
      generateQuestionsFromText(form.getValues('jdText'), form.getValues('cvText'), {
        candidateName: form.getValues('candidate_first_name'),
        languageMode: form.getValues('language_mode'),
      }),
  })

  const applyCvResult = (result: Awaited<ReturnType<typeof extractCvFromFile>>) => {
    if (result.cvText) {
      form.setValue('cvText', result.cvText, { shouldValidate: true })
    }
    const structured = asCvStructured(result.cvStructured) ?? {
      name: result.candidateName,
      raw_text: result.cvText,
    }
    setCvStructured(structured)
    if (result.candidateName && !form.getValues('candidate_first_name').trim()) {
      const { first, last } = splitFullName(result.candidateName)
      form.setValue('candidate_first_name', first, { shouldValidate: true })
      if (last) {
        form.setValue('candidate_last_name', last, { shouldValidate: true })
      }
    }
  }

  const applyJdResult = (result: Awaited<ReturnType<typeof extractJdFromFile>>) => {
    if (result.jdText) {
      form.setValue('jdText', result.jdText, { shouldValidate: true })
    }
    setJdStructured(asJdStructured(result.jdStructured) ?? { jd_summary: result.jdText })
  }

  const applyQuestionsResult = (
    result: Awaited<ReturnType<typeof generateQuestionsFromText>>,
  ) => {
    if (result.questions?.length) {
      form.setValue('questions', result.questions, { shouldValidate: true })
      setQuestionsGenerated(true)
      return true
    }
    setError('n8n responded but no questions were found. Check the workflow output.')
    return false
  }

  const resetQuestionsBank = () => {
    form.setValue('questions', defaultValues.questions, { shouldValidate: true })
    setQuestionsGenerated(false)
  }

  const submitJoin = (replaceExisting = false) => {
    const parsed = joinFormSchema.safeParse(form.getValues())
    if (!parsed.success) {
      const first = parsed.error.issues[0]
      setError(first?.message ?? 'Please complete all required fields')
      if (first?.path.includes('questions') || first?.path.includes('jdText') || first?.path.includes('cvText')) {
        setStep(5)
      } else if (first?.path.includes('meeting_url')) {
        setStep(6)
      }
      return
    }

    const data = parsed.data
    setError(null)
    setDuplicateDialog(null)

    const coverage = checkBankCoverage(data.questions)
    if (!coverage.ok) {
      setError(`Question bank incomplete: ${coverage.missing.join('; ')}`)
      setStep(5)
      return
    }

    joinMutation.mutate({
      meeting_url: data.meeting_url.trim(),
      bot_name: DEFAULT_BOT_NAME,
      candidate_name: data.candidate_first_name.trim(),
      jdText: data.jdText.trim(),
      cvText: data.cvText.trim(),
      questions: toApiQuestions(data.questions),
      language_mode: data.language_mode,
      greeting_message: data.greeting_message?.trim() || undefined,
      replace_existing: replaceExisting,
    })
  }

  const prevStep = () => {
    setError(null)
    if (step === 2) setStep(1)
    else if (step === 3) setStep(2)
    else if (step === 4) setStep(3)
    else if (step === 5) {
      resetQuestionsBank()
      setStep(4)
    } else if (step === 6) setStep(5)
  }

  const nextStep = async () => {
    setError(null)

    if (step === 1) {
      const ok = await form.trigger(['candidate_first_name', 'candidate_last_name', 'language_mode'])
      if (!ok || !step1Ready || !cvFile) return
      try {
        const result = await extractCvMutation.mutateAsync()
        applyCvResult(result)
        setStep(2)
      } catch (err) {
        if (err instanceof ApiError) {
          setError(formatApiError(err.message, err.detail))
        } else {
          setError(err instanceof Error ? err.message : 'Resume extraction failed')
        }
      }
      return
    }

    if (step === 2) {
      if (!step1bReady) {
        setError('Review and edit the resume text before continuing.')
        return
      }
      setStep(3)
      return
    }

    if (step === 3) {
      const ok = await form.trigger(['position_name'])
      if (!ok || !step2Ready || !jdFile) return
      try {
        const result = await extractJdMutation.mutateAsync()
        applyJdResult(result)
        setStep(4)
      } catch (err) {
        if (err instanceof ApiError) {
          setError(formatApiError(err.message, err.detail))
        } else {
          setError(err instanceof Error ? err.message : 'Job description extraction failed')
        }
      }
      return
    }

    if (step === 4) {
      if (!step2bReady) {
        setError('Review and edit the job description text before continuing.')
        return
      }
      resetQuestionsBank()
      setStep(5)
      return
    }

    if (step === 5) {
      if (!questionsGenerated) {
        try {
          const result = await questionsMutation.mutateAsync()
          applyQuestionsResult(result)
        } catch (err) {
          if (err instanceof ApiError) {
            setError(formatApiError(err.message, err.detail))
          } else {
            setError(err instanceof Error ? err.message : 'Question generation failed')
          }
        }
        return
      }

      if (!step3Ready) {
        const coverage = checkBankCoverage(form.getValues('questions'))
        if (!coverage.ok) {
          setError(`Question bank incomplete: ${coverage.missing.join('; ')}`)
        } else {
          setError('Complete all question fields before continuing.')
        }
        return
      }

      setStep(6)
    }
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (step === TOTAL_STEPS) {
      submitJoin(false)
    }
  }

  const wizardBusy =
    extractCvMutation.isPending || extractJdMutation.isPending || questionsMutation.isPending

  const proceedLabel = useMemo(() => {
    if (step === 1 && extractCvMutation.isPending) return 'Extracting resume…'
    if (step === 3 && extractJdMutation.isPending) return 'Extracting job description…'
    if (step === 5 && questionsMutation.isPending) return 'Generating questions…'
    if (step === TOTAL_STEPS) {
      return joinMutation.isPending ? 'Sending bot…' : 'Send bot to meeting'
    }
    if (step === 1) return 'Extract & continue'
    if (step === 2) return 'Continue to job'
    if (step === 3) return 'Extract & continue'
    if (step === 4) return 'Continue to questions'
    if (step === 5) return questionsGenerated ? 'Continue to join' : 'Generate questions'
    return 'Continue'
  }, [
    step,
    questionsGenerated,
    extractCvMutation.isPending,
    extractJdMutation.isPending,
    questionsMutation.isPending,
    joinMutation.isPending,
  ])

  const cvReviewData = cvStructured ?? { raw_text: values.cvText }
  const jdReviewData = jdStructured ?? { jd_summary: values.jdText }

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl select-none flex-col px-1 sm:px-0">
      <div className="mb-3 shrink-0 rounded-xl border border-border bg-card/95 px-3 py-3 shadow-sm backdrop-blur-sm sm:px-4">
        <JoinWizardSteps step={displayWizardStep(step)} labels={WIZARD_LABELS} />
      </div>

      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden border-border shadow-sm">
        <CardContent className="flex min-h-0 flex-1 flex-col p-4 sm:p-5">
          {error && (
            <Alert className="mb-4 shrink-0 border-destructive/30 bg-destructive/5 text-destructive">
              {error}
            </Alert>
          )}

          <FormProvider {...form}>
            <form onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col">
              <div
                className={cn(
                  'min-h-0 flex-1',
                  step === 5 && questionsGenerated
                    ? 'flex flex-col overflow-hidden'
                    : 'overflow-y-auto',
                )}
              >
              {step === 1 && (
                <FormSectionCard
                  title="Candidate detail"
                  description="Who is being interviewed and which language the bot should use."
                >
                  <div className="space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <Label htmlFor="candidate_first_name">First name</Label>
                        <Input
                          id="candidate_first_name"
                          className="mt-1.5 select-text"
                          placeholder="e.g. Rakesh"
                          {...form.register('candidate_first_name')}
                        />
                        {form.formState.errors.candidate_first_name && (
                          <p className="mt-1 text-xs text-destructive">
                            {form.formState.errors.candidate_first_name.message}
                          </p>
                        )}
                      </div>
                      <div>
                        <Label htmlFor="candidate_last_name">Last name</Label>
                        <Input
                          id="candidate_last_name"
                          className="mt-1.5 select-text"
                          placeholder="e.g. Sharma"
                          {...form.register('candidate_last_name')}
                        />
                        {form.formState.errors.candidate_last_name && (
                          <p className="mt-1 text-xs text-destructive">
                            {form.formState.errors.candidate_last_name.message}
                          </p>
                        )}
                      </div>
                    </div>

                    <div>
                      <Label>Interview language</Label>
                      <RadioGroup
                        value={values.language_mode}
                        onValueChange={(v) =>
                          form.setValue('language_mode', v as 'english' | 'hinglish')
                        }
                        className="mt-3 flex gap-3"
                      >
                        {(
                          [
                            { value: 'english', label: 'English' },
                            { value: 'hinglish', label: 'Hinglish' },
                          ] as const
                        ).map(({ value, label }) => (
                          <label
                            key={value}
                            className={cn(
                              'flex flex-1 cursor-pointer items-center justify-center rounded-lg border px-4 py-3 text-sm transition-colors',
                              values.language_mode === value
                                ? 'border-foreground bg-foreground text-background'
                                : 'border-border bg-card hover:bg-muted/50',
                            )}
                          >
                            <RadioGroupItem value={value} id={`lang-${value}`} className="sr-only" />
                            {label}
                          </label>
                        ))}
                      </RadioGroup>
                    </div>

                    <CompactFileUpload
                      label="Candidate resume"
                      file={cvFile}
                      onFileSelect={setCvFile}
                      disabled={wizardBusy}
                      error={!cvFile && form.formState.isSubmitted ? 'Resume file is required' : undefined}
                    />
                    {savedMeta?.cvFileName && !cvFile ? (
                      <p className="text-xs text-muted-foreground">
                        Previously uploaded: {savedMeta.cvFileName} — re-upload to continue after
                        refresh.
                      </p>
                    ) : null}
                  </div>
                </FormSectionCard>
              )}

              {step === 2 && (
                <FormSectionCard
                  title="Review extracted resume"
                  description="Structured profile from your upload. Edit the resume text at the bottom before continuing."
                >
                  <CvExtractionReview
                    structured={cvReviewData}
                    cvText={values.cvText}
                    onCvTextChange={(text) =>
                      form.setValue('cvText', text, { shouldValidate: true })
                    }
                  />
                </FormSectionCard>
              )}

              {step === 3 && (
                <FormSectionCard
                  title="Job description"
                  description="Upload the JD and name the role. We will extract details on continue."
                >
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="position_name">Position name</Label>
                      <Input
                        id="position_name"
                        className="mt-1.5 select-text"
                        placeholder="e.g. Application Support Engineer"
                        {...form.register('position_name')}
                      />
                      {form.formState.errors.position_name && (
                        <p className="mt-1 text-xs text-destructive">
                          {form.formState.errors.position_name.message}
                        </p>
                      )}
                    </div>

                    <CompactFileUpload
                      label="Job description document"
                      file={jdFile}
                      onFileSelect={setJdFile}
                      disabled={wizardBusy}
                    />
                    {savedMeta?.jdFileName && !jdFile ? (
                      <p className="text-xs text-muted-foreground">
                        Previously uploaded: {savedMeta.jdFileName} — re-upload to extract again.
                      </p>
                    ) : null}
                  </div>
                </FormSectionCard>
              )}

              {step === 4 && (
                <FormSectionCard
                  title="Review extracted job description"
                  description="Structured role details from your upload. Edit the job text at the bottom before continuing."
                >
                  <JdExtractionReview
                    structured={jdReviewData}
                    jdText={values.jdText}
                    onJdTextChange={(text) =>
                      form.setValue('jdText', text, { shouldValidate: true })
                    }
                  />
                </FormSectionCard>
              )}

              {step === 5 && (
                <FormSectionCard
                  title="Interview questions"
                  description={
                    questionsGenerated
                      ? undefined
                      : 'Generate a question bank from the reviewed resume and job description.'
                  }
                  className={
                    questionsGenerated
                      ? 'flex h-full min-h-0 flex-col overflow-hidden border-0 p-0 shadow-none'
                      : undefined
                  }
                  contentClassName={
                    questionsGenerated ? 'flex min-h-0 flex-1 flex-col overflow-hidden' : undefined
                  }
                >
                  {questionsGenerated ? (
                    <QuestionBankEditor fillHeight />
                  ) : (
                    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-6 py-10 text-center">
                      <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-full border border-border bg-background">
                        <Sparkles className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
                      </span>
                      <p className="text-sm font-medium">Ready to generate questions</p>
                      <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
                        n8n will create ~15 questions from the resume and job description you
                        reviewed. You can edit them before continuing.
                      </p>
                    </div>
                  )}
                </FormSectionCard>
              )}

              {step === 6 && (
                <div className="space-y-5">
                  <Alert className="border-border bg-muted/30 py-2.5">
                    <p className="text-xs">
                      <span className="font-medium">
                        {formatCandidateDisplayName(
                          values.candidate_first_name,
                          values.candidate_last_name,
                        )}
                      </span>
                      {' · '}
                      {values.position_name || 'Role'}
                      {' · '}
                      {values.language_mode}
                      {' · '}
                      {questionCount} questions ready
                    </p>
                    <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                      Sending the bot to the meeting is the point of no return. You can leave from
                      the live page if setup fails.
                    </p>
                  </Alert>

                  <FormSectionCard
                    title="Join meeting"
                    description="Paste the Teams, Zoom, or Meet link. The bot waits in the lobby until you start."
                  >
                    <div className="space-y-4">
                      <div>
                        <Label htmlFor="meeting_url">Meeting URL</Label>
                        <Input
                          id="meeting_url"
                          className="mt-1.5 select-text"
                          placeholder="https://teams.microsoft.com/..."
                          {...form.register('meeting_url')}
                        />
                        {form.formState.errors.meeting_url && (
                          <p className="mt-1 text-xs text-destructive">
                            {form.formState.errors.meeting_url.message}
                          </p>
                        )}
                        {isTeamsLauncherUrl(values.meeting_url ?? '') && (
                          <p className="mt-1 text-xs text-muted-foreground">{MEETING_URL_HINT}</p>
                        )}
                      </div>
                      <div>
                        <Label htmlFor="bot_name">Bot display name</Label>
                        <Input
                          id="bot_name"
                          readOnly
                          aria-readonly="true"
                          className="mt-1.5 cursor-not-allowed bg-muted/40 text-foreground"
                          {...form.register('bot_name')}
                        />
                  
                      </div>
                      <div>
                        <Label htmlFor="greeting_message">Custom greeting (optional)</Label>
                        <Textarea
                          id="greeting_message"
                          className="mt-1.5 min-h-[80px] select-text"
                          placeholder="Optional opening line for the bot. Leave blank to use the default intro."
                          {...form.register('greeting_message')}
                        />
                      </div>
                    </div>
                  </FormSectionCard>
                </div>
              )}

              </div>

              <div className="-mx-4 mt-4 flex shrink-0 items-center justify-between border-t border-border bg-card px-4 py-3 sm:-mx-5 sm:px-5">
                <Button
                  type="button"
                  variant="outline"
                  onClick={prevStep}
                  disabled={step === 1 || joinMutation.isPending || wizardBusy}
                >
                  Back
                </Button>
                {step < TOTAL_STEPS ? (
                  <Button
                    type="button"
                    onClick={nextStep}
                    disabled={!proceedEnabled || wizardBusy}
                  >
                    {wizardBusy && (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    )}
                    {proceedLabel}
                  </Button>
                ) : (
                  <Button type="submit" disabled={!proceedEnabled || joinMutation.isPending}>
                    {joinMutation.isPending && (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    )}
                    {proceedLabel}
                  </Button>
                )}
              </div>
            </form>
          </FormProvider>
        </CardContent>
      </Card>

      <Dialog
        open={duplicateDialog !== null}
        onOpenChange={(open) => !open && setDuplicateDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Interview already in progress</DialogTitle>
            <DialogDescription>
              {duplicateDialog?.message ??
                'A bot is already registered for this meeting URL.'}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              onClick={() => {
                if (duplicateDialog) {
                  navigate(`/interviews/${duplicateDialog.botId}`)
                }
                setDuplicateDialog(null)
              }}
            >
              Continue existing
            </Button>
            <Button
              variant="destructive"
              disabled={joinMutation.isPending}
              onClick={() => submitJoin(true)}
            >
              {joinMutation.isPending ? 'Replacing…' : 'Replace and start fresh'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
