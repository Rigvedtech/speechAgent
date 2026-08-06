-- Job openings / positions (manual, upload, bulk, or org ATS import).

CREATE TABLE job_postings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    created_by          UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    job_title           VARCHAR(255) NOT NULL,
    jd_text             TEXT,
    jd_document_id      UUID REFERENCES documents (id) ON DELETE SET NULL,
    source              VARCHAR(20) NOT NULL DEFAULT 'manual',
    external_ats_id     VARCHAR(255),
    status              VARCHAR(20) NOT NULL DEFAULT 'open',
    description         TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    domain_tags         TEXT[] NOT NULL DEFAULT '{}',
    structured_json     JSONB,
    content_hash        TEXT,
    pipeline_status     VARCHAR(20) NOT NULL DEFAULT 'pending',

    CONSTRAINT job_postings_status_valid CHECK (
        status IN ('draft', 'open', 'closed', 'filled')
    ),
    CONSTRAINT job_postings_source_valid CHECK (
        source IN ('manual', 'upload', 'ats', 'bulk_upload')
    ),
    CONSTRAINT job_postings_pipeline_status_valid CHECK (
        pipeline_status IN ('pending', 'processing', 'ready', 'failed')
    ),
    CONSTRAINT job_postings_title_nonempty CHECK (LENGTH(TRIM(job_title)) >= 2),
    CONSTRAINT job_postings_jd_min_len CHECK (
        jd_text IS NULL OR LENGTH(TRIM(jd_text)) >= 100
    )
);

CREATE INDEX idx_job_postings_organization ON job_postings (organization_id);
CREATE INDEX idx_job_postings_created_by ON job_postings (created_by);
CREATE INDEX idx_job_postings_status ON job_postings (organization_id, status)
    WHERE is_active = TRUE AND deleted_at IS NULL;
CREATE INDEX idx_job_postings_title_trgm ON job_postings
    USING GIN (job_title gin_trgm_ops);
CREATE INDEX idx_job_postings_source ON job_postings (organization_id, source);
CREATE INDEX idx_job_postings_domain_tags ON job_postings USING GIN (domain_tags);
CREATE INDEX idx_job_postings_pipeline_status ON job_postings (organization_id, pipeline_status)
    WHERE is_active = TRUE AND deleted_at IS NULL;
CREATE UNIQUE INDEX idx_job_postings_org_ats_id ON job_postings (organization_id, external_ats_id)
    WHERE external_ats_id IS NOT NULL;

ALTER TABLE document_extractions
    ADD CONSTRAINT document_extractions_job_posting_id_fkey
    FOREIGN KEY (job_posting_id) REFERENCES job_postings (id) ON DELETE SET NULL;

CREATE INDEX idx_document_extractions_job_posting ON document_extractions (job_posting_id);

COMMENT ON TABLE job_postings IS
    'Recruiter-owned job requisitions; may come from manual entry, upload, bulk, or ATS.';
COMMENT ON COLUMN job_postings.source IS
    'How this job entered the system: manual, upload, ats, or bulk_upload.';
COMMENT ON COLUMN job_postings.external_ats_id IS
    'Job id in the org ATS; used for dedupe/re-import. NULL if not from ATS.';
COMMENT ON COLUMN job_postings.status IS
    'Requirement lifecycle: draft, open, closed, filled.';
COMMENT ON COLUMN job_postings.pipeline_status IS
    'Extract/embed pipeline for this JD: pending, processing, ready, failed.';
COMMENT ON COLUMN job_postings.domain_tags IS
    'Domain family tags for matching related CVs across requirements.';
