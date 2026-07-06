export type LanguageMode = 'english' | 'hinglish'

export interface PlannedQuestion {
  slot: number
  id: string
  difficulty: string
  source: string
  question: string
  spoken_question: string
}

export interface QuestionBankItem {
  id: string
  difficulty: string
  source: string
  question: string
}

export interface JoinMeetingRequest {
  meeting_url: string
  bot_name?: string
  candidate_name?: string
  jdText?: string
  cvText?: string
  questions?: QuestionBankItem[]
  language_mode?: LanguageMode
  greeting_message?: string
  replace_existing?: boolean
}

export interface JoinMeetingResponse {
  success: boolean
  bot_id: string
  bot_name: string
  meeting_url: string
  status: string
  message?: string
  interview_configured?: boolean
  language_mode?: LanguageMode
  localization_status?: string
  questions_planned?: number
  planned_questions?: PlannedQuestion[]
}

export interface StatusResponse {
  bot_id: string
  status: string
  meeting_url?: string
  is_active: boolean
  recall_phase?: string
  interview_configured?: boolean
  interview_started?: boolean
  localization_status?: string
  ready_to_start?: boolean
  questions_planned?: number
  candidate_name?: string
  language_mode?: LanguageMode
  planned_questions?: PlannedQuestion[]
  current_question_slot?: number
  questions_scored?: number
  interview_phase?: string
  interview_ended?: boolean
}

export interface StartInterviewResponse {
  success: boolean
  bot_id: string
  message: string
  candidate_name: string
  language_mode: LanguageMode
  questions_planned: number
  planned_questions: PlannedQuestion[]
  planned_question_ids: string[]
  phase: string
  localization_status?: string
}

export interface LeaveResponse {
  success: boolean
  bot_id: string
  message: string
}

export interface SessionBot {
  bot_id: string
  meeting_url: string
  is_active: boolean
  is_started: boolean
  interview_ended: boolean
  interview_phase?: string
  localization_status?: string
  language_mode?: LanguageMode
  candidate_name?: string
  questions_scored: number
}

export interface SessionsResponse {
  active_sessions: number
  bots: SessionBot[]
}

export interface ReportSummary {
  bot_id: string
  candidate_name?: string
  overall_average?: number
  questions_scored?: number
  questions_planned?: number
  stopped_reason?: string
  completed_at?: string
  has_feedback?: boolean
}

export interface ReportsListResponse {
  reports: ReportSummary[]
}

export interface PerQuestionReport {
  question_index: number
  question_id: string
  difficulty: string
  source: string
  question_text: string
  answer_text: string
  score: number
  confident: boolean
  relevant: boolean
  strengths: string
  develop: string
  fix: string
  abuse_flag: boolean
}

export interface InterviewReport {
  candidate_name: string
  bot_id: string
  phase: string
  stopped_reason: string
  questions_planned: number
  questions_scored: number
  abuse_warnings: number
  continue_threshold: number
  rolling_window: number
  last_4_average?: number
  overall_average?: number
  per_question: PerQuestionReport[]
  planned_questions?: Array<{
    slot: number
    id: string
    difficulty: string
    source: string
    question: string
    asked: boolean
  }>
  summary_develop: string[]
  summary_fix: string[]
  transcript?: string[]
  completed_at?: string
}

export interface InterviewReportResponse {
  success: boolean
  report: InterviewReport
}

export interface HealthResponse {
  status: string
  service: string
  websocket_url?: string
  bot_name?: string
  lobby_timeout_minutes?: number
}

export interface ApiErrorDetail {
  message?: string
  bot_id?: string
  phase?: string
  localization_status?: string
  error?: string
  [key: string]: unknown
}

export type TechIssues = 'none' | 'minor' | 'major'
export type WouldRepeat = 'yes' | 'maybe' | 'no'

export interface CandidateFeedback {
  bot_id: string
  overall_rating: number
  clarity_rating: number
  tech_issues: TechIssues
  improve_text: string
  would_repeat?: WouldRepeat
  candidate_name?: string
  submitted_at?: string
}

export interface FeedbackContextResponse {
  success: boolean
  bot_id: string
  candidate_name?: string
  already_submitted: boolean
}

export interface FeedbackResponse {
  success: boolean
  feedback: CandidateFeedback
}

export interface SubmitFeedbackResponse {
  success: boolean
  message?: string
}
