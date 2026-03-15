package sqlc

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type stubDBTX struct {
	execFn     func(context.Context, string, ...interface{}) (pgconn.CommandTag, error)
	queryFn    func(context.Context, string, ...interface{}) (pgx.Rows, error)
	queryRowFn func(context.Context, string, ...interface{}) pgx.Row
}

func (s *stubDBTX) Exec(ctx context.Context, q string, args ...interface{}) (pgconn.CommandTag, error) {
	return s.execFn(ctx, q, args...)
}

func (s *stubDBTX) Query(ctx context.Context, q string, args ...interface{}) (pgx.Rows, error) {
	return s.queryFn(ctx, q, args...)
}

func (s *stubDBTX) QueryRow(ctx context.Context, q string, args ...interface{}) pgx.Row {
	return s.queryRowFn(ctx, q, args...)
}

type stubRows struct {
	closed bool
	next   bool
}

func (s *stubRows) Close()                                       { s.closed = true }
func (s *stubRows) Err() error                                   { return nil }
func (s *stubRows) CommandTag() pgconn.CommandTag                { return pgconn.CommandTag{} }
func (s *stubRows) FieldDescriptions() []pgconn.FieldDescription { return nil }
func (s *stubRows) Next() bool {
	if s.next {
		s.next = false
		return true
	}
	return false
}
func (s *stubRows) Scan(dest ...interface{}) error { return nil }
func (s *stubRows) Values() ([]interface{}, error) { return nil, nil }
func (s *stubRows) RawValues() [][]byte            { return nil }
func (s *stubRows) Conn() *pgx.Conn                { return nil }

type stubRow struct {
	scanCalled *bool
}

func (s *stubRow) Scan(dest ...interface{}) error {
	*s.scanCalled = true
	return nil
}

func TestWithQueryTimeout_ExecAddsDeadline(t *testing.T) {
	t.Parallel()

	wrapped := WithQueryTimeout(&stubDBTX{
		execFn: func(ctx context.Context, _ string, _ ...interface{}) (pgconn.CommandTag, error) {
			deadline, ok := ctx.Deadline()
			require.True(t, ok)
			remaining := time.Until(deadline)
			assert.LessOrEqual(t, remaining, 150*time.Millisecond)
			assert.Greater(t, remaining, 0*time.Millisecond)
			return pgconn.CommandTag{}, nil
		},
		queryFn: func(context.Context, string, ...interface{}) (pgx.Rows, error) { return nil, nil },
		queryRowFn: func(context.Context, string, ...interface{}) pgx.Row {
			return &stubRow{scanCalled: new(bool)}
		},
	}, 150*time.Millisecond)

	_, err := wrapped.Exec(context.Background(), "SELECT 1")
	require.NoError(t, err)
}

func TestWithQueryTimeout_QueryCancelsOnClose(t *testing.T) {
	t.Parallel()

	rows := &stubRows{}
	var capturedCtx context.Context
	wrapped := WithQueryTimeout(&stubDBTX{
		execFn: func(context.Context, string, ...interface{}) (pgconn.CommandTag, error) {
			return pgconn.CommandTag{}, nil
		},
		queryFn: func(ctx context.Context, _ string, _ ...interface{}) (pgx.Rows, error) {
			capturedCtx = ctx
			return rows, nil
		},
		queryRowFn: func(context.Context, string, ...interface{}) pgx.Row {
			return &stubRow{scanCalled: new(bool)}
		},
	}, time.Second)

	qRows, err := wrapped.Query(context.Background(), "SELECT 1")
	require.NoError(t, err)
	require.NotNil(t, capturedCtx)
	select {
	case <-capturedCtx.Done():
		t.Fatal("context should not be canceled before rows are closed")
	default:
	}

	qRows.Close()
	assert.True(t, rows.closed)
	select {
	case <-capturedCtx.Done():
		assert.ErrorIs(t, capturedCtx.Err(), context.Canceled)
	default:
		t.Fatal("expected query context to be canceled after rows.Close")
	}
}

func TestWithQueryTimeout_QueryRowCancelsOnScan(t *testing.T) {
	t.Parallel()

	var capturedCtx context.Context
	scanCalled := false
	wrapped := WithQueryTimeout(&stubDBTX{
		execFn: func(context.Context, string, ...interface{}) (pgconn.CommandTag, error) {
			return pgconn.CommandTag{}, nil
		},
		queryFn: func(context.Context, string, ...interface{}) (pgx.Rows, error) { return &stubRows{}, nil },
		queryRowFn: func(ctx context.Context, _ string, _ ...interface{}) pgx.Row {
			capturedCtx = ctx
			return &stubRow{scanCalled: &scanCalled}
		},
	}, time.Second)

	row := wrapped.QueryRow(context.Background(), "SELECT 1")
	select {
	case <-capturedCtx.Done():
		t.Fatal("context should not be canceled before Scan")
	default:
	}

	err := row.Scan()
	require.NoError(t, err)
	assert.True(t, scanCalled)
	select {
	case <-capturedCtx.Done():
		assert.ErrorIs(t, capturedCtx.Err(), context.Canceled)
	default:
		t.Fatal("expected query row context to be canceled after Scan")
	}
}

func TestWithQueryTimeout_QueryErrorCancelsContext(t *testing.T) {
	t.Parallel()

	boom := errors.New("boom")
	var capturedCtx context.Context
	wrapped := WithQueryTimeout(&stubDBTX{
		execFn: func(context.Context, string, ...interface{}) (pgconn.CommandTag, error) {
			return pgconn.CommandTag{}, nil
		},
		queryFn: func(ctx context.Context, _ string, _ ...interface{}) (pgx.Rows, error) {
			capturedCtx = ctx
			return nil, boom
		},
		queryRowFn: func(context.Context, string, ...interface{}) pgx.Row { return nil },
	}, time.Second)

	_, err := wrapped.Query(context.Background(), "SELECT 1")
	require.ErrorIs(t, err, boom)
	select {
	case <-capturedCtx.Done():
		assert.ErrorIs(t, capturedCtx.Err(), context.Canceled)
	default:
		t.Fatal("expected query context to be canceled on query error")
	}
}

var _ pgx.Rows = (*stubRows)(nil)
var _ pgx.Row = (*stubRow)(nil)
var _ DBTX = (*stubDBTX)(nil)
