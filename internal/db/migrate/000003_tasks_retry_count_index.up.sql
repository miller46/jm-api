CREATE INDEX IF NOT EXISTS idx_tasks_retry_count_status ON tasks (retry_count, status);
