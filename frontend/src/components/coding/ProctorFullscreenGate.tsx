import { Maximize2 } from 'lucide-react'
import type { ProctorLiveState } from '@/lib/proctoring/types'
import {
  FULLSCREEN_SUBMIT_AT_EXIT,
  FULLSCREEN_WARN_AT_EXIT,
} from '@/lib/proctoring/types'

/**
 * Separate from 3/3 attempts: blur workspace until candidate re-enters fullscreen.
 */
export function ProctorFullscreenGate({
  state,
  onEnterFullscreen,
}: {
  state: ProctorLiveState
  onEnterFullscreen: () => void
}) {
  if (!state.fullscreenGateOpen || state.screenLocked || state.forceSubmitted) {
    return null
  }

  const exits = state.fullscreenExitCount
  const showFinalWarn = state.fullscreenFinalWarn || exits >= FULLSCREEN_WARN_AT_EXIT

  return (
    <div className="absolute inset-0 z-[54] flex items-center justify-center bg-[#0f1115]/80 px-4 backdrop-blur-md">
      <div className="w-full max-w-md rounded-2xl border border-sky-400/30 bg-[#161a22] p-6 shadow-2xl ring-1 ring-white/5">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-sky-500/15 ring-1 ring-sky-400/40">
            <Maximize2 className="h-5 w-5 text-sky-300" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold text-white">Fullscreen required</p>
            <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">
              Return to fullscreen to continue coding. Fullscreen exits are tracked separately
              from your 3 warning attempts.
            </p>
            {showFinalWarn ? (
              <p className="mt-3 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-100">
                You exited fullscreen {exits} time{exits === 1 ? '' : 's'}. The next exit will
                auto-submit your code.
              </p>
            ) : (
              <p className="mt-3 text-xs text-zinc-500">
                Exit {exits}/{FULLSCREEN_SUBMIT_AT_EXIT - 1} before final warning
              </p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onEnterFullscreen}
          className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-sky-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-sky-400"
        >
          <Maximize2 className="h-4 w-4" />
          Enter fullscreen mode
        </button>
      </div>
    </div>
  )
}
