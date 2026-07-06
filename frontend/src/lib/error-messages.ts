import type { ApiErrorDetail } from '@/types/api'

export function formatApiError(message: string, detail?: unknown): string {
  if (!detail || typeof detail !== 'object') return message

  const d = detail as ApiErrorDetail
  if (d.phase === 'lobby') {
    return 'Bot is in the lobby. Admit the bot from Teams before starting.'
  }
  if (d.localization_status === 'pending') {
    return 'Translating questions to Hinglish. Please wait…'
  }
  if (d.localization_status === 'failed') {
    return d.error ? `Hinglish localization failed: ${d.error}` : 'Hinglish localization failed.'
  }
  if (d.bot_id && message.toLowerCase().includes('already')) {
    return 'An interview is already active for this meeting.'
  }
  return d.message ?? message
}
