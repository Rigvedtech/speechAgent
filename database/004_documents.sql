-- JD / CV files (upload or ATS import). Typed text can skip this table.

CREATE TABLE documents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id   UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    uploaded_by       UUID REFERENCES users (id) ON DELETE SET NULL,
    candidate_id      UUID REFERENCES candidates (id) ON DELETE SET NULL,
    document_type     VARCHAR(10) NOT NULL,
    source            VARCHAR(20) NOT NULL DEFAULT 'upload',
    external_ats_id   VARCHAR(255),
    original_filename VARCHAR(512),
    storage_path      TEXT,
    mime_type         VARCHAR(127),
    file_size_bytes   BIGINT,
    extracted_text    TEXT,
    upload_status     VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT documents_type_valid CHECK (document_type IN ('jd', 'cv')),
    CONSTRAINT documents_source_valid CHECK (
        source IN ('upload', 'manual', 'ats')
    ),
    CONSTRAINT documents_status_valid CHECK (
        upload_status IN ('pending', 'processing', 'ready', 'failed')
    )
);

CREATE INDEX idx_documents_organization ON documents (organization_id);
CREATE INDEX idx_documents_type ON documents (organization_id, document_type);
CREATE INDEX idx_documents_candidate ON documents (candidate_id)
    WHERE candidate_id IS NOT NULL;
CREATE INDEX idx_documents_source ON documents (organization_id, source);
CREATE UNIQUE INDEX idx_documents_org_ats_id ON documents (organization_id, document_type, external_ats_id)
    WHERE external_ats_id IS NOT NULL;

COMMENT ON TABLE documents IS
    'JD/CV files from upload or ATS; typed text can skip this table and go into extractions/configs.';
COMMENT ON COLUMN documents.candidate_id IS 'CV → candidate link; leave NULL for JD files.';
COMMENT ON COLUMN documents.source IS
    'Origin of this file: upload, manual (rare file save), or ats.';
COMMENT ON COLUMN documents.external_ats_id IS
    'Document id in the org ATS; NULL if not imported from ATS.';
