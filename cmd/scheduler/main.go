package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/jack/jm-api-go/internal/config"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/dbconn"
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

	pool, err := dbconn.ConnectWithRetry(context.Background(), cfg)
	if err != nil {
		return fmt.Errorf("connecting to database: %w", err)
	}
	defer pool.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(pool, cfg.QueryTimeout))
	scheduler := service.NewSchedulerServiceFromSQLC(pool, queries, service.SchedulerConfig{
		PollIntervalSeconds: cfg.SchedulerPollIntervalSeconds,
		QueryLimit:          cfg.SchedulerQueryLimit,
		WorkerPoolSize:      cfg.SchedulerWorkerPoolSize,
	})

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	if err := scheduler.Start(ctx); err != nil {
		return err
	}

	<-ctx.Done()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
	defer cancel()
	return scheduler.Stop(shutdownCtx)
}
