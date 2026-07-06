import { useEffect, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { ArrowRight, Moon, Sun } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { PrabhatBrand } from '@/components/brand/PrabhatBrand'
import { Button } from '@/components/ui/button'
import { PRABHAT_CONTACT_URL } from '@/lib/marketing'
import { cn } from '@/lib/utils'

const navLinks = [
  { href: '#features', label: 'Features' },
  { href: '#how-it-works', label: 'How it works' },
  { href: '#faq', label: 'FAQ' },
]

export function MarketingShell() {
  const { theme, toggleTheme } = useTheme()
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const main = document.querySelector('[data-marketing-scroll]')
    if (!main) return

    const onScroll = () => setScrolled(main.scrollTop > 8)
    onScroll()
    main.addEventListener('scroll', onScroll, { passive: true })
    return () => main.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="flex h-dvh select-none flex-col overflow-hidden bg-background text-foreground">
      <header
        className={cn(
          'sticky top-0 z-20 shrink-0 border-b transition-[background-color,border-color,box-shadow] duration-300 ease-out',
          scrolled
            ? 'border-sidebar-border/80 bg-sidebar/90 shadow-[0_1px_0_rgba(0,0,0,0.04)] backdrop-blur-md dark:shadow-[0_1px_0_rgba(255,255,255,0.04)]'
            : 'border-transparent bg-transparent',
        )}
      >
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link
            to="/"
            className="surface-hover rounded-md px-1 py-0.5 transition-opacity hover:opacity-90"
          >
            <PrabhatBrand />
          </Link>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Landing sections">
            {navLinks.map(({ href, label }) => (
              <a
                key={href}
                href={href}
                className="landing-nav-link cursor-pointer rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {label}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-2">
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
            <Button asChild size="sm" className="group">
              <a href={PRABHAT_CONTACT_URL} target="_blank" rel="noopener noreferrer">
                Get started
                <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
              </a>
            </Button>
          </div>
        </div>
      </header>

      <main
        data-marketing-scroll
        className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain scroll-smooth"
      >
        <Outlet />
      </main>
    </div>
  )
}
