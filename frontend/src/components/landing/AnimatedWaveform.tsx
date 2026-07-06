import { cn } from '@/lib/utils'

const BAR_HEIGHTS = [10, 18, 14, 24, 14, 18, 10] as const

interface AnimatedWaveformProps {
  className?: string
  barClassName?: string
  animated?: boolean
}

export function AnimatedWaveform({
  className,
  barClassName,
  animated = true,
}: AnimatedWaveformProps) {
  return (
    <div
      className={cn('flex items-end gap-[3px]', className)}
      aria-hidden
    >
      {BAR_HEIGHTS.map((height, index) => (
        <span
          key={index}
          className={cn(
            'w-[3px] rounded-full bg-foreground/80',
            animated && 'wave-bar',
            barClassName,
          )}
          style={{
            height: `${height}px`,
            animationDelay: animated ? `${index * 90}ms` : undefined,
          }}
        />
      ))}
    </div>
  )
}
