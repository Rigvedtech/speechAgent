import { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { createUser, deleteUser, listUsers, updateUser } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import type { AuthUser, UserRole } from '@/types/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { Alert } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
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

type DialogMode = 'create' | 'edit'

const emptyForm = {
  fullName: '',
  email: '',
  password: '',
  role: 'recruiter' as UserRole,
}

export function TeamSettingsPage() {
  const { isAdmin, user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>('create')
  const [editingUser, setEditingUser] = useState<AuthUser | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [formOk, setFormOk] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AuthUser | null>(null)

  const users = useQuery({
    queryKey: queryKeys.users,
    queryFn: listUsers,
    enabled: isAdmin,
  })

  useEffect(() => {
    if (!formOk) return
    const t = window.setTimeout(() => setFormOk(null), 2500)
    return () => window.clearTimeout(t)
  }, [formOk])

  const filteredUsers = useMemo(() => {
    const list = users.data ?? []
    const q = search.trim().toLowerCase()
    if (!q) return list
    return list.filter(
      (u) =>
        u.full_name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        u.role.toLowerCase().includes(q),
    )
  }, [users.data, search])

  const openCreate = () => {
    setDialogMode('create')
    setEditingUser(null)
    setForm(emptyForm)
    setFormError(null)
    setFormOk(null)
    setDialogOpen(true)
  }

  const openEdit = (u: AuthUser) => {
    setDialogMode('edit')
    setEditingUser(u)
    setForm({
      fullName: u.full_name,
      email: u.email,
      password: '',
      role: u.role,
    })
    setFormError(null)
    setFormOk(null)
    setDialogOpen(true)
  }

  const createMutation = useMutation({
    mutationFn: () =>
      createUser({
        full_name: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
      }),
    onSuccess: () => {
      setFormOk('User created')
      setFormError(null)
      setForm(emptyForm)
      void queryClient.invalidateQueries({ queryKey: queryKeys.users })
      window.setTimeout(() => setDialogOpen(false), 900)
    },
    onError: (err) => {
      setFormOk(null)
      setFormError(
        err instanceof ApiError ? formatApiError(err.message, err.detail) : 'Could not create user',
      )
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!editingUser) throw new Error('No user selected')
      return updateUser(editingUser.id, {
        full_name: form.fullName.trim(),
        role: form.role,
        ...(form.password.trim() ? { password: form.password } : {}),
      })
    },
    onSuccess: () => {
      setFormOk('User updated')
      setFormError(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.users })
      window.setTimeout(() => setDialogOpen(false), 900)
    },
    onError: (err) => {
      setFormOk(null)
      setFormError(
        err instanceof ApiError ? formatApiError(err.message, err.detail) : 'Could not update user',
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (userId: string) => deleteUser(userId),
    onSuccess: () => {
      setDeleteTarget(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.users })
    },
  })

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />
  }

  const saving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CardHeader className="shrink-0 space-y-4 pb-4">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <CardTitle>Team members</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Manage recruiters, viewers, and admins in your organization.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative w-full max-w-sm">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                strokeWidth={1.5}
              />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, email, or role"
                className="pl-9"
                aria-label="Search team members"
              />
            </div>

            <Button type="button" size="sm" onClick={openCreate} className="shrink-0 self-start lg:self-auto">
              <Plus className="h-4 w-4" strokeWidth={1.5} />
              Add user
            </Button>
          </div>
        </CardHeader>

        <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden pb-4">
          {users.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : users.isError ? (
            <p className="text-sm text-destructive">Could not load users.</p>
          ) : !(users.data ?? []).length ? (
            <p className="text-sm text-muted-foreground">
              No members yet. Click <span className="font-medium text-foreground">Add user</span> to
              invite someone.
            </p>
          ) : !filteredUsers.length ? (
            <p className="text-sm text-muted-foreground">No members match your search.</p>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border">
              <table className="w-full table-fixed text-sm">
                <thead>
                  <tr className="border-b border-border bg-card text-left text-muted-foreground">
                    <th className="sticky top-0 z-10 w-[36%] bg-card px-4 py-2.5 font-medium">
                      Member
                    </th>
                    <th className="sticky top-0 z-10 w-[18%] bg-card px-4 py-2.5 font-medium">
                      Role
                    </th>
                    <th className="sticky top-0 z-10 w-[16%] bg-card px-4 py-2.5 font-medium">
                      Status
                    </th>
                    <th className="sticky top-0 z-10 w-[18%] bg-card px-4 py-2.5 font-medium">
                      Last login
                    </th>
                    <th className="sticky top-0 z-10 w-[12%] bg-card px-4 py-2.5 font-medium text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((u) => {
                    const isSelf = u.id === currentUser?.id
                    return (
                      <tr key={u.id} className="border-b border-border last:border-0">
                        <td className="max-w-0 px-4 py-2.5">
                          <p className="truncate font-medium text-foreground">{u.full_name}</p>
                          <p className="truncate text-xs text-muted-foreground">{u.email}</p>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="inline-flex rounded-md border border-border bg-muted/40 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                            {u.role}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          <span
                            className={cn(
                              'inline-flex items-center gap-1.5 text-xs',
                              u.is_active ? 'text-foreground' : 'text-muted-foreground',
                            )}
                          >
                            <span
                              className={cn(
                                'h-1.5 w-1.5 rounded-full',
                                u.is_active ? 'bg-success' : 'bg-muted-foreground/50',
                              )}
                            />
                            {u.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="truncate px-4 py-2.5 text-xs text-muted-foreground">
                          {u.last_login_at
                            ? new Date(u.last_login_at).toLocaleString(undefined, {
                                dateStyle: 'medium',
                                timeStyle: 'short',
                              })
                            : '—'}
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => openEdit(u)}
                              aria-label={`Edit ${u.full_name}`}
                              title="Edit user"
                            >
                              <Pencil className="h-3.5 w-3.5" strokeWidth={1.5} />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive hover:text-destructive"
                              disabled={isSelf || !u.is_active || deleteMutation.isPending}
                              onClick={() => setDeleteTarget(u)}
                              aria-label={`Deactivate ${u.full_name}`}
                              title={isSelf ? 'Cannot deactivate yourself' : 'Deactivate user'}
                            >
                              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{dialogMode === 'create' ? 'Add user' : 'Edit user'}</DialogTitle>
            <DialogDescription>
              {dialogMode === 'create'
                ? 'Create a recruiter, viewer, or admin for your organization.'
                : 'Update this member’s details. Leave password blank to keep the current one.'}
            </DialogDescription>
          </DialogHeader>

          {formError && (
            <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
              {formError}
            </Alert>
          )}
          {formOk && (
            <Alert className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
              {formOk}
            </Alert>
          )}

          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              setFormError(null)
              if (dialogMode === 'create') createMutation.mutate()
              else updateMutation.mutate()
            }}
          >
            <div>
              <Label htmlFor="team-name">Full name</Label>
              <Input
                id="team-name"
                className="mt-1.5"
                value={form.fullName}
                onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
                required
                minLength={2}
              />
            </div>
            <div>
              <Label htmlFor="team-email">Email</Label>
              <Input
                id="team-email"
                type="email"
                className="mt-1.5"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                required
                disabled={dialogMode === 'edit'}
              />
              {dialogMode === 'edit' ? (
                <p className="mt-1 text-xs text-muted-foreground">Email cannot be changed.</p>
              ) : null}
            </div>
            <div>
              <Label htmlFor="team-role">Role</Label>
              <Select
                value={form.role}
                onValueChange={(v) => setForm((f) => ({ ...f, role: v as UserRole }))}
              >
                <SelectTrigger id="team-role" className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="recruiter">Recruiter</SelectItem>
                  <SelectItem value="viewer">Viewer</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="team-password">
                {dialogMode === 'create' ? 'Temporary password' : 'New password (optional)'}
              </Label>
              <PasswordInput
                id="team-password"
                className="mt-1.5"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                required={dialogMode === 'create'}
                minLength={dialogMode === 'create' || form.password ? 8 : undefined}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Min. 8 characters with a letter and a number.
              </p>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving
                  ? dialogMode === 'create'
                    ? 'Adding…'
                    : 'Saving…'
                  : dialogMode === 'create'
                    ? 'Add user'
                    : 'Save changes'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Deactivate user?</DialogTitle>
            <DialogDescription>
              {deleteTarget
                ? `${deleteTarget.full_name} will no longer be able to sign in. You can keep their history in the organization.`
                : null}
            </DialogDescription>
          </DialogHeader>
          {deleteMutation.isError ? (
            <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
              {deleteMutation.error instanceof ApiError
                ? formatApiError(deleteMutation.error.message, deleteMutation.error.detail)
                : 'Could not deactivate user'}
            </Alert>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={deleteMutation.isPending || !deleteTarget}
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              {deleteMutation.isPending ? 'Deactivating…' : 'Deactivate'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
