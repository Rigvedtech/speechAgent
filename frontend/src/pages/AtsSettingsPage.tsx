import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plug, PlugZap, Unplug } from 'lucide-react'
import {
  disconnectAts,
  getAtsSettings,
  testAtsConnection,
  updateAtsSettings,
} from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { queryKeys } from '@/lib/query-keys'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'

type AuthType = 'api_key_header' | 'bearer'

const DEFAULT_CUSTOM = {
  baseUrl: 'http://localhost:1010',
  authType: 'api_key_header' as AuthType,
  authHeaderName: 'X-API-Key',
  originalDomain: 'localhost:1010',
  jobsListPath: '/api/external/v1/requirements',
  jobsListQuery: 'page=1&page_size=10',
  jobsIdField: 'request_id',
  jobsTitleField: 'job_title',
  jobsDescriptionField: 'job_description',
  jobsStatusField: 'status',
  jobsItemsKey: 'requirements',
  candidatesListPath: '/api/external/v1/requirements/{request_id}/candidates',
  candidatesDependsOn: 'request_id',
  candidatesIdField: 'student_id',
  candidatesNameField: 'name',
  candidatesEmailField: 'email',
  candidatesPhoneField: 'contact_no',
  candidatesItemsKey: 'candidates',
  jdDownloadPath: '/api/external/v1/requirements/{request_id}/jd',
  resumeDownloadPath: '/api/external/v1/candidates/{student_id}/resume',
}

function parseListQuery(raw: string): Record<string, string> {
  const out: Record<string, string> = {}
  const trimmed = raw.trim()
  if (!trimmed) return out
  try {
    if (trimmed.startsWith('{')) {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>
      for (const [k, v] of Object.entries(parsed)) {
        if (v != null) out[k] = String(v)
      }
      return out
    }
  } catch {
    /* fall through to querystring */
  }
  const params = new URLSearchParams(trimmed)
  params.forEach((v, k) => {
    out[k] = v
  })
  return out
}

function digString(cfg: Record<string, unknown>, ...path: string[]): string {
  let cur: unknown = cfg
  for (const key of path) {
    if (!cur || typeof cur !== 'object') return ''
    cur = (cur as Record<string, unknown>)[key]
  }
  return typeof cur === 'string' ? cur : cur != null ? String(cur) : ''
}

