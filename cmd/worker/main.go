package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/jack/jm-api-go/internal/config"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/observability"
	"github.com/jack/jm-api-go/internal/service"
)

func main() {
	if err := run(); err != nil {
		slog.Error("fatal error", "error", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("loading config: %w", err)
	}

	observability.SetupLogging(cfg.LogLevel, cfg.LogJSON, cfg.LogSampleRate)

	pool, err := pgxpool.New(context.Background(), cfg.DatabaseURL)
	if err != nil {
		return fmt.Errorf("connecting to database: %w", err)
	}
	defer pool.Close()

	queries := sqlc.New(pool)
	worker := service.NewWorkerService(queries)

	// Register task handlers
	worker.RegisterHandler("echo", func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error) {
		return payload, nil
	})

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	return worker.RunForever(ctx)
}
