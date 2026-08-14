export function formatAdminUserRole(role: string): string {
  if (role === 'platform_admin') return 'Platform admin'
  if (role === 'admin') return 'Org admin'
  if (role === 'recruiter') return 'Recruiter'
  if (role === 'viewer') return 'Viewer'
  return role.replaceAll('_', ' ')
}
