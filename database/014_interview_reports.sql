-- Final interview summary (report card) after wrap-up.

CREATE TABLE interview_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    job_title           VARCHAR(255) NOT NULL,
    recruiter_name      VARCHAR(255) NOT NULL,
    candidate_name      VARCHAR(255) NOT NULL,
    questions_planned   SMALLINT NOT NULL,
    questions_scored    SMALLINT NOT NULL,
    overall_average     NUMERIC(4, 2),
    last_n_average      NUMERIC(4, 2),
    rolling_window      SMALLINT NOT NULL DEFAULT 6,
    continue_threshold  NUMERIC(4, 2) NOT NULL DEFAULT 5.50,
    qualified           BOOLEAN NOT NULL DEFAULT FALSE,
    abuse_warnings      SMALLINT NOT NULL DEFAULT 0,
    stopped_reason      VARCHAR(40) NOT NULL,
    phase               VARCHAR(20) NOT NULL DEFAULT 'ended',
    summary_develop     JSONB NOT NULL DEFAULT '[]',
    summary_fix         JSONB NOT NULL DEFAULT '[]',
    report_json         JSONB,
    full_transcript     TEXT,
    interview_completed BOOLEAN NOT NULL DEFAULT TRUE,
    completed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_reports_interview_unique UNIQUE (interview_id),
    CONSTRAINT interview_reports_stopped_reason_valid CHECK (
        stopped_reason IN (
            'none',
            'completed_all_questions',
            'low_recent_average',
            'abuse',
            'manual'
        )
    )
);

CREATE INDEX idx_interview_reports_completed ON interview_reports (completed_at DESC);
CREATE INDEX idx_interview_reports_average ON interview_reports (overall_average);
CREATE INDEX idx_interview_reports_job_title ON interview_reports (job_title);
CREATE INDEX idx_interview_reports_qualified ON interview_reports (job_title, qualified)
    WHERE qualified = TRUE;

COMMENT ON TABLE interview_reports IS 'Final report with denormalized job/recruiter/candidate for lists and search.';
COMMENT ON COLUMN interview_reports.qualified IS 'TRUE when overall_average >= continue_threshold at wrap-up.';
COMMENT ON COLUMN interview_reports.full_transcript IS 'Optional denormalized export; source of truth is transcript_turns.';
