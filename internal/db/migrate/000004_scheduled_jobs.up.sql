-- Migration to create scheduled jobs tables
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    job_type VARCHAR(100) NOT NULL,
    cron_expression VARCHAR(255) NOT NULL,
    next_run_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}',
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run_at ON scheduled_jobs(next_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_enabled ON scheduled_jobs(is_enabled);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run_enabled ON scheduled_jobs(next_run_at, is_enabled);

CREATE TABLE IF NOT EXISTS scheduled_job_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    success BOOLEAN,
    output TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_executions_job_id ON scheduled_job_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_job_executions_started_at ON scheduled_job_executions(started_at);
