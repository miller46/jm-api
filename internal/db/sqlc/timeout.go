package sqlc

import (
	"context"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

// WithQueryTimeout wraps DB operations with a per-query timeout.
func WithQueryTimeout(db DBTX, timeout time.Duration) DBTX {
	if timeout <= 0 {
		return db
	}
	return &timeoutDB{db: db, timeout: timeout}
}

type timeoutDB struct {
	db      DBTX
	timeout time.Duration
}

func (t *timeoutDB) Exec(ctx context.Context, query string, args ...interface{}) (pgconn.CommandTag, error) {
	timeoutCtx, cancel := context.WithTimeout(ctx, t.timeout)
	defer cancel()
	return t.db.Exec(timeoutCtx, query, args...)
}

func (t *timeoutDB) Query(ctx context.Context, query string, args ...interface{}) (pgx.Rows, error) {
	timeoutCtx, cancel := context.WithTimeout(ctx, t.timeout)
	rows, err := t.db.Query(timeoutCtx, query, args...)
	if err != nil {
		cancel()
		return nil, err
	}
	return &rowsWithCancel{Rows: rows, cancel: cancel}, nil
}

func (t *timeoutDB) QueryRow(ctx context.Context, query string, args ...interface{}) pgx.Row {
	timeoutCtx, cancel := context.WithTimeout(ctx, t.timeout)
	row := t.db.QueryRow(timeoutCtx, query, args...)
	return &rowWithCancel{row: row, cancel: cancel}
}

type rowsWithCancel struct {
	pgx.Rows
	cancelOnce sync.Once
	cancel     context.CancelFunc
}

func (r *rowsWithCancel) Close() {
	r.Rows.Close()
	r.cancelOnce.Do(r.cancel)
}

func (r *rowsWithCancel) Next() bool {
	next := r.Rows.Next()
	if !next {
		r.cancelOnce.Do(r.cancel)
	}
	return next
}

type rowWithCancel struct {
	row    pgx.Row
	cancel context.CancelFunc
}

func (r *rowWithCancel) Scan(dest ...interface{}) error {
	defer r.cancel()
	return r.row.Scan(dest...)
}
