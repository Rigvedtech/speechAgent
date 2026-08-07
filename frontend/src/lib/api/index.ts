import { request, requestFormData } from '@/lib/api-client'
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
  CameraIntegrityToggleResponse,
  JobPosting,
  CreateCandidateRequest,
  UpdateCandidateRequest,
  CreateJobPostingRequest,
  UpdateJobPostingRequest,
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
  BatchExtractSummary,
  BatchParseSummary,
  CvBatchUploadResponse,
  JdUploadResponse,
  JobResume,
  ScoreJobMatchesResponse,
  UploadBatch,
  CodingTaskSummary,
  CodingTaskDetail,
  CodingDomain,
  CodingSession,
  CodingSubmitRequest,
  CodingSubmitResponse,
  CodingWorkspace,
  CodingRunRequest,
  CodingRunResponse,
  CodingRunExamplesResponse,
  InterviewCodingConfig,
  InterviewCodingConfigOut,
  CodingLanguage,
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

export function toggleCameraIntegrity(botId: string, enabled: boolean) {
  return request<CameraIntegrityToggleResponse>(`/api/interviews/${botId}/camera-integrity`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })
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

export function listCandidates(params?: { q?: string; jobPostingId?: string }) {
  const query = new URLSearchParams()
  if (params?.q) query.set('q', params.q)
  if (params?.jobPostingId) query.set('job_posting_id', params.jobPostingId)
  const qs = query.toString() ? `?${query.toString()}` : ''
  return request<Candidate[]>(`/api/candidates${qs}`)
}

