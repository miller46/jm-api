package service

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type pgxQuerier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
}

type pgScheduledJobStore struct {
	db pgxQuerier
}

func NewPGScheduledJobStore(db pgxQuerier) scheduledJobStore {
	return &pgScheduledJobStore{db: db}
}

func (s *pgScheduledJobStore) CreateExecution(ctx context.Context, scheduledJobID string) (string, error) {
	const q = `
INSERT INTO scheduled_job_executions (job_id, started_at)
VALUES ($1, NOW())
RETURNING id`

	var executionID string
	if err := s.db.QueryRow(ctx, q, scheduledJobID).Scan(&executionID); err != nil {
		return "", fmt.Errorf("insert scheduled_job_executions: %w", err)
	}
	return executionID, nil
}

func (s *pgScheduledJobStore) MarkExecutionSuccess(ctx context.Context, executionID string, output string) error {
	const q = `
UPDATE scheduled_job_executions
SET completed_at = NOW(), success = true, output = $2
WHERE id = $1`

	if _, err := s.db.Exec(ctx, q, executionID, output); err != nil {
		return fmt.Errorf("update scheduled_job_executions success: %w", err)
	}
	return nil
}

func (s *pgScheduledJobStore) MarkExecutionFailure(ctx context.Context, executionID string, errMsg string) error {
	const q = `
UPDATE scheduled_job_executions
SET completed_at = NOW(), success = false, error_message = $2
WHERE id = $1`

	if _, err := s.db.Exec(ctx, q, executionID, errMsg); err != nil {
		return fmt.Errorf("update scheduled_job_executions failure: %w", err)
	}
	return nil
}

func (s *pgScheduledJobStore) UpdateScheduledJobRun(ctx context.Context, scheduledJobID string, lastErr *string) error {
	const q = `
UPDATE scheduled_jobs
SET last_run_at = NOW(), last_error = $2
WHERE id = $1`

	if _, err := s.db.Exec(ctx, q, scheduledJobID, lastErr); err != nil {
		return fmt.Errorf("update scheduled_jobs: %w", err)
	}
	return nil
}
