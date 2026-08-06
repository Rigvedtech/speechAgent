-- JD↔CV match scores for shortlisting (hybrid/rerank/LLM breakdown in JSON).

CREATE TABLE IF NOT EXISTS job_candidate_matches (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    job_posting_id   UUID NOT NULL REFERENCES job_postings (id) ON DELETE CASCADE,
    candidate_id     UUID NOT NULL REFERENCES candidates (id) ON DELETE CASCADE,
    cv_document_id   UUID REFERENCES documents (id) ON DELETE SET NULL,
    score            NUMERIC(5, 2) NOT NULL DEFAULT 0,
    rank             INTEGER,
    score_breakdown  JSONB,
    reasons_json     JSONB,
    domain_overlap   TEXT[] NOT NULL DEFAULT '{}',
    model_version    TEXT,
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT job_candidate_matches_unique_pair UNIQUE (job_posting_id, candidate_id),
    CONSTRAINT job_candidate_matches_score_range CHECK (score >= 0 AND score <= 100)
);

CREATE INDEX IF NOT EXISTS idx_job_candidate_matches_org ON job_candidate_matches (organization_id);
CREATE INDEX IF NOT EXISTS idx_job_candidate_matches_job_score
    ON job_candidate_matches (job_posting_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_job_candidate_matches_candidate ON job_candidate_matches (candidate_id);
CREATE INDEX IF NOT EXISTS idx_job_candidate_matches_domain_overlap
    ON job_candidate_matches USING GIN (domain_overlap);

COMMENT ON TABLE job_candidate_matches IS
    'JD↔CV match scores for shortlisting (hybrid/rerank/LLM breakdown in JSON).';
COMMENT ON COLUMN job_candidate_matches.cv_document_id IS
    'Exact document version used when scoring.';
COMMENT ON COLUMN job_candidate_matches.score IS
    'Final fit score 0–100 used for top-N pagination.';
COMMENT ON COLUMN job_candidate_matches.score_breakdown IS
    'Component scores e.g. {bm25, vector, rerank, llm, metadata}.';
COMMENT ON COLUMN job_candidate_matches.reasons_json IS
    'Human-readable match reasons / gaps for recruiter UI.';
COMMENT ON COLUMN job_candidate_matches.domain_overlap IS
    'Intersection of JD and CV domain_tags at score time.';
COMMENT ON COLUMN job_candidate_matches.model_version IS
    'Embed/rerank/prompt version for reproducibility.';
