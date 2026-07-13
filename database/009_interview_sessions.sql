-- One voice-bot interview session (= one Recall bot join).
-- Lean core record: who/when/meeting/bot. Runtime state (Recall phase,
-- localization, Output Media page id, greeting) stays in app memory /
-- interview_configs.settings_json — not duplicated here.

CREATE TABLE interview_sessions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id                 UUID NOT NULL,
    organization_id        UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    created_by             UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    candidate_id           UUID NOT NULL REFERENCES candidates (id) ON DELETE RESTRICT,
    job_posting_id         UUID NOT NULL REFERENCES job_postings (id) ON DELETE RESTRICT,
    meeting_url            TEXT NOT NULL,
    meeting_url_normalized TEXT NOT NULL,
    bot_name               VARCHAR(100) NOT NULL DEFAULT 'Prabhat',
    language_mode          VARCHAR(20) NOT NULL DEFAULT 'english',
    interview_started      BOOLEAN NOT NULL DEFAULT FALSE,
    interview_ended        BOOLEAN NOT NULL DEFAULT FALSE,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    stopped_reason         VARCHAR(40) NOT NULL DEFAULT 'none',
    started_at             TIMESTAMPTZ,
    completed_at           TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_sessions_bot_id_unique UNIQUE (bot_id),
    CONSTRAINT interview_sessions_language_valid CHECK (
        language_mode IN ('english', 'hinglish')
    ),
    CONSTRAINT interview_sessions_stopped_reason_valid CHECK (
        stopped_reason IN (
            'none',
            'completed_all_questions',
            'low_recent_average',
            'abuse',
            'manual'
        )
    )
);

CREATE INDEX idx_interview_sessions_org ON interview_sessions (organization_id);
CREATE INDEX idx_interview_sessions_created_by ON interview_sessions (created_by, completed_at DESC);
CREATE INDEX idx_interview_sessions_job_posting ON interview_sessions (job_posting_id, completed_at DESC);
CREATE INDEX idx_interview_sessions_candidate ON interview_sessions (candidate_id);
CREATE INDEX idx_interview_sessions_meeting ON interview_sessions (meeting_url_normalized);
CREATE INDEX idx_interview_sessions_completed ON interview_sessions (completed_at DESC)
    WHERE interview_ended = TRUE;

COMMENT ON TABLE interview_sessions IS 'Core interview record linking recruiter, job posting, and candidate.';
COMMENT ON COLUMN interview_sessions.bot_id IS
    'Current Recall bot id (API path key). On Resend-to-Lobby, update this in place; keep interview_id stable.';
COMMENT ON COLUMN interview_sessions.created_by IS 'Recruiter who scheduled this interview.';
COMMENT ON COLUMN interview_sessions.meeting_url_normalized IS 'Canonical meeting URL for duplicate-join prevention.';
COMMENT ON COLUMN interview_sessions.stopped_reason IS
    'Live/end reason on the session; after wrap-up prefer interview_reports.stopped_reason.';
