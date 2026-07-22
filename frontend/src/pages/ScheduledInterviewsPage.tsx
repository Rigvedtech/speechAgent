import { Link, useNavigate } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, Check, Copy, Search } from 'lucide-react'
import {
  cancelScheduledInterview,
  listScheduledInterviews,
  sendScheduledToLobby,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { upsertSession } from '@/lib/session-store'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { MeetingPlatformIcon } from '@/components/meeting/MeetingPlatformIcon'
import { truncate } from '@/lib/utils'

export function ScheduledInterviewsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [copiedMeetingId, setCopiedMeetingId] = useState<string | null>(null)

  const copyMeetingUrl = async (id: string, url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopiedMeetingId(id)
      window.setTimeout(() => {
        setCopiedMeetingId((current) => (current === id ? null : current))
      }, 2000)
    } catch {
      setError('Could not copy meeting link')
    }
  }

  const scheduled = useQuery({
    queryKey: queryKeys.scheduledInterviews,
    queryFn: listScheduledInterviews,
    retry: 1,
  })

  const sendLobbyMutation = useMutation({
    mutationFn: (row: { id: string; meeting_url: string; candidate_name: string }) =>
      sendScheduledToLobby(row),
    onSuccess: (data, row) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scheduledInterviews })
      upsertSession({
        botId: data.bot_id,
        candidateName: row.candidate_name,
        meetingUrl: data.meeting_url,
        languageMode: data.language_mode,
        createdAt: new Date().toISOString(),
      })
      navigate(`/interviews/${data.bot_id}`, {
        state: { plannedQuestions: data.planned_questions },
      })
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to send bot to lobby',
      )
    },
  })

  const cancelMutation = useMutation({
    mutationFn: cancelScheduledInterview,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scheduledInterviews })
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to cancel interview',
      )
    },
  })

  const rows = scheduled.data ?? []
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter(
      (row) =>
        row.candidate_name.toLowerCase().includes(q) ||
        row.job_title.toLowerCase().includes(q),
    )
  }, [rows, search])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CardHeader className="shrink-0 space-y-4 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Scheduled interviews</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Setup saved without a bot — send to lobby when the candidate is ready
              </p>
            </div>
            <Button asChild size="sm">
              <Link to="/interviews/new">New interview</Link>
            </Button>
          </div>

          <div className="relative w-full max-w-sm">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              strokeWidth={1.5}
            />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search candidate or role"
              className="pl-9"
              aria-label="Search scheduled interviews"
            />
          </div>

          {error && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
        </CardHeader>

        <CardContent className="min-h-0 flex-1 overflow-auto pt-0">
          {scheduled.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : !filtered.length ? (
            <div className="rounded-lg border border-dashed border-border bg-muted/30 px-6 py-12 text-center">
              <CalendarClock
                className="mx-auto h-8 w-8 text-muted-foreground/50"
                strokeWidth={1.25}
              />
              <p className="mt-3 text-sm font-medium">
                {rows.length ? 'No matches' : 'No scheduled interviews'}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {rows.length
                  ? 'Try a different search'
                  : 'Use Schedule on New Interview to save setup without joining yet'}
              </p>
              {!rows.length && (
                <Button asChild size="sm" className="mt-4">
                  <Link to="/interviews/new">Schedule interview</Link>
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="pb-3 pr-4 font-medium">Candidate</th>
                    <th className="pb-3 pr-4 font-medium">Role</th>
                    <th className="pb-3 pr-4 font-medium">Language</th>
                    <th className="pb-3 pr-4 font-medium">Questions</th>
                    <th className="pb-3 pr-4 font-medium">Meeting</th>
                    <th className="pb-3 pr-4 font-medium">Created</th>
                    <th className="pb-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => (
                    <tr
                      key={row.id}
                      className="row-hover border-b border-border last:border-0"
                    >
                      <td className="py-3 pr-4 font-medium">{row.candidate_name}</td>
                      <td className="py-3 pr-4 text-muted-foreground">{row.job_title}</td>
                      <td className="py-3 pr-4">
                        <Badge variant="secondary">{row.language_mode}</Badge>
                      </td>
                      <td className="py-3 pr-4 tabular-nums">{row.questions_planned}</td>
                      <td className="py-3 pr-4">
                        <div className="flex min-w-0 max-w-[16rem] items-center gap-2">
                          <MeetingPlatformIcon url={row.meeting_url} size={16} />
                          <span
                            className="min-w-0 flex-1 truncate text-muted-foreground"
                            title={row.meeting_url}
                          >
                            {truncate(row.meeting_url, 28)}
                          </span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
                            title={
                              copiedMeetingId === row.id ? 'Copied' : 'Copy meeting link'
                            }
                            aria-label={
                              copiedMeetingId === row.id
                                ? 'Meeting link copied'
                                : 'Copy meeting link'
                            }
                            onClick={() => {
                              setError(null)
                              void copyMeetingUrl(row.id, row.meeting_url)
                            }}
                          >
                            {copiedMeetingId === row.id ? (
                              <Check className="h-3.5 w-3.5 text-success" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                          </Button>
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-muted-foreground">
                        {new Date(row.created_at).toLocaleDateString(undefined, {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </td>
                      <td className="py-3">
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            disabled={sendLobbyMutation.isPending}
                            onClick={() => {
                              setError(null)
                              sendLobbyMutation.mutate(row)
                            }}
                          >
                            Send to lobby
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={cancelMutation.isPending}
                            onClick={() => {
                              setError(null)
                              cancelMutation.mutate(row.id)
                            }}
                          >
                            Cancel
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
