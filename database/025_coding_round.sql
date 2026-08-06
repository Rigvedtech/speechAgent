-- Coding round: task bank, per-interview config, and submissions (Monaco / technical round).

CREATE TABLE IF NOT EXISTS coding_tasks (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id    UUID REFERENCES organization (id) ON DELETE CASCADE,
    slug               VARCHAR(64) NOT NULL,
    title              VARCHAR(255) NOT NULL,
    difficulty         VARCHAR(20) NOT NULL DEFAULT 'medium',
    statement          TEXT NOT NULL,
    examples_json      JSONB NOT NULL DEFAULT '[]'::jsonb,
    constraints_text   TEXT NOT NULL DEFAULT '',
    starter_code_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    entry_function     VARCHAR(64),
    allowed_languages  TEXT[] NOT NULL DEFAULT ARRAY['python', 'javascript']::text[],
    skill_tags         TEXT[] NOT NULL DEFAULT '{}'::text[],
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT coding_tasks_difficulty_valid CHECK (
        difficulty IN ('easy', 'medium', 'hard')
    ),
    CONSTRAINT coding_tasks_title_nonempty CHECK (LENGTH(TRIM(title)) >= 2),
    CONSTRAINT coding_tasks_statement_nonempty CHECK (LENGTH(TRIM(statement)) >= 20),
    CONSTRAINT coding_tasks_slug_nonempty CHECK (LENGTH(TRIM(slug)) >= 2)
);

-- Global seed tasks: organization_id IS NULL, unique slug.
-- Org-specific tasks: unique (organization_id, slug).
CREATE UNIQUE INDEX IF NOT EXISTS uq_coding_tasks_global_slug
    ON coding_tasks (slug)
    WHERE organization_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_coding_tasks_org_slug
    ON coding_tasks (organization_id, slug)
    WHERE organization_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_coding_tasks_active
    ON coding_tasks (is_active, difficulty);

CREATE TABLE IF NOT EXISTS interview_coding_configs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id       UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    enabled            BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_languages  TEXT[] NOT NULL DEFAULT ARRAY['python', 'javascript']::text[],
    default_language   VARCHAR(32) NOT NULL DEFAULT 'python',
    task_ids           UUID[] NOT NULL DEFAULT '{}'::uuid[],
    assigned_task_id   UUID REFERENCES coding_tasks (id) ON DELETE SET NULL,
    time_limit_min     SMALLINT NOT NULL DEFAULT 25,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_coding_configs_interview_unique UNIQUE (interview_id),
    CONSTRAINT interview_coding_configs_time_range CHECK (
        time_limit_min BETWEEN 5 AND 180
    ),
    CONSTRAINT interview_coding_configs_default_lang_nonempty CHECK (
        LENGTH(TRIM(default_language)) >= 2
    ),
    CONSTRAINT interview_coding_configs_enabled_needs_task CHECK (
        enabled = FALSE OR assigned_task_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_interview_coding_configs_enabled
    ON interview_coding_configs (enabled)
    WHERE enabled = TRUE;

CREATE TABLE IF NOT EXISTS coding_submissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id    UUID REFERENCES interview_sessions (id) ON DELETE CASCADE,
    task_id         UUID NOT NULL REFERENCES coding_tasks (id) ON DELETE RESTRICT,
    organization_id UUID REFERENCES organization (id) ON DELETE CASCADE,
    language        VARCHAR(32) NOT NULL,
    code            TEXT NOT NULL DEFAULT '',
    status          VARCHAR(20) NOT NULL DEFAULT 'draft',
    score           NUMERIC(5, 2),
    review_notes    TEXT,
    is_demo         BOOLEAN NOT NULL DEFAULT FALSE,
    demo_token      VARCHAR(64),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT coding_submissions_status_valid CHECK (
        status IN ('draft', 'submitted', 'reviewed')
    ),
    CONSTRAINT coding_submissions_language_nonempty CHECK (
        LENGTH(TRIM(language)) >= 2
    ),
    CONSTRAINT coding_submissions_demo_or_interview CHECK (
        (is_demo = TRUE AND demo_token IS NOT NULL)
        OR (is_demo = FALSE AND interview_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_coding_submissions_demo_token
    ON coding_submissions (demo_token)
    WHERE demo_token IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_coding_submissions_interview_task
    ON coding_submissions (interview_id, task_id)
    WHERE interview_id IS NOT NULL AND is_demo = FALSE;

CREATE INDEX IF NOT EXISTS idx_coding_submissions_interview
    ON coding_submissions (interview_id)
    WHERE interview_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_coding_submissions_status
    ON coding_submissions (status, submitted_at DESC);

COMMENT ON TABLE coding_tasks IS
    'Coding problem bank for technical round (global seeds + optional org tasks).';
COMMENT ON TABLE interview_coding_configs IS
    'Per-interview coding round settings set at schedule time.';
COMMENT ON TABLE coding_submissions IS
    'Candidate code drafts/submissions; is_demo=true supports /coding/demo testing.';
COMMENT ON COLUMN interview_coding_configs.task_ids IS
    'Up to three task UUIDs prepared at schedule time; assigned_task_id is the one given to the candidate.';
