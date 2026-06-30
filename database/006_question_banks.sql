-- Reusable question pools (catalog), e.g. per job role.

CREATE TABLE question_banks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    created_by      UUID REFERENCES users (id) ON DELETE SET NULL,
    name            VARCHAR(255) NOT NULL,
    job_title       VARCHAR(255),
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_question_banks_organization ON question_banks (organization_id);

COMMENT ON TABLE question_banks IS 'Master question catalog; items are copied into interview_questions at join time.';
