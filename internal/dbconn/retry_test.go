package dbconn

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jack/jm-api-go/internal/config"
)

func testConfig() *config.Config {
	return &config.Config{
		DatabaseURL:                "postgres://localhost/test?sslmode=disable",
		DBConnectRetryEnabled:      true,
		DBConnectRetryMaxAttempts:  5,
		DBConnectRetryInitialDelay: 10 * time.Millisecond,
		DBConnectRetryMaxDelay:     40 * time.Millisecond,
	}
}

func TestConnectWithRetry_SucceedsAfterRetries(t *testing.T) {
	cfg := testConfig()
	var attempts int
	var slept []time.Duration

	pool, err := connectWithRetry(
		context.Background(),
		cfg,
		func(d time.Duration) { slept = append(slept, d) },
		func(_ context.Context, _ *pgxpool.Config) (*pgxpool.Pool, error) {
			attempts++
			if attempts < 3 {
				return nil, errors.New("db not ready")
			}
			return &pgxpool.Pool{}, nil
		},
		func(_ context.Context, _ *pgxpool.Pool) error { return nil },
	)

	require.NoError(t, err)
	require.NotNil(t, pool)
	assert.Equal(t, 3, attempts)
	assert.Equal(t, []time.Duration{10 * time.Millisecond, 20 * time.Millisecond}, slept)
}

func TestConnectWithRetry_FailsAfterMaxAttempts(t *testing.T) {
	cfg := testConfig()
	cfg.DBConnectRetryMaxAttempts = 3
	var attempts int

	pool, err := connectWithRetry(
		context.Background(),
		cfg,
		func(_ time.Duration) {},
		func(_ context.Context, _ *pgxpool.Config) (*pgxpool.Pool, error) {
			attempts++
			return nil, errors.New("db down")
		},
		func(_ context.Context, _ *pgxpool.Pool) error { return nil },
	)

	require.Error(t, err)
	assert.Nil(t, pool)
	assert.Equal(t, 3, attempts)
	assert.Contains(t, err.Error(), "failed after 3 attempt")
}

func TestConnectWithRetry_DisabledRetryAttemptsOnce(t *testing.T) {
	cfg := testConfig()
	cfg.DBConnectRetryEnabled = false
	var attempts int

	_, err := connectWithRetry(
		context.Background(),
		cfg,
		func(_ time.Duration) { t.Fatal("sleep should not be called when retry is disabled") },
		func(_ context.Context, _ *pgxpool.Config) (*pgxpool.Pool, error) {
			attempts++
			return nil, errors.New("db down")
		},
		func(_ context.Context, _ *pgxpool.Pool) error { return nil },
	)

	require.Error(t, err)
	assert.Equal(t, 1, attempts)
}

func TestBackoffDelay_CapsAtMax(t *testing.T) {
	initial := 1 * time.Second
	max := 5 * time.Second

	assert.Equal(t, 1*time.Second, backoffDelay(initial, max, 1))
	assert.Equal(t, 2*time.Second, backoffDelay(initial, max, 2))
	assert.Equal(t, 4*time.Second, backoffDelay(initial, max, 3))
	assert.Equal(t, 5*time.Second, backoffDelay(initial, max, 4))
	assert.Equal(t, 5*time.Second, backoffDelay(initial, max, 5))
}
