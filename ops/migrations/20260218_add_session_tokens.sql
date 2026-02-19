-- Issue #61: persistent refresh-token session store
-- Apply this migration before deploying the new auth flow.

CREATE TABLE IF NOT EXISTS session_tokens (
    token_jti VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    rotated_from_jti VARCHAR(64) NULL
);

CREATE INDEX IF NOT EXISTS ix_session_tokens_user_id
    ON session_tokens (user_id);

CREATE INDEX IF NOT EXISTS ix_session_tokens_expires_at
    ON session_tokens (expires_at);

CREATE INDEX IF NOT EXISTS ix_session_tokens_rotated_from_jti
    ON session_tokens (rotated_from_jti);

-- Optional recurring cleanup job (PostgreSQL + pg_cron):
-- SELECT cron.schedule('cleanup_expired_session_tokens', '*/10 * * * *',
--   $$DELETE FROM session_tokens WHERE expires_at <= NOW()$$);
