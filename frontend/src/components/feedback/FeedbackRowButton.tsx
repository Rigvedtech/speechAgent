import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface FeedbackRowButtonProps {
  hasFeedback?: boolean
  onViewSubmitted: () => void
}

export function FeedbackRowButton({ hasFeedback, onViewSubmitted }: FeedbackRowButtonProps) {
  const [pendingOpen, setPendingOpen] = useState(false)

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="cursor-pointer"
        onClick={() => {
          if (hasFeedback) onViewSubmitted()
          else setPendingOpen(true)
        }}
      >
        Feedback
      </Button>

      <Dialog open={pendingOpen} onOpenChange={setPendingOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Feedback pending</DialogTitle>
            <DialogDescription>Feedback is not submitted.</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </>
  )
}
