import { cn } from '@/lib/utils'

const BAR_HEIGHTS = [10, 18, 14, 24, 14, 18, 10] as const
const BAR_WIDTH = 2.5
const BAR_GAP = 1.5
const MARK_HEIGHT = 24
const MARK_WIDTH = BAR_HEIGHTS.length * BAR_WIDTH + (BAR_HEIGHTS.length - 1) * BAR_GAP

interface PrabhatMarkProps {
  className?: string
}

export function PrabhatMark({ className }: PrabhatMarkProps) {
  return (
    <svg
      viewBox={`0 0 ${MARK_WIDTH} ${MARK_HEIGHT}`}
      className={cn('shrink-0 text-sidebar-foreground', className)}
      aria-hidden
    >
      {BAR_HEIGHTS.map((height, index) => (
        <rect
          key={index}
          x={index * (BAR_WIDTH + BAR_GAP)}
          y={MARK_HEIGHT - height}
          width={BAR_WIDTH}
          height={height}
          rx={BAR_WIDTH / 2}
          fill="currentColor"
        />
      ))}
    </svg>
  )
}
