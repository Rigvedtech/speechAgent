-- Registry linking Postgres documents/chunks to Qdrant vector points (vectors live in Qdrant).

CREATE TABLE IF NOT EXISTS qdrant_document_points (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id   UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    document_id       UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index       INTEGER NOT NULL DEFAULT 0,
    chunk_text        TEXT NOT NULL,
    content_hash      TEXT,
    qdrant_collection VARCHAR(128) NOT NULL,
    qdrant_point_id   TEXT NOT NULL,
    doc_type          VARCHAR(10),
    domain_tags       TEXT[] NOT NULL DEFAULT '{}',
    candidate_id      UUID REFERENCES candidates (id) ON DELETE SET NULL,
    job_posting_id    UUID REFERENCES job_postings (id) ON DELETE SET NULL,
    metadata          JSONB NOT NULL DEFAULT '{}',
    embed_model       TEXT,
    vector_dim        INTEGER,
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT qdrant_document_points_chunk_unique UNIQUE (document_id, chunk_index),
    CONSTRAINT qdrant_document_points_point_unique UNIQUE (qdrant_collection, qdrant_point_id),
    CONSTRAINT qdrant_document_points_chunk_nonneg CHECK (chunk_index >= 0),
    CONSTRAINT qdrant_document_points_dim_positive CHECK (vector_dim IS NULL OR vector_dim > 0),
    CONSTRAINT qdrant_document_points_doc_type_valid CHECK (
        doc_type IS NULL OR doc_type IN ('jd', 'cv')
    )
);

CREATE INDEX IF NOT EXISTS idx_qdrant_points_org ON qdrant_document_points (organization_id);
CREATE INDEX IF NOT EXISTS idx_qdrant_points_document ON qdrant_document_points (document_id);
CREATE INDEX IF NOT EXISTS idx_qdrant_points_collection ON qdrant_document_points (qdrant_collection);
CREATE INDEX IF NOT EXISTS idx_qdrant_points_domain_tags ON qdrant_document_points USING GIN (domain_tags);
CREATE INDEX IF NOT EXISTS idx_qdrant_points_candidate ON qdrant_document_points (candidate_id)
    WHERE candidate_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_qdrant_points_job ON qdrant_document_points (job_posting_id)
    WHERE job_posting_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_qdrant_points_content_hash
    ON qdrant_document_points (organization_id, content_hash)
    WHERE content_hash IS NOT NULL;

COMMENT ON TABLE qdrant_document_points IS
    'Registry linking Postgres documents/chunks to Qdrant vector points (no vectors in PG).';
COMMENT ON COLUMN qdrant_document_points.chunk_text IS
    'Text that was embedded; kept in PG for BM25/hybrid and audit.';
COMMENT ON COLUMN qdrant_document_points.qdrant_collection IS
    'Qdrant collection name used for upsert/search.';
COMMENT ON COLUMN qdrant_document_points.qdrant_point_id IS
    'Point id in Qdrant (usually same as this row UUID as string).';
COMMENT ON COLUMN qdrant_document_points.domain_tags IS
    'Copied into Qdrant payload for filtered vector search.';
COMMENT ON COLUMN qdrant_document_points.embed_model IS
    'Embedding model id (e.g. text-embedding-3-small) for versioning.';
COMMENT ON COLUMN qdrant_document_points.vector_dim IS
    'Vector size in Qdrant for this point; must match collection config.';
COMMENT ON COLUMN qdrant_document_points.synced_at IS
    'Last successful upsert to Qdrant; NULL/old = needs re-sync.';
