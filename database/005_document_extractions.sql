-- n8n (or similar) extraction runs that produce JD/CV text and question lists.

CREATE TABLE document_extractions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    requested_by    UUID REFERENCES users (id) ON DELETE SET NULL,
    jd_document_id  UUID REFERENCES documents (id) ON DELETE SET NULL,
    cv_document_id  UUID REFERENCES documents (id) ON DELETE SET NULL,
    external_request_id VARCHAR(255),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    jd_text         TEXT,
    cv_text         TEXT,
    questions_json  JSONB,
    raw_response    JSONB,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,

    CONSTRAINT document_extractions_status_valid CHECK (
        status IN ('pending', 'processing', 'success', 'failed')
    )
);

CREATE INDEX idx_document_extractions_org ON document_extractions (organization_id);
CREATE INDEX idx_document_extractions_status ON document_extractions (status);

COMMENT ON TABLE document_extractions IS 'Async JD/CV parsing and question generation (e.g. n8n webhook).';
