-- One n8n (or similar) run: parse JD/CV and generate questions for that candidate+role.
-- Manual paste is allowed: jd_document_id / cv_document_id may be NULL when text is typed.

CREATE TABLE document_extractions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    requested_by        UUID REFERENCES users (id) ON DELETE SET NULL,
    candidate_id        UUID REFERENCES candidates (id) ON DELETE SET NULL,
    job_posting_id      UUID,
    jd_document_id      UUID REFERENCES documents (id) ON DELETE SET NULL,
    cv_document_id      UUID REFERENCES documents (id) ON DELETE SET NULL,
    external_request_id VARCHAR(255),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    jd_text             TEXT,
    cv_text             TEXT,
    questions_json      JSONB,
    raw_response        JSONB,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,

    CONSTRAINT document_extractions_status_valid CHECK (
        status IN ('pending', 'processing', 'success', 'failed')
    )
);

CREATE INDEX idx_document_extractions_org ON document_extractions (organization_id);
CREATE INDEX idx_document_extractions_status ON document_extractions (status);
CREATE INDEX idx_document_extractions_candidate ON document_extractions (candidate_id)
    WHERE candidate_id IS NOT NULL;

COMMENT ON TABLE document_extractions IS
    'Per-run JD/CV text + generated questions; copied into interview_questions at join.';
COMMENT ON COLUMN document_extractions.candidate_id IS
    'Candidate whose CV drove this generation (NULL only if not yet linked).';
COMMENT ON COLUMN document_extractions.job_posting_id IS
    'Optional job this run belongs to (FK added in 006_job_postings.sql).';
COMMENT ON COLUMN document_extractions.questions_json IS
    'Generated question list for this JD+CV run.';
