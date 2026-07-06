import { cn } from '@/lib/utils'

type PlatformId = 'teams' | 'zoom' | 'meet' | 'webex'

interface Platform {
  id: PlatformId
  name: string
  icon: string
}

export const PLATFORMS: Platform[] = [
  { id: 'teams', name: 'Microsoft Teams', icon: '/platforms/teams.png' },
  { id: 'zoom', name: 'Zoom', icon: '/platforms/zoom.png' },
  { id: 'meet', name: 'Google Meet', icon: '/platforms/meet.png' },
  { id: 'webex', name: 'Webex', icon: '/platforms/webex.png' },
]

interface PlatformBadgeProps {
  platform: Platform
  className?: string
}

export function PlatformBadge({ platform, className }: PlatformBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex cursor-pointer items-center gap-2.5 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-foreground shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-[transform,border-color,box-shadow] duration-300 hover:-translate-y-px hover:border-foreground/15 hover:shadow-[0_4px_12px_-6px_rgba(0,0,0,0.12)] dark:shadow-[0_1px_2px_rgba(0,0,0,0.2)] dark:hover:shadow-[0_4px_12px_-6px_rgba(0,0,0,0.45)]',
        className,
      )}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border/60 bg-background p-1">
        <img
          src={platform.icon}
          alt=""
          width={24}
          height={24}
          className="h-6 w-6 object-contain"
          loading="lazy"
          decoding="async"
        />
      </span>
      {platform.name}
    </span>
  )
}
