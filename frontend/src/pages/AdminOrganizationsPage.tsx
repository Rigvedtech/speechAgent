import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createAdminOrganization, listAdminOrganizations, patchAdminOrganization } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
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

const emptyCreate = {
  name: '',
  adminName: '',
  adminEmail: '',
  adminPassword: '',
}

export function AdminOrganizationsPage() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'all' | 'active' | 'inactive'>('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(emptyCreate)
  const [formError, setFormError] = useState<string | null>(null)

  const orgs = useQuery({
    queryKey: queryKeys.adminOrganizations,
    queryFn: listAdminOrganizations,
  })

  const rows = useMemo(() => {
    const list = orgs.data ?? []
    const q = search.trim().toLowerCase()
    return list.filter((row) => {
      if (status === 'active' && (row.is_platform || !row.is_active)) return false
      if (status === 'inactive' && (row.is_platform || row.is_active)) return false
      if (!q) return true
      return row.name.toLowerCase().includes(q) || row.slug.toLowerCase().includes(q)
    })
  }, [orgs.data, search, status])

  const toggle = useMutation({
    mutationFn: (row: { id: string; is_active: boolean }) =>
      patchAdminOrganization(row.id, { is_active: !row.is_active }),
    onSuccess: (row) => {
      setNotice(row.is_active ? `${row.name} is active.` : `${row.name} is deactivated.`)
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminOrganizations })
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminOverview })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setNotice(formatApiError(err.message, err.detail))
      }
    },
  })

  const createMutation = useMutation({
    mutationFn: () =>
      createAdminOrganization({
        name: form.name.trim(),
        admin_full_name: form.adminName.trim(),
        admin_email: form.adminEmail.trim(),
        admin_password: form.adminPassword,
      }),
    onSuccess: (result) => {
      setCreateOpen(false)
      setForm(emptyCreate)
      setFormError(null)
      setNotice(
        `Created ${result.organization.name}. Send login ${result.login_email} and the password you set.`,
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminOrganizations })
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminOverview })
    },
    onError: (err) => {
      if (err instanceof ApiError) setFormError(formatApiError(err.message, err.detail))
      else setFormError('Could not create organization.')
    },
  })

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <Input
            className="max-w-xs"
            placeholder="Search company or slug"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="flex gap-1">
            {(['all', 'active', 'inactive'] as const).map((key) => (
              <Button
                key={key}
                type="button"
                size="sm"
                variant={status === key ? 'default' : 'outline'}
                onClick={() => setStatus(key)}
              >
                {key === 'all' ? 'All' : key === 'active' ? 'Active' : 'Inactive'}
              </Button>
            ))}
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          onClick={() => {
            setForm(emptyCreate)
            setFormError(null)
            setCreateOpen(true)
          }}
        >
          Create organization
        </Button>
      </div>

      <FlashAlert
        message={notice}
        onDismiss={() => setNotice(null)}
        className="border-success/30 bg-success/[0.06]"
      />

      <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-border bg-card">
        {orgs.isLoading ? (
          <p className="p-6 text-sm text-muted-foreground">Loading organizations…</p>
        ) : rows.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">No organizations match.</p>
        ) : (
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-border text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Company</th>
                <th className="px-3 py-2.5 font-medium">Users</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5 font-medium">Created</th>
                <th className="px-3 py-2.5 pr-4 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-border/70 last:border-b-0">
                  <td className="px-4 py-3 align-middle">
                    <Link
                      to={`/admin/organizations/${row.id}`}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {row.name}
                    </Link>
                    <p className="text-xs text-muted-foreground">{row.slug}</p>
                  </td>
                  <td className="px-3 py-3 align-middle">{row.user_count}</td>
                  <td className="px-3 py-3 align-middle">
                    {row.is_platform ? (
                      <Badge variant="secondary">Platform org</Badge>
                    ) : row.is_active ? (
                      <Badge variant="success">Active</Badge>
                    ) : (
                      <Badge variant="secondary">Inactive</Badge>
                    )}
                  </td>
                  <td className="px-3 py-3 align-middle text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(row.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-3 pr-4 align-middle">
                    <div className="flex justify-end gap-2">
                      <Button asChild variant="outline" size="sm">
                        <Link to={`/admin/organizations/${row.id}`}>Users</Link>
                      </Button>
                      {row.is_platform ? null : (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={toggle.isPending}
                          onClick={() => toggle.mutate(row)}
                        >
                          {row.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                      )}
                    </div>
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
            <DialogTitle>Create organization</DialogTitle>
            <DialogDescription>
              Creates the company and its first org admin login. Send them email + password yourself.
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
              <Label htmlFor="org-name">Company name</Label>
              <Input
                id="org-name"
                className="mt-1.5"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
                minLength={2}
              />
            </div>
            <div>
              <Label htmlFor="org-admin-name">Org admin name</Label>
              <Input
                id="org-admin-name"
                className="mt-1.5"
                value={form.adminName}
                onChange={(e) => setForm((f) => ({ ...f, adminName: e.target.value }))}
                required
                minLength={2}
              />
            </div>
            <div>
              <Label htmlFor="org-admin-email">Org admin email</Label>
              <Input
                id="org-admin-email"
                type="email"
                className="mt-1.5"
                value={form.adminEmail}
                onChange={(e) => setForm((f) => ({ ...f, adminEmail: e.target.value }))}
                required
              />
            </div>
            <div>
              <Label htmlFor="org-admin-password">Temporary password</Label>
              <PasswordInput
                id="org-admin-password"
                className="mt-1.5"
                value={form.adminPassword}
                onChange={(e) => setForm((f) => ({ ...f, adminPassword: e.target.value }))}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating…' : 'Create company'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
