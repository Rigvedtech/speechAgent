import { useCallback, useSyncExternalStore } from 'react'
import {
  clearAuth,
  loadAuth,
  saveAuth,
  subscribeAuth,
  type AuthSession,
} from '@/lib/auth-store'

export function useAuth() {
  const session = useSyncExternalStore(subscribeAuth, loadAuth, () => null)

  const setSession = useCallback((next: AuthSession) => {
    saveAuth(next)
  }, [])

  const logout = useCallback(() => {
    clearAuth()
  }, [])

  return {
    session,
    user: session?.user ?? null,
    organization: session?.organization ?? null,
    isAuthenticated: Boolean(session?.access_token),
    isAdmin: session?.user?.role === 'admin',
    setSession,
    logout,
  }
}
