import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { submitAccessRequest } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FlashAlert } from '@/components/ui/flash-alert'
import { AUTH_CONTROL_CLASS, AUTH_LABEL_CLASS, AuthSplitLayout } from '@/layouts/AuthSplitLayout'

export function RequestAccessPage() {
  const [companyName, setCompanyName] = useState('')
  const [contactName, setContactName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [website, setWebsite] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const mutation = useMutation({
    mutationFn: () =>
      submitAccessRequest({
        company_name: companyName.trim(),
        contact_name: contactName.trim(),
        email: email.trim(),
        phone: phone.trim(),
        website: website.trim() || undefined,
      }),
    onSuccess: () => {
      setDone(true)
      setError(null)
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(formatApiError(err.message, err.detail))
      } else {
        setError('Could not submit the request. Try again.')
      }
    },
  })

  return (
    <AuthSplitLayout>
      <div>
        <h1 className="font-serif text-[2rem] font-medium leading-tight tracking-tight">
          Request access
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          Access is granted by our team. Submit your details to request a login.
        </p>

        <FlashAlert
          message={error}
          onDismiss={() => setError(null)}
          className="mt-6 border-destructive/30 bg-destructive/5 text-destructive"
        />

        {done ? (
          <div className="mt-8 space-y-4">
            <p className="text-sm leading-relaxed text-muted-foreground">
              Thanks. If this request is new, our team will review it and email you if access is
              granted. You cannot sign in until then.
            </p>
            <Button asChild className="h-12 w-full rounded-xl text-[15px]">
              <Link to="/login">Back to sign in</Link>
            </Button>
          </div>
        ) : (
          <form
            className="mt-8 space-y-5"
            onSubmit={(e) => {
              e.preventDefault()
              setError(null)
              mutation.mutate()
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="company" className={AUTH_LABEL_CLASS}>
                Company name
              </Label>
              <Input
                id="company"
                className={AUTH_CONTROL_CLASS}
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Acme Hiring"
                required
                minLength={2}
                autoComplete="organization"
              />
            </div>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="contact" className={AUTH_LABEL_CLASS}>
                  Your name
                </Label>
                <Input
                  id="contact"
                  className={AUTH_CONTROL_CLASS}
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                  placeholder="Jane Shah"
                  required
                  minLength={2}
                  autoComplete="name"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone" className={AUTH_LABEL_CLASS}>
                  Phone
                </Label>
                <Input
                  id="phone"
                  type="tel"
                  className={AUTH_CONTROL_CLASS}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="98765 43210"
                  required
                  minLength={7}
                  autoComplete="tel"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className={AUTH_LABEL_CLASS}>
                Work email
              </Label>
              <Input
                id="email"
                type="email"
                className={AUTH_CONTROL_CLASS}
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <div className="hidden" aria-hidden="true">
              <Label htmlFor="website">Website</Label>
              <Input
                id="website"
                tabIndex={-1}
                autoComplete="off"
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
              />
            </div>
            <Button
              type="submit"
              className="h-12 w-full rounded-xl text-[15px]"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? 'Submitting…' : 'Request access'}
            </Button>
          </form>
        )}

        {!done ? (
          <p className="mt-8 text-sm text-muted-foreground">
            Already approved?{' '}
            <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
              Sign in
            </Link>
          </p>
        ) : null}
      </div>
    </AuthSplitLayout>
  )
}
