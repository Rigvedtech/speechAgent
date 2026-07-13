-- People being interviewed; owned by a recruiter within an organization.

CREATE TABLE candidates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    full_name       VARCHAR(255) NOT NULL,
    email           VARCHAR(320),
    phone           VARCHAR(50),
    cv_text         TEXT,
    notes           TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT candidates_email_lower CHECK (email IS NULL OR email = LOWER(email))
);

CREATE INDEX idx_candidates_organization ON candidates (organization_id);
CREATE INDEX idx_candidates_created_by ON candidates (created_by);
CREATE INDEX idx_candidates_name ON candidates (organization_id, full_name);
CREATE INDEX idx_candidates_active ON candidates (created_by, full_name)
    WHERE is_active = TRUE AND deleted_at IS NULL;

COMMENT ON TABLE candidates IS 'Interview candidates scoped to recruiter (created_by) and organization.';
COMMENT ON COLUMN candidates.cv_text IS
    'Latest profile CV text; each interview freezes its own copy in interview_configs.cv_text.';
