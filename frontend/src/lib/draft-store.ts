import { splitFullName, type JoinFormValues } from '@/schemas/join-form.schema'

import type { CvStructured, JdStructured } from '@/types/extraction'

const DRAFT_KEY = 'speechagent:interview-draft:v2'
const DRAFT_META_KEY = 'speechagent:interview-draft-meta:v3'

export interface InterviewDraftMeta {
  cvFileName?: string | null
  jdFileName?: string | null
  wizardStep?: number
  cvStructured?: CvStructured | null
  jdStructured?: JdStructured | null
  questionsGenerated?: boolean
}

const emptyDraft: JoinFormValues = {
  meeting_url: '',
  bot_name: 'Prabhat',
  candidate_first_name: '',
  candidate_last_name: '',
  language_mode: 'english',
  position_name: '',
  jdText: '',
  cvText: '',
  greeting_message: '',
  questions: [
    {
      id: '1',
      difficulty: 'Low',
      source: 'jd',
      question: '',
    },
  ],
}

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
    const parsed = JSON.parse(raw) as Partial<JoinFormValues> & { candidate_name?: string }
    let first = parsed.candidate_first_name ?? ''
    let last = parsed.candidate_last_name ?? ''
    if (!first.trim() && parsed.candidate_name?.trim()) {
      const split = splitFullName(parsed.candidate_name)
      first = split.first
      last = split.last
    }
    return {
      ...emptyDraft,
      ...parsed,
      candidate_first_name: first,
      candidate_last_name: last,
      questions: parsed.questions?.length ? parsed.questions : emptyDraft.questions,
    }
  } catch {
    return null
  }
}

export function saveInterviewDraftMeta(meta: InterviewDraftMeta) {
  try {
    sessionStorage.setItem(DRAFT_META_KEY, JSON.stringify(meta))
  } catch {
    // ignore
  }
}

export function loadInterviewDraftMeta(): InterviewDraftMeta | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_META_KEY)
    if (!raw) return null
    return JSON.parse(raw) as InterviewDraftMeta
  } catch {
    return null
  }
}

export function clearInterviewDraft() {
  sessionStorage.removeItem(DRAFT_KEY)
  sessionStorage.removeItem(DRAFT_META_KEY)
}
