import { useEffect, useRef, useState } from 'react'
import { Alert } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

const FADE_MS = 300
const DEFAULT_DURATION_MS = 5000

type FlashAlertProps = {
  message: string | null | undefined
  onDismiss: () => void
  className?: string
  /** Total visible time including fade-out (default 5s). */
  durationMs?: number
}

/**
 * Auto-hides success/error banners after a few seconds with a short fade.
 * Pass null/undefined message to unmount immediately.
 */
export function FlashAlert({
  message,
  onDismiss,
  className,
  durationMs = DEFAULT_DURATION_MS,
}: FlashAlertProps) {
  const onDismissRef = useRef(onDismiss)
  onDismissRef.current = onDismiss

  const [text, setText] = useState<string | null>(message ?? null)
  const [entered, setEntered] = useState(false)

  useEffect(() => {
    if (!message) {
      setEntered(false)
      setText(null)
      return
    }

    setText(message)
    setEntered(false)
    const enterId = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => setEntered(true))
    })

    const fadeDelay = Math.max(0, durationMs - FADE_MS)
    const fadeId = window.setTimeout(() => setEntered(false), fadeDelay)
    const clearId = window.setTimeout(() => {
      onDismissRef.current()
      setText(null)
    }, durationMs)

    return () => {
      window.cancelAnimationFrame(enterId)
      window.clearTimeout(fadeId)
      window.clearTimeout(clearId)
    }
  }, [message, durationMs])

  if (!text) return null

  return (
    <Alert
      className={cn(
        'transition-[opacity,transform] duration-300 ease-out',
        entered ? 'translate-y-0 opacity-100' : '-translate-y-1 opacity-0',
        className,
      )}
    >
      {text}
    </Alert>
  )
}
