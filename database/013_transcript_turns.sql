-- Full raw conversation log: every AI and candidate spoken line in order.

CREATE TABLE transcript_turns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id    UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    sequence_num    INTEGER NOT NULL,
    role            VARCHAR(20) NOT NULL,
    text            TEXT NOT NULL,
    turn_type       VARCHAR(30) NOT NULL DEFAULT 'other',
    spoken_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT transcript_turns_sequence_unique UNIQUE (interview_id, sequence_num),
    CONSTRAINT transcript_turns_role_valid CHECK (role IN ('assistant', 'user')),
    CONSTRAINT transcript_turns_type_valid CHECK (
        turn_type IN (
            'greeting',
            'introduction',
            'question',
            'answer',
            'clarifier',
            'rephrase',
            'repeat',
            'presence_check',
            'continuation',
            'closing',
            'other'
        )
    ),
    CONSTRAINT transcript_turns_text_nonempty CHECK (LENGTH(TRIM(text)) > 0)
);

CREATE INDEX idx_transcript_turns_interview ON transcript_turns (interview_id, sequence_num);
CREATE INDEX idx_transcript_turns_spoken_at ON transcript_turns (interview_id, spoken_at);

COMMENT ON TABLE transcript_turns IS 'Complete raw transcription; separate from scored interview_answers.';
COMMENT ON COLUMN transcript_turns.role IS 'assistant = bot [AI]; user = candidate [You].';
