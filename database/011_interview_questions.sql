-- The 10 questions selected for this interview (with per-slot status).

CREATE TABLE interview_questions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    bank_item_id        UUID REFERENCES question_bank_items (id) ON DELETE SET NULL,
    slot                SMALLINT NOT NULL,
    external_question_id VARCHAR(64) NOT NULL,
    difficulty          VARCHAR(20) NOT NULL,
    source              VARCHAR(20) NOT NULL,
    question_text       TEXT NOT NULL,
    spoken_question     TEXT,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    asked_at            TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_questions_slot_unique UNIQUE (interview_id, slot),
    CONSTRAINT interview_questions_difficulty_valid CHECK (
        difficulty IN ('Low', 'Intermediate', 'Hard')
    ),
    CONSTRAINT interview_questions_source_valid CHECK (
        source IN ('jd', 'resume', 'other')
    ),
    CONSTRAINT interview_questions_status_valid CHECK (
        status IN ('pending', 'in_progress', 'completed', 'remaining')
    ),
    CONSTRAINT interview_questions_slot_range CHECK (slot BETWEEN 1 AND 20)
);

CREATE INDEX idx_interview_questions_interview ON interview_questions (interview_id);
CREATE INDEX idx_interview_questions_status ON interview_questions (interview_id, status);

COMMENT ON TABLE interview_questions IS 'Planned question plan for one session; status tracks completed vs remaining.';
COMMENT ON COLUMN interview_questions.status IS 'pending → in_progress → completed; remaining if interview ends before this slot.';
