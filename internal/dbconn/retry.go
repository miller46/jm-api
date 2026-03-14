package dbconn

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/jack/jm-api-go/internal/config"
	"github.com/jack/jm-api-go/internal/observability"
)

type sleepFunc func(time.Duration)

type connectorFunc func(context.Context, *pgxpool.Config) (*pgxpool.Pool, error)

type pingFunc func(context.Context, *pgxpool.Pool) error

func ConnectWithRetry(ctx context.Context, cfg *config.Config) (*pgxpool.Pool, error) {
	return connectWithRetry(ctx, cfg, time.Sleep, pgxpool.NewWithConfig, pingPool)
}

func connectWithRetry(ctx context.Context, cfg *config.Config, sleep sleepFunc, connector connectorFunc, ping pingFunc) (*pgxpool.Pool, error) {
	poolConfig, err := pgxpool.ParseConfig(cfg.DatabaseURL)
	if err != nil {
		return nil, fmt.Errorf("parsing database URL: %w", err)
	}
	poolConfig.MaxConns = int32(cfg.DBPoolMaxConns)
	poolConfig.MinConns = int32(cfg.DBPoolMinConns)

	maxAttempts := cfg.DBConnectRetryMaxAttempts
	if !cfg.DBConnectRetryEnabled {
		maxAttempts = 1
	}

	for attempt := 1; attempt <= maxAttempts; attempt++ {
		pool, err := connector(ctx, poolConfig)
		if err == nil {
			err = ping(ctx, pool)
		}
		if err == nil {
			observability.ObserveDBConnectionAttempt("success")
			slog.Info("database connected", "attempt", attempt)
			return pool, nil
		}
		observability.ObserveDBConnectionAttempt("failure")
		if pool != nil {
			pool.Close()
		}

		if attempt == maxAttempts {
			return nil, fmt.Errorf("database connection failed after %d attempt(s): %w", attempt, err)
		}

		delay := backoffDelay(cfg.DBConnectRetryInitialDelay, cfg.DBConnectRetryMaxDelay, attempt)
		slog.Warn("database connection attempt failed; retrying", "attempt", attempt, "max_attempts", maxAttempts, "next_delay", delay, "error", err)
		sleep(delay)
	}

	return nil, fmt.Errorf("database connection failed")
}

func backoffDelay(initial, max time.Duration, attempt int) time.Duration {
	multiplier := math.Pow(2, float64(attempt-1))
	delay := time.Duration(float64(initial) * multiplier)
	if delay > max {
		return max
	}
	return delay
}

func pingPool(ctx context.Context, pool *pgxpool.Pool) error {
	return pool.Ping(ctx)
}
