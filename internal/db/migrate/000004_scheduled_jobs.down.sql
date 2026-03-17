-- Down migration for scheduled_jobs
DROP TABLE IF EXISTS scheduled_job_executions;
DROP TABLE IF EXISTS scheduled_jobs;
