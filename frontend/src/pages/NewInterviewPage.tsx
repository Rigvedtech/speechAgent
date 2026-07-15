import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm, FormProvider } from 'react-hook-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, Sparkles } from 'lucide-react'
import {
  createCandidate,
  createJobPosting,
  getAtsSettings,
  importAtsCandidate,
  importAtsJob,
  joinMeeting,
  listCandidates,
  listJobPostings,
  scheduleInterview,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
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
  type DocumentInputMode,
  type JoinFormValues,
} from '@/schemas/join-form.schema'
import type {
  ApiErrorDetail,
  AtsCandidateDetail,
  AtsJobDetail,
  Candidate,
  JobPosting,
} from '@/types/api'
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
import { InputModeToggle } from '@/components/interview/InputModeToggle'
import { EntityPicker } from '@/components/interview/EntityPicker'
import { AtsImportDialog } from '@/components/interview/AtsImportDialog'
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

const WIZARD_LABELS = ['Job', 'Candidate', 'Questions', 'Join']
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
  // Job is first: if past job entry without JD data, reset to job step
  if (
    savedStep >= 2 &&
    !meta?.jdStructured &&
    !meta?.jdFileName &&
    meta?.jdInputMode !== 'manual'
  ) {
    return 1
  }
  // Candidate is second: if past candidate entry without CV data, reset to candidate step
  if (
    savedStep >= 4 &&
    !meta?.cvStructured &&
    !meta?.cvFileName &&
    meta?.cvInputMode !== 'manual'
  ) {
    return 3
  }
  return savedStep
}

