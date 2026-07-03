import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LayoutDashboard, PlusCircle, FileText, Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getHealth } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { useTheme } from '@/hooks/useTheme'
import { PrabhatBrand } from '@/components/brand/PrabhatBrand'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/interviews/new', label: 'New Interview', icon: PlusCircle },
  { to: '/reports', label: 'Reports', icon: FileText },
]

const pageTitles: Record<string, string> = {
  '/': 'Overview',
  '/interviews/new': 'Schedule interview',
  '/reports': 'Reports',
}

function resolveTitle(pathname: string) {
  if (pathname === '/interviews/new') {
    return 'Schedule interview'
  }
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
  const { theme, toggleTheme } = useTheme()

  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 30000,
    retry: 1,
  })

  const online = health.isSuccess && health.data?.status === 'healthy'
  const isInterviewWizard = location.pathname === '/interviews/new'
  const isLiveSession =
    /^\/interviews\/[^/]+$/.test(location.pathname) &&
    !location.pathname.endsWith('/report')
  const isReportsPage = location.pathname === '/reports'
  const isReportDetailPage = /^\/interviews\/[^/]+\/report$/.test(location.pathname)
  const isFixedHeightPage =
    isInterviewWizard || isLiveSession || isReportsPage || isReportDetailPage

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sticky sidebar — same tone as header (unified shell, not black vs white) */}
      <aside className="no-print sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
        <div className="flex h-14 shrink-0 items-center border-b border-sidebar-border px-2">
          <div className="px-3">
            <PrabhatBrand />
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 p-2">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'surface-hover flex items-center gap-2.5 rounded-md px-3 py-2.5 text-base',
                  isActive
                    ? 'bg-sidebar-active font-medium text-sidebar-foreground'
                    : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="shrink-0 border-t border-sidebar-border p-2">
          <div
            className={cn(
              'flex items-center gap-2.5 rounded-md px-3 py-2.5',
              online ? 'bg-success/5' : 'bg-destructive/5',
            )}
            role="status"
            aria-live="polite"
          >
            <span className="flex h-4 w-4 shrink-0 items-center justify-center">
              <span
                className={cn(
                  'h-2 w-2 rounded-full',
                  online ? 'bg-success shadow-[0_0_6px_rgba(34,197,94,0.45)]' : 'bg-destructive',
                )}
                aria-hidden
              />
            </span>
            <span
              className={cn(
                'text-xs font-medium leading-none',
                online ? 'text-sidebar-foreground' : 'text-sidebar-muted',
              )}
            >
              {online ? 'Server is up' : 'Server is down'}
            </span>
          </div>
        </div>
      </aside>

      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <header className="no-print z-10 flex h-14 shrink-0 items-center justify-between border-b border-sidebar-border bg-sidebar px-6 backdrop-blur-sm">
          <h1 className="truncate text-base font-semibold leading-none tracking-tight">{title}</h1>

          <button
            type="button"
            onClick={toggleTheme}
            className="surface-hover inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-foreground hover:bg-muted"
            aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            title={theme === 'light' ? 'Dark mode' : 'Light mode'}
          >
            {theme === 'light' ? (
              <Moon className="h-4 w-4" strokeWidth={1.5} />
            ) : (
              <Sun className="h-4 w-4" strokeWidth={1.5} />
            )}
          </button>
        </header>

        <main
          className={cn(
            'flex-1 px-6',
            isFixedHeightPage ? 'min-h-0 overflow-hidden py-4' : 'overflow-y-auto py-8',
          )}
        >
          <div
            className={cn(
              'mx-auto max-w-[1100px]',
              isFixedHeightPage && 'flex h-full min-h-0 flex-col',
            )}
          >
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
