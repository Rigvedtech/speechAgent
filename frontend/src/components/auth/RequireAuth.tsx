import { useEffect, useRef } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { getMe } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'

export function RequireAuth() {
  const { isAuthenticated, session, setSession } = useAuth()
  const location = useLocation()
  const refreshed = useRef(false)

  useEffect(() => {
    if (!isAuthenticated || !session || refreshed.current) return
    refreshed.current = true
    void getMe()
      .then((me) => {
        setSession({
          ...session,
          user: me.user,
          organization: me.organization,
          is_platform_admin: Boolean(me.is_platform_admin),
        })
      })
      .catch(() => {
        // Keep the existing session; 401 handler will sign the user out if needed.
      })
  }, [isAuthenticated, session, setSession])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}

export function RequirePlatformAdmin() {
  const { isPlatformAdmin } = useAuth()
  if (!isPlatformAdmin) {
    return <Navigate to="/dashboard" replace />
  }
  return <Outlet />
}

export function RequireTenant() {
  const { isPlatformAdmin } = useAuth()
  if (isPlatformAdmin) {
    return <Navigate to="/admin" replace />
  }
  return <Outlet />
}
