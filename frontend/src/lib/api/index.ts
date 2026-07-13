import { request } from '@/lib/api-client'
import type { FeedbackFormValues } from '@/schemas/feedback-form.schema'
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
