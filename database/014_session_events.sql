-- Operational audit trail for interview lifecycle events.

CREATE TABLE session_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id    UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    event_type      VARCHAR(50) NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT session_events_type_valid CHECK (
        event_type IN (
            'bot_created',
            'bot_joined_meeting',
            'lobby_timeout',
            'interview_started',
            'question_asked',
            'answer_scored',
            
            'localization_completed',
            'localization_failed',
            'playback_done',
            'interview_ended',
            'bot_left',
            'error'
        )
    )
);

CREATE INDEX idx_session_events_interview ON session_events (interview_id, created_at);
CREATE INDEX idx_session_events_type ON session_events (event_type, created_at DESC);

COMMENT ON TABLE session_events IS 'Lightweight audit log; optional but useful for debugging and analytics.';
