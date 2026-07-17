import type { IconType } from 'react-icons'
import { BsMicrosoftTeams } from 'react-icons/bs'
import { SiGooglemeet, SiWebex, SiZoom } from 'react-icons/si'
import { Video } from 'lucide-react'
import {
  detectMeetingPlatform,
  meetingPlatformLabel,
  type MeetingPlatform,
} from '@/lib/meeting-url'
import { cn } from '@/lib/utils'

type Props = {
  url: string
  className?: string
  size?: number
}

const BRAND: Record<Exclude<MeetingPlatform, 'unknown'>, { Icon: IconType; color: string }> = {
  meet: { Icon: SiGooglemeet, color: '#00832D' },
  teams: { Icon: BsMicrosoftTeams, color: '#5059C9' },
  zoom: { Icon: SiZoom, color: '#2D8CFF' },
  webex: { Icon: SiWebex, color: '#00BCEB' },
}

export function MeetingPlatformIcon({ url, className, size = 16 }: Props) {
  const platform = detectMeetingPlatform(url)
  const label = meetingPlatformLabel(platform)

  if (platform === 'unknown') {
    return (
      <span
        className={cn(
          'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted',
          className,
        )}
        title={label}
        aria-label={label}
      >
        <Video className="text-muted-foreground" size={size} strokeWidth={1.75} aria-hidden />
      </span>
    )
  }

  const { Icon, color } = BRAND[platform]

  return (
    <span
      className={cn(
        'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-border',
        className,
      )}
      title={label}
      aria-label={label}
    >
      <Icon size={size} color={color} aria-hidden />
    </span>
  )
}
