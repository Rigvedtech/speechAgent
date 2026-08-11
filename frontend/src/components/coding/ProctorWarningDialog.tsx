import { AlertTriangle, AppWindow, Users } from 'lucide-react'
import type { ProctorLiveState } from '@/lib/proctoring/types'
import { PROCTOR_MAX_WARNINGS } from '@/lib/proctoring/types'

export function ProctorWarningDialog({
  state,
  onDismiss,
}: {
  state: ProctorLiveState
  onDismiss: () => void
}) {
  const dialog = state.warningDialog
  if (!dialog || state.screenLocked || state.fullscreenGateOpen) return null

  const Icon = dialog.kind === 'multi_face' ? Users : AppWindow

  return (
    <div className="absolute inset-0 z-[55] flex items-center justify-center bg-[#0f1115]/75 px-4 backdrop-blur-md">
      <div className="w-full max-w-md rounded-2xl border border-amber-400/30 bg-[#161a22] p-6 shadow-2xl ring-1 ring-white/5">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-amber-500/15 ring-1 ring-amber-400/40">
            <AlertTriangle className="h-5 w-5 text-amber-300" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold text-white">{dialog.title}</p>
            <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{dialog.message}</p>
            <p className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-amber-200">
              <Icon className="h-3.5 w-3.5" />
              Warning {dialog.warningNumber} of {PROCTOR_MAX_WARNINGS} · Attempts left:{' '}
              {dialog.attemptsLeft}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="mt-5 w-full rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-black hover:bg-amber-400"
        >
          I understand — continue
        </button>
      </div>
    </div>
  )
}
