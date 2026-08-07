import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  Briefcase,
  ChevronDown,
  Eye,
  FileText,
  ListFilter,
  Loader2,
  Plug,
  Search,
  Users,
} from 'lucide-react'
import {
  getAtsJob,
  getAtsSettings,
  listAtsCandidates,
  listAtsJobs,
  openAtsFilePreview,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { truncate } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert } from '@/components/ui/alert'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useAuth } from '@/hooks/useAuth'
import type { AtsRemoteJob } from '@/types/api'

const PAGE_SIZE = 10

type StatusFilter = 'all' | 'open' | 'candidate_submission' | 'closed'

const STATUS_FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'open', label: 'Open' },
  { value: 'candidate_submission', label: 'Submission' },
  { value: 'closed', label: 'Closed' },
]

function jobStatusRaw(job: AtsRemoteJob): string {
  return (job.status || job.description || '').trim()
}

/** Normalize ATS status strings (Open, Candidate_Submission, Closed, …). */
function normalizeJobStatus(raw: string): StatusFilter | null {
  const key = raw.trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (!key) return null
  if (key === 'open' || key.startsWith('open_')) return 'open'
  if (
    key.includes('candidate_submission') ||
    key.includes('candidate_submiss') ||
    key === 'submission'
  ) {
    return 'candidate_submission'
  }
  if (key === 'closed' || key.startsWith('closed') || key === 'filled') return 'closed'
  return null
}

function formatStatusLabel(raw: string): string {
  const normalized = normalizeJobStatus(raw)
  if (normalized === 'open') return 'Open'
  if (normalized === 'candidate_submission') return 'Submission'
  if (normalized === 'closed') return 'Closed'
  return raw.replace(/_/g, ' ')
}

function matchesStatusFilter(job: AtsRemoteJob, filter: StatusFilter): boolean {
  if (filter === 'all') return true
  const bucket = normalizeJobStatus(jobStatusRaw(job))
  return bucket === filter
}

