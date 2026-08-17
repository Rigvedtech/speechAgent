import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { completePasswordSetup, verifyPasswordSetup } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { Button } from '@/components/ui/button'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { FlashAlert } from '@/components/ui/flash-alert'
import {
  AUTH_BUTTON_CLASS,
  AUTH_CONTROL_CLASS,
  AUTH_FOOTER_CLASS,
  AUTH_LABEL_CLASS,
  AUTH_LINK_CLASS,
  AUTH_SUB_CLASS,
  AUTH_TITLE_CLASS,
  AuthSplitLayout,
} from '@/layouts/AuthSplitLayout'

export function SetPasswordPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const tokenRef = useRef(params.get('token')?.trim() || '')
  const token = tokenRef.current
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (params.get('token')) {
      navigate('/set-password', { replace: true })
    }
  }, [navigate, params])

  const preview = useQuery({
    queryKey: ['password-setup', token],
    queryFn: () => verifyPasswordSetup(token),
    enabled: token.length >= 20,
    retry: false,
  })

  const mutation = useMutation({
    mutationFn: () => completePasswordSetup(token, password),
    onSuccess: () => {
      navigate('/login', {
        replace: true,
        state: { notice: 'Password saved. Sign in with your email and new password.' },
      })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Could not save the password. Try again.')
      }
    },
  })

  const linkInvalid =
    token.length < 20 || (preview.isError && preview.error instanceof ApiError)

  return (
    <AuthSplitLayout>
      <div>
        <h1 className={AUTH_TITLE_CLASS}>Set your password</h1>
        <p className={AUTH_SUB_CLASS}>
          {preview.data?.full_name
            ? `Welcome, ${preview.data.full_name}. Choose a password for your Prabhat login.`
            : 'Choose a password for your Prabhat login.'}
        </p>

        <FlashAlert
          message={error}
          onDismiss={() => setError(null)}
          className="mt-6 border-destructive/30 bg-destructive/5 text-destructive"
        />

        {linkInvalid ? (
          <div className="mt-8 space-y-4">
            <p className="text-sm leading-relaxed text-neutral-500">
              This link is invalid or has expired. Ask your administrator to send a new invite.
            </p>
            <Button asChild className={AUTH_BUTTON_CLASS}>
              <Link to="/login">Back to sign in</Link>
            </Button>
          </div>
        ) : (
          <form
            className="mt-8 space-y-5"
            onSubmit={(e) => {
              e.preventDefault()
              setError(null)
              if (password !== confirm) {
                setError('Passwords do not match.')
                return
              }
              mutation.mutate()
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="new-password" className={AUTH_LABEL_CLASS}>
                New password
              </Label>
              <PasswordInput
                id="new-password"
                autoComplete="new-password"
                className={AUTH_CONTROL_CLASS}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password" className={AUTH_LABEL_CLASS}>
                Confirm password
              </Label>
              <PasswordInput
                id="confirm-password"
                autoComplete="new-password"
                className={AUTH_CONTROL_CLASS}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                minLength={8}
              />
              <p className="text-[13px] text-neutral-500">
                At least 8 characters, including a letter and a number.
              </p>
            </div>
            <Button type="submit" className={AUTH_BUTTON_CLASS} disabled={mutation.isPending || preview.isLoading}>
              {mutation.isPending ? 'Saving…' : 'Save password'}
            </Button>
          </form>
        )}

        {!linkInvalid ? (
          <p className={AUTH_FOOTER_CLASS}>
            Already set a password?{' '}
            <Link to="/login" className={AUTH_LINK_CLASS}>
              Sign in
            </Link>
          </p>
        ) : null}
      </div>
    </AuthSplitLayout>
  )
}
