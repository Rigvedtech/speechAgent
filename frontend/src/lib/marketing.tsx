import type { ReactElement, ReactNode } from 'react'
import { Link as RouterLink } from 'react-router-dom'

/** Marketing / Vercel build — landing page only (no /login in this bundle). */
export const LANDING_ONLY = import.meta.env.VITE_LANDING_ONLY === 'true'

/** External site for Get Started when LANDING_ONLY=true */
export const PRABHAT_SITE_URL =
  (import.meta.env.VITE_GET_STARTED_URL || 'https://rigvedtech.com').trim() ||
  'https://rigvedtech.com'

/** @deprecated Prefer GetStartedLink; kept for any contact deep-links */
export const PRABHAT_CONTACT_URL = 'https://rigvedtech.com/contact'

type GetStartedLinkProps = {
  className?: string
  children: ReactNode
}

/**
 * LANDING_ONLY=true  → https://rigvedtech.com (or VITE_GET_STARTED_URL)
 * LANDING_ONLY=false → /login (full app)
 */
export function GetStartedLink({
  className,
  children,
}: GetStartedLinkProps): ReactElement {
  if (LANDING_ONLY) {
    return (
      <a
        href={PRABHAT_SITE_URL}
        target="_blank"
        rel="noopener noreferrer"
        className={className}
      >
        {children}
      </a>
    )
  }

  return (
    <RouterLink to="/login" className={className}>
      {children}
    </RouterLink>
  )
}
