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
  interview_id?: string
  candidate_id?: string
  job_posting_id?: string
  job_title?: string
  document_extraction_id?: string
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
  interview_id?: string
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

export interface RejoinResponse {
  success: boolean
  old_bot_id: string
  new_bot_id: string
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

export type UserRole = 'admin' | 'recruiter' | 'viewer'

export interface AuthUser {
  id: string
  organization_id: string
  full_name: string
  email: string
  role: UserRole
  is_active: boolean
  last_login_at?: string | null
  created_at?: string
}

export interface Candidate {
  id: string
  organization_id: string
  created_by: string
  full_name: string
  email?: string | null
  phone?: string | null
  cv_text?: string | null
  notes?: string | null
  source: string
  external_ats_id?: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface JobPosting {
  id: string
  organization_id: string
  created_by: string
  job_title: string
  jd_text?: string | null
  description?: string | null
  status: string
  source: string
  external_ats_id?: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CreateCandidateRequest {
  full_name: string
  email?: string
  phone?: string
  cv_text?: string
  notes?: string
  source?: 'manual' | 'upload'
}

export interface CreateJobPostingRequest {
  job_title: string
  jd_text?: string
  description?: string
  status?: 'draft' | 'open' | 'closed' | 'filled'
  source?: 'manual' | 'upload'
}

export interface CreateUserRequest {
  full_name: string
  email: string
  password: string
  role: UserRole
}

export interface UpdateUserRequest {
  full_name?: string
  role?: UserRole
  is_active?: boolean
  password?: string
}

export interface ScheduledInterview {
  id: string
  candidate_id: string
  job_posting_id: string
  candidate_name: string
  job_title: string
  meeting_url: string
  language_mode: LanguageMode
  bot_name: string
  questions_planned: number
  created_at: string
  candidate_full_name?: string | null
  job_posting_title?: string | null
}

export interface ScheduleInterviewRequest {
  meeting_url: string
  candidate_id: string
  job_posting_id: string
  candidate_name: string
  job_title: string
  jdText: string
  cvText: string
  questions: QuestionBankItem[]
  language_mode?: LanguageMode
  bot_name?: string
  greeting_message?: string
  document_extraction_id?: string
}

export interface ScheduleInterviewResponse {
  success: boolean
  interview: ScheduledInterview
  message?: string
}

export interface DocumentRecord {
  id: string
  organization_id: string
  uploaded_by?: string | null
  candidate_id?: string | null
  document_type: 'cv' | 'jd' | string
  source: string
  external_ats_id?: string | null
  original_filename?: string | null
  mime_type?: string | null
  file_size_bytes?: number | null
  upload_status: string
  has_extracted_text: boolean
  created_at: string
  updated_at: string
}

export interface DocumentDetail extends DocumentRecord {
  extracted_text?: string | null
  storage_path?: string | null
}

export interface AtsSettings {
  provider?: string | null
  config: Record<string, unknown>
  connected_at?: string | null
  is_connected: boolean
  has_api_key: boolean
  supported_providers: string[]
}

export interface AtsSettingsUpdate {
  provider: 'demo' | 'custom'
  config?: Record<string, unknown>
  api_key?: string
  clear_api_key?: boolean
  test?: boolean
}

export interface AtsTestResult {
  ok: boolean
  provider: string
  message: string
  candidates?: number
  jobs?: number
}

export interface AtsRemoteCandidate {
  external_id: string
  full_name: string
  email?: string | null
  phone?: string | null
  has_cv_text: boolean
  has_cv_url: boolean
  already_imported: boolean
  local_candidate_id?: string | null
}

export interface AtsRemoteJob {
  external_id: string
  job_title: string
  description?: string | null
  has_jd_text: boolean
  has_jd_url: boolean
  already_imported: boolean
  local_job_posting_id?: string | null
}

export interface AtsJobDetail {
  external_id: string
  job_title: string
  description?: string | null
  jd_text?: string | null
  has_jd_url: boolean
  already_imported: boolean
  local_job_posting_id?: string | null
}

export interface AtsCandidateDetail {
  external_id: string
  full_name: string
  email?: string | null
  phone?: string | null
  cv_text?: string | null
  has_cv_url: boolean
  already_imported: boolean
  local_candidate_id?: string | null
  parent_id?: string | null
}

export interface AtsJobsPage {
  items: AtsRemoteJob[]
  page: number
  page_size: number
  total?: number | null
  total_pages?: number | null
  has_next: boolean
  has_prev: boolean
}
