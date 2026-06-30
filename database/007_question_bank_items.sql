-- Single question inside a reusable question bank.

CREATE TABLE question_bank_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_id         UUID NOT NULL REFERENCES question_banks (id) ON DELETE CASCADE,
    external_id     VARCHAR(64) NOT NULL,
    difficulty      VARCHAR(20) NOT NULL,
    source          VARCHAR(20) NOT NULL DEFAULT 'jd',
    question_text   TEXT NOT NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT question_bank_items_difficulty_valid CHECK (
        difficulty IN ('Low', 'Intermediate', 'Hard')
    ),
    CONSTRAINT question_bank_items_source_valid CHECK (
        source IN ('jd', 'resume', 'other')
    ),
    CONSTRAINT question_bank_items_text_nonempty CHECK (LENGTH(TRIM(question_text)) >= 10)
);

CREATE UNIQUE INDEX idx_question_bank_items_external
    ON question_bank_items (bank_id, external_id);
CREATE INDEX idx_question_bank_items_bank_difficulty
    ON question_bank_items (bank_id, difficulty, source);

COMMENT ON TABLE question_bank_items IS 'One row per question in a bank; maps to API QuestionBankItem.id.';
COMMENT ON COLUMN question_bank_items.external_id IS 'Business id from frontend/n8n (e.g. "11"), unique per bank.';
