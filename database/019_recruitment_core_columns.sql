-- Circular FKs + idempotent column upgrades for DBs created before matching pipeline.
-- Safe to re-run on prabhat_DB (already migrated).

-- candidates enrichment
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS current_title VARCHAR(255);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location VARCHAR(255);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS linkedin_url TEXT;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS structured_json JSONB;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS domain_tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS primary_cv_document_id UUID;

ALTER TABLE candidates DROP CONSTRAINT IF EXISTS candidates_source_valid;
ALTER TABLE candidates
    ADD CONSTRAINT candidates_source_valid CHECK (
        source IN ('manual', 'upload', 'ats', 'bulk_upload')
    );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'candidates_primary_cv_document_id_fkey'
    ) THEN
        ALTER TABLE candidates
            ADD CONSTRAINT candidates_primary_cv_document_id_fkey
            FOREIGN KEY (primary_cv_document_id) REFERENCES documents (id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_candidates_domain_tags ON candidates USING GIN (domain_tags);
CREATE INDEX IF NOT EXISTS idx_candidates_primary_cv_document ON candidates (primary_cv_document_id)
    WHERE primary_cv_document_id IS NOT NULL;

-- documents enrichment
ALTER TABLE documents ADD COLUMN IF NOT EXISTS job_posting_id UUID;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS structured_json JSONB;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message TEXT;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_source_valid;
ALTER TABLE documents
    ADD CONSTRAINT documents_source_valid CHECK (
        source IN ('upload', 'manual', 'ats', 'bulk_upload')
    );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documents_job_posting_id_fkey'
    ) THEN
        ALTER TABLE documents
            ADD CONSTRAINT documents_job_posting_id_fkey
            FOREIGN KEY (job_posting_id) REFERENCES job_postings (id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_documents_job_posting ON documents (job_posting_id)
    WHERE job_posting_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents (organization_id, content_hash)
    WHERE content_hash IS NOT NULL;

-- job_postings enrichment
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS domain_tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS structured_json JSONB;
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS pipeline_status VARCHAR(20) NOT NULL DEFAULT 'pending';

ALTER TABLE job_postings DROP CONSTRAINT IF EXISTS job_postings_source_valid;
ALTER TABLE job_postings
    ADD CONSTRAINT job_postings_source_valid CHECK (
        source IN ('manual', 'upload', 'ats', 'bulk_upload')
    );

ALTER TABLE job_postings DROP CONSTRAINT IF EXISTS job_postings_pipeline_status_valid;
ALTER TABLE job_postings
    ADD CONSTRAINT job_postings_pipeline_status_valid CHECK (
        pipeline_status IN ('pending', 'processing', 'ready', 'failed')
    );

CREATE INDEX IF NOT EXISTS idx_job_postings_domain_tags ON job_postings USING GIN (domain_tags);
CREATE INDEX IF NOT EXISTS idx_job_postings_pipeline_status ON job_postings (organization_id, pipeline_status)
    WHERE is_active = TRUE AND deleted_at IS NULL;
