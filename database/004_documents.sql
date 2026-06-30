-- Uploaded JD / CV files and extracted text.

CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    uploaded_by     UUID REFERENCES users (id) ON DELETE SET NULL,
    document_type   VARCHAR(10) NOT NULL,
    original_filename VARCHAR(512),
    storage_path    TEXT,
    mime_type       VARCHAR(127),
    file_size_bytes BIGINT,
    extracted_text  TEXT,
    upload_status   VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT documents_type_valid CHECK (document_type IN ('jd', 'cv')),
    CONSTRAINT documents_status_valid CHECK (
        upload_status IN ('pending', 'processing', 'ready', 'failed')
    )
);

CREATE INDEX idx_documents_organization ON documents (organization_id);
CREATE INDEX idx_documents_type ON documents (organization_id, document_type);

COMMENT ON TABLE documents IS 'Job descriptions and resumes uploaded before interview setup.';