export function NewInterviewPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const savedDraft = loadInterviewDraft()
  const savedMeta = loadInterviewDraftMeta()

  const [step, setStep] = useState(() => resolveInitialStep(savedMeta?.wizardStep, savedMeta))
  const [error, setError] = useState<string | null>(null)
  const [jdFile, setJdFile] = useState<File | null>(null)
  const [cvFile, setCvFile] = useState<File | null>(null)
  const [cvInputMode, setCvInputMode] = useState<DocumentInputMode>(
    savedMeta?.cvInputMode ?? 'upload',
  )
  const [jdInputMode, setJdInputMode] = useState<DocumentInputMode>(
    savedMeta?.jdInputMode ?? 'upload',
  )
  const [cvStructured, setCvStructured] = useState<CvStructured | null>(
    savedMeta?.cvStructured ?? null,
  )
  const [jdStructured, setJdStructured] = useState<JdStructured | null>(
    savedMeta?.jdStructured ?? null,
  )
  const [candidateId, setCandidateId] = useState<string | null>(savedMeta?.candidateId ?? null)
  const [jobPostingId, setJobPostingId] = useState<string | null>(savedMeta?.jobPostingId ?? null)
  const [extractionId, setExtractionId] = useState<string | null>(savedMeta?.extractionId ?? null)
  const [atsJobExternalId, setAtsJobExternalId] = useState<string | null>(
    savedMeta?.atsJobExternalId ?? null,
  )
  const [pendingAtsJobExternalId, setPendingAtsJobExternalId] = useState<string | null>(
    savedMeta?.pendingAtsJobExternalId ?? null,
  )
  const [pendingAtsCandidateExternalId, setPendingAtsCandidateExternalId] = useState<string | null>(
    savedMeta?.pendingAtsCandidateExternalId ?? null,
  )
  const [pendingAtsCandidateParentId, setPendingAtsCandidateParentId] = useState<string | null>(
    savedMeta?.pendingAtsCandidateParentId ?? null,
  )
  const [questionsGenerated, setQuestionsGenerated] = useState(() => {
    if (savedMeta?.questionsGenerated) return true
    return (savedDraft?.questions ?? []).some((q) => q.question.trim().length >= 10)
  })
  const [duplicateDialog, setDuplicateDialog] = useState<{
    botId: string
    message: string
  } | null>(null)
  const [atsImportOpen, setAtsImportOpen] = useState(false)
  const [atsImportMode, setAtsImportMode] = useState<'candidate' | 'job'>('job')

  const candidatesQuery = useQuery({
    queryKey: queryKeys.candidates,
    queryFn: () => listCandidates(),
  })
  const jobsQuery = useQuery({
    queryKey: queryKeys.jobPostings,
    queryFn: () => listJobPostings(),
  })
  const atsSettingsQuery = useQuery({
    queryKey: queryKeys.atsSettings,
    queryFn: getAtsSettings,
  })
  const atsConnected = Boolean(atsSettingsQuery.data?.is_connected)

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
      cvInputMode,
      jdInputMode,
      candidateId,
      jobPostingId,
      extractionId,
      atsJobExternalId,
      pendingAtsJobExternalId,
      pendingAtsCandidateExternalId,
      pendingAtsCandidateParentId,
    })
  }, [
    cvFile,
    jdFile,
    step,
    cvStructured,
    jdStructured,
    questionsGenerated,
    cvInputMode,
    jdInputMode,
    candidateId,
    jobPostingId,
    extractionId,
    atsJobExternalId,
    pendingAtsJobExternalId,
    pendingAtsCandidateExternalId,
    pendingAtsCandidateParentId,
  ])

  const ensureCandidateId = async (): Promise<string | null> => {
    if (candidateId) return candidateId
    if (pendingAtsCandidateExternalId) {
      const imported = await importAtsCandidate(
        pendingAtsCandidateExternalId,
        pendingAtsCandidateParentId || atsJobExternalId || undefined,
      )
      setCandidateId(imported.id)
      setPendingAtsCandidateExternalId(null)
      setPendingAtsCandidateParentId(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.candidates })
      return imported.id
    }
    const first = form.getValues('candidate_first_name').trim()
    const last = form.getValues('candidate_last_name').trim()
    const fullName = formatCandidateDisplayName(first, last)
    if (fullName.length < 2) return null
    const created = await createCandidate({
      full_name: fullName,
      cv_text: form.getValues('cvText').trim() || undefined,
      source: cvInputMode === 'upload' ? 'upload' : 'manual',
    })
    setCandidateId(created.id)
    void queryClient.invalidateQueries({ queryKey: queryKeys.candidates })
    return created.id
  }

  const ensureJobPostingId = async (): Promise<string | null> => {
    if (jobPostingId) return jobPostingId
    if (pendingAtsJobExternalId) {
      const imported = await importAtsJob(pendingAtsJobExternalId)
      setJobPostingId(imported.id)
      setAtsJobExternalId(imported.external_ats_id ?? pendingAtsJobExternalId)
      setPendingAtsJobExternalId(null)
      form.setValue('position_name', imported.job_title, { shouldValidate: true })
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobPostings })
      return imported.id
    }
    const title = form.getValues('position_name').trim()
    if (title.length < 2) return null
    const jd = form.getValues('jdText').trim()
    const created = await createJobPosting({
      job_title: title,
      jd_text: jd.length >= 100 ? jd : undefined,
      source: jdInputMode === 'upload' ? 'upload' : 'manual',
    })
    setJobPostingId(created.id)
    if (created.job_title !== title) {
      form.setValue('position_name', created.job_title, { shouldValidate: true })
    }
    void queryClient.invalidateQueries({ queryKey: queryKeys.jobPostings })
    return created.id
  }

  const step1Ready = isStep1Ready(values, cvFile, cvInputMode)
  const step1bReady = isStep1bReady(values)
  const step2Ready = isStep2Ready(values, jdFile, jdInputMode)
  const step2bReady = isStep2bReady(values)
  const step3Ready = isStep3Ready(values)
  const step4Ready = isStep4Ready(values.meeting_url ?? '')

  const proceedEnabled = useMemo(() => {
    if (step === 1) return step2Ready
    if (step === 2) return step2bReady
    if (step === 3) return step1Ready
    if (step === 4) return step1bReady
    if (step === 5) return questionsGenerated ? step3Ready : true
    return step4Ready
  }, [step, step1Ready, step1bReady, step2Ready, step2bReady, step3Ready, step4Ready, questionsGenerated])

  const questionCount = values.questions?.filter((q) => q.question.trim()).length ?? 0

  const handleJoinSuccess = (data: Awaited<ReturnType<typeof joinMeeting>>) => {
    clearInterviewDraft()
    void queryClient.invalidateQueries({ queryKey: queryKeys.scheduledInterviews })
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

  const buildJoinPayload = async (replaceExisting = false) => {
    const parsed = joinFormSchema.safeParse(form.getValues())
    if (!parsed.success) {
      const first = parsed.error.issues[0]
      setError(first?.message ?? 'Please complete all required fields')
      if (first?.path.includes('questions') || first?.path.includes('jdText') || first?.path.includes('cvText')) {
        setStep(5)
      } else if (first?.path.includes('meeting_url')) {
        setStep(6)
      }
      return null
    }

    const data = parsed.data
    const coverage = checkBankCoverage(data.questions)
    if (!coverage.ok) {
      setError(`Question bank incomplete: ${coverage.missing.join('; ')}`)
      setStep(5)
      return null
    }

    const [cid, jid] = await Promise.all([ensureCandidateId(), ensureJobPostingId()])
    if (!cid || !jid) {
      setError('Select or create a candidate and job before scheduling or sending to lobby.')
      setStep(1)
      return null
    }
    return {
      meeting_url: data.meeting_url.trim(),
      bot_name: DEFAULT_BOT_NAME,
      candidate_name: data.candidate_first_name.trim(),
      jdText: data.jdText.trim(),
      cvText: data.cvText.trim(),
      questions: toApiQuestions(data.questions),
      language_mode: data.language_mode,
      greeting_message: data.greeting_message?.trim() || undefined,
      replace_existing: replaceExisting,
      candidate_id: cid,
      job_posting_id: jid,
      job_title: data.position_name.trim(),
      document_extraction_id: extractionId ?? undefined,
    }
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

  const scheduleMutation = useMutation({
    mutationFn: scheduleInterview,
    onSuccess: () => {
      clearInterviewDraft()
      void queryClient.invalidateQueries({ queryKey: queryKeys.scheduledInterviews })
      navigate('/interviews/scheduled', { state: { scheduled: true } })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Failed to schedule interview')
      }
    },
  })

  const extractCvMutation = useMutation({
    mutationFn: async () => {
      if (!cvFile) throw new Error('Upload a resume file')
      return extractCvFromFile(cvFile)
    },
  })

  const extractJdMutation = useMutation({
    mutationFn: async () => {
      if (!jdFile) throw new Error('Upload a job description file')
      return extractJdFromFile(jdFile)
    },
  })

  const questionsMutation = useMutation({
    mutationFn: async () => {
      return generateQuestionsFromText(form.getValues('jdText'), form.getValues('cvText'), {
        candidateName: form.getValues('candidate_first_name'),
        languageMode: form.getValues('language_mode'),
        extractionId,
      })
    },
  })

  const applyCvResult = (result: Awaited<ReturnType<typeof extractCvFromFile>>) => {
    if (result.cvText) {
      form.setValue('cvText', result.cvText, { shouldValidate: true })
    }
    if (result.extractionId) setExtractionId(result.extractionId)
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
    if (result.extractionId) setExtractionId(result.extractionId)
    setJdStructured(asJdStructured(result.jdStructured) ?? { jd_summary: result.jdText })
  }

  const applyQuestionsResult = (
    result: Awaited<ReturnType<typeof generateQuestionsFromText>>,
  ) => {
    if (result.extractionId) setExtractionId(result.extractionId)
    if (result.questions?.length) {
      form.setValue('questions', result.questions, { shouldValidate: true })
      setQuestionsGenerated(true)
      return true
    }
    setError('n8n responded but no questions were found. Check the workflow output.')
    return false
  }

  const applyCandidateRow = (row: Candidate) => {
    setCandidateId(row.id)
    setPendingAtsCandidateExternalId(null)
    setPendingAtsCandidateParentId(null)
    const { first, last } = splitFullName(row.full_name)
    form.setValue('candidate_first_name', first, { shouldValidate: true })
    form.setValue('candidate_last_name', last, { shouldValidate: true })
    if (row.cv_text?.trim()) {
      form.setValue('cvText', row.cv_text, { shouldValidate: true })
      setCvInputMode('manual')
      setCvFile(null)
      setCvStructured({ name: row.full_name, raw_text: row.cv_text })
    }
  }

  const applyJobRow = (row: JobPosting) => {
    setJobPostingId(row.id)
    setPendingAtsJobExternalId(null)
    setAtsJobExternalId(row.external_ats_id ?? null)
    form.setValue('position_name', row.job_title, { shouldValidate: true })
    if (row.jd_text?.trim()) {
      form.setValue('jdText', row.jd_text, { shouldValidate: true })
      setJdInputMode('manual')
      setJdFile(null)
      setJdStructured({ jd_summary: row.jd_text })
    }
  }

  const applyAtsJobDetail = (detail: AtsJobDetail) => {
    setAtsJobExternalId(detail.external_id)
    if (detail.already_imported && detail.local_job_posting_id) {
      setJobPostingId(detail.local_job_posting_id)
      setPendingAtsJobExternalId(null)
    } else {
      setJobPostingId(null)
      setPendingAtsJobExternalId(detail.external_id)
    }
    form.setValue('position_name', detail.job_title, { shouldValidate: true })
    const jd = detail.jd_text?.trim() || detail.description?.trim() || ''
    if (jd) {
      form.setValue('jdText', jd, { shouldValidate: true })
      setJdInputMode('manual')
      setJdFile(null)
      setJdStructured({ jd_summary: jd })
    }
  }

  const applyAtsCandidateDetail = (detail: AtsCandidateDetail) => {
    const parent = detail.parent_id || atsJobExternalId
    if (detail.already_imported && detail.local_candidate_id) {
      setCandidateId(detail.local_candidate_id)
      setPendingAtsCandidateExternalId(null)
      setPendingAtsCandidateParentId(null)
    } else {
      setCandidateId(null)
      setPendingAtsCandidateExternalId(detail.external_id)
      setPendingAtsCandidateParentId(parent)
    }
    const { first, last } = splitFullName(detail.full_name)
    form.setValue('candidate_first_name', first, { shouldValidate: true })
    form.setValue('candidate_last_name', last, { shouldValidate: true })
    if (detail.cv_text?.trim()) {
      form.setValue('cvText', detail.cv_text, { shouldValidate: true })
      setCvInputMode('manual')
      setCvFile(null)
      setCvStructured({ name: detail.full_name, raw_text: detail.cv_text })
    }
  }

  const selectCandidate = (id: string | null) => {
    setCandidateId(id)
    setPendingAtsCandidateExternalId(null)
    setPendingAtsCandidateParentId(null)
    if (!id) return
    const row = (candidatesQuery.data ?? []).find((c) => c.id === id)
    if (!row) return
    applyCandidateRow(row)
  }

  const selectJob = (id: string | null) => {
    setJobPostingId(id)
    setPendingAtsJobExternalId(null)
    if (!id) {
      setAtsJobExternalId(null)
      return
    }
    const row = (jobsQuery.data ?? []).find((j) => j.id === id)
    if (!row) return
    applyJobRow(row)
  }

  const resetQuestionsBank = () => {
    form.setValue('questions', defaultValues.questions, { shouldValidate: true })
    setQuestionsGenerated(false)
  }

  const submitJoin = async (replaceExisting = false) => {
    setError(null)
    setDuplicateDialog(null)
    try {
      const payload = await buildJoinPayload(replaceExisting)
      if (!payload) return
      joinMutation.mutate(payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to prepare interview')
    }
  }

  const submitSchedule = async () => {
    setError(null)
    try {
      const payload = await buildJoinPayload(false)
      if (!payload) return
      scheduleMutation.mutate({
        meeting_url: payload.meeting_url,
        candidate_id: payload.candidate_id,
        job_posting_id: payload.job_posting_id,
        candidate_name: payload.candidate_name,
        job_title: payload.job_title,
        jdText: payload.jdText,
        cvText: payload.cvText,
        questions: payload.questions,
        language_mode: payload.language_mode,
        bot_name: payload.bot_name,
        greeting_message: payload.greeting_message,
        document_extraction_id: payload.document_extraction_id,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to schedule interview')
    }
  }

  const submitBusy = joinMutation.isPending || scheduleMutation.isPending

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

    // Step 1–2: Job first
    if (step === 1) {
      const ok = await form.trigger(['position_name'])
      if (!ok || !step2Ready) return

      if (jdInputMode === 'manual') {
        const text = form.getValues('jdText').trim()
        if (text.length < 100) {
          setError('Paste a fuller job description (100+ characters) before continuing.')
          return
        }
        setJdStructured({ jd_summary: text })
        setStep(2)
        return
      }

      if (!jdFile) return
      try {
        const result = await extractJdMutation.mutateAsync()
        applyJdResult(result)
        setStep(2)
      } catch (err) {
        if (err instanceof ApiError) {
          setError(formatApiError(err.message, err.detail))
        } else {
          setError(err instanceof Error ? err.message : 'Job description extraction failed')
        }
      }
      return
    }

    if (step === 2) {
      if (!step2bReady) {
        setError('Review and edit the job description text before continuing.')
        return
      }
      setStep(3)
      return
    }

    // Step 3–4: Candidate
    if (step === 3) {
      const ok = await form.trigger(['candidate_first_name', 'candidate_last_name', 'language_mode'])
      if (!ok || !step1Ready) return

      if (cvInputMode === 'manual') {
        const text = form.getValues('cvText').trim()
        if (text.length < 50) {
          setError('Paste at least a short resume (50+ characters) before continuing.')
          return
        }
        setCvStructured({
          name: formatCandidateDisplayName(
            form.getValues('candidate_first_name'),
            form.getValues('candidate_last_name'),
          ),
          raw_text: text,
        })
        setStep(4)
        return
      }

      if (!cvFile) return
      try {
        const result = await extractCvMutation.mutateAsync()
        applyCvResult(result)
        setStep(4)
      } catch (err) {
        if (err instanceof ApiError) {
          setError(formatApiError(err.message, err.detail))
        } else {
          setError(err instanceof Error ? err.message : 'Resume extraction failed')
        }
      }
      return
    }

    if (step === 4) {
      if (!step1bReady) {
        setError('Review and edit the resume text before continuing.')
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
    if (step === 1 && extractJdMutation.isPending) return 'Extracting job description…'
    if (step === 3 && extractCvMutation.isPending) return 'Extracting resume…'
    if (step === 5 && questionsMutation.isPending) return 'Generating questions…'
    if (step === TOTAL_STEPS) {
      return joinMutation.isPending ? 'Sending bot…' : 'Send to lobby'
    }
    if (step === 1) return jdInputMode === 'manual' ? 'Continue' : 'Extract & continue'
    if (step === 2) return 'Continue to candidate'
    if (step === 3) return cvInputMode === 'manual' ? 'Continue' : 'Extract & continue'
    if (step === 4) return 'Continue to questions'
    if (step === 5) return questionsGenerated ? 'Continue to join' : 'Generate questions'
    return 'Continue'
  }, [
    step,
    questionsGenerated,
    cvInputMode,
    jdInputMode,
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
              {step === 3 && (
                <FormSectionCard
                  title="Candidate"
                  description="Choose a saved candidate, import from ATS, or enter details and a resume."
                >
                  <div className="space-y-4">
                    <EntityPicker
                      label="Saved candidates"
                      placeholder="Select a candidate"
                      value={candidateId}
                      loading={candidatesQuery.isLoading}
                      disabled={wizardBusy}
                      options={(candidatesQuery.data ?? []).map((c) => ({
                        id: c.id,
                        label: c.full_name,
                        hint: c.email ?? undefined,
                      }))}
                      onChange={selectCandidate}
                      onClear={() => {
                        setCandidateId(null)
                        setPendingAtsCandidateExternalId(null)
                        setPendingAtsCandidateParentId(null)
                      }}
                      helperText="Selecting a saved candidate fills the fields below."
                      action={
                        atsConnected ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 gap-1.5 px-2 text-xs"
                            disabled={wizardBusy}
                            onClick={() => {
                              setAtsImportMode('candidate')
                              setAtsImportOpen(true)
                            }}
                          >
                            <Download className="h-3.5 w-3.5" strokeWidth={1.5} />
                            From ATS
                          </Button>
                        ) : null
                      }
                    />
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

                    <div>
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <Label>Candidate resume</Label>
                      </div>
                      <InputModeToggle
                        value={cvInputMode}
                        disabled={wizardBusy}
                        onChange={(mode) => {
                          setCvInputMode(mode)
                          setError(null)
                          if (mode === 'manual') {
                            setCvFile(null)
                          }
                        }}
                      />
                      <div className="mt-3">
                        {cvInputMode === 'upload' ? (
                          <>
                            <CompactFileUpload
                              label="Upload resume"
                              file={cvFile}
                              onFileSelect={setCvFile}
                              disabled={wizardBusy}
                              error={
                                !cvFile && form.formState.isSubmitted
                                  ? 'Resume file is required'
                                  : undefined
                              }
                            />
                            {savedMeta?.cvFileName && !cvFile ? (
                              <p className="mt-1.5 text-xs text-muted-foreground">
                                Previously uploaded: {savedMeta.cvFileName} — re-upload to continue
                                after refresh.
                              </p>
                            ) : null}
                          </>
                        ) : (
                          <div>
                            <Textarea
                              id="cvText_manual"
                              className="min-h-[180px] select-text"
                              placeholder="Paste the full resume text here…"
                              value={values.cvText}
                              disabled={wizardBusy}
                              onChange={(e) =>
                                form.setValue('cvText', e.target.value, { shouldValidate: true })
                              }
                            />
                            <p className="mt-1.5 text-xs text-muted-foreground">
                              Tip: paste the complete resume so question generation has enough
                              context (min. 50 characters).
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </FormSectionCard>
              )}

              {step === 4 && (
                <FormSectionCard
                  title={
                    cvInputMode === 'manual' ? 'Review resume text' : 'Review extracted resume'
                  }
                  description={
                    cvInputMode === 'manual'
                      ? 'Confirm the resume text you entered. Edit anything before continuing.'
                      : 'Structured profile from your upload. Edit the resume text at the bottom before continuing.'
                  }
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

              {step === 1 && (
                <FormSectionCard
                  title="Job"
                  description="Choose a saved role, import from ATS, or add a new job description."
                >
                  <div className="space-y-4">
                    <EntityPicker
                      label="Saved jobs"
                      placeholder="Select a job"
                      value={jobPostingId}
                      loading={jobsQuery.isLoading}
                      disabled={wizardBusy}
                      options={(jobsQuery.data ?? []).map((j) => ({
                        id: j.id,
                        label: j.job_title,
                        hint: j.status,
                      }))}
                      onChange={selectJob}
                      onClear={() => {
                        setJobPostingId(null)
                        setPendingAtsJobExternalId(null)
                        setAtsJobExternalId(null)
                      }}
                      helperText="Selecting a saved job fills the fields below."
                      action={
                        atsConnected ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 gap-1.5 px-2 text-xs"
                            disabled={wizardBusy}
                            onClick={() => {
                              setAtsImportMode('job')
                              setAtsImportOpen(true)
                            }}
                          >
                            <Download className="h-3.5 w-3.5" strokeWidth={1.5} />
                            From ATS
                          </Button>
                        ) : null
                      }
                    />
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

                    <div>
                      <div className="mb-2">
                        <Label>Job description</Label>
                      </div>
                      <InputModeToggle
                        value={jdInputMode}
                        disabled={wizardBusy}
                        onChange={(mode) => {
                          setJdInputMode(mode)
                          setError(null)
                          if (mode === 'manual') {
                            setJdFile(null)
                          }
                        }}
                      />
                      <div className="mt-3">
                        {jdInputMode === 'upload' ? (
                          <>
                            <CompactFileUpload
                              label="Upload job description"
                              file={jdFile}
                              onFileSelect={setJdFile}
                              disabled={wizardBusy}
                            />
                            {savedMeta?.jdFileName && !jdFile ? (
                              <p className="mt-1.5 text-xs text-muted-foreground">
                                Previously uploaded: {savedMeta.jdFileName} — re-upload to extract
                                again.
                              </p>
                            ) : null}
                          </>
                        ) : (
                          <div>
                            <Textarea
                              id="jdText_manual"
                              className="min-h-[180px] select-text"
                              placeholder="Paste the full job description here…"
                              value={values.jdText}
                              disabled={wizardBusy}
                              onChange={(e) =>
                                form.setValue('jdText', e.target.value, { shouldValidate: true })
                              }
                            />
                            <p className="mt-1.5 text-xs text-muted-foreground">
                              Tip: include responsibilities and must-have skills (min. 100
                              characters).
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </FormSectionCard>
              )}

              {step === 2 && (
                <FormSectionCard
                  title={
                    jdInputMode === 'manual'
                      ? 'Review job description text'
                      : 'Review extracted job description'
                  }
                  description={
                    jdInputMode === 'manual'
                      ? 'Confirm the job text you entered. Edit anything before continuing.'
                      : 'Structured role details from your upload. Edit the job text at the bottom before continuing.'
                  }
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
                      Schedule saves the setup without creating a bot. Send to lobby creates the
                      Recall bot and opens the live session.
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
                  disabled={step === 1 || submitBusy || wizardBusy}
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
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={!proceedEnabled || submitBusy}
                      onClick={() => void submitSchedule()}
                    >
                      {scheduleMutation.isPending && (
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                      )}
                      {scheduleMutation.isPending ? 'Scheduling…' : 'Schedule'}
                    </Button>
                    <Button
                      type="submit"
                      disabled={!proceedEnabled || submitBusy}
                    >
                      {joinMutation.isPending && (
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                      )}
                      {proceedLabel}
                    </Button>
                  </div>
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
              onClick={() => void submitJoin(true)}
            >
              {joinMutation.isPending ? 'Replacing…' : 'Replace and start fresh'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <AtsImportDialog
        open={atsImportOpen}
        mode={atsImportMode}
        onOpenChange={setAtsImportOpen}
        lockedParentId={atsImportMode === 'candidate' ? atsJobExternalId : null}
        onPickJob={applyAtsJobDetail}
        onPickCandidate={applyAtsCandidateDetail}
      />
    </div>
  )
}
