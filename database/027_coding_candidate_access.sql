-- Candidate coding access token + multi-file workspace JSON.

ALTER TABLE interview_coding_configs
    ADD COLUMN IF NOT EXISTS access_token VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_interview_coding_configs_access_token
    ON interview_coding_configs (access_token)
    WHERE access_token IS NOT NULL;

ALTER TABLE coding_submissions
    ADD COLUMN IF NOT EXISTS workspace_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN interview_coding_configs.access_token IS
    'Public candidate link token for /c/{token} (no recruiter login).';
COMMENT ON COLUMN coding_submissions.workspace_json IS
    'Multi-file workspace: {files:{path:content}, activePath, entryPath}.';
