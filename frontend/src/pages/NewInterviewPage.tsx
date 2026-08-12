import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm, FormProvider } from 'react-hook-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, Sparkles } from 'lucide-react'
import {
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
import { generateQuestionsFromText } from '@/lib/n8n'
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
  isCandidateSelectReady,
  isJobSelectReady,
  isStep1bReady,
  isStep2bReady,
  isStep3Ready,
  isStep4Ready,
  joinFormSchema,
  splitFullName,
  toApiQuestions,
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
  type CvStructured,
  type JdStructured,
} from '@/types/extraction'
import { JoinWizardSteps } from '@/components/interview/JoinWizardSteps'
import { QuestionBankEditor } from '@/components/interview/QuestionBankEditor'
import {
  CodingRoundPanel,
  toInterviewCodingConfig,
  type CodingRoundState,
} from '@/components/interview/CodingRoundPanel'
import { FormSectionCard } from '@/components/interview/FormSectionCard'
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
import { FlashAlert } from '@/components/ui/flash-alert'
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

const WIZARD_LABELS = ['Job', 'Candidate', 'Questions', 'Coding', 'Join']
const TOTAL_STEPS = 7

function displayWizardStep(step: number): number {
  if (step <= 2) return 1
  if (step <= 4) return 2
  if (step === 5) return 3
  if (step === 6) return 4
  return 5
}

