import { useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { grantAccessRequest, listAccessRequests, rejectAccessRequest } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import type { AccessRequest, AccessRequestStatus } from '@/types/api'
import { Button } from '@/components/ui/button'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { FlashAlert } from '@/components/ui/flash-alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

function statusBadge(status: AccessRequest['status']) {
  if (status === 'granted') return <Badge variant="success">Granted</Badge>
  if (status === 'rejected') return <Badge variant="secondary">Rejected</Badge>
  return <Badge variant="warning">Pending</Badge>
}

function formatRequestedAt(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function DetailField({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
      <p className={cn('mt-1 truncate text-sm', value ? 'text-foreground' : 'text-muted-foreground')}>
        {value || '—'}
      </p>
    </div>
  )
}

export function AccessRequestsPage() {
  const { isPlatformAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<'all' | AccessRequestStatus>('pending')
  const [grantTarget, setGrantTarget] = useState<AccessRequest | null>(null)
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const requests = useQuery({
    queryKey: queryKeys.accessRequests,
    queryFn: () => listAccessRequests(),
    enabled: isPlatformAdmin,
  })

  const rows = requests.data ?? []
  const counts = useMemo(() => {
    return {
      all: rows.length,
      pending: rows.filter((row) => row.status === 'pending').length,
      granted: rows.filter((row) => row.status === 'granted').length,
      rejected: rows.filter((row) => row.status === 'rejected').length,
    }
  }, [rows])

  const visible = useMemo(
    () => (filter === 'all' ? rows : rows.filter((row) => row.status === filter)),
    [filter, rows],
  )

  const grantMutation = useMutation({
    mutationFn: () => {
      if (!grantTarget) throw new Error('No request selected')
      return grantAccessRequest(grantTarget.id, { password })
    },
    onSuccess: (result) => {
      setGrantTarget(null)
      setPassword('')
      setFormError(null)
      setNotice(
        `Access granted for ${result.organization_name}. Send login email ${result.login_email} and the password you just set.`,
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.accessRequests })
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminOverview })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setFormError(formatApiError(err.message, err.detail))
      } else {
        setFormError('Could not grant access.')
      }
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => rejectAccessRequest(id),
    onSuccess: () => {
      setNotice('Request rejected.')
      void queryClient.invalidateQueries({ queryKey: queryKeys.accessRequests })
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminOverview })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setNotice(formatApiError(err.message, err.detail))
      }
    },
  })

  if (!isPlatformAdmin) {
    return <Navigate to="/login" replace />
  }

  const filters: Array<{ id: 'all' | AccessRequestStatus; label: string; count: number }> = [
    { id: 'pending', label: 'Pending', count: counts.pending },
    { id: 'granted', label: 'Granted', count: counts.granted },
    { id: 'rejected', label: 'Rejected', count: counts.rejected },
    { id: 'all', label: 'All', count: counts.all },
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex flex-wrap gap-1">
        {filters.map((item) => (
          <Button
            key={item.id}
            type="button"
            size="sm"
            variant={filter === item.id ? 'default' : 'outline'}
            onClick={() => setFilter(item.id)}
          >
            {item.label}
            <span className="ml-1.5 tabular-nums opacity-70">{item.count}</span>
          </Button>
        ))}
      </div>

      <FlashAlert
        message={notice}
        onDismiss={() => setNotice(null)}
        className="border-success/30 bg-success/[0.06]"
      />

      {requests.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading requests…</p>
      ) : visible.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            {rows.length === 0
              ? 'No access requests yet.'
              : filter === 'all'
                ? 'No access requests yet.'
                : `No ${filter} requests.`}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {visible.map((row) => (
            <Card key={row.id}>
              <CardContent className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-base font-semibold tracking-tight">{row.company_name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Requested {formatRequestedAt(row.created_at)}
                    </p>
                  </div>
                  {statusBadge(row.status)}
                </div>

                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <DetailField label="Contact" value={row.contact_name} />
                  <DetailField label="Email" value={row.email} />
                  <DetailField label="Phone" value={row.phone} />
                </div>

                {row.message ? (
                  <div className="mt-4 rounded-md bg-muted/50 px-3 py-2.5">
                    <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                      Note
                    </p>
                    <p className="mt-1 text-sm leading-relaxed">{row.message}</p>
                  </div>
                ) : null}

                {row.status === 'pending' ? (
                  <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-border pt-4">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={rejectMutation.isPending}
                      onClick={() => rejectMutation.mutate(row.id)}
                    >
                      Reject
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => {
                        setGrantTarget(row)
                        setPassword('')
                        setFormError(null)
                      }}
                    >
                      Grant access
                    </Button>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog
        open={Boolean(grantTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setGrantTarget(null)
            setPassword('')
            setFormError(null)
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Grant access</DialogTitle>
            <DialogDescription>
              Creates the company and first org admin. Send them email + password yourself.
            </DialogDescription>
          </DialogHeader>
          {grantTarget ? (
            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <p className="font-medium">{grantTarget.company_name}</p>
              <p className="mt-1 text-sm text-muted-foreground">{grantTarget.contact_name}</p>
              <p className="text-sm text-muted-foreground">{grantTarget.email}</p>
            </div>
          ) : null}
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              grantMutation.mutate()
            }}
          >
            {formError ? <p className={cn('text-sm text-destructive')}>{formError}</p> : null}
            <div>
              <Label htmlFor="grant-password">Temporary password</Label>
              <PasswordInput
                id="grant-password"
                className="mt-1.5"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                At least 8 characters, including a letter and a number.
              </p>
            </div>
            <Button type="submit" className="w-full" disabled={grantMutation.isPending}>
              {grantMutation.isPending ? 'Granting…' : 'Create login and grant'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
