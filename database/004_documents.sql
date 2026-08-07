-- JD / CV files (upload, bulk, or ATS import). Typed text can skip this table.

CREATE TABLE documents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id   UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    uploaded_by       UUID REFERENCES users (id) ON DELETE SET NULL,
    candidate_id      UUID REFERENCES candidates (id) ON DELETE SET NULL,
    -- FK to job_postings added in 019 (created after 006)
    job_posting_id    UUID,
    document_type     VARCHAR(10) NOT NULL,
    source            VARCHAR(20) NOT NULL DEFAULT 'upload',
    external_ats_id   VARCHAR(255),
    original_filename VARCHAR(512),
    storage_path      TEXT,
    mime_type         VARCHAR(127),
    file_size_bytes   BIGINT,
    extracted_text    TEXT,
    upload_status     VARCHAR(20) NOT NULL DEFAULT 'pending',
    content_hash      TEXT,
    structured_json   JSONB,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT documents_type_valid CHECK (document_type IN ('jd', 'cv')),
    CONSTRAINT documents_source_valid CHECK (
        source IN ('upload', 'manual', 'ats', 'bulk_upload')
    ),
    CONSTRAINT documents_status_valid CHECK (
        upload_status IN ('pending', 'processing', 'ready', 'failed')
    )
);

CREATE INDEX idx_documents_organization ON documents (organization_id);
CREATE INDEX idx_documents_type ON documents (organization_id, document_type);
CREATE INDEX idx_documents_candidate ON documents (candidate_id)
    WHERE candidate_id IS NOT NULL;
CREATE INDEX idx_documents_job_posting ON documents (job_posting_id)
    WHERE job_posting_id IS NOT NULL;
CREATE INDEX idx_documents_source ON documents (organization_id, source);
CREATE INDEX idx_documents_content_hash ON documents (organization_id, content_hash)
    WHERE content_hash IS NOT NULL;
CREATE UNIQUE INDEX idx_documents_org_ats_id ON documents (organization_id, document_type, external_ats_id)
    WHERE external_ats_id IS NOT NULL;

COMMENT ON TABLE documents IS
    'JD/CV files from upload, bulk, or ATS; typed text can skip this table and go into extractions/configs.';
COMMENT ON COLUMN documents.candidate_id IS 'CV → candidate link; leave NULL for JD files.';
COMMENT ON COLUMN documents.job_posting_id IS 'JD → requirement link; optional for CV files.';
COMMENT ON COLUMN documents.source IS
    'Origin of this file: upload, manual, ats, or bulk_upload.';
COMMENT ON COLUMN documents.external_ats_id IS
    'Document id in the org ATS; NULL if not imported from ATS.';
COMMENT ON COLUMN documents.content_hash IS
    'Hash of file/text used to skip re-extract / re-embed.';
