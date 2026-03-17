CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    payload JSONB,
    last_run_at TIMESTAMPTZ,
    last_error TEXT,
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_update_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_name ON scheduled_jobs (name);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_last_run_at ON scheduled_jobs (last_run_at);

CREATE TABLE IF NOT EXISTS scheduled_job_executions (
    id VARCHAR(32) PRIMARY KEY DEFAULT md5(random()::text || clock_timestamp()::text),
    scheduled_job_id VARCHAR(32) NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    success BOOLEAN,
    output TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_scheduled_job_executions_scheduled_job_id ON scheduled_job_executions (scheduled_job_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_job_executions_started_at ON scheduled_job_executions (started_at);
