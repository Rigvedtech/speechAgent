import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  CalendarPlus,
  CheckCircle2,
  Eye,
  FileText,
  Gauge,
  Loader2,
  RefreshCcw,
  Trash2,
  UploadCloud,
  UserRound,
} from 'lucide-react'
import {
  extractUploadBatch,
  getDocument,
  getJobPosting,
  listJobResumes,
  parseUploadBatch,
  scoreJobMatches,
  updateCandidate,
  updateJobPosting,
  uploadJobResumes,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import {
  clearInterviewDraft,
  saveInterviewDraft,
  saveInterviewDraftMeta,
} from '@/lib/draft-store'
import { queryKeys } from '@/lib/query-keys'
import { splitFullName } from '@/schemas/join-form.schema'
import { useAuth } from '@/hooks/useAuth'
import { FileDropzone } from '@/components/bulk-upload/FileDropzone'
import { Alert } from '@/components/ui/alert'
import { FlashAlert } from '@/components/ui/flash-alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { Textarea } from '@/components/ui/textarea'
import type { JobResume } from '@/types/api'

type UploadStage = 'idle' | 'uploading' | 'extracting' | 'parsing'

const MAX_FILES = 50
const MAX_BYTES = 20 * 1024 * 1024

const UPLOAD_STAGE_LABELS: Record<UploadStage, string> = {
  idle: 'Upload and process resumes',
  uploading: 'Uploading resumes…',
  extracting: 'Extracting text and OCR…',
  parsing: 'Creating candidate profiles…',
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : 'Something went wrong'
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function bytesLabel(bytes?: number | null) {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function resumeStatus(resume: JobResume) {
  if (resume.candidate_id) return <Badge variant="success">Profile ready</Badge>
  if (resume.upload_status === 'failed') return <Badge variant="destructive">Failed</Badge>
  if (resume.upload_status === 'processing') return <Badge variant="warning">Processing</Badge>
  return <Badge variant="secondary">{resume.upload_status}</Badge>
}

function isScoreable(resume: JobResume) {
  return Boolean(resume.candidate_id && (resume.cv_text?.trim().length ?? 0) >= 40)
}

function isUnscored(resume: JobResume) {
  return isScoreable(resume) && resume.match_score == null
}

/** Normalize to 1–10 (legacy API rows may still be 0–100). */
function scoreOnTen(score: number | null | undefined): number | null {
  if (score == null || Number.isNaN(score)) return null
  let value = Number(score)
  if (value > 10) value = value / 10
  return Math.round(Math.max(1, Math.min(10, value)) * 10) / 10
}

function formatTen(score: number | null | undefined): string {
  const value = scoreOnTen(score)
  if (value == null) return '—'
  return Number.isInteger(value) ? `${value}/10` : `${value.toFixed(1)}/10`
}

function scoreBadge(score: number | null | undefined) {
  const value = scoreOnTen(score)
  if (value == null) {
    return <Badge variant="secondary">—</Badge>
  }
  const label = formatTen(value)
  if (value >= 7.5) return <Badge variant="success">{label}</Badge>
  if (value >= 5) return <Badge variant="warning">{label}</Badge>
  return <Badge variant="destructive">{label}</Badge>
}

function FitScoreMark({ score }: { score: number | null | undefined }) {
  const value = scoreOnTen(score)
  if (value == null) {
    return <span className="text-sm text-muted-foreground/70">—</span>
  }
  const tone =
    value >= 7.5 ? 'text-success' : value >= 5 ? 'text-warning' : 'text-destructive'
  const whole = Number.isInteger(value) ? String(value) : value.toFixed(1)
  return (
    <span className={`inline-flex items-baseline gap-0.5 tabular-nums ${tone}`}>
      <span className="text-xl font-semibold tracking-tight">{whole}</span>
      <span className="text-[11px] font-medium text-muted-foreground">/10</span>
    </span>
  )
}

/** Component scores are stored 0–100 (sometimes as strings from JSON). */
function asPercent(raw: unknown): number | null {
  if (raw == null || raw === '') return null
  const n = typeof raw === 'number' ? raw : Number(raw)
  if (!Number.isFinite(n)) return null
  // Already a percentage / 0–100 component
  if (n > 10) return Math.max(0, Math.min(100, Math.round(n)))
  // Rare: already on 1–10 — expand to %
  return Math.max(0, Math.min(100, Math.round(n * 10)))
}

function BreakdownBar({ label, value }: { label: string; value?: unknown }) {
  const pct = asPercent(value)
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{pct == null ? '—' : `${pct}%`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-foreground/80 transition-[width]"
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
    </div>
  )
}

export function JobResumesPage() {
  const { jobId = '' } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canWrite = user?.role !== 'viewer'

  const job = useQuery({
    queryKey: queryKeys.jobPosting(jobId),
    queryFn: () => getJobPosting(jobId),
    enabled: Boolean(jobId),
  })
  const resumes = useQuery({
    queryKey: queryKeys.jobResumes(jobId),
    queryFn: () => listJobResumes(jobId),
    enabled: Boolean(jobId),
  })

  const [resumeFiles, setResumeFiles] = useState<File[]>([])
  const [stage, setStage] = useState<UploadStage>('idle')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [uploadKey, setUploadKey] = useState(0)
  const [showUploadPanel, setShowUploadPanel] = useState(false)
  const [jdPreviewOpen, setJdPreviewOpen] = useState(false)
  const [isEditingJdText, setIsEditingJdText] = useState(false)
  const [jdTextDraft, setJdTextDraft] = useState('')
  const [cvPreviewDocumentId, setCvPreviewDocumentId] = useState<string | null>(null)
  const [isEditingCvText, setIsEditingCvText] = useState(false)
  const [cvTextDraft, setCvTextDraft] = useState('')
  const [scoring, setScoring] = useState(false)
  const [scoringCandidateId, setScoringCandidateId] = useState<string | null>(null)
  const [schedulingCandidateId, setSchedulingCandidateId] = useState<string | null>(null)
  const [scoreDetailResume, setScoreDetailResume] = useState<JobResume | null>(null)

  const busy = stage !== 'idle'
  const jdReady = Boolean(
    job.data?.jd_text?.trim()
    || (job.data?.jd_document_id && job.data.pipeline_status === 'ready'),
  )
  const resumeRows = resumes.data ?? []

  useEffect(() => {
    if (!scoreDetailResume) return
    const latest = resumeRows.find((r) => r.document_id === scoreDetailResume.document_id)
    if (latest && latest !== scoreDetailResume) {
      setScoreDetailResume(latest)
    }
  }, [resumeRows, scoreDetailResume])

  const unscoredCount = resumeRows.filter(isUnscored).length
  const scoredCount = resumeRows.filter((r) => isScoreable(r) && r.match_score != null).length
  const scoreableCount = resumeRows.filter(isScoreable).length
  const notScoreableCount = resumeRows.filter(
    (r) => Boolean(r.candidate_id) && !isScoreable(r),
  ).length
  const canGetScore = Boolean(
    canWrite && jdReady && resumeRows.length > 0 && unscoredCount > 0,
  )
  const canRescore = Boolean(
    canWrite && jdReady && resumeRows.length > 0 && unscoredCount === 0 && scoredCount > 0,
  )
  const getScoreTitle = !jdReady
    ? 'Process the JD before scoring'
    : resumeRows.length === 0
      ? 'Upload resumes before scoring'
      : scoreableCount === 0
        ? 'No CV has enough extracted text to score yet (open Preview and save CV text, or re-parse)'
        : unscoredCount === 0
          ? canRescore
            ? 'Re-score only if JD or CV text changed — unchanged pairs keep their score'
            : 'All scoreable CVs are already scored'
          : `Score ${unscoredCount} unscored CV${unscoredCount === 1 ? '' : 's'} against this JD (1–10)`
  const jdDocument = useQuery({
    queryKey: ['document', job.data?.jd_document_id],
    queryFn: () => getDocument(job.data!.jd_document_id!),
    enabled: Boolean(
      jdPreviewOpen
      && job.data?.jd_document_id
      && !job.data.jd_text?.trim(),
    ),
  })
  const jdPreviewText =
    job.data?.jd_text?.trim()
    || jdDocument.data?.extracted_text?.trim()
    || ''

  useEffect(() => {
    if (!jdPreviewOpen) {
      setIsEditingJdText(false)
      setJdTextDraft('')
      return
    }
    if (jdDocument.isLoading && !jdPreviewText) return
    if (!isEditingJdText) {
      setJdTextDraft(jdPreviewText)
    }
  }, [jdPreviewOpen, jdPreviewText, jdDocument.isLoading, isEditingJdText])

  const saveJdTextMutation = useMutation({
    mutationFn: async () => {
      if (!jobId) throw new Error('Job not found.')
      const updated = jdTextDraft.trim()
      if (updated.length < 100) {
        throw new Error('JD text must be at least 100 characters.')
      }
      return updateJobPosting(jobId, { jd_text: updated })
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.jobPosting(jobId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobPostings }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobResumes(jobId) }),
      ])
      setIsEditingJdText(false)
      setSuccess('Job description updated. Fit scores were cleared — rescore when ready.')
    },
    onError: (nextError) => {
      setError(errorMessage(nextError))
    },
  })

  const cvPreviewDocument = useQuery({
    queryKey: ['document', cvPreviewDocumentId],
    queryFn: () => getDocument(cvPreviewDocumentId!),
    enabled: Boolean(cvPreviewDocumentId),
  })
  const selectedResume = (resumes.data ?? []).find((resume) => resume.document_id === cvPreviewDocumentId) ?? null
  const cvPreviewText =
    selectedResume?.cv_text?.trim()
    || cvPreviewDocument.data?.extracted_text?.trim()
    || ''

  useEffect(() => {
    if (!selectedResume) {
      setIsEditingCvText(false)
      setCvTextDraft('')
      return
    }
    setIsEditingCvText(false)
    setCvTextDraft(selectedResume.cv_text?.trim() || cvPreviewDocument.data?.extracted_text?.trim() || '')
  }, [selectedResume, cvPreviewDocument.data?.extracted_text])

  const saveCvTextMutation = useMutation({
    mutationFn: async () => {
      if (!selectedResume?.candidate_id) {
        throw new Error('Candidate profile is not ready yet.')
      }
      const updated = cvTextDraft.trim()
      if (updated.length < 50) {
        throw new Error('CV text must be at least 50 characters.')
      }
      return updateCandidate(selectedResume.candidate_id, {
        cv_text: updated,
      })
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.jobResumes(jobId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.candidates }),
      ])
      setIsEditingCvText(false)
      setSuccess('CV extracted text updated.')
    },
    onError: (nextError) => {
      setError(errorMessage(nextError))
    },
  })

  function selectResumes(files: File[]) {
    setError(null)
    setSuccess(null)
    if (files.length > MAX_FILES) {
      setError(`Select a maximum of ${MAX_FILES} resumes per batch.`)
      return
    }
    const oversized = files.find((file) => file.size > MAX_BYTES)
    if (oversized) {
      setError(`${oversized.name} exceeds the 20 MB file limit.`)
      return
    }
    setResumeFiles(files)
  }

  async function processResumes() {
    if (!jobId || !jdReady) {
      setError('This job needs a successfully processed JD before resumes can be uploaded.')
      return
    }
    if (resumeFiles.length < 1 || resumeFiles.length > MAX_FILES) {
      setError(`Select between 1 and ${MAX_FILES} resumes.`)
      return
    }

    setError(null)
    setSuccess(null)
    try {
      setStage('uploading')
      const uploaded = await uploadJobResumes(jobId, resumeFiles)
      setStage('extracting')
      await extractUploadBatch(uploaded.batch_id)
      setStage('parsing')
      const parsed = await parseUploadBatch(uploaded.batch_id)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.jobResumes(jobId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.candidates }),
      ])
      setSuccess(
        `${parsed.parsed + parsed.skipped_already_parsed} candidate profile${
          parsed.parsed + parsed.skipped_already_parsed === 1 ? '' : 's'
        } processed${parsed.failed ? ` · ${parsed.failed} failed` : ''}.`,
      )
      setResumeFiles([])
      setUploadKey((current) => current + 1)
      setShowUploadPanel(false)
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setStage('idle')
    }
  }

  async function runGetScore(opts?: {
    force?: boolean
    candidateIds?: string[]
  }) {
    if (!jobId) return
    const force = Boolean(opts?.force)
    const candidateIds = opts?.candidateIds
    const isRowRescore = Boolean(candidateIds?.length)
    if (!isRowRescore) {
      if (!force && !canGetScore) return
      if (force && !canRescore && !canGetScore) return
    }
    setError(null)
    setSuccess(null)
    setScoring(true)
    if (isRowRescore && candidateIds?.[0]) setScoringCandidateId(candidateIds[0])
    try {
      const result = await scoreJobMatches(jobId, {
        ...(force || isRowRescore ? { force: true } : {}),
        ...(candidateIds?.length ? { candidate_ids: candidateIds } : {}),
      })
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobResumes(jobId) })
      const unchanged = result.skipped_unchanged ?? 0
      const parts = [
        result.scored
          ? `${result.scored} CV${result.scored === 1 ? '' : 's'} scored (1–10) against this JD`
          : unchanged > 0
            ? 'Scores unchanged — JD and CV text are the same'
            : 'No new CVs scored',
      ]
      if (!force && !isRowRescore && result.skipped_already_scored) {
        parts.push(`${result.skipped_already_scored} already scored (skipped)`)
      }
      if ((force || isRowRescore) && unchanged > 0 && result.scored > 0) {
        parts.push(`${unchanged} unchanged (kept)`)
      }
      if (result.skipped_no_text) {
        parts.push(`${result.skipped_no_text} missing CV text`)
      }
      if (result.failed) {
        parts.push(`${result.failed} failed`)
      }
      setSuccess(parts.join(' · '))
      // Keep detail panel in sync after row rescore
      if (scoreDetailResume?.candidate_id && candidateIds?.includes(scoreDetailResume.candidate_id)) {
        const refreshed = (await listJobResumes(jobId)).find(
          (r) => r.candidate_id === scoreDetailResume.candidate_id,
        )
        if (refreshed) setScoreDetailResume(refreshed)
      }
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setScoring(false)
      setScoringCandidateId(null)
    }
  }

  const scheduleInterviewFromResume = async (resume: JobResume) => {
    const candidateId = resume.candidate_id
    const jobRow = job.data
    if (!candidateId || !jobId) {
      setError('This resume is not linked to a candidate profile yet.')
      return
    }
    if (!jobRow) {
      setError('Job details are still loading. Try again in a moment.')
      return
    }

    setError(null)
    setSchedulingCandidateId(candidateId)
    try {
      let jd = jobRow.jd_text?.trim() || ''
      if (jd.length < 100 && jobRow.jd_document_id) {
        const doc = await getDocument(jobRow.jd_document_id)
        jd = doc.extracted_text?.trim() || ''
      }
      const cv = resume.cv_text?.trim() || ''
      if (jd.length < 100) {
        setError(
          'Job description text is missing. Open Preview JD and ensure the JD is processed before scheduling.',
        )
        return
      }
      if (cv.length < 50) {
        setError(
          'This CV has no usable resume text yet. Open Preview CV, save the text, then try again.',
        )
        return
      }

      const { first, last } = splitFullName(resume.full_name || '')
      clearInterviewDraft()
      saveInterviewDraft({
        meeting_url: '',
        bot_name: 'Prabhat',
        candidate_first_name: first,
        candidate_last_name: last,
        language_mode: 'english',
        position_name: jobRow.job_title,
        jdText: jd,
        cvText: cv,
        greeting_message: '',
        questions: [
          {
            id: '1',
            difficulty: 'Low',
            source: 'jd',
            question: '',
          },
        ],
      })
      saveInterviewDraftMeta({
        cvFileName: null,
        jdFileName: null,
        wizardStep: 5,
        jobPostingId: jobId,
        candidateId,
        jdStructured: { jd_summary: jd },
        cvStructured: {
          name: resume.full_name || undefined,
          raw_text: cv,
        },
        questionsGenerated: false,
        extractionId: null,
        atsJobExternalId: jobRow.external_ats_id ?? null,
        pendingAtsJobExternalId: null,
        pendingAtsCandidateExternalId: null,
        pendingAtsCandidateParentId: null,
      })
      navigate({
        pathname: '/interviews/new',
        search: `?jobId=${encodeURIComponent(jobId)}&candidateId=${encodeURIComponent(candidateId)}`,
      })
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setSchedulingCandidateId(null)
    }
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,rgba(0,0,0,0.06),transparent)]"
      />

      <div className="relative z-[1] flex min-h-0 flex-1 flex-col gap-4">
        <header className="shrink-0">
          <button
            type="button"
            onClick={() => navigate('/jobs/bulk-upload')}
            className="group mb-3 inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5 transition-transform duration-200 group-hover:-translate-x-0.5" />
            Job descriptions
          </button>

          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <h1 className="truncate text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
                  {job.data?.job_title ?? 'Role'}
                </h1>
                <span
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium',
                    jdReady
                      ? 'border-success/25 bg-success/8 text-success'
                      : 'border-warning/30 bg-warning/8 text-warning',
                  )}
                >
                  <span className={cn('h-1.5 w-1.5 rounded-full', jdReady ? 'bg-success' : 'bg-warning')} />
                  {jdReady ? 'JD ready' : 'JD pending'}
                </span>
                {scoredCount > 0 && unscoredCount === 0 ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-success">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    All scored
                  </span>
                ) : null}
              </div>
              <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">
                Shortlist for this role only · fit scored 1–10
                {unscoredCount > 0 ? ` · ${unscoredCount} waiting` : ''}
                {notScoreableCount > 0 ? ` · ${notScoreableCount} need CV text` : ''}
              </p>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-3">
              <div className="flex overflow-hidden rounded-lg border border-border bg-card">
                {(
                  [
                    ['CVs', resumeRows.length],
                    ['Scored', scoredCount],
                    ['Open', unscoredCount],
                  ] as const
                ).map(([label, value], i) => (
                  <div
                    key={label}
                    className={cn(
                      'flex min-w-[4.25rem] flex-col px-3.5 py-2',
                      i > 0 && 'border-l border-border',
                    )}
                  >
                    <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {label}
                    </span>
                    <span className="text-lg font-semibold tabular-nums leading-none tracking-tight">
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              <div className="flex items-center rounded-lg border border-border bg-card p-1 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
                {jdReady ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-9 rounded-md px-3"
                    onClick={() => setJdPreviewOpen(true)}
                  >
                    <Eye className="h-4 w-4" />
                    Preview JD
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant={showUploadPanel ? 'secondary' : 'ghost'}
                  size="sm"
                  className="h-9 rounded-md px-3"
                  disabled={!jdReady || !canWrite}
                  onClick={() => setShowUploadPanel((current) => !current)}
                >
                  <UploadCloud className="h-4 w-4" />
                  {showUploadPanel ? 'Hide upload' : 'Upload'}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  className="h-9 min-w-[8rem] rounded-md px-4"
                  disabled={(!canGetScore && !canRescore) || scoring || busy}
                  title={getScoreTitle}
                  onClick={() => void runGetScore({ force: canRescore && !canGetScore })}
                >
                  {scoring ? <Loader2 className="h-4 w-4 animate-spin" /> : <Gauge className="h-4 w-4" />}
                  {scoring
                    ? 'Scoring…'
                    : canGetScore
                      ? `Score ${unscoredCount}`
                      : canRescore
                        ? 'Rescore all'
                        : 'Score'}
                </Button>
              </div>
            </div>
          </div>
        </header>

        <FlashAlert
          message={error}
          onDismiss={() => setError(null)}
          className="shrink-0 border-destructive/40 text-destructive"
        />
        <FlashAlert
          message={success}
          onDismiss={() => setSuccess(null)}
          className="shrink-0 border-success/30 bg-success/[0.06] text-success"
        />
        {!canWrite ? (
          <Alert className="shrink-0">Viewer accounts can inspect CVs but cannot upload documents.</Alert>
        ) : null}
        {!job.isLoading && !jdReady ? (
          <Alert className="shrink-0">
            Return to the JD dashboard and process this job description before uploading CVs.
          </Alert>
        ) : null}
        {jdReady && scoreableCount === 0 && resumeRows.length > 0 ? (
          <Alert className="shrink-0 border-warning/30 bg-warning/5">
            Profiles exist but no usable CV text was found for scoring. Open Preview → edit/save CV
            text, or re-run extract/parse on the uploads.
          </Alert>
        ) : null}

        {showUploadPanel ? (
          <section className="shrink-0 overflow-hidden rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
              <div>
                <h2 className="text-sm font-semibold tracking-tight">Upload resumes</h2>
                <p className="text-xs text-muted-foreground">
                  1–50 files · linked only to this job
                </p>
              </div>
            </div>
            <div className={cn('p-5', !jdReady && 'opacity-65')}>
              <div className="grid items-start gap-4 lg:grid-cols-[1fr_auto]">
                <FileDropzone
                  key={uploadKey}
                  id={`resume-files-${uploadKey}`}
                  title="Drop resumes here"
                  hint="PDF, DOC, DOCX, or scanned image · max 20 MB each"
                  selectedLabel={
                    resumeFiles.length
                      ? `${resumeFiles.length} resume${resumeFiles.length === 1 ? '' : 's'} selected`
                      : undefined
                  }
                  multiple
                  disabled={!jdReady || busy || !canWrite}
                  onFiles={selectResumes}
                />
                <Button
                  type="button"
                  className="h-11 px-6 lg:mt-5"
                  onClick={processResumes}
                  disabled={!jdReady || busy || !canWrite || resumeFiles.length < 1}
                >
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                  {UPLOAD_STAGE_LABELS[stage]}
                </Button>
              </div>

              {resumeFiles.length ? (
                <div className="mt-4 overflow-hidden rounded-lg border border-border">
                  <div className="grid grid-cols-[minmax(0,1fr)_100px_44px] bg-muted/50 px-4 py-2 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                    <span>Selected</span>
                    <span>Size</span>
                    <span />
                  </div>
                  <div className="max-h-44 divide-y divide-border overflow-y-auto">
                    {resumeFiles.map((file, index) => (
                      <div
                        key={`${file.name}-${file.size}-${index}`}
                        className="grid grid-cols-[minmax(0,1fr)_100px_44px] items-center px-4 py-2.5 text-sm"
                      >
                        <span className="truncate">{file.name}</span>
                        <span className="text-xs text-muted-foreground">{bytesLabel(file.size)}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${file.name}`}
                          disabled={busy}
                          onClick={() => {
                            setResumeFiles((current) =>
                              current.filter((_, itemIndex) => itemIndex !== index),
                            )
                          }}
                          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
          <div className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border px-4 sm:px-5">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold tracking-tight">Candidates</h2>
              <p className="text-[11px] leading-none text-muted-foreground">
                Click fit score for breakdown · ranked against this JD
              </p>
            </div>
            <span className="rounded-md border border-border bg-muted/40 px-2 py-0.5 text-[11px] font-medium tabular-nums text-muted-foreground">
              {resumeRows.length} total
            </span>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {resumeRows.length > 0 ? (
              <table className="w-full min-w-[980px] table-fixed text-left">
                <thead className="sticky top-0 z-10 border-b border-border bg-card/95 backdrop-blur-sm">
                  <tr className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                    <th className="w-12 px-4 py-2.5 font-medium">#</th>
                    <th className="w-[22%] px-3 py-2.5 font-medium">Candidate</th>
                    <th className="w-[16%] px-3 py-2.5 font-medium">Resume</th>
                    <th className="w-[14%] px-3 py-2.5 font-medium">Title</th>
                    <th className="w-[10%] px-3 py-2.5 font-medium">JD fit</th>
                    <th className="w-[12%] px-3 py-2.5 font-medium">Status</th>
                    <th className="w-[10%] px-3 py-2.5 font-medium">Uploaded</th>
                    <th className="w-[168px] px-3 py-2.5 pr-4 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {resumeRows.map((resume, index) => {
                    const fitTitle = [
                      resume.match_summary,
                      resume.match_rank != null ? `Rank #${resume.match_rank}` : null,
                      resume.match_score != null ? 'Click for breakdown' : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')
                    const rowScoring =
                      scoring &&
                      scoringCandidateId != null &&
                      scoringCandidateId === resume.candidate_id
                    const rowScheduling = schedulingCandidateId === resume.candidate_id
                    const displayRank = resume.match_rank ?? index + 1
                    const canSchedule = Boolean(
                      canWrite && resume.candidate_id && isScoreable(resume) && jdReady,
                    )
                    return (
                      <tr
                        key={resume.document_id}
                        className="group border-b border-border/70 transition-colors duration-150 last:border-b-0 hover:bg-muted/40"
                      >
                        <td className="px-4 py-3 align-middle">
                          <span className="text-xs font-medium tabular-nums text-muted-foreground">
                            {String(displayRank).padStart(2, '0')}
                          </span>
                        </td>
                        <td className="px-3 py-3 align-middle">
                          <div className="flex min-w-0 items-center gap-3">
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-foreground transition-transform duration-200 group-hover:scale-[1.04]">
                              <UserRound className="h-4 w-4" />
                            </span>
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium tracking-tight">
                                {resume.full_name || 'Candidate processing'}
                              </p>
                              <p className="truncate text-xs text-muted-foreground">
                                {resume.email || 'No email'}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-3 align-middle">
                          <div className="flex min-w-0 items-start gap-2">
                            <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                            <div className="min-w-0">
                              <p className="truncate text-sm">
                                {resume.original_filename || 'Uploaded resume'}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                {bytesLabel(resume.file_size_bytes)}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-3 align-middle text-sm text-muted-foreground">
                          <span className="line-clamp-2" title={resume.current_title || undefined}>
                            {resume.current_title || '—'}
                          </span>
                        </td>
                        <td className="px-3 py-3 align-middle">
                          {resume.match_score != null ? (
                            <button
                              type="button"
                              className="rounded-md outline-none transition-opacity hover:opacity-75 focus-visible:ring-2 focus-visible:ring-ring"
                              title={fitTitle || undefined}
                              onClick={() => {
                                const latest =
                                  resumeRows.find((r) => r.document_id === resume.document_id) ??
                                  resume
                                setScoreDetailResume(latest)
                              }}
                            >
                              <FitScoreMark score={resume.match_score} />
                            </button>
                          ) : (
                            <FitScoreMark score={resume.match_score} />
                          )}
                        </td>
                        <td className="px-3 py-3 align-middle">{resumeStatus(resume)}</td>
                        <td className="px-3 py-3 align-middle text-sm whitespace-nowrap text-muted-foreground">
                          {formatDate(resume.created_at)}
                        </td>
                        <td className="px-3 py-3 pr-4 align-middle">
                          <div className="flex justify-end">
                            <div className="inline-flex h-8 items-center rounded-md border border-border bg-card p-0.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 shrink-0 rounded-[5px]"
                                title="Preview CV"
                                onClick={() => setCvPreviewDocumentId(resume.document_id)}
                              >
                                <Eye className="h-3.5 w-3.5" />
                              </Button>
                              {canWrite && isScoreable(resume) ? (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="h-7 w-7 shrink-0 rounded-[5px]"
                                  disabled={scoring || busy || !jdReady}
                                  title={
                                    resume.match_score != null
                                      ? 'Re-score only if this CV or the JD changed'
                                      : 'Score this CV against the JD'
                                  }
                                  onClick={() =>
                                    void runGetScore({
                                      force: true,
                                      candidateIds: [resume.candidate_id!],
                                    })
                                  }
                                >
                                  {rowScoring ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <RefreshCcw className="h-3.5 w-3.5" />
                                  )}
                                </Button>
                              ) : null}
                              {canWrite && resume.candidate_id ? (
                                <>
                                  <span
                                    className="mx-0.5 h-4 w-px shrink-0 bg-border"
                                    aria-hidden
                                  />
                                  <Button
                                    type="button"
                                    size="sm"
                                    className="h-7 shrink-0 gap-1.5 rounded-[5px] px-2.5 text-[11px] font-medium"
                                    disabled={busy || !canSchedule || rowScheduling}
                                    title={
                                      !jdReady
                                        ? 'JD must be ready before scheduling'
                                        : !isScoreable(resume)
                                          ? 'CV text is required before scheduling'
                                          : 'Schedule interview with this job and candidate'
                                    }
                                    onClick={() => void scheduleInterviewFromResume(resume)}
                                  >
                                    {rowScheduling ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <CalendarPlus className="h-3.5 w-3.5" />
                                    )}
                                    Schedule
                                  </Button>
                                </>
                              ) : null}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            ) : null}

            {!resumes.isLoading && resumeRows.length === 0 ? (
              <div className="flex h-full min-h-[280px] flex-col items-center justify-center px-6 py-16 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-dashed border-border bg-muted/30">
                  <FileText className="h-7 w-7 text-muted-foreground" />
                </div>
                <p className="mt-5 text-base font-semibold tracking-tight">No resumes yet</p>
                <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted-foreground">
                  Upload CVs for this role, then score them against the job description.
                </p>
                {canWrite && jdReady ? (
                  <Button
                    type="button"
                    className="mt-6 h-10 px-5"
                    onClick={() => setShowUploadPanel(true)}
                  >
                    <UploadCloud className="h-4 w-4" />
                    Upload resumes
                  </Button>
                ) : null}
              </div>
            ) : null}
            {resumes.isLoading ? (
              <div className="flex h-full min-h-[240px] items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading resumes…
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <Dialog
        open={Boolean(scoreDetailResume)}
        onOpenChange={(open) => {
          if (!open) setScoreDetailResume(null)
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex flex-wrap items-center gap-2">
              <span>JD fit</span>
              {scoreDetailResume ? scoreBadge(scoreDetailResume.match_score) : null}
              {scoreDetailResume?.match_rank != null ? (
                <span className="text-sm font-normal text-muted-foreground">
                  Rank #{scoreDetailResume.match_rank}
                </span>
              ) : null}
            </DialogTitle>
            <DialogDescription>
              {scoreDetailResume?.full_name || 'Candidate'} · scored against this job only
            </DialogDescription>
          </DialogHeader>
          {scoreDetailResume ? (
            <div className="space-y-4">
              {scoreDetailResume.match_summary ? (
                <p className="rounded-lg border bg-muted/20 px-3 py-2.5 text-sm leading-relaxed">
                  {scoreDetailResume.match_summary}
                </p>
              ) : null}

              <div className="space-y-3 rounded-lg border px-3 py-3">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Breakdown
                </p>
                <BreakdownBar
                  label="Skills match"
                  value={scoreDetailResume.match_breakdown?.skills_match}
                />
                <BreakdownBar
                  label="Experience fit"
                  value={scoreDetailResume.match_breakdown?.experience_fit}
                />
                <BreakdownBar
                  label="Skill usage"
                  value={scoreDetailResume.match_breakdown?.skill_usage}
                />
                <BreakdownBar
                  label="Domain alignment"
                  value={scoreDetailResume.match_breakdown?.domain_alignment}
                />
                {!scoreDetailResume.match_breakdown
                  || (
                    scoreDetailResume.match_breakdown.skills_match == null
                    && scoreDetailResume.match_breakdown.experience_fit == null
                    && scoreDetailResume.match_breakdown.skill_usage == null
                    && scoreDetailResume.match_breakdown.domain_alignment == null
                  ) ? (
                  <p className="text-xs text-muted-foreground">
                    No component breakdown stored for this score. Click Rescore to regenerate percentages.
                  </p>
                ) : null}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border px-3 py-2.5">
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Strengths
                  </p>
                  {(scoreDetailResume.match_reasons?.strengths?.length ?? 0) > 0 ? (
                    <ul className="list-disc space-y-1 pl-4 text-sm">
                      {scoreDetailResume.match_reasons!.strengths!.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">No strengths listed.</p>
                  )}
                </div>
                <div className="rounded-lg border px-3 py-2.5">
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Gaps
                  </p>
                  {(scoreDetailResume.match_reasons?.gaps?.length ?? 0) > 0 ? (
                    <ul className="list-disc space-y-1 pl-4 text-sm">
                      {scoreDetailResume.match_reasons!.gaps!.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">No gaps listed.</p>
                  )}
                </div>
              </div>

              {((scoreDetailResume.match_reasons?.matched_skills?.length ?? 0) > 0
                || (scoreDetailResume.match_reasons?.missing_skills?.length ?? 0) > 0) ? (
                <div className="space-y-2 text-xs">
                  {(scoreDetailResume.match_reasons?.matched_skills?.length ?? 0) > 0 ? (
                    <p>
                      <span className="font-medium text-muted-foreground">Matched: </span>
                      {scoreDetailResume.match_reasons!.matched_skills!.slice(0, 12).join(', ')}
                    </p>
                  ) : null}
                  {(scoreDetailResume.match_reasons?.missing_skills?.length ?? 0) > 0 ? (
                    <p>
                      <span className="font-medium text-muted-foreground">Missing: </span>
                      {scoreDetailResume.match_reasons!.missing_skills!.slice(0, 12).join(', ')}
                    </p>
                  ) : null}
                </div>
              ) : null}

              {canWrite && scoreDetailResume.candidate_id ? (
                <div className="flex justify-end border-t pt-3">
                  <Button
                    type="button"
                    size="sm"
                    disabled={scoring || !jdReady}
                    onClick={() =>
                      void runGetScore({
                        force: true,
                        candidateIds: [scoreDetailResume.candidate_id!],
                      })
                    }
                  >
                    {scoring && scoringCandidateId === scoreDetailResume.candidate_id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCcw className="h-4 w-4" />
                    )}
                    Rescore this CV
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog
        open={jdPreviewOpen}
        onOpenChange={(open) => {
          setJdPreviewOpen(open)
          if (!open) {
            setIsEditingJdText(false)
          }
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{job.data?.job_title ?? 'Job description'}</DialogTitle>
            <DialogDescription>
              Stored job description used for this CV dashboard.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-muted-foreground">JD text</p>
              {canWrite ? (
                isEditingJdText ? (
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={saveJdTextMutation.isPending}
                      onClick={() => {
                        setIsEditingJdText(false)
                        setJdTextDraft(jdPreviewText)
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      disabled={saveJdTextMutation.isPending}
                      onClick={() => {
                        setError(null)
                        setSuccess(null)
                        void saveJdTextMutation.mutateAsync()
                      }}
                    >
                      {saveJdTextMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : null}
                      Save
                    </Button>
                  </div>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={jdDocument.isLoading}
                    onClick={() => {
                      setJdTextDraft(jdPreviewText)
                      setIsEditingJdText(true)
                    }}
                  >
                    Edit
                  </Button>
                )
              ) : null}
            </div>
            {jdDocument.isLoading && !jdPreviewText ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading job description…
              </div>
            ) : isEditingJdText ? (
              <Textarea
                value={jdTextDraft}
                onChange={(event) => setJdTextDraft(event.target.value)}
                className="min-h-[320px] max-h-[55vh] font-mono text-sm leading-6"
              />
            ) : jdPreviewText ? (
              <div className="max-h-[55vh] overflow-auto rounded-md bg-muted/20 px-4 py-3">
                <p className="whitespace-pre-wrap text-sm leading-6">{jdPreviewText}</p>
              </div>
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">
                The JD is processed, but preview text is unavailable.
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(cvPreviewDocumentId)}
        onOpenChange={(open) => {
          if (!open) {
            setCvPreviewDocumentId(null)
            setIsEditingCvText(false)
          }
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Candidate CV preview</DialogTitle>
            <DialogDescription>
              {cvPreviewDocument.data?.original_filename || 'Stored resume text for this candidate'}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">CV extracted text</p>
              {selectedResume?.candidate_id ? (
                isEditingCvText ? (
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={saveCvTextMutation.isPending}
                      onClick={() => {
                        setIsEditingCvText(false)
                        setCvTextDraft(cvPreviewText)
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      disabled={saveCvTextMutation.isPending}
                      onClick={() => {
                        setError(null)
                        setSuccess(null)
                        void saveCvTextMutation.mutateAsync()
                      }}
                    >
                      {saveCvTextMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : null}
                      Save
                    </Button>
                  </div>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setIsEditingCvText(true)}
                  >
                    Edit
                  </Button>
                )
              ) : (
                <p className="text-xs text-muted-foreground">Profile still processing</p>
              )}
            </div>
            <Textarea
              value={cvTextDraft}
              disabled={!isEditingCvText || !selectedResume?.candidate_id}
              onChange={(event) => setCvTextDraft(event.target.value)}
              className="min-h-[240px]"
            />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
