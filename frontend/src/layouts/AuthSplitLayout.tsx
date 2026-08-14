import type { ReactNode } from 'react'
import { PrabhatMark } from '@/components/brand/PrabhatMark'

interface AuthSplitLayoutProps {
  children: ReactNode
}

export const AUTH_CONTROL_CLASS =
  'h-12 rounded-xl border-transparent bg-[#f4f4f4] px-4 text-[15px] shadow-none placeholder:text-neutral-400 focus-visible:border-transparent focus-visible:ring-1 focus-visible:ring-black/20'

export const AUTH_LABEL_CLASS = 'text-[13px] font-medium text-neutral-800'

export function AuthSplitLayout({ children }: AuthSplitLayoutProps) {
  return (
    <div className="min-h-dvh bg-[#2c2c2c] p-3 xl:p-4">
      <div className="grid min-h-[calc(100dvh-1.5rem)] overflow-hidden bg-white p-[14px] lg:grid-cols-[minmax(0,1.15fr)_minmax(440px,0.85fr)] xl:min-h-[calc(100dvh-2rem)] xl:p-4">
        <aside className="group relative hidden overflow-hidden bg-[#1a1814] lg:block">
          <img
            src="/auth-hero.png"
            alt=""
            className="absolute inset-0 h-full w-full origin-center object-cover object-center transition-transform duration-700 ease-out group-hover:scale-[1.06]"
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

        <main className="flex min-h-[calc(100dvh-1.5rem-28px)] flex-col bg-white lg:min-h-0">
          <div className="flex flex-1 flex-col px-8 py-8 sm:px-12 lg:px-14 lg:py-10 xl:px-16 xl:py-12">
            <div className="w-full max-w-[400px]">{children}</div>
          </div>
        </main>
      </div>
    </div>
  )
}
