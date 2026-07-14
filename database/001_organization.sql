-- Tenant / company using the interview platform.
-- ATS connection is org-scoped: all users in the org share one ATS bank.

CREATE TABLE organization (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(255) NOT NULL,
    slug             VARCHAR(100) NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    ats_provider     VARCHAR(50),
    ats_config       JSONB NOT NULL DEFAULT '{}',
    ats_connected_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT organization_slug_format CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$')
);

CREATE UNIQUE INDEX idx_organization_slug ON organization (slug);

COMMENT ON TABLE organization IS 'Hiring company or team (multi-tenant root).';
COMMENT ON COLUMN organization.ats_provider IS
    'ATS system for this org (e.g. greenhouse, lever, custom). NULL = not connected.';
COMMENT ON COLUMN organization.ats_config IS
    'Non-secret ATS settings (base URL, org external id, field maps). Store API secrets in env/vault.';
COMMENT ON COLUMN organization.ats_connected_at IS
    'When ATS was last successfully connected for this organization.';
