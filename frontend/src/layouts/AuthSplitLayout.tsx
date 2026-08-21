import type { ReactNode } from 'react'
import { PrabhatMark } from '@/components/brand/PrabhatMark'

interface AuthSplitLayoutProps {
  children: ReactNode
}

export const AUTH_CONTROL_CLASS =
  'h-12 rounded-xl border-transparent bg-[#f4f4f4] px-4 text-[15px] text-neutral-950 shadow-none placeholder:text-neutral-400 focus-visible:border-transparent focus-visible:ring-1 focus-visible:ring-black/20'

export const AUTH_LABEL_CLASS = 'text-[13px] font-medium text-neutral-800'

export const AUTH_TITLE_CLASS =
  'font-serif text-[2rem] font-medium leading-tight tracking-tight text-neutral-950'

export const AUTH_SUB_CLASS = 'mt-3 text-sm leading-relaxed text-neutral-500'

export const AUTH_FOOTER_CLASS = 'mt-8 text-sm text-neutral-500'

export const AUTH_LINK_CLASS = 'font-medium text-neutral-950 underline-offset-4 hover:underline'

export const AUTH_BUTTON_CLASS =
  'h-12 w-full rounded-xl bg-neutral-950 text-[15px] text-white hover:bg-neutral-800 hover:opacity-100'

export function AuthSplitLayout({ children }: AuthSplitLayoutProps) {
  return (
    <div className="auth-split h-dvh overflow-hidden bg-[#2c2c2c] p-3 text-neutral-950 xl:p-4">
      <div className="grid h-full overflow-hidden bg-white p-[14px] lg:grid-cols-[minmax(0,1.15fr)_minmax(440px,0.85fr)]">
        <aside className="group relative hidden h-full min-h-0 overflow-hidden bg-[#1a1814] lg:block">
          <img
            src="/auth-hero.png"
            alt=""
            className="absolute inset-0 size-full origin-center object-cover object-center will-change-transform transition-transform duration-[1400ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-[1.08] motion-reduce:transition-none motion-reduce:group-hover:scale-100"
          />
          <div
            className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/5 to-transparent"
            aria-hidden
          />
          <div className="absolute left-8 top-8 xl:left-10 xl:top-10">
            <div className="flex items-center gap-2.5 text-white">
              <PrabhatMark className="h-4 w-auto text-white" />
              <span className="text-xl font-semibold tracking-wide">
                PRABHAT<span className="text-white/80">.</span>
              </span>
            </div>
          </div>
          <div className="absolute inset-x-0 bottom-0 p-8 xl:p-10">
            <div className="max-w-md">
              <p className="font-serif text-3xl font-medium tracking-tight text-white xl:text-[2.15rem]">
                Dawn of clearer hiring.
              </p>
              <p className="mt-2 text-sm leading-relaxed text-white/80">
                AI interviews for hiring teams.
              </p>
            </div>
          </div>
        </aside>

        <main className="flex h-full min-h-0 flex-col overflow-y-auto bg-white text-neutral-950">
          <div className="flex min-h-full flex-1 flex-col items-center justify-center px-8 py-8 sm:px-12 lg:px-14 lg:py-10 xl:px-16 xl:py-12">
            <div className="w-full max-w-[400px]">
              <div className="mb-8 flex items-center gap-2.5">
                <PrabhatMark className="h-4 w-auto text-neutral-950" />
                <span className="text-xl font-semibold tracking-wide text-neutral-950">
                  PRABHAT<span className="text-[#7c3aed]">.</span>
                </span>
              </div>
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
