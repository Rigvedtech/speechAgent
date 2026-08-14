import { Navigate } from 'react-router-dom'

/** Public org signup is closed. Keep this path so old links still work. */
export function RegisterOrgPage() {
  return <Navigate to="/request-access" replace />
}
