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

-- Indexes for calendar and scheduler lookups
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run_at ON scheduled_jobs(next_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_enabled ON scheduled_jobs(enabled);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due ON scheduled_jobs (next_run_at) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_name ON scheduled_jobs (name);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_last_run_at ON scheduled_jobs (last_run_at);

CREATE TABLE IF NOT EXISTS scheduled_job_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheduled_job_id UUID NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    success BOOLEAN,
    output TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_scheduled_job_executions_scheduled_job_id ON scheduled_job_executions (scheduled_job_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_job_executions_started_at ON scheduled_job_executions (started_at);
