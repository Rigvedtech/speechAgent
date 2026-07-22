import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { registerOrg } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { PrabhatBrand } from '@/components/brand/PrabhatBrand'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { Alert } from '@/components/ui/alert'
import { Card, CardContent } from '@/components/ui/card'

export function RegisterOrgPage() {
  const navigate = useNavigate()
  const { setSession } = useAuth()
  const [organizationName, setOrganizationName] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      registerOrg({
        organization_name: organizationName.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      }),
    onSuccess: (data) => {
      setSession(data)
      navigate('/dashboard', { replace: true })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Registration failed')
      }
    },
  })

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md border-border shadow-sm">
        <CardContent className="space-y-6 p-6 sm:p-8">
          <div className="space-y-2 text-center">
            <div className="flex justify-center">
              <PrabhatBrand />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Create organization</h1>
            <p className="text-sm text-muted-foreground">
              First signup creates your company and makes you the admin.
            </p>
          </div>

          {error && (
            <Alert className="border-destructive/30 bg-destructive/5 text-destructive">{error}</Alert>
          )}

          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              setError(null)
              mutation.mutate()
            }}
          >
            <div>
              <Label htmlFor="org">Company name</Label>
              <Input
                id="org"
                className="mt-1.5"
                value={organizationName}
                onChange={(e) => setOrganizationName(e.target.value)}
                placeholder="Acme Hiring"
                required
                minLength={2}
              />
            </div>
            <div>
              <Label htmlFor="full_name">Your name</Label>
              <Input
                id="full_name"
                className="mt-1.5"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                minLength={2}
              />
            </div>
            <div>
              <Label htmlFor="email">Work email</Label>
              <Input
                id="email"
                type="email"
                className="mt-1.5"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <PasswordInput
                id="password"
                className="mt-1.5"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                At least 8 characters, including a letter and a number.
              </p>
            </div>
            <Button type="submit" className="w-full" disabled={mutation.isPending}>
              {mutation.isPending ? 'Creating…' : 'Create organization'}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
