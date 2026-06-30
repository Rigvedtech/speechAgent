-- Frozen JD/CV and scoring config at interview join (immutable snapshot).

CREATE TABLE interview_configs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id            UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    question_bank_id        UUID REFERENCES question_banks (id) ON DELETE SET NULL,
    document_extraction_id  UUID REFERENCES document_extractions (id) ON DELETE SET NULL,
    jd_text                 TEXT NOT NULL,
    cv_text                 TEXT NOT NULL,
    continue_threshold      NUMERIC(4, 2) NOT NULL DEFAULT 5.50,
    rolling_window          SMALLINT NOT NULL DEFAULT 6,
    questions_planned_count SMALLINT NOT NULL DEFAULT 10,
    settings_json           JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_configs_interview_unique UNIQUE (interview_id),
    CONSTRAINT interview_configs_jd_min_len CHECK (LENGTH(TRIM(jd_text)) >= 100),
    CONSTRAINT interview_configs_cv_min_len CHECK (LENGTH(TRIM(cv_text)) >= 50),
    CONSTRAINT interview_configs_planned_range CHECK (
        questions_planned_count BETWEEN 1 AND 20
    )
);

COMMENT ON TABLE interview_configs IS 'Snapshot of JD, CV, and thresholds used for this interview only.';
COMMENT ON COLUMN interview_configs.settings_json IS 'TTS/STT language, speaker, thresholds at join time.';
