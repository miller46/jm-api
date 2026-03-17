package service

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type queryRowRecorder struct {
	err error
}

func (r *queryRowRecorder) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	id, ok := dest[0].(*string)
	if !ok {
		return errors.New("unexpected scan destination type")
	}
	*id = "execution-id"
	return nil
}

type pgxQuerierStub struct {
	lastQuery string
	lastArgs  []any
	rowErr    error
}

func (s *pgxQuerierStub) QueryRow(_ context.Context, sql string, args ...any) pgx.Row {
	s.lastQuery = sql
	s.lastArgs = args
	return &queryRowRecorder{err: s.rowErr}
}

func (s *pgxQuerierStub) Exec(_ context.Context, _ string, _ ...any) (pgconn.CommandTag, error) {
	return pgconn.CommandTag{}, nil
}

func TestPGScheduledJobStoreCreateExecutionUsesJobIDColumn(t *testing.T) {
	stub := &pgxQuerierStub{}
	store := NewPGScheduledJobStore(stub)

	id, err := store.CreateExecution(context.Background(), "job-123")
	if err != nil {
		t.Fatalf("CreateExecution returned error: %v", err)
	}
	if id != "execution-id" {
		t.Fatalf("expected execution-id, got %q", id)
	}
	if !strings.Contains(stub.lastQuery, "INSERT INTO scheduled_job_executions (job_id, started_at)") {
		t.Fatalf("expected query to insert into job_id column, query: %s", stub.lastQuery)
	}
}
