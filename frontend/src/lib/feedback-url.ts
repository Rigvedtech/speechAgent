/** Public candidate feedback URL for a given interview bot id. */
export function buildFeedbackUrl(botId: string): string {
  const path = `/feedback/${encodeURIComponent(botId)}`
  if (typeof window !== 'undefined') {
    return `${window.location.origin}${path}`
  }
  return path
}
