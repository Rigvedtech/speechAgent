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
  /** Same as schedule — attach coding round when sending to lobby directly */
  coding?: InterviewCodingConfig
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
  camera_integrity_armed?: boolean
}

export interface CameraIntegrityToggleResponse {
  success: boolean
  bot_id: string
  camera_integrity_armed: boolean
  message: string
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

export type UserRole = 'admin' | 'recruiter' | 'viewer' | 'platform_admin'
export type TenantUserRole = 'admin' | 'recruiter' | 'viewer'

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

export type AccessRequestStatus = 'pending' | 'granted' | 'rejected'

export interface AccessRequest {
  id: string
  company_name: string
  contact_name: string
  email: string
  phone?: string | null
  message?: string | null
  status: AccessRequestStatus
  granted_org_id?: string | null
  granted_at?: string | null
  created_at: string
}

export interface AccessRequestPublicResult {
  ok: boolean
  message: string
}

export interface GrantAccessResult {
  request: AccessRequest
  organization_name: string
  login_email: string
}

export interface AdminOrganization {
  id: string
  name: string
  slug: string
  is_active: boolean
  is_platform: boolean
  created_at: string
  user_count: number
}

export interface AdminOrganizationDetail {
  organization: AdminOrganization
  users: AuthUser[]
}

export interface AdminOverview {
  pending_requests: number
  customer_orgs: number
  active_orgs: number
  inactive_orgs: number
  tenant_users: number
  operators: number
  interviews_this_month: number
  requests_by_status: {
    pending: number
    granted: number
    rejected: number
  }
  users_by_role: {
    admin: number
    recruiter: number
    viewer: number
  }
  interviews_by_month: Array<{
    month: string
    label: string
    count: number
  }>
}

export interface Candidate {
  id: string
  organization_id: string
  created_by: string
  full_name: string
  email?: string | null
  phone?: string | null
  current_title?: string | null
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
  jd_document_id?: string | null
  pipeline_status: 'pending' | 'processing' | 'ready' | 'failed'
  description?: string | null
  status: string
  source: string
  external_ats_id?: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export type UploadItemStatus = 'queued' | 'processing' | 'ready' | 'failed' | 'skipped'
export type UploadBatchStatus = 'queued' | 'processing' | 'done' | 'failed' | 'cancelled'

export interface BulkUploadItem {
  id: string
  original_filename?: string | null
  file_size_bytes?: number | null
  mime_type?: string | null
  status: UploadItemStatus
  document_id?: string | null
  error_message?: string | null
  created_at: string
  completed_at?: string | null
}

export interface UploadBatch {
  id: string
  organization_id: string
  job_posting_id?: string | null
  batch_type: 'cv' | 'jd'
  status: UploadBatchStatus
  total_count: number
  success_count: number
  fail_count: number
  error_message?: string | null
  created_at: string
  completed_at?: string | null
  items: BulkUploadItem[]
}

export interface CvBatchUploadResponse {
  batch_id: string
  job_posting_id: string
  total_files: number
  total_queued: number
  total_duplicate_skipped: number
  items: Array<{
    original_filename: string
    document_id: string
    batch_item_id: string
    status: UploadItemStatus
    is_duplicate: boolean
    file_size_bytes: number
    mime_type: string
  }>
}

export interface JdUploadResponse {
  job_posting_id: string
  document_id: string
  batch_id: string
  status: UploadItemStatus
  is_duplicate: boolean
  original_filename: string
  mime_type: string
  file_size_bytes: number
}

export interface JobResume {
  document_id: string
  candidate_id?: string | null
  original_filename?: string | null
  file_size_bytes?: number | null
  mime_type?: string | null
  upload_status: string
  error_message?: string | null
  full_name?: string | null
  email?: string | null
  current_title?: string | null
  cv_text?: string | null
  created_at: string
  /** Null / missing = unscored for this job */
  match_score?: number | null
  match_rank?: number | null
  match_scored_at?: string | null
  match_summary?: string | null
  match_reasons?: {
    summary?: string
    strengths?: string[]
    gaps?: string[]
    matched_skills?: string[]
    missing_skills?: string[]
  } | null
  match_breakdown?: {
    scale?: string
    skills_match?: number | string
    experience_fit?: number | string
    skill_usage?: number | string
    domain_alignment?: number | string
    overall_llm?: number | string
    final?: number | string
    final_100?: number | string
    matched_skills?: string[]
    missing_skills?: string[]
    llm_source?: string
    weights?: Record<string, number>
    [key: string]: unknown
  } | null
}

export interface JobMatchResult {
  candidate_id: string
  document_id?: string | null
  score: number
  rank?: number | null
  score_breakdown?: Record<string, unknown> | null
  reasons_json?: JobResume['match_reasons']
  domain_overlap: string[]
  model_version?: string | null
  scored_at: string
}

export interface ScoreJobMatchesResponse {
  job_posting_id: string
  total_candidates: number
  scored: number
  skipped_already_scored: number
  skipped_unchanged?: number
  skipped_no_profile: number
  skipped_no_text: number
  failed: number
  unscored_remaining: number
  results: JobMatchResult[]
}

export interface BatchExtractSummary {
  batch_id: string
  total: number
  extracted: number
  failed: number
  skipped_already_done: number
}

export interface ParsedDocumentResult {
  document_id: string
  candidate_id?: string | null
  linked_to_job: boolean
  document_type: string
  original_filename?: string | null
  upload_status: string
  parse_status: 'parsed' | 'no_text' | 'failed'
  full_name?: string | null
  email?: string | null
  current_title?: string | null
  skills: string[]
  required_skills: string[]
}

export interface BatchParseSummary {
  batch_id: string
  total: number
  parsed: number
  skipped_no_text: number
  skipped_already_parsed: number
  failed: number
  results: ParsedDocumentResult[]
}

export interface CreateCandidateRequest {
  full_name: string
  email?: string
  phone?: string
  current_title?: string
  cv_text?: string
  notes?: string
  source?: 'manual' | 'upload'
}

export interface UpdateCandidateRequest {
  full_name?: string
  email?: string
  phone?: string
  current_title?: string
  cv_text?: string
  notes?: string
  is_active?: boolean
}

export interface CreateJobPostingRequest {
  job_title: string
  jd_text?: string
  description?: string
  status?: 'draft' | 'open' | 'closed' | 'filled'
  source?: 'manual' | 'upload'
}

export interface UpdateJobPostingRequest {
  job_title?: string
  jd_text?: string
  description?: string
  status?: 'draft' | 'open' | 'closed' | 'filled'
  is_active?: boolean
}

export interface CreateUserRequest {
  full_name: string
  email: string
  password: string
  role: TenantUserRole
}

export interface UpdateUserRequest {
  full_name?: string
  role?: TenantUserRole
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
  coding_enabled?: boolean
}

export type CodingLanguage =
  | 'python'
  | 'javascript'
  | 'typescript'
  | 'java'
  | 'cpp'
  | 'csharp'
  | 'go'
  | 'ruby'
  | 'php'
  | 'kotlin'
  | 'rust'
  | 'swift'

export interface CodingExample {
  input: string
  output: string
  explanation?: string | null
}

export interface CodingTaskSummary {
  id: string
  slug: string
  title: string
  difficulty: string
  skill_tags: string[]
  allowed_languages: string[]
  domain_id?: string | null
  is_org_owned?: boolean
  estimated_time_min?: number
}

export interface CodingTaskDetail extends CodingTaskSummary {
  statement: string
  examples: CodingExample[]
  constraints_text: string
  starter_code: Record<string, string>
  entry_function?: string | null
}

export interface CodingDomain {
  id: string
  slug: string
  name: string
  language: string
  description: string
  is_active: boolean
  problem_count: number
  max_problems: number
  can_generate: boolean
  is_org_owned?: boolean
}

export interface InterviewCodingConfig {
  enabled: boolean
  domain_id?: string | null
  allowed_languages: CodingLanguage[]
  default_language: CodingLanguage
  /** When task_ids empty, server auto-assigns this many from shared bank. */
  problem_count?: number | null
  task_ids: string[]
  assigned_task_id?: string | null
  time_limit_min: number
  /** task_id -> recruiter time limit (minutes) */
  task_time_limits?: Record<string, number>
}

export interface CodingBankStatus {
  problem_count: number
  max_problems: number
  free_slots: number
  generate_batch_size: number
  next_generate_count: number
  seed_target: number
  can_generate: boolean
  can_seed: boolean
}

export interface CodingBankGenerateResult {
  created: CodingTaskDetail[]
  requested: number
  created_count: number
  problem_count: number
  max_problems: number
  errors: string[]
}

export interface CodingBankSeedResult {
  before: number
  inserted: number
  after: number
  target: number
}

export interface InterviewCodingConfigOut extends InterviewCodingConfig {
  interview_id: string
  coding_uri?: string | null
  wrapup_message?: string | null
}

export interface CodingWorkspace {
  files: Record<string, string>
  activePath: string
  entryPath: string
}

export interface CodingAssignedTaskProgress {
  task_id: string
  title: string
  difficulty: string
  time_limit_min: number
  status: string
  is_current: boolean
}

export interface CodingProctorSummary {
  risk_level: 'clean' | 'review' | 'high' | string
  warn_count: number
  critical_count: number
  counts: Record<string, number>
  last_event_type?: string | null
  last_severity?: string | null
  updated_at?: string | null
}

export interface CodingSession {
  interview_id?: string | null
  bot_id?: string | null
  demo_token?: string | null
  access_token?: string | null
  enabled: boolean
  language: string
  allowed_languages: string[]
  language_locked?: boolean
  domain_id?: string | null
  domain_name?: string | null
  time_limit_min: number
  started_at?: string | null
  ends_at?: string | null
  task: CodingTaskDetail
  submission_status: string
  code: string
  workspace?: CodingWorkspace
  coding_uri?: string | null
  task_index?: number
  task_count?: number
  has_next_task?: boolean
  assigned_tasks?: CodingAssignedTaskProgress[]
  proctoring_enabled?: boolean
  proctor_started?: boolean
  proctor_summary?: CodingProctorSummary
}

export type CodingProctorSeverity = 'info' | 'warn' | 'critical'

export interface CodingProctorEventInput {
  event_type: string
  severity?: CodingProctorSeverity
  detail?: Record<string, unknown>
  client_ts?: string | null
}

export interface CodingProctorFrameResult {
  face_count: number
  multi_face: boolean
  gaze?: string | null
  risk?: string | null
  signal: string
  severity: string
  gate_ok: boolean
  summary: CodingProctorSummary
}

export interface CodingProctorStartResult {
  started_at: string
  ends_at: string
  time_limit_min: number
  summary: CodingProctorSummary
}

export interface CodingSubmitRequest {
  language: string
  code: string
  status?: 'draft' | 'submitted'
  workspace?: CodingWorkspace
}

export interface CodingSubmitResponse {
  id: string
  status: string
  language: string
  submitted_at?: string | null
  task_id: string
  interview_id?: string | null
  demo_token?: string | null
  has_next_task?: boolean
  next_task_id?: string | null
  task_index?: number
  task_count?: number
}

export interface CodingRunRequest {
  language: string
  code: string
  stdin?: string
  timeout_sec?: number
}

export interface CodingRunResponse {
  ok: boolean
  exit_code: number
  stdout: string
  stderr: string
  timed_out: boolean
  language: string
  error?: string | null
}

export interface CodingExampleRunResult {
  index: number
  input: string
  expected: string
  actual: string
  stderr: string
  exit_code: number
  timed_out: boolean
  passed: boolean
  error?: string | null
}

export interface CodingComplexity {
  time: string
  space: string
  note?: string
  confidence?: string
}

export interface CodingRunExamplesResponse {
  passed: number
  total: number
  all_passed: boolean
  results: CodingExampleRunResult[]
  complexity?: CodingComplexity | null
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
  coding?: InterviewCodingConfig
}

export interface ScheduleInterviewResponse {
  success: boolean
  interview: ScheduledInterview
  coding?: InterviewCodingConfigOut | null
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
  status?: string | null
  cv_filename?: string | null
  has_cv_text: boolean
  has_cv_url: boolean
  already_imported: boolean
  local_candidate_id?: string | null
}

export interface AtsRemoteJob {
  external_id: string
  job_title: string
  description?: string | null
  company_name?: string | null
  status?: string | null
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
  company_name?: string | null
  status?: string | null
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
  status?: string | null
  cv_filename?: string | null
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
