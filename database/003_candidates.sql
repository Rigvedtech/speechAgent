-- People being interviewed (may appear in multiple sessions).

CREATE TABLE candidates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organization (id) ON DELETE SET NULL,
    full_name       VARCHAR(255) NOT NULL,
    email           VARCHAR(320),
    phone           VARCHAR(50),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_candidates_organization ON candidates (organization_id);
CREATE INDEX idx_candidates_name ON candidates (organization_id, full_name);

COMMENT ON TABLE candidates IS 'Interview candidates; linked to one or more interview sessions.';
