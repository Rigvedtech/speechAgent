-- Role/domain family graph for matching related JDs and CVs.

CREATE TABLE IF NOT EXISTS domain_taxonomy (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organization (id) ON DELETE CASCADE,
    slug            VARCHAR(64) NOT NULL,
    display_name    VARCHAR(128) NOT NULL,
    parent_slug     VARCHAR(64),
    aliases         TEXT[] NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT domain_taxonomy_slug_format CHECK (slug ~ '^[a-z0-9]+(?:_[a-z0-9]+)*$')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_domain_taxonomy_org_slug
    ON domain_taxonomy (organization_id, slug)
    WHERE organization_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_domain_taxonomy_system_slug
    ON domain_taxonomy (slug)
    WHERE organization_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_domain_taxonomy_parent
    ON domain_taxonomy (parent_slug)
    WHERE parent_slug IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_domain_taxonomy_aliases
    ON domain_taxonomy USING GIN (aliases);

COMMENT ON TABLE domain_taxonomy IS 'Role/domain family graph for matching related JDs and CVs.';
COMMENT ON COLUMN domain_taxonomy.organization_id IS 'NULL = global default taxonomy; set for org-specific tags.';
COMMENT ON COLUMN domain_taxonomy.parent_slug IS 'Optional parent domain slug (e.g. frontend parent = web).';
COMMENT ON COLUMN domain_taxonomy.aliases IS 'Alternate labels that map to this slug (e.g. react_dev → frontend).';
