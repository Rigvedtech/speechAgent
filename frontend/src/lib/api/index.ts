import { request } from '@/lib/api-client'
import type { FeedbackFormValues } from '@/schemas/feedback-form.schema'
import type { AuthSession } from '@/lib/auth-store'
import type {
  JoinMeetingRequest,
  JoinMeetingResponse,
  LeaveResponse,
  RejoinResponse,
  StartInterviewResponse,
  StatusResponse,
  SessionsResponse,
  ReportsListResponse,
  InterviewReportResponse,
  HealthResponse,
  FeedbackContextResponse,
  FeedbackResponse,
  SubmitFeedbackResponse,
  Candidate,
  JobPosting,
  CreateCandidateRequest,
  CreateJobPostingRequest,
  CreateUserRequest,
  UpdateUserRequest,
  AuthUser,
  ScheduleInterviewRequest,
  ScheduleInterviewResponse,
  ScheduledInterview,
  DocumentRecord,
  DocumentDetail,
  AtsSettings,
  AtsSettingsUpdate,
  AtsTestResult,
  AtsRemoteCandidate,
  AtsJobsPage,
  AtsJobDetail,
  AtsCandidateDetail,
} from '@/types/api'

export function joinMeeting(body: JoinMeetingRequest) {
  return request<JoinMeetingResponse>('/api/join', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getBotStatus(botId: string) {
  return request<StatusResponse>(`/api/status/${botId}`)
}

export function startInterview(botId: string, body: Record<string, never> = {}) {
  return request<StartInterviewResponse>(`/api/start/${botId}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function leaveMeeting(botId: string) {
  return request<LeaveResponse>(`/api/leave/${botId}`, { method: 'DELETE' })
}

export function rejoinBot(botId: string) {
  return request<RejoinResponse>(`/api/rejoin/${botId}`, { method: 'POST' })
}

export function cancelInterviewSetup(botId: string) {
  return request<LeaveResponse>(`/api/interviews/${botId}/cancel`, { method: 'POST' })
}

export function listSessions() {
  return request<SessionsResponse>('/api/sessions')
}

export function listReports() {
  return request<ReportsListResponse>('/api/reports')
}

export function getInterviewReport(botId: string) {
  return request<InterviewReportResponse>(`/api/interview/${botId}/report`)
}

export function getHealth() {
  return request<HealthResponse>('/health')
}

export function getFeedbackContext(botId: string) {
  return request<FeedbackContextResponse>(`/api/feedback/${botId}/context`)
}

export function getFeedback(botId: string) {
  return request<FeedbackResponse>(`/api/feedback/${botId}`)
}

export function submitFeedback(botId: string, body: FeedbackFormValues) {
  return request<SubmitFeedbackResponse>(`/api/feedback/${botId}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function registerOrg(body: {
  organization_name: string
  organization_slug?: string
  full_name: string
  email: string
  password: string
}) {
  return request<AuthSession>('/api/auth/register-org', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function login(body: { email: string; password: string }) {
  return request<AuthSession>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getMe() {
  return request<{ user: AuthUser; organization: AuthSession['organization'] }>('/api/auth/me')
}

export function listUsers() {
  return request<AuthUser[]>('/api/users')
}

export function createUser(body: CreateUserRequest) {
  return request<AuthUser>('/api/users', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateUser(userId: string, body: UpdateUserRequest) {
  return request<AuthUser>(`/api/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteUser(userId: string) {
  return request<AuthUser>(`/api/users/${userId}`, {
    method: 'DELETE',
  })
}

export function listCandidates(params?: { q?: string }) {
  const qs = params?.q ? `?q=${encodeURIComponent(params.q)}` : ''
  return request<Candidate[]>(`/api/candidates${qs}`)
}

export function createCandidate(body: CreateCandidateRequest) {
  return request<Candidate>('/api/candidates', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listJobPostings(params?: { q?: string }) {
  const qs = params?.q ? `?q=${encodeURIComponent(params.q)}` : ''
  return request<JobPosting[]>(`/api/job-postings${qs}`)
}

export function createJobPosting(body: CreateJobPostingRequest) {
  return request<JobPosting>('/api/job-postings', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function scheduleInterview(body: ScheduleInterviewRequest) {
  return request<ScheduleInterviewResponse>('/api/interviews/schedule', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listScheduledInterviews() {
  return request<ScheduledInterview[]>('/api/interviews/scheduled')
}

export function cancelScheduledInterview(interviewId: string) {
  return request<ScheduledInterview>(
    `/api/interviews/scheduled/${interviewId}/cancel`,
    { method: 'POST' },
  )
}

export function sendScheduledToLobby(
  interview: Pick<ScheduledInterview, 'id' | 'meeting_url'>,
  replaceExisting = false,
) {
  return joinMeeting({
    meeting_url: interview.meeting_url,
    interview_id: interview.id,
    replace_existing: replaceExisting,
  })
}

export function listDocuments(params?: {
  document_type?: 'cv' | 'jd'
  candidate_id?: string
  status?: string
}) {
  const qs = new URLSearchParams()
  if (params?.document_type) qs.set('document_type', params.document_type)
  if (params?.candidate_id) qs.set('candidate_id', params.candidate_id)
  if (params?.status) qs.set('status', params.status)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request<DocumentRecord[]>(`/api/documents${suffix}`)
}

export function getDocument(documentId: string) {
  return request<DocumentDetail>(`/api/documents/${documentId}`)
}

export function getAtsSettings() {
  return request<AtsSettings>('/api/ats/settings')
}

export function updateAtsSettings(body: AtsSettingsUpdate) {
  return request<AtsSettings>('/api/ats/settings', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function testAtsConnection() {
  return request<AtsTestResult>('/api/ats/test', { method: 'POST' })
}

export function disconnectAts() {
  return request<AtsSettings>('/api/ats/disconnect', { method: 'POST' })
}

export function listAtsCandidates(params?: { q?: string; request_id?: string }) {
  const qs = new URLSearchParams()
  if (params?.q) qs.set('q', params.q)
  if (params?.request_id) qs.set('request_id', params.request_id)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request<AtsRemoteCandidate[]>(`/api/ats/candidates${suffix}`)
}

export function listAtsJobs(params?: { q?: string; page?: number; page_size?: number }) {
  const qs = new URLSearchParams()
  if (params?.q) qs.set('q', params.q)
  if (params?.page) qs.set('page', String(params.page))
  if (params?.page_size) qs.set('page_size', String(params.page_size))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request<AtsJobsPage>(`/api/ats/jobs${suffix}`)
}

export function getAtsJob(externalId: string) {
  return request<AtsJobDetail>(`/api/ats/jobs/${encodeURIComponent(externalId)}`)
}

export function getAtsCandidate(externalId: string, requestId?: string) {
  const qs = new URLSearchParams()
  if (requestId) qs.set('request_id', requestId)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request<AtsCandidateDetail>(
    `/api/ats/candidates/${encodeURIComponent(externalId)}${suffix}`,
  )
}

export function importAtsCandidate(externalId: string, parentId?: string) {
  return request<Candidate>('/api/ats/import/candidate', {
    method: 'POST',
    body: JSON.stringify({
      external_id: externalId,
      ...(parentId ? { parent_id: parentId } : {}),
    }),
  })
}

export function importAtsJob(externalId: string) {
  return request<JobPosting>('/api/ats/import/job', {
    method: 'POST',
    body: JSON.stringify({ external_id: externalId }),
  })
}

/** Open ATS JD/resume in a new tab via authenticated proxy. */
export async function openAtsFilePreview(
  kind: 'job' | 'candidate',
  externalId: string,
  parentId?: string,
) {
  const { getAccessToken } = await import('@/lib/auth-store')
  const base = import.meta.env.VITE_API_BASE_URL ?? ''
  const path =
    kind === 'job'
      ? `/api/ats/jobs/${encodeURIComponent(externalId)}/file`
      : `/api/ats/candidates/${encodeURIComponent(externalId)}/file${
          parentId ? `?request_id=${encodeURIComponent(parentId)}` : ''
        }`
  const token = getAccessToken()
  const res = await fetch(`${base}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    let message = `Preview failed (${res.status})`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* keep default */
    }
    throw new Error(message)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
