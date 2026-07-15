-- Per-org ATS API key (encrypted at rest by the application).
-- Apply on existing DBs:
--   psql -U postgres -d prabhat_DB -f database/018_organization_ats_api_key.sql
--
-- App stores ciphertext only (e.g. Fernet). Never store plaintext API keys.
-- Decryption uses a server master key from env (e.g. ATS_SECRET_ENCRYPTION_KEY).

ALTER TABLE organization
    ADD COLUMN IF NOT EXISTS ats_api_key_encrypted TEXT;

COMMENT ON COLUMN organization.ats_api_key_encrypted IS
    'Encrypted ATS API key for this org (app-layer encrypt/decrypt). NULL = no key set. Never store plaintext.';

COMMENT ON COLUMN organization.ats_config IS
    'Non-secret ATS settings (base_url, paths, field maps). Secrets go in ats_api_key_encrypted.';
