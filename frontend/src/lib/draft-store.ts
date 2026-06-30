import type { JoinFormValues } from '@/schemas/join-form.schema'

const DRAFT_KEY = 'speechagent:interview-draft:v1'

export function saveInterviewDraft(values: JoinFormValues) {
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(values))
  } catch {
    // sessionStorage full or unavailable — ignore
  }
}

export function loadInterviewDraft(): JoinFormValues | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    return JSON.parse(raw) as JoinFormValues
  } catch {
    return null
  }
}

export function clearInterviewDraft() {
  sessionStorage.removeItem(DRAFT_KEY)
}
