import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { login } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { FlashAlert } from '@/components/ui/flash-alert'
import { AUTH_BUTTON_CLASS, AUTH_CONTROL_CLASS, AUTH_FOOTER_CLASS, AUTH_LABEL_CLASS, AUTH_LINK_CLASS, AUTH_SUB_CLASS, AUTH_TITLE_CLASS, AuthSplitLayout } from '@/layouts/AuthSplitLayout'
import { clearInterviewDraft } from '@/lib/draft-store'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { setSession } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const from =
    (location.state as { from?: string } | null)?.from &&
    (location.state as { from: string }).from !== '/login' &&
    !(location.state as { from: string }).from.startsWith('/interviews/new')
      ? (location.state as { from: string }).from
      : '/dashboard'

  const mutation = useMutation({
    mutationFn: () => login({ email: email.trim(), password }),
    onSuccess: (data) => {
      // Fresh session: never resume another user's in-progress schedule wizard.
      clearInterviewDraft()
      setSession(data)
      navigate(data.is_platform_admin ? '/admin' : from, { replace: true })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Login failed')
      }
    },
  })

  return (
    <AuthSplitLayout>
      <div>
        <h1 className={AUTH_TITLE_CLASS}>
          Sign in to your account
        </h1>
        <p className={AUTH_SUB_CLASS}>
          Use your organization account to schedule interviews.
        </p>

        <FlashAlert
          message={error}
          onDismiss={() => setError(null)}
          className="mt-6 border-destructive/30 bg-destructive/5 text-destructive"
        />

        <form
          className="mt-8 space-y-5"
          onSubmit={(e) => {
            e.preventDefault()
            setError(null)
            mutation.mutate()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="email" className={AUTH_LABEL_CLASS}>
              Email
            </Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="name@company.com"
              className={AUTH_CONTROL_CLASS}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password" className={AUTH_LABEL_CLASS}>
              Password
            </Label>
            <PasswordInput
              id="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              className={AUTH_CONTROL_CLASS}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
            />
          </div>
          <Button
            type="submit"
            className={AUTH_BUTTON_CLASS}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <p className={AUTH_FOOTER_CLASS}>
          Need access?{' '}
          <Link to="/request-access" className={AUTH_LINK_CLASS}>
            Request access
          </Link>
        </p>
      </div>
    </AuthSplitLayout>
  )
}
