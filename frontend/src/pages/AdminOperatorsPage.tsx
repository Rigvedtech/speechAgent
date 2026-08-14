import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  changeAdminPassword,
  createAdminOperator,
  listAdminOperators,
  patchAdminOperator,
} from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import type { AuthUser } from '@/types/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FlashAlert } from '@/components/ui/flash-alert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PasswordInput } from '@/components/ui/password-input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const emptyForm = { fullName: '', email: '', password: '' }

export function AdminOperatorsPage() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [resetTarget, setResetTarget] = useState<AuthUser | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [ownOpen, setOwnOpen] = useState(false)
  const [ownCurrent, setOwnCurrent] = useState('')
  const [ownNext, setOwnNext] = useState('')
  const [ownError, setOwnError] = useState<string | null>(null)

  const operators = useQuery({
    queryKey: queryKeys.adminOperators,
    queryFn: listAdminOperators,
  })
  const rows = operators.data ?? []

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.adminOperators })
    void queryClient.invalidateQueries({ queryKey: queryKeys.adminOverview })
  }

  const createMutation = useMutation({
    mutationFn: () =>
      createAdminOperator({
        full_name: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
      }),
    onSuccess: (user) => {
      setCreateOpen(false)
      setForm(emptyForm)
      setFormError(null)
      setNotice(`Platform admin ${user.email} created. Send them the password you set.`)
      invalidate()
    },
    onError: (err) => {
      if (err instanceof ApiError) setFormError(formatApiError(err.message, err.detail))
      else setFormError('Could not create platform admin.')
    },
  })

  const toggleMutation = useMutation({
    mutationFn: (row: AuthUser) => patchAdminOperator(row.id, { is_active: !row.is_active }),
    onSuccess: (user) => {
      setNotice(user.is_active ? `${user.email} is active.` : `${user.email} is deactivated.`)
      invalidate()
    },
    onError: (err) => {
      if (err instanceof ApiError) setNotice(formatApiError(err.message, err.detail))
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => {
      if (!resetTarget) throw new Error('No platform admin')
      return patchAdminOperator(resetTarget.id, { password: resetPassword })
    },
    onSuccess: (user) => {
      setResetTarget(null)
      setResetPassword('')
      setNotice(`Password updated for ${user.email}.`)
      invalidate()
    },
    onError: (err) => {
      if (err instanceof ApiError) setNotice(formatApiError(err.message, err.detail))
    },
  })

  const ownMutation = useMutation({
    mutationFn: () => changeAdminPassword({ current_password: ownCurrent, new_password: ownNext }),
    onSuccess: () => {
      setOwnOpen(false)
      setOwnCurrent('')
      setOwnNext('')
      setOwnError(null)
      setNotice('Your password was updated.')
    },
    onError: (err) => {
      if (err instanceof ApiError) setOwnError(formatApiError(err.message, err.detail))
      else setOwnError('Could not update password.')
    },
  })

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => { setOwnError(null); setOwnOpen(true) }}>
          Change my password
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() => {
            setForm(emptyForm)
            setFormError(null)
            setCreateOpen(true)
          }}
        >
          Add platform admin
        </Button>
      </div>

      <FlashAlert
        message={notice}
        onDismiss={() => setNotice(null)}
        className="border-success/30 bg-success/[0.06]"
      />

      <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-border bg-card">
        {operators.isLoading ? (
          <p className="p-6 text-sm text-muted-foreground">Loading platform admins…</p>
        ) : rows.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">No platform admins yet.</p>
        ) : (
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-border text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-3 py-2.5 font-medium">Role</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5 pr-4 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isSelf = row.id === currentUser?.id
                return (
                  <tr key={row.id} className="border-b border-border/70 last:border-b-0">
                    <td className="px-4 py-3 align-middle">
                      <p className="font-medium">
                        {row.full_name}
                        {isSelf ? <span className="ml-2 text-xs font-normal text-muted-foreground">you</span> : null}
                      </p>
                      <p className="text-xs text-muted-foreground">{row.email}</p>
                    </td>
                    <td className="px-3 py-3 align-middle">
                      <Badge variant="outline">Platform admin</Badge>
                    </td>
                    <td className="px-3 py-3 align-middle">
                      {row.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="secondary">Inactive</Badge>}
                    </td>
                    <td className="px-3 py-3 pr-4 align-middle">
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setResetTarget(row)
                            setResetPassword('')
                          }}
                        >
                          Reset password
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={toggleMutation.isPending || isSelf}
                          onClick={() => toggleMutation.mutate(row)}
                        >
                          {row.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add platform admin</DialogTitle>
            <DialogDescription>
              They sign in on the same login page and open this admin panel. Distinct from an org admin.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              createMutation.mutate()
            }}
          >
            {formError ? <p className={cn('text-sm text-destructive')}>{formError}</p> : null}
            <div>
              <Label htmlFor="op-name">Name</Label>
              <Input
                id="op-name"
                className="mt-1.5"
                value={form.fullName}
                onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
                required
                minLength={2}
              />
            </div>
            <div>
              <Label htmlFor="op-email">Email</Label>
              <Input
                id="op-email"
                type="email"
                className="mt-1.5"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                required
              />
            </div>
            <div>
              <Label htmlFor="op-password">Temporary password</Label>
              <PasswordInput
                id="op-password"
                className="mt-1.5"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating…' : 'Create platform admin'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(resetTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setResetTarget(null)
            setResetPassword('')
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
            <DialogDescription>Sets a new password for {resetTarget?.email}.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              resetMutation.mutate()
            }}
          >
            <div>
              <Label htmlFor="op-reset">New password</Label>
              <PasswordInput
                id="op-reset"
                className="mt-1.5"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={resetMutation.isPending}>
              {resetMutation.isPending ? 'Saving…' : 'Update password'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={ownOpen} onOpenChange={setOwnOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Change my password</DialogTitle>
            <DialogDescription>Use this after the first platform admin login.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              ownMutation.mutate()
            }}
          >
            {ownError ? <p className={cn('text-sm text-destructive')}>{ownError}</p> : null}
            <div>
              <Label htmlFor="own-current">Current password</Label>
              <PasswordInput
                id="own-current"
                className="mt-1.5"
                value={ownCurrent}
                onChange={(e) => setOwnCurrent(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            <div>
              <Label htmlFor="own-next">New password</Label>
              <PasswordInput
                id="own-next"
                className="mt-1.5"
                value={ownNext}
                onChange={(e) => setOwnNext(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={ownMutation.isPending}>
              {ownMutation.isPending ? 'Saving…' : 'Update password'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
