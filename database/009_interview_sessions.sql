-- One interview session. May be scheduled before a Recall bot exists.
-- Lean core: who/when/meeting/bot. Runtime Recall/localization state stays in app memory.

CREATE TABLE interview_sessions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id                 UUID,
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

CREATE UNIQUE INDEX idx_interview_sessions_bot_id ON interview_sessions (bot_id)
    WHERE bot_id IS NOT NULL;
CREATE INDEX idx_interview_sessions_org ON interview_sessions (organization_id);
CREATE INDEX idx_interview_sessions_created_by ON interview_sessions (created_by, completed_at DESC);
CREATE INDEX idx_interview_sessions_job_posting ON interview_sessions (job_posting_id, completed_at DESC);
CREATE INDEX idx_interview_sessions_candidate ON interview_sessions (candidate_id);
CREATE INDEX idx_interview_sessions_meeting ON interview_sessions (meeting_url_normalized);
CREATE INDEX idx_interview_sessions_scheduled ON interview_sessions (created_by, created_at DESC)
    WHERE bot_id IS NULL AND interview_ended = FALSE;
CREATE INDEX idx_interview_sessions_completed ON interview_sessions (completed_at DESC)
    WHERE interview_ended = TRUE;

COMMENT ON TABLE interview_sessions IS
    'Core interview record. bot_id NULL = scheduled (not yet sent to lobby).';
COMMENT ON COLUMN interview_sessions.bot_id IS
    'Recall bot id after Send to lobby. NULL while scheduled. On rejoin, update in place; keep interview id stable.';
COMMENT ON COLUMN interview_sessions.created_by IS 'Recruiter who scheduled this interview.';
COMMENT ON COLUMN interview_sessions.meeting_url_normalized IS
    'Canonical meeting URL for duplicate-join prevention.';
COMMENT ON COLUMN interview_sessions.stopped_reason IS
    'Live/end reason on the session; after wrap-up prefer interview_reports.stopped_reason.';