export function createCandidate(body: CreateCandidateRequest) {
  return request<Candidate>('/api/candidates', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateCandidate(candidateId: string, body: UpdateCandidateRequest) {
  return request<Candidate>(`/api/candidates/${candidateId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function listJobPostings(params?: { q?: string }) {
  const qs = params?.q ? `?q=${encodeURIComponent(params.q)}` : ''
  return request<JobPosting[]>(`/api/job-postings${qs}`)
}

export function getJobPosting(jobId: string) {
  return request<JobPosting>(`/api/job-postings/${jobId}`)
}

export function createJobPosting(body: CreateJobPostingRequest) {
  return request<JobPosting>('/api/job-postings', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateJobPosting(jobId: string, body: UpdateJobPostingRequest) {
  return request<JobPosting>(`/api/job-postings/${jobId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function uploadJobDescription(jobId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return requestFormData<JdUploadResponse>(`/api/jobs/${jobId}/upload-jd`, formData)
}

export function uploadJobResumes(jobId: string, files: File[]) {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  return requestFormData<CvBatchUploadResponse>(`/api/jobs/${jobId}/upload-cvs`, formData, {
    timeoutMs: 300000,
  })
}

export function getUploadBatch(batchId: string) {
  return request<UploadBatch>(`/api/batches/${batchId}`)
}

export function listJobResumes(jobId: string) {
  return request<JobResume[]>(`/api/jobs/${jobId}/resumes`)
}

/** Score unscored CVs against this JD (skips already scored unless force). */
export function scoreJobMatches(jobId: string, body?: { force?: boolean; candidate_ids?: string[] }) {
  return request<ScoreJobMatchesResponse>(`/api/jobs/${jobId}/score-matches`, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
    timeoutMs: 10 * 60 * 1000,
  })
}

export function extractUploadBatch(batchId: string) {
  return request<BatchExtractSummary>(`/api/batches/${batchId}/extract`, {
    method: 'POST',
    timeoutMs: 10 * 60 * 1000,
  })
}

export function parseUploadBatch(batchId: string) {
  return request<BatchParseSummary>(`/api/batches/${batchId}/parse`, {
    method: 'POST',
    timeoutMs: 10 * 60 * 1000,
  })
}

export function scheduleInterview(body: ScheduleInterviewRequest) {
  return request<ScheduleInterviewResponse>('/api/interviews/schedule', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listCodingTasks(opts?: { difficulty?: string; domain_id?: string }) {
  const params = new URLSearchParams()
  if (opts?.difficulty) params.set('difficulty', opts.difficulty)
  if (opts?.domain_id) params.set('domain_id', opts.domain_id)
  const qs = params.toString() ? `?${params.toString()}` : ''
  return request<CodingTaskSummary[]>(`/api/coding/tasks${qs}`)
}

export function listCodingDomains() {
  return request<CodingDomain[]>('/api/coding/domains')
}

export function createCodingDomain(body: {
  name: string
  language: string
  description?: string
}) {
  return request<CodingDomain>('/api/coding/domains', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listDomainCodingTasks(domainId: string, opts?: { owned_only?: boolean }) {
  const qs = opts?.owned_only ? '?owned_only=true' : ''
  return request<CodingTaskSummary[]>(
    `/api/coding/domains/${encodeURIComponent(domainId)}/tasks${qs}`,
  )
}

export function generateDomainCodingTask(domainId: string) {
  return request<CodingTaskDetail>(
    `/api/coding/domains/${encodeURIComponent(domainId)}/tasks/generate`,
    { method: 'POST', timeoutMs: 120_000 },
  )
}

export function deactivateDomainCodingTask(domainId: string, taskId: string) {
  return request<{ ok: boolean; id: string }>(
    `/api/coding/domains/${encodeURIComponent(domainId)}/tasks/${encodeURIComponent(taskId)}`,
    { method: 'DELETE' },
  )
}

export function deactivateAllDomainCodingTasks(domainId: string) {
  return request<{ ok: boolean; deleted: number }>(
    `/api/coding/domains/${encodeURIComponent(domainId)}/tasks`,
    { method: 'DELETE' },
  )
}

export function getCodingTask(taskId: string) {
  return request<CodingTaskDetail>(`/api/coding/tasks/${encodeURIComponent(taskId)}`)
}

export function putInterviewCodingConfig(interviewId: string, body: InterviewCodingConfig) {
  return request<InterviewCodingConfigOut>(
    `/api/coding/interviews/${encodeURIComponent(interviewId)}/config`,
    { method: 'PUT', body: JSON.stringify(body) },
  )
}

export function getCodingSessionByBot(botId: string) {
  return request<CodingSession>(
    `/api/coding/interviews/by-bot/${encodeURIComponent(botId)}/session`,
  )
}

export function getCodingSessionByInterview(interviewId: string) {
  return request<CodingSession>(
    `/api/coding/interviews/${encodeURIComponent(interviewId)}/session`,
  )
}

export function submitCodingByBot(botId: string, body: CodingSubmitRequest) {
  return request<CodingSubmitResponse>(
    `/api/coding/interviews/by-bot/${encodeURIComponent(botId)}/submit`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function submitCodingByInterview(interviewId: string, body: CodingSubmitRequest) {
  return request<CodingSubmitResponse>(
    `/api/coding/interviews/${encodeURIComponent(interviewId)}/submit`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function startDemoCodingSession(body?: {
  task_id?: string
  domain_id?: string
  language?: CodingLanguage
}) {
  return request<CodingSession>('/api/coding/demo/start', {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  })
}

export function getDemoCodingSession(demoToken: string) {
  return request<CodingSession>(
    `/api/coding/demo/${encodeURIComponent(demoToken)}`,
  )
}

export function submitDemoCodingSession(demoToken: string, body: CodingSubmitRequest) {
  return request<CodingSubmitResponse>(
    `/api/coding/demo/${encodeURIComponent(demoToken)}/submit`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function runCodingSnippet(body: CodingRunRequest) {
  return request<CodingRunResponse>('/api/coding/run', {
    method: 'POST',
    body: JSON.stringify(body),
    timeoutMs: 30_000,
  })
}

export function runCodingExamples(body: {
  language: string
  code: string
  task_id: string
  timeout_sec?: number
  workspace?: CodingWorkspace
}) {
  return request<CodingRunExamplesResponse>('/api/coding/run-examples', {
    method: 'POST',
    body: JSON.stringify(body),
    timeoutMs: 60_000,
  })
}

export function getPublicCodingSession(token: string) {
  return request<CodingSession>(`/api/coding/public/${encodeURIComponent(token)}`)
}

export function savePublicCodingSession(
  token: string,
  body: CodingSubmitRequest,
) {
  return request<CodingSubmitResponse>(
    `/api/coding/public/${encodeURIComponent(token)}/save`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function runPublicCodingExamples(
  token: string,
  body: {
    language?: string
    code?: string
    workspace?: CodingWorkspace
    timeout_sec?: number
  },
) {
  return request<CodingRunExamplesResponse>(
    `/api/coding/public/${encodeURIComponent(token)}/run-examples`,
    {
      method: 'POST',
      body: JSON.stringify(body),
      timeoutMs: 60_000,
    },
  )
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
