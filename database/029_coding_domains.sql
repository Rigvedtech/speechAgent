-- Coding domains (language tracks) + link tasks/config to a domain.

CREATE TABLE IF NOT EXISTS coding_domains (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id    UUID REFERENCES organization (id) ON DELETE CASCADE,
    slug               VARCHAR(64) NOT NULL,
    name               VARCHAR(120) NOT NULL,
    language           VARCHAR(32) NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order         SMALLINT NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT coding_domains_language_valid CHECK (
        language IN (
            'python', 'javascript', 'typescript', 'java', 'cpp', 'csharp',
            'go', 'ruby', 'php', 'kotlin', 'rust', 'swift'
        )
    ),
    CONSTRAINT coding_domains_slug_nonempty CHECK (LENGTH(TRIM(slug)) >= 2),
    CONSTRAINT coding_domains_name_nonempty CHECK (LENGTH(TRIM(name)) >= 2)
);

-- Global domains: organization_id IS NULL
CREATE UNIQUE INDEX IF NOT EXISTS uq_coding_domains_global_slug
    ON coding_domains (slug)
    WHERE organization_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_coding_domains_org_slug
    ON coding_domains (organization_id, slug)
    WHERE organization_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_coding_domains_active
    ON coding_domains (is_active, sort_order);

ALTER TABLE coding_tasks
    ADD COLUMN IF NOT EXISTS domain_id UUID REFERENCES coding_domains (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_coding_tasks_domain
    ON coding_tasks (domain_id, is_active);

ALTER TABLE interview_coding_configs
    ADD COLUMN IF NOT EXISTS domain_id UUID REFERENCES coding_domains (id) ON DELETE SET NULL;

COMMENT ON TABLE coding_domains IS
    'Language tracks for the coding bank. Selecting a domain locks the candidate editor to that language.';
COMMENT ON COLUMN coding_tasks.domain_id IS
    'Domain this problem belongs to (max 5 org-owned active problems per domain).';
COMMENT ON COLUMN interview_coding_configs.domain_id IS
    'Domain chosen at schedule time; candidate language is locked to domain.language.';

-- Seed global domains (unlocked for every org)
INSERT INTO coding_domains (id, organization_id, slug, name, language, description, sort_order)
SELECT
    'b1111111-1111-4111-8111-111111111101',
    NULL,
    'python',
    'Python',
    'python',
    'Python coding track. Candidate editor is locked to Python when this domain is selected.',
    1
WHERE NOT EXISTS (
    SELECT 1 FROM coding_domains WHERE slug = 'python' AND organization_id IS NULL
);

INSERT INTO coding_domains (id, organization_id, slug, name, language, description, sort_order)
SELECT
    'b1111111-1111-4111-8111-111111111102',
    NULL,
    'javascript',
    'JavaScript',
    'javascript',
    'JavaScript coding track. Candidate editor is locked to JavaScript when this domain is selected.',
    2
WHERE NOT EXISTS (
    SELECT 1 FROM coding_domains WHERE slug = 'javascript' AND organization_id IS NULL
);

-- Attach existing seed tasks to Python domain
UPDATE coding_tasks
SET domain_id = (
    SELECT id FROM coding_domains
    WHERE slug = 'python' AND organization_id IS NULL
    LIMIT 1
)
WHERE organization_id IS NULL
  AND slug IN ('second-largest', 'group-anagrams', 'meeting-rooms')
  AND domain_id IS NULL;
