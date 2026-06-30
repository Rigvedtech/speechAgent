-- Final interview summary (report card) after wrap-up.

CREATE TABLE interview_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    candidate_name      VARCHAR(255) NOT NULL,
    questions_planned   SMALLINT NOT NULL,
    questions_scored    SMALLINT NOT NULL,
    overall_average     NUMERIC(4, 2),
    last_n_average      NUMERIC(4, 2),
    rolling_window      SMALLINT NOT NULL DEFAULT 6,
    continue_threshold  NUMERIC(4, 2) NOT NULL DEFAULT 5.50,
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

COMMENT ON TABLE interview_reports IS 'Final report; report_json mirrors legacy reports/*.json for migration.';
COMMENT ON COLUMN interview_reports.full_transcript IS 'Optional denormalized export; source of truth is transcript_turns.';
