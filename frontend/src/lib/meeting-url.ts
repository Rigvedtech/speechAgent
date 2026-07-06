/** Hint when user pasted a Teams launcher wrapper instead of a direct meet link. */
export function isTeamsLauncherUrl(url: string): boolean {
  const lower = url.toLowerCase()
  return lower.includes('/dl/launcher') || lower.includes('launcher.html')
}

export const MEETING_URL_HINT =
  'Use a direct link like https://teams.microsoft.com/meet/... In Teams: Share → Copy link. Launcher URLs (dl/launcher) are converted automatically on send.'
