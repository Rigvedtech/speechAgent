import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ChevronRight,
  FilePlus2,
  FileText,
  Loader2,
  Plus,
  Search,
} from 'lucide-react'
import {
  createJobPosting,
  extractUploadBatch,
  listJobPostings,
  parseUploadBatch,
  uploadJobDescription,
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
import { Input } from '@/components/ui/input'
import type { JobPosting } from '@/types/api'

type CreateStage = 'idle' | 'creating' | 'uploading' | 'extracting' | 'parsing'

const MAX_BYTES = 20 * 1024 * 1024
const MAX_JD_FILES = 50

const CREATE_STAGE_LABELS: Record<CreateStage, string> = {
  idle: 'Create and process JD',
  creating: 'Creating job…',
  uploading: 'Uploading JD…',
  extracting: 'Extracting text…',
  parsing: 'Parsing requirements…',
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : 'Something went wrong'
}

function isJdReady(job: JobPosting) {
  return Boolean(
    job.jd_text?.trim()
    || (job.jd_document_id && job.pipeline_status === 'ready'),
  )
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function pipelineBadge(job: JobPosting) {
  if (isJdReady(job)) return <Badge variant="success">Ready</Badge>
  if (job.pipeline_status === 'failed') return <Badge variant="destructive">Failed</Badge>
  if (job.pipeline_status === 'processing') return <Badge variant="warning">Processing</Badge>
  return <Badge variant="secondary">{job.jd_document_id ? 'Pending' : 'JD required'}</Badge>
}

function fileStemAsTitle(fileName: string) {
  const rawStem = fileName.replace(/\.[^/.]+$/, '')
  const normalized = rawStem
    .replace(/[_\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (normalized.length >= 2) return normalized.slice(0, 255)
  return 'Untitled JD'
}

export function BulkUploadPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canWrite = user?.role !== 'viewer'
  const jobs = useQuery({
    queryKey: queryKeys.jobPostings,
    queryFn: () => listJobPostings(),
  })

  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [jdFiles, setJdFiles] = useState<File[]>([])
  const [createStage, setCreateStage] = useState<CreateStage>('idle')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const busy = createStage !== 'idle'
  const filteredJobs = useMemo(() => {
    const query = search.trim().toLowerCase()
    const localJobs = (jobs.data ?? []).filter((job) => job.source !== 'ats')
    if (!query) return localJobs
    return localJobs.filter((job) => job.job_title.toLowerCase().includes(query))
  }, [jobs.data, search])

  function setDialogOpen(open: boolean) {
    if (busy) return
    setCreateOpen(open)
    if (!open) {
      setJdFiles([])
      setError(null)
      setCreateStage('idle')
    }
  }

  function openJob(job: JobPosting) {
    navigate(`/jobs/${job.id}/resumes`)
  }

  async function createJd() {
    if (jdFiles.length < 1) {
      setError('Choose at least one JD file.')
      return
    }
    if (jdFiles.length > MAX_JD_FILES) {
      setError(`Select a maximum of ${MAX_JD_FILES} JD files per batch.`)
      return
    }
    const oversized = jdFiles.find((file) => file.size > MAX_BYTES)
    if (oversized) {
      setError(`${oversized.name} exceeds the 20 MB file limit.`)
      return
    }

    setError(null)
    setSuccess(null)
    let processed = 0
    const failed: string[] = []
    try {
      for (const jdFile of jdFiles) {
        const title = fileStemAsTitle(jdFile.name)
        try {
          setCreateStage('creating')
          const job = await createJobPosting({ job_title: title, source: 'upload' })
          setCreateStage('uploading')
          const uploaded = await uploadJobDescription(job.id, jdFile)
          setCreateStage('extracting')
          await extractUploadBatch(uploaded.batch_id)
          setCreateStage('parsing')
          const parsed = await parseUploadBatch(uploaded.batch_id)
          if (
            parsed.parsed + parsed.skipped_already_parsed < 1
            || parsed.failed > 0
            || parsed.skipped_no_text > 0
          ) {
            throw new Error('JD parsing failed')
          }
          processed += 1
        } catch (itemError) {
          failed.push(`${jdFile.name}: ${errorMessage(itemError)}`)
        }
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobPostings })
      setCreateStage('idle')
      if (failed.length === 0) {
        setCreateOpen(false)
        setJdFiles([])
        setSuccess(
          `${processed} job description${processed === 1 ? '' : 's'} created and processed.`,
        )
        return
      }
      const preview = failed.slice(0, 2).join(' | ')
      const extra = failed.length > 2 ? ` (+${failed.length - 2} more)` : ''
      setError(
        `Processed ${processed}/${jdFiles.length}. Failed ${failed.length}. ${preview}${extra}`,
      )
    } catch (nextError) {
      setCreateStage('idle')
      setError(errorMessage(nextError))
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobPostings })
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Job descriptions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Select a processed JD to view and upload its resumes.
          </p>
        </div>
        <Button
          type="button"
          disabled={!canWrite}
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="h-4 w-4" />
          Create new JD
        </Button>
      </div>

      {!canWrite ? <Alert>Viewer accounts cannot create or upload documents.</Alert> : null}
      {success ? <Alert className="border-success/30 bg-success/[0.06] text-success">{success}</Alert> : null}

      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between gap-4 border-b p-4">
            <div className="relative w-full max-w-sm">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search job descriptions"
                className="pl-9"
              />
            </div>
            <span className="whitespace-nowrap text-xs text-muted-foreground">
              {filteredJobs.length} {filteredJobs.length === 1 ? 'JD' : 'JDs'}
            </span>
          </div>

          <div className="max-h-[calc(100vh-15rem)] min-h-80 overflow-auto">
            <table className="w-full min-w-[760px] text-left">
              <thead className="sticky top-0 z-10 border-b bg-card text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-5 py-3 font-medium">Job description</th>
                  <th className="px-5 py-3 font-medium">Source</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Created</th>
                  <th className="w-12 px-5 py-3"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredJobs.map((job) => {
                  const ready = isJdReady(job)
                  return (
                    <tr
                      key={job.id}
                      tabIndex={0}
                      onClick={() => openJob(job)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') openJob(job)
                      }}
                      className="row-hover cursor-pointer"
                    >
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                            <FileText className="h-4 w-4" />
                          </span>
                          <div>
                            <p className="font-medium text-foreground">{job.job_title}</p>
                            <p className="mt-0.5 text-xs text-muted-foreground">
                              {ready
                                ? 'Click to open CV dashboard'
                                : 'Open CV dashboard · upload requires a processed JD'}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4 text-sm capitalize text-muted-foreground">{job.source}</td>
                      <td className="px-5 py-4">{pipelineBadge(job)}</td>
                      <td className="px-5 py-4 text-sm text-muted-foreground">{formatDate(job.created_at)}</td>
                      <td className="px-5 py-4">
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {!jobs.isLoading && filteredJobs.length === 0 ? (
            <div className="flex flex-col items-center px-6 py-16 text-center">
              <FilePlus2 className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 font-medium">No job descriptions found</p>
              <p className="mt-1 text-xs text-muted-foreground">Create a JD to start uploading resumes.</p>
            </div>
          ) : null}
          {jobs.isLoading ? (
            <div className="flex items-center justify-center gap-2 px-6 py-16 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading job descriptions…
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Create new job description</DialogTitle>
            <DialogDescription>
              Choose one or more JD files. Each file creates a separate job using the file name as title.
            </DialogDescription>
          </DialogHeader>

          {error ? <Alert className="border-destructive/40 text-destructive">{error}</Alert> : null}

          <div className="space-y-4">
            <FileDropzone
              id="new-jd-file"
              title={`Choose 1-${MAX_JD_FILES} JD files`}
              hint="PDF, DOC, DOCX, or scanned image · Maximum 20 MB each"
              selectedLabel={
                jdFiles.length
                  ? `${jdFiles.length} JD file${jdFiles.length === 1 ? '' : 's'} selected`
                  : undefined
              }
              multiple
              disabled={busy}
              onFiles={(files) => {
                setError(null)
                setSuccess(null)
                setJdFiles(files.slice(0, MAX_JD_FILES))
              }}
            />
            {jdFiles.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                First title preview:{' '}
                <span className="font-medium text-foreground">
                  {fileStemAsTitle(jdFiles[0].name)}
                </span>
              </p>
            ) : null}
            <Button
              type="button"
              className="w-full"
              onClick={createJd}
              disabled={busy || jdFiles.length < 1}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePlus2 className="h-4 w-4" />}
              {CREATE_STAGE_LABELS[createStage]}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
