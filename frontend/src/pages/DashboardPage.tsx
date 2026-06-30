import { Link } from 'react-router-dom'
import { useActiveSessions } from '@/hooks/useActiveSessions'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelInterviewSetup, getHealth } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { truncate } from '@/lib/utils'

export function DashboardPage() {
  const queryClient = useQueryClient()
  const sessions = useActiveSessions()
  const health = useQuery({ queryKey: queryKeys.health, queryFn: getHealth, retry: 1 })

  const cancelMutation = useMutation({
    mutationFn: cancelInterviewSetup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions })
    },
  })

  const lobbyTimeoutMin = health.data?.lobby_timeout_minutes ?? 15

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Active sessions
            </CardTitle>
          </CardHeader>
          <CardContent>
            {sessions.isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <p className="text-3xl font-semibold">{sessions.data?.active_sessions ?? 0}</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Backend
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <Badge variant={health.isSuccess ? 'success' : 'destructive'}>
              {health.isSuccess ? health.data?.status ?? 'healthy' : 'offline'}
            </Badge>
            {health.isSuccess && (
              <p className="text-xs text-muted-foreground">
                Lobby auto-leave after {lobbyTimeoutMin} min if not started
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Active interviews</CardTitle>
          <Button asChild size="sm">
            <Link to="/interviews/new">New interview</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {sessions.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : !sessions.data?.bots.length ? (
            <p className="text-sm text-muted-foreground">No active sessions.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">Candidate</th>
                    <th className="pb-2 pr-4 font-medium">Meeting</th>
                    <th className="pb-2 pr-4 font-medium">Phase</th>
                    <th className="pb-2 pr-4 font-medium">Started</th>
                    <th className="pb-2 pr-4 font-medium">Scored</th>
                    <th className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.data.bots.map((bot) => (
                    <tr key={bot.bot_id} className="border-b border-border last:border-0 hover:bg-muted/40">
                      <td className="py-3 pr-4">{bot.candidate_name ?? '—'}</td>
                      <td className="py-3 pr-4 text-muted-foreground">
                        {truncate(bot.meeting_url, 40)}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant="secondary">{bot.interview_phase ?? '—'}</Badge>
                      </td>
                      <td className="py-3 pr-4">{bot.is_started ? 'Yes' : 'No'}</td>
                      <td className="py-3 pr-4">{bot.questions_scored}</td>
                      <td className="py-3">
                        <div className="flex flex-wrap gap-2">
                          <Button asChild variant="outline" size="sm">
                            <Link to={`/interviews/${bot.bot_id}`}>Open</Link>
                          </Button>
                          {!bot.is_started && !bot.interview_ended && (
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={cancelMutation.isPending}
                              onClick={() => cancelMutation.mutate(bot.bot_id)}
                            >
                              Cancel
                            </Button>
                          )}
                          {(bot.interview_ended || bot.interview_phase === 'ended') && (
                            <Button asChild variant="ghost" size="sm">
                              <Link to={`/interviews/${bot.bot_id}/report`}>Report</Link>
                            </Button>
                          )}
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
