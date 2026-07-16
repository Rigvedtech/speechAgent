import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Eye, Loader2, Search } from 'lucide-react'
import {
  getAtsCandidate,
  getAtsJob,
  getAtsSettings,
  listAtsCandidates,
  listAtsJobs,
  openAtsFilePreview,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import type { AtsCandidateDetail, AtsJobDetail, AtsRemoteJob } from '@/types/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

type Mode = 'candidate' | 'job'

interface AtsImportDialogProps {
  open: boolean
  mode: Mode
  onOpenChange: (open: boolean) => void
  /** When set in candidate mode, skip requirement picker and list this job's candidates. */
  lockedParentId?: string | null
  onPickJob?: (detail: AtsJobDetail) => void
  onPickCandidate?: (detail: AtsCandidateDetail) => void
}

const PAGE_SIZE = 10

export function AtsImportDialog({
  open,
  mode,
  onOpenChange,
  lockedParentId = null,
  onPickJob,
  onPickCandidate,
}: AtsImportDialogProps) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [parentId, setParentId] = useState<string | null>(null)
  const [jobsPage, setJobsPage] = useState(1)
  const [jobsAccum, setJobsAccum] = useState<AtsRemoteJob[]>([])
  const [jobsHasNext, setJobsHasNext] = useState(false)
  const [jobsTotal, setJobsTotal] = useState<number | null>(null)
  const [previewingId, setPreviewingId] = useState<string | null>(null)
  const [pickingId, setPickingId] = useState<string | null>(null)

  const settings = useQuery({
    queryKey: queryKeys.atsSettings,
    queryFn: getAtsSettings,
    enabled: open,
  })

  const candidatesDependOn = Boolean(
    (settings.data?.config as { candidates?: { list_depends_on?: string } } | undefined)
      ?.candidates?.list_depends_on,
  )

  const effectiveParentId =
    mode === 'candidate' && lockedParentId ? lockedParentId : parentId

  const showJobPicker =
    mode === 'job' ||
    (mode === 'candidate' && candidatesDependOn && !effectiveParentId && !lockedParentId)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => window.clearTimeout(t)
  }, [search])

  useEffect(() => {
    if (!open) return
    setSearch('')
    setDebouncedSearch('')
    setError(null)
    setParentId(lockedParentId)
    setJobsPage(1)
    setJobsAccum([])
    setJobsHasNext(false)
    setJobsTotal(null)
    setPickingId(null)
    void queryClient.invalidateQueries({ queryKey: queryKeys.atsJobs })
    void queryClient.invalidateQueries({ queryKey: queryKeys.atsCandidates })
  }, [open, mode, lockedParentId, queryClient])

  useEffect(() => {
    if (!open) return
    setJobsPage(1)
    setJobsAccum([])
    setJobsHasNext(false)
    setJobsTotal(null)
  }, [debouncedSearch, open])

  const jobsQuery = useQuery({
    queryKey: [...queryKeys.atsJobs, debouncedSearch, jobsPage, PAGE_SIZE, open],
    queryFn: () =>
      listAtsJobs({
        q: debouncedSearch || undefined,
        page: jobsPage,
        page_size: PAGE_SIZE,
      }),
    enabled: open && showJobPicker,
    staleTime: 0,
  })

  useEffect(() => {
    if (!open || !showJobPicker) return
    if (!jobsQuery.data) return
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
  }, [open, showJobPicker, jobsQuery.dataUpdatedAt, jobsQuery.data])

  const candidates = useQuery({
    queryKey: [...queryKeys.atsCandidates, debouncedSearch, effectiveParentId, open],
    queryFn: () =>
      listAtsCandidates({
        q: debouncedSearch || undefined,
        request_id: effectiveParentId || undefined,
      }),
    enabled:
      open &&
      mode === 'candidate' &&
      (!candidatesDependOn || Boolean(effectiveParentId)),
    staleTime: 0,
  })

  const pending = Boolean(pickingId)
  const jobsLoading =
    showJobPicker &&
    jobsAccum.length === 0 &&
    (jobsQuery.isLoading || jobsQuery.isFetching || jobsQuery.isPending)
  const loading = showJobPicker ? jobsLoading : candidates.isLoading

  const previewJob = async (externalId: string) => {
    setPreviewingId(externalId)
    setError(null)
    try {
      await openAtsFilePreview('job', externalId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open JD file')
    } finally {
      setPreviewingId(null)
    }
  }

  const previewCandidate = async (externalId: string) => {
    setPreviewingId(externalId)
    setError(null)
    try {
      await openAtsFilePreview('candidate', externalId, effectiveParentId || undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open resume')
    } finally {
      setPreviewingId(null)
    }
  }

  const pickJob = async (externalId: string) => {
    setPickingId(externalId)
    setError(null)
    try {
      const detail = await getAtsJob(externalId)
      onPickJob?.(detail)
      onOpenChange(false)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Could not load job from ATS',
      )
    } finally {
      setPickingId(null)
    }
  }

  const pickCandidate = async (externalId: string) => {
    setPickingId(externalId)
    setError(null)
    try {
      const detail = await getAtsCandidate(externalId, effectiveParentId || undefined)
      onPickCandidate?.(detail)
      onOpenChange(false)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Could not load candidate from ATS',
      )
    } finally {
      setPickingId(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg gap-4">
        <DialogHeader className="space-y-1.5">
          <DialogTitle>
            {mode === 'candidate'
              ? effectiveParentId
                ? lockedParentId
                  ? 'Pick a candidate for this job'
                  : 'Pick a candidate'
                : candidatesDependOn
                  ? 'Pick a requirement'
                  : 'Pick a candidate'
              : 'Pick a job from ATS'}
          </DialogTitle>
          <DialogDescription>
            {mode === 'candidate' && candidatesDependOn && !effectiveParentId
              ? 'Choose the role first, then select a candidate under it.'
              : lockedParentId && mode === 'candidate'
                ? 'Showing candidates for the job you already selected. Saved to your workspace when you schedule or send the bot.'
                : 'Selection fills this interview. CV/JD are saved only when you schedule or send the bot to lobby.'}
          </DialogDescription>
        </DialogHeader>

        {parentId && !lockedParentId ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-mt-1 h-8 self-start px-2 text-xs text-muted-foreground"
            onClick={() => setParentId(null)}
          >
            ← Back to requirements
          </Button>
        ) : null}

        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            strokeWidth={1.5}
          />
          <Input
            className="h-10 pl-9"
            placeholder={showJobPicker ? 'Search roles…' : 'Search candidates…'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {error ? (
          <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="max-h-80 space-y-1.5 overflow-y-auto rounded-lg border border-border bg-muted/10 p-1.5">
          {loading ? (
            <div className="space-y-1.5 p-1">
              <Skeleton className="h-14 w-full rounded-md" />
              <Skeleton className="h-14 w-full rounded-md" />
              <Skeleton className="h-14 w-full rounded-md" />
            </div>
          ) : showJobPicker ? (
            jobsAccum.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                {jobsQuery.isError ? 'Could not load jobs. Try again.' : 'No matching roles'}
              </p>
            ) : (
              <>
                {jobsAccum.map((row) => (
                  <div
                    key={row.external_id}
                    className="flex items-center gap-2 rounded-md border border-transparent bg-card px-2.5 py-2 hover:border-border"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium leading-tight">{row.job_title}</p>
                      <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                        {row.description ?? row.external_id}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {row.has_jd_url ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title="Preview JD"
                          disabled={previewingId === row.external_id}
                          onClick={() => void previewJob(row.external_id)}
                        >
                          {previewingId === row.external_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Eye className="h-3.5 w-3.5" strokeWidth={1.5} />
                          )}
                        </Button>
                      ) : null}
                      {mode === 'candidate' ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-8"
                          onClick={() => setParentId(row.external_id)}
                        >
                          Open
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          size="sm"
                          className="h-8"
                          disabled={pending}
                          onClick={() => void pickJob(row.external_id)}
                        >
                          {pickingId === row.external_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : null}
                          Use
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
                {jobsHasNext ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-9 w-full gap-1 text-xs text-muted-foreground"
                    disabled={jobsQuery.isFetching}
                    onClick={() => setJobsPage((p) => p + 1)}
                  >
                    {jobsQuery.isFetching ? (
                      'Loading…'
                    ) : (
                      <>
                        Show more
                        <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                        {jobsTotal != null ? (
                          <span className="text-muted-foreground/70">
                            · {jobsAccum.length}/{jobsTotal}
                          </span>
                        ) : null}
                      </>
                    )}
                  </Button>
                ) : null}
              </>
            )
          ) : (candidates.data ?? []).length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">No candidates</p>
          ) : (
            (candidates.data ?? []).map((row) => (
              <div
                key={row.external_id}
                className="flex items-center gap-2 rounded-md border border-transparent bg-card px-2.5 py-2 hover:border-border"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium leading-tight">{row.full_name}</p>
                  <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                    {row.email ?? row.external_id}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {row.has_cv_url ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      title="Preview resume"
                      disabled={previewingId === row.external_id}
                      onClick={() => void previewCandidate(row.external_id)}
                    >
                      {previewingId === row.external_id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Eye className="h-3.5 w-3.5" strokeWidth={1.5} />
                      )}
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    className="h-8"
                    disabled={pending}
                    onClick={() => void pickCandidate(row.external_id)}
                  >
                    {pickingId === row.external_id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : null}
                    Use
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
