/** Persist auth session in localStorage for API Bearer tokens. */

export interface AuthUser {
  id: string
  organization_id: string
  full_name: string
  email: string
  role: 'admin' | 'recruiter' | 'viewer'
  is_active: boolean
}

export interface AuthOrganization {
  id: string
  name: string
  slug: string
  is_active: boolean
  ats_provider?: string | null
  ats_connected_at?: string | null
}

export interface AuthSession {
  access_token: string
  user: AuthUser
  organization: AuthOrganization
}

const AUTH_KEY = 'speechagent:auth:v1'
const AUTH_EVENT = 'speechagent-auth-changed'

/** Stable snapshot for useSyncExternalStore (must not return a new object each call). */
let cachedRaw: string | null | undefined
let cachedSession: AuthSession | null = null

function parseSession(raw: string | null): AuthSession | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as AuthSession
    if (!parsed?.access_token || !parsed?.user?.id || !parsed?.organization?.id) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function loadAuth(): AuthSession | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY)
    if (raw === cachedRaw) {
      return cachedSession
    }
    cachedRaw = raw
    cachedSession = parseSession(raw)
    return cachedSession
  } catch {
    cachedRaw = null
    cachedSession = null
    return null
  }
}

export function saveAuth(session: AuthSession) {
  const raw = JSON.stringify(session)
  localStorage.setItem(AUTH_KEY, raw)
  cachedRaw = raw
  cachedSession = session
  window.dispatchEvent(new Event(AUTH_EVENT))
}

export function clearAuth() {
  localStorage.removeItem(AUTH_KEY)
  cachedRaw = null
  cachedSession = null
  window.dispatchEvent(new Event(AUTH_EVENT))
}

export function getAccessToken(): string | null {
  return loadAuth()?.access_token ?? null
}

export function subscribeAuth(listener: () => void) {
  window.addEventListener(AUTH_EVENT, listener)
  window.addEventListener('storage', listener)
  return () => {
    window.removeEventListener(AUTH_EVENT, listener)
    window.removeEventListener('storage', listener)
  }
}
