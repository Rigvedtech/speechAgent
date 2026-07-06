-- Read models for recruiter dashboards, job-title search, and interview pickers.

CREATE OR REPLACE VIEW v_interview_overview AS
SELECT
    s.id                    AS interview_id,
    s.bot_id,
    s.organization_id,
    s.created_by            AS recruiter_id,
    u.full_name             AS recruiter_name,
    u.email                 AS recruiter_email,
    s.job_posting_id,
    jp.job_title,
    jp.status               AS job_status,
    s.candidate_id,
    c.full_name             AS candidate_name,
    c.email                 AS candidate_email,
    s.meeting_url,
    s.recall_status,
    s.phase,
    s.interview_started,
    s.interview_ended,
    s.stopped_reason        AS session_stopped_reason,
    s.started_at,
    s.completed_at          AS session_completed_at,
    s.created_at            AS session_created_at,
    r.overall_average,
    r.questions_scored,
    r.questions_planned,
    r.qualified,
    r.stopped_reason        AS report_stopped_reason,
    r.completed_at          AS report_completed_at
FROM interview_sessions s
JOIN users u ON u.id = s.created_by
JOIN job_postings jp ON jp.id = s.job_posting_id
JOIN candidates c ON c.id = s.candidate_id
LEFT JOIN interview_reports r ON r.interview_id = s.id;

COMMENT ON VIEW v_interview_overview IS
    'Recruiter + job title + candidate for session lists and job_title search.';

CREATE OR REPLACE VIEW v_job_posting_stats AS
SELECT
    jp.id                   AS job_posting_id,
    jp.organization_id,
    jp.created_by           AS recruiter_id,
    jp.job_title,
    jp.status,
    COUNT(s.id)             AS total_interviews,
    COUNT(s.id) FILTER (WHERE s.interview_ended = TRUE) AS completed_interviews,
    COUNT(r.id) FILTER (WHERE r.stopped_reason = 'completed_all_questions') AS completed_fully,
    COUNT(r.id) FILTER (WHERE r.qualified = TRUE) AS qualified_count,
    ROUND(AVG(r.overall_average), 2) AS avg_score
FROM job_postings jp
LEFT JOIN interview_sessions s ON s.job_posting_id = jp.id
LEFT JOIN interview_reports r ON r.interview_id = s.id
WHERE jp.is_active = TRUE AND jp.deleted_at IS NULL
GROUP BY jp.id, jp.organization_id, jp.created_by, jp.job_title, jp.status;

COMMENT ON VIEW v_job_posting_stats IS
    'Per job posting: interview counts, fully completed, qualified, average score.';
