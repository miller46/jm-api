CREATE TABLE IF NOT EXISTS failed_tasks (
    id BIGSERIAL PRIMARY KEY,
    original_task_id VARCHAR(32) NOT NULL UNIQUE,
    task_type VARCHAR(128) NOT NULL,
    payload JSONB,
    error_message TEXT NOT NULL,
    error_stack TEXT,
    attempt_count INTEGER NOT NULL,
    final_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    create_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failed_tasks_task_type ON failed_tasks (task_type);
CREATE INDEX IF NOT EXISTS idx_failed_tasks_final_attempt_at ON failed_tasks (final_attempt_at);
CREATE INDEX IF NOT EXISTS idx_failed_tasks_create_at ON failed_tasks (create_at);
