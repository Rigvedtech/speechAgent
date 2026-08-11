import type { ReactNode } from 'react'
import { Camera, CheckCircle2, Loader2, Maximize2, ShieldAlert, UserRound } from 'lucide-react'
import type { ProctorChecklist, ProctorLiveState } from '@/lib/proctoring/types'
import { cn } from '@/lib/utils'

function Row({
  ok,
  label,
  hint,
  icon: Icon,
}: {
  ok: boolean
  label: string
  hint: string
  icon: typeof Camera
}) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border px-3 py-2.5',
        ok
          ? 'border-emerald-500/30 bg-emerald-500/10'
          : 'border-white/10 bg-white/[0.03]',
      )}
    >
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', ok ? 'text-emerald-400' : 'text-zinc-400')} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-100">
          {label}{' '}
          {ok ? (
            <CheckCircle2 className="ml-1 inline h-3.5 w-3.5 text-emerald-400" />
          ) : null}
        </p>
        <p className="mt-0.5 text-xs text-zinc-400">{hint}</p>
      </div>
    </div>
  )
}

export function ProctorGate({
  state,
  taskTitle,
  timeLimitMin,
  starting,
  preview,
  onRequestFullscreen,
  onRetryCamera,
  onStart,
}: {
  state: ProctorLiveState
  taskTitle: string
  timeLimitMin: number
  starting: boolean
  preview: ReactNode
  onRequestFullscreen: () => void
  onRetryCamera: () => void
  onStart: () => void
}) {
  const c: ProctorChecklist = state.checklist
  const ready = c.camera && c.face && c.fullscreen

  return (
    <div className="flex h-full min-h-0 items-center justify-center bg-[#0f1115] px-4 py-8">
      <div className="grid w-full max-w-4xl gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-amber-300/90">
            <ShieldAlert className="h-5 w-5" />
            <p className="text-sm font-medium tracking-wide">Proctored coding round</p>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">{taskTitle}</h1>
          <p className="text-sm leading-relaxed text-zinc-400">
            Before the timer starts, enable your webcam, keep your face clearly visible, and enter
            fullscreen. Camera, focus, and paste activity are logged for review.
          </p>
          <p className="text-xs text-zinc-500">Time limit once started: {timeLimitMin} minutes</p>

          <div className="space-y-2">
            <Row
              ok={c.camera}
              icon={Camera}
              label="Webcam"
              hint={
                state.cameraError
                  ? state.cameraError
                  : c.camera
                    ? 'Camera is on'
                    : 'Allow camera access to continue'
              }
            />
            <Row
              ok={c.face}
              icon={UserRound}
              label="Single face visible"
              hint={
                c.face
                  ? 'Face check passed'
                  : state.multiFace
                    ? 'Multiple faces detected — only you should be in frame'
                    : 'Look at the camera until your face is detected'
              }
            />
            <Row
              ok={c.fullscreen}
              icon={Maximize2}
              label="Fullscreen"
              hint={
                c.fullscreen
                  ? 'Fullscreen active'
                  : 'Fullscreen is required for the coding round'
              }
            />
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            {!c.camera && (
              <button
                type="button"
                onClick={onRetryCamera}
                className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-100 hover:bg-white/10"
              >
                Retry camera
              </button>
            )}
            {!c.fullscreen && (
              <button
                type="button"
                onClick={onRequestFullscreen}
                className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-100 hover:bg-white/10"
              >
                Enter fullscreen
              </button>
            )}
            <button
              type="button"
              disabled={!ready || starting}
              onClick={onStart}
              className={cn(
                'inline-flex items-center gap-2 rounded-md px-4 py-2 text-xs font-semibold',
                ready
                  ? 'bg-sky-500 text-white hover:bg-sky-400'
                  : 'cursor-not-allowed bg-zinc-700 text-zinc-400',
              )}
            >
              {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Start coding round
            </button>
          </div>
        </div>

        <div className="relative overflow-hidden rounded-xl border border-white/10 bg-black shadow-2xl">
          {preview}
          <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-black/60 px-2 py-1 text-[11px] text-zinc-200">
            Live preview · faces: {state.faceCount}
            {state.gaze ? ` · ${state.gaze}` : ''}
          </div>
        </div>
      </div>
    </div>
  )
}
