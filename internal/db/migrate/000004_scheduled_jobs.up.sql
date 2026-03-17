-- Migration to create scheduled_jobs table
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    job_type VARCHAR(100) NOT NULL,
    payload JSONB DEFAULT '{}',
    cron_expression VARCHAR(100) NOT NULL,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for efficient calendar queries
CREATE INDEX idx_scheduled_jobs_next_run_at ON scheduled_jobs(next_run_at);
CREATE INDEX idx_scheduled_jobs_enabled ON scheduled_jobs(enabled);
