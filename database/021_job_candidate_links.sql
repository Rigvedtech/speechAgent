-- Upload attachment: this CV was added under this requirement (JD).

CREATE TABLE IF NOT EXISTS job_candidate_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    job_posting_id  UUID NOT NULL REFERENCES job_postings (id) ON DELETE CASCADE,
    candidate_id    UUID NOT NULL REFERENCES candidates (id) ON DELETE CASCADE,
    cv_document_id  UUID REFERENCES documents (id) ON DELETE SET NULL,
    linked_by       UUID REFERENCES users (id) ON DELETE SET NULL,
    link_source     VARCHAR(20) NOT NULL DEFAULT 'upload',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT job_candidate_links_unique_pair UNIQUE (job_posting_id, candidate_id),
    CONSTRAINT job_candidate_links_source_valid CHECK (
        link_source IN ('upload', 'bulk', 'manual', 'ats')
    )
);

CREATE INDEX IF NOT EXISTS idx_job_candidate_links_org ON job_candidate_links (organization_id);
CREATE INDEX IF NOT EXISTS idx_job_candidate_links_job ON job_candidate_links (job_posting_id);
CREATE INDEX IF NOT EXISTS idx_job_candidate_links_candidate ON job_candidate_links (candidate_id);
CREATE INDEX IF NOT EXISTS idx_job_candidate_links_document ON job_candidate_links (cv_document_id)
    WHERE cv_document_id IS NOT NULL;

COMMENT ON TABLE job_candidate_links IS
    'Upload attachment: this CV was added under this requirement (JD).';
COMMENT ON COLUMN job_candidate_links.cv_document_id IS
    'Exact CV file used for this link; prefer over guessing from candidates.primary_cv_document_id.';
COMMENT ON COLUMN job_candidate_links.link_source IS
    'How the link was created: upload, bulk, manual, or ats.';
