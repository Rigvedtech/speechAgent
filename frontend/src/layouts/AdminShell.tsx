import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Building2, Inbox, LayoutDashboard, LogOut, Moon, Shield, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useAuth } from '@/hooks/useAuth'
import { PrabhatBrand } from '@/components/brand/PrabhatBrand'

const navItems = [
  { to: '/admin', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/admin/requests', label: 'Access requests', icon: Inbox },
  { to: '/admin/organizations', label: 'Organizations', icon: Building2 },
  { to: '/admin/operators', label: 'Platform admins', icon: Shield },
]

function resolveHeader(pathname: string) {
  if (pathname.startsWith('/admin/organizations/')) {
    return { title: 'Organization', subtitle: 'Users and status for this company' }
  }
  if (pathname.startsWith('/admin/organizations')) {
    return { title: 'Organizations', subtitle: 'Customer companies and their users' }
  }
  if (pathname.startsWith('/admin/requests')) {
    return { title: 'Access requests', subtitle: 'Review, grant, or reject company sign-up requests' }
  }
  if (pathname.startsWith('/admin/operators')) {
    return { title: 'Platform admins', subtitle: 'Can grant access and manage every company' }
  }
  if (pathname === '/admin' || pathname === '/admin/') {
    return { title: 'Overview', subtitle: 'Companies, people, and interview volume' }
  }
  return { title: 'Admin', subtitle: '' }
}

export function AdminShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { theme, toggleTheme } = useTheme()
  const { user, logout } = useAuth()
  const { title, subtitle } = resolveHeader(location.pathname)
  const isOverview = location.pathname === '/admin' || location.pathname === '/admin/'

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
        <div className="flex h-14 shrink-0 items-center border-b border-sidebar-border px-2">
          <div className="px-3">
            <PrabhatBrand />
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 p-2">
          <p className="px-3 pb-1 pt-2 text-[10px] font-medium uppercase tracking-[0.14em] text-sidebar-muted">
            Platform
          </p>
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'surface-hover flex items-center gap-2.5 rounded-md px-3 py-2 text-sm',
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
          <div className="rounded-md px-3 py-1">
            <div className="flex items-center gap-2">
              <p className="min-w-0 flex-1 truncate text-xs font-medium leading-tight text-sidebar-foreground">
                {user?.full_name}
              </p>
              <button
                type="button"
                onClick={() => {
                  logout()
                  queryClient.clear()
                  navigate('/login', { replace: true })
                }}
                className="surface-hover inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground"
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
            </div>
            <p className="truncate text-[11px] leading-tight text-sidebar-muted">Platform admin</p>
          </div>
        </div>
      </aside>

      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <header className="z-10 flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-sidebar-border bg-sidebar px-6 py-2.5">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold leading-none tracking-tight">{title}</h1>
            {subtitle ? (
              <p className="mt-1 truncate text-xs text-muted-foreground">{subtitle}</p>
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
            'min-h-0 flex-1 px-6',
            isOverview ? 'overflow-hidden py-4' : 'overflow-y-auto py-5',
          )}
        >
          <div
            className={cn(
              'mx-auto flex w-full max-w-6xl flex-col',
              isOverview ? 'h-full min-h-0' : 'min-h-full',
            )}
          >
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
