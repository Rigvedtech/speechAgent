import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  Loader2,
  Sparkles,
  Trash2,
  Play,
  Lock,
  Plus,
} from 'lucide-react'
import {
  createCodingDomain,
  deactivateAllDomainCodingTasks,
  deactivateDomainCodingTask,
  generateDomainCodingTask,
  listCodingDomains,
  listDomainCodingTasks,
  startDemoCodingSession,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { Alert } from '@/components/ui/alert'
import { FlashAlert } from '@/components/ui/flash-alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { CODING_LANGUAGE_OPTIONS } from '@/lib/coding-languages'
import type { CodingDomain, CodingLanguage } from '@/types/api'

export function CodingDashboardPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newLanguage, setNewLanguage] = useState<CodingLanguage>('python')
  const [newDescription, setNewDescription] = useState('')

  const domainsQuery = useQuery({
    queryKey: queryKeys.codingDomains,
    queryFn: listCodingDomains,
    staleTime: 30_000,
  })

  const domains = domainsQuery.data ?? []
  const selected: CodingDomain | undefined =
    domains.find((d) => d.id === selectedId) ?? domains[0]

  useEffect(() => {
    if (!selectedId && domains[0]?.id) {
      setSelectedId(domains[0].id)
    }
  }, [domains, selectedId])

  const tasksQuery = useQuery({
    queryKey: queryKeys.codingDomainTasks(selected?.id ?? ''),
    queryFn: () => listDomainCodingTasks(selected!.id, { owned_only: true }),
    enabled: Boolean(selected?.id),
  })

  const tasks = tasksQuery.data ?? []
  const tasksLoading = tasksQuery.isLoading || tasksQuery.isFetching

  const createMutation = useMutation({
    mutationFn: () =>
      createCodingDomain({
        name: newName.trim(),
        language: newLanguage,
        description: newDescription.trim(),
      }),
    onSuccess: async (domain) => {
      setError(null)
      setCreateOpen(false)
      setNewName('')
      setNewDescription('')
      setNewLanguage('python')
      await queryClient.invalidateQueries({ queryKey: queryKeys.codingDomains })
      setSelectedId(domain.id)
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to create domain',
      )
    },
  })

  const generateMutation = useMutation({
    mutationFn: () => generateDomainCodingTask(selected!.id),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.codingDomains })
      await queryClient.invalidateQueries({
        queryKey: queryKeys.codingDomainTasks(selected!.id),
      })
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to generate problem',
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (taskId: string) =>
      deactivateDomainCodingTask(selected!.id, taskId),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.codingDomains })
      await queryClient.invalidateQueries({
        queryKey: queryKeys.codingDomainTasks(selected!.id),
      })
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
    mutationFn: () => deactivateAllDomainCodingTasks(selected!.id),
    onSuccess: async (res) => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.codingDomains })
      await queryClient.invalidateQueries({
        queryKey: queryKeys.codingDomainTasks(selected!.id),
      })
      if (!res.deleted) {
        setError('No problems to delete in this domain.')
      }
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
    mutationFn: (taskId: string) =>
      startDemoCodingSession({
        domain_id: selected!.id,
        task_id: taskId,
      }),
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

  const canGenerate = useMemo(() => {
    if (!selected) return false
    return selected.can_generate && !generateMutation.isPending
  }, [selected, generateMutation.isPending])

  const canSubmitCreate =
    newName.trim().length >= 2 && !createMutation.isPending

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <FlashAlert
        message={error}
        onDismiss={() => setError(null)}
        className="shrink-0 border-destructive/30 bg-destructive/5 text-destructive"
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 md:grid-cols-[280px_minmax(0,1fr)]">
        {/* Domains column */}
        <Card className="flex min-h-0 flex-col overflow-hidden md:h-full">
          <CardHeader className="flex shrink-0 flex-row items-center justify-between gap-2 space-y-0 pb-3">
            <CardTitle className="text-sm">Domains</CardTitle>
            <Button size="sm" variant="secondary" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              Create
            </Button>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden p-4 pt-0">
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {domainsQuery.isLoading && (
                <div className="flex h-24 items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading…
                </div>
              )}
              {!domainsQuery.isLoading && domains.length === 0 && (
                <div className="flex h-40 flex-col items-center justify-center rounded-md border border-dashed border-border px-4 text-center">
                  <p className="text-sm text-muted-foreground">No domains yet.</p>
                  <Button
                    size="sm"
                    className="mt-3"
                    onClick={() => setCreateOpen(true)}
                  >
                    <Plus className="h-4 w-4" />
                    Create domain
                  </Button>
                </div>
              )}
              {domains.map((domain) => {
                const active = selected?.id === domain.id
                return (
                  <button
                    key={domain.id}
                    type="button"
                    onClick={() => {
                      setSelectedId(domain.id)
                      setError(null)
                    }}
                    className={cn(
                      'w-full rounded-md border px-3 py-2.5 text-left transition-colors',
                      active
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/40',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{domain.name}</span>
                      <Badge variant="secondary">
                        {domain.problem_count}/{domain.max_problems}
                      </Badge>
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Language locked: {domain.language}
                      {domain.is_org_owned ? ' · custom' : ''}
                    </p>
                  </button>
                )
              })}
            </div>
          </CardContent>
        </Card>

        {/* Problems card */}
        <Card className="flex min-h-0 flex-col overflow-hidden md:h-full">
          <CardHeader className="flex shrink-0 flex-row flex-wrap items-center justify-between gap-2 space-y-0 pb-3">
            <div className="min-w-0">
              <CardTitle className="text-sm">
                {selected ? `${selected.name} problems` : 'Problems'}
              </CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                {selected
                  ? `${selected.problem_count}/${selected.max_problems} problems. Generate adds one AI problem at a time. Delete one or Delete all.`
                  : 'Select a domain to manage problems.'}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={
                  !selected ||
                  tasks.length === 0 ||
                  deleteAllMutation.isPending ||
                  deleteMutation.isPending
                }
                title="Delete all problems in this domain"
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete all ${tasks.length} problem(s) in ${selected?.name ?? 'this domain'}?`,
                    )
                  ) {
                    deleteAllMutation.mutate()
                  }
                }}
              >
                {deleteAllMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Delete all
              </Button>
              <Button
                size="sm"
                disabled={!canGenerate || !selected}
                title={
                  selected && !selected.can_generate
                    ? `Max ${selected.max_problems} problems — remove one to generate more`
                    : 'Generate one DSA problem with AI'
                }
                onClick={() => generateMutation.mutate()}
              >
                {generateMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                Generate
              </Button>
            </div>
          </CardHeader>

          <CardContent className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-4 pt-0">
            {selected && !selected.can_generate ? (
              <Alert className="shrink-0">
                Generate is locked — this domain already has {selected.max_problems}{' '}
                org problems. Delete one to unlock Generate.
              </Alert>
            ) : null}

            <div className="relative min-h-0 flex-1 overflow-y-auto rounded-md border border-border">
              {tasksLoading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-card/80">
                  <span className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading problems…
                  </span>
                </div>
              )}

              {!tasksLoading && tasks.length === 0 && (
                <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 px-6 text-center">
                  <p className="text-sm font-medium">No problems in this domain</p>
                  <p className="max-w-sm text-xs text-muted-foreground">
                    Click Generate to create one DSA problem with AI (up to{' '}
                    {selected?.max_problems ?? 5} total).
                  </p>
                </div>
              )}

              {tasks.length > 0 && (
                <ul className="divide-y divide-border">
                  {tasks.map((task) => (
                    <li
                      key={task.id}
                      className="flex min-h-[72px] flex-wrap items-center justify-between gap-2 px-3 py-2.5"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">{task.title}</span>
                          <Badge variant="secondary">{task.difficulty}</Badge>
                        </div>
                        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                          {(task.skill_tags ?? []).join(' · ') || task.slug}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
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
                          size="sm"
                          variant="outline"
                          disabled={deleteMutation.isPending || deleteAllMutation.isPending}
                          title="Delete this problem"
                          onClick={() => {
                            if (window.confirm(`Delete “${task.title}”?`)) {
                              deleteMutation.mutate(task.id)
                            }
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <p className="flex shrink-0 items-start gap-2 text-[11px] text-muted-foreground">
              <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Opening Demo or sharing a coding URI locks the candidate editor to{' '}
              <strong>{selected?.language ?? 'the domain language'}</strong>. They
              cannot change domain or language.
            </p>
          </CardContent>
        </Card>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create domain</DialogTitle>
            <DialogDescription>
              Domains group coding problems by language. When you assign a domain in an
              interview, the candidate editor is locked to that language — they cannot
              switch. Use Generate later to add up to 5 AI DSA problems per domain.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div>
              <Label htmlFor="domain-name">Name</Label>
              <Input
                id="domain-name"
                className="mt-1.5"
                placeholder="e.g. Backend Java"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </div>
            <div>
              <Label>Language (locked for candidates)</Label>
              <Select
                value={newLanguage}
                onValueChange={(v) => setNewLanguage(v as CodingLanguage)}
              >
                <SelectTrigger className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-64">
                  {CODING_LANGUAGE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.id} value={opt.id}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                Java is in this list (right under Python). Editor supports Java syntax;
                Run requires a JDK (`javac` / `java` on PATH). Python, JS/TS, C++, Go,
                Ruby, and PHP also run when their tools are installed.
              </p>
            </div>
            <div>
              <Label htmlFor="domain-desc">Description (optional)</Label>
              <Input
                id="domain-desc"
                className="mt-1.5"
                placeholder="Short note for recruiters"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!canSubmitCreate}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