export function AtsSettingsPage() {
  const { isAdmin, session, setSession } = useAuth()
  const queryClient = useQueryClient()
  const [form, setForm] = useState(DEFAULT_CUSTOM)
  const [apiKey, setApiKey] = useState('')
  const [clearApiKey, setClearApiKey] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const settings = useQuery({
    queryKey: queryKeys.atsSettings,
    queryFn: getAtsSettings,
  })

  const syncOrgAts = (data: {
    provider: string | null
    connected_at: string | null
    is_connected: boolean
  }) => {
    if (!session) return
    setSession({
      ...session,
      organization: {
        ...session.organization,
        ats_provider: data.is_connected ? data.provider : null,
        ats_connected_at: data.is_connected ? data.connected_at : null,
      },
    })
  }

  const setField = <K extends keyof typeof DEFAULT_CUSTOM>(
    key: K,
    value: (typeof DEFAULT_CUSTOM)[K],
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  useEffect(() => {
    if (!settings.data) return
    const cfg = (settings.data.config ?? {}) as Record<string, unknown>
    if (!cfg.base_url && !settings.data.is_connected) return

    const listQuery = digString(cfg, 'jobs', 'list_query')
      ? Object.entries(
          (cfg.jobs as { list_query?: Record<string, string> })?.list_query ?? {},
        )
          .map(([k, v]) => `${k}=${v}`)
          .join('&')
      : DEFAULT_CUSTOM.jobsListQuery

    const extra =
      (cfg.extra_headers as Record<string, string> | undefined) ?? {}

    setForm({
      baseUrl: digString(cfg, 'base_url') || DEFAULT_CUSTOM.baseUrl,
      authType:
        digString(cfg, 'auth', 'type') === 'bearer' ? 'bearer' : 'api_key_header',
      authHeaderName:
        digString(cfg, 'auth', 'header_name') || DEFAULT_CUSTOM.authHeaderName,
      originalDomain:
        extra['X-Original-Domain'] || DEFAULT_CUSTOM.originalDomain,
      jobsListPath:
        digString(cfg, 'jobs', 'list_path') || DEFAULT_CUSTOM.jobsListPath,
      jobsListQuery: listQuery,
      jobsIdField:
        digString(cfg, 'jobs', 'id_field') || DEFAULT_CUSTOM.jobsIdField,
      jobsTitleField:
        digString(cfg, 'jobs', 'title_field') || DEFAULT_CUSTOM.jobsTitleField,
      jobsDescriptionField:
        digString(cfg, 'jobs', 'description_field') ||
        DEFAULT_CUSTOM.jobsDescriptionField,
      jobsStatusField:
        digString(cfg, 'jobs', 'status_field') || DEFAULT_CUSTOM.jobsStatusField,
      jobsItemsKey:
        digString(cfg, 'jobs', 'items_key') || DEFAULT_CUSTOM.jobsItemsKey,
      candidatesListPath:
        digString(cfg, 'candidates', 'list_path') ||
        DEFAULT_CUSTOM.candidatesListPath,
      candidatesDependsOn:
        digString(cfg, 'candidates', 'list_depends_on') ||
        DEFAULT_CUSTOM.candidatesDependsOn,
      candidatesIdField:
        digString(cfg, 'candidates', 'id_field') ||
        DEFAULT_CUSTOM.candidatesIdField,
      candidatesNameField:
        digString(cfg, 'candidates', 'name_field') ||
        DEFAULT_CUSTOM.candidatesNameField,
      candidatesEmailField:
        digString(cfg, 'candidates', 'email_field') ||
        DEFAULT_CUSTOM.candidatesEmailField,
      candidatesPhoneField:
        digString(cfg, 'candidates', 'phone_field') ||
        DEFAULT_CUSTOM.candidatesPhoneField,
      candidatesItemsKey:
        digString(cfg, 'candidates', 'items_key') ||
        DEFAULT_CUSTOM.candidatesItemsKey,
      jdDownloadPath:
        digString(cfg, 'downloads', 'jd_path') || DEFAULT_CUSTOM.jdDownloadPath,
      resumeDownloadPath:
        digString(cfg, 'downloads', 'resume_path') ||
        DEFAULT_CUSTOM.resumeDownloadPath,
    })
    setApiKey('')
    setClearApiKey(false)
  }, [settings.data])

  const buildConfig = () => {
    const extraHeaders: Record<string, string> = {
      Accept: 'application/json',
    }
    if (form.originalDomain.trim()) {
      extraHeaders['X-Original-Domain'] = form.originalDomain.trim()
    }
    const jobs: Record<string, unknown> = {
      list_path: form.jobsListPath.trim(),
      list_query: parseListQuery(form.jobsListQuery),
      id_field: form.jobsIdField.trim(),
      title_field: form.jobsTitleField.trim(),
      description_field: form.jobsDescriptionField.trim(),
      status_field: form.jobsStatusField.trim(),
    }
    if (form.jobsItemsKey.trim()) jobs.items_key = form.jobsItemsKey.trim()

    const candidates: Record<string, unknown> = {
      list_path: form.candidatesListPath.trim(),
      list_depends_on: form.candidatesDependsOn.trim() || undefined,
      id_field: form.candidatesIdField.trim(),
      name_field: form.candidatesNameField.trim(),
      email_field: form.candidatesEmailField.trim(),
      phone_field: form.candidatesPhoneField.trim() || 'contact_no',
    }
    if (form.candidatesItemsKey.trim()) {
      candidates.items_key = form.candidatesItemsKey.trim()
    }

    return {
      base_url: form.baseUrl.trim(),
      auth: {
        type: form.authType,
        header_name: form.authHeaderName.trim() || 'X-API-Key',
      },
      extra_headers: extraHeaders,
      jobs,
      candidates,
      downloads: {
        jd_path: form.jdDownloadPath.trim(),
        resume_path: form.resumeDownloadPath.trim(),
      },
    }
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      updateAtsSettings({
        provider: 'custom',
        test: true,
        config: buildConfig(),
        api_key: apiKey.trim() || undefined,
        clear_api_key: clearApiKey,
      }),
    onSuccess: (data) => {
      setError(null)
      setApiKey('')
      setClearApiKey(false)
      setSuccess('ATS connected and tested successfully.')
      syncOrgAts({
        provider: data.provider ?? null,
        connected_at: data.connected_at ?? null,
        is_connected: data.is_connected,
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.atsSettings })
    },
    onError: (err) => {
      setSuccess(null)
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to save ATS settings',
      )
    },
  })

  const testMutation = useMutation({
    mutationFn: testAtsConnection,
    onSuccess: (data) => {
      setError(null)
      setSuccess(data.message)
      void queryClient.invalidateQueries({ queryKey: queryKeys.atsSettings })
    },
    onError: (err) => {
      setSuccess(null)
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'ATS test failed',
      )
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: disconnectAts,
    onSuccess: (data) => {
      setSuccess('ATS disconnected.')
      setError(null)
      setApiKey('')
      setClearApiKey(false)
      syncOrgAts({
        provider: data.provider ?? null,
        connected_at: data.connected_at ?? null,
        is_connected: data.is_connected,
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.atsSettings })
    },
    onError: (err) => {
      setSuccess(null)
      setError(
        err instanceof ApiError
          ? formatApiError(err.message, err.detail)
          : 'Failed to disconnect',
      )
    },
  })

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />
  }

  const connected = Boolean(settings.data?.is_connected)
  const hasApiKey = Boolean(settings.data?.has_api_key)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CardHeader className="shrink-0 space-y-2 pb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>ATS connection</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Configure endpoints and field maps per organization. API keys are
                encrypted in the database.
              </p>
            </div>
            {connected ? (
              <Badge variant="secondary" className="gap-1">
                <PlugZap className="h-3 w-3" strokeWidth={1.5} />
                {settings.data?.provider}
              </Badge>
            ) : (
              <Badge variant="outline">Not connected</Badge>
            )}
          </div>
          {settings.data?.connected_at && (
            <p className="text-xs text-muted-foreground">
              Last connected:{' '}
              {new Date(settings.data.connected_at).toLocaleString(undefined, {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
            </p>
          )}
        </CardHeader>

        <CardContent className="min-h-0 flex-1 space-y-5 overflow-auto">
          {error && (
            <Alert className="border-destructive/30 bg-destructive/5 text-destructive">
              {error}
            </Alert>
          )}
          {success && (
            <Alert className="border-success/30 bg-success/5 text-foreground">
              {success}
            </Alert>
          )}

          {settings.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <>
              <div className="space-y-6">
                  <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
                    <h3 className="text-sm font-medium">Connection</h3>
                    <div>
                      <Label htmlFor="base_url">Base URL</Label>
                      <Input
                        id="base_url"
                        className="mt-1.5"
                        placeholder="http://localhost:1010"
                        value={form.baseUrl}
                        onChange={(e) => setField('baseUrl', e.target.value)}
                      />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <Label>Auth type</Label>
                        <Select
                          value={form.authType}
                          onValueChange={(v) =>
                            setField('authType', v as AuthType)
                          }
                        >
                          <SelectTrigger className="mt-1.5">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="api_key_header">
                              API key header (X-API-Key)
                            </SelectItem>
                            <SelectItem value="bearer">Bearer token</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      {form.authType === 'api_key_header' && (
                        <div>
                          <Label htmlFor="auth_header">Header name</Label>
                          <Input
                            id="auth_header"
                            className="mt-1.5"
                            value={form.authHeaderName}
                            onChange={(e) =>
                              setField('authHeaderName', e.target.value)
                            }
                          />
                        </div>
                      )}
                    </div>
                    <div>
                      <Label htmlFor="api_key">API key</Label>
                      <Input
                        id="api_key"
                        type="password"
                        className="mt-1.5"
                        autoComplete="new-password"
                        placeholder={
                          hasApiKey && !clearApiKey
                            ? '••••••••  (leave blank to keep existing)'
                            : 'Paste API key'
                        }
                        value={apiKey}
                        disabled={clearApiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                      />
                      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                        {hasApiKey ? (
                          <span>A key is already stored (encrypted).</span>
                        ) : (
                          <span>No key stored yet.</span>
                        )}
                        {hasApiKey && (
                          <label className="flex items-center gap-1.5">
                            <input
                              type="checkbox"
                              checked={clearApiKey}
                              onChange={(e) => {
                                setClearApiKey(e.target.checked)
                                if (e.target.checked) setApiKey('')
                              }}
                            />
                            Clear stored key
                          </label>
                        )}
                      </div>
                    </div>
                    <div>
                      <Label htmlFor="original_domain">
                        X-Original-Domain (optional)
                      </Label>
                      <Input
                        id="original_domain"
                        className="mt-1.5"
                        placeholder="localhost:1010"
                        value={form.originalDomain}
                        onChange={(e) =>
                          setField('originalDomain', e.target.value)
                        }
                      />
                    </div>
                  </section>

                  <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
                    <h3 className="text-sm font-medium">Jobs / requirements</h3>
                    <div>
                      <Label htmlFor="jobs_path">List path</Label>
                      <Input
                        id="jobs_path"
                        className="mt-1.5 font-mono text-xs"
                        value={form.jobsListPath}
                        onChange={(e) => setField('jobsListPath', e.target.value)}
                      />
                    </div>
                    <div>
                      <Label htmlFor="jobs_query">
                        List query (page=1&amp;page_size=10)
                      </Label>
                      <Input
                        id="jobs_query"
                        className="mt-1.5 font-mono text-xs"
                        value={form.jobsListQuery}
                        onChange={(e) =>
                          setField('jobsListQuery', e.target.value)
                        }
                      />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <Label>ID field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.jobsIdField}
                          onChange={(e) =>
                            setField('jobsIdField', e.target.value)
                          }
                        />
                      </div>
                      <div>
                        <Label>Title field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.jobsTitleField}
                          onChange={(e) =>
                            setField('jobsTitleField', e.target.value)
                          }
                        />
                      </div>
                      <div>
                        <Label>Description field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.jobsDescriptionField}
                          onChange={(e) =>
                            setField('jobsDescriptionField', e.target.value)
                          }
                        />
                      </div>
                      <div>
                        <Label>Status field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.jobsStatusField}
                          onChange={(e) =>
                            setField('jobsStatusField', e.target.value)
                          }
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <Label>Items key (optional, e.g. requirements)</Label>
                        <Input
                          className="mt-1.5"
                          value={form.jobsItemsKey}
                          onChange={(e) =>
                            setField('jobsItemsKey', e.target.value)
                          }
                          placeholder="auto-detect if empty"
                        />
                      </div>
                    </div>
                  </section>

                  <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
                    <h3 className="text-sm font-medium">Candidates</h3>
                    <div>
                      <Label>List path (use {'{request_id}'} placeholder)</Label>
                      <Input
                        className="mt-1.5 font-mono text-xs"
                        value={form.candidatesListPath}
                        onChange={(e) =>
                          setField('candidatesListPath', e.target.value)
                        }
                      />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <Label>Depends on (parent id name)</Label>
                        <Input
                          className="mt-1.5"
                          value={form.candidatesDependsOn}
                          onChange={(e) =>
                            setField('candidatesDependsOn', e.target.value)
                          }
                          placeholder="request_id"
                        />
                      </div>
                      <div>
                        <Label>Items key</Label>
                        <Input
                          className="mt-1.5"
                          value={form.candidatesItemsKey}
                          onChange={(e) =>
                            setField('candidatesItemsKey', e.target.value)
                          }
                        />
                      </div>
                      <div>
                        <Label>ID field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.candidatesIdField}
                          onChange={(e) =>
                            setField('candidatesIdField', e.target.value)
                          }
                        />
                      </div>
                      <div>
                        <Label>Name field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.candidatesNameField}
                          onChange={(e) =>
                            setField('candidatesNameField', e.target.value)
                          }
                        />
                      </div>
                      <div>
                        <Label>Email field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.candidatesEmailField}
                          onChange={(e) =>
                            setField('candidatesEmailField', e.target.value)
                          }
                        />
                      </div>
                      <div>
                        <Label>Phone field</Label>
                        <Input
                          className="mt-1.5"
                          value={form.candidatesPhoneField}
                          onChange={(e) =>
                            setField('candidatesPhoneField', e.target.value)
                          }
                        />
                      </div>
                    </div>
                  </section>

                  <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
                    <h3 className="text-sm font-medium">Downloads</h3>
                    <div>
                      <Label>JD download path</Label>
                      <Input
                        className="mt-1.5 font-mono text-xs"
                        value={form.jdDownloadPath}
                        onChange={(e) =>
                          setField('jdDownloadPath', e.target.value)
                        }
                      />
                    </div>
                    <div>
                      <Label>Resume download path</Label>
                      <Input
                        className="mt-1.5 font-mono text-xs"
                        value={form.resumeDownloadPath}
                        onChange={(e) =>
                          setField('resumeDownloadPath', e.target.value)
                        }
                      />
                    </div>
                  </section>
                </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  disabled={saveMutation.isPending || !form.baseUrl.trim()}
                  onClick={() => {
                    setSuccess(null)
                    saveMutation.mutate()
                  }}
                >
                  <Plug className="h-4 w-4" strokeWidth={1.5} />
                  {saveMutation.isPending ? 'Saving…' : 'Save & test'}
                </Button>
                {connected && (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={testMutation.isPending}
                      onClick={() => {
                        setSuccess(null)
                        testMutation.mutate()
                      }}
                    >
                      {testMutation.isPending ? 'Testing…' : 'Test connection'}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={disconnectMutation.isPending}
                      onClick={() => {
                        setSuccess(null)
                        disconnectMutation.mutate()
                      }}
                    >
                      <Unplug className="h-4 w-4" strokeWidth={1.5} />
                      Disconnect
                    </Button>
                  </>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
