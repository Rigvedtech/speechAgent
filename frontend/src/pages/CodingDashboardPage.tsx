import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Loader2, Sparkles, Trash2, Play, Database } from 'lucide-react'
import {
  deactivateAllBankCodingTasks,
  deactivateBankCodingTask,
  generateCodingBankBatch,
  getCodingBankStatus,
  listCodingBank,
  listCodingDomains,
  seedCodingBank,
  startDemoCodingSession,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { FlashAlert } from '@/components/ui/flash-alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { CodingLanguage } from '@/types/api'

export function CodingDashboardPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [demoDomainId, setDemoDomainId] = useState<string | null>(null)

  const bankQuery = useQuery({
    queryKey: queryKeys.codingBank,
    queryFn: listCodingBank,
    staleTime: 15_000,
  })
  const statusQuery = useQuery({
    queryKey: queryKeys.codingBankStatus,
    queryFn: getCodingBankStatus,
    staleTime: 15_000,
  })
  const domainsQuery = useQuery({
    queryKey: queryKeys.codingDomains,
    queryFn: listCodingDomains,
    staleTime: 60_000,
  })

  const tasks = bankQuery.data ?? []
  const status = statusQuery.data
  const domains = domainsQuery.data ?? []
  const selectedDemoDomain =
    domains.find((d) => d.id === demoDomainId) ?? domains[0] ?? null
  const demoLang = (selectedDemoDomain?.language || 'python') as CodingLanguage

  useEffect(() => {
    if (!demoDomainId && domains[0]?.id) {
      setDemoDomainId(domains[0].id)
    }
  }, [domains, demoDomainId])

  const invalidateBank = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.codingBank })
    await queryClient.invalidateQueries({ queryKey: queryKeys.codingBankStatus })
    await queryClient.invalidateQueries({ queryKey: queryKeys.codingDomains })
  }

  const seedMutation = useMutation({
    mutationFn: seedCodingBank,
    onSuccess: async (res) => {
      setError(null)
      setInfo(
        res.inserted
          ? `Seeded ${res.inserted} problems (${res.after}/${res.target}).`
          : `Bank already has ${res.after} problems (target ${res.target}).`,
      )
      await invalidateBank()
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to seed bank',
      )
    },
  })

  const generateMutation = useMutation({
    mutationFn: generateCodingBankBatch,
    onSuccess: async (res) => {
      setError(null)
      setInfo(
        `Generated ${res.created_count} of ${res.requested} problems (${res.problem_count}/${res.max_problems}).`,
      )
      await invalidateBank()
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to generate problems',
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (taskId: string) => deactivateBankCodingTask(taskId),
    onSuccess: async () => {
      setError(null)
      setInfo(null)
      await invalidateBank()
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to remove problem',
      )
    },
  })

  const deleteAllMutation = useMutation({
    mutationFn: deactivateAllBankCodingTasks,
    onSuccess: async (res) => {
      setError(null)
      setInfo(res.deleted ? `Deleted ${res.deleted} problems.` : 'No problems to delete.')
      await invalidateBank()
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to delete problems',
      )
    },
  })

  const demoMutation = useMutation({
    mutationFn: (taskId: string) => {
      const domain = selectedDemoDomain
      const language = (domain?.language || demoLang || 'python') as CodingLanguage
      return startDemoCodingSession({
        task_id: taskId,
        domain_id: domain?.id,
        language,
      })
    },
    onSuccess: (session) => {
      const token = session.access_token || session.demo_token
      if (token) window.location.assign(`/c/${token}`)
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to start demo',
      )
    },
  })

  const count = status?.problem_count ?? tasks.length
  const max = status?.max_problems ?? 100
  const nextGen = status?.next_generate_count ?? 0
  const busy =
    seedMutation.isPending ||
    generateMutation.isPending ||
    deleteMutation.isPending ||
    deleteAllMutation.isPending

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <FlashAlert
        message={error}
        onDismiss={() => setError(null)}
        className="shrink-0 border-destructive/30 bg-destructive/5 text-destructive"
      />
      <FlashAlert
        message={info}
        onDismiss={() => setInfo(null)}
        className="shrink-0 border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
      />

      <Card className="flex min-h-0 flex-1 flex-col border-border/60">
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0 pb-3">
          <div>
            <CardTitle className="text-base">Shared problems</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {count}/{max} · {status?.free_slots ?? Math.max(0, max - count)} free
              {nextGen > 0 ? ` · Generate +${nextGen}` : ''}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground">Demo lang</span>
              <Select
                value={selectedDemoDomain?.id ?? ''}
                onValueChange={(id) => setDemoDomainId(id)}
              >
                <SelectTrigger className="h-8 w-[180px] text-xs">
                  <SelectValue placeholder="Select language" />
                </SelectTrigger>
                <SelectContent>
                  {domains.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name} ({d.language})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || !status?.can_seed}
              onClick={() => seedMutation.mutate()}
              title="Load curated DSA problems (up to 90)"
            >
              {seedMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Database className="h-4 w-4" />
              )}
              Seed bank
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || tasks.length === 0}
              onClick={() => {
                if (
                  window.confirm(
                    `Delete all ${tasks.length} problems from the shared bank?`,
                  )
                ) {
                  deleteAllMutation.mutate()
                }
              }}
            >
              Delete all
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={busy || !status?.can_generate || nextGen <= 0}
              title={
                nextGen <= 0
                  ? `Max ${max} problems — delete some to generate more`
                  : `Generate up to ${nextGen} AI problems`
              }
              onClick={() => generateMutation.mutate()}
            >
              {generateMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              Generate{nextGen > 0 ? ` (+${nextGen})` : ''}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="min-h-0 flex-1 overflow-y-auto pb-4">
          {bankQuery.isLoading ? (
            <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading bank…
            </div>
          ) : tasks.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/70 px-4 py-10 text-center">
              <p className="text-sm font-medium">Bank is empty</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Click <span className="font-medium text-foreground">Seed bank</span> for ~90 curated
                DSA problems, or Generate to add AI problems (+10 at a time).
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {tasks.map((task) => (
                <li
                  key={task.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/50 bg-muted/20 px-3 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-medium">{task.title}</p>
                      <Badge variant="secondary" className="text-[10px] uppercase">
                        {task.difficulty}
                      </Badge>
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                      {(task.skill_tags || []).slice(0, 4).join(' · ') || 'DSA'}
                      {' · '}
                      multi-language
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8"
                      disabled={demoMutation.isPending}
                      onClick={() => demoMutation.mutate(task.id)}
                    >
                      {demoMutation.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Play className="h-3.5 w-3.5" />
                      )}
                      Demo
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      disabled={busy}
                      onClick={() => deleteMutation.mutate(task.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
