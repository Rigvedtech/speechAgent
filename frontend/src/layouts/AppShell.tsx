import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  PlusCircle,
  CalendarClock,
  FileText,
  Moon,
  Sun,
  Users,
  LogOut,
  Plug,
  Briefcase,
  Upload,
  Code2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getHealth } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'
import { useTheme } from '@/hooks/useTheme'
import { useAuth } from '@/hooks/useAuth'
import { PrabhatBrand } from '@/components/brand/PrabhatBrand'

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/interviews/new', label: 'New Interview', icon: PlusCircle },
  { to: '/interviews/scheduled', label: 'Scheduled', icon: CalendarClock },
  { to: '/jobs/bulk-upload', label: 'Job Requirements', icon: Upload },
  { to: '/coding', label: 'Coding', icon: Code2 },
  { to: '/reports', label: 'Reports', icon: FileText },
]

const pageTitles: Record<string, string> = {
  '/dashboard': 'Overview',
  '/interviews/new': 'Schedule interview',
  '/interviews/scheduled': 'Scheduled interviews',
  '/ats/jobs': 'External ATS',
  '/jobs/bulk-upload': 'Job requirements',
  '/coding': 'Coding dashboard',
  '/coding/demo': 'Coding demo',
  '/reports': 'Reports',
  '/settings/team': 'Team',
  '/settings/ats': 'ATS',
}

function resolveTitle(pathname: string) {
  if (pathname === '/interviews/new') {
    return 'Schedule interview'
  }
  if (pathname === '/interviews/scheduled') {
    return 'Scheduled interviews'
  }
  if (pathname === '/ats/jobs' || pathname.startsWith('/ats/jobs/')) {
    return 'External ATS'
  }
  if (pathname === '/jobs/bulk-upload') {
    return 'Job requirements'
  }
  if (pathname === '/coding' || pathname.startsWith('/coding/')) {
    if (pathname.startsWith('/coding/demo')) return 'Coding demo'
    return 'Coding dashboard'
  }
  if (pathname.includes('/coding')) {
    return 'Coding task'
  }
  if (pathname === '/settings/team') {
    return 'Team'
  }
  if (pathname === '/settings/ats') {
    return 'ATS connection'
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
  const navigate = useNavigate()
  const title = resolveTitle(location.pathname)
  const { theme, toggleTheme } = useTheme()
  const { user, organization, isAdmin, logout } = useAuth()

  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 30000,
    retry: 1,
  })

  const online = health.isSuccess && health.data?.status === 'healthy'
  const isInterviewWizard = location.pathname === '/interviews/new'
  const isScheduledPage = location.pathname === '/interviews/scheduled'
  const isLiveSession =
    /^\/interviews\/[^/]+$/.test(location.pathname) &&
    !location.pathname.endsWith('/report') &&
    location.pathname !== '/interviews/scheduled'
  const isReportsPage = location.pathname === '/reports'
  const isTeamPage = location.pathname === '/settings/team'
  const isAtsPage = location.pathname === '/settings/ats'
  const isAtsBrowsePage =
    location.pathname === '/ats/jobs' || location.pathname.startsWith('/ats/jobs/')
  const isBulkUploadPage = location.pathname === '/jobs/bulk-upload'
  const isCodingDashboard = location.pathname === '/coding'
  const isCodingPage =
    location.pathname.includes('/coding') || location.pathname.startsWith('/coding/')
  const isReportDetailPage = /^\/interviews\/[^/]+\/report$/.test(location.pathname)
  const isFixedHeightPage =
    isInterviewWizard ||
    isScheduledPage ||
    isLiveSession ||
    isReportsPage ||
    isReportDetailPage ||
    isTeamPage ||
    isAtsPage ||
    isAtsBrowsePage ||
    isBulkUploadPage ||
    isCodingPage

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="no-print sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
        <div className="flex h-14 shrink-0 items-center border-b border-sidebar-border px-2">
          <div className="px-3">
            <PrabhatBrand serverOnline={online} />
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
                  'surface-hover flex items-center gap-2.5 rounded-md px-3 py-2 text-base',
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
          {isAdmin ? (
            <>
              <NavLink
                to="/settings/team"
                className={({ isActive }) =>
                  cn(
                    'surface-hover flex items-center gap-2.5 rounded-md px-3 py-2 text-sm',
                    isActive
                      ? 'bg-sidebar-active font-medium text-sidebar-foreground'
                      : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
                  )
                }
              >
                <Users className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                Team
              </NavLink>
              <NavLink
                to="/ats/jobs"
                className={({ isActive }) =>
                  cn(
                    'surface-hover flex items-center gap-2.5 rounded-md px-3 py-2 text-sm',
                    isActive
                      ? 'bg-sidebar-active font-medium text-sidebar-foreground'
                      : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
                  )
                }
              >
                <Briefcase className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                External ATS
              </NavLink>
              <NavLink
                to="/settings/ats"
                className={({ isActive }) =>
                  cn(
                    'surface-hover flex items-center gap-2.5 rounded-md px-3 py-2 text-sm',
                    isActive
                      ? 'bg-sidebar-active font-medium text-sidebar-foreground'
                      : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
                  )
                }
              >
                <Plug className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                ATS
              </NavLink>
            </>
          ) : null}
        </nav>

        <div className="shrink-0 border-t border-sidebar-border p-2">
          <div className="rounded-md px-3 py-1">
            <div className="flex items-center gap-2">
              <p className="min-w-0 flex-1 truncate text-xs font-medium leading-tight text-sidebar-foreground">
                {user?.full_name}
              </p>
              <button
                type="button"
                onClick={() => {
                  logout()
                  navigate('/login', { replace: true })
                }}
                className="surface-hover inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground"
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
            </div>
            <p className="truncate text-[11px] leading-tight text-sidebar-muted text-transform: capitalize">
              {organization?.name} · {user?.role}
            </p>
          </div>
        </div>
      </aside>

      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <header
          className={cn(
            'no-print z-10 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-sidebar-border bg-sidebar px-6 backdrop-blur-sm',
            isCodingDashboard && 'min-h-14 h-auto py-2.5',
          )}
        >
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold leading-none tracking-tight">
              {title}
            </h1>
            {isCodingDashboard ? (
              <p className="mt-1 max-w-3xl text-[11px] leading-snug text-muted-foreground">
                A domain is a language track (Python, Java, …). Create one, then add up to
                5 DSA problems. Candidates stay locked to that language.
              </p>
            ) : null}
          </div>

          <button
            type="button"
            onClick={toggleTheme}
            className="surface-hover inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-card text-foreground hover:bg-muted"
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
