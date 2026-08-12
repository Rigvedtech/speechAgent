import { AppWindow, Lock, Maximize2, Monitor, UserRound, Users } from 'lucide-react'
import type { ProctorLiveState } from '@/lib/proctoring/types'

export function ProctorLockOverlay({ state }: { state: ProctorLiveState }) {
  if (!state.screenLocked && !state.forceSubmitted) return null

  const reasonLabel =
    state.lockReason === 'multi_face'
      ? 'Multiple faces detected'
      : state.lockReason === 'tab_switch'
        ? 'Tab switch / warning limit'
        : state.lockReason === 'tab_away'
          ? 'Left tab for 10 seconds'
          : state.lockReason === 'no_face'
            ? 'Face not visible for 10 seconds'
            : state.lockReason === 'fullscreen_exit'
              ? 'Fullscreen exited too many times'
              : state.lockReason === 'second_display'
                ? 'Multiple displays detected again'
                : state.lockReason === 'camera_lost'
                ? 'Camera disconnected'
                : 'Proctoring violation'

  const Icon =
    state.lockReason === 'multi_face'
      ? Users
      : state.lockReason === 'no_face' || state.lockReason === 'camera_lost'
        ? UserRound
        : state.lockReason === 'fullscreen_exit'
          ? Maximize2
          : state.lockReason === 'second_display'
            ? Monitor
          : AppWindow

  return (
    <div className="absolute inset-0 z-[60] flex flex-col items-center justify-center gap-4 bg-[#0f1115]/92 px-6 text-center backdrop-blur-md">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-rose-500/15 ring-1 ring-rose-500/40">
        <Lock className="h-7 w-7 text-rose-300" />
      </div>
      <div className="space-y-2">
        <p className="text-xl font-semibold tracking-tight text-white">Submitting your work</p>
        <p className="inline-flex items-center gap-1.5 text-sm text-rose-200/90">
          <Icon className="h-4 w-4" />
          {reasonLabel}
        </p>
        <p className="mx-auto max-w-md text-sm leading-relaxed text-zinc-400">
          Your coding round is ending. Your latest work is being submitted automatically.
        </p>
      </div>
      <p className="text-xs text-zinc-500">Please wait — do not close this window.</p>
    </div>
  )
}
