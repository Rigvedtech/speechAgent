-- Recruiters and admins who schedule interviews.

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    full_name       VARCHAR(255) NOT NULL,
    email           VARCHAR(320) NOT NULL,
    password_hash   VARCHAR(255),
    auth_provider   VARCHAR(50),
    auth_provider_id VARCHAR(255),
    role            VARCHAR(20) NOT NULL DEFAULT 'recruiter',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT users_role_valid CHECK (role IN ('admin', 'recruiter', 'viewer')),
    CONSTRAINT users_email_lower CHECK (email = LOWER(email))
);

CREATE UNIQUE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_organization ON users (organization_id);

COMMENT ON TABLE users IS 'Recruiters and admins belonging to an organization.';
COMMENT ON COLUMN users.role IS 'admin | recruiter | viewer';
