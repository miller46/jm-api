-- Add soft delete support to scheduled_jobs
ALTER TABLE scheduled_jobs ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- Create index for efficient soft delete filtering
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_deleted_at ON scheduled_jobs(deleted_at) WHERE deleted_at IS NOT NULL;