export function AtsBrowsePage() {
  const { requestId: requestIdParam } = useParams<{ requestId?: string }>()
  const requestId = requestIdParam ? decodeURIComponent(requestIdParam) : null
  const navigate = useNavigate()
  const { isAdmin } = useAuth()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [jobsPage, setJobsPage] = useState(1)
  const [jobsAccum, setJobsAccum] = useState<
    Awaited<ReturnType<typeof listAtsJobs>>['items']
  >([])
  const [jobsHasNext, setJobsHasNext] = useState(false)
  const [jobsTotal, setJobsTotal] = useState<number | null>(null)
  const [previewingId, setPreviewingId] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [jdOpen, setJdOpen] = useState(false)
  const [jdPreviewId, setJdPreviewId] = useState<string | null>(null)
  const [jdPreviewTitle, setJdPreviewTitle] = useState<string | null>(null)
  /** When status filter is on, keep loading ATS pages until we reach this many matches. */
  const matchTargetRef = useRef(PAGE_SIZE)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => window.clearTimeout(t)
  }, [search])

  useEffect(() => {
    setSearch('')
    setDebouncedSearch('')
    setPreviewError(null)
    setJdOpen(false)
    setJdPreviewId(null)
    setJdPreviewTitle(null)
  }, [requestId])

  useEffect(() => {
    if (requestId) return
    setJobsPage(1)
    setJobsAccum([])
    setJobsHasNext(false)
    setJobsTotal(null)
    matchTargetRef.current = PAGE_SIZE
  }, [debouncedSearch, requestId])

  useEffect(() => {
    matchTargetRef.current = PAGE_SIZE
  }, [statusFilter])

  const settings = useQuery({
    queryKey: queryKeys.atsSettings,
    queryFn: getAtsSettings,
  })

  const connected = Boolean(settings.data?.is_connected)

  const jobsQuery = useQuery({
    queryKey: [...queryKeys.atsJobs, 'browse', debouncedSearch, jobsPage, PAGE_SIZE],
    queryFn: () =>
      listAtsJobs({
        q: debouncedSearch || undefined,
        page: jobsPage,
        page_size: PAGE_SIZE,
      }),
    enabled: connected && !requestId,
    staleTime: 0,
  })

  useEffect(() => {
    if (requestId || !jobsQuery.data) return
    const page = jobsQuery.data
    setJobsHasNext(Boolean(page.has_next))
    setJobsTotal(page.total ?? null)
    setJobsAccum((prev) => {
      if (page.page <= 1) return page.items ?? []
      const seen = new Set(prev.map((j) => j.external_id))
      const merged = [...prev]
      for (const item of page.items ?? []) {
        if (!seen.has(item.external_id)) merged.push(item)
      }
      return merged
    })
  }, [requestId, jobsQuery.dataUpdatedAt, jobsQuery.data])

  const jobDetail = useQuery({
    queryKey: [...queryKeys.atsJobs, 'detail', requestId],
    queryFn: () => getAtsJob(requestId!),
    enabled: connected && Boolean(requestId),
  })

  const candidatesQuery = useQuery({
    queryKey: [...queryKeys.atsCandidates, 'browse', requestId, debouncedSearch],
    queryFn: () =>
      listAtsCandidates({
        q: debouncedSearch || undefined,
        request_id: requestId || undefined,
      }),
    enabled: connected && Boolean(requestId),
    staleTime: 0,
  })

  const candidates = useMemo(() => candidatesQuery.data ?? [], [candidatesQuery.data])

  const filteredJobs = useMemo(
    () => jobsAccum.filter((job) => matchesStatusFilter(job, statusFilter)),
    [jobsAccum, statusFilter],
  )

  // Status filter: keep fetching ATS pages until ~10 matches (or no more pages).
  useEffect(() => {
    if (requestId || statusFilter === 'all') return
    if (jobsQuery.isFetching || jobsQuery.isLoading || jobsQuery.isPending) return
    if (!jobsHasNext) return
    if (filteredJobs.length >= matchTargetRef.current) return
    if (jobsPage >= 40) return
    setJobsPage((p) => p + 1)
  }, [
    requestId,
    statusFilter,
    filteredJobs.length,
    jobsHasNext,
    jobsQuery.isFetching,
    jobsQuery.isLoading,
    jobsQuery.isPending,
    jobsPage,
  ])

  const listFromJobs = useMemo(() => {
    if (!requestId) return null
    return jobsAccum.find((j) => j.external_id === requestId) ?? null
  }, [jobsAccum, requestId])

  const headerTitle =
    jobDetail.data?.job_title ?? listFromJobs?.job_title ?? requestId ?? 'Requirement'
  const headerCompany =
    jobDetail.data?.company_name ?? listFromJobs?.company_name ?? null
  const headerStatus =
    jobDetail.data?.status ?? listFromJobs?.status ?? listFromJobs?.description ?? null
  const jdText = jobDetail.data?.jd_text?.trim() || null

  const jdPreviewQuery = useQuery({
    queryKey: [...queryKeys.atsJobs, 'jd-preview', jdPreviewId],
    queryFn: () => getAtsJob(jdPreviewId!),
    enabled: connected && Boolean(jdPreviewId),
  })

  const openJdTextPreview = (externalId: string, title?: string | null) => {
    setPreviewError(null)
    setJdPreviewTitle(title?.trim() || null)
    setJdPreviewId(externalId)
  }

  const previewCandidate = async (externalId: string) => {
    setPreviewingId(externalId)
    setPreviewError(null)
    try {
      await openAtsFilePreview('candidate', externalId, requestId || undefined)
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Could not open resume')
    } finally {
      setPreviewingId(null)
    }
  }

  const jdPreviewBody = jdPreviewQuery.data?.jd_text?.trim() || null
  const jdPreviewDialog = (
    <Dialog
      open={Boolean(jdPreviewId)}
      onOpenChange={(open) => {
        if (!open) {
          setJdPreviewId(null)
          setJdPreviewTitle(null)
        }
      }}
    >
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-3 overflow-hidden">
        <DialogHeader className="shrink-0 space-y-1.5 pr-6">
          <DialogTitle className="leading-snug">
            {jdPreviewQuery.data?.job_title || jdPreviewTitle || 'Job description'}
          </DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {jdPreviewId}
            {jdPreviewQuery.data?.company_name
              ? ` · ${jdPreviewQuery.data.company_name}`
              : ''}
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border bg-muted/20 px-3 py-3">
          {jdPreviewQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-5/6" />
              <Skeleton className="h-3 w-4/6" />
              <Skeleton className="h-3 w-3/4" />
            </div>
          ) : jdPreviewQuery.isError ? (
            <p className="text-sm text-destructive">
              {jdPreviewQuery.error instanceof ApiError
                ? formatApiError(
                    jdPreviewQuery.error.message,
                    jdPreviewQuery.error.detail,
                  )
                : 'Could not load job description.'}
            </p>
          ) : jdPreviewBody ? (
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">
              {jdPreviewBody}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">
              No job description text available for this requirement.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )

  if (settings.isLoading) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!connected) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Briefcase className="h-4 w-4" strokeWidth={1.5} />
            ATS jobs
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            Connect your ATS to browse requirements and candidate resumes linked to each
            job.
          </Alert>
          {isAdmin ? (
            <Button asChild>
              <Link to="/settings/ats">
                <Plug className="mr-2 h-4 w-4" strokeWidth={1.5} />
                Open ATS settings
              </Link>
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">
              Ask an org admin to connect ATS under Settings → ATS.
            </p>
          )}
        </CardContent>
      </Card>
    )
  }

  if (requestId) {
    return (
      <>
      <div className="flex h-full min-h-0 flex-col">
        <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <CardHeader className="shrink-0 space-y-4 pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="-ml-2 h-8 gap-1.5 px-2 text-muted-foreground"
                  onClick={() => navigate('/ats/jobs')}
                >
                  <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
                  Back to jobs
                </Button>
                <div>
                  <CardTitle className="text-lg leading-snug">{headerTitle}</CardTitle>
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    <span className="font-mono">{requestId}</span>
                    {headerCompany ? (
                      <>
                        <span aria-hidden>·</span>
                        <span>{headerCompany}</span>
                      </>
                    ) : null}
                    {headerStatus ? (
                      <Badge variant="secondary" className="font-normal">
                        {headerStatus}
                      </Badge>
                    ) : null}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => openJdTextPreview(requestId, headerTitle)}
                >
                  <Eye className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                  Preview JD
                </Button>
              </div>
            </div>

            {(jdText || jobDetail.isLoading) && (
              <Collapsible open={jdOpen} onOpenChange={setJdOpen}>
                <div className="rounded-lg border border-border bg-muted/20">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-medium hover:bg-muted/40"
                    >
                      <span className="flex items-center gap-2">
                        <FileText className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} />
                        Job description
                      </span>
                      <ChevronDown
                        className={`h-4 w-4 text-muted-foreground transition-transform ${
                          jdOpen ? 'rotate-180' : ''
                        }`}
                        strokeWidth={1.5}
                      />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="border-t border-border px-3 py-3">
                      {jobDetail.isLoading ? (
                        <div className="space-y-2">
                          <Skeleton className="h-3 w-full" />
                          <Skeleton className="h-3 w-5/6" />
                          <Skeleton className="h-3 w-4/6" />
                        </div>
                      ) : (
                        <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap font-sans text-xs leading-relaxed text-muted-foreground">
                          {jdText}
                        </pre>
                      )}
                    </div>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            )}

            <div className="relative w-full max-w-sm">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                strokeWidth={1.5}
              />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search candidates…"
                className="h-9 pl-9"
              />
            </div>

            {previewError ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {previewError}
              </p>
            ) : null}
            {jobDetail.isError ? (
              <p className="text-sm text-muted-foreground">
                Could not load full JD details; showing candidates for this requirement.
              </p>
            ) : null}
          </CardHeader>

          <CardContent className="min-h-0 flex-1 overflow-y-auto pb-4 pt-0">
            <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
              <Users className="h-3.5 w-3.5" strokeWidth={1.5} />
              {candidatesQuery.isLoading
                ? 'Loading candidates…'
                : `${candidates.length} candidate${candidates.length === 1 ? '' : 's'}`}
            </div>

            {candidatesQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-16 w-full rounded-md" />
                <Skeleton className="h-16 w-full rounded-md" />
                <Skeleton className="h-16 w-full rounded-md" />
              </div>
            ) : candidatesQuery.isError ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {candidatesQuery.error instanceof ApiError
                  ? formatApiError(
                      candidatesQuery.error.message,
                      candidatesQuery.error.detail,
                    )
                  : 'Could not load candidates for this requirement.'}
              </p>
            ) : candidates.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16 text-center">
                <Users className="mb-2 h-8 w-8 text-muted-foreground/50" strokeWidth={1.25} />
                <p className="text-sm font-medium">No candidates</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  ATS returned no resumes for this requirement.
                </p>
              </div>
            ) : (
              <ul className="space-y-2">
                {candidates.map((row) => (
                  <li
                    key={row.external_id}
                    className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-3.5 py-3 transition-colors hover:bg-muted/30"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-medium leading-tight">
                          {row.full_name}
                        </p>
                        {row.status ? (
                          <Badge variant="outline" className="font-normal">
                            {row.status}
                          </Badge>
                        ) : null}
                        {row.already_imported ? (
                          <Badge variant="secondary" className="font-normal">
                            In workspace
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-1 truncate text-[11px] text-muted-foreground">
                        <span className="font-mono">{row.external_id}</span>
                        {row.email ? (
                          <>
                            <span aria-hidden> · </span>
                            {row.email}
                          </>
                        ) : null}
                        {row.phone ? (
                          <>
                            <span aria-hidden> · </span>
                            {row.phone}
                          </>
                        ) : null}
                      </p>
                      {row.cv_filename ? (
                        <p className="mt-0.5 truncate text-[11px] text-muted-foreground/80">
                          {row.cv_filename}
                        </p>
                      ) : null}
                    </div>
                    {row.has_cv_url ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="shrink-0"
                        disabled={previewingId === row.external_id}
                        onClick={() => void previewCandidate(row.external_id)}
                      >
                        {previewingId === row.external_id ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Eye className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                        )}
                        Preview CV
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">No resume</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
      {jdPreviewDialog}
      </>
    )
  }

  const jobsLoading =
    (jobsAccum.length === 0 &&
      (jobsQuery.isLoading || jobsQuery.isFetching || jobsQuery.isPending)) ||
    (statusFilter !== 'all' &&
      filteredJobs.length < PAGE_SIZE &&
      jobsHasNext &&
      (jobsQuery.isFetching || jobsQuery.isLoading || jobsQuery.isPending))

  const filterFilling =
    statusFilter !== 'all' &&
    filteredJobs.length > 0 &&
    filteredJobs.length < matchTargetRef.current &&
    jobsHasNext &&
    (jobsQuery.isFetching || jobsQuery.isLoading)

  return (
    <>
    <div className="flex h-full min-h-0 flex-col">
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CardHeader className="shrink-0 space-y-4 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Briefcase className="h-4 w-4" strokeWidth={1.5} />
                ATS jobs
              </CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Browse requirements from your connected ATS. Open a job to see linked
                candidates and resumes.
              </p>
            </div>
            {isAdmin ? (
              <Button asChild variant="outline" size="sm">
                <Link to="/settings/ats">ATS settings</Link>
              </Button>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="relative min-w-[12rem] w-full max-w-sm">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                strokeWidth={1.5}
              />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search roles…"
                className="h-9 pl-9"
              />
            </div>
            <Select
              value={statusFilter}
              onValueChange={(v) => setStatusFilter(v as StatusFilter)}
            >
              <SelectTrigger className="h-9 w-[200px] shrink-0 bg-card" aria-label="Filter by status">
                <span className="flex min-w-0 items-center gap-2">
                  <ListFilter className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.5} />
                  <SelectValue placeholder="Status" />
                </span>
              </SelectTrigger>
              <SelectContent align="end">
                {STATUS_FILTER_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {previewError ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {previewError}
            </p>
          ) : null}
        </CardHeader>

        <CardContent className="min-h-0 flex-1 overflow-y-auto pb-4 pt-0">
          {jobsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full rounded-md" />
              <Skeleton className="h-16 w-full rounded-md" />
              <Skeleton className="h-16 w-full rounded-md" />
            </div>
          ) : jobsQuery.isError ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {jobsQuery.error instanceof ApiError
                ? formatApiError(jobsQuery.error.message, jobsQuery.error.detail)
                : 'Could not load jobs from ATS.'}
            </p>
          ) : jobsAccum.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16 text-center">
              <Briefcase className="mb-2 h-8 w-8 text-muted-foreground/50" strokeWidth={1.25} />
              <p className="text-sm font-medium">No requirements found</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Try another search or check the ATS connection.
              </p>
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16 text-center">
              {jobsQuery.isFetching || jobsHasNext ? (
                <>
                  <Loader2 className="mb-2 h-8 w-8 animate-spin text-muted-foreground/60" />
                  <p className="text-sm font-medium">Finding matching jobs…</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Loading more requirements to fill this filter.
                  </p>
                </>
              ) : (
                <>
                  <ListFilter className="mb-2 h-8 w-8 text-muted-foreground/50" strokeWidth={1.25} />
                  <p className="text-sm font-medium">No jobs match this status</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Try another filter or clear it to see all roles.
                  </p>
                  {statusFilter !== 'all' ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-4"
                      onClick={() => setStatusFilter('all')}
                    >
                      Clear status filter
                    </Button>
                  ) : null}
                </>
              )}
            </div>
          ) : (
            <ul className="space-y-2">
              {filteredJobs.map((row) => {
                const statusRaw = jobStatusRaw(row)
                const statusLabel = statusRaw ? formatStatusLabel(statusRaw) : null
                return (
                <li key={row.external_id}>
                  <button
                    type="button"
                    className="flex w-full flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-3.5 py-3 text-left transition-colors hover:border-foreground/15 hover:bg-muted/30"
                    onClick={() =>
                      navigate(`/ats/jobs/${encodeURIComponent(row.external_id)}`)
                    }
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-medium leading-tight">
                          {row.job_title}
                        </p>
                        {statusLabel ? (
                          <Badge variant="secondary" className="font-normal">
                            {statusLabel}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-1 truncate text-[11px] text-muted-foreground">
                        <span className="font-mono">{row.external_id}</span>
                        {row.company_name ? (
                          <>
                            <span aria-hidden> · </span>
                            {row.company_name}
                          </>
                        ) : null}
                        {!row.company_name &&
                        row.description &&
                        normalizeJobStatus(row.description) === null ? (
                          <>
                            <span aria-hidden> · </span>
                            {truncate(row.description, 80)}
                          </>
                        ) : null}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        title="Preview JD text"
                        onClick={(e) => {
                          e.stopPropagation()
                          openJdTextPreview(row.external_id, row.job_title)
                        }}
                      >
                        <Eye className="h-3.5 w-3.5" strokeWidth={1.5} />
                      </Button>
                      <span className="text-xs font-medium text-muted-foreground">
                        Open →
                      </span>
                    </div>
                  </button>
                </li>
                )
              })}
              {jobsHasNext || filterFilling ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="h-9 w-full gap-1 text-xs text-muted-foreground"
                  disabled={jobsQuery.isFetching || filterFilling}
                  onClick={() => {
                    if (statusFilter !== 'all') {
                      matchTargetRef.current = filteredJobs.length + PAGE_SIZE
                    }
                    setJobsPage((p) => p + 1)
                  }}
                >
                  {jobsQuery.isFetching || filterFilling ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Loading matches…
                    </>
                  ) : (
                    <>
                      Show more
                      <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                      {jobsTotal != null ? (
                        <span className="text-muted-foreground/70">
                          · {jobsAccum.length}/{jobsTotal}
                          {statusFilter !== 'all'
                            ? ` · ${filteredJobs.length} shown`
                            : ''}
                        </span>
                      ) : statusFilter !== 'all' ? (
                        <span className="text-muted-foreground/70">
                          · {filteredJobs.length} shown
                        </span>
                      ) : null}
                    </>
                  )}
                </Button>
              ) : null}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
    {jdPreviewDialog}
    </>
  )
}
