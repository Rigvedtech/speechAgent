import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { submitAccessRequest } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { formatApiError } from '@/lib/error-messages'
import {
  DEFAULT_PHONE_ISO,
  PHONE_COUNTRIES,
  countryFlagSrc,
  nationalDigits,
  phoneCountry,
  phonePlaceholder,
  validateNationalNumber,
} from '@/lib/phone'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FlashAlert } from '@/components/ui/flash-alert'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { AUTH_BUTTON_CLASS, AUTH_CONTROL_CLASS, AUTH_FOOTER_CLASS, AUTH_LABEL_CLASS, AUTH_LINK_CLASS, AUTH_SUB_CLASS, AUTH_TITLE_CLASS, AuthSplitLayout } from '@/layouts/AuthSplitLayout'
import { cn } from '@/lib/utils'

function CountryFlag({ iso, className }: { iso: string; className?: string }) {
  return (
    <img
      src={countryFlagSrc(iso)}
      alt=""
      width={20}
      height={15}
      className={cn('h-[15px] w-5 shrink-0 rounded-[2px] object-cover', className)}
    />
  )
}

export function RequestAccessPage() {
  const [companyName, setCompanyName] = useState('')
  const [contactName, setContactName] = useState('')
  const [email, setEmail] = useState('')
  const [phoneIso, setPhoneIso] = useState(DEFAULT_PHONE_ISO)
  const [phoneNational, setPhoneNational] = useState('')
  const [phoneError, setPhoneError] = useState<string | null>(null)
  const [website, setWebsite] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const country = phoneCountry(phoneIso)

  const mutation = useMutation({
    mutationFn: (phone: string) =>
      submitAccessRequest({
        company_name: companyName.trim(),
        contact_name: contactName.trim(),
        email: email.trim(),
        phone,
        website: website.trim() || undefined,
      }),
    onSuccess: () => {
      setDone(true)
      setError(null)
      setPhoneError(null)
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        const message = formatApiError(err.message, err.detail)
        if (/phone|digit|country/i.test(message)) setPhoneError(message)
        else setError(message)
      } else {
        setError('Could not submit the request. Try again.')
      }
    },
  })

  return (
    <AuthSplitLayout>
      <div>
        <h1 className={AUTH_TITLE_CLASS}>
          Request access
        </h1>
        <p className={AUTH_SUB_CLASS}>
          Access is granted by our team. Submit your details to request a login.
        </p>

        <FlashAlert
          message={error}
          onDismiss={() => setError(null)}
          className="mt-6 border-destructive/30 bg-destructive/5 text-destructive"
        />

        {done ? (
          <div className="mt-8 space-y-4">
            <p className="text-sm leading-relaxed text-neutral-500">
              Thanks. If this request is new, our team will review it and email you if access is
              granted. You cannot sign in until then.
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
              const checked = validateNationalNumber(phoneIso, phoneNational)
              if (!checked.ok) {
                setPhoneError(checked.message)
                return
              }
              setPhoneError(null)
              mutation.mutate(checked.e164)
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
                placeholder="Your company"
                required
                minLength={2}
                autoComplete="organization"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact" className={AUTH_LABEL_CLASS}>
                Your name
              </Label>
              <Input
                id="contact"
                className={AUTH_CONTROL_CLASS}
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
                placeholder="Your full name"
                required
                minLength={2}
                autoComplete="name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone" className={AUTH_LABEL_CLASS}>
                Phone
              </Label>
              <div className="flex gap-2">
                <Select
                  value={phoneIso}
                  onValueChange={(iso) => {
                    setPhoneIso(iso)
                    setPhoneError(null)
                  }}
                >
                  <SelectTrigger
                    aria-label="Country code"
                    className={cn(
                      AUTH_CONTROL_CLASS,
                      'w-[6.75rem] shrink-0 justify-between gap-1.5 px-2.5 text-[13px] [&>svg]:h-3.5 [&>svg]:w-3.5 [&>svg]:opacity-40',
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      <CountryFlag iso={phoneIso} />
                      <span className="tabular-nums">+{country.dial}</span>
                    </span>
                  </SelectTrigger>
                  <SelectContent className="max-h-64 border-neutral-200 bg-white text-neutral-950">
                    {PHONE_COUNTRIES.map((row) => (
                      <SelectItem key={row.iso} value={row.iso} className="pr-3">
                        <span className="flex items-center gap-2">
                          <CountryFlag iso={row.iso} />
                          <span className="text-neutral-800">{row.name}</span>
                          <span className="tabular-nums text-neutral-400">+{row.dial}</span>
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  id="phone"
                  type="tel"
                  inputMode="numeric"
                  className={AUTH_CONTROL_CLASS}
                  value={phoneNational}
                  onChange={(e) => {
                    const next = nationalDigits(e.target.value).slice(0, country.max)
                    setPhoneNational(next)
                    setPhoneError(null)
                  }}
                  placeholder={phonePlaceholder(phoneIso)}
                  required
                  autoComplete="tel-national"
                />
              </div>
              {phoneError ? (
                <p className="text-[13px] text-red-600">{phoneError}</p>
              ) : (
                <p className="text-[13px] text-neutral-500">
                  {country.min === country.max
                    ? `${country.name}: ${country.min} digits`
                    : `${country.name}: ${country.min}–${country.max} digits`}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className={AUTH_LABEL_CLASS}>
                Work email
              </Label>
              <Input
                id="email"
                type="email"
                className={AUTH_CONTROL_CLASS}
                placeholder="you@company.com"
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
              className={AUTH_BUTTON_CLASS}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? 'Submitting…' : 'Request access'}
            </Button>
          </form>
        )}

        {!done ? (
          <p className={AUTH_FOOTER_CLASS}>
            Already approved?{' '}
            <Link to="/login" className={AUTH_LINK_CLASS}>
              Sign in
            </Link>
          </p>
        ) : null}
      </div>
    </AuthSplitLayout>
  )
}
