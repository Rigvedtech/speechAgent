import { Outlet } from 'react-router-dom'
import { Moon, Sun } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { PrabhatBrand } from '@/components/brand/PrabhatBrand'
import { Button } from '@/components/ui/button'

export function PublicShell() {
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-sidebar-border bg-sidebar px-4 sm:px-6">
        <PrabhatBrand />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-9 w-9 text-muted-foreground"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-4 py-6 sm:px-8 sm:py-10">
        <div className="mx-auto w-full max-w-2xl pb-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
