import type { LanguageMode } from '@/types/api'

const STORAGE_KEY = 'speechagent:sessions:v1'
const MAX_SESSIONS = 50

export interface StoredSession {
  botId: string
  candidateName: string
  meetingUrl: string
  languageMode: LanguageMode
  createdAt: string
  lastSeenPhase?: string
  completed?: boolean
}

function readAll(): StoredSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as StoredSession[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeAll(sessions: StoredSession[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, MAX_SESSIONS)))
}

export function upsertSession(session: StoredSession) {
  const all = readAll().filter((s) => s.botId !== session.botId)
  all.unshift(session)
  writeAll(all)
}

export function updateSessionPhase(botId: string, phase: string) {
  const all = readAll()
  const idx = all.findIndex((s) => s.botId === botId)
  if (idx === -1) return
  all[idx] = { ...all[idx], lastSeenPhase: phase }
  writeAll(all)
}

export function markSessionCompleted(botId: string) {
  const all = readAll()
  const idx = all.findIndex((s) => s.botId === botId)
  if (idx === -1) return
  all[idx] = { ...all[idx], completed: true, lastSeenPhase: 'ended' }
  writeAll(all)
}

export function getStoredSessions(): StoredSession[] {
  return readAll()
}

export function getStoredSession(botId: string): StoredSession | undefined {
  return readAll().find((s) => s.botId === botId)
}
