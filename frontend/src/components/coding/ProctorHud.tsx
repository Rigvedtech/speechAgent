import { useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { Maximize2, Shield } from 'lucide-react'
import type { ProctorLiveState } from '@/lib/proctoring/types'
import { PROCTOR_MAX_WARNINGS } from '@/lib/proctoring/types'
import { cn } from '@/lib/utils'

type CamPos = { x: number; y: number }

export function ProctorHud({
  state,
  preview,
  onRequestFullscreen,
}: {
  state: ProctorLiveState
  preview: ReactNode
  onRequestFullscreen: () => void
}) {
  const risk = state.summary?.risk_level || 'clean'
  const attempts = state.warningAttemptsLeft
  const dragRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    origX: number
    origY: number
  } | null>(null)
  const [camPos, setCamPos] = useState<CamPos | null>(null)

  const onCamPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    const rect = e.currentTarget.getBoundingClientRect()
    const x = camPos?.x ?? rect.left
    const y = camPos?.y ?? rect.top
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      origX: x,
      origY: y,
    }
    if (!camPos) setCamPos({ x, y })
  }

  const onCamPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = dragRef.current
    if (!d || d.pointerId !== e.pointerId) return
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    const w = e.currentTarget.offsetWidth
    const h = e.currentTarget.offsetHeight
    const maxX = Math.max(0, window.innerWidth - w)
    const maxY = Math.max(0, window.innerHeight - h)
    setCamPos({
      x: Math.min(maxX, Math.max(0, d.origX + dx)),
      y: Math.min(maxY, Math.max(0, d.origY + dy)),
    })
  }

  const onCamPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId === e.pointerId) {
      dragRef.current = null
      try {
        e.currentTarget.releasePointerCapture(e.pointerId)
      } catch {
        // ignore
      }
    }
  }

  return (
    <>
      <div
        className="fixed z-40 w-44 touch-none select-none overflow-hidden rounded-lg border border-white/15 bg-black/70 shadow-xl backdrop-blur"
        style={
          camPos
            ? { left: camPos.x, top: camPos.y, right: 'auto', bottom: 'auto' }
            : { right: 16, bottom: 16 }
        }
        onPointerDown={onCamPointerDown}
        onPointerMove={onCamPointerMove}
        onPointerUp={onCamPointerUp}
        onPointerCancel={onCamPointerUp}
        title="Drag to move camera preview"
      >
        <div className="pointer-events-none">{preview}</div>
        <div className="flex cursor-grab items-center justify-between gap-1 px-2 py-1 text-[10px] text-zinc-300 active:cursor-grabbing">
          <span>{state.checklist.camera ? 'Cam on' : 'Cam off'}</span>
          <span>faces {state.faceCount}</span>
        </div>
      </div>

      <div className="fixed left-1/2 top-3 z-40 flex -translate-x-1/2 flex-wrap items-center justify-center gap-2 px-3">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium backdrop-blur',
            risk === 'high'
              ? 'border-rose-400/40 bg-rose-500/20 text-rose-100'
              : risk === 'review'
                ? 'border-amber-400/40 bg-amber-500/20 text-amber-50'
                : 'border-emerald-400/30 bg-emerald-500/15 text-emerald-50',
          )}
        >
          <Shield className="h-3 w-3" />
          Proctoring · {risk}
        </span>

        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium backdrop-blur',
            state.forceSubmitted || state.finalSubmitPending || attempts <= 0
              ? 'border-rose-400/40 bg-rose-500/20 text-rose-100'
              : attempts === 1
                ? 'border-amber-400/40 bg-amber-500/20 text-amber-50'
                : 'border-white/15 bg-black/40 text-zinc-100',
          )}
          title="Warnings for tab switch / multi-face"
        >
          {state.forceSubmitted || state.finalSubmitPending
            ? 'Submitting…'
            : `Attempts left: ${attempts}/${PROCTOR_MAX_WARNINGS}`}
        </span>

        {state.faceMissingSecondsLeft != null ? (
          <span className="inline-flex items-center rounded-full border border-rose-400/40 bg-rose-500/20 px-2.5 py-1 text-[11px] font-medium text-rose-100 backdrop-blur">
            Face · {state.faceMissingSecondsLeft}s
          </span>
        ) : null}

        {state.tabAwaySecondsLeft != null ? (
          <span className="inline-flex items-center rounded-full border border-rose-400/40 bg-rose-500/20 px-2.5 py-1 text-[11px] font-medium text-rose-100 backdrop-blur">
            Tab · {state.tabAwaySecondsLeft}s
          </span>
        ) : null}

        {state.banner &&
        !state.screenLocked &&
        !state.fullscreenGateOpen &&
        !state.warningDialog ? (
          <button
            type="button"
            onClick={() => {
              if (!state.fullscreen) onRequestFullscreen()
            }}
            className="inline-flex max-w-md items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-500/20 px-3 py-1 text-[11px] text-amber-50 backdrop-blur"
          >
            {!state.fullscreen ? <Maximize2 className="h-3 w-3 shrink-0" /> : null}
            <span className="truncate">{state.banner}</span>
          </button>
        ) : null}
      </div>
    </>
  )
}
