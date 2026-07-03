import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { StatusResponse } from '@/types/api'

interface PhaseDialogContent {
  key: string
  title: string
  description: string
  showSpinner?: boolean
}

function resolvePhaseDialog(
  data: StatusResponse | undefined,
  setupNotStarted: boolean,
  lobbyTimeoutMin: number,
): PhaseDialogContent | null {
  if (!data || data.interview_started || data.interview_ended || data.ready_to_start) {
    return null
  }

  if (data.recall_phase === 'lobby') {
    return {
      key: 'lobby',
      title: 'Bot waiting in lobby',
      description: setupNotStarted
        ? `Admit the bot from Teams before starting. If not started within ${lobbyTimeoutMin} minutes, it will leave automatically.`
        : 'Admit the bot from Teams before starting.',
    }
  }

  if (data.recall_phase === 'in_meeting') {
    if (data.language_mode === 'hinglish' && data.localization_status === 'pending') {
      return {
        key: 'localizing',
        title: 'Preparing interview',
        description:
          'The bot is in the meeting room. Translating questions to Hinglish — this may take a moment.',
        showSpinner: true,
      }
    }

    return {
      key: 'in_meeting',
      title: 'Bot in meeting',
      description:
        'The bot was admitted to the meeting room. Wait until the status shows Ready, then click Start interview.',
    }
  }

  return null
}

interface PhaseStatusDialogProps {
  data: StatusResponse | undefined
  setupNotStarted: boolean
  lobbyTimeoutMin: number
}

export function PhaseStatusDialog({
  data,
  setupNotStarted,
  lobbyTimeoutMin,
}: PhaseStatusDialogProps) {
  const phase = resolvePhaseDialog(data, setupNotStarted, lobbyTimeoutMin)
  const [dismissedKey, setDismissedKey] = useState<string | null>(null)

  useEffect(() => {
    if (phase?.key && dismissedKey && dismissedKey !== phase.key) {
      setDismissedKey(null)
    }
  }, [phase?.key, dismissedKey])

  const open = Boolean(phase) && dismissedKey !== phase?.key

  if (!phase) return null

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && phase) {
          setDismissedKey(phase.key)
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {phase.showSpinner && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            {phase.title}
          </DialogTitle>
          <DialogDescription className="text-left leading-relaxed">
            {phase.description}
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end">
          <Button type="button" size="sm" onClick={() => setDismissedKey(phase.key)}>
            Got it
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
