-- Platform operator org + role. The first operator user is created manually
-- (one-off), not by this migration and not by deploy.

ALTER TABLE organization
    ADD COLUMN IF NOT EXISTS is_platform BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN organization.is_platform IS
    'True for the Rigved operator organization. Not a customer tenant.';

UPDATE organization
SET is_platform = TRUE
WHERE slug = 'rigved-platform' AND is_platform IS DISTINCT FROM TRUE;

INSERT INTO organization (name, slug, is_platform)
SELECT 'Rigved Platform', 'rigved-platform', TRUE
WHERE NOT EXISTS (SELECT 1 FROM organization WHERE is_platform = TRUE);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_one_platform
    ON organization (is_platform)
    WHERE is_platform;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_valid;
ALTER TABLE users
    ADD CONSTRAINT users_role_valid
    CHECK (role IN ('admin', 'recruiter', 'viewer', 'platform_admin'));

COMMENT ON COLUMN users.role IS 'admin | recruiter | viewer | platform_admin';
