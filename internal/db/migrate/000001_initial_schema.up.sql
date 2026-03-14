-- Users table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(32) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_update_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Bots table
CREATE TABLE IF NOT EXISTS bots (
    id VARCHAR(32) PRIMARY KEY,
    rig_id VARCHAR(128) NOT NULL,
    last_run_at TIMESTAMPTZ,
    kill_switch BOOLEAN NOT NULL DEFAULT FALSE,
    last_run_log TEXT,
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_update_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bots_rig_id ON bots (rig_id);
CREATE INDEX IF NOT EXISTS idx_bots_kill_switch ON bots (kill_switch);
CREATE INDEX IF NOT EXISTS idx_bots_create_at ON bots (create_at);
CREATE INDEX IF NOT EXISTS idx_bots_last_update_at ON bots (last_update_at);
CREATE INDEX IF NOT EXISTS idx_bots_last_run_at ON bots (last_run_at);
CREATE INDEX IF NOT EXISTS idx_bots_rig_id_kill_switch ON bots (rig_id, kill_switch);
CREATE INDEX IF NOT EXISTS idx_bots_kill_switch_last_run_at ON bots (kill_switch, last_run_at);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(32) PRIMARY KEY,
    type VARCHAR(128) NOT NULL,
    payload JSONB,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    result JSONB,
    error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    processing_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_update_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks (type);
CREATE INDEX IF NOT EXISTS idx_tasks_create_at ON tasks (create_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status_create_at ON tasks (status, create_at);
CREATE INDEX IF NOT EXISTS idx_tasks_processing_started_at ON tasks (processing_started_at);

-- Webhooks table
CREATE TABLE IF NOT EXISTS webhooks (
    id VARCHAR(32) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_url VARCHAR(1024) NOT NULL,
    secret VARCHAR(255) NOT NULL,
    event_types JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_update_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_user_id ON webhooks (user_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_is_active ON webhooks (is_active);

-- Webhook delivery logs table
CREATE TABLE IF NOT EXISTS webhook_delivery_logs (
    id VARCHAR(32) PRIMARY KEY,
    webhook_id VARCHAR(32) NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    success BOOLEAN NOT NULL,
    attempts INTEGER NOT NULL,
    status_code INTEGER,
    response_body TEXT,
    error_message TEXT,
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_delivery_logs_webhook_id ON webhook_delivery_logs (webhook_id);
CREATE INDEX IF NOT EXISTS idx_webhook_delivery_logs_event_type ON webhook_delivery_logs (event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_delivery_logs_create_at ON webhook_delivery_logs (create_at);

-- Session tokens table
CREATE TABLE IF NOT EXISTS session_tokens (
    token_jti VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    rotated_from_jti VARCHAR(64),
    user_agent_hash VARCHAR(64),
    ip_subnet VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_session_tokens_user_id ON session_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_session_tokens_expires_at ON session_tokens (expires_at);
CREATE INDEX IF NOT EXISTS idx_session_tokens_rotated_from_jti ON session_tokens (rotated_from_jti);
