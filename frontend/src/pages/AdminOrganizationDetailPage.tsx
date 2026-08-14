import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createAdminOrgUser,
  getAdminOrganization,
  patchAdminOrganization,
  patchAdminUser,
} from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import type { AuthUser, TenantUserRole } from '@/types/api'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { formatAdminUserRole } from '@/lib/admin-labels'

const emptyForm = {
  fullName: '',
  email: '',
  password: '',
  role: 'recruiter' as TenantUserRole,
}

export function AdminOrganizationDetailPage() {
  const { orgId = '' } = useParams()
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [resetTarget, setResetTarget] = useState<AuthUser | null>(null)
  const [resetPassword, setResetPassword] = useState('')

  const detail = useQuery({
    queryKey: queryKeys.adminOrganization(orgId),
    queryFn: () => getAdminOrganization(orgId),
    enabled: Boolean(orgId),
  })

  const org = detail.data?.organization
  const users = detail.data?.users ?? []

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.adminOrganization(orgId) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.adminOrganizations })
  }

  const toggleOrg = useMutation({
    mutationFn: () => patchAdminOrganization(orgId, { is_active: !org?.is_active }),
    onSuccess: (row) => {
      setNotice(row.is_active ? `${row.name} is active.` : `${row.name} is deactivated.`)
      invalidate()
    },
    onError: (err) => {
      if (err instanceof ApiError) setNotice(formatApiError(err.message, err.detail))
    },
  })

  const createUser = useMutation({
    mutationFn: () =>
      createAdminOrgUser(orgId, {
        full_name: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
      }),
    onSuccess: (user) => {
      setCreateOpen(false)
      setForm(emptyForm)
      setFormError(null)
      setNotice(`Created ${user.email}. Send them the password you set.`)
      invalidate()
    },
    onError: (err) => {
      if (err instanceof ApiError) setFormError(formatApiError(err.message, err.detail))
      else setFormError('Could not create user.')
    },
  })

  const toggleUser = useMutation({
    mutationFn: (row: AuthUser) => patchAdminUser(row.id, { is_active: !row.is_active }),
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
      if (!resetTarget) throw new Error('No user')
      return patchAdminUser(resetTarget.id, { password: resetPassword })
    },
    onSuccess: (user) => {
      setResetTarget(null)
      setResetPassword('')
      setNotice(`Password updated for ${user.email}. Send it to them yourself.`)
      invalidate()
    },
    onError: (err) => {
      if (err instanceof ApiError) setNotice(formatApiError(err.message, err.detail))
    },
  })

  if (detail.isLoading) {
    return <p className="p-6 text-sm text-muted-foreground">Loading organization…</p>
  }
  if (!org) {
    return (
      <div className="p-6">
        <p className="text-sm text-muted-foreground">Organization not found.</p>
        <Link to="/admin/organizations" className="mt-2 inline-block text-sm underline-offset-4 hover:underline">
          Back to organizations
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/admin/organizations" className="text-xs text-muted-foreground underline-offset-4 hover:underline">
            Organizations
          </Link>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">{org.name}</h2>
          <p className="text-sm text-muted-foreground">
            {org.slug} · {org.user_count} user{org.user_count === 1 ? '' : 's'}
          </p>
        </div>
        <div className="flex gap-2">
          {org.is_platform ? (
            <Badge variant="secondary">Platform org</Badge>
          ) : (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={toggleOrg.isPending}
                onClick={() => toggleOrg.mutate()}
              >
                {org.is_active ? 'Deactivate org' : 'Activate org'}
              </Button>
              <Button type="button" size="sm" onClick={() => { setForm(emptyForm); setFormError(null); setCreateOpen(true) }}>
                Add user
              </Button>
            </>
          )}
        </div>
      </div>

      <FlashAlert
        message={notice}
        onDismiss={() => setNotice(null)}
        className="border-success/30 bg-success/[0.06]"
      />

      <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-border bg-card">
        {users.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">No users in this organization.</p>
        ) : (
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-border text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-3 py-2.5 font-medium">Role</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5 pr-4 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((row) => (
                <tr key={row.id} className="border-b border-border/70 last:border-b-0">
                  <td className="px-4 py-3 align-middle">
                    <p className="font-medium">{row.full_name}</p>
                    <p className="text-xs text-muted-foreground">{row.email}</p>
                  </td>
                    <td className="px-3 py-3 align-middle">{formatAdminUserRole(row.role)}</td>
                  <td className="px-3 py-3 align-middle">
                    {row.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="secondary">Inactive</Badge>}
                  </td>
                  <td className="px-3 py-3 pr-4 align-middle">
                    {row.role === 'platform_admin' ? (
                      <p className="text-right text-xs text-muted-foreground">Platform admin</p>
                    ) : (
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
                          disabled={toggleUser.isPending}
                          onClick={() => toggleUser.mutate(row)}
                        >
                          {row.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add user</DialogTitle>
            <DialogDescription>Creates a login in {org.name}. Send them the password yourself.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              createUser.mutate()
            }}
          >
            {formError ? <p className={cn('text-sm text-destructive')}>{formError}</p> : null}
            <div>
              <Label htmlFor="new-name">Name</Label>
              <Input
                id="new-name"
                className="mt-1.5"
                value={form.fullName}
                onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
                required
                minLength={2}
              />
            </div>
            <div>
              <Label htmlFor="new-email">Email</Label>
              <Input
                id="new-email"
                type="email"
                className="mt-1.5"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                required
              />
            </div>
            <div>
              <Label htmlFor="new-role">Role</Label>
              <Select
                value={form.role}
                onValueChange={(value) => setForm((f) => ({ ...f, role: value as TenantUserRole }))}
              >
                <SelectTrigger id="new-role" className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Org admin</SelectItem>
                  <SelectItem value="recruiter">Recruiter</SelectItem>
                  <SelectItem value="viewer">Viewer</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="new-password">Temporary password</Label>
              <PasswordInput
                id="new-password"
                className="mt-1.5"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={createUser.isPending}>
              {createUser.isPending ? 'Creating…' : 'Create user'}
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
            <DialogDescription>
              Sets a new password for {resetTarget?.email}. Send it to them yourself.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              resetMutation.mutate()
            }}
          >
            <div>
              <Label htmlFor="reset-password">New password</Label>
              <PasswordInput
                id="reset-password"
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
    </div>
  )
}
