-- Browser proctoring for public coding rounds (/c/{token}).
-- Timer must not start until candidate clears the proctor gate (started_at nullable).

ALTER TABLE coding_submissions
    ALTER COLUMN started_at DROP NOT NULL;

ALTER TABLE coding_submissions
    ALTER COLUMN started_at DROP DEFAULT;

ALTER TABLE coding_submissions
    ADD COLUMN IF NOT EXISTS proctor_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN coding_submissions.started_at IS
    'Set when candidate clears proctor gate via POST /public/{token}/start; null until then.';
COMMENT ON COLUMN coding_submissions.proctor_summary_json IS
    'Aggregated integrity summary: risk, counts, last signals.';

CREATE TABLE IF NOT EXISTS coding_proctor_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id   UUID NOT NULL REFERENCES coding_submissions (id) ON DELETE CASCADE,
    event_type      VARCHAR(64) NOT NULL,
    severity        VARCHAR(16) NOT NULL DEFAULT 'info',
    detail_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    client_ts       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT coding_proctor_events_severity_valid CHECK (
        severity IN ('info', 'warn', 'critical')
    )
);

CREATE INDEX IF NOT EXISTS idx_coding_proctor_events_submission
    ON coding_proctor_events (submission_id, created_at);

CREATE INDEX IF NOT EXISTS idx_coding_proctor_events_type
    ON coding_proctor_events (event_type, created_at DESC);

COMMENT ON TABLE coding_proctor_events IS
    'Candidate coding proctor audit trail (camera, face, focus, input, display).';
