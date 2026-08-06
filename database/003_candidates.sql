-- People being interviewed; owned by a recruiter within an organization.
-- May originate from manual entry, upload, bulk upload, or org ATS import.

CREATE TABLE candidates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    full_name       VARCHAR(255) NOT NULL,
    email           VARCHAR(320),
    phone           VARCHAR(50),
    cv_text         TEXT,
    notes           TEXT,
    source          VARCHAR(20) NOT NULL DEFAULT 'manual',
    external_ats_id VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Matching / profile enrichment (FK to documents added in 019)
    current_title           VARCHAR(255),
    location                VARCHAR(255),
    linkedin_url            TEXT,
    structured_json         JSONB,
    domain_tags             TEXT[] NOT NULL DEFAULT '{}',
    content_hash            TEXT,
    primary_cv_document_id  UUID,

    CONSTRAINT candidates_email_lower CHECK (email IS NULL OR email = LOWER(email)),
    CONSTRAINT candidates_source_valid CHECK (
        source IN ('manual', 'upload', 'ats', 'bulk_upload')
    )
);

CREATE INDEX idx_candidates_organization ON candidates (organization_id);
CREATE INDEX idx_candidates_created_by ON candidates (created_by);
CREATE INDEX idx_candidates_name ON candidates (organization_id, full_name);
CREATE INDEX idx_candidates_active ON candidates (created_by, full_name)
    WHERE is_active = TRUE AND deleted_at IS NULL;
CREATE UNIQUE INDEX idx_candidates_org_ats_id ON candidates (organization_id, external_ats_id)
    WHERE external_ats_id IS NOT NULL;
CREATE INDEX idx_candidates_domain_tags ON candidates USING GIN (domain_tags);
CREATE INDEX idx_candidates_primary_cv_document ON candidates (primary_cv_document_id)
    WHERE primary_cv_document_id IS NOT NULL;

COMMENT ON TABLE candidates IS 'Interview candidates scoped to recruiter (created_by) and organization.';
COMMENT ON COLUMN candidates.cv_text IS
    'Latest profile CV text; each interview freezes its own copy in interview_configs.cv_text.';
COMMENT ON COLUMN candidates.source IS
    'How this candidate entered the system: manual, upload, ats, or bulk_upload.';
COMMENT ON COLUMN candidates.external_ats_id IS
    'Candidate id in the org ATS; used for dedupe/re-import. NULL if not from ATS.';
COMMENT ON COLUMN candidates.domain_tags IS
    'Role/domain tags for cross-JD matching (e.g. fullstack, frontend).';
COMMENT ON COLUMN candidates.primary_cv_document_id IS
    'Latest/primary CV file; exact bytes in documents.';
