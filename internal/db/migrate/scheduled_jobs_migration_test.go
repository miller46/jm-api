package migrate_test

import (
	"os"
	"strings"
	"testing"
)

func TestScheduledJobsMigrationContainsRequiredSchema(t *testing.T) {
	b, err := os.ReadFile("000004_scheduled_jobs.up.sql")
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	sql := string(b)

	required := []string{
		"CREATE TABLE IF NOT EXISTS scheduled_jobs",
		"is_enabled BOOLEAN NOT NULL DEFAULT TRUE",
		"payload JSONB NOT NULL DEFAULT '{}'",
		"CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run_at ON scheduled_jobs(next_run_at)",
		"CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_enabled ON scheduled_jobs(is_enabled)",
		"CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run_enabled ON scheduled_jobs(next_run_at, is_enabled)",
		"CREATE TABLE IF NOT EXISTS scheduled_job_executions",
		"job_id UUID NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE",
		"CREATE INDEX IF NOT EXISTS idx_job_executions_job_id ON scheduled_job_executions(job_id)",
		"CREATE INDEX IF NOT EXISTS idx_job_executions_started_at ON scheduled_job_executions(started_at)",
	}

	for _, fragment := range required {
		if !strings.Contains(sql, fragment) {
			t.Fatalf("migration missing required fragment: %s", fragment)
		}
	}
}