function resolveInitialStep(
  savedStep: number | undefined,
  meta: ReturnType<typeof loadInterviewDraftMeta>,
): number {
  if (!savedStep || savedStep < 1 || savedStep > TOTAL_STEPS) return 1
  // Job first: need a selected job (or structured JD) before leaving step 1/2
  if (savedStep >= 2 && !meta?.jobPostingId && !meta?.jdStructured) {
    return 1
  }
  // Candidate second: need a selected candidate before leaving step 3/4
  if (savedStep >= 4 && !meta?.candidateId && !meta?.cvStructured) {
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
  const [codingRound, setCodingRound] = useState<CodingRoundState>({
    enabled: false,
    domainId: null,
    defaultLanguage: 'python',
    problemCount: 1,
    assignedTaskId: null,
    timeLimitMin: 30,
    taskIds: [],
    taskTimes: {},
  })
  const [error, setError] = useState<string | null>(null)
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
  const selectedJobId = jobPostingId ?? null

  const candidatesQuery = useQuery({
    queryKey: queryKeys.candidatesByJob(selectedJobId),
    queryFn: () => (
      selectedJobId
        ? listCandidates({ jobPostingId: selectedJobId })
        : Promise.resolve([])
    ),
    enabled: Boolean(selectedJobId),
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
    if (step === 7) {
      form.setValue('bot_name', DEFAULT_BOT_NAME)
    }
  }, [step, form])

  useEffect(() => {
    saveInterviewDraftMeta({
      cvFileName: null,
      jdFileName: null,
      wizardStep: step,
      cvStructured,
      jdStructured,
      questionsGenerated,
      candidateId,
      jobPostingId,
      extractionId,
      atsJobExternalId,
      pendingAtsJobExternalId,
      pendingAtsCandidateExternalId,
      pendingAtsCandidateParentId,
    })
  }, [
    step,
    cvStructured,
    jdStructured,
    questionsGenerated,
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
      if (imported.cv_text?.trim()) {
        form.setValue('cvText', imported.cv_text, { shouldValidate: true })
        setCvStructured({ name: imported.full_name, raw_text: imported.cv_text })
      }
      return imported.id
    }
    return null
  }

  const ensureJobPostingId = async (): Promise<string | null> => {
    if (jobPostingId) return jobPostingId
    if (pendingAtsJobExternalId) {
      const imported = await importAtsJob(pendingAtsJobExternalId)
      setJobPostingId(imported.id)
      setAtsJobExternalId(imported.external_ats_id ?? pendingAtsJobExternalId)
      setPendingAtsJobExternalId(null)
      form.setValue('position_name', imported.job_title, { shouldValidate: true })
      if (imported.jd_text?.trim()) {
        form.setValue('jdText', imported.jd_text, { shouldValidate: true })
        setJdStructured({ jd_summary: imported.jd_text })
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobPostings })
      return imported.id
    }
    return null
  }

  const jobSelectReady = isJobSelectReady(jobPostingId ?? pendingAtsJobExternalId, values)
  const candidateSelectReady = isCandidateSelectReady(
    candidateId ?? pendingAtsCandidateExternalId,
    values,
  )
  const step1bReady = isStep1bReady(values)
  const step2bReady = isStep2bReady(values)
  const step3Ready = isStep3Ready(values)
  const step4Ready = isStep4Ready(values.meeting_url ?? '')

  const proceedEnabled = useMemo(() => {
    if (step === 1) return jobSelectReady
    if (step === 2) return step2bReady
    if (step === 3) return candidateSelectReady
    if (step === 4) return step1bReady
    if (step === 5) return questionsGenerated ? step3Ready : true
    if (step === 6) {
      // Coding is optional; if enabled, require language + assigned tasks
      if (!codingRound.enabled) return true
      return Boolean(codingRound.domainId && codingRound.taskIds.length > 0)
    }
    return step4Ready
  }, [
    step,
    jobSelectReady,
    candidateSelectReady,
    step1bReady,
    step2bReady,
    step3Ready,
    step4Ready,
    questionsGenerated,
    codingRound.enabled,
    codingRound.domainId,
    codingRound.taskIds.length,
  ])

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
        setStep(7)
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
      setError('Select a saved candidate and job from the database before scheduling.')
      setStep(!jid ? 1 : 3)
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

  const questionsMutation = useMutation({
    mutationFn: async () => {
      return generateQuestionsFromText(form.getValues('jdText'), form.getValues('cvText'), {
        candidateName: form.getValues('candidate_first_name'),
        languageMode: form.getValues('language_mode'),
        extractionId,
      })
    },
  })

  const applyQuestionsResult = (
    result: Awaited<ReturnType<typeof generateQuestionsFromText>>,
  ) => {
    if (result.extractionId) setExtractionId(result.extractionId)
    if (result.questions?.length) {
      form.setValue('questions', result.questions, { shouldValidate: true })
      setQuestionsGenerated(true)
      return true
    }
    setError('Question generation returned no questions. Try again.')
    return false
  }

  const applyCandidateRow = (row: Candidate) => {
    setCandidateId(row.id)
    setPendingAtsCandidateExternalId(null)
    setPendingAtsCandidateParentId(null)
    const { first, last } = splitFullName(row.full_name)
    form.setValue('candidate_first_name', first, { shouldValidate: true })
    form.setValue('candidate_last_name', last, { shouldValidate: true })
    const cv = row.cv_text?.trim() || ''
    form.setValue('cvText', cv, { shouldValidate: true })
    setCvStructured(cv ? { name: row.full_name, raw_text: cv } : null)
  }

  const applyJobRow = (row: JobPosting) => {
    setJobPostingId(row.id)
    setPendingAtsJobExternalId(null)
    setAtsJobExternalId(row.external_ats_id ?? null)
    form.setValue('position_name', row.job_title, { shouldValidate: true })
    const jd = row.jd_text?.trim() || ''
    form.setValue('jdText', jd, { shouldValidate: true })
    setJdStructured(jd ? { jd_summary: jd } : null)
  }

  const applyAtsJobDetail = (detail: AtsJobDetail) => {
    const nextJobId = detail.already_imported ? detail.local_job_posting_id ?? null : null
    if (nextJobId !== jobPostingId) clearCandidateSelection()
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
    form.setValue('jdText', jd, { shouldValidate: true })
    setJdStructured(jd ? { jd_summary: jd } : null)
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
    const cv = detail.cv_text?.trim() || ''
    form.setValue('cvText', cv, { shouldValidate: true })
    setCvStructured(cv ? { name: detail.full_name, raw_text: cv } : null)
  }

  const clearCandidateSelection = useCallback(() => {
    setCandidateId(null)
    setPendingAtsCandidateExternalId(null)
    setPendingAtsCandidateParentId(null)
    form.setValue('candidate_first_name', '', { shouldValidate: true })
    form.setValue('candidate_last_name', '', { shouldValidate: true })
    form.setValue('cvText', '', { shouldValidate: true })
    setCvStructured(null)
  }, [form])

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
    const changed = id !== jobPostingId
    if (changed) clearCandidateSelection()
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

  useEffect(() => {
    if (!candidateId || pendingAtsCandidateExternalId) return
    if (candidatesQuery.isLoading || candidatesQuery.isFetching) return
    if (!candidatesQuery.data) return
    const inFilteredList = (candidatesQuery.data ?? []).some((candidate) => candidate.id === candidateId)
    if (!inFilteredList) {
      clearCandidateSelection()
    }
  }, [
    candidateId,
    candidatesQuery.data,
    candidatesQuery.isLoading,
    candidatesQuery.isFetching,
    pendingAtsCandidateExternalId,
    clearCandidateSelection,
  ])

  const resetQuestionsBank = () => {
    form.setValue('questions', defaultValues.questions, { shouldValidate: true })
    setQuestionsGenerated(false)
  }

  const assertCodingReady = () => {
    if (codingRound.enabled && !codingRound.domainId) {
      setError('Select a coding language, or turn off the coding round.')
      return false
    }
    if (
      codingRound.enabled &&
      (codingRound.problemCount < 1 || codingRound.problemCount > 5)
    ) {
      setError('Choose between 1 and 5 coding tasks.')
      return false
    }
    if (codingRound.enabled && codingRound.taskIds.length === 0) {
      setError('No tasks were assigned from the bank. Seed the bank or Re-pick, then continue.')
      return false
    }
    return true
  }

  const submitJoin = async (replaceExisting = false) => {
    setError(null)
    setDuplicateDialog(null)
    try {
      if (!assertCodingReady()) return
      const payload = await buildJoinPayload(replaceExisting)
      if (!payload) return
      const coding = toInterviewCodingConfig(codingRound)
      joinMutation.mutate({
        ...payload,
        ...(coding ? { coding } : {}),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to prepare interview')
    }
  }

  const submitSchedule = async () => {
    setError(null)
    try {
      if (!assertCodingReady()) return
      const payload = await buildJoinPayload(false)
      if (!payload) return
      const coding = toInterviewCodingConfig(codingRound)
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
        ...(coding ? { coding } : {}),
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
    else if (step === 7) setStep(6)
  }

  const nextStep = async () => {
    setError(null)

    // Step 1–2: Job first (select from DB only)
    if (step === 1) {
      if (!jobPostingId && !pendingAtsJobExternalId) {
        setError('Select a saved job from the database (upload JDs in Bulk Upload).')
        return
      }
      const text = form.getValues('jdText').trim()
      if (text.length < 100) {
        setError(
          'Selected job has no usable JD text yet. Process the job in Bulk Upload, then select it here.',
        )
        return
      }
      const ok = await form.trigger(['position_name'])
      if (!ok || !jobSelectReady) return
      if (!jdStructured) setJdStructured({ jd_summary: text })
      setStep(2)
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

    // Step 3–4: Candidate (select from DB only)
    if (step === 3) {
      if (!candidateId && !pendingAtsCandidateExternalId) {
        setError('Select a saved candidate from the database (upload CVs in Bulk Upload).')
        return
      }
      const text = form.getValues('cvText').trim()
      if (text.length < 50) {
        setError(
          'Selected candidate has no usable resume text yet. Process the CV in Bulk Upload, then select it here.',
        )
        return
      }
      const ok = await form.trigger(['candidate_first_name', 'candidate_last_name', 'language_mode'])
      if (!ok || !candidateSelectReady) return
      if (!cvStructured) {
        setCvStructured({
          name: formatCandidateDisplayName(
            form.getValues('candidate_first_name'),
            form.getValues('candidate_last_name'),
          ),
          raw_text: text,
        })
      }
      setStep(4)
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
      const jdText = form.getValues('jdText').trim()
      const cvText = form.getValues('cvText').trim()
      if (jdText.length < 100 || cvText.length < 50) {
        if (jdText.length < 100) {
          setError('Job description text is missing. Select a processed JD in Job Requirements first.')
          setStep(1)
        } else {
          setError('Resume text is missing. Select a processed candidate CV linked to this job.')
          setStep(3)
        }
        return
      }
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
      return
    }

    if (step === 6) {
      if (!assertCodingReady()) return
      setStep(7)
    }
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (step === TOTAL_STEPS) {
      submitJoin(false)
    }
  }

  const wizardBusy = questionsMutation.isPending

  const proceedLabel = useMemo(() => {
    if (step === 5 && questionsMutation.isPending) return 'Generating questions…'
    if (step === TOTAL_STEPS) {
      return joinMutation.isPending ? 'Sending bot…' : 'Send to lobby'
    }
    if (step === 1) return 'Continue'
    if (step === 2) return 'Continue to candidate'
    if (step === 3) return 'Continue'
    if (step === 4) return 'Continue to questions'
    if (step === 5) return questionsGenerated ? 'Continue to coding' : 'Generate questions'
    if (step === 6) return 'Continue to join'
    return 'Continue'
  }, [step, questionsGenerated, questionsMutation.isPending, joinMutation.isPending])

  const cvReviewData = cvStructured ?? { raw_text: values.cvText }
  const jdReviewData = jdStructured ?? { jd_summary: values.jdText }

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl select-none flex-col px-1 sm:px-0">
      <div className="mb-3 shrink-0 rounded-xl border border-border bg-card/95 px-3 py-3 shadow-sm backdrop-blur-sm sm:px-4">
        <JoinWizardSteps step={displayWizardStep(step)} labels={WIZARD_LABELS} />
      </div>

      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden border-border shadow-sm">
        <CardContent className="flex min-h-0 flex-1 flex-col p-4 sm:p-5">
          <FlashAlert
            message={error}
            onDismiss={() => setError(null)}
            className="mb-4 shrink-0 border-destructive/30 bg-destructive/5 text-destructive"
          />

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
                  description="Select a candidate uploaded under the selected job (Bulk Upload)."
                >
                  <div className="space-y-4">
                    <EntityPicker
                      label="Saved candidates"
                      placeholder="Select a candidate"
                      value={candidateId}
                      loading={candidatesQuery.isLoading}
                      disabled={wizardBusy}
                      allowCreate={false}
                      options={(candidatesQuery.data ?? []).map((c) => ({
                        id: c.id,
                        label: c.full_name,
                        hint: c.cv_text?.trim()
                          ? c.email ?? 'resume ready'
                          : 'no resume text',
                      }))}
                      onChange={selectCandidate}
                      onClear={clearCandidateSelection}
                      helperText="Only candidates linked to this selected job and with extracted resume text can continue."
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
                          readOnly
                          {...form.register('candidate_first_name')}
                        />
                      </div>
                      <div>
                        <Label htmlFor="candidate_last_name">Last name</Label>
                        <Input
                          id="candidate_last_name"
                          className="mt-1.5 select-text"
                          readOnly
                          {...form.register('candidate_last_name')}
                        />
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

                    {values.cvText.trim() ? (
                      <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5">
                        <p className="text-xs font-medium text-foreground">Resume loaded from database</p>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {values.cvText.trim().length.toLocaleString()} characters — review on the next step.
                        </p>
                      </div>
                    ) : candidateId || pendingAtsCandidateExternalId ? (
                      <p className="text-xs text-destructive">
                        No resume text on this candidate. Process the CV in Bulk Upload first.
                      </p>
                    ) : null}
                  </div>
                </FormSectionCard>
              )}

              {step === 4 && (
                <FormSectionCard
                  title="Review resume text"
                  description="Confirm the resume loaded from the database. Edit if needed before generating questions."
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
                  description="Select a job already in the database (upload JDs in Bulk Upload)."
                >
                  <div className="space-y-4">
                    <EntityPicker
                      label="Saved jobs"
                      placeholder="Select a job"
                      value={jobPostingId}
                      loading={jobsQuery.isLoading}
                      disabled={wizardBusy}
                      allowCreate={false}
                      options={(jobsQuery.data ?? []).map((j) => ({
                        id: j.id,
                        label: j.job_title,
                        hint: j.jd_text?.trim()
                          ? j.status
                          : 'no JD text',
                      }))}
                      onChange={selectJob}
                      onClear={() => {
                        setJobPostingId(null)
                        setPendingAtsJobExternalId(null)
                        setAtsJobExternalId(null)
                        form.setValue('jdText', '', { shouldValidate: true })
                        form.setValue('position_name', '', { shouldValidate: true })
                        setJdStructured(null)
                      }}
                      helperText="Only jobs with extracted JD text can continue."
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
                        readOnly
                        {...form.register('position_name')}
                      />
                    </div>

                    {values.jdText.trim() ? (
                      <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5">
                        <p className="text-xs font-medium text-foreground">
                          Job description loaded from database
                        </p>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {values.jdText.trim().length.toLocaleString()} characters — review on the next step.
                        </p>
                      </div>
                    ) : jobPostingId || pendingAtsJobExternalId ? (
                      <p className="text-xs text-destructive">
                        No JD text on this job. Process the job description in Bulk Upload first.
                      </p>
                    ) : null}
                  </div>
                </FormSectionCard>
              )}

              {step === 2 && (
                <FormSectionCard
                  title="Review job description text"
                  description="Confirm the JD loaded from the database. Edit if needed before continuing."
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
                      : 'Generate a question bank from the selected resume and job description.'
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
                        We will create ~15 questions from the selected resume and job description.
                        You can edit them before continuing.
                      </p>
                    </div>
                  )}
                </FormSectionCard>
              )}

              {step === 6 && (
                <FormSectionCard title="Coding round">
                  <CodingRoundPanel
                    value={codingRound}
                    onChange={setCodingRound}
                    disabled={submitBusy || wizardBusy}
                    jobPostingId={jobPostingId}
                    candidateId={candidateId}
                  />
                </FormSectionCard>
              )}

              {step === 7 && (
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
                      {codingRound.enabled
                        ? ` · coding ${codingRound.problemCount || 1}×${codingRound.defaultLanguage}`
                        : ''}
                    </p>
                  </Alert>
                  <FormSectionCard title="Join meeting">
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
