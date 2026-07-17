/** Hint when user pasted a Teams launcher wrapper instead of a direct meet link. */
export function isTeamsLauncherUrl(url: string): boolean {
  const lower = url.toLowerCase()
  return lower.includes('/dl/launcher') || lower.includes('launcher.html')
}

export const MEETING_URL_HINT =
  'Use a direct link like https://teams.microsoft.com/meet/... In Teams: Share → Copy link. Launcher URLs (dl/launcher) are converted automatically on send.'

export type MeetingPlatform = 'teams' | 'meet' | 'zoom' | 'webex' | 'unknown'

export function detectMeetingPlatform(url: string): MeetingPlatform {
  const u = (url || '').toLowerCase()
  if (
    u.includes('teams.microsoft.com') ||
    u.includes('teams.live.com') ||
    u.includes('microsoft.com/l/meetup-join')
  ) {
    return 'teams'
  }
  if (u.includes('meet.google.com') || u.includes('google.com/meet')) {
    return 'meet'
  }
  if (u.includes('zoom.us') || u.includes('zoom.com')) {
    return 'zoom'
  }
  if (u.includes('webex.com')) {
    return 'webex'
  }
  return 'unknown'
}

export function meetingPlatformLabel(platform: MeetingPlatform): string {
  switch (platform) {
    case 'teams':
      return 'Microsoft Teams'
    case 'meet':
      return 'Google Meet'
    case 'zoom':
      return 'Zoom'
    case 'webex':
      return 'Cisco Webex'
    default:
      return 'Meeting link'
  }
}
