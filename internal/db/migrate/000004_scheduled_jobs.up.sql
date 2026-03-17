CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    task_type VARCHAR(128) NOT NULL,
    task_payload JSONB,
    cron_expression VARCHAR(128) NOT NULL,
    next_run_at TIMESTAMPTZ NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_update_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due ON scheduled_jobs (next_run_at) WHERE is_enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_enabled ON scheduled_jobs (is_enabled);
