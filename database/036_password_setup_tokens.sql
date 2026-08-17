-- One-time hashed tokens for invite / set-password links.
-- Raw token is emailed once and never stored.

CREATE TABLE IF NOT EXISTS password_setup_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash  CHAR(64) NOT NULL,
    purpose     VARCHAR(32) NOT NULL DEFAULT 'invite',
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT password_setup_tokens_purpose_valid CHECK (
        purpose IN ('invite')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_password_setup_tokens_hash
    ON password_setup_tokens (token_hash);

CREATE INDEX IF NOT EXISTS idx_password_setup_tokens_user_unused
    ON password_setup_tokens (user_id)
    WHERE used_at IS NULL;

COMMENT ON TABLE password_setup_tokens IS
    'HMAC-SHA256 hashes of one-time set-password tokens. Raw tokens are never stored.';
