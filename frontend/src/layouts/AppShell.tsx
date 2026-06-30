import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LayoutDashboard, PlusCircle, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getHealth } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/interviews/new', label: 'New Interview', icon: PlusCircle },
  { to: '/reports', label: 'Reports', icon: FileText },
]

const pageTitles: Record<string, string> = {
  '/': 'Dashboard',
  '/interviews/new': 'New Interview',
  '/reports': 'Reports',
}

function resolveTitle(pathname: string) {
  if (pathname.startsWith('/interviews/') && pathname.endsWith('/report')) {
    return 'Interview Report'
  }
  if (pathname.startsWith('/interviews/')) {
    return 'Live Session'
  }
  return pageTitles[pathname] ?? 'SpeechAgent'
}

export function AppShell() {
  const location = useLocation()
  const title = resolveTitle(location.pathname)

  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 30000,
    retry: 1,
  })

  const online = health.isSuccess && health.data?.status === 'healthy'

  return (
    <div className="flex min-h-screen">
      <aside className="no-print w-60 shrink-0 border-r border-border bg-muted/50">
        <div className="flex h-14 items-center border-b border-border px-5">
          <span className="text-base font-semibold">SpeechAgent</span>
        </div>
        <nav className="flex flex-col gap-1 p-3">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-card font-medium text-foreground shadow-sm'
                    : 'text-muted-foreground hover:bg-card hover:text-foreground',
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print flex h-14 items-center justify-between border-b border-border bg-card px-6">
          <h1 className="text-lg font-semibold">{title}</h1>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span
              className={cn('h-2 w-2 rounded-full', online ? 'bg-success' : 'bg-destructive')}
            />
            {online ? 'Backend online' : 'Backend offline'}
          </div>
        </header>
        <main className="flex-1 px-6 py-8">
          <div className="mx-auto max-w-[1100px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
