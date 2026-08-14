-- Invite-only SaaS: public form captures leads. Access is granted by platform admins only.

CREATE TABLE IF NOT EXISTS access_requests (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name     VARCHAR(255) NOT NULL,
    contact_name     VARCHAR(255) NOT NULL,
    email            VARCHAR(320) NOT NULL,
    phone            VARCHAR(40),
    message          TEXT,
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',
    ip_address       VARCHAR(64),
    granted_org_id   UUID REFERENCES organization (id) ON DELETE SET NULL,
    granted_by_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    granted_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT access_requests_status_valid CHECK (
        status IN ('pending', 'granted', 'rejected')
    ),
    CONSTRAINT access_requests_email_lower CHECK (email = LOWER(email))
);

CREATE INDEX IF NOT EXISTS idx_access_requests_status_created
    ON access_requests (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_access_requests_email
    ON access_requests (email);

COMMENT ON TABLE access_requests IS
    'Public request-access leads. Does not create a login until a platform admin grants access.';
