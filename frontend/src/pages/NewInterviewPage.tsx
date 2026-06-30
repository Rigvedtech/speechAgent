import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm, FormProvider } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { joinMeeting } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { extractJdCvFromFiles } from '@/lib/n8n'
import { upsertSession } from '@/lib/session-store'
import {
  clearInterviewDraft,
  loadInterviewDraft,
  saveInterviewDraft,
} from '@/lib/draft-store'
import { isTeamsLauncherUrl, MEETING_URL_HINT } from '@/lib/meeting-url'
import {
  joinFormSchema,
  checkBankCoverage,
  toApiQuestions,
  type JoinFormValues,
} from '@/schemas/join-form.schema'
import type { ApiErrorDetail } from '@/types/api'
import { JoinWizardSteps } from '@/components/interview/JoinWizardSteps'
import { QuestionBankEditor } from '@/components/interview/QuestionBankEditor'
import { DocumentUploadField } from '@/components/interview/DocumentUploadField'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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

const defaultValues: JoinFormValues = {
  meeting_url: '',
  bot_name: '',
  candidate_name: '',
  language_mode: 'english',
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

const WIZARD_LABELS = ['Prepare', 'Join meeting']

export function NewInterviewPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [extractNotice, setExtractNotice] = useState<string | null>(null)
  const [jdFile, setJdFile] = useState<File | null>(null)
  const [cvFile, setCvFile] = useState<File | null>(null)
  const [duplicateDialog, setDuplicateDialog] = useState<{
    botId: string
    message: string
  } | null>(null)

  const savedDraft = loadInterviewDraft()
  const form = useForm<JoinFormValues>({
    resolver: zodResolver(joinFormSchema),
    defaultValues: savedDraft ?? defaultValues,
    mode: 'onBlur',
  })

  useEffect(() => {
    const sub = form.watch((values) => {
      saveInterviewDraft(values as JoinFormValues)
    })
    return () => sub.unsubscribe()
  }, [form])

  const handleJoinSuccess = (data: Awaited<ReturnType<typeof joinMeeting>>) => {
    clearInterviewDraft()
    upsertSession({
      botId: data.bot_id,
      candidateName: form.getValues('candidate_name'),
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

  const extractMutation = useMutation({
    mutationFn: () => extractJdCvFromFiles(jdFile, cvFile),
    onSuccess: (result) => {
      setError(null)
      let filled: string[] = []

      if (result.jdText) {
        form.setValue('jdText', result.jdText, { shouldValidate: true })
        filled.push('job description')
      }
      if (result.cvText) {
        form.setValue('cvText', result.cvText, { shouldValidate: true })
        filled.push('resume')
      }
      if (result.candidateName && !form.getValues('candidate_name').trim()) {
        form.setValue('candidate_name', result.candidateName, { shouldValidate: true })
        filled.push('candidate name')
      }
      if (result.questions?.length) {
        form.setValue('questions', result.questions, { shouldValidate: true })
        filled.push(`${result.questions.length} questions`)
      }

      if (filled.length) {
        setExtractNotice(`Extracted: ${filled.join(', ')}. Review before continuing.`)
      } else {
        setExtractNotice(
          'n8n responded but no recognizable fields were found. Check the workflow output.',
        )
      }
    },
    onError: (err) => {
      setExtractNotice(null)
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError(err instanceof Error ? err.message : 'Document extraction failed')
      }
    },
  })

  const submitJoin = (replaceExisting = false) => {
    const values = form.getValues()
    setError(null)
    setDuplicateDialog(null)

    const coverage = checkBankCoverage(values.questions)
    if (!coverage.ok) {
      setError(`Question bank incomplete: ${coverage.missing.join('; ')}`)
      setStep(1)
      return
    }

    joinMutation.mutate({
      meeting_url: values.meeting_url.trim(),
      bot_name: values.bot_name?.trim() || undefined,
      candidate_name: values.candidate_name.trim(),
      jdText: values.jdText.trim(),
      cvText: values.cvText.trim(),
      questions: toApiQuestions(values.questions),
      language_mode: values.language_mode,
      greeting_message: values.greeting_message?.trim() || undefined,
      replace_existing: replaceExisting,
    })
  }

  const nextStep = async () => {
    setError(null)
    if (step === 1) {
      const ok = await form.trigger([
        'candidate_name',
        'language_mode',
        'jdText',
        'cvText',
        'greeting_message',
      ])
      const coverage = checkBankCoverage(form.getValues('questions'))
      if (!coverage.ok) {
        setError(`Question bank incomplete: ${coverage.missing.join('; ')}`)
        return
      }
      if (ok) setStep(2)
    }
  }

  const onSubmit = form.handleSubmit(() => submitJoin(false))

  const values = form.watch()
  const questionCount = values.questions?.filter((q) => q.question.trim()).length ?? 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Schedule interview</CardTitle>
        <CardDescription>
          Prepare questions first, then send the bot to the meeting. It waits in the lobby until
          you start.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <JoinWizardSteps step={step} labels={WIZARD_LABELS} />
        {error && (
          <Alert className="mb-4 border-destructive/30 bg-destructive/5 text-destructive">
            {error}
          </Alert>
        )}
        {extractNotice && (
          <Alert className="mb-4 border-success/30 bg-success/5 text-foreground">{extractNotice}</Alert>
        )}

        <FormProvider {...form}>
          <form onSubmit={onSubmit} className="space-y-4">
            {step === 1 && (
              <div className="space-y-4">
                <div>
                  <Label htmlFor="candidate_name">Candidate name</Label>
                  <Input id="candidate_name" {...form.register('candidate_name')} />
                  {form.formState.errors.candidate_name && (
                    <p className="mt-1 text-xs text-destructive">
                      {form.formState.errors.candidate_name.message}
                    </p>
                  )}
                </div>
                <div>
                  <Label>Language</Label>
                  <RadioGroup
                    value={form.watch('language_mode')}
                    onValueChange={(v) =>
                      form.setValue('language_mode', v as 'english' | 'hinglish')
                    }
                    className="mt-2 flex gap-6"
                  >
                    <div className="flex items-center gap-2">
                      <RadioGroupItem value="english" id="lang-en" />
                      <Label htmlFor="lang-en">English</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <RadioGroupItem value="hinglish" id="lang-hi" />
                      <Label htmlFor="lang-hi">Hinglish</Label>
                    </div>
                  </RadioGroup>
                </div>

                <DocumentUploadField
                  id="jdText"
                  label="Job description"
                  value={form.watch('jdText')}
                  onChange={(v) => form.setValue('jdText', v, { shouldValidate: true })}
                  error={form.formState.errors.jdText?.message}
                  file={jdFile}
                  onFileSelect={setJdFile}
                  disabled={extractMutation.isPending}
                />

                <DocumentUploadField
                  id="cvText"
                  label="Candidate resume"
                  value={form.watch('cvText')}
                  onChange={(v) => form.setValue('cvText', v, { shouldValidate: true })}
                  error={form.formState.errors.cvText?.message}
                  file={cvFile}
                  onFileSelect={setCvFile}
                  disabled={extractMutation.isPending}
                />

                <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3">
                  <p className="text-sm text-muted-foreground">
                    Upload JD and CV files, then extract text and questions via n8n.
                  </p>
                  <Button
                    type="button"
                    variant="default"
                    size="sm"
                    disabled={(!jdFile && !cvFile) || extractMutation.isPending}
                    onClick={() => {
                      setExtractNotice(null)
                      extractMutation.mutate()
                    }}
                  >
                    {extractMutation.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Extracting…
                      </>
                    ) : (
                      'Extract from documents'
                    )}
                  </Button>
                </div>

                <QuestionBankEditor />

                <div>
                  <Label htmlFor="greeting_message">Custom greeting (optional)</Label>
                  <Textarea id="greeting_message" {...form.register('greeting_message')} />
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-4">
                <Alert className="border-border bg-muted/40">
                  <p className="text-sm">
                    <span className="font-medium">{values.candidate_name || 'Candidate'}</span>
                    {' · '}
                    {values.language_mode}
                    {' · '}
                    {questionCount} questions ready
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Sending the bot to the meeting is the point of no return. You can cancel from
                    the live page if setup fails.
                  </p>
                </Alert>

                <div>
                  <Label htmlFor="meeting_url">Teams / Zoom / Meet URL</Label>
                  <Input
                    id="meeting_url"
                    placeholder="https://teams.microsoft.com/..."
                    {...form.register('meeting_url')}
                  />
                  {form.formState.errors.meeting_url && (
                    <p className="mt-1 text-xs text-destructive">
                      {form.formState.errors.meeting_url.message}
                    </p>
                  )}
                  {isTeamsLauncherUrl(form.watch('meeting_url') ?? '') && (
                    <p className="mt-1 text-xs text-muted-foreground">{MEETING_URL_HINT}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="bot_name">Bot name (optional)</Label>
                  <Input id="bot_name" {...form.register('bot_name')} />
                </div>
              </div>
            )}

            <div className="flex justify-between pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep((s) => Math.max(1, s - 1))}
                disabled={step === 1 || joinMutation.isPending}
              >
                Back
              </Button>
              {step < 2 ? (
                <Button type="button" onClick={nextStep}>
                  Continue to join
                </Button>
              ) : (
                <Button type="submit" disabled={joinMutation.isPending}>
                  {joinMutation.isPending ? 'Sending bot…' : 'Send bot to meeting'}
                </Button>
              )}
            </div>
          </form>
        </FormProvider>
      </CardContent>

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
    </Card>
  )
}
