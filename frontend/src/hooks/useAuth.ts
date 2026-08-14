import { useCallback, useSyncExternalStore } from 'react'
import {
  clearAuth,
  loadAuth,
  saveAuth,
  subscribeAuth,
  type AuthSession,
} from '@/lib/auth-store'
import { clearInterviewDraft } from '@/lib/draft-store'

export function useAuth() {
  const session = useSyncExternalStore(subscribeAuth, loadAuth, () => null)

  const setSession = useCallback((next: AuthSession) => {
    const prevId = loadAuth()?.user?.id
    // Switching accounts must not keep the previous user's schedule wizard draft.
    if (prevId && prevId !== next.user.id) {
      clearInterviewDraft()
    }
    saveAuth(next)
  }, [])

  const logout = useCallback(() => {
    clearInterviewDraft()
    clearAuth()
  }, [])

  return {
    session,
    user: session?.user ?? null,
    organization: session?.organization ?? null,
    isAuthenticated: Boolean(session?.access_token),
    isAdmin: session?.user?.role === 'admin',
    isPlatformAdmin: Boolean(session?.is_platform_admin) || session?.user?.role === 'platform_admin',
    setSession,
    logout,
  }
}
