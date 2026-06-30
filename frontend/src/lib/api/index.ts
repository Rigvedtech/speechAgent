import { request } from '@/lib/api-client'
import type {
  JoinMeetingRequest,
  JoinMeetingResponse,
  LeaveResponse,
  StartInterviewResponse,
  StatusResponse,
  SessionsResponse,
  ReportsListResponse,
  InterviewReportResponse,
  HealthResponse,
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
