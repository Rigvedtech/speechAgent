import type { ReactElement, ReactNode } from 'react'
import { Link as RouterLink } from 'react-router-dom'

/** Marketing / Vercel build — landing page only (no /login in this bundle). */
export const LANDING_ONLY = import.meta.env.VITE_LANDING_ONLY === 'true'

/** Full app request-access URL when the marketing site is hosted separately. */
export const PRABHAT_APP_ACCESS_URL =
  (import.meta.env.VITE_GET_STARTED_URL || 'https://prabhat.rigvedtech.com/request-access').trim() ||
  'https://prabhat.rigvedtech.com/request-access'

export const PRABHAT_APP_LOGIN_URL = 'https://prabhat.rigvedtech.com/login'

/** @deprecated Prefer GetStartedLink; kept for any contact deep-links */
export const PRABHAT_CONTACT_URL = 'https://rigvedtech.com/contact'

type GetStartedLinkProps = {
  className?: string
  children: ReactNode
}

/**
 * LANDING_ONLY=true  → full-app request-access (VM)
 * LANDING_ONLY=false → /request-access on this origin
 */
export function GetStartedLink({
  className,
  children,
}: GetStartedLinkProps): ReactElement {
  if (LANDING_ONLY) {
    return (
      <a href={PRABHAT_APP_ACCESS_URL} className={className}>
        {children}
      </a>
    )
  }

  return (
    <RouterLink to="/request-access" className={className}>
      {children}
    </RouterLink>
  )
}
