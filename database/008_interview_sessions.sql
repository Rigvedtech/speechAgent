-- One voice-bot interview session (= one Recall bot join).

CREATE TABLE interview_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id              UUID NOT NULL,
    organization_id     UUID REFERENCES organization (id) ON DELETE SET NULL,
    created_by          UUID REFERENCES users (id) ON DELETE SET NULL,
    candidate_id        UUID REFERENCES candidates (id) ON DELETE SET NULL,
    meeting_url         TEXT NOT NULL,
    meeting_url_normalized TEXT NOT NULL,
    bot_name            VARCHAR(100) NOT NULL DEFAULT 'Prabhat',
    recall_status       VARCHAR(30) NOT NULL DEFAULT 'joining',
    page_session_id     UUID,
    output_mode         VARCHAR(20) NOT NULL DEFAULT 'webpage',
    language_mode       VARCHAR(20) NOT NULL DEFAULT 'english',
    localization_status VARCHAR(20) NOT NULL DEFAULT 'not_needed',
    localization_error  TEXT,
    greeting_message    TEXT,
    phase               VARCHAR(20) NOT NULL DEFAULT 'greeting',
    interview_started   BOOLEAN NOT NULL DEFAULT FALSE,
    interview_ended     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    stopped_reason      VARCHAR(40) NOT NULL DEFAULT 'none',
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_sessions_bot_id_unique UNIQUE (bot_id),
    CONSTRAINT interview_sessions_output_mode_valid CHECK (
        output_mode IN ('webpage', 'file_upload', 'webrtc')
    ),
    CONSTRAINT interview_sessions_language_valid CHECK (
        language_mode IN ('english', 'hinglish')
    ),
    CONSTRAINT interview_sessions_localization_valid CHECK (
        localization_status IN ('not_needed', 'pending', 'ready', 'failed')
    ),
    CONSTRAINT interview_sessions_phase_valid CHECK (
        phase IN ('greeting', 'await_intro', 'core', 'closing', 'ended')
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
CREATE INDEX idx_interview_sessions_candidate ON interview_sessions (candidate_id);
CREATE INDEX idx_interview_sessions_created_by ON interview_sessions (created_by);
CREATE INDEX idx_interview_sessions_meeting ON interview_sessions (meeting_url_normalized);
CREATE INDEX idx_interview_sessions_completed ON interview_sessions (completed_at DESC)
    WHERE interview_ended = TRUE;

COMMENT ON TABLE interview_sessions IS 'Core interview record; bot_id matches Recall.ai bot UUID.';
COMMENT ON COLUMN interview_sessions.bot_id IS 'Recall.ai bot id — primary external identifier used by the API today.';
