import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  CheckCircle2,
  Eye,
  FileText,
  Loader2,
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
  updateCandidate,
  uploadJobResumes,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import { useAuth } from '@/hooks/useAuth'
import { FileDropzone } from '@/components/bulk-upload/FileDropzone'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
  const [cvPreviewDocumentId, setCvPreviewDocumentId] = useState<string | null>(null)
  const [isEditingCvText, setIsEditingCvText] = useState(false)
  const [cvTextDraft, setCvTextDraft] = useState('')

  const busy = stage !== 'idle'
  const jdReady = Boolean(
    job.data?.jd_text?.trim()
    || (job.data?.jd_document_id && job.data.pipeline_status === 'ready'),
  )
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

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-ml-3 mb-2 text-muted-foreground"
            onClick={() => navigate('/jobs/bulk-upload')}
          >
            <ArrowLeft className="h-4 w-4" />
            Job descriptions
          </Button>
          <h1 className="text-2xl font-semibold tracking-tight">
            {job.data?.job_title ?? 'CV dashboard'}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Resumes uploaded here are linked only to this job description.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {jdReady ? (
            <Button type="button" variant="outline" size="sm" onClick={() => setJdPreviewOpen(true)}>
              <Eye className="h-4 w-4" />
              Preview JD
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!jdReady || !canWrite}
            onClick={() => setShowUploadPanel((current) => !current)}
          >
            <UploadCloud className="h-4 w-4" />
            {showUploadPanel ? 'Hide upload' : 'Upload resumes'}
          </Button>
          <Badge variant={jdReady ? 'success' : 'warning'}>
            {jdReady ? <CheckCircle2 className="mr-1 h-3 w-3" /> : null}
            {jdReady ? 'JD ready' : 'JD not ready'}
          </Badge>
          <Badge variant="outline">{resumes.data?.length ?? 0} CVs</Badge>
        </div>
      </div>

      {error ? <Alert className="border-destructive/40 text-destructive">{error}</Alert> : null}
      {success ? <Alert className="border-success/30 bg-success/[0.06] text-success">{success}</Alert> : null}
      {!canWrite ? <Alert>Viewer accounts can inspect CVs but cannot upload documents.</Alert> : null}
      {!job.isLoading && !jdReady ? (
        <Alert>Return to the JD dashboard and process this job description before uploading CVs.</Alert>
      ) : null}

      {showUploadPanel ? (
        <Card className={!jdReady ? 'opacity-65' : 'border-foreground/20'}>
          <CardContent className="p-5">
            <div className="grid items-start gap-5 lg:grid-cols-[1fr_auto]">
              <FileDropzone
                key={uploadKey}
                id={`resume-files-${uploadKey}`}
                title="Choose 1–50 resume files"
                hint="PDF, DOC, DOCX, or scanned image · Maximum 20 MB each"
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
                className="h-11 px-6 lg:mt-6"
                onClick={processResumes}
                disabled={!jdReady || busy || !canWrite || resumeFiles.length < 1}
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                {UPLOAD_STAGE_LABELS[stage]}
              </Button>
            </div>

            {resumeFiles.length ? (
              <div className="mt-5 overflow-hidden rounded-lg border">
                <div className="grid grid-cols-[minmax(0,1fr)_100px_44px] bg-muted/30 px-4 py-2 text-xs uppercase tracking-wide text-muted-foreground">
                  <span>Selected resume</span>
                  <span>Size</span>
                  <span />
                </div>
                <div className="max-h-52 divide-y overflow-y-auto">
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
                        className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-destructive"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <h2 className="font-semibold">Candidate resumes</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                All CVs processed against this job description.
              </p>
            </div>
            <Badge variant="secondary">{resumes.data?.length ?? 0} total</Badge>
          </div>

          <div className="max-h-[calc(100vh-24rem)] min-h-56 overflow-auto">
            <table className="w-full min-w-[860px] text-left">
              <thead className="sticky top-0 z-10 border-b bg-card text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-5 py-3 font-medium">Candidate</th>
                  <th className="px-5 py-3 font-medium">Resume file</th>
                  <th className="px-5 py-3 font-medium">Current title</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Uploaded</th>
                  <th className="px-5 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(resumes.data ?? []).map((resume) => (
                  <tr key={resume.document_id} className="row-hover">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-foreground">
                          <UserRound className="h-4 w-4" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {resume.full_name || 'Candidate processing'}
                          </p>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">
                            {resume.email || 'No email extracted'}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0">
                          <p className="max-w-56 truncate text-sm">
                            {resume.original_filename || 'Uploaded resume'}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {bytesLabel(resume.file_size_bytes)}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-sm text-muted-foreground">
                      {resume.current_title || '—'}
                    </td>
                    <td className="px-5 py-4">
                      {resumeStatus(resume)}
                      {resume.error_message ? (
                        <p className="mt-1 max-w-52 text-xs text-destructive">{resume.error_message}</p>
                      ) : null}
                    </td>
                    <td className="px-5 py-4 text-sm text-muted-foreground">
                      {formatDate(resume.created_at)}
                    </td>
                    <td className="px-5 py-4">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setCvPreviewDocumentId(resume.document_id)}
                      >
                        <Eye className="h-4 w-4" />
                        Preview CV
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!resumes.isLoading && (resumes.data?.length ?? 0) === 0 ? (
            <div className="flex flex-col items-center px-6 py-16 text-center">
              <FileText className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 font-medium">No resumes uploaded yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Select resume files above to create candidate profiles for this JD.
              </p>
            </div>
          ) : null}
          {resumes.isLoading ? (
            <div className="flex items-center justify-center gap-2 px-6 py-16 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading resumes…
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={jdPreviewOpen} onOpenChange={setJdPreviewOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{job.data?.job_title ?? 'Job description'}</DialogTitle>
            <DialogDescription>Stored job description used for this CV dashboard.</DialogDescription>
          </DialogHeader>
          <div className="max-h-[65vh] overflow-auto rounded-lg border bg-muted/20 p-5">
            {jdDocument.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading job description…
              </div>
            ) : jdPreviewText ? (
              <p className="whitespace-pre-wrap text-sm leading-6">{jdPreviewText}</p>
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
