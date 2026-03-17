-- Revert soft delete support
DROP INDEX IF EXISTS idx_scheduled_jobs_deleted_at;
ALTER TABLE scheduled_jobs DROP COLUMN IF EXISTS deleted_at;
